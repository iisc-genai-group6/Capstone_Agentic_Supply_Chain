import logging
from typing import Any

logger = logging.getLogger(__name__)


class ScenarioSimulator:
    """Monte Carlo / discrete-event simulation for disruption scenarios."""

    async def simulate(self, scenario: dict[str, Any]) -> dict[str, Any]:
        logger.info("ScenarioSimulator.simulate invoked")
        return {
            "scenario_id": scenario.get("id"),
            "impact_score": 0.0,
            "affected_nodes": [],
        }
