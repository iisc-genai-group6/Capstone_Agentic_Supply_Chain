# Agentic Supply Chain Disruption Predictor & Simulation Engine

An AI-powered supply chain disruption prediction and simulation system that proactively
monitors global risk signals, predicts potential supply chain disruptions, forecasts demand
impact, and simulates mitigation scenarios using multi-agent AI workflows, Retrieval-Augmented
Generation (RAG), time-series forecasting, and discrete-event simulation techniques.

## Overview

Modern supply chains are highly interconnected networks involving suppliers, manufacturers,
logistics providers, ports, warehouses, and retailers across multiple countries. Disruptions
such as extreme weather events, geopolitical conflicts, labor strikes, port closures, tariffs,
or factory shutdowns can significantly affect inventory availability, delivery timelines, and
revenue.

Most organizations react only *after* disruptions occur because monitoring large-scale,
real-time data sources manually is difficult and inefficient. This project builds a
**LangGraph-orchestrated multi-agent platform** that continuously ingests disruption-related
information, classifies supply chain risks, forecasts demand fluctuations, simulates disruption
scenarios, and generates mitigation recommendations.

The platform aims to support proactive risk management, improve operational resilience, and
assist organizations in strategic supply chain planning.

## Key Features

- **Real-time risk monitoring** across news feeds, weather alerts, shipping indices, and logistics signals
- **LLM-based disruption classification** (weather, geopolitical, logistics, raw material shortages, demand shocks)
- **Weather risk detection** for ports, transport hubs, and manufacturing facilities
- **Supplier-level and trade-lane risk scoring** via DistilBERT classifiers
- **Demand forecasting** that incorporates disruption risk signals
- **Discrete-event simulation** of supply chain networks with Monte Carlo stockout/revenue impact estimation
- **Natural-language mitigation recommendations** (alternate suppliers, route changes, safety stock adjustments)
- **Interactive dashboard** with disruption heatmaps, timelines, simulation outcomes, and high-risk alerts

## Architecture: Multi-Agent Workflow

The system is composed of specialized agents orchestrated with LangGraph:

| # | Agent | Responsibility |
|---|-------|----------------|
| 1 | **Real-Time Data Ingestion Agent** | Continuously collects data from RSS feeds, logistics/weather APIs, and shipping indices; extracts disruption events using `feedparser` and NLP pipelines; stores signals in a structured format |
| 2 | **News & Event Analysis Agent** | Analyzes news articles and logistics alerts with LLMs; identifies disruption categories |
| 3 | **Weather Risk Monitoring Agent** | Fetches forecasts via Open-Meteo API; detects extreme weather affecting ports, hubs, and factories |
| 4 | **Risk Classification Agent** | LangGraph-based orchestration using DistilBERT classifiers; generates supplier-level and trade-lane risk scores |
| 5 | **Demand Forecasting Agent** | Trains forecasting models with Facebook Prophet; folds disruption signals into demand predictions |
| 6 | **Simulation Agent** | Models suppliers, warehouses, ports, and retailers as network nodes using SimPy discrete-event simulation; runs Monte Carlo simulations for stockout probability and revenue impact |
| 7 | **Mitigation Recommendation Agent** | Generates natural-language mitigation strategies using LLMs |
| 8 | **Dashboard & Alerting** | Gradio dashboard for risk visualization, scenario analysis, and high-risk alerts |
| 9 | **Evaluation** | Measures risk classification accuracy, demand forecast deviation, and simulation/recommendation quality |

## Data Sources

| Source | Type | Content |
|--------|------|---------|
| [SupplyChainNet (Kaggle)](https://www.kaggle.com/datasets) | Dataset | Historical supply chain transactions, shipping records, supplier info, logistics delays, disruption events |
| [Freightos Baltic Index](https://fbx.freightos.com/) | Public index | Container shipping rate indices, freight trends, logistics cost fluctuations |
| [Open-Meteo API](https://open-meteo.com/) | API | Historical and forecast weather data for logistics hubs and shipping regions |
| Reuters / Bloomberg / Supply Chain Dive RSS, Google News API | News/RSS | Articles on labor strikes, geopolitical risks, tariffs, factory shutdowns, logistics disruptions |
| AI-generated synthetic events | Synthetic | Simulated demand shocks, disruption narratives, supplier failures, logistics incidents |

## Tech Stack

- **Orchestration:** LangGraph (multi-agent workflows)
- **LLMs / RAG:** News analysis & mitigation recommendation generation
- **Classification:** DistilBERT (`distilbert-base-uncased`)
- **Forecasting:** Facebook Prophet
- **Simulation:** SimPy (discrete-event), Monte Carlo methods
- **Ingestion:** feedparser, NLP pipelines
- **Dashboard:** Gradio

## Project layout

```
repo-root/
├── backend/                # the Python service: pipeline, ingestion, agents, notebooks, tests
│   ├── src/agentic_scd/    #   importable package
│   ├── notebooks/  tests/  scripts/  data/
│   ├── pyproject.toml  uv.lock
│   └── Dockerfile  .dockerignore
├── docker-compose.yml      # orchestrates the stack (postgres + the app container)
├── .env / .env.example     # shared config (DB creds, API keys)
└── README.md
```

**Where to run what:** the Python project lives in **`backend/`** — run `uv` and
`scripts/` commands from there (`cd backend`). `docker-compose.yml` and `.env` live at the
**repo root** — run `docker compose` from the root. (A future `frontend/` React app will
sit alongside `backend/`.)

## Quick start

Two ways to clone and run, differing in **where the app runs** — in a container, or on
your host via `uv`. **Postgres always runs in Docker** in both. Each brings the
environment up and then **stops there** — no UI or pipeline starts automatically; you pick
a run mode (CLI, Gradio, or Jupyter).

### Running with Docker

The fastest path — **the only prerequisite is Docker** (Desktop on Windows/Mac, Engine on
Linux; works the same in **GitHub Codespaces**). `docker compose` brings up Postgres plus
an `app` container (Python 3.11 + uv + the project, deps preinstalled) and leaves it idle.

```bash
cp .env.example .env          # Compose reads it; GROQ_API_KEY can stay empty (offline)
docker compose up -d          # build + start postgres and the idle app (first run builds)
docker compose ps             # postgres "healthy", app "running"
```

Optionally load some signals into the DB (otherwise a synthetic seed is used at run time):

```bash
docker compose exec app uv run agentic-scd-batch     # seed historical baselines
docker compose exec app uv run agentic-scd-collect   # run the connectors once
```

Then pick a run mode — each is a single `exec` into the already-running `app` container:

```bash
# 1) CLI — end-to-end pipeline, prints a stage-by-stage summary
docker compose exec app uv run agentic-scd

# 2) Gradio dashboard — "Run pipeline" UI
docker compose exec app uv run agentic-scd-dashboard
#   then open http://localhost:7860

# 3) Jupyter — the interactive dev notebooks (--allow-root: the container runs as root)
docker compose exec app uv run jupyter lab --ip 0.0.0.0 --no-browser --allow-root
#   open the printed URL, replacing the host with http://localhost:8888/...?token=...
```

`backend/src` and `backend/notebooks` are bind-mounted, so edits on your host show up live
in the container (and notebook changes are saved back to the repo). Stop everything with
`docker compose down` (data persists on the `pgdata` volume; add `-v` to wipe it).

### Running with uv

The app runs on your host; **Postgres still runs in Docker**.

**Prerequisites:** **Docker** (for Postgres) and **[`uv`](https://docs.astral.sh/uv/)** —
uv manages dependencies, runs the app, and will **provision Python 3.11+ automatically** if
your host doesn't already have it. Install uv if you don't have it yet:

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# …or, if you already have Python + pip:
pip install uv
```

From the repo **root**, prepare config and start Postgres; then `cd backend` for the
Python project (uv fetches Python 3.11+ on first sync if missing):

```bash
# repo root (where .env and docker-compose.yml live)
cp .env.example .env              # GROQ_API_KEY can stay empty (offline)
docker compose up -d postgres     # just the database; the app runs on uv
docker compose ps                 # postgres should report "healthy"

# the Python project
cd backend
uv sync --group notebooks         # create .venv + install deps (incl. Jupyter)
```

Optionally load some signals (otherwise a synthetic seed is used at run time):

```bash
uv run agentic-scd-batch      # seed historical baselines
uv run agentic-scd-collect    # run the connectors once
```

Then pick a run mode:

```bash
# 1) CLI — end-to-end pipeline, prints a stage-by-stage summary
uv run agentic-scd

# 2) Gradio dashboard — "Run pipeline" UI
uv run agentic-scd-dashboard
#   then open http://localhost:7860

# 3) Jupyter — the interactive dev notebooks
uv run jupyter lab
#   opens in your browser; pick the "Python 3 (ipykernel)" kernel
```

## Getting Started (Phase 0 scaffold)

The repository currently contains the **Phase 0 scaffold**: an importable
`agentic_scd` package, a thin LLM wrapper, the shared `DisruptionSignal` schema,
a typed LangGraph state, and a single stub ingestion node wired into a runnable
graph. It runs **fully offline** with no API key.

**Prerequisites:** [`uv`](https://docs.astral.sh/uv/) (it provisions Python 3.11+
automatically). Run these from **`backend/`** (`cd backend`):

```bash
uv sync                       # create .venv + install from pyproject.toml + uv.lock
uv run agentic-scd            # build & run the graph; prints a GraphState with new_signals
#   python -m agentic_scd     # equivalent module invocation
uv run pytest                 # smoke test
uv run ruff check .           # lint
uv run ruff format --check .  # formatting
```

Configuration is read from a `.env` file (see `.env.example`). With no
`GROQ_API_KEY` set, the LLM wrapper returns a deterministic mock response so the
scaffold never requires network access. Package layout lives under `backend/src/agentic_scd/`
(`config/`, `llm/`, `ingestion/`, `graph/`, `db/`), filled in over successive phases.

## Dev database (Phase 0.5)

A throwaway **local Postgres** runs via Docker Compose so a database exists from
Phase 1 onward. The app still runs on the local `uv` workflow and connects over
`DATABASE_URL` — Docker here runs **only** the database (no tables/schema yet;
those land in Phase 1). **Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/)
running.**

```bash
docker compose up -d postgres     # start just the DB (postgres:16-alpine)
docker compose ps                 # postgres should report "healthy"
```

The connection settings come from `.env` (`POSTGRES_*` feed the container;
`DATABASE_URL` is what the app uses). Verify connectivity:

```bash
uv run python -c "from agentic_scd.db import ping; print(ping())"
#   PingResult(ok=True, detail='SELECT 1 ok')  when the DB is up
```

If no database is reachable, `ping()` returns `PingResult(ok=False, ...)` with a
clear message (never a crash), so the app stays offline-runnable and the test
suite still passes.

**Backup / restore** (cross-platform, via `uv run` from `backend/`). Dumps are timestamped
SQL files written to `backend/data/backups/` (git-ignored):

```bash
uv run python scripts/db_dump.py                       # -> data/backups/pgdump-<ts>.sql
uv run python scripts/db_restore.py data/backups/<snapshot>.sql
```

Data persists on the named `pgdata` volume across `docker compose down` → `up`;
`docker compose down -v` also drops the volume (wiping the data).

## Data ingestion (Phase 1)

The ingestion layer turns messy external data into clean, deduplicated, **relevant**
disruption signals. Collectors run **on-demand** (the scheduled poller and webhook are
Phase 1b) through one pipeline: **fetch → normalize → relevance-gate → dedupe →
persist**. The graph then reads what was persisted.

```bash
docker compose up -d postgres     # Phase 0.5 DB (optional — see offline note below)
uv run agentic-scd-collect        # run every enabled source once through the pipeline
```

The collector prints a per-source summary (fetched / kept / dropped / persisted /
live-vs-fallback), e.g.:

```
source                fetched   kept  dropped  persisted       path
supplychain_rss           510    469       41        469       live
open_meteo                  3      3        0          3       live
synthetic                   3      3        0          3       live
```

**Sources** are toggled by config in `sources.yaml` (not code): query-scoped RSS
(`feedparser`), Open-Meteo weather (`httpx`), and an always-available synthetic
generator. Each connector's `fetch()` is wrapped so any failure (network / empty)
degrades to a cached/synthetic `fallback()` instead of crashing — the path taken is
logged.

**Relevance gate** (Stage 0 + Stage 1 only): Stage 0 targets supply-chain sources;
Stage 1 keeps a signal only if its normalized text hits the disruption lexicon in
`lexicon.yaml` (strike, embargo, typhoon, tariff, …). It favors recall and logs the
drop rate; re-tune the lexicon and re-run freely.

**What persists where:**
- **Accepted signals** (full record + `raw_payload`, `status='new'`) → Postgres
  `signals` table (the system of record and the decoupled handoff).
- **Rejected items** → only their `dedup_hash` in `seen_rejected` (so the same junk
  isn't re-evaluated every run).
- **Raw pulls** → timestamped JSON **snapshot files** in `backend/data/snapshots/`
  (gitignored), *not* the DB — the audit/replay path. Offline fallback fixtures live
  under `data/fallback/` (committed).

Dedupe is **exact SHA-256** over the normalized title+body, so re-running the collector
never creates duplicate rows.

**Into the graph.** `uv run agentic-scd` runs the pipeline: `ingest_node` drains only
`status='new'` rows (flipping them to `processing`, so old news is never reprocessed),
then an **input guardrail** node discards anything off-topic / unsafe / schema-invalid
before downstream agents.

**Offline contract.** Everything runs with **no Docker and no network**: the synthetic
connector and cached fallbacks still yield signals, and with no DB the collector reports
in-memory only while `ingest_node` returns an empty batch — never a crash.

```bash
uv run agentic-scd-collect        # synthetic + cached fallbacks, no crash
uv run agentic-scd                # graph runs end-to-end
uv run pytest                     # green; DB-touching tests skip cleanly when no DB
```

## Always-on ingestion service (Phase 1b)

Phase 1a runs collectors **on-demand**. Phase 1b wraps that same pipeline in two
**always-on triggers** — a scheduled poller and a supplier webhook — running as one
FastAPI service so the system monitors continuously instead of only when invoked. Both
triggers write through the *same* normalize → gate → dedupe → persist path into the
*same* `signals` table the graph drains. Batch loaders and retention/TTL close out the
ingestion layer in **Phase 1c** (below).

```bash
docker compose up -d postgres     # optional — see the offline note below
uv run agentic-scd-ingest         # start the service (webhook + in-process scheduler)
```

- **Scheduled poller** — an in-process APScheduler job runs the full collector
  (`collect()`) every `INGEST_POLL_INTERVAL_MINUTES` (default 10), overlap-safe
  (`max_instances=1`). Disable it with `INGEST_SCHEDULER_ENABLED=false` to run
  webhook-only.
- **Supplier webhook** — `POST /signals` accepts a pushed disruption event, normalizes it
  (`source=supplier_webhook`), and runs it through gate → dedupe → persist, returning a
  JSON summary. No signature auth in the MVP. Drive it with the synthetic sender:

```bash
uv run python scripts/send_synthetic_event.py     # POSTs synthetic events to /signals
curl -s localhost:8001/health                     # {status, scheduler_running, db_reachable}
```

Signals from **either** trigger drain the same way — `uv run agentic-scd` runs the graph,
whose `ingest_node` reads the new rows behind the input guardrail. Config lives in
`.env` (`INGEST_*`, `WEBHOOK_SOURCE_RELIABILITY`); see `.env.example`.

**Offline contract.** With **no DB**, the service still starts, the poller ticks
in-memory, and `POST /signals` returns HTTP 200 with `persisted=0` (never a 5xx); with
**no network**, the poller falls back to synthetic/cached data. `uv run pytest` stays
green offline (the webhook → persist round-trip test skips cleanly with no DB).

## Batch loaders & retention (Phase 1c)

Phase 1a/1b cover **live** sources. Phase 1c adds the deferred **historical** seeding and
table housekeeping through one on-demand CLI — the batch counterpart to
`agentic-scd-collect`. It reads **committed** snapshots under `backend/data/seed/` so a run works
**fully offline** (no Kaggle/Freightos download), feeds them through the *same*
normalize → gate → dedupe → persist tail (idempotent on `dedup_hash`), and prunes stale
rows.

```bash
uv run agentic-scd-batch          # offline: seed from data/seed/ + run retention
uv run agentic-scd-batch --load   # loaders only (no retention)
uv run agentic-scd-batch --retain # retention only (no seeding)
```

- **Freightos loader** (`FREIGHT_INDEX`) — Freightos Baltic Index freight-rate rows →
  freight-rate baselines.
- **Kaggle SupplyChainNet loader** (`DATASET`) — historical `demand` baselines + persisted
  `disruption` KB-history records.
- **Retention / TTL** — prunes `seen_rejected` hashes older than
  `RETENTION_REJECTED_TTL_DAYS` (default 30) and **terminal** `signals` (`status='done'`)
  older than `RETENTION_SIGNALS_TTL_DAYS` (default 90). It **never** touches
  `new`/`processing` rows the pipeline still needs.

**Persist, not embed.** Phase 1c lands this data in **Postgres** (+ snapshot files) and
**does not embed anything** — the vector store (Chroma) is stood up later in Phase 4 (impact
KB) and reused in Phase 7 (playbooks). The baselines feed **Prophet** forecasting in Phase 5.

**Offline contract.** With **no DB**, the CLI still parses the seed snapshots, prints a
per-source summary, and exits 0 (nothing persisted; retention a clean no-op). A second run
with Postgres up persists **0 new** rows (idempotent). Config lives in `.env`
(`BATCH_ENABLED`, `RETENTION_ENABLED`, `RETENTION_*_TTL_DAYS`); see `.env.example`.

## Walking skeleton (Phase 2)

The thin end-to-end slice: every remaining agent is wired as a **deterministic stub** so
the whole chain runs now and produces one coherent result —
`ingest → input-guard → classify → impact → forecast → simulate → recommend`. Each stub
does the *simplest real thing*; Phases 3–7 deepen them one at a time (Groq/DistilBERT,
RAG + Chroma, Prophet, SimPy, RAG-grounded mitigation) behind the same node signatures.

```bash
uv run agentic-scd                # run the full chain, print a stage-by-stage summary
uv run agentic-scd-dashboard      # the same run in a minimal Gradio dashboard
```

The CLI prints classification, impact, forecast (baseline vs risk-adjusted), simulation
(stockout probability + revenue impact), and recommended actions. The Gradio app exposes a
**"Run pipeline"** button with one panel per stage (the run-status strip, heatmap, and
what-if controls arrive in Phase 8).

**Always demoable.** When ingestion yields no signals (no DB / no new rows), a deterministic
**synthetic seed** injects one signal so the chain always shows a full end-to-end result —
`uv run agentic-scd` works with no Docker and no network. The stubs are pure-Python and
deterministic (no LLM/Prophet/SimPy yet), so `uv run pytest` stays green fully offline.

## Dev notebooks (Phase 2.5)

Interactive Jupyter notebooks so the team can drive each agent and the full graph by
hand and develop Phases 3+ in isolation. They import the editable `agentic_scd` package,
so they stay in lock-step with the source — no logic is duplicated.

```bash
cd backend                        # the Python project (notebooks live here)
uv sync --group notebooks         # installs jupyterlab + ipykernel (not a runtime dep)
uv run jupyter lab                # launch, then pick the "Python 3 (ipykernel)" kernel
```

Recommended order (under `backend/notebooks/`):

| Notebook | What it's for |
|----------|---------------|
| `00_orchestration` | The full pipeline with an **overall architecture diagram**; steps the graph and shows `GraphState` after each hop. |
| `10_classify` … `50_recommend` | One per agent — each opens with **its own diagram** (internal steps, state contract, fallback) and calls the node in isolation. |
| `60_ingestion` | Trigger connectors / batch loaders; inspect the relevance gate and the `signals` table. |
| `90_contributor_guide` | Setup, conventions, and a worked example of **adding a new agent to the graph**. |

The `00_orchestration` and `90_contributor_guide` notebooks include a **Setup** section
that runs ingestion against Postgres — start it from the **repo root** first
(`docker compose up -d postgres`), since the compose file and `.env` live there. The
per-agent notebooks run **fully offline** on synthetic sample state, so you can iterate
with no DB.

> **Committing notebooks:** clear outputs first (Edit → Clear Outputs of All Cells, or
> `uv run jupyter nbconvert --clear-output --inplace notebooks/*.ipynb`) to keep diffs
> reviewable. There is no strip hook — it's a convention.

## Evaluation

- Risk classification accuracy
- Demand forecast deviation
- Simulation realism and mitigation recommendation quality

## Challenges

1. **Real-Time Data Integration** — continuously process multiple external data sources reliably
2. **Risk Signal Extraction** — identify meaningful disruption indicators from noisy news and weather data
3. **Forecasting Uncertainty** — handle uncertainty in demand forecasting under disruption conditions
4. **Simulation Complexity** — model realistic supply chain behavior and interconnected dependencies
5. **Multi-Agent Coordination** — synchronize ingestion, forecasting, simulation, and mitigation agents
6. **Scalability** — efficiently manage large-scale supplier networks and logistics data
7. **Recommendation Reliability** — generate actionable, business-relevant mitigation strategies

This repo also contain a local-first version of capstone project for predicting supply-chain disruptions, estimating business impact, and simulating mitigation options. It turns external signals such as RSS news, Open-Meteo weather alerts, freight snapshots, supplier webhook events, and packaged historical data into a ranked action plan that a supply-chain analyst can review.

The local first version of project is packaged as a normal Python application. After creating a Python environment, install it once and run the CLI, API, ingestion service, MCP tools, or Gradio dashboard from anywhere.

## What is included

The implementation now contains a working end-to-end system rather than only a scaffold:

- A Python package named `agentic-scd` with console commands.
- A LangGraph pipeline with a built-in fallback runner when LangGraph is not available.
- Ingestion connectors for RSS, Open-Meteo, synthetic scenarios, Freightos-style snapshots, and a Kaggle-style supply-chain dataset.
- A SQLite persistence layer that works immediately after package installation.
- Batch loaders, deduplication, relevance filtering, input guardrails, and retention cleanup.
- MCP-style external data tools, with a real FastMCP server when the optional `mcp` package is installed.
- Agent stages for event analysis, risk classification, impact mapping, demand forecasting, Monte Carlo simulation, and mitigation recommendation.
- A Gradio dashboard with executive KPIs, signal monitoring, impact mapping, forecast, simulation, mitigation, trace JSON, and local KB Q&A.
- A FastAPI service for `/run`, `/collect`, `/signals`, `/runs`, and health checks.
- Packaged demo datasets, scenario library, local network knowledge base, playbooks, and synthetic classifier corpus.

The default runtime is offline-safe. Live RSS and weather calls are attempted by the collector, but cached fallback data is used automatically when the network is unavailable.

## Local First Project layout (embedded inside the Notebook based Proect)

```text
Capstone_Agentic_Supply_Chain/
├── pyproject.toml
├── README.md
├── backend/
│   ├── pyproject.toml
│   ├── src/agentic_scd/
│   │   ├── agents/
│   │   ├── api/
│   │   ├── assets/
│   │   ├── config/
│   │   ├── data/
│   │   ├── db/
│   │   ├── evaluation/
│   │   ├── graph/
│   │   ├── ingestion/
│   │   ├── llm/
│   │   ├── mcp/
│   │   ├── rag/
│   │   └── ui/
│   ├── data/
│   ├── tests/
│   └── notebooks/
├── docker-compose.yml
└── .env.example
```
The root `pyproject.toml` makes the repository installable from the project root. The `backend/pyproject.toml` is kept for people who prefer working inside `backend/`.

## Install with pyenv or venv

From the unzipped project root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```
With `pyenv`, one clean path is:

```bash
pyenv install 3.11.9
pyenv virtualenv 3.11.9 agentic-scd
pyenv activate agentic-scd
python -m pip install --upgrade pip
python -m pip install -e .
```

The package stores its local SQLite database, snapshots, generated data, and run traces under `~/.agentic_scd` by default. To keep everything inside the project folder during a demo, set:

```bash
export AGENTIC_SCD_HOME="$PWD/.agentic_scd"

## Run the project

Start with one packaged demo scenario:

```bash
agentic-scd --scenario "Typhoon approaching Shanghai Port"
```

Run the default pipeline without naming a scenario:

```bash
agentic-scd
```

Print the full structured state:

```bash
agentic-scd --scenario "Supplier quality failure" --json
```

Load the historical seed snapshots and run retention cleanup:

```bash
agentic-scd-batch
```

Refresh external data connectors once. This tries live RSS and Open-Meteo first, then falls back to cached data when needed:

```bash
agentic-scd-collect
```

Generate the 300-row synthetic disruption corpus used for classifier experiments:

```bash
agentic-scd-generate-data
```

Run a small deterministic evaluation harness:

```bash
agentic-scd-evaluate
```

## Gradio dashboard

Launch the dashboard:

```bash
agentic-scd-dashboard
```

Open:

```text
http://127.0.0.1:7860
```

Try these built-in scenarios from the dropdown:

- Typhoon approaching Shanghai Port
- Supplier quality failure
- Packaging supplier labor strike
- Freight price shock
- Tariff policy change

The dashboard has tabs for the executive overview, risk monitor, impact map, demand forecast, simulation lab, mitigation plan, trace JSON, and local knowledge-base Q&A.

## FastAPI service

Start the API:

```bash
agentic-scd-api
```

Open the docs:

```text
http://127.0.0.1:8000/docs
```

Useful calls:

```bash
curl -X POST http://127.0.0.1:8000/run \
  -H "Content-Type: application/json" \
  -d '{"scenario_name":"Packaging supplier labor strike"}'

curl -X POST http://127.0.0.1:8000/collect
curl http://127.0.0.1:8000/runs
curl http://127.0.0.1:8000/signals
```

Push a synthetic supplier event through the webhook:

```bash
curl -X POST http://127.0.0.1:8000/signals \
  -H "Content-Type: application/json" \
  -d '{
    "title":"Supplier D temporary shutdown after flood damage",
    "body":"The supplier expects a seven day production delay and partial shipment backlog.",
    "location":{"region":"Netherlands","hub_port":"Rotterdam DC"},
    "payload":{"supplier":"Supplier D","severity_hint":"high"}
  }'
```

Then run:

```bash
agentic-scd
```

## Ingestion service

The ingestion service runs a supplier webhook and, by default, a scheduled collector:

```bash
agentic-scd-ingest
```

It listens on `127.0.0.1:8001` unless changed in the environment.

```bash
curl http://127.0.0.1:8001/health
curl -X POST http://127.0.0.1:8001/collect
```

Send the built-in supplier webhook demo events to the ingestion service:

```bash
agentic-scd-send-event
```

Or send them to a custom URL:

```bash
agentic-scd-send-event http://127.0.0.1:8001
```

The same helper is still available for direct script-style use:

```bash
python scripts/send_synthetic_event.py http://127.0.0.1:8001
```

## MCP external data tools

Print the MCP tool manifest:

```bash
agentic-scd-mcp --manifest
```

Call a tool directly without running a server:

```bash
agentic-scd-mcp --tool fetch_weather_hubs --args '{"live":false}'
agentic-scd-mcp --tool load_freight_snapshot
agentic-scd-mcp --tool synthetic_scenarios --args '{"count":2}'
```

When the optional `mcp` package is installed, `agentic-scd-mcp` starts a FastMCP stdio server and exposes these tools:

- `fetch_rss_signals`
- `fetch_weather_hubs`
- `load_freight_snapshot`
- `load_supply_dataset`
- `synthetic_scenarios`

Install optional integrations with:

```bash
python -m pip install -e '.[full]'
```

The project does not require the optional extras for the default CLI, dashboard, API, ingestion, or evaluation flow.

## Environment variables

Copy `.env.example` to `.env` only when you want to override defaults:

```bash
cp .env.example .env
```

Most demos do not need a `.env` file. Important settings are:

```text
AGENTIC_SCD_HOME=.agentic_scd
DATABASE_URL=sqlite:///.agentic_scd/agentic_scd.sqlite
GROQ_API_KEY=
USE_MOCK_LLM=true
INGEST_POLL_INTERVAL_MINUTES=10
SIMULATION_ITERATIONS=300
GRADIO_SHARE=false
```

If `GROQ_API_KEY` is empty, the LLM wrapper returns deterministic offline text. The mitigation agent is already grounded in local playbooks, so the core demo remains reliable without an API key.

## Docker path

Docker is optional. The package path above is the simplest way to run the system. To run the local app in Docker:

```bash
cp .env.example .env
mkdir -p .agentic_scd
docker compose up --build
```

Then open:

```text
http://127.0.0.1:7860
```

The Docker image uses the same SQLite-backed local runtime and persists data in the `.agentic_scd` folder mounted from the host.

## A typical demo flow

A clean five-minute demo can use this order:

```bash
export AGENTIC_SCD_HOME="$PWD/.agentic_scd"
agentic-scd-batch
agentic-scd-collect
agentic-scd --scenario "Typhoon approaching Shanghai Port"
agentic-scd-dashboard
```

In the dashboard, run the same typhoon scenario, then switch to supplier quality failure and packaging supplier labor strike. The three cases show high-path simulation, medium-path forecast plus impact mapping, and labor disruption mitigation.

## Notes on implementation choices

The original architecture called for PostgreSQL, Chroma, Prophet, DistilBERT, and Groq. The code keeps those seams but makes the installed package reliable on a fresh machine by using SQLite, a local lexical classifier, a lightweight retrieval layer, a NumPy forecaster, and a Monte Carlo simulation by default. The optional `full` extra is where heavier integrations can be plugged in without changing the public commands.


### Source-install build backend note

This release uses the small local `build_backend.py` file to build the package from source. A clean `pyenv` or `venv` can now run `python -m pip install .` without needing setuptools inside pip's temporary build-isolation environment. If an older checkout fails with `Cannot import 'setuptools.build_meta'`, remove that older unpacked folder, unzip this release, and reinstall from the project root.

## Test import hygiene

The repository now protects both supported pytest entry points from an older installed `agentic-scd` copy in the active virtual environment. Run either command after reinstalling the package:

```bash
python3 -m pytest backend/tests
cd backend && python3 -m pytest tests
```

For a direct import sanity check from the project root, run:

```bash
PYTHONPATH="$PWD/backend/src:$PWD/scripts:$PWD" python3 -c "import agentic_scd, pathlib; print(agentic_scd.__version__); print(pathlib.Path(agentic_scd.__file__).resolve())"
```

The path should point into this checkout's `backend/src/agentic_scd` folder.

## Troubleshooting

A few Gradio and Starlette releases print a repeated warning like this while the browser is polling the queue:

```text
StarletteDeprecationWarning: 'HTTP_422_UNPROCESSABLE_ENTITY' is deprecated.
```

It is a dependency warning, not a failed pipeline run. Version 1.0.5 suppresses that known warning inside the dashboard and API entry points, so reinstalling the package from this folder is enough:

```bash
python -m pip install -e .
agentic-scd-dashboard
```

If the browser is already open, stop the old dashboard process with `Ctrl+C`, start it again, and refresh the page.

## References

- [Facebook Prophet Documentation](https://facebook.github.io/prophet/)
- [SimPy Documentation](https://simpy.readthedocs.io/en/latest/)
- [Feedparser Documentation](https://feedparser.readthedocs.io/en/latest/)
- [DistilBERT Model Documentation](https://huggingface.co/distilbert-base-uncased)
- [Open-Meteo API](https://open-meteo.com/)
- [Freightos Baltic Index](https://fbx.freightos.com/)

---

*Capstone Project — IISc / TalentSprint (Part of Accenture).*
