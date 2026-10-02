"""Nạp dữ liệu hai bước (MH-10, MH-11): Kiểm tra tệp → Xác nhận → Ghi.

    POST   /uploads                    chỉ đọc tệp (QT-07): `{ma_tep_cho}` hoặc
                                       `{load_id, status: "rejected"}`
    GET    /uploads/{ma}               màn Xác nhận
    DELETE /uploads/{ma}               "Huỷ, không nạp" — 204
    POST   /uploads/{ma}/confirm       ghi một giao dịch: `{load_id, status}`

Tệp chờ chỉ người đã tải lên mới xem, xác nhận hay huỷ được; người khác nhận
404 như tệp không có (không tiết lộ tệp có tồn tại hay không).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile

from ...errors import DuLieuVaoSai, KhongTimThay, NguonDuLieuError
from ...pipeline import nap, tep_cho
from .. import json
from ..deps import NguCanhApi, mo_ngu_canh

router = APIRouter()

CHI_NHAN_XLSX = "Portal chỉ nhận tệp .xlsx. Hãy mở tệp trong Excel và lưu lại đúng định dạng."


def _nam(nam: str) -> int:
    """Năm dữ liệu bắt buộc ở mọi nhóm, 2025–2031 (QT-02)."""
    nam = (nam or "").strip()
    if not nam:
        raise DuLieuVaoSai("Chưa chọn Năm dữ liệu.")
    if not nam.isdigit() or int(nam) not in nap.CAC_NAM:
        raise DuLieuVaoSai("Năm dữ liệu phải từ 2025 đến 2031.")
    return int(nam)


def _loai_tep(ngu_canh: NguCanhApi, nhom, loai: str):
    """Loại tệp: bắt buộc khi nhóm có nhiều loại tệp (QT-03); nhóm một loại tệp thì
    lấy loại duy nhất đó."""
    cac = ngu_canh.cac_loai_tep(nhom)
    if not cac:
        raise DuLieuVaoSai(
            f"Nhóm {nhom.name} chưa có thông tin: chưa khai báo loại tệp nên chưa nạp, "
            f"chưa có lịch sử và chưa có dữ liệu.")
    if loai:
        for form_id, form in cac:
            if form.code == loai:
                return form_id, form
        raise DuLieuVaoSai("Loại tệp không hợp lệ.")
    if len(cac) > 1:
        raise DuLieuVaoSai("Chưa chọn Loại tệp.")
    return cac[0]


@router.post("/uploads")
def kiem_tra_tep(nhom: str = Form(""), nam: str = Form(""), loai: str = Form(""),
                 file: UploadFile | None = File(None),
                 ngu_canh: NguCanhApi = Depends(mo_ngu_canh)) -> dict:
    if not nhom:
        raise DuLieuVaoSai("Chưa chọn Nhóm thông tin.")
    dm = ngu_canh.nhom(nhom)
    nam_so = _nam(nam)
    form_id, form = _loai_tep(ngu_canh, dm, loai)
    if file is None or not file.filename:
        raise DuLieuVaoSai("Chưa chọn tệp.")
    ten_tep = Path(file.filename).name
    if not ten_tep.lower().endswith(".xlsx"):
        raise DuLieuVaoSai(CHI_NHAN_XLSX)
    ngu_canh.bat_buoc_kho_san_sang()
    try:
        return nap.kiem_tra(
            ngu_canh.container.kho, ngu_canh.container.so_tay, ngu_canh.settings,
            domain_id=dm.domain_id, domain_code=dm.code, form_id=form_id, form=form,
            nam=nam_so, ten_tep=ten_tep, nguon=file.file, nguoi_id=ngu_canh.nguoi.user_id,
            nguoi_ten=ngu_canh.nguoi.user_name, request_id=ngu_canh.ma_yeu_cau)
    except NguonDuLieuError:
        raise DuLieuVaoSai(CHI_NHAN_XLSX) from None


def _tep_cua_toi(ngu_canh: NguCanhApi, ma: str) -> tep_cho.TepCho:
    tep = tep_cho.doc(ngu_canh.settings.upload_dir, ma)
    if tep is None or tep.thong_tin.get("nguoi_id") != ngu_canh.nguoi.user_id:
        raise KhongTimThay(nap.TEP_CHO_HET)
    return tep


@router.get("/uploads/{ma}")
def xem_tep_cho(ma: str, ngu_canh: NguCanhApi = Depends(mo_ngu_canh)) -> dict:
    tep = _tep_cua_toi(ngu_canh, ma)
    form = ngu_canh.registry.form(tep.thong_tin["loai"])
    return json.sach(nap.thong_tin_cho(ngu_canh.kho(), form, tep))


@router.delete("/uploads/{ma}", status_code=204)
def huy_tep_cho(ma: str, ngu_canh: NguCanhApi = Depends(mo_ngu_canh)) -> Response:
    tep = _tep_cua_toi(ngu_canh, ma)
    tep_cho.xoa(tep)
    return Response(status_code=204)


@router.post("/uploads/{ma}/confirm")
def xac_nhan(ma: str, ngu_canh: NguCanhApi = Depends(mo_ngu_canh)) -> dict:
    tep = _tep_cua_toi(ngu_canh, ma)
    form = ngu_canh.registry.form(tep.thong_tin["loai"])
    ngu_canh.bat_buoc_kho_san_sang()
    return nap.xac_nhan(ngu_canh.container.kho, ngu_canh.container.so_tay,
                        ngu_canh.settings, form, tep, domain_code=tep.thong_tin["nhom"],
                        request_id=ngu_canh.ma_yeu_cau)
