import pytest
from pathlib import Path
from datetime import datetime, timezone
import re

import jirahub
from jirahub.config import load_config, generate_config_template, SyncFeature
from jirahub.entities import Source


CONFIG_PATH = Path(__file__).parent / "configs"


def test_load_config_minimal():
    config = load_config(CONFIG_PATH / "minimal_config.ini")

    assert config.jira.server == "https://test.jira.server"
    assert config.jira.project_key == "TEST"
    assert config.jira.github_repository_field is None
    assert config.jira.github_issue_id_field is None
    assert config.jira.closed_statuses == {"closed"}
    assert config.jira.close_status == "Closed"
    assert config.jira.reopen_status == "Reopened"
    assert config.jira.open_status is None

    assert config.jira.sync.create_issues is False
    assert config.jira.sync.sync_comments is False
    assert config.jira.sync.sync_status is False
    assert config.jira.sync.sync_labels is False
    assert config.jira.sync.sync_milestones is False
    assert config.jira.sync.labels == set()
    assert config.jira.sync.redact_regexes == []

    assert config.jira.filter.min_created_at is None
    assert config.jira.filter.include_labels == set()
    assert config.jira.filter.exclude_labels == set()
    assert config.jira.filter.open_only is True

    assert config.jira.defaults.issue_type == "Story"
    assert config.jira.defaults.priority is None
    assert config.jira.defaults.components == set()

    assert config.github.repository == "testing/test-repo"
    assert config.github.max_retries == 3

    assert config.github.sync.create_issues is False
    assert config.github.sync.sync_comments is False
    assert config.github.sync.sync_status is False
    assert config.github.sync.sync_labels is False
    assert config.github.sync.sync_milestones is False
    assert config.github.sync.labels == set()
    assert config.github.sync.redact_regexes == []

    assert config.github.filter.min_created_at is None
    assert config.github.filter.include_issue_types == set()
    assert config.github.filter.exclude_issue_types == set()
    assert config.github.filter.include_components == set()
    assert config.github.filter.exclude_components == set()
    assert config.github.filter.include_labels == set()
    assert config.github.filter.exclude_labels == set()
    assert config.github.filter.open_only is True


def test_load_config_full():
    config = load_config(CONFIG_PATH / "full_config.ini")

    assert config.jira.server == "https://test.jira.server"
    assert config.jira.project_key == "TEST"
    assert config.jira.github_repository_field == "github_repository"
    assert config.jira.github_issue_id_field == "github_issue_id"
    assert config.jira.closed_statuses == {"closed", "done"}
    assert config.jira.close_status == "Done"
    assert config.jira.reopen_status == "Ready"
    assert config.jira.open_status == "Open"
    assert config.jira.max_retries == 5

    assert config.jira.sync.create_issues is True
    assert config.jira.sync.sync_comments is True
    assert config.jira.sync.sync_status is True
    assert config.jira.sync.sync_labels is True
    assert config.jira.sync.sync_milestones is True
    assert config.jira.sync.labels == {"From GitHub"}
    assert config.jira.sync.redact_regexes == [re.compile(r"(?<=secret GitHub data: ).+?\b")]

    assert config.jira.filter.min_created_at == datetime(1983, 11, 20, 11, 0, 0, tzinfo=timezone.utc)
    assert config.jira.filter.include_labels == {"Possible"}
    assert config.jira.filter.exclude_labels == {"Impossible"}
    assert config.jira.filter.open_only is False

    assert config.jira.defaults.issue_type == "Bug"
    assert config.jira.defaults.priority == "Critical"
    assert config.jira.defaults.components == {"Doohickey"}

    assert config.github.repository == "testing/test-repo"
    assert config.github.max_retries == 10

    assert config.github.sync.create_issues is True
    assert config.github.sync.sync_comments is True
    assert config.github.sync.sync_status is True
    assert config.github.sync.sync_labels is True
    assert config.github.sync.sync_milestones is True
    assert config.github.sync.labels == {"From JIRA"}
    assert config.github.sync.redact_regexes == [re.compile(r"(?<=secret JIRA data: ).+?\b")]

    assert config.github.filter.min_created_at == datetime(1983, 11, 20, 11, 0, 0, tzinfo=timezone.utc)
    assert config.github.filter.include_issue_types == {"Bug", "Story", "Task"}
    assert config.github.filter.exclude_issue_types == {"Epic"}
    assert config.github.filter.include_components == {"Thingummy", "Whatsit"}
    assert config.github.filter.exclude_components == {"Widget"}
    assert config.github.filter.include_labels == {"Possible", "Unlikely"}
    assert config.github.filter.exclude_labels == {"Impossible"}
    assert config.github.filter.open_only is True


def test_load_config_multiple():
    config = load_config([CONFIG_PATH / "fragment_config_base.ini", CONFIG_PATH / "fragment_config_overrides.ini"])

    # From the base config
    assert config.jira.server == "https://test.jira.server"
    assert config.jira.sync.create_issues is True

    # From the overrides config
    assert config.jira.project_key == "TEST"
    assert config.jira.max_retries == 7
    assert config.github.repository == "testing/test-repo"
    assert config.jira.sync.sync_milestones is False


def test_load_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_config([CONFIG_PATH / "full_config.ini", CONFIG_PATH / "missing_file.ini"])


def test_load_config_incomplete():
    with pytest.raises(TypeError):
        load_config(CONFIG_PATH / "incomplete_config.ini")


def test_load_config_invalid_data_type():
    with pytest.raises(ValueError):
        load_config(CONFIG_PATH / "invalid_type_config.ini")


def test_generate_config_template():
    path = Path(jirahub.__file__).parent / "resources" / "config_template.ini"
    with path.open("r") as file:
        expected = file.read()

    assert generate_config_template() == expected


class TestJirahubConfig:
    def test_get_source_config(self, config):
        assert config.get_source_config(Source.JIRA) == config.jira
        assert config.get_source_config(Source.GITHUB) == config.github

    def test_get_filter_config(self, config):
        assert config.get_filter_config(Source.JIRA) == config.jira.filter
        assert config.get_filter_config(Source.GITHUB) == config.github.filter

    def test_get_sync_config(self, config):
        assert config.get_sync_config(Source.JIRA) == config.jira.sync
        assert config.get_sync_config(Source.GITHUB) == config.github.sync

    def test_get_defaults_config(self, config):
        assert config.get_defaults_config(Source.JIRA) == config.jira.defaults
        assert config.get_defaults_config(Source.GITHUB) == config.github.defaults

    @pytest.mark.parametrize("source", list(Source))
    @pytest.mark.parametrize("sync_feature", list(SyncFeature))
    @pytest.mark.parametrize("enabled", [True, False])
    def test_is_enabled(self, config, source, sync_feature, enabled):
        setattr(config.get_sync_config(source), sync_feature.key, enabled)
        assert config.is_enabled(source, sync_feature) is enabled
