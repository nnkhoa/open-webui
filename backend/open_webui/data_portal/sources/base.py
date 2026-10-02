"""Giao diện bộ đọc nguồn dữ liệu.

Thêm nguồn mới (csv, API…) = thêm một lớp con và gắn `@register`. Đường xử lý
không biết tệp đến từ đâu, chỉ biết ba việc: có sheet nào, dòng tiêu đề gì,
các dòng dữ liệu là gì.

Mọi giá trị trả về đều là **văn bản hoặc None**, đúng như ô trong nguồn — không
sửa, không suy đoán, không làm tròn ở lớp này.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Protocol

from ..errors import NguonDuLieuError


@dataclass(frozen=True)
class SourceRow:
    number: int                       # số dòng thật trong nguồn (dòng Excel)
    values: dict[str, str | None]     # theo tên cột đã khai, không theo vị trí


@dataclass(frozen=True)
class LoiNguon:
    """Thiếu sheet hoặc thiếu cột khi bộ đọc tách tệp — từ chối cả tệp.

    `code` là mã ở `pipeline/ma_loi.py`; `truong` điền vào câu của mã đó.
    """

    sheet: str
    vi_tri: str
    code: str
    truong: dict[str, str]


class SourceReader(Protocol):
    kind: ClassVar[str]
    yeu_cau: ClassVar[tuple[str, ...]]  # thẻ "Yêu cầu đối với tệp"; rỗng = mặc định

    def sheets(self) -> list[str]: ...

    def header(self, sheet: str) -> list[str | None]: ...

    # `anh_xa` là `{tên kỹ thuật: tên cột trong tệp}` — xem `xlsx.XlsxReader.rows`.
    def rows(self, sheet: str, anh_xa: dict[str, str]) -> Iterator[SourceRow]: ...

    def loi_nguon(self) -> list[LoiNguon]: ...

    def close(self) -> None: ...


READERS: dict[str, type] = {}


def register(cls):
    READERS[cls.kind] = cls
    return cls


def mo(kind: str, path: Path, header_row: int = 1, form=None) -> SourceReader:
    """Mở bộ đọc của dạng nguồn `kind`. `form` là khai báo bộ bảng — bộ đọc cần
    biết cột nào phải có (bộ đọc theo dòng tiêu đề của HQ-MAU-GC)."""
    cls = READERS.get(kind)
    if cls is None:
        raise NguonDuLieuError(
            f"Chưa có bộ đọc cho nguồn {kind!r}. Các nguồn có sẵn: "
            f"{', '.join(sorted(READERS))}."
        )
    return cls(path, header_row, form)


def yeu_cau(kind: str) -> tuple[str, ...]:
    """Thẻ "Yêu cầu đối với tệp" riêng của dạng nguồn; rỗng thì dùng câu mặc định."""
    cls = READERS.get(kind)
    return cls.yeu_cau if cls else ()


def chuan_ten(value) -> str:
    """So tên sheet và tên cột: chuẩn hoá NFC, bỏ khoảng trắng thừa, không phân
    biệt hoa thường."""
    return " ".join(unicodedata.normalize("NFC", str(value or "")).split()).lower()
