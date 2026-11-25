"""Request models accepted by dashboard API endpoints."""

from typing import Any

from pydantic import BaseModel, Field, model_validator


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


class MaxLossRequest(BaseModel):
    """A new max-loss limit, expressed in exactly one unit."""

    loss_percent: float | None = Field(default=None, gt=0, le=100)
    loss_amount: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def exactly_one_limit_is_set(self):
        if (self.loss_percent is None) == (self.loss_amount is None):
            raise ValueError("Provide exactly one of loss_percent or loss_amount")
        return self
