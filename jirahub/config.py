from datetime import datetime, timezone
import importlib.resources as importlib_resources
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Set, List
from configparser import ConfigParser
from pathlib import Path
from collections.abc import Iterable
from functools import partial
import re

from . import resources as jirahub_resources
from .entities import Source


__all__ = ["load_config", "generate_config_template"]


logger = logging.getLogger(__name__)


class SyncFeature(Enum):
    CREATE_ISSUES = ({"CREATE_ISSUES", "EDIT_ISSUES"}, False)
    SYNC_COMMENTS = ({"ADD_COMMENTS", "DELETE_OWN_COMMENTS", "EDIT_OWN_COMMENTS"}, False)
    SYNC_STATUS = ({"CLOSE_ISSUES", "RESOLVE_ISSUES"}, True)
    SYNC_LABELS = ({"EDIT_ISSUES"}, True)
    SYNC_MILESTONES = ({"EDIT_ISSUES", "RESOLVE_ISSUES"}, True)

    def __init__(self, jira_permissions_required, github_push_required):
        self.jira_permissions_required = jira_permissions_required
        self.github_push_required = github_push_required

    @property
    def key(self):
        return self.name.lower()

    def __str__(self):
        return self.name.lower()


@dataclass
class FilterConfig:
    min_created_at: datetime = None
    include_issue_types: Set[str] = field(default_factory=set)
    exclude_issue_types: Set[str] = field(default_factory=set)
    include_components: Set[str] = field(default_factory=set)
    exclude_components: Set[str] = field(default_factory=set)
    include_labels: Set[str] = field(default_factory=set)
    exclude_labels: Set[str] = field(default_factory=set)
    open_only: bool = True

    @classmethod
    def from_raw_config(cls, raw_config, section):
        options = {}

        options.update(_get_datetime_options(raw_config, section, ["min_created_at"]))
        options.update(
            _get_set_options(
                raw_config,
                section,
                [
                    "include_issue_types",
                    "exclude_issue_types",
                    "include_components",
                    "exclude_components",
                    "include_labels",
                    "exclude_labels",
                ],
            )
        )
        options.update(_get_bool_options(raw_config, section, ["open_only"]))

        return cls(**options)


@dataclass
class SyncConfig:
    create_issues: bool = False
    sync_comments: bool = False
    sync_status: bool = False
    sync_labels: bool = False
    sync_milestones: bool = False
    labels: Set[str] = field(default_factory=set)
    redact_regexes: List[re.Pattern] = field(default_factory=list)

    @classmethod
    def from_raw_config(cls, raw_config, section):
        options = {}

        options.update(
            _get_bool_options(
                raw_config, section, ["create_issues", "sync_comments", "sync_status", "sync_labels", "sync_milestones"]
            )
        )
        options.update(_get_set_options(raw_config, section, ["labels"]))
        options.update(_get_regex_list_options(raw_config, section, ["redact_regexes"]))

        return cls(**options)


@dataclass
class DefaultsConfig:
    issue_type: str = "Story"
    priority: str = None
    components: Set[str] = field(default_factory=set)

    @classmethod
    def from_raw_config(cls, raw_config, section):
        options = {}

        options.update(_get_string_options(raw_config, section, ["issue_type", "priority"]))
        options.update(_get_set_options(raw_config, section, ["components"]))

        return cls(**options)


@dataclass
class JiraConfig:
    server: str
    project_key: str
    github_repository_field: str = None
    github_issue_id_field: str = None
    closed_statuses: Set[str] = field(default_factory=lambda: {"closed"})
    close_status: str = "Closed"
    reopen_status: str = "Reopened"
    open_status: str = None
    max_retries: int = 3
    sync: SyncConfig = field(default_factory=lambda: SyncConfig())
    filter: FilterConfig = field(default_factory=lambda: FilterConfig())
    defaults: DefaultsConfig = field(default_factory=lambda: DefaultsConfig())

    @classmethod
    def from_raw_config(cls, raw_config):
        options = {}

        options.update(
            _get_string_options(
                raw_config,
                "jira",
                [
                    "server",
                    "project_key",
                    "github_repository_field",
                    "github_issue_id_field",
                    "close_status",
                    "reopen_status",
                    "open_status",
                    "create_issue_type",
                    "create_priority",
                    "create_component",
                ],
            )
        )
        options.update(_get_int_options(raw_config, "jira", ["max_retries"]))
        options.update(_get_set_options(raw_config, "jira", ["closed_statuses"], lower=True))

        if raw_config.has_section("jira:sync"):
            options["sync"] = SyncConfig.from_raw_config(raw_config, "jira:sync")

        if raw_config.has_section("jira:filter"):
            options["filter"] = FilterConfig.from_raw_config(raw_config, "jira:filter")

        if raw_config.has_section("jira:defaults"):
            options["defaults"] = DefaultsConfig.from_raw_config(raw_config, "jira:defaults")

        return cls(**options)


@dataclass
class GithubConfig:
    repository: str
    max_retries: int = 3
    sync: SyncConfig = field(default_factory=lambda: SyncConfig())
    filter: FilterConfig = field(default_factory=lambda: FilterConfig())
    defaults: DefaultsConfig = field(default_factory=lambda: DefaultsConfig())

    @classmethod
    def from_raw_config(cls, raw_config):
        options = {}

        options.update(_get_string_options(raw_config, "github", ["repository"]))
        options.update(_get_int_options(raw_config, "github", ["max_retries"]))

        if raw_config.has_section("github:sync"):
            options["sync"] = SyncConfig.from_raw_config(raw_config, "github:sync")

        if raw_config.has_section("github:filter"):
            options["filter"] = FilterConfig.from_raw_config(raw_config, "github:filter")

        return cls(**options)


@dataclass
class JirahubConfig:
    jira: JiraConfig
    github: GithubConfig

    @classmethod
    def from_raw_config(cls, raw_config):
        options = {}

        options["jira"] = JiraConfig.from_raw_config(raw_config)
        options["github"] = GithubConfig.from_raw_config(raw_config)

        return cls(**options)

    def get_source_config(self, source):
        if source == Source.JIRA:
            return self.jira
        else:
            return self.github

    def get_filter_config(self, source):
        return self.get_source_config(source).filter

    def get_sync_config(self, source):
        return self.get_source_config(source).sync

    def get_defaults_config(self, source):
        return self.get_source_config(source).defaults

    def is_enabled(self, source, sync_feature):
        return getattr(self.get_sync_config(source), sync_feature.key)


def _get_datetime(raw_config, section, option_name):
    value = raw_config.get(section, option_name).strip()

    dt = datetime.fromisoformat(value)

    return dt.replace(tzinfo=timezone.utc)


def _get_set(raw_config, section, option_name, lower=False):
    value = raw_config.get(section, option_name).strip()
    if lower:
        value = value.lower()

    if "\n" in value:
        return {v.strip() for v in value.split("\n") if v.strip()}
    else:
        return {v.strip() for v in value.split(",") if v.strip()}


def _get_regex_list(raw_config, section, option_name):
    value = raw_config.get(section, option_name).strip()

    return [re.compile(v.strip()) for v in value.split("\n") if v.strip()]


def _get_datetime_options(raw_config, section, option_names):
    return _get_options(raw_config, section, option_names, partial(_get_datetime, raw_config))


def _get_set_options(raw_config, section, option_names, lower=False):
    return _get_options(raw_config, section, option_names, partial(partial(_get_set, lower=lower), raw_config))


def _get_regex_list_options(raw_config, section, option_names):
    return _get_options(raw_config, section, option_names, partial(_get_regex_list, raw_config))


def _get_bool_options(raw_config, section, option_names):
    return _get_options(raw_config, section, option_names, raw_config.getboolean)


def _get_string_options(raw_config, section, option_names):
    return _get_options(raw_config, section, option_names, raw_config.get)


def _get_int_options(raw_config, section, option_names):
    return _get_options(raw_config, section, option_names, raw_config.getint)


def _get_options(raw_config, section, option_names, get_function):
    options = {}
    for option_name in option_names:
        if raw_config.has_option(section, option_name):
            options[option_name] = get_function(section, option_name)
    return options


def load_config(paths):
    if not isinstance(paths, Iterable) or isinstance(paths, str):
        paths = [paths]

    for path in paths:
        p = Path(path)
        if not (p.exists() and p.is_file()):
            raise FileNotFoundError(f"Config file at {path} not found")

    raw_config = ConfigParser()
    raw_config.read(paths)

    return JirahubConfig.from_raw_config(raw_config)


def generate_config_template():
    return importlib_resources.read_text(jirahub_resources, "config_template.ini")
