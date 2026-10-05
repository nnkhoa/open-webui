"""Xem tệp gốc (B11, MH-22): danh sách sheet kể cả ẩn, dòng ẩn, theo trang."""

from __future__ import annotations

from open_webui.data_portal.sources import source_file
from .conftest import can_tep_mau


def test_danh_sach_sheet_hqkd():
    sheet = source_file.list_sheets(can_tep_mau())
    assert [(s["so"], s["ten"], s["so_dong"], s["an"]) for s in sheet] == [
        (1, "TỔNG HỢP", 524, False),
        (2, "DANH SACH KHACH HANG THEO HDX", 232, False),
        (3, "DANH MỤC CHI PHÍ", 27, False),
    ]


def test_noi_dung_theo_trang_va_dong_an():
    tep = can_tep_mau()
    trang1 = source_file.sheet_page(tep, 1, 1, 50)
    assert trang1["tong"] == 524 and trang1["cot"][0] == "A"
    assert [d["rn"] for d in trang1["dong"]] == list(range(1, 51))
    assert len(trang1["dong"][0]["o"]) == len(trang1["cot"])
    trang_cuoi = source_file.sheet_page(tep, 1, 11, 50)
    assert [d["rn"] for d in trang_cuoi["dong"]] == list(range(501, 525))
    an = [d for p in range(1, 12) for d in source_file.sheet_page(tep, 1, p, 50)["dong"] if d["an"]]
    assert len(an) == trang1["so_dong_an"] == 121
    assert source_file.sheet_page(tep, 9, 1, 50) is None


def test_dinh_dang_so():
    assert source_file._format_number(1234567.891, "#,##0.00") == "1.234.567,89"
    assert source_file._format_number(0.304, "0.00%") == "30,40%"
    assert source_file._format_number(108541, "General") == "108541"
    assert source_file._format_number(-5, "#,##0") == "-5"
