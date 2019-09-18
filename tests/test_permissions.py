import pytest

from jirahub.permissions import check_permissions
from jirahub.config import SyncFeature

from . import mocks


def test_check_permissions(config):
    errors = check_permissions(config)
    assert len(errors) == 0


@pytest.mark.parametrize("env_key", ["JIRAHUB_JIRA_USERNAME", "JIRAHUB_JIRA_PASSWORD", "JIRAHUB_GITHUB_TOKEN"])
def test_check_permissions_missing_env(monkeypatch, config, env_key):
    monkeypatch.delenv(env_key)

    errors = check_permissions(config)
    assert len(errors) == 1
    assert env_key in errors[0]


def test_check_permissions_bad_jira_credentials(config):
    mocks.MockJIRA.valid_basic_auths = []

    errors = check_permissions(config)
    assert len(errors) == 1
    assert "JIRA rejected credentials" in errors[0]


def test_check_permissions_bad_jira_server(config):
    mocks.MockJIRA.valid_servers = []

    errors = check_permissions(config)
    assert len(errors) == 1
    assert "Unable to communicate with JIRA server" in errors[0]


def test_check_permissions_missing_jira_project(config):
    mocks.MockJIRA.valid_project_keys = []

    errors = check_permissions(config)
    assert len(errors) == 1
    assert f"JIRA project {config.jira.project_key} does not exist" in errors[0]


def test_check_permissions_missing_jira_browse_projects(config):
    mocks.MockJIRA.permissions = [p for p in mocks.MockJIRA.ALL_PERMISSIONS if p != "BROWSE_PROJECTS"]

    errors = check_permissions(config)
    assert len(errors) == 1
    assert "BROWSE_PROJECTS" in errors[0]


def test_check_permissions_missing_jira_edit_issues(config):
    mocks.MockJIRA.permissions = [p for p in mocks.MockJIRA.ALL_PERMISSIONS if p != "EDIT_ISSUES"]

    errors = check_permissions(config)
    assert len(errors) == 1
    assert "EDIT_ISSUES" in errors[0]


def test_check_permissions_jira_issue_filter(config):
    config.jira.issue_filter = lambda _: True

    mocks.MockJIRA.permissions = mocks.MockJIRA.ALL_PERMISSIONS
    errors = check_permissions(config)
    assert len(errors) == 0

    mocks.MockJIRA.permissions = [p for p in mocks.MockJIRA.ALL_PERMISSIONS if p != "CREATE_ISSUES"]
    errors = check_permissions(config)
    assert len(errors) == 1
    assert "CREATE_ISSUES" in errors[0]
    assert "c.jira.issue_filter" in errors[0]


def test_check_permissions_notify_watchers(config):
    config.jira.notify_watchers = False

    mocks.MockJIRA.permissions = mocks.MockJIRA.ALL_PERMISSIONS
    errors = check_permissions(config)
    assert len(errors) == 0

    mocks.MockJIRA.permissions = [
        p for p in mocks.MockJIRA.ALL_PERMISSIONS if p not in {"ADMINISTER", "ADMINISTER_PROJECTS", "SYSTEM_ADMIN"}
    ]
    errors = check_permissions(config)
    assert len(errors) == 1
    assert "ADMINISTER_PROJECTS" in errors[0]
    assert "c.jira.notify_watchers" in errors[0]


@pytest.mark.parametrize(
    "sync_feature, permission",
    [
        (SyncFeature.SYNC_COMMENTS, "ADD_COMMENTS"),
        (SyncFeature.SYNC_COMMENTS, "DELETE_OWN_COMMENTS"),
        (SyncFeature.SYNC_COMMENTS, "EDIT_OWN_COMMENTS"),
        (SyncFeature.SYNC_STATUS, "CLOSE_ISSUES"),
        (SyncFeature.SYNC_STATUS, "RESOLVE_ISSUES"),
        (SyncFeature.SYNC_LABELS, "EDIT_ISSUES"),
        (SyncFeature.SYNC_MILESTONES, "EDIT_ISSUES"),
        (SyncFeature.SYNC_MILESTONES, "RESOLVE_ISSUES"),
    ],
)
@pytest.mark.parametrize(
    "feature_enabled, has_permission, error_expected",
    [(True, True, False), (True, False, True), (False, True, False), (False, False, False)],
)
def test_check_permissions_jira_sync_feature(
    config, sync_feature, permission, feature_enabled, has_permission, error_expected
):
    setattr(config.jira, sync_feature.key, feature_enabled)

    if not has_permission:
        mocks.MockJIRA.permissions = [p for p in mocks.MockJIRA.ALL_PERMISSIONS if not p == permission]

    errors = check_permissions(config)

    has_error = any(e for e in errors if f"c.jira.{sync_feature.key}" in e and permission in e)
    assert error_expected == has_error


def test_check_permissions_bad_github_credentials(config):
    mocks.MockGithub.valid_tokens = []

    errors = check_permissions(config)
    assert len(errors) == 1
    assert "GitHub rejected credentials" in errors[0]


def test_check_permissions_missing_github_repo(config):
    mocks.MockGithub.repositories = []

    errors = check_permissions(config)
    assert len(errors) == 1
    assert "GitHub repository" in errors[0]


def test_check_permissions_github_issue_filter(config):
    config.github.issue_filter = lambda _: True

    for repo in mocks.MockGithub.repositories:
        repo.permissions = mocks.MockGithubPermissions(push=True)

    errors = check_permissions(config)
    assert len(errors) == 0

    for repo in mocks.MockGithub.repositories:
        repo.permissions = mocks.MockGithubPermissions(push=False)

    errors = check_permissions(config)
    assert len(errors) == 1
    assert "c.github.issue_filter" in errors[0]


@pytest.mark.parametrize(
    "sync_feature, push_required",
    [
        (SyncFeature.SYNC_COMMENTS, False),
        (SyncFeature.SYNC_STATUS, True),
        (SyncFeature.SYNC_LABELS, True),
        (SyncFeature.SYNC_MILESTONES, True),
    ],
)
@pytest.mark.parametrize("feature_enabled, has_push", [(True, True), (True, False), (False, True), (False, False)])
def test_check_permissions_github_sync_feature(config, sync_feature, push_required, feature_enabled, has_push):
    setattr(config.github, sync_feature.key, feature_enabled)

    for repo in mocks.MockGithub.repositories:
        repo.permissions = mocks.MockGithubPermissions(push=has_push)

    errors = check_permissions(config)

    if feature_enabled and push_required and not has_push:
        assert len(errors) == 1
        assert str(sync_feature) in errors[0]
    else:
        assert len(errors) == 0
