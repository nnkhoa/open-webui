"""Bước Kiểm tra tệp (A1–A3, B4 đặc tả) — chỉ đọc tệp, không cần database."""

from __future__ import annotations

from decimal import Decimal

import openpyxl

from open_webui.data_portal.pipeline import cac_buoc, kiem_tra_tep
from open_webui.data_portal.registry.loader import doc_thu_muc
from .conftest import KHAI_BAO, can_tep_mau

FORM = doc_thu_muc(KHAI_BAO).form("BAO_CAO_HQKH")


def test_tep_nbc_t1_t7_dung_so_cua_dac_ta():
    kt = kiem_tra_tep.kiem_tra(FORM, can_tep_mau(), 2026)
    assert kt["loi"] == [] and kt["buoc_loi"] is None
    assert kt["so_sheet"] == 3
    bang = {b["bang"]: b for b in kt["bang"]}
    assert [b["bang"] for b in kt["bang"]] == [
        "fact_ket_qua_kd", "fact_chi_phi", "dim_khach_hang", "dim_khoan_cp"]
    assert (bang["fact_ket_qua_kd"]["doc"], bang["fact_ket_qua_kd"]["se_ghi"]) == (348, 348)
    assert (bang["fact_chi_phi"]["doc"], bang["fact_chi_phi"]["se_ghi"]) == (6960, 6960)
    assert (bang["dim_khach_hang"]["doc"], bang["dim_khach_hang"]["trung_bo"],
            bang["dim_khach_hang"]["se_ghi"]) == (227, 90, 137)
    assert bang["dim_khoan_cp"]["se_ghi"] == 26
    assert bang["dim_khach_hang"]["sheet"] == "DANH SACH KHACH HANG THEO HDX"
    assert bang["fact_chi_phi"]["sheet"] == "TỔNG HỢP"
    assert round(Decimal(bang["fact_chi_phi"]["tong"]), 2) == Decimal("122689472100.65")
    assert round(Decimal(bang["fact_ket_qua_kd"]["tong"]), 2) == Decimal("3193114446744.50")
    assert bang["dim_khach_hang"]["tong"] is None
    thang = bang["fact_ket_qua_kd"]["theo_ky"]
    assert sorted(thang, key=int) == ["1", "2", "3", "4", "5", "6", "7"]
    assert thang["1"]["so_dong"] == 50 and thang["1"]["so_cot"] == 15
    assert bang["fact_chi_phi"]["theo_ky"]["1"]["so_dong"] == 1000


def test_cau_a3_va_a2_theo_dac_ta():
    kt = kiem_tra_tep.kiem_tra(FORM, can_tep_mau(), 2026)
    buoc = cac_buoc.buoc_a(kt, nguoi="admin", a4=None)
    theo_ma = {b["ma"]: b for b in buoc}
    assert theo_ma["A1"]["ket_qua"] == "Đúng định dạng .xlsx, đọc được 3 sheet."
    assert theo_ma["A2"]["ket_qua"] == (
        "Đủ 3 sheet TỔNG HỢP, DANH SACH KHACH HANG THEO HDX, DANH MỤC CHI PHÍ; "
        "đúng tên cột.")
    assert theo_ma["A3"]["ket_qua"] == (
        "Đọc 7.561 dòng, không thiếu giá trị bắt buộc. 90 dòng trùng ở Danh mục khách "
        "hàng sẽ bỏ (227 → 137). Sẽ ghi 7.471 dòng.")
    assert theo_ma["A5"]["ket_qua"] == "admin đã bấm xác nhận."
    assert [b["ket_luan"] for b in buoc] == ["Đúng", "Đúng", "Hợp lệ", "Xong", "Đã xác nhận"]


def test_thieu_sheet_bi_tu_choi_o_a2(tmp_path):
    so = openpyxl.load_workbook(can_tep_mau())
    del so["DANH MỤC CHI PHÍ"]
    tep = tmp_path / "thieu-sheet.xlsx"
    so.save(tep)
    kt = kiem_tra_tep.kiem_tra(FORM, tep, 2026)
    assert kt["buoc_loi"] == "A2"
    assert [e["reason_code"] for e in kt["loi"]] == ["MISSING_SHEET"]
    buoc = cac_buoc.buoc_a(kt, nguoi="admin", a4=None) + cac_buoc.buoc_b_tu_choi("A2", "B4")
    assert buoc[1]["ket_qua"] == "Có 1 lỗi (thiếu sheet). Cả tệp bị từ chối."
    assert buoc[1]["trang_thai"] == "err"
    assert all(b["ket_luan"] == "Không chạy" for b in buoc[2:])
    assert buoc[2]["ket_qua"] == "Không chạy vì tệp bị từ chối ở bước A2."


def test_bo_doc_theo_dong_tieu_de_hq_mau_gc():
    from open_webui.data_portal.sources import base
    from .conftest import TEP_GIA_CONG, TEP_MAY_MAU

    registry = doc_thu_muc(KHAI_BAO)
    form = registry.form("LICH_MAY_MAU")
    doc = base.mo(form.source_kind, can_tep_mau(TEP_MAY_MAU), 1, form)
    assert doc.loi_nguon() == []
    tt = doc.thong_tin
    assert (tt["sheet"].strip(), tt["dong_tieu_de"], tt["dong_tu"], tt["dong_den"]) == (
        "30 Sep - OK", 11, 14, 1716)
    assert (tt["so_dong_an"], tt["so_dong_hien"]) == (1613, 90)
    assert tt["o_tong"]["gia_tri"] == "141" and tt["ngay_ban"] == "30/09/2026"
    assert doc.gia_tri_tieu_de("GIÁ TIỀN (USD)") == "USD"
    form_gc = registry.form("DON_GIA_CONG")
    doc = base.mo(form_gc.source_kind, can_tep_mau(TEP_GIA_CONG), 1, form_gc)
    assert doc.thong_tin["sheet"] == "Final 09.4"          # sheet ẩn "Fty update" không tính
    assert doc.thong_tin["o_tong"]["gia_tri"] == "108541"


def test_doc_lai_doc_lap_khop_bo_doc_chinh():
    """R1: đường đọc XML độc lập cho đúng các dòng như bộ đọc openpyxl."""
    from open_webui.data_portal.sources import base
    from open_webui.data_portal.sources.bang_theo_tieu_de_verify import BangTheoTieuDeDocLai
    from .conftest import TEP_MAY_MAU

    form = doc_thu_muc(KHAI_BAO).form("LICH_MAY_MAU")
    tep = can_tep_mau(TEP_MAY_MAU)
    chinh = {r.number for r in base.mo(form.source_kind, tep, 1, form).rows(
        "LICH_MAY_MAU", form.tables[0].anh_xa_tieu_de)}
    _, hang = BangTheoTieuDeDocLai(tep, form).doc_sheet("LICH_MAY_MAU")
    assert set(hang) == chinh and len(chinh) == 1703
