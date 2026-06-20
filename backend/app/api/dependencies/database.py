from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import Container
from app.db.session import DatabaseSessionManager


def _get_container(request: Request) -> Container:
    return request.app.state.container


async def get_db_session(
    request: Request,
) -> AsyncGenerator[AsyncSession, None]:
    session_manager: DatabaseSessionManager = _get_container(request).db_session_manager()
    async with session_manager.session() as session:
        yield session


DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]
