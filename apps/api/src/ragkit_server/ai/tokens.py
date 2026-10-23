"""Token counting and token windows for chunking and context budgets.

Uses tiktoken's o200k_base encoding (a close proxy for current hosted models). If the
encoding cannot be loaded (an air-gapped host without the cached file), it falls back to
the four-characters-per-token rule and says so in the log once.
"""

from __future__ import annotations

import re
from typing import Any

from ragkit_server.core.logging import get_logger

log = get_logger("ragkit.tokens")
_WORD = re.compile(r"\S+")


class TokenCounter:
    def __init__(self, mode: str = "tiktoken") -> None:
        self._encoding: Any = None
        self.name = "heuristic"
        if mode == "tiktoken":
            try:
                import tiktoken

                self._encoding = tiktoken.get_encoding("o200k_base")
                self.name = "o200k_base"
            except Exception as exc:
                log.warning("tokenizer_fallback", fallback="heuristic", error=str(exc))

    def count(self, text: str) -> int:
        if not text:
            return 0
        if self._encoding is not None:
            return len(self._encoding.encode_ordinary(text))
        return max(1, (len(text) + 3) // 4)

    def truncate(self, text: str, max_tokens: int) -> str:
        if self.count(text) <= max_tokens:
            return text
        if self._encoding is not None:
            decoded: str = self._encoding.decode(self._encoding.encode_ordinary(text)[:max_tokens])
            return decoded
        return text[: max_tokens * 4]

    def windows(self, text: str, size: int, overlap: int) -> list[tuple[int, int]]:
        """Character spans of consecutive `size`-token windows overlapping by `overlap` tokens.

        Spans are snapped to word boundaries (a window never starts or ends inside a word),
        so a window can be a token or two longer than `size`.
        """
        if not text.strip():
            return []
        step = max(1, size - overlap)
        starts = self._token_starts(text)
        spans: list[tuple[int, int]] = []
        total = len(starts)
        for first in range(0, total, step):
            last = first + size
            start = _snap_start(text, starts[first])
            end = len(text) if last >= total else _snap_end(text, starts[last])
            if end > start and text[start:end].strip():
                spans.append((start, end))
            if last >= total:
                break
        return spans

    def _token_starts(self, text: str) -> list[int]:
        if self._encoding is not None:
            tokens = self._encoding.encode_ordinary(text)
            decoded, offsets = self._encoding.decode_with_offsets(tokens)
            if decoded == text:
                return [int(offset) for offset in offsets]
        # Heuristic: one token per four characters, starting at word boundaries.
        starts: list[int] = []
        for match in _WORD.finditer(text):
            word_start, word_end = match.span()
            starts.extend(range(word_start, word_end, 4))
        return starts


def _snap_start(text: str, index: int) -> int:
    # Inside a word: move forward to the next word, so no window starts mid-word.
    while 0 < index < len(text) and not text[index - 1].isspace() and not text[index].isspace():
        index += 1
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def _snap_end(text: str, index: int) -> int:
    # Inside a word: extend to its end, so no window ends mid-word.
    while 0 < index < len(text) and not text[index].isspace() and not text[index - 1].isspace():
        index += 1
    return index
