"""Điều phối một lần nạp.

    chặn tệp trùng → kiểm tra cấu trúc → ghi lớp gốc → ép kiểu → chặn nội dung
    trùng → chuẩn hoá → phân tích → đối chiếu R1–R4 → chốt

Toàn bộ việc ghi nằm trong **một giao dịch duy nhất**, dưới khoá theo cặp
(nhóm thông tin, bộ bảng). Hoặc mọi thứ vào đủ, hoặc không gì vào cả: lỗi ở bất kỳ
bước nào làm cả lần nạp bị huỷ, không có dòng nào bị loại riêng.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

from ..db import sql as q
from ..db.lock import acquire_write_locks
from ..errors import ReconcileError, StructureError
from ..formatting import format_integer
from ..registry.schema import Form
from ..sources import customer_report, header_table  # noqa: F401
from ..sources.base import open_reader
from . import bronze, cac_buoc, doi_chieu_the, gold, kiem_tra_tep, reconcile, silver, validate
from .context import LoadContext
from .structure import kiem_tra as kiem_tra_cau_truc


def _table_id_theo_ten(conn, form_id: int) -> dict[str, int]:
    return {r["name"]: r["table_id"] for r in q.query(
        conn, "SELECT table_id, name FROM ctl.form_table WHERE form_id = %s", (form_id,))}


def chay(conn, form: Form, *, domain_id: int, domain_code: str, form_id: int,
         upload_id: int, upload_path: Path, file_name: str, file_sha256: str,
         actor_user_id: int | None, actor_username: str, request_id: str,
         settings, nam: int | None = None, kiem_tra: dict | None = None,
         a4: str | None = None) -> int:
    """Nạp một tệp đã nằm trên đĩa. Trả `load_id` của lần nạp thành công.

    `nam` là Năm dữ liệu chọn lúc nạp (QT-02). `kiem_tra` là kết quả bước Kiểm tra
    tệp đã chạy trước khi người nạp xác nhận (`kiem_tra_tep.kiem_tra`); không có
    thì chạy lại ở đây. `a4` là câu của bước So với dữ liệu đang có.
    """
    bat_dau = time.monotonic()

    # Tạo lần nạp và lô.
    load_id = q.scalar(
        conn,
        """
        INSERT INTO ctl.load (upload_id, domain_id, form_id, form_version, status,
                              actor_user_id, actor_username, request_id, nam)
             VALUES (%s, %s, %s, %s, 'running', %s, %s, %s, %s)
          RETURNING load_id
        """,
        (upload_id, domain_id, form_id, form.version, actor_user_id,
         actor_username, request_id, nam),
    )
    batch_id = q.scalar(
        conn,
        "INSERT INTO ctl.batch (load_id, domain_id, form_id, state) "
        "VALUES (%s, %s, %s, 'open') RETURNING batch_id",
        (load_id, domain_id, form_id),
    )
    q.execute(conn, "UPDATE ctl.load SET batch_id = %s WHERE load_id = %s",
              (batch_id, load_id))

    ctx = LoadContext(
        conn=conn, form=form, domain_id=domain_id, domain_code=domain_code,
        form_id=form_id, load_id=load_id, batch_id=batch_id, upload_path=upload_path,
        file_name=file_name, actor_user_id=actor_user_id, actor_username=actor_username,
        request_id=request_id, nam=nam,
    )
    table_id = _table_id_theo_ten(conn, form_id)

    # Khoá đúng phạm vi ghi.
    acquire_write_locks(conn, [(domain_id, form_id)])

    ctx.reader = open_reader(form.source_kind, upload_path, form)
    try:
        return _chay_trong_khoa(ctx, table_id, settings, bat_dau, kiem_tra, a4)
    finally:
        ctx.reader.close()


def _chay_trong_khoa(ctx: LoadContext, table_id: dict[str, int], settings,
                     bat_dau: float, kt: dict | None, a4: str | None) -> int:
    conn, form = ctx.conn, ctx.form

    # Kiểm tra cấu trúc. Sai ⇒ từ chối cả tệp, không ghi dòng nào.
    loi = kiem_tra_cau_truc(ctx.reader, form)
    if loi:
        raise StructureError(loi)
    if kt is None:
        kt = kiem_tra_tep.kiem_tra(form, ctx.upload_path, ctx.nam)

    ctx.sheets_count = sum(
        1 for t in form.tables
        if any(s.lower() == t.sheet.lower() for s in ctx.reader.sheets())
    )

    # B9: chụp số dòng, tổng tiền theo tháng của năm đang nạp trước khi ghi.
    truoc = doi_chieu_the.chup_truoc(ctx)

    # Ghi lớp gốc rồi ép kiểu. Danh mục trước, số liệu sau.
    for table in form.tables_by_dependency:
        hang_goc = bronze.ghi(ctx, table)
        ctx.dong_sach[table.name], trung = validate.kiem_tra(table, hang_goc)
        ctx.bang(table).rows_duplicate = len(trung)
        _ghi_nhan_ky(ctx, table)

    # Chuẩn hoá rồi phân tích.
    for table in form.tables_by_dependency:
        silver.hop_nhat(ctx, table, ctx.dong_sach[table.name])
        gold.dung(ctx, table)
        silver.ghi_phan_vung(ctx, table, table_id[table.name])

    # Đối chiếu R1–R4 và các thẻ đối chiếu (B7–B9). Lệch bất kỳ ⇒ huỷ toàn bộ.
    lech = reconcile.chay(ctx, table_id)
    the = doi_chieu_the.tinh(ctx, truoc, kt)
    cac_buoc = _cac_buoc(ctx, kt, a4, the, lech)
    if lech or the["lech"]:
        lech += [{"step": "B4", "table": None, "label": doi_chieu_the.TIEU_DE.get(m, m),
                  "nhan_buoc": "Đối chiếu tệp gốc ↔ database"} for m in the["lech"]]
        raise ReconcileError(lech, steps=cac_buoc, reconciliation=the["the"])

    # Chốt.
    ms = int((time.monotonic() - bat_dau) * 1000)
    q.execute(
        conn,
        """
        UPDATE ctl.load
           SET status = 'success', rows_read = %s,
               rows_written = %s, sheets_count = %s, finished_at = %s,
               duration_ms = %s, report = %s, message = NULL,
               kiem_tra = %s, cac_buoc = %s, doi_chieu = %s
         WHERE load_id = %s
        """,
        (ctx.rows_read, ctx.rows_written, ctx.sheets_count,
         datetime.now(UTC), ms,
         _json(ctx.bao_cao()), _json(kt), _json(cac_buoc), _json(the["the"]),
         ctx.load_id),
    )
    q.execute(conn, "UPDATE ctl.batch SET state = 'current', closed_at = now() "
                    "WHERE batch_id = %s", (ctx.batch_id,))

    return ctx.load_id


def _json(gia_tri) -> str:
    return json.dumps(gia_tri, ensure_ascii=False, default=str)


# Bước đối chiếu R1–R4 nằm ở bước nào của mục 17.
BUOC_CUA = {"R1": "B1", "R2": "B2", "R4a": "B2", "R3": "B3", "R4c": "B4"}


def _cac_buoc(ctx: LoadContext, kt: dict, a4: str | None, the: dict,
              lech: list[dict]) -> list[dict]:
    """A1–A5 từ bước Kiểm tra tệp, B1–B5 từ đối chiếu vừa chạy (mục 17)."""
    lech_theo_buoc: dict[str, list[str]] = {}
    for e in lech:
        lech_theo_buoc.setdefault(BUOC_CUA.get(e["step"], "B4"), []).append(e["label"])
    mot_bang = len(ctx.form.tables) == 1
    ra = cac_buoc.buoc_a(kt, nguoi=ctx.actor_username, a4=a4, mot_bang=mot_bang)

    recon: dict[str, list[dict]] = {}
    for r in reconcile.ket_qua_theo_lan_nap(ctx.conn, ctx.load_id):
        recon.setdefault(r["step"], []).append(r)
    se_ghi = {b["bang"]: b["se_ghi"] for b in kt.get("bang", [])}
    bang = [t for t in ctx.form.tables_by_display_order if ctx.bang(t).rows_bronze]

    # B1 — tệp ↔ lớp gốc, qua đường đọc độc lập.
    r1 = recon.get("R1", [])
    tep = sum(int(r["expected"] or 0) for r in r1)
    goc = sum(int(r["actual"] or 0) for r in r1)
    hong = [r for r in r1 if not r["passed"]]
    b1_lech = "; ".join(
        [f"bảng {r['table_label']} khác tệp ở {format_integer(_so_cho(r))} chỗ" for r in hong]
        + [f"bảng {t} khác tệp" for t in lech_theo_buoc.get("B1", [])
           if t not in {r["table_label"] for r in hong}])
    b1 = ("B1", not hong and "B1" not in lech_theo_buoc,
          f"Đọc lại tệp độc lập rồi so: {format_integer(tep)} dòng trong tệp = "
          f"{format_integer(goc)} dòng đã ghi.",
          f"Đọc lại tệp độc lập rồi so: {b1_lech}.")

    # B2 — số dòng chuẩn hoá so với số dòng sẽ ghi ở A3.
    lech_b2 = []
    for t in bang:
        k = ctx.bang(t)
        thuc = k.rows_silver + k.rows_unchanged
        if thuc != se_ghi.get(t.name, thuc):
            lech_b2.append(f"bảng {t.label} lệch {format_integer(abs(thuc - se_ghi[t.name]))} dòng")
    r2_hong = [r for r in recon.get("R2", []) + recon.get("R4a", []) if not r["passed"]]
    for r in r2_hong:
        cau = f"bảng {r['table_label']} lệch {format_integer(abs(int(r['diff'] or 0)))} dòng"
        if cau not in lech_b2:
            lech_b2.append(cau)
    for ten in lech_theo_buoc.get("B2", []):
        if not any(c.startswith(f"bảng {ten} ") for c in lech_b2):
            lech_b2.append(f"bảng {ten} lệch")
    tong_se_ghi = sum(se_ghi.get(t.name, 0) for t in bang)
    tong_ghi = sum(ctx.bang(t).rows_silver + ctx.bang(t).rows_unchanged for t in bang)
    b2 = ("B2", not lech_b2,
          f"So với số dòng sẽ ghi ở A3: {format_integer(tong_se_ghi)} = {format_integer(tong_ghi)} dòng.",
          f"So với số dòng sẽ ghi ở A3: {', '.join(lech_b2)}.")

    # B3 — chuẩn hoá ↔ phân tích.
    r3 = recon.get("R3", [])
    hong3 = [r for r in r3 if not r["passed"]]
    khong_doi = sum(ctx.bang(t).rows_unchanged for t in bang)
    a = sum(int(r["expected"] or 0) for r in r3) + khong_doi
    b = sum(int(r["actual"] or 0) for r in r3) + khong_doi
    b3_lech = [f"Bảng {r['table_label']}: {format_integer(int(r['expected'] or 0))} ≠ "
               f"{format_integer(int(r['actual'] or 0))} dòng" for r in hong3]
    b3_lech += [f"Bảng {t} lệch" for t in lech_theo_buoc.get("B3", [])
                if t not in {r["table_label"] for r in hong3}]
    b3 = ("B3", not b3_lech, f"{format_integer(a)} = {format_integer(b)} dòng.",
          "; ".join(b3_lech) + ".")

    # B4 — tổng tiền, tháng, các mã; cộng tổng kiểm soát R4c.
    hong4 = [r for r in recon.get("R4c", []) if not r["passed"]]
    cau_b4 = the["b4"]
    if hong4 and not the["lech"]:
        cau_b4 = ("Tổng kiểm soát lệch ở bảng "
                  + ", ".join(r["table_label"] for r in hong4) + ".")
    b4 = ("B4", not hong4 and not the["lech"], the["b4"], cau_b4)

    ra += cac_buoc.buoc_b([b1, b2, b3, b4], chot=_cau_chot(ctx, kt),
                          ten_buoc_b4=cac_buoc.ten_b4(kt))
    return ra


def _so_cho(r: dict) -> int:
    """Số ô và dòng khác nhau giữa tệp và lớp gốc mà R1 ghi lại."""
    chi_tiet = r["detail"] or {}
    return sum(len(chi_tiet.get(k, [])) for k in ("o_lech", "thieu_o_goc", "thua_o_goc"))


def _cau_chot(ctx: LoadContext, kt: dict) -> str:
    """B5: "Dữ liệu tháng 1–7 năm 2026 có hiệu lực từ lúc này."."""
    if kt.get("cau_chot"):
        return kt["cau_chot"]
    thang = sorted({int(k) for b in kt.get("bang", []) for k in (b.get("theo_ky") or {})
                    if str(k).isdigit()})
    nam = f" năm {ctx.nam}" if ctx.nam else ""
    if not thang:
        return f"Dữ liệu{nam} có hiệu lực từ lúc này."
    pham_vi = str(thang[0]) if len(thang) == 1 else f"{thang[0]}–{thang[-1]}"
    return f"Dữ liệu tháng {pham_vi}{nam} có hiệu lực từ lúc này."


def _ghi_nhan_ky(ctx: LoadContext, table) -> None:
    """Kỳ nào bị lô này chạm tới — nguồn của "Kỳ dữ liệu" trên các màn."""
    if not table.partition_by:
        return
    col = table.partition_column
    cac_ky = set()
    for dong in ctx.dong_sach.get(table.name, []):
        gia_tri = dong.values.get(col.name)
        if gia_tri is not None:
            cac_ky.add(col.display(gia_tri) if col.type == "month" else str(gia_tri))
    ctx.ky_cham_toi[table.name] = cac_ky
