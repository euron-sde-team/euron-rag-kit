from __future__ import annotations

import uuid
from typing import Any

from ragkit_server.retrieval.types import Hit


def hit(
    text: str,
    *,
    n: int = 1,
    title: str = "Handbook",
    location: str = "Section 1",
    heading: str = "",
    external_id: str | None = None,
    context: str | None = None,
    fused: float = 0.0,
    metadata: dict[str, Any] | None = None,
) -> Hit:
    return Hit(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid5(uuid.NAMESPACE_URL, title),
        document_title=title,
        external_id=external_id or title.lower().replace(" ", "-"),
        location=location,
        heading=heading,
        text=text,
        context=context,
        token_count=max(1, len(text) // 4),
        metadata=metadata or {},
        fused_score=fused,
        n=n,
    )
