import pytest
from sqlalchemy.dialects import postgresql

from ragkit_server.models import Chunk
from ragkit_server.retrieval.filters import MAX_CONDITIONS, FilterError, compile_filter


def sql(spec: dict) -> tuple[str, dict]:  # type: ignore[type-arg]
    expression = compile_filter(spec, Chunk.meta)
    assert expression is not None
    compiled = expression.compile(dialect=postgresql.dialect())
    return str(compiled), compiled.params


def test_no_filter_compiles_to_nothing() -> None:
    assert compile_filter(None, Chunk.meta) is None
    assert compile_filter({}, Chunk.meta) is None


def test_equality_uses_jsonb_containment_with_bound_values() -> None:
    text, params = sql({"section": "guides", "author.team": "payments"})
    assert text.count("@>") == 2
    assert {"section": "guides"} in params.values()
    assert {"author": {"team": "payments"}} in params.values()


def test_comparisons_cast_only_values_of_the_right_type() -> None:
    text, params = sql({"year": {"$gte": 2025}, "published": {"$lt": "2026-07-01"}})
    assert "CASE WHEN (jsonb_typeof" in text
    assert "AS NUMERIC" in text
    assert 2025 in params.values()
    assert "2026-07-01" in params.values()


def test_membership_logic_and_existence() -> None:
    text, _ = sql(
        {
            "$or": [
                {"audience": {"$in": ["developers", "admins"]}},
                {"tags": {"$contains": "beta"}},
            ],
            "draft": {"$exists": False},
            "$not": {"section": "legal"},
        }
    )
    assert " OR " in text
    assert "IS NULL" in text
    assert "NOT" in text


@pytest.mark.parametrize(
    ("spec", "fragment"),
    [
        ({"a; drop table chunks": 1}, "field names"),
        ({"x": {"$regex": ".*"}}, "unknown operator"),
        ({"$or": []}, "non-empty list"),
        ({"x": None}, "strings, numbers or booleans"),
        ({"x": {"$in": []}}, "list of 1 to"),
        ({"x": {"$gt": True}}, "compares numbers or strings"),
        ({"x": {"$exists": "yes"}}, "true or false"),
        ({"$not": {"$not": {"$not": {"$not": {"x": 1}}}}}, "nests deeper"),
    ],
)
def test_invalid_filters_explain_the_problem(spec: dict, fragment: str) -> None:  # type: ignore[type-arg]
    with pytest.raises(FilterError) as error:
        compile_filter(spec, Chunk.meta)
    assert fragment in error.value.message
    assert error.value.code == "invalid_filter"


def test_condition_budget() -> None:
    spec = {f"field{i}": i for i in range(MAX_CONDITIONS + 1)}
    with pytest.raises(FilterError):
        compile_filter(spec, Chunk.meta)
