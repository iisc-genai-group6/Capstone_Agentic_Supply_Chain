from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from agentic_scd.ingestion.connectors.base import RawItem
from agentic_scd.ingestion.dedupe import assign_hash
from agentic_scd.ingestion.paths import RUN_DIR, SNAPSHOT_DIR
from agentic_scd.ingestion.schema import DisruptionSignal, Location
from agentic_scd.ingestion.sqlutil import commit, execute, placeholders

INSERT_SIGNAL_SQLITE = """
INSERT OR IGNORE INTO signals (
    signal_id, dedup_hash, source, source_type, source_reliability,
    fetched_at, event_time, title, raw_text, url,
    location, severity_hint, schema_version, raw_payload, status
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')
"""

INSERT_SIGNAL_PG = """
INSERT INTO signals (
    signal_id, dedup_hash, source, source_type, source_reliability,
    fetched_at, event_time, title, raw_text, url,
    location, severity_hint, schema_version, raw_payload, status
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'new')
ON CONFLICT (dedup_hash) DO NOTHING
"""


def dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat()


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def location_json(location) -> str | None:
    if not location:
        return None
    return json.dumps(location.model_dump(exclude_none=True), sort_keys=True)


def row_get(row, key: str, default=None):
    try:
        return row[key]
    except Exception:
        return default


def row_to_signal(row) -> DisruptionSignal:
    location = json.loads(row_get(row, "location")) if row_get(row, "location") else None
    payload = json.loads(row_get(row, "raw_payload")) if row_get(row, "raw_payload") else None
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
    if not signal.dedup_hash:
        assign_hash(signal)
    payload = json.dumps(signal.raw_payload or {}, sort_keys=True)
    if hasattr(conn, "execute"):
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
    else:
        args = {
            "signal_id": signal.signal_id,
            "dedup_hash": signal.dedup_hash,
            "source": signal.source,
            "source_type": signal.source_type,
            "source_reliability": signal.source_reliability,
            "fetched_at": dt(signal.fetched_at),
            "event_time": dt(signal.event_time),
            "title": signal.title,
            "raw_text": signal.raw_text,
            "url": signal.url,
            "location": location_json(signal.location),
            "severity_hint": signal.severity_hint,
            "schema_version": signal.schema_version,
            "raw_payload": payload,
        }
        cur = execute(conn, INSERT_SIGNAL_PG, args)
    return getattr(cur, "rowcount", 0) > 0


def record_rejected(conn, dedup_hash_value: str) -> None:
    if hasattr(conn, "execute"):
        execute(conn, "INSERT OR IGNORE INTO seen_rejected (dedup_hash) VALUES (?)", (dedup_hash_value,))
    else:
        execute(conn, "INSERT INTO seen_rejected (dedup_hash) VALUES (%s) ON CONFLICT (dedup_hash) DO NOTHING", (dedup_hash_value,))


def mark_done(conn, signal_ids: list[str]) -> None:
    if not signal_ids:
        return
    if hasattr(conn, "execute"):
        sql = f"UPDATE signals SET status = 'done' WHERE signal_id IN ({placeholders(len(signal_ids), 'sqlite')})"
    else:
        sql = f"UPDATE signals SET status = 'done' WHERE signal_id IN ({placeholders(len(signal_ids), 'pyformat')})"
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
    payload = json.dumps(serialize_state(state), default=str, indent=2)
    execute(conn, "INSERT OR REPLACE INTO pipeline_runs (run_id, scenario_name, route, max_severity, payload) VALUES (?, ?, ?, ?, ?)", (run_id, scenario_name, route, max_severity, payload))
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


def recent_runs(conn, limit: int = 10) -> list[dict]:
    rows = execute(conn, "SELECT run_id, created_at, scenario_name, route, max_severity, payload FROM pipeline_runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(row) for row in rows]


def recent_signals(conn, limit: int = 50) -> list[DisruptionSignal]:
    rows = execute(conn, "SELECT * FROM signals ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [row_to_signal(row) for row in rows]
