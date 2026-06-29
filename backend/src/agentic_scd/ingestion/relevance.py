from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from agentic_scd.ingestion.paths import LEXICON_YAML
from agentic_scd.ingestion.schema import DisruptionSignal


@lru_cache(maxsize=8)
def load_lexicon(path: str | Path | None = None) -> tuple[str, ...]:
    lexicon_path = Path(path) if path else LEXICON_YAML
    doc = yaml.safe_load(lexicon_path.read_text(encoding="utf-8")) or {}
    return tuple(str(item).lower() for item in doc.get("keywords", []))


def passes_lexicon(signal: DisruptionSignal, lexicon: tuple[str, ...] | None = None) -> bool:
    terms = lexicon if lexicon is not None else load_lexicon()
    haystack = signal.text.lower()
    if signal.source_type == "WEATHER" and str(signal.severity_hint or "none").lower() in {"none", "low"}:
        severe_terms = ("storm", "flood", "typhoon", "gale", "snow", "thunderstorm")
        return any(term in haystack for term in severe_terms)
    return any(term in haystack for term in terms)


def is_relevant(signal: DisruptionSignal, lexicon: tuple[str, ...] | None = None) -> bool:
    return bool(signal.source) and passes_lexicon(signal, lexicon)

def gate(signals: list[DisruptionSignal], lexicon: tuple[str, ...] | None = None) -> tuple[list[DisruptionSignal], list[DisruptionSignal]]:
    terms = lexicon if lexicon is not None else load_lexicon()
    kept: list[DisruptionSignal] = []
    dropped: list[DisruptionSignal] = []
    for signal in signals:
        if is_relevant(signal, terms):
            kept.append(signal)
        else:
            dropped.append(signal)
    return kept, dropped
