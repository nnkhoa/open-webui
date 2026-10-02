"""Ghi khai báo (`khai_bao/`) vào sổ tay, rồi chiếu sang kho.

Giao diện đọc siêu dữ liệu từ cơ sở dữ liệu chứ không đọc tệp YAML, nên thẻ
dữ liệu và ngăn giải thích cột không thể lệch khỏi khai báo. Chạy lại nhiều lần
cho cùng kết quả.

Hai đích đến, khác vai:

    sổ tay (SQLite)   Sinh ra `domain_id`, `form_id`, `table_id` và giữ chúng
                      ổn định theo mã / tên qua mọi lần khởi động.
    kho (PostgreSQL)  BẢN CHIẾU, chép nguyên số hiệu từ sổ tay, để sổ ghi mỗi
                      lần nạp có chỗ trỏ vào và một câu truy vấn thẳng vào kho
                      đọc được tên bảng mà không phải mở tệp SQLite.

Bộ bảng không còn trong mã nguồn bị gỡ khỏi sổ tay. Nhóm thông tin không còn trong
`domains.yaml` chuyển sang `suspended`: ẩn khỏi giao diện, dữ liệu đã nạp giữ
nguyên.

`conn_kho` là `None` khi kho chưa cấu hình. Khi đó chỉ ghi sổ tay — bản chiếu
được dựng lại ở lần kết nối kho kế tiếp, xem `chieu_lai`.
"""

from __future__ import annotations

import json

from ..db import sql as q
from ..db import sql_sotay as qs
from .loader import FormRegistry
from .schema import Form


def dong_bo(so, conn_kho, registry: FormRegistry) -> None:
    """Ghi mọi bộ bảng và nhóm thông tin, gỡ những gì không còn trong mã nguồn."""
    form_id = {form.code: _ghi_form(so, form) for form in registry.forms}
    _go_form_cu(so, list(form_id.values()))
    _ghi_domain(so, registry, form_id)
    chieu_lai(so, conn_kho)


# --------------------------------------------------------------------------- #
#  Sổ tay — nguồn chuẩn
# --------------------------------------------------------------------------- #


def _go_form_cu(so, con: list[int]) -> None:
    cho = ", ".join("?" * len(con))
    qs.execute(so, f"DELETE FROM ctl_form WHERE form_id NOT IN ({cho})", tuple(con))


def _ghi_domain(so, registry: FormRegistry, form_id: dict[str, int]) -> None:
    """Domain theo `domains.yaml`, giữ `domain_id` theo mã."""
    for d in registry.domains:
        domain_id = qs.scalar(
            so,
            """
            INSERT INTO ctl_domain (code, name, description, status)
                 VALUES (?, ?, ?, 'active')
            ON CONFLICT (code) DO UPDATE
                    SET name = excluded.name, description = excluded.description,
                        status = 'active'
              RETURNING domain_id
            """,
            (d.code, d.name, d.description),
        )
        qs.execute(so, "DELETE FROM ctl_domain_form WHERE domain_id = ?", (domain_id,))
        for thu_tu, ma in enumerate(d.cac_bo_bang, start=1):
            qs.execute(so, "INSERT INTO ctl_domain_form (domain_id, form_id, thu_tu) "
                           "VALUES (?, ?, ?)", (domain_id, form_id[ma], thu_tu))

    ma = [d.code for d in registry.domains]
    qs.execute(
        so,
        f"UPDATE ctl_domain SET status = 'suspended' "
        f" WHERE code NOT IN ({', '.join('?' * len(ma))})",
        tuple(ma))


def _ghi_form(so, form: Form) -> int:
    form_id = qs.scalar(
        so,
        """
        INSERT INTO ctl_form (code, label, description, current_version, yaml_sha256, policy)
             VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (code) DO UPDATE
                SET label = excluded.label,
                    description = excluded.description,
                    current_version = excluded.current_version,
                    yaml_sha256 = excluded.yaml_sha256,
                    policy = excluded.policy
          RETURNING form_id
        """,
        (form.code, form.label, form.description, form.version, form.yaml_sha256,
         json.dumps({
             "unknown_sheet": form.policy.unknown_sheet,
             "unknown_column": form.policy.unknown_column,
             "missing_column": form.policy.missing_column,
         })),
    )

    # Bảng trước, cột sau — cột trỏ vào table_id vừa ghi.
    theo_ten: dict[str, int] = {}
    for table in form.tables_hien_thi:
        theo_ten[table.name] = qs.scalar(
            so,
            """
            INSERT INTO ctl_form_table (form_id, name, kind, sheet, label, card_label,
                                        description, card_description, grain, business_key,
                                        merge_strategy, partition_by, order_by, display_order)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (name) DO UPDATE
                    SET form_id = excluded.form_id, kind = excluded.kind,
                        sheet = excluded.sheet, label = excluded.label,
                        card_label = excluded.card_label, description = excluded.description,
                        card_description = excluded.card_description, grain = excluded.grain,
                        business_key = excluded.business_key,
                        merge_strategy = excluded.merge_strategy,
                        partition_by = excluded.partition_by, order_by = excluded.order_by,
                        display_order = excluded.display_order
              RETURNING table_id
            """,
            (form_id, table.name, table.kind, table.sheet, table.label, table.nhan_the,
             table.description, table.card_description, table.grain,
             json.dumps(list(table.business_key), ensure_ascii=False),
             table.merge,
             json.dumps(list(table.partition_by), ensure_ascii=False),
             json.dumps(list(table.order), ensure_ascii=False),
             table.display_order),
        )

    for table in form.tables_hien_thi:
        table_id = theo_ten[table.name]
        qs.execute(so, "DELETE FROM ctl_form_column WHERE table_id = ?", (table_id,))
        for col in table.columns:
            qs.execute(
                so,
                """
                INSERT INTO ctl_form_column (table_id, name, ordinal, type, required,
                                             is_business_key, label, meaning, how, example,
                                             enum_values, role, display_width, show_in_table)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (table_id, col.name, col.ordinal, col.type, 1 if col.required else 0,
                 1 if col.is_business_key else 0, col.label, col.meaning, col.how,
                 col.example,
                 json.dumps(list(col.values), ensure_ascii=False) if col.values else None,
                 col.role, col.display_width, 1 if col.show_in_table else 0),
            )
    return form_id


def cap_dataset(so) -> list[dict]:
    """Mỗi (nhóm thông tin, bảng thuộc bộ bảng của nhóm thông tin đó) là một bộ dữ
    liệu ở màn Dữ liệu.

    Sổ tay không giữ bảng `dataset` riêng: cặp (nhóm thông tin, bảng) suy thẳng ra được
    từ `ctl_domain_form` và `ctl_form_table`. Bên kho thì cần bảng thật để truy
    vấn phân quyền theo nhóm thông tin.
    """
    return qs.query(
        so,
        """
        SELECT df.domain_id, ft.table_id,
               coalesce(ft.card_label, ft.label)             AS label,
               coalesce(ft.card_description, ft.description) AS description,
               ft.display_order
          FROM ctl_domain_form df
          JOIN ctl_domain d      ON d.domain_id = df.domain_id AND d.status = 'active'
          JOIN ctl_form_table ft ON ft.form_id = df.form_id
        """,
    )


# --------------------------------------------------------------------------- #
#  Kho — bản chiếu
# --------------------------------------------------------------------------- #


def chieu_lai(so, conn_kho) -> None:
    """Chép khai báo từ sổ tay sang kho, giữ nguyên số hiệu.

    Gọi sau mỗi lần khai báo đổi, và một lần nữa mỗi khi nối lại được kho —
    kho có thể đã tắt lúc portal khởi động, hoặc là một cơ sở dữ liệu mới vừa
    được trỏ tới.
    """
    if conn_kho is None:
        return
    _chieu_domain(so, conn_kho)
    _chieu_form(so, conn_kho)
    _chieu_bang_va_cot(so, conn_kho)
    _chieu_domain_form(so, conn_kho)
    _chieu_dataset(so, conn_kho)


def _chieu_domain(so, conn_kho) -> None:
    for d in qs.query(so, "SELECT domain_id, code, name, description, status FROM ctl_domain"):
        q.execute(
            conn_kho,
            """
            INSERT INTO ctl.domain (domain_id, code, name, description, status)
                 VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (domain_id) DO UPDATE
                    SET code = EXCLUDED.code, name = EXCLUDED.name,
                        description = EXCLUDED.description, status = EXCLUDED.status
            """,
            (d["domain_id"], d["code"], d["name"], d["description"], d["status"]),
        )


def _chieu_form(so, conn_kho) -> None:
    for f in qs.query(
        so, "SELECT form_id, code, label, description, current_version, yaml_sha256, policy "
            "  FROM ctl_form"):
        q.execute(
            conn_kho,
            """
            INSERT INTO ctl.form (form_id, code, label, description, current_version,
                                  yaml_sha256, policy)
                 VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (form_id) DO UPDATE
                    SET code = EXCLUDED.code, label = EXCLUDED.label,
                        description = EXCLUDED.description,
                        current_version = EXCLUDED.current_version,
                        yaml_sha256 = EXCLUDED.yaml_sha256, policy = EXCLUDED.policy
            """,
            (f["form_id"], f["code"], f["label"], f["description"], f["current_version"],
             f["yaml_sha256"], f["policy"]),
        )


def _chieu_domain_form(so, conn_kho) -> None:
    """Thay toàn bộ cặp (nhóm thông tin, bộ bảng) — bảng nhỏ. Một nhóm có thể có
    nhiều bộ bảng (loại tệp); mỗi bộ bảng thuộc tối đa một nhóm."""
    q.execute(conn_kho, "DELETE FROM ctl.domain_form")
    for df in qs.query(so, "SELECT domain_id, form_id, thu_tu FROM ctl_domain_form"):
        q.execute(conn_kho, "INSERT INTO ctl.domain_form (domain_id, form_id, thu_tu) "
                            "VALUES (%s, %s, %s)",
                  (df["domain_id"], df["form_id"], df["thu_tu"]))


def _chieu_bang_va_cot(so, conn_kho) -> None:
    for t in qs.query(so, "SELECT * FROM ctl_form_table"):
        q.execute(
            conn_kho,
            """
            INSERT INTO ctl.form_table (table_id, form_id, name, kind, sheet, label,
                                        card_label, description, card_description, grain,
                                        business_key, merge_strategy, partition_by, order_by,
                                        display_order)
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (table_id) DO UPDATE
                    SET form_id = EXCLUDED.form_id, name = EXCLUDED.name,
                        kind = EXCLUDED.kind, sheet = EXCLUDED.sheet,
                        label = EXCLUDED.label, card_label = EXCLUDED.card_label,
                        description = EXCLUDED.description,
                        card_description = EXCLUDED.card_description,
                        grain = EXCLUDED.grain, business_key = EXCLUDED.business_key,
                        merge_strategy = EXCLUDED.merge_strategy,
                        partition_by = EXCLUDED.partition_by, order_by = EXCLUDED.order_by,
                        display_order = EXCLUDED.display_order
            """,
            (t["table_id"], t["form_id"], t["name"], t["kind"], t["sheet"], t["label"],
             t["card_label"], t["description"], t["card_description"], t["grain"],
             json.loads(t["business_key"]), t["merge_strategy"],
             json.loads(t["partition_by"]), json.loads(t["order_by"]),
             t["display_order"]),
        )
        q.execute(conn_kho, "DELETE FROM ctl.form_column WHERE table_id = %s",
                  (t["table_id"],))

    for c in qs.query(so, "SELECT * FROM ctl_form_column ORDER BY table_id, ordinal"):
        q.execute(
            conn_kho,
            """
            INSERT INTO ctl.form_column (table_id, name, ordinal, type, required,
                                         is_business_key, label, meaning, how, example,
                                         enum_values, role, display_width, show_in_table)
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (c["table_id"], c["name"], c["ordinal"], c["type"], bool(c["required"]),
             bool(c["is_business_key"]), c["label"], c["meaning"], c["how"], c["example"],
             json.loads(c["enum_values"]) if c["enum_values"] else None,
             c["role"], c["display_width"], bool(c["show_in_table"])),
        )


def _chieu_dataset(so, conn_kho) -> None:
    cap = cap_dataset(so)
    q.execute(
        conn_kho,
        "DELETE FROM ctl.dataset d WHERE NOT EXISTS ("
        "  SELECT 1 FROM unnest(%s::int[], %s::int[]) AS k(domain_id, table_id) "
        "   WHERE k.domain_id = d.domain_id AND k.table_id = d.table_id)",
        ([c["domain_id"] for c in cap], [c["table_id"] for c in cap]))
    for ds in cap:
        q.execute(
            conn_kho,
            """
            INSERT INTO ctl.dataset (domain_id, table_id, label, description, display_order)
                 VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (domain_id, table_id) DO UPDATE
                    SET label = EXCLUDED.label,
                        description = EXCLUDED.description,
                        display_order = EXCLUDED.display_order
            """,
            (ds["domain_id"], ds["table_id"], ds["label"], ds["description"],
             ds["display_order"]),
        )
