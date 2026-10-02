"""Bối cảnh một lần nạp — thứ mọi chặng của đường xử lý dùng chung.

Giữ trạng thái, không giữ hành vi: mỗi chặng đọc cái nó cần và ghi kết quả của
nó vào đây.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..registry.schema import Form, FormTable


@dataclass
class DongSach:
    """Một dòng đã ép kiểu, sẵn sàng vào lớp chuẩn hoá."""

    source_row: int
    bronze_id: int
    row_hash: str
    values: dict[str, Any]


@dataclass
class KetQuaBang:
    """Số dòng qua từng lớp của một bảng — nguồn của bảng "Kết quả theo từng bảng"."""

    table: str
    label: str
    rows_file: int = 0
    rows_bronze: int = 0
    rows_silver: int = 0
    rows_gold: int = 0
    rows_superseded: int = 0
    rows_unchanged: int = 0
    rows_duplicate: int = 0


@dataclass
class LoadContext:
    conn: Any
    form: Form
    domain_id: int
    domain_code: str
    form_id: int
    load_id: int
    batch_id: int
    upload_path: Path
    file_name: str
    actor_user_id: int | None
    actor_username: str
    request_id: str

    # Năm dữ liệu chọn lúc nạp (QT-02) — ghi vào cột `nam` của bảng số liệu.
    nam: int | None = None

    reader: Any = None
    sheets_count: int = 0
    dong_sach: dict[str, list[DongSach]] = field(default_factory=dict)
    ket_qua: dict[str, KetQuaBang] = field(default_factory=dict)
    ky_cham_toi: dict[str, set[str]] = field(default_factory=dict)

    def bang(self, table: FormTable) -> KetQuaBang:
        if table.name not in self.ket_qua:
            self.ket_qua[table.name] = KetQuaBang(table.name, table.label)
        return self.ket_qua[table.name]

    @property
    def rows_read(self) -> int:
        return sum(k.rows_bronze for k in self.ket_qua.values())

    @property
    def rows_written(self) -> int:
        return sum(k.rows_silver for k in self.ket_qua.values())

    def bao_cao(self) -> dict:
        """`ctl.load.report` — số dòng theo tên bảng và kỳ bị chạm tới."""
        return {
            "tables": {
                k.table: {
                    "label": k.label,
                    "rows_file": k.rows_file,
                    "rows_bronze": k.rows_bronze,
                    "rows_silver": k.rows_silver,
                    "rows_gold": k.rows_gold,
                    "rows_superseded": k.rows_superseded,
                    "rows_unchanged": k.rows_unchanged,
                    "rows_duplicate": k.rows_duplicate,
                }
                for k in self.ket_qua.values()
            },
            "partitions": {t: sorted(k) for t, k in self.ky_cham_toi.items()},
        }
