from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from agentic_scd.agents.schema import Classification, ImpactMap
from agentic_scd.ingestion.schema import DisruptionSignal
from agentic_scd.rag.retriever import impact_retriever

if TYPE_CHECKING:
    from agentic_scd.graph.state import GraphState

CATEGORY_HINTS = {
    "weather": ["port", "warehouse", "Sea"],
    "natural_disaster": ["Taiwan", "chip", "supplier"],
    "labor": ["port", "warehouse"],
    "labor_strike": ["port", "warehouse"],
    "logistics": ["lane", "Sea", "port"],
    "policy": ["supplier", "lane", "tariff"],
    "geopolitical": ["supplier", "lane"],
    "raw_material": ["supplier", "products"],
    "quality": ["supplier", "products"],
    "demand_shock": ["warehouse", "products"],
}


def default_impact(classification: Classification) -> ImpactMap:
    category = classification.category
    if category in {"natural_disaster", "weather"}:
        suppliers = ["Taiwan chip supplier"] if category == "natural_disaster" else ["Supplier A"]
        lanes = ["Taiwan-US West"] if category == "natural_disaster" else ["Shanghai-Los Angeles"]
        facilities = ["Assembly Plant 3"] if category == "natural_disaster" else ["Los Angeles Import DC"]
    elif category in {"logistics", "labor", "labor_strike"}:
        suppliers = ["Supplier A"]
        lanes = ["Shanghai-Los Angeles"]
        facilities = ["Los Angeles Import DC"]
    else:
        suppliers = ["Supplier B"]
        lanes = ["Mumbai-Rotterdam"]
        facilities = ["Rotterdam DC"]
    reasoning = f"Mapped {category} risk to {len(suppliers)} supplier(s), {len(lanes)} lane(s), and {len(facilities)} facility node(s)."
    return ImpactMap(signal_id=classification.signal_id, affected_suppliers=suppliers, affected_lanes=lanes, affected_facilities=facilities, reasoning=reasoning)


def fallback_signal(classification: Classification) -> DisruptionSignal:
    return DisruptionSignal(signal_id=classification.signal_id, source="classification", source_type="SYNTHETIC", fetched_at=datetime.now(UTC), title=classification.category)


def map_impact(signal: DisruptionSignal, classification: Classification) -> ImpactMap:
    query_parts = [signal.text, classification.category]
    query_parts.extend(CATEGORY_HINTS.get(classification.category, []))
    if signal.region:
        query_parts.append(signal.region)
    docs = impact_retriever().search(" ".join(query_parts), top_k=6)
    suppliers: list[str] = []
    lanes: list[str] = []
    facilities: list[str] = []
    products: list[str] = []
    context: list[str] = []
    for doc in docs:
        meta = doc.metadata
        kind = meta.get("kind")
        name = str(meta.get("name", meta.get("lane", doc.doc_id)))
        context.append(doc.text)
        if kind == "suppliers":
            suppliers.append(name)
            products.extend(str(item) for item in meta.get("products", []))
            if meta.get("primary_lane"):
                lanes.append(str(meta["primary_lane"]))
        elif kind == "facilities":
            facilities.append(name)
            lanes.extend(str(item) for item in meta.get("lanes", []))
        elif kind == "lanes":
            lanes.append(name)
    base = default_impact(classification)
    if not suppliers:
        suppliers = base.affected_suppliers
    if not lanes:
        lanes = base.affected_lanes
    if not facilities:
        facilities = base.affected_facilities
    reasoning = f"Mapped {classification.category} risk to {len(suppliers)} supplier(s), {len(lanes)} lane(s), and {len(facilities)} facility node(s)."
    return ImpactMap(
        signal_id=signal.signal_id,
        affected_suppliers=list(dict.fromkeys(suppliers))[:4],
        affected_lanes=list(dict.fromkeys(lanes))[:5],
        affected_facilities=list(dict.fromkeys(facilities))[:4],
        product_categories=list(dict.fromkeys(products))[:5],
        retrieved_context=context[:4],
        reasoning=reasoning,
    )


def impact_node(state: "GraphState") -> dict:
    signals = {signal.signal_id: signal for signal in state.get("new_signals", [])}
    impacts = []
    for item in state.get("classifications", []):
        if item.severity < 3:
            continue
        signal = signals.get(item.signal_id)
        impacts.append(map_impact(signal, item) if signal else default_impact(item))
    return {"impacts": impacts}
