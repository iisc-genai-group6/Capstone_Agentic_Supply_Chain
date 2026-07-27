from __future__ import annotations

from typing import TYPE_CHECKING

from agentic_scd.agents.sim_engine import run_discrete_event
from agentic_scd.agents.forecast import aggregate_risk
from agentic_scd.agents.schema import Classification, Forecast, ImpactMap, Simulation
from agentic_scd.config import get_settings
from agentic_scd.rag.retriever import simulation_retriever

if TYPE_CHECKING:
    from agentic_scd.graph.state import GraphState


def simulation_context(
    classifications: list[Classification], impacts: list[ImpactMap], forecast: Forecast | None
) -> tuple[list[str], float]:
    if not classifications and not impacts:
        return [], 1.0
    query_parts = [item.category for item in classifications]
    for impact in impacts:
        query_parts.extend(impact.affected_entities[:3])
    if forecast is not None:
        query_parts.append(forecast.note)
    docs = simulation_retriever().search(" ".join(query_parts), top_k=4)
    rows: list[str] = []
    multiplier = 1.0
    for doc in docs:
        label = (
            doc.metadata.get("title")
            or doc.metadata.get("name")
            or doc.metadata.get("lane")
            or doc.doc_id
        )
        rows.append(f"{label}: {doc.text}")
        kind = str(doc.metadata.get("kind", ""))
        if kind in {"dataset_history", "history", "runtime_signal"}:
            multiplier += 0.025
        elif kind in {"lanes", "facilities", "suppliers"}:
            multiplier += 0.015
    return rows[:4], round(min(1.12, multiplier), 4)


def run_simulation(classifications: list[Classification], impacts: list[ImpactMap], forecast: Forecast | None = None, iterations: int | None = None, overrides: dict | None = None) -> Simulation:
    settings = get_settings()
    n = iterations or settings.simulation_iterations
    risk = aggregate_risk(classifications)
    affected = sum(len(item.affected_entities) for item in impacts)
    if risk <= 0 and affected <= 0:
        return Simulation(stockout_probability=0.0, revenue_impact=0.0, recovery_time_days=0.0, service_level=1.0, expected_shortage_units=0.0, iterations=n, assumptions="No active risk or affected network nodes.", engine="discrete_event_local")
    retrieved_context, calibration = simulation_context(classifications, impacts, forecast)
    data = run_discrete_event(classifications, impacts, forecast, n, overrides)
    stockout_probability = min(1.0, float(data["stockout_probability"]) * min(1.05, calibration))
    revenue_impact = float(data["revenue_impact"]) * calibration
    recovery_time_days = float(data["recovery_time_days"]) * (1.0 + max(0.0, calibration - 1.0) * 0.6)
    expected_shortage_units = float(data["expected_shortage_units"]) * calibration
    assumptions = str(data["assumptions"])
    if retrieved_context:
        assumptions = f"{assumptions} Retrieved {len(retrieved_context)} similar local records for calibration."
    return Simulation(
        stockout_probability=round(stockout_probability, 4),
        revenue_impact=round(revenue_impact, 2),
        recovery_time_days=round(recovery_time_days, 1),
        service_level=float(data["service_level"]),
        expected_shortage_units=round(expected_shortage_units, 2),
        iterations=int(data["iterations"]),
        assumptions=assumptions,
        revenue_loss_p50=float(data["revenue_loss_p50"]),
        revenue_loss_p90=float(data["revenue_loss_p90"]),
        engine=str(data["engine"]),
        retrieved_context=retrieved_context,
    )


def simulate_node(state: "GraphState") -> dict:
    simulation = run_simulation(state.get("classifications", []), state.get("impacts", []), state.get("forecast"))
    return {"simulation": simulation}
