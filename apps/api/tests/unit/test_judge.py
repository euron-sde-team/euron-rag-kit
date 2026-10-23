import pytest

from ragkit_server.ai.answerers import Usage
from ragkit_server.ai.judge import JudgeError, ModelJudge, parse_verdict


def test_verdicts_are_parsed_from_fenced_or_chatty_replies() -> None:
    verdict = parse_verdict(
        'Here you go:\n```json\n{"faithfulness": 0.75, "correctness": 1.2, "reason": "ok"}\n```'
    )
    assert verdict.faithfulness == 0.75
    assert verdict.correctness == 1.0  # clamped
    assert verdict.reason == "ok"
    assert parse_verdict('{"faithfulness": 1, "correctness": null}').correctness is None


@pytest.mark.parametrize(
    "reply",
    ["no json here", '{"faithfulness": "high"}', '{"faithfulness": true}', "[1, 2]", "{broken"],
)
def test_unusable_replies_raise(reply: str) -> None:
    with pytest.raises(JudgeError):
        parse_verdict(reply)


async def test_the_judge_sends_the_reference_and_trims_context() -> None:
    sent: list[list[dict[str, str]]] = []

    class FakeClient:
        provider = "ollama"
        default_model = "judge-model"

        async def complete(self, messages, *, model=None, max_tokens):  # type: ignore[no-untyped-def]
            sent.append(messages)
            return '{"faithfulness": 0.5, "correctness": 0.25, "reason": "partly"}', Usage()

        async def aclose(self) -> None:
            return None

    judge = ModelJudge(FakeClient(), None)
    verdict = await judge.grade(
        "q?", "an answer", ["x" * 5000, "y" * 5000, "z" * 10], "the reference"
    )
    assert judge.label == "ollama:judge-model"
    assert (verdict.faithfulness, verdict.correctness) == (0.5, 0.25)
    user = sent[0][1]["content"]
    assert "the reference" in user
    assert "z" * 10 not in user  # the context budget ran out before the third passage
