from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

from .. import messages
from ..errors import RegistryError
from ..formatting import EMPTY, format_amount, format_date, format_integer, format_percent

CODE_VALUE_UNPARSABLE = 'VALUE_UNPARSABLE'
CODE_MONTH_UNPARSABLE = 'MONTH_UNPARSABLE'
CODE_ENUM_UNKNOWN = 'ENUM_UNKNOWN'

NUMBER_PATTERN = re.compile(r'^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$')
INTEGER_PATTERN = re.compile(r'^[+-]?\d+$')
MONTH_PATTERN = re.compile(r'^(\d{4})-(\d{2})$')


@dataclass(frozen=True)
class Verdict:
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
    name: ClassVar[str] = ''
    silver_sql_type: ClassVar[str] = 'text'
    align: ClassVar[str] = 'left'
    label: ClassVar[str] = messages.REGISTRY_TYPE_TEXT
    summable: ClassVar[bool] = False

    def __init__(self, column: Any = None) -> None:
        self.column = column

    def parse(self, raw: str | None) -> Verdict:
        raise NotImplementedError

    def display(self, value: Any) -> str:
        return EMPTY if value is None else str(value)


TYPES: dict[str, type[ColumnType]] = {}


def register(cls: type[ColumnType]) -> type[ColumnType]:
    TYPES[cls.name] = cls
    return cls


def build(type_name: str, column: Any = None) -> ColumnType:
    cls = TYPES.get(type_name)
    if cls is None:
        raise RegistryError(
            messages.REGISTRY_TYPE_NOT_REGISTERED.format(type=type_name, available=', '.join(sorted(TYPES)))
        )
    return cls(column)


@register
class TextType(ColumnType):
    name = 'text'
    silver_sql_type = 'text'
    label = messages.REGISTRY_TYPE_TEXT

    def parse(self, raw: str | None) -> Verdict:
        return Verdict.good(raw)


class _NumericType(ColumnType):
    silver_sql_type = 'numeric'
    align = 'right'
    summable = True

    def parse(self, raw: str | None) -> Verdict:
        if raw is None:
            return Verdict.good(None)
        text = raw.strip().replace(' ', '')
        if not text:
            return Verdict.good(None)
        if not NUMBER_PATTERN.match(text):
            return Verdict.bad(CODE_VALUE_UNPARSABLE)
        try:
            return Verdict.good(Decimal(text))
        except InvalidOperation:
            return Verdict.bad(CODE_VALUE_UNPARSABLE)


@register
class MoneyType(_NumericType):
    name = 'money'
    label = messages.REGISTRY_TYPE_MONEY

    def display(self, value: Any) -> str:
        return format_amount(value)


@register
class NumberType(_NumericType):
    name = 'number'
    label = messages.REGISTRY_TYPE_NUMBER

    def display(self, value: Any) -> str:
        return format_amount(value)


@register
class CurrencyType(MoneyType):
    name = 'currency'
    label = messages.REGISTRY_TYPE_CURRENCY


@register
class RatioType(_NumericType):
    name = 'ratio'
    label = messages.REGISTRY_TYPE_RATIO
    summable = False

    DIVISION_BY_ZERO = '#DIV/0!'

    def parse(self, raw: str | None) -> Verdict:
        if raw is not None and raw.strip().upper() == self.DIVISION_BY_ZERO:
            return Verdict.good(Decimal(0))
        return super().parse(raw)

    def display(self, value: Any) -> str:
        return format_percent(value)


@register
class IntType(ColumnType):
    name = 'int'
    silver_sql_type = 'bigint'
    align = 'right'
    summable = True
    label = messages.REGISTRY_TYPE_INT

    def parse(self, raw: str | None) -> Verdict:
        if raw is None or not raw.strip():
            return Verdict.good(None)
        text = raw.strip()
        if not INTEGER_PATTERN.match(text):
            return Verdict.bad(CODE_VALUE_UNPARSABLE)
        return Verdict.good(int(text))

    def display(self, value: Any) -> str:
        return format_integer(value)


@register
class MonthType(ColumnType):
    name = 'month'
    silver_sql_type = 'date'
    label = messages.REGISTRY_TYPE_MONTH

    def parse(self, raw: str | None) -> Verdict:
        if raw is None or not raw.strip():
            return Verdict.good(None)
        match = MONTH_PATTERN.match(raw.strip())
        if not match:
            return Verdict.bad(CODE_MONTH_UNPARSABLE)
        year, month = int(match.group(1)), int(match.group(2))
        if not 1 <= month <= 12:
            return Verdict.bad(CODE_MONTH_UNPARSABLE)
        return Verdict.good(dt.date(year, month, 1))

    def display(self, value: Any) -> str:
        if value is None:
            return EMPTY
        if isinstance(value, (dt.date, dt.datetime)):
            return f'{value.year:04d}-{value.month:02d}'
        return str(value)


@register
class DateType(ColumnType):
    name = 'date'
    silver_sql_type = 'date'
    label = messages.REGISTRY_TYPE_DATE

    def parse(self, raw: str | None) -> Verdict:
        if raw is None or not raw.strip():
            return Verdict.good(None)
        try:
            return Verdict.good(dt.date.fromisoformat(raw.strip()[:10]))
        except ValueError:
            return Verdict.bad(CODE_VALUE_UNPARSABLE)

    def display(self, value: Any) -> str:
        return format_date(value)


@register
class EnumType(ColumnType):
    name = 'enum'
    silver_sql_type = 'text'
    label = messages.REGISTRY_TYPE_ENUM

    def parse(self, raw: str | None) -> Verdict:
        if raw is None or not raw.strip():
            return Verdict.good(None)
        text = raw.strip()
        allowed = getattr(self.column, 'values', None) or []
        if not allowed:
            return Verdict.good(text)
        by_lowercase = {str(value).strip().lower(): str(value) for value in allowed}
        match = by_lowercase.get(text.lower())
        if match is None:
            return Verdict.bad(CODE_ENUM_UNKNOWN)
        return Verdict.good(match)


@register
class BoolType(ColumnType):
    name = 'bool'
    silver_sql_type = 'boolean'
    label = messages.REGISTRY_TYPE_BOOL

    TRUE_VALUES: ClassVar[set[str]] = {'true', '1', 'có', 'co', 'yes', 'x'}
    FALSE_VALUES: ClassVar[set[str]] = {'false', '0', 'không', 'khong', 'no'}

    def parse(self, raw: str | None) -> Verdict:
        if raw is None or not raw.strip():
            return Verdict.good(None)
        text = raw.strip().lower()
        if text in self.TRUE_VALUES:
            return Verdict.good(True)
        if text in self.FALSE_VALUES:
            return Verdict.good(False)
        return Verdict.bad(CODE_VALUE_UNPARSABLE)

    def display(self, value: Any) -> str:
        if value is None:
            return EMPTY
        return messages.REGISTRY_BOOL_TRUE if value else messages.REGISTRY_BOOL_FALSE
