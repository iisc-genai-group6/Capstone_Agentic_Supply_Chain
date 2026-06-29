from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SourceType:
    RSS = "RSS"
    WEATHER = "WEATHER"
    FREIGHT_INDEX = "FREIGHT_INDEX"
    DATASET = "DATASET"
    SYNTHETIC = "SYNTHETIC"
    WEBHOOK = "WEBHOOK"


class RawItem(BaseModel):
    title: str = ""
    body: str = ""
    url: str | None = None
    published: str | None = None
    location: dict | None = None
    payload: dict = Field(default_factory=dict)


@runtime_checkable
class Connector(Protocol):
    name: str
    source_type: str
    reliability: float

    def fetch(self) -> list[RawItem]: ...

    def fallback(self) -> list[RawItem]: ...


def fetch_with_fallback(connector: Connector) -> tuple[list[RawItem], str]:
    try:
        items = connector.fetch()
        if items:
            return items, "live"
    except Exception as exc:
        logger.warning("%s live fetch failed: %s", connector.name, exc)
    items = connector.fallback()
    return items, "fallback"
