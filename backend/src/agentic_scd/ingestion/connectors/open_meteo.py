from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from agentic_scd.ingestion.connectors.base import RawItem, SourceType

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
DAILY = "weather_code,wind_speed_10m_max,precipitation_sum"
WMO: dict[int, tuple[str, str]] = {
    0: ("clear sky", "none"),
    1: ("mainly clear", "none"),
    2: ("partly cloudy", "none"),
    3: ("overcast", "none"),
    45: ("fog", "low"),
    61: ("rain", "low"),
    63: ("heavy rain causing flood risk", "moderate"),
    65: ("heavy rain and flooding disruption", "severe"),
    71: ("snowfall", "moderate"),
    75: ("heavy snow storm", "severe"),
    82: ("violent storm with flooding", "severe"),
    95: ("thunderstorm", "severe"),
    99: ("severe thunderstorm with gale-force wind", "severe"),
}


class OpenMeteoConnector:
    source_type = SourceType.WEATHER

    def __init__(self, name: str, reliability: float, hubs: list[dict[str, Any]], fallback_path: Path | None = None) -> None:
        self.name = name
        self.reliability = reliability
        self.hubs = list(hubs)
        self.fallback_path = fallback_path

    @staticmethod
    def hub_item(hub: dict[str, Any], response: dict[str, Any]) -> RawItem:
        daily = response.get("daily", {})
        code = int((daily.get("weather_code") or [0])[0])
        wind = (daily.get("wind_speed_10m_max") or [None])[0]
        precip = (daily.get("precipitation_sum") or [None])[0]
        phrase, hint = WMO.get(code, ("unsettled weather", "low"))
        place = hub.get("hub_port") or hub.get("region") or "configured hub"
        body = f"Forecast {phrase} at {place}. Max wind {wind} km/h and precipitation {precip} mm."
        if hint in {"moderate", "severe"}:
            body += " Conditions may disrupt port and shipping operations."
        return RawItem(
            title=f"Weather forecast for {place}: {phrase}",
            body=body,
            published=(daily.get("time") or [None])[0],
            location={"region": hub.get("region"), "lat": hub.get("lat"), "lon": hub.get("lon"), "hub_port": hub.get("hub_port")},
            payload={"hub": hub, "response": response, "severity_hint": hint},
        )

    def fetch(self) -> list[RawItem]:
        items: list[RawItem] = []
        with httpx.Client(timeout=10.0) as client:
            for hub in self.hubs:
                response = client.get(
                    FORECAST_URL,
                    params={"latitude": hub["lat"], "longitude": hub["lon"], "daily": DAILY, "forecast_days": 1},
                )
                response.raise_for_status()
                items.append(self.hub_item(hub, response.json()))
        return items

    def fallback(self) -> list[RawItem]:
        if not self.fallback_path or not self.fallback_path.exists():
            return []
        snapshot = json.loads(self.fallback_path.read_text(encoding="utf-8"))
        return [self.hub_item(row["hub"], row["response"]) for row in snapshot]
