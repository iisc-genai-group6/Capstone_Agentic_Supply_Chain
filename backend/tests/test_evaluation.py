from __future__ import annotations

from agentic_scd.evaluation.metrics import evaluate


def test_evaluation_report_has_expected_metrics(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_SCD_HOME", str(tmp_path))
    report = evaluate()
    assert report.classification_accuracy >= 0.9
    assert report.forecast_mape < 0.2
    assert report.recommendation_actions >= 1
