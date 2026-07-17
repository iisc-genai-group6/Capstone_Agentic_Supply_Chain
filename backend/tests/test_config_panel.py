from __future__ import annotations

import os

from agentic_scd.config import get_settings
from agentic_scd.config.localfirst import apply_runtime_env, read_local_env
from agentic_scd.ingestion.relevance import load_lexicon
from agentic_scd.ingestion.registry import load_registry
from agentic_scd.ingestion.store import save_run_result


def test_apply_runtime_env_persists_values(monkeypatch, tmp_path) -> None:
    env_file = tmp_path / "localfirst.env"
    monkeypatch.setattr(
        "agentic_scd.config.localfirst.local_env_path", lambda: env_file
    )
    keys = ["DATABASE_URL", "GROQ_API_KEY", "USE_MOCK_LLM"]
    for key in keys:
        os.environ.pop(key, None)
    try:
        path = apply_runtime_env(
            {
                "DATABASE_URL": "postgresql://user:pass@localhost:5432/agentic",
                "GROQ_API_KEY": "secret-key",
                "USE_MOCK_LLM": "0",
            }
        )
        stored = read_local_env()
        assert path == env_file
        assert stored["DATABASE_URL"].startswith("postgresql://")
        assert stored["GROQ_API_KEY"] == "secret-key"
        assert os.getenv("USE_MOCK_LLM") == "0"
    finally:
        for key in keys:
            os.environ.pop(key, None)


def test_save_run_result_uses_current_data_home(monkeypatch, tmp_path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    monkeypatch.setenv("AGENTIC_SCD_HOME", str(first))
    get_settings.cache_clear()
    path_a = save_run_result(None, "run-a", {"route": "full_path"})
    monkeypatch.setenv("AGENTIC_SCD_HOME", str(second))
    get_settings.cache_clear()
    path_b = save_run_result(None, "run-b", {"route": "full_path"})
    assert path_a.parent == first / "runs"
    assert path_b.parent == second / "runs"
    get_settings.cache_clear()


def test_registry_and_lexicon_follow_runtime_overrides(
    monkeypatch, tmp_path
) -> None:
    sources_path = tmp_path / "sources.yaml"
    lexicon_path = tmp_path / "lexicon.yaml"
    sources_path.write_text(
        "\n".join(
            [
                "sources:",
                "  - name: custom_synthetic",
                "    type: SYNTHETIC",
                "    reliability: 0.8",
                "    enabled: true",
                "    config:",
                "      count: 2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    lexicon_path.write_text(
        "\n".join(["keywords:", "  - harbor closure", "  - customs strike"]) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENTIC_SCD_SOURCES_YAML", str(sources_path))
    monkeypatch.setenv("AGENTIC_SCD_LEXICON_YAML", str(lexicon_path))
    load_lexicon.cache_clear()
    connectors = load_registry()
    terms = load_lexicon()
    assert any(connector.name == "custom_synthetic" for connector in connectors)
    assert terms == ("harbor closure", "customs strike")
    load_lexicon.cache_clear()


def test_vector_database_defaults_to_postgres_when_primary_database_is_postgres(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("AGENTIC_SCD_HOME", str(tmp_path))
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://user:pass@localhost:5432/agentic"
    )
    monkeypatch.delenv("VECTOR_DATABASE_URL", raising=False)
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.database_url == "postgresql://user:pass@localhost:5432/agentic"
    assert settings.vector_database_url == settings.database_url
    get_settings.cache_clear()
