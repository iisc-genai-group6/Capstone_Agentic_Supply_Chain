from __future__ import annotations

from pathlib import Path

from agentic_scd.config import get_settings
from agentic_scd.db.client import sqlite_path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKUPS_DIR = BACKEND_ROOT / "data" / "backups"


def database_path() -> Path:
    settings = get_settings()
    url = settings.resolved_database_url
    if not url:
        raise RuntimeError("No SQLite database URL configured")
    return sqlite_path(url)
