from __future__ import annotations

from pathlib import Path

from agentic_scd.config import Settings
from agentic_scd.db.client import connect

SCHEMA_SQL_PATH = Path(__file__).with_name("schema.sql")


def schema_sql() -> str:
    return SCHEMA_SQL_PATH.read_text(encoding="utf-8")


def init_db(settings: Settings | None = None) -> bool:
    try:
        with connect(settings) as conn:
            conn.executescript(schema_sql())
            conn.commit()
    except Exception:
        return False
    return True
