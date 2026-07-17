from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from agentic_scd.__main__ import run
from agentic_scd.config import get_settings
from agentic_scd.rag.retriever import retriever_stats


@dataclass
class EvaluationReport:
    classification_accuracy: float
    forecast_mape: float
    simulation_boundary_error: float
    recommendation_actions: int
    weather_coverage: float
    retrieval_documents: int

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def mape(actual: list[float], predicted: list[float]) -> float:
    a = np.array(actual, dtype=float)
    p = np.array(predicted, dtype=float)
    denom = np.maximum(np.abs(a), 1.0)
    return float(np.mean(np.abs((a - p) / denom)))


def evaluate() -> EvaluationReport:
    get_settings.cache_clear()
    try:
        weather_state = run("Typhoon approaching Shanghai Port")
        policy_state = run("Tariff policy change")
        weather_rows = weather_state.get("classifications", [])
        policy_rows = policy_state.get("classifications", [])
        accuracy = np.mean(
            [
                1.0 if weather_rows and weather_rows[0].category == "weather" else 0.0,
                1.0 if policy_rows and policy_rows[0].category in {"policy", "geopolitical"} else 0.0,
            ]
        )
        forecast = policy_state.get("forecast")
        forecast_mape = mape(forecast.baseline, forecast.adjusted) if forecast else 0.0
        simulation = weather_state.get("simulation")
        boundary = abs((simulation.stockout_probability if simulation else 0.0) - 0.75)
        rec = weather_state.get("recommendation")
        actions = len(rec.actions) if rec else 0
        weather_coverage = 1.0 if weather_state.get("weather_risks") else 0.0
        stats = retriever_stats()
        corpus = int(stats["impact_documents"]) + int(stats["mitigation_documents"]) + int(stats["history_documents"])
        return EvaluationReport(round(float(accuracy), 4), round(forecast_mape, 4), round(boundary, 4), actions, round(weather_coverage, 4), corpus)
    finally:
        get_settings.cache_clear()


def main() -> None:
    report = evaluate()
    for key, value in report.as_dict().items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
