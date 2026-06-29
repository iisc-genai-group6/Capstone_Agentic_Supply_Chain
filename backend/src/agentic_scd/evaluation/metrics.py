from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from agentic_scd.__main__ import run


@dataclass
class EvaluationReport:
    classification_accuracy: float
    forecast_mape: float
    simulation_boundary_error: float
    recommendation_actions: int

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def mape(actual: list[float], predicted: list[float]) -> float:
    a = np.array(actual, dtype=float)
    p = np.array(predicted, dtype=float)
    denom = np.maximum(np.abs(a), 1.0)
    return float(np.mean(np.abs((a - p) / denom)))


def evaluate() -> EvaluationReport:
    state = run("Typhoon approaching Shanghai Port")
    classifications = state.get("classifications", [])
    expected = "weather"
    accuracy = 1.0 if classifications and classifications[0].category == expected else 0.0
    forecast = state.get("forecast")
    forecast_mape = mape(forecast.baseline, forecast.adjusted) if forecast else 0.0
    simulation = state.get("simulation")
    boundary = abs((simulation.stockout_probability if simulation else 0.0) - 0.90)
    rec = state.get("recommendation")
    actions = len(rec.actions) if rec else 0
    return EvaluationReport(round(accuracy, 4), round(forecast_mape, 4), round(boundary, 4), actions)


def main() -> None:
    report = evaluate()
    for key, value in report.as_dict().items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
