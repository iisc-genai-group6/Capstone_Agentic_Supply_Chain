from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper."""

    items: list[T]
    total: int
    skip: int = Field(ge=0)
    limit: int = Field(ge=1, le=1000)


class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str
    code: str | None = None
    field: str | None = None
