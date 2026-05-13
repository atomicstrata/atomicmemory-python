"""Recursive filter expression types.

Port of `atomicmemory-sdk/src/memory/types.ts:149-168`. `FilterExpr` is a
recursive discriminated union of and/or/not nodes plus a leaf
`FieldFilter`. We model it as a `RootModel` so consumers can construct
expressions ergonomically from dicts or by hand.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel

FieldFilterOp = Literal[
    "eq",
    "neq",
    "gt",
    "gte",
    "lt",
    "lte",
    "in",
    "contains",
    "exists",
]

FieldFilterValue = str | int | float | bool | datetime | list[str | int | float] | None


class FieldFilter(BaseModel):
    """Leaf filter on a single record field."""

    model_config = ConfigDict(extra="forbid")

    field: str
    op: FieldFilterOp
    value: FieldFilterValue = None


class FilterAnd(BaseModel):
    model_config = ConfigDict(extra="forbid")
    and_: list[FilterExpr] = Field(alias="and")


class FilterOr(BaseModel):
    model_config = ConfigDict(extra="forbid")
    or_: list[FilterExpr] = Field(alias="or")


class FilterNot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    not_: FilterExpr = Field(alias="not")


FilterExprNode = Annotated[
    FilterAnd | FilterOr | FilterNot | FieldFilter,
    Field(union_mode="left_to_right"),
]


class FilterExpr(RootModel[FilterExprNode]):
    """A composable filter expression over memory metadata fields."""


FilterAnd.model_rebuild()
FilterOr.model_rebuild()
FilterNot.model_rebuild()
