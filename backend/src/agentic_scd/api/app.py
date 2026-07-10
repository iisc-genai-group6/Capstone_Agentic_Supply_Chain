from __future__ import annotations

import logging

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agentic_scd.__main__ import run
from agentic_scd.config import get_settings
from agentic_scd.db import connect, init_db, ping
from agentic_scd.ingestion.collect import collect
from agentic_scd.ingestion.normalize import normalize
from agentic_scd.ingestion.pipeline import ingest_signals
from agentic_scd.ingestion.store import recent_runs, recent_signals, serialize_state
from agentic_scd.ingestion.webhook import WebhookEvent, webhook_source
from agentic_scd.rag.retriever import retrieval_mode, retriever_stats
from agentic_scd.runtime_warnings import suppress_known_dependency_warnings

suppress_known_dependency_warnings()

logger = logging.getLogger(__name__)


class RunRequest(BaseModel):
    scenario_name: str | None = None
    use_pending_signals: bool = False


def database_mode(url: str | None) -> str:
    lowered = (url or "").lower()
    if lowered.startswith("postgresql:") or lowered.startswith("postgres:"):
        return "postgres"
    if lowered.startswith("sqlite:"):
        return "sqlite"
    return "none"


def create_app() -> FastAPI:
    app = FastAPI(title="Agentic SCD API", version="1.0.3")

    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_credentials=True,
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

    @app.post("/run")
    def run_pipeline(payload: RunRequest) -> dict:
        state = run(payload.scenario_name, use_pending_signals=payload.use_pending_signals)
        return serialize_state(state)

    @app.post("/collect")
    def collect_sources() -> dict:
        summary = collect()
        return {
            "db_persisted": summary.db_persisted,
            "sources": [result.__dict__ for result in summary.results],
            "totals": summary.totals.__dict__,
        }

    @app.post("/signals")
    def post_signal(event: WebhookEvent) -> dict:
        init_db()
        signal = normalize(event.to_raw_item(), webhook_source())
        with connect() as conn:
            result = ingest_signals([signal], conn)
        return {"kept": result.kept, "dropped": result.dropped, "persisted": result.persisted, "duplicate": result.duplicate, "persisted_to_db": result.persisted > 0}

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
    uvicorn.run(create_app(), host=settings.ingest_host, port=8000)


if __name__ == "__main__":
    main()
