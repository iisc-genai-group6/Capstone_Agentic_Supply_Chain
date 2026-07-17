from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from agentic_scd.agents.forecast_engine import adjusted_projection, baseline_projection, freight_pressure
from agentic_scd.agents.schema import Classification, Forecast, ImpactMap
from agentic_scd.ingestion.paths import SEED_DIR
from agentic_scd.rag.retriever import forecast_retriever

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


def forecast_context(classifications: list[Classification], impacts: list[ImpactMap]) -> tuple[list[str], float]:
    if not classifications and not impacts:
        return [], 0.0
    query_parts = [item.category for item in classifications]
    for impact in impacts:
        query_parts.extend(impact.affected_lanes[:2])
        query_parts.extend(impact.product_categories[:2])
    docs = forecast_retriever().search(" ".join(query_parts), top_k=4)
    rows: list[str] = []
    pressure = 0.0
    for doc in docs:
        label = (
            doc.metadata.get("title")
            or doc.metadata.get("name")
            or doc.metadata.get("lane")
            or doc.doc_id
        )
        rows.append(f"{label}: {doc.text}")
        kind = str(doc.metadata.get("kind", ""))
        if kind == "freight_rate":
            pressure += 0.018
        elif kind in {"demand_history", "dataset_history", "runtime_signal"}:
            pressure += 0.01
    return rows[:4], round(min(0.08, pressure), 4)


def build_forecast(classifications: list[Classification], impacts: list[ImpactMap]) -> Forecast:
    risk = aggregate_risk(classifications)
    # Dominant category — pick the highest-severity classification's category
    # so the demand curve shape reflects the disruption type, not just risk score.
    dominant_category = ""
    if classifications:
        top = max(classifications, key=lambda c: c.severity)
        dominant_category = top.category or ""
    baseline, baseline_source, model_name = baseline_projection(HORIZON)
    freight_delta, freight_source = freight_pressure()
    retrieved_context, context_pressure = forecast_context(classifications, impacts)
    adjusted, disruption_factor = adjusted_projection(baseline, risk, len(impacts), freight_delta + context_pressure, dominant_category)
    dates = [(date.today() + timedelta(days=7 * idx)).isoformat() for idx in range(HORIZON)]
    deviation = 0.0 if not baseline else round(100 * (sum(adjusted) - sum(baseline)) / sum(baseline), 2)
    mean_adjusted = float(np.mean(adjusted)) if adjusted else 0.0
    mean_baseline = float(np.mean(baseline)) if baseline else 1.0
    inventory_days = round(max(1.0, 26 * (1 - risk) + 4), 1)
    delay = round(max(0.0, risk * 12 + len(impacts) * 0.7 + max(0.0, freight_delta) * 18), 1)
    mape = round(abs(mean_baseline - mean_adjusted) / max(mean_baseline, 1.0), 4)
    if baseline_source == "database":
        note = f"Baseline source: persisted DATASET history in the configured database, adjusted by aggregate risk {risk:.2f}."
    elif baseline_source == "seed_csv":
        note = f"Baseline source: packaged supply-chain CSV baseline, adjusted by aggregate risk {risk:.2f}."
    else:
        note = f"Baseline source: synthetic fallback baseline, adjusted by aggregate risk {risk:.2f}."
    note = (
        f"{note} Forecast engine: {model_name}. Freight pressure source: "
        f"{freight_source} ({freight_delta:+.1%}). Retrieved context pressure: "
        f"{context_pressure:+.1%} from {len(retrieved_context)} local records."
    )
    return Forecast(
        dates=dates,
        baseline=baseline,
        adjusted=adjusted,
        demand_deviation_pct=deviation,
        inventory_days_left=inventory_days,
        predicted_delay_days=delay,
        mape_estimate=mape,
        note=note,
        model_name=model_name,
        freight_pressure_pct=round((freight_delta + context_pressure) * 100.0, 2),
        retrieved_context=retrieved_context,
    )


def forecast_node(state: "GraphState") -> dict:
    return {"forecast": build_forecast(state.get("classifications", []), state.get("impacts", []))}
