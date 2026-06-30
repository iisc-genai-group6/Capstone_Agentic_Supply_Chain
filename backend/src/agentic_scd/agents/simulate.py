from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from agentic_scd.agents.forecast import aggregate_risk
from agentic_scd.agents.schema import Classification, Forecast, ImpactMap, Simulation
from agentic_scd.config import get_settings

if TYPE_CHECKING:
    from agentic_scd.graph.state import GraphState


def run_simulation(classifications: list[Classification], impacts: list[ImpactMap], forecast: Forecast | None = None, iterations: int | None = None) -> Simulation:
    settings = get_settings()
    n = iterations or settings.simulation_iterations
    risk = aggregate_risk(classifications)
    affected = sum(len(item.affected_entities) for item in impacts)
    if risk <= 0 and affected <= 0:
        return Simulation(stockout_probability=0.0, revenue_impact=0.0, recovery_time_days=0.0, service_level=1.0, expected_shortage_units=0.0, iterations=n, assumptions="No active risk or affected network nodes.")
    baseline_demand = float(np.mean(forecast.baseline)) if forecast and forecast.baseline else 900.0
    adjusted_demand = float(np.mean(forecast.adjusted)) if forecast and forecast.adjusted else baseline_demand * (1 - 0.18 * risk)
    rng = np.random.default_rng(42 + int(1000 * risk) + affected)
    lead_time_shift = rng.gamma(shape=2.0 + affected * 0.08, scale=1.5 + risk, size=n)
    demand_noise = rng.normal(loc=max(0.0, baseline_demand - adjusted_demand), scale=max(8.0, baseline_demand * 0.04), size=n)
    available_days = max(1.0, (forecast.inventory_days_left if forecast else 18.0))
    stock_buffer = baseline_demand * available_days / 7.0
    shortage_units = np.maximum(0.0, demand_noise * 5.5 + lead_time_shift * baseline_demand / 6.0 - stock_buffer * (1 - risk * 0.75))
    stockout = float(np.mean(shortage_units > 0))
    revenue_losses = shortage_units * 18.5 * (1.0 + risk)
    p50 = float(np.percentile(revenue_losses, 50))
    p90 = float(np.percentile(revenue_losses, 90))
    recovery = float(np.percentile(lead_time_shift, 80) + 2 + risk * 6)
    service_level = max(0.0, 1.0 - stockout * (0.55 + 0.25 * risk))
    assumptions = f"{n} Monte Carlo runs, aggregate risk {risk:.2f}, affected network nodes {affected}, baseline demand {baseline_demand:.0f}."
    return Simulation(
        stockout_probability=round(stockout, 4),
        revenue_impact=round(float(np.mean(revenue_losses)), 2),
        recovery_time_days=round(recovery, 1),
        service_level=round(service_level, 4),
        expected_shortage_units=round(float(np.mean(shortage_units)), 2),
        iterations=n,
        assumptions=assumptions,
        revenue_loss_p50=round(p50, 2),
        revenue_loss_p90=round(p90, 2),
    )


def simulate_node(state: "GraphState") -> dict:
    simulation = run_simulation(state.get("classifications", []), state.get("impacts", []), state.get("forecast"))
    return {"simulation": simulation}
