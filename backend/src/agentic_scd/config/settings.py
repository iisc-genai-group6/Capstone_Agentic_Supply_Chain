from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
DEFAULT_DATA_DIR = Path.home() / ".agentic_scd"


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw.strip())
    except ValueError:
        return default


def resolve_data_dir() -> Path:
    raw = os.getenv("AGENTIC_SCD_HOME")
    path = Path(raw).expanduser() if raw else DEFAULT_DATA_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_database_url(data_dir: Path) -> str:
    explicit = os.getenv("DATABASE_URL")
    if explicit:
        return explicit
    return f"sqlite:///{data_dir / 'agentic_scd.sqlite'}"


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=resolve_data_dir)
    database_url: str | None = None
    groq_api_key: str | None = None
    groq_model: str = DEFAULT_GROQ_MODEL
    use_mock_llm: bool = True
    ingest_poll_interval_minutes: int = 10
    ingest_scheduler_enabled: bool = True
    ingest_host: str = "127.0.0.1"
    ingest_port: int = 8001
    webhook_source_reliability: float = 0.6
    batch_enabled: bool = True
    retention_enabled: bool = True
    retention_rejected_ttl_days: int = 30
    retention_signals_ttl_days: int = 90
    simulation_iterations: int = 300
    dashboard_share: bool = False

    @property
    def resolved_database_url(self) -> str | None:
        return self.database_url if self.database_url is not None else build_database_url(self.data_dir)

    @property
    def llm_is_mock(self) -> bool:
        return self.use_mock_llm or not self.groq_api_key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()
    data_dir = resolve_data_dir()
    return Settings(
        data_dir=data_dir,
        database_url=build_database_url(data_dir),
        groq_api_key=os.getenv("GROQ_API_KEY") or None,
        groq_model=os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL),
        use_mock_llm=env_flag("USE_MOCK_LLM", default=True),
        ingest_poll_interval_minutes=env_int("INGEST_POLL_INTERVAL_MINUTES", 10),
        ingest_scheduler_enabled=env_flag("INGEST_SCHEDULER_ENABLED", default=True),
        ingest_host=os.getenv("INGEST_HOST", "127.0.0.1"),
        ingest_port=env_int("INGEST_PORT", 8001),
        webhook_source_reliability=env_float("WEBHOOK_SOURCE_RELIABILITY", 0.6),
        batch_enabled=env_flag("BATCH_ENABLED", default=True),
        retention_enabled=env_flag("RETENTION_ENABLED", default=True),
        retention_rejected_ttl_days=env_int("RETENTION_REJECTED_TTL_DAYS", 30),
        retention_signals_ttl_days=env_int("RETENTION_SIGNALS_TTL_DAYS", 90),
        simulation_iterations=env_int("SIMULATION_ITERATIONS", 300),
        dashboard_share=env_flag("GRADIO_SHARE", default=False),
    )
