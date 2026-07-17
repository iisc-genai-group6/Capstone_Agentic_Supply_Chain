from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from agentic_scd.ingestion.connectors.base import RawItem
from agentic_scd.ingestion.connectors.synthetic import SyntheticConnector
from agentic_scd.ingestion.paths import FALLBACK_DIR
from agentic_scd.ingestion.schema import DisruptionSignal, Location
from agentic_scd.ingestion.normalize import normalize
from agentic_scd.ingestion.paths import SEED_DIR

if TYPE_CHECKING:
    from agentic_scd.graph.state import GraphState


def weather_scenario_signal(row: dict):
    path = FALLBACK_DIR / "open_meteo_hubs.json"
    if not path.exists():
        return None
    snapshots = json.loads(path.read_text(encoding="utf-8"))
    text = " ".join(str(row.get(key, "")) for key in ("name", "title", "body")).lower()
    region = str(row.get("region", "")).lower()
    snapshot = None
    for item in snapshots:
        hub = item.get("hub", {})
        hub_port = str(hub.get("hub_port", "")).lower()
        if hub_port and hub_port in text:
            snapshot = item
            break
    if snapshot is None:
        snapshot = next(
            (item for item in snapshots if str(item.get("hub", {}).get("region", "")).lower() == region),
            None,
        )
    if snapshot is None:
        return None
    hub = snapshot["hub"]
    payload = {
        "severity_hint": "high" if row.get("severity", 0) >= 7 else "moderate",
        **row,
        "hub": hub,
        "response": snapshot["response"],
    }
    return DisruptionSignal(
        signal_id=str(uuid.uuid4()),
        source="scenario_library",
        source_type="WEATHER",
        source_reliability=0.8,
        fetched_at=datetime.now(UTC),
        title=row["title"],
        raw_text=row["body"],
        location=Location(**hub),
        severity_hint=str(payload["severity_hint"]),
        raw_payload=payload,
    )


def scenario_signal(name: str):
    path = SEED_DIR / "scenarios.json"
    if not path.exists():
        return None
    rows = json.loads(path.read_text(encoding="utf-8"))
    for row in rows:
        if row.get("name") == name:
            if row.get("category") == "weather":
                signal = weather_scenario_signal(row)
                if signal is not None:
                    return signal
            connector = SyntheticConnector("scenario_library", 0.8, 1)
            raw = RawItem(
                title=row["title"],
                body=row["body"],
                location={"region": row.get("region")},
                payload={"severity_hint": "high" if row.get("severity", 0) >= 7 else "moderate", **row},
            )
            return normalize(raw, connector)
    return None


def _pick_seed_scenario() -> dict:
    """Pick a scenario from scenarios.json keyed by the current hour so the
    seed rotates across runs during the day instead of always returning the
    same hardcoded signal.  Falls back to a safe default if the file is
    missing.

    Only scenarios with severity >= 4.0 are considered — low-severity entries
    route to monitor_only which skips the impact and forecast agents, breaking
    the assumption that a no-scenario run always exercises the full pipeline.
    """
    path = SEED_DIR / "scenarios.json"
    if path.exists():
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
            # Filter to MEDIUM+ severity only so fallback always takes full_path
            eligible = [r for r in rows if r.get("severity", 0) >= 4.0]
            if eligible:
                idx = datetime.now(UTC).hour % len(eligible)
                return eligible[idx]
        except Exception:
            pass
    # Absolute fallback — only reached if scenarios.json is missing
    return {
        "title": "Supply chain disruption signal detected",
        "body": "An unspecified supply chain disruption has been detected affecting logistics and inventory levels.",
        "region": "Global",
        "severity": 5.0,
    }


def seed_node(state: "GraphState") -> dict:
    if state.get("new_signals"):
        return {}
    scenario_name = state.get("scenario_name")
    if scenario_name:
        signal = scenario_signal(scenario_name)
        if signal:
            return {"new_signals": [signal]}

    # No named scenario and no live signals found from feeds.
    # Inject a rotating fallback signal so the pipeline always has something
    # to run on, but label it explicitly as a seed fallback so the dashboard
    # and logs make clear this is NOT a real live disruption signal.
    row = _pick_seed_scenario()
    # Use a distinct source name so the signals table shows "seed_fallback"
    # rather than "demo_seed" or "SYNTHETIC", making it immediately clear
    # in the demo that live feeds returned nothing and this is a placeholder.
    connector = SyntheticConnector(name="seed_fallback", reliability=0.7, count=1)
    raw = RawItem(
        title=row["title"],
        body=row["body"],
        location={"region": row.get("region", "Global")},
        payload={
            "severity_hint": "high" if row.get("severity", 0) >= 7 else "moderate",
            "fallback_seed": True,   # flag for UI display
            "fallback_reason": "No live signals found from configured feeds — using seed scenario as fallback.",
            **row,
        },
    )
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "seed_node: no live signals found — injecting seed fallback '%s' (region: %s). "
        "Run 'agentic-scd-collect' to populate the database with fresh feed data.",
        row["title"], row.get("region", "Global"),
    )
    return {"new_signals": [normalize(raw, connector)]}
