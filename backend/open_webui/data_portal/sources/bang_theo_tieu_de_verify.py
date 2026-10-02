"""Đường đọc **độc lập** của tệp HQ-MAU-GC — chỉ cho đối chiếu R1.

Đọc XML qua `XlsxDocLai`, không qua openpyxl, không qua `bang_theo_tieu_de.py`;
chỉ dùng chung khai báo bộ bảng. Dựng lại đúng quy tắc: sheet đang hiện có đủ cột
ở dòng tiêu đề, dữ liệu từ dòng tiêu đề + `dong_du_lieu` tới trước dòng trống
đầu tiên, bỏ dòng tổng. Chỗ nào hai đường hiểu tệp khác nhau thì R1 lệch và cả
lần nạp bị huỷ.
"""

from __future__ import annotations

from pathlib import Path

from .base import chuan_ten
from .xlsx_verify import XlsxDocLai

TIM_TIEU_DE_TRONG = 30
DAU_DONG_TONG = ("total", "tổng cộng")


class BangTheoTieuDeDocLai:
    """Cùng hình dạng `doc_sheet` để `reconcile.r1` dùng."""

    def __init__(self, path: Path, form) -> None:
        table = form.tables[0]
        can = list(dict.fromkeys(c.tieu_de for c in table.cot_tu_tep))
        khoa = {chuan_ten(c) for c in can}
        self._tieu_de: dict[int, str] = {}
        self._hang: dict[int, dict[int, str]] = {}
        doc = XlsxDocLai(path)
        try:
            for ten_sheet in doc.cac_sheet_hien():
                luoi = doc.luoi(ten_sheet)
                for so in sorted(r for r in luoi if r <= TIM_TIEU_DE_TRONG):
                    theo_ten: dict[str, int] = {}
                    for c in sorted(luoi[so]):
                        theo_ten.setdefault(chuan_ten(luoi[so][c]), c)
                    if khoa <= set(theo_ten):
                        self._dung(luoi, so, {theo_ten[chuan_ten(c)]: c for c in can},
                                   int(form.source_opts.get("dong_du_lieu", 1)))
                        return
        finally:
            doc.close()

    def _dung(self, luoi, dong_td: int, cot: dict[int, str], lech: int) -> None:
        self._tieu_de = cot
        so = dong_td + lech
        while so in luoi:
            o = {c: luoi[so][c] for c in cot if c in luoi[so]}
            tong = any(chuan_ten(v).startswith(DAU_DONG_TONG) for v in o.values())
            if o and not tong:
                self._hang[so] = o
            so += 1

    def close(self) -> None:
        return None

    def doc_sheet(self, ten_sheet: str
                  ) -> tuple[dict[int, str], dict[int, dict[int, str | None]]]:
        return dict(self._tieu_de), dict(self._hang)
