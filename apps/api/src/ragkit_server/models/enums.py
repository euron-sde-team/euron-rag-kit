"""Value sets stored as text with CHECK constraints (cheaper to evolve than Postgres enums)."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"

    @property
    def rank(self) -> int:
        return {Role.VIEWER: 1, Role.EDITOR: 2, Role.OWNER: 3}[self]

    def allows(self, required: Role) -> bool:
        return self.rank >= required.rank


class SourceType(StrEnum):
    FILE = "file"
    URL = "url"
    TEXT = "text"


class DocumentKind(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    MD = "md"
    HTML = "html"
    TXT = "txt"
    CSV = "csv"


class SectionKind(StrEnum):
    PAGE = "page"
    SECTION = "section"
    TABLE = "table"


class JobStatus(StrEnum):
    """Documents (parsing) and index entries (chunking and embedding) share these states."""

    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


UNFINISHED = (JobStatus.QUEUED, JobStatus.PROCESSING)


class IndexStatus(StrEnum):
    EMPTY = "empty"
    BUILDING = "building"
    READY = "ready"
    FAILED = "failed"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

    @property
    def finished(self) -> bool:
        return self in (RunStatus.COMPLETED, RunStatus.FAILED)


class QueryKind(StrEnum):
    QUERY = "query"
    ANSWER = "answer"
