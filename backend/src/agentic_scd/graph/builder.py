from __future__ import annotations

from typing import Any

from agentic_scd.agents.classify import classify_node
from agentic_scd.agents.forecast import forecast_node
from agentic_scd.agents.impact import impact_node
from agentic_scd.agents.news import news_node
from agentic_scd.agents.recommend import recommend_node
from agentic_scd.agents.simulate import simulate_node
from agentic_scd.graph.seed import seed_node
from agentic_scd.graph.state import GraphState
from agentic_scd.ingestion.agent import ingestion_node
from agentic_scd.ingestion.guardrails import input_guardrail_node

PIPELINE = [
    "ingestion",
    "input_guardrail",
    "seed",
    "news",
    "classify",
    "impact",
    "forecast",
    "simulate",
    "recommend",
]

NODE_FNS = {
    "ingestion": ingestion_node,
    "input_guardrail": input_guardrail_node,
    "seed": seed_node,
    "news": news_node,
    "classify": classify_node,
    "impact": impact_node,
    "forecast": forecast_node,
    "simulate": simulate_node,
    "recommend": recommend_node,
}


class SimpleGraph:
    def invoke(self, state: dict | None = None) -> GraphState:
        current: dict = dict(state or {})
        for name in PIPELINE:
            update = NODE_FNS[name](current)
            current.update(update or {})
        return current


def build_graph() -> Any:
    try:
        from langgraph.graph import END, START, StateGraph

        builder = StateGraph(GraphState)
        for name in PIPELINE:
            builder.add_node(name, NODE_FNS[name])
        builder.add_edge(START, PIPELINE[0])
        for upstream, downstream in zip(PIPELINE, PIPELINE[1:], strict=False):
            builder.add_edge(upstream, downstream)
        builder.add_edge(PIPELINE[-1], END)
        return builder.compile()
    except Exception:
        return SimpleGraph()
