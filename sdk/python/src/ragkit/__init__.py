"""Python SDK and CLI for Euron RAGKit: ingest, query, answer and evaluate."""

__version__ = "0.1.0"

from ragkit.client import CollectionClient, Evals, RAGKit, load_jsonl
from ragkit.errors import (
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
    RAGKitError,
    RateLimitError,
    ValidationError,
)

__all__ = [
    "AuthenticationError",
    "CollectionClient",
    "Evals",
    "NotFoundError",
    "PermissionDeniedError",
    "RAGKit",
    "RAGKitError",
    "RateLimitError",
    "ValidationError",
    "__version__",
    "load_jsonl",
]
