import pytest
from pathlib import Path
import re
import copy

import jirahub
from jirahub.config import load_config, generate_config_template, SyncFeature, validate_config, _REQUIRED_PARAMETERS
from jirahub.entities import Source


CONFIG_PATH = Path(__file__).parent / "configs"


def test_load_config_minimal():
    config = load_config(CONFIG_PATH / "minimal_config.py")

    assert config.jira.server == "https://test.jira.server"
    assert config.jira.project_key == "TEST"
    assert config.jira.github_issue_url_field_id == 12345
    assert config.jira.jirahub_metadata_field_id == 67890
    assert config.jira.closed_statuses == ["closed"]
    assert config.jira.close_status == "Closed"
    assert config.jira.reopen_status == "Reopened"
    assert config.jira.open_status is None
    assert config.jira.max_retries == 3
    assert config.jira.notify_watchers is True
    assert config.jira.sync_comments is False
    assert config.jira.sync_status is False
    assert config.jira.sync_labels is False
    assert config.jira.sync_milestones is False
    assert config.jira.create_tracking_comment is False
    assert config.jira.redact_patterns == []
    assert config.jira.issue_title_formatter is None
    assert config.jira.issue_body_formatter is None
    assert config.jira.comment_body_formatter is None
    assert config.jira.issue_filter is None
    assert config.jira.before_issue_create == []

    assert config.github.repository == "testing/test-repo"
    assert config.github.max_retries == 3
    assert config.github.sync_comments is False
    assert config.github.sync_status is False
    assert config.github.sync_labels is False
    assert config.github.sync_milestones is False
    assert config.github.create_tracking_comment is False
    assert config.github.redact_patterns == []
    assert config.github.issue_title_formatter is None
    assert config.github.issue_body_formatter is None
    assert config.github.comment_body_formatter is None
    assert config.github.issue_filter is None
    assert config.github.before_issue_create == []


def test_load_config_full():
    config = load_config(CONFIG_PATH / "full_config.py")

    assert config.jira.server == "https://test.jira.server"
    assert config.jira.project_key == "TEST"
    assert config.jira.github_issue_url_field_id == 12345
    assert config.jira.jirahub_metadata_field_id == 67890
    assert config.jira.closed_statuses == ["Closed", "Done"]
    assert config.jira.close_status == "Done"
    assert config.jira.reopen_status == "Ready"
    assert config.jira.open_status == "Open"
    assert config.jira.max_retries == 5
    assert config.jira.notify_watchers is False
    assert config.jira.sync_comments is True
    assert config.jira.sync_status is True
    assert config.jira.sync_labels is True
    assert config.jira.sync_milestones is True
    assert config.jira.create_tracking_comment is True
    assert config.jira.redact_patterns == [re.compile(r"(?<=secret GitHub data: ).+?\b")]
    assert callable(config.jira.issue_title_formatter)
    assert callable(config.jira.issue_body_formatter)
    assert callable(config.jira.comment_body_formatter)
    assert callable(config.jira.issue_filter)
    assert callable(config.jira.before_issue_create[0])

    assert config.github.repository == "testing/test-repo"
    assert config.github.max_retries == 10
    assert config.github.sync_comments is True
    assert config.github.sync_status is True
    assert config.github.sync_labels is True
    assert config.github.sync_milestones is True
    assert config.github.create_tracking_comment is True
    assert config.github.redact_patterns == [re.compile(r"(?<=secret JIRA data: ).+?\b")]
    assert callable(config.github.issue_title_formatter)
    assert callable(config.github.issue_body_formatter)
    assert callable(config.github.comment_body_formatter)
    assert callable(config.github.issue_filter)
    assert callable(config.github.before_issue_create[0])


def test_load_config_multiple():
    config = load_config([CONFIG_PATH / "fragment_config_base.py", CONFIG_PATH / "fragment_config_overrides.py"])

    # From the base config
    assert config.jira.server == "https://test.jira.server"
    assert callable(config.jira.issue_filter)

    # From the overrides config
    assert config.jira.project_key == "TEST"
    assert config.jira.max_retries == 7
    assert config.github.repository == "testing/test-repo"
    assert config.jira.sync_milestones is False


def test_load_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_config([CONFIG_PATH / "full_config.py", CONFIG_PATH / "missing_file.py"])


def test_load_config_incomplete():
    with pytest.raises(RuntimeError):
        load_config(CONFIG_PATH / "incomplete_config.py")


def test_generate_config_template():
    path = Path(jirahub.__file__).parent / "resources" / "config_template.py"
    with path.open("r") as file:
        expected = file.read()

    assert generate_config_template() == expected


def test_validate_config(config):
    # Initially, no exceptions
    validate_config(config)

    for param, _ in _REQUIRED_PARAMETERS:
        invalid_config = copy.deepcopy(config)
        parts = param.split(".")
        setattr(getattr(invalid_config, parts[0]), parts[1], None)
        with pytest.raises(RuntimeError):
            validate_config(invalid_config)


class TestJirahubConfig:
    def test_get_source_config(self, config):
        assert config.get_source_config(Source.JIRA) == config.jira
        assert config.get_source_config(Source.GITHUB) == config.github

    @pytest.mark.parametrize("source", list(Source))
    @pytest.mark.parametrize("sync_feature", list(SyncFeature))
    @pytest.mark.parametrize("enabled", [True, False])
    def test_is_enabled(self, config, source, sync_feature, enabled):
        setattr(config.get_source_config(source), sync_feature.key, enabled)
        assert config.is_enabled(source, sync_feature) is enabled
