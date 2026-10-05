"""Kiểm tra cấu trúc tệp.

Kiểm soát duy nhất trước khi ghi một dòng nào: tên sheet, tên cột. Sai thì **từ
chối cả tệp, không ghi dòng nào** — đúng thông điệp P04-B "Không có
dữ liệu nào được cập nhật".

Cột nhận theo **tên**, không theo vị trí, chuẩn hoá NFC, không phân biệt hoa
thường. Giá trị từng ô không kiểm tra ở đây; đó là việc của `validate.py`.
"""

from __future__ import annotations

from ..registry.schema import Form
from ..sources.base import chuan_ten
from .ma_loi import ma


def dong_loi(sheet: str | None, vi_tri: str, code: str, **truong) -> dict:
    """Một dòng của bảng "Lỗi cần sửa": Sheet · Vị trí · Vấn đề · Cách xử lý."""
    return {
        "sheet": sheet,
        "position": vi_tri,
        "issue": ma(code).cau(**truong),
        "reason_code": code,
        "fix": ma(code).cach_xu_ly,
        "cell_ref": truong.get("cell_ref"),
    }


def kiem_tra(reader, form: Form) -> list[dict]:
    """Trả danh sách lỗi cấu trúc. Rỗng nghĩa là tệp qua được bước này."""
    # Bộ đọc không tách được tệp (thiếu sheet, thiếu cột) ⇒ chỉ nêu lỗi đó, các
    # kiểm tra dưới đây chạy trên bảng rỗng không nói thêm được gì.
    loi_nguon = reader.loi_nguon()
    if loi_nguon:
        return [dong_loi(x.sheet, x.vi_tri, x.code, **x.truong) for x in loi_nguon]

    loi: list[dict] = []
    policy = form.policy

    theo_sheet = {chuan_ten(t.sheet): t for t in form.tables}
    co_trong_tep = {chuan_ten(s): s for s in reader.sheets()}

    # Sheet ngoài khai báo.
    if policy.unknown_sheet == "reject":
        for khoa, ten_that in co_trong_tep.items():
            if khoa not in theo_sheet:
                loi.append(dong_loi(ten_that, "Toàn bộ sheet", "UNKNOWN_SHEET", ten=ten_that,
                                cell_ref=ten_that))

    # Thiếu sheet đã khai.
    for table in form.tables:
        if chuan_ten(table.sheet) not in co_trong_tep:
            if policy.missing_column == "reject":
                loi.append(dong_loi(table.label, "Toàn bộ sheet", "MISSING_SHEET",
                                    ten=table.sheet))
            continue
        loi += _kiem_tra_sheet(reader, form, table)
    return loi


def _kiem_tra_sheet(reader, form: Form, table) -> list[dict]:
    loi: list[dict] = []
    policy = form.policy
    vi_tri, khong_ten, lap = reader.vi_tri_cot(table.sheet)

    # Cột `nam` và cột để trống không có trong tệp nên không đòi ở dòng tiêu đề.
    can = {chuan_ten(c.file_header): c.file_header for c in table.file_columns}

    for ten in lap:
        loi.append(dong_loi(table.label, "Dòng 1", "DUPLICATE_COLUMN", ten=ten))

    if policy.missing_column == "reject":
        for khoa, ten in can.items():
            if khoa not in vi_tri:
                loi.append(dong_loi(table.label, "Dòng 1", "MISSING_COLUMN", ten=ten,
                                cell_ref=f"{table.sheet}!1:1"))

    if policy.unknown_column == "reject":
        for khoa, chi_so in vi_tri.items():
            if khoa not in can:
                that = reader.header(table.sheet)[chi_so - 1]
                loi.append(dong_loi(table.label, f"Cột {_chu_cot(chi_so)}", "UNKNOWN_COLUMN",
                                ten=that, cell_ref=f"{table.sheet}!{_chu_cot(chi_so)}1"))

    # Ô có dữ liệu ở cột không có tên cột — chỉ kiểm khi đã không còn lỗi tên cột,
    # để không đổ một loạt lỗi phụ lên người dùng khi nguyên nhân là thiếu tiêu đề.
    if not loi and khong_ten:
        for so_dong, chu in reader.o_co_du_lieu_ngoai_cot(table.sheet, khong_ten):
            loi.append(dong_loi(table.label, f"Dòng {so_dong}, cột {chu}",
                            "DATA_IN_UNNAMED_COLUMN",
                            cell_ref=f"{table.sheet}!{chu}{so_dong}"))
    return loi


def _chu_cot(chi_so: int) -> str:
    chu = ""
    while chi_so > 0:
        chi_so, du = divmod(chi_so - 1, 26)
        chu = chr(65 + du) + chu
    return chu
