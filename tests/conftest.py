import pytest
from datetime import datetime, timezone

from jirahub.entities import User, Source, Comment, Issue, Metadata
from jirahub.config import JiraConfig, GithubConfig, JirahubConfig
import jirahub.jira
import jirahub.github
import jirahub.permissions

from . import constants
from . import mocks


@pytest.fixture(autouse=True)
def setup_environment(monkeypatch):
    monkeypatch.setenv("JIRAHUB_JIRA_USERNAME", constants.TEST_JIRA_USERNAME)
    monkeypatch.setenv("JIRAHUB_JIRA_PASSWORD", constants.TEST_JIRA_PASSWORD)
    monkeypatch.setenv("JIRAHUB_GITHUB_TOKEN", constants.TEST_GITHUB_TOKEN)


@pytest.fixture(autouse=True)
def mock_raw_clients(monkeypatch):
    monkeypatch.setattr(jirahub.jira, "JIRA", mocks.MockJIRA)
    monkeypatch.setattr(jirahub.permissions, "JIRA", mocks.MockJIRA)
    monkeypatch.setattr(jirahub.github, "Github", mocks.MockGithub)
    monkeypatch.setattr(jirahub.permissions, "Github", mocks.MockGithub)


@pytest.fixture(autouse=True)
def reset_mocks():
    mocks.reset()


@pytest.fixture
def jira_config():
    return JiraConfig(
        server=constants.TEST_JIRA_SERVER,
        project_key=constants.TEST_JIRA_PROJECT_KEY,
        github_issue_url_field_id=12345,
        jirahub_metadata_field_id=67890,
    )


@pytest.fixture
def github_config():
    return GithubConfig(repository=constants.TEST_GITHUB_REPOSITORY)


@pytest.fixture()
def config(jira_config, github_config):
    return JirahubConfig(jira=jira_config, github=github_config)


@pytest.fixture
def jira_client():
    return mocks.MockClient(source=Source.JIRA)


@pytest.fixture
def github_client():
    return mocks.MockClient(source=Source.GITHUB)


@pytest.fixture
def create_user():
    next_id = 1

    def _create_user(source, **kwargs):
        nonlocal next_id

        fields = {
            "source": source,
            "username": f"username{next_id}",
            "display_name": f"Test {source} User {next_id}",
            "raw_user": None,
        }

        fields.update(kwargs)

        next_id += 1

        return User(**fields)

    return _create_user


@pytest.fixture
def create_bot_user():
    def _create_bot_user(source):
        if source == Source.JIRA:
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

    return _create_bot_user


@pytest.fixture
def create_comment(create_user):
    def _create_comment(source, comment_class=Comment, **kwargs):
        comment_id = mocks.next_comment_id()

        fields = {
            "source": source,
            "is_bot": False,
            "created_at": datetime.utcnow().replace(tzinfo=timezone.utc),
            "updated_at": datetime.utcnow().replace(tzinfo=timezone.utc),
            "body": f"Body of comment id {comment_id}.",
            "raw_comment": None,
        }

        fields.update(kwargs)

        if "user" not in fields:
            fields["user"] = create_user(source)

        fields["comment_id"] = mocks.next_comment_id()

        return comment_class(**fields)

    return _create_comment


@pytest.fixture
def create_mirror_comment(create_comment, create_bot_user):
    def _create_mirror_comment(source, source_comment=None, **kwargs):
        kwargs["is_bot"] = True
        kwargs["user"] = create_bot_user(source)

        return create_comment(source, **kwargs)

    return _create_mirror_comment


@pytest.fixture
def create_issue(create_user, create_comment):
    def _create_issue(source, issue_class=Issue, **kwargs):
        if source == Source.JIRA:
            issue_id = mocks.next_jira_issue_id()

            fields = {
                "source": source,
                "is_bot": False,
                "issue_id": issue_id,
                "project": constants.TEST_JIRA_PROJECT_KEY,
                "created_at": datetime.utcnow().replace(tzinfo=timezone.utc),
                "updated_at": datetime.utcnow().replace(tzinfo=timezone.utc),
                "title": f"Title of JIRA issue id {issue_id}",
                "body": f"Body of JIRA issue id {issue_id}.",
                "labels": {"jiralabel1", "jiralabel2"},
                "is_open": True,
                "components": {"jiracomponent1", "jiracomponent2"},
                "raw_issue": None,
                "priority": "Major",
                "issue_type": "Bug",
                "milestones": {"jiramilestone1", "jiramilestone2"},
            }
        else:
            issue_id = mocks.next_github_issue_id()

            fields = {
                "source": source,
                "is_bot": False,
                "issue_id": issue_id,
                "project": constants.TEST_GITHUB_REPOSITORY,
                "created_at": datetime.utcnow().replace(tzinfo=timezone.utc),
                "updated_at": datetime.utcnow().replace(tzinfo=timezone.utc),
                "title": f"Title of GitHub issue id {issue_id}",
                "body": f"Body of GitHub issue id {issue_id}.",
                "labels": {"githublabel1", "githublabel2"},
                "is_open": True,
                "components": {},
                "raw_issue": None,
                "priority": None,
                "issue_type": None,
                "milestones": {"githubmilestone1", "githubmilestone2"},
            }

        fields.update(kwargs)

        if "user" not in fields:
            fields["user"] = create_user(source)

        if "comments" not in fields:
            fields["comments"] = []

        return issue_class(**fields)

    return _create_issue


@pytest.fixture
def create_mirror_issue(create_issue, create_bot_user):
    def _create_mirror_issue(source, source_issue=None, **kwargs):
        kwargs["is_bot"] = True
        kwargs["user"] = create_bot_user(source)

        if source == Source.JIRA and source_issue:
            kwargs["metadata"] = Metadata(github_repository=source_issue.project, github_issue_id=source_issue.issue_id)

        return create_issue(source, **kwargs)

    return _create_mirror_issue
