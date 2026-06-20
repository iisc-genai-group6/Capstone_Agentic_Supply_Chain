import logging

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

from app.core.config import Settings

logger = logging.getLogger(__name__)


class QdrantVectorStore:
    """Qdrant-backed vector store for supply chain document retrieval."""

    def __init__(self, client: AsyncQdrantClient, settings: Settings) -> None:
        self._client = client
        self._collection = settings.qdrant_collection

    async def ensure_collection(self, vector_size: int = 1536) -> None:
        collections = await self._client.get_collections()
        names = {c.name for c in collections.collections}
        if self._collection in names:
            return

        logger.info("Creating Qdrant collection: %s", self._collection)
        await self._client.create_collection(
            collection_name=self._collection,
            vectors_config=qmodels.VectorParams(size=vector_size, distance=qmodels.Distance.COSINE),
        )

    async def search(self, query_vector: list[float], limit: int = 5) -> list[dict]:
        results = await self._client.search(
            collection_name=self._collection,
            query_vector=query_vector,
            limit=limit,
        )
        return [{"id": str(hit.id), "score": hit.score, "payload": hit.payload} for hit in results]
