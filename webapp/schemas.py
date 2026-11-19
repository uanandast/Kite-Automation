"""Request models accepted by dashboard API endpoints."""

from typing import Any

from pydantic import BaseModel, Field


class IndexRequest(BaseModel):
    index: str


class ShiftRequest(BaseModel):
    legs: list[str | dict[str, Any]]
    shift: int


class ExitLegsRequest(BaseModel):
    legs: list[str | dict[str, Any]]


class RecommendedOrderRequest(BaseModel):
    """Quantity, in exchange units, for the currently displayed recommendation."""

    quantity: int = Field(gt=0)
