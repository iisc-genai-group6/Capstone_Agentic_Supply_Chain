from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any
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


def translate_sql(sql: str) -> str:
    text = sql
    text = re.sub(r"now\(\)\s*-\s*interval\s+'(\d+)\s+days'", r"datetime('now', '-\1 days')", text, flags=re.IGNORECASE)
    text = re.sub(r"now\(\)\s*-\s*make_interval\(days\s*=>\s*%s\)", "datetime('now', '-' || %s || ' days')", text, flags=re.IGNORECASE)
    text = re.sub(r"now\(\)\s*-\s*make_interval\(days\s*=>\s*\?\)", "datetime('now', '-' || ? || ' days')", text, flags=re.IGNORECASE)
    text = text.replace("%s", "?")
    text = re.sub(r"\bnow\(\)", "CURRENT_TIMESTAMP", text, flags=re.IGNORECASE)
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


def connect(settings: Settings | None = None) -> CompatConnection:
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
    return CompatConnection(conn)


def ping(settings: Settings | None = None) -> PingResult:
    try:
        with connect(settings) as conn:
            row = conn.execute("SELECT 1").fetchone()
    except DatabaseNotConfiguredError as exc:
        return PingResult(ok=False, detail=f"database not configured: {exc}")
    except Exception as exc:
        return PingResult(ok=False, detail=str(exc))
    if row and row[0] == 1:
        return PingResult(ok=True, detail="SELECT 1 ok")
    return PingResult(ok=False, detail="unexpected database response")
