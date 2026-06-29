from __future__ import annotations

import argparse
import logging

from agentic_scd.config import Settings, get_settings
from agentic_scd.db import connect, init_db
from agentic_scd.ingestion.batch import BatchSummary, load_batch
from agentic_scd.ingestion.retention import RetentionSummary, run_retention

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="agentic-scd-batch")
    parser.add_argument("--load", action="store_true")
    parser.add_argument("--retain", action="store_true")
    return parser.parse_args(argv)


def run(settings: Settings | None = None, *, do_load: bool = True, do_retain: bool = True) -> tuple[BatchSummary | None, RetentionSummary | None]:
    settings = settings or get_settings()
    db_ready = init_db(settings)
    conn = connect(settings) if db_ready else None
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
    where = "SQLite" if db_persisted else "in-memory"
    print(f"Batch run complete - persistence: {where}")
    if batch is not None:
        header = f"{'source':<24}{'loaded':>8}{'kept':>7}{'dropped':>9}{'persisted':>11}"
        print(header)
        print("-" * len(header))
        if batch.enabled:
            for result in batch.results:
                print(f"{result.name:<24}{result.loaded:>8}{result.kept:>7}{result.dropped:>9}{result.persisted:>11}")
            total = batch.totals
            print("-" * len(header))
            print(f"{'TOTAL':<24}{total.loaded:>8}{total.kept:>7}{total.dropped:>9}{total.persisted:>11}")
        else:
            print("Batch loaders disabled")
    if retention is not None:
        if retention.ran:
            print(f"Retention: pruned {retention.rejected_pruned} rejected hashes and {retention.signals_pruned} done signals")
        else:
            print("Retention: skipped")


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = parse_args(argv)
    do_load = args.load or not (args.load or args.retain)
    do_retain = args.retain or not (args.load or args.retain)
    batch, retention = run(do_load=do_load, do_retain=do_retain)
    print_summary(batch, retention)


if __name__ == "__main__":
    main()
