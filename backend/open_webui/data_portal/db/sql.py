from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from psycopg import sql
from psycopg.rows import dict_row

Statement = sql.Composable | str


def table_identifier(schema: str, name: str) -> sql.Identifier:
    return sql.Identifier(schema, name)


def column_list(names: Iterable[str]) -> sql.Composed:
    return sql.SQL(', ').join(sql.Identifier(name) for name in names)


def placeholders(count: int) -> sql.Composed:
    return sql.SQL(', ').join(sql.Placeholder() * count)


def query(conn, statement: Statement, params: Sequence[Any] | None = None) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(statement, params)
        return cur.fetchall()


def query_one(conn, statement: Statement, params: Sequence[Any] | None = None) -> dict | None:
    rows = query(conn, statement, params)
    return rows[0] if rows else None


def scalar(conn, statement: Statement, params: Sequence[Any] | None = None) -> Any:
    with conn.cursor() as cur:
        cur.execute(statement, params)
        row = cur.fetchone()
        return None if row is None else row[0]


def execute(conn, statement: Statement, params: Sequence[Any] | None = None) -> int:
    with conn.cursor() as cur:
        cur.execute(statement, params)
        return cur.rowcount


def execute_many(conn, statement: Statement, rows: Sequence[Sequence[Any]]) -> None:
    if not rows:
        return
    with conn.cursor() as cur:
        cur.executemany(statement, rows)
