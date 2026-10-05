"""Ghi lớp gốc.

Mọi dòng không trống được ghi, **mọi giá trị dạng văn bản, y nguyên như tệp**:
không sửa, không suy đoán, không làm tròn. Lớp gốc là bằng chứng phục vụ kiểm
toán, và là đầu vào của đối chiếu R1.
"""

from __future__ import annotations

from datetime import UTC, datetime

from psycopg import sql

from ..db import sql as q
from ..registry.schema import FormTable
from ..sources.base import SourceRow
from .context import LoadContext
from .dedup import bam_dong


def dien_ngoai_tep(table: FormTable, dong: SourceRow, nam: int | None,
                   reader=None) -> SourceRow:
    """Thêm giá trị các cột không lấy từ ô dữ liệu của tệp vào một dòng:

    · `nam` — Năm dữ liệu chọn lúc nạp (QT-02);
    · cột `lay_tu: tieu_de` — đơn vị ghi trong tiêu đề cột ("GIÁ TIỀN (USD)" → USD).

    Lớp gốc giữ văn bản, nên năm cũng ghi dạng văn bản như mọi ô khác. Cột
    `lay_tu: trong` để trống (QT-21).
    """
    them: dict[str, str | None] = {}
    for c in table.columns:
        if c.la_nam:
            them[c.name] = None if nam is None else str(nam)
        elif c.tu_tieu_de and reader is not None and hasattr(reader, "gia_tri_tieu_de"):
            them[c.name] = reader.gia_tri_tieu_de(c.tieu_de)
    return SourceRow(dong.number, {**dong.values, **them}) if them else dong


def ghi(ctx: LoadContext, table: FormTable) -> list[tuple[int, int, str, dict]]:
    """Đọc sheet của `table`, ghi vào `bronze.<t>`.

    Trả `[(bronze_id, source_row, row_hash, giá trị văn bản)]` theo thứ tự đọc,
    để bước kiểm tra giá trị dùng tiếp mà không phải đọc lại tệp.
    """
    cot = table.column_names
    hang = [dien_ngoai_tep(table, r, ctx.nam, ctx.reader)
            for r in ctx.reader.rows(table.sheet, table.anh_xa_tieu_de)]
    ket_qua = ctx.bang(table)
    ket_qua.rows_file = len(hang)

    if not hang:
        ket_qua.rows_bronze = 0
        return []

    luc = datetime.now(UTC)
    cau = sql.SQL(
        "INSERT INTO {} ({}, domain_id, load_id, batch_id, source_sheet, source_row, "
        "loaded_at, row_hash) VALUES ({}, %s, %s, %s, %s, %s, %s, %s) RETURNING row_id"
    ).format(
        sql.Identifier("bronze", table.name),
        q.column_list(cot),
        q.placeholders(len(cot)),
    )

    ra: list[tuple[int, int, str, dict]] = []
    with ctx.conn.cursor() as cur:
        for row in hang:
            row_hash = bam_dong(table.sheet, row.values, cot)
            tham_so = [row.values.get(c) for c in cot]
            tham_so += [ctx.domain_id, ctx.load_id, ctx.batch_id, table.sheet,
                        row.number, luc, row_hash]
            cur.execute(cau, tham_so)
            bronze_id = cur.fetchone()[0]
            ra.append((bronze_id, row.number, row_hash, row.values))

    ket_qua.rows_bronze = len(ra)
    return ra
