"""Bộ đọc tệp NBC nhận sheet **theo dòng tiêu đề cột** — HQ-MAU-GC (QT-16).

Tên sheet đổi theo ngày ("30 Sep - OK", "Final 09.4"), nên không tìm sheet theo
tên: chọn sheet **đang hiện** có đủ các cột cần lấy ở một dòng tiêu đề trong 30
dòng đầu. Phải đúng một sheet như vậy — không có, hoặc có hơn một, là lỗi làm cả
tệp bị từ chối (QT-06; chọn nhầm loại tệp rơi vào lỗi này).

Dữ liệu:

    · bắt đầu sau dòng tiêu đề `dong_du_lieu` dòng (khai ở bộ bảng: Lịch may mẫu
      có dòng tiêu đề tiếng Anh và một dòng trống nên là 3, Đơn gia công là 1);
    · tới dòng trước dòng trống đầu tiên;
    · **đọc cả dòng đang ẩn** (bộ lọc Excel), bỏ dòng tổng ("TOTAL", "TỔNG CỘNG").

So tên cột sau khi bỏ xuống dòng và khoảng trắng thừa (`chuan_ten`). Cột có
trong tệp mà bộ bảng không khai thì không đọc (QT-21). Giá trị là văn bản y như
ô — lấy kết quả công thức đã lưu, không tự tính lại.

Bộ đọc còn ghi lại những thứ chỉ có trong tệp để đối chiếu: ô tổng (P1, P10),
ngày của bản ("DATE : 30 Sep 2026"), số dòng dữ liệu đang bị ẩn.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

from .base import LoiNguon, SourceRow, chuan_ten, register
from .xlsx import mo_so, o_thanh_van_ban, o_trong

KIND = "bang_theo_tieu_de"
TIM_TIEU_DE_TRONG = 30
DAU_DONG_TONG = ("total", "tổng cộng")
_O = re.compile(r"^([A-Z]+)(\d+)$")
_THANG = {t: i for i, t in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul",
                                      "aug", "sep", "oct", "nov", "dec"), start=1)}
_NGAY_BAN = re.compile(r"(\d{1,2})\s*[-/ ]\s*([A-Za-z]{3})[A-Za-z]*\.?\s*[-/ ]?\s*(\d{4})")


def chi_so_cot(chu: str) -> int:
    n = 0
    for ky_tu in chu:
        n = n * 26 + (ord(ky_tu) - 64)
    return n


def la_dong_tong(gia_tri: list[str | None]) -> bool:
    """Dòng cộng tổng ("TOTAL :", "TỔNG CỘNG …") — không phải dữ liệu."""
    return any(v is not None and chuan_ten(v).startswith(DAU_DONG_TONG) for v in gia_tri)


def doc_ngay_ban(gia_tri) -> str | None:
    """"DATE : 30 Sep 2026" → "30/09/2026" (ngày của bản theo dõi, bước B5)."""
    if isinstance(gia_tri, (datetime, date)):
        return gia_tri.strftime("%d/%m/%Y")
    khop = _NGAY_BAN.search(str(gia_tri or ""))
    if not khop or khop.group(2).lower()[:3] not in _THANG:
        return None
    try:
        ngay = date(int(khop.group(3)), _THANG[khop.group(2).lower()[:3]], int(khop.group(1)))
    except ValueError:
        return None
    return ngay.strftime("%d/%m/%Y")


def don_vi(tieu_de: str | None) -> str | None:
    """Phần trong ngoặc của tiêu đề cột: "GIÁ TIỀN\\n(USD)" → "USD"."""
    khop = re.search(r"\(([^()]+)\)\s*$", " ".join(str(tieu_de or "").split()))
    return khop.group(1).strip() if khop else None


@register
class BangTheoTieuDeReader:
    kind = KIND
    yeu_cau = ()

    def __init__(self, path: Path, header_row: int = 1, form=None) -> None:
        if form is None or len(form.tables) != 1:
            raise ValueError("Bộ đọc theo dòng tiêu đề cần đúng một bảng trong bộ bảng.")
        self.path = path
        self._form = form
        self._table = form.tables[0]
        self._opts = form.source_opts
        self._can = list(dict.fromkeys(c.tieu_de for c in self._table.cot_tu_tep))
        # Thứ tự cột như trong tệp (khai ở bộ bảng) cho câu báo lỗi; mặc định theo cột.
        thu_tu = [c for c in self._opts.get("cot_can", []) if c in self._can]
        self._cot_bao_loi = thu_tu + [c for c in self._can if c not in thu_tu]
        self._loi: list[LoiNguon] = []
        self._hang: list[SourceRow] = []
        self._tieu_de: dict[str, tuple[int, str]] = {}   # chuan_ten → (cột, chữ gốc)
        self.thong_tin: dict = {}
        so = mo_so(path, data_only=True)
        try:
            self._doc(so)
        finally:
            so.close()

    # -- giao diện bộ đọc ---------------------------------------------------- #

    def close(self) -> None:
        return None

    def loi_nguon(self) -> list[LoiNguon]:
        return list(self._loi)

    def sheets(self) -> list[str]:
        return [self._table.sheet]

    def header(self, sheet: str) -> list[str | None]:
        return list(self._can)

    def vi_tri_cot(self, sheet: str) -> tuple[dict[str, int], list[int], list[str]]:
        return ({chuan_ten(c): i for i, c in enumerate(self._can, start=1)}, [], [])

    def o_co_du_lieu_ngoai_cot(self, sheet: str, khong_ten: list[int]) -> list[tuple[int, str]]:
        return []

    def rows(self, sheet: str, anh_xa: dict[str, str]) -> Iterator[SourceRow]:
        theo_tieu_de = {chuan_ten(c): c for c in self._can}
        for dong in self._hang:
            yield SourceRow(dong.number, {ten: dong.values.get(theo_tieu_de.get(chuan_ten(td)))
                                          for ten, td in anh_xa.items()})

    def sheet_goc(self, sheet: str) -> str:
        return self.thong_tin.get("sheet", "")

    def gia_tri_tieu_de(self, tieu_de: str) -> str | None:
        """Đơn vị ghi trong tiêu đề cột (cột `lay_tu: tieu_de`)."""
        muc = self._tieu_de.get(chuan_ten(tieu_de))
        return don_vi(muc[1]) if muc else None

    # -- đọc tệp ------------------------------------------------------------- #

    def _doc(self, so) -> None:
        can = {chuan_ten(c) for c in self._can}
        ung_vien = []
        for ws in so.worksheets:
            if ws.sheet_state != "visible":
                continue
            # Chỉ các ô có trong tệp — sheet định dạng tới cột XFD không thành lưới khổng lồ.
            luoi: dict[int, dict[int, object]] = {}
            for (r, c), o in ws._cells.items():
                if not o_trong(o.value):
                    luoi.setdefault(r, {})[c] = o.value
            for r in range(1, TIM_TIEU_DE_TRONG + 1):
                ten = {}
                lap = set()
                for c, v in sorted(luoi.get(r, {}).items()):
                    if isinstance(v, str):
                        k = chuan_ten(v)
                        if k in ten and k in can:
                            lap.add(v)
                        ten.setdefault(k, (c, v))
                if can <= set(ten):
                    ung_vien.append((ws, r, ten, lap, luoi))
                    break

        loai = self._form.label
        cot = ", ".join(" ".join(c.split()) for c in self._cot_bao_loi)
        if not ung_vien:
            self._loi.append(LoiNguon("Cả tệp", "Dòng tiêu đề", "NO_DATA_SHEET", {
                "n": str(len(self._can)), "loai": loai, "cot": cot}))
            return
        if len(ung_vien) > 1:
            self._loi.append(LoiNguon("Cả tệp", "Dòng tiêu đề", "MANY_DATA_SHEETS", {
                "so": str(len(ung_vien)), "n": str(len(self._can)), "loai": loai,
                "cac_sheet": ", ".join(u[0].title.strip() for u in ung_vien)}))
            return
        ws, dong_td, ten, lap, luoi = ung_vien[0]
        for v in sorted(lap):
            self._loi.append(LoiNguon(ws.title.strip(), f"Dòng {dong_td}", "DUPLICATE_COLUMN",
                                      {"ten": " ".join(v.split())}))
        if self._loi:
            return
        self._tieu_de = ten
        cot_can = [ten[chuan_ten(c)][0] for c in self._can]

        bat_dau = dong_td + int(self._opts.get("dong_du_lieu", 1))
        an = {r for r, kt in ws.row_dimensions.items() if kt.hidden}
        dong_den = bat_dau - 1
        so_an = 0
        r = bat_dau
        while r in luoi:
            gia_tri = [o_thanh_van_ban(luoi[r].get(c)) for c in cot_can]
            if not la_dong_tong(gia_tri) and any(v is not None for v in gia_tri):
                self._hang.append(SourceRow(r, dict(zip(self._can, gia_tri, strict=True))))
                so_an += r in an
            dong_den = r
            r += 1

        self.thong_tin = {
            "sheet": ws.title, "dong_tieu_de": dong_td, "so_cot_can": len(self._can),
            "dong_tu": bat_dau, "dong_den": dong_den,
            "so_dong_an": so_an, "so_dong_hien": len(self._hang) - so_an,
        }
        o_tong = self._opts.get("o_tong")
        if o_tong:
            khop = _O.match(str(o_tong))
            c, d = chi_so_cot(khop.group(1)), int(khop.group(2))
            self.thong_tin["o_tong"] = {
                "o": o_tong, "gia_tri": o_thanh_van_ban(luoi.get(d, {}).get(c)),
                "tieu_de": " ".join(str(luoi.get(dong_td, {}).get(c) or "").split()),
                "ghi_nhan": bool(self._opts.get("o_tong_ghi_nhan")),
            }
        o_ngay = self._opts.get("o_ngay_ban")
        if o_ngay:
            khop = _O.match(str(o_ngay))
            self.thong_tin["ngay_ban"] = doc_ngay_ban(
                luoi.get(int(khop.group(2)), {}).get(chi_so_cot(khop.group(1))))
