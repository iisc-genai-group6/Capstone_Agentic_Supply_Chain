from __future__ import annotations

import json
from typing import TYPE_CHECKING

from agentic_scd.ingestion.connectors.base import RawItem
from agentic_scd.ingestion.connectors.synthetic import SyntheticConnector
from agentic_scd.ingestion.normalize import normalize
from agentic_scd.ingestion.paths import SEED_DIR

if TYPE_CHECKING:
    from agentic_scd.graph.state import GraphState


def scenario_signal(name: str):
    path = SEED_DIR / "scenarios.json"
    if not path.exists():
        return None
    rows = json.loads(path.read_text(encoding="utf-8"))
    for row in rows:
        if row.get("name") == name:
            connector = SyntheticConnector("scenario_library", 0.8, 1)
            raw = RawItem(
                title=row["title"],
                body=row["body"],
                location={"region": row.get("region")},
                payload={"severity_hint": "high" if row.get("severity", 0) >= 7 else "moderate", **row},
            )
            return normalize(raw, connector)
    return None


def seed_node(state: "GraphState") -> dict:
    if state.get("new_signals"):
        return {}
    scenario_name = state.get("scenario_name")
    if scenario_name:
        signal = scenario_signal(scenario_name)
        if signal:
            return {"new_signals": [signal]}
    connector = SyntheticConnector(name="demo_seed", reliability=0.7, count=1)
    return {"new_signals": [normalize(item, connector) for item in connector.fetch()]}
