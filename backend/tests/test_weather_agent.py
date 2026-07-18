"""Weather Risk Monitoring agent — offline, driven by the packaged fallback snapshot."""

import json
from datetime import UTC, datetime

from agentic_scd.agents.classify import classify_node
from agentic_scd.agents.schema import WeatherRiskAssessment
from agentic_scd.agents.weather import assess_weather_signal, weather_node
from agentic_scd.ingestion.paths import FALLBACK_DIR
from agentic_scd.ingestion.schema import DisruptionSignal, Location
from agentic_scd.ingestion.weather.core import parse_daily_series


def load_snapshot() -> list[dict]:
    return json.loads((FALLBACK_DIR / "open_meteo_hubs.json").read_text(encoding="utf-8"))


def weather_signal(row: dict, signal_id: str = "wx-1") -> DisruptionSignal:
    hub = row["hub"]
    return DisruptionSignal(
        signal_id=signal_id,
        source="open_meteo",
        source_type="WEATHER",
        source_reliability=0.9,
        fetched_at=datetime.now(UTC),
        title=f"Weather forecast for {hub['hub_port']}",
        raw_text="",
        location=Location(**hub),
        severity_hint="severe",
        raw_payload={"hub": hub, "response": row["response"]},
    )


def rss_signal() -> DisruptionSignal:
    return DisruptionSignal(
        signal_id="rss-1",
        source="stub",
        source_type="RSS",
        fetched_at=datetime.now(UTC),
        title="Port strike halts shipments",
        raw_text="freight delay",
    )


def shanghai_row() -> dict:
    return next(row for row in load_snapshot() if row["hub"]["hub_port"] == "Port of Shanghai")


def test_parse_daily_series_yields_seven_days() -> None:
    for row in load_snapshot():
        days = parse_daily_series(row["hub"], row["response"])
        assert len(days) == 7


def test_assess_weather_signal_flags_severe_hub() -> None:
    assessment = assess_weather_signal(weather_signal(shanghai_row()))
    assert isinstance(assessment, WeatherRiskAssessment)
    assert assessment.horizon_days == 7
    assert assessment.aggregate_severity >= 7.0
    assert assessment.port_disruption_risk >= 0.6
    assert "port_ops" in assessment.affected_operations
    assert assessment.peak_day


def test_assess_non_weather_signal_returns_none() -> None:
    assert assess_weather_signal(rss_signal()) is None


def test_weather_node_over_weather_signal() -> None:
    out = weather_node({"new_signals": [weather_signal(shanghai_row())]})
    assert len(out["weather_risks"]) == 1


def test_weather_node_ignores_non_weather_signals() -> None:
    out = weather_node({"new_signals": [rss_signal()]})
    assert out["weather_risks"] == []


def test_classify_severity_boosted_by_weather() -> None:
    # Use hint=low and lower reliability so the plain severity stays well
    # below 10.0, leaving headroom for the weather boost to be visible.
    # (The original test used hint=severe which already saturates at 10.0.)
    row = shanghai_row()
    hub = row["hub"]
    from datetime import UTC, datetime
    from agentic_scd.ingestion.schema import DisruptionSignal, Location
    signal = DisruptionSignal(
        signal_id="wx-boost-test",
        source="open_meteo",
        source_type="WEATHER",
        source_reliability=0.5,
        fetched_at=datetime.now(UTC),
        title=f"Weather forecast for {hub['hub_port']}",
        raw_text="",
        location=Location(**hub),
        severity_hint="low",
        raw_payload={"hub": hub, "response": row["response"]},
    )
    risks = weather_node({"new_signals": [signal]})["weather_risks"]

    boosted = classify_node({"new_signals": [signal], "weather_risks": risks})["classifications"][0]
    plain   = classify_node({"new_signals": [signal]})["classifications"][0]

    assert boosted.category == "weather"
    assert boosted.severity > plain.severity, (
        f"Weather boost not visible: plain={plain.severity} boosted={boosted.severity}. "
        "Hint and reliability must keep plain severity below 10.0 so boost has headroom."
    )

def test_classify_weather_enriches_confidence_and_rationale() -> None:
    signal = weather_signal(shanghai_row())
    risks = weather_node({"new_signals": [signal]})["weather_risks"]

    boosted = classify_node({"new_signals": [signal], "weather_risks": risks})["classifications"][0]
    plain   = classify_node({"new_signals": [signal]})["classifications"][0]

    assert boosted.category == "weather"
    assert boosted.confidence > plain.confidence
    assert "7-day hub forecast" in boosted.rationale
