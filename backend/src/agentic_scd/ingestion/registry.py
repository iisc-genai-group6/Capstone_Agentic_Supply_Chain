from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from agentic_scd.ingestion.connectors.base import Connector, SourceType
from agentic_scd.ingestion.connectors.open_meteo import OpenMeteoConnector
from agentic_scd.ingestion.connectors.rss import RssConnector
from agentic_scd.ingestion.connectors.synthetic import SyntheticConnector
from agentic_scd.ingestion.paths import ASSET_DIR, PROJECT_ROOT, SOURCES_YAML


def resolve_path(rel: str | None) -> Path | None:
    if not rel:
        return None
    candidate = Path(rel)
    if candidate.is_absolute():
        return candidate
    asset_candidate = ASSET_DIR / candidate
    trimmed_asset = ASSET_DIR / Path(*candidate.parts[1:]) if candidate.parts and candidate.parts[0] == "data" else asset_candidate
    for path in (Path.cwd() / candidate, PROJECT_ROOT / candidate, asset_candidate, trimmed_asset):
        if path.exists():
            return path
    return trimmed_asset


def build_rss(entry: dict[str, Any]) -> RssConnector:
    cfg = entry.get("config", {})
    return RssConnector(entry["name"], entry["reliability"], cfg.get("feeds", []), cfg.get("queries", []), resolve_path(entry.get("fallback_path")))


def build_open_meteo(entry: dict[str, Any]) -> OpenMeteoConnector:
    cfg = entry.get("config", {})
    return OpenMeteoConnector(entry["name"], entry["reliability"], cfg.get("hubs", []), resolve_path(entry.get("fallback_path")))


def build_synthetic(entry: dict[str, Any]) -> SyntheticConnector:
    cfg = entry.get("config", {})
    return SyntheticConnector(entry["name"], entry["reliability"], cfg.get("count", 3))


BUILDERS: dict[str, Callable[[dict[str, Any]], Connector]] = {
    SourceType.RSS: build_rss,
    SourceType.WEATHER: build_open_meteo,
    SourceType.SYNTHETIC: build_synthetic,
}


def load_registry(path: str | Path | None = None) -> list[Connector]:
    registry_path = Path(path) if path else SOURCES_YAML
    doc = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    connectors: list[Connector] = []
    for entry in doc.get("sources", []):
        if not entry.get("enabled", True):
            continue
        builder = BUILDERS.get(entry["type"])
        if builder is None:
            raise ValueError(f"unknown source type {entry['type']!r}")
        connectors.append(builder(entry))
    return connectors
