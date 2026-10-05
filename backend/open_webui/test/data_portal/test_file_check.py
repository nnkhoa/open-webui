"""Bước Kiểm tra tệp (A1–A3, B4 đặc tả) — chỉ đọc tệp, không cần database."""

from __future__ import annotations

from decimal import Decimal

import openpyxl

from open_webui.data_portal.pipeline import file_check, steps
from open_webui.data_portal.registry.loader import load_definitions
from .conftest import DEFINITIONS_DIR, can_tep_mau

FORM = load_definitions(DEFINITIONS_DIR).form("BAO_CAO_HQKH")


def test_tep_nbc_t1_t7_dung_so_cua_dac_ta():
    kt = file_check.check_file(FORM, can_tep_mau(), 2026)
    assert kt["errors"] == [] and kt["failed_step"] is None
    assert kt["sheet_count"] == 3
    bang = {b["table"]: b for b in kt["tables"]}
    assert [b["table"] for b in kt["tables"]] == [
        "fact_ket_qua_kd", "fact_chi_phi", "dim_khach_hang", "dim_khoan_cp"]
    assert (bang["fact_ket_qua_kd"]["read"], bang["fact_ket_qua_kd"]["to_write"]) == (348, 348)
    assert (bang["fact_chi_phi"]["read"], bang["fact_chi_phi"]["to_write"]) == (6960, 6960)
    assert (bang["dim_khach_hang"]["read"], bang["dim_khach_hang"]["duplicates"],
            bang["dim_khach_hang"]["to_write"]) == (227, 90, 137)
    assert bang["dim_khoan_cp"]["to_write"] == 26
    assert bang["dim_khach_hang"]["sheet"] == "DANH SACH KHACH HANG THEO HDX"
    assert bang["fact_chi_phi"]["sheet"] == "TỔNG HỢP"
    assert round(Decimal(bang["fact_chi_phi"]["total"]), 2) == Decimal("122689472100.65")
    assert round(Decimal(bang["fact_ket_qua_kd"]["total"]), 2) == Decimal("3193114446744.50")
    assert bang["dim_khach_hang"]["total"] is None
    thang = bang["fact_ket_qua_kd"]["by_period"]
    assert sorted(thang, key=int) == ["1", "2", "3", "4", "5", "6", "7"]
    assert thang["1"]["row_count"] == 50 and thang["1"]["column_count"] == 15
    assert bang["fact_chi_phi"]["by_period"]["1"]["row_count"] == 1000


def test_cau_a3_va_a2_theo_dac_ta():
    kt = file_check.check_file(FORM, can_tep_mau(), 2026)
    buoc = steps.check_steps(kt, user="admin", a4_result=None)
    theo_ma = {b["code"]: b for b in buoc}
    assert theo_ma["A1"]["result"] == "Đúng định dạng .xlsx, đọc được 3 sheet."
    assert theo_ma["A2"]["result"] == (
        "Đủ 3 sheet TỔNG HỢP, DANH SACH KHACH HANG THEO HDX, DANH MỤC CHI PHÍ; "
        "đúng tên cột.")
    assert theo_ma["A3"]["result"] == (
        "Đọc 7.561 dòng, không thiếu giá trị bắt buộc. 90 dòng trùng ở Danh mục khách "
        "hàng sẽ bỏ (227 → 137). Sẽ ghi 7.471 dòng.")
    assert theo_ma["A5"]["result"] == "admin đã bấm xác nhận."
    assert [b["verdict"] for b in buoc] == ["Đúng", "Đúng", "Hợp lệ", "Xong", "Đã xác nhận"]


def test_thieu_sheet_bi_tu_choi_o_a2(tmp_path):
    so = openpyxl.load_workbook(can_tep_mau())
    del so["DANH MỤC CHI PHÍ"]
    tep = tmp_path / "thieu-sheet.xlsx"
    so.save(tep)
    kt = file_check.check_file(FORM, tep, 2026)
    assert kt["failed_step"] == "A2"
    assert [e["reason_code"] for e in kt["errors"]] == ["MISSING_SHEET"]
    buoc = steps.check_steps(kt, user="admin", a4_result=None) + steps.rejected_write_steps("A2", "B4")
    assert buoc[1]["result"] == "Có 1 lỗi (thiếu sheet). Cả tệp bị từ chối."
    assert buoc[1]["status"] == "err"
    assert all(b["verdict"] == "Không chạy" for b in buoc[2:])
    assert buoc[2]["result"] == "Không chạy vì tệp bị từ chối ở bước A2."


def test_bo_doc_theo_dong_tieu_de_hq_mau_gc():
    from open_webui.data_portal.sources import base
    from .conftest import TEP_GIA_CONG, TEP_MAY_MAU

    registry = load_definitions(DEFINITIONS_DIR)
    form = registry.form("LICH_MAY_MAU")
    doc = base.open_reader(form.source_kind, can_tep_mau(TEP_MAY_MAU), form)
    assert doc.source_issues() == []
    tt = doc.info
    assert (tt.sheet.strip(), tt.header_row, tt.first_row, tt.last_row) == (
        "30 Sep - OK", 11, 14, 1716)
    assert (tt.hidden_row_count, tt.visible_row_count) == (1613, 90)
    assert tt.total_cell.value == "141" and tt.report_date == "30/09/2026"
    assert doc.header_value("GIÁ TIỀN (USD)") == "USD"
    form_gc = registry.form("DON_GIA_CONG")
    doc = base.open_reader(form_gc.source_kind, can_tep_mau(TEP_GIA_CONG), form_gc)
    assert doc.info.sheet == "Final 09.4"          # sheet ẩn "Fty update" không tính
    assert doc.info.total_cell.value == "108541"


def test_doc_lai_doc_lap_khop_bo_doc_chinh():
    """R1: đường đọc XML độc lập cho đúng các dòng như bộ đọc openpyxl."""
    from open_webui.data_portal.sources import base
    from open_webui.data_portal.sources.header_table_verify import HeaderTableVerifyReader
    from .conftest import TEP_MAY_MAU

    form = load_definitions(DEFINITIONS_DIR).form("LICH_MAY_MAU")
    tep = can_tep_mau(TEP_MAY_MAU)
    chinh = {r.number for r in base.open_reader(form.source_kind, tep, form).rows(
        "LICH_MAY_MAU", form.tables[0].header_map)}
    _, hang = HeaderTableVerifyReader(tep, form).read_table("LICH_MAY_MAU")
    assert set(hang) == chinh and len(chinh) == 1703
