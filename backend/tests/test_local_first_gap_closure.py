from __future__ import annotations

import json
from datetime import UTC, datetime

from agentic_scd.agents.news import heuristic_analysis
from agentic_scd.agents.recommend import build_recommendation
from agentic_scd.agents.schema import Classification, ImpactMap, Simulation
from agentic_scd.agents.weather import weather_node
from agentic_scd.config import Settings, get_settings
from agentic_scd.ingestion.connectors.freight import FreightIndexConnector
from agentic_scd.ingestion.paths import FALLBACK_DIR, SEED_DIR
from agentic_scd.evaluation.metrics import evaluate
from agentic_scd.ingestion.registry import load_registry
from agentic_scd.ingestion.schema import DisruptionSignal, Location
from agentic_scd.rag.retriever import history_retriever, retriever_stats


def make_signal(title: str, body: str, region: str, hint: str = "severe") -> DisruptionSignal:
    return DisruptionSignal(
        signal_id=title.lower().replace(" ", "-"),
        source="test",
        source_type="WEBHOOK",
        source_reliability=0.9,
        fetched_at=datetime.now(UTC),
        title=title,
        raw_text=body,
        location=Location(region=region, hub_port="Port of Shanghai"),
        severity_hint=hint,
    )


def test_weather_node_extracts_risk_row() -> None:
    snapshot = json.loads((FALLBACK_DIR / "open_meteo_hubs.json").read_text(encoding="utf-8"))
    row = next(item for item in snapshot if item["hub"]["hub_port"] == "Port of Shanghai")
    signal = DisruptionSignal(
        signal_id="weather-shanghai",
        source="open_meteo",
        source_type="WEATHER",
        source_reliability=0.9,
        fetched_at=datetime.now(UTC),
        title="Typhoon closes Shanghai port",
        raw_text="Typhoon flooding and gale force winds are shutting container handling at Shanghai port.",
        location=Location(**row["hub"]),
        severity_hint="severe",
        raw_payload={"hub": row["hub"], "response": row["response"]},
    )
    rows = weather_node({"new_signals": [signal]})["weather_risks"]
    assert len(rows) == 1
    assert rows[0].aggregate_severity >= 7.0
    assert rows[0].region == "China"


def test_registry_includes_freight_connector() -> None:
    connectors = load_registry()
    assert any(getattr(connector, "source_type", "") == "FREIGHT_INDEX" for connector in connectors)


def test_freight_connector_fallback_replays_snapshot() -> None:
    connector = FreightIndexConnector("freight", 0.85, fallback_path=SEED_DIR / "freightos_baltic_index.json")
    items = connector.fallback()
    assert items
    assert items[0].payload["kind"] == "freight_rate"
    assert items[0].location["region"] in {"North America", "Europe", "Asia"}


def test_history_retriever_reports_hybrid_mode() -> None:
    docs = history_retriever().search("freight rate China East Asia North America West Coast", top_k=2)
    stats = retriever_stats()
    assert stats["mode"] == "hybrid_hash_vector"
    assert docs
    assert any(doc.metadata.get("category") == "logistics" for doc in docs)


def test_settings_use_real_llm_when_key_present(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTIC_SCD_HOME", str(tmp_path))
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.delenv("USE_MOCK_LLM", raising=False)
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.llm_is_mock is False
    get_settings.cache_clear()


def test_recommendation_uses_llm_json_when_available(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "agentic_scd.agents.recommend.get_settings",
        lambda: Settings(
            data_dir=tmp_path,
            database_url=f"sqlite:///{tmp_path / 'agentic.sqlite'}",
            groq_api_key="test-key",
            use_mock_llm=False,
        ),
    )
    monkeypatch.setattr(
        "agentic_scd.agents.recommend.completion",
        lambda *args, **kwargs: json.dumps(
            {
                "actions": [
                    {
                        "action": "Shift 30 percent of exposed volume to Supplier C and reserve expedited freight for the top SKU set.",
                        "urgency": "critical",
                        "expected_impact": "Cuts stockout risk during the port outage window.",
                        "owner": "Logistics lead",
                        "evidence": "Shanghai weather disruption and the freight playbook both support alternate routing.",
                    }
                ]
            }
        ),
    )
    recommendation = build_recommendation(
        [Classification(signal_id="x", category="weather", risk_score=0.82)],
        [ImpactMap(signal_id="x", affected_suppliers=["Supplier A"], affected_lanes=["Shanghai-Los Angeles"])],
        Simulation(stockout_probability=0.61, revenue_impact=12000.0),
    )
    assert recommendation.generation_mode == "llm_playbook"
    assert recommendation.structured_actions
    assert recommendation.structured_actions[0].owner == "Supply chain director"
    assert any("Supplier C" in action.action for action in recommendation.structured_actions)


def test_evaluation_reports_weather_and_retrieval(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTIC_SCD_HOME", str(tmp_path))
    get_settings.cache_clear()
    report = evaluate()
    assert report.weather_coverage >= 1.0
    assert report.retrieval_documents > 0
    get_settings.cache_clear()
