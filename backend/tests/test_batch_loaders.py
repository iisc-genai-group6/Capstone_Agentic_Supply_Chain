"""Phase 1c batch loaders — parse committed seed snapshots, idempotent re-runs.

Fully offline: reads the committed ``data/seed/`` snapshots, builds normalized signals,
and exercises idempotency through a ``FakeConn`` (no Postgres, no network).
"""

from agentic_scd.ingestion.batch import freightos, kaggle, load_batch
from agentic_scd.ingestion.connectors.base import SourceType
from agentic_scd.ingestion.schema import DisruptionSignal

if __package__:
    from .fakes import FakeConn, make_settings
else:
    from fakes import FakeConn, make_settings


def test_freightos_build_signals_counts_and_type() -> None:
    signals = freightos.build_signals()
    assert len(signals) == 8
    assert all(isinstance(s, DisruptionSignal) for s in signals)
    assert all(s.source_type == SourceType.FREIGHT_INDEX for s in signals)
    assert all(s.source == "freightos_baltic_index" for s in signals)
    # Key fields normalized from the snapshot.
    assert all("Freight rate" in s.title for s in signals)
    assert all(s.event_time is not None for s in signals)
    assert signals[0].raw_payload["kind"] == "freight_rate"


def test_kaggle_build_signals_counts_and_kinds() -> None:
    signals = kaggle.build_signals()
    assert len(signals) == 8
    assert all(s.source_type == SourceType.DATASET for s in signals)
    kinds = {s.raw_payload["kind"] for s in signals}
    assert kinds == {"demand", "disruption"}


def test_freightos_load_offline_parses_but_does_not_persist() -> None:
    result = freightos.load(conn=None)
    assert result.loaded == 8
    assert result.kept == 8  # all freight-rate rows pass the relevance gate
    assert result.dropped == 0
    assert result.persisted == 0  # no DB -> nothing persisted


def test_loaders_are_idempotent_on_second_run() -> None:
    conn = FakeConn()
    first = freightos.load(conn)
    assert first.persisted == first.kept == 8
    # Re-running the same snapshot persists no new rows (ON CONFLICT on dedup_hash).
    second = freightos.load(conn)
    assert second.loaded == 8
    assert second.persisted == 0
    assert len(conn.signals) == 8


def test_load_batch_runs_all_enabled_loaders() -> None:
    summary = load_batch(conn=None, settings=make_settings())
    assert summary.enabled is True
    assert summary.db_persisted is False
    assert {r.name for r in summary.results} == {
        "freightos_baltic_index",
        "kaggle_supplychainnet",
    }
    assert summary.totals.loaded == 16
    assert summary.totals.kept == 16  # everything in the seed passes the gate
    assert summary.totals.persisted == 0


def test_load_batch_disabled_is_noop() -> None:
    summary = load_batch(conn=None, settings=make_settings(batch_enabled=False))
    assert summary.enabled is False
    assert summary.results == []
