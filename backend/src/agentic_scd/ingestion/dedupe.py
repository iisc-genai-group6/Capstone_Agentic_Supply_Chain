from __future__ import annotations

import hashlib

from agentic_scd.ingestion.schema import DisruptionSignal


def assign_hash(signal: DisruptionSignal) -> DisruptionSignal:
    basis = f"{signal.title.strip().lower()}|{signal.raw_text.strip().lower()}"
    signal.dedup_hash = hashlib.sha256(basis.encode("utf-8")).hexdigest()
    return signal


def is_duplicate(dedup_hash_value: str | None, conn) -> bool:
    if not dedup_hash_value or conn is None:
        return False
    row = conn.execute(
        "SELECT 1 FROM seen_rejected WHERE dedup_hash = ? UNION ALL SELECT 1 FROM signals WHERE dedup_hash = ? LIMIT 1",
        (dedup_hash_value, dedup_hash_value),
    ).fetchone()
    return row is not None
