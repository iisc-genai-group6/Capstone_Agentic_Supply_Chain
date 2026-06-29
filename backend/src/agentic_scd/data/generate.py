from __future__ import annotations

import json
from pathlib import Path

from agentic_scd.config import get_settings

LABELS = {
    "weather": ["storm closes port", "flooding blocks roads", "typhoon disrupts factory", "gale force winds delay shipping"],
    "geopolitical": ["tariff raises landed cost", "sanction blocks supplier", "embargo delays customs", "border tension slows freight"],
    "logistics": ["port congestion creates backlog", "freight rate surge delays orders", "container shortage hits lane", "carrier rollover delays cargo"],
    "raw_material": ["ingredient shortage slows production", "supplier outage affects component", "recall reduces available stock", "factory shutdown cuts capacity"],
    "demand_shock": ["unexpected promotion lifts demand", "panic buying drains inventory", "forecast error creates spike", "retailer order surge strains stock"],
    "labor_strike": ["union strike stops port", "warehouse walkout delays picking", "driver strike blocks deliveries", "factory labor stoppage cuts output"],
}


def generate_events(path: Path | None = None, per_class: int = 50) -> Path:
    settings = get_settings()
    out = path or settings.data_dir / "synthetic_disruption_events.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for label, phrases in LABELS.items():
        for idx in range(per_class):
            phrase = phrases[idx % len(phrases)]
            rows.append({"description": f"{phrase.title()} in region {idx % 9}. Analysts expect service-level pressure and mitigation review.", "region": f"Region {idx % 9}", "severity": 1 + (idx * 3) % 10, "label": label})
    out.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    return out


def main() -> None:
    path = generate_events()
    print(f"Generated synthetic training events at {path}")


if __name__ == "__main__":
    main()
