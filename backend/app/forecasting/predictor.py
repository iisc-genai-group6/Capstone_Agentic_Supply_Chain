import logging
from typing import Any

logger = logging.getLogger(__name__)


class DisruptionPredictor:
    """Statistical / ML forecasting for supply chain disruptions."""

    async def predict(self, features: dict[str, Any]) -> dict[str, Any]:
        logger.info("DisruptionPredictor.predict invoked")
        return {
            "probability": 0.0,
            "horizon_days": features.get("horizon_days", 30),
            "drivers": [],
        }
