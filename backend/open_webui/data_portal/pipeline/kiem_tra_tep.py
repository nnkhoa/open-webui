"""Bước Kiểm tra tệp (A1–A3) — **chỉ đọc tệp, không ghi gì vào database** (QT-07).

Chạy đủ mọi kiểm tra mà bước ghi sẽ chạy, nhưng trước khi có giao dịch nào:

    A1  nhận tệp: mở được, đếm sheet
    A2  cấu trúc: sheet, tên cột (`structure.kiem_tra`)
    A3  dữ liệu từng dòng: thiếu giá trị bắt buộc, ô không đổi được kiểu, dòng
        trùng y hệt sẽ bỏ, số dòng sẽ ghi, tổng tiền / tổng số lượng

Kết quả là `dict` thuần (số tiền để dạng chuỗi cho khỏi mất chữ số), cất được
xuống tệp chờ xác nhận và dùng lại ở màn Xác nhận, ở các bước A1–A3 của lần nạp.
Có lỗi thì `loi` khác rỗng và `buoc_loi` là bước bị chặn — cả tệp bị từ chối
(QT-05, QT-06).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from ..errors import CauTrucError
from ..registry.schema import Form, FormTable
from ..sources import bang_theo_tieu_de, bao_cao_kh  # noqa: F401 — đăng ký bộ đọc
from ..sources import base as nguon
from ..sources.xlsx import ten_cac_sheet
from . import validate
from .bronze import dien_ngoai_tep
from .dedup import bam_dong
from .structure import kiem_tra as kiem_tra_cau_truc

HOP_LE = "Hợp lệ"
KHONG_HOP_LE = "Không hợp lệ"


def loai_tong(table: FormTable) -> str | None:
    """Cột "Tổng" ở thẻ Kết quả kiểm tra: tổng số lượng (HQ-MAU-GC), tổng tiền
    (HQKD), hoặc không có (danh mục)."""
    if any(c.name == "so_luong" and c.role == "measure" for c in table.columns):
        return "so_luong"
    if table.cot_tien:
        return "tien"
    return None


def cot_cong_tong(table: FormTable) -> list[str]:
    """Các cột được cộng vào cột "Tổng" của bảng."""
    kieu = loai_tong(table)
    if kieu == "so_luong":
        return ["so_luong"]
    if kieu == "tien":
        return [c.name for c in table.cot_tien]
    return []


def sheet_goc(reader, table: FormTable) -> str:
    """Sheet của tệp NBC mà bảng được lấy ra."""
    ham = getattr(reader, "sheet_goc", None)
    return ham(table.sheet) if ham else table.sheet


def kiem_tra(form: Form, duong_dan: Path, nam: int | None) -> dict:
    """Kiểm tra một tệp đã nằm trên đĩa. Ném `NguonDuLieuError` nếu không mở được."""
    cac_sheet = ten_cac_sheet(duong_dan)
    ket_qua: dict = {"so_sheet": len(cac_sheet), "cac_sheet": cac_sheet,
                     "loi": [], "buoc_loi": None, "bang": []}

    reader = nguon.mo(form.source_kind, duong_dan, form.header_row, form)
    try:
        loi = kiem_tra_cau_truc(reader, form)
        if loi:
            ket_qua["loi"], ket_qua["buoc_loi"] = loi, "A2"
            if any(e.get("reason_code") == "NO_DATA_SHEET" for e in loi):
                # "Không sheet nào có đủ 7 cột của Lịch may mẫu. Cả tệp bị từ chối."
                ket_qua["cau_loi_a2"] = (
                    f"Không sheet nào có đủ {len(form.tables[0].cot_tu_tep)} cột của "
                    f"{form.label}. Cả tệp bị từ chối.")
            return ket_qua
        loi_dong: list[dict] = []
        for table in form.tables_hien_thi:
            ket_qua["bang"].append(_kiem_tra_bang(reader, table, nam, loi_dong))
        if loi_dong:
            ket_qua["loi"], ket_qua["buoc_loi"] = loi_dong, "A3"
        ket_qua["sheet_du_lieu"] = _sheet_du_lieu(reader, form)
        # Bộ đọc theo dòng tiêu đề (HQ-MAU-GC) ghi thêm: dòng tiêu đề, khoảng dòng
        # dữ liệu, ô tổng, ngày của bản, số dòng đang ẩn — cho A2, A3, B5 và đối chiếu.
        tt = getattr(reader, "thong_tin", None) or {}
        ket_qua.update({k: tt[k] for k in ("dong_tieu_de", "so_cot_can", "dong_tu",
                                           "dong_den", "o_tong", "ngay_ban", "so_dong_an",
                                           "so_dong_hien") if k in tt})
        if len(form.tables) == 1 and form.tables[0].merge == "replace_all" and nam:
            ban = f" (bản {tt['ngay_ban']})" if tt.get("ngay_ban") else ""
            ket_qua["cau_chot"] = f"{form.label} năm {nam}{ban} có hiệu lực từ lúc này."
        return ket_qua
    finally:
        reader.close()


def _sheet_du_lieu(reader, form: Form) -> str | None:
    """Sheet lấy dữ liệu khi cả bộ bảng chỉ lấy từ một sheet (HQ-MAU-GC)."""
    cac = {sheet_goc(reader, t) for t in form.tables}
    return cac.pop().strip() if len(cac) == 1 and len(form.tables) == 1 else None


def _kiem_tra_bang(reader, table: FormTable, nam: int | None, loi: list[dict]) -> dict:
    hang = []
    for dong in reader.rows(table.sheet, table.anh_xa_tieu_de):
        dong = dien_ngoai_tep(table, dong, nam, reader)
        hang.append((0, dong.number, bam_dong(table.sheet, dong.values, table.column_names),
                     dong.values))

    o_hong: dict[str, dict[str, int]] = {}
    try:
        giu, trung = validate.kiem_tra(table, hang, o_hong)
        thieu = 0
    except CauTrucError as exc:
        loi += exc.loi
        thieu = len(exc.loi)
        giu, trung = [], []

    cot_tong = cot_cong_tong(table)
    tong = sum((Decimal(d.values[c]) for d in giu for c in cot_tong
                if d.values.get(c) is not None), Decimal(0))

    ra = {
        "bang": table.name,
        "ten_bang": table.label,
        "loai": table.kind,
        "sheet": sheet_goc(reader, table),
        "doc": len(hang),
        "thieu_bat_buoc": thieu,
        "trung_bo": len(trung),
        "o_trong": sum(sum(v.values()) for v in o_hong.values()),
        "o_trong_chi_tiet": [
            {"cot": cot, "so_o": sum(theo.values()),
             "gia_tri": [{"gia_tri": g, "so_o": n} for g, n in theo.items()]}
            for cot, theo in o_hong.items()],
        "se_ghi": len(giu),
        "loai_tong": loai_tong(table),
        "tong": str(tong) if cot_tong else None,
        "so_cot_tong": len(table.cot_tu_tep),
        "ket_luan": KHONG_HOP_LE if thieu else HOP_LE,
    }
    if table.partition_by:
        ra["theo_ky"] = _theo_ky(table, giu, cot_tong)
    if table.name in NHOM_XAC_NHAN:
        ra["theo_nhom"] = _theo_nhom(table, hang, giu)
    return ra


# Thẻ ở màn Xác nhận của HQ-MAU-GC: "Theo tháng giao mẫu" (Lịch may mẫu), "Theo đơn
# vị gia công" (Đơn gia công ngoài) — cột chia nhóm và cách chia.
NHOM_XAC_NHAN = {"fact_may_mau": ("ngay_giao_mau", "thang"),
                 "fact_gia_cong": ("ma_don_vi_gc", "gia_tri")}
CHUA_CO_NGAY = "Chưa có ngày giao mẫu"


def khoa_thang(gia_tri) -> str | None:
    """Ngày → "2026-06" để sắp theo thời gian; None nếu không có ngày."""
    return None if gia_tri is None else f"{gia_tri.year:04d}-{gia_tri.month:02d}"


def _theo_nhom(table: FormTable, hang: list, giu: list) -> dict:
    """Số dòng, số lượng theo nhóm của tệp; thứ tự nhóm như trong tệp."""
    cot, cach = NHOM_XAC_NHAN[table.name]
    nhom: dict[str, dict] = {}
    o_trong = khong_doc = 0
    for (_, _, _, tho), d in zip(hang, giu, strict=False):
        gia_tri = d.values.get(cot)
        if cach == "thang":
            khoa = khoa_thang(gia_tri) or ""
            if gia_tri is None:
                o_trong += tho.get(cot) is None
                khong_doc += tho.get(cot) is not None
        else:
            khoa = "" if gia_tri is None else str(gia_tri)
        muc = nhom.setdefault(khoa, {"so_dong": 0, "so_luong": Decimal(0)})
        muc["so_dong"] += 1
        if d.values.get("so_luong") is not None:
            muc["so_luong"] += Decimal(d.values["so_luong"])
    return {"cot": cot, "cach": cach, "o_trong": o_trong, "khong_doc": khong_doc,
            "thu_tu": list(nhom),
            "nhom": {k: {"so_dong": v["so_dong"], "so_luong": str(v["so_luong"])}
                     for k, v in nhom.items()}}


def _theo_ky(table: FormTable, dong: list, cot_tong: list[str]) -> dict[str, dict]:
    """Số dòng, số cột có giá trị và tổng theo từng kỳ của tệp."""
    cot_ky = table.partition_column
    tu_tep = [c.name for c in table.cot_tu_tep]
    ra: dict[str, dict] = {}
    cot_dung: dict[str, set[str]] = {}
    for d in dong:
        gia_tri = d.values.get(cot_ky.name)
        if gia_tri is None:
            continue
        ky = cot_ky.display(gia_tri) if cot_ky.type == "month" else str(gia_tri)
        muc = ra.setdefault(ky, {"so_dong": 0, "tong": Decimal(0)})
        muc["so_dong"] += 1
        muc["tong"] += sum((d.values[c] for c in cot_tong if d.values.get(c) is not None),
                           Decimal(0))
        cot_dung.setdefault(ky, set()).update(c for c in tu_tep if d.values.get(c) is not None)
    for ky, muc in ra.items():
        muc["so_cot"] = len(cot_dung[ky])
        muc["tong"] = str(muc["tong"])
    return ra
