"""Mã băm của tệp và của từng dòng.

Mã băm tệp lưu vào `ctl.upload` để truy vết. Mã băm dòng là căn cứ để lớp chuẩn
hoá biết một dòng có y hệt bản hiện hành hay không.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def bam_tep(path: Path, khoi: int = 1 << 20) -> tuple[str, int]:
    """Tính sha256 **trong lúc đọc theo khối**, không nạp cả tệp vào bộ nhớ."""
    h = hashlib.sha256()
    so_byte = 0
    with path.open("rb") as f:
        while True:
            mau = f.read(khoi)
            if not mau:
                break
            h.update(mau)
            so_byte += len(mau)
    return h.hexdigest(), so_byte


def bam_dong(sheet: str, gia_tri: dict[str, str | None], cot: list[str]) -> str:
    """Mã băm nội dung nghiệp vụ của một dòng, không tính cột truy vết.

    Thứ tự cột lấy theo khai báo bộ bảng nên ổn định giữa các lần nạp.
    """
    h = hashlib.sha256()
    h.update(sheet.encode("utf-8"))
    for ten in cot:
        v = gia_tri.get(ten)
        # Ô trống và ô chứa chuỗi rỗng là hai thứ khác nhau, nên đánh dấu khác
        # nhau: mã băm là căn cứ để nói "dòng này y hệt bản hiện hành", không
        # được phép coi hai nội dung khác nhau là một.
        if v is None:
            h.update(b"\x1e")
        else:
            h.update(b"\x1f")
            h.update(str(v).encode("utf-8"))
    return h.hexdigest()
