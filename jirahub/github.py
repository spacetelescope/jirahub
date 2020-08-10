import logging
import re
import os
from datetime import timezone

from github import Github, UnknownObjectException

from .entities import Issue, Comment, User, Source
from .utils import isolate_regions


__all__ = ["Client", "Formatter", "get_token"]


logger = logging.getLogger(__name__)


def get_token():
    return os.environ.get("JIRAHUB_GITHUB_TOKEN")


def _parse_datetime(value):
    # GitHub datetimes are datetime objects in UTC, they just don't have tzinfo set.
    return value.replace(tzinfo=timezone.utc)


class _IssueMapper:
    """
    This class is responsible for mapping the fields of the GitHub client's resource objects
    to our own in jirahub.entities.
    """

    def __init__(self, bot_username, raw_milestones):
        self._bot_username = bot_username
        self._raw_milestones_by_name = {m.title: m for m in raw_milestones}

    def get_user(self, raw_user):
        if not raw_user.name:
            display_name = raw_user.login
        else:
            display_name = raw_user.name

        return User(source=Source.GITHUB, username=raw_user.login, display_name=display_name, raw_user=raw_user)

    def get_comment(self, raw_comment):
        user = self.get_user(raw_comment.user)
        is_bot = user.username == self._bot_username

        body = raw_comment.body
        if body is None:
            body = ""

        comment_id = raw_comment.id
        created_at = _parse_datetime(raw_comment.created_at)
        updated_at = _parse_datetime(raw_comment.updated_at)

        return Comment(
            source=Source.GITHUB,
            is_bot=is_bot,
            comment_id=comment_id,
            created_at=created_at,
            updated_at=updated_at,
            user=user,
            body=body,
            raw_comment=raw_comment,
        )

    def get_raw_comment_fields(self, fields, comment=None):
        raw_fields = {}

        if "body" in fields:
            if fields["body"]:
                body = fields["body"]
            else:
                body = ""
            raw_fields["body"] = body

        return raw_fields

    def get_issue(self, raw_issue, raw_comments):
        user = self.get_user(raw_issue.user)
        is_bot = user.username == self._bot_username

        comments = [self.get_comment(c) for c in raw_comments]

        body = raw_issue.body
        if body is None:
            body = ""

        issue_id = raw_issue.number
        project = raw_issue.repository.full_name
        created_at = _parse_datetime(raw_issue.created_at)
        updated_at = _parse_datetime(raw_issue.updated_at)

        title = raw_issue.title
        labels = {l.name for l in raw_issue.labels}

        if raw_issue.milestone:
            milestones = {raw_issue.milestone.title}
        else:
            milestones = set()

        is_open = raw_issue.state == "open"

        return Issue(
            source=Source.GITHUB,
            is_bot=is_bot,
            issue_id=issue_id,
            project=project,
            created_at=created_at,
            updated_at=updated_at,
            user=user,
            title=title,
            body=body,
            labels=labels,
            is_open=is_open,
            milestones=milestones,
            comments=comments,
            raw_issue=raw_issue,
        )

    def get_raw_issue_fields(self, fields, issue=None):
        fields = fields.copy()
        raw_fields = {}

        if "title" in fields:
            raw_fields["title"] = fields.pop("title")

        if "body" in fields:
            if fields["body"]:
                body = fields["body"]
            else:
                body = ""
            raw_fields["body"] = body
            fields.pop("body")

        if "milestones" in fields:
            raw_milestones = []
            if fields["milestones"]:
                for milestone in fields["milestones"]:
                    if milestone in self._raw_milestones_by_name:
                        raw_milestones.append(self._raw_milestones_by_name[milestone])
                    else:
                        if issue:
                            issue_str = issue
                        else:
                            issue_str = "New issue"
                        logger.warning("%s has milestone %s, but it is not available on GitHub", issue_str, milestone)

            if raw_milestones:
                if len(raw_milestones) > 1:
                    if issue:
                        issue_str = issue
                    else:
                        issue_str = "New issue"
                    logger.warning(
                        "%s has multiple milestones (%s), but GitHub only supports one; choosing %s",
                        issue_str,
                        ", ".join([m.title for m in raw_milestones]),
                        raw_milestones[0].title,
                    )
                raw_fields["milestone"] = raw_milestones[0]
            elif issue:
                raw_fields["milestone"] = None
            fields.pop("milestones")

        if "labels" in fields:
            if fields["labels"]:
                raw_fields["labels"] = list(fields["labels"])
            else:
                raw_fields["labels"] = []
            fields.pop("labels")

        if "is_open" in fields:
            if fields["is_open"]:
                raw_fields["state"] = "open"
            else:
                raw_fields["state"] = "closed"
            fields.pop("is_open")

        raw_fields.update(fields)
        return raw_fields


class Client:
    @classmethod
    def from_config(cls, config):
        github = Github(get_token(), retry=config.github.max_retries)

        return cls(config, github)

    def __init__(self, config, github):
        self._config = config
        self._github = github
        self._repo = github.get_repo(config.github.repository)
        self._mapper = _IssueMapper(github.get_user().login, self._repo.get_milestones())

    def get_user(self, username):
        return self._mapper.get_user(self._github.get_user(username))

    def find_issues(self, min_updated_at=None):
        if min_updated_at:
            assert min_updated_at.tzinfo is not None

        if min_updated_at:
            raw_issues = self._repo.get_issues(
                sort="updated", direction="asc", since=min_updated_at.astimezone(timezone.utc), state="all"
            )
        else:
            raw_issues = self._repo.get_issues(sort="updated", direction="asc", state="all")

        # Already paginated by GitHub's client:
        for raw_issue in raw_issues:
            # The GitHub API treats pull requests as issues (but not the other way around):
            if not raw_issue.pull_request:
                yield self._mapper.get_issue(raw_issue, raw_issue.get_comments())

    def find_other_issue(self, jira_issue):
        assert jira_issue.source == Source.JIRA

        if jira_issue.metadata.github_repository and jira_issue.metadata.github_issue_id:
            assert jira_issue.metadata.github_repository == self._config.github.repository
            raw_issue = self._repo.get_issue(jira_issue.metadata.github_issue_id)
            return self._mapper.get_issue(raw_issue, raw_issue.get_comments())
        else:
            return None

    def get_issue(self, issue_id):
        raw_issue = self._repo.get_issue(issue_id)
        return self._mapper.get_issue(raw_issue, raw_issue.get_comments())

    def create_issue(self, fields):
        raw_fields = self._mapper.get_raw_issue_fields(fields)
        raw_issue = self._repo.create_issue(**raw_fields)
        new_issue = self._mapper.get_issue(raw_issue, [])

        logger.info("Created %s", new_issue)

        return new_issue

    def update_issue(self, issue, fields):
        assert issue.source == Source.GITHUB

        if ("title" in fields or "body" in fields) and not issue.is_bot:
            raise ValueError("Cannot update title or body of issue owned by another user")

        raw_fields = self._mapper.get_raw_issue_fields(fields, issue=issue)
        issue.raw_issue.edit(**raw_fields)
        updated_issue = self._mapper.get_issue(issue.raw_issue, issue.raw_issue.get_comments())

        logger.info("Updated %s", updated_issue)

        return updated_issue

    def create_comment(self, issue, fields):
        assert issue.source == Source.GITHUB

        raw_fields = self._mapper.get_raw_comment_fields(fields)
        raw_comment = issue.raw_issue.create_comment(**raw_fields)
        new_comment = self._mapper.get_comment(raw_comment)

        logger.info("Created %s on %s", new_comment, issue)

        return new_comment

    def update_comment(self, comment, fields):
        assert comment.source == Source.GITHUB

        if not comment.is_bot:
            raise ValueError("Cannot update comment owned by another user")

        raw_fields = self._mapper.get_raw_comment_fields(fields, comment=comment)
        comment.raw_comment.edit(**raw_fields)

        logger.info("Updated %s", comment)

    def delete_comment(self, comment):
        assert comment.source == Source.GITHUB

        if not comment.is_bot:
            raise ValueError("Cannot delete comment owned by another user")

        comment.raw_comment.delete()

        logger.info("Deleted %s", comment)

    def is_issue(self, issue_id):
        try:
            issue = self._repo.get_issue(issue_id)
        except UnknownObjectException:
            return False
        else:
            # The GitHub API treats pull requests as issues (but not the other way around):
            if issue.pull_request:
                return False
            else:
                return True

    def is_pull_request(self, pr_id):
        try:
            self._repo.get_pull(pr_id)
        except UnknownObjectException:
            return False
        else:
            return True


class Formatter:
    ISSUE_RE = re.compile(r"^https://github.com/([^/]+/[^/]+)/issues/([0-9]+)$")
    PR_RE = re.compile(r"^https://github.com/([^/]+/[^/]+)/pull/([0-9]+)$")
    USER_PROFILE_RE = re.compile(r"^https://github.com/([^/]+)$")
    H1_RE = re.compile(r"\bh1\. ")
    H2_RE = re.compile(r"\bh2\. ")
    H3_RE = re.compile(r"\bh3\. ")
    H4_RE = re.compile(r"\bh4\. ")
    H5_RE = re.compile(r"\bh5\. ")
    H6_RE = re.compile(r"\bh6\. ")
    CODE_OPEN_RE = re.compile(r"\{code(:(.*?))?\}")
    CODE_CLOSE_RE = re.compile(r"\{code\}")
    NOFORMAT_RE = re.compile(r"\{noformat\}")
    QUOTE_RE = re.compile(r"\{quote\}")
    COLOR_RE = re.compile(r"\{color.*?\}")
    HASH_NUMBER_RE = re.compile(r"#([0-9]+)")
    BOLD_RE = re.compile(r"(^|\W)\*(\w(.*?\w)?)\*($|\W)")
    ITALIC_RE = re.compile(r"(^|\W)_(\w(.*?\w)?)_($|\W)")
    MONOSPACED_RE = re.compile(r"\{\{(.*?)\}\}")
    STRIKETHROUGH_RE = re.compile(r"(^|\W)-(\w(.*?\w)?)-($|\W)")
    INSERTED_RE = re.compile(r"(^|\W)\+(\w(.*?\w)?)\+($|\W)")
    SUPERSCRIPT_RE = re.compile(r"(^|\W)\^(\w(.*?\w)?)\^($|\W)")
    SUBSCRIPT_RE = re.compile(r"(^|\W)~(\w(.*?\w)?)~($|\W)")
    URL_WITH_TEXT_RE = re.compile(r"\[(.*?)\|(http.*?)\]")
    URL_RE = re.compile(r"(\s|^)\[?(http.*?)\]?(\s|$)")
    USER_MENTION_RE = re.compile(r"\[~(.+?)\]")
    GITHUB_USER_MENTION_RE = re.compile(r"(^|\s)@(\w+?)\b")

    def __init__(self, config, url_helper, jira_client):
        self._config = config
        self._url_helper = url_helper
        self._jira_client = jira_client

    def format_link(self, url, link_text=None):
        if link_text:
            return f"[{link_text}]({url})"
        else:
            match = Formatter.ISSUE_RE.match(url)
            if match:
                repository = match.group(1)
                issue_id = int(match.group(2))

                if repository == self._config.github.repository:
                    return f"#{issue_id}"
                else:
                    return f"{repository}#{issue_id}"

            match = Formatter.PR_RE.match(url)
            if match:
                repository = match.group(1)
                pr_id = int(match.group(2))

                if repository == self._config.github.repository:
                    return f"#{pr_id}"
                else:
                    return f"{repository}#{pr_id}"

            match = Formatter.USER_PROFILE_RE.match(url)
            if match:
                username = match.group(1)
                return f"@{username}"

            return f"<{url}>"

    def format_body(self, body):
        regions = [(body, True)]

        regions = isolate_regions(regions, Formatter.CODE_OPEN_RE, Formatter.CODE_CLOSE_RE, self._handle_code_content)

        regions = isolate_regions(regions, Formatter.NOFORMAT_RE, Formatter.NOFORMAT_RE, self._handle_noformat_content)

        regions = isolate_regions(regions, Formatter.QUOTE_RE, Formatter.QUOTE_RE, self._handle_quoted_content)

        result = ""
        for content, formatted in regions:
            if formatted:
                content = self._format_content(content)
            result = result + content

        return result

    def _handle_noformat_content(self, content, open_match):
        if len(content) > 0:
            return (f"```{content}```", False)
        else:
            return ("", False)

    def _handle_code_content(self, content, open_match):
        if open_match.group(2):
            language = open_match.group(2)
        else:
            language = ""

        if len(content) > 0:
            return (f"```{language}{content}```", False)
        else:
            return ("", False)

    def _handle_quoted_content(self, content, open_match):
        if len(content) > 0:
            lines = content.split("\n")
            if not lines[0].strip():
                lines = lines[1:]
            if not lines[-1].strip():
                lines = lines[:-1]
            content = "\n" + "\n".join("> " + l for l in lines) + "\n"
            return (content, True)
        else:
            return ("", False)

    def _format_user_mention(self, match):
        username = match.group(1)
        try:
            user = self._jira_client.get_user(username)
        except Exception:
            logger.warning("Missing JIRA user with username %s", username)
            user = None

        if user:
            link_text = user.display_name
        else:
            link_text = username

        url = self._url_helper.get_user_profile_url(source=Source.JIRA, username=username)

        return self.format_link(url, link_text)

    def _format_github_user_mention(self, match):
        # Insert an invisible character between the @ and the username
        # to prevent GitHub from mentioning a user.  U+2063 is the
        # "invisible separator" code point.
        return match.group(1) + "@\u2063" + match.group(2)

    def _format_content(self, content):
        # Perform this transformation early since we don't want it to end up escaping
        # intentional user mentions:
        content = Formatter.GITHUB_USER_MENTION_RE.sub(self._format_github_user_mention, content)

        content = Formatter.HASH_NUMBER_RE.sub(lambda match: f"#&#x2060;{match.group(1)}", content)
        content = Formatter.H1_RE.sub("# ", content)
        content = Formatter.H2_RE.sub("## ", content)
        content = Formatter.H3_RE.sub("### ", content)
        content = Formatter.H4_RE.sub("#### ", content)
        content = Formatter.H5_RE.sub("##### ", content)
        content = Formatter.H6_RE.sub("###### ", content)
        content = Formatter.COLOR_RE.sub("", content)
        content = Formatter.BOLD_RE.sub(
            lambda match: match.group(1) + f"**{match.group(2)}**" + match.group(4), content
        )
        content = Formatter.ITALIC_RE.sub(
            lambda match: match.group(1) + f"*{match.group(2)}*" + match.group(4), content
        )
        content = Formatter.SUBSCRIPT_RE.sub(
            lambda match: match.group(1) + f"<sub>{match.group(2)}</sub>" + match.group(4), content
        )
        content = Formatter.MONOSPACED_RE.sub(lambda match: f"`{match.group(1)}`", content)
        content = Formatter.STRIKETHROUGH_RE.sub(
            lambda match: match.group(1) + f"~~{match.group(2)}~~" + match.group(4), content
        )
        content = Formatter.INSERTED_RE.sub(
            lambda match: match.group(1) + f"<ins>{match.group(2)}</ins>" + match.group(4), content
        )
        content = Formatter.SUPERSCRIPT_RE.sub(
            lambda match: match.group(1) + f"<sup>{match.group(2)}</sup>" + match.group(4), content
        )
        content = Formatter.URL_WITH_TEXT_RE.sub(
            lambda match: self.format_link(match.group(2), match.group(1)), content
        )
        content = Formatter.URL_RE.sub(
            lambda match: match.group(1) + self.format_link(match.group(2)) + match.group(3), content
        )
        content = Formatter.USER_MENTION_RE.sub(self._format_user_mention, content)

        return content
