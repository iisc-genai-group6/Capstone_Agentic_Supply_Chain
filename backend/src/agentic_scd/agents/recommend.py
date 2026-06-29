from __future__ import annotations

from typing import TYPE_CHECKING

from agentic_scd.agents.schema import Classification, ImpactMap, MitigationAction, Recommendation, Simulation
from agentic_scd.rag.retriever import mitigation_retriever

if TYPE_CHECKING:
    from agentic_scd.graph.state import GraphState

OWNER_BY_CATEGORY = {
    "weather": "Logistics lead",
    "labor_strike": "Transportation manager",
    "logistics": "Control tower analyst",
    "geopolitical": "Procurement lead",
    "raw_material": "Sourcing manager",
    "demand_shock": "Demand planner",
    "quality": "Supplier quality engineer",
    "other": "Supply chain analyst",
}


def urgency(classification: Classification, simulation: Simulation) -> str:
    if classification.severity > 7 or simulation.stockout_probability >= 0.6:
        return "critical"
    if classification.severity >= 5 or simulation.stockout_probability >= 0.35:
        return "high"
    return "medium"


def build_recommendation(classifications: list[Classification], impacts: list[ImpactMap], simulation: Simulation) -> Recommendation:
    structured: list[MitigationAction] = []
    evidence: list[str] = []
    categories = list(dict.fromkeys(item.category for item in classifications)) or ["other"]
    max_by_category = {category: max((item for item in classifications if item.category == category), key=lambda item: item.severity, default=None) for category in categories}
    for category in categories:
        classification = max_by_category.get(category)
        docs = mitigation_retriever().search(category, top_k=2, category=category)
        if not docs:
            docs = mitigation_retriever().search(category, top_k=2)
        if docs:
            chosen = docs[0]
            meta = chosen.metadata
            action = str(meta.get("action", "Review supplier exposure and raise safety stock."))
            expected = str(meta.get("expected_effect", "Reduces disruption exposure."))
            evidence.append(f"{meta.get('title', chosen.doc_id)}: {expected}")
        else:
            action = "Review supplier exposure, reserve safety stock, and prepare an alternate route."
            expected = "Creates a controlled response while more data arrives."
        level = urgency(classification, simulation) if classification else "medium"
        owner = OWNER_BY_CATEGORY.get(category, "Supply chain analyst")
        structured.append(MitigationAction(action=action, urgency=level, expected_impact=expected, owner=owner))
    if simulation.stockout_probability >= 0.5:
        structured.insert(0, MitigationAction(action="Open a daily disruption war-room until stockout probability drops below 35 percent.", urgency="critical", expected_impact="Keeps cross-functional decisions synchronized during the highest-risk window.", owner="Supply chain director"))
    actions = [f"[{item.urgency.upper()}] {item.action} Owner: {item.owner}." for item in structured]
    impacted = sum(len(item.affected_entities) for item in impacts)
    summary = f"{len(actions)} ranked actions for {len(categories)} risk category(ies), {impacted} affected network node(s), stockout probability {simulation.stockout_probability:.0%}, expected revenue impact {simulation.revenue_impact:,.0f}."
    return Recommendation(actions=actions, structured_actions=structured, summary=summary, evidence=evidence)


def recommend_node(state: "GraphState") -> dict:
    simulation = state.get("simulation") or Simulation(stockout_probability=0.0)
    return {"recommendation": build_recommendation(state.get("classifications", []), state.get("impacts", []), simulation)}
