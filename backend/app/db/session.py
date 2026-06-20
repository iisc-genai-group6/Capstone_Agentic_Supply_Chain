from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class DatabaseSessionManager:
    """Manages async database sessions with explicit transaction boundaries."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        session = self._session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    @asynccontextmanager
    async def session_readonly(self) -> AsyncGenerator[AsyncSession, None]:
        session = self._session_factory()
        try:
            yield session
        finally:
            await session.close()

    async def ping(self) -> bool:
        from sqlalchemy import text

        async with self.session_readonly() as session:
            await session.execute(text("SELECT 1"))
        return True


async def get_session(
    session_manager: DatabaseSessionManager,
) -> AsyncGenerator[AsyncSession, None]:
    async with session_manager.session() as session:
        yield session
