from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from uuid import UUID

from app.domain.entities.base import BaseEntity

TEntity = TypeVar("TEntity", bound=BaseEntity)


class IService(ABC, Generic[TEntity]):
    """Application service port — defines use-case contract."""

    @abstractmethod
    async def get_by_id(self, entity_id: UUID) -> TEntity:
        ...

    @abstractmethod
    async def list(self, *, skip: int = 0, limit: int = 100) -> list[TEntity]:
        ...

    @abstractmethod
    async def create(self, entity: TEntity) -> TEntity:
        ...

    @abstractmethod
    async def update(self, entity: TEntity) -> TEntity:
        ...

    @abstractmethod
    async def delete(self, entity_id: UUID) -> None:
        ...
