from fastapi import APIRouter, Response, status

from app.api.dependencies.services import HealthServiceDep
from app.schemas.health import HealthResponse, HealthStatus

router = APIRouter()


@router.get("/live", response_model=HealthResponse)
async def liveness(health_service: HealthServiceDep) -> HealthResponse:
    """Kubernetes liveness probe — confirms the process is running."""
    return await health_service.check_liveness()


@router.get("/ready", response_model=HealthResponse)
async def readiness(
    health_service: HealthServiceDep,
    response: Response,
) -> HealthResponse:
    """Kubernetes readiness probe — confirms dependencies are reachable."""
    result = await health_service.check_readiness()
    if result.status == HealthStatus.UNHEALTHY:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
