"""Quy tắc hiển thị

Nằm ở tầng trong cùng cạnh `config` và `errors`, không nằm trong `web`: sổ đăng
ký kiểu cột cũng cần biết in một giá trị ra sao (`ColumnType.display`), mà nó
thì không được phép biết gì về tầng API.

Một chỗ duy nhất quyết định cách một con số hiện lên màn hình, nên P02, P04,
P06 và P08 không thể trình bày khác nhau về cùng một giá trị.

    số nguyên, số tiền   phân tách nghìn bằng **dấu chấm**    1.031.204.925
    số âm                dấu trừ, không ngoặc, màu đỏ         -439.449.283
    số bằng 0            hiện 0, không hiện gạch              0
    tỷ lệ                tối đa 2 chữ số thập phân, dấu phẩy  30,40%
    giá trị trống        gạch ngang dài                       —
    ngày giờ             dd/mm/yyyy, HH:MM                    21/09/2026, 10:18
    kỳ                   giữ nguyên YYYY-MM                   2026-01
    dung lượng tệp       1 chữ số thập phân, dấu phẩy         39,1 KB
    mã lần nạp           tiền tố #                            #105
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

EMPTY = "—"


def _decimal(gia_tri) -> Decimal | None:
    if gia_tri is None or gia_tri == "":
        return None
    if isinstance(gia_tri, Decimal):
        return gia_tri
    try:
        return Decimal(str(gia_tri))
    except (InvalidOperation, ValueError, TypeError):
        return None


def so_nguyen(gia_tri) -> str:
    """`1.031.204.925`. Giá trị 0 hiện `0`, không hiện gạch."""
    so = _decimal(gia_tri)
    if so is None:
        return EMPTY
    nguyen = int(so.to_integral_value())
    return f"{nguyen:,}".replace(",", ".")


def so_tien(gia_tri) -> str:
    """Số tiền: bỏ phần thập phân bằng 0, giữ tối đa 2 chữ số nếu có."""
    so = _decimal(gia_tri)
    if so is None:
        return EMPTY
    if so == so.to_integral_value():
        return so_nguyen(so)
    phan = f"{so:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return phan


def ty_le(gia_tri) -> str:
    """`30,40%` — tối đa 2 chữ số thập phân, dấu phẩy."""
    so = _decimal(gia_tri)
    if so is None:
        return EMPTY
    return f"{so * 100:.2f}".replace(".", ",") + "%"


def am(gia_tri) -> bool:
    """Số âm hiện màu đỏ, không tô nền."""
    so = _decimal(gia_tri)
    return so is not None and so < 0


def ngay_gio(gia_tri) -> str:
    if not isinstance(gia_tri, (datetime, date)):
        return EMPTY if gia_tri is None else str(gia_tri)
    if isinstance(gia_tri, datetime):
        return gia_tri.strftime("%d/%m/%Y, %H:%M")
    return gia_tri.strftime("%d/%m/%Y")


def ngay(gia_tri) -> str:
    if not isinstance(gia_tri, (datetime, date)):
        return EMPTY if gia_tri is None else str(gia_tri)
    return gia_tri.strftime("%d/%m/%Y")


def ky(gia_tri) -> str:
    """Kỳ giữ nguyên dạng `YYYY-MM`."""
    if gia_tri is None:
        return EMPTY
    if isinstance(gia_tri, (datetime, date)):
        return f"{gia_tri.year:04d}-{gia_tri.month:02d}"
    return str(gia_tri)


def dung_luong(so_byte) -> str:
    """`39,1 KB` — 1 chữ số thập phân, dấu phẩy."""
    if so_byte is None:
        return EMPTY
    so = float(so_byte)
    for don_vi in ("byte", "KB", "MB", "GB"):
        if so < 1024 or don_vi == "GB":
            if don_vi == "byte":
                return f"{int(so)} byte"
            return f"{so:.1f}".replace(".", ",") + f" {don_vi}"
        so /= 1024
    return f"{so:.1f} GB"


def rong(gia_tri) -> str:
    """Giá trị trống hiện gạch ngang dài, chuỗi rỗng cũng vậy."""
    if gia_tri is None or (isinstance(gia_tri, str) and not gia_tri.strip()):
        return EMPTY
    return str(gia_tri)


def o_bang(gia_tri, cot: dict) -> str:
    """Định dạng một ô ở P08 theo kiểu cột đã khai trong bộ bảng."""
    col = cot.get("col")
    if col is None:
        return rong(gia_tri)
    return col.display(gia_tri)
