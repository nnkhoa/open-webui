"""Màn Dữ liệu (MH-30), Chi tiết bảng (MH-31), Giải thích các cột (MH-32), Tải Excel.

    GET /tables?nhom&nam                        các bảng của nhóm, số dòng, lần nạp
    GET /tables/{bang}?lop&nam&ky&tim&trang&moi cột, dòng, tổng dòng, dòng tổng
    GET /tables/{bang}/export.xlsx?lop&nam&ky&tim  tệp Excel kèm sheet THONG_TIN

Bảng phải thuộc một nhóm thông tin đang hoạt động; mọi truy vấn lọc theo nhóm đó
ngay trong câu SQL. Bảng danh mục dùng chung mọi năm: bỏ qua bộ lọc năm (QT-19).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from ...domain import bang as bang_dl
from ...domain import xuat_excel
from ...errors import InvalidInput, NotFound
from .. import json
from ..deps import NguCanhApi, mo_ngu_canh
from .lan_nap import _nam, trang_moi
from .nhom import loai_tep_json

router = APIRouter()

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _pham_vi_thang(cac_ky: list) -> str | None:
    if not cac_ky:
        return None
    return str(cac_ky[0]) if len(cac_ky) == 1 else f"{cac_ky[0]} → {cac_ky[-1]}"


@router.get("/tables")
def danh_sach(nhom: str = "", nam: str = "",
              ngu_canh: NguCanhApi = Depends(mo_ngu_canh)) -> list[dict]:
    dm = ngu_canh.nhom(nhom)
    nam_so = _nam(nam)
    ra = []
    for muc in bang_dl.danh_sach(ngu_canh.kho(), ngu_canh.registry, dm.domain_id, nam_so):
        t = muc["table"]
        la_fact = not t.is_dim
        ra.append({
            "bang": t.name, "ten": t.label, "mo_ta": t.description,
            "loai": t.kind,
            "nam": nam_so if la_fact else None,
            "thang": _pham_vi_thang(muc["cac_ky"]) if la_fact else None,
            "loai_tep": loai_tep_json(muc["form"]),
            "load_id": muc["load_id"],
            "so_dong": muc["so_dong"],
            "cap_nhat": muc["cap_nhat"],
        })
    return json.sach(ra)


def _bang(ngu_canh: NguCanhApi, ten: str):
    """Bảng thuộc nhóm thông tin đang hoạt động, kèm nhóm và loại tệp của nó."""
    nhom = bang_dl.nhom_cua_bang(ngu_canh.kho(), ten)
    if nhom is None:
        raise NotFound("Không tìm thấy bảng dữ liệu này.")
    table = ngu_canh.registry.table(ten)
    form = next(f for f in ngu_canh.registry.forms if table in f.tables)
    return nhom, table, form


def _loc(lop: str, nam: str, table) -> tuple[str, int | None]:
    lop = lop or "gold"
    if lop not in bang_dl.TEN_LOP:
        raise InvalidInput("Lớp dữ liệu không hợp lệ.")
    return lop, (_nam(nam) if table.cot_nam is not None else None)


@router.get("/tables/{ten}")
def chi_tiet(ten: str, lop: str = "", nam: str = "", ky: str = "", tim: str = "",
             trang: int = 1, moi: int | None = None,
             ngu_canh: NguCanhApi = Depends(mo_ngu_canh)) -> dict:
    nhom, table, form = _bang(ngu_canh, ten)
    lop, nam_so = _loc(lop, nam, table)
    trang, moi = trang_moi(trang, moi, 50)
    conn = ngu_canh.kho()
    tk = bang_dl.thong_ke(conn, table, nhom["domain_id"], nam_so)
    du_lieu = bang_dl.doc(conn, table, nhom["domain_id"], lop=lop, nam=nam_so, ky=ky.strip(),
                          tim=tim.strip(), trang=trang, moi=moi)
    thang_moi_nhat = None
    if tk["cac_ky"] and table.cot_nam is not None:
        nam_cuoi = nam_so if nam_so is not None else _nam_moi_nhat(conn, table, nhom)
        thang_moi_nhat = f"{tk['cac_ky'][-1]}/{nam_cuoi}" if nam_cuoi else None
    return json.sach({
        "bang": table.name, "ten": table.label, "mo_ta": table.description,
        "moi_dong_la": table.grain, "nhom": nhom["code"], "loai": table.kind,
        "loai_tep": loai_tep_json(form), "lop": lop, "nam": nam_so,
        "thang_moi_nhat": thang_moi_nhat, "cap_nhat": tk["cap_nhat"],
        # Chip "Tháng" chỉ ở bảng HQKD có cột kỳ (`ky_thang` của Đơn gia công để trống).
        "co_ky": bool(table.partition_by),
        "ky_ds": [str(k) for k in tk["cac_ky"]],
        "cot": bang_dl.thong_tin_cot(table, form.tables),
        "tong": du_lieu["tong"], "dong": du_lieu["dong"], "dong_tong": du_lieu["dong_tong"],
    })


def _nam_moi_nhat(conn, table, nhom) -> int | None:
    """Năm mới nhất có dữ liệu khi đang xem "Tất cả năm"."""
    for nam in range(2031, 2024, -1):
        if bang_dl.thong_ke(conn, table, nhom["domain_id"], nam)["so_dong"]:
            return nam
    return None


@router.get("/tables/{ten}/export.xlsx")
def tai_excel(ten: str, lop: str = "", nam: str = "", ky: str = "", tim: str = "",
              ngu_canh: NguCanhApi = Depends(mo_ngu_canh)) -> Response:
    nhom, table, form = _bang(ngu_canh, ten)
    lop, nam_so = _loc(lop, nam, table)
    du_lieu = bang_dl.doc(ngu_canh.kho(), table, nhom["domain_id"], lop=lop, nam=nam_so,
                          ky=ky.strip(), tim=tim.strip(), trang=1, moi=None)
    bo_loc = ", ".join(f"{k} = {v}" for k, v in (("nam", nam_so), ("ky", ky.strip()),
                                                 ("tim", tim.strip())) if v) or "Không lọc"
    noi_dung = xuat_excel.ghi(table, du_lieu, nhom=f"{nhom['code']} — {nhom['name']}",
                              ten_lop=bang_dl.TEN_LOP[lop], bo_loc=bo_loc,
                              cot=bang_dl.thong_tin_cot(table, form.tables))
    ten_tep = xuat_excel.ten_tep(nhom["code"], table, lop, nam_so)
    return Response(noi_dung, media_type=XLSX, headers={
        "Content-Disposition": f'attachment; filename="{ten_tep}"',
        "X-So-Dong": str(du_lieu["tong"])})
