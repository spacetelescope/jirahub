from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import List, Any, Dict
from jira.exceptions import JIRAError
import requests
import re

from jirahub.entities import Issue, Comment, User, Source

from github import BadCredentialsException, UnknownObjectException
from github.GithubObject import NotSet

from . import constants


def reset():
    MockJIRA.reset()
    MockGithub.reset()


def now():
    return datetime.utcnow().replace(tzinfo=timezone.utc)


def next_github_issue_id():
    result = next_github_issue_id._next_id
    next_github_issue_id._next_id += 1
    return result


next_github_issue_id._next_id = 1


def next_jira_issue_id():
    result = f"{constants.TEST_JIRA_PROJECT_KEY}-{next_jira_issue_id._next_id}"
    next_jira_issue_id._next_id += 1
    return result


next_jira_issue_id._next_id = 1


def next_comment_id():
    result = next_comment_id._next_id
    next_comment_id._next_id += 1
    return result


next_comment_id._next_id = 1


_JIRA_TZ = timezone(timedelta(hours=-4))


def _jira_format_datetime(dt):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    dt = dt.astimezone(_JIRA_TZ)

    ms = int(dt.microsecond / 1e3)

    return dt.strftime("%Y-%m-%dT%H:%M:%S") + f".{ms:03d}" + dt.strftime("%z")


def _jira_now():
    return _jira_format_datetime(now())


def _jira_named_object_list(values):
    return [MockJIRANamedObject(name=v["name"]) for v in values]


def _jira_named_object(value):
    if value is None:
        return None
    else:
        return MockJIRANamedObject(name=value["name"])


def _jira_process_issue_fields(fields):
    fields = fields.copy()

    if "fixVersions" in fields:
        fields["fixVersions"] = _jira_named_object_list(fields["fixVersions"])

    if "components" in fields:
        fields["components"] = _jira_named_object_list(fields["components"])

    if "priority" in fields:
        fields["priority"] = _jira_named_object(fields["priority"])

    if "issuetype" in fields:
        fields["issuetype"] = _jira_named_object(fields["issuetype"])

    if "status" in fields:
        fields["status"] = _jira_named_object(fields["status"])

    return fields


def _bot_jira_user():
    return MockJIRAUser(name=constants.TEST_JIRA_USERNAME, displayName=constants.TEST_JIRA_USER_DISPLAY_NAME)


class MockLogger:
    def __init__(self):
        self.warnings = []
        self.errors = []
        self.infos = []

    def warning(self, *args):
        self.warnings.append(args)

    def error(self, *args):
        self.errors.append(args)

    def info(self, *args):
        self.infos.append(args)


@dataclass
class MockJIRAUser:
    name: str
    displayName: str


@dataclass
class MockJIRAComment:
    body: str
    issue_key: str
    jira: Any
    id: int = field(default_factory=next_comment_id)
    author: MockJIRAUser = field(default_factory=_bot_jira_user)
    created: str = field(default_factory=_jira_now)
    updated: str = field(default_factory=_jira_now)

    def update(self, fields=None, async_=None, jira=None, body="", visibility=None):
        self.body = body
        self.updated = _jira_now()

    def delete(self, params=None):
        self.jira.comments_list.remove(self)


@dataclass
class MockJIRANamedObject:
    name: str


@dataclass
class MockJIRAProject:
    key: str = constants.TEST_JIRA_PROJECT_KEY


@dataclass
class MockJIRAIssueFields:
    summary: str
    creator: MockJIRAUser = field(default_factory=_bot_jira_user)
    description: str = None
    labels: List[str] = field(default_factory=list)
    fixVersions: List[MockJIRANamedObject] = field(default_factory=list)
    components: List[MockJIRANamedObject] = field(default_factory=list)
    priority: MockJIRANamedObject = field(
        default_factory=lambda: MockJIRANamedObject(name=constants.TEST_JIRA_DEFAULT_PRIORITY)
    )
    issuetype: MockJIRANamedObject = field(
        default_factory=lambda: MockJIRANamedObject(name=constants.TEST_JIRA_DEFAULT_ISSUE_TYPE)
    )
    status: MockJIRANamedObject = field(
        default_factory=lambda: MockJIRANamedObject(name=constants.TEST_JIRA_DEFAULT_STATUS)
    )
    created: str = field(default_factory=_jira_now)
    updated: str = field(default_factory=_jira_now)
    customfield_12345: str = None
    customfield_67890: str = None
    project: MockJIRAProject = field(default_factory=lambda: MockJIRAProject())
    custom_field: str = None


@dataclass
class MockJIRAIssue:
    fields: MockJIRAIssueFields
    key: str = field(default_factory=next_jira_issue_id)

    def update(self, fields=None, update=None, async_=None, jira=None, notify=True):
        fields = _jira_process_issue_fields(fields)

        for key, value in fields.items():
            setattr(self.fields, key, value)

        self.fields.updated = _jira_now()

    def _transition(self, status):
        self.fields.status = MockJIRANamedObject(name=status)
        self.fields.updated = _jira_now()


class MockJIRA:
    ALL_PERMISSIONS = [
        "VIEW_WORKFLOW_READONLY",
        "CREATE_ISSUES",
        "VIEW_DEV_TOOLS",
        "BULK_CHANGE",
        "CREATE_ATTACHMENT",
        "DELETE_OWN_COMMENTS",
        "WORK_ON_ISSUES",
        "PROJECT_ADMIN",
        "COMMENT_EDIT_ALL",
        "ATTACHMENT_DELETE_OWN",
        "WORKLOG_DELETE_OWN",
        "CLOSE_ISSUE",
        "MANAGE_WATCHER_LIST",
        "VIEW_VOTERS_AND_WATCHERS",
        "ADD_COMMENTS",
        "COMMENT_DELETE_ALL",
        "CREATE_ISSUE",
        "DELETE_OWN_ATTACHMENTS",
        "DELETE_ALL_ATTACHMENTS",
        "ASSIGN_ISSUE",
        "LINK_ISSUE",
        "EDIT_OWN_WORKLOGS",
        "CREATE_ATTACHMENTS",
        "EDIT_ALL_WORKLOGS",
        "SCHEDULE_ISSUE",
        "CLOSE_ISSUES",
        "SET_ISSUE_SECURITY",
        "SCHEDULE_ISSUES",
        "WORKLOG_DELETE_ALL",
        "COMMENT_DELETE_OWN",
        "ADMINISTER_PROJECTS",
        "DELETE_ALL_COMMENTS",
        "RESOLVE_ISSUES",
        "VIEW_READONLY_WORKFLOW",
        "ADMINISTER",
        "MOVE_ISSUES",
        "TRANSITION_ISSUES",
        "SYSTEM_ADMIN",
        "DELETE_OWN_WORKLOGS",
        "BROWSE",
        "EDIT_ISSUE",
        "MODIFY_REPORTER",
        "EDIT_ISSUES",
        "MANAGE_WATCHERS",
        "EDIT_OWN_COMMENTS",
        "ASSIGN_ISSUES",
        "BROWSE_PROJECTS",
        "VIEW_VERSION_CONTROL",
        "WORK_ISSUE",
        "COMMENT_ISSUE",
        "WORKLOG_EDIT_ALL",
        "EDIT_ALL_COMMENTS",
        "DELETE_ISSUE",
        "MANAGE_SPRINTS_PERMISSION",
        "USER_PICKER",
        "CREATE_SHARED_OBJECTS",
        "ATTACHMENT_DELETE_ALL",
        "DELETE_ISSUES",
        "MANAGE_GROUP_FILTER_SUBSCRIPTIONS",
        "RESOLVE_ISSUE",
        "ASSIGNABLE_USER",
        "TRANSITION_ISSUE",
        "COMMENT_EDIT_OWN",
        "MOVE_ISSUE",
        "WORKLOG_EDIT_OWN",
        "DELETE_ALL_WORKLOGS",
        "LINK_ISSUES",
    ]

    UPDATED_RE = re.compile(r"\bupdated > ([0-9]+)\b")
    ISSUE_URL_RE = re.compile(r"\bgithub_issue_url = '(.*?)'")

    valid_servers = []
    valid_basic_auths = []
    valid_project_keys = []
    permissions = []

    @classmethod
    def reset(cls):
        cls.valid_servers = [constants.TEST_JIRA_SERVER]
        cls.valid_basic_auths = [(constants.TEST_JIRA_USERNAME, constants.TEST_JIRA_PASSWORD)]
        cls.valid_project_keys = [constants.TEST_JIRA_PROJECT_KEY]
        cls.permissions = cls.ALL_PERMISSIONS.copy()

    def __init__(self, server, basic_auth, max_retries=3):
        self.server = server
        self.basic_auth = basic_auth
        self.max_retries = max_retries

        if self.server not in MockJIRA.valid_servers:
            raise requests.exceptions.ConnectionError

        if self.basic_auth not in MockJIRA.valid_basic_auths:
            raise JIRAError()

        self.issues = []
        self.comments_list = []
        self.users = [_bot_jira_user()]

    def my_permissions(self, projectKey):
        if projectKey not in MockJIRA.valid_project_keys:
            raise JIRAError()

        permissions = {}
        for permission_id, permission in enumerate(MockJIRA.ALL_PERMISSIONS):
            entry = {
                "id": str(permission_id),
                "key": permission,
                "name": permission,
                "description": permission,
                "havePermission": permission in MockJIRA.permissions,
            }
            permissions[permission] = entry

        return {"permissions": permissions}

    def search_issues(self, jql_str, startAt=0, maxResults=50):
        updated_match = MockJIRA.UPDATED_RE.search(jql_str)
        issue_url_match = MockJIRA.ISSUE_URL_RE.search(jql_str)

        if updated_match:
            ms = int(updated_match.group(1)) / 1000.0
            dt = datetime.fromtimestamp(ms, tz=timezone.utc)
            min_updated = _jira_format_datetime(dt)
            # Times in ISO-8601 in the same timezone are comparable lexicographically:
            issues = [i for i in self.issues if i.fields.updated >= min_updated]
        elif issue_url_match:
            github_issue_url = issue_url_match.group(1)
            issues = [i for i in self.issues if github_issue_url in i.fields.github_issue_url]
        else:
            issues = self.issues

        return issues[startAt : startAt + maxResults]

    def comments(self, issue):
        return [c for c in self.comments_list if c.issue_key == issue.key]

    def issue(self, id):
        try:
            return next(i for i in self.issues if i.key == id)
        except StopIteration:
            raise JIRAError()

    def create_issue(self, fields):
        fields = _jira_process_issue_fields(fields)

        project = fields.pop("project")
        assert project in MockJIRA.valid_project_keys

        fields = MockJIRAIssueFields(**fields)
        issue = MockJIRAIssue(fields=fields)
        self.issues.append(issue)
        return issue

    def add_comment(self, issue, body):
        comment = MockJIRAComment(jira=self, issue_key=issue, body=body)
        self.comments_list.append(comment)
        return comment

    def user(self, username):
        try:
            return next(u for u in self.users if u.name == username)
        except StopIteration:
            raise JIRAError()

    def transition_issue(self, issue, status):
        issue._transition(status)


MockJIRA.reset()


def _bot_github_user():
    return MockGithubUser(login=constants.TEST_GITHUB_USER_LOGIN, name=constants.TEST_GITHUB_USER_NAME)


@dataclass
class MockGithubPermissions:
    admin: bool = False
    pull: bool = True
    push: bool = True


@dataclass
class MockGithubMilestone:
    title: str


@dataclass
class MockGithubUser:
    login: str
    name: str


@dataclass
class MockGithubComment:
    body: str
    issue: Any
    id: int = field(default_factory=next_comment_id)
    user: MockGithubUser = field(default_factory=_bot_github_user)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def edit(self, body):
        self.body = body
        self.updated_at = datetime.utcnow()

    def delete(self):
        self.issue.comments.remove(self)


@dataclass
class MockGithubLabel:
    name: str


@dataclass
class MockGithubPull:
    title: str
    number: int = field(default_factory=next_github_issue_id)


@dataclass
class MockGithubIssue:
    body: str
    title: str
    repository: Any
    number: int = field(default_factory=next_github_issue_id)
    user: MockGithubUser = field(default_factory=_bot_github_user)
    state: str = "open"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    labels: List[MockGithubLabel] = field(default_factory=list)
    milestone: MockGithubMilestone = None
    comments: List[MockGithubComment] = field(default_factory=list)
    pull_request: Dict[str, Any] = None
    assignee: str = None

    def edit(self, body=NotSet, title=NotSet, state=NotSet, labels=NotSet, milestone=NotSet):
        if body != NotSet:
            self.body = body

        if title != NotSet:
            self.title = title

        if state != NotSet:
            self.state = state

        if labels != NotSet:
            self.labels = [MockGithubLabel(name=l) for l in labels]

        if milestone != NotSet:
            self.milestone = milestone

        self.updated_at = datetime.utcnow()

    def create_comment(self, body):
        comment = MockGithubComment(body=body, issue=self)

        self.comments.append(comment)

        return comment

    def get_comments(self):
        return self.comments


@dataclass
class MockGithubRepository:
    full_name: str = constants.TEST_GITHUB_REPOSITORY
    name: str = constants.TEST_GITHUB_REPOSITORY_NAME
    permissions: MockGithubPermissions = field(default_factory=lambda: MockGithubPermissions())
    milestones: List[MockGithubMilestone] = field(default_factory=list)
    issues: List[MockGithubIssue] = field(default_factory=list)
    pulls: List[MockGithubPull] = field(default_factory=list)

    def get_milestones(self):
        return self.milestones

    def get_issues(self, sort=None, direction=None, since=None, state=None):
        assert state == "all"

        for issue in self.issues:
            if since is None or issue.updated_at >= since.replace(tzinfo=None):
                yield issue

    def get_issue(self, number):
        try:
            return next(i for i in self.issues if i.number == number)
        except StopIteration:
            raise UnknownObjectException(404, {})

    def create_issue(self, title, body=None, milestone=None, labels=[], assignee=None):
        issue = MockGithubIssue(
            body=body,
            title=title,
            labels=[MockGithubLabel(name=l) for l in labels],
            milestone=milestone,
            repository=self,
            assignee=assignee,
        )

        self.issues.append(issue)

        return issue

    def get_pull(self, number):
        try:
            return next(p for p in self.pulls if p.number == number)
        except StopIteration:
            raise UnknownObjectException(404, {})


@dataclass
class MockGithub:
    token: str = constants.TEST_GITHUB_TOKEN
    retry: int = 3
    users: List[MockGithubUser] = field(default_factory=lambda: [_bot_github_user()])

    repositories = []
    valid_tokens = []

    @classmethod
    def reset(cls):
        cls.repositories = [
            MockGithubRepository(
                full_name=constants.TEST_GITHUB_REPOSITORY,
                name=constants.TEST_GITHUB_REPOSITORY_NAME,
                permissions=MockGithubPermissions(admin=False, pull=True, push=True),
                milestones=[MockGithubMilestone(title="7.0.1"), MockGithubMilestone(title="8.5.3")],
            )
        ]
        cls.valid_tokens = [constants.TEST_GITHUB_TOKEN]

    def get_repo(self, full_name):
        if self.token not in MockGithub.valid_tokens:
            raise BadCredentialsException(400, {})

        try:
            return next(r for r in MockGithub.repositories if r.full_name == full_name)
        except StopIteration:
            raise UnknownObjectException(404, {})

    def get_user(self, username=constants.TEST_GITHUB_USER_LOGIN):
        try:
            return next(u for u in self.users if u.login == username)
        except StopIteration:
            raise UnknownObjectException(404, {})


MockGithub.reset()


class MockClient:
    def __init__(self, source):
        self._source = source
        self.issues = []
        self.users = []
        self.pull_request_ids = []
        self.reset_stats()

    def reset_stats(self):
        self.issue_creates = 0
        self.issue_updates = 0
        self.comment_creates = 0
        self.comment_updates = 0
        self.comment_deletes = 0

    def get_user(self, username):
        try:
            return next(u for u in self.users if u.username == username)
        except StopIteration:
            raise Exception(f"Missing User with username {username}")

    def find_issues(self, min_updated_at=None):
        if min_updated_at:
            assert min_updated_at.tzinfo is not None

        for issue in self.issues:
            if min_updated_at is None or issue.updated_at >= min_updated_at:
                yield issue

    def find_other_issue(self, issue):
        if issue.source == Source.JIRA:
            if issue.metadata.github_repository and issue.metadata.github_issue_id:
                try:
                    return next(
                        i
                        for i in self.issues
                        if i.project == issue.metadata.github_repository
                        and i.issue_id == issue.metadata.github_issue_id
                    )
                except StopIteration:
                    return None
            else:
                return None
        else:
            try:
                return next(
                    i
                    for i in self.issues
                    if i.metadata.github_repository == issue.project and i.metadata.github_issue_id == issue.issue_id
                )
            except StopIteration:
                return None

    def get_issue(self, issue_id):
        try:
            return next(i for i in self.issues if i.issue_id == issue_id)
        except StopIteration:
            raise Exception(f"Missing Issue id {issue_id}")

    def create_issue(self, create_fields):
        fields = {
            "source": self._source,
            "is_bot": True,
            "issue_id": self._get_next_issue_id(),
            "project": self._get_project(),
            "created_at": now(),
            "updated_at": now(),
            "user": self._get_user(),
            "is_open": True,
        }

        for field_name in ["title", "is_open", "body", "priority", "issue_type", "metadata"]:
            if create_fields.get(field_name):
                fields[field_name] = create_fields[field_name]

        for field_name in ["labels", "milestones", "components"]:
            if create_fields.get(field_name):
                fields[field_name] = set(create_fields[field_name])

        issue = Issue(**fields)
        self.issues.append(issue)

        self.issue_creates += 1

        return issue

    def update_issue(self, issue, update_fields):
        assert issue.source == self._source

        if ("title" in update_fields or "body" in update_fields) and not issue.is_bot:
            raise ValueError("Cannot update title or body of issue owned by another user")

        fields = issue.__dict__.copy()
        fields["updated_at"] = now()

        for field_name in ["title", "body", "priority", "issue_type", "metadata"]:
            if field_name in update_fields:
                if update_fields[field_name]:
                    fields[field_name] = update_fields[field_name]
                else:
                    fields.pop(field_name)

        for field_name in ["labels", "milestones", "components"]:
            if field_name in update_fields:
                if update_fields[field_name]:
                    fields[field_name] = set(update_fields[field_name])
                else:
                    fields.pop(field_name)

        if "is_open" in update_fields:
            fields["is_open"] = update_fields["is_open"]

        updated_issue = Issue(**fields)
        self.issues = [i for i in self.issues if i.issue_id != issue.issue_id]
        self.issues.append(updated_issue)

        self.issue_updates += 1

        return updated_issue

    def create_comment(self, issue, create_fields):
        assert issue.source == self._source

        fields = {
            "source": self._source,
            "is_bot": True,
            "comment_id": self._get_next_comment_id(),
            "created_at": now(),
            "updated_at": now(),
            "user": self._get_user(),
        }

        for field_name in ["body", "metadata", "issue_metadata"]:
            if create_fields.get(field_name):
                fields[field_name] = create_fields[field_name]

        comment = Comment(**fields)
        issue.comments.append(comment)

        self.comment_creates += 1

        return comment

    def update_comment(self, comment, update_fields):
        assert comment.source == self._source

        if not comment.is_bot:
            raise ValueError("Cannot update comment owned by another user")

        issue = self._get_comment_issue(comment)

        fields = comment.__dict__.copy()
        fields["updated_at"] = now()

        for field_name in ["body", "metadata", "issue_metadata"]:
            if field_name in update_fields:
                if update_fields.get(field_name):
                    fields[field_name] = update_fields[field_name]
                else:
                    fields.pop(field_name)

        updated_comment = Comment(**fields)

        issue.comments.remove(comment)
        issue.comments.append(updated_comment)

        self.comment_updates += 1

    def delete_comment(self, comment):
        assert comment.source == self._source

        if not comment.is_bot:
            raise ValueError("Cannot delete comment owned by another user")

        self._get_comment_issue(comment).comments.remove(comment)

        self.comment_deletes += 1

    def is_issue(self, issue_id):
        if self._source == Source.JIRA:
            raise AttributeError("JIRA Client does not implement is_issue")

        return any(i for i in self.issues if i.issue_id == issue_id)

    def is_pull_request(self, pull_request_id):
        if self._source == Source.JIRA:
            raise AttributeError("JIRA Client does not implement is_pull_request")

        return pull_request_id in self.pull_request_ids

    def _get_comment_issue(self, comment):
        for issue in self.issues:
            if comment in issue.comments:
                return issue

        assert False

    def _get_user(self):
        if self._source == Source.JIRA:
            return User(
                source=Source.JIRA,
                username=constants.TEST_JIRA_USERNAME,
                display_name=constants.TEST_JIRA_USER_DISPLAY_NAME,
            )
        else:
            return User(
                source=Source.GITHUB,
                username=constants.TEST_GITHUB_USER_LOGIN,
                display_name=constants.TEST_GITHUB_USER_NAME,
            )

    def _get_next_issue_id(self):
        if self._source == Source.JIRA:
            return next_jira_issue_id()
        else:
            return next_github_issue_id()

    def _get_project(self):
        if self._source == Source.JIRA:
            return constants.TEST_JIRA_PROJECT_KEY
        else:
            return constants.TEST_GITHUB_REPOSITORY

    def _get_next_comment_id(self):
        return next_comment_id()
