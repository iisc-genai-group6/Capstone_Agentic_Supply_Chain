from __future__ import annotations

from fastapi.testclient import TestClient

from agentic_scd.api.app import create_app


def test_api_run_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_SCD_HOME", str(tmp_path))
    client = TestClient(create_app())
    response = client.post("/run", json={"scenario_name": "Supplier quality failure"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["classifications"]
    assert payload["recommendation"]["actions"]
