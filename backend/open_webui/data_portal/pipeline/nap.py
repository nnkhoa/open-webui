"""Luồng nạp hai bước của Data Portal (mục 6.1): Kiểm tra tệp → Xác nhận → Ghi.

    kiem_tra   chỉ đọc tệp (QT-07). Sai ⇒ tạo lần nạp "Bị từ chối", lưu tệp và
               danh sách lỗi. Đúng ⇒ cất tệp chờ, trả `ma_tep_cho`.
    xac_nhan   ghi trong **một giao dịch** dưới khoá (nhóm, loại tệp) như đường
               nạp sẵn có (`orchestrator.chay`); lệch ⇒ huỷ cả lần (QT-12, QT-13).
    huy        xoá tệp chờ, database không đổi (CN-13).

Mô-đun này điều phối, không tự kiểm tra hay ghi dữ liệu: việc đó là của
`kiem_tra_tep` và `orchestrator`. Bản ghi lần nạp thất bại ghi ở giao dịch riêng
vì giao dịch nạp đã bị huỷ.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from psycopg import sql

from ..db import sql as q
from ..errors import NotFound, ReconcileError, SourceFileError, StructureError
from ..registry.schema import Form, FormTable
from ..security.audit import record_event
from . import cac_buoc, dedup, kiem_tra_tep, orchestrator, tep_cho
from .reconcile import NHAN_BUOC

# Năm dữ liệu chọn được (QT-02).
CAC_NAM = tuple(range(2025, 2032))

TEP_CHO_HET = ("Tệp này đã được nạp hoặc đã quá hạn chờ xác nhận. Hãy xem Lịch sử nạp, "
               "hoặc chọn lại tệp.")
A4_HQKD = "Đã hiện cho người nạp ở màn Xác nhận."


def _luc() -> str:
    return datetime.now(UTC).isoformat()


# --------------------------------------------------------------------------- #
#  Bước 2 — Kiểm tra tệp
# --------------------------------------------------------------------------- #


def kiem_tra(kho, so_tay, settings, *, domain_id: int, domain_code: str, form_id: int,
             form: Form, nam: int, ten_tep: str, nguon: BinaryIO, nguoi_id: str,
             nguoi_ten: str, request_id: str) -> dict:
    """Đọc và kiểm tra tệp, không ghi dữ liệu. Trả `{"ma_tep_cho"}` hoặc
    `{"load_id", "status": "rejected"}`. Tệp không mở được ⇒ `SourceFileError`."""
    tep_cho.don_tep_bo_do(settings.upload_dir)
    tep = tep_cho.luu(settings.upload_dir, nguon, {
        "domain_id": domain_id, "nhom": domain_code, "form_id": form_id,
        "loai": form.code, "nam": nam, "ten_tep": ten_tep,
        "nguoi_id": nguoi_id, "nguoi": nguoi_ten, "luc": _luc(),
    })
    file_sha256, so_byte = dedup.bam_tep(tep.duong_dan)
    try:
        kt = kiem_tra_tep.kiem_tra(form, tep.duong_dan, nam)
    except SourceFileError:
        tep_cho.xoa(tep)
        raise
    tep.thong_tin.update({"sha256": file_sha256, "size_bytes": so_byte, "kiem_tra": kt})

    if kt["loi"]:
        dich = _cat_tep(settings.upload_dir, tep)
        cac = (cac_buoc.buoc_a(kt, nguoi=nguoi_ten, a4=None, mot_bang=len(form.tables) == 1)
               + cac_buoc.buoc_b_tu_choi(kt["buoc_loi"], cac_buoc.ten_b4(kt)))
        load_id = ghi_that_bai(
            kho, so_tay, "rejected", kt["loi"], domain_id=domain_id, form_id=form_id,
            file_name=ten_tep, file_sha256=file_sha256, so_byte=so_byte,
            storage_uri=str(dich), nguoi_id=nguoi_id, nguoi_ten=nguoi_ten,
            request_id=request_id, nam=nam, kiem_tra=kt, cac=cac, doi_chieu=None)
        tep_cho.xoa(tep)
        return {"load_id": load_id, "status": "rejected"}

    tep_cho.ghi_thong_tin(tep)
    return {"ma_tep_cho": tep.ma}


def _cat_tep(upload_dir: Path, tep: tep_cho.TepCho) -> Path:
    """Chép tệp chờ sang chỗ cất lâu dài của tệp đã tải lên (PCN-06)."""
    ten = Path(tep.thong_tin["ten_tep"]).name
    dich = upload_dir / f"{datetime.now(UTC):%Y%m%d%H%M%S}_{tep.ma[:8]}_{ten}"
    dich.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(tep.duong_dan, dich)
    return dich


def ghi_that_bai(kho, so_tay, trang_thai: str, loi: list[dict], *, domain_id: int,
                 form_id: int, file_name: str, file_sha256: str, so_byte: int,
                 storage_uri: str, nguoi_id: str, nguoi_ten: str, request_id: str,
                 nam: int | None, kiem_tra: dict | None, cac: list[dict] | None,
                 doi_chieu: dict | None) -> int:
    """Ghi bản ghi lần nạp thất bại (Bị từ chối / Lỗi đối chiếu) ở giao dịch mới."""
    with kho.transaction() as conn:
        upload_id = q.scalar(
            conn,
            "INSERT INTO ctl.upload (domain_id, form_id, file_name, file_sha256, "
            "size_bytes, storage_uri, uploaded_by, uploaded_by_username) "
            "VALUES (%s, %s, %s, %s, %s, %s, NULL, %s) RETURNING upload_id",
            (domain_id, form_id, file_name, file_sha256, so_byte, storage_uri, nguoi_ten),
        )
        form_version = q.scalar(conn, "SELECT current_version FROM ctl.form WHERE form_id = %s",
                                (form_id,))
        load_id = q.scalar(
            conn,
            "INSERT INTO ctl.load (upload_id, domain_id, form_id, form_version, status, "
            "actor_user_id, actor_username, request_id, errors, finished_at, message, "
            "nam, kiem_tra, cac_buoc, doi_chieu, sheets_count) "
            "VALUES (%s, %s, %s, %s, %s, NULL, %s, %s, %s, now(), %s, %s, %s, %s, %s, %s) "
            "RETURNING load_id",
            (upload_id, domain_id, form_id, form_version, trang_thai, nguoi_ten, request_id,
             _json(loi),
             "Không có dữ liệu nào được cập nhật." if trang_thai == "rejected"
             else "Toàn bộ thay đổi đã được huỷ.",
             nam, _json(kiem_tra), _json(cac), _json(doi_chieu),
             (kiem_tra or {}).get("so_sheet", 0)),
        )
    with so_tay.transaction() as so:
        record_event(so, action=f"load.{trang_thai}", actor_user_id=None,
                    actor_username=nguoi_ten, domain_id=domain_id, object_type="load",
                    object_id=str(load_id), request_id=request_id,
                    detail={"nguoi_id": nguoi_id, "nam": nam})
    return load_id


def _json(gia_tri) -> str | None:
    return None if gia_tri is None else json.dumps(gia_tri, ensure_ascii=False, default=str)


# --------------------------------------------------------------------------- #
#  Bước 3 — Xác nhận: hiện kết quả kiểm tra, so với dữ liệu đang có
# --------------------------------------------------------------------------- #


def _so(gia_tri) -> int | float | None:
    """Số trả về dạng số (mục 9.1): nguyên thì `int`, có phần lẻ thì `float`."""
    if gia_tri is None:
        return None
    from decimal import Decimal

    d = Decimal(str(gia_tri))
    return int(d) if d == d.to_integral_value() else float(d)


def _lan_nap(hang: dict | None) -> dict | None:
    if not hang:
        return None
    return {"load_id": hang["load_id"], "luc": hang["started_at"],
            "nguoi": hang["actor_username"]}


def ky_dang_co(conn, table: FormTable, domain_id: int, nam: int | None) -> dict[str, dict]:
    """Kỳ đang có dữ liệu hiện hành trong năm đã chọn, kèm lần nạp giữ dữ liệu đó."""
    nam_dk = sql.SQL("")
    tham: list = [domain_id]
    if table.year_column is not None:
        nam_dk = sql.SQL(" AND s.{} IS NOT DISTINCT FROM %s").format(
            sql.Identifier(table.year_column.name))
        tham.append(nam)
    hang = q.query(conn, sql.SQL(
        "SELECT s.{cot}::text AS ky, count(*) AS so_dong, max(s.load_id) AS load_id "
        "  FROM {bang} s WHERE s.domain_id = %s AND s.is_current{nam} GROUP BY 1"
    ).format(cot=sql.Identifier(table.partition_column.name),
             bang=sql.Identifier("silver", table.name), nam=nam_dk), tham)
    lan = _cac_lan_nap(conn, [r["load_id"] for r in hang])
    return {r["ky"]: {"so_dong": r["so_dong"], **(lan.get(r["load_id"]) or {})}
            for r in hang}


def _cac_lan_nap(conn, cac_id: list[int]) -> dict[int, dict]:
    if not cac_id:
        return {}
    return {r["load_id"]: {"load_id": r["load_id"], "luc": r["started_at"],
                           "nguoi": r["actor_username"]}
            for r in q.query(conn, "SELECT load_id, started_at, actor_username FROM ctl.load "
                                   " WHERE load_id = ANY(%s)", (cac_id,))}


def giong_het(conn, domain_id: int, form_id: int, nam: int | None,
              file_sha256: str) -> dict | None:
    """QT-15: lần nạp đang có hiệu lực cùng nhóm, năm, loại tệp có cùng mã băm tệp."""
    hang = q.query_one(
        conn, "SELECT l.load_id, l.started_at, l.actor_username FROM ctl.load l "
              "  JOIN ctl.upload u USING (upload_id) "
              " WHERE l.domain_id = %s AND l.form_id = %s AND u.file_sha256 = %s "
              "   AND l.nam IS NOT DISTINCT FROM %s AND l.status = 'success' "
              " ORDER BY l.load_id DESC LIMIT 1",
        (domain_id, form_id, file_sha256, nam))
    return _lan_nap(hang)


def thong_tin_cho(conn, form: Form, tep: tep_cho.TepCho) -> dict:
    """Dữ liệu màn Xác nhận (MH-11): thông tin tệp, kết quả kiểm tra, thông báo,
    bảng theo tháng — so với dữ liệu **đang có lúc hỏi**."""
    tt = tep.thong_tin
    kt = tt["kiem_tra"]
    nam = tt["nam"]
    ra = {
        "ma_tep_cho": tep.ma,
        "nhom": tt["nhom"],
        "nam": nam,
        "loai": {"ma": form.code, "ten": form.label, "phu": form.subtitle},
        "ten_tep": tt["ten_tep"],
        "size_bytes": tt["size_bytes"],
        "sheet": kt.get("sheet_du_lieu"),
        "kiem_tra": [{
            "bang": b["bang"], "ten_bang": b["ten_bang"], "sheet": b["sheet"],
            "doc": b["doc"], "thieu_bat_buoc": b["thieu_bat_buoc"],
            "trung_bo": b["trung_bo"], "o_trong": b["o_trong"],
            "o_trong_chi_tiet": [{"cot": c["cot"], "so_o": c["so_o"]}
                                 for c in b["o_trong_chi_tiet"]],
            "se_ghi": b["se_ghi"], "tong": _so(b["tong"]), "ket_luan": b["ket_luan"],
        } for b in kt["bang"]],
        "giong_het": giong_het(conn, tt["domain_id"], tt["form_id"], nam, tt["sha256"]),
        "ghi_de": [], "moi": [], "truoc": None,
    }
    if form.source_kind == "bang_theo_tieu_de":
        ra.update(_theo_nhom_gc(conn, form, tt["domain_id"], nam, kt))
    else:
        ra.update(_theo_thang(conn, form, tt["domain_id"], nam, kt))
    return ra


def truoc_gc(conn, table: FormTable, domain_id: int, nam: int | None) -> dict | None:
    """HQ-MAU-GC: dữ liệu đang có hiệu lực của cùng (loại tệp, năm) — sẽ bị ghi đè
    toàn bộ (QT-10)."""
    hang = q.query_one(conn, sql.SQL(
        "SELECT count(*) AS so_dong, max(load_id) AS load_id FROM {} "
        " WHERE domain_id = %s AND is_current AND nam IS NOT DISTINCT FROM %s").format(
        sql.Identifier("silver", table.name)), (domain_id, nam))
    if not hang or not hang["so_dong"]:
        return None
    lan = _cac_lan_nap(conn, [hang["load_id"]]).get(hang["load_id"]) or {}
    return {"so_dong": hang["so_dong"], **lan}


def cau_a4(conn, form: Form, domain_id: int, nam: int | None) -> str:
    """Câu bước A4. HQ-MAU-GC: lần nạp đầu, hay ghi đè toàn bộ của lần nạp nào."""
    if form.source_kind != "bang_theo_tieu_de":
        return A4_HQKD
    truoc = truoc_gc(conn, form.tables[0], domain_id, nam)
    if truoc is None:
        return f"Lần nạp đầu của {form.label} năm {nam}."
    return f"Ghi đè toàn bộ {form.label} năm {nam} của lần nạp #{truoc['load_id']}."


def _theo_nhom_gc(conn, form: Form, domain_id: int, nam: int | None, kt: dict) -> dict:
    """HQ-MAU-GC — thẻ "Theo tháng giao mẫu" / "Theo đơn vị gia công"."""
    table = form.tables[0]
    b = kt["bang"][0]
    tn = b.get("theo_nhom") or {"cot": None, "cach": "", "thu_tu": [], "nhom": {}}
    truoc = truoc_gc(conn, table, domain_id, nam)
    theo_thang = tn["cach"] == "thang"
    hien = (_nhom_dang_co(conn, table, domain_id, nam, tn["cot"], theo_thang)
            if tn["cot"] else {})
    thu_tu = (sorted(tn["thu_tu"], key=lambda k: (k == "", k)) if theo_thang
              else tn["thu_tu"])
    dong = []
    for khoa in thu_tu:
        muc = tn["nhom"][khoa]
        hang = {"nhom": khoa or "(trống)", "so_dong": muc["so_dong"],
                "so_luong": _so(muc["so_luong"]), "hien_co": hien.get(khoa),
                "cach_ghi": "Ghi đè" if hien.get(khoa) else "Ghi thêm"}
        if theo_thang:
            if khoa:
                nam_t, thang = khoa.split("-")
                hang["nhom"] = f"Tháng {int(thang)}/{nam_t}"
            else:
                hang["nhom"] = kiem_tra_tep.CHUA_CO_NGAY
                hang["phu"] = (f"{tn['o_trong']} ô trống, "
                               f"{tn['khong_doc']} ô không đọc được ngày")
        dong.append(hang)
    tieu_de, cot_dau = (("Theo tháng giao mẫu", "Tháng giao mẫu") if theo_thang
                        else ("Theo đơn vị gia công", "Đơn vị gia công"))
    return {
        "truoc": truoc,
        "ghi_de": [form.label] if truoc else [],
        "moi": [] if truoc else [form.label],
        "theo_nhom": {"tieu_de": tieu_de, "cot_dau": cot_dau, "dong": dong,
                      "tong": {"so_dong": b["doc"], "so_luong": _so(b["tong"]),
                               "hien_co": truoc["so_dong"] if truoc else None}},
    }


def _nhom_dang_co(conn, table: FormTable, domain_id: int, nam: int | None, cot: str,
                  theo_thang: bool) -> dict[str, dict]:
    """Số dòng đang có theo nhóm (tháng giao mẫu / đơn vị gia công) của năm đã chọn."""
    bieu_thuc = (sql.SQL("coalesce(to_char(s.{}, 'YYYY-MM'), '')") if theo_thang
                 else sql.SQL("coalesce(s.{}::text, '')")).format(sql.Identifier(cot))
    hang = q.query(conn, sql.SQL(
        "SELECT {bt} AS khoa, count(*) AS so_dong, max(s.load_id) AS load_id FROM {bang} s "
        " WHERE s.domain_id = %s AND s.is_current AND s.nam IS NOT DISTINCT FROM %s "
        " GROUP BY 1").format(bt=bieu_thuc, bang=sql.Identifier("silver", table.name)),
        (domain_id, nam))
    lan = _cac_lan_nap(conn, [r["load_id"] for r in hang])
    return {r["khoa"]: {"so_dong": r["so_dong"], **(lan.get(r["load_id"]) or {})}
            for r in hang}


def _theo_thang(conn, form: Form, domain_id: int, nam: int | None, kt: dict) -> dict:
    """HQKD — thẻ "Theo tháng": mỗi tháng một dòng cho mỗi bảng số liệu, Ghi đè /
    Ghi thêm theo dữ liệu đang có của tháng đó trong năm đã chọn (QT-09)."""
    theo_bang = {b["bang"]: b for b in kt["bang"]}
    bang = [t for t in form.tables_by_display_order if t.partition_by and t.name in theo_bang]
    dang_co = {t.name: ky_dang_co(conn, t, domain_id, nam) for t in bang}
    cac_ky = sorted({k for t in bang for k in theo_bang[t.name].get("theo_ky", {})},
                    key=lambda k: (len(k), k))
    dong, ghi_de, moi = [], [], []
    tong = 0
    for ky in cac_ky:
        co = False
        for t in bang:
            muc = theo_bang[t.name]["theo_ky"].get(ky)
            if muc is None:
                continue
            hien = dang_co[t.name].get(ky)
            co = co or bool(hien)
            dong.append({
                "nhom": f"Tháng {ky}/{nam}" if nam else f"Tháng {ky}",
                "du_lieu": t.label,
                "so_dong": muc["so_dong"],
                "so_cot": muc["so_cot"],
                "so_cot_tong": theo_bang[t.name]["so_cot_tong"],
                "hien_co": hien,
                "cach_ghi": "Ghi đè" if hien else "Ghi thêm",
            })
            tong += muc["so_dong"]
        thang = int(ky) if ky.isdigit() else ky
        (ghi_de if co else moi).append(thang)
    return {"ghi_de": ghi_de, "moi": moi,
            "theo_nhom": {"tieu_de": "Theo tháng", "cot_dau": "Tháng", "dong": dong,
                          "tong": {"so_dong": tong}}}


def huy(upload_dir: Path, ma: str) -> bool:
    tep = tep_cho.doc(upload_dir, ma)
    if tep is None:
        return False
    tep_cho.xoa(tep)
    return True


# --------------------------------------------------------------------------- #
#  Bước 3 → 4 — Xác nhận thêm mới dữ liệu: ghi, đối chiếu, chốt
# --------------------------------------------------------------------------- #


def xac_nhan(kho, so_tay, settings, form: Form, tep: tep_cho.TepCho, *,
             domain_code: str, request_id: str) -> dict:
    """Ghi tệp chờ vào database. Trả `{"load_id", "status"}`."""
    giu = tep_cho.giu_de_ghi(tep)
    if giu is None:
        raise NotFound(TEP_CHO_HET)
    tt = giu.thong_tin
    kt = tt["kiem_tra"]
    dich = _cat_tep(settings.upload_dir, giu)
    chung = {"domain_id": tt["domain_id"], "form_id": tt["form_id"],
             "file_name": tt["ten_tep"], "file_sha256": tt["sha256"]}
    try:
        try:
            with kho.transaction() as conn:
                upload_id = q.scalar(
                    conn,
                    "INSERT INTO ctl.upload (domain_id, form_id, file_name, file_sha256, "
                    "size_bytes, storage_uri, uploaded_by, uploaded_by_username) "
                    "VALUES (%s, %s, %s, %s, %s, %s, NULL, %s) RETURNING upload_id",
                    (tt["domain_id"], tt["form_id"], tt["ten_tep"], tt["sha256"],
                     tt["size_bytes"], str(dich), tt["nguoi"]),
                )
                a4 = cau_a4(conn, form, tt["domain_id"], tt["nam"])
                load_id = orchestrator.chay(
                    conn, form, domain_code=domain_code, upload_id=upload_id,
                    upload_path=dich, actor_user_id=None, actor_username=tt["nguoi"],
                    request_id=request_id, settings=settings, nam=tt["nam"],
                    kiem_tra=kt, a4=a4, **chung)
        except StructureError as exc:
            kt_loi = {**kt, "loi": exc.errors, "buoc_loi": "A3"}
            cac = (cac_buoc.buoc_a(kt_loi, nguoi=tt["nguoi"], a4=None,
                                   mot_bang=len(form.tables) == 1)
                   + cac_buoc.buoc_b_tu_choi("A3", cac_buoc.ten_b4(kt)))
            load_id = ghi_that_bai(
                kho, so_tay, "rejected", exc.errors, so_byte=tt["size_bytes"],
                storage_uri=str(dich), nguoi_id=tt["nguoi_id"], nguoi_ten=tt["nguoi"],
                request_id=request_id, nam=tt["nam"], kiem_tra=kt_loi, cac=cac,
                doi_chieu=None, domain_id=tt["domain_id"], form_id=tt["form_id"],
                file_name=tt["ten_tep"], file_sha256=tt["sha256"])
            return {"load_id": load_id, "status": "rejected"}
        except ReconcileError as exc:
            load_id = ghi_that_bai(
                kho, so_tay, "mismatch", lech_thanh_loi(exc.mismatches), so_byte=tt["size_bytes"],
                storage_uri=str(dich), nguoi_id=tt["nguoi_id"], nguoi_ten=tt["nguoi"],
                request_id=request_id, nam=tt["nam"], kiem_tra=kt, cac=exc.steps,
                doi_chieu=exc.reconciliation, domain_id=tt["domain_id"], form_id=tt["form_id"],
                file_name=tt["ten_tep"], file_sha256=tt["sha256"])
            return {"load_id": load_id, "status": "mismatch"}
    except BaseException:
        # Lỗi ngoài dự kiến: không có lần nạp nào được ghi — trả tệp về hàng chờ.
        dich.unlink(missing_ok=True)
        tep_cho.tra_lai(giu)
        raise
    finally:
        if giu.thu_muc.exists() and giu.thu_muc.name.endswith(tep_cho.DANG_GHI):
            tep_cho.xoa(giu)

    with so_tay.transaction() as so:
        record_event(so, action="load.success", actor_user_id=None, actor_username=tt["nguoi"],
                    domain_id=tt["domain_id"], object_type="load", object_id=str(load_id),
                    request_id=request_id, detail={"nguoi_id": tt["nguoi_id"],
                                                   "nam": tt["nam"]})
    return {"load_id": load_id, "status": "success"}


def lech_thanh_loi(lech: list[dict]) -> list[dict]:
    """Chênh lệch đối chiếu thành dòng của danh sách lỗi (tab Lỗi, tệp CSV)."""
    return [{
        "sheet": e.get("label"),
        "position": NHAN_BUOC.get(e.get("step"), e.get("nhan_buoc") or e.get("step")),
        "issue": f"Bước {e.get('step')} lệch",
        "reason_code": "RECON_MISMATCH",
        "fix": "Xem tab Đối chiếu tệp gốc ↔ database để biết chỗ lệch.",
        "step": e.get("step"),
        "cell_ref": None,
    } for e in lech]
