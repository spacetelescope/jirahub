import logging

from .entities import Source, MetadataField
from .config import SyncFeature
from .utils import UrlHelper

from . import jira, github


__all__ = ["IssueSync"]


logger = logging.getLogger(__name__)


class _IssueFilter:
    def __init__(self, filter_config):
        self._filter_config = filter_config

    def accept(self, issue):
        if self._filter_config.open_only and not issue.is_open:
            return False

        if self._filter_config.min_created_at:
            if issue.created_at < self._filter_config.min_created_at:
                return False

        if self._filter_config.include_issue_types:
            if issue.issue_type not in self._filter_config.include_issue_types:
                return False

        if self._filter_config.exclude_issue_types:
            if issue.issue_type in self._filter_config.exclude_issue_types:
                return False

        if self._filter_config.include_components:
            if not self._filter_config.include_components.intersection(issue.components):
                return False

        if self._filter_config.exclude_components:
            if self._filter_config.exclude_components.intersection(issue.components):
                return False

        if self._filter_config.include_labels:
            if not self._filter_config.include_labels.intersection(issue.labels):
                return False

        if self._filter_config.exclude_labels:
            if self._filter_config.exclude_labels.intersection(issue.labels):
                return False

        return True


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
        self._issue_filter_by_source = {
            Source.JIRA: _IssueFilter(config.jira.filter),
            Source.GITHUB: _IssueFilter(config.github.filter),
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
        return self._issue_filter_by_source[source].accept(issue)

    def sync_feature_enabled(self, source, sync_feature):
        return self._config.is_enabled(source, sync_feature)

    def find_updated_issues(self, min_updated_at=None):
        yield from self.get_client(Source.JIRA).find_issues(min_updated_at)
        yield from self.get_client(Source.GITHUB).find_issues(min_updated_at)

    def perform_sync(self, min_updated_at=None):
        if min_updated_at:
            assert min_updated_at.tzinfo is not None

        seen = set()

        for updated_issue in self.find_updated_issues(min_updated_at):
            if (updated_issue.source, updated_issue.issue_id) in seen:
                continue

            try:
                other_issue = self._perform_sync_issue(updated_issue)
            except Exception:
                logger.exception("Failed syncing %s", updated_issue)
            else:
                seen.add((updated_issue.source, updated_issue.issue_id))
                if other_issue:
                    seen.add((other_issue.source, other_issue.issue_id))

    def _perform_sync_issue(self, updated_issue):
        other_source = updated_issue.source.other

        if updated_issue.mirror_id or updated_issue.github_issue_id:
            if updated_issue.mirror_id:
                if updated_issue.mirror_project != self.get_project(other_source):
                    logger.info("%s was updated, but is mirrored in a different project/repository", updated_issue)
                    return None

                other_issue = self.get_client(other_source).get_issue(updated_issue.mirror_id)
            else:
                assert updated_issue.source == Source.JIRA

                if (
                    self._config.jira.github_repository_field
                    and updated_issue.github_repository != self._config.github.repository
                ):
                    logger.info(
                        "%s was updated, but repository field (%s) does not match configured repository (%s)",
                        updated_issue,
                        updated_issue.github_repository,
                        self._config.github.repository,
                    )
                    return None

                other_issue = self.get_client(other_source).get_issue(updated_issue.github_issue_id)

            updated_issue_updates, other_issue_updates = self.make_issue_updates(updated_issue, other_issue)

            if updated_issue_updates:
                logger.info("Updating %s: %s", updated_issue, updated_issue_updates)
                if not self.dry_run:
                    self.get_client(updated_issue.source).update_issue(updated_issue, updated_issue_updates)
                else:
                    logger.info("Skipping issue update due to dry run")

            if other_issue_updates:
                logger.info("Updating %s: %s", other_issue, other_issue_updates)
                if not self.dry_run:
                    self.get_client(other_issue.source).update_issue(other_issue, other_issue_updates)
                else:
                    logger.info("Skipping issue update due to dry run")

            if not updated_issue.is_bot and not updated_issue.tracking_comment:
                self._create_tracking_comment(updated_issue, other_issue)

            if not other_issue.is_bot and not other_issue.tracking_comment:
                self._create_tracking_comment(other_issue, updated_issue)

            self.sync_comments(updated_issue, other_issue)

            return other_issue
        else:
            if self.sync_feature_enabled(other_source, SyncFeature.CREATE_ISSUES) and self.accept_issue(
                other_source, updated_issue
            ):
                mirror_issue_fields = self.make_mirror_issue(updated_issue)

                logger.info("Creating mirror of %s: %s", updated_issue, mirror_issue_fields)
                if not self.dry_run:
                    mirror_issue = self.get_client(other_source).create_issue(mirror_issue_fields)
                    self._create_tracking_comment(updated_issue, mirror_issue)

                    updated_issue_updates, _ = self.make_issue_updates(updated_issue, mirror_issue)
                    if updated_issue_updates:
                        logger.info("Updating %s: %s", updated_issue, updated_issue_updates)
                        self.get_client(updated_issue.source).update_issue(updated_issue, updated_issue_updates)

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

            if mirror_issue.title_hash != source_issue.title_hash:
                mirror_updates["title"] = self.make_mirror_issue_title(source_issue)

                if "metadata" not in mirror_updates:
                    mirror_updates["metadata"] = mirror_issue.metadata.copy()

                mirror_updates["metadata"][MetadataField.TITLE_HASH.key] = source_issue.title_hash

            if mirror_issue.body_hash != source_issue.body_hash:
                mirror_updates["body"] = self.make_mirror_issue_body(source_issue)

                if "metadata" not in mirror_updates:
                    mirror_updates["metadata"] = mirror_issue.metadata.copy()

                mirror_updates["metadata"][MetadataField.BODY_HASH.key] = source_issue.body_hash

        fields = [("is_open", SyncFeature.SYNC_STATUS), ("milestones", SyncFeature.SYNC_MILESTONES)]

        for field_name, sync_feature in fields:
            one_field_updates, two_field_updates = self._make_field_updates(
                issue_one, issue_two, field_name, sync_feature
            )
            one_updates.update(one_field_updates)
            two_updates.update(two_field_updates)

        one_labels_updates, two_labels_updates = self._make_labels_updates(issue_one, issue_two)
        one_updates.update(one_labels_updates)
        two_updates.update(two_labels_updates)

        if issue_one.source == Source.JIRA:
            jira_issue = issue_one
            jira_updates = one_updates
            github_issue = issue_two
        else:
            jira_issue = issue_two
            jira_updates = two_updates
            github_issue = issue_one

        if self._config.jira.github_repository_field:
            if jira_issue.github_repository != self._config.github.repository:
                jira_updates["github_repository"] = self._config.github.repository

        if self._config.jira.github_issue_id_field:
            if jira_issue.github_issue_id != github_issue.issue_id:
                jira_updates["github_issue_id"] = github_issue.issue_id

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

    def _make_labels_updates(self, issue_one, issue_two):
        one_enabled = self.sync_feature_enabled(issue_one.source, SyncFeature.SYNC_LABELS)
        two_enabled = self.sync_feature_enabled(issue_two.source, SyncFeature.SYNC_LABELS)

        one_sync_labels = self.get_source_config(issue_one.source).sync.labels
        two_sync_labels = self.get_source_config(issue_two.source).sync.labels

        one_labels = issue_one.labels - one_sync_labels
        two_labels = issue_two.labels - two_sync_labels

        if one_enabled and two_enabled:
            if issue_one.updated_at > issue_two.updated_at:
                two_labels = one_labels
            else:
                one_labels = two_labels
        elif one_enabled:
            one_labels = two_labels
        elif two_enabled:
            two_labels = one_labels

        one_labels = one_labels | one_sync_labels
        two_labels = two_labels | two_sync_labels

        one_updates = {}
        two_updates = {}

        if issue_one.labels != one_labels:
            one_updates["labels"] = one_labels

        if issue_two.labels != two_labels:
            two_updates["labels"] = two_labels

        return one_updates, two_updates

    def sync_comments(self, issue_one, issue_two):
        if not self.sync_feature_enabled(issue_one.source, SyncFeature.SYNC_COMMENTS) and not self.sync_feature_enabled(
            issue_two.source, SyncFeature.SYNC_COMMENTS
        ):
            return

        issue_one_comments = [(issue_one, c, issue_two) for c in issue_one.comments if not c.is_tracking_comment]
        issue_two_comments = [(issue_two, c, issue_one) for c in issue_two.comments if not c.is_tracking_comment]
        all_comments = issue_one_comments + issue_two_comments

        comments_by_id = {c.comment_id: c for _, c, _ in all_comments}
        comments_by_mirror_id = {c.mirror_id: c for _, c, _ in all_comments if c.is_bot}

        for issue, comment, other_issue in all_comments:
            try:
                if comment.is_bot:
                    source_comment = comments_by_id.get(comment.mirror_id)
                    if not source_comment and self.sync_feature_enabled(comment.source, SyncFeature.SYNC_COMMENTS):
                        logger.info("Deleting %s on %s", comment, issue)

                        if not self.dry_run:
                            self.get_client(comment.source).delete_comment(comment)
                        else:
                            logger.info("Skipping comment delete due to dry run")
                else:
                    mirror_comment = comments_by_mirror_id.get(comment.comment_id, None)
                    if mirror_comment:
                        if self.sync_feature_enabled(mirror_comment.source, SyncFeature.SYNC_COMMENTS):
                            if mirror_comment.body_hash != comment.body_hash:
                                mirror_comment_updates = {"body": self.make_mirror_comment_body(issue, comment)}

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
                                self.get_client(other_issue.source).create_comment(other_issue, mirror_comment_fields)
                            else:
                                logger.info("Skipping comment create due to dry run")
            except Exception:
                logger.exception("Failed syncing %s", comment)

    def make_mirror_comment(self, source_issue, source_comment, mirror_issue):
        fields = {}

        fields["body"] = self.make_mirror_comment_body(source_issue, source_comment)

        metadata = {
            MetadataField.MIRROR_ID.key: source_comment.comment_id,
            MetadataField.BODY_HASH.key: source_comment.body_hash,
        }

        fields["metadata"] = metadata

        return fields

    def make_mirror_issue(self, source_issue):
        mirror_source = source_issue.source.other
        mirror_config = self.get_source_config(mirror_source)

        fields = {}

        fields["title"] = self.make_mirror_issue_title(source_issue)
        fields["body"] = self.make_mirror_issue_body(source_issue)

        if mirror_config.defaults.issue_type:
            fields["issue_type"] = mirror_config.defaults.issue_type

        if mirror_config.defaults.priority:
            fields["priority"] = mirror_config.defaults.priority

        if mirror_config.defaults.components:
            fields["components"] = mirror_config.defaults.components.copy()

        if self.sync_feature_enabled(mirror_source, SyncFeature.SYNC_LABELS):
            fields["labels"] = source_issue.labels.copy()

        sync_labels = self.get_source_config(mirror_source).sync.labels
        if sync_labels:
            if "labels" not in fields:
                fields["labels"] = set()
            fields["labels"] = fields["labels"] | sync_labels

        if self.sync_feature_enabled(mirror_source, SyncFeature.SYNC_MILESTONES):
            fields["milestones"] = source_issue.milestones.copy()

        metadata = {
            MetadataField.MIRROR_ID.key: source_issue.issue_id,
            MetadataField.MIRROR_PROJECT.key: source_issue.project,
            MetadataField.BODY_HASH.key: source_issue.body_hash,
            MetadataField.TITLE_HASH.key: source_issue.title_hash,
        }

        fields["metadata"] = metadata

        if self._config.jira.github_repository_field:
            if source_issue.source == Source.GITHUB:
                fields["github_repository"] = self._config.github.repository

        if self._config.jira.github_issue_id_field:
            if source_issue.source == Source.GITHUB:
                fields["github_issue_id"] = source_issue.issue_id

        return fields

    def _create_tracking_comment(self, source_issue, mirror_issue):
        fields = {}

        fields["body"] = self.make_tracking_comment_body(mirror_issue)

        metadata = {MetadataField.IS_TRACKING_COMMENT.key: True}
        fields["metadata"] = metadata

        issue_metadata = {
            MetadataField.MIRROR_ID.key: mirror_issue.issue_id,
            MetadataField.MIRROR_PROJECT.key: mirror_issue.project,
        }
        fields["issue_metadata"] = issue_metadata

        logger.info("Creating tracking comment on %s: %s", source_issue, fields)

        if not self.dry_run:
            self.get_client(source_issue.source).create_comment(source_issue, fields)
        else:
            logger.info("Skipping tracking comment create due to dry run")

    def make_mirror_issue_title(self, source_issue):
        return self.redact_text(source_issue.source.other, source_issue.title)

    def make_mirror_issue_body(self, source_issue):
        mirror_source = source_issue.source.other
        formatter = self.get_formatter(mirror_source)

        user_url = self.url_helper.get_user_profile_url(source_issue.user)
        user_link = formatter.format_link(user_url, source_issue.user.display_name)

        if source_issue.source == Source.JIRA:
            link_text = f"{source_issue.issue_id}"
        else:
            link_text = f"#{source_issue.issue_id}"

        issue_url = self.url_helper.get_issue_url(source_issue)
        issue_link = formatter.format_link(issue_url, link_text)

        body = self.redact_text(mirror_source, source_issue.body)
        body = formatter.format_body(body)

        return f"_Issue {issue_link} was created on {source_issue.source} by {user_link}:_\r\n\r\n{body}"

    def make_mirror_comment_body(self, source_issue, source_comment):
        formatter = self.get_formatter(source_comment.source.other)

        user_url = self.url_helper.get_user_profile_url(source_comment.user)
        user_link = formatter.format_link(user_url, source_comment.user.display_name)

        comment_url = self.url_helper.get_comment_url(source_issue, source_comment)
        comment_link = formatter.format_link(comment_url, str(source_issue.source))

        body = self.redact_text(source_comment.source.other, source_comment.body)
        body = formatter.format_body(body)

        return f"_Comment by {user_link} on {comment_link}:_\r\n\r\n{body}"

    def make_tracking_comment_body(self, mirror_issue):
        if mirror_issue.source == Source.JIRA:
            link_text = f"{mirror_issue.issue_id}"
        else:
            link_text = f"#{mirror_issue.issue_id}"

        issue_url = self.url_helper.get_issue_url(mirror_issue)
        formatted_link = self.get_formatter(mirror_issue.source.other).format_link(issue_url, link_text)
        return f"_Tracked on {mirror_issue.source} as issue {formatted_link}._"

    def redact_text(self, source, text):
        for regex in self.get_source_config(source).sync.redact_regexes:
            for match in regex.finditer(text):
                text = text[: match.start()] + "\u2588" * (match.end() - match.start()) + text[match.end() :]

        return text
