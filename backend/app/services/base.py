from typing import Generic, TypeVar
from uuid import UUID

from app.domain.entities.base import BaseEntity
from app.domain.exceptions import EntityNotFoundError
from app.domain.interfaces.repositories import IRepository
from app.domain.interfaces.services import IService

TEntity = TypeVar("TEntity", bound=BaseEntity)


class BaseService(IService[TEntity], Generic[TEntity]):
    """Base application service delegating persistence to a repository."""

    def __init__(self, repository: IRepository[TEntity]) -> None:
        self._repository = repository

    async def get_by_id(self, entity_id: UUID) -> TEntity:
        entity = await self._repository.get_by_id(entity_id)
        if entity is None:
            raise EntityNotFoundError(self.__class__.__name__, str(entity_id))
        return entity

    async def list(self, *, skip: int = 0, limit: int = 100) -> list[TEntity]:
        return await self._repository.get_all(skip=skip, limit=limit)

    async def create(self, entity: TEntity) -> TEntity:
        return await self._repository.create(entity)

    async def update(self, entity: TEntity) -> TEntity:
        if not await self._repository.exists(entity.id):
            raise EntityNotFoundError(self.__class__.__name__, str(entity.id))
        entity.touch()
        return await self._repository.update(entity)

    async def delete(self, entity_id: UUID) -> None:
        deleted = await self._repository.delete(entity_id)
        if not deleted:
            raise EntityNotFoundError(self.__class__.__name__, str(entity_id))
