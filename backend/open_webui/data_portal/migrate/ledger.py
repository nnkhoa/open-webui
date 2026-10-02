"""Sổ phiên bản schema

Ghi từng bước đã chạy kèm mã kiểm tra, nên chạy lại là vô hại và sửa một tệp
đã chạy bị phát hiện ngay.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from pathlib import Path

from psycopg import sql

from ..db import sql as q
from ..errors import MigrationError

TEN_TEP = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")


@dataclass(frozen=True)
class Buoc:
    version: int
    name: str
    sql_text: str
    source: str            # 'manual' | 'generated'

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql_text.encode("utf-8")).hexdigest()

    @property
    def nhan(self) -> str:
        return f"{self.version:04d}_{self.name}"


def doc_cac_buoc(thu_muc: Path) -> list[Buoc]:
    """Đọc `NNNN_ten.sql` ở thư mục gốc (viết tay) và trong `auto/` (sinh ra)."""
    buoc: list[Buoc] = []
    for path, nguon in [(p, "manual") for p in sorted(thu_muc.glob("*.sql"))] + [
        (p, "generated") for p in sorted((thu_muc / "auto").glob("*.sql"))
    ]:
        khop = TEN_TEP.match(path.name)
        if not khop:
            raise MigrationError(
                f"Tên tệp nâng cấp {path.name!r} phải theo dạng NNNN_ten_khong_dau.sql"
            )
        buoc.append(Buoc(int(khop.group(1)), khop.group(2),
                         path.read_text(encoding="utf-8"), nguon))
    so = [b.version for b in buoc]
    trung = {v for v in so if so.count(v) > 1}
    if trung:
        raise MigrationError(f"Số hiệu nâng cấp bị lặp: {sorted(trung)}.")
    return sorted(buoc, key=lambda b: b.version)


def so_da_chay(conn) -> dict[int, str]:
    co_so = q.scalar(
        conn,
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema = 'ctl' AND table_name = 'schema_migration'",
    )
    if not co_so:
        return {}
    return {r["version"]: r["checksum"]
            for r in q.query(conn, "SELECT version, checksum FROM ctl.schema_migration")}


def ap_dung(conn, thu_muc: Path, nguoi_chay: str = "cli") -> list[str]:
    """Áp dụng các bước chưa chạy, theo thứ tự, mỗi bước trong một giao dịch.

    Bước đã chạy mà nội dung đổi ⇒ dừng với lỗi. Tệp nâng cấp đã áp dụng là bất
    biến; muốn đổi thì thêm bước mới.
    """
    cac_buoc = doc_cac_buoc(thu_muc)
    da_chay = so_da_chay(conn)
    ap: list[str] = []
    for buoc in cac_buoc:
        cu = da_chay.get(buoc.version)
        if cu is not None:
            if cu != buoc.checksum:
                raise MigrationError(
                    f"Bước {buoc.nhan} đã chạy nhưng nội dung tệp đã đổi. "
                    f"Tệp nâng cấp đã áp dụng là bất biến — hãy thêm một bước mới."
                )
            continue
        chay_mot_buoc(conn, buoc, nguoi_chay)
        conn.commit()
        ap.append(buoc.nhan)
    return ap


def chay_mot_buoc(conn, buoc: Buoc, nguoi_chay: str) -> None:
    """Chạy một bước và ghi sổ, **không chốt giao dịch** — người gọi chốt."""
    bat_dau = time.monotonic()
    with conn.cursor() as cur:
        cur.execute(buoc.sql_text)
    ms = int((time.monotonic() - bat_dau) * 1000)
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL(
                "INSERT INTO ctl.schema_migration "
                "(version, name, checksum, source, applied_by, duration_ms) "
                "VALUES (%s, %s, %s, %s, %s, %s)"
            ),
            (buoc.version, buoc.name, buoc.checksum, buoc.source, nguoi_chay, ms),
        )
