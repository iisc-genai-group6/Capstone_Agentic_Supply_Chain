from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from agentic_scd.ingestion.connectors.base import RawItem
from agentic_scd.ingestion.dedupe import assign_hash
from agentic_scd.ingestion.paths import RUN_DIR, SNAPSHOT_DIR
from agentic_scd.ingestion.schema import DisruptionSignal, Location

INSERT_SIGNAL = """
INSERT OR IGNORE INTO signals (
    signal_id, dedup_hash, source, source_type, source_reliability,
    fetched_at, event_time, title, raw_text, url,
    location, severity_hint, schema_version, raw_payload, status
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')
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


def row_to_signal(row) -> DisruptionSignal:
    location = json.loads(row["location"]) if row["location"] else None
    payload = json.loads(row["raw_payload"]) if row["raw_payload"] else None
    return DisruptionSignal(
        signal_id=row["signal_id"],
        dedup_hash=row["dedup_hash"],
        source=row["source"],
        source_type=row["source_type"],
        source_reliability=row["source_reliability"],
        fetched_at=parse_dt(row["fetched_at"]) or datetime.now(UTC),
        event_time=parse_dt(row["event_time"]),
        title=row["title"],
        raw_text=row["raw_text"] or "",
        url=row["url"],
        location=Location(**location) if location else None,
        severity_hint=row["severity_hint"],
        schema_version=row["schema_version"],
        raw_payload=payload,
    )


def persist_signal(conn, signal: DisruptionSignal) -> bool:
    if not signal.dedup_hash:
        assign_hash(signal)
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
    cur = conn.execute(INSERT_SIGNAL, args)
    return cur.rowcount > 0


def record_rejected(conn, dedup_hash_value: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO seen_rejected (dedup_hash) VALUES (?)",
        (dedup_hash_value,),
    )


def mark_done(conn, signal_ids: list[str]) -> None:
    if not signal_ids:
        return
    placeholders = ",".join("?" for _ in signal_ids)
    conn.execute(f"UPDATE signals SET status = 'done' WHERE signal_id IN ({placeholders})", signal_ids)


def write_snapshot(connector_name: str, raw_items: list[RawItem]) -> Path:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = SNAPSHOT_DIR / f"{connector_name}-{stamp}.json"
    path.write_text(
        json.dumps([item.model_dump() for item in raw_items], default=str, indent=2),
        encoding="utf-8",
    )
    return path


def save_run_result(conn, run_id: str, state: dict, scenario_name: str | None = None) -> Path:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    route = state.get("route", "unknown")
    classifications = state.get("classifications", []) or []
    max_severity = max((getattr(item, "severity", 0.0) for item in classifications), default=0.0)
    payload = json.dumps(serialize_state(state), default=str, indent=2)
    conn.execute(
        "INSERT OR REPLACE INTO pipeline_runs (run_id, scenario_name, route, max_severity, payload) VALUES (?, ?, ?, ?, ?)",
        (run_id, scenario_name, route, max_severity, payload),
    )
    conn.commit()
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
    rows = conn.execute(
        "SELECT run_id, created_at, scenario_name, route, max_severity, payload FROM pipeline_runs ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def recent_signals(conn, limit: int = 50) -> list[DisruptionSignal]:
    rows = conn.execute(
        "SELECT * FROM signals ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [row_to_signal(row) for row in rows]
