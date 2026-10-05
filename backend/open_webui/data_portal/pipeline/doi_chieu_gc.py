"""Các thẻ đối chiếu riêng của HQ-MAU-GC (mục 18.2) — B7, B8, B15, B16.

    b) Đối chiếu tổng: tổng so_luong, tổng don_gia, ô tổng của tệp (P10 chỉ ghi
       nhận vì SUBTOTAL chỉ cộng dòng đang hiện; P1 phải khớp)
    c) Ô không đọc được ngày hoặc số, để trống trong database
    d) Đối chiếu số lượng theo một chiều (tháng giao mẫu, nhóm, khách, …), có trang
    e) Đối chiếu các mã (đếm giá trị khác nhau, không tính ô trống)
    f) Các bảng của nhóm trong năm, trước và sau lần nạp

Thẻ a) Đối chiếu số dòng dùng chung với HQKD (`doi_chieu_the`). Chạy trong giao
dịch ghi; số cất dạng số (nguyên → int, lẻ → float).
"""

from __future__ import annotations

from decimal import Decimal

from .. import messages
from ..formatting import format_amount, format_integer
from ..registry.schema import FormTable
from .context import LoadContext
from .doi_chieu_the import TIEU_DE, _mo_bang, so
from .file_check import month_key

KHONG = Decimal(0)

# Chiều chia ở thẻ d): (cột, nhãn chip). Cột đầu là mặc định.
CHIEU = {
    "fact_may_mau": [("ngay_giao_mau", "Tháng giao mẫu"),
                     ("ma_nhom_kd", "Nhóm kinh doanh (SALE)"),
                     ("ten_khach", "Khách hàng"), ("ma_giai_doan_mau", "Loại mẫu")],
    "fact_gia_cong": [("ma_don_vi_gc", "Đơn vị gia công"), ("khu_vuc", "Khu vực"),
                      ("ten_khach", "Khách hàng"), ("ma_hang", "Mã hàng")],
}

# Thẻ e): (nội dung, cột, tên ngắn trong câu B4).
MA = {
    "fact_may_mau": [("Số tháng giao mẫu", "ngay_giao_mau", "tháng"),
                     ("Số khách hàng (ten_khach)", "ten_khach", "khách hàng"),
                     ("Số nhóm kinh doanh (ma_nhom_kd)", "ma_nhom_kd", "nhóm"),
                     ("Số mã hàng (ma_mau)", "ma_mau", "mã hàng"),
                     ("Số loại mẫu (ma_giai_doan_mau)", "ma_giai_doan_mau", "loại mẫu")],
    "fact_gia_cong": [("Số đơn vị gia công (ma_don_vi_gc)", "ma_don_vi_gc", "đơn vị gia công"),
                      ("Số khu vực (khu_vuc)", "khu_vuc", None),
                      ("Số khách hàng (ten_khach)", "ten_khach", "khách hàng"),
                      ("Số mã hàng (ma_hang)", "ma_hang", "mã hàng"),
                      ("Số đơn hàng (ma_don_hang)", "ma_don_hang", "đơn hàng"),
                      ("Số màu (mau)", "mau", "màu")],
}


def _tong(dong: list[dict], cot: str) -> Decimal:
    return sum((Decimal(d[cot]) for d in dong if d.get(cot) is not None), KHONG)


def _khoa(cot: str, gia_tri) -> str:
    if gia_tri is None:
        return ""
    return month_key(gia_tri) if cot == "ngay_giao_mau" else str(gia_tri)


# --------------------------------------------------------------------------- #
#  b) Đối chiếu tổng
# --------------------------------------------------------------------------- #


def the_tong(ctx: LoadContext, table: FormTable, goc: list, db: list, kt: dict) -> dict:
    dong = []
    for cot in ("so_luong", "don_gia"):
        if cot not in table.column_names:
            continue
        tep, trong_db = _tong(goc, cot), _tong(db, cot)
        dong.append({"o": [f"Tổng cột {cot}", so(tep), so(trong_db), so(trong_db - tep)],
                     "ket_luan": "Đúng" if tep == trong_db else "Lệch",
                     "mo": _mo_bang(ctx, table, "gold")})
    o_tong = kt.get("o_tong")
    if o_tong and o_tong.get("gia_tri") is not None:
        try:
            tep = Decimal(o_tong["gia_tri"])
        except ArithmeticError:
            tep = None
        if tep is not None:
            trong_db = _tong(db, "so_luong")
            hang = {"o": [f"Ô tổng {o_tong['o']} của tệp ({o_tong['tieu_de']})", so(tep),
                          so(trong_db), so(trong_db - tep)]}
            if o_tong.get("ghi_nhan"):
                # SUBTOTAL chỉ cộng dòng đang hiện — chỉ ghi nhận, không chặn (QT-14).
                hang["ket_luan"] = "Ghi nhận"
                hang["phu"] = (f"Chỉ cộng {format_integer(kt.get('so_dong_hien', 0))} dòng đang "
                               f"hiện; {format_integer(kt.get('so_dong_an', 0))} dòng bị bộ lọc "
                               f"Excel ẩn. Portal đọc cả dòng ẩn.")
            else:
                hang["ket_luan"] = "Đúng" if tep == trong_db else "Lệch"
            dong.append(hang)
    return {"ma": "tong", "tieu_de": TIEU_DE["tong_gc"],
            "cot": [{"t": "Nội dung"}, {"t": "Theo tệp gốc", "r": True},
                    {"t": "Trong database", "r": True}, {"t": "Lệch", "r": True},
                    {"t": "Kết luận"}],
            "dong": dong}


# --------------------------------------------------------------------------- #
#  c) Ô không đọc được ngày hoặc số (B16)
# --------------------------------------------------------------------------- #


def the_o_trong(kt: dict) -> dict | None:
    """Theo cột rồi theo giá trị trong tệp; chỉ có thẻ khi có ô như vậy."""
    dong = []
    for b in kt.get("bang", []):
        for c in b["o_trong_chi_tiet"]:
            for g in sorted(c["gia_tri"], key=lambda x: -x["so_o"]):
                dong.append({"o": [c["cot"], g["gia_tri"], g["so_o"], None],
                             "ket_luan": "Ghi nhận"})
    if not dong:
        return None
    return {"ma": "o_trong", "tieu_de": TIEU_DE["o_trong"],
            "so": sum(d["o"][2] for d in dong),
            "cot": [{"t": "Cột"}, {"t": "Giá trị trong tệp"}, {"t": "Số ô", "r": True},
                    {"t": "Trong database"}, {"t": "Kết luận"}],
            "dong": dong}


# --------------------------------------------------------------------------- #
#  d) Số lượng theo một chiều — ma trận cất lại, dựng theo trang khi được hỏi
# --------------------------------------------------------------------------- #


def ma_tran_chieu(ctx: LoadContext, table: FormTable, goc: list, db: list) -> dict:
    chia: dict[str, dict] = {}
    co_lech = False
    for cot, nhan in CHIEU.get(table.name, []):
        nhom: dict[str, dict] = {}
        for phia, dong in (("tep", goc), ("db", db)):
            for d in dong:
                muc = nhom.setdefault(_khoa(cot, d.get(cot)),
                                      {"tep": 0, "db": 0, "sl_tep": KHONG, "sl_db": KHONG})
                muc[phia] += 1
                if d.get("so_luong") is not None:
                    muc[f"sl_{phia}"] += Decimal(d["so_luong"])
        for v in nhom.values():
            co_lech = co_lech or v["tep"] != v["db"] or v["sl_tep"] != v["sl_db"]
        chia[cot] = {"nhan": nhan, "nhom": [
            {"khoa": k, "tep": v["tep"], "db": v["db"], "sl_tep": so(v["sl_tep"]),
             "sl_db": so(v["sl_db"])} for k, v in nhom.items()]}
    return {"ma": "theo_chieu", "bang": table.name, "nam": ctx.year, "chia": chia,
            "thu_tu_chia": [c for c, _ in CHIEU.get(table.name, [])], "lech": co_lech}


def _nhan_nhom(cot: str, khoa: str) -> str:
    if cot == "ngay_giao_mau":
        if not khoa:
            return messages.CHECK_NO_DELIVERY_DATE
        nam, thang = khoa.split("-")
        return f"Tháng {int(thang)}/{nam}"
    return khoa or "(trống)"


def dung_the_chieu(ma_tran: dict, *, chia_theo: str | None, trang: int, moi: int) -> dict:
    thu_tu = ma_tran.get("thu_tu_chia") or list(ma_tran.get("chia", {}))
    the = {"ma": "theo_chieu", "tieu_de": "", "cot": [], "dong": []}
    if not thu_tu:
        return the
    cot = chia_theo if chia_theo in ma_tran["chia"] else thu_tu[0]
    muc = ma_tran["chia"][cot]
    if cot == "ngay_giao_mau":
        nhom = sorted(muc["nhom"], key=lambda n: (n["khoa"] == "", n["khoa"]))
    else:
        nhom = sorted(muc["nhom"], key=lambda n: (-n["sl_tep"], n["khoa"] == "", n["khoa"]))
    nhan = muc["nhan"]
    the["tieu_de"] = TIEU_DE["theo_chieu"].format(chia_theo=nhan[0].lower() + nhan[1:])
    the["so"] = len(nhom)
    the["tuy_chon"] = [{"ten": "chia_theo", "nhan": "Chia theo", "gia_tri": cot,
                        "mac": thu_tu[0],
                        "lua_chon": [{"v": c, "t": ma_tran["chia"][c]["nhan"]}
                                     for c in thu_tu]}]
    the["cot"] = [{"t": nhan}, {"t": "Số dòng theo tệp gốc", "r": True},
                  {"t": "Số dòng trong database", "r": True},
                  {"t": "Số lượng theo tệp gốc", "r": True},
                  {"t": "Số lượng trong database", "r": True}, {"t": "Lệch", "r": True},
                  {"t": "Kết luận"}]
    tu = (trang - 1) * moi
    for n in nhom[tu:tu + moi]:
        lech = Decimal(str(n["sl_db"])) - Decimal(str(n["sl_tep"]))
        hang = {"o": [_nhan_nhom(cot, n["khoa"]), n["tep"], n["db"], n["sl_tep"], n["sl_db"],
                      so(lech)],
                "ket_luan": "Đúng" if n["tep"] == n["db"] and lech == 0 else "Lệch"}
        if n["khoa"]:
            tim = n["khoa"]
            if cot == "ngay_giao_mau":
                nam, thang = n["khoa"].split("-")
                tim = f"{thang}/{nam}"
            hang["mo"] = {"bang": ma_tran["bang"], "lop": "gold",
                          **({"nam": ma_tran["nam"]} if ma_tran.get("nam") else {}),
                          "tim": tim}
        the["dong"].append(hang)
    tong = [sum(n["tep"] for n in nhom), sum(n["db"] for n in nhom),
            sum(Decimal(str(n["sl_tep"])) for n in nhom),
            sum(Decimal(str(n["sl_db"])) for n in nhom)]
    the["tong"] = ["Tổng", tong[0], tong[1], so(tong[2]), so(tong[3]), so(tong[3] - tong[2]),
                   None]
    the["trang"] = {"trang": trang, "moi": moi, "tong": len(nhom)}
    return the


# --------------------------------------------------------------------------- #
#  e) Các mã
# --------------------------------------------------------------------------- #


def the_ma(table: FormTable, goc: list, db: list) -> dict:
    dong = []
    for noi_dung, cot, _ in MA.get(table.name, []):
        a = {_khoa(cot, d.get(cot)) for d in goc} - {""}
        b = {_khoa(cot, d.get(cot)) for d in db} - {""}
        dong.append({"o": [noi_dung, len(a), len(b)], "ket_luan": "Khớp" if a == b else "Lệch"})
    return {"ma": "ma", "tieu_de": TIEU_DE["ma_gc"],
            "cot": [{"t": "Nội dung"}, {"t": "Theo tệp gốc", "r": True},
                    {"t": "Trong database", "r": True}, {"t": "Kết luận"}],
            "dong": dong}


# --------------------------------------------------------------------------- #
#  f) Các bảng của nhóm trước và sau lần nạp
# --------------------------------------------------------------------------- #


def the_truoc_sau(ctx: LoadContext, table: FormTable, truoc: dict[str, int],
                  sau: dict[str, int], cac_bang: list[dict]) -> dict:
    dong = []
    se_ghi = ctx.table_result(table).rows_silver
    for b in cac_bang:
        ten = b["name"]
        t, s = truoc.get(ten, 0), sau.get(ten, 0)
        if ten == table.name:
            cach = "Ghi đè" if t else "Ghi thêm"
            ket_luan = "Đúng" if s == se_ghi else "Lệch"
        else:
            cach, ket_luan = "Không đụng tới", ("Giữ nguyên" if s == t else "Lệch")
        hang = {"o": [b["label"], "Có" if ten == table.name else "Không", t, s, cach],
                "ket_luan": ket_luan, "phu": ten}
        if s:
            hang["mo"] = {"bang": ten, "lop": "gold", **({"nam": ctx.year} if ctx.year else {})}
        dong.append(hang)
    return {"ma": "truoc_sau",
            "tieu_de": TIEU_DE["truoc_sau_gc"].format(nhom=ctx.domain_code, nam=ctx.year or ""),
            "cot": [{"t": "Bảng"}, {"t": "Có trong tệp"},
                    {"t": "Số dòng trước lần nạp", "r": True},
                    {"t": "Số dòng sau lần nạp", "r": True}, {"t": "Cách ghi"},
                    {"t": "Kết luận"}],
            "dong": dong}


# --------------------------------------------------------------------------- #
#  Câu của bước B4
# --------------------------------------------------------------------------- #


def cau_b4(the: dict, lech: list[str], kt: dict, ten_bang: str) -> str:
    """"Tổng so_luong 4.911 = 4.911; tổng don_gia 77.416,50 = 77.416,50; số tháng,
    khách hàng, nhóm, mã hàng, loại mẫu khớp."."""
    if lech:
        return "Có chênh lệch ở: " + "; ".join(
            the[m]["tieu_de"] for m in lech if m in the) + "."
    phan = []
    for d in the["tong"]["dong"]:
        ten = d["o"][0]
        if ten.startswith("Tổng cột "):
            nhan = "Tổng" if not phan else "tổng"
            phan.append(f"{nhan} {ten.removeprefix('Tổng cột ')} "
                        f"{format_amount(Decimal(str(d['o'][1])))} = "
                        f"{format_amount(Decimal(str(d['o'][2])))}")
        elif d["ket_luan"] != "Ghi nhận" and phan:
            o_tong = kt.get("o_tong") or {}
            phan[0] += f", bằng ô tổng {o_tong.get('o', '')} của tệp"
    ten_ngan = [x[2] for x in MA.get(ten_bang, []) if x[2]]
    if ten_ngan:
        phan.append(f"số {', '.join(ten_ngan)} khớp")
    return "; ".join(phan) + "."
