import pytest
from datetime import timedelta
import re

from jirahub.jirahub import IssueSync
from jirahub.entities import Source, Metadata, CommentMetadata
from jirahub.config import SyncFeature
from jirahub import github, jira

from . import mocks, constants


def assert_client_activity(
    client, issue_creates=0, issue_updates=0, comment_creates=0, comment_updates=0, comment_deletes=0
):
    assert client.issue_creates == issue_creates
    assert client.issue_updates == issue_updates
    assert client.comment_creates == comment_creates
    assert client.comment_updates == comment_updates
    assert client.comment_deletes == comment_deletes


def set_features(config, source, enabled_features):
    for feature in SyncFeature:
        setattr(config.get_source_config(source), feature.key, feature in enabled_features)


def enable_issue_filter(config, source):
    if source == Source.JIRA:
        config.jira.issue_filter = lambda issue: True
    else:
        config.github.issue_filter = lambda issue: True


def assert_comment_updates(original_comment, updated_comment, **updates):
    assert updated_comment.source == original_comment.source
    assert updated_comment.comment_id == original_comment.comment_id
    assert updated_comment.created_at == original_comment.created_at
    assert updated_comment.updated_at > original_comment.updated_at
    assert updated_comment.user.username == original_comment.user.username
    assert updated_comment.is_bot == original_comment.is_bot

    if "body" in updates:
        assert updated_comment.body == updates["body"]
    else:
        assert updated_comment.body == original_comment.body


def assert_issue_updates(original_issue, updated_issue, **updates):
    assert updated_issue.source == original_issue.source
    assert updated_issue.is_bot == original_issue.is_bot
    assert updated_issue.issue_id == original_issue.issue_id
    assert updated_issue.created_at == original_issue.created_at
    assert updated_issue.updated_at > original_issue.updated_at
    assert updated_issue.user.username == original_issue.user.username

    for field_name in ["title", "is_open", "body", "labels", "priority", "issue_type", "milestones", "components"]:
        if field_name in updates:
            assert getattr(updated_issue, field_name) == updates[field_name]
        else:
            assert getattr(updated_issue, field_name) == getattr(original_issue, field_name)

    if "metadata" in updates:
        expected_metadata = updates["metadata"]
    else:
        expected_metadata = original_issue.metadata

    if expected_metadata is None:
        expected_metadata = Metadata()

    assert updated_issue.metadata.github_repository == expected_metadata.github_repository
    assert updated_issue.metadata.github_issue_id == expected_metadata.github_issue_id

    expected_comment_metadata = set()
    for cm in expected_metadata.comments:
        expected_comment_metadata.add((cm.jira_comment_id, cm.github_comment_id))

    actual_comment_metadata = set()
    for cm in updated_issue.metadata.comments:
        actual_comment_metadata.add((cm.jira_comment_id, cm.github_comment_id))

    assert actual_comment_metadata == expected_comment_metadata


class TestIssueSync:
    @pytest.fixture
    def issue_sync(self, config, jira_client, github_client):
        return IssueSync(config, jira_client, github_client)

    @pytest.fixture
    def issue_sync_dry_run(self, config, jira_client, github_client):
        return IssueSync(config, jira_client, github_client, dry_run=True)

    def test_from_config(self, config):
        # Just confirming no exceptions here:
        issue_sync = IssueSync.from_config(config)
        issue_sync.perform_sync()

    def test_get_source_config(self, issue_sync, config):
        assert issue_sync.get_source_config(Source.JIRA) == config.jira
        assert issue_sync.get_source_config(Source.GITHUB) == config.github

    def test_get_client(self, issue_sync, jira_client, github_client):
        assert issue_sync.get_client(Source.JIRA) == jira_client
        assert issue_sync.get_client(Source.GITHUB) == github_client

    def test_get_formatter(self, issue_sync):
        assert isinstance(issue_sync.get_formatter(Source.JIRA), jira.Formatter)
        assert isinstance(issue_sync.get_formatter(Source.GITHUB), github.Formatter)

    def test_get_project(self, config, issue_sync):
        assert issue_sync.get_project(Source.JIRA) == config.jira.project_key
        assert issue_sync.get_project(Source.GITHUB) == config.github.repository

    @pytest.mark.parametrize("source", list(Source))
    def test_accept_issue(self, issue_sync, config, source, create_issue):
        issue = create_issue(source)
        assert issue_sync.accept_issue(source, issue) is False
        enable_issue_filter(config, source)
        assert issue_sync.accept_issue(source, issue) is True

    @pytest.mark.parametrize("source", list(Source))
    @pytest.mark.parametrize("sync_feature", list(SyncFeature))
    @pytest.mark.parametrize("enabled", [True, False])
    def test_sync_feature_enabled(self, issue_sync, config, source, sync_feature, enabled):
        setattr(config.get_source_config(source), sync_feature.key, enabled)
        assert issue_sync.sync_feature_enabled(source, sync_feature) is enabled

    def test_find_updated_issues(self, issue_sync, github_client, jira_client, create_issue):
        jira_issues = [create_issue(Source.JIRA, updated_at=mocks.now() - timedelta(hours=i)) for i in range(5)]
        github_issues = [create_issue(Source.GITHUB, updated_at=mocks.now() - timedelta(hours=i)) for i in range(5)]

        jira_client.issues = jira_issues
        github_client.issues = github_issues

        result = issue_sync.find_issues()
        assert {id(i) for i in result} == {id(i) for i in jira_issues + github_issues}

        result = issue_sync.find_issues(mocks.now() - timedelta(hours=3))
        assert {id(i) for i in result} == {id(i) for i in jira_issues[:3] + github_issues[:3]}

        retry_issues = [(Source.JIRA, jira_issues[-1].issue_id), (Source.GITHUB, github_issues[-1].issue_id)]
        result = issue_sync.find_issues(mocks.now() - timedelta(hours=3), retry_issues=retry_issues)
        assert {id(i) for i in result} == {
            id(i) for i in jira_issues[:3] + github_issues[:3] + [jira_issues[-1], github_issues[-1]]
        }

    def test_perform_sync_no_features(self, issue_sync, config, github_client, jira_client, create_issue):
        jira_client.issues = [create_issue(Source.JIRA) for _ in range(5)]
        github_client.issues = [create_issue(Source.GITHUB) for _ in range(5)]

        issue_sync.perform_sync()

        assert_client_activity(jira_client)
        assert_client_activity(github_client)

    def test_perform_sync_manual_link(
        self, issue_sync, config, github_client, jira_client, create_issue, create_comment
    ):
        set_features(config, Source.JIRA, set(SyncFeature))
        set_features(config, Source.GITHUB, set(SyncFeature))

        github_comment = create_comment(Source.GITHUB)
        github_issue = create_issue(
            Source.GITHUB, comments=[github_comment], updated_at=mocks.now() - timedelta(hours=1)
        )
        github_client.issues = [github_issue]

        jira_comment = create_comment(Source.JIRA)
        jira_issue = create_issue(
            Source.JIRA,
            comments=[jira_comment],
            metadata=Metadata(github_repository=github_issue.project, github_issue_id=github_issue.issue_id),
        )
        jira_client.issues = [jira_issue]

        # Manually linked issue:
        issue_sync.perform_sync()
        assert_client_activity(jira_client, comment_creates=1, issue_updates=1)
        assert_client_activity(github_client, issue_updates=1, comment_creates=1)
        updated_github_issue = github_client.get_issue(github_issue.issue_id)
        assert_issue_updates(
            github_issue, updated_github_issue, labels=jira_issue.labels, milestones=jira_issue.milestones
        )
        updated_jira_issue = jira_client.get_issue(jira_issue.issue_id)
        assert_issue_updates(
            jira_issue,
            updated_jira_issue,
            metadata=Metadata(
                github_repository=github_issue.project,
                github_issue_id=github_issue.issue_id,
                comments=[
                    CommentMetadata(
                        jira_comment_id=jira_comment.comment_id,
                        github_comment_id=updated_github_issue.comments[1].comment_id,
                    ),
                    CommentMetadata(
                        jira_comment_id=updated_jira_issue.comments[1].comment_id,
                        github_comment_id=github_comment.comment_id,
                    ),
                ],
            ),
        )

        # Update to linked GitHub issue:
        jira_issue = updated_jira_issue
        jira_client.reset_stats()
        github_client.update_issue(updated_github_issue, {"is_open": False})
        github_client.reset_stats()
        issue_sync.perform_sync()
        assert_client_activity(jira_client, issue_updates=1)
        assert_client_activity(github_client)
        updated_jira_issue = jira_client.get_issue(jira_issue.issue_id)
        assert_issue_updates(jira_issue, updated_jira_issue, is_open=False)

    def test_perform_sync_comment_behavior(
        self, issue_sync, config, github_client, jira_client, create_issue, create_comment
    ):
        enable_issue_filter(config, Source.GITHUB)

        jira_comment = create_comment(Source.JIRA)
        jira_issue = create_issue(Source.JIRA, comments=[jira_comment])
        jira_client.issues = [jira_issue]

        issue_sync.perform_sync()
        assert_client_activity(github_client, issue_creates=1)
        assert_client_activity(jira_client, issue_updates=1)

        jira_client.reset_stats()
        github_client.reset_stats()
        set_features(config, Source.GITHUB, {SyncFeature.SYNC_COMMENTS})
        issue_sync.perform_sync()
        assert_client_activity(github_client, comment_creates=1)
        assert_client_activity(jira_client, issue_updates=1)
        github_comment = github_client.issues[0].comments[0]
        assert jira_comment.body in github_comment.body

        jira_comment.__dict__["body"] = "Updated comment body."
        jira_client.reset_stats()
        github_client.reset_stats()
        issue_sync.perform_sync()
        assert_client_activity(github_client, comment_updates=1)
        assert_client_activity(jira_client)
        github_comment = github_client.issues[0].comments[0]
        assert jira_comment.body in github_comment.body

        jira_client.issues[0].comments.remove(jira_comment)
        jira_client.reset_stats()
        github_client.reset_stats()
        issue_sync.perform_sync()
        assert_client_activity(github_client, comment_deletes=1)
        assert_client_activity(jira_client, issue_updates=1)

    def test_perform_sync_tracking_comment(self, issue_sync, config, github_client, jira_client, create_issue):
        config.github.create_tracking_comment = True
        for source in Source:
            enable_issue_filter(config, source)

        jira_issue = create_issue(Source.JIRA)
        jira_client.issues = [jira_issue]
        issue_sync.perform_sync()
        assert_client_activity(github_client, issue_creates=1)
        assert_client_activity(jira_client, issue_updates=1)

        github_issue = create_issue(Source.GITHUB)
        github_client.issues.append(github_issue)
        jira_client.reset_stats()
        github_client.reset_stats()
        issue_sync.perform_sync()
        assert_client_activity(github_client, comment_creates=1)
        assert_client_activity(jira_client, issue_creates=1, issue_updates=1)

        jira_client.reset_stats()
        github_client.reset_stats()
        issue_sync.perform_sync()
        assert_client_activity(github_client)
        assert_client_activity(jira_client)

        github_client.issues[-1].comments[0].__dict__["body"] = "foo"
        jira_client.reset_stats()
        github_client.reset_stats()
        issue_sync.perform_sync()
        assert_client_activity(github_client, comment_updates=1)
        assert_client_activity(jira_client)

    def test_perform_sync_min_updated_at(self, issue_sync, config, github_client, jira_client, create_issue):
        for source in Source:
            enable_issue_filter(config, source)

        now = mocks.now()

        jira_issue = create_issue(Source.JIRA, updated_at=now - timedelta(hours=2))
        jira_client.issues = [jira_issue]
        github_issue = create_issue(Source.GITHUB, updated_at=now - timedelta(hours=1))
        github_client.issues = [github_issue]

        issue_sync.perform_sync(min_updated_at=now)
        assert_client_activity(github_client)
        assert_client_activity(jira_client)

        issue_sync.perform_sync(min_updated_at=now - timedelta(hours=1.5))
        assert_client_activity(github_client)
        assert_client_activity(jira_client, issue_creates=1)

        jira_client.reset_stats()
        github_client.reset_stats()
        issue_sync.perform_sync(min_updated_at=now - timedelta(hours=2.5))
        assert_client_activity(github_client, issue_creates=1)
        assert_client_activity(jira_client, issue_updates=1)

    def test_perform_sync_all_features(
        self, issue_sync, config, github_client, jira_client, create_issue, create_comment
    ):
        for source in Source:
            set_features(config, source, set(SyncFeature))
            config.get_source_config(source).create_tracking_comment = True

        config.jira.issue_filter = lambda issue: "pickme" in issue.labels
        config.jira.issue_title_formatter = lambda issue, title: "Title from GitHub: " + title
        config.jira.issue_body_formatter = lambda issue, body: "Body from GitHub: " + body
        config.jira.comment_body_formatter = lambda issue, comment, body: "Comment body from GitHub: " + body
        config.github.issue_filter = lambda issue: "pickmetoo" in issue.labels
        config.github.issue_title_formatter = lambda issue, title: "Title from JIRA: " + title
        config.github.issue_body_formatter = lambda issue, body: "Body from JIRA: " + body
        config.github.comment_body_formatter = lambda issue, comment, body: "Comment body from JIRA: " + body

        jira_issue_excluded = create_issue(Source.JIRA, labels=set())
        jira_comments = [create_comment(Source.JIRA) for _ in range(3)]
        jira_issue = create_issue(Source.JIRA, labels={"pickmetoo"}, milestones={"7.1.0"}, comments=jira_comments)
        jira_client.issues = [jira_issue_excluded, jira_issue]

        github_issue_excluded = create_issue(Source.GITHUB, labels=set())
        github_comments = [create_comment(Source.GITHUB) for _ in range(3)]
        github_issue = create_issue(Source.GITHUB, labels={"pickme"}, milestones={"8.5.2"}, comments=github_comments)
        github_client.issues = [github_issue_excluded, github_issue]

        issue_sync.perform_sync()
        assert_client_activity(jira_client, issue_creates=1, comment_creates=4, issue_updates=3)
        assert_client_activity(github_client, issue_creates=1, comment_creates=4)
        mirror_jira_issue = next(i for i in jira_client.issues if i.is_bot)
        assert mirror_jira_issue.title == "Title from GitHub: " + github_issue.title
        assert mirror_jira_issue.body == "Body from GitHub: " + github_issue.body
        assert mirror_jira_issue.labels == {"pickme"}
        assert mirror_jira_issue.milestones == {"8.5.2"}
        assert mirror_jira_issue.metadata.github_repository == constants.TEST_GITHUB_REPOSITORY
        assert mirror_jira_issue.metadata.github_issue_id == github_issue.issue_id
        assert mirror_jira_issue.metadata.github_tracking_comment_id is not None
        assert mirror_jira_issue.metadata.jira_tracking_comment_id is None
        assert mirror_jira_issue.is_bot is True
        assert mirror_jira_issue.is_open is True
        assert len(mirror_jira_issue.comments) == 3
        mirror_github_issue = next(i for i in github_client.issues if i.is_bot)
        assert mirror_github_issue.title == "Title from JIRA: " + jira_issue.title
        assert mirror_github_issue.body == "Body from JIRA: " + jira_issue.body
        assert mirror_github_issue.labels == {"pickmetoo"}
        assert mirror_github_issue.milestones == {"7.1.0"}
        assert mirror_github_issue.is_bot is True
        assert mirror_github_issue.is_open is True
        assert len(mirror_github_issue.comments) == 3

        jira_issue = jira_client.get_issue(jira_issue.issue_id)
        assert jira_issue.metadata.github_tracking_comment_id is None
        assert jira_issue.metadata.jira_tracking_comment_id is not None

        jira_client.reset_stats()
        github_client.reset_stats()
        issue_sync.perform_sync()
        assert_client_activity(jira_client)
        assert_client_activity(github_client)

        jira_client.reset_stats()
        github_client.reset_stats()
        jira_issue = jira_client.get_issue(jira_issue.issue_id)
        jira_issue.__dict__["title"] = "Updated JIRA title"
        jira_issue.__dict__["body"] = "Updated JIRA body"
        jira_issue.__dict__["milestones"] = {"7.2.0"}
        jira_issue.__dict__["labels"] = {"pickmetoo", "jirahub", "andme"}
        jira_issue.__dict__["is_open"] = False
        jira_issue.__dict__["updated_at"] = mocks.now()
        issue_sync.perform_sync()
        assert_client_activity(jira_client)
        assert_client_activity(github_client, issue_updates=1)
        mirror_github_issue = github_client.get_issue(mirror_github_issue.issue_id)
        assert mirror_github_issue.title == "Title from JIRA: Updated JIRA title"
        assert mirror_github_issue.body == "Body from JIRA: Updated JIRA body"
        assert mirror_github_issue.labels == {"pickmetoo", "jirahub", "andme"}
        assert mirror_github_issue.milestones == {"7.2.0"}
        assert mirror_github_issue.is_open is False

        jira_client.reset_stats()
        github_client.reset_stats()
        github_issue = github_client.get_issue(github_issue.issue_id)
        github_issue.__dict__["title"] = "Updated GitHub title"
        github_issue.__dict__["body"] = "Updated GitHub body"
        github_issue.__dict__["milestones"] = {"8.5.3"}
        github_issue.__dict__["labels"] = {"pickme", "jirahub", "andme"}
        github_issue.__dict__["is_open"] = False
        github_issue.__dict__["updated_at"] = mocks.now()
        issue_sync.perform_sync()
        assert_client_activity(jira_client, issue_updates=1)
        assert_client_activity(github_client)
        mirror_jira_issue = jira_client.get_issue(mirror_jira_issue.issue_id)
        assert mirror_jira_issue.title == "Title from GitHub: Updated GitHub title"
        assert mirror_jira_issue.body == "Body from GitHub: Updated GitHub body"
        assert mirror_jira_issue.labels == {"pickme", "jirahub", "andme"}
        assert mirror_jira_issue.milestones == {"8.5.3"}
        assert mirror_jira_issue.is_open is False

    @pytest.mark.parametrize("source", list(Source))
    def test_perform_sync_one_direction(self, issue_sync, config, github_client, jira_client, source, create_issue):
        set_features(config, source.other, set(SyncFeature))
        enable_issue_filter(config, source.other)
        our_client = issue_sync.get_client(source)
        other_client = issue_sync.get_client(source.other)

        our_issue = create_issue(source, labels={"label1", "label2"}, milestones={"milestone1", "milestone2"})
        other_issue = create_issue(source.other)

        our_client.issues.append(our_issue)
        other_client.issues.append(other_issue)

        issue_sync.perform_sync()
        if source == Source.JIRA:
            assert_client_activity(our_client, issue_updates=1)
        else:
            assert_client_activity(our_client)

        assert_client_activity(other_client, issue_creates=1)
        mirror_issue = next(i for i in other_client.issues if i.is_bot)
        assert mirror_issue.title == our_issue.title
        assert our_issue.body in mirror_issue.body
        assert mirror_issue.labels == our_issue.labels
        assert mirror_issue.milestones == our_issue.milestones
        assert mirror_issue.is_bot is True
        assert mirror_issue.is_open is True

        our_client.reset_stats()
        other_client.reset_stats()
        issue_sync.perform_sync()
        assert_client_activity(our_client)
        assert_client_activity(other_client)

        our_client.reset_stats()
        other_client.reset_stats()
        our_issue = our_client.get_issue(our_issue.issue_id)
        our_issue.__dict__["title"] = "Updated title"
        our_issue.__dict__["body"] = "Updated body"
        our_issue.__dict__["milestones"] = {"milestone3"}
        our_issue.__dict__["labels"] = {"label1", "label3"}
        our_issue.__dict__["is_open"] = False
        issue_sync.perform_sync()
        assert_client_activity(our_client)
        assert_client_activity(other_client, issue_updates=1)
        mirror_issue = other_client.get_issue(mirror_issue.issue_id)
        assert mirror_issue.title == "Updated title"
        assert "Updated body" in mirror_issue.body
        assert mirror_issue.labels == {"label1", "label3"}
        assert mirror_issue.milestones == {"milestone3"}
        assert mirror_issue.is_open is False

        our_client.reset_stats()
        other_client.reset_stats()
        mirror_issue.__dict__["milestones"] = {"milestone4"}
        mirror_issue.__dict__["labels"] = {"label1"}
        mirror_issue.__dict__["is_open"] = True
        issue_sync.perform_sync()
        assert_client_activity(our_client)
        assert_client_activity(other_client, issue_updates=1)
        mirror_issue = other_client.get_issue(mirror_issue.issue_id)
        assert mirror_issue.milestones == {"milestone3"}
        assert mirror_issue.labels == {"label1", "label3"}
        assert mirror_issue.is_open is False

    def test_perform_sync_dry_run(
        self,
        issue_sync_dry_run,
        config,
        github_client,
        jira_client,
        create_issue,
        create_comment,
        create_mirror_issue,
        create_mirror_comment,
    ):
        for source in Source:
            set_features(config, source, set(SyncFeature))
            enable_issue_filter(config, source)
            config.get_source_config(source).create_tracking_comment = True

        new_jira_issue = create_issue(Source.JIRA)
        existing_jira_issue = create_issue(Source.JIRA)
        existing_jira_comment = create_comment(Source.JIRA)
        deleted_jira_comment = create_comment(Source.JIRA)
        new_jira_comment = create_comment(Source.JIRA)
        mirror_github_issue = create_mirror_issue(Source.GITHUB, source_issue=existing_jira_issue)
        mirror_github_comment = create_mirror_comment(Source.GITHUB, source_comment=existing_jira_comment)
        mirror_github_deleted_comment = create_mirror_comment(Source.GITHUB, source_comment=deleted_jira_comment)
        metadata = Metadata(
            github_repository=mirror_github_issue.project,
            github_issue_id=mirror_github_issue.issue_id,
            comments=[
                CommentMetadata(
                    jira_comment_id=existing_jira_comment.comment_id, github_comment_id=mirror_github_comment.comment_id
                ),
                CommentMetadata(
                    jira_comment_id=deleted_jira_comment.comment_id,
                    github_comment_id=mirror_github_deleted_comment.comment_id,
                ),
            ],
        )
        existing_jira_comment.__dict__["body"] = "Updated comment body"
        existing_jira_issue.__dict__["metadata"] = metadata
        existing_jira_issue.__dict__["body"] = "Updated issue body"
        existing_jira_issue.comments.append(existing_jira_comment)
        existing_jira_issue.comments.append(new_jira_comment)
        mirror_github_issue.comments.append(mirror_github_comment)
        mirror_github_issue.comments.append(mirror_github_deleted_comment)
        github_client.issues = [mirror_github_issue]
        jira_client.issues = [existing_jira_issue, new_jira_issue]

        issue_sync_dry_run.perform_sync()

        assert_client_activity(jira_client)
        assert_client_activity(github_client)

    def test_perform_sync_exception_raised_by_issue(self, issue_sync, config, github_client, jira_client, create_issue):
        for source in Source:
            enable_issue_filter(config, source)

        jira_issue = create_issue(Source.JIRA)
        bogus_jira_issue = create_issue(Source.JIRA)
        jira_client.issues = [bogus_jira_issue, jira_issue]

        github_issue = create_issue(Source.GITHUB)
        bogus_github_issue = create_issue(Source.GITHUB)
        github_client.issues = [bogus_github_issue, github_issue]

        def exceptional_formatter(issue, body):
            if issue == bogus_jira_issue or issue == bogus_github_issue:
                raise Exception("Nope")
            else:
                return body

        config.jira.issue_body_formatter = exceptional_formatter
        config.github.issue_body_formatter = exceptional_formatter

        failed_issues = issue_sync.perform_sync()

        assert_client_activity(jira_client, issue_creates=1, issue_updates=1)
        assert_client_activity(github_client, issue_creates=1)

        assert len(failed_issues) == 2
        assert (Source.JIRA, bogus_jira_issue.issue_id) in failed_issues
        assert (Source.GITHUB, bogus_github_issue.issue_id) in failed_issues

    def test_perform_sync_missing_issue(self, issue_sync, config, github_client, jira_client, create_issue):
        # Confirm that a deleted source issue doesn't impact unrelated issues
        enable_issue_filter(config, Source.GITHUB)

        jira_issue = create_issue(Source.JIRA)
        deleted_jira_issue = create_issue(Source.JIRA)
        jira_client.issues = [jira_issue, deleted_jira_issue]
        issue_sync.perform_sync()
        assert_client_activity(jira_client, issue_updates=2)
        assert_client_activity(github_client, issue_creates=2)

        jira_client.reset_stats()
        github_client.reset_stats()
        jira_client.issues = [i for i in jira_client.issues if i.issue_id != deleted_jira_issue.issue_id]
        jira_client.issues[0].__dict__["title"] = "Updated title"
        issue_sync.perform_sync()
        assert_client_activity(jira_client)
        assert_client_activity(github_client, issue_updates=1)

    def test_exception_raised_by_comment(
        self, issue_sync, config, github_client, jira_client, create_issue, create_comment
    ):
        for source in Source:
            set_features(config, source, {SyncFeature.SYNC_COMMENTS})
            enable_issue_filter(config, source)

        jira_comment = create_comment(Source.JIRA)
        bogus_jira_comment = create_comment(Source.JIRA)
        jira_issue = create_issue(Source.JIRA, comments=[bogus_jira_comment, jira_comment])
        jira_client.issues = [jira_issue]

        github_comment = create_comment(Source.GITHUB)
        bogus_github_comment = create_comment(Source.GITHUB)
        github_issue = create_issue(Source.GITHUB, comments=[bogus_github_comment, github_comment])
        github_client.issues = [github_issue]

        def exceptional_formatter(issue, comment, body):
            if comment == bogus_jira_comment or comment == bogus_github_comment:
                raise Exception("Nope")
            else:
                return body

        config.jira.comment_body_formatter = exceptional_formatter
        config.github.comment_body_formatter = exceptional_formatter

        issue_sync.perform_sync()

        assert_client_activity(jira_client, issue_creates=1, comment_creates=1, issue_updates=3)
        assert_client_activity(github_client, issue_creates=1, comment_creates=1)

    def test_perform_sync_wrong_github_repository(self, issue_sync, config, github_client, jira_client, create_issue):
        for source in Source:
            enable_issue_filter(config, source)

        issue = create_issue(
            Source.JIRA, metadata=Metadata(github_repository="testing/some-other-repo", github_issue_id=1234)
        )
        jira_client.issues.append(issue)

        issue_sync.perform_sync()

        assert_client_activity(jira_client)
        assert_client_activity(github_client)

    def test_perform_sync_redactions(
        self, issue_sync, config, github_client, jira_client, create_issue, create_comment
    ):
        set_features(config, Source.GITHUB, {SyncFeature.SYNC_COMMENTS})
        enable_issue_filter(config, Source.GITHUB)

        config.github.redact_patterns = [re.compile(r"(?<=secret JIRA data: ).+?\b")]

        comment = create_comment(
            Source.JIRA, body="This comment body contains secret JIRA data: hideme, but we can see the rest of it."
        )
        source_issue = create_issue(
            Source.JIRA,
            title="This title contains secret JIRA data: hideme",
            body="This body contains secret JIRA data: hideme.\nin multiple places, secret JIRA data: hidemetoo. But we redacted it all!",
            comments=[comment],
        )
        jira_client.issues = [source_issue]

        issue_sync.perform_sync()

        assert_client_activity(jira_client, issue_updates=2)
        assert_client_activity(github_client, issue_creates=1, comment_creates=1)

        mirror_issue = github_client.issues[0]
        assert mirror_issue.title == "This title contains secret JIRA data: ██████"
        assert (
            "This body contains secret JIRA data: ██████.\nin multiple places, secret JIRA data: █████████. But we redacted it all!"
            in mirror_issue.body
        )
        mirror_comment = github_client.issues[0].comments[0]
        assert (
            "This comment body contains secret JIRA data: ██████, but we can see the rest of it." in mirror_comment.body
        )

    @pytest.mark.parametrize("source", list(Source))
    def test_before_issue_create(self, issue_sync, config, source, create_issue):
        enable_issue_filter(config, source.other)

        def hook(issue, fields):
            fields["labels"] = ["jirahub"]
            return fields

        config.get_source_config(source.other).before_issue_create.append(hook)

        source_issue = create_issue(source)
        issue_sync.get_client(source).issues = [source_issue]

        issue_sync.perform_sync()

        if source == Source.JIRA:
            assert_client_activity(issue_sync.get_client(Source.JIRA), issue_updates=1)
            assert_client_activity(issue_sync.get_client(Source.GITHUB), issue_creates=1)
        else:
            assert_client_activity(issue_sync.get_client(Source.JIRA), issue_creates=1)
            assert_client_activity(issue_sync.get_client(Source.GITHUB))

        mirror_issue = issue_sync.get_client(source.other).issues[0]
        assert mirror_issue.labels == {"jirahub"}

    @pytest.mark.parametrize("source", list(Source))
    def test_issue_title_formatter(self, issue_sync, config, source, create_issue):
        enable_issue_filter(config, source.other)

        def formatter(issue, title):
            return "JIRAHUB: " + title

        config.get_source_config(source.other).issue_title_formatter = formatter

        source_issue = create_issue(source)
        issue_sync.get_client(source).issues = [source_issue]

        issue_sync.perform_sync()

        if source == Source.JIRA:
            assert_client_activity(issue_sync.get_client(Source.JIRA), issue_updates=1)
            assert_client_activity(issue_sync.get_client(Source.GITHUB), issue_creates=1)
        else:
            assert_client_activity(issue_sync.get_client(Source.JIRA), issue_creates=1)
            assert_client_activity(issue_sync.get_client(Source.GITHUB))

        mirror_issue = issue_sync.get_client(source.other).issues[0]
        assert mirror_issue.title == "JIRAHUB: " + source_issue.title

    @pytest.mark.parametrize("source", list(Source))
    def test_issue_body_formatter(self, issue_sync, config, source, create_issue):
        enable_issue_filter(config, source.other)

        def formatter(issue, body):
            return "JIRAHUB: " + body

        config.get_source_config(source.other).issue_body_formatter = formatter

        source_issue = create_issue(source)
        issue_sync.get_client(source).issues = [source_issue]

        issue_sync.perform_sync()

        if source == Source.JIRA:
            assert_client_activity(issue_sync.get_client(Source.JIRA), issue_updates=1)
            assert_client_activity(issue_sync.get_client(Source.GITHUB), issue_creates=1)
        else:
            assert_client_activity(issue_sync.get_client(Source.JIRA), issue_creates=1)
            assert_client_activity(issue_sync.get_client(Source.GITHUB))

        mirror_issue = issue_sync.get_client(source.other).issues[0]
        assert mirror_issue.body == "JIRAHUB: " + source_issue.body

    @pytest.mark.parametrize("source", list(Source))
    def test_comment_body_formatter(self, issue_sync, config, source, create_issue, create_comment):
        enable_issue_filter(config, source.other)
        set_features(config, source.other, {SyncFeature.SYNC_COMMENTS})

        def formatter(issue, comment, body):
            return "JIRAHUB: " + body

        config.get_source_config(source.other).comment_body_formatter = formatter

        source_issue = create_issue(source)
        source_comment = create_comment(source)
        source_issue.comments.append(source_comment)
        issue_sync.get_client(source).issues = [source_issue]

        issue_sync.perform_sync()

        if source == Source.JIRA:
            assert_client_activity(issue_sync.get_client(Source.JIRA), issue_updates=2)
            assert_client_activity(issue_sync.get_client(Source.GITHUB), issue_creates=1, comment_creates=1)
        else:
            assert_client_activity(
                issue_sync.get_client(Source.JIRA), issue_creates=1, comment_creates=1, issue_updates=1
            )
            assert_client_activity(issue_sync.get_client(Source.GITHUB))

        mirror_comment = issue_sync.get_client(source.other).issues[0].comments[0]
        assert mirror_comment.body == "JIRAHUB: " + source_comment.body
