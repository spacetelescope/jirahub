import sys
from pathlib import Path
from datetime import datetime, timedelta
import json

from jirahub import command_line
from jirahub.jirahub import IssueSync
from jirahub.entities import Source

from . import mocks


CONFIG_DIR = Path(__file__).parent / "configs"
CONFIG_PATH = CONFIG_DIR / "full_config.py"
BASE_CONFIG_PATH = CONFIG_DIR / "fragment_config_base.py"
OVERRIDES_CONFIG_PATH = CONFIG_DIR / "fragment_config_overrides.py"
MISSING_CONFIG_PATH = CONFIG_DIR / "missing.py"
BAD_CONFIG_PATH = CONFIG_DIR / "bad_config.py"
FAILING_CONFIG_PATH = CONFIG_DIR / "fragment_config_failing.py"


def monkey_patch_args(monkeypatch, args):
    monkeypatch.setattr(sys, "argv", args)


def test_main_generate_config(monkeypatch):
    monkey_patch_args(monkeypatch, ["jirahub", "generate-config"])
    assert command_line.main() == 0


def test_main_check_permissions(monkeypatch):
    monkey_patch_args(monkeypatch, ["jirahub", "check-permissions", str(CONFIG_PATH)])
    assert command_line.main() == 0


def test_main_check_permissions_invalid(monkeypatch):
    monkey_patch_args(monkeypatch, ["jirahub", "check-permissions", str(CONFIG_PATH)])
    mocks.MockJIRA.valid_project_keys = []
    assert command_line.main() == 1


def test_main_check_permissions_missing_config(monkeypatch):
    monkey_patch_args(monkeypatch, ["jirahub", "check-permissions", str(MISSING_CONFIG_PATH)])
    assert command_line.main() == 1


def test_main_check_permissions_exception(monkeypatch):
    monkey_patch_args(monkeypatch, ["jirahub", "check-permissions", str(CONFIG_PATH)])

    def broken_permissions(config):
        raise Exception("nope")

    monkeypatch.setattr(command_line, "check_permissions", broken_permissions)
    assert command_line.main() == 1


def test_main_sync(monkeypatch, tmp_path):
    monkey_patch_args(monkeypatch, ["jirahub", "sync", str(CONFIG_PATH)])
    assert command_line.main() == 0

    monkey_patch_args(monkeypatch, ["jirahub", "sync", str(BASE_CONFIG_PATH), str(OVERRIDES_CONFIG_PATH)])
    assert command_line.main() == 0

    monkey_patch_args(monkeypatch, ["jirahub", "sync", "-v", str(CONFIG_PATH)])
    assert command_line.main() == 0

    monkey_patch_args(monkeypatch, ["jirahub", "sync", "--min-updated-at", "1983-11-20T11:00:00", str(CONFIG_PATH)])
    assert command_line.main() == 0

    state_path = tmp_path / "state.json"
    with open(state_path, "w") as file:
        file.write(json.dumps({"min_updated_at": "2018-01-01T01:23:45"}))
    monkey_patch_args(monkeypatch, ["jirahub", "sync", "--state-path", str(state_path), str(CONFIG_PATH)])
    assert command_line.main() == 0
    with open(state_path, "r") as file:
        new_state = json.loads(file.read())
        new_placeholder = datetime.fromisoformat(new_state["min_updated_at"])
    assert abs(new_placeholder - datetime.utcnow()) < timedelta(seconds=1)

    missing_state_path = tmp_path / "missing_state.json"
    monkey_patch_args(monkeypatch, ["jirahub", "sync", "--state-path", str(missing_state_path), str(CONFIG_PATH)])
    assert command_line.main() == 0
    with open(missing_state_path, "r") as file:
        new_state = json.loads(file.read())
        new_placeholder = datetime.fromisoformat(new_state["min_updated_at"])
    assert abs(new_placeholder - datetime.utcnow()) < timedelta(seconds=1)


def test_main_sync_retry_issues(monkeypatch, tmp_path, jira_client, github_client, create_issue):
    jira_issue = create_issue(Source.JIRA)
    jira_client.issues = [jira_issue]

    github_issue = create_issue(Source.GITHUB)
    github_client.issues = [github_issue]

    class MockIssueSync:
        @classmethod
        def from_config(cls, config, dry_run=False):
            return IssueSync(config=config, jira_client=jira_client, github_client=github_client, dry_run=dry_run)

    monkeypatch.setattr(command_line, "IssueSync", MockIssueSync)

    state_path = tmp_path / "state.json"

    monkey_patch_args(
        monkeypatch, ["jirahub", "sync", "--state-path", str(state_path), str(CONFIG_PATH), str(FAILING_CONFIG_PATH)]
    )
    assert command_line.main() == 0

    with open(state_path, "r") as file:
        state = json.loads(file.read())
    retry_issues = {(Source[i["source"]], i["issue_id"]) for i in state["retry_issues"]}
    assert (Source.JIRA, jira_issue.issue_id) in retry_issues
    assert (Source.GITHUB, github_issue.issue_id) in retry_issues

    monkey_patch_args(monkeypatch, ["jirahub", "sync", "--state-path", str(state_path), str(CONFIG_PATH)])
    assert command_line.main() == 0

    with open(state_path, "r") as file:
        state = json.loads(file.read())
    assert len(state["retry_issues"]) == 0


def test_main_sync_missing_config(monkeypatch):
    monkey_patch_args(monkeypatch, ["jirahub", "sync", str(MISSING_CONFIG_PATH)])
    assert command_line.main() == 1


def test_main_sync_failure(monkeypatch):
    monkey_patch_args(monkeypatch, ["jirahub", "sync", str(BAD_CONFIG_PATH)])
    assert command_line.main() == 1
