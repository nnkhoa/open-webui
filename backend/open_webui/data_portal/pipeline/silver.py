"""Dựng lớp chuẩn hoá

Cơ chế: **phiên bản theo lô**, không ghi đè tại chỗ.

    · dòng mới hoàn toàn            → thêm, is_current = true
    · dòng cũ, nội dung y hệt       → không ghi gì, giữ nguyên bản hiện hành
    · dòng cũ, nội dung đổi         → bản cũ hết hiệu lực, thêm bản mới
    · (replace_partition) dòng hiện hành thuộc kỳ mà tệp mới chạm tới nhưng tệp
      mới không có  → coi như NBC đã xoá, đánh dấu hết hiệu lực

Nhờ vậy "sửa một ô rồi nạp lại" là **ghi đè có lịch sử**: số dòng hiện hành
không tăng, bản cũ vẫn truy được qua `is_current = false`. Gỡ một lần nạp chỉ
tốn chi phí bằng kích thước lô, không phải dựng lại toàn kho.

Không có bước nào ở đây quét toàn bộ kho: mọi câu đều bị giới hạn theo
`domain_id` cộng khoá nghiệp vụ hoặc kỳ, đều có chỉ mục.
"""

from __future__ import annotations

from datetime import UTC, datetime

from psycopg import sql

from ..db import sql as q
from ..registry.schema import FormTable
from .context import DongSach, LoadContext


def _ten_tam(table: FormTable) -> str:
    return f"stg_{table.name}"


def _dieu_kien_khoa(table: FormTable, trai: str, phai: str) -> sql.Composed:
    """`a.bk1 IS NOT DISTINCT FROM b.bk1 AND …` — NULL so bằng NULL.

    Dùng `IS NOT DISTINCT FROM` chứ không dùng `=` vì cột khoá có thể rỗng ở
    những bảng mà cột đó không bắt buộc (ví dụ `ma_khach` của bảng Chi phí khi
    cấp phân bổ là toàn công ty).
    """
    return sql.SQL(" AND ").join(
        sql.SQL("{}.{} IS NOT DISTINCT FROM {}.{}").format(
            sql.Identifier(trai), sql.Identifier(c),
            sql.Identifier(phai), sql.Identifier(c),
        )
        for c in table.business_key
    )


def ky_da_ep_kieu(ctx: LoadContext, table: FormTable) -> list:
    """Kỳ mà lô chạm tới, ở đúng kiểu của cột phân vùng.

    `ctx.ky_cham_toi` giữ dạng hiển thị (`2026-01`) để in lên màn hình; câu SQL
    thì cần đúng kiểu cột (`date`), nên ép lại qua chính bộ xử lý kiểu của cột.
    """
    if not table.partition_by:
        return []
    col = table.partition_column
    ra = []
    for ky in sorted(ctx.ky_cham_toi.get(table.name, set())):
        phan = col.handler.parse(ky)
        ra.append(phan.value if phan.ok else ky)
    return ra


def dieu_kien_nam(table: FormTable, nam: int | None, bi_danh: str
                  ) -> tuple[sql.Composable, list]:
    """` AND s.nam IS NOT DISTINCT FROM %s` với bảng có cột năm (QT-02): tháng 1/2026
    và tháng 1/2027 là hai kỳ khác nhau, nạp lại chỉ thay kỳ của đúng năm đã chọn."""
    cot = table.year_column
    if cot is None:
        return sql.SQL(""), []
    return (sql.SQL(" AND {}.{} IS NOT DISTINCT FROM %s").format(
        sql.Identifier(bi_danh), sql.Identifier(cot.name)), [nam])


def _tao_bang_tam(ctx: LoadContext, table: FormTable, dong: list[DongSach]) -> None:
    cot = table.column_names
    dinh_nghia = sql.SQL(", ").join(
        [sql.SQL("{} {}").format(sql.Identifier(c.name), sql.SQL(c.silver_sql_type))
         for c in table.columns]
        + [sql.SQL("row_hash char(64)"), sql.SQL("bronze_id bigint"),
           sql.SQL("source_row int")]
    )
    ten = sql.Identifier(_ten_tam(table))
    q.execute(ctx.conn, sql.SQL("DROP TABLE IF EXISTS {}").format(ten))
    q.execute(ctx.conn,
              sql.SQL("CREATE TEMP TABLE {} ({}) ON COMMIT DROP").format(ten, dinh_nghia))
    if not dong:
        return
    q.execute_many(
        ctx.conn,
        sql.SQL("INSERT INTO {} ({}, row_hash, bronze_id, source_row) VALUES ({})").format(
            ten, q.column_list(cot), q.placeholders(len(cot) + 3)
        ),
        [[d.values.get(c) for c in cot] + [d.row_hash, d.bronze_id, d.source_row]
         for d in dong],
    )


def hop_nhat(ctx: LoadContext, table: FormTable, dong: list[DongSach]) -> None:
    """Đưa các dòng đã ép kiểu vào `silver.<t>` theo chiến lược khai ở bộ bảng."""
    ket_qua = ctx.bang(table)
    _tao_bang_tam(ctx, table, dong)
    tam = sql.Identifier(_ten_tam(table))
    dich = sql.Identifier("silver", table.name)
    luc = datetime.now(UTC)

    if table.merge == "append" or not table.business_key:
        ket_qua.rows_silver = _them(ctx, table, tam, dich, luc, loc_khong_doi=False)
        return

    if table.merge == "replace_all":
        # QT-10: tệp là bản theo dõi luỹ kế — mọi dòng hiện hành của cùng (loại tệp,
        # năm) hết hiệu lực, thay bằng toàn bộ dòng trong tệp. Năm khác giữ nguyên.
        nam, tham_nam = dieu_kien_nam(table, ctx.nam, "s")
        ket_qua.rows_superseded = q.execute(
            ctx.conn,
            sql.SQL("UPDATE {dich} s SET is_current = false, valid_to = %s, "
                    "superseded_by_batch_id = %s "
                    " WHERE s.domain_id = %s AND s.is_current{nam}").format(
                dich=dich, nam=nam),
            (luc, ctx.batch_id, ctx.domain_id, *tham_nam),
        )
        ket_qua.rows_silver = _them(ctx, table, tam, dich, luc, loc_khong_doi=False)
        ket_qua.rows_unchanged = 0
        return

    thay_the = 0

    # (a) Dòng hiện hành có cùng khoá nhưng nội dung đã đổi → hết hiệu lực.
    thay_the += q.execute(
        ctx.conn,
        sql.SQL(
            "UPDATE {dich} s SET is_current = false, valid_to = %s, "
            "superseded_by_batch_id = %s "
            " WHERE s.domain_id = %s AND s.is_current "
            "   AND EXISTS (SELECT 1 FROM {tam} g "
            "                WHERE {khop} AND g.row_hash <> s.row_hash)"
        ).format(dich=dich, tam=tam, khop=_dieu_kien_khoa(table, "g", "s")),
        (luc, ctx.batch_id, ctx.domain_id),
    )

    # (b) replace_partition: dòng hiện hành thuộc kỳ mà tệp mới chạm tới nhưng
    #     tệp mới không còn ⇒ coi như đã bị xoá ở nguồn.
    cac_ky = ky_da_ep_kieu(ctx, table)
    if table.merge == "replace_partition" and cac_ky and table.partition_by:
        cot_ky = table.partition_column
        nam, tham_nam = dieu_kien_nam(table, ctx.nam, "s")
        thay_the += q.execute(
            ctx.conn,
            sql.SQL(
                "UPDATE {dich} s SET is_current = false, valid_to = %s, "
                "superseded_by_batch_id = %s "
                " WHERE s.domain_id = %s AND s.is_current "
                "   AND s.{cot_ky} = ANY(%s){nam} "
                "   AND NOT EXISTS (SELECT 1 FROM {tam} g WHERE {khop})"
            ).format(dich=dich, tam=tam, cot_ky=sql.Identifier(cot_ky.name), nam=nam,
                     khop=_dieu_kien_khoa(table, "g", "s")),
            (luc, ctx.batch_id, ctx.domain_id, cac_ky, *tham_nam),
        )

    # (c) Thêm dòng mới, bỏ qua dòng y hệt bản hiện hành ("không đổi").
    them = _them(ctx, table, tam, dich, luc, loc_khong_doi=True)

    ket_qua.rows_silver = them
    ket_qua.rows_superseded = thay_the
    ket_qua.rows_unchanged = len(dong) - them


def _them(ctx: LoadContext, table: FormTable, tam, dich, luc, loc_khong_doi: bool) -> int:
    cot = table.column_names
    chon = sql.SQL(", ").join(sql.SQL("g.{}").format(sql.Identifier(c)) for c in cot)
    dieu_kien = sql.SQL("")
    if loc_khong_doi:
        dieu_kien = sql.SQL(
            " WHERE NOT EXISTS (SELECT 1 FROM {dich} c "
            "                    WHERE c.domain_id = %s AND c.is_current "
            "                      AND {khop} AND c.row_hash = g.row_hash)"
        ).format(dich=dich, khop=_dieu_kien_khoa(table, "g", "c"))

    cau = sql.SQL(
        "INSERT INTO {dich} ({cot}, domain_id, load_id, batch_id, bronze_id, "
        "source_sheet, source_row, row_hash, valid_from, is_current) "
        "SELECT {chon}, %s, %s, %s, g.bronze_id, %s, g.source_row, g.row_hash, %s, true "
        "  FROM {tam} g{dieu_kien}"
    ).format(dich=dich, cot=q.column_list(cot), chon=chon, tam=tam, dieu_kien=dieu_kien)

    tham_so = [ctx.domain_id, ctx.load_id, ctx.batch_id, table.sheet, luc]
    if loc_khong_doi:
        tham_so.append(ctx.domain_id)
    return q.execute(ctx.conn, cau, tham_so)


def ghi_phan_vung(ctx: LoadContext, table: FormTable, table_id: int) -> None:
    """Ghi `ctl.batch_partition`: kỳ nào bị chạm, bao nhiêu dòng, tổng kiểm soát.

    Tổng kiểm soát là số mà R4c so lại — bảo chứng toán học rằng tiền không
    biến mất.
    """
    hien_thi = sorted(ctx.ky_cham_toi.get(table.name, set()))
    gia_tri_ky = ky_da_ep_kieu(ctx, table)
    cac_ky = list(zip(hien_thi, gia_tri_ky, strict=True)) or [("—", None)]
    ket_qua = ctx.bang(table)
    cot_do = [c.name for c in table.measures]

    for ky, gia_tri in cac_ky:
        tong = {}
        if cot_do:
            tong = _tong_theo_ky(ctx, table, gia_tri, cot_do)
        q.execute(
            ctx.conn,
            """
            INSERT INTO ctl.batch_partition (batch_id, table_id, partition_key,
                                             rows_written, rows_superseded, sum_control)
                 VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (batch_id, table_id, partition_key) DO UPDATE
                    SET rows_written = EXCLUDED.rows_written,
                        rows_superseded = EXCLUDED.rows_superseded,
                        sum_control = EXCLUDED.sum_control
            """,
            (ctx.batch_id, table_id, ky,
             ket_qua.rows_silver if len(cac_ky) == 1 else 0,
             ket_qua.rows_superseded if len(cac_ky) == 1 else 0,
             _json(tong)),
        )


def _tong_theo_ky(ctx: LoadContext, table: FormTable, ky, cot_do: list[str]) -> dict:
    nam, tham_nam = dieu_kien_nam(table, ctx.nam, "s")
    if not table.partition_by or ky is None:
        dieu_kien = sql.SQL("s.domain_id = %s AND s.is_current{}").format(nam)
        tham_so = [ctx.domain_id, *tham_nam]
    else:
        cot_ky = table.partition_column
        dieu_kien = sql.SQL("s.domain_id = %s AND s.is_current AND s.{} = %s{}").format(
            sql.Identifier(cot_ky.name), nam)
        tham_so = [ctx.domain_id, ky, *tham_nam]
    chon = sql.SQL(", ").join(
        sql.SQL("coalesce(sum(s.{}), 0) AS {}").format(sql.Identifier(c), sql.Identifier(c))
        for c in cot_do
    )
    row = q.query_one(
        ctx.conn,
        sql.SQL("SELECT {chon} FROM {dich} s WHERE {dk}").format(
            chon=chon, dich=sql.Identifier("silver", table.name), dk=dieu_kien),
        tham_so,
    )
    return {k: str(v) for k, v in (row or {}).items()}


def _json(gia_tri: dict) -> str:
    import json

    return json.dumps(gia_tri, ensure_ascii=False, default=str)
