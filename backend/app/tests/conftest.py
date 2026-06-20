import pytest
from httpx import ASGITransport, AsyncClient

from app.core.container import create_container, lifespan_container
from app.main import create_app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncClient:
    app = create_app()
    container = create_container()
    app.state.container = container

    async with lifespan_container(container):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
