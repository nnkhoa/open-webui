"""Đối chiếu R1–R4, chạy trong giao dịch ghi của lần nạp.

    R1   Tệp ↔ Dữ liệu gốc        đọc lại tệp bằng **đường mã nguồn độc lập**
    R2   Gốc ↔ Chuẩn hoá          mỗi dòng gốc vào chuẩn hoá, hoặc y hệt bản hiện
                                  hành, hoặc là dòng trùng y hệt trong tệp
    R3   Chuẩn hoá ↔ Phân tích    so hai chiều trên các cột được chép
    R4a  không mất dòng           mọi dòng gốc của lô có mặt ở chuẩn hoá
    R4c  **tổng kiểm soát**       Σ tiền(tệp) = Σ tiền(chuẩn hoá) + Σ tiền(không đổi)

Mọi phép đối chiếu giới hạn trong lô vừa nạp, nên chi phí tỉ lệ với kích thước
tệp chứ không tỉ lệ với kích thước kho.

**R4c là bảo chứng không mất tiền.** Sai số phải bằng 0 tuyệt đối, tính trên
kiểu `numeric` chứ không phải số thực dấu phẩy động. Lệch ở bất kỳ bước nào ⇒
huỷ toàn bộ giao dịch.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from psycopg import sql

from ..db import sql as q
from ..registry.schema import FormTable
from ..sources.bang_theo_tieu_de_verify import BangTheoTieuDeDocLai
from ..sources.bao_cao_kh_verify import BaoCaoKhDocLai
from ..sources.base import chuan_ten
from .context import LoadContext

# Mốc ngày của Excel trên Windows (1900), đã tính cả lỗi năm nhuận 1900.
MOC_EXCEL = date(1899, 12, 30)

NHAN_BUOC = {
    "R1": "Tệp → Dữ liệu gốc",
    "R2": "Dữ liệu gốc → Chuẩn hoá",
    "R3": "Chuẩn hoá → Phân tích",
    "R4a": "Không mất dòng",
    "R4c": "Tổng kiểm soát",
}


def _ghi(ctx: LoadContext, step: str, table_id: int, metric: str,
         expected, actual, passed: bool, detail: dict | None = None) -> None:
    ky_vong = None if expected is None else Decimal(str(expected))
    thuc_te = None if actual is None else Decimal(str(actual))
    lech = None if (ky_vong is None or thuc_te is None) else thuc_te - ky_vong
    q.execute(
        ctx.conn,
        """
        INSERT INTO ctl.recon_result (load_id, step, table_id, metric, expected, actual,
                                      diff, passed, detail)
             VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (load_id, step, table_id, metric) DO UPDATE
                SET expected = EXCLUDED.expected, actual = EXCLUDED.actual,
                    diff = EXCLUDED.diff, passed = EXCLUDED.passed,
                    detail = EXCLUDED.detail
        """,
        (ctx.load_id, step, table_id, metric, ky_vong, thuc_te, lech, passed,
         json.dumps(detail or {}, ensure_ascii=False, default=str)),
    )


# --------------------------------------------------------------------------- #
#  So giá trị giữa hai đường đọc
# --------------------------------------------------------------------------- #


def _so(gia_tri: str | None) -> Decimal | None:
    if gia_tri is None:
        return None
    try:
        return Decimal(str(gia_tri).strip())
    except (InvalidOperation, ValueError):
        return None


def bang_nhau(a: str | None, b: str | None) -> bool:
    """So một ô đọc bằng hai đường khác nhau.

    Hai đường đọc cùng một tệp có thể trình bày khác nhau mà nội dung vẫn là
    một: `1031204925` với `1031204925.0`, hay ngày lưu dạng số thứ tự của Excel
    với ngày đã dựng thành ISO. Chỗ này nhận biết các cách trình bày đó; ngoài
    ra thì so đúng từng ký tự.
    """
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if str(a).strip() == str(b).strip():
        return True
    sa, sb = _so(a), _so(b)
    if sa is not None and sb is not None:
        if sa == sb:
            return True
        # Excel lưu số dưới dạng số thực dấu phẩy động 64 bit. Hai đường đọc in
        # ra cùng một số đó theo hai cách khác nhau — đường đọc thẳng XML giữ
        # đủ chữ số (`0.009561952091034449`), openpyxl rút về dạng ngắn nhất
        # vẫn quay về đúng số đó (`0.00956195209103445`). Cùng giá trị, khác
        # cách viết, nên so tiếp ở mức số thực.
        try:
            return float(sa) == float(sb)
        except (OverflowError, ValueError):
            return False
    # Một bên là số thứ tự ngày của Excel, bên kia là ngày ISO.
    for so, van_ban in ((sa, b), (sb, a)):
        if so is None or so <= 0 or so > 2_958_465:
            continue
        try:
            ngay = MOC_EXCEL + timedelta(days=int(so))
        except (OverflowError, ValueError):
            continue
        if str(van_ban).strip().startswith(ngay.isoformat()):
            return True
    return False


# --------------------------------------------------------------------------- #
#  R1 — Tệp ↔ Dữ liệu gốc, qua đường đọc độc lập
# --------------------------------------------------------------------------- #


def r1(ctx: LoadContext, table: FormTable, table_id: int) -> bool:
    doc_lai = (BangTheoTieuDeDocLai(ctx.upload_path, ctx.form)
               if ctx.form.source_kind == "bang_theo_tieu_de"
               else BaoCaoKhDocLai(ctx.upload_path))
    try:
        tieu_de, hang_tep = doc_lai.doc_sheet(table.sheet)
    finally:
        doc_lai.close()

    theo_cot = {chuan_ten(ten): chi_so for chi_so, ten in tieu_de.items()}
    # Cột `nam` và cột để trống không có trong tệp — không có gì để đọc lại.
    can = {c.name: theo_cot.get(chuan_ten(c.tieu_de)) for c in table.cot_tu_tep}

    goc = q.query(
        ctx.conn,
        sql.SQL("SELECT source_row, {cot} FROM {bang} WHERE load_id = %s").format(
            cot=q.column_list(table.column_names),
            bang=sql.Identifier("bronze", table.name)),
        (ctx.load_id,),
    )
    theo_dong = {r["source_row"]: r for r in goc}

    # Dòng trong tệp có dữ liệu ở cột đã khai nhưng không có ở lớp gốc, và
    # ngược lại — so hai chiều.
    dong_tep = {
        so for so, o in hang_tep.items()
        if any(o.get(chi_so) is not None for chi_so in can.values() if chi_so)
    }
    thieu_o_goc = sorted(dong_tep - set(theo_dong))
    thua_o_goc = sorted(set(theo_dong) - dong_tep)

    lech: list[dict] = []
    for so_dong, ban_ghi in theo_dong.items():
        o_tep = hang_tep.get(so_dong, {})
        for ten, chi_so in can.items():
            trong_tep = o_tep.get(chi_so) if chi_so else None
            if not bang_nhau(trong_tep, ban_ghi[ten]):
                lech.append({"source_row": so_dong, "column": ten,
                             "tep": trong_tep, "goc": ban_ghi[ten]})
                if len(lech) >= 20:
                    break
        if len(lech) >= 20:
            break

    tong_lech = len(lech) + len(thieu_o_goc) + len(thua_o_goc)
    dat = tong_lech == 0
    _ghi(ctx, "R1", table_id, "so_dong", len(dong_tep), len(theo_dong), dat,
         {"o_lech": lech, "thieu_o_goc": thieu_o_goc[:20], "thua_o_goc": thua_o_goc[:20]})
    return dat


# --------------------------------------------------------------------------- #
#  R2 — Gốc ↔ Chuẩn hoá
# --------------------------------------------------------------------------- #


def r2(ctx: LoadContext, table: FormTable, table_id: int) -> bool:
    """Mỗi dòng gốc của lô có **đúng một** kết cục: vào chuẩn hoá, y hệt bản
    hiện hành nên không ghi lại, hoặc trùng y hệt một dòng trước nó trong tệp.
    Không dòng nào biến mất."""
    ket_qua = ctx.bang(table)
    vao = q.scalar(
        ctx.conn,
        sql.SQL("SELECT count(*) FROM {} WHERE batch_id = %s").format(
            sql.Identifier("silver", table.name)),
        (ctx.batch_id,),
    )
    khong_doi, trung = ket_qua.rows_unchanged, ket_qua.rows_duplicate
    ky_vong = ket_qua.rows_bronze
    thuc_te = vao + khong_doi + trung
    dat = ky_vong == thuc_te
    _ghi(ctx, "R2", table_id, "ket_cuc_tung_dong", ky_vong, thuc_te, dat,
         {"vao_chuan_hoa": vao, "khong_doi": khong_doi, "trung_trong_tep": trung})
    return dat


# --------------------------------------------------------------------------- #
#  R3 — Chuẩn hoá ↔ Phân tích
# --------------------------------------------------------------------------- #


def r3(ctx: LoadContext, table: FormTable, table_id: int) -> bool:
    """So hai chiều bằng `EXCEPT ALL` trên các cột được chép nguyên."""
    cot = q.column_list(table.column_names)
    silver = sql.Identifier("silver", table.name)
    gold = sql.Identifier("gold", table.name)

    cau = sql.SQL(
        "WITH s AS (SELECT {cot} FROM {silver} WHERE batch_id = %s AND is_current), "
        "     g AS (SELECT {cot} FROM {gold} WHERE batch_id = %s AND is_current) "
        "SELECT (SELECT count(*) FROM (SELECT * FROM s EXCEPT ALL SELECT * FROM g) x) "
        "       AS thieu_o_gold, "
        "       (SELECT count(*) FROM (SELECT * FROM g EXCEPT ALL SELECT * FROM s) y) "
        "       AS thua_o_gold, "
        "       (SELECT count(*) FROM s) AS so_silver, "
        "       (SELECT count(*) FROM g) AS so_gold"
    ).format(cot=cot, silver=silver, gold=gold)
    row = q.query_one(ctx.conn, cau, (ctx.batch_id, ctx.batch_id))

    dat = row["thieu_o_gold"] == 0 and row["thua_o_gold"] == 0
    _ghi(ctx, "R3", table_id, "so_dong", row["so_silver"], row["so_gold"], dat,
         {"thieu_o_gold": row["thieu_o_gold"], "thua_o_gold": row["thua_o_gold"]})
    return dat


# --------------------------------------------------------------------------- #
#  R4 — bất biến toàn cục
# --------------------------------------------------------------------------- #


def r4a(ctx: LoadContext, table: FormTable, table_id: int) -> bool:
    """Mọi dòng của lô có mặt ở lớp chuẩn hoá, trừ dòng y hệt bản hiện hành và
    dòng trùng y hệt trong tệp — không dòng nào bị bỏ vì lý do khác."""
    ket_qua = ctx.bang(table)
    so = q.scalar(
        ctx.conn,
        sql.SQL("SELECT count(*) FROM {} WHERE batch_id = %s").format(
            sql.Identifier("silver", table.name)),
        (ctx.batch_id,),
    )
    ky_vong = ket_qua.rows_bronze - ket_qua.rows_unchanged - ket_qua.rows_duplicate
    dat = so == ky_vong
    _ghi(ctx, "R4a", table_id, "dong_giu_lai", ky_vong, so, dat,
         {"business_key": table.business_key})
    return dat


def _tong_do(table: FormTable) -> list[str]:
    """Các cột tiền được cộng vào tổng kiểm soát."""
    return [c.name for c in table.measures if c.type in ("money", "currency")]


def r4c(ctx: LoadContext, table: FormTable, table_id: int) -> bool:
    """Tổng kiểm soát — bảo chứng không mất tiền.

        Σ(tệp, các ô đọc được thành số)
            = Σ(dòng lô này ghi vào chuẩn hoá)
            + Σ(dòng có trong tệp nhưng y hệt bản hiện hành, không ghi lại)

    Vế trái đọc thẳng từ lớp gốc — tức là từ tệp, chưa qua bất kỳ phép biến đổi
    nào. Vế phải là mọi chỗ mà một con số có thể đi tới. Lệch dù chỉ một đồng ⇒
    huỷ cả lần nạp.
    """
    cot_tien = _tong_do(table)
    if not cot_tien:
        return True

    # Vế trái: đọc lớp gốc, ép văn bản sang numeric, bỏ qua ô không phải số
    # (những ô đó để trống ở chuẩn hoá, không mang tiền).
    bieu_thuc = sql.SQL(" + ").join(
        sql.SQL("coalesce(sum(CASE WHEN {c} ~ '^[+-]?([0-9]+(\\.[0-9]*)?|\\.[0-9]+)"
                "([eE][+-]?[0-9]+)?$' THEN {c}::numeric ELSE 0 END), 0)").format(
            c=sql.Identifier(col))
        for col in cot_tien
    )
    tong_tep = q.scalar(
        ctx.conn,
        sql.SQL("SELECT {bt} FROM {bang} WHERE load_id = %s").format(
            bt=bieu_thuc, bang=sql.Identifier("bronze", table.name)),
        (ctx.load_id,),
    ) or Decimal(0)

    tong_silver = q.scalar(
        ctx.conn,
        sql.SQL("SELECT {bt} FROM {bang} WHERE batch_id = %s").format(
            bt=sql.SQL(" + ").join(
                sql.SQL("coalesce(sum({}), 0)").format(sql.Identifier(c)) for c in cot_tien),
            bang=sql.Identifier("silver", table.name)),
        (ctx.batch_id,),
    ) or Decimal(0)

    tong_khong_doi = _tong_dong_khong_doi(ctx, table, cot_tien)

    ve_phai = Decimal(tong_silver) + Decimal(tong_khong_doi)
    lech = Decimal(tong_tep) - ve_phai
    dat = lech == 0
    _ghi(ctx, "R4c", table_id, "tong_kiem_soat", tong_tep, ve_phai, dat, {
        "cot": cot_tien,
        "tong_tep": str(tong_tep),
        "tong_chuan_hoa": str(tong_silver),
        "tong_khong_doi": str(tong_khong_doi),
        "lech": str(lech),
    })
    return dat


def _tong_dong_khong_doi(ctx: LoadContext, table: FormTable, cot_tien: list[str]) -> Decimal:
    """Tiền của các dòng có trong tệp nhưng y hệt bản hiện hành nên không ghi lại.

    Đọc từ bảng tạm mà `silver.hop_nhat` đã dựng trong cùng giao dịch — cố ý,
    vì đây là cách duy nhất biết chính xác dòng nào đã bị bỏ qua vì "không đổi".
    """
    if table.merge in ("append", "replace_all") or not table.business_key:
        return Decimal(0)
    tam = sql.Identifier(f"stg_{table.name}")
    co = q.scalar(ctx.conn, "SELECT to_regclass(%s)", (f"pg_temp.stg_{table.name}",))
    if co is None:
        return Decimal(0)
    khop = sql.SQL(" AND ").join(
        sql.SQL("c.{c} IS NOT DISTINCT FROM g.{c}").format(c=sql.Identifier(c))
        for c in table.business_key
    )
    tong = q.scalar(
        ctx.conn,
        sql.SQL(
            "SELECT {bt} FROM {tam} g "
            " WHERE EXISTS (SELECT 1 FROM {silver} c "
            "                WHERE c.domain_id = %s AND c.is_current AND {khop} "
            "                  AND c.row_hash = g.row_hash AND c.batch_id <> %s)"
        ).format(
            bt=sql.SQL(" + ").join(
                sql.SQL("coalesce(sum(g.{}), 0)").format(sql.Identifier(c)) for c in cot_tien),
            tam=tam, silver=sql.Identifier("silver", table.name), khop=khop),
        (ctx.domain_id, ctx.batch_id),
    )
    return Decimal(tong or 0)


# --------------------------------------------------------------------------- #
#  Chạy cả bộ
# --------------------------------------------------------------------------- #


def chay(ctx: LoadContext, table_id_theo_ten: dict[str, int]) -> list[dict]:
    """Chạy R1–R4 cho mọi bảng. Trả danh sách bước lệch — rỗng nghĩa là khớp hết."""
    lech: list[dict] = []
    for table in ctx.form.tables_theo_thu_tu:
        table_id = table_id_theo_ten[table.name]
        if ctx.bang(table).rows_bronze == 0:
            continue
        for buoc, ham in (("R1", r1), ("R2", r2), ("R3", r3),
                          ("R4a", r4a), ("R4c", r4c)):
            if not ham(ctx, table, table_id):
                lech.append({"step": buoc, "table": table.name, "label": table.label,
                             "nhan_buoc": NHAN_BUOC[buoc]})
    return lech


def ket_qua_theo_lan_nap(conn, load_id: int) -> list[dict]:
    """Bảng ở tab Đối chiếu kỹ thuật của màn Chi tiết lần nạp."""
    return q.query(
        conn,
        """
        SELECT r.step, r.metric, r.expected, r.actual, r.diff, r.passed, r.detail,
               ft.label AS table_label, ft.name AS table_name
          FROM ctl.recon_result r
          LEFT JOIN ctl.form_table ft ON ft.table_id = r.table_id
         WHERE r.load_id = %s
         ORDER BY ft.display_order, r.step
        """,
        (load_id,),
    )
