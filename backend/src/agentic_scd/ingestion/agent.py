from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agentic_scd.db import connect, init_db
from agentic_scd.ingestion.sqlutil import commit, dialect, execute, placeholders
from agentic_scd.ingestion.store import row_to_signal

if TYPE_CHECKING:
    from agentic_scd.graph.state import GraphState

logger = logging.getLogger(__name__)

SELECT_NEW = "SELECT * FROM signals WHERE status = 'new' AND source_type NOT IN ('DATASET', 'FREIGHT_INDEX') ORDER BY created_at"


def read_new_signals(conn) -> list:
    rows = execute(conn, SELECT_NEW).fetchall()
    signals = [row_to_signal(row) for row in rows]
    if signals:
        ids = [signal.signal_id for signal in signals]
        style = "sqlite" if dialect(conn) == "sqlite" else "pyformat"
        sql = f"UPDATE signals SET status = 'processing' WHERE signal_id IN ({placeholders(len(ids), style)})"
        execute(conn, sql, tuple(ids))
        commit(conn)
    return signals


def ingestion_node(state: "GraphState") -> dict:
    if state.get("scenario_name") and not state.get("use_pending_signals"):
        return {"new_signals": []}
    try:
        init_db()
        with connect() as conn:
            signals = read_new_signals(conn)
    except Exception as exc:
        logger.warning("ingestion node used in-memory fallback: %s", exc)
        signals = []
    return {"new_signals": signals}
