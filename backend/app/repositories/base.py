from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import EntityNotFoundError
from app.models.base import BaseModel

TModel = TypeVar("TModel", bound=BaseModel)


class BaseRepository(Generic[TModel]):
    """Generic async repository implementing CRUD against SQLAlchemy ORM models.

    Concrete repositories implement domain ``IRepository`` ports and delegate
    persistence to this base class with entity/model mappers.
    """

    def __init__(self, session: AsyncSession, model: type[TModel]) -> None:
        self._session = session
        self._model = model

    async def get_by_id(self, entity_id: UUID) -> TModel | None:
        result = await self._session.execute(
            select(self._model).where(self._model.id == entity_id)
        )
        return result.scalar_one_or_none()

    async def get_all(self, *, skip: int = 0, limit: int = 100) -> list[TModel]:
        result = await self._session.execute(
            select(self._model).offset(skip).limit(limit).order_by(self._model.created_at.desc())
        )
        return list(result.scalars().all())

    async def create(self, entity: TModel) -> TModel:
        self._session.add(entity)
        await self._session.flush()
        await self._session.refresh(entity)
        return entity

    async def update(self, entity: TModel) -> TModel:
        merged = await self._session.merge(entity)
        await self._session.flush()
        await self._session.refresh(merged)
        return merged

    async def delete(self, entity_id: UUID) -> bool:
        result = await self._session.execute(
            delete(self._model).where(self._model.id == entity_id)
        )
        return result.rowcount > 0

    async def exists(self, entity_id: UUID) -> bool:
        result = await self._session.execute(
            select(func.count()).select_from(self._model).where(self._model.id == entity_id)
        )
        return (result.scalar_one() or 0) > 0

    async def get_by_id_or_raise(self, entity_id: UUID) -> TModel:
        entity = await self.get_by_id(entity_id)
        if entity is None:
            raise EntityNotFoundError(self._model.__name__, str(entity_id))
        return entity

    async def count(self) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(self._model)
        )
        return result.scalar_one() or 0

    async def filter_by(self, **kwargs: Any) -> list[TModel]:
        result = await self._session.execute(select(self._model).filter_by(**kwargs))
        return list(result.scalars().all())
