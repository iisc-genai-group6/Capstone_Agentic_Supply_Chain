from __future__ import annotations

import json
from pathlib import Path

from agentic_scd.ingestion.connectors.open_meteo import OpenMeteoConnector
from agentic_scd.ingestion.connectors.rss import RssConnector
from agentic_scd.ingestion.connectors.synthetic import SyntheticConnector
from agentic_scd.ingestion.paths import FALLBACK_DIR, SEED_DIR


class ExternalDataMCP:
    def list_tools(self) -> list[dict]:
        return [
            {"name": "fetch_rss_signals", "description": "Fetch supply-chain RSS signals with cached fallback."},
            {"name": "fetch_weather_hubs", "description": "Fetch Open-Meteo weather signals for configured logistics hubs."},
            {"name": "load_freight_snapshot", "description": "Load the packaged Freightos-style freight snapshot."},
            {"name": "load_supply_dataset", "description": "Load the packaged Kaggle-style supply-chain CSV metadata."},
            {"name": "synthetic_scenarios", "description": "Return deterministic synthetic disruption scenarios."},
        ]

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        arguments = arguments or {}
        if name == "fetch_rss_signals":
            connector = RssConnector("mcp_rss", 0.7, arguments.get("feeds", []), arguments.get("queries", ["port strike", "supplier shutdown"]), FALLBACK_DIR / "rss_supplychain.xml")
            items = connector.fetch() if arguments.get("live", False) else connector.fallback()
            return {"items": [item.model_dump() for item in items]}
        if name == "fetch_weather_hubs":
            hubs = arguments.get("hubs") or [
                {"hub_port": "Port of Shanghai", "region": "China", "lat": 31.23, "lon": 121.47},
                {"hub_port": "Port of Rotterdam", "region": "Netherlands", "lat": 51.95, "lon": 4.14},
                {"hub_port": "Port of Los Angeles", "region": "USA", "lat": 33.74, "lon": -118.27},
            ]
            connector = OpenMeteoConnector("mcp_weather", 0.9, hubs, FALLBACK_DIR / "open_meteo_hubs.json")
            items = connector.fetch() if arguments.get("live", False) else connector.fallback()
            return {"items": [item.model_dump() for item in items]}
        if name == "load_freight_snapshot":
            return json.loads((SEED_DIR / "freightos_baltic_index.json").read_text(encoding="utf-8"))
        if name == "load_supply_dataset":
            path = SEED_DIR / "supply_chain_dataset.csv"
            return {"path": str(path), "rows": sum(1 for _ in path.open(encoding="utf-8")) - 1}
        if name == "synthetic_scenarios":
            connector = SyntheticConnector("mcp_synthetic", 0.7, int(arguments.get("count", 4)))
            return {"items": [item.model_dump() for item in connector.fetch()]}
        raise ValueError(f"Unknown MCP tool: {name}")


def manifest() -> dict:
    mcp = ExternalDataMCP()
    return {"name": "agentic-scd-external-data", "tools": mcp.list_tools()}
