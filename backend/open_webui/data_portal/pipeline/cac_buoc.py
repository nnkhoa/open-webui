"""Các bước xử lý A1–A5, B1–B5 của một lần nạp (mục 17 đặc tả) — lưu theo lần nạp.

Mỗi bước là một dòng: mã, tên, **một dòng kết quả**, nhãn kết luận và trạng
thái vòng tròn (`ok` ✓ / `err` ! / `skip` –). Câu chữ chép nguyên văn đặc tả;
số liệu lấy từ bước Kiểm tra tệp (`kiem_tra_tep`) và từ đối chiếu sau khi ghi.

Hàm thuần: nhận số liệu, trả danh sách `dict` để ghi vào `ctl.load.cac_buoc`.
"""

from __future__ import annotations

from ..format import so_nguyen

TEN = {
    "A1": "Nhận tệp",
    "A2": "Kiểm tra cấu trúc tệp",
    "A3": "Kiểm tra dữ liệu từng dòng",
    "A4": "So với dữ liệu đang có",
    "A5": "Người nạp xác nhận",
    "B1": "Ghi dữ liệu gốc",
    "B2": "Ghi dữ liệu chuẩn hoá",
    "B3": "Ghi dữ liệu phân tích",
    "B4": "Đối chiếu tổng tiền, tháng, khách hàng",
    "B5": "Chốt",
}
TEN_B4_SO_LUONG = "Đối chiếu số lượng và các mã"

# Tên ngắn của từng loại lỗi trong câu "Có {n} lỗi (thiếu cột, lặp cột, thiếu sheet)".
TEN_LOI = {
    "MISSING_SHEET": "thiếu sheet",
    "UNKNOWN_SHEET": "sheet ngoài bộ bảng",
    "MISSING_COLUMN": "thiếu cột",
    "UNKNOWN_COLUMN": "cột ngoài bộ bảng",
    "DUPLICATE_COLUMN": "lặp cột",
    "DATA_IN_UNNAMED_COLUMN": "ô có dữ liệu ở cột không tên",
    "MISSING_REQUIRED": "thiếu giá trị bắt buộc",
    "BK_DUPLICATE_IN_BATCH": "dòng trùng định danh",
    "NO_DATA_SHEET": "không có sheet đủ cột",
    "MANY_DATA_SHEETS": "nhiều sheet đủ cột",
}

HUY_THEO = "Bị huỷ cùng cả lần ghi vì bước trước lệch."
HUY_CHOT = "Không có dòng nào của lần nạp này được lưu. Dữ liệu trước lần nạp giữ nguyên."


def _buoc(ma: str, ket_qua: str, ket_luan: str, trang_thai: str, ten: str = "") -> dict:
    return {"ma": ma, "ten": ten or TEN[ma], "ket_qua": ket_qua, "ket_luan": ket_luan,
            "trang_thai": trang_thai}


def _khong_chay(ma: str, buoc_loi: str, ten: str = "") -> dict:
    return _buoc(ma, f"Không chạy vì tệp bị từ chối ở bước {buoc_loi}.", "Không chạy",
                 "skip", ten)


def _cac_loai_loi(loi: list[dict]) -> str:
    ten: list[str] = []
    for e in loi:
        t = TEN_LOI.get(e.get("reason_code") or "", "")
        if t and t not in ten:
            ten.append(t)
    return ", ".join(ten)


def cau_co_loi(loi: list[dict]) -> str:
    """"Có 3 lỗi (thiếu cột, lặp cột, thiếu sheet). Cả tệp bị từ chối."."""
    loai = _cac_loai_loi(loi)
    return (f"Có {so_nguyen(len(loi))} lỗi" + (f" ({loai})" if loai else "")
            + ". Cả tệp bị từ chối.")


def ten_b4(kt: dict) -> str:
    return TEN_B4_SO_LUONG if any(b.get("loai_tong") == "so_luong" for b in kt["bang"]) \
        else TEN["B4"]


def buoc_a(kt: dict, *, nguoi: str, a4: str | None, mot_bang: bool = False) -> list[dict]:
    """A1–A5. `a4` là câu của bước So với dữ liệu đang có; None khi bị từ chối."""
    loi_o = kt.get("buoc_loi")
    ra = [_buoc("A1", f"Đúng định dạng .xlsx, đọc được {so_nguyen(kt['so_sheet'])} sheet.",
                "Đúng", "ok")]

    # A2 — cấu trúc
    if loi_o == "A2":
        cau = kt.get("cau_loi_a2") or cau_co_loi(kt["loi"])
        ra.append(_buoc("A2", cau, "Sai", "err"))
    elif kt.get("sheet_du_lieu") and kt.get("dong_tieu_de"):
        ra.append(_buoc(
            "A2", f"Sheet {kt['sheet_du_lieu']} có đủ {so_nguyen(kt['so_cot_can'])} cột "
                  f"cần lấy ở dòng tiêu đề {so_nguyen(kt['dong_tieu_de'])}.", "Đúng", "ok"))
    else:
        sheet = [s for s in kt["cac_sheet"] if s in {b["sheet"] for b in kt["bang"]}]
        ra.append(_buoc("A2", f"Đủ {so_nguyen(len(sheet))} sheet {', '.join(sheet)}; "
                              f"đúng tên cột.", "Đúng", "ok"))

    # A3 — dữ liệu từng dòng
    if loi_o == "A2":
        ra.append(_khong_chay("A3", "A2"))
    elif loi_o == "A3":
        ra.append(_buoc("A3", cau_co_loi(kt["loi"]), "Sai", "err"))
    else:
        ra.append(_buoc("A3", cau_a3(kt, mot_bang), "Hợp lệ", "ok"))

    # A4, A5
    if loi_o:
        ra += [_khong_chay("A4", loi_o), _khong_chay("A5", loi_o)]
    else:
        ra.append(_buoc("A4", a4 or "Đã hiện cho người nạp ở màn Xác nhận.", "Xong", "ok"))
        ra.append(_buoc("A5", f"{nguoi} đã bấm xác nhận.", "Đã xác nhận", "ok"))
    return ra


def cau_a3(kt: dict, mot_bang: bool) -> str:
    """"Đọc 7.561 dòng, không thiếu giá trị bắt buộc. 90 dòng trùng ở Danh mục khách
    hàng sẽ bỏ (227 → 137). Sẽ ghi 7.471 dòng." — hoặc dạng một bảng của HQ-MAU-GC."""
    bang = kt["bang"]
    doc = sum(b["doc"] for b in bang)
    se_ghi = sum(b["se_ghi"] for b in bang)
    o_trong = sum(b["o_trong"] for b in bang)
    phan: list[str] = []
    if mot_bang:
        pham_vi = (f" (dòng {so_nguyen(kt['dong_tu'])}–{so_nguyen(kt['dong_den'])})"
                   if kt.get("dong_tu") and kt.get("dong_den") else "")
        trung = sum(b["trung_bo"] for b in bang)
        phan.append(f"Đọc {so_nguyen(doc)} dòng{pham_vi}, "
                    + ("không có dòng trùng." if not trung
                       else f"{so_nguyen(trung)} dòng trùng sẽ bỏ."))
    else:
        phan.append(f"Đọc {so_nguyen(doc)} dòng, không thiếu giá trị bắt buộc.")
        for b in bang:
            if b["trung_bo"]:
                phan.append(f"{so_nguyen(b['trung_bo'])} dòng trùng ở {b['ten_bang']} sẽ bỏ "
                            f"({so_nguyen(b['doc'])} → {so_nguyen(b['se_ghi'])}).")
    if o_trong:
        phan.append(f"{so_nguyen(o_trong)} ô không đọc được ngày hoặc số sẽ để trống.")
    phan.append(f"Sẽ ghi {so_nguyen(se_ghi)} dòng.")
    return " ".join(phan)


def buoc_b_tu_choi(buoc_loi: str, ten_buoc_b4: str) -> list[dict]:
    return [_khong_chay(m, buoc_loi, ten_buoc_b4 if m == "B4" else "")
            for m in ("B1", "B2", "B3", "B4", "B5")]


def buoc_b(ket_qua: list[tuple[str, bool, str, str]], *, chot: str,
           ten_buoc_b4: str) -> list[dict]:
    """B1–B5 sau khi ghi.

    `ket_qua` là `[(mã, đạt, câu khi khớp, câu khi lệch)]` cho B1–B4 theo thứ
    tự. Bước lệch đầu tiên hiện "Lệch"; các bước sau nó "Đã huỷ" (QT-13).
    """
    ra: list[dict] = []
    da_lech = False
    for ma, dat, cau_khop, cau_lech in ket_qua:
        ten = ten_buoc_b4 if ma == "B4" else ""
        if da_lech:
            ra.append(_buoc(ma, HUY_THEO, "Đã huỷ", "skip", ten))
        elif dat:
            ra.append(_buoc(ma, cau_khop, "Đúng" if ma == "B4" else "Khớp", "ok", ten))
        else:
            ra.append(_buoc(ma, cau_lech, "Lệch", "err", ten))
            da_lech = True
    if da_lech:
        ra.append(_buoc("B5", HUY_CHOT, "Đã huỷ", "skip"))
    else:
        ra.append(_buoc("B5", chot, "Đã chốt", "ok"))
    return ra
