from __future__ import annotations


def placeholders(count: int, style: str) -> str:
    token = "%s" if style == "pyformat" else "?"
    return ",".join(token for _ in range(count))


def style_for(conn) -> str:
    return "execute" if hasattr(conn, "execute") else "pyformat"


def execute(conn, sql: str, params=None):
    if hasattr(conn, "execute"):
        return conn.execute(sql, params or ())
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur


def fetchone(conn, sql: str, params=None):
    if hasattr(conn, "execute"):
        return conn.execute(sql, params or ()).fetchone()
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchone()


def commit(conn) -> None:
    if hasattr(conn, "commit"):
        conn.commit()
