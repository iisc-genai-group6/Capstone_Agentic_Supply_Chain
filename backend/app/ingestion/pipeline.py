import logging
from typing import Any

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """ETL pipeline for supplier, logistics, and market data ingestion."""

    async def ingest(self, source: str, payload: dict[str, Any]) -> dict[str, Any]:
        logger.info("IngestionPipeline.ingest from source=%s", source)
        return {"source": source, "records_processed": 0, "status": "accepted"}
