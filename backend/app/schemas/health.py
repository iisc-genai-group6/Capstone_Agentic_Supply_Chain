from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"


class ComponentHealth(BaseModel):
    name: str
    status: HealthStatus
    latency_ms: float = Field(ge=0)
    detail: str | None = None


class HealthResponse(BaseModel):
    status: HealthStatus
    timestamp: datetime
    components: list[ComponentHealth]
