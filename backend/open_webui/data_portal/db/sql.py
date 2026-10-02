"""Dựng câu SQL an toàn — cấm nối chuỗi.

Mọi định danh (tên schema, tên bảng, tên cột) đi qua `psycopg.sql.Identifier`
và mọi giá trị đi qua tham số.

Tên bảng và tên cột trong portal đến từ khai báo bộ bảng, đã qua biểu thức
`^[a-z][a-z0-9_]*$` ở `registry/schema.py`, nhưng vẫn bọc `Identifier` — không
dựa vào một lớp kiểm tra duy nhất cho việc bảo mật.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from psycopg import sql
from psycopg.rows import dict_row

Sql = sql.Composable


def bang(schema: str, ten: str) -> sql.Identifier:
    return sql.Identifier(schema, ten)



def danh_sach_cot(ten: Iterable[str]) -> sql.Composed:
    return sql.SQL(", ").join(sql.Identifier(t) for t in ten)


def cho_cho(n: int) -> sql.Composed:
    return sql.SQL(", ").join(sql.Placeholder() * n)


def query(conn, cau: Sql | str, tham_so: Sequence[Any] | None = None) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(cau, tham_so)
        return cur.fetchall()


def query_one(conn, cau: Sql | str, tham_so: Sequence[Any] | None = None) -> dict | None:
    rows = query(conn, cau, tham_so)
    return rows[0] if rows else None


def scalar(conn, cau: Sql | str, tham_so: Sequence[Any] | None = None) -> Any:
    with conn.cursor() as cur:
        cur.execute(cau, tham_so)
        row = cur.fetchone()
        return None if row is None else row[0]


def execute(conn, cau: Sql | str, tham_so: Sequence[Any] | None = None) -> int:
    with conn.cursor() as cur:
        cur.execute(cau, tham_so)
        return cur.rowcount


def execute_many(conn, cau: Sql | str, hang: Sequence[Sequence[Any]]) -> None:
    if not hang:
        return
    with conn.cursor() as cur:
        cur.executemany(cau, hang)
