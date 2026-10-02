"""Sổ đăng ký kiểu cột.

Thêm một kiểu cột mới = thêm một lớp con `ColumnType` và gắn `@register`.
Không sửa đường xử lý, không sửa bộ sinh DDL, không sửa giao diện.

Mỗi kiểu trả lời bốn câu:
  · lưu ở lớp chuẩn hoá bằng kiểu SQL nào  (`silver_sql_type`)
  · một giá trị văn bản có hợp lệ không    (`parse`)
  · hiển thị ra màn hình thế nào           (`display`)
  · căn trái hay căn phải trên màn hình    (`align`)

Lớp gốc luôn là `text` — lưu y nguyên như tệp.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

from ..errors import RegistryError

# Mã kết quả ép kiểu không thành.
CODE_VALUE_UNPARSABLE = "VALUE_UNPARSABLE"
CODE_MONTH_UNPARSABLE = "MONTH_UNPARSABLE"
CODE_ENUM_UNKNOWN = "ENUM_UNKNOWN"


@dataclass(frozen=True)
class Verdict:
    """Kết quả đọc một ô.

    `ok=True` ⇒ `value` dùng được ở lớp chuẩn hoá.
    `ok=False` ⇒ `code` là mã lý do, `value` là None. Dòng đi đâu tuỳ cột đó có
    phải khoá nghiệp vụ hay không — quyết định ở `pipeline/validate.py`, không
    quyết định ở đây.
    """

    ok: bool
    value: Any = None
    code: str | None = None

    @classmethod
    def good(cls, value: Any) -> Verdict:
        return cls(True, value, None)

    @classmethod
    def bad(cls, code: str) -> Verdict:
        return cls(False, None, code)


class ColumnType:
    """Giao diện một kiểu cột."""

    name: ClassVar[str] = ""
    silver_sql_type: ClassVar[str] = "text"
    align: ClassVar[str] = "left"          # 'left' | 'right'
    label_vi: ClassVar[str] = "Văn bản"    # nhãn ở ngăn Giải thích các cột (P08)
    summable: ClassVar[bool] = False       # có cộng được ở hàng Tổng không

    bronze_sql_type: ClassVar[str] = "text"

    def __init__(self, column: Any = None) -> None:
        self.column = column

    def parse(self, raw: str | None) -> Verdict:
        raise NotImplementedError

    def display(self, value: Any) -> str:
        from ..format import EMPTY

        return EMPTY if value is None else str(value)


TYPES: dict[str, type[ColumnType]] = {}


def register(cls: type[ColumnType]) -> type[ColumnType]:
    TYPES[cls.name] = cls
    return cls


def build(type_name: str, column: Any = None) -> ColumnType:
    cls = TYPES.get(type_name)
    if cls is None:
        raise RegistryError(
            f"Kiểu cột {type_name!r} chưa được đăng ký. "
            f"Các kiểu có sẵn: {', '.join(sorted(TYPES))}."
        )
    return cls(column)


# --------------------------------------------------------------------------- #
#  Các kiểu có sẵn
# --------------------------------------------------------------------------- #

_NUMBER = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")
_INT = re.compile(r"^[+-]?\d+$")
_MONTH = re.compile(r"^(\d{4})-(\d{2})$")


@register
class TextType(ColumnType):
    name = "text"
    silver_sql_type = "text"
    label_vi = "Văn bản"

    def parse(self, raw: str | None) -> Verdict:
        return Verdict.good(raw)


class _NumericType(ColumnType):
    """Nền chung cho money / ratio / currency."""

    silver_sql_type = "numeric"
    align = "right"
    summable = True

    def parse(self, raw: str | None) -> Verdict:
        if raw is None:
            return Verdict.good(None)
        text = raw.strip().replace(" ", "")
        if not text:
            return Verdict.good(None)
        if not _NUMBER.match(text):
            return Verdict.bad(CODE_VALUE_UNPARSABLE)
        try:
            return Verdict.good(Decimal(text))
        except InvalidOperation:
            return Verdict.bad(CODE_VALUE_UNPARSABLE)


@register
class MoneyType(_NumericType):
    name = "money"
    label_vi = "Số, có thể âm"

    def display(self, value: Any) -> str:
        from ..format import so_tien

        return so_tien(value)


@register
class NumberType(_NumericType):
    """Số đo không phải tiền (số lượng, đơn giá USD) — không cộng vào tổng tiền."""

    name = "number"
    label_vi = "Số"

    def display(self, value: Any) -> str:
        from ..format import so_tien

        return so_tien(value)


@register
class CurrencyType(MoneyType):
    name = "currency"
    label_vi = "Số tiền kèm đơn vị"


@register
class RatioType(_NumericType):
    name = "ratio"
    label_vi = "Tỷ lệ"
    summable = False          # cộng tỷ lệ lại là vô nghĩa

    # Excel ghi "#DIV/0!" khi mẫu số bằng 0 (khách không có doanh thu trong
    # tháng). NBC xác nhận kế toán để các ô này bằng 0 — lớp gốc vẫn giữ nguyên.
    LOI_CHIA_0 = "#DIV/0!"

    def parse(self, raw: str | None) -> Verdict:
        if raw is not None and raw.strip().upper() == self.LOI_CHIA_0:
            return Verdict.good(Decimal(0))
        return super().parse(raw)

    def display(self, value: Any) -> str:
        from ..format import ty_le

        return ty_le(value)


@register
class IntType(ColumnType):
    name = "int"
    silver_sql_type = "bigint"
    align = "right"
    summable = True
    label_vi = "Số nguyên"

    def parse(self, raw: str | None) -> Verdict:
        if raw is None or not raw.strip():
            return Verdict.good(None)
        text = raw.strip()
        if not _INT.match(text):
            return Verdict.bad(CODE_VALUE_UNPARSABLE)
        return Verdict.good(int(text))

    def display(self, value: Any) -> str:
        from ..format import so_nguyen

        return so_nguyen(value)


@register
class MonthType(ColumnType):
    name = "month"
    silver_sql_type = "date"
    label_vi = "Văn bản (YYYY-MM)"

    def parse(self, raw: str | None) -> Verdict:
        if raw is None or not raw.strip():
            return Verdict.good(None)
        text = raw.strip()
        match = _MONTH.match(text)
        if not match:
            return Verdict.bad(CODE_MONTH_UNPARSABLE)
        year, month = int(match.group(1)), int(match.group(2))
        if not 1 <= month <= 12:
            return Verdict.bad(CODE_MONTH_UNPARSABLE)
        return Verdict.good(date(year, month, 1))

    def display(self, value: Any) -> str:
        from ..format import EMPTY

        if value is None:
            return EMPTY
        if isinstance(value, (date, datetime)):
            return f"{value.year:04d}-{value.month:02d}"
        return str(value)


@register
class DateType(ColumnType):
    name = "date"
    silver_sql_type = "date"
    label_vi = "Ngày"

    def parse(self, raw: str | None) -> Verdict:
        if raw is None or not raw.strip():
            return Verdict.good(None)
        try:
            return Verdict.good(date.fromisoformat(raw.strip()[:10]))
        except ValueError:
            return Verdict.bad(CODE_VALUE_UNPARSABLE)

    def display(self, value: Any) -> str:
        from ..format import ngay

        return ngay(value)


@register
class EnumType(ColumnType):
    name = "enum"
    silver_sql_type = "text"
    label_vi = "Danh sách giá trị"

    def parse(self, raw: str | None) -> Verdict:
        if raw is None or not raw.strip():
            return Verdict.good(None)
        text = raw.strip()
        allowed = getattr(self.column, "values", None) or []
        if not allowed:
            return Verdict.good(text)
        lowered = {str(v).strip().lower(): str(v) for v in allowed}
        hit = lowered.get(text.lower())
        if hit is None:
            # Ngoài danh sách: lớp chuẩn hoá giữ nguyên văn bản gốc.
            return Verdict.bad(CODE_ENUM_UNKNOWN)
        return Verdict.good(hit)


@register
class BoolType(ColumnType):
    name = "bool"
    silver_sql_type = "boolean"
    label_vi = "Có / Không"

    _TRUE: ClassVar[set[str]] = {"true", "1", "có", "co", "yes", "x"}
    _FALSE: ClassVar[set[str]] = {"false", "0", "không", "khong", "no"}

    def parse(self, raw: str | None) -> Verdict:
        if raw is None or not raw.strip():
            return Verdict.good(None)
        text = raw.strip().lower()
        if text in self._TRUE:
            return Verdict.good(True)
        if text in self._FALSE:
            return Verdict.good(False)
        return Verdict.bad(CODE_VALUE_UNPARSABLE)

    def display(self, value: Any) -> str:
        from ..format import EMPTY

        return EMPTY if value is None else ("Có" if value else "Không")
