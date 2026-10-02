"""Màn Dữ liệu, Chi tiết bảng, Tải Excel (mục 19, QT-19, QT-20, B12, B17)."""

from __future__ import annotations

import io

import openpyxl
import pytest

from .conftest import can_tep_mau, tai_len


@pytest.fixture
def da_nap(admin):
    ma = tai_len(admin, can_tep_mau()).json()["ma_tep_cho"]
    return admin("POST", f"/uploads/{ma}/confirm").json()["load_id"]


def test_danh_sach_bang(admin, da_nap):
    d = admin("GET", "/tables?nhom=HQKD&nam=2026").json()
    assert [b["bang"] for b in d] == ["fact_ket_qua_kd", "fact_chi_phi", "dim_khach_hang",
                                      "dim_khoan_cp"]
    kqkd, cp, kh, dm = d
    assert (kqkd["ten"], kqkd["loai"], kqkd["nam"], kqkd["thang"], kqkd["so_dong"]) == (
        "Kết quả kinh doanh", "fact", 2026, "1 → 7", 348)
    assert kqkd["mo_ta"] == ("Doanh thu, giá vốn và lợi nhuận theo tháng, khách hàng và nhóm "
                             "kinh doanh.")
    assert kqkd["load_id"] == da_nap and kqkd["cap_nhat"]
    assert kqkd["loai_tep"]["ma"] == "BAO_CAO_HQKH"
    assert cp["so_dong"] == 6960
    assert (kh["nam"], kh["thang"], kh["so_dong"]) == (None, None, 137)
    assert (dm["ten"], dm["so_dong"]) == ("Danh mục chi phí", 26)
    nam_khac = admin("GET", "/tables?nhom=HQKD&nam=2027").json()
    assert nam_khac[0]["so_dong"] == 0 and nam_khac[0]["load_id"] is None
    assert nam_khac[2]["so_dong"] == 137          # danh mục dùng chung mọi năm


def test_chi_tiet_bang_va_loc(admin, da_nap):
    d = admin("GET", "/tables/fact_ket_qua_kd?nam=2026").json()
    assert (d["bang"], d["nhom"], d["loai"], d["lop"], d["tong"]) == (
        "fact_ket_qua_kd", "HQKD", "fact", "gold", 348)
    assert d["thang_moi_nhat"] == "7/2026" and d["co_ky"] is True
    assert d["ky_ds"] == ["1", "2", "3", "4", "5", "6", "7"]
    assert d["cot"][0]["ten"] == "nam"
    assert d["cot"][0]["ten_nbc"] == "Không có trong tệp — lấy từ ô Năm dữ liệu chọn lúc nạp"
    assert d["cot"][0]["bat_buoc"] is True
    ten_cot = [c["ten"] for c in d["cot"]]
    assert len(d["dong"]) == 50 and len(d["dong"][0]) == len(ten_cot)
    assert d["dong"][0][0] == 2026
    assert d["dong_tong"] is None
    doanh_thu = next(c for c in d["cot"] if c["ten"] == "doanh_thu")
    assert doanh_thu["so_do"] and doanh_thu["kieu"] == "money"

    thang3 = admin("GET", "/tables/fact_ket_qua_kd?nam=2026&ky=3").json()
    assert thang3["tong"] == 53
    i = ten_cot.index("doanh_thu")
    assert thang3["dong_tong"][i] == 272752377208
    assert thang3["dong_tong"][0] is None
    sale1 = admin("GET", "/tables/fact_ket_qua_kd?nam=2026&tim=SALE%201").json()
    assert sale1["tong"] == 62
    trang2 = admin("GET", "/tables/fact_ket_qua_kd?nam=2026&trang=2&moi=100").json()
    assert len(trang2["dong"]) == 100
    goc = admin("GET", "/tables/fact_ket_qua_kd?nam=2026&lop=bronze&ky=3").json()
    assert goc["tong"] == 53 and goc["dong_tong"] is None
    assert admin("GET", "/tables/fact_ket_qua_kd?nam=2027").json()["tong"] == 0
    assert admin("GET", "/tables/fact_ket_qua_kd?lop=xyz").status_code == 422
    assert admin("GET", "/tables/khong_co_bang").status_code == 404
    dm = admin("GET", "/tables/dim_khach_hang?nam=2030").json()
    assert dm["tong"] == 137 and dm["co_ky"] is False


def test_tai_excel_kem_thong_tin(admin, da_nap):
    r = admin("GET", "/tables/fact_ket_qua_kd/export.xlsx?nam=2026&ky=3")
    assert r.status_code == 200
    assert r.headers["content-disposition"] == (
        'attachment; filename="HQKD-fact_ket_qua_kd-gold-2026.xlsx"')
    so = openpyxl.load_workbook(io.BytesIO(r.content))
    assert so.sheetnames == ["fact_ket_qua_kd", "THONG_TIN"]
    du_lieu = list(so["fact_ket_qua_kd"].values)
    assert du_lieu[0][:3] == ("nam", "ky_thang", "ma_khach")
    assert len(du_lieu) == 1 + 53
    tt = list(so["THONG_TIN"].values)
    assert [d[0] for d in tt[:10]] == ["Bảng", "Tên bảng", "Nội dung", "Mỗi dòng là",
                                       "Dùng để", "Nhóm thông tin", "Lớp dữ liệu", "Bộ lọc",
                                       "Số dòng", "Xuất lúc"]
    assert tt[6][1] == "Dữ liệu phân tích"
    assert tt[7][1] == "nam = 2026, ky = 3"
    assert tt[8][1] == 53
    assert tt[11] == ("ten_cot", "ten_trong_tep_nbc", "kieu_du_lieu", "bat_buoc", "y_nghia",
                      "dung_de", "vi_du")
    assert tt[12][0] == "nam"
