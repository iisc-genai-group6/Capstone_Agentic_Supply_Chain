from __future__ import annotations

import json

from agentic_scd.config import get_settings
from agentic_scd.db import connect, init_db, ping
from agentic_scd.ingestion.connectors.open_meteo import OpenMeteoConnector
from agentic_scd.ingestion.connectors.freight import FreightIndexConnector
from agentic_scd.ingestion.connectors.rss import RssConnector
from agentic_scd.ingestion.connectors.synthetic import SyntheticConnector
from agentic_scd.ingestion.paths import FALLBACK_DIR, SEED_DIR
from agentic_scd.ingestion.store import recent_runs, recent_signals
from agentic_scd.rag.retriever import rebuild_vector_store, retrieval_mode, retriever_stats


def database_mode(url: str | None) -> str:
    lowered = (url or "").lower()
    if lowered.startswith("postgresql:") or lowered.startswith("postgres:"):
        return "postgres"
    if lowered.startswith("sqlite:"):
        return "sqlite"
    return "none"


class ExternalDataMCP:
    def list_tools(self) -> list[dict]:
        return [
            {"name": "fetch_rss_signals", "description": "Fetch supply-chain RSS signals with cached fallback."},
            {"name": "fetch_weather_hubs", "description": "Fetch Open-Meteo weather signals for configured logistics hubs."},
            {"name": "fetch_freight_index", "description": "Fetch the local-first freight index feed with cached fallback."},
            {"name": "load_freight_snapshot", "description": "Load the packaged Freightos-style freight snapshot."},
            {"name": "load_supply_dataset", "description": "Load the packaged Kaggle-style supply-chain CSV metadata."},
            {"name": "load_network_knowledge", "description": "Load the packaged supplier, facility, and lane knowledge graph."},
            {"name": "load_mitigation_playbooks", "description": "Load the packaged mitigation playbooks used by the recommendation agent."},
            {"name": "load_seed_corpus", "description": "Inspect the packaged synthetic and historical disruption corpora."},
            {"name": "inspect_vector_store", "description": "Inspect the local-first separate vector store, collections, and corpus sizes."},
            {"name": "rebuild_vector_store", "description": "Rebuild one or more local-first vector-store collections from the current corpora."},
            {"name": "inspect_runtime_state", "description": "Inspect the local runtime mode, database health, and recent persisted data."},
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
        if name == "fetch_freight_index":
            connector = FreightIndexConnector("mcp_freight", 0.85, arguments.get("url"), SEED_DIR / "freightos_baltic_index.json")
            items = connector.fetch() if arguments.get("live", False) else connector.fallback()
            return {"items": [item.model_dump() for item in items]}
        if name == "load_freight_snapshot":
            return json.loads((SEED_DIR / "freightos_baltic_index.json").read_text(encoding="utf-8"))
        if name == "load_supply_dataset":
            path = SEED_DIR / "supply_chain_dataset.csv"
            preview = path.read_text(encoding="utf-8").splitlines()[:6]
            return {"path": str(path), "rows": max(0, len(preview) - 1) if len(preview) <= 6 else sum(1 for _ in path.open(encoding="utf-8")) - 1, "preview": preview}
        if name == "load_network_knowledge":
            return json.loads((SEED_DIR / "network.json").read_text(encoding="utf-8"))
        if name == "load_mitigation_playbooks":
            rows = json.loads((SEED_DIR / "playbooks.json").read_text(encoding="utf-8"))
            return {"count": len(rows), "items": rows}
        if name == "load_seed_corpus":
            scenarios = json.loads((SEED_DIR / "scenarios.json").read_text(encoding="utf-8"))
            historical = json.loads((SEED_DIR / "kaggle_supplychainnet.json").read_text(encoding="utf-8"))
            synthetic = [line for line in (SEED_DIR / "synthetic_disruption_events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            return {
                "scenario_count": len(scenarios),
                "historical_demand_rows": sum(1 for row in historical.get("records", []) if row.get("kind") == "demand"),
                "historical_disruption_rows": sum(1 for row in historical.get("records", []) if row.get("kind") == "disruption"),
                "synthetic_event_rows": len(synthetic),
            }
        if name == "inspect_vector_store":
            return {"mode": retrieval_mode(), **retriever_stats()}
        if name == "rebuild_vector_store":
            collections = arguments.get("collections")
            return rebuild_vector_store(collections if isinstance(collections, list) else None)
        if name == "inspect_runtime_state":
            settings = get_settings()
            status = ping(settings)
            signals = []
            runs = []
            try:
                init_db(settings)
                with connect(settings) as conn:
                    signals = [item.model_dump(mode="json") for item in recent_signals(conn, int(arguments.get("signal_limit", 5)))]
                    runs = recent_runs(conn, int(arguments.get("run_limit", 5)))
            except Exception:
                signals = []
                runs = []
            return {
                "database_mode": database_mode(settings.resolved_database_url),
                "database_ok": status.ok,
                "database_status": status.detail,
                "llm_mode": "mock" if settings.llm_is_mock else f"groq:{settings.groq_model}",
                "data_dir": str(settings.data_dir),
                "retrieval_mode": retrieval_mode(),
                "vector_store_path": retriever_stats()["vector_store_path"],
                "recent_signals": signals,
                "recent_runs": runs,
            }
        if name == "synthetic_scenarios":
            connector = SyntheticConnector("mcp_synthetic", 0.7, int(arguments.get("count", 4)))
            return {"items": [item.model_dump() for item in connector.fetch()]}
        raise ValueError(f"Unknown MCP tool: {name}")


def manifest() -> dict:
    mcp = ExternalDataMCP()
    return {"name": "agentic-scd-external-data", "tools": mcp.list_tools()}
