from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation

EMPTY = '—'


def format_integer(value) -> str:
    number = _to_decimal(value)
    if number is None:
        return EMPTY
    return f'{int(number.to_integral_value()):,}'.replace(',', '.')


def format_amount(value) -> str:
    number = _to_decimal(value)
    if number is None:
        return EMPTY
    if number == number.to_integral_value():
        return format_integer(number)
    return f'{number:,.2f}'.replace(',', '\x00').replace('.', ',').replace('\x00', '.')


def format_percent(value) -> str:
    number = _to_decimal(value)
    if number is None:
        return EMPTY
    return f'{number * 100:.2f}'.replace('.', ',') + '%'


def format_date(value) -> str:
    if not isinstance(value, (dt.datetime, dt.date)):
        return EMPTY if value is None else str(value)
    return value.strftime('%d/%m/%Y')


def _to_decimal(value) -> Decimal | None:
    if value is None or value == '':
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
