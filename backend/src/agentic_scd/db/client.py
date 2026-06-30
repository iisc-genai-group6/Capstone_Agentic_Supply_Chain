from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from agentic_scd.config import Settings, get_settings

CONNECT_TIMEOUT_SECONDS = 5


class DatabaseNotConfiguredError(RuntimeError):
    pass


@dataclass(frozen=True)
class PingResult:
    ok: bool
    detail: str

    def __bool__(self) -> bool:
        return self.ok


def database_dialect(database_url: str | None) -> str | None:
    if not database_url:
        return None
    lowered = database_url.lower()
    if lowered.startswith("sqlite:"):
        return "sqlite"
    if lowered.startswith("postgresql:") or lowered.startswith("postgres:"):
        return "postgres"
    return None


def sqlite_path(database_url: str) -> Path:
    if database_url.startswith("sqlite:///"):
        return Path(unquote(database_url.replace("sqlite:///", "", 1))).expanduser()
    if database_url.startswith("sqlite://"):
        parsed = urlparse(database_url)
        return Path(unquote(parsed.path)).expanduser()
    raise DatabaseNotConfiguredError(
        "SQLite URL expected. Use sqlite:////path/to/agentic_scd.sqlite."
    )


def translate_sql(sql: str) -> str:
    text = sql
    text = re.sub(
        r"now\(\)\s*-\s*interval\s+'(\d+)\s+days'",
        r"datetime('now', '-\1 days')",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"now\(\)\s*-\s*make_interval\(days\s*=>\s*%s\)",
        "datetime('now', '-' || %s || ' days')",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"now\(\)\s*-\s*make_interval\(days\s*=>\s*\?\)",
        "datetime('now', '-' || ? || ' days')",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\bnow\(\)", "CURRENT_TIMESTAMP", text, flags=re.IGNORECASE)
    text = text.replace("%s", "?")
    return text


def adapt_params(params: Any) -> Any:
    if params is None:
        return ()
    return params


class CompatCursor:
    def __init__(self, cursor: sqlite3.Cursor) -> None:
        self._cursor = cursor

    def __enter__(self) -> "CompatCursor":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
        return None

    def execute(self, sql: str, params: Any = None) -> "CompatCursor":
        self._cursor.execute(translate_sql(sql), adapt_params(params))
        return self

    def fetchone(self) -> Any:
        return self._cursor.fetchone()

    def fetchall(self) -> list[Any]:
        return self._cursor.fetchall()

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    def close(self) -> None:
        self._cursor.close()

    def __iter__(self):
        return iter(self._cursor)


class CompatConnection:
    agentic_scd_dialect = "sqlite"

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def __enter__(self) -> "CompatConnection":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        self.close()
        return None

    def execute(self, sql: str, params: Any = None) -> CompatCursor:
        cursor = self._conn.cursor()
        return CompatCursor(cursor).execute(sql, params)

    def executescript(self, sql: str) -> None:
        self._conn.executescript(sql)

    def cursor(self) -> CompatCursor:
        return CompatCursor(self._conn.cursor())

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()

    @property
    def raw(self) -> sqlite3.Connection:
        return self._conn


def connect(
    settings: Settings | None = None, *, connect_timeout: int = CONNECT_TIMEOUT_SECONDS
):
    settings = settings or get_settings()
    url = settings.resolved_database_url
    if not url:
        raise DatabaseNotConfiguredError("No database URL configured")
    dialect = database_dialect(url)
    if dialect == "sqlite":
        path = sqlite_path(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return CompatConnection(conn)
    if dialect == "postgres":
        try:
            import psycopg
        except ImportError as exc:
            raise DatabaseNotConfiguredError(
                "PostgreSQL support requires psycopg. Install the Docker/notebook dependencies or use SQLite."
            ) from exc
        return psycopg.connect(url, connect_timeout=connect_timeout)
    raise DatabaseNotConfiguredError(f"Unsupported DATABASE_URL scheme: {urlparse(url).scheme}")


def ping(settings: Settings | None = None) -> PingResult:
    settings = settings or get_settings()
    if not settings.resolved_database_url:
        return PingResult(ok=False, detail="database not configured")
    try:
        with connect(settings) as conn:
            if getattr(conn, "agentic_scd_dialect", None) == "sqlite":
                row = conn.execute("SELECT 1").fetchone()
            else:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    row = cur.fetchone()
    except Exception as exc:
        message = str(exc).strip().splitlines()[0] if str(exc).strip() else repr(exc)
        return PingResult(ok=False, detail=message)
    if row and row[0] == 1:
        return PingResult(ok=True, detail="SELECT 1 ok")
    return PingResult(ok=False, detail=f"unexpected database response: {row!r}")
