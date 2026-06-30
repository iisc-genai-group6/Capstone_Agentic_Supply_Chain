from __future__ import annotations

import argparse
import logging

from agentic_scd.config import Settings, get_settings
from agentic_scd.db import DatabaseNotConfiguredError, connect, init_db
from agentic_scd.ingestion.batch import BatchSummary, load_batch
from agentic_scd.ingestion.retention import RetentionSummary, run_retention

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="agentic-scd-batch", description="Seed historical data and prune stale rows.")
    parser.add_argument("--load", action="store_true", help="run the batch loaders only")
    parser.add_argument("--retain", action="store_true", help="run retention/TTL pruning only")
    return parser.parse_args(argv)


def open_connection(settings: Settings):
    try:
        return connect(settings)
    except Exception as exc:
        if isinstance(exc, DatabaseNotConfiguredError):
            logger.warning("batch: no DB available (%s)", exc)
        else:
            logger.warning("batch: no DB available (%s)", exc)
        return None


def run(settings: Settings | None = None, *, do_load: bool = True, do_retain: bool = True) -> tuple[BatchSummary | None, RetentionSummary | None]:
    settings = settings or get_settings()
    db_ready = init_db(settings)
    conn = open_connection(settings) if db_ready else None
    batch_summary: BatchSummary | None = None
    retention_summary: RetentionSummary | None = None
    try:
        if do_load:
            batch_summary = load_batch(conn, settings)
        if do_retain:
            retention_summary = run_retention(conn, settings)
    finally:
        if conn is not None:
            conn.close()
    return batch_summary, retention_summary


def print_summary(batch: BatchSummary | None, retention: RetentionSummary | None) -> None:
    db_persisted = bool(batch and batch.db_persisted) or bool(retention and retention.ran)
    where = "SQLite" if db_persisted else "no DB (offline)"
    path = "live" if db_persisted else "offline"
    print(f"Batch run complete - persistence: {where}")
    if batch is not None:
        header = f"{'source':<24}{'loaded':>8}{'kept':>7}{'dropped':>9}{'persisted':>11}{'path':>9}"
        print(header)
        print("-" * len(header))
        if batch.enabled:
            for r in batch.results:
                print(f"{r.name:<24}{r.loaded:>8}{r.kept:>7}{r.dropped:>9}{r.persisted:>11}{path:>9}")
            t = batch.totals
            print("-" * len(header))
            print(f"{'TOTAL':<24}{t.loaded:>8}{t.kept:>7}{t.dropped:>9}{t.persisted:>11}{'':>9}")
        else:
            print("(batch loaders disabled)")
    if retention is not None:
        if retention.ran:
            print(f"Retention: pruned {retention.rejected_pruned} seen_rejected, {retention.signals_pruned} done signals")
        else:
            print("Retention: skipped (no DB or disabled)")


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = parse_args(argv)
    do_load = args.load or not (args.load or args.retain)
    do_retain = args.retain or not (args.load or args.retain)
    batch, retention = run(do_load=do_load, do_retain=do_retain)
    print_summary(batch, retention)


if __name__ == "__main__":
    main()
