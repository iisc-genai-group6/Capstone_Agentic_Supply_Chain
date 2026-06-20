from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dependency_injector import containers, providers
from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings
from app.db.session import DatabaseSessionManager
from app.services.health_service import HealthService


class Container(containers.DeclarativeContainer):
    """Application dependency injection container."""

    wiring_config = containers.WiringConfiguration(
        modules=[
            "app.main",
        ]
    )

    config: providers.Singleton[Settings] = providers.Singleton(get_settings)

    # PostgreSQL
    db_engine = providers.Singleton(
        create_async_engine,
        config.provided.postgres_dsn,
        pool_size=config.provided.postgres_pool_size,
        max_overflow=config.provided.postgres_max_overflow,
        pool_pre_ping=True,
        echo=config.provided.app_debug,
    )

    db_session_factory = providers.Singleton(
        async_sessionmaker,
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    db_session_manager = providers.Singleton(
        DatabaseSessionManager,
        session_factory=db_session_factory,
    )

    # Redis
    redis_client = providers.Singleton(
        Redis.from_url,
        config.provided.redis_dsn,
        decode_responses=True,
    )

    # Qdrant
    qdrant_client = providers.Singleton(
        AsyncQdrantClient,
        host=config.provided.qdrant_host,
        port=config.provided.qdrant_port,
        grpc_port=config.provided.qdrant_grpc_port,
        api_key=config.provided.qdrant_api_key,
        prefer_grpc=False,
        check_compatibility=False,
    )

    # Services
    health_service = providers.Factory(
        HealthService,
        db_session_manager=db_session_manager,
        redis_client=redis_client,
        qdrant_client=qdrant_client,
    )


def create_container() -> Container:
    container = Container()
    return container


@asynccontextmanager
async def lifespan_container(container: Container) -> AsyncGenerator[Container, None]:
    """Manage container lifecycle: wire dependencies and shutdown resources."""
    container.wire()

    db_engine = container.db_engine()
    redis = container.redis_client()
    qdrant = container.qdrant_client()

    yield container

    await qdrant.close()
    await redis.aclose()
    await db_engine.dispose()
    container.unwire()
