from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Any, Set


__all__ = ["Source", "User", "Comment", "Issue", "Metadata", "CommentMetadata"]


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


@dataclass(frozen=True)
class CommentMetadata:
    jira_comment_id: int
    github_comment_id: int


@dataclass(frozen=True)
class Metadata:
    github_repository: str = None
    github_issue_id: int = None
    github_tracking_comment_id: int = None
    jira_tracking_comment_id: int = None
    comments: List[CommentMetadata] = field(default_factory=list)


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
    raw_comment: Any = None

    def __str__(self):
        return f"{self.source} comment {self.comment_id}"


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
    metadata: Metadata = field(default_factory=Metadata)
    raw_issue: Any = None

    def __str__(self):
        return f"{self.source} issue {self.issue_id}"
