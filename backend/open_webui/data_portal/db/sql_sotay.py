"""Truy vấn sổ tay SQLite — cùng hình dạng hàm với `app/db/sql.py`.

Hai tầng lưu trữ, hai mô-đun truy vấn, cố ý không gộp:

    q  (app/db/sql.py)        -> PostgreSQL, ô giữ chỗ `%s`, `psycopg.sql`
    qs (mô-đun này)           -> SQLite,     ô giữ chỗ `?`

Nhìn tên mô-đun trong một hàm là biết ngay hàm đó đang đọc kho dữ liệu hay đọc
sổ tay. Một lớp trừu tượng chung che cả hai sẽ giấu mất đúng thứ người đọc cần
thấy — nhất là ở chỗ không thể trộn: SQLite và PostgreSQL không chung một giao
dịch được.

Sổ tay có lược đồ cố định, không có tên bảng hay tên cột nào đến từ người dùng,
nên ở đây không cần bộ dựng định danh như `sql.Identifier` bên PostgreSQL.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from typing import Any


def query(conn: sqlite3.Connection, cau: str,
          tham_so: Sequence[Any] | None = None) -> list[dict]:
    cur = conn.execute(cau, tuple(tham_so or ()))
    ten_cot = [m[0] for m in cur.description or []]
    return [dict(zip(ten_cot, hang, strict=True)) for hang in cur.fetchall()]


def query_one(conn: sqlite3.Connection, cau: str,
              tham_so: Sequence[Any] | None = None) -> dict | None:
    hang = query(conn, cau, tham_so)
    return hang[0] if hang else None


def scalar(conn: sqlite3.Connection, cau: str,
           tham_so: Sequence[Any] | None = None) -> Any:
    hang = conn.execute(cau, tuple(tham_so or ())).fetchone()
    return None if hang is None else hang[0]


def execute(conn: sqlite3.Connection, cau: str,
            tham_so: Sequence[Any] | None = None) -> int:
    return conn.execute(cau, tuple(tham_so or ())).rowcount
