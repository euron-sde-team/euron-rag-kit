"""Column types.

`Embedding` hands numpy arrays straight to the asyncpg pgvector codec registered in
`db.session`, so vectors travel in binary both ways. (pgvector's own SQLAlchemy type
formats vectors as text first, which that binary codec rejects.)
"""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import Float
from sqlalchemy.sql.expression import ColumnElement
from sqlalchemy.types import UserDefinedType

# Embedding widths with a partial HNSW index (one per width, see the initial migration).
# A model of any other width is refused when a pipeline version is created.
SUPPORTED_DIMS: tuple[int, ...] = (384, 768, 1024, 1536)


class Embedding(UserDefinedType[Any]):
    cache_ok = True

    def __init__(self, dim: int | None = None) -> None:
        self.dim = dim

    def get_col_spec(self, **_: Any) -> str:
        return "vector" if self.dim is None else f"vector({self.dim})"

    def bind_processor(self, dialect: Any) -> None:
        return None

    def result_processor(self, dialect: Any, coltype: Any) -> None:
        return None

    class comparator_factory(UserDefinedType.Comparator[Any]):  # noqa: N801
        def cosine_distance(self, other: Any) -> ColumnElement[float]:
            return cast("ColumnElement[float]", self.op("<=>", return_type=Float)(other))
