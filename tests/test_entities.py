import pytest
import dataclasses

from jirahub.entities import Source


class TestSource:
    def test_str(self):
        assert str(Source.JIRA) == "JIRA"
        assert str(Source.GITHUB) == "GitHub"

    def test_other(self):
        assert Source.JIRA.other == Source.GITHUB
        assert Source.GITHUB.other == Source.JIRA


class TestUser:
    def test_frozen(self, create_user):
        user = create_user(Source.JIRA)
        with pytest.raises(dataclasses.FrozenInstanceError):
            user.username = "nope"

    @pytest.mark.parametrize("source", list(Source))
    def test_str(self, create_user, source):
        user = create_user(source)
        user_str = str(user)
        assert str(source) in user_str
        assert user.username in user_str
        assert user.display_name in user_str


class TestComment:
    def test_frozen(self, create_comment):
        comment = create_comment(Source.JIRA)
        with pytest.raises(dataclasses.FrozenInstanceError):
            comment.body = "nope"

    @pytest.mark.parametrize("source", list(Source))
    def test_str(self, create_comment, source):
        comment = create_comment(source)
        comment_str = str(comment)

        assert str(source) in comment_str
        assert str(comment.comment_id) in comment_str


class TestIssue:
    def test_frozen(self, create_issue):
        issue = create_issue(Source.JIRA)
        with pytest.raises(dataclasses.FrozenInstanceError):
            issue.body = "nope"

    @pytest.mark.parametrize("source", list(Source))
    def test_str(self, create_issue, source):
        issue = create_issue(source)
        issue_str = str(issue)

        assert str(source) in issue_str
        assert str(issue.issue_id) in issue_str
