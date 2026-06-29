from __future__ import annotations

from typing import TYPE_CHECKING

from agentic_scd.agents.schema import Classification, ImpactMap
from agentic_scd.ingestion.schema import DisruptionSignal
from agentic_scd.rag.retriever import impact_retriever

if TYPE_CHECKING:
    from agentic_scd.graph.state import GraphState

CATEGORY_HINTS = {
    "weather": ["port", "warehouse", "Sea"],
    "labor_strike": ["port", "warehouse"],
    "logistics": ["lane", "Sea", "port"],
    "geopolitical": ["supplier", "lane"],
    "raw_material": ["supplier", "products"],
    "quality": ["supplier", "products"],
    "demand_shock": ["warehouse", "products"],
}


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
    if not suppliers:
        suppliers = ["Supplier A" if classification.category in {"weather", "logistics"} else "Supplier B"]
    if not lanes:
        lanes = ["Shanghai-Los Angeles" if classification.category in {"weather", "logistics"} else "Mumbai-Rotterdam"]
    if not facilities:
        facilities = ["Los Angeles Import DC"]
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
    impacts = [map_impact(signals[item.signal_id], item) for item in state.get("classifications", []) if item.signal_id in signals and item.severity >= 3]
    return {"impacts": impacts}
