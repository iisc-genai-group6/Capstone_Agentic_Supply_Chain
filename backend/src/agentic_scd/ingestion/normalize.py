from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from agentic_scd.ingestion.connectors.base import Connector, RawItem
from agentic_scd.ingestion.schema import DisruptionSignal, Location

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return WS_RE.sub(" ", TAG_RE.sub(" ", value)).strip()


def parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed: datetime | None = None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        parsed = None
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def extract_location(raw: RawItem) -> Location | None:
    if not raw.location:
        return None
    values = {key: raw.location.get(key) for key in ("region", "lat", "lon", "hub_port")}
    loc = Location(**values)
    return loc if loc.model_dump(exclude_none=True) else None


def normalize(raw: RawItem, connector: Connector) -> DisruptionSignal:
    payload = dict(raw.payload or {})
    title = clean_text(raw.title)
    body = clean_text(raw.body)
    return DisruptionSignal(
        signal_id=str(uuid.uuid4()),
        source=connector.name,
        source_type=connector.source_type,
        source_reliability=connector.reliability,
        fetched_at=datetime.now(UTC),
        event_time=parse_utc(raw.published),
        title=title or "Untitled supply-chain signal",
        raw_text=body,
        url=raw.url,
        location=extract_location(raw),
        severity_hint=payload.get("severity_hint") or payload.get("severity"),
        raw_payload=payload or None,
    )
