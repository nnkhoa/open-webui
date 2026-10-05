"""Màn Dữ liệu (MH-30) và Chi tiết bảng (MH-31) cho API JSON.

Bảng hiển thị sinh từ khai báo bộ bảng như `datasets.py`. Khác ở chỗ bảng số
liệu lọc được theo **năm dữ liệu** (cột `nam`, QT-02) và trả giá trị thô — tầng
giao diện tự định dạng.
"""

from __future__ import annotations

from decimal import Decimal

from psycopg import sql

from ..db import sql as q
from ..errors import NotFound
from ..registry.loader import FormRegistry
from ..registry.schema import FormTable
from . import datasets

TEN_LOP = {"gold": "Dữ liệu phân tích", "silver": "Dữ liệu chuẩn hoá", "bronze": "Dữ liệu gốc"}


def nhom_cua_bang(conn, ten_bang: str) -> dict | None:
    """Nhóm thông tin đang hoạt động có bảng này — chặn đọc bảng ngoài bộ bảng."""
    return q.query_one(
        conn,
        "SELECT d.domain_id, d.code, d.name, ft.form_id FROM ctl.dataset ds "
        "  JOIN ctl.form_table ft ON ft.table_id = ds.table_id "
        "  JOIN ctl.domain d ON d.domain_id = ds.domain_id "
        " WHERE ft.name = %s AND ds.is_visible AND d.status = 'active' LIMIT 1",
        (ten_bang,))


def _nam_dk(table: FormTable, nam: int | None, lop: str) -> tuple[sql.Composable, list]:
    cot = table.year_column
    if cot is None or nam is None:
        return sql.SQL(""), []
    if lop == "bronze":
        return sql.SQL(" AND t.{}::text = %s").format(sql.Identifier(cot.name)), [str(nam)]
    return sql.SQL(" AND t.{} = %s").format(sql.Identifier(cot.name)), [nam]


def thong_ke(conn, table: FormTable, domain_id: int, nam: int | None) -> dict:
    """Số dòng, các tháng, cập nhật lúc, lần nạp mới nhất của một bảng ở lớp phân tích."""
    nam_dk, tham_nam = _nam_dk(table, nam, "gold")
    ky = table.partition_column
    chon_ky = (sql.SQL(", array_agg(DISTINCT t.{}) AS cac_ky").format(sql.Identifier(ky.name))
               if ky is not None else sql.SQL(""))
    hang = q.query_one(conn, sql.SQL(
        "SELECT count(*) AS so_dong, max(t.load_id) AS load_id{ky} FROM {bang} t "
        " WHERE t.domain_id = %s AND t.is_current{nam}").format(
        ky=chon_ky, bang=sql.Identifier("gold", table.name), nam=nam_dk),
        [domain_id, *tham_nam])
    cac_ky = sorted(k for k in (hang.get("cac_ky") or []) if k is not None) if ky else []
    cap_nhat = None
    if hang["so_dong"]:
        cap_nhat = q.scalar(conn, sql.SQL(
            "SELECT max(l.finished_at) FROM ctl.load l WHERE l.load_id IN "
            "(SELECT DISTINCT t.load_id FROM {bang} t "
            "  WHERE t.domain_id = %s AND t.is_current{nam})").format(
            bang=sql.Identifier("gold", table.name), nam=nam_dk), [domain_id, *tham_nam])
    return {"so_dong": hang["so_dong"], "cac_ky": cac_ky, "cap_nhat": cap_nhat}


def lan_nap_moi_nhat(conn, domain_id: int, form_id: int, nam: int | None) -> int | None:
    """Lần nạp thành công mới nhất của loại tệp trong năm đang lọc."""
    dk, tham = "", [domain_id, form_id]
    if nam is not None:
        dk, tham = " AND nam = %s", [*tham, nam]
    return q.scalar(conn, f"SELECT max(load_id) FROM ctl.load WHERE domain_id = %s "
                          f"AND form_id = %s AND status = 'success'{dk}", tham)


def danh_sach(conn, registry: FormRegistry, domain_id: int, nam: int | None) -> list[dict]:
    """Các bảng của nhóm theo thứ tự hiển thị, kể cả bảng chưa nạp."""
    hang = q.query(
        conn,
        "SELECT ft.name, ft.form_id, f.code AS form_code FROM ctl.dataset ds "
        "  JOIN ctl.form_table ft ON ft.table_id = ds.table_id "
        "  JOIN ctl.form f ON f.form_id = ft.form_id "
        "  LEFT JOIN ctl.domain_form df ON df.domain_id = ds.domain_id "
        "                              AND df.form_id = ft.form_id "
        " WHERE ds.domain_id = %s AND ds.is_visible "
        " ORDER BY df.thu_tu, ds.display_order, ft.name", (domain_id,))
    ra = []
    for r in hang:
        table = registry.table(r["name"])
        form = registry.form(r["form_code"])
        tk = thong_ke(conn, table, domain_id, nam)
        ra.append({
            "table": table, "form": form, **tk,
            "load_id": lan_nap_moi_nhat(conn, domain_id, r["form_id"],
                                        nam if table.year_column is not None else None),
        })
    return ra


def _ep_so(gia_tri):
    if isinstance(gia_tri, Decimal):
        return int(gia_tri) if gia_tri == gia_tri.to_integral_value() else float(gia_tri)
    return gia_tri


def doc(conn, table: FormTable, domain_id: int, *, lop: str, nam: int | None, ky: str,
        tim: str, trang: int, moi: int | None) -> dict:
    """Các dòng của bảng theo bộ lọc. `moi=None` ⇒ lấy hết (tải Excel)."""
    if lop not in TEN_LOP:
        raise NotFound(f"Không có lớp dữ liệu {lop!r}.")
    cot = [c for c in table.columns if c.show_in_table]
    where, tham = _bo_loc(table, lop, nam, ky, tim, domain_id)
    tu = sql.SQL("{} t").format(sql.Identifier(lop, table.name))
    tong = q.scalar(conn, sql.SQL("SELECT count(*) FROM {} WHERE {}").format(tu, where), tham)

    thu_tu = sql.SQL(", ").join(
        sql.SQL("t.{}").format(sql.Identifier(c)) for c in (table.order or table.business_key)
    ) or sql.SQL("1")
    gioi_han = sql.SQL("")
    tham_trang: list = []
    if moi is not None:
        gioi_han = sql.SQL(" LIMIT %s OFFSET %s")
        tham_trang = [moi, (trang - 1) * moi]
    hang = q.query(conn, sql.SQL("SELECT {chon} FROM {tu} WHERE {w} ORDER BY {tt}{gh}").format(
        chon=sql.SQL(", ").join(sql.SQL("t.{}").format(sql.Identifier(c.name)) for c in cot),
        tu=tu, w=where, tt=thu_tu, gh=gioi_han), [*tham, *tham_trang])

    dong_tong = None
    so_do = [c for c in cot if c.is_measure]
    if (ky or tim) and so_do and lop != "bronze":
        tong_cot = q.query_one(conn, sql.SQL("SELECT {} FROM {} WHERE {}").format(
            sql.SQL(", ").join(sql.SQL("coalesce(sum(t.{c}), 0) AS {c}").format(
                c=sql.Identifier(c.name)) for c in so_do), tu, where), tham) or {}
        dong_tong = [_ep_so(tong_cot.get(c.name)) if c.is_measure else None for c in cot]

    return {"cot": cot, "dong": [[_ep_so(r[c.name]) for c in cot] for r in hang],
            "tong": tong, "dong_tong": dong_tong}


def _bo_loc(table: FormTable, lop: str, nam: int | None, ky: str, tim: str,
            domain_id: int) -> tuple[sql.Composed, list]:
    dk = [sql.SQL("t.domain_id = %s")]
    tham: list = [domain_id]
    if lop in ("gold", "silver"):
        dk.append(sql.SQL("t.is_current"))
    nam_dk, tham_nam = _nam_dk(table, nam, lop)
    if tham_nam:
        dk.append(sql.SQL("TRUE{}").format(nam_dk))
        tham += tham_nam
    if ky and table.partition_by:
        cot_ky = table.partition_column
        phan = cot_ky.handler.parse(ky)
        if phan.ok and phan.value is not None and lop != "bronze":
            dk.append(sql.SQL("t.{} = %s").format(sql.Identifier(cot_ky.name)))
            tham.append(phan.value)
        else:
            dk.append(sql.SQL("t.{}::text = %s").format(sql.Identifier(cot_ky.name)))
            tham.append(ky)
    if tim:
        # Tìm trong cột chữ và cột ngày (ngày so theo dạng DD/MM/YYYY trên màn).
        phan_tim = []
        for c in table.columns:
            if c.type in ("text", "enum") or (lop == "bronze" and c.type == "date"):
                phan_tim.append(sql.SQL("t.{}::text ILIKE %s").format(sql.Identifier(c.name)))
                tham.append(f"%{tim}%")
            elif c.type == "date":
                phan_tim.append(sql.SQL("to_char(t.{}, 'DD/MM/YYYY') ILIKE %s").format(
                    sql.Identifier(c.name)))
                tham.append(f"%{tim}%")
        if phan_tim:
            dk.append(sql.SQL("({})").format(sql.SQL(" OR ").join(phan_tim)))
    return sql.SQL(" AND ").join(dk), tham


def thong_tin_cot(table: FormTable, cac_bang: list[FormTable]) -> list[dict]:
    """Ngăn "Giải thích các cột" (MH-32) và sheet THONG_TIN của tệp tải về."""
    return [{
        "ten": c.name,
        "ten_nbc": c.label,
        "kieu": c.type,
        "kieu_hien": c.type_label,
        "bat_buoc": c.is_business_key or c.required,
        "y_nghia": c.meaning,
        "dung_de": datasets.dung_de(table, c, cac_bang),
        "vi_du": c.example,
        "so_do": c.is_measure,
    } for c in table.columns if c.show_in_table]
