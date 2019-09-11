import pytest
import dataclasses
import hashlib

from jirahub.entities import Source, MetadataField


class TestSource:
    def test_str(self):
        assert str(Source.JIRA) == "JIRA"
        assert str(Source.GITHUB) == "GitHub"

    def test_other(self):
        assert Source.JIRA.other == Source.GITHUB
        assert Source.GITHUB.other == Source.JIRA


class TestMetadataField:
    def test_key(self):
        assert MetadataField.MIRROR_ID.key == "mirror_id"
        assert MetadataField.MIRROR_PROJECT.key == "mirror_project"
        assert MetadataField.BODY_HASH.key == "body_hash"
        assert MetadataField.TITLE_HASH.key == "title_hash"
        assert MetadataField.IS_TRACKING_COMMENT.key == "is_tracking_comment"


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

    def test_mirror_id(self, create_comment, create_mirror_comment, create_tracking_comment):
        source_comment = create_comment(Source.JIRA)
        mirror_comment = create_mirror_comment(Source.GITHUB, source_comment=source_comment)
        tracking_comment = create_tracking_comment(Source.JIRA)

        assert source_comment.mirror_id is None
        assert mirror_comment.mirror_id == source_comment.comment_id
        assert tracking_comment.mirror_id is None

    def test_is_tracking_comment(self, create_comment, create_mirror_comment, create_tracking_comment):
        source_comment = create_comment(Source.JIRA)
        mirror_comment = create_mirror_comment(Source.GITHUB, source_comment=source_comment)
        tracking_comment = create_tracking_comment(Source.JIRA)

        assert source_comment.is_tracking_comment is False
        assert mirror_comment.is_tracking_comment is False
        assert tracking_comment.is_tracking_comment is True

    def test_body_hash(self, create_comment, create_mirror_comment, create_tracking_comment):
        source_comment = create_comment(Source.JIRA)
        mirror_comment = create_mirror_comment(Source.GITHUB, source_comment=source_comment)

        assert source_comment.body_hash == hashlib.md5(source_comment.body.encode("utf-8")).hexdigest()
        assert mirror_comment.body_hash == source_comment.body_hash

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

    def test_mirror_id(self, create_issue, create_mirror_issue, create_tracking_comment):
        source_issue = create_issue(Source.JIRA)
        mirror_issue = create_mirror_issue(Source.GITHUB, source_issue=source_issue)

        assert source_issue.mirror_id is None
        assert mirror_issue.mirror_id == source_issue.issue_id

        tracking_comment = create_tracking_comment(Source.JIRA, source_issue=mirror_issue)
        source_issue.comments.append(tracking_comment)

        assert source_issue.mirror_id == mirror_issue.issue_id

    def test_mirror_project(self, create_issue, create_mirror_issue, create_tracking_comment):
        source_issue = create_issue(Source.JIRA)
        mirror_issue = create_mirror_issue(Source.GITHUB, source_issue=source_issue)

        assert source_issue.mirror_project is None
        assert mirror_issue.mirror_project == source_issue.project

        tracking_comment = create_tracking_comment(Source.JIRA, source_issue=mirror_issue)
        source_issue.comments.append(tracking_comment)

        assert source_issue.mirror_project == mirror_issue.project

    def test_body_hash(self, create_issue, create_mirror_issue):
        source_issue = create_issue(Source.JIRA)
        mirror_issue = create_mirror_issue(Source.GITHUB, source_issue=source_issue)

        assert source_issue.body_hash == hashlib.md5(source_issue.body.encode("utf-8")).hexdigest()
        assert mirror_issue.body_hash == source_issue.body_hash

    def test_body_hash_none_value(self, create_issue):
        issue = create_issue(Source.JIRA, body=None)
        assert issue.body_hash == hashlib.md5("".encode("utf-8")).hexdigest()

    def test_title_hash(self, create_issue, create_mirror_issue):
        source_issue = create_issue(Source.JIRA)
        mirror_issue = create_mirror_issue(Source.GITHUB, source_issue=source_issue)

        assert source_issue.body_hash == hashlib.md5(source_issue.body.encode("utf-8")).hexdigest()
        assert mirror_issue.body_hash == source_issue.body_hash

    def test_tracking_comment(self, create_issue, create_mirror_issue, create_tracking_comment):
        source_issue = create_issue(Source.JIRA)
        mirror_issue = create_mirror_issue(Source.GITHUB, source_issue=source_issue)

        assert source_issue.tracking_comment is None

        tracking_comment = create_tracking_comment(Source.JIRA, source_issue=mirror_issue)
        source_issue.comments.append(tracking_comment)

        assert source_issue.tracking_comment == tracking_comment

    @pytest.mark.parametrize("source", list(Source))
    def test_str(self, create_issue, source):
        issue = create_issue(source)
        issue_str = str(issue)

        assert str(source) in issue_str
        assert str(issue.issue_id) in issue_str
