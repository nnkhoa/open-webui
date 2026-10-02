"""Mã lỗi làm tệp bị từ chối: câu nói với người dùng và cách sửa.

Một chỗ duy nhất giữ ba thứ — mã, câu hiển thị, hướng dẫn sửa — nên màn Kết
quả xử lý, màn Chi tiết lần nạp và tệp CSV danh sách lỗi không thể nói khác
nhau về cùng một lỗi. Portal nạp hết hoặc không nạp gì: mọi mã ở đây đều làm
cả tệp bị từ chối, không có mức cảnh báo.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MaLoi:
    ma: str
    mau_cau: str
    cach_xu_ly: str

    def cau(self, **truong) -> str:
        try:
            return self.mau_cau.format(**truong)
        except KeyError:
            return self.mau_cau


BANG_MA: dict[str, MaLoi] = {m.ma: m for m in [
    # -- tên sheet, tên cột ------------------------------------------------- #
    MaLoi("MISSING_SHEET", "Thiếu sheet “{ten}”",
          "Bổ sung sheet đúng tên như trong bộ bảng"),
    MaLoi("UNKNOWN_SHEET", "Sheet “{ten}” không thuộc bộ bảng",
          "Xoá sheet trước khi nạp lại"),
    MaLoi("MISSING_COLUMN", "Thiếu cột “{ten}”",
          "Bổ sung đúng tên cột ở dòng tiêu đề"),
    MaLoi("UNKNOWN_COLUMN", "Có cột ngoài bộ bảng “{ten}”",
          "Xoá cột hoặc chuyển nội dung ra khỏi tệp nạp"),
    MaLoi("DUPLICATE_COLUMN", "Tên cột “{ten}” bị lặp",
          "Đổi tên hoặc xoá cột thừa"),
    MaLoi("DATA_IN_UNNAMED_COLUMN", "Ô có dữ liệu ở cột không có tên cột",
          "Đặt tên cột hoặc xoá dữ liệu thừa"),
    # -- nhận sheet theo dòng tiêu đề (HQ-MAU-GC, QT-16) ---------------------- #
    MaLoi("NO_DATA_SHEET", "Không có sheet đang hiện nào có đủ {n} cột của {loai}: {cot}",
          "Chọn đúng Loại tệp, hoặc sửa dòng tiêu đề đúng tên cột"),
    MaLoi("MANY_DATA_SHEETS",
          "Có {so} sheet đang hiện cùng có đủ {n} cột của {loai}: {cac_sheet}",
          "Chỉ để một sheet đang hiện có đủ các cột này, ẩn hoặc xoá các sheet còn lại"),

    # -- giá trị theo khai báo bộ bảng --------------------------------------- #
    MaLoi("MISSING_REQUIRED", "Thiếu giá trị bắt buộc ở cột “{ten}”",
          "Điền giá trị cho cột này ở mọi dòng"),
    MaLoi("BK_DUPLICATE_IN_BATCH", "Có {n} dòng trùng định danh",
          "Gộp hoặc phân biệt các dòng trùng"),
]}


def ma(code: str) -> MaLoi:
    return BANG_MA.get(code) or MaLoi(code, code, "")
