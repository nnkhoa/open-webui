"""Đổi giá trị trả về sang dạng JSON của API (mục 9.1).

Số trả về dạng số — nguyên thì số nguyên, có phần lẻ thì số thực; thời gian
theo ISO 8601. Giao diện tự định dạng theo 13.3.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal


def so(gia_tri) -> int | float | None:
    if gia_tri is None:
        return None
    if isinstance(gia_tri, (int, float)) and not isinstance(gia_tri, bool):
        return gia_tri
    d = Decimal(str(gia_tri))
    return int(d) if d == d.to_integral_value() else float(d)


def iso(gia_tri) -> str | None:
    if isinstance(gia_tri, (datetime, date)):
        return gia_tri.isoformat()
    return gia_tri


def sach(gia_tri):
    """Đi qua cả cây: `Decimal` → số, `datetime` → ISO 8601."""
    if isinstance(gia_tri, dict):
        return {k: sach(v) for k, v in gia_tri.items()}
    if isinstance(gia_tri, (list, tuple)):
        return [sach(v) for v in gia_tri]
    if isinstance(gia_tri, Decimal):
        return so(gia_tri)
    if isinstance(gia_tri, (datetime, date)):
        return gia_tri.isoformat()
    return gia_tri
