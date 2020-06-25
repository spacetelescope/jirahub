import json
import re
from datetime import datetime, timezone
import logging
import os
import dataclasses
import urllib

from jira import JIRA

from .entities import Issue, Comment, User, Source, Metadata, CommentMetadata
from . import utils


__all__ = ["Client", "Formatter", "get_username", "get_password"]


logger = logging.getLogger(__name__)


def get_username():
    return os.environ.get("JIRAHUB_JIRA_USERNAME")


def get_password():
    return os.environ.get("JIRAHUB_JIRA_PASSWORD")


_JIRA_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"


def _parse_datetime(value):
    return datetime.strptime(value, _JIRA_DATETIME_FORMAT).astimezone(timezone.utc)


def _client_field_name(field_id):
    return f"customfield_{field_id}"


def _jql_field_name(field_id):
    return f"cf[{field_id}]"


class _IssueMapper:
    """
    This class is responsible for mapping the fields of the JIRA client's resource objects
    to our own in jirahub.entities.
    """

    def __init__(self, config, bot_username):
        self._config = config
        self._bot_username = bot_username

    def get_user(self, raw_user):
        if not raw_user.displayName:
            display_name = raw_user.name
        else:
            display_name = raw_user.displayName

        return User(source=Source.JIRA, username=raw_user.name, display_name=display_name, raw_user=raw_user)

    def get_comment(self, raw_comment):
        user = self.get_user(raw_comment.author)
        is_bot = user.username == self._bot_username

        body = raw_comment.body
        if body is None:
            body = ""

        comment_id = raw_comment.id

        created_at = _parse_datetime(raw_comment.created)
        updated_at = _parse_datetime(raw_comment.updated)

        return Comment(
            source=Source.JIRA,
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
        user = self.get_user(raw_issue.fields.creator)
        is_bot = user.username == self._bot_username

        comments = [self.get_comment(c) for c in raw_comments]

        body = raw_issue.fields.description
        if body is None:
            body = ""

        issue_id = raw_issue.key
        project = raw_issue.fields.project.key
        created_at = _parse_datetime(raw_issue.fields.created)
        updated_at = _parse_datetime(raw_issue.fields.updated)
        title = raw_issue.fields.summary
        labels = set([urllib.parse.unquote(l) for l in raw_issue.fields.labels])
        milestones = {v.name for v in raw_issue.fields.fixVersions}
        components = {c.name for c in raw_issue.fields.components}

        if raw_issue.fields.priority:
            priority = raw_issue.fields.priority.name
        else:
            priority = None

        if raw_issue.fields.issuetype:
            issue_type = raw_issue.fields.issuetype.name
        else:
            issue_type = None

        is_open = raw_issue.fields.status.name.lower() not in [s.lower() for s in self._config.jira.closed_statuses]

        metadata = self._get_metadata(raw_issue)

        return Issue(
            source=Source.JIRA,
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
            priority=priority,
            issue_type=issue_type,
            milestones=milestones,
            components=components,
            comments=comments,
            metadata=metadata,
            raw_issue=raw_issue,
        )

    def get_raw_issue_fields(self, fields, issue=None):
        fields = fields.copy()
        raw_fields = {}

        if "title" in fields:
            raw_fields["summary"] = fields.pop("title")

        if "body" in fields:
            if fields["body"]:
                body = fields["body"]
            else:
                body = ""
            raw_fields["description"] = body
            fields.pop("body")

        if "metadata" in fields:
            raw_fields.update(self._get_raw_metadata_fields(fields.pop("metadata")))

        if "labels" in fields:
            if fields["labels"]:
                raw_fields["labels"] = [urllib.parse.quote(l) for l in fields["labels"]]
            else:
                raw_fields["labels"] = []
            fields.pop("labels")

        if "milestones" in fields:
            if fields["milestones"]:
                raw_fields["fixVersions"] = self._make_name_list(fields["milestones"])
            else:
                raw_fields["fixVersions"] = []
            fields.pop("milestones")

        if "components" in fields:
            if fields["components"]:
                raw_fields["components"] = self._make_name_list(fields["components"])
            else:
                raw_fields["components"] = []
            fields.pop("components")

        if "priority" in fields:
            if fields["priority"]:
                raw_fields["priority"] = {"name": fields["priority"]}
            else:
                raw_fields["priority"] = None
            fields.pop("priority")

        if "issue_type" in fields:
            raw_fields["issuetype"] = {"name": fields.pop("issue_type")}

        transition = None
        if issue is None:
            if "is_open" in fields:
                if fields["is_open"]:
                    status = self._config.jira.open_status
                else:
                    status = self._config.jira.close_status
            else:
                status = self._config.jira.open_status
            if status:
                raw_fields["status"] = {"name": status}
        elif "is_open" in fields:
            if fields["is_open"]:
                transition = self._config.jira.reopen_status
            else:
                transition = self._config.jira.close_status
        fields.pop("is_open", None)

        raw_fields.update(fields)
        return raw_fields, transition

    def _make_name_list(self, values):
        return [{"name": v} for v in values]

    def _get_metadata(self, raw_issue):
        kwargs = {}

        field_name = _client_field_name(self._config.jira.github_issue_url_field_id)
        github_issue_url = getattr(raw_issue.fields, field_name)
        if github_issue_url:
            github_repository, github_issue_id = utils.extract_github_ids_from_url(github_issue_url)
            kwargs["github_repository"] = github_repository
            kwargs["github_issue_id"] = github_issue_id

        field_name = _client_field_name(self._config.jira.jirahub_metadata_field_id)
        metadata_json = getattr(raw_issue.fields, field_name)
        if metadata_json:
            try:
                metadata_dict = json.loads(metadata_json)
            except Exception:
                logger.exception("Failed to deserialize JSON")
            else:
                kwargs.update(metadata_dict)

        if kwargs.get("comments"):
            kwargs["comments"] = [CommentMetadata(**c) for c in kwargs["comments"]]

        return Metadata(**kwargs)

    def _get_raw_metadata_fields(self, metadata):
        raw_fields = {}

        if not metadata:
            return {
                _client_field_name(self._config.jira.github_issue_url_field_id): None,
                _client_field_name(self._config.jira.jirahub_metadata_field_id): None,
            }

        if metadata.github_repository and metadata.github_issue_id:
            github_issue_url = utils.make_github_issue_url(metadata.github_repository, metadata.github_issue_id)
        else:
            github_issue_url = None
        field_name = _client_field_name(self._config.jira.github_issue_url_field_id)
        raw_fields[field_name] = github_issue_url

        metadata_dict = dataclasses.asdict(metadata)
        metadata_dict.pop("github_repository")
        metadata_dict.pop("github_issue_id")
        field_name = _client_field_name(self._config.jira.jirahub_metadata_field_id)
        raw_fields[field_name] = json.dumps(metadata_dict)

        return raw_fields


class Client:
    _PAGE_SIZE = 50

    @classmethod
    def from_config(cls, config):
        jira = JIRA(
            config.jira.server, basic_auth=(get_username(), get_password()), max_retries=config.jira.max_retries
        )

        return cls(config, jira, get_username())

    def __init__(self, config, jira, bot_username):
        self._config = config
        self._jira = jira
        self._mapper = _IssueMapper(config, bot_username)

    def get_user(self, username):
        return self._mapper.get_user(self._jira.user(username))

    def find_issues(self, min_updated_at=None):
        if min_updated_at:
            assert min_updated_at.tzinfo is not None

        query = self._make_query(min_updated_at=min_updated_at)

        current_page = 0
        while True:
            start_idx = current_page * Client._PAGE_SIZE
            raw_issues = self._jira.search_issues(query, start_idx, Client._PAGE_SIZE)

            for raw_issue in raw_issues:
                # The JIRA client is a buggy and will occasionally return None
                # for the creator field, even when the data exists.  Reloading the
                # issues one by one seems to fix that.
                raw_issue = self._jira.issue(raw_issue.key)
                raw_comments = self._jira.comments(raw_issue)
                yield self._mapper.get_issue(raw_issue, raw_comments)

            if len(raw_issues) < Client._PAGE_SIZE:
                break

            current_page += 1

    def find_other_issue(self, github_issue):
        assert github_issue.source == Source.GITHUB

        github_issue_url = utils.make_github_issue_url(github_issue.project, github_issue.issue_id)
        query = self._make_query(github_issue_url=github_issue_url)
        raw_issues = self._jira.search_issues(query)

        if len(raw_issues) > 1:
            raise RuntimeError(f"{github_issue} has multiple linked JIRA issues")
        elif len(raw_issues) == 1:
            # Reloading the issue to make sure we get the creator field (see note above).
            raw_issue = self._jira.issue(raw_issues[0].key)
            raw_comments = self._jira.comments(raw_issue)
            return self._mapper.get_issue(raw_issue, raw_comments)
        else:
            return None

    def get_issue(self, issue_id):
        raw_issue = self._jira.issue(issue_id)
        raw_comments = self._jira.comments(raw_issue)
        return self._mapper.get_issue(raw_issue, raw_comments)

    def create_issue(self, fields):
        raw_fields, _ = self._mapper.get_raw_issue_fields(fields)
        raw_fields["project"] = self._config.jira.project_key
        raw_issue = self._jira.create_issue(fields=raw_fields)
        new_issue = self._mapper.get_issue(raw_issue, [])

        logger.info("Created issue %s", new_issue)

        return new_issue

    def update_issue(self, issue, fields):
        assert issue.source == Source.JIRA

        if ("title" in fields or "body" in fields) and not issue.is_bot:
            raise ValueError("Cannot update title or body of issue owned by another user")

        raw_fields, transition = self._mapper.get_raw_issue_fields(fields, issue=issue)
        if len(raw_fields) > 0:
            issue.raw_issue.update(notify=self._config.jira.notify_watchers, fields=raw_fields)
        if transition is not None:
            self._jira.transition_issue(issue.raw_issue, transition)

        raw_comments = self._jira.comments(issue.raw_issue)
        updated_issue = self._mapper.get_issue(issue.raw_issue, raw_comments)

        logger.info("Updated issue %s", updated_issue)

        return updated_issue

    def create_comment(self, issue, fields):
        assert issue.source == Source.JIRA

        fields = self._mapper.get_raw_comment_fields(fields)
        raw_comment = self._jira.add_comment(issue=issue.issue_id, **fields)
        new_comment = self._mapper.get_comment(raw_comment)

        logger.info("Created comment %s on issue %s", new_comment, issue)

        return new_comment

    def update_comment(self, comment, fields):
        assert comment.source == Source.JIRA

        if not comment.is_bot:
            raise ValueError("Cannot update comment owned by another user")

        fields = self._mapper.get_raw_comment_fields(fields, comment=comment)
        comment.raw_comment.update(**fields)
        updated_comment = self._mapper.get_comment(comment.raw_comment)

        logger.info("Updated comment %s", updated_comment)

        return updated_comment

    def delete_comment(self, comment):
        assert comment.source == Source.JIRA

        if not comment.is_bot:
            raise ValueError("Cannot delete comment owned by another user")

        comment.raw_comment.delete()

        logger.info("Deleted comment %s", comment)

    def _make_query(self, min_updated_at=None, github_issue_url=None):
        filters = []

        quoted_project_key = self._quote_query_string(self._config.jira.project_key)
        filters.append(f"project = {quoted_project_key}")

        if min_updated_at:
            min_updated_at_ms = int(min_updated_at.timestamp() * 1000)
            filters.append(f"updated > {min_updated_at_ms}")

        if github_issue_url:
            quoted_url = self._quote_query_string(github_issue_url)
            field_name = _jql_field_name(self._config.jira.github_issue_url_field_id)
            filters.append(f"{field_name} = {quoted_url}")

        return " and ".join(filters) + " order by updated asc"

    def _quote_query_string(self, value):
        return "'" + value.replace("'", "\\'") + "'"


class Formatter:
    H1_RE = re.compile(r"(\s|^)# ")
    H2_RE = re.compile(r"(\s|^)## ")
    H3_RE = re.compile(r"(\s|^)### ")
    H4_RE = re.compile(r"(\s|^)#### ")
    H5_RE = re.compile(r"(\s|^)##### ")
    H6_RE = re.compile(r"(\s|^)###### ")
    NOFORMAT_OPEN_RE = re.compile(r"```(\w*)")
    NOFORMAT_CLOSE_RE = re.compile(r"```")
    HASH_NUMBER_RE = re.compile(r"(^|\s)#([0-9]+)($|\s)")
    USER_MENTION_RE = re.compile(r"(^|\s)@(\w+?)\b")
    ITALIC_RE = re.compile(r"(^|[^\w*])\*(\w(.*?\w)?)\*($|[^\w*])")
    BOLD_RE = re.compile(r"(^|\W)\*\*(\w(.*?\w)?)\*\*($|\W)")
    MONOSPACED_RE = re.compile(r"`(.+?)`")
    STRIKETHROUGH_RE = re.compile(r"(^|\W)~~(\w(.*?\w)?)~~($|\W)")
    INSERTED_RE = re.compile(r"<ins>(.+?)</ins>")
    SUPERSCRIPT_RE = re.compile(r"<sup>(.+?)</sup>")
    SUBSCRIPT_RE = re.compile(r"<sub>(.+?)</sub>")
    URL_WITH_TEXT_RE = re.compile(r"\[(.*?)\]\((http.*?)\)")
    URL_RE = re.compile(r"(\s|^)<?(http.*?)>?(\s|$)")
    QUOTE_RE = re.compile(r"((^> .*?$)(\r?\n)?)+", re.MULTILINE)

    def __init__(self, config, url_helper, github_client):
        self._config = config
        self._url_helper = url_helper
        self._github_client = github_client

    def format_link(self, url, link_text=None):
        if link_text:
            return f"[{link_text}|{url}]"
        else:
            return f"[{url}]"

    def format_body(self, body):
        regions = [(body, True)]

        regions = utils.isolate_regions(
            regions, Formatter.NOFORMAT_OPEN_RE, Formatter.NOFORMAT_CLOSE_RE, self._handle_noformat_content
        )

        result = ""
        for content, formatted in regions:
            if formatted:
                content = self._format_content(content)
            result = result + content

        return result

    def _handle_noformat_content(self, content, open_match):
        if open_match.group(1):
            return ("{code:" + open_match.group(1) + "}" + content + "{code}", False)
        else:
            return ("{noformat}" + content + "{noformat}", False)

    def _format_user_mention(self, match):
        username = match.group(2)
        try:
            user = self._github_client.get_user(username)
        except Exception:
            logger.warning("Missing GitHub user with username %s", username)
            user = None

        if user:
            url = self._url_helper.get_user_profile_url(user)
            link_text = user.display_name
            return match.group(1) + self.format_link(url, link_text)
        else:
            return match.group(0)

    def _format_issue_or_pull(self, match):
        number = int(match.group(2))

        if self._github_client.is_issue(number):
            url = self._url_helper.get_issue_url(source=Source.GITHUB, issue_id=number)
            link = self.format_link(url, f"#{number}")
            return match.group(1) + link + match.group(3)
        elif self._github_client.is_pull_request(number):
            url = self._url_helper.get_pull_request_url(number)
            link = self.format_link(url, f"#{number}")
            return match.group(1) + link + match.group(3)
        else:
            return match.group(0)

    def _format_quote_block(self, match):
        content = match.group(0)
        content = "{quote}\n" + content
        if content.endswith("\n"):
            content = content + "{quote}"
        else:
            content = content + "\n{quote}"

        lines = content.split("\n")

        new_lines = []
        for line in lines:
            if line.startswith("> "):
                new_lines.append(line[2:])
            else:
                new_lines.append(line)

        return "\n".join(new_lines)

    def _format_content(self, content):
        content = Formatter.HASH_NUMBER_RE.sub(self._format_issue_or_pull, content)
        content = Formatter.H1_RE.sub(lambda match: match.group(1) + "h1. ", content)
        content = Formatter.H2_RE.sub(lambda match: match.group(1) + "h2. ", content)
        content = Formatter.H3_RE.sub(lambda match: match.group(1) + "h3. ", content)
        content = Formatter.H4_RE.sub(lambda match: match.group(1) + "h4. ", content)
        content = Formatter.H5_RE.sub(lambda match: match.group(1) + "h5. ", content)
        content = Formatter.H6_RE.sub(lambda match: match.group(1) + "h6. ", content)
        content = Formatter.ITALIC_RE.sub(
            lambda match: match.group(1) + f"_{match.group(2)}_" + match.group(4), content
        )
        content = Formatter.BOLD_RE.sub(lambda match: match.group(1) + f"*{match.group(2)}*" + match.group(4), content)
        content = Formatter.SUBSCRIPT_RE.sub(lambda match: f"~{match.group(1)}~", content)
        content = Formatter.MONOSPACED_RE.sub(lambda match: "{{" + match.group(1) + "}}", content)
        content = Formatter.STRIKETHROUGH_RE.sub(
            lambda match: match.group(1) + f"-{match.group(2)}-" + match.group(4), content
        )
        content = Formatter.INSERTED_RE.sub(lambda match: f"+{match.group(1)}+", content)
        content = Formatter.SUPERSCRIPT_RE.sub(lambda match: f"^{match.group(1)}^", content)
        content = Formatter.USER_MENTION_RE.sub(self._format_user_mention, content)
        content = Formatter.URL_WITH_TEXT_RE.sub(
            lambda match: self.format_link(match.group(2), match.group(1)), content
        )
        content = Formatter.URL_RE.sub(
            lambda match: match.group(1) + self.format_link(match.group(2)) + match.group(3), content
        )
        content = Formatter.QUOTE_RE.sub(self._format_quote_block, content)

        return content
