"""Every model, imported here so `Base.metadata` is complete for Alembic and the tests."""

from ragkit_server.models.api_key import ApiKey
from ragkit_server.models.audit import AuditEvent
from ragkit_server.models.chunk import Chunk
from ragkit_server.models.collection import Collection
from ragkit_server.models.document import Document, DocumentSection
from ragkit_server.models.evaluation import Dataset, DatasetItem, EvalResult, EvalRun
from ragkit_server.models.pipeline import Index, IndexEntry, PipelineVersion
from ragkit_server.models.project import Membership, Project
from ragkit_server.models.query_log import QueryLog
from ragkit_server.models.user import User

__all__ = [
    "ApiKey",
    "AuditEvent",
    "Chunk",
    "Collection",
    "Dataset",
    "DatasetItem",
    "Document",
    "DocumentSection",
    "EvalResult",
    "EvalRun",
    "Index",
    "IndexEntry",
    "Membership",
    "PipelineVersion",
    "Project",
    "QueryLog",
    "User",
]
