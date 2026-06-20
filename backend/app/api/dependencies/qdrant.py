from typing import Annotated

from fastapi import Depends, Request
from qdrant_client import AsyncQdrantClient


def get_qdrant_client(request: Request) -> AsyncQdrantClient:
    return request.app.state.container.qdrant_client()


QdrantDep = Annotated[AsyncQdrantClient, Depends(get_qdrant_client)]
