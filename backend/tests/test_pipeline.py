from __future__ import annotations

from agentic_scd.__main__ import run


def test_typhoon_scenario_runs_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_SCD_HOME", str(tmp_path))
    state = run("Typhoon approaching Shanghai Port")
    assert state["new_signals"]
    assert state["classifications"][0].category == "weather"
    assert state["simulation"].stockout_probability > 0
    assert state["recommendation"].actions


def test_labor_scenario_is_high_risk(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_SCD_HOME", str(tmp_path))
    state = run("Packaging supplier labor strike")
    categories = {item.category for item in state["classifications"]}
    assert "labor_strike" in categories
    assert max(item.severity for item in state["classifications"]) >= 7
