from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from typing import Any


def query(conn: sqlite3.Connection, statement: str, params: Sequence[Any] | None = None) -> list[dict]:
    cur = conn.execute(statement, tuple(params or ()))
    columns = [description[0] for description in cur.description or []]
    return [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]


def query_one(conn: sqlite3.Connection, statement: str, params: Sequence[Any] | None = None) -> dict | None:
    rows = query(conn, statement, params)
    return rows[0] if rows else None


def scalar(conn: sqlite3.Connection, statement: str, params: Sequence[Any] | None = None) -> Any:
    row = conn.execute(statement, tuple(params or ())).fetchone()
    return None if row is None else row[0]


def execute(conn: sqlite3.Connection, statement: str, params: Sequence[Any] | None = None) -> int:
    return conn.execute(statement, tuple(params or ())).rowcount
