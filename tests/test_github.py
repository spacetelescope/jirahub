import pytest

from typing import Generator
from datetime import datetime, timedelta, timezone

from jirahub import github
from jirahub.entities import Source, User, Metadata
from jirahub.utils import UrlHelper

from . import constants, mocks


def test_get_token():
    assert github.get_token() == constants.TEST_GITHUB_TOKEN


class TestClient:
    @pytest.fixture
    def mock_repo(self):
        return mocks.MockGithub.repositories[0]

    @pytest.fixture
    def mock_github(self):
        return mocks.MockGithub()

    @pytest.fixture
    def client(self, config, mock_github):
        return github.Client(config, mock_github)

    def test_from_config(self, config):
        # Just "asserting" that there are no exceptions here.
        client = github.Client.from_config(config)
        assert isinstance(client, github.Client)

    def test_init(self, config, mock_github):
        # Just "asserting" that there are no exceptions here.
        github.Client(config, mock_github)

    def test_init_bad_credentials(self, config):
        with pytest.raises(Exception):
            github.Client(config, mocks.MockGithub(token="nope"))

    def test_init_missing_repo(self, config):
        config.github.repository = "testing/nope"
        with pytest.raises(Exception):
            github.Client(config, mocks.MockGithub())

    def test_get_user(self, client, mock_github):
        mock_github.users.append(mocks.MockGithubUser("testusername123", "Test User 123"))
        mock_github.users.append(mocks.MockGithubUser("nodisplayname", None))

        user = client.get_user("testusername123")
        assert user.username == "testusername123"
        assert user.display_name == "Test User 123"

        user = client.get_user("nodisplayname")
        assert user.username == "nodisplayname"
        assert user.display_name == "nodisplayname"

        with pytest.raises(Exception):
            client.get_user("nope")

    def test_find_issues(self, client, mock_repo):
        result = client.find_issues()
        assert isinstance(result, Generator)
        assert len(list(result)) == 0

        mock_repo.create_issue(title="Test issue")

        result = list(client.find_issues())
        assert len(result) == 1

    def test_find_issues_min_updated_at(self, client, mock_repo):
        now = datetime.utcnow().replace(tzinfo=timezone.utc)

        result = client.find_issues(min_updated_at=now)
        assert isinstance(result, Generator)
        assert len(list(result)) == 0

        mock_repo.create_issue(title="Test issue")

        result = list(client.find_issues(min_updated_at=now + timedelta(seconds=1)))
        assert len(result) == 0

        result = list(client.find_issues(min_updated_at=now - timedelta(seconds=1)))
        assert len(result) == 1

    def test_find_other_issue(self, client, mock_repo, create_issue):
        jira_issue = create_issue(Source.JIRA)

        assert client.find_other_issue(jira_issue) is None

        raw_github_issue = mock_repo.create_issue(title="Test issue")
        jira_issue = create_issue(
            Source.JIRA,
            metadata=Metadata(
                github_repository=constants.TEST_GITHUB_REPOSITORY, github_issue_id=raw_github_issue.number
            ),
        )

        result = client.find_other_issue(jira_issue)
        assert result.issue_id == raw_github_issue.number

    def test_get_issue(self, client, mock_repo):
        raw_issue = mock_repo.create_issue(title="Test issue")

        result = client.get_issue(raw_issue.number)

        assert result.issue_id == raw_issue.number

    def test_get_issue_missing(self, client):
        with pytest.raises(Exception):
            client.get_issue(12390)

    def test_create_issue_all_fields(self, client, mock_repo):
        result = client.create_issue(
            {
                "title": "Test issue",
                "body": "This is an issue body.",
                "labels": ["label1", "label2"],
                "milestones": [mock_repo.milestones[0].title],
            }
        )

        assert result.title == "Test issue"
        assert result.body == "This is an issue body."
        assert result.labels == {"label1", "label2"}
        assert result.milestones == {mock_repo.milestones[0].title}

        assert len(mock_repo.issues) == 1
        raw_issue = mock_repo.issues[0]

        assert raw_issue.title == "Test issue"
        assert raw_issue.body.startswith("This is an issue body.")
        assert set([l.name for l in raw_issue.labels]) == {"label1", "label2"}
        assert raw_issue.milestone == mock_repo.milestones[0]

    def test_create_issue_minimum_fields(self, client, mock_repo):
        result = client.create_issue({"title": "Test issue"})

        assert result.title == "Test issue"
        assert len(mock_repo.issues) == 1
        assert mock_repo.issues[0].title == "Test issue"

    def test_create_issue_custom_field(self, client, mock_repo):
        result = client.create_issue({"title": "Test issue", "assignee": "big.bird"})

        assert result.title == "Test issue"
        assert len(mock_repo.issues) == 1
        assert mock_repo.issues[0].assignee == "big.bird"

    def test_create_issue_milestone_behavior(self, client, mock_repo):
        # Milestone that doesn't exist:
        client.create_issue({"title": "Test issue", "milestones": ["10.12.4"]})

        assert len(mock_repo.issues) == 1
        assert mock_repo.issues[0].milestone is None

        mock_repo.issues = []

        # One milestone that does exist, and one that does not:
        client.create_issue({"title": "Test issue", "milestones": ["10.12.4", mock_repo.milestones[0].title]})

        assert len(mock_repo.issues) == 1
        assert mock_repo.issues[0].milestone == mock_repo.milestones[0]

        mock_repo.issues = []

        # Multiple milestones exist:
        client.create_issue(
            {
                "title": "Test issue",
                "milestones": ["10.12.4", mock_repo.milestones[1].title, mock_repo.milestones[0].title],
            }
        )

        assert len(mock_repo.issues) == 1
        assert mock_repo.issues[0].milestone == mock_repo.milestones[1]

        mock_repo.issues = []

        # Update to a milestone that doesn't exist:
        issue = client.create_issue({"title": "Test issue"})
        client.update_issue(issue, {"milestones": ["10.12.4"]})

        assert len(mock_repo.issues) == 1
        assert mock_repo.issues[0].milestone is None

    def test_update_issue(self, client, mock_repo):
        raw_issue = mock_repo.create_issue(title="Test issue")

        issue = client.get_issue(raw_issue.number)

        client.update_issue(issue, {"title": "New title"})

        assert raw_issue.title == "New title"

    def test_update_issue_other_user(self, client):
        issue = client.create_issue({"title": "Test issue"})
        issue.raw_issue.user = mocks.MockGithubUser("somestranger", "Some Stranger")
        issue = client.get_issue(issue.issue_id)

        client.update_issue(issue, {"labels": ["fee", "fi", "fo", "fum"]})
        issue = client.get_issue(issue.issue_id)
        assert issue.labels == {"fee", "fi", "fo", "fum"}

        with pytest.raises(Exception):
            client.update_issue(issue, {"title": "nope"})

        with pytest.raises(Exception):
            client.update_issue(issue, {"body": "nope"})

    def test_update_issue_wrong_source(self, client, create_issue):
        jira_issue = create_issue(Source.JIRA)

        with pytest.raises(AssertionError):
            client.update_issue(jira_issue, {"title": "nope"})

    def test_issue_fields_round_trip(self, client, mock_repo):
        issue = client.create_issue(
            {
                "title": "Original title",
                "body": "Original body",
                "milestones": [mock_repo.milestones[0].title],
                "labels": ["originallabel1", "originallabel2"],
            }
        )

        issue_id = issue.issue_id

        issue = client.get_issue(issue_id)

        assert issue.source == Source.GITHUB
        assert issue.title == "Original title"
        assert issue.body == "Original body"
        assert issue.milestones == {mock_repo.milestones[0].title}
        assert issue.labels == {"originallabel1", "originallabel2"}
        assert issue.is_bot is True
        assert issue.issue_id == issue_id
        assert issue.project == constants.TEST_GITHUB_REPOSITORY
        assert abs(datetime.utcnow().replace(tzinfo=timezone.utc) - issue.created_at) < timedelta(seconds=1)
        assert issue.created_at.tzinfo == timezone.utc
        assert abs(datetime.utcnow().replace(tzinfo=timezone.utc) - issue.created_at) < timedelta(seconds=1)
        assert issue.updated_at.tzinfo == timezone.utc
        assert issue.user.source == Source.GITHUB
        assert issue.user.username == constants.TEST_GITHUB_USER_LOGIN
        assert issue.user.display_name == constants.TEST_GITHUB_USER_NAME
        assert issue.is_open is True

        client.update_issue(
            issue,
            {
                "title": "Updated title",
                "body": "Updated body",
                "milestones": [mock_repo.milestones[1].title],
                "labels": ["updatedlabel1", "updatedlabel2"],
                "is_open": False,
            },
        )

        issue = client.get_issue(issue_id)

        assert issue.title == "Updated title"
        assert issue.body == "Updated body"
        assert issue.milestones == {mock_repo.milestones[1].title}
        assert issue.labels == {"updatedlabel1", "updatedlabel2"}
        assert issue.is_open is False

        client.update_issue(issue, {"is_open": True})

        issue = client.get_issue(issue_id)

        assert issue.is_open is True

        client.update_issue(issue, {"body": None, "milestones": None, "labels": None})

        issue = client.get_issue(issue_id)

        assert issue.title == "Updated title"
        assert issue.body == ""
        assert issue.milestones == set()
        assert issue.labels == set()

    def test_non_mirror_issue(self, client, mock_repo):
        raw_issue = mock_repo.create_issue(title="Test issue")
        raw_issue.user = mocks.MockGithubUser("somestranger", "Some Stranger")

        issue = client.get_issue(raw_issue.number)

        assert issue.is_bot is False

    def test_issue_with_comments(self, client, mock_repo):
        raw_issue = mock_repo.create_issue(title="Test issue")
        [raw_issue.create_comment(f"This is comment #{i+1}") for i in range(3)]

        issue = client.get_issue(raw_issue.number)

        assert len(issue.comments) == 3
        for i in range(3):
            assert issue.comments[i].body == f"This is comment #{i+1}"

    def test_create_comment(self, client, mock_repo):
        issue = client.create_issue({"title": "Issue title"})

        client.create_comment(issue, {"body": "Comment body"})

        raw_issue = mock_repo.issues[0]
        assert len(raw_issue.comments) == 1
        raw_comment = raw_issue.comments[0]

        assert raw_comment.body == "Comment body"

    def test_create_comment_wrong_source(self, client, create_issue):
        jira_issue = create_issue(Source.JIRA)

        with pytest.raises(AssertionError):
            client.create_comment(jira_issue, {"body": "nope"})

    def test_update_comment(self, client, mock_repo):
        issue = client.create_issue({"title": "Issue title"})
        comment = client.create_comment(issue, {"body": "Original comment body"})

        client.update_comment(comment, {"body": "Updated comment body"})

        assert mock_repo.issues[0].comments[0].body == "Updated comment body"

    def test_update_comment_other_user(self, client):
        issue = client.create_issue({"title": "Test issue"})
        comment = client.create_comment(issue, {"body": "Comment body"})
        comment.raw_comment.user = mocks.MockGithubUser("somestranger", "Some Stranger")
        comment = client.get_issue(issue.issue_id).comments[0]

        with pytest.raises(Exception):
            client.update_comment(comment, {"body": "nope"})

    def test_update_comment_wrong_source(self, client, create_comment):
        jira_comment = create_comment(Source.JIRA)

        with pytest.raises(AssertionError):
            client.update_comment(jira_comment, {"body": "nope"})

    def test_delete_comment(self, client, mock_repo):
        issue = client.create_issue({"title": "Issue title"})
        comment = client.create_comment(issue, {"body": "Comment body"})

        assert len(mock_repo.issues[0].comments) == 1

        client.delete_comment(comment)

        assert len(mock_repo.issues[0].comments) == 0

    def test_delete_comment_wrong_source(self, client, create_comment):
        jira_comment = create_comment(Source.JIRA)

        with pytest.raises(AssertionError):
            client.delete_comment(jira_comment)

    def test_delete_comment_wrong_user(self, client, create_comment):
        comment = create_comment(Source.GITHUB)

        with pytest.raises(ValueError):
            client.delete_comment(comment)

    def test_non_mirror_comment(self, client, mock_repo):
        raw_issue = mock_repo.create_issue(title="Test issue")
        raw_issue.comments.append(
            mocks.MockGithubComment(
                body="Test comment body", user=mocks.MockGithubUser("somestranger", "Some Stranger"), issue=raw_issue
            )
        )

        issue = client.get_issue(raw_issue.number)

        assert issue.comments[0].is_bot is False

    def test_comment_fields_round_trip(self, client):
        issue = client.create_issue({"title": "Issue title"})
        comment = client.create_comment(issue, {"body": "Original comment body"})

        issue_id = issue.issue_id

        comment = client.get_issue(issue_id).comments[0]

        assert comment.source == Source.GITHUB
        assert comment.is_bot is True
        assert comment.comment_id == comment.comment_id
        assert abs(datetime.utcnow().replace(tzinfo=timezone.utc) - comment.created_at) < timedelta(seconds=1)
        assert comment.created_at.tzinfo == timezone.utc
        assert abs(datetime.utcnow().replace(tzinfo=timezone.utc) - comment.created_at) < timedelta(seconds=1)
        assert comment.updated_at.tzinfo == timezone.utc
        assert comment.user.source == Source.GITHUB
        assert comment.user.username == constants.TEST_GITHUB_USER_LOGIN
        assert comment.user.display_name == constants.TEST_GITHUB_USER_NAME
        assert comment.body == "Original comment body"

        client.update_comment(comment, {"body": "Updated comment body"})

        comment = client.get_issue(issue_id).comments[0]

        assert comment.body == "Updated comment body"

    def test_is_issue(self, client, mock_repo):
        raw_issue = mock_repo.create_issue(title="Test issue")
        raw_pull = mocks.MockGithubPull(title="Test PR")
        mock_repo.pulls.append(raw_pull)

        assert client.is_issue(raw_issue.number) is True
        assert client.is_issue(raw_pull.number) is False
        assert client.is_issue(12512512) is False

    def test_is_pull_request(self, client, mock_repo):
        raw_issue = mock_repo.create_issue(title="Test issue")
        raw_pull = mocks.MockGithubPull(title="Test PR")
        mock_repo.pulls.append(raw_pull)

        assert client.is_pull_request(raw_issue.number) is False
        assert client.is_pull_request(raw_pull.number) is True
        assert client.is_pull_request(12512512) is False


class TestFormatter:
    @pytest.fixture
    def formatter(self, config, jira_client):
        url_helper = UrlHelper.from_config(config)

        return github.Formatter(config, url_helper, jira_client)

    @pytest.mark.parametrize(
        "url, link_text, expected",
        [
            ("https://www.example.com", None, "<https://www.example.com>"),
            ("https://www.example.com", "link text", "[link text](https://www.example.com)"),
            (
                "https://github.com/testing/test-repo/blob/stable/.gitignore#L13",
                None,
                "<https://github.com/testing/test-repo/blob/stable/.gitignore#L13>",
            ),
            ("https://github.com/testing/test-repo/issues/2", None, "#2"),
            (
                "https://github.com/testing/test-repo/issues/2",
                "link text",
                "[link text](https://github.com/testing/test-repo/issues/2)",
            ),
            ("https://github.com/testing/other-test-repo/issues/5", None, "testing/other-test-repo#5"),
            (
                "https://github.com/testing/other-test-repo/issues/5",
                "link text",
                "[link text](https://github.com/testing/other-test-repo/issues/5)",
            ),
            ("https://github.com/testing/test-repo/pull/6", None, "#6"),
            (
                "https://github.com/testing/test-repo/pull/6",
                "link text",
                "[link text](https://github.com/testing/test-repo/pull/6)",
            ),
            ("https://github.com/testing/other-test-repo/pull/4", None, "testing/other-test-repo#4"),
            (
                "https://github.com/testing/other-test-repo/pull/4",
                "link text",
                "[link text](https://github.com/testing/other-test-repo/pull/4)",
            ),
            ("https://github.com/username123", None, "@username123"),
            ("https://github.com/username123", "link text", "[link text](https://github.com/username123)"),
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
                "This is a body with a unadorned URL: <https://www.example.com>",
            ),
            (
                "This is a body with a JIRA formatted link, but no link text: [https://www.example.com]",
                "This is a body with a JIRA formatted link, but no link text: <https://www.example.com>",
            ),
            (
                "This is a body with a [JIRA formatted external link|https://www.example.com].",
                "This is a body with a [JIRA formatted external link](https://www.example.com).",
            ),
            (
                "This is a body with a [JIRA formatted GitHub issue link|https://github.com/testing/test-repo/issues/2]",
                "This is a body with a [JIRA formatted GitHub issue link](https://github.com/testing/test-repo/issues/2)",
            ),
            (
                "This is a body with a JIRA mention: [~username123]",
                "This is a body with a JIRA mention: [Test User 123](https://test.jira.server/secure/ViewProfile.jspa?name=username123)",
            ),
            (
                "This is a body with a JIRA mention that doesn't exist: [~missing]",
                "This is a body with a JIRA mention that doesn't exist: [missing](https://test.jira.server/secure/ViewProfile.jspa?name=missing)",
            ),
            ("This body is #1!", "This body is #&#x2060;1!"),
            (
                "This is a link to GitHub code: https://github.com/testing/test-repo/blob/stable/.gitignore#L13",
                "This is a link to GitHub code: <https://github.com/testing/test-repo/blob/stable/.gitignore#L13>",
            ),
            (
                "This is a link to a GitHub issue in the same repo: https://github.com/testing/test-repo/issues/2",
                "This is a link to a GitHub issue in the same repo: #2",
            ),
            (
                "This is a link to a GitHub issue in the same repo: [https://github.com/testing/test-repo/issues/2]",
                "This is a link to a GitHub issue in the same repo: #2",
            ),
            (
                "This is a link to a GitHub issue in another repo: https://github.com/testing/other-test-repo/issues/5",
                "This is a link to a GitHub issue in another repo: testing/other-test-repo#5",
            ),
            (
                "This is a link to a GitHub issue in another repo: [https://github.com/testing/other-test-repo/issues/5]",
                "This is a link to a GitHub issue in another repo: testing/other-test-repo#5",
            ),
            (
                "This is a link to a GitHub PR in the same repo: https://github.com/testing/test-repo/pull/4",
                "This is a link to a GitHub PR in the same repo: #4",
            ),
            (
                "This is a link to a GitHub PR in the same repo: [https://github.com/testing/test-repo/pull/4]",
                "This is a link to a GitHub PR in the same repo: #4",
            ),
            (
                "This is a link to a GitHub PR in another repo: https://github.com/testing/other-test-repo/pull/6",
                "This is a link to a GitHub PR in another repo: testing/other-test-repo#6",
            ),
            (
                "This is a link to a GitHub PR in another repo: [https://github.com/testing/other-test-repo/pull/6]",
                "This is a link to a GitHub PR in another repo: testing/other-test-repo#6",
            ),
            (
                "This is a link to a GitHub user profile: https://github.com/username123",
                "This is a link to a GitHub user profile: @username123",
            ),
            (
                "This is a link to a GitHub user profile: [https://github.com/username123]",
                "This is a link to a GitHub user profile: @username123",
            ),
            (
                "This looks like a GitHub user mention but should be escaped: @username123",
                "This looks like a GitHub user mention but should be escaped: @\u2063username123",
            ),
            (
                "This is a body with *bold*, _italic_, and {{monospaced}} text.",
                "This is a body with **bold**, *italic*, and `monospaced` text.",
            ),
            (
                "This is a body with -deleted-, +inserted+, ^superscript^, and ~subscript~ text.",
                "This is a body with ~~deleted~~, <ins>inserted</ins>, <sup>superscript</sup>, and <sub>subscript</sub> text.",
            ),
            (
                "This is a body with a {color:red}color tag{color} which is unsupported by GitHub.",
                "This is a body with a color tag which is unsupported by GitHub.",
            ),
            (
                """This body has a block of Python code in it:
{code:python}
import sys
sys.stdout.write("Hello, world!")
sys.stdout.write("\n")
{code}""",
                """This body has a block of Python code in it:
```python
import sys
sys.stdout.write("Hello, world!")
sys.stdout.write("\n")
```""",
            ),
            (
                """This body has a block of generic code in it:
{code}
import sys
sys.stdout.write("Hello, world!")
sys.stdout.write("\n")
{code}""",
                """This body has a block of generic code in it:
```
import sys
sys.stdout.write("Hello, world!")
sys.stdout.write("\n")
```""",
            ),
            (
                """This body has a preformatted block of text in it:
{noformat}
  Ain't no formatting *here*!
{noformat}""",
                """This body has a preformatted block of text in it:
```
  Ain't no formatting *here*!
```""",
            ),
            (
                """This body has a quote block in it:
{quote}
Quotes are great!
Turns out there *is* formatting in here!
{quote}""",
                """This body has a quote block in it:

> Quotes are great!
> Turns out there **is** formatting in here!
""",
            ),
            ("This body has empty quoted content: {quote}{quote}", "This body has empty quoted content: "),
            ("This body has empty code content: {code}{code}", "This body has empty code content: "),
            ("This body has empty noformat content: {noformat}{noformat}", "This body has empty noformat content: "),
            ("h1. What a heading", "# What a heading"),
            ("h2. What a heading", "## What a heading"),
            ("h3. What a heading", "### What a heading"),
            ("h4. What a heading", "#### What a heading"),
            ("h5. What a heading", "##### What a heading"),
            ("h6. What a heading", "###### What a heading"),
        ],
    )
    def test_format_body(self, formatter, body, expected, jira_client):
        jira_client.users.append(User(Source.JIRA, "username123", "Test User 123"))

        assert formatter.format_body(body) == expected
