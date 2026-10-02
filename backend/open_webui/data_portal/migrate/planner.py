"""So khai báo bảng với schema thật, sinh bước nâng cấp chênh lệch

`manage makemigration` gọi vào đây. Đầu ra là một tệp SQL trong
`migrations/kho/auto/` — đọc và duyệt được như mã nguồn, rồi `manage migrate`
mới áp dụng. Không bao giờ sinh và chạy thẳng: một khai báo sai không được
phép tự sửa schema.
"""

from __future__ import annotations

from pathlib import Path

from ..errors import MigrationError
from ..registry.khac_biet import so_sanh
from ..registry.schema import Form


def so_hieu_ke_tiep(thu_muc: Path) -> int:
    hien_co = [int(p.name[:4]) for p in thu_muc.glob("*.sql") if p.name[:4].isdigit()]
    hien_co += [int(p.name[:4]) for p in (thu_muc / "auto").glob("*.sql")
                if p.name[:4].isdigit()]
    return (max(hien_co) + 1) if hien_co else 1


def sinh_buoc(conn, form: Form, thu_muc: Path) -> Path | None:
    """Ghi chênh lệch giữa `form` và schema thật thành một bước nâng cấp mới.

    Không có chênh lệch ⇒ `None`. Có thay đổi chạm vào dữ liệu đã lưu (xoá cột,
    đổi kiểu cột của bảng đang có dòng) ⇒ dừng, không sinh gì.
    """
    ke = so_sanh(conn, form)
    if ke.bi_chan:
        raise MigrationError("Khai báo có thay đổi chạm vào dữ liệu đã lưu:\n" + "\n".join(
            f"  · {t.mo_ta} — {t.ly_do}" for t in ke.bi_chan))
    if not ke.can_ddl:
        return None
    auto = thu_muc / "auto"
    auto.mkdir(parents=True, exist_ok=True)
    so = so_hieu_ke_tiep(thu_muc)
    dich = auto / f"{so:04d}_form_{form.code.lower()}_v{form.version}.sql"
    dich.write_text(ke.sinh_ddl(), encoding="utf-8")
    return dich
