"""Xem tệp gốc đã tải lên (CN-22, MH-22) — từng sheet kiểu Excel, kể cả sheet và
dòng đang ẩn.

Đọc bằng openpyxl ở chế độ đầy đủ (không `read_only`) vì chỉ chế độ đó cho biết
dòng nào đang bị ẩn. Giá trị lấy kết quả công thức đã lưu trong tệp và hiện như
ô Excel hiện: số theo định dạng ô, ngày `DD/MM/YYYY` (mục 12.14). Dấu phân cách
theo quy ước 13.3: chấm phân cách nghìn, phẩy thập phân.

Tệp gốc không đổi sau khi tải lên, nên lưới đã dựng được giữ lại trong bộ nhớ
cho vài tệp gần nhất — lật trang không phải mở lại tệp.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time
from functools import lru_cache
from pathlib import Path

from .xlsx import mo_so, o_trong

_SO_LE = re.compile(r"\.(0+)")


@dataclass(frozen=True)
class SheetGoc:
    ten: str
    an: bool
    luoi: tuple[tuple[str | None, ...], ...]   # tới dòng cuối có dữ liệu
    dong_an: frozenset[int]                     # số dòng Excel đang bị ẩn
    so_cot: int


def _nhom_nghin(nguyen: str) -> str:
    am = nguyen.startswith("-")
    so = nguyen.lstrip("-")
    nhom = []
    while len(so) > 3:
        nhom.insert(0, so[-3:])
        so = so[:-3]
    nhom.insert(0, so)
    return ("-" if am else "") + ".".join(nhom)


def _so(gia_tri: float | int, dinh_dang: str) -> str:
    """Số theo định dạng ô: số chữ số lẻ, phân cách nghìn, phần trăm."""
    dd = (dinh_dang or "General").split(";")[0]
    phan_tram = "%" in dd
    if phan_tram:
        gia_tri = gia_tri * 100
    if dd == "General":
        if isinstance(gia_tri, int) or float(gia_tri).is_integer():
            return str(int(gia_tri))
        return repr(float(gia_tri)).replace(".", ",")
    le = _SO_LE.search(dd)
    so_le = len(le.group(1)) if le else 0
    chuoi = f"{gia_tri:.{so_le}f}"
    nguyen, _, phan = chuoi.partition(".")
    if "," in dd.split(".")[0]:
        nguyen = _nhom_nghin(nguyen)
    ra = nguyen + ("," + phan if phan else "")
    return ra + ("%" if phan_tram else "")


def hien_thi(o) -> str | None:
    """Giá trị một ô như Excel hiện."""
    v = o.value
    if o_trong(v):
        return None
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, datetime):
        if v.time() == time():
            return v.strftime("%d/%m/%Y")
        return v.strftime("%d/%m/%Y %H:%M")
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, (int, float)):
        return _so(v, o.number_format)
    return str(v)


@lru_cache(maxsize=4)
def _doc(duong_dan: str, _mtime: float) -> tuple[SheetGoc, ...]:
    so = mo_so(Path(duong_dan), data_only=True)
    try:
        ra = []
        for ws in so.worksheets:
            # Duyệt các ô **có trong tệp** (`_cells`), không duyệt cả lưới: sheet có
            # định dạng tới cột XFD sẽ thành hàng chục triệu ô trống.
            o_co: dict[tuple[int, int], str] = {}
            for (so_dong, so_cot), o in ws._cells.items():
                gia_tri = hien_thi(o)
                if gia_tri is not None:
                    o_co[(so_dong, so_cot)] = gia_tri
            dong_cuoi = max((d for d, _ in o_co), default=0)
            so_cot = max((c for _, c in o_co), default=0)
            luoi = tuple(tuple(o_co.get((d, c)) for c in range(1, so_cot + 1))
                         for d in range(1, dong_cuoi + 1))
            dong_an = frozenset(
                so_dong for so_dong, kt in ws.row_dimensions.items()
                if kt.hidden and so_dong <= dong_cuoi)
            ra.append(SheetGoc(ten=ws.title, an=ws.sheet_state != "visible",
                               luoi=luoi, dong_an=dong_an, so_cot=so_cot))
        return tuple(ra)
    finally:
        so.close()


def doc(duong_dan: Path) -> tuple[SheetGoc, ...]:
    return _doc(str(duong_dan), duong_dan.stat().st_mtime)


def chu_cot(chi_so: int) -> str:
    chu = ""
    while chi_so > 0:
        chi_so, du = divmod(chi_so - 1, 26)
        chu = chr(65 + du) + chu
    return chu


def cac_sheet(duong_dan: Path) -> list[dict]:
    """Danh sách sheet: số thứ tự (từ 1), tên, số dòng, ẩn / hiện, số dòng ẩn."""
    return [{"so": i, "ten": s.ten, "so_dong": len(s.luoi), "an": s.an,
             "so_dong_an": len(s.dong_an)}
            for i, s in enumerate(doc(duong_dan), start=1)]


def noi_dung(duong_dan: Path, so: int, trang: int, moi: int) -> dict | None:
    """Một trang của sheet thứ `so`; None nếu không có sheet đó."""
    cac = doc(duong_dan)
    if not 1 <= so <= len(cac):
        return None
    s = cac[so - 1]
    tu = (trang - 1) * moi
    return {
        "so": so, "ten": s.ten, "an": s.an,
        "cot": [chu_cot(i) for i in range(1, s.so_cot + 1)],
        "tong": len(s.luoi),
        "so_dong_an": len(s.dong_an),
        "dong": [{"rn": tu + i, "o": list(h), "an": (tu + i) in s.dong_an}
                 for i, h in enumerate(s.luoi[tu:tu + moi], start=1)],
    }
