# agentic-scd — backend

The Python service for the **Agentic Supply Chain Disruption Predictor & Simulation
Engine**: the LangGraph pipeline, ingestion layer, agents, FastAPI/Gradio surfaces, and
the dev notebooks.

This directory is the Python project (`pyproject.toml` lives here). Run `uv` commands
from **here** (`cd backend`); run `docker compose` from the **repo root** (one level up),
where `docker-compose.yml` and `.env` live.

```bash
uv sync --group notebooks     # install deps (incl. Jupyter)
uv run agentic-scd            # run the end-to-end pipeline
uv run pytest                 # tests
```

See the **repo-root `README.md`** for the full quick start (Docker and uv paths),
architecture, and per-phase documentation.
