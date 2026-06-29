from __future__ import annotations

from typing import TypedDict

from agentic_scd.agents.schema import Classification, EventAnalysis, Forecast, ImpactMap, Recommendation, Simulation
from agentic_scd.ingestion.schema import DisruptionSignal


class GraphState(TypedDict, total=False):
    new_signals: list[DisruptionSignal]
    event_analyses: list[EventAnalysis]
    classifications: list[Classification]
    impacts: list[ImpactMap]
    forecast: Forecast
    simulation: Simulation
    recommendation: Recommendation
    route: str
    scenario_name: str
    run_id: str
