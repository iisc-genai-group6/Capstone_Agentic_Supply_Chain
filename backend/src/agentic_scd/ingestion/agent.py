from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agentic_scd.db import connect, init_db
from agentic_scd.ingestion.store import row_to_signal

if TYPE_CHECKING:
    from agentic_scd.graph.state import GraphState

logger = logging.getLogger(__name__)


SELECT_NEW = "SELECT * FROM signals WHERE status = 'new' AND source_type NOT IN ('DATASET', 'FREIGHT_INDEX') ORDER BY created_at"


def read_new_signals(conn) -> list:
    rows = conn.execute(SELECT_NEW).fetchall()
    signals = [row_to_signal(row) for row in rows]
    if signals:
        ids = [signal.signal_id for signal in signals]
        placeholders = ",".join("?" for _ in ids)
        conn.execute(f"UPDATE signals SET status = 'processing' WHERE signal_id IN ({placeholders})", ids)
        conn.commit()
    return signals


def ingestion_node(state: "GraphState") -> dict:
    try:
        init_db()
        with connect() as conn:
            signals = read_new_signals(conn)
    except Exception as exc:
        logger.warning("ingestion node used in-memory fallback: %s", exc)
        signals = []
    return {"new_signals": signals}
