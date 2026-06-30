from __future__ import annotations

from dataclasses import dataclass

from agentic_scd.ingestion.dedupe import assign_hash, is_duplicate
from agentic_scd.ingestion.relevance import gate
from agentic_scd.ingestion.schema import DisruptionSignal
from agentic_scd.ingestion.sqlutil import commit
from agentic_scd.ingestion.store import persist_signal, record_rejected


@dataclass
class IngestResult:
    kept: int = 0
    dropped: int = 0
    persisted: int = 0

    @property
    def duplicate(self) -> int:
        return max(0, self.kept - self.persisted)


def ingest_signals(signals: list[DisruptionSignal], conn) -> IngestResult:
    kept, dropped = gate(signals)
    result = IngestResult(kept=len(kept), dropped=len(dropped))
    if conn is None:
        return result
    for signal in kept:
        assign_hash(signal)
        if is_duplicate(signal.dedup_hash, conn):
            continue
        if persist_signal(conn, signal):
            result.persisted += 1
    for signal in dropped:
        record_rejected(conn, assign_hash(signal).dedup_hash or "")
    commit(conn)
    return result
