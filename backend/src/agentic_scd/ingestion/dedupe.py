from __future__ import annotations

import hashlib

from agentic_scd.ingestion.schema import DisruptionSignal
from agentic_scd.ingestion.sqlutil import fetchone


def assign_hash(signal: DisruptionSignal) -> DisruptionSignal:
    basis = f"{signal.title.strip().lower()}|{signal.raw_text.strip().lower()}"
    signal.dedup_hash = hashlib.sha256(basis.encode("utf-8")).hexdigest()
    return signal


def is_duplicate(dedup_hash_value: str | None, conn) -> bool:
    if not dedup_hash_value or conn is None:
        return False
    if hasattr(conn, "execute"):
        sql = "SELECT 1 FROM seen_rejected WHERE dedup_hash = ? UNION ALL SELECT 1 FROM signals WHERE dedup_hash = ? LIMIT 1"
        params = (dedup_hash_value, dedup_hash_value)
    else:
        sql = "SELECT 1 FROM seen_rejected WHERE dedup_hash = %s UNION ALL SELECT 1 FROM signals WHERE dedup_hash = %s LIMIT 1"
        params = (dedup_hash_value, dedup_hash_value)
    return fetchone(conn, sql, params) is not None
