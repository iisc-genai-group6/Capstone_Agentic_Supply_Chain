from __future__ import annotations

from agentic_scd.config import Settings
from agentic_scd.db import connect, init_db
from agentic_scd.ingestion.batch_cli import run as run_batch
from agentic_scd.ingestion.collect import collect
from agentic_scd.mcp.external_data import ExternalDataMCP


def settings(tmp_path):
    return Settings(data_dir=tmp_path, database_url=f"sqlite:///{tmp_path / 'test.sqlite'}")


def test_batch_and_collect_persist_to_sqlite(tmp_path):
    cfg = settings(tmp_path)
    batch, _ = run_batch(cfg, do_load=True, do_retain=False)
    summary = collect(cfg)
    assert batch is not None
    assert batch.totals.loaded >= 1
    assert summary.totals.fetched >= 1
    init_db(cfg)
    with connect(cfg) as conn:
        count = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    assert count >= summary.totals.persisted


def test_mcp_manifest_and_tool_call():
    mcp = ExternalDataMCP()
    names = {tool["name"] for tool in mcp.list_tools()}
    assert "fetch_weather_hubs" in names
    result = mcp.call_tool("synthetic_scenarios", {"count": 1})
    assert len(result["items"]) == 1
