# Agentic Supply Chain Disruption Predictor

Production-ready backend scaffold using Clean Architecture.

## Stack

- Python 3.12, FastAPI, Pydantic v2
- PostgreSQL + SQLAlchemy 2.0 + Alembic
- Redis, Qdrant
- LangChain, LangGraph
- Docker Compose

## Quick Start

```bash
cp .env.example .env
docker compose up --build
```

API: http://localhost:8000/docs

## Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
docker compose up postgres redis qdrant -d
alembic upgrade head
uvicorn app.main:app --reload
```

## Architecture

```
API → Application (services) → Domain ← Infrastructure (repositories, db, redis, qdrant)
```

## Health Endpoints

- `GET /api/v1/health/live` — liveness probe
- `GET /api/v1/health/ready` — readiness (Postgres, Redis, Qdrant)
