from __future__ import annotations

import json
import logging
import os

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agentic_scd.__main__ import run
from agentic_scd.agents.schema import Classification, Forecast, ImpactMap
from agentic_scd.agents.simulate import run_simulation
from agentic_scd.config import get_settings
from agentic_scd.config.localfirst import CONFIG_FIELDS, apply_runtime_env, local_env_path
from agentic_scd.db import connect, init_db, ping
from agentic_scd.db.client import DatabaseNotConfiguredError
from agentic_scd.ingestion.collect import collect
from agentic_scd.ingestion.normalize import normalize
from agentic_scd.ingestion.paths import SEED_DIR
from agentic_scd.ingestion.pipeline import ingest_signals
from agentic_scd.ingestion.relevance import load_lexicon
from agentic_scd.ingestion.store import (
    list_approvals,
    recent_runs,
    recent_signals,
    save_approval,
    serialize_state,
)
from agentic_scd.ingestion.webhook import WebhookEvent, webhook_source
from agentic_scd.observability import configure_tracing
from agentic_scd.rag.retriever import (
    rebuild_vector_store,
    history_retriever,
    impact_retriever,
    mitigation_retriever,
    retrieval_mode,
    retriever_stats,
)
from agentic_scd.runtime_warnings import suppress_known_dependency_warnings

suppress_known_dependency_warnings()
configure_tracing()

logger = logging.getLogger(__name__)

# Origins the React product UI is served from. Configurable via API_CORS_ORIGINS
# (comma-separated) so the UI can be reached from other machines on the LAN. The
# default "*" keeps the local-first demo working from any host; when an explicit
# list is provided, credentials are allowed too.
def cors_config() -> tuple[list[str], bool]:
    raw = os.getenv("API_CORS_ORIGINS", "*").strip()
    if raw in {"", "*"}:
        return ["*"], False
    return [origin.strip() for origin in raw.split(",") if origin.strip()], True


class RunRequest(BaseModel):
    scenario_name: str | None = None
    use_pending_signals: bool = False


class AskRequest(BaseModel):
    question: str


class ConfigUpdate(BaseModel):
    values: dict[str, object]


class VectorStoreRequest(BaseModel):
    collections: list[str] | None = None


class WhatIfOverrides(BaseModel):
    safety_stock_days: float | None = None
    alt_supplier_share_pct: float | None = None
    lead_time_mean_days: float | None = None


class WhatIfRequest(BaseModel):
    classifications: list[dict] = []
    impacts: list[dict] = []
    forecast: dict | None = None
    iterations: int | None = None
    overrides: WhatIfOverrides = WhatIfOverrides()


class ApprovalRequest(BaseModel):
    run_id: str
    action_index: int
    action_text: str
    owner: str | None = None
    approved_by: str | None = None


def database_mode(url: str | None) -> str:
    lowered = (url or "").lower()
    if lowered.startswith("postgresql:") or lowered.startswith("postgres:"):
        return "postgres"
    if lowered.startswith("sqlite:"):
        return "sqlite"
    return "none"


def scenario_names() -> list[str]:
    path = SEED_DIR / "scenarios.json"
    if not path.exists():
        return []
    return [row["name"] for row in json.loads(path.read_text(encoding="utf-8"))]


def load_network() -> dict:
    path = SEED_DIR / "network.json"
    if not path.exists():
        return {"suppliers": [], "facilities": [], "lanes": []}
    return json.loads(path.read_text(encoding="utf-8"))


def ask_network(question: str) -> str:
    docs = impact_retriever().search(question, top_k=3) + mitigation_retriever().search(question, top_k=3)
    if not docs:
        return "No local network or playbook context matched that question."
    settings = get_settings()
    lines = ["Relevant local context:"]
    seen: set[str] = set()
    context_rows: list[str] = []
    for doc in docs:
        if doc.doc_id in seen:
            continue
        seen.add(doc.doc_id)
        label = doc.metadata.get("name") or doc.metadata.get("title") or doc.doc_id
        row = f"- {label}: {doc.text}"
        lines.append(row)
        context_rows.append(row)
        if len(seen) >= 5:
            break
    if not settings.llm_is_mock:
        system = "Answer using the provided local supply-chain context only. Keep the response concise and practical."
        prompt = f"Question: {question}\n\nContext:\n" + "\n".join(context_rows)
        try:
            answer = completion(prompt, system=system, settings=settings, temperature=0).strip()
            if answer:
                return f"### Answer\n{answer}\n\n" + "\n".join(lines)
        except Exception:
            pass
    return "\n".join(lines)


def config_value(field_name: str):
    settings = get_settings()
    if field_name == "GROQ_MODEL":
        return os.getenv(field_name, settings.groq_model)
    if field_name == "USE_MOCK_LLM":
        return settings.use_mock_llm
    if field_name == "INGEST_POLL_INTERVAL_MINUTES":
        return str(settings.ingest_poll_interval_minutes)
    if field_name == "INGEST_SCHEDULER_ENABLED":
        return settings.ingest_scheduler_enabled
    if field_name == "INGEST_HOST":
        return settings.ingest_host
    if field_name == "INGEST_PORT":
        return str(settings.ingest_port)
    if field_name == "WEBHOOK_SOURCE_RELIABILITY":
        return str(settings.webhook_source_reliability)
    if field_name == "BATCH_ENABLED":
        return settings.batch_enabled
    if field_name == "RETENTION_ENABLED":
        return settings.retention_enabled
    if field_name == "RETENTION_REJECTED_TTL_DAYS":
        return str(settings.retention_rejected_ttl_days)
    if field_name == "RETENTION_SIGNALS_TTL_DAYS":
        return str(settings.retention_signals_ttl_days)
    if field_name == "SIMULATION_ITERATIONS":
        return str(settings.simulation_iterations)
    if field_name == "GRADIO_SHARE":
        return settings.dashboard_share
    if field_name == "GRADIO_SERVER_NAME":
        return os.getenv(field_name, "127.0.0.1")
    return os.getenv(field_name, "")


def config_snapshot() -> dict:
    settings = get_settings()
    status = ping(settings)
    retrieval = retriever_stats()
    fields = [
        {
            "name": field.name,
            "label": field.label,
            "section": field.section,
            "kind": field.kind,
            "secret": field.secret,
            "value": config_value(field.name),
        }
        for field in CONFIG_FIELDS
    ]
    return {
        "fields": fields,
        "runtime": {
            "config_file": str(local_env_path()),
            "storage_mode": database_mode(settings.resolved_database_url),
            "storage_detail": status.detail,
            "database_url": settings.resolved_database_url or "",
            "llm_mode": "mock" if settings.llm_is_mock else f"groq:{settings.groq_model}",
            "retrieval_mode": retrieval_mode(),
            "retriever_stats": retrieval,
            "data_dir": str(settings.data_dir),
        },
    }


def apply_config(values: dict[str, object]) -> dict:
    apply_runtime_env(values)
    get_settings.cache_clear()
    load_lexicon.cache_clear()
    impact_retriever.cache_clear()
    mitigation_retriever.cache_clear()
    history_retriever.cache_clear()
    return config_snapshot()


def create_app() -> FastAPI:
    app = FastAPI(title="Agentic SCD API", version="1.1.0")

    allow_origins, allow_credentials = cors_config()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict:
        settings = get_settings()
        result = ping(settings)
        return {
            "status": "ok" if result.ok else "degraded",
            "database": result.detail,
            "database_mode": database_mode(settings.resolved_database_url),
            "llm_mode": "mock" if settings.llm_is_mock else f"groq:{settings.groq_model}",
            "data_dir": str(settings.data_dir),
            "retrieval_mode": retrieval_mode(),
            "retriever_stats": retriever_stats(),
        }

    @app.get("/scenarios")
    def list_scenarios() -> dict:
        return {"scenarios": scenario_names()}

    @app.get("/network")
    def get_network() -> dict:
        return load_network()
    @app.get("/vector-store")
    def vector_store_state() -> dict:
        return retriever_stats()

    @app.post("/vector-store/rebuild")
    def rebuild_vectors(payload: VectorStoreRequest) -> dict:
        return rebuild_vector_store(payload.collections)

    @app.post("/run")
    def run_pipeline(payload: RunRequest) -> dict:
        state = run(payload.scenario_name, use_pending_signals=payload.use_pending_signals)
        return serialize_state(state)

    @app.post("/what-if")
    def what_if(payload: WhatIfRequest) -> dict:
        classifications = [Classification(**item) for item in payload.classifications]
        impacts = [ImpactMap(**item) for item in payload.impacts]
        forecast = Forecast(**payload.forecast) if payload.forecast else None
        overrides = payload.overrides.model_dump(exclude_none=True)
        simulation = run_simulation(
            classifications,
            impacts,
            forecast,
            iterations=payload.iterations,
            overrides=overrides,
        )
        return simulation.model_dump(mode="json")

    @app.post("/collect")
    def collect_sources() -> dict:
        summary = collect()
        return {
            "db_persisted": summary.db_persisted,
            "sources": [result.__dict__ for result in summary.results],
            "totals": summary.totals.__dict__,
        }

    @app.post("/ask")
    def ask(payload: AskRequest) -> dict:
        return {"answer": ask_network(payload.question)}

    @app.get("/config")
    def get_config() -> dict:
        return config_snapshot()

    @app.post("/config")
    def post_config(payload: ConfigUpdate) -> dict:
        return apply_config(payload.values)

    @app.post("/signals")
    def post_signal(event: WebhookEvent) -> dict:
        init_db()
        signal = normalize(event.to_raw_item(), webhook_source())
        with connect() as conn:
            result = ingest_signals([signal], conn)
        return {"kept": result.kept, "dropped": result.dropped, "persisted": result.persisted, "duplicate": result.duplicate, "persisted_to_db": result.persisted > 0}

    @app.post("/approvals")
    def create_approval(payload: ApprovalRequest) -> dict:
        saved = False
        try:
            init_db()
            with connect() as conn:
                saved = save_approval(
                    conn,
                    payload.run_id,
                    payload.action_index,
                    payload.action_text,
                    payload.owner,
                    payload.approved_by,
                )
        except DatabaseNotConfiguredError:
            saved = False
        return {
            "persisted": saved,
            "run_id": payload.run_id,
            "action_index": payload.action_index,
            "action_text": payload.action_text,
            "owner": payload.owner,
            "approved_by": payload.approved_by,
        }

    @app.get("/approvals")
    def get_approvals(run_id: str) -> dict:
        try:
            init_db()
            with connect() as conn:
                return {"approvals": list_approvals(conn, run_id)}
        except DatabaseNotConfiguredError:
            return {"approvals": []}

    @app.get("/signals")
    def list_signals(limit: int = 50) -> dict:
        init_db()
        with connect() as conn:
            rows = recent_signals(conn, limit)
        return {"signals": [item.model_dump(mode="json") for item in rows]}

    @app.get("/runs")
    def list_runs(limit: int = 20) -> dict:
        init_db()
        with connect() as conn:
            return {"runs": recent_runs(conn, limit)}

    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    host = os.getenv("API_HOST") or settings.ingest_host
    uvicorn.run(create_app(), host=host, port=8000)


if __name__ == "__main__":
    main()
