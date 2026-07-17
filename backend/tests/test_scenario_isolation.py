from __future__ import annotations

from datetime import UTC, datetime

from agentic_scd.__main__ import run
from agentic_scd.config import Settings
from agentic_scd.db import connect, init_db
from agentic_scd.ingestion.dedupe import assign_hash
from agentic_scd.ingestion.schema import DisruptionSignal
from agentic_scd.ingestion.store import persist_signal


def test_named_scenario_ignores_pending_collected_signals(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTIC_SCD_HOME", str(tmp_path))
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'agentic_scd.sqlite'}")
    init_db(settings)
    signal = assign_hash(
        DisruptionSignal(
            signal_id="pending-policy-signal",
            source="test",
            source_type="RSS",
            source_reliability=0.8,
            fetched_at=datetime.now(UTC),
            title="Tariff embargo on imports",
            raw_text="Customs checks delay inbound lanes.",
        )
    )
    with connect(settings) as conn:
        persist_signal(conn, signal)
        conn.commit()
    state = run("Typhoon approaching Shanghai Port")
    classifications = state.get("classifications", [])
    assert classifications
    assert classifications[0].category == "weather"
    assert state["new_signals"][0].source == "scenario_library"
    assert state["new_signals"][0].source_type == "WEATHER"
    assert state.get("weather_risks")
