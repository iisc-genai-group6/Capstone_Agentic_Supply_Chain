from __future__ import annotations

import logging
from dataclasses import dataclass, field

from agentic_scd.config import Settings, get_settings
from agentic_scd.db import connect, init_db
from agentic_scd.ingestion.connectors.base import Connector, fetch_with_fallback
from agentic_scd.ingestion.normalize import normalize
from agentic_scd.ingestion.pipeline import ingest_signals
from agentic_scd.ingestion.registry import load_registry
from agentic_scd.ingestion.store import write_snapshot

logger = logging.getLogger(__name__)


@dataclass
class SourceResult:
    name: str
    fetched: int = 0
    kept: int = 0
    dropped: int = 0
    persisted: int = 0
    fallback_used: bool = False


@dataclass
class CollectSummary:
    db_persisted: bool = False
    results: list[SourceResult] = field(default_factory=list)

    @property
    def totals(self) -> SourceResult:
        total = SourceResult(name="TOTAL")
        for result in self.results:
            total.fetched += result.fetched
            total.kept += result.kept
            total.dropped += result.dropped
            total.persisted += result.persisted
        return total


def process_connector(connector: Connector, conn) -> SourceResult:
    result = SourceResult(name=connector.name)
    raw_items, path = fetch_with_fallback(connector)
    result.fetched = len(raw_items)
    result.fallback_used = path == "fallback"
    write_snapshot(connector.name, raw_items)
    signals = [normalize(item, connector) for item in raw_items]
    ingested = ingest_signals(signals, conn)
    result.kept = ingested.kept
    result.dropped = ingested.dropped
    result.persisted = ingested.persisted
    return result


def collect(settings: Settings | None = None) -> CollectSummary:
    settings = settings or get_settings()
    db_ready = init_db(settings)
    summary = CollectSummary(db_persisted=db_ready)
    conn = connect(settings) if db_ready else None
    try:
        for connector in load_registry():
            summary.results.append(process_connector(connector, conn))
    finally:
        if conn is not None:
            conn.close()
    return summary


def print_summary(summary: CollectSummary) -> None:
    where = "SQLite" if summary.db_persisted else "in-memory"
    print(f"Collection complete - persistence: {where}")
    header = f"{'source':<20}{'fetched':>9}{'kept':>7}{'dropped':>9}{'persisted':>11}{'path':>11}"
    print(header)
    print("-" * len(header))
    for result in summary.results:
        path = "fallback" if result.fallback_used else "live"
        print(f"{result.name:<20}{result.fetched:>9}{result.kept:>7}{result.dropped:>9}{result.persisted:>11}{path:>11}")
    total = summary.totals
    print("-" * len(header))
    print(f"{'TOTAL':<20}{total.fetched:>9}{total.kept:>7}{total.dropped:>9}{total.persisted:>11}{'':>11}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    print_summary(collect())


if __name__ == "__main__":
    main()
