"""So khai báo bảng với schema thật, và **xếp hạng rủi ro** từng thay đổi.

`manage makemigration` sinh bước nâng cấp từ đây. Ba mức:

    an_toan        thêm bảng, thêm cột, sửa nhãn — không dòng nào bị ảnh hưởng
    can_kiem_tra   dựng lại khoá nghiệp vụ, dựng lại view — chạy được nhưng
                   có thể đổ nếu dữ liệu đang có vi phạm ràng buộc mới
    bi_chan        xoá cột, đổi kiểu cột trên bảng **đang có dữ liệu**

Có thay đổi `bi_chan` thì không sinh bước nâng cấp nào. Muốn đổi thật thì
chuyển dữ liệu sang bảng mới — một việc có kế hoạch, không phải một lệnh.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from psycopg import sql

from ..db import sql as q
from .ddl import (
    ddl_bang_moi,
    ddl_bo_bat_buoc,
    ddl_dung_lai_khoa,
    ddl_dung_lai_view,
    ddl_them_cot,
)
from .schema import Form, FormTable

AN_TOAN = "an_toan"
CAN_KIEM_TRA = "can_kiem_tra"
BI_CHAN = "bi_chan"

# Cột do hệ thống sinh ở lớp chuẩn hoá — không phải cột nghiệp vụ, không đem so.
COT_HE_THONG = {
    "domain_id", "load_id", "batch_id", "bronze_id", "source_sheet", "source_row",
    "row_hash", "valid_from", "valid_to", "is_current", "superseded_by_batch_id",
    "supersedes_sk", "silver_sk", "row_id",
}


@dataclass(frozen=True)
class ThayDoi:
    loai: str
    muc: str
    bang: str
    mo_ta: str
    cot: str | None = None
    ly_do: str | None = None
    ddl: str = ""


@dataclass
class KeHoach:
    """Toàn bộ chênh lệch giữa một khai báo và schema thật."""

    form_code: str
    thay_doi: list[ThayDoi] = field(default_factory=list)

    @property
    def bi_chan(self) -> list[ThayDoi]:
        return [t for t in self.thay_doi if t.muc == BI_CHAN]

    @property
    def can_ddl(self) -> list[ThayDoi]:
        return [t for t in self.thay_doi if t.ddl]

    def sinh_ddl(self, ghi_chu: str = "") -> str:
        phan = [
            "-- " + "=" * 75,
            f"--  Nâng cấp bảng theo khai báo {self.form_code}",
            "--  TỆP NÀY SINH TỰ ĐỘNG bởi lệnh manage makemigration. Không sửa bằng tay.",
        ]
        if ghi_chu:
            phan.append(f"--  {ghi_chu}")
        phan += ["-- " + "=" * 75, ""]
        for t in self.can_ddl:
            phan += [f"-- {t.mo_ta}", t.ddl, ""]
        return "\n".join(phan).rstrip() + "\n"


# --------------------------------------------------------------------------- #
#  Đọc schema thật
# --------------------------------------------------------------------------- #


def cot_dang_co(conn, schema: str, ten_bang: str) -> dict[str, str]:
    """`{tên cột: kiểu SQL đầy đủ}` — `format_type` cho đúng `numeric(18,2)`."""
    hang = q.query(
        conn,
        """
        SELECT a.attname                                   AS ten,
               pg_catalog.format_type(a.atttypid, a.atttypmod) AS kieu
          FROM pg_attribute a
          JOIN pg_class c     ON c.oid = a.attrelid
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = %s AND c.relname = %s
               AND a.attnum > 0 AND NOT a.attisdropped
         ORDER BY a.attnum
        """,
        (schema, ten_bang),
    )
    return {r["ten"]: r["kieu"] for r in hang}


def cot_bat_buoc(conn, schema: str, ten_bang: str) -> set[str]:
    """Cột đang mang `NOT NULL`."""
    hang = q.query(
        conn,
        """
        SELECT a.attname AS ten
          FROM pg_attribute a
          JOIN pg_class c     ON c.oid = a.attrelid
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = %s AND c.relname = %s
               AND a.attnum > 0 AND NOT a.attisdropped AND a.attnotnull
        """,
        (schema, ten_bang),
    )
    return {r["ten"] for r in hang}


def so_dong(conn, schema: str, ten_bang: str) -> int:
    cau = sql.SQL("SELECT count(*) FROM {}").format(q.table_identifier(schema, ten_bang))
    return int(q.scalar(conn, cau) or 0)


def khoa_dang_co(conn, ten_bang: str) -> str:
    """Định nghĩa chỉ mục khoá nghiệp vụ đang có ở lớp chuẩn hoá, hoặc chuỗi rỗng."""
    return q.scalar(
        conn,
        "SELECT indexdef FROM pg_indexes "
        "WHERE schemaname = 'silver' AND indexname = %s",
        (f"silver_{ten_bang}_bk_idx",),
    ) or ""


# --------------------------------------------------------------------------- #
#  So sánh
# --------------------------------------------------------------------------- #


def so_sanh(conn, form: Form) -> KeHoach:
    """Chênh lệch giữa khai báo `form` và schema thật đang chạy."""
    ke = KeHoach(form_code=form.code)
    # Bảng mới phải dựng theo thứ tự phụ thuộc: danh mục trước, số liệu sau.
    for table in form.tables_theo_thu_tu:
        dang_co = cot_dang_co(conn, "silver", table.name)
        if not dang_co:
            ke.thay_doi.append(ThayDoi(
                loai="them_bang", muc=AN_TOAN, bang=table.name,
                mo_ta=f"Tạo mới bảng {table.label} ({table.name}) ở cả bốn lớp",
                ddl=ddl_bang_moi(table),
            ))
            continue
        _so_sanh_bang(conn, ke, table, dang_co)
    _bang_thua(conn, ke, form)
    return ke


def _so_sanh_bang(conn, ke: KeHoach, table: FormTable, dang_co: dict[str, str]) -> None:
    nghiep_vu = {t: k for t, k in dang_co.items()
                 if t not in COT_HE_THONG and t != table.sk_column}
    dem = so_dong(conn, "silver", table.name)
    co_du_lieu = dem > 0
    bat_buoc = cot_bat_buoc(conn, "silver", table.name) | cot_bat_buoc(conn, "gold", table.name)

    them_cot = False
    for col in table.columns:
        if col.name in bat_buoc and not col.required:
            # Bảng dựng từ khai báo cũ (cột khoá tự động bắt buộc) mà bước 0010
            # chạy lúc kho chưa có bản chiếu khai báo nên không gỡ được.
            ke.thay_doi.append(ThayDoi(
                loai="bo_bat_buoc", muc=AN_TOAN, bang=table.name, cot=col.name,
                mo_ta=f"Cho phép trống cột {col.label} ({col.name}) ở {table.name}",
                ddl=ddl_bo_bat_buoc(table, col),
            ))
        kieu_that = nghiep_vu.pop(col.name, None)
        if kieu_that is None:
            ke.thay_doi.append(ThayDoi(
                loai="them_cot", muc=AN_TOAN, bang=table.name, cot=col.name,
                mo_ta=f"Thêm cột {col.label} ({col.name}) vào {table.name}",
                ly_do=(f"Bảng đang có {dem:,} dòng — các dòng cũ để trống cột này"
                       .replace(",", ".")) if co_du_lieu else None,
                ddl=ddl_them_cot(table, col),
            ))
            them_cot = True
            continue
        if kieu_that.split("(")[0] != col.silver_sql_type.split("(")[0]:
            ke.thay_doi.append(ThayDoi(
                loai="doi_kieu",
                muc=BI_CHAN if co_du_lieu else CAN_KIEM_TRA,
                bang=table.name, cot=col.name,
                mo_ta=(f"Đổi kiểu cột {col.label} ({col.name}): "
                       f"{kieu_that} → {col.silver_sql_type}"),
                ly_do=(f"Bảng đang có {dem:,} dòng. Đổi kiểu có thể làm mất hoặc sai "
                       f"giá trị đã lưu, nên phải chuyển dữ liệu sang bảng mới."
                       .replace(",", ".")) if co_du_lieu
                      else "Bảng chưa có dòng nào nên đổi kiểu không mất gì.",
            ))

    if them_cot:
        ke.thay_doi.append(ThayDoi(
            loai="dung_lai_view", muc=AN_TOAN, bang=table.name,
            mo_ta=f"Dựng lại view phục vụ analytics.v_{table.name} với các cột mới",
            ddl=ddl_dung_lai_view(table),
        ))

    for thua in nghiep_vu:
        ke.thay_doi.append(ThayDoi(
            loai="xoa_cot",
            muc=BI_CHAN if co_du_lieu else CAN_KIEM_TRA,
            bang=table.name, cot=thua,
            mo_ta=f"Bỏ cột {thua} khỏi {table.name}",
            ly_do=(f"Bảng đang có {dem:,} dòng. Giá trị trong cột này sẽ mất hẳn."
                   .replace(",", ".")) if co_du_lieu
                  else "Bảng chưa có dòng nào nên bỏ cột không mất gì.",
        ))

    if table.business_key:
        dinh_nghia = khoa_dang_co(conn, table.name)
        if dinh_nghia and not _khoa_khop(dinh_nghia, table):
            ke.thay_doi.append(ThayDoi(
                loai="doi_khoa", muc=CAN_KIEM_TRA, bang=table.name,
                mo_ta=(f"Đổi khoá nghiệp vụ của {table.name} thành "
                       f"({', '.join(table.business_key)})"),
                ly_do=("Dựng lại chỉ mục duy nhất. Nếu dữ liệu đang có hai dòng trùng "
                       "theo khoá mới thì bước nâng cấp sẽ dừng và không đổi gì."),
                ddl=ddl_dung_lai_khoa(table),
            ))


def _cot_trong_chi_muc(dinh_nghia: str, ten_cot: set[str]) -> list[str]:
    """Danh sách cột theo đúng thứ tự trong một câu `CREATE INDEX`.

    PostgreSQL viết lại biểu thức khi lưu (`coalesce(ma_khach::text, '')` thành
    `COALESCE(ma_khach, ''::text)`), nên không so được bằng chuỗi. Ở đây tách
    phần trong ngoặc theo dấu phẩy ở mức ngoài cùng rồi lấy tên cột đầu tiên
    nhận ra được trong mỗi phần.
    """
    than = dinh_nghia[dinh_nghia.find("(") + 1:]
    than = than[:than.rfind(")")]
    phan, sau, muc = [], "", 0
    for ky_tu in than:
        if ky_tu == "(":
            muc += 1
        elif ky_tu == ")":
            muc -= 1
        if ky_tu == "," and muc == 0:
            phan.append(sau)
            sau = ""
        else:
            sau += ky_tu
    phan.append(sau)

    ra = []
    for p in phan:
        for tu in re.findall(r"[a-z_][a-z0-9_]*", p.lower()):
            if tu in ten_cot:
                ra.append(tu)
                break
    return ra


def _khoa_khop(dinh_nghia: str, table: FormTable) -> bool:
    """Chỉ mục đang có đã đúng danh sách và thứ tự cột khoá chưa."""
    nhan_ra = set(table.column_names) | {"domain_id"}
    mong_doi = ["domain_id", *table.business_key]
    return _cot_trong_chi_muc(dinh_nghia, nhan_ra) == mong_doi


def _bang_thua(conn, ke: KeHoach, form: Form) -> None:
    """Bảng từng thuộc khai báo này nhưng khai báo mới không còn nhắc tới."""
    khai_bao = {t.name for t in form.tables}
    hang = q.query(
        conn,
        """
        SELECT ft.name FROM ctl.form_table ft
          JOIN ctl.form f ON f.form_id = ft.form_id
         WHERE f.code = %s
        """,
        (form.code,),
    )
    for r in hang:
        if r["name"] in khai_bao:
            continue
        con_bang = bool(cot_dang_co(conn, "silver", r["name"]))
        dem = so_dong(conn, "silver", r["name"]) if con_bang else 0
        ke.thay_doi.append(ThayDoi(
            loai="xoa_bang",
            muc=BI_CHAN if dem else CAN_KIEM_TRA,
            bang=r["name"],
            mo_ta=f"Bỏ bảng {r['name']} khỏi khai báo",
            ly_do=(f"Bảng đang có {dem:,} dòng.".replace(",", ".") if dem
                   else "Bảng chưa có dòng nào."),
        ))
