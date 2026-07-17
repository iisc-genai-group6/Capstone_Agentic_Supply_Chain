from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from agentic_scd.agents.schema import EventAnalysis
from agentic_scd.config import get_settings
from agentic_scd.ingestion.schema import DisruptionSignal
from agentic_scd.llm.client import completion
from agentic_scd.rag.retriever import news_retriever

if TYPE_CHECKING:
    from agentic_scd.graph.state import GraphState

ENTITY_RE = re.compile(r"\b[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3}\b")
CATEGORY_EVENT_TYPES = {
    "weather": "weather_disruption",
    "logistics": "logistics_disruption",
    "labor": "labor_disruption",
    "labor_strike": "labor_disruption",
    "policy": "geopolitical_disruption",
    "geopolitical": "geopolitical_disruption",
    "quality": "quality_disruption",
    "raw_material": "supply_shortage_disruption",
    "demand_shock": "demand_disruption",
}


def related_context(signal: DisruptionSignal) -> tuple[list[str], str]:
    query = " ".join(part for part in (signal.title, signal.raw_text, signal.region or "") if part)
    docs = news_retriever().search(query, top_k=3)
    rows: list[str] = []
    categories: list[str] = []
    for doc in docs:
        label = (
            doc.metadata.get("title")
            or doc.metadata.get("name")
            or doc.metadata.get("lane")
            or doc.doc_id
        )
        rows.append(f"{label}: {doc.text}")
        category = str(doc.metadata.get("category", "")).strip().lower()
        if category:
            categories.append(category)
    for category in categories:
        if category in CATEGORY_EVENT_TYPES:
            return rows, CATEGORY_EVENT_TYPES[category]
    return rows, ""


def heuristic_analysis(signal: DisruptionSignal, retrieved_context: list[str] | None = None, retrieved_event_type: str = "") -> EventAnalysis:
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
    elif retrieved_event_type:
        event_type = retrieved_event_type
    return EventAnalysis(
        signal_id=signal.signal_id,
        event_type=event_type,
        entities=entities[:8],
        extracted_region=signal.region,
        severity_hint=str(hint),
        summary=f"{signal.title}. {signal.raw_text[:180]}".strip(),
        retrieved_context=list(retrieved_context or [])[:3],
    )


def llm_analysis(signal: DisruptionSignal, retrieved_context: list[str] | None = None) -> EventAnalysis | None:
    settings = get_settings()
    if settings.llm_is_mock:
        return None
    prompt = json.dumps(
        {
            "title": signal.title,
            "body": signal.raw_text,
            "region": signal.region,
            "severity_hint": signal.severity_hint,
            "retrieved_context": list(retrieved_context or [])[:3],
        },
        ensure_ascii=False,
    )
    system = "Return JSON only with keys event_type, entities, extracted_region, severity_hint, summary."
    try:
        raw = completion(prompt, system=system, settings=settings, temperature=0)
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return None
        data = json.loads(raw[start : end + 1])
    except Exception:
        return None
    entities: list[str] = []
    for item in data.get("entities", []):
        value = " ".join(str(item).split())
        if value and value not in entities:
            entities.append(value)
    region = data.get("extracted_region") or signal.region
    summary = " ".join(str(data.get("summary") or "").split()) or f"{signal.title}. {signal.raw_text[:180]}".strip()
    event_type = " ".join(str(data.get("event_type") or "supply_chain_signal").split()) or "supply_chain_signal"
    severity_hint = " ".join(str(data.get("severity_hint") or signal.severity_hint or "none").split()) or "none"
    return EventAnalysis(
        signal_id=signal.signal_id,
        event_type=event_type,
        entities=entities[:8],
        extracted_region=str(region) if region else None,
        severity_hint=severity_hint,
        summary=summary,
        retrieved_context=list(retrieved_context or [])[:3],
    )


def analyze_signal(signal: DisruptionSignal) -> EventAnalysis:
    retrieved_context, retrieved_event_type = related_context(signal)
    return llm_analysis(signal, retrieved_context) or heuristic_analysis(signal, retrieved_context, retrieved_event_type)


def news_node(state: "GraphState") -> dict:
    return {"event_analyses": [analyze_signal(signal) for signal in state.get("new_signals", [])]}
