"""Nạp dữ liệu hai bước: POST /uploads (chỉ đọc), GET / DELETE /uploads/{ma},
POST /uploads/{ma}/confirm (ghi một giao dịch). Đặc tả 6.1, 15, QT-02…QT-15."""

from __future__ import annotations

import openpyxl

from open_webui.data_portal.pipeline import reconcile
from .conftest import can_tep_mau, dem, tai_len

DEM_DU_LIEU = ("SELECT (SELECT count(*) FROM ctl.load) + (SELECT count(*) FROM ctl.upload)"
               " + (SELECT count(*) FROM bronze.fact_ket_qua_kd)"
               " + (SELECT count(*) FROM silver.fact_chi_phi)")


def _nap(goi, nam="2026", tep=None):
    ma = tai_len(goi, tep or can_tep_mau(), nam=nam).json()["pending_id"]
    return goi("POST", f"/uploads/{ma}/confirm").json()


def _gold_nam(ct, bang, nam):
    return dem(ct, f"SELECT count(*) FROM gold.{bang} WHERE is_current AND nam = %s", (nam,))


def test_domains(admin):
    r = admin("GET", "/domains")
    assert r.status_code == 200
    hqkd = r.json()[0]
    assert hqkd == {"code": "HQKD", "name": "Hiệu quả kinh doanh theo nhóm và khách hàng",
                    "subtitle": "HQKD · Báo cáo hiệu quả từng khách hàng",
                    "file_types": [{"code": "BAO_CAO_HQKH",
                                    "name": "Báo cáo hiệu quả từng khách hàng", "subtitle": None}]}


def test_kiem_tra_tep_khong_ghi_database(admin, sach):
    """NT-07: bước Kiểm tra tệp không ghi gì vào database."""
    truoc = dem(sach, DEM_DU_LIEU)
    r = tai_len(admin, can_tep_mau())
    assert r.status_code == 200
    assert set(r.json()) == {"pending_id"}
    assert dem(sach, DEM_DU_LIEU) == truoc == 0


def test_tham_so_bat_buoc_422(admin):
    tep = can_tep_mau()
    assert tai_len(admin, tep, nam="").json()["detail"] == "Chưa chọn Năm dữ liệu."
    for nam in ("2024", "2032", "abc"):
        r = tai_len(admin, tep, nam=nam)
        assert r.status_code == 422
        assert r.json()["detail"] == "Năm dữ liệu phải từ 2025 đến 2031."
    assert tai_len(admin, tep, nhom="KHONG-CO").status_code == 422
    assert tai_len(admin, tep, loai="KHONG_CO").status_code == 422


def test_chi_nhan_xlsx(admin, tmp_path):
    xls = tmp_path / "bao-cao.xls"
    xls.write_bytes(b"khong phai xlsx")
    r = tai_len(admin, xls)
    assert r.status_code == 422
    assert r.json()["detail"] == ("Portal chỉ nhận tệp .xlsx. Hãy mở tệp trong Excel và lưu "
                                  "lại đúng định dạng.")
    hong = tmp_path / "hong.xlsx"
    hong.write_bytes(b"khong phai zip")
    assert tai_len(admin, hong).status_code == 422


def test_man_xac_nhan_lan_dau(admin):
    ma = tai_len(admin, can_tep_mau()).json()["pending_id"]
    r = admin("GET", f"/uploads/{ma}")
    assert r.status_code == 200
    d = r.json()
    assert (d["domain"], d["year"], d["file_type"]["code"], d["size_bytes"]) == (
        "HQKD", 2026, "BAO_CAO_HQKH", can_tep_mau().stat().st_size)
    kt = {b["table"]: b for b in d["checks"]}
    assert kt["fact_ket_qua_kd"]["read"] == 348
    assert kt["dim_khach_hang"]["duplicates"] == 90
    assert kt["dim_khach_hang"]["to_write"] == 137
    assert kt["fact_chi_phi"]["total"] == 122689472100.6453
    assert kt["fact_ket_qua_kd"]["verdict"] == "Hợp lệ"
    assert d["identical"] is None
    assert d["new"] == [1, 2, 3, 4, 5, 6, 7] and d["overwrite"] == []
    dong = d["by_group"]["rows"]
    assert dong[0] == {"group": "Tháng 1/2026", "data": "Kết quả kinh doanh",
                       "row_count": 50, "column_count": 15, "total_column_count": 15, "existing": None,
                       "write_mode": "Ghi thêm"}
    assert dong[1]["data"] == "Chi phí" and dong[1]["row_count"] == 1000
    assert d["by_group"]["total"]["row_count"] == 348 + 6960


def test_huy_tep_cho(admin, sach):
    ma = tai_len(admin, can_tep_mau()).json()["pending_id"]
    assert admin("DELETE", f"/uploads/{ma}").status_code == 204
    assert admin("GET", f"/uploads/{ma}").status_code == 404
    assert admin("POST", f"/uploads/{ma}/confirm").status_code == 404
    assert dem(sach, DEM_DU_LIEU) == 0


def test_tep_cho_cua_nguoi_khac_404(admin, loader):
    ma = tai_len(admin, can_tep_mau()).json()["pending_id"]
    r = loader("GET", f"/uploads/{ma}")
    assert r.status_code == 404
    assert loader("DELETE", f"/uploads/{ma}").status_code == 404
    assert admin("GET", f"/uploads/{ma}").status_code == 200


def test_xac_nhan_ghi_thanh_cong(admin, sach):
    kq = _nap(admin)
    assert kq["status"] == "success"
    assert _gold_nam(sach, "fact_ket_qua_kd", 2026) == 348
    assert _gold_nam(sach, "fact_chi_phi", 2026) == 6960
    assert dem(sach, "SELECT count(*) FROM gold.dim_khach_hang WHERE is_current") == 137
    assert dem(sach, "SELECT year FROM ctl.load WHERE load_id = %s", (kq["load_id"],)) == 2026
    # Xác nhận lần hai: tệp chờ đã ghi, không còn.
    assert dem(sach, "SELECT count(*) FROM ctl.load") == 1


def test_nap_lai_cung_nam_ghi_de_theo_thang(admin, sach):
    """QT-09, QT-15: nạp lại đúng tệp đó thì báo giống hệt, mọi tháng Ghi đè, số
    dòng không đổi."""
    lan1 = _nap(admin)["load_id"]
    ma = tai_len(admin, can_tep_mau()).json()["pending_id"]
    d = admin("GET", f"/uploads/{ma}").json()
    assert d["identical"]["load_id"] == lan1 and d["identical"]["user"] == "admin"
    assert d["overwrite"] == [1, 2, 3, 4, 5, 6, 7] and d["new"] == []
    assert d["by_group"]["rows"][0]["write_mode"] == "Ghi đè"
    assert d["by_group"]["rows"][0]["existing"]["row_count"] == 50
    assert d["by_group"]["rows"][0]["existing"]["load_id"] == lan1
    kq = admin("POST", f"/uploads/{ma}/confirm").json()
    assert kq["status"] == "success"
    assert _gold_nam(sach, "fact_ket_qua_kd", 2026) == 348
    the = admin("GET", f"/loads/{kq['load_id']}/reconcile?card=before_after").json()["cards"][0]
    assert the["rows"][0]["cells"][2:] == ["50 / 1.000", "50 / 1.000", "Ghi đè"]
    assert the["rows"][7]["verdict"] == "Giữ nguyên"


def test_nam_khac_la_ky_khac(admin, sach):
    """QT-02: tháng 1/2026 và tháng 1/2027 là hai kỳ khác nhau."""
    _nap(admin, "2026")
    ma = tai_len(admin, can_tep_mau(), nam="2027").json()["pending_id"]
    d = admin("GET", f"/uploads/{ma}").json()
    assert d["new"] == [1, 2, 3, 4, 5, 6, 7] and d["identical"] is None
    assert admin("POST", f"/uploads/{ma}/confirm").json()["status"] == "success"
    assert _gold_nam(sach, "fact_ket_qua_kd", 2026) == 348
    assert _gold_nam(sach, "fact_ket_qua_kd", 2027) == 348


def test_tep_sai_cau_truc_bi_tu_choi(admin, sach, tmp_path):
    so = openpyxl.load_workbook(can_tep_mau())
    del so["DANH MỤC CHI PHÍ"]
    tep = tmp_path / "thieu-sheet.xlsx"
    so.save(tep)
    r = tai_len(admin, tep)
    assert r.status_code == 200
    kq = r.json()
    assert kq["status"] == "rejected"
    ct = admin("GET", f"/loads/{kq['load_id']}").json()
    assert ct["status"] == "rejected" and ct["total_rows"] == 0
    assert ct["errors"] == [{"sheet": "DANH MỤC CHI PHÍ", "location": "Toàn bộ sheet",
                             "issue": "Thiếu sheet “DANH MỤC CHI PHÍ”",
                             "resolution": "Bổ sung sheet đúng tên như trong bộ bảng"}]
    assert [b["status"] for b in ct["steps"]] == ["ok", "err"] + ["skip"] * 8
    assert dem(sach, "SELECT count(*) FROM bronze.fact_ket_qua_kd") == 0
    # Tệp đã tải lên được lưu để xem lại (CN-22).
    assert admin("GET", f"/loads/{kq['load_id']}/file").status_code == 200


def test_lech_doi_chieu_huy_ca_lan_nap(admin, sach, monkeypatch):
    """NT-12: giả lập lệch ở bước ghi — huỷ cả lần, trạng thái Lỗi đối chiếu, dữ
    liệu cũ giữ nguyên."""
    _nap(admin)
    truoc = _gold_nam(sach, "fact_ket_qua_kd", 2026)
    monkeypatch.setattr(reconcile, "reconcile_bronze_to_silver", lambda *a: False)
    kq = _nap(admin)
    assert kq["status"] == "mismatch"
    assert _gold_nam(sach, "fact_ket_qua_kd", 2026) == truoc == 348
    assert dem(sach, "SELECT count(*) FROM ctl.batch") == 1
    ct = admin("GET", f"/loads/{kq['load_id']}").json()
    buoc = {b["code"]: b for b in ct["steps"]}
    assert buoc["B1"]["verdict"] == "Khớp"
    assert buoc["B2"]["verdict"] == "Lệch" and buoc["B2"]["status"] == "err"
    assert buoc["B3"]["verdict"] == "Đã huỷ"
    assert buoc["B3"]["result"] == "Bị huỷ cùng cả lần ghi vì bước trước lệch."
    assert buoc["B5"]["result"] == ("Không có dòng nào của lần nạp này được lưu. Dữ liệu "
                                     "trước lần nạp giữ nguyên.")
    assert not ct["is_active"] and not ct["can_rollback"]
    the = admin("GET", f"/loads/{kq['load_id']}/reconcile?card=before_after").json()["cards"][0]
    assert the["message"] == ("Lần nạp bị huỷ nên mọi tháng trong database giữ nguyên "
                                "như trước lần nạp.")
