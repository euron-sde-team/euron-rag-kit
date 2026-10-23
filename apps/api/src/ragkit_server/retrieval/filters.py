"""Metadata filters: a small JSON language compiled to SQL over `chunks.metadata` (JSONB).

    {"section": "guides"}                              equality (uses the GIN index)
    {"year": {"$gte": 2025}}                           comparison (numbers or ISO strings)
    {"audience": {"$in": ["developers", "admins"]}}    membership
    {"tags": {"$contains": "beta"}}                    array contains a value
    {"$or": [{"section": "guides"}, {"section": "api"}]}

Field names are checked against a strict pattern and every value is a bound parameter, so
nothing in a filter is ever spliced into SQL text.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from sqlalchemy import Numeric, and_, case, func, not_, or_
from sqlalchemy.sql.elements import ColumnElement

from ragkit_server.core.errors import UnprocessableError

MAX_CONDITIONS = 32
MAX_DEPTH = 4
MAX_IN_VALUES = 50
_FIELD = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,63}$")
_COMPARISONS = {"$gt", "$gte", "$lt", "$lte"}
_FIELD_OPERATORS = {"$eq", "$ne", "$in", "$nin", "$exists", "$contains", *_COMPARISONS}
Scalar = str | int | float | bool


class FilterError(UnprocessableError):
    code = "invalid_filter"
    message = "The filter is not valid."


def compile_filter(spec: Mapping[str, Any] | None, column: Any) -> ColumnElement[bool] | None:
    """A boolean SQL expression for `spec` over a JSONB `column`, or None for no filter."""
    if not spec:
        return None
    budget = [MAX_CONDITIONS]
    return _object(spec, column, depth=1, where="filters", budget=budget)


def _object(
    spec: Any, column: Any, *, depth: int, where: str, budget: list[int]
) -> ColumnElement[bool]:
    if depth > MAX_DEPTH:
        raise FilterError(f"{where} nests deeper than {MAX_DEPTH} levels.")
    if not isinstance(spec, Mapping) or not spec:
        raise FilterError(f"{where} must be a non-empty object.")
    clauses: list[ColumnElement[bool]] = []
    for key, value in spec.items():
        here = f"{where}.{key}"
        if key in ("$and", "$or"):
            if not isinstance(value, list) or not value:
                raise FilterError(f"{here} must be a non-empty list of filters.")
            parts = [
                _object(item, column, depth=depth + 1, where=f"{here}[{i}]", budget=budget)
                for i, item in enumerate(value)
            ]
            clauses.append(and_(*parts) if key == "$and" else or_(*parts))
        elif key == "$not":
            clauses.append(not_(_object(value, column, depth=depth + 1, where=here, budget=budget)))
        elif key.startswith("$"):
            raise FilterError(f"{here}: unknown operator {key}.")
        else:
            clauses.append(_field(_path(key, here), value, column, here, budget))
    return clauses[0] if len(clauses) == 1 else and_(*clauses)


def _path(key: str, where: str) -> tuple[str, ...]:
    parts = tuple(key.split("."))
    if len(parts) > 3 or not all(_FIELD.match(part) for part in parts):
        raise FilterError(
            f"{where}: field names use letters, digits, _ and -, nested at most three levels."
        )
    return parts


def _scalar(value: Any, where: str) -> Scalar:
    if isinstance(value, bool | int | float | str) and not (
        isinstance(value, float) and value != value  # NaN never matches anything
    ):
        return value
    raise FilterError(f"{where}: values must be strings, numbers or booleans.")


def _nested(path: tuple[str, ...], value: Any) -> dict[str, Any]:
    nested: Any = value
    for part in reversed(path):
        nested = {part: nested}
    result: dict[str, Any] = nested
    return result


def _field(
    path: tuple[str, ...], value: Any, column: Any, where: str, budget: list[int]
) -> ColumnElement[bool]:
    budget[0] -= 1
    if budget[0] < 0:
        raise FilterError(f"A filter may have at most {MAX_CONDITIONS} conditions.")
    if not isinstance(value, Mapping):
        return _equals(path, _scalar(value, where), column)
    if not value or not all(key in _FIELD_OPERATORS for key in value):
        unknown = sorted(k for k in value if k not in _FIELD_OPERATORS) or ["(empty)"]
        raise FilterError(
            f"{where}: unknown operator {unknown[0]}. Nested fields use dotted names (author.team)."
        )
    clauses = [
        _operator(path, op, operand, column, f"{where}.{op}") for op, operand in value.items()
    ]
    return clauses[0] if len(clauses) == 1 else and_(*clauses)


def _equals(path: tuple[str, ...], value: Scalar, column: Any) -> ColumnElement[bool]:
    contains: ColumnElement[bool] = column.contains(_nested(path, value))
    return contains


def _operator(
    path: tuple[str, ...], op: str, operand: Any, column: Any, where: str
) -> ColumnElement[bool]:
    if op == "$eq":
        return _equals(path, _scalar(operand, where), column)
    if op == "$ne":
        return not_(_equals(path, _scalar(operand, where), column))
    if op in ("$in", "$nin"):
        if not isinstance(operand, list) or not 0 < len(operand) <= MAX_IN_VALUES:
            raise FilterError(f"{where} needs a list of 1 to {MAX_IN_VALUES} values.")
        matches = or_(*[_equals(path, _scalar(item, where), column) for item in operand])
        return matches if op == "$in" else not_(matches)
    if op == "$exists":
        if not isinstance(operand, bool):
            raise FilterError(f"{where} must be true or false.")
        present: ColumnElement[bool] = column[path].is_not(None)
        return present if operand else not_(present)
    if op == "$contains":
        contains: ColumnElement[bool] = column.contains(_nested(path, [_scalar(operand, where)]))
        return contains
    return _compare(path, op, operand, column, where)


def _compare(
    path: tuple[str, ...], op: str, operand: Any, column: Any, where: str
) -> ColumnElement[bool]:
    value = column[path]
    if isinstance(operand, bool) or not isinstance(operand, int | float | str):
        raise FilterError(f"{where} compares numbers or strings (ISO dates sort as strings).")
    # CASE guarantees the cast only runs on numbers; a bare AND would not, and a string such
    # as "beta" would make the whole query fail.
    if isinstance(operand, str):
        typed = case((func.jsonb_typeof(value) == "string", value.astext), else_=None)
    else:
        typed = case((func.jsonb_typeof(value) == "number", value.astext.cast(Numeric)), else_=None)
    match op:
        case "$gt":
            return typed > operand
        case "$gte":
            return typed >= operand
        case "$lt":
            return typed < operand
        case "$lte":
            return typed <= operand
    raise FilterError(f"{where}: unknown comparison.")
