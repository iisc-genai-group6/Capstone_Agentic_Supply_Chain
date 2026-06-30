# agentic-scd backend

The backend contains the importable `agentic_scd` package used by the CLI, Gradio dashboard, FastAPI service, ingestion service, MCP tools, synthetic webhook sender, and evaluation harness.

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
agentic-scd-send-event http://127.0.0.1:8001
```

The package stores runtime data in `~/.agentic_scd` unless `AGENTIC_SCD_HOME` is set.


### Source-install build backend note

This release uses the small local `build_backend.py` file to build the package from source. A clean `pyenv` or `venv` can now run `python -m pip install .` without needing setuptools inside pip's temporary build-isolation environment. If an older checkout fails with `Cannot import 'setuptools.build_meta'`, remove that older unpacked folder, unzip this release, and reinstall from the project root.

## Test import hygiene

The repository now protects both supported pytest entry points from an older installed `agentic-scd` copy in the active virtual environment. From the backend folder, run:

```bash
python3 -m pytest tests
```

For a direct import sanity check from the backend folder, run:

```bash
PYTHONPATH="$PWD/src:$PWD/../scripts:$PWD/.." python3 -c "import agentic_scd, pathlib; print(agentic_scd.__version__); print(pathlib.Path(agentic_scd.__file__).resolve())"
```

The version should be `1.0.5`, and the path should point into this checkout's `src/agentic_scd` folder.

## Troubleshooting

Some Gradio and Starlette combinations emit a repeated `HTTP_422_UNPROCESSABLE_ENTITY` deprecation warning while the UI queue is active. The application filters that known dependency warning at startup. Reinstall the package and restart `agentic-scd-dashboard` if an older editable install is still running.
