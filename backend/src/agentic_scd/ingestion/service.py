from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass

import uvicorn
from fastapi import FastAPI, Request

try:
    from apscheduler.schedulers.background import BackgroundScheduler
except Exception:
    @dataclass
    class _Job:
        id: str
        max_instances: int
        next_run_time: object | None = object()

    class BackgroundScheduler:
        def __init__(self) -> None:
            self.running = False
            self.jobs = {}

        def add_job(self, func, trigger=None, minutes=None, args=None, id=None, max_instances=1, coalesce=True) -> None:
            self.jobs[id] = _Job(id=id, max_instances=max_instances)

        def get_job(self, job_id):
            return self.jobs.get(job_id)

        def start(self) -> None:
            self.running = True

        def shutdown(self, wait: bool = False) -> None:
            self.running = False

from agentic_scd.config import Settings, get_settings
from agentic_scd.db import DatabaseNotConfiguredError, connect, init_db, ping
from agentic_scd.ingestion.collect import collect
from agentic_scd.ingestion.normalize import normalize
from agentic_scd.ingestion.pipeline import ingest_signals
from agentic_scd.ingestion.webhook import WebhookEvent, webhook_source
from agentic_scd.runtime_warnings import suppress_known_dependency_warnings

suppress_known_dependency_warnings()

logger = logging.getLogger(__name__)
POLL_JOB_ID = "ingestion_poll"


def run_poll_cycle(settings: Settings) -> None:
    try:
        summary = collect(settings)
        total = summary.totals
        logger.info("poll cycle fetched=%d kept=%d dropped=%d persisted=%d", total.fetched, total.kept, total.dropped, total.persisted)
    except Exception:
        logger.exception("poll cycle failed")


def start_scheduler(settings: Settings) -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_poll_cycle, trigger="interval", minutes=settings.ingest_poll_interval_minutes, args=[settings], id=POLL_JOB_ID, max_instances=1, coalesce=True)
    scheduler.start()
    return scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    init_db(settings)
    app.state.scheduler = start_scheduler(settings) if settings.ingest_scheduler_enabled else None
    try:
        yield
    finally:
        if app.state.scheduler is not None:
            app.state.scheduler.shutdown(wait=False)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Agentic SCD ingestion service", lifespan=lifespan)
    app.state.settings = settings

    @app.get("/health")
    def health(request: Request) -> dict:
        scheduler = getattr(request.app.state, "scheduler", None)
        status = ping(request.app.state.settings)
        return {"status": "ok", "scheduler_running": bool(scheduler and scheduler.running), "db_reachable": status.ok}

    @app.post("/signals")
    def post_signal(event: WebhookEvent, request: Request) -> dict:
        cfg: Settings = request.app.state.settings
        signal = normalize(event.to_raw_item(), webhook_source(cfg))
        db_persisted = False
        try:
            init_db(cfg)
            with connect(cfg) as conn:
                result = ingest_signals([signal], conn)
            db_persisted = True
        except DatabaseNotConfiguredError:
            result = ingest_signals([signal], None)
        return {"kept": result.kept, "dropped": result.dropped, "persisted": result.persisted, "duplicate": result.duplicate, "persisted_to_db": db_persisted and result.persisted > 0}

    @app.post("/collect")
    def post_collect(request: Request) -> dict:
        summary = collect(request.app.state.settings)
        return {"db_persisted": summary.db_persisted, "sources": [result.__dict__ for result in summary.results], "totals": summary.totals.__dict__}

    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    uvicorn.run(create_app(settings), host=settings.ingest_host, port=settings.ingest_port)


if __name__ == "__main__":
    main()
