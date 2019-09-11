from enum import Enum, auto
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Set
import hashlib


__all__ = ["Source", "MetadataField", "User", "Comment", "Issue"]


class Source(Enum):
    JIRA = "JIRA"
    GITHUB = "GitHub"

    def __str__(self):
        return self.value

    @property
    def other(self):
        if self == Source.JIRA:
            return Source.GITHUB
        else:
            return Source.JIRA


class MetadataField(Enum):
    MIRROR_ID = auto()
    MIRROR_PROJECT = auto()
    BODY_HASH = auto()
    TITLE_HASH = auto()
    IS_TRACKING_COMMENT = auto()

    @property
    def key(self):
        return self.name.lower()


@dataclass(frozen=True)
class User:
    source: Source
    username: str
    display_name: str
    raw_user: Any = None

    def __str__(self):
        return f"{self.source} user {self.display_name} ({self.username})"


@dataclass(frozen=True)
class Comment:
    source: Source
    comment_id: int
    created_at: datetime
    updated_at: datetime
    user: User
    is_bot: bool
    body: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    issue_metadata: Dict[str, Any] = field(default_factory=dict)
    raw_comment: Any = None

    def __str__(self):
        return f"{self.source} comment {self.comment_id}"

    @property
    def mirror_id(self):
        return self.metadata.get(MetadataField.MIRROR_ID.key)

    @property
    def is_tracking_comment(self):
        return bool(self.metadata.get(MetadataField.IS_TRACKING_COMMENT.key))

    @property
    def body_hash(self):
        if self.is_bot:
            return self.metadata[MetadataField.BODY_HASH.key]
        else:
            return _hash_string(self.body)


@dataclass(frozen=True)
class Issue:
    source: Source
    is_bot: bool
    issue_id: Any
    project: str
    created_at: datetime
    updated_at: datetime
    user: User
    title: str
    is_open: bool
    body: str = ""
    labels: Set[str] = field(default_factory=set)
    priority: str = None
    issue_type: str = None
    milestones: Set[str] = field(default_factory=set)
    components: Set[str] = field(default_factory=set)
    comments: List[Comment] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    raw_issue: Any = None
    github_repository: str = None
    github_issue_id: int = None

    def __str__(self):
        return f"{self.source} issue {self.issue_id}"

    @property
    def mirror_id(self):
        return self._get_metadata(MetadataField.MIRROR_ID)

    @property
    def mirror_project(self):
        return self._get_metadata(MetadataField.MIRROR_PROJECT)

    @property
    def body_hash(self):
        if self.is_bot:
            return self.metadata[MetadataField.BODY_HASH.key]
        else:
            return _hash_string(self.body)

    @property
    def title_hash(self):
        if self.is_bot:
            return self.metadata[MetadataField.TITLE_HASH.key]
        else:
            return _hash_string(self.title)

    def _get_metadata(self, metadata_field):
        if metadata_field.key in self.metadata:
            return self.metadata[metadata_field.key]

        comment = self.tracking_comment
        if comment:
            return comment.issue_metadata.get(metadata_field.key)

        return None

    @property
    def tracking_comment(self):
        return next((c for c in self.comments if c.is_tracking_comment), None)


def _hash_string(value):
    if value is None:
        value = ""

    return hashlib.md5(value.encode("utf-8")).hexdigest()
