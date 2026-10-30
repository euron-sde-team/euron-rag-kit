"""The optional model judge for evaluation runs with `grader: model`.

The judge reads the question, the context the answerer was given, the answer and the
reference answer, and returns faithfulness and correctness scores with a one-line reason.
Replies are parsed defensively (models wrap JSON in prose or code fences); anything that
does not parse raises `JudgeError`, and the evaluation falls back to deterministic grading
for that question and records that it did.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ragkit_server.ai.answerers import ChatClient
from ragkit_server.ai.prompts import judge_messages

_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
MAX_CONTEXT_CHARS = 6000


class JudgeError(Exception):
    """The judge's reply could not be used."""


@dataclass(frozen=True, slots=True)
class Verdict:
    faithfulness: float
    relevance: float | None
    correctness: float | None
    reason: str


def _score(value: Any, name: str, *, nullable: bool) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise JudgeError(f"{name} is not a number")
    return min(1.0, max(0.0, float(value)))


def parse_verdict(reply: str) -> Verdict:
    match = _OBJECT.search(reply)
    if match is None:
        raise JudgeError("no JSON object in the reply")
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError as exc:
        raise JudgeError("the reply is not valid JSON") from exc
    if not isinstance(data, dict):
        raise JudgeError("the reply is not an object")
    faithfulness = _score(data.get("faithfulness"), "faithfulness", nullable=False)
    relevance = _score(data.get("relevance"), "relevance", nullable=True)
    correctness = _score(data.get("correctness"), "correctness", nullable=True)
    reason = str(data.get("reason") or "")[:300]
    return Verdict(
        faithfulness=faithfulness or 0.0,
        relevance=relevance,
        correctness=correctness,
        reason=reason,
    )


class ModelJudge:
    def __init__(self, client: ChatClient, model: str | None) -> None:
        self.client = client
        self.model = model or client.default_model
        self.label = f"{client.provider}:{self.model}"

    async def grade(
        self, question: str, answer: str, contexts: Sequence[str], reference: str | None
    ) -> Verdict:
        trimmed: list[str] = []
        budget = MAX_CONTEXT_CHARS
        for text in contexts:
            if budget <= 0:
                break
            trimmed.append(text[:budget])
            budget -= len(text)
        reply, _ = await self.client.complete(
            judge_messages(question, answer, trimmed, reference), model=self.model, max_tokens=200
        )
        return parse_verdict(reply)
