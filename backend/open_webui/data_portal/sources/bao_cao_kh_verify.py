"""Đường đọc **độc lập** của báo cáo hiệu quả từng khách hàng — chỉ cho đối chiếu R1.

Đối chiếu Tệp ↔ Dữ liệu gốc mà dùng lại bộ đã ghi dữ liệu thì chỉ chứng minh bộ
đọc nhất quán với chính nó. Mô-đun này dựng lại bốn bảng phẳng bằng đường khác
hẳn: đọc XML qua `XlsxDocLai`, không qua openpyxl, không qua `bao_cao_kh.py`.
Chỉ dùng chung khai báo bố cục ở `bao_cao_kh_mau.py`.

Không kiểm lỗi: tệp tới được đây thì đã qua `bao_cao_kh.loi_nguon()`. Chỗ nào
hai đường hiểu tệp khác nhau thì R1 lệch và cả lần nạp bị huỷ.
"""

from __future__ import annotations

from pathlib import Path

from . import bao_cao_kh_mau as mau
from .base import chuan_ten
from .xlsx_verify import XlsxDocLai

Luoi = dict[int, dict[int, str]]


def _dong_tieu_de(luoi: Luoi, *tieu_de: str) -> int | None:
    can = {chuan_ten(t) for t in tieu_de}
    for so in sorted(luoi):
        if so > mau.TIM_TIEU_DE_TRONG:
            break
        if can <= {chuan_ten(v) for v in luoi[so].values()}:
            return so
    return None


def _cot(dong: dict[int, str], tieu_de: str, tu: int = 0) -> int | None:
    khop = [c for c, v in dong.items() if chuan_ten(v) == chuan_ten(tieu_de) and c >= tu]
    return min(khop) if khop else None


def _tong_hop(luoi: Luoi) -> tuple[list[dict], list[dict]]:
    dong_td = _dong_tieu_de(luoi, mau.TD_THANG, mau.TD_MA_KHACH)
    if dong_td is None:
        return [], []
    td = luoi[dong_td]
    ma = {c: v.strip() for c, v in luoi.get(dong_td - 1, {}).items()}
    nhom = {c: v.strip() for c, v in luoi.get(dong_td - 2, {}).items()}

    cot_kqkd: dict[str, int | None] = {
        ten: next((c for c, m in ma.items() if m == code), None)
        for ten, code in mau.KQKD_THEO_MA.items()}
    for ten, (tieu_de, sau) in mau.KQKD_THEO_TIEU_DE.items():
        neo = _cot(td, sau) if sau else None
        cot_kqkd[ten] = _cot(td, tieu_de, neo + 1 if neo else 0)
    cot_cp = sorted(nhom) + [_cot(td, t) for t in mau.CP_NGOAI_NHOM]

    c_thang, c_nhom_kd = _cot(td, mau.TD_THANG), _cot(td, mau.TD_NHOM_KD)
    c_ma_kh, c_ten_kh = _cot(td, mau.TD_MA_KHACH), _cot(td, mau.TD_TEN_KHACH)

    kqkd: list[dict] = []
    chi_phi: list[dict] = []
    for so in sorted(r for r in luoi if r > dong_td):
        o = luoi[so]
        if mau.la_dong_danh_dau(list(o.values())):
            continue
        thang = o.get(c_thang)
        if thang is not None and chuan_ten(thang) == chuan_ten(mau.DAU_LUY_KE):
            break
        if thang is None or (o.get(c_ma_kh) is None and o.get(c_ten_kh) is None):
            continue
        if mau.la_dong_tong(o.get(c_ma_kh), o.get(c_ten_kh)):
            continue
        chung = {"ky_thang": thang, "ma_khach": o.get(c_ma_kh),
                 "ma_nhom_kd": o.get(c_nhom_kd)}
        kqkd.append(chung | {"ten_khach": o.get(c_ten_kh)}
                    | {ten: o.get(c) for ten, c in cot_kqkd.items()})
        for c in cot_cp:
            chi_phi.append(chung | {"ma_khoan_cp": ma.get(c), "cap_phan_bo": mau.CAP_PHAN_BO,
                                    "so_tien": o.get(c)})
    return kqkd, chi_phi


def _danh_muc(luoi: Luoi, td_ma: str, td_ten: str, cot: tuple[str, str]) -> list[dict]:
    dong_td = _dong_tieu_de(luoi, td_ma, td_ten)
    if dong_td is None:
        return []
    c_ma, c_ten = _cot(luoi[dong_td], td_ma), _cot(luoi[dong_td], td_ten)
    ra: list[dict] = []
    for so in sorted(r for r in luoi if r > dong_td):
        if mau.la_dong_danh_dau(list(luoi[so].values())):
            continue
        gia_tri = (luoi[so].get(c_ma), luoi[so].get(c_ten))
        if any(v is not None for v in gia_tri):
            ra.append(dict(zip(cot, gia_tri, strict=True)))
    return ra


class BaoCaoKhDocLai:
    """Cùng hình dạng `doc_sheet` để `reconcile.r1` dùng."""

    def __init__(self, path: Path) -> None:
        doc = XlsxDocLai(path)
        try:
            kqkd, chi_phi = _tong_hop(doc.luoi(mau.SHEET_TONG_HOP))
            ds_khach = _danh_muc(doc.luoi(mau.SHEET_DS_KHACH), mau.TD_DS_MA, mau.TD_DS_TEN,
                                 ("ma_khach", "ten_khach"))
            dm_cp = _danh_muc(doc.luoi(mau.SHEET_DM_CP), mau.TD_DM_MA, mau.TD_DM_TEN,
                              ("ma_khoan_cp", "ten_khoan"))
        finally:
            doc.close()
        self._bang: dict[str, list[dict]] = {
            mau.KET_QUA_KD: kqkd, mau.CHI_PHI: chi_phi,
            mau.DM_KHACH_HANG: ds_khach,
            mau.DM_KHOAN_CP: [d | {"nhom_chi_phi": mau.NHOM_CHI_PHI.get(
                (d["ma_khoan_cp"] or "").strip())} for d in dm_cp],
        }

    def close(self) -> None:
        return None

    def doc_sheet(
        self, ten_sheet: str
    ) -> tuple[dict[int, str], dict[int, dict[int, str | None]]]:
        ten = next(t for t in mau.BANG_PHANG if chuan_ten(t) == chuan_ten(ten_sheet))
        tieu_de = dict(enumerate(mau.BANG_PHANG[ten], start=1))
        hang = {
            so: {i: dong[c] for i, c in tieu_de.items() if dong.get(c) is not None}
            for so, dong in enumerate(self._bang[ten], start=2)
        }
        return tieu_de, hang
