from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from agentic_scd.ingestion.connectors.base import RawItem
from agentic_scd.ingestion.dedupe import assign_hash
from agentic_scd.ingestion.paths import RUN_DIR, SNAPSHOT_DIR
from agentic_scd.ingestion.schema import DisruptionSignal, Location
from agentic_scd.ingestion.sqlutil import commit, dialect, execute, placeholders

INSERT_SIGNAL_SQLITE = """
INSERT OR IGNORE INTO signals (
    signal_id, dedup_hash, source, source_type, source_reliability,
    fetched_at, event_time, title, raw_text, url,
    location, severity_hint, schema_version, raw_payload, status
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')
"""


SIGNAL_COLUMNS = [
    "signal_id",
    "dedup_hash",
    "source",
    "source_type",
    "source_reliability",
    "fetched_at",
    "event_time",
    "title",
    "raw_text",
    "url",
    "location",
    "severity_hint",
    "schema_version",
    "raw_payload",
    "status",
    "created_at",
]

RUN_COLUMNS = ["run_id", "created_at", "scenario_name", "route", "max_severity", "payload"]

INSERT_SIGNAL_PG = """
INSERT INTO signals (
    signal_id, dedup_hash, source, source_type, source_reliability,
    fetched_at, event_time, title, raw_text, url,
    location, severity_hint, schema_version, raw_payload, status
) VALUES (
    %(signal_id)s, %(dedup_hash)s, %(source)s, %(source_type)s, %(source_reliability)s,
    %(fetched_at)s, %(event_time)s, %(title)s, %(raw_text)s, %(url)s,
    %(location)s, %(severity_hint)s, %(schema_version)s, %(raw_payload)s, 'new'
)
ON CONFLICT (dedup_hash) DO NOTHING
"""


def json_adapter(value):
    if value is None:
        return None
    try:
        from psycopg.types.json import Json
        return Json(value)
    except Exception:
        return value


def dt(value: datetime | None):
    if value is None:
        return None
    return value.astimezone(UTC).isoformat()


def parse_dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def location_json(location) -> str | None:
    if not location:
        return None
    return json.dumps(location.model_dump(exclude_none=True), sort_keys=True)


def row_get(row, key: str, default=None):
    if row is None:
        return default
    try:
        return row[key]
    except Exception:
        pass
    if isinstance(row, tuple) and key in SIGNAL_COLUMNS:
        index = SIGNAL_COLUMNS.index(key)
        if index < len(row):
            return row[index]
    return default


def parse_json_value(value):
    if value is None or value == "":
        return None
    if isinstance(value, dict):
        return value
    return json.loads(value)


def row_to_signal(row) -> DisruptionSignal:
    location = parse_json_value(row_get(row, "location"))
    payload = parse_json_value(row_get(row, "raw_payload"))
    return DisruptionSignal(
        signal_id=row_get(row, "signal_id"),
        dedup_hash=row_get(row, "dedup_hash"),
        source=row_get(row, "source"),
        source_type=row_get(row, "source_type"),
        source_reliability=row_get(row, "source_reliability"),
        fetched_at=parse_dt(row_get(row, "fetched_at")) or datetime.now(UTC),
        event_time=parse_dt(row_get(row, "event_time")),
        title=row_get(row, "title"),
        raw_text=row_get(row, "raw_text", "") or "",
        url=row_get(row, "url"),
        location=Location(**location) if location else None,
        severity_hint=row_get(row, "severity_hint"),
        schema_version=row_get(row, "schema_version"),
        raw_payload=payload,
    )


def persist_signal(conn, signal: DisruptionSignal) -> bool:
    if conn is None:
        return False
    if not signal.dedup_hash:
        assign_hash(signal)
    if dialect(conn) == "sqlite":
        payload = json.dumps(signal.raw_payload or {}, sort_keys=True)
        args = (
            signal.signal_id,
            signal.dedup_hash,
            signal.source,
            signal.source_type,
            signal.source_reliability,
            dt(signal.fetched_at),
            dt(signal.event_time),
            signal.title,
            signal.raw_text,
            signal.url,
            location_json(signal.location),
            signal.severity_hint,
            signal.schema_version,
            payload,
        )
        cur = execute(conn, INSERT_SIGNAL_SQLITE, args)
        return getattr(cur, "rowcount", 0) > 0
    params = {
        "signal_id": signal.signal_id,
        "dedup_hash": signal.dedup_hash,
        "source": signal.source,
        "source_type": signal.source_type,
        "source_reliability": signal.source_reliability,
        "fetched_at": signal.fetched_at,
        "event_time": signal.event_time,
        "title": signal.title,
        "raw_text": signal.raw_text,
        "url": signal.url,
        "location": json_adapter(signal.location.model_dump(exclude_none=True) if signal.location else None),
        "severity_hint": signal.severity_hint,
        "schema_version": signal.schema_version,
        "raw_payload": json_adapter(signal.raw_payload or {}),
    }
    cur = execute(conn, INSERT_SIGNAL_PG, params)
    return getattr(cur, "rowcount", 0) > 0


def record_rejected(conn, dedup_hash_value: str) -> None:
    if conn is None:
        return
    if dialect(conn) == "sqlite":
        execute(conn, "INSERT OR IGNORE INTO seen_rejected (dedup_hash) VALUES (?)", (dedup_hash_value,))
    else:
        execute(conn, "INSERT INTO seen_rejected (dedup_hash) VALUES (%s) ON CONFLICT (dedup_hash) DO NOTHING", (dedup_hash_value,))


def mark_done(conn, signal_ids: list[str]) -> None:
    if not signal_ids or conn is None:
        return
    style = "sqlite" if dialect(conn) == "sqlite" else "pyformat"
    sql = f"UPDATE signals SET status = 'done' WHERE signal_id IN ({placeholders(len(signal_ids), style)})"
    execute(conn, sql, tuple(signal_ids))


def write_snapshot(connector_name: str, raw_items: list[RawItem]) -> Path:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = SNAPSHOT_DIR / f"{connector_name}-{stamp}.json"
    path.write_text(json.dumps([item.model_dump() for item in raw_items], default=str, indent=2), encoding="utf-8")
    return path


def save_run_result(conn, run_id: str, state: dict, scenario_name: str | None = None) -> Path:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    route = state.get("route", "unknown")
    classifications = state.get("classifications", []) or []
    max_severity = max((getattr(item, "severity", 0.0) for item in classifications), default=0.0)
    serialized = serialize_state(state)
    payload = json.dumps(serialized, default=str, indent=2)
    if conn is not None:
        if dialect(conn) == "sqlite":
            execute(conn, "INSERT OR REPLACE INTO pipeline_runs (run_id, scenario_name, route, max_severity, payload) VALUES (?, ?, ?, ?, ?)", (run_id, scenario_name, route, max_severity, payload))
        else:
            execute(conn, "INSERT INTO pipeline_runs (run_id, scenario_name, route, max_severity, payload) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (run_id) DO UPDATE SET scenario_name = EXCLUDED.scenario_name, route = EXCLUDED.route, max_severity = EXCLUDED.max_severity, payload = EXCLUDED.payload", (run_id, scenario_name, route, max_severity, json_adapter(serialized)))
        commit(conn)
    path = RUN_DIR / f"{run_id}.json"
    path.write_text(payload, encoding="utf-8")
    return path


def serialize_state(state: dict) -> dict:
    out: dict = {}
    for key, value in state.items():
        if isinstance(value, list):
            out[key] = [serialize_item(item) for item in value]
        else:
            out[key] = serialize_item(value)
    return out


def serialize_item(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def row_to_dict(row) -> dict:
    if isinstance(row, dict):
        return row
    try:
        return dict(row)
    except Exception:
        pass
    if isinstance(row, tuple):
        return dict(zip(RUN_COLUMNS, row))
    return {}


def recent_runs(conn, limit: int = 10) -> list[dict]:
    if conn is None:
        return []
    if dialect(conn) == "sqlite":
        rows = execute(conn, "SELECT run_id, created_at, scenario_name, route, max_severity, payload FROM pipeline_runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    else:
        rows = execute(conn, "SELECT run_id, created_at, scenario_name, route, max_severity, payload FROM pipeline_runs ORDER BY created_at DESC LIMIT %s", (limit,)).fetchall()
    out = []
    for row in rows:
        item = row_to_dict(row)
        out.append(item)
    return out


def recent_signals(conn, limit: int = 50) -> list[DisruptionSignal]:
    if conn is None:
        return []
    if dialect(conn) == "sqlite":
        rows = execute(conn, "SELECT * FROM signals ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    else:
        rows = execute(conn, "SELECT * FROM signals ORDER BY created_at DESC LIMIT %s", (limit,)).fetchall()
    return [row_to_signal(row) for row in rows]
