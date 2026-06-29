from __future__ import annotations

import re
from typing import TYPE_CHECKING

from agentic_scd.agents.schema import EventAnalysis
from agentic_scd.ingestion.schema import DisruptionSignal

if TYPE_CHECKING:
    from agentic_scd.graph.state import GraphState

ENTITY_RE = re.compile(r"\b[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3}\b")


def analyze_signal(signal: DisruptionSignal) -> EventAnalysis:
    text = signal.text
    entities = []
    for match in ENTITY_RE.findall(text):
        if match not in entities and len(match) > 2:
            entities.append(match)
    hint = signal.severity_hint or "none"
    event_type = "supply_chain_signal"
    lowered = text.lower()
    if any(term in lowered for term in ("typhoon", "storm", "flood", "weather", "earthquake")):
        event_type = "weather_disruption"
    elif any(term in lowered for term in ("strike", "union", "walkout")):
        event_type = "labor_disruption"
    elif any(term in lowered for term in ("tariff", "sanction", "embargo")):
        event_type = "geopolitical_disruption"
    elif any(term in lowered for term in ("defect", "inspection", "recall")):
        event_type = "quality_disruption"
    elif any(term in lowered for term in ("port", "freight", "shipping", "congestion", "delay")):
        event_type = "logistics_disruption"
    return EventAnalysis(
        signal_id=signal.signal_id,
        event_type=event_type,
        entities=entities[:8],
        extracted_region=signal.region,
        severity_hint=str(hint),
        summary=f"{signal.title}. {signal.raw_text[:180]}".strip(),
    )


def news_node(state: "GraphState") -> dict:
    return {"event_analyses": [analyze_signal(signal) for signal in state.get("new_signals", [])]}
