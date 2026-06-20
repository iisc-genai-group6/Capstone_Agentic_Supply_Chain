from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from uuid import UUID

from app.domain.entities.base import BaseEntity

TEntity = TypeVar("TEntity", bound=BaseEntity)


class IRepository(ABC, Generic[TEntity]):
    """Repository port — defines persistence contract for domain entities."""

    @abstractmethod
    async def get_by_id(self, entity_id: UUID) -> TEntity | None:
        ...

    @abstractmethod
    async def get_all(self, *, skip: int = 0, limit: int = 100) -> list[TEntity]:
        ...

    @abstractmethod
    async def create(self, entity: TEntity) -> TEntity:
        ...

    @abstractmethod
    async def update(self, entity: TEntity) -> TEntity:
        ...

    @abstractmethod
    async def delete(self, entity_id: UUID) -> bool:
        ...

    @abstractmethod
    async def exists(self, entity_id: UUID) -> bool:
        ...
