# Agentic Supply Chain Disruption Predictor & Simulation Engine

This is a local-first capstone project for predicting supply-chain disruptions, estimating business impact, and simulating mitigation options. It turns external signals such as RSS news, Open-Meteo weather alerts, freight snapshots, supplier webhook events, and packaged historical data into a ranked action plan that a supply-chain analyst can review.

The project is packaged as a normal Python application. After creating a Python environment, install it once and run the CLI, API, ingestion service, MCP tools, or Gradio dashboard from anywhere.

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

## Project layout

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

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
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
```

On Windows PowerShell:

```powershell
$env:AGENTIC_SCD_HOME="$PWD\.agentic_scd"
```

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

The version should be `1.0.5`, and the path should point into this checkout's `backend/src/agentic_scd` folder.

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
