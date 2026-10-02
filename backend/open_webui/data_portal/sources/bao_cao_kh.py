"""Bộ đọc báo cáo "HIỆU QUẢ TỪNG KHÁCH HÀNG" — tách báo cáo thành bốn bảng phẳng.

Đường xử lý không biết gì về báo cáo: nó chỉ thấy bốn sheet `KET_QUA_KD`,
`CHI_PHI`, `DM_KHACH_HANG`, `DM_KHOAN_CP`. Bố cục báo cáo khai ở
`bao_cao_kh_mau.py`.

Tách thế nào — lấy đúng thứ có trong tệp, ô trống để trống; hai cột khai cố
định trong `bao_cao_kh_mau.py` (`cap_phan_bo`, `nhom_chi_phi`):

* KET_QUA_KD     mỗi dòng khách hàng của sheet TỔNG HỢP (có THÁNG, và có mã
                 hoặc tên khách hàng; bỏ dòng "TỔNG CỘNG THÁNG …") ra một dòng.
                 `ky_thang` là ô THÁNG, `ten_khach` là ô "Khách hàng" của
                 chính dòng đó.
* CHI_PHI        mỗi dòng khách hàng ra một dòng cho **mỗi cột chi phí**, mã
                 khoản lấy ở dòng mã ngay trên tên cột; `cap_phan_bo` cố định.
* DM_KHACH_HANG  mỗi dòng của sheet DANH SACH KHACH HANG THEO HDX.
* DM_KHOAN_CP    mỗi dòng của sheet DANH MỤC CHI PHÍ, nhóm chi phí gán theo mã.

Giá trị lấy **kết quả công thức Excel đã lưu trong tệp**, không tự tính lại.
Lỗi duy nhất bộ đọc báo ra là thiếu sheet hoặc thiếu cột — khi đó cả tệp bị từ
chối ở bước kiểm tra cấu trúc.

Số dòng của bảng phẳng đánh từ 2 theo thứ tự sinh ra — đúng số dòng nếu bảng
phẳng được ghi ra một sheet Excel có tiêu đề ở dòng 1.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from . import bao_cao_kh_mau as mau
from .base import LoiNguon, SourceRow, chuan_ten, register
from .xlsx import mo_so, o_thanh_van_ban, o_trong


class _Sheet:
    def __init__(self, ws) -> None:
        self.ws = ws
        self.ten = ws.title

    def hang(self, so_dong: int) -> list:
        return [c.value for c in self.ws[so_dong]]

    def dong_cuoi(self) -> int:
        return self.ws.max_row

    def tim_dong(self, *tieu_de: str) -> int | None:
        """Dòng đầu tiên chứa đủ các tiêu đề — dòng tiêu đề của sheet."""
        can = {chuan_ten(t) for t in tieu_de}
        for so in range(1, min(mau.TIM_TIEU_DE_TRONG, self.dong_cuoi()) + 1):
            if can <= {chuan_ten(v) for v in self.hang(so) if not o_trong(v)}:
                return so
        return None


@register
class BaoCaoKhReader:
    kind = mau.KIND
    yeu_cau = (
        "Tệp Excel định dạng .xlsx, đúng mẫu báo cáo hiệu quả từng khách hàng",
        "Có đủ ba sheet TỔNG HỢP, DANH SACH KHACH HANG THEO HDX, DANH MỤC CHI PHÍ",
    )

    def __init__(self, path: Path, header_row: int = 1, form=None) -> None:
        self.path = path
        self._loi: list[LoiNguon] = []
        self._bang: dict[str, list[dict[str, str | None]]] = {
            ten: [] for ten in mau.BANG_PHANG}
        so = mo_so(path, data_only=True)
        try:
            self._doc(so)
        finally:
            so.close()
        if self._loi:
            self._bang = {ten: [] for ten in mau.BANG_PHANG}

    # -- giao diện bộ đọc ---------------------------------------------------- #

    def close(self) -> None:
        return None

    def loi_nguon(self) -> list[LoiNguon]:
        return list(self._loi)

    def sheets(self) -> list[str]:
        return list(mau.BANG_PHANG)

    def header(self, sheet: str) -> list[str | None]:
        return list(mau.BANG_PHANG[self._ten_bang(sheet)])

    def vi_tri_cot(self, sheet: str) -> tuple[dict[str, int], list[int], list[str]]:
        return ({chuan_ten(c): i for i, c in enumerate(self.header(sheet), start=1)}, [], [])

    def o_co_du_lieu_ngoai_cot(self, sheet: str, khong_ten: list[int]) -> list[tuple[int, str]]:
        return []

    def rows(self, sheet: str, anh_xa: dict[str, str]) -> Iterator[SourceRow]:
        """Khoá theo tên kỹ thuật, bỏ dòng trống hoàn toàn."""
        theo_tieu_de = {chuan_ten(c): c for c in self.header(sheet)}
        lay = {ten: theo_tieu_de[chuan_ten(td)] for ten, td in anh_xa.items()
               if chuan_ten(td) in theo_tieu_de}
        for so_dong, dong in enumerate(self._bang[self._ten_bang(sheet)], start=2):
            gia_tri = {ten: dong.get(cot) for ten, cot in lay.items()}
            if any(v is not None for v in gia_tri.values()):
                yield SourceRow(so_dong, gia_tri)

    def sheet_goc(self, sheet: str) -> str:
        """Sheet trong tệp NBC mà bảng phẳng `sheet` được tách ra."""
        return mau.SHEET_GOC[self._ten_bang(sheet)]

    def _ten_bang(self, sheet: str) -> str:
        for ten in mau.BANG_PHANG:
            if chuan_ten(ten) == chuan_ten(sheet):
                return ten
        raise KeyError(sheet)

    # -- tách báo cáo thành bảng phẳng -------------------------------------- #

    def _thieu_cot(self, sheet: str, so_dong: int, ten: str, code: str = "MISSING_COLUMN"):
        self._loi.append(LoiNguon(sheet, f"Dòng {so_dong}", code, {"ten": ten}))

    def _doc(self, so) -> None:
        theo_ten = {chuan_ten(n): n for n in so.sheetnames}
        sheet: dict[str, _Sheet] = {}
        for ten in (mau.SHEET_TONG_HOP, mau.SHEET_DS_KHACH, mau.SHEET_DM_CP):
            that = theo_ten.get(chuan_ten(ten))
            if that is None:
                self._loi.append(LoiNguon(ten, "Toàn bộ sheet", "MISSING_SHEET", {"ten": ten}))
            else:
                sheet[ten] = _Sheet(so[that])
        if self._loi:
            return
        self._doc_tong_hop(sheet[mau.SHEET_TONG_HOP])
        self._doc_danh_muc(sheet[mau.SHEET_DS_KHACH], mau.DM_KHACH_HANG,
                           mau.TD_DS_MA, mau.TD_DS_TEN, ("ma_khach", "ten_khach"))
        self._doc_danh_muc(sheet[mau.SHEET_DM_CP], mau.DM_KHOAN_CP,
                           mau.TD_DM_MA, mau.TD_DM_TEN, ("ma_khoan_cp", "ten_khoan"))
        for dong in self._bang[mau.DM_KHOAN_CP]:
            dong["nhom_chi_phi"] = mau.NHOM_CHI_PHI.get((dong["ma_khoan_cp"] or "").strip())

    def _doc_tong_hop(self, sh: _Sheet) -> None:
        dong_td = sh.tim_dong(mau.TD_THANG, mau.TD_MA_KHACH)
        if dong_td is None:
            self._thieu_cot(sh.ten, 1, mau.TD_THANG)
            return
        tieu_de = [None if o_trong(v) else chuan_ten(v) for v in sh.hang(dong_td)]
        ma = [None if o_trong(v) else str(v).strip()
              for v in (sh.hang(dong_td - 1) if dong_td > 1 else [])]
        nhom = [None if o_trong(v) else str(v).strip()
                for v in (sh.hang(dong_td - 2) if dong_td > 2 else [])]

        def cot_theo_tieu_de(td: str, sau: str | None = None) -> int | None:
            tu = 0
            if sau is not None:
                neo = cot_theo_tieu_de(sau)
                if neo is None:
                    return None
                tu = neo + 1
            khop = [i for i, t in enumerate(tieu_de) if t == chuan_ten(td) and i >= tu]
            if not khop:
                self._thieu_cot(sh.ten, dong_td, td)
                return None
            if sau is None and len(khop) > 1:
                self._thieu_cot(sh.ten, dong_td, td, "DUPLICATE_COLUMN")
                return None
            return khop[0]

        def cot_theo_ma(m: str) -> int | None:
            khop = [i for i, v in enumerate(ma) if v == m]
            if len(khop) != 1:
                self._thieu_cot(sh.ten, dong_td - 1, m,
                                "MISSING_COLUMN" if not khop else "DUPLICATE_COLUMN")
                return None
            return khop[0]

        c_thang = cot_theo_tieu_de(mau.TD_THANG)
        c_nhom_kd = cot_theo_tieu_de(mau.TD_NHOM_KD)
        c_ma_kh = cot_theo_tieu_de(mau.TD_MA_KHACH)
        c_ten_kh = cot_theo_tieu_de(mau.TD_TEN_KHACH)
        kqkd = {ten: cot_theo_ma(m) for ten, m in mau.KQKD_THEO_MA.items()}
        kqkd |= {ten: cot_theo_tieu_de(td, sau)
                 for ten, (td, sau) in mau.KQKD_THEO_TIEU_DE.items()}
        cot_cp = [i for i, n in enumerate(nhom) if n is not None]
        cot_cp += [i for i in (cot_theo_tieu_de(td) for td in mau.CP_NGOAI_NHOM)
                   if i is not None]
        if self._loi:
            return

        def o(hang: list, i: int) -> str | None:
            return o_thanh_van_ban(hang[i]) if i < len(hang) else None

        for so_dong in range(dong_td + 1, sh.dong_cuoi() + 1):
            hang = sh.hang(so_dong)
            if mau.la_dong_danh_dau(hang):
                continue
            thang = o(hang, c_thang)
            if thang is not None and chuan_ten(thang) == chuan_ten(mau.DAU_LUY_KE):
                break
            ma_khach, ten_khach = o(hang, c_ma_kh), o(hang, c_ten_kh)
            if thang is None or (ma_khach is None and ten_khach is None):
                continue
            if mau.la_dong_tong(ma_khach, ten_khach):
                continue
            chung = {"ky_thang": thang, "ma_khach": ma_khach,
                     "ma_nhom_kd": o(hang, c_nhom_kd)}
            self._bang[mau.KET_QUA_KD].append(
                chung | {"ten_khach": ten_khach} | {ten: o(hang, i) for ten, i in kqkd.items()})
            for i in cot_cp:
                self._bang[mau.CHI_PHI].append(chung | {
                    "ma_khoan_cp": ma[i] if i < len(ma) else None,
                    "cap_phan_bo": mau.CAP_PHAN_BO,
                    "so_tien": o(hang, i),
                })

    def _doc_danh_muc(self, sh: _Sheet, bang: str, td_ma: str, td_ten: str,
                      cot: tuple[str, str]) -> None:
        dong_td = sh.tim_dong(td_ma, td_ten)
        if dong_td is None:
            self._thieu_cot(sh.ten, 1, td_ma)
            return
        td = [None if o_trong(v) else chuan_ten(v) for v in sh.hang(dong_td)]
        c_ma, c_ten = td.index(chuan_ten(td_ma)), td.index(chuan_ten(td_ten))
        for so_dong in range(dong_td + 1, sh.dong_cuoi() + 1):
            hang = sh.hang(so_dong)
            if mau.la_dong_danh_dau(hang):
                continue
            gia_tri = [o_thanh_van_ban(hang[i]) if i < len(hang) else None
                       for i in (c_ma, c_ten)]
            if any(v is not None for v in gia_tri):
                self._bang[bang].append(dict(zip(cot, gia_tri, strict=True)))
