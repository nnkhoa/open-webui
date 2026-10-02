"""Các thẻ "Đối chiếu tệp gốc ↔ database" (mục 18 đặc tả) — B7, B8, B9.

Chạy **trong giao dịch ghi** của lần nạp, sau khi đã dựng lớp phân tích:

    phía "theo tệp gốc"   tính từ lớp gốc của lần nạp (chữ y như ô Excel, đã so
                          từng dòng với tệp ở R1), ép kiểu bằng đúng bộ xử lý
                          kiểu của cột;
    phía "trong database" tính từ lớp phân tích, đúng phạm vi lần nạp chạm tới
                          (năm đã chọn và các tháng có trong tệp; danh mục: các
                          mã có trong tệp).

Kết quả cất vào `ctl.load.doi_chieu` để xem lại được cả khi giao dịch đã huỷ
(lỗi đối chiếu). Thẻ không phụ thuộc tham số được cất ở dạng đã dựng sẵn; thẻ
có ô chọn (theo tháng / cột tiền / nhóm) cất ma trận số rồi dựng khi được hỏi.

Mọi số tiền cất dạng chuỗi để không mất chữ số; so sánh trên `Decimal`.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from psycopg import sql

from ..db import sql as q
from ..format import so_nguyen, so_tien
from ..registry.schema import FormTable
from .context import LoadContext
from .kiem_tra_tep import cot_cong_tong

KHONG = Decimal(0)

TIEU_DE = {
    "so_dong": "Đối chiếu số dòng: tệp gốc ↔ database",
    "tong": "Đối chiếu tổng tiền cả bảng: tệp gốc ↔ database",
    "tong_gc": "Đối chiếu tổng: tệp gốc ↔ database",
    "o_trong": "Ô không đọc được ngày hoặc số, để trống trong database",
    "theo_chieu": "Đối chiếu số lượng theo {chia_theo}",
    "ma_gc": "Đối chiếu các mã: tệp gốc ↔ database",
    "truoc_sau_gc": "Nhóm {nhom} năm {nam} trước và sau lần nạp",
    "tien_theo_nhom": "Đối chiếu tổng tiền theo tháng, cột tiền, nhóm",
    "ma": "Đối chiếu tháng, khách hàng, nhóm, khoản mục",
    "truoc_sau": "Các tháng trong năm {nam} trước và sau lần nạp",
}
THONG_BAO_HUY = "Lần nạp bị huỷ nên mọi tháng trong database giữ nguyên như trước lần nạp."
THONG_BAO_TU_CHOI = ("Không có dữ liệu đối chiếu vì tệp bị từ chối ở bước kiểm tra cấu trúc, "
                     "chưa có gì được ghi vào database.")

# Cách chia ở thẻ "theo tháng, cột tiền, nhóm" — cột nào có trong bảng thì có lựa chọn đó.
CHIA_THEO = {"ky_thang": "Tháng", "ma_nhom_kd": "Nhóm kinh doanh", "ma_khoan_cp": "Khoản mục"}
TAT_CA = "tat_ca"
NHAN_TAT_CA = "Tất cả cột tiền cộng lại"


# --------------------------------------------------------------------------- #
#  Đọc hai phía
# --------------------------------------------------------------------------- #


def _ep(table: FormTable, ten: str, tho):
    """Giá trị lớp gốc (văn bản) ép theo kiểu cột — như lớp chuẩn hoá sẽ thấy."""
    if tho is None:
        return None
    phan = table.column(ten).handler.parse(tho)
    return phan.value if phan.ok else None


def _dong_goc(ctx: LoadContext, table: FormTable) -> list[dict]:
    """Các dòng lớp gốc của lần nạp, đã ép kiểu."""
    hang = q.query(ctx.conn, sql.SQL("SELECT {} FROM {} WHERE load_id = %s").format(
        q.danh_sach_cot(table.column_names), sql.Identifier("bronze", table.name)),
        (ctx.load_id,))
    return [{c: _ep(table, c, r[c]) for c in table.column_names} for r in hang]


def _pham_vi(ctx: LoadContext, table: FormTable, goc: list[dict]) -> tuple[sql.Composed, list]:
    """Điều kiện chọn dòng lớp phân tích thuộc phạm vi lần nạp."""
    dk = [sql.SQL("t.domain_id = %s"), sql.SQL("t.is_current")]
    tham: list = [ctx.domain_id]
    if table.cot_nam is not None:
        dk.append(sql.SQL("t.{} IS NOT DISTINCT FROM %s").format(
            sql.Identifier(table.cot_nam.name)))
        tham.append(ctx.nam)
    if table.partition_by:
        cot = table.partition_column.name
        dk.append(sql.SQL("t.{} = ANY(%s)").format(sql.Identifier(cot)))
        tham.append(sorted({d[cot] for d in goc if d[cot] is not None}))
    return sql.SQL(" AND ").join(dk), tham


def _dong_db(ctx: LoadContext, table: FormTable, goc: list[dict]) -> list[dict]:
    """Các dòng hiện hành ở lớp phân tích thuộc phạm vi lần nạp."""
    dk, tham = _pham_vi(ctx, table, goc)
    hang = q.query(ctx.conn, sql.SQL("SELECT {} FROM {} t WHERE {}").format(
        q.danh_sach_cot(table.column_names), sql.Identifier("gold", table.name), dk), tham)
    if table.is_dim and table.business_key:
        khoa = {tuple(d[c] for c in table.business_key) for d in goc}
        hang = [r for r in hang if tuple(r[c] for c in table.business_key) in khoa]
    return hang


def so(gia_tri) -> int | float:
    """Số để trả về / cất: nguyên thì `int`, có phần lẻ thì `float` (mục 9.1)."""
    d = Decimal(gia_tri)
    return int(d) if d == d.to_integral_value() else float(d)


def _tong(dong: list[dict], cot: list[str]) -> Decimal:
    return sum((Decimal(d[c]) for d in dong for c in cot if d.get(c) is not None), KHONG)


# --------------------------------------------------------------------------- #
#  B9 — chụp trước khi ghi
# --------------------------------------------------------------------------- #


def chup_truoc(ctx: LoadContext) -> dict:
    """Số dòng và tổng tiền theo tháng của năm đang nạp, **trước** khi ghi; với
    HQ-MAU-GC thêm số dòng của mọi bảng số liệu trong nhóm (`_nhom`).

    Gọi sau khi đã giữ khoá ghi, trước khi đụng tới lớp chuẩn hoá.
    """
    ra: dict[str, dict] = {}
    for table in ctx.form.tables:
        if table.is_dim or table.cot_nam is None:
            continue
        ra[table.name] = _theo_thang_db(ctx, table)
    if la_theo_tieu_de(ctx):
        ra["_nhom"] = _so_dong_nhom(ctx)
    return ra


def la_theo_tieu_de(ctx: LoadContext) -> bool:
    """Loại tệp HQ-MAU-GC: một bảng, nhận theo dòng tiêu đề, ghi đè toàn bộ."""
    return ctx.form.source_kind == "bang_theo_tieu_de"


def _bang_so_lieu_nhom(ctx: LoadContext) -> list[dict]:
    """Các bảng số liệu có cột `nam` của nhóm thông tin, theo thứ tự hiển thị."""
    return q.query(ctx.conn, """
        SELECT ft.name, ft.label FROM ctl.dataset ds
          JOIN ctl.form_table ft ON ft.table_id = ds.table_id
          LEFT JOIN ctl.domain_form df ON df.domain_id = ds.domain_id
                                      AND df.form_id = ft.form_id
         WHERE ds.domain_id = %s AND ft.kind = 'fact' AND ds.is_visible
           AND EXISTS (SELECT 1 FROM ctl.form_column c
                        WHERE c.table_id = ft.table_id AND c.name = 'nam')
         ORDER BY df.thu_tu, ds.display_order, ft.name""", (ctx.domain_id,))


def _so_dong_nhom(ctx: LoadContext) -> dict[str, int]:
    return {b["name"]: q.scalar(ctx.conn, sql.SQL(
        "SELECT count(*) FROM {} WHERE domain_id = %s AND is_current AND nam = %s").format(
        sql.Identifier("gold", b["name"])), (ctx.domain_id, ctx.nam))
        for b in _bang_so_lieu_nhom(ctx)}


def _theo_thang_db(ctx: LoadContext, table: FormTable) -> dict[str, dict]:
    """`{kỳ: {so_dong, tong}}` của năm đang nạp ở lớp phân tích; không có cột kỳ
    thì một mục `*` cho cả năm."""
    cot_tien = [c.name for c in table.cot_tien]
    tong = sql.SQL(" + ").join(
        sql.SQL("coalesce(sum(t.{}), 0)").format(sql.Identifier(c)) for c in cot_tien
    ) if cot_tien else sql.SQL("0")
    if table.partition_by:
        ky = sql.SQL("t.{}::text").format(sql.Identifier(table.partition_column.name))
    else:
        ky = sql.SQL("'*'")
    hang = q.query(ctx.conn, sql.SQL(
        "SELECT {ky} AS ky, count(*) AS so_dong, {tong} AS tong FROM {bang} t "
        " WHERE t.domain_id = %s AND t.is_current AND t.{nam} IS NOT DISTINCT FROM %s "
        " GROUP BY 1").format(ky=ky, tong=tong, bang=sql.Identifier("gold", table.name),
                              nam=sql.Identifier(table.cot_nam.name)),
        (ctx.domain_id, ctx.nam))
    return {r["ky"]: {"so_dong": r["so_dong"], "tong": str(r["tong"])} for r in hang if r["ky"]}


# --------------------------------------------------------------------------- #
#  Tính các thẻ
# --------------------------------------------------------------------------- #


def tinh(ctx: LoadContext, truoc: dict, kt: dict) -> dict:
    """Dựng dữ liệu các thẻ. Trả `{"the": {...}, "lech": [tên thẻ lệch], "b4": câu}`."""
    goc = {t.name: _dong_goc(ctx, t) for t in ctx.form.tables}
    db = {t.name: _dong_db(ctx, t, goc[t.name]) for t in ctx.form.tables}
    sheet_so = {ten: i for i, ten in enumerate(kt.get("cac_sheet", []), start=1)}
    sheet_bang = {b["bang"]: b["sheet"] for b in kt.get("bang", [])}

    the: dict[str, dict] = {}
    lech: list[str] = []
    the["so_dong"] = _the_so_dong(ctx, sheet_so, sheet_bang)
    if la_theo_tieu_de(ctx):
        from . import doi_chieu_gc

        table = ctx.form.tables[0]
        g, d = goc[table.name], db[table.name]
        the["tong"] = doi_chieu_gc.the_tong(ctx, table, g, d, kt)
        o_trong = doi_chieu_gc.the_o_trong(kt)
        if o_trong is not None:
            the["o_trong"] = o_trong
        the["theo_chieu"] = doi_chieu_gc.ma_tran_chieu(ctx, table, g, d)
        the["ma"] = doi_chieu_gc.the_ma(table, g, d)
        the["truoc_sau"] = doi_chieu_gc.the_truoc_sau(
            ctx, table, truoc.get("_nhom", {}), _so_dong_nhom(ctx), _bang_so_lieu_nhom(ctx))
    else:
        the["tong"] = _the_tong(ctx, goc, db)
        the["tien_theo_nhom"] = _ma_tran_tien(ctx, goc, db)
        the["ma"] = _the_ma(ctx, goc, db)
        the["truoc_sau"] = _the_truoc_sau(ctx, truoc, goc)

    for ma, t in the.items():
        if ma in ("tien_theo_nhom", "theo_chieu"):
            if t["lech"]:
                lech.append(ma)
        elif any(d.get("ket_luan") in ("Thiếu", "Thừa", "Lệch") for d in t["dong"]):
            lech.append(ma)

    if la_theo_tieu_de(ctx):
        from . import doi_chieu_gc

        cau = doi_chieu_gc.cau_b4(the, lech, kt, ctx.form.tables[0].name)
    else:
        cau = _cau_b4(the, lech)
    return {"the": the, "lech": lech, "b4": cau}


def _mo_bang(ctx: LoadContext, table: FormTable, lop: str, **them) -> dict:
    mo = {"bang": table.name, "lop": lop}
    if table.cot_nam is not None and ctx.nam is not None:
        mo["nam"] = ctx.nam
    mo.update({k: v for k, v in them.items() if v is not None})
    return mo


def _the_so_dong(ctx: LoadContext, sheet_so: dict, sheet_bang: dict) -> dict:
    """a) Số dòng qua từng lớp của mỗi bảng."""
    dong, tong = [], [0, 0, 0, 0, 0]
    for table in ctx.form.tables_hien_thi:
        k = ctx.bang(table)
        chuan_hoa = k.rows_silver + k.rows_unchanged
        phan_tich = k.rows_gold + k.rows_unchanged
        ky_vong = k.rows_bronze - k.rows_duplicate
        if k.rows_bronze == k.rows_file and chuan_hoa == ky_vong and phan_tich == chuan_hoa:
            ket_luan = "Đủ"
            phu = (f"Đủ sau khi bỏ {so_nguyen(k.rows_duplicate)} dòng trùng y hệt"
                   if k.rows_duplicate else None)
        else:
            sai = min((k.rows_bronze - k.rows_file, chuan_hoa - ky_vong,
                       phan_tich - chuan_hoa), key=lambda x: (x == 0, x))
            ket_luan = "Thiếu" if sai < 0 else "Thừa"
            phu = (f"Gốc → Chuẩn hoá lệch {so_nguyen(abs(chuan_hoa - ky_vong))} dòng"
                   if chuan_hoa != ky_vong else None)
        sheet = sheet_so.get(sheet_bang.get(table.name, ""))
        o = [table.label,
             {"v": k.rows_file, **({"mo": {"sheet": sheet}} if sheet else {})},
             {"v": k.rows_bronze, "mo": _mo_bang(ctx, table, "bronze")},
             {"v": chuan_hoa, "mo": _mo_bang(ctx, table, "silver")},
             {"v": phan_tich, "mo": _mo_bang(ctx, table, "gold")},
             k.rows_duplicate]
        hang = {"o": o, "ket_luan": ket_luan, "phu": table.name,
                "mo": _mo_bang(ctx, table, "gold")}
        if phu:
            hang["ket_luan_phu"] = phu
        dong.append(hang)
        for i, v in enumerate((k.rows_file, k.rows_bronze, chuan_hoa, phan_tich,
                               k.rows_duplicate)):
            tong[i] += v
    return {
        "ma": "so_dong", "tieu_de": TIEU_DE["so_dong"],
        "cot": [{"t": "Bảng"}, {"t": "Tách từ tệp gốc", "r": True}, {"t": "Gốc", "r": True},
                {"t": "Chuẩn hoá", "r": True}, {"t": "Phân tích", "r": True},
                {"t": "Dòng trùng đã bỏ", "r": True}, {"t": "Kết luận"}],
        "dong": dong, "tong": ["Tổng", *tong, None],
    }


def _the_tong(ctx: LoadContext, goc: dict, db: dict) -> dict:
    """b) Tổng mọi cột tiền của từng bảng số liệu."""
    dong = []
    for table in sorted((t for t in ctx.form.tables if t.cot_tien and not t.is_dim),
                        key=lambda t: t.name):
        cot = [c.name for c in table.cot_tien]
        tep, trong_db = _tong(goc[table.name], cot), _tong(db[table.name], cot)
        dong.append({"o": [table.label, so(tep), so(trong_db), so(trong_db - tep)],
                     "ket_luan": "Đúng" if tep == trong_db else "Lệch",
                     "mo": _mo_bang(ctx, table, "gold")})
    return {
        "ma": "tong", "tieu_de": TIEU_DE["tong"],
        "cot": [{"t": "Bảng"}, {"t": "Tổng theo tệp gốc", "r": True},
                {"t": "Tổng trong database", "r": True}, {"t": "Lệch", "r": True},
                {"t": "Kết luận"}],
        "dong": dong,
    }


def _ma_tran_tien(ctx: LoadContext, goc: dict, db: dict) -> dict:
    """c) Ma trận số dòng và tổng tiền theo (bảng, cách chia, nhóm, cột tiền)."""
    ten_khoan: dict[str, str] = {}
    for table in ctx.form.tables:
        if table.is_dim and "ma_khoan_cp" in table.column_names \
                and "ten_khoan" in table.column_names:
            for d in goc[table.name]:
                if d["ma_khoan_cp"] is not None and d["ten_khoan"] is not None:
                    ten_khoan.setdefault(str(d["ma_khoan_cp"]), str(d["ten_khoan"]))

    bang: dict[str, dict] = {}
    thu_tu: list[str] = []
    co_lech = False
    for table in ctx.form.tables_hien_thi:
        if table.is_dim or not table.cot_tien:
            continue
        cot = [c.name for c in table.cot_tien]
        chia: dict[str, dict] = {}
        for ten_chia in CHIA_THEO:
            if ten_chia not in table.column_names:
                continue
            nhom: dict[str, dict] = defaultdict(lambda: {
                "tep": 0, "db": 0,
                "tien_tep": defaultdict(lambda: KHONG), "tien_db": defaultdict(lambda: KHONG)})
            for phia, dong in (("tep", goc[table.name]), ("db", db[table.name])):
                for d in dong:
                    khoa = "" if d[ten_chia] is None else str(d[ten_chia])
                    nhom[khoa][phia] += 1
                    for c in cot:
                        if d.get(c) is not None:
                            nhom[khoa][f"tien_{phia}"][c] += Decimal(d[c])
            for muc in nhom.values():
                if muc["tep"] != muc["db"] or any(
                        muc["tien_tep"][c] != muc["tien_db"][c] for c in cot):
                    co_lech = True
            chia[ten_chia] = {k: {"tep": v["tep"], "db": v["db"],
                                  "tien_tep": {c: str(v["tien_tep"][c]) for c in cot},
                                  "tien_db": {c: str(v["tien_db"][c]) for c in cot}}
                              for k, v in nhom.items()}
        # jsonb không giữ thứ tự khoá, nên thứ tự bảng và cách chia cất riêng.
        bang[table.name] = {"ten": table.label,
                            "cot": [{"v": c.name, "t": c.label} for c in table.cot_tien],
                            "chia": chia, "thu_tu_chia": list(chia)}
        thu_tu.append(table.name)
    return {"ma": "tien_theo_nhom", "bang": bang, "thu_tu": thu_tu, "ten_khoan": ten_khoan,
            "lech": co_lech, "nam": ctx.nam}


def dung_the_tien(ma_tran: dict, *, bang: str | None, cot: str | None,
                  chia_theo: str | None) -> dict:
    """Dựng thẻ c) từ ma trận đã cất, theo lựa chọn Bảng · Cột tiền · Chia theo.

    Đổi bảng thì cột tiền về cột đầu; Khoản mục chỉ có ở bảng có cột đó.
    """
    cac_bang = ma_tran.get("bang", {})
    the = {"ma": "tien_theo_nhom", "tieu_de": TIEU_DE["tien_theo_nhom"], "cot": [],
           "dong": [], "tuy_chon": []}
    if not cac_bang:
        return the
    thu_tu = ma_tran.get("thu_tu") or list(cac_bang)
    bang = bang if bang in cac_bang else thu_tu[0]
    muc = cac_bang[bang]
    thu_tu_chia = muc.get("thu_tu_chia") or list(muc["chia"])
    lua_cot = [{"v": c["v"], "t": c["t"]} for c in muc["cot"]]
    if len(lua_cot) > 1:
        lua_cot.append({"v": TAT_CA, "t": NHAN_TAT_CA})
    gia_tri_cot = [c["v"] for c in lua_cot]
    cot = cot if cot in gia_tri_cot else gia_tri_cot[0]
    chia_theo = chia_theo if chia_theo in muc["chia"] else thu_tu_chia[0]
    cong = [c["v"] for c in muc["cot"]] if cot == TAT_CA else [cot]

    the["tuy_chon"] = [
        {"ten": "bang", "nhan": "Bảng", "gia_tri": bang, "mac": thu_tu[0],
         "lua_chon": [{"v": k, "t": cac_bang[k]["ten"]} for k in thu_tu]},
        {"ten": "cot", "nhan": "Cột tiền", "gia_tri": cot, "mac": gia_tri_cot[0],
         "lua_chon": lua_cot},
        {"ten": "chia_theo", "nhan": "Chia theo", "gia_tri": chia_theo,
         "mac": thu_tu_chia[0],
         "lua_chon": [{"v": k, "t": CHIA_THEO[k]} for k in thu_tu_chia]},
    ]
    the["cot"] = [{"t": CHIA_THEO[chia_theo]}, {"t": "Số dòng theo tệp gốc", "r": True},
                  {"t": "Số dòng trong database", "r": True},
                  {"t": "Tổng theo tệp gốc", "r": True},
                  {"t": "Tổng trong database", "r": True}, {"t": "Lệch", "r": True},
                  {"t": "Kết luận"}]

    def _thu_tu(k: str):
        return (k == "", int(k) if k.isdigit() else 0, k)

    tong = [0, 0, KHONG, KHONG]
    nam = ma_tran.get("nam")
    for khoa in sorted(muc["chia"][chia_theo], key=_thu_tu):
        v = muc["chia"][chia_theo][khoa]
        tien_tep = sum((Decimal(v["tien_tep"][c]) for c in cong), KHONG)
        tien_db = sum((Decimal(v["tien_db"][c]) for c in cong), KHONG)
        khop = v["tep"] == v["db"] and tien_tep == tien_db
        if chia_theo == "ky_thang":
            nhan = f"Tháng {khoa}" if khoa else "(trống)"
            mo = {"ky": int(khoa)} if khoa.isdigit() else None
        else:
            nhan = khoa or "(trống)"
            mo = {"tim": khoa} if khoa else None
        hang = {"o": [nhan, v["tep"], v["db"], so(tien_tep), so(tien_db),
                      so(tien_db - tien_tep)],
                "ket_luan": "Đúng" if khop else "Lệch"}
        if chia_theo == "ma_khoan_cp" and khoa in ma_tran.get("ten_khoan", {}):
            hang["phu"] = ma_tran["ten_khoan"][khoa]
        if mo is not None:
            hang["mo"] = {"bang": bang, "lop": "gold", **({"nam": nam} if nam else {}), **mo}
        the["dong"].append(hang)
        tong[0] += v["tep"]
        tong[1] += v["db"]
        tong[2] += tien_tep
        tong[3] += tien_db
    the["tong"] = ["Tổng", tong[0], tong[1], so(tong[2]), so(tong[3]),
                   so(tong[3] - tong[2]), None]
    return the


def _the_ma(ctx: LoadContext, goc: dict, db: dict) -> dict:
    """d) Đếm giá trị khác nhau của các mã; mã thiếu trong danh mục; mã nhiều tên."""
    the = {"ma": "ma", "tieu_de": TIEU_DE["ma"],
           "cot": [{"t": "Nội dung"}, {"t": "Theo tệp gốc", "r": True},
                   {"t": "Trong database", "r": True}, {"t": "Kết luận"}],
           "dong": []}
    co = {t.name for t in ctx.form.tables}

    def khac_nhau(dong: list[dict], cot: str) -> set:
        return {d[cot] for d in dong if d.get(cot) is not None}

    def them(noi_dung: str, tep, trong_db, khop: bool) -> None:
        the["dong"].append({"o": [noi_dung, tep, trong_db],
                            "ket_luan": "Khớp" if khop else "Lệch"})

    if "fact_ket_qua_kd" in co:
        g, d = goc["fact_ket_qua_kd"], db["fact_ket_qua_kd"]
        thang_g, thang_d = sorted(khac_nhau(g, "ky_thang")), sorted(khac_nhau(d, "ky_thang"))

        def ds_thang(ds):
            return f"{len(ds)} (tháng {', '.join(str(x) for x in ds)})" if ds else "0"

        them("Số tháng trong Kết quả kinh doanh", ds_thang(thang_g), ds_thang(thang_d),
             thang_g == thang_d)
        for cot, nhan in (("ma_khach", "Số khách hàng trong Kết quả kinh doanh"),
                          ("ma_nhom_kd", "Số nhóm kinh doanh trong Kết quả kinh doanh")):
            a, b = khac_nhau(g, cot), khac_nhau(d, cot)
            them(nhan, len(a), len(b), a == b)
    if "fact_chi_phi" in co:
        g, d = goc["fact_chi_phi"], db["fact_chi_phi"]
        for cot, nhan in (("ma_khach", "Số khách hàng trong Chi phí"),
                          ("ma_khoan_cp", "Số khoản mục trong Chi phí")):
            a, b = khac_nhau(g, cot), khac_nhau(d, cot)
            them(nhan, len(a), len(b), a == b)
    if "dim_khach_hang" in co:
        g, d = goc["dim_khach_hang"], db["dim_khach_hang"]
        a, b = khac_nhau(g, "ma_khach"), khac_nhau(d, "ma_khach")
        them("Số mã khách hàng trong Danh mục khách hàng",
             f"{so_nguyen(len(a))} mã ({so_nguyen(len(g))} dòng)",
             f"{so_nguyen(len(b))} mã ({so_nguyen(len(d))} dòng)", a == b)
    if "dim_khoan_cp" in co:
        g, d = goc["dim_khoan_cp"], db["dim_khoan_cp"]
        a, b = khac_nhau(g, "ma_khoan_cp"), khac_nhau(d, "ma_khoan_cp")
        them("Số khoản mục trong Danh mục chi phí", len(a), len(b), a == b)

    # Hai dòng chỉ ghi nhận (QT-14): không chặn nạp.
    if "dim_khach_hang" in co and ("fact_ket_qua_kd" in co or "fact_chi_phi" in co):
        danh_muc = khac_nhau(goc["dim_khach_hang"], "ma_khach")
        thieu: dict[str, dict] = {}
        for ten_bang in ("fact_ket_qua_kd", "fact_chi_phi"):
            for d in goc.get(ten_bang, []):
                ma = d.get("ma_khach")
                if ma is None or ma in danh_muc:
                    continue
                muc = thieu.setdefault(ma, {"ten": None, "thang": set()})
                if d.get("ten_khach") and not muc["ten"]:
                    muc["ten"] = d["ten_khach"]
                if d.get("ky_thang") is not None:
                    muc["thang"].add(d["ky_thang"])
        mo_ta = "; ".join(_mo_ta_ma_thieu(ma, v) for ma, v in sorted(thieu.items()))
        _ghi_nhan(the,
                  "Mã khách hàng có trong số liệu nhưng không có trong Danh mục khách hàng",
                  mo_ta, len(thieu))

        ten_theo_ma: dict[str, list[str]] = {}
        for d in goc["dim_khach_hang"]:
            if d.get("ma_khach") is None or d.get("ten_khach") is None:
                continue
            ds = ten_theo_ma.setdefault(d["ma_khach"], [])
            if d["ten_khach"] not in ds:
                ds.append(d["ten_khach"])
        nhieu = {m: t for m, t in ten_theo_ma.items() if len(t) > 1}
        _ghi_nhan(the, "Mã khách hàng có nhiều tên trong Danh mục khách hàng",
                  "; ".join(f"{m}: {' / '.join(t)}" for m, t in sorted(nhieu.items())),
                  len(nhieu))
    return the


def _mo_ta_ma_thieu(ma: str, v: dict) -> str:
    """"BP-TTXK-N04 · TARGET AUSTRALIA PTY. LTD. (tháng 6, 7)"."""
    ra = ma + (f" · {v['ten']}" if v["ten"] else "")
    if v["thang"]:
        ra += f" (tháng {', '.join(str(t) for t in sorted(v['thang']))})"
    return ra


def _ghi_nhan(the: dict, noi_dung: str, mo_ta: str, so: int) -> None:
    """Dòng chỉ ghi nhận: có thì nhãn "Ghi nhận", không có thì "0" và "Khớp"."""
    if so:
        the["dong"].append({"o": [noi_dung, mo_ta, so], "ket_luan": "Ghi nhận"})
    else:
        the["dong"].append({"o": [noi_dung, "0", 0], "ket_luan": "Khớp"})


def _the_truoc_sau(ctx: LoadContext, truoc: dict, goc: dict) -> dict:
    """e) Đủ 12 tháng của năm: số dòng trước / sau lần nạp, cách ghi, kết luận."""
    bang = [t for t in ctx.form.tables_hien_thi
            if not t.is_dim and t.cot_nam is not None and t.partition_by]
    the = {"ma": "truoc_sau", "tieu_de": TIEU_DE["truoc_sau"].format(nam=ctx.nam or ""),
           "cot": [{"t": "Tháng"}, {"t": "Có trong tệp"},
                   {"t": "Số dòng trước lần nạp", "r": True},
                   {"t": "Số dòng sau lần nạp", "r": True}, {"t": "Cách ghi"},
                   {"t": "Kết luận"}],
           "dong": [], "cac_bang": [t.label for t in bang]}
    if not bang:
        return the
    sau = {t.name: _theo_thang_db(ctx, t) for t in bang}
    trong_tep = {t.name: defaultdict(int) for t in bang}
    for t in bang:
        cot = t.partition_column.name
        for d in goc[t.name]:
            if d[cot] is not None:
                trong_tep[t.name][str(d[cot])] += 1

    for thang in range(1, 13):
        ky = str(thang)
        co = any(trong_tep[t.name].get(ky) for t in bang)
        so_truoc = [truoc.get(t.name, {}).get(ky, {}).get("so_dong", 0) for t in bang]
        so_sau = [sau[t.name].get(ky, {}).get("so_dong", 0) for t in bang]
        if co:
            cach_ghi = "Ghi đè" if any(so_truoc) else "Ghi thêm"
            dat = all(sau[t.name].get(ky, {}).get("so_dong", 0) == trong_tep[t.name].get(ky, 0)
                      for t in bang)
            ket_luan = "Đúng" if dat else "Lệch"
        else:
            cach_ghi = "Không đụng tới"
            giu = all(
                _so_tong(truoc.get(t.name, {}), ky) == _so_tong(sau[t.name], ky)
                for t in bang)
            ket_luan = "Giữ nguyên" if giu else "Lệch"
        hang = {"o": [f"Tháng {thang}/{ctx.nam}", "Có" if co else "Không",
                      " / ".join(so_nguyen(x) for x in so_truoc),
                      " / ".join(so_nguyen(x) for x in so_sau), cach_ghi],
                "ket_luan": ket_luan}
        if any(so_sau):
            hang["mo"] = _mo_bang(ctx, bang[0], "gold", ky=thang)
        the["dong"].append(hang)
    return the


def _so_tong(theo_ky: dict, ky: str) -> tuple[int, Decimal]:
    muc = theo_ky.get(ky, {})
    return muc.get("so_dong", 0), Decimal(muc.get("tong", "0"))


def _cau_b4(the: dict, lech: list[str]) -> str:
    """Câu của bước B4."""
    if lech:
        return "Có chênh lệch ở: " + "; ".join(
            TIEU_DE[m].format(nam="") if m in TIEU_DE else m for m in lech) + "."
    tong = the.get("tong", {}).get("dong", [])
    chi_tiet = "; ".join(f"{d['o'][0]} {so_tien(Decimal(str(d['o'][1])))}" for d in tong)
    return ("Lệch 0 ở mọi tháng, mọi cột tiền; số tháng, khách hàng, nhóm, khoản mục khớp. "
            f"Tổng cả bảng lệch 0 ở {len(tong)}/{len(tong)} bảng ({chi_tiet}).")


def cot_tong_bang(table: FormTable) -> list[str]:
    """Cột cộng vào tổng của bảng — dùng chung với bước Kiểm tra tệp."""
    return cot_cong_tong(table)


def dung_the_chieu(ma_tran: dict, *, chia_theo: str | None, trang: int, moi: int) -> dict:
    """Dựng thẻ "Đối chiếu số lượng theo {chia theo}" (HQ-MAU-GC) theo trang."""
    from . import doi_chieu_gc

    return doi_chieu_gc.dung_the_chieu(ma_tran, chia_theo=chia_theo, trang=trang, moi=moi)
