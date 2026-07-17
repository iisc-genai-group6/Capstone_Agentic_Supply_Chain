from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from agentic_scd.agents.forecast import build_forecast
from agentic_scd.agents.impact import map_impact
from agentic_scd.agents.news import analyze_signal
from agentic_scd.agents.recommend import build_recommendation
from agentic_scd.agents.schema import Classification
from agentic_scd.agents.simulate import run_simulation
from agentic_scd.agents.weather import weather_node
from agentic_scd.config import get_settings
from agentic_scd.ingestion.paths import FALLBACK_DIR
from agentic_scd.ingestion.schema import DisruptionSignal, Location
from agentic_scd.rag.retriever import forecast_documents, rebuild_vector_store, retriever_stats


def make_signal(title: str, body: str, region: str = "Netherlands") -> DisruptionSignal:
    return DisruptionSignal(
        signal_id=title.lower().replace(" ", "-"),
        source="test",
        source_type="WEBHOOK",
        source_reliability=0.9,
        fetched_at=datetime.now(UTC),
        title=title,
        raw_text=body,
        location=Location(region=region, hub_port="Port of Rotterdam"),
        severity_hint="high",
    )


def test_vector_store_persists_in_separate_sqlite_db(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENTIC_SCD_HOME", str(tmp_path))
    get_settings.cache_clear()
    result = rebuild_vector_store()
    stats = retriever_stats()
    path = Path(str(stats["vector_store_path"]))
    assert stats["backend"] == "sqlite_vector_store"
    assert path.exists()
    with sqlite3.connect(path) as conn:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "vector_collections" in names
    assert "vector_documents" in names
    assert result["collections"]["impact"] > 0
    assert result["collections"]["mitigation"] > 0
    get_settings.cache_clear()


def test_vector_store_deduplicates_forecast_doc_ids(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENTIC_SCD_HOME", str(tmp_path))
    get_settings.cache_clear()
    rebuild_vector_store(["forecast"])
    stats = retriever_stats()
    assert stats["forecast_documents"] == len({document.doc_id for document in forecast_documents()})
    get_settings.cache_clear()


def test_vector_store_follows_postgres_when_primary_database_is_postgres(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("AGENTIC_SCD_HOME", str(tmp_path))
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://user:pass@localhost:5432/agentic"
    )
    monkeypatch.delenv("VECTOR_DATABASE_URL", raising=False)
    get_settings.cache_clear()
    stats = retriever_stats()
    assert stats["backend"] == "postgres_vector_store"
    assert str(stats["vector_store_path"]).startswith("postgresql://")
    get_settings.cache_clear()


def test_all_localfirst_agents_consume_retrieved_context(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENTIC_SCD_HOME", str(tmp_path))
    get_settings.cache_clear()
    signal = make_signal(
        "Port strike delays Rotterdam shipments",
        "Port strike and freight congestion are delaying container shipments moving through Rotterdam.",
    )
    analysis = analyze_signal(signal)
    classification = Classification(
        signal_id=signal.signal_id,
        category="logistics",
        risk_score=0.72,
    )
    impact = map_impact(signal, classification)
    forecast = build_forecast([classification], [impact])
    simulation = run_simulation([classification], [impact], forecast)
    recommendation = build_recommendation([classification], [impact], simulation)
    snapshot = json.loads((FALLBACK_DIR / "open_meteo_hubs.json").read_text(encoding="utf-8"))
    weather_row = next(item for item in snapshot if item["hub"]["hub_port"] == "Port of Shanghai")
    weather_signal = DisruptionSignal(
        signal_id="weather-shanghai",
        source="open_meteo",
        source_type="WEATHER",
        source_reliability=0.9,
        fetched_at=datetime.now(UTC),
        title="Weather forecast for Port of Shanghai",
        raw_text="",
        location=Location(**weather_row["hub"]),
        severity_hint="severe",
        raw_payload={"hub": weather_row["hub"], "response": weather_row["response"]},
    )
    weather = weather_node({"new_signals": [weather_signal]})["weather_risks"][0]

    assert analysis.retrieved_context
    assert weather.retrieved_context
    assert impact.retrieved_context
    assert forecast.retrieved_context
    assert simulation.retrieved_context
    assert recommendation.evidence
    get_settings.cache_clear()
