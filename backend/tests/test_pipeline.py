"""Shared ingest_signals tail — gate/dedupe/persist counts, offline (conn=None)."""

from datetime import UTC, datetime

from agentic_scd.ingestion.pipeline import IngestResult, ingest_signals
from agentic_scd.ingestion.schema import DisruptionSignal


def make_signal(title: str, body: str = "") -> DisruptionSignal:
    return DisruptionSignal(
        signal_id="x",
        source="stub",
        source_type="RSS",
        fetched_at=datetime.now(UTC),
        title=title,
        raw_text=body,
    )


def test_ingest_signals_offline_splits_but_does_not_persist() -> None:
    signals = [
        make_signal("Port strike halts shipments"),
        make_signal("Tariff disrupts supplier logistics"),
        make_signal("Cat video goes viral"),  # off-topic -> dropped
    ]
    result = ingest_signals(signals, conn=None)
    assert isinstance(result, IngestResult)
    assert result.kept == 2
    assert result.dropped == 1
    assert result.persisted == 0  # no DB -> nothing persisted


def test_ingest_result_duplicate_is_kept_minus_persisted() -> None:
    result = IngestResult(kept=5, dropped=1, persisted=3)
    assert result.duplicate == 2
