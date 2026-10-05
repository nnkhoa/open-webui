"""Màn Dữ liệu, Chi tiết bảng, Tải Excel (mục 19, QT-19, QT-20, B12, B17)."""

from __future__ import annotations

import io

import openpyxl
import pytest

from .conftest import can_tep_mau, tai_len


@pytest.fixture
def da_nap(admin):
    ma = tai_len(admin, can_tep_mau()).json()["pending_id"]
    return admin("POST", f"/uploads/{ma}/confirm").json()["load_id"]


def test_danh_sach_bang(admin, da_nap):
    d = admin("GET", "/tables?domain=HQKD&year=2026").json()
    assert [b["table"] for b in d] == ["fact_ket_qua_kd", "fact_chi_phi", "dim_khach_hang",
                                      "dim_khoan_cp"]
    kqkd, cp, kh, dm = d
    assert (kqkd["name"], kqkd["kind"], kqkd["year"], kqkd["months"], kqkd["row_count"]) == (
        "Kết quả kinh doanh", "fact", 2026, "1 → 7", 348)
    assert kqkd["description"] == ("Doanh thu, giá vốn và lợi nhuận theo tháng, khách hàng và nhóm "
                             "kinh doanh.")
    assert kqkd["load_id"] == da_nap and kqkd["updated_at"]
    assert kqkd["file_type"]["code"] == "BAO_CAO_HQKH"
    assert cp["row_count"] == 6960
    assert (kh["year"], kh["months"], kh["row_count"]) == (None, None, 137)
    assert (dm["name"], dm["row_count"]) == ("Danh mục chi phí", 26)
    nam_khac = admin("GET", "/tables?domain=HQKD&year=2027").json()
    assert nam_khac[0]["row_count"] == 0 and nam_khac[0]["load_id"] is None
    assert nam_khac[2]["row_count"] == 137          # danh mục dùng chung mọi năm


def test_chi_tiet_bang_va_loc(admin, da_nap):
    d = admin("GET", "/tables/fact_ket_qua_kd?year=2026").json()
    assert (d["table"], d["domain"], d["kind"], d["layer"], d["total"]) == (
        "fact_ket_qua_kd", "HQKD", "fact", "gold", 348)
    assert d["latest_month"] == "7/2026" and d["has_period"] is True
    assert d["periods"] == ["1", "2", "3", "4", "5", "6", "7"]
    assert d["columns"][0]["name"] == "nam"
    assert d["columns"][0]["source_name"] == "Không có trong tệp — lấy từ ô Năm dữ liệu chọn lúc nạp"
    assert d["columns"][0]["required"] is True
    ten_cot = [c["name"] for c in d["columns"]]
    assert len(d["rows"]) == 50 and len(d["rows"][0]) == len(ten_cot)
    assert d["rows"][0][0] == 2026
    assert d["total_row"] is None
    doanh_thu = next(c for c in d["columns"] if c["name"] == "doanh_thu")
    assert doanh_thu["is_measure"] and doanh_thu["type"] == "money"

    thang3 = admin("GET", "/tables/fact_ket_qua_kd?year=2026&period=3").json()
    assert thang3["total"] == 53
    i = ten_cot.index("doanh_thu")
    assert thang3["total_row"][i] == 272752377208
    assert thang3["total_row"][0] is None
    sale1 = admin("GET", "/tables/fact_ket_qua_kd?year=2026&query=SALE%201").json()
    assert sale1["total"] == 62
    trang2 = admin("GET", "/tables/fact_ket_qua_kd?year=2026&page=2&page_size=100").json()
    assert len(trang2["rows"]) == 100
    goc = admin("GET", "/tables/fact_ket_qua_kd?year=2026&layer=bronze&period=3").json()
    assert goc["total"] == 53 and goc["total_row"] is None
    assert admin("GET", "/tables/fact_ket_qua_kd?year=2027").json()["total"] == 0
    assert admin("GET", "/tables/fact_ket_qua_kd?layer=xyz").status_code == 422
    assert admin("GET", "/tables/khong_co_bang").status_code == 404
    dm = admin("GET", "/tables/dim_khach_hang?year=2030").json()
    assert dm["total"] == 137 and dm["has_period"] is False


def test_tai_excel_kem_thong_tin(admin, da_nap):
    r = admin("GET", "/tables/fact_ket_qua_kd/export.xlsx?year=2026&period=3")
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
