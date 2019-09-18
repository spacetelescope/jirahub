import sys
from pathlib import Path
from datetime import datetime, timedelta

from jirahub import command_line

from . import mocks


CONFIG_DIR = Path(__file__).parent / "configs"
CONFIG_PATH = CONFIG_DIR / "full_config.py"
BASE_CONFIG_PATH = CONFIG_DIR / "fragment_config_base.py"
OVERRIDES_CONFIG_PATH = CONFIG_DIR / "fragment_config_overrides.py"
MISSING_CONFIG_PATH = CONFIG_DIR / "missing.py"
BAD_CONFIG_PATH = CONFIG_DIR / "bad_config.py"


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

    placeholder_path = tmp_path / "placeholder.txt"
    with open(placeholder_path, "w") as file:
        file.write("2018-01-01T01:23:45")
    monkey_patch_args(monkeypatch, ["jirahub", "sync", "--placeholder-path", str(placeholder_path), str(CONFIG_PATH)])
    assert command_line.main() == 0
    with open(placeholder_path, "r") as file:
        new_placeholder = datetime.fromisoformat(file.read().strip())
    assert abs(new_placeholder - datetime.utcnow()) < timedelta(seconds=1)

    missing_placeholder_path = tmp_path / "missing_placeholder.txt"
    monkey_patch_args(
        monkeypatch, ["jirahub", "sync", "--placeholder-path", str(missing_placeholder_path), str(CONFIG_PATH)]
    )
    assert command_line.main() == 0
    with open(missing_placeholder_path, "r") as file:
        new_placeholder = datetime.fromisoformat(file.read().strip())
    assert abs(new_placeholder - datetime.utcnow()) < timedelta(seconds=1)


def test_main_sync_missing_config(monkeypatch):
    monkey_patch_args(monkeypatch, ["jirahub", "sync", str(MISSING_CONFIG_PATH)])
    assert command_line.main() == 1


def test_main_sync_failure(monkeypatch):
    monkey_patch_args(monkeypatch, ["jirahub", "sync", str(BAD_CONFIG_PATH)])
    assert command_line.main() == 1
