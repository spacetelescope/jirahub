import logging
import dataclasses

from .entities import Source, Metadata, CommentMetadata
from .config import SyncFeature
from .utils import UrlHelper

from . import jira, github


__all__ = ["IssueSync"]


logger = logging.getLogger(__name__)


_DEFAULT_ISSUE_TYPE = "Task"


class IssueSync:
    @classmethod
    def from_config(cls, config, dry_run=False):
        jira_client = jira.Client.from_config(config)
        github_client = github.Client.from_config(config)

        return cls(config=config, jira_client=jira_client, github_client=github_client, dry_run=dry_run)

    def __init__(self, config, jira_client, github_client, dry_run=False):
        self._config = config

        self._client_by_source = {Source.JIRA: jira_client, Source.GITHUB: github_client}

        self.url_helper = UrlHelper.from_config(config)

        self._formatter_by_source = {
            Source.JIRA: jira.Formatter(config, self.url_helper, self.get_client(Source.GITHUB)),
            Source.GITHUB: github.Formatter(config, self.url_helper, self.get_client(Source.JIRA)),
        }

        self.dry_run = dry_run

    def get_source_config(self, source):
        return self._config.get_source_config(source)

    def get_client(self, source):
        return self._client_by_source[source]

    def get_formatter(self, source):
        return self._formatter_by_source[source]

    def get_project(self, source):
        if source == Source.JIRA:
            return self._config.jira.project_key
        else:
            return self._config.github.repository

    def accept_issue(self, source, issue):
        if issue.is_bot:
            return False

        issue_filter = self._config.get_source_config(source).issue_filter
        if issue_filter:
            return issue_filter(issue)
        else:
            return False

    def sync_feature_enabled(self, source, sync_feature):
        return self._config.is_enabled(source, sync_feature)

    def find_issues(self, min_updated_at=None, retry_issues=None):
        yield from self.get_client(Source.JIRA).find_issues(min_updated_at)
        yield from self.get_client(Source.GITHUB).find_issues(min_updated_at)

        if retry_issues is not None:
            for source, issue_id in retry_issues:
                yield self.get_client(source).get_issue(issue_id)

    def perform_sync(self, min_updated_at=None, retry_issues=None):
        if min_updated_at:
            assert min_updated_at.tzinfo is not None

        seen = set()
        failed = set()

        for updated_issue in self.find_issues(min_updated_at, retry_issues=retry_issues):
            if (updated_issue.source, updated_issue.issue_id) in seen:
                continue

            try:
                other_issue = self._perform_sync_issue(updated_issue)
            except Exception:
                logger.exception("Failed syncing %s", updated_issue)
                failed.add((updated_issue.source, updated_issue.issue_id))
            else:
                seen.add((updated_issue.source, updated_issue.issue_id))
                if other_issue:
                    seen.add((other_issue.source, other_issue.issue_id))

        return failed

    def _perform_sync_issue(self, updated_issue):
        other_source = updated_issue.source.other

        if (
            updated_issue.source == Source.JIRA
            and updated_issue.metadata.github_repository
            and updated_issue.metadata.github_repository != self._config.github.repository
        ):
            logger.info(
                "%s was updated, but linked repository (%s) does not match configured repository (%s)",
                updated_issue,
                updated_issue.metadata.github_repository,
                self._config.github.repository,
            )
            return None

        other_issue = self.get_client(other_source).find_other_issue(updated_issue)
        if other_issue:
            updated_issue_updates, other_issue_updates = self.make_issue_updates(updated_issue, other_issue)

            if updated_issue_updates:
                logger.info("Updating %s: %s", updated_issue, updated_issue_updates)
                if not self.dry_run:
                    updated_issue = self.get_client(updated_issue.source).update_issue(
                        updated_issue, updated_issue_updates
                    )
                else:
                    logger.info("Skipping issue update due to dry run")

            if other_issue_updates:
                logger.info("Updating %s: %s", other_issue, other_issue_updates)
                if not self.dry_run:
                    other_issue = self.get_client(other_issue.source).update_issue(other_issue, other_issue_updates)
                else:
                    logger.info("Skipping issue update due to dry run")

            self.sync_comments(updated_issue, other_issue)

            return other_issue
        elif self.accept_issue(other_source, updated_issue):
            mirror_issue_fields = self.make_mirror_issue(updated_issue)

            for hook in self.get_source_config(other_source).before_issue_create:
                mirror_issue_fields = hook(updated_issue, mirror_issue_fields)

            logger.info("Creating mirror of %s: %s", updated_issue, mirror_issue_fields)
            if not self.dry_run:
                mirror_issue = self.get_client(other_source).create_issue(mirror_issue_fields)

                updated_issue_updates, _ = self.make_issue_updates(updated_issue, mirror_issue)
                if updated_issue_updates:
                    logger.info("Updating %s: %s", updated_issue, updated_issue_updates)
                    updated_issue = self.get_client(updated_issue.source).update_issue(
                        updated_issue, updated_issue_updates
                    )

                self.sync_comments(updated_issue, mirror_issue)
                return mirror_issue
            else:
                logger.info("Skipping issue create due to dry run")
                return None
        else:
            return None

    def make_issue_updates(self, issue_one, issue_two):
        one_updates = {}
        two_updates = {}

        if issue_one.is_bot or issue_two.is_bot:
            if issue_one.is_bot:
                source_issue = issue_two
                mirror_issue = issue_one
                mirror_updates = one_updates
            else:
                source_issue = issue_one
                mirror_issue = issue_two
                mirror_updates = two_updates

            expected_mirror_title = self.make_mirror_issue_title(source_issue)
            if expected_mirror_title != mirror_issue.title:
                mirror_updates["title"] = expected_mirror_title

            expected_mirror_body = self.make_mirror_issue_body(source_issue)
            if expected_mirror_body != mirror_issue.body:
                mirror_updates["body"] = expected_mirror_body

        fields = [
            ("is_open", SyncFeature.SYNC_STATUS),
            ("milestones", SyncFeature.SYNC_MILESTONES),
            ("labels", SyncFeature.SYNC_LABELS),
        ]

        for field_name, sync_feature in fields:
            one_field_updates, two_field_updates = self._make_field_updates(
                issue_one, issue_two, field_name, sync_feature
            )
            one_updates.update(one_field_updates)
            two_updates.update(two_field_updates)

        if issue_one.source == Source.JIRA:
            jira_issue = issue_one
            jira_updates = one_updates
            github_issue = issue_two
        else:
            jira_issue = issue_two
            jira_updates = two_updates
            github_issue = issue_one

        if (
            jira_issue.metadata.github_repository != github_issue.project
            or jira_issue.metadata.github_issue_id != github_issue.issue_id
        ):
            metadata = Metadata(
                github_repository=github_issue.project,
                github_issue_id=github_issue.issue_id,
                comments=jira_issue.metadata.comments,
            )
            jira_updates["metadata"] = metadata

        return one_updates, two_updates

    def _make_field_updates(self, issue_one, issue_two, field_name, sync_feature):
        one_enabled = self.sync_feature_enabled(issue_one.source, sync_feature)
        two_enabled = self.sync_feature_enabled(issue_two.source, sync_feature)

        one_updates = {}
        two_updates = {}

        if one_enabled or two_enabled:
            one_value = getattr(issue_one, field_name)
            two_value = getattr(issue_two, field_name)

            if not one_value == two_value:
                if one_enabled and two_enabled:
                    if issue_one.updated_at > issue_two.updated_at:
                        two_updates[field_name] = one_value
                    else:
                        one_updates[field_name] = two_value
                elif one_enabled:
                    one_updates[field_name] = two_value
                elif two_enabled:
                    two_updates[field_name] = one_value

        return one_updates, two_updates

    def sync_comments(self, issue_one, issue_two):
        if issue_one.source == Source.JIRA:
            jira_issue = issue_one
        else:
            jira_issue = issue_two

        rebuild_comment_metadata = False

        tracking_comment_ids_by_source = {
            Source.GITHUB: jira_issue.metadata.github_tracking_comment_id,
            Source.JIRA: jira_issue.metadata.jira_tracking_comment_id,
        }

        for issue, other_issue in [(issue_one, issue_two), (issue_two, issue_one)]:
            if self.get_source_config(issue.source).create_tracking_comment and not issue.is_bot:
                tracking_comment_id = tracking_comment_ids_by_source[issue.source]
                tracking_comment = next((c for c in issue.comments if c.comment_id == tracking_comment_id), None)

                if tracking_comment is None:
                    tracking_comment_fields = self.make_tracking_comment(other_issue)

                    logger.info("Creating tracking comment on %s: %s", issue, tracking_comment_fields)

                    if not self.dry_run:
                        tracking_comment = self.get_client(issue.source).create_comment(issue, tracking_comment_fields)
                        tracking_comment_ids_by_source[issue.source] = tracking_comment.comment_id
                    else:
                        logger.info("Skipping comment create due to dry run")

                    rebuild_comment_metadata = True
                else:
                    expected_comment_body = self.make_tracking_comment_body(other_issue)
                    if tracking_comment.body != expected_comment_body:
                        tracking_comment_updates = {"body": expected_comment_body}

                        logger.info("Updating %s on %s: %s", tracking_comment, issue, tracking_comment_updates)

                        if not self.dry_run:
                            self.get_client(issue.source).update_comment(tracking_comment, tracking_comment_updates)
                        else:
                            logger.info("Skipping comment update due to dry run")

        tracking_comment_ids = set(tracking_comment_ids_by_source.values())
        issue_one_comments = [
            (issue_one, c, issue_two) for c in issue_one.comments if c.comment_id not in tracking_comment_ids
        ]
        issue_two_comments = [
            (issue_two, c, issue_one) for c in issue_two.comments if c.comment_id not in tracking_comment_ids
        ]
        all_comments = issue_one_comments + issue_two_comments
        comments_by_id = {(c.source, c.comment_id): c for _, c, _ in all_comments}

        comments_by_linked_id = {}
        for comment_metadata in jira_issue.metadata.comments:
            jira_comment = comments_by_id.get((Source.JIRA, comment_metadata.jira_comment_id))
            github_comment = comments_by_id.get((Source.GITHUB, comment_metadata.github_comment_id))

            if jira_comment and github_comment:
                comments_by_linked_id[(Source.JIRA, jira_comment.comment_id)] = github_comment
                comments_by_linked_id[(Source.GITHUB, github_comment.comment_id)] = jira_comment
            else:
                rebuild_comment_metadata = True

        for issue, comment, other_issue in all_comments:
            try:
                if comment.is_bot:
                    source_comment = comments_by_linked_id.get((comment.source, comment.comment_id))
                    if not source_comment and self.sync_feature_enabled(comment.source, SyncFeature.SYNC_COMMENTS):
                        logger.info("Deleting %s on %s", comment, issue)

                        if not self.dry_run:
                            self.get_client(comment.source).delete_comment(comment)
                        else:
                            logger.info("Skipping comment delete due to dry run")

                        rebuild_comment_metadata = True
                else:
                    mirror_comment = comments_by_linked_id.get((comment.source, comment.comment_id))
                    if mirror_comment:
                        if self.sync_feature_enabled(mirror_comment.source, SyncFeature.SYNC_COMMENTS):
                            expected_mirror_body = self.make_mirror_comment_body(issue, comment)
                            if mirror_comment.body != expected_mirror_body:
                                mirror_comment_updates = {"body": expected_mirror_body}

                                logger.info(
                                    "Updating %s on %s: %s", mirror_comment, other_issue, mirror_comment_updates
                                )

                                if not self.dry_run:
                                    self.get_client(other_issue.source).update_comment(
                                        mirror_comment, mirror_comment_updates
                                    )
                                else:
                                    logger.info("Skipping comment update due to dry run")

                    else:
                        if self.sync_feature_enabled(other_issue.source, SyncFeature.SYNC_COMMENTS):
                            mirror_comment_fields = self.make_mirror_comment(issue, comment, other_issue)

                            logger.info("Creating comment on %s: %s", other_issue, mirror_comment_fields)

                            if not self.dry_run:
                                mirror_comment = self.get_client(other_issue.source).create_comment(
                                    other_issue, mirror_comment_fields
                                )
                                comments_by_linked_id[(mirror_comment.source, mirror_comment.comment_id)] = comment
                                comments_by_linked_id[(comment.source, comment.comment_id)] = mirror_comment
                            else:
                                logger.info("Skipping comment create due to dry run")

                            rebuild_comment_metadata = True
            except Exception:
                logger.exception("Failed syncing %s", comment)

        if rebuild_comment_metadata:
            new_comment_metadata_list = []
            for (source, comment_id), comment in comments_by_linked_id.items():
                if source == Source.JIRA:
                    new_comment_metadata_list.append(
                        CommentMetadata(jira_comment_id=comment_id, github_comment_id=comment.comment_id)
                    )

            kwargs = dataclasses.asdict(jira_issue.metadata)
            kwargs["comments"] = new_comment_metadata_list
            kwargs["jira_tracking_comment_id"] = tracking_comment_ids_by_source[Source.JIRA]
            kwargs["github_tracking_comment_id"] = tracking_comment_ids_by_source[Source.GITHUB]

            new_metadata = Metadata(**kwargs)

            if not self.dry_run:
                self.get_client(Source.JIRA).update_issue(jira_issue, {"metadata": new_metadata})
            else:
                logger.info("Skipping comment metadata update due to dry run")

    def make_mirror_comment(self, source_issue, source_comment, mirror_issue):
        fields = {}

        fields["body"] = self.make_mirror_comment_body(source_issue, source_comment)

        return fields

    def make_tracking_comment(self, source_issue):
        fields = {}

        fields["body"] = self.make_tracking_comment_body(source_issue)

        return fields

    def make_mirror_issue(self, source_issue):
        mirror_source = source_issue.source.other

        fields = {}

        fields["title"] = self.make_mirror_issue_title(source_issue)
        fields["body"] = self.make_mirror_issue_body(source_issue)

        if self.sync_feature_enabled(mirror_source, SyncFeature.SYNC_LABELS):
            fields["labels"] = source_issue.labels.copy()

        if self.sync_feature_enabled(mirror_source, SyncFeature.SYNC_MILESTONES):
            fields["milestones"] = source_issue.milestones.copy()

        if mirror_source == Source.JIRA:
            fields["issue_type"] = _DEFAULT_ISSUE_TYPE

            metadata = Metadata(github_repository=source_issue.project, github_issue_id=source_issue.issue_id)
            fields["metadata"] = metadata

        return fields

    def make_mirror_issue_title(self, source_issue):
        title = self.redact_text(source_issue.source.other, source_issue.title)

        custom_formatter = self.get_source_config(source_issue.source.other).issue_title_formatter
        if custom_formatter:
            return custom_formatter(source_issue, title)
        else:
            return title

    def make_mirror_issue_body(self, source_issue):
        mirror_source = source_issue.source.other
        formatter = self.get_formatter(mirror_source)

        body = self.redact_text(mirror_source, source_issue.body)
        body = formatter.format_body(body)

        custom_formatter = self.get_source_config(mirror_source).issue_body_formatter
        if custom_formatter:
            return custom_formatter(source_issue, body)
        else:
            user_url = self.url_helper.get_user_profile_url(source_issue.user)
            user_link = formatter.format_link(user_url, source_issue.user.display_name)

            if source_issue.source == Source.JIRA:
                link_text = f"{source_issue.issue_id}"
            else:
                link_text = f"#{source_issue.issue_id}"

            issue_url = self.url_helper.get_issue_url(source_issue)
            issue_link = formatter.format_link(issue_url, link_text)

            return f"_Issue {issue_link} was created on {source_issue.source} by {user_link}:_\r\n\r\n{body}"

    def make_mirror_comment_body(self, source_issue, source_comment):
        mirror_source = source_comment.source.other
        formatter = self.get_formatter(mirror_source)

        body = self.redact_text(mirror_source, source_comment.body)
        body = formatter.format_body(body)

        custom_formatter = self.get_source_config(mirror_source).comment_body_formatter
        if custom_formatter:
            return custom_formatter(source_issue, source_comment, body)
        else:
            user_url = self.url_helper.get_user_profile_url(source_comment.user)
            user_link = formatter.format_link(user_url, source_comment.user.display_name)

            comment_url = self.url_helper.get_comment_url(source_issue, source_comment)
            comment_link = formatter.format_link(comment_url, str(source_issue.source))

            return f"_Comment by {user_link} on {comment_link}:_\r\n\r\n{body}"

    def make_tracking_comment_body(self, source_issue):
        mirror_source = source_issue.source.other
        formatter = self.get_formatter(mirror_source)

        if source_issue.source == Source.JIRA:
            link_text = f"{source_issue.issue_id}"
        else:
            link_text = f"#{source_issue.issue_id}"

        issue_url = self.url_helper.get_issue_url(source_issue)
        issue_link = formatter.format_link(issue_url, link_text)

        return f"_This issue is tracked on {source_issue.source} as {issue_link}._"

    def redact_text(self, source, text):
        for pattern in self.get_source_config(source).redact_patterns:
            for match in pattern.finditer(text):
                text = text[: match.start()] + "\u2588" * (match.end() - match.start()) + text[match.end() :]

        return text
