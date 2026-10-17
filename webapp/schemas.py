"""Request models accepted by dashboard API endpoints."""

from typing import Any

from pydantic import BaseModel


class IndexRequest(BaseModel):
    index: str


class ShiftRequest(BaseModel):
    legs: list[str | dict[str, Any]]
    shift: int


class ExitLegsRequest(BaseModel):
    legs: list[str | dict[str, Any]]
