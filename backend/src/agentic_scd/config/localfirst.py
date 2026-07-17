from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

LOCAL_ENV_FILENAME = "localfirst.env"


@dataclass(frozen=True)
class ConfigField:
    name: str
    label: str
    section: str
    kind: str = "text"
    secret: bool = False


CONFIG_FIELDS: tuple[ConfigField, ...] = (
    ConfigField("AGENTIC_SCD_HOME", "Data home", "Storage"),
    ConfigField("DATABASE_URL", "Database URL", "Storage"),
    ConfigField("VECTOR_DATABASE_URL", "Vector DB URL", "Storage"),
    ConfigField("AGENTIC_SCD_SOURCES_YAML", "Sources YAML", "Storage"),
    ConfigField("AGENTIC_SCD_LEXICON_YAML", "Lexicon YAML", "Storage"),
    ConfigField("GROQ_API_KEY", "Groq API key", "LLM", secret=True),
    ConfigField("GROQ_MODEL", "Groq model", "LLM"),
    ConfigField("USE_MOCK_LLM", "Use mock LLM", "LLM", kind="bool"),
    ConfigField("RAG_AUTO_REBUILD", "RAG auto rebuild", "RAG", kind="bool"),
    ConfigField(
        "INGEST_POLL_INTERVAL_MINUTES",
        "Ingest poll interval minutes",
        "Ingestion",
    ),
    ConfigField(
        "INGEST_SCHEDULER_ENABLED",
        "Ingest scheduler enabled",
        "Ingestion",
        kind="bool",
    ),
    ConfigField("INGEST_HOST", "Ingest host", "Ingestion"),
    ConfigField("INGEST_PORT", "Ingest port", "Ingestion"),
    ConfigField(
        "WEBHOOK_SOURCE_RELIABILITY",
        "Webhook source reliability",
        "Ingestion",
    ),
    ConfigField("BATCH_ENABLED", "Batch enabled", "Operations", kind="bool"),
    ConfigField(
        "RETENTION_ENABLED", "Retention enabled", "Operations", kind="bool"
    ),
    ConfigField(
        "RETENTION_REJECTED_TTL_DAYS",
        "Rejected retention days",
        "Operations",
    ),
    ConfigField(
        "RETENTION_SIGNALS_TTL_DAYS",
        "Signal retention days",
        "Operations",
    ),
    ConfigField("SIMULATION_ITERATIONS", "Simulation iterations", "Operations"),
    ConfigField("GRADIO_SHARE", "Gradio share", "Dashboard", kind="bool"),
    ConfigField("GRADIO_SERVER_NAME", "Gradio server name", "Dashboard"),
    ConfigField("OPENAI_API_KEY", "OpenAI API key", "Optional", secret=True),
    ConfigField("HF_TOKEN", "HF token", "Optional", secret=True),
    ConfigField("XAI_API_KEY", "xAI API key", "Optional", secret=True),
)

CONFIG_FIELD_NAMES = tuple(field.name for field in CONFIG_FIELDS)


def local_env_path() -> Path:
    return Path.home() / ".agentic_scd" / LOCAL_ENV_FILENAME


def should_apply_local_env_defaults() -> bool:
    if os.getenv("AGENTIC_SCD_IGNORE_LOCAL_ENV", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return False
    return "pytest" not in sys.modules


def read_local_env() -> dict[str, str]:
    path = local_env_path()
    if not path.exists():
        return {}
    return {
        key: str(value)
        for key, value in dotenv_values(path).items()
        if value is not None
    }


def apply_local_env_defaults() -> dict[str, str]:
    if not should_apply_local_env_defaults():
        return {}
    values = read_local_env()
    for key, value in values.items():
        os.environ.setdefault(key, value)
    return values


def normalize_env_value(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def quote_env_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    if any(ch.isspace() for ch in value) or any(ch in value for ch in "#'\"\\"):
        return f'"{escaped}"'
    return value


def persist_local_env(values: dict[str, str | None]) -> Path:
    merged = {key: value for key, value in read_local_env().items() if key in CONFIG_FIELD_NAMES}
    for key, value in values.items():
        if key not in CONFIG_FIELD_NAMES:
            continue
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    path = local_env_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}={quote_env_value(value)}" for key, value in sorted(merged.items())]
    content = "\n".join(lines)
    if content:
        content += "\n"
    path.write_text(content, encoding="utf-8")
    return path


def apply_runtime_env(values: dict[str, object]) -> Path:
    normalized = {
        key: normalize_env_value(value)
        for key, value in values.items()
        if key in CONFIG_FIELD_NAMES
    }
    for key, value in normalized.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    return persist_local_env(normalized)
