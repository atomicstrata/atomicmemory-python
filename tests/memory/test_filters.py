"""Tests for FilterExpr recursive types."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from atomicmemory.memory.filters import FieldFilter, FilterExpr


def test_field_filter_basic() -> None:
    expr = FilterExpr.model_validate({"field": "kind", "op": "eq", "value": "fact"})

    inner = expr.root
    assert isinstance(inner, FieldFilter)
    assert inner.field == "kind"
    assert inner.op == "eq"
    assert inner.value == "fact"


def test_and_combinator() -> None:
    expr = FilterExpr.model_validate(
        {
            "and": [
                {"field": "kind", "op": "eq", "value": "fact"},
                {"field": "score", "op": "gte", "value": 0.5},
            ]
        }
    )

    assert hasattr(expr.root, "and_")


def test_not_combinator_wraps_expression() -> None:
    expr = FilterExpr.model_validate({"not": {"field": "kind", "op": "eq", "value": "fact"}})

    assert hasattr(expr.root, "not_")


def test_field_filter_rejects_unknown_op() -> None:
    with pytest.raises(ValidationError):
        FieldFilter.model_validate({"field": "x", "op": "bogus", "value": 1})


def test_or_combinator_can_nest() -> None:
    expr = FilterExpr.model_validate(
        {
            "or": [
                {"field": "a", "op": "eq", "value": 1},
                {"and": [{"field": "b", "op": "gt", "value": 2}, {"field": "c", "op": "lt", "value": 3}]},
            ]
        }
    )

    assert hasattr(expr.root, "or_")
