import pytest
import json
from typing import Generator
from datetime import datetime, timedelta, timezone

from jirahub import jira
from jirahub.entities import Source, User, Metadata, CommentMetadata
from jirahub.utils import UrlHelper

from . import constants, mocks


def test_get_username():
    assert jira.get_username() == constants.TEST_JIRA_USERNAME


def test_get_password():
    assert jira.get_password() == constants.TEST_JIRA_PASSWORD


class TestClient:
    @pytest.fixture
    def mock_jira(self):
        return mocks.MockJIRA(
            server=constants.TEST_JIRA_SERVER, basic_auth=(constants.TEST_JIRA_USERNAME, constants.TEST_JIRA_PASSWORD)
        )

    @pytest.fixture
    def client(self, config, mock_jira):
        return jira.Client(config=config, jira=mock_jira, bot_username=constants.TEST_JIRA_USERNAME)

    def test_from_config(self, config):
        # Just "asserting" that there are no exceptions here.
        result = jira.Client.from_config(config)
        assert isinstance(result, jira.Client)

    def test_init(self, config, mock_jira):
        # Just "asserting" that there are no exceptions here.
        jira.Client(config=config, jira=mock_jira, bot_username=constants.TEST_JIRA_USERNAME)

    def test_get_user(self, client, mock_jira):
        mock_jira.users.append(mocks.MockJIRAUser("testusername123", "Test User 123"))
        mock_jira.users.append(mocks.MockJIRAUser("nodisplayname", None))

        user = client.get_user("testusername123")
        assert user.username == "testusername123"
        assert user.display_name == "Test User 123"

        user = client.get_user("nodisplayname")
        assert user.username == "nodisplayname"
        assert user.display_name == "nodisplayname"

        with pytest.raises(Exception):
            client.get_user("nope")

    def test_find_issues(self, client, mock_jira):
        result = client.find_issues()
        assert isinstance(result, Generator)
        assert len(list(result)) == 0

        mock_jira.create_issue(fields={"project": constants.TEST_JIRA_PROJECT_KEY, "summary": "Test issue"})

        result = list(client.find_issues())
        assert len(result) == 1

    def test_find_issues_paging(self, client, mock_jira):
        issue_ids = set()
        num_issues = client._PAGE_SIZE * 2 + 1
        for i in range(num_issues):
            raw_issue = mock_jira.create_issue(
                fields={"project": constants.TEST_JIRA_PROJECT_KEY, "summary": f"Test issue {i}"}
            )
            issue_ids.add(raw_issue.key)

        found_issue_ids = set()
        issue_count = 0
        for issue in client.find_issues():
            issue_count += 1
            found_issue_ids.add(issue.issue_id)

        assert issue_count == num_issues
        assert found_issue_ids == issue_ids

    def test_find_issues_min_updated_at(self, client, mock_jira):
        now = datetime.utcnow().replace(tzinfo=timezone.utc)

        result = client.find_issues(min_updated_at=now)
        assert isinstance(result, Generator)
        assert len(list(result)) == 0

        mock_jira.create_issue(fields={"project": constants.TEST_JIRA_PROJECT_KEY, "summary": "Test issue"})

        result = list(client.find_issues(min_updated_at=now + timedelta(seconds=1)))
        assert len(result) == 0

        result = list(client.find_issues(min_updated_at=now - timedelta(seconds=1)))
        assert len(result) == 1

    def test_find_other_issue(self, client, mock_jira, create_issue):
        github_issue = create_issue(Source.GITHUB)

        assert client.find_other_issue(github_issue) is None

        raw_jira_issue = mock_jira.create_issue(
            fields={
                "project": constants.TEST_JIRA_PROJECT_KEY,
                "summary": "Test issue",
                "customfield_12345": f"https://github.com/testing/test-repo/issues/{github_issue.issue_id}",
            }
        )
        result = client.find_other_issue(github_issue)
        assert result.issue_id == raw_jira_issue.key

        mock_jira.create_issue(
            fields={
                "project": constants.TEST_JIRA_PROJECT_KEY,
                "summary": "Test issue",
                "customfield_12345": f"https://github.com/testing/test-repo/issues/{github_issue.issue_id}",
            }
        )
        with pytest.raises(RuntimeError):
            client.find_other_issue(github_issue)

    def test_get_issue(self, client, mock_jira):
        raw_issue = mock_jira.create_issue({"project": constants.TEST_JIRA_PROJECT_KEY, "summary": "Test issue"})

        result = client.get_issue(raw_issue.key)

        assert result.issue_id == raw_issue.key

    def test_get_issue_bad_metadata(self, client, mock_jira):
        raw_issue = mock_jira.create_issue(
            {
                "project": constants.TEST_JIRA_PROJECT_KEY,
                "summary": "Test issue",
                "customfield_67890": "definitely not JSON",
            }
        )

        result = client.get_issue(raw_issue.key)

        assert result.metadata.comments == []

    def test_get_issue_missing(self, client):
        with pytest.raises(Exception):
            client.get_issue("TEST-123456")

    def test_create_issue_all_fields(self, client, mock_jira, config):
        result = client.create_issue(
            {
                "title": "Test issue",
                "body": "This is an issue body.",
                "labels": ["label1", "label2"],
                "priority": "Critical",
                "issue_type": "Task",
                "milestones": ["7.1.0", "8.5.3"],
                "components": ["toaster", "fridge"],
                "metadata": Metadata(
                    github_repository="testing/test-repo",
                    github_issue_id=451,
                    comments=[CommentMetadata(jira_comment_id=18, github_comment_id=100)],
                ),
            }
        )

        assert result.title == "Test issue"
        assert result.body == "This is an issue body."
        assert result.labels == {"label1", "label2"}
        assert result.priority == "Critical"
        assert result.issue_type == "Task"
        assert result.milestones == {"7.1.0", "8.5.3"}
        assert result.components == {"toaster", "fridge"}
        assert result.metadata.github_repository == "testing/test-repo"
        assert result.metadata.github_issue_id == 451
        assert len(result.metadata.comments) == 1
        assert result.metadata.comments[0].jira_comment_id == 18
        assert result.metadata.comments[0].github_comment_id == 100
        assert result.is_open is True

        assert len(mock_jira.issues) == 1
        raw_issue = mock_jira.issues[0]

        assert raw_issue.fields.summary == "Test issue"
        assert raw_issue.fields.description.startswith("This is an issue body.")
        assert set(raw_issue.fields.labels) == {"label1", "label2"}
        assert set(v.name for v in raw_issue.fields.fixVersions) == {"7.1.0", "8.5.3"}
        assert set(c.name for c in raw_issue.fields.components) == {"toaster", "fridge"}
        assert raw_issue.fields.priority.name == "Critical"
        assert raw_issue.fields.issuetype.name == "Task"
        assert raw_issue.fields.status.name == constants.TEST_JIRA_DEFAULT_STATUS
        assert raw_issue.fields.customfield_12345 == "https://github.com/testing/test-repo/issues/451"

        metadata_json = raw_issue.fields.customfield_67890
        metadata = json.loads(metadata_json)
        assert len(metadata["comments"]) == 1
        assert metadata["comments"][0]["jira_comment_id"] == 18
        assert metadata["comments"][0]["github_comment_id"] == 100

    def test_create_issue_minimum_fields(self, client, mock_jira):
        result = client.create_issue({"title": "Test issue"})

        assert result.title == "Test issue"
        assert result.priority == constants.TEST_JIRA_DEFAULT_PRIORITY
        assert result.issue_type == constants.TEST_JIRA_DEFAULT_ISSUE_TYPE
        assert result.is_open is True

        assert len(mock_jira.issues) == 1
        raw_issue = mock_jira.issues[0]

        assert raw_issue.fields.summary == "Test issue"

    def test_create_issue_custom_field(self, client, mock_jira):
        result = client.create_issue({"title": "Test issue", "custom_field": "custom value"})

        assert result.title == "Test issue"
        assert result.priority == constants.TEST_JIRA_DEFAULT_PRIORITY
        assert result.issue_type == constants.TEST_JIRA_DEFAULT_ISSUE_TYPE
        assert result.is_open is True

        assert len(mock_jira.issues) == 1
        raw_issue = mock_jira.issues[0]

        assert raw_issue.fields.custom_field == "custom value"

    def test_update_issue(self, client, mock_jira):
        raw_issue = mock_jira.create_issue({"project": constants.TEST_JIRA_PROJECT_KEY, "summary": "Test issue"})

        issue = client.get_issue(raw_issue.key)

        client.update_issue(issue, {"title": "New title"})

        assert raw_issue.fields.summary == "New title"

    def test_update_issue_other_user(self, client):
        issue = client.create_issue({"title": "Test issue"})
        issue.raw_issue.fields.creator = mocks.MockJIRAUser("somestranger", "Some Stranger")
        issue = client.get_issue(issue.issue_id)

        client.update_issue(issue, {"labels": ["fee", "fi", "fo", "fum"]})
        issue = client.get_issue(issue.issue_id)
        assert issue.labels == {"fee", "fi", "fo", "fum"}

        with pytest.raises(Exception):
            client.update_issue(issue, {"title": "nope"})

        with pytest.raises(Exception):
            client.update_issue(issue, {"body": "nope"})

    def test_update_issue_wrong_source(self, client, create_issue):
        github_issue = create_issue(Source.GITHUB)

        with pytest.raises(AssertionError):
            client.update_issue(github_issue, {"title": "nope"})

    def test_issue_status_behavior(self, client, mock_jira, config):
        config.jira.closed_statuses = {"closed", "done"}

        config.jira.open_status = None
        issue = client.create_issue({"title": "Test issue"})
        assert issue.raw_issue.fields.status.name == constants.TEST_JIRA_DEFAULT_STATUS
        client.update_issue(issue, {"is_open": False})
        assert issue.raw_issue.fields.status.name == config.jira.close_status
        client.update_issue(issue, {"is_open": True})
        assert issue.raw_issue.fields.status.name == config.jira.reopen_status
        issue = client.create_issue({"title": "Test issue", "is_open": True})
        assert issue.raw_issue.fields.status.name == constants.TEST_JIRA_DEFAULT_STATUS
        issue = client.create_issue({"title": "Test issue", "is_open": False})
        assert issue.raw_issue.fields.status.name == config.jira.close_status

        config.jira.open_status = "Rarin To Go"
        issue = client.create_issue({"title": "Test issue"})
        assert issue.raw_issue.fields.status.name == config.jira.open_status
        client.update_issue(issue, {"is_open": False})
        assert issue.raw_issue.fields.status.name == config.jira.close_status
        client.update_issue(issue, {"is_open": True})
        assert issue.raw_issue.fields.status.name == config.jira.reopen_status
        issue = client.create_issue({"title": "Test issue", "is_open": True})
        assert issue.raw_issue.fields.status.name == config.jira.open_status
        issue = client.create_issue({"title": "Test issue", "is_open": False})
        assert issue.raw_issue.fields.status.name == config.jira.close_status

        raw_issue = mock_jira.create_issue(
            {"project": constants.TEST_JIRA_PROJECT_KEY, "summary": "Test issue", "status": {"name": "Done"}}
        )
        assert raw_issue.fields.status.name == "Done"
        issue = client.get_issue(raw_issue.key)
        assert issue.is_open is False

        raw_issue = mock_jira.create_issue(
            {"project": constants.TEST_JIRA_PROJECT_KEY, "summary": "Test issue", "status": {"name": "Ready"}}
        )
        assert raw_issue.fields.status.name == "Ready"
        issue = client.get_issue(raw_issue.key)
        assert issue.is_open is True

    def test_issue_fields_round_trip(self, client, config):
        issue = client.create_issue(
            {
                "title": "Original title",
                "body": "Original body",
                "milestones": ["originalmilestone1", "originalmilestone2"],
                "labels": ["originallabel1", "originallabel2"],
                "priority": "Original Priority",
                "issue_type": "Original Type",
                "components": ["originalcomponent1", "originalcomponent2"],
                "metadata": Metadata(
                    github_repository="testing/test-repo",
                    github_issue_id=451,
                    comments=[CommentMetadata(jira_comment_id=18, github_comment_id=100)],
                ),
            }
        )
        issue_id = issue.issue_id

        issue = client.get_issue(issue_id)
        assert issue.source == Source.JIRA
        assert issue.title == "Original title"
        assert issue.body == "Original body"
        assert issue.milestones == {"originalmilestone1", "originalmilestone2"}
        assert issue.labels == {"originallabel1", "originallabel2"}
        assert issue.priority == "Original Priority"
        assert issue.issue_type == "Original Type"
        assert issue.components == {"originalcomponent1", "originalcomponent2"}
        assert issue.is_bot is True
        assert issue.issue_id == issue_id
        assert issue.project == constants.TEST_JIRA_PROJECT_KEY
        assert abs(datetime.utcnow().replace(tzinfo=timezone.utc) - issue.created_at) < timedelta(seconds=1)
        assert issue.created_at.tzinfo == timezone.utc
        assert abs(datetime.utcnow().replace(tzinfo=timezone.utc) - issue.created_at) < timedelta(seconds=1)
        assert issue.updated_at.tzinfo == timezone.utc
        assert issue.user.source == Source.JIRA
        assert issue.user.username == constants.TEST_JIRA_USERNAME
        assert issue.user.display_name == constants.TEST_JIRA_USER_DISPLAY_NAME
        assert issue.metadata.github_repository == "testing/test-repo"
        assert issue.metadata.github_issue_id == 451
        assert len(issue.metadata.comments) == 1
        assert issue.metadata.comments[0].jira_comment_id == 18
        assert issue.metadata.comments[0].github_comment_id == 100
        assert issue.is_open is True

        client.update_issue(
            issue,
            {
                "title": "Updated title",
                "body": "Updated body",
                "milestones": ["updatedmilestone1", "updatedmilestone2"],
                "labels": ["updatedlabel1", "updatedlabel2"],
                "priority": "Updated Priority",
                "issue_type": "Updated Type",
                "components": ["updatedcomponent1", "updatedcomponent2"],
                "metadata": Metadata(
                    github_repository="testing/test-repo2",
                    github_issue_id=4512,
                    comments=[CommentMetadata(jira_comment_id=182, github_comment_id=1002)],
                ),
                "is_open": False,
            },
        )
        issue = client.get_issue(issue_id)
        assert issue.title == "Updated title"
        assert issue.body == "Updated body"
        assert issue.milestones == {"updatedmilestone1", "updatedmilestone2"}
        assert issue.labels == {"updatedlabel1", "updatedlabel2"}
        assert issue.priority == "Updated Priority"
        assert issue.issue_type == "Updated Type"
        assert issue.components == {"updatedcomponent1", "updatedcomponent2"}
        assert issue.metadata.github_repository == "testing/test-repo2"
        assert issue.metadata.github_issue_id == 4512
        assert len(issue.metadata.comments) == 1
        assert issue.metadata.comments[0].jira_comment_id == 182
        assert issue.metadata.comments[0].github_comment_id == 1002
        assert issue.is_open is False

        client.update_issue(issue, {"is_open": True})
        issue = client.get_issue(issue_id)
        assert issue.is_open is True

        client.update_issue(
            issue,
            {
                "body": None,
                "milestones": [],
                "labels": [],
                "components": [],
                "priority": None,
                "issue_type": None,
                "metadata": None,
            },
        )
        issue = client.get_issue(issue_id)
        assert issue.title == "Updated title"
        assert issue.body == ""
        assert issue.milestones == set()
        assert issue.labels == set()
        assert issue.components == set()
        assert issue.priority is None
        assert issue.issue_type is None
        assert issue.metadata.github_repository is None
        assert issue.metadata.github_issue_id is None
        assert issue.metadata.comments == []

        client.update_issue(
            issue, {"body": None, "milestones": None, "labels": None, "components": None, "metadata": None}
        )
        issue = client.get_issue(issue_id)
        assert issue.title == "Updated title"
        assert issue.body == ""
        assert issue.milestones == set()
        assert issue.labels == set()
        assert issue.components == set()
        assert issue.metadata.github_repository is None
        assert issue.metadata.github_issue_id is None
        assert issue.metadata.comments == []

    def test_non_mirror_issue(self, client, mock_jira):
        raw_issue = mock_jira.create_issue(fields={"project": constants.TEST_JIRA_PROJECT_KEY, "summary": "Test issue"})
        raw_issue.fields.creator = mocks.MockJIRAUser("somestranger", "Some Stranger")
        issue = client.get_issue(raw_issue.key)

        assert issue.is_bot is False

    def test_issue_with_comments(self, client, mock_jira):
        raw_issue = mock_jira.create_issue(fields={"project": constants.TEST_JIRA_PROJECT_KEY, "summary": "Test issue"})
        [mock_jira.add_comment(raw_issue.key, f"This is comment #{i+1}") for i in range(3)]

        issue = client.get_issue(raw_issue.key)

        assert len(issue.comments) == 3
        for i in range(3):
            assert issue.comments[i].body == f"This is comment #{i+1}"

    def test_create_comment(self, client, mock_jira):
        issue = client.create_issue({"title": "Issue title"})

        client.create_comment(issue, {"body": "Comment body"})

        assert len(mock_jira.comments_list) == 1
        raw_comment = mock_jira.comments_list[0]

        assert raw_comment.issue_key == issue.issue_id
        assert raw_comment.body == "Comment body"

    def test_create_comment_wrong_source(self, client, create_issue):
        github_issue = create_issue(Source.GITHUB)

        with pytest.raises(AssertionError):
            client.create_comment(github_issue, {"body": "nope"})

    def test_update_comment(self, client, mock_jira):
        issue = client.create_issue({"title": "Issue title"})
        comment = client.create_comment(issue, {"body": "Original comment body"})

        client.update_comment(comment, {"body": "Updated comment body"})

        assert mock_jira.comments_list[0].body == "Updated comment body"

    def test_update_comment_other_user(self, client):
        issue = client.create_issue({"title": "Test issue"})
        comment = client.create_comment(issue, {"body": "Comment body"})
        comment.raw_comment.author = mocks.MockJIRAUser("somestranger", "Some Stranger")
        comment = client.get_issue(issue.issue_id).comments[0]

        with pytest.raises(Exception):
            client.update_comment(comment, {"body": "nope"})

    def test_update_comment_wrong_source(self, client, create_comment):
        github_comment = create_comment(Source.GITHUB)

        with pytest.raises(AssertionError):
            client.update_comment(github_comment, {"body": "nope"})

    def test_delete_comment(self, client, mock_jira):
        issue = client.create_issue({"title": "Issue title"})
        comment = client.create_comment(issue, {"body": "Comment body"})

        assert len(mock_jira.comments_list) == 1

        client.delete_comment(comment)

        assert len(mock_jira.comments_list) == 0

    def test_delete_comment_wrong_source(self, client, create_comment):
        github_comment = create_comment(Source.GITHUB)

        with pytest.raises(AssertionError):
            client.delete_comment(github_comment)

    def test_delete_comment_wrong_user(self, client, create_comment):
        comment = create_comment(Source.JIRA)

        with pytest.raises(ValueError):
            client.delete_comment(comment)

    def test_non_mirror_comment(self, client, mock_jira):
        raw_issue = mock_jira.create_issue(fields={"project": constants.TEST_JIRA_PROJECT_KEY, "summary": "Test issue"})
        raw_comment = mock_jira.add_comment(issue=raw_issue.key, body="Test comment body")
        raw_comment.author = mocks.MockJIRAUser("somestranger", "Some Stranger")

        issue = client.get_issue(raw_issue.key)

        assert issue.comments[0].is_bot is False

    def test_comment_fields_round_trip(self, client):
        issue = client.create_issue({"title": "Issue title"})
        comment = client.create_comment(issue, {"body": "Original comment body"})

        issue_id = issue.issue_id

        comment = client.get_issue(issue_id).comments[0]

        assert comment.source == Source.JIRA
        assert comment.is_bot is True
        assert comment.comment_id == comment.comment_id
        assert abs(datetime.utcnow().replace(tzinfo=timezone.utc) - comment.created_at) < timedelta(seconds=1)
        assert comment.created_at.tzinfo == timezone.utc
        assert abs(datetime.utcnow().replace(tzinfo=timezone.utc) - comment.created_at) < timedelta(seconds=1)
        assert comment.updated_at.tzinfo == timezone.utc
        assert comment.user.source == Source.JIRA
        assert comment.user.username == constants.TEST_JIRA_USERNAME
        assert comment.user.display_name == constants.TEST_JIRA_USER_DISPLAY_NAME
        assert comment.body == "Original comment body"

        client.update_comment(comment, {"body": "Updated comment body"})

        comment = client.get_issue(issue_id).comments[0]

        assert comment.body == "Updated comment body"


class TestFormatter:
    @pytest.fixture
    def formatter(self, config, github_client):
        url_helper = UrlHelper.from_config(config)
        return jira.Formatter(config, url_helper, github_client)

    @pytest.mark.parametrize(
        "url, link_text, expected",
        [
            ("https://www.example.com", None, "[https://www.example.com]"),
            ("https://www.example.com", "link text", "[link text|https://www.example.com]"),
        ],
    )
    def test_format_link(self, formatter, url, link_text, expected):
        assert formatter.format_link(url=url, link_text=link_text) == expected

    @pytest.mark.parametrize(
        "body, expected",
        [
            ("This is a body without formatting.", "This is a body without formatting."),
            (
                "This is a body with a unadorned URL: https://www.example.com",
                "This is a body with a unadorned URL: [https://www.example.com]",
            ),
            (
                "This is a body with a GitHub formatted link, but no link text: <https://www.example.com>",
                "This is a body with a GitHub formatted link, but no link text: [https://www.example.com]",
            ),
            (
                "This is a body with a [GitHub formatted external link](https://www.example.com).",
                "This is a body with a [GitHub formatted external link|https://www.example.com].",
            ),
            (
                "This is a body with a [GitHub issue link](https://github.com/testing/test-repo/issues/2) with link text.",
                "This is a body with a [GitHub issue link|https://github.com/testing/test-repo/issues/2] with link text.",
            ),
            (
                "This is a body with a GitHub mention: @username123",
                "This is a body with a GitHub mention: [Test User 123|https://github.com/username123]",
            ),
            (
                "This is a body with a GitHub mention that doesn't exist: @missing",
                "This is a body with a GitHub mention that doesn't exist: @missing",
            ),
            (
                "This is a link to a GitHub issue in the same repo: #2",
                "This is a link to a GitHub issue in the same repo: [#2|https://github.com/testing/test-repo/issues/2]",
            ),
            (
                "This is a link to a GitHub issue in another repo: testing/other-test-repo#5",
                "This is a link to a GitHub issue in another repo: testing/other-test-repo#5",
            ),
            (
                "This is a link to a GitHub PR in the same repo: #4",
                "This is a link to a GitHub PR in the same repo: [#4|https://github.com/testing/test-repo/pull/4]",
            ),
            (
                "This is a link to a GitHub issue/PR that doesn't exist: #43",
                "This is a link to a GitHub issue/PR that doesn't exist: #43",
            ),
            (
                "This is a link to a GitHub PR in another repo: testing/other-test-repo#6",
                "This is a link to a GitHub PR in another repo: testing/other-test-repo#6",
            ),
            (
                "This is a body with **bold**, *italic*, and `monospaced` text.",
                "This is a body with *bold*, _italic_, and {{monospaced}} text.",
            ),
            (
                "This is a body with ~~deleted~~, <ins>inserted</ins>, <sup>superscript</sup>, and <sub>subscript</sub> text.",
                "This is a body with -deleted-, +inserted+, ^superscript^, and ~subscript~ text.",
            ),
            (
                """This body has a block of Python code in it:
```python
import sys
sys.stdout.write("Hello, world!")
sys.stdout.write("\n")
```""",
                """This body has a block of Python code in it:
{code:python}
import sys
sys.stdout.write("Hello, world!")
sys.stdout.write("\n")
{code}""",
            ),
            (
                """This body forgot to close its preformatted block:
```
Whoopsie daisies""",
                """This body forgot to close its preformatted block:
{noformat}
Whoopsie daisies{noformat}""",
            ),
            (
                """This body has a preformatted block of text in it:
```
  Ain't no formatting *here*!
```""",
                """This body has a preformatted block of text in it:
{noformat}
  Ain't no formatting *here*!
{noformat}""",
            ),
            (
                """This body has a quote block in it:
> Quotes are great!
> Turns out there **is** formatting in here!
""",
                """This body has a quote block in it:
{quote}
Quotes are great!
Turns out there *is* formatting in here!
{quote}""",
            ),
            (
                "> This is a single line quote",
                """{quote}
This is a single line quote
{quote}""",
            ),
            ("# What a heading", "h1. What a heading"),
            ("## What a heading", "h2. What a heading"),
            ("### What a heading", "h3. What a heading"),
            ("#### What a heading", "h4. What a heading"),
            ("##### What a heading", "h5. What a heading"),
            ("###### What a heading", "h6. What a heading"),
        ],
    )
    def test_format_body(self, formatter, body, expected, github_client, create_issue):
        github_client.users.append(User(Source.GITHUB, "username123", "Test User 123"))
        github_client.issues.append(create_issue(Source.GITHUB, issue_id=2))
        github_client.pull_request_ids.append(4)

        assert formatter.format_body(body) == expected
