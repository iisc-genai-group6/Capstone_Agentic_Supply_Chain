from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from agentic_scd.ingestion.paths import SEED_DIR

TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_\-]+")


@dataclass(frozen=True)
class Document:
    doc_id: str
    text: str
    metadata: dict


def tokens(text: str) -> set[str]:
    return {item.lower() for item in TOKEN_RE.findall(text)}


def score(query: str, document: Document) -> float:
    q = tokens(query)
    d = tokens(document.text)
    if not q or not d:
        return 0.0
    overlap = len(q & d)
    return overlap / math.sqrt(len(q) * len(d))


class LocalRetriever:
    def __init__(self, documents: list[Document]) -> None:
        self.documents = documents

    def search(self, query: str, top_k: int = 4, category: str | None = None) -> list[Document]:
        docs = self.documents
        if category:
            preferred = [doc for doc in docs if doc.metadata.get("category") == category]
            if preferred:
                docs = preferred
        ranked = sorted(docs, key=lambda doc: score(query, doc), reverse=True)
        return ranked[:top_k]


def network_documents() -> list[Document]:
    path = SEED_DIR / "network.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    docs: list[Document] = []
    for section in ("suppliers", "facilities", "lanes"):
        for idx, row in enumerate(data.get(section, [])):
            text = " ".join(str(value) for value in row.values())
            docs.append(Document(doc_id=f"{section}-{idx}", text=text, metadata={"kind": section, **row}))
    return docs


def playbook_documents() -> list[Document]:
    path = SEED_DIR / "playbooks.json"
    if not path.exists():
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [
        Document(
            doc_id=f"playbook-{idx}",
            text=" ".join([row.get("title", ""), row.get("action", ""), " ".join(row.get("best_for", [])), row.get("expected_effect", "")]),
            metadata={"kind": "playbook", **row},
        )
        for idx, row in enumerate(rows)
    ]


@lru_cache(maxsize=1)
def impact_retriever() -> LocalRetriever:
    return LocalRetriever(network_documents())


@lru_cache(maxsize=1)
def mitigation_retriever() -> LocalRetriever:
    return LocalRetriever(playbook_documents())


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))
