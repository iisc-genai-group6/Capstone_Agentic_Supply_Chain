from __future__ import annotations

from datetime import UTC, datetime

from agentic_scd.agents.schema import EventAnalysis, ImpactMap, WeatherRiskAssessment
from agentic_scd.ingestion.schema import DisruptionSignal, Location
from agentic_scd.ui.gradio_app import analysis_table, impact_table, signals_table, weather_table


def make_signal() -> DisruptionSignal:
    return DisruptionSignal(
        signal_id="sig-1",
        source="test",
        source_type="RSS",
        source_reliability=0.8,
        fetched_at=datetime(2026, 7, 12, 10, 30, tzinfo=UTC),
        event_time=datetime(2026, 7, 11, 8, 15, tzinfo=UTC),
        title="Port strike delays Rotterdam shipments",
        raw_text="Port strike and shipping congestion are delaying containers.",
        location=Location(region="Netherlands", hub_port="Port of Rotterdam"),
    )


def test_event_dates_are_shown_across_dashboard_event_tables() -> None:
    signal = make_signal()
    state = {
        "new_signals": [signal],
        "event_analyses": [
            EventAnalysis(
                signal_id=signal.signal_id,
                event_type="logistics_disruption",
                extracted_region="Netherlands",
            )
        ],
        "weather_risks": [
            WeatherRiskAssessment(
                signal_id=signal.signal_id,
                hub_port="Port of Rotterdam",
                region="Netherlands",
            )
        ],
        "impacts": [
            ImpactMap(
                signal_id=signal.signal_id,
                affected_suppliers=["Supplier A"],
                affected_lanes=["Rotterdam-New York"],
            )
        ],
    }
    expected = "2026-07-11 08:15 UTC"

    signals = signals_table(state)
    analysis = analysis_table(state)
    weather = weather_table(state)
    impact = impact_table(state)

    assert signals.loc[0, "event_date"] == expected
    assert analysis.loc[0, "event_date"] == expected
    assert weather.loc[0, "event_date"] == expected
    assert impact.loc[0, "event_date"] == expected
