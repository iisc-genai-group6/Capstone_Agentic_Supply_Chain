"""Weather Risk Monitoring agent (README agent #3).

Runs between ``news`` and ``classify``. For each freshly ingested ``WEATHER`` signal it
parses the packaged Open-Meteo forecast into a multi-day series and scores hub-level
disruption risk, emitting ``WeatherRiskAssessment`` objects the classifier and impact
mapper can lean on. Fully offline: it reads the structured payload the connector already
persisted, never re-fetching during the pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agentic_scd.agents.schema import WeatherRiskAssessment
from agentic_scd.ingestion.schema import DisruptionSignal
from agentic_scd.ingestion.weather.core import (
    operations_at_risk,
    parse_daily_series,
    peak_day,
    score_hub_risk,
    summarize_hub_forecast,
)
from agentic_scd.rag.retriever import weather_retriever

if TYPE_CHECKING:
    from agentic_scd.graph.state import GraphState


def _hub_from_signal(signal: DisruptionSignal) -> dict[str, Any]:
    payload = signal.raw_payload or {}
    hub = payload.get("hub")
    if isinstance(hub, dict) and hub:
        return hub
    location = signal.location
    if location is not None:
        return {
            "hub_port": location.hub_port,
            "region": location.region,
            "lat": location.lat,
            "lon": location.lon,
        }
    return {}


def _retrieved_hub_context(hub: dict[str, Any]) -> tuple[list[str], list[str]]:
    query = " ".join(
        part
        for part in (
            str(hub.get("hub_port") or ""),
            str(hub.get("region") or ""),
            "port lane warehouse facility operations weather disruption",
        )
        if part
    )
    docs = weather_retriever().search(query, top_k=3)
    rows: list[str] = []
    ops: list[str] = []
    for doc in docs:
        label = (
            doc.metadata.get("name")
            or doc.metadata.get("title")
            or doc.metadata.get("lane")
            or doc.doc_id
        )
        rows.append(f"{label}: {doc.text}")
        kind = str(doc.metadata.get("kind", ""))
        if kind == "lanes":
            ops.append("ocean_freight")
        elif kind == "facilities":
            ops.append("warehouse_operations")
        elif kind == "suppliers":
            ops.append("supplier_inbound")
    return rows, list(dict.fromkeys(ops))


def assess_weather_signal(signal: DisruptionSignal) -> WeatherRiskAssessment | None:
    """Build a hub-level risk assessment for one WEATHER signal, or None otherwise."""
    if signal.source_type != "WEATHER":
        return None
    payload = signal.raw_payload or {}
    response = payload.get("response")
    if not isinstance(response, dict):
        return None
    hub = _hub_from_signal(signal)
    days = parse_daily_series(hub, response)
    aggregate = score_hub_risk(days)
    peak = peak_day(days)
    retrieved_context, contextual_operations = _retrieved_hub_context(hub)
    port_risk = round(min(1.0, max(0.0, (aggregate - 1.0) / 9.0)), 4)
    return WeatherRiskAssessment(
        signal_id=signal.signal_id,
        hub_port=hub.get("hub_port"),
        region=hub.get("region"),
        lat=hub.get("lat"),
        lon=hub.get("lon"),
        horizon_days=len(days),
        daily_forecasts=days,
        aggregate_severity=aggregate,
        port_disruption_risk=port_risk,
        affected_operations=list(
            dict.fromkeys(operations_at_risk(days, hub) + contextual_operations)
        ),
        peak_day=peak.date if peak else None,
        summary=summarize_hub_forecast(hub, days),
        retrieved_context=retrieved_context[:3],
    )


def weather_node(state: "GraphState") -> dict:
    assessments = [assess_weather_signal(signal) for signal in state.get("new_signals", [])]
    return {"weather_risks": [item for item in assessments if item is not None]}
