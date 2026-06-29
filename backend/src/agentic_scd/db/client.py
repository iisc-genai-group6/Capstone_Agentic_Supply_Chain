from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from agentic_scd.config import Settings, get_settings


class DatabaseNotConfiguredError(RuntimeError):
    pass


@dataclass(frozen=True)
class PingResult:
    ok: bool
    detail: str

    def __bool__(self) -> bool:
        return self.ok


def sqlite_path(database_url: str) -> Path:
    if database_url.startswith("sqlite:///"):
        return Path(unquote(database_url.replace("sqlite:///", "", 1))).expanduser()
    if database_url.startswith("sqlite://"):
        parsed = urlparse(database_url)
        return Path(unquote(parsed.path)).expanduser()
    raise DatabaseNotConfiguredError(
        "The packaged runtime uses SQLite. Set DATABASE_URL=sqlite:////path/to/file.db."
    )


def connect(settings: Settings | None = None) -> sqlite3.Connection:
    settings = settings or get_settings()
    url = settings.resolved_database_url
    if not url:
        raise DatabaseNotConfiguredError("No database URL configured")
    path = sqlite_path(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ping(settings: Settings | None = None) -> PingResult:
    try:
        with connect(settings) as conn:
            row = conn.execute("SELECT 1").fetchone()
    except Exception as exc:
        return PingResult(ok=False, detail=str(exc))
    if row and row[0] == 1:
        return PingResult(ok=True, detail="SELECT 1 ok")
    return PingResult(ok=False, detail="unexpected database response")
