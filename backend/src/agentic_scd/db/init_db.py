from __future__ import annotations

from pathlib import Path

from agentic_scd.config import Settings
from agentic_scd.db.client import connect

SCHEMA_SQL_PATH = Path(__file__).with_name("schema.sql")

POSTGRES_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS signals (
    signal_id TEXT PRIMARY KEY,
    dedup_hash TEXT UNIQUE,
    source TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_reliability DOUBLE PRECISION,
    fetched_at TIMESTAMPTZ NOT NULL,
    event_time TIMESTAMPTZ,
    title TEXT NOT NULL,
    raw_text TEXT NOT NULL DEFAULT '',
    url TEXT,
    location JSONB,
    severity_hint TEXT,
    schema_version INTEGER NOT NULL,
    raw_payload JSONB,
    status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'processing', 'done')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_signals_status ON signals (status);
CREATE INDEX IF NOT EXISTS idx_signals_dedup_hash ON signals (dedup_hash);
CREATE TABLE IF NOT EXISTS seen_rejected (
    dedup_hash TEXT PRIMARY KEY,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    scenario_name TEXT,
    route TEXT,
    max_severity DOUBLE PRECISION,
    payload JSONB NOT NULL
);
"""


def schema_sql() -> str:
    return SCHEMA_SQL_PATH.read_text(encoding="utf-8")


def init_db(settings: Settings | None = None) -> bool:
    try:
        with connect(settings) as conn:
            if getattr(conn, "agentic_scd_dialect", None) == "sqlite":
                conn.executescript(schema_sql())
            else:
                with conn.cursor() as cur:
                    cur.execute(POSTGRES_SCHEMA_SQL)
            conn.commit()
    except Exception:
        return False
    return True
