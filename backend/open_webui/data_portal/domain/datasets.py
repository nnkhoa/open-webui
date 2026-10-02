"""Nghiệp vụ bộ dữ liệu — P07 và P08.

Bảng hiển thị **sinh từ khai báo bộ bảng**, không viết cứng cột nào: đổi YAML
thì bảng ở P08, ngăn giải thích cột và hàng tổng đổi theo.
"""

from __future__ import annotations

from decimal import Decimal

from psycopg import sql

from ..db import sql as q
from ..errors import KhongTimThay
from ..registry.loader import FormRegistry
from ..registry.schema import FormColumn, FormTable

NHAN_LOP = {
    "gold": "Dữ liệu phân tích · Gold",
    "silver": "Dữ liệu chuẩn hoá · Silver",
    "bronze": "Dữ liệu gốc · Bronze",
}
LOP_HOP_LE = tuple(NHAN_LOP)


def the_du_lieu(conn, domain_id: int) -> list[dict]:
    """Lưới thẻ "Dữ liệu nghiệp vụ" ở P07, và bảng "Dữ liệu hiện có" ở P02."""
    return q.query(
        conn,
        """
        SELECT ft.name, ft.table_id, ft.kind,
               coalesce(ft.card_label, ft.label)               AS tieu_de,
               coalesce(ft.card_description, ft.description)   AS mo_ta,
               ft.label                                        AS nhan_day_du,
               (SELECT bp.partition_key FROM ctl.batch_partition bp
                  JOIN ctl.batch b ON b.batch_id = bp.batch_id
                 WHERE bp.table_id = ft.table_id AND b.domain_id = %(d)s
                   AND b.state = 'current' AND bp.partition_key <> '—'
                 ORDER BY lpad(bp.partition_key, 12, '0') LIMIT 1)      AS ky_cu_nhat,
               (SELECT bp.partition_key FROM ctl.batch_partition bp
                  JOIN ctl.batch b ON b.batch_id = bp.batch_id
                 WHERE bp.table_id = ft.table_id AND b.domain_id = %(d)s
                   AND b.state = 'current' AND bp.partition_key <> '—'
                 ORDER BY lpad(bp.partition_key, 12, '0') DESC LIMIT 1) AS ky_moi_nhat,
               (SELECT max(l.finished_at) FROM ctl.batch_partition bp
                  JOIN ctl.batch b ON b.batch_id = bp.batch_id
                  JOIN ctl.load l ON l.load_id = b.load_id
                 WHERE bp.table_id = ft.table_id AND b.domain_id = %(d)s
                   AND l.status = 'success')                   AS cap_nhat
          FROM ctl.dataset ds
          JOIN ctl.form_table ft ON ft.table_id = ds.table_id
         WHERE ds.domain_id = %(d)s AND ds.is_visible
         ORDER BY ds.display_order, ft.name
        """,
        {"d": domain_id},
    )


def so_dong(conn, table: FormTable, domain_id: int, lop: str = "gold") -> int:
    """Số dòng của một bộ dữ liệu ở một lớp.

    Lớp phân tích và chuẩn hoá lọc `is_current` để không đếm các phiên bản cũ;
    lớp gốc đếm hết vì nó là bản ghi y nguyên mọi lần nạp.
    """
    if lop not in LOP_HOP_LE:
        raise KhongTimThay(f"Không có lớp dữ liệu {lop!r}.")
    dieu_kien = sql.SQL("domain_id = %s")
    if lop in ("gold", "silver"):
        dieu_kien = sql.SQL("domain_id = %s AND is_current")
    return q.scalar(
        conn,
        sql.SQL("SELECT count(*) FROM {} WHERE {}").format(
            sql.Identifier(lop, table.name), dieu_kien),
        (domain_id,),
    )


def cot_hien_thi(table: FormTable, lop: str) -> list[dict]:
    """Các cột bảng ở P08, theo đúng khai báo bộ bảng — như nhau ở cả ba lớp."""
    cot: list[dict] = []
    for col in table.columns:
        if not col.show_in_table:
            continue
        cot.append({
            "key": col.name, "label": col.label, "align": col.align,
            "width": col.display_width, "is_measure": col.is_measure,
            "type": col.type, "col": col,
        })
    return cot


def dung_de(table: FormTable, col: FormColumn, cac_bang: list[FormTable]) -> str:
    """Cột dùng để làm gì — suy từ khai báo (khoá, kỳ, số đo, tỷ lệ), không viết tay."""
    phan: list[str] = []
    if col.is_business_key:
        khac = [k for k in table.business_key if k != col.name]
        phan.append(f"Khoá: cùng {', '.join(khac)} xác định một dòng." if khac
                    else "Khoá: xác định một dòng.")
    if col.name in table.partition_by:
        phan.append("Kỳ nạp: nạp lại một tháng thì thay toàn bộ dòng của tháng đó.")
    if table.kind == "fact":
        dm = [t for t in cac_bang if t.is_dim and t.business_key == [col.name]]
        if dm:
            phan.append(f"Nối sang {dm[0].name} ({dm[0].label}).")
    if col.type == "ratio":
        phan.append("Tỷ lệ tính sẵn cho từng dòng, lấy nguyên từ tệp NBC. Cách gom theo "
                    "nhóm hay tháng khai ở Lớp ngữ nghĩa.")
    elif col.is_measure:
        phan.append("Số đo: cộng được khi gom theo tháng, nhóm kinh doanh, khách hàng.")
    elif not phan:
        phan.append("Thuộc tính mô tả: dùng để lọc, gom nhóm và hiển thị.")
    return " ".join(phan)


def _cau_chon(table: FormTable, lop: str, cot: list[dict]) -> tuple[sql.Composed, sql.Composed]:
    """Mệnh đề SELECT và FROM cho một lớp."""
    chon = [sql.SQL("t.{}").format(sql.Identifier(c["key"])) for c in cot]
    return sql.SQL(", ").join(chon), sql.SQL("{} t").format(sql.Identifier(lop, table.name))


def _bo_loc(table: FormTable, lop: str, ky: str, tim: str,
            domain_id: int) -> tuple[sql.Composed, list]:
    dieu_kien = [sql.SQL("t.domain_id = %s")]
    tham_so: list = [domain_id]
    if lop in ("gold", "silver"):
        dieu_kien.append(sql.SQL("t.is_current"))

    if ky and table.partition_by:
        cot_ky = table.partition_column
        phan = cot_ky.handler.parse(ky)
        if phan.ok and lop != "bronze":
            dieu_kien.append(sql.SQL("t.{} = %s").format(sql.Identifier(cot_ky.name)))
            tham_so.append(phan.value)
        else:
            dieu_kien.append(sql.SQL("t.{}::text = %s").format(sql.Identifier(cot_ky.name)))
            tham_so.append(ky)
    if tim:
        cot_chu = [c.name for c in table.columns if c.type in ("text", "enum")]
        if cot_chu:
            dieu_kien.append(sql.SQL("({})").format(sql.SQL(" OR ").join(
                sql.SQL("t.{}::text ILIKE %s").format(sql.Identifier(c)) for c in cot_chu)))
            tham_so += [f"%{tim}%"] * len(cot_chu)
    return sql.SQL(" AND ").join(dieu_kien), tham_so


def doc_bang(conn, registry: FormRegistry, table: FormTable, domain_id: int, *,
             lop: str = "gold", ky: str = "", tim: str = "",
             trang: int = 1, moi_trang: int = 50) -> dict:
    """Dữ liệu cho bảng ở P08, kèm hàng tổng khi đang lọc."""
    if lop not in LOP_HOP_LE:
        raise KhongTimThay(f"Không có lớp dữ liệu {lop!r}.")
    cot = cot_hien_thi(table, lop)
    chon, tu = _cau_chon(table, lop, cot)
    where, tham_so = _bo_loc(table, lop, ky, tim, domain_id)

    tong_dong = q.scalar(
        conn, sql.SQL("SELECT count(*) FROM {tu} WHERE {w}").format(tu=tu, w=where), tham_so)

    thu_tu = sql.SQL(", ").join(
        sql.SQL("t.{}").format(sql.Identifier(c)) for c in (table.order or table.business_key)
    ) or sql.SQL("1")
    hang = q.query(
        conn,
        sql.SQL("SELECT {chon} FROM {tu} WHERE {w} ORDER BY {tt} LIMIT %s OFFSET %s").format(
            chon=chon, tu=tu, w=where, tt=thu_tu),
        [*tham_so, moi_trang, (trang - 1) * moi_trang],
    )

    # Hàng tổng **chỉ hiện khi đang lọc**. Cột nào được cộng do
    # `role: measure` quyết định, không viết cứng.
    dang_loc = bool(ky or tim)
    tong: dict[str, Decimal] = {}
    if dang_loc and table.measures and lop != "bronze":
        bieu_thuc = sql.SQL(", ").join(
            sql.SQL("coalesce(sum(t.{c}), 0) AS {c}").format(c=sql.Identifier(c.name))
            for c in table.measures)
        tong = q.query_one(
            conn,
            sql.SQL("SELECT {bt} FROM {tu} WHERE {w}").format(bt=bieu_thuc, tu=tu, w=where),
            tham_so,
        ) or {}

    return {
        "cot": cot,
        "hang": hang,
        "tong_dong": tong_dong,
        "tong": tong,
        "dang_loc": dang_loc,
        "lop": lop,
        "nhan_lop": NHAN_LOP[lop],
    }


def cac_ky(conn, table: FormTable, domain_id: int) -> list[str]:
    if not table.partition_by:
        return []
    rows = q.query(
        conn,
        """
        SELECT DISTINCT bp.partition_key AS ky, lpad(bp.partition_key, 12, '0') AS thu_tu
          FROM ctl.batch_partition bp
          JOIN ctl.batch b ON b.batch_id = bp.batch_id
         WHERE bp.table_id = (SELECT table_id FROM ctl.form_table WHERE name = %s)
           AND b.domain_id = %s AND b.state = 'current' AND bp.partition_key <> '—'
         ORDER BY thu_tu DESC
        """,
        (table.name, domain_id),
    )
    return [r["ky"] for r in rows]

