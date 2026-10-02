"""Sinh DDL từ khai báo bảng

Toàn bộ mô-đun này là **hàm thuần**: nhận đối tượng khai báo, trả chuỗi SQL.
Không mở kết nối, không đọc biến môi trường, không đọc giờ hệ thống. Nhờ vậy
cùng một khai báo luôn sinh ra đúng một chuỗi SQL, đọc được bằng mắt trước khi
chạy.

Ba lớp có cùng các cột nghiệp vụ: gốc giữ văn bản y như tệp, chuẩn hoá và phân
tích mang kiểu đã ép. Lớp phân tích là bản chép lớp chuẩn hoá — không nối khoá,
không thêm dòng.
"""

from __future__ import annotations

from .schema import Form, FormColumn, FormTable


def bieu_thuc_khoa(table: FormTable) -> str:
    """Biểu thức đánh chỉ mục cho khoá nghiệp vụ.

    Cột khoá được phép để trống thì quy về chuỗi rỗng trước khi so. Lý do: trong
    PostgreSQL, chỉ mục duy nhất coi hai NULL là **khác nhau**, nên hai dòng
    cùng thiếu giá trị định danh vẫn lọt qua được. Quy về chuỗi rỗng bịt khe
    đó, và chạy được trên PostgreSQL 14 chứ không cần `NULLS NOT DISTINCT` của
    bản 15.

    Chỉ quy với cột kiểu văn bản. Ép cột ngày sang văn bản
    phụ thuộc DateStyle nên PostgreSQL không cho dùng trong chỉ mục.
    """
    phan = []
    for ten in table.business_key:
        col = table.column(ten)
        van_ban = col.handler.silver_sql_type == "text"
        phan.append(ten if col.required or not van_ban else f"coalesce({ten}, '')")
    return ", ".join(phan)


def _cot(ten: str, kieu: str, them: str = "") -> str:
    return f"    {ten:<26} {kieu}{them}"


def _khoi(ten_bang: str, dong: list[str], ghi_chu: str = "") -> str:
    than = ",\n".join(dong)
    dau = f"-- {ghi_chu}\n" if ghi_chu else ""
    return f"{dau}CREATE TABLE {ten_bang} (\n{than}\n);"


# --------------------------------------------------------------------------- #
#  Lớp gốc — bronze
# --------------------------------------------------------------------------- #


def ddl_bronze(table: FormTable) -> str:
    """Lưu y nguyên như tệp: mọi cột nghiệp vụ là `text`, không ép kiểu, không
    sửa, không suy đoán."""
    dong = [_cot("row_id", "bigserial", "   PRIMARY KEY")]
    dong += [_cot(c.name, "text") for c in table.columns]
    dong += [
        _cot("domain_id", "smallint", "    NOT NULL REFERENCES ctl.domain(domain_id)"),
        _cot("load_id", "bigint", "      NOT NULL REFERENCES ctl.load(load_id)"),
        _cot("batch_id", "bigint", "      NOT NULL REFERENCES ctl.batch(batch_id)"),
        _cot("source_sheet", "text", "        NOT NULL"),
        _cot("source_row", "int", "         NOT NULL"),
        _cot("loaded_at", "timestamptz", " NOT NULL"),
        _cot("row_hash", "char(64)", "    NOT NULL"),
        "    UNIQUE (load_id, source_sheet, source_row)",
    ]
    sql = _khoi(f"bronze.{table.name}", dong, f"{table.label} — dữ liệu gốc, y nguyên như tệp")
    sql += f"\n\nCREATE INDEX bronze_{table.name}_batch_idx ON bronze.{table.name} (batch_id);"
    sql += f"\nCREATE INDEX bronze_{table.name}_hash_idx ON bronze.{table.name} (row_hash);"
    return sql


# --------------------------------------------------------------------------- #
#  Lớp chuẩn hoá — silver
# --------------------------------------------------------------------------- #


def ddl_silver(table: FormTable) -> str:
    """Đã ép kiểu, có khoá thay thế, có phiên bản theo lô.

    Ràng buộc duy nhất trên khoá nghiệp vụ đặt ở cơ sở dữ liệu, không phụ thuộc
    mã nguồn — đây là lớp bảo vệ chống gộp dòng làm mất số liệu.
    """
    sk = table.sk_column
    dong = [_cot(sk, "bigint", "      GENERATED ALWAYS AS IDENTITY PRIMARY KEY")]
    dong += [_cot(c.name, c.silver_sql_type, "  NOT NULL" if c.required else "")
             for c in table.columns]
    dong += [
        _cot("domain_id", "smallint", "    NOT NULL REFERENCES ctl.domain(domain_id)"),
        _cot("load_id", "bigint", "      NOT NULL REFERENCES ctl.load(load_id)"),
        _cot("batch_id", "bigint", "      NOT NULL REFERENCES ctl.batch(batch_id)"),
        _cot("bronze_id", "bigint", f"      NOT NULL REFERENCES bronze.{table.name}(row_id)"),
        _cot("source_sheet", "text", "        NOT NULL"),
        _cot("source_row", "int", "         NOT NULL"),
        _cot("row_hash", "char(64)", "    NOT NULL"),
        _cot("valid_from", "timestamptz", " NOT NULL"),
        _cot("valid_to", "timestamptz"),
        _cot("is_current", "boolean", "     NOT NULL DEFAULT true"),
        _cot("superseded_by_batch_id", "bigint", "      REFERENCES ctl.batch(batch_id)"),
        _cot("supersedes_sk", "bigint"),
    ]
    sql = _khoi(f"silver.{table.name}", dong,
                f"{table.label} — đã ép kiểu, có phiên bản theo lô")
    if table.business_key:
        sql += (
            f"\n\n-- Khoá nghiệp vụ dùng để tra cứu, **không** duy nhất: một dòng trong tệp\n"
            f"-- là một dòng ở đây, kể cả khi cột khoá để trống nên hai dòng trùng khoá.\n"
            f"CREATE INDEX silver_{table.name}_bk_idx\n"
            f"    ON silver.{table.name} (domain_id, {bieu_thuc_khoa(table)}) WHERE is_current;"
        )
    sql += (
        f"\nCREATE INDEX silver_{table.name}_batch_idx ON silver.{table.name} (batch_id);"
        f"\nCREATE INDEX silver_{table.name}_bronze_idx ON silver.{table.name} (bronze_id);"
    )
    if table.partition_by:
        cot_pk = ", ".join(table.partition_by)
        sql += (
            f"\nCREATE INDEX silver_{table.name}_part_idx\n"
            f"    ON silver.{table.name} (domain_id, {cot_pk}) WHERE is_current;"
        )
    return sql


# --------------------------------------------------------------------------- #
#  Lớp phân tích — gold
# --------------------------------------------------------------------------- #


def ddl_gold(table: FormTable) -> str:
    """Bản chép các dòng hiện hành của lớp chuẩn hoá, kèm cột truy vết."""
    sk = table.sk_column
    dong = [_cot(sk, "bigint", "      GENERATED ALWAYS AS IDENTITY PRIMARY KEY")]
    dong += [_cot(c.name, c.silver_sql_type, "  NOT NULL" if c.required else "")
             for c in table.columns]
    dong += [
        _cot("domain_id", "smallint", "    NOT NULL REFERENCES ctl.domain(domain_id)"),
        _cot("silver_sk", "bigint", f"      NOT NULL REFERENCES silver.{table.name}({sk})"),
        _cot("load_id", "bigint", "      NOT NULL REFERENCES ctl.load(load_id)"),
        _cot("batch_id", "bigint", "      NOT NULL REFERENCES ctl.batch(batch_id)"),
        _cot("source_sheet", "text", "        NOT NULL"),
        _cot("source_row", "int", "         NOT NULL"),
        _cot("is_current", "boolean", "     NOT NULL DEFAULT true"),
    ]
    sql = _khoi(f"gold.{table.name}", dong, f"{table.label} — bản chép lớp chuẩn hoá")
    sql += (
        f"\n\nCREATE UNIQUE INDEX gold_{table.name}_silver_idx\n"
        f"    ON gold.{table.name} (silver_sk);"
        f"\nCREATE INDEX gold_{table.name}_batch_idx ON gold.{table.name} (batch_id);"
    )
    if table.partition_by:
        cot_pk = ", ".join(table.partition_by)
        sql += (
            f"\nCREATE INDEX gold_{table.name}_part_idx\n"
            f"    ON gold.{table.name} (domain_id, {cot_pk}) WHERE is_current;"
        )
    return sql


# --------------------------------------------------------------------------- #
#  Tầng phục vụ — analytics
# --------------------------------------------------------------------------- #


def ddl_analytics(table: FormTable) -> str:
    """View chỉ đọc — tầng duy nhất công cụ ngoài được chạm.

    Đã lọc `is_current`, nên công cụ đọc thẳng không bao giờ đếm trùng dòng
    của các phiên bản cũ.
    """
    chon = [f"t.{c.name}" for c in table.columns]
    chon += ["t.domain_id", "t.load_id", "t.batch_id", "t.source_sheet", "t.source_row"]
    than = ",\n           ".join(chon)
    return (
        f"-- {table.label}\n"
        f"CREATE VIEW analytics.v_{table.name} AS\n"
        f"    SELECT {than}\n"
        f"      FROM gold.{table.name} t\n"
        f"     WHERE t.is_current;"
    )


# --------------------------------------------------------------------------- #
#  Ghép cả khai báo
# --------------------------------------------------------------------------- #


def ddl_form(form: Form) -> str:
    """Toàn bộ DDL của một khai báo, theo thứ tự phụ thuộc: danh mục trước."""
    phan: list[str] = [
        "-- " + "=" * 75,
        f"--  Khai báo {form.code} v{form.version} — {form.label}",
        "--  TỆP NÀY SINH TỰ ĐỘNG TỪ khai_bao/forms/. Không sửa bằng tay.",
        f"--  Nguồn: mã kiểm tra YAML {form.yaml_sha256[:16]}",
        "-- " + "=" * 75,
        "",
    ]
    thu_tu = form.tables_theo_thu_tu
    for nhan, sinh in (("lớp gốc", ddl_bronze), ("lớp chuẩn hoá", ddl_silver),
                       ("lớp phân tích", ddl_gold), ("tầng phục vụ", ddl_analytics)):
        phan.append(f"-- ---------- {nhan} " + "-" * (60 - len(nhan)))
        phan.append("")
        for table in thu_tu:
            phan.append(sinh(table))
            phan.append("")
    return "\n".join(phan).rstrip() + "\n"


# --------------------------------------------------------------------------- #
#  Nâng cấp tại chỗ — dùng cho `manage makemigration`
# --------------------------------------------------------------------------- #
#
#  Bốn hàm dưới đây sinh DDL cho **chênh lệch**, không sinh lại từ đầu. Vẫn là
#  hàm thuần như cả mô-đun: người dùng đọc được toàn văn câu lệnh trên màn hình
#  xem trước rồi mới bấm áp dụng.
#
#  Cột thêm vào bảng đã có dữ liệu **luôn cho phép rỗng ở cơ sở dữ liệu**, kể cả
#  khi khai báo ghi `required: true`. Lý do: các dòng cũ không có giá trị nào để
#  điền, và ép `NOT NULL` sẽ làm cả bước nâng cấp đổ. Tính bắt buộc vẫn được giữ
#  ở đường nạp — tệp có dòng thiếu giá trị bị từ chối như thường.


def ddl_bang_moi(table: FormTable) -> str:
    """Toàn bộ bốn lớp của một bảng mới."""
    return "\n\n".join([ddl_bronze(table), ddl_silver(table), ddl_gold(table),
                        ddl_analytics(table)])


def ddl_them_cot(table: FormTable, col: FormColumn) -> str:
    """Thêm một cột vào cả ba lớp. View phục vụ dựng lại **một lần** sau khi đã
    thêm đủ mọi cột mới (`ddl_dung_lai_view`) — dựng sau từng cột thì view nhắc
    tới cột chưa kịp thêm."""
    cau = [
        f"ALTER TABLE bronze.{table.name} ADD COLUMN {col.name} text;",
        f"ALTER TABLE silver.{table.name} ADD COLUMN {col.name} {col.silver_sql_type};",
        f"ALTER TABLE gold.{table.name}   ADD COLUMN {col.name} {col.silver_sql_type};",
    ]
    return "\n".join(cau)


def ddl_bo_bat_buoc(table: FormTable, col: FormColumn) -> str:
    """Cột khai là không bắt buộc mà bảng còn `NOT NULL` — gỡ ở hai lớp có kiểu."""
    return "\n".join(
        f"ALTER TABLE {lop}.{table.name} ALTER COLUMN {col.name} DROP NOT NULL;"
        for lop in ("silver", "gold"))


def ddl_dung_lai_view(table: FormTable) -> str:
    """View ở tầng phục vụ liệt kê cột theo tên nên phải dựng lại khi cột đổi."""
    return f"DROP VIEW IF EXISTS analytics.v_{table.name};\n" + ddl_analytics(table)


def ddl_dung_lai_khoa(table: FormTable) -> str:
    """Khoá nghiệp vụ đổi ⇒ dựng lại chỉ mục tra cứu ở lớp chuẩn hoá."""
    return "\n".join([
        f"DROP INDEX IF EXISTS silver.silver_{table.name}_bk_idx;",
        f"CREATE INDEX silver_{table.name}_bk_idx",
        f"    ON silver.{table.name} (domain_id, {bieu_thuc_khoa(table)}) WHERE is_current;",
    ])
