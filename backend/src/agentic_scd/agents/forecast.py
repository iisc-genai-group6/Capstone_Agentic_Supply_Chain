from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from agentic_scd.agents.schema import Classification, Forecast, ImpactMap
from agentic_scd.ingestion.paths import SEED_DIR

if TYPE_CHECKING:
    from agentic_scd.graph.state import GraphState

HORIZON = 8


def aggregate_risk(classifications: list[Classification]) -> float:
    if not classifications:
        return 0.0
    return round(float(np.mean([item.risk_score for item in classifications])), 4)


def baseline_from_dataset(path: Path | None = None) -> list[float]:
    csv_path = path or SEED_DIR / "supply_chain_dataset.csv"
    if not csv_path.exists():
        return [1000.0 + 35 * idx for idx in range(HORIZON)]
    values: list[float] = []
    with csv_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                demand = float(row.get("Number of products sold", 0))
                stock = float(row.get("Stock levels", 0))
                values.append(max(10.0, demand + 0.35 * stock))
            except ValueError:
                continue
    if not values:
        return [1000.0 + 35 * idx for idx in range(HORIZON)]
    chunks = np.array_split(np.array(values, dtype=float), HORIZON)
    baseline = [float(np.mean(chunk)) for chunk in chunks]
    trend = np.polyfit(np.arange(len(baseline)), baseline, 1)[0] if len(baseline) > 1 else 0.0
    return [round(max(10.0, baseline[idx] + 0.25 * trend * idx), 2) for idx in range(HORIZON)]


def build_forecast(classifications: list[Classification], impacts: list[ImpactMap]) -> Forecast:
    risk = aggregate_risk(classifications)
    baseline = baseline_from_dataset()
    disruption_factor = min(0.55, risk * (0.18 + 0.025 * len(impacts)))
    adjusted = [round(value * (1 - disruption_factor * ((idx + 1) / HORIZON)), 2) for idx, value in enumerate(baseline)]
    dates = [(date.today() + timedelta(days=7 * idx)).isoformat() for idx in range(HORIZON)]
    deviation = 0.0 if not baseline else round(100 * (sum(adjusted) - sum(baseline)) / sum(baseline), 2)
    mean_adjusted = float(np.mean(adjusted)) if adjusted else 0.0
    mean_baseline = float(np.mean(baseline)) if baseline else 1.0
    inventory_days = round(max(1.0, 26 * (1 - risk) + 4), 1)
    delay = round(max(0.0, risk * 12 + len(impacts) * 0.7), 1)
    mape = round(abs(mean_baseline - mean_adjusted) / max(mean_baseline, 1.0), 4)
    return Forecast(dates=dates, baseline=baseline, adjusted=adjusted, demand_deviation_pct=deviation, inventory_days_left=inventory_days, predicted_delay_days=delay, mape_estimate=mape, note=f"Offline baseline from the packaged supply-chain dataset, adjusted by aggregate risk {risk:.2f}.")


def forecast_node(state: "GraphState") -> dict:
    return {"forecast": build_forecast(state.get("classifications", []), state.get("impacts", []))}
