from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Callable

import numpy as np

from agentic_scd.config import Settings, get_settings
from agentic_scd.db import connect, init_db
from agentic_scd.db.client import database_dialect, sqlite_path
from agentic_scd.ingestion.paths import SEED_DIR
from agentic_scd.ingestion.sqlutil import execute

TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_\-]+")
VECTOR_DIMS = 192
MIN_SCORE = 0.05


@dataclass(frozen=True)
class Document:
    doc_id: str
    text: str
    metadata: dict


def unique_documents(documents: list[Document]) -> list[Document]:
    ordered: dict[str, Document] = {}
    for document in documents:
        ordered.setdefault(document.doc_id, document)
    return list(ordered.values())


def tokens(text: str) -> set[str]:
    return {item.lower() for item in TOKEN_RE.findall(text)}


def lexical_score(query: str, document: Document) -> float:
    q = tokens(query)
    d = tokens(document.text)
    if not q or not d:
        return 0.0
    overlap = len(q & d)
    meta_tokens = tokens(
        " ".join(
            str(document.metadata.get(key, ""))
            for key in ("category", "kind", "region", "name", "title", "route", "lane", "hub", "hub_port")
        )
    )
    phrase_bonus = 0.2 if query.lower().strip() and query.lower() in document.text.lower() else 0.0
    metadata_bonus = 0.15 if q & meta_tokens else 0.0
    return overlap / math.sqrt(len(q) * len(d)) + phrase_bonus + metadata_bonus


def vector(text: str) -> np.ndarray:
    row = np.zeros(VECTOR_DIMS, dtype=float)
    for token in tokens(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % VECTOR_DIMS
        weight = 1.0 + min(2.0, len(token) / 12.0)
        row[index] += weight if digest[2] % 2 == 0 else -weight
    norm = float(np.linalg.norm(row))
    if norm <= 0:
        return row
    return row / norm


def vector_score(query: str, document: Document) -> float:
    qv = vector(query)
    dv = vector(document.text)
    if not np.any(qv) or not np.any(dv):
        return 0.0
    return float(np.dot(qv, dv))


def score_document(query: str, document: Document, dense_score: float | None = None) -> float:
    lexical = lexical_score(query, document)
    dense = dense_score if dense_score is not None else vector_score(query, document)
    freshness = 0.05 if document.metadata.get("kind") in {"runtime_signal", "freight_rate"} else 0.0
    return 0.58 * lexical + 0.42 * dense + freshness


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def row_value(row, key: str, index: int):
    if isinstance(row, tuple):
        return row[index]
    return row[key]


def parse_json(value):
    if value is None or value == "":
        return {}
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def network_documents() -> list[Document]:
    data = read_json(SEED_DIR / "network.json", {})
    docs: list[Document] = []
    for section in ("suppliers", "facilities", "lanes"):
        for idx, row in enumerate(data.get(section, [])):
            text = " ".join(str(value) for value in row.values())
            docs.append(Document(doc_id=f"{section}-{idx}", text=text, metadata={"kind": section, **row}))
    return docs


def playbook_documents() -> list[Document]:
    rows = read_json(SEED_DIR / "playbooks.json", [])
    return [
        Document(
            doc_id=f"playbook-{idx}",
            text=" ".join(
                [
                    row.get("title", ""),
                    row.get("action", ""),
                    " ".join(row.get("best_for", [])),
                    row.get("expected_effect", ""),
                ]
            ),
            metadata={"kind": "playbook", **row},
        )
        for idx, row in enumerate(rows)
    ]


def synthetic_history_documents() -> list[Document]:
    path = SEED_DIR / "synthetic_disruption_events.jsonl"
    if not path.exists():
        return []
    docs: list[Document] = []
    for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        row = json.loads(line)
        docs.append(
            Document(
                doc_id=f"synthetic-{idx}",
                text=" ".join([str(row.get("description", "")), str(row.get("region", "")), str(row.get("label", ""))]),
                metadata={"kind": "history", "category": row.get("label", "other"), **row},
            )
        )
    return docs


def kaggle_history_documents() -> list[Document]:
    data = read_json(SEED_DIR / "kaggle_supplychainnet.json", {})
    docs: list[Document] = []
    for idx, row in enumerate(data.get("records", [])):
        if row.get("kind") != "disruption":
            continue
        docs.append(
            Document(
                doc_id=f"dataset-disruption-{idx}",
                text=" ".join([str(row.get("description", "")), str(row.get("region", "")), str(row.get("disruption_type", ""))]),
                metadata={"kind": "dataset_history", "category": row.get("disruption_type", "other").replace(" ", "_").lower(), **row},
            )
        )
    return docs


def freight_documents() -> list[Document]:
    data = read_json(SEED_DIR / "freightos_baltic_index.json", {})
    docs: list[Document] = []
    for idx, row in enumerate(data.get("rows", [])):
        lane = row.get("lane", row.get("lane_code", "freight lane"))
        rate = row.get("rate_usd_feu")
        change = row.get("change_pct")
        text = f"Freight rate {lane} {rate} change {change} percent {row.get('date')}"
        docs.append(
            Document(
                doc_id=f"freight-{idx}",
                text=text,
                metadata={
                    "kind": "freight_rate",
                    "category": "logistics",
                    "lane": lane,
                    "rate_usd_feu": rate,
                    "change_pct": change,
                    "date": row.get("date"),
                },
            )
        )
    return docs


def demand_documents() -> list[Document]:
    path = SEED_DIR / "supply_chain_dataset.csv"
    if not path.exists():
        return []
    docs: list[Document] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for idx, row in enumerate(csv.DictReader(handle)):
            product = row.get("Product type", "")
            location = row.get("Location", "")
            carrier = row.get("Shipping carriers", "")
            transport = row.get("Transportation modes", "")
            sold = row.get("Number of products sold", "")
            stock = row.get("Stock levels", "")
            route = row.get("Routes", "")
            text = " ".join([product, location, carrier, transport, sold, stock, route]).strip()
            docs.append(
                Document(
                    doc_id=f"demand-{idx}",
                    text=text,
                    metadata={
                        "kind": "demand_history",
                        "category": "demand_shock",
                        "region": location,
                        "product": product,
                        "route": route,
                    },
                )
            )
    return docs


def runtime_documents() -> list[Document]:
    if not init_db():
        return []
    try:
        with connect() as conn:
            token = "?" if getattr(conn, "agentic_scd_dialect", None) == "sqlite" else "%s"
            signal_rows = execute(
                conn,
                f"SELECT signal_id, title, raw_text, source_type, location, raw_payload FROM signals ORDER BY created_at DESC LIMIT {token}",
                (50,),
            ).fetchall()
    except Exception:
        return []
    docs: list[Document] = []
    for row in signal_rows:
        location = parse_json(row_value(row, "location", 4))
        payload = parse_json(row_value(row, "raw_payload", 5))
        region = location.get("region") or payload.get("region") or ""
        category = (
            payload.get("label")
            or payload.get("kind")
            or payload.get("disruption_type")
            or payload.get("webhook_event", {}).get("payload", {}).get("label")
            or "runtime_signal"
        )
        text = " ".join(
            [
                str(row_value(row, "title", 1)),
                str(row_value(row, "raw_text", 2)),
                str(row_value(row, "source_type", 3)),
                str(region),
                str(category),
            ]
        )
        docs.append(
            Document(
                doc_id=str(row_value(row, "signal_id", 0)),
                text=text,
                metadata={
                    "kind": "runtime_signal",
                    "category": str(category).replace(" ", "_").lower(),
                    "region": region,
                    "source_type": row_value(row, "source_type", 3),
                },
            )
        )
    return docs


def history_documents() -> list[Document]:
    return synthetic_history_documents() + kaggle_history_documents() + freight_documents() + runtime_documents()


def news_documents() -> list[Document]:
    return synthetic_history_documents() + kaggle_history_documents() + runtime_documents()


def weather_documents() -> list[Document]:
    return network_documents() + runtime_documents() + freight_documents()


def impact_documents() -> list[Document]:
    return network_documents() + history_documents()


def forecast_documents() -> list[Document]:
    return demand_documents() + freight_documents() + history_documents()


def simulation_documents() -> list[Document]:
    return history_documents() + network_documents() + demand_documents()


def mitigation_documents() -> list[Document]:
    return playbook_documents() + freight_documents() + runtime_documents()


COLLECTION_PROVIDERS: dict[str, Callable[[], list[Document]]] = {
    "news": news_documents,
    "weather": weather_documents,
    "history": history_documents,
    "impact": impact_documents,
    "forecast": forecast_documents,
    "simulation": simulation_documents,
    "mitigation": mitigation_documents,
}


SQLITE_VECTOR_SCHEMA = """
CREATE TABLE IF NOT EXISTS vector_collections (
    collection_name TEXT PRIMARY KEY,
    source_signature TEXT NOT NULL,
    document_count INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vector_documents (
    collection_name TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    text TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    vector_json TEXT NOT NULL,
    PRIMARY KEY (collection_name, doc_id)
);
"""

POSTGRES_VECTOR_SCHEMA = """
CREATE TABLE IF NOT EXISTS vector_collections (
    collection_name TEXT PRIMARY KEY,
    source_signature TEXT NOT NULL,
    document_count INTEGER NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS vector_documents (
    collection_name TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    text TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    vector_json TEXT NOT NULL,
    PRIMARY KEY (collection_name, doc_id)
);
CREATE INDEX IF NOT EXISTS idx_vector_documents_collection ON vector_documents (collection_name);
"""


def vector_store_dialect(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    raw = settings.vector_database_url or ""
    return database_dialect(raw) or "sqlite"


def vector_store_backend(settings: Settings | None = None) -> str:
    if vector_store_dialect(settings) == "postgres":
        return "postgres_vector_store"
    return "sqlite_vector_store"


def vector_store_path(settings: Settings | None = None) -> Path | str:
    settings = settings or get_settings()
    raw = settings.vector_database_url or ""
    if vector_store_dialect(settings) == "postgres":
        return raw
    path = Path(raw).expanduser() if raw and "://" not in raw else sqlite_path(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _vector_connection(settings: Settings | None = None):
    settings = settings or get_settings()
    vector_url = settings.vector_database_url or settings.database_url
    if vector_url and vector_store_dialect(settings) == "sqlite" and "://" not in vector_url:
        vector_url = f"sqlite:///{Path(vector_url).expanduser()}"
    return connect(replace(settings, database_url=vector_url))


def _ensure_schema(conn) -> None:
    if getattr(conn, "agentic_scd_dialect", None) == "sqlite":
        conn.executescript(SQLITE_VECTOR_SCHEMA)
        return
    with conn.cursor() as cur:
        cur.execute(POSTGRES_VECTOR_SCHEMA)


def _param_token(conn) -> str:
    return "?" if getattr(conn, "agentic_scd_dialect", None) == "sqlite" else "%s"


def _executemany(conn, sql: str, rows: list[tuple]) -> None:
    if getattr(conn, "agentic_scd_dialect", None) == "sqlite":
        for row in rows:
            conn.execute(sql, row)
        return
    with conn.cursor() as cur:
        cur.executemany(sql, rows)


def _document_signature(documents: list[Document]) -> str:
    digest = hashlib.sha256()
    for document in sorted(documents, key=lambda item: item.doc_id):
        digest.update(document.doc_id.encode("utf-8"))
        digest.update(b"\x1f")
        digest.update(document.text.encode("utf-8"))
        digest.update(b"\x1f")
        digest.update(json.dumps(document.metadata, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _vector_json(values: np.ndarray) -> str:
    return json.dumps([round(float(item), 8) for item in values.tolist()], separators=(",", ":"))


def _ensure_collection(
    collection_name: str,
    provider: Callable[[], list[Document]],
    settings: Settings | None = None,
    *,
    force: bool = False,
) -> int:
    settings = settings or get_settings()
    documents = unique_documents(provider())
    signature = _document_signature(documents)
    with _vector_connection(settings) as conn:
        _ensure_schema(conn)
        token = _param_token(conn)
        current = execute(
            conn,
            f"SELECT source_signature, document_count FROM vector_collections WHERE collection_name = {token}",
            (collection_name,),
        ).fetchone()
        should_rebuild = force or current is None
        if (
            not should_rebuild
            and settings.rag_auto_rebuild
            and (
                row_value(current, "source_signature", 0) != signature
                or int(row_value(current, "document_count", 1)) != len(documents)
            )
        ):
            should_rebuild = True
        if should_rebuild:
            execute(
                conn,
                f"DELETE FROM vector_documents WHERE collection_name = {token}",
                (collection_name,),
            )
            rows = [
                (
                    collection_name,
                    document.doc_id,
                    document.text,
                    json.dumps(document.metadata, sort_keys=True, separators=(",", ":")),
                    _vector_json(vector(document.text)),
                )
                for document in documents
            ]
            if rows:
                _executemany(
                    conn,
                    f"INSERT INTO vector_documents (collection_name, doc_id, text, metadata_json, vector_json) VALUES ({token}, {token}, {token}, {token}, {token})",
                    rows,
                )
            execute(
                conn,
                (
                    "INSERT INTO vector_collections (collection_name, source_signature, document_count, updated_at) "
                    f"VALUES ({token}, {token}, {token}, CURRENT_TIMESTAMP) "
                    "ON CONFLICT(collection_name) DO UPDATE SET "
                    "source_signature = excluded.source_signature, "
                    "document_count = excluded.document_count, "
                    "updated_at = CURRENT_TIMESTAMP"
                ),
                (collection_name, signature, len(documents)),
            )
            conn.commit()
    return len(documents)


def _stored_documents(
    collection_name: str,
    provider: Callable[[], list[Document]],
    settings: Settings | None = None,
) -> list[tuple[Document, np.ndarray]]:
    settings = settings or get_settings()
    _ensure_collection(collection_name, provider, settings)
    with _vector_connection(settings) as conn:
        _ensure_schema(conn)
        rows = execute(
            conn,
            f"SELECT doc_id, text, metadata_json, vector_json FROM vector_documents WHERE collection_name = {_param_token(conn)}",
            (collection_name,),
        ).fetchall()
    return [
        (
            Document(
                doc_id=str(row_value(row, "doc_id", 0)),
                text=str(row_value(row, "text", 1)),
                metadata=parse_json(row_value(row, "metadata_json", 2)),
            ),
            np.array(parse_json(row_value(row, "vector_json", 3)), dtype=float),
        )
        for row in rows
    ]


def _fallback_search(
    documents: list[Document],
    query: str,
    top_k: int,
    category: str | None = None,
) -> list[Document]:
    ranked: list[tuple[float, Document]] = []
    for document in unique_documents(documents):
        if category and document.metadata.get("category") != category:
            continue
        score = score_document(query, document)
        if score > MIN_SCORE:
            ranked.append((score, document))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [document for _, document in ranked[:top_k]]


def search_collection(
    collection_name: str,
    provider: Callable[[], list[Document]],
    query: str,
    top_k: int = 4,
    category: str | None = None,
    settings: Settings | None = None,
) -> list[Document]:
    settings = settings or get_settings()
    try:
        qv = vector(query)
        ranked: list[tuple[float, Document]] = []
        for document, stored_vector in _stored_documents(collection_name, provider, settings):
            if category and document.metadata.get("category") != category:
                continue
            dense = 0.0 if not np.any(qv) or not np.any(stored_vector) else float(np.dot(qv, stored_vector))
            score = score_document(query, document, dense)
            if score > MIN_SCORE:
                ranked.append((score, document))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [document for _, document in ranked[:top_k]]
    except Exception:
        return _fallback_search(provider(), query, top_k, category)


def rebuild_vector_store(
    collections: list[str] | tuple[str, ...] | None = None,
    settings: Settings | None = None,
) -> dict[str, object]:
    settings = settings or get_settings()
    names = list(collections or COLLECTION_PROVIDERS)
    counts = {
        name: _ensure_collection(name, COLLECTION_PROVIDERS[name], settings, force=True)
        for name in names
        if name in COLLECTION_PROVIDERS
    }
    return {
        "backend": vector_store_backend(settings),
        "vector_store_path": str(vector_store_path(settings)),
        "collections": counts,
    }


def vector_store_stats(settings: Settings | None = None) -> dict[str, object]:
    settings = settings or get_settings()
    try:
        counts = {
            name: _ensure_collection(name, provider, settings)
            for name, provider in COLLECTION_PROVIDERS.items()
        }
    except Exception:
        counts = {name: 0 for name in COLLECTION_PROVIDERS}
    return {
        "backend": vector_store_backend(settings),
        "vector_store_path": str(vector_store_path(settings)),
        "collections": counts,
    }


class LocalRetriever:
    def __init__(
        self,
        collection_name: str,
        documents: Callable[[], list[Document]],
        mode: str = "hybrid_hash_vector",
    ) -> None:
        self.collection_name = collection_name
        self._documents = documents
        self.mode = mode

    @property
    def documents(self) -> list[Document]:
        try:
            return [document for document, _ in _stored_documents(self.collection_name, self._documents)]
        except Exception:
            return unique_documents(self._documents())

    def score(self, query: str, document: Document) -> float:
        return score_document(query, document)

    def search(self, query: str, top_k: int = 4, category: str | None = None) -> list[Document]:
        return search_collection(self.collection_name, self._documents, query, top_k=top_k, category=category)


@lru_cache(maxsize=1)
def news_retriever() -> LocalRetriever:
    return LocalRetriever("news", news_documents)


@lru_cache(maxsize=1)
def weather_retriever() -> LocalRetriever:
    return LocalRetriever("weather", weather_documents)


@lru_cache(maxsize=1)
def impact_retriever() -> LocalRetriever:
    return LocalRetriever("impact", impact_documents)


@lru_cache(maxsize=1)
def mitigation_retriever() -> LocalRetriever:
    return LocalRetriever("mitigation", mitigation_documents)


@lru_cache(maxsize=1)
def history_retriever() -> LocalRetriever:
    return LocalRetriever("history", history_documents)


@lru_cache(maxsize=1)
def forecast_retriever() -> LocalRetriever:
    return LocalRetriever("forecast", forecast_documents)


@lru_cache(maxsize=1)
def simulation_retriever() -> LocalRetriever:
    return LocalRetriever("simulation", simulation_documents)


def retrieval_mode() -> str:
    return impact_retriever().mode


def retriever_stats() -> dict[str, int | str | dict[str, int]]:
    stats = vector_store_stats()
    collections = stats["collections"]
    return {
        "mode": retrieval_mode(),
        "backend": str(stats["backend"]),
        "vector_store_path": str(stats["vector_store_path"]),
        "collections": collections,
        "news_documents": int(collections.get("news", 0)),
        "weather_documents": int(collections.get("weather", 0)),
        "impact_documents": int(collections.get("impact", 0)),
        "mitigation_documents": int(collections.get("mitigation", 0)),
        "history_documents": int(collections.get("history", 0)),
        "forecast_documents": int(collections.get("forecast", 0)),
        "simulation_documents": int(collections.get("simulation", 0)),
    }
