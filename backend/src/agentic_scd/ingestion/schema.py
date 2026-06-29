from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

SCHEMA_VERSION = 3


class Location(BaseModel):
    region: str | None = None
    lat: float | None = None
    lon: float | None = None
    hub_port: str | None = None


class DisruptionSignal(BaseModel):
    signal_id: str
    dedup_hash: str | None = None
    source: str
    source_type: str
    source_reliability: float | None = None
    fetched_at: datetime
    event_time: datetime | None = None
    title: str
    raw_text: str = ""
    url: str | None = None
    location: Location | None = None
    severity_hint: str | None = None
    raw_payload: dict | None = None
    schema_version: int = SCHEMA_VERSION
    category: str | None = None
    severity: float | None = Field(default=None, ge=0, le=10)
    affected_entities: list[str] | None = None

    @property
    def text(self) -> str:
        return f"{self.title} {self.raw_text}".strip()

    @property
    def region(self) -> str | None:
        if self.location and self.location.region:
            return self.location.region
        payload = self.raw_payload or {}
        value = payload.get("region") or payload.get("Location")
        return str(value) if value else None
