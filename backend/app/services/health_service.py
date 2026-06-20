import logging
from datetime import UTC, datetime

from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis

from app.db.session import DatabaseSessionManager
from app.schemas.health import ComponentHealth, HealthResponse, HealthStatus

logger = logging.getLogger(__name__)


class HealthService:
    """Aggregates health checks across infrastructure dependencies."""

    def __init__(
        self,
        db_session_manager: DatabaseSessionManager,
        redis_client: Redis,
        qdrant_client: AsyncQdrantClient,
    ) -> None:
        self._db = db_session_manager
        self._redis = redis_client
        self._qdrant = qdrant_client

    async def check_liveness(self) -> HealthResponse:
        return HealthResponse(
            status=HealthStatus.HEALTHY,
            timestamp=datetime.now(UTC),
            components=[
                ComponentHealth(name="api", status=HealthStatus.HEALTHY, latency_ms=0.0),
            ],
        )

    async def check_readiness(self) -> HealthResponse:
        components: list[ComponentHealth] = []
        overall = HealthStatus.HEALTHY

        for name, checker in [
            ("postgres", self._check_postgres),
            ("redis", self._check_redis),
            ("qdrant", self._check_qdrant),
        ]:
            component = await checker()
            components.append(component)
            if component.status == HealthStatus.UNHEALTHY:
                overall = HealthStatus.UNHEALTHY
            elif component.status == HealthStatus.DEGRADED and overall == HealthStatus.HEALTHY:
                overall = HealthStatus.DEGRADED

        return HealthResponse(
            status=overall,
            timestamp=datetime.now(UTC),
            components=components,
        )

    async def _check_postgres(self) -> ComponentHealth:
        import time

        start = time.perf_counter()
        try:
            await self._db.ping()
            latency = (time.perf_counter() - start) * 1000
            return ComponentHealth(name="postgres", status=HealthStatus.HEALTHY, latency_ms=latency)
        except Exception as exc:
            logger.exception("Postgres health check failed")
            return ComponentHealth(
                name="postgres",
                status=HealthStatus.UNHEALTHY,
                latency_ms=(time.perf_counter() - start) * 1000,
                detail=str(exc),
            )

    async def _check_redis(self) -> ComponentHealth:
        import time

        start = time.perf_counter()
        try:
            pong = await self._redis.ping()
            latency = (time.perf_counter() - start) * 1000
            status = HealthStatus.HEALTHY if pong else HealthStatus.UNHEALTHY
            return ComponentHealth(name="redis", status=status, latency_ms=latency)
        except Exception as exc:
            logger.exception("Redis health check failed")
            return ComponentHealth(
                name="redis",
                status=HealthStatus.UNHEALTHY,
                latency_ms=(time.perf_counter() - start) * 1000,
                detail=str(exc),
            )

    async def _check_qdrant(self) -> ComponentHealth:
        import time

        start = time.perf_counter()
        try:
            await self._qdrant.get_collections()
            latency = (time.perf_counter() - start) * 1000
            return ComponentHealth(name="qdrant", status=HealthStatus.HEALTHY, latency_ms=latency)
        except Exception as exc:
            logger.exception("Qdrant health check failed")
            return ComponentHealth(
                name="qdrant",
                status=HealthStatus.UNHEALTHY,
                latency_ms=(time.perf_counter() - start) * 1000,
                detail=str(exc),
            )
