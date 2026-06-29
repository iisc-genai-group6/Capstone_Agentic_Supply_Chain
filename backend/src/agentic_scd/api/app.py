from __future__ import annotations

import logging

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from agentic_scd.__main__ import run
from agentic_scd.config import get_settings
from agentic_scd.db import connect, init_db, ping
from agentic_scd.ingestion.collect import collect
from agentic_scd.ingestion.normalize import normalize
from agentic_scd.ingestion.pipeline import ingest_signals
from agentic_scd.ingestion.store import recent_runs, recent_signals, serialize_state
from agentic_scd.ingestion.webhook import WebhookEvent, webhook_source
from agentic_scd.runtime_warnings import suppress_known_dependency_warnings

suppress_known_dependency_warnings()

logger = logging.getLogger(__name__)


class RunRequest(BaseModel):
    scenario_name: str | None = None


def create_app() -> FastAPI:
    app = FastAPI(title="Agentic SCD API", version="1.0.1")

    @app.get("/health")
    def health() -> dict:
        result = ping()
        return {"status": "ok" if result.ok else "degraded", "database": result.detail}

    @app.post("/run")
    def run_pipeline(payload: RunRequest) -> dict:
        state = run(payload.scenario_name)
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
        return {"kept": result.kept, "dropped": result.dropped, "persisted": result.persisted, "duplicate": result.duplicate}

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
