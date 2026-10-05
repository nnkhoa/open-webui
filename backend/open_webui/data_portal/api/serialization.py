from __future__ import annotations

import datetime as dt
from decimal import Decimal


def serialize(value):
    if isinstance(value, dict):
        return {key: serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize(item) for item in value]
    if isinstance(value, Decimal):
        return _to_number(value)
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    return value


def _to_number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)
