from __future__ import annotations

from dataclasses import dataclass

from agentic_scd.ingestion.sqlutil import dialect, execute


@dataclass
class RetentionSummary:
    ran: bool = False
    rejected_pruned: int = 0
    signals_pruned: int = 0


def prune_seen_rejected(conn, ttl_days: int) -> int:
    if dialect(conn) == "sqlite":
        cur = execute(conn, "DELETE FROM seen_rejected WHERE first_seen_at < datetime('now', ?)", (f"-{ttl_days} days",))
    else:
        cur = execute(conn, "DELETE FROM seen_rejected WHERE first_seen_at < now() - make_interval(days => %s)", (ttl_days,))
    return cur.rowcount


def prune_signals(conn, ttl_days: int) -> int:
    if dialect(conn) == "sqlite":
        cur = execute(conn, "DELETE FROM signals WHERE status = 'done' AND created_at < datetime('now', ?)", (f"-{ttl_days} days",))
    else:
        cur = execute(conn, "DELETE FROM signals WHERE status = 'done' AND created_at < now() - make_interval(days => %s)", (ttl_days,))
    return cur.rowcount


def run_retention(conn, settings) -> RetentionSummary:
    if conn is None or not settings.retention_enabled:
        return RetentionSummary(ran=False)
    rejected = prune_seen_rejected(conn, settings.retention_rejected_ttl_days)
    signals = prune_signals(conn, settings.retention_signals_ttl_days)
    conn.commit()
    return RetentionSummary(ran=True, rejected_pruned=rejected, signals_pruned=signals)
