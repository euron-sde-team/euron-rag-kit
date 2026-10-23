"""A retrieved chunk as every later stage sees it: fusion, reranking, answers and evaluation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Hit:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    external_id: str
    location: str
    heading: str
    text: str
    context: str | None
    token_count: int
    metadata: dict[str, Any] = field(default_factory=dict)
    section_ordinal: int = 0
    vector_score: float | None = None
    keyword_score: float | None = None
    fused_score: float = 0.0
    rerank_score: float | None = None
    vector_rank: int | None = None
    keyword_rank: int | None = None
    fused_rank: int | None = None
    rerank_rank: int | None = None
    # Citation number, once the hit is packed into an answer's context.
    n: int = 0

    @property
    def passage(self) -> str:
        """What an answerer and the relevance judge read: the window when there is one."""
        return self.context or self.text

    @property
    def score(self) -> float:
        return self.rerank_score if self.rerank_score is not None else self.fused_score

    def public(self, *, rank: int) -> dict[str, Any]:
        """The shape sent to clients: scores and ranks per stage, rounded."""

        def rounded(value: float | None) -> float | None:
            return None if value is None else round(value, 4)

        return {
            "rank": rank,
            "chunk_id": str(self.chunk_id),
            "document_id": str(self.document_id),
            "document_title": self.document_title,
            "external_id": self.external_id,
            "location": self.location,
            "heading": self.heading,
            "text": self.text,
            "context": self.context,
            "metadata": self.metadata,
            "score": round(self.score, 4),
            "scores": {
                "vector": rounded(self.vector_score),
                "keyword": rounded(self.keyword_score),
                "fused": rounded(self.fused_score),
                "rerank": rounded(self.rerank_score),
            },
            "ranks": {
                "vector": self.vector_rank,
                "keyword": self.keyword_rank,
                "fused": self.fused_rank,
                "rerank": self.rerank_rank,
            },
        }
