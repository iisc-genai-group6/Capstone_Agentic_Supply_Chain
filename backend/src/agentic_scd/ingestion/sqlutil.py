from __future__ import annotations


def dialect(conn) -> str:
    return getattr(conn, "agentic_scd_dialect", None) or "postgres"


def placeholders(count: int, style: str) -> str:
    token = "%s" if style == "pyformat" else "?"
    return ",".join(token for _ in range(count))


def style_for(conn) -> str:
    return "sqlite" if dialect(conn) == "sqlite" else "pyformat"


def execute(conn, sql: str, params=None):
    if dialect(conn) == "sqlite":
        return conn.execute(sql, params or ())
    cur = conn.cursor()
    cur.execute(sql, params or ())
    return cur


def fetchone(conn, sql: str, params=None):
    if dialect(conn) == "sqlite":
        return conn.execute(sql, params or ()).fetchone()
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchone()


def fetchall(conn, sql: str, params=None):
    if dialect(conn) == "sqlite":
        return conn.execute(sql, params or ()).fetchall()
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchall()


def commit(conn) -> None:
    if hasattr(conn, "commit"):
        conn.commit()
