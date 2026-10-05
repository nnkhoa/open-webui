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

from ... import messages
from ...errors import InvalidInput, NotFound, SourceFileError
from ...pipeline import pending_uploads, upload
from ...pipeline.pending_uploads import PendingUpload
from ...pipeline.upload import UploadRequest
from .. import json
from ..deps import NguCanhApi, mo_ngu_canh

router = APIRouter()

CHI_NHAN_XLSX = "Portal chỉ nhận tệp .xlsx. Hãy mở tệp trong Excel và lưu lại đúng định dạng."


def _nam(nam: str) -> int:
    """Năm dữ liệu bắt buộc ở mọi nhóm, 2025–2031 (QT-02)."""
    nam = (nam or "").strip()
    if not nam:
        raise InvalidInput("Chưa chọn Năm dữ liệu.")
    if not nam.isdigit() or int(nam) not in upload.YEARS:
        raise InvalidInput("Năm dữ liệu phải từ 2025 đến 2031.")
    return int(nam)


def _loai_tep(ngu_canh: NguCanhApi, nhom, loai: str):
    """Loại tệp: bắt buộc khi nhóm có nhiều loại tệp (QT-03); nhóm một loại tệp thì
    lấy loại duy nhất đó."""
    cac = ngu_canh.cac_loai_tep(nhom)
    if not cac:
        raise InvalidInput(
            f"Nhóm {nhom.name} chưa có thông tin: chưa khai báo loại tệp nên chưa nạp, "
            f"chưa có lịch sử và chưa có dữ liệu.")
    if loai:
        for form_id, form in cac:
            if form.code == loai:
                return form_id, form
        raise InvalidInput("Loại tệp không hợp lệ.")
    if len(cac) > 1:
        raise InvalidInput("Chưa chọn Loại tệp.")
    return cac[0]


@router.post("/uploads")
def kiem_tra_tep(nhom: str = Form(""), nam: str = Form(""), loai: str = Form(""),
                 file: UploadFile | None = File(None),
                 ngu_canh: NguCanhApi = Depends(mo_ngu_canh)) -> dict:
    if not nhom:
        raise InvalidInput("Chưa chọn Nhóm thông tin.")
    dm = ngu_canh.nhom(nhom)
    nam_so = _nam(nam)
    form_id, form = _loai_tep(ngu_canh, dm, loai)
    if file is None or not file.filename:
        raise InvalidInput("Chưa chọn tệp.")
    ten_tep = Path(file.filename).name
    if not ten_tep.lower().endswith(".xlsx"):
        raise InvalidInput(CHI_NHAN_XLSX)
    ngu_canh.bat_buoc_kho_san_sang()
    try:
        return upload.check_upload(ngu_canh.container, UploadRequest(
            domain_id=dm.domain_id, domain_code=dm.code, form_id=form_id, form=form,
            year=nam_so, file_name=ten_tep, source=file.file, user_id=ngu_canh.nguoi.user_id,
            user_name=ngu_canh.nguoi.user_name, request_id=ngu_canh.ma_yeu_cau))
    except SourceFileError:
        raise InvalidInput(CHI_NHAN_XLSX) from None


def _tep_cua_toi(ngu_canh: NguCanhApi, ma: str) -> PendingUpload:
    tep = pending_uploads.get_pending(ngu_canh.settings.upload_dir, ma)
    if tep is None or tep.metadata.user_id != ngu_canh.nguoi.user_id:
        raise NotFound(messages.UPLOAD_PENDING_EXPIRED)
    return tep


@router.get("/uploads/{ma}")
def xem_tep_cho(ma: str, ngu_canh: NguCanhApi = Depends(mo_ngu_canh)) -> dict:
    tep = _tep_cua_toi(ngu_canh, ma)
    form = ngu_canh.registry.form(tep.metadata.file_type)
    return json.sach(upload.pending_upload_view(ngu_canh.kho(), form, tep))


@router.delete("/uploads/{ma}", status_code=204)
def huy_tep_cho(ma: str, ngu_canh: NguCanhApi = Depends(mo_ngu_canh)) -> Response:
    tep = _tep_cua_toi(ngu_canh, ma)
    pending_uploads.delete(tep)
    return Response(status_code=204)


@router.post("/uploads/{ma}/confirm")
def xac_nhan(ma: str, ngu_canh: NguCanhApi = Depends(mo_ngu_canh)) -> dict:
    tep = _tep_cua_toi(ngu_canh, ma)
    ngu_canh.bat_buoc_kho_san_sang()
    return upload.confirm_upload(ngu_canh.container, tep, request_id=ngu_canh.ma_yeu_cau)
