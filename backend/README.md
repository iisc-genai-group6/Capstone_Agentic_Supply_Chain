# agentic-scd backend

The backend contains the importable `agentic_scd` package used by the CLI, Gradio dashboard, FastAPI service, ingestion service, MCP tools, and evaluation harness.

Most users should install from the repository root:

```bash
python -m pip install -e .
agentic-scd-dashboard
```

Backend-only development also works:

```bash
cd backend
python -m pip install -e .
agentic-scd --scenario "Typhoon approaching Shanghai Port"
```

The package stores runtime data in `~/.agentic_scd` unless `AGENTIC_SCD_HOME` is set.

## Troubleshooting

Some Gradio and Starlette combinations emit a repeated `HTTP_422_UNPROCESSABLE_ENTITY` deprecation warning while the UI queue is active. The application filters that known dependency warning at startup. Reinstall the package and restart `agentic-scd-dashboard` if an older editable install is still running.
