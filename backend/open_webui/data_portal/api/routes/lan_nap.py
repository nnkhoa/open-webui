"""Lịch sử nạp (MH-20), Chi tiết lần nạp (MH-21), Tệp gốc (MH-22), gỡ / xoá lịch sử.

    GET    /loads                          danh sách, tổng số, người nạp để lọc
    GET    /loads/{id}                     thông tin, các bước A1–B5, lỗi
    GET    /loads/{id}/reconcile           các thẻ đối chiếu (mục 18)
    GET    /loads/{id}/errors.csv          loi-lan-nap-{id}.csv
    GET    /loads/{id}/file                tệp .xlsx gốc
    GET    /loads/{id}/file/sheets         danh sách sheet, kể cả sheet ẩn
    GET    /loads/{id}/file/sheets/{n}     nội dung một sheet theo trang
    DELETE /loads/{id}                     chỉ Admin: gỡ (QT-17) / xoá lịch sử (QT-18)
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from fastapi import APIRouter, Depends, Response
from fastapi.responses import FileResponse

from ...domain import lan_nap
from ...errors import DuLieuVaoSai, KhongTimThay, XungDot
from ...pipeline import doi_chieu_the, rollback
from ...security.audit import ghi as ghi_nhat_ky
from ...sources import tep_goc
from .. import json
from ..deps import NguCanhApi, mo_ngu_canh, mo_ngu_canh_admin
from .nhom import loai_tep_json

router = APIRouter()

KHONG_THAY = "Không tìm thấy lần nạp này."
CAC_MOI = (25, 50, 100)
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def trang_moi(trang: int, moi: int | None, mac_dinh: int) -> tuple[int, int]:
    """Phân trang (mục 9.1): `trang` từ 1, `moi` là 25 / 50 / 100."""
    moi = mac_dinh if moi is None else moi
    if trang < 1 or moi not in CAC_MOI:
        raise DuLieuVaoSai("Tham số phân trang không hợp lệ.")
    return trang, moi


def _nam(nam: str) -> int | None:
    if not nam:
        return None
    if not nam.isdigit():
        raise DuLieuVaoSai("Năm dữ liệu không hợp lệ.")
    return int(nam)


def _lan_nap(ngu_canh: NguCanhApi, load_id: int) -> dict:
    hang = lan_nap.chi_tiet(ngu_canh.kho(), load_id)
    if hang is None:
        raise KhongTimThay(KHONG_THAY)
    return hang


# --------------------------------------------------------------------------- #
#  Danh sách, chi tiết
# --------------------------------------------------------------------------- #


@router.get("/loads")
def danh_sach(nhom: str = "", nam: str = "", loai: str = "", trang_thai: str = "",
              nguoi: str = "", tim: str = "", trang: int = 1, moi: int | None = None,
              ngu_canh: NguCanhApi = Depends(mo_ngu_canh)) -> dict:
    dm = ngu_canh.nhom(nhom)
    trang, moi = trang_moi(trang, moi, 25)
    form_id = None
    if loai:
        form_id = next((fid for fid, f in ngu_canh.cac_loai_tep(dm) if f.code == loai), None)
        if form_id is None:
            raise DuLieuVaoSai("Loại tệp không hợp lệ.")
    if trang_thai and trang_thai not in lan_nap.TRANG_THAI:
        raise DuLieuVaoSai("Trạng thái không hợp lệ.")
    conn = ngu_canh.kho()
    hang, tong = lan_nap.danh_sach(conn, dm.domain_id, nam=_nam(nam), form_id=form_id,
                                   trang_thai=trang_thai, nguoi=nguoi, tim=tim.strip(),
                                   trang=trang, moi=moi)
    return json.sach({
        "tong": tong,
        "nguoi_nap": lan_nap.nguoi_nap(conn, dm.domain_id),
        "dong": [{
            "id": r["load_id"], "ten_tep": r["file_name"], "nam": r["nam"],
            "loai": {"ma": r["form_code"], "ten": r["form_label"]},
            "nguoi": r["nguoi"], "luc": r["started_at"],
            "so_dong": r["rows_read"] if r["status"] == "success" else 0,
            "status": r["status"],
        } for r in hang],
    })


@router.get("/loads/{load_id}")
def chi_tiet(load_id: int, ngu_canh: NguCanhApi = Depends(mo_ngu_canh)) -> dict:
    r = _lan_nap(ngu_canh, load_id)
    form = ngu_canh.registry.form(r["form_code"])
    kt = r["kiem_tra"] or {}
    thanh_cong = r["status"] == "success"
    co_the_go = thanh_cong and rollback.co_go_duoc(ngu_canh.kho(), load_id)[0]
    return json.sach({
        "id": r["load_id"], "status": r["status"], "nhom": r["domain_code"], "nam": r["nam"],
        "loai": loai_tep_json(form), "ten_tep": r["file_name"], "size_bytes": r["size_bytes"],
        "nguoi": r["nguoi"], "luc": r["started_at"],
        "thang": lan_nap.pham_vi_thang(r),
        "sheet": kt.get("sheet_du_lieu") if r["status"] != "rejected" else None,
        "tong_so_dong": r["rows_read"] if thanh_cong else 0,
        "so_dong_ghi": lan_nap.so_dong_ghi(r),
        "so_sheet": kt.get("so_sheet") or r["sheets_count"],
        "buoc": r["cac_buoc"] or [],
        "loi": lan_nap.danh_sach_loi(r),
        "co_the_go": co_the_go,
        "co_hieu_luc": thanh_cong,
        "bang_chinh": lan_nap.bang_chinh(ngu_canh.registry, r["form_code"]),
    })


# --------------------------------------------------------------------------- #
#  Đối chiếu
# --------------------------------------------------------------------------- #

THU_TU_THE = ("so_dong", "tong", "tien_theo_nhom", "o_trong", "theo_chieu", "ma",
              "truoc_sau")


@router.get("/loads/{load_id}/reconcile")
def doi_chieu(load_id: int, the: str = "", bang: str = "", cot: str = "",
              chia_theo: str = "", trang: int = 1, moi: int | None = None,
              ngu_canh: NguCanhApi = Depends(mo_ngu_canh)) -> dict:
    r = _lan_nap(ngu_canh, load_id)
    trang, moi = trang_moi(trang, moi, 25)
    if r["status"] == "rejected":
        return {"the": [{"ma": "tu_choi", "tieu_de": "Đối chiếu tệp gốc ↔ database",
                         "thong_bao": doi_chieu_the.THONG_BAO_TU_CHOI, "cot": [], "dong": []}]}
    luu = r["doi_chieu"] or {}
    ra = []
    for ma in THU_TU_THE:
        if ma not in luu or (the and the != ma):
            continue
        if ma == "tien_theo_nhom":
            muc = doi_chieu_the.dung_the_tien(luu[ma], bang=bang or None, cot=cot or None,
                                              chia_theo=chia_theo or None)
        elif ma == "theo_chieu":
            muc = doi_chieu_the.dung_the_chieu(luu[ma], chia_theo=chia_theo or None,
                                               trang=trang, moi=moi)
        else:
            muc = {k: v for k, v in luu[ma].items() if k != "cac_bang"}
        if ma == "truoc_sau" and r["status"] == "mismatch":
            muc = {**muc, "dong": [], "thong_bao": doi_chieu_the.THONG_BAO_HUY}
        ra.append(muc)
    if the and not ra:
        raise KhongTimThay("Không có thẻ đối chiếu này.")
    return json.sach({"the": ra})


# --------------------------------------------------------------------------- #
#  Danh sách lỗi, tệp gốc
# --------------------------------------------------------------------------- #


@router.get("/loads/{load_id}/errors.csv")
def tai_loi(load_id: int, ngu_canh: NguCanhApi = Depends(mo_ngu_canh)) -> Response:
    r = _lan_nap(ngu_canh, load_id)
    bo_dem = io.StringIO()
    bo_dem.write("﻿")                      # để Excel mở đúng tiếng Việt
    ghi = csv.writer(bo_dem)
    ghi.writerow(["Sheet", "Vị trí", "Vấn đề", "Cách xử lý"])
    for e in lan_nap.danh_sach_loi(r):
        ghi.writerow([e["sheet"] or "", e["vi_tri"] or "", e["van_de"] or "",
                      e["cach_xu_ly"] or ""])
    return Response(bo_dem.getvalue(), media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="loi-lan-nap-{load_id}.csv"'})


def _tep(ngu_canh: NguCanhApi, load_id: int) -> tuple[dict, Path]:
    r = _lan_nap(ngu_canh, load_id)
    duong = Path(r["storage_uri"] or "")
    if not duong.is_file():
        raise KhongTimThay("Không còn tệp gốc của lần nạp này.")
    return r, duong


@router.get("/loads/{load_id}/file")
def tai_tep_goc(load_id: int, ngu_canh: NguCanhApi = Depends(mo_ngu_canh)) -> FileResponse:
    r, duong = _tep(ngu_canh, load_id)
    return FileResponse(duong, media_type=XLSX, filename=r["file_name"])


@router.get("/loads/{load_id}/file/sheets")
def cac_sheet(load_id: int, ngu_canh: NguCanhApi = Depends(mo_ngu_canh)) -> list[dict]:
    _, duong = _tep(ngu_canh, load_id)
    return tep_goc.cac_sheet(duong)


@router.get("/loads/{load_id}/file/sheets/{so}")
def noi_dung_sheet(load_id: int, so: int, trang: int = 1, moi: int | None = None,
                   ngu_canh: NguCanhApi = Depends(mo_ngu_canh)) -> dict:
    _, duong = _tep(ngu_canh, load_id)
    trang, moi = trang_moi(trang, moi, 50)
    ra = tep_goc.noi_dung(duong, so, trang, moi)
    if ra is None:
        raise KhongTimThay("Không có sheet này trong tệp.")
    return ra


# --------------------------------------------------------------------------- #
#  Gỡ dữ liệu, xoá lịch sử — chỉ Admin
# --------------------------------------------------------------------------- #


@router.delete("/loads/{load_id}", status_code=204)
def xoa(load_id: int, ngu_canh: NguCanhApi = Depends(mo_ngu_canh_admin)) -> Response:
    """Thành công ⇒ gỡ dữ liệu (chỉ lần mới nhất, QT-17; không thì 409). Bị từ
    chối / lỗi đối chiếu / đã gỡ ⇒ xoá lịch sử (QT-18)."""
    container = ngu_canh.container
    ngu_canh.bat_buoc_kho_san_sang()
    with container.giao_dich_kho() as conn:
        r = lan_nap.chi_tiet(conn, load_id)
        if r is None:
            raise KhongTimThay(KHONG_THAY)
        if r["status"] == "success":
            duoc, ly_do = rollback.co_go_duoc(conn, load_id)
            if not duoc:
                raise XungDot(ly_do)
            tep = rollback.go(conn, container.registry, load_id)["tep"]
            hanh_dong = "load.rollback"
        else:
            tep = rollback.xoa_lich_su(conn, load_id)
            hanh_dong = "load.delete_history"
    if tep:
        Path(tep).unlink(missing_ok=True)
    with container.so_tay.giao_dich() as so:
        ghi_nhat_ky(so, action=hanh_dong, actor_user_id=None,
                    actor_username=ngu_canh.nguoi.user_name, domain_id=r["domain_id"],
                    object_type="load", object_id=str(load_id),
                    request_id=ngu_canh.ma_yeu_cau,
                    detail={"nguoi_id": ngu_canh.nguoi.user_id, "ten_tep": r["file_name"]})
    return Response(status_code=204)

