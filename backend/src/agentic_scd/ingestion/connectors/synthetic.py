from __future__ import annotations

from agentic_scd.ingestion.connectors.base import RawItem, SourceType

SCENARIOS = [
    {
        "title": "Port strike halts container shipments at major hub",
        "body": "A labor strike has stopped container handling, causing shipping delays and port congestion expected to ripple across supply chains.",
        "severity_hint": "high",
        "region": "USA",
    },
    {
        "title": "Typhoon forces factory shutdown across manufacturing region",
        "body": "A typhoon warning has triggered a factory shutdown and a temporary blockade of inland freight routes, threatening component shortages.",
        "severity_hint": "severe",
        "region": "China",
    },
    {
        "title": "New tariff disrupts cross-border supplier logistics",
        "body": "A newly announced tariff has disrupted supplier logistics, with embargo concerns and product recall risk compounding shortage exposure.",
        "severity_hint": "moderate",
        "region": "North America",
    },
    {
        "title": "Supplier quality failure creates raw material shortage",
        "body": "A supplier failed inspection with a high defect rate and delayed replacement batches, creating shortage risk for production.",
        "severity_hint": "moderate",
        "region": "India",
    },
]


class SyntheticConnector:
    source_type = SourceType.SYNTHETIC

    def __init__(self, name: str, reliability: float, count: int = 3) -> None:
        self.name = name
        self.reliability = reliability
        self.count = count

    def build_items(self) -> list[RawItem]:
        items = [SCENARIOS[i % len(SCENARIOS)] for i in range(self.count)]
        return [
            RawItem(
                title=item["title"],
                body=item["body"],
                location={"region": item["region"]},
                payload={"scenario_index": i, "severity_hint": item["severity_hint"], **item},
            )
            for i, item in enumerate(items)
        ]

    def fetch(self) -> list[RawItem]:
        return self.build_items()

    def fallback(self) -> list[RawItem]:
        return self.build_items()
