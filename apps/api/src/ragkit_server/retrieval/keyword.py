"""The full-text side of retrieval: a query's words as a Postgres tsquery."""

from __future__ import annotations

import re

from ragkit_server.core.text import STOPWORDS

_WORD = re.compile(r"[a-z0-9]+")
MAX_TERMS = 24


def keyword_query(question: str) -> str | None:
    """An OR query over the question's meaningful words, ranked by cover density later.

    `websearch_to_tsquery` would AND every word, which suits a search box and fails a
    natural-language question whose words are mostly not in the passage. Words are passed
    unstemmed: Postgres applies the same English stemmer to the query and to the index.
    """
    words = [w for w in _WORD.findall(question.lower()) if w not in STOPWORDS and len(w) > 1]
    unique = list(dict.fromkeys(words))[:MAX_TERMS]
    return " | ".join(unique) or None
