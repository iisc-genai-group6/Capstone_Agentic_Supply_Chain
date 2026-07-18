"""Phase 1c retention/TTL — offline no-op + DB-touching prune scoping.

The no-op tests run fully offline. The pruning test is DB-touching and skips cleanly
when no Postgres is reachable; it asserts only its own marker rows so it never disturbs
unrelated data, and cleans up after itself.
"""

import uuid

import pytest

from agentic_scd.db import connect, init_db, ping
from agentic_scd.ingestion.retention import (
    RetentionSummary,
    prune_seen_rejected,
    prune_signals,
    run_retention,
)

if __package__:
    from .fakes import make_settings
else:
    from fakes import make_settings


def test_run_retention_no_db_is_clean_noop() -> None:
    summary = run_retention(None, make_settings())
    assert isinstance(summary, RetentionSummary)
    assert summary.ran is False
    assert summary.rejected_pruned == 0
    assert summary.signals_pruned == 0


def test_run_retention_disabled_is_noop() -> None:
    # conn is non-None but retention is disabled -> still a no-op (conn untouched).
    sentinel = object()
    summary = run_retention(sentinel, make_settings(retention_enabled=False))
    assert summary.ran is False


@pytest.fixture
def conn():
    result = ping()
    if not result.ok:
        pytest.skip(f"no Postgres reachable ({result.detail})")
    assert init_db() is True
    connection = connect()
    yield connection
    connection.close()


def _insert_signal(cur, signal_id: str, status: str, age_days: int) -> None:
    cur.execute(
        "INSERT INTO signals (signal_id, dedup_hash, source, source_type, "
        "fetched_at, title, schema_version, status, created_at) VALUES "
        "(%s, %s, 'test', 'DATASET', now(), 'retention test', 2, %s, "
        "now() - make_interval(days => %s))",
        (signal_id, signal_id, status, age_days),
    )


def test_prune_removes_only_stale_rows(conn) -> None:
    marker = uuid.uuid4().hex
    old_rej = f"old_{marker}"
    new_rej = f"new_{marker}"
    sig_ids = {
        "done_old": f"done_old_{marker}",
        "done_new": f"done_new_{marker}",
        "new_old": f"new_old_{marker}",
        "proc_old": f"proc_old_{marker}",
    }
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO seen_rejected (dedup_hash, first_seen_at) VALUES "
            "(%s, now() - interval '100 days')",
            (old_rej,),
        )
        cur.execute(
            "INSERT INTO seen_rejected (dedup_hash, first_seen_at) VALUES (%s, now())",
            (new_rej,),
        )
        _insert_signal(cur, sig_ids["done_old"], "done", 100)
        _insert_signal(cur, sig_ids["done_new"], "done", 1)
        _insert_signal(cur, sig_ids["new_old"], "new", 100)
        _insert_signal(cur, sig_ids["proc_old"], "processing", 100)
    conn.commit()

    try:
        prune_seen_rejected(conn, ttl_days=30)
        prune_signals(conn, ttl_days=90)
        conn.commit()

        with conn.cursor() as cur:
            cur.execute(
                "SELECT dedup_hash FROM seen_rejected WHERE dedup_hash IN (%s, %s)",
                (old_rej, new_rej),
            )
            remaining_rej = {r[0] for r in cur.fetchall()}
            cur.execute(
                "SELECT signal_id FROM signals WHERE dedup_hash LIKE %s",
                (f"%{marker}",),
            )
            remaining_sig = {r[0] for r in cur.fetchall()}

        # Old rejected hash pruned; recent one kept.
        assert remaining_rej == {new_rej}
        # Only the stale 'done' signal is pruned; live/in-window rows preserved.
        assert sig_ids["done_old"] not in remaining_sig
        assert sig_ids["done_new"] in remaining_sig
        assert sig_ids["new_old"] in remaining_sig
        assert sig_ids["proc_old"] in remaining_sig
    finally:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM seen_rejected WHERE dedup_hash IN (%s, %s)",
                (old_rej, new_rej),
            )
            cur.execute("DELETE FROM signals WHERE dedup_hash LIKE %s", (f"%{marker}",))
        conn.commit()
