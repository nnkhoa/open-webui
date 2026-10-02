"""Cấu hình Data Portal — đọc từ biến môi trường, kiểm tra ngay khi khởi động.

Không có giá trị bí mật viết cứng, không có tên bảng hay URL môi trường rải
rác trong mã. Sai cấu hình thì báo lúc khởi động kèm câu chỉ rõ chỗ sai, chứ
không chết giữa lúc người dùng đang nạp tệp.

Biến môi trường mang tiền tố `DATA_PORTAL_` để không đụng biến của Open WebUI
(`DATABASE_URL` của Open WebUI là cơ sở dữ liệu riêng của nó, không phải kho).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

GOI = Path(__file__).resolve().parent
# Cùng mặc định với `DATA_DIR` của Open WebUI (`backend/data`).
DATA_DIR = Path(os.getenv("DATA_DIR", GOI.parents[1] / "data"))


@dataclass(frozen=True)
class Settings:
    # Kho dữ liệu PostgreSQL **không** khai ở đây: địa chỉ của nó nằm trong sổ
    # tay SQLite, sửa từ màn Cấu hình database. Biến `DATA_PORTAL_DATABASE_URL`
    # chỉ là giá trị mồi cho lần cấu hình đầu tiên.
    database_url_mac_dinh: str | None
    so_tay_path: Path
    so_tay_migrations_dir: Path
    registry_dir: Path
    migrations_dir: Path
    upload_dir: Path
    page_sizes: tuple[int, ...] = field(default=(25, 50, 100))
    default_page_size: int = 50

    def kiem_tra(self) -> None:
        if self.database_url_mac_dinh and not self.database_url_mac_dinh.startswith("postgres"):
            raise ValueError(
                f"DATA_PORTAL_DATABASE_URL phải là chuỗi kết nối PostgreSQL, "
                f"đang là {self.database_url_mac_dinh!r}."
            )
        for ten, thu_muc in (("nâng cấp sổ tay", self.so_tay_migrations_dir),
                             ("khai báo", self.registry_dir),
                             ("nâng cấp schema", self.migrations_dir)):
            if not thu_muc.is_dir():
                raise ValueError(f"Không thấy thư mục {ten}: {thu_muc}")
        self.so_tay_path.parent.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)


def doc_cau_hinh() -> Settings:
    thu_muc = Path(os.getenv("DATA_PORTAL_DIR", DATA_DIR / "data_portal"))
    settings = Settings(
        database_url_mac_dinh=os.getenv("DATA_PORTAL_DATABASE_URL") or None,
        so_tay_path=thu_muc / "so-tay.db",
        so_tay_migrations_dir=GOI / "migrations" / "so_tay",
        registry_dir=GOI / "khai_bao",
        migrations_dir=GOI / "migrations" / "kho",
        upload_dir=thu_muc / "uploads",
    )
    settings.kiem_tra()
    return settings
