import importlib.resources as importlib_resources
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Callable
from pathlib import Path
from collections.abc import Iterable
import re

from . import resources as jirahub_resources
from .entities import Source, Issue, Comment


__all__ = ["load_config", "generate_config_template"]


logger = logging.getLogger(__name__)


class SyncFeature(Enum):
    SYNC_COMMENTS = ({"ADD_COMMENTS", "DELETE_OWN_COMMENTS", "EDIT_OWN_COMMENTS"}, False)
    SYNC_STATUS = ({"CLOSE_ISSUES", "RESOLVE_ISSUES", "TRANSITION_ISSUES"}, True)
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
class JiraConfig:
    server: str = None
    project_key: str = None
    github_issue_url_field_id: int = None
    jirahub_metadata_field_id: int = None
    closed_statuses: List[str] = field(default_factory=lambda: ["closed"])
    close_status: str = "Closed"
    reopen_status: str = "Reopened"
    open_status: str = None
    max_retries: int = 3
    notify_watchers: bool = True
    sync_comments: bool = False
    sync_status: bool = False
    sync_labels: bool = False
    sync_milestones: bool = False
    create_tracking_comment: bool = False
    redact_patterns: List[re.Pattern] = field(default_factory=list)
    issue_title_formatter: Callable[[Issue, str], str] = None
    issue_body_formatter: Callable[[Issue, str], str] = None
    comment_body_formatter: Callable[[Issue, Comment, str], str] = None
    issue_filter: Callable[[Issue], bool] = None
    before_issue_create: List[Callable[[Issue, dict], dict]] = field(default_factory=list)


@dataclass
class GithubConfig:
    repository: str = None
    max_retries: int = 3
    sync_comments: bool = False
    sync_status: bool = False
    sync_labels: bool = False
    sync_milestones: bool = False
    create_tracking_comment: bool = False
    redact_patterns: List[re.Pattern] = field(default_factory=list)
    issue_title_formatter: Callable[[Issue, str], str] = None
    issue_body_formatter: Callable[[Issue, str], str] = None
    comment_body_formatter: Callable[[Issue, Comment, str], str] = None
    issue_filter: Callable[[Issue], bool] = None
    before_issue_create: List[Callable[[Issue, dict], dict]] = field(default_factory=list)


@dataclass
class JirahubConfig:
    jira: JiraConfig = field(default_factory=JiraConfig)
    github: GithubConfig = field(default_factory=GithubConfig)

    def get_source_config(self, source):
        if source == Source.JIRA:
            return self.jira
        else:
            return self.github

    def is_enabled(self, source, sync_feature):
        return getattr(self.get_source_config(source), sync_feature.key)


def load_config(paths):
    config = JirahubConfig()

    if not isinstance(paths, Iterable) or isinstance(paths, str):
        paths = [paths]

    for path in paths:
        p = Path(path)
        if not (p.exists() and p.is_file()):
            raise FileNotFoundError(f"Config file at {path} not found")
        with p.open() as file:
            exec(file.read(), {}, {"c": config})

    validate_config(config)

    return config


def generate_config_template():
    return importlib_resources.read_text(jirahub_resources, "config_template.py")


_REQUIRED_PARAMETERS = {
    ("jira.server", "JIRA server"),
    ("jira.project_key", "JIRA project key"),
    ("jira.github_issue_url_field_id", "JIRA issue URL field ID"),
    ("jira.jirahub_metadata_field_id", "JIRA metadata field ID"),
    ("github.repository", "GitHub repository"),
}


def validate_config(config):
    for param, description in _REQUIRED_PARAMETERS:
        value = config
        for part in param.split("."):
            value = getattr(value, part)
        if not value:
            raise RuntimeError(f"Missing {description}, please set c.{param} in your config file")
