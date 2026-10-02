"""Cấu hình database (MH-40, CN-50) — chỉ Admin.

    GET    /db-config         xem cấu hình (không bao giờ trả mật khẩu, PCN-02)
    POST   /db-config/test    thử kết nối với thông tin đang nhập, không lưu gì
    PUT    /db-config         thử, được thì lưu và portal dùng kết nối này ngay
    DELETE /db-config         bỏ cấu hình; dữ liệu trong database không bị đụng tới

Không đòi kho: cấu hình sai thì đây là đường duy nhất để sửa. Ô Mật khẩu để
trống nghĩa là giữ mật khẩu đang lưu.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...domain import ket_noi_kho
from ...security.audit import ghi as ghi_nhat_ky
from .. import json
from ..deps import NguCanhApi, mo_ngu_canh_admin

router = APIRouter()

SSL_MAC_DINH = "prefer"
DA_BO = "Đã bỏ cấu hình. Dữ liệu trong cơ sở dữ liệu đó không bị đụng tới."


class CauHinhVao(BaseModel):
    host: str = ""
    port: str | int = ""
    database: str = ""
    username: str = ""
    password: str = ""
    ghi_chu: str = ""


def _ket_noi(ngu_canh: NguCanhApi, vao: CauHinhVao) -> ket_noi_kho.KetNoi:
    """Soi từng ô (sai ⇒ 422 kèm lỗi theo ô), rồi dựng kết nối."""
    cu = ket_noi_kho.doc(ngu_canh.so())
    host, cong, database, username, sslmode = ket_noi_kho.kiem_tra_dau_vao(
        vao.host, str(vao.port), vao.database, vao.username,
        cu.sslmode if cu else SSL_MAC_DINH)
    mat_khau = vao.password or (cu.password if cu else "")
    return ket_noi_kho.KetNoi(host=host, port=cong, database=database, username=username,
                              password=mat_khau, sslmode=sslmode)


@router.get("/db-config")
def xem(ngu_canh: NguCanhApi = Depends(mo_ngu_canh_admin)) -> dict:
    kho = ngu_canh.container.kho
    kho.con_song()
    luu = ket_noi_kho.doc_day_du(ngu_canh.so())
    cau_hinh = None
    if luu:
        cau_hinh = {k: luu[k] for k in ("host", "port", "database", "username", "ghi_chu")}
    mo_ta = f"{luu['username']}@{luu['host']}:{luu['port']}/{luu['database']}" if luu else None
    return json.sach({
        "cau_hinh": cau_hinh,
        "ket_noi": ({"ok": kho.da_cau_hinh, "mo_ta": mo_ta, "ly_do": kho.ly_do or None}
                    if luu else None),
        "lan_thu": luu["thu_luc"] if luu else None,
        "luu_luc": luu["cap_nhat_luc"] if luu else None,
    })


@router.post("/db-config/test")
def thu(vao: CauHinhVao, ngu_canh: NguCanhApi = Depends(mo_ngu_canh_admin)) -> dict:
    dat, thong_bao = ket_noi_kho.thu(_ket_noi(ngu_canh, vao))
    return {"ok": dat, "thong_bao": thong_bao}


@router.put("/db-config")
def luu(vao: CauHinhVao, ngu_canh: NguCanhApi = Depends(mo_ngu_canh_admin)) -> dict:
    """Thử trước, ghi sau. Không kết nối được thì báo lỗi, giữ cấu hình cũ."""
    ket_noi = _ket_noi(ngu_canh, vao)
    dat, thong_bao = ket_noi_kho.thu(ket_noi)
    if not dat:
        return {"ok": False, "thong_bao": thong_bao}
    so = ngu_canh.so()
    nguoi = ngu_canh.nguoi
    ket_noi_kho.luu(so, ket_noi, ghi_chu=vao.ghi_chu, dat=True, thong_diep=thong_bao,
                    nguoi=nguoi.user_name)
    ghi_nhat_ky(so, action="kho.cau_hinh", actor_user_id=None, actor_username=nguoi.user_name,
                object_type="ket_noi_kho", object_id=ket_noi.mo_ta,
                request_id=ngu_canh.ma_yeu_cau,
                detail={"nguoi_id": nguoi.user_id, "mo_ta": ket_noi.mo_ta})
    ngu_canh.container.noi_lai_kho(so)
    return {"ok": True, "thong_bao": f"Đã lưu và nối tới {ket_noi.mo_ta}."}


@router.delete("/db-config")
def bo(ngu_canh: NguCanhApi = Depends(mo_ngu_canh_admin)) -> dict:
    so = ngu_canh.so()
    nguoi = ngu_canh.nguoi
    ket_noi_kho.xoa(so)
    ghi_nhat_ky(so, action="kho.ngat", actor_user_id=None, actor_username=nguoi.user_name,
                object_type="ket_noi_kho", object_id="-", request_id=ngu_canh.ma_yeu_cau,
                detail={"nguoi_id": nguoi.user_id})
    ngu_canh.container.kho.ngat("Quản trị đã bỏ cấu hình kết nối.", quen_dia_chi=True)
    return {"thong_bao": DA_BO}
