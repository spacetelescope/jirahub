import pytest

from jirahub.utils import UrlHelper, make_github_issue_url, extract_github_ids_from_url
from jirahub.entities import Source

from . import constants


def test_make_github_issue_url():
    assert make_github_issue_url("spacetelescope/jwst", 143) == "https://github.com/spacetelescope/jwst/issues/143"


def test_extract_github_ids_from_url():
    url = "https://github.com/spacetelescope/jwst/issues/143"
    github_repository, github_issue_id = extract_github_ids_from_url(url)

    assert github_repository == "spacetelescope/jwst"
    assert github_issue_id == 143


def test_extract_github_ids_from_url_bad_url():
    url = "https://www.zombo.com/spacetelescope/jwst/issues/143"
    assert extract_github_ids_from_url(url) == (None, None)


class TestUrlHelper:
    @pytest.fixture
    def url_helper(self):
        return UrlHelper(constants.TEST_JIRA_SERVER, constants.TEST_GITHUB_REPOSITORY)

    def test_from_config(self, url_helper, config):
        url_helper_from_config = UrlHelper.from_config(config)

        assert url_helper.get_issue_url(
            source=Source.JIRA, issue_id="TEST-198"
        ) == url_helper_from_config.get_issue_url(source=Source.JIRA, issue_id="TEST-198")
        assert url_helper.get_issue_url(source=Source.GITHUB, issue_id=43) == url_helper_from_config.get_issue_url(
            source=Source.GITHUB, issue_id=43
        )

    def test_get_issue_url_jira(self, url_helper, create_issue):
        result = url_helper.get_issue_url(source=Source.JIRA, issue_id="TEST-489")
        assert result == "https://test.jira.server/browse/TEST-489"

        issue = create_issue(source=Source.JIRA)
        result = url_helper.get_issue_url(issue=issue)
        assert result == f"https://test.jira.server/browse/{issue.issue_id}"

    def test_get_issue_url_github(self, url_helper, create_issue):
        result = url_helper.get_issue_url(source=Source.GITHUB, issue_id=489)
        assert result == "https://github.com/testing/test-repo/issues/489"

        issue = create_issue(source=Source.GITHUB)
        result = url_helper.get_issue_url(issue=issue)
        assert result == f"https://github.com/testing/test-repo/issues/{issue.issue_id}"

    def test_get_pull_request_url(self, url_helper):
        result = url_helper.get_pull_request_url(586)
        assert result == "https://github.com/testing/test-repo/pull/586"

    def test_get_comment_url_jira(self, url_helper, create_issue, create_comment):
        result = url_helper.get_comment_url(source=Source.JIRA, issue_id="TEST-489", comment_id=14938)
        assert result == "https://test.jira.server/browse/TEST-489?focusedCommentId=14938#comment-14938"

        issue = create_issue(source=Source.JIRA)
        comment = create_comment(source=Source.JIRA)
        result = url_helper.get_comment_url(issue=issue, comment=comment)
        assert (
            result
            == f"https://test.jira.server/browse/{issue.issue_id}?focusedCommentId={comment.comment_id}#comment-{comment.comment_id}"
        )

    def test_get_comment_url_github(self, url_helper, create_issue, create_comment):
        result = url_helper.get_comment_url(source=Source.GITHUB, issue_id=489, comment_id=14938)
        assert result == "https://github.com/testing/test-repo/issues/489#issuecomment-14938"

        issue = create_issue(source=Source.GITHUB)
        comment = create_comment(source=Source.GITHUB)
        result = url_helper.get_comment_url(issue=issue, comment=comment)
        assert (
            result == f"https://github.com/testing/test-repo/issues/{issue.issue_id}#issuecomment-{comment.comment_id}"
        )

    def test_get_user_profile_url_jira(self, url_helper, create_user):
        result = url_helper.get_user_profile_url(source=Source.JIRA, username="testuser123@example.com")
        assert result == "https://test.jira.server/secure/ViewProfile.jspa?name=testuser123%40example.com"

        user = create_user(source=Source.JIRA)
        result = url_helper.get_user_profile_url(user=user)
        assert result == f"https://test.jira.server/secure/ViewProfile.jspa?name={user.username}"

    def test_get_user_profile_url_github(self, url_helper, create_user):
        result = url_helper.get_user_profile_url(source=Source.GITHUB, username="testuser123@example.com")
        assert result == "https://github.com/testuser123%40example.com"

        user = create_user(source=Source.GITHUB)
        result = url_helper.get_user_profile_url(user=user)
        assert result == f"https://github.com/{user.username}"
