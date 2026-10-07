from __future__ import annotations

import re
from typing import Any

from .. import messages
from ..registry.customer_aliases import customer_name_key
from ..registry.schema import (
    NORMALIZE_CUSTOMER_CODE,
    NORMALIZE_SALES_GROUP,
    NORMALIZE_SPLIT_HEAD,
    NORMALIZE_SPLIT_TAIL,
    Form,
    FormTable,
)
from .context import CleanRow

WHITESPACE_PATTERN = re.compile(r'\s+')
SPLIT_PATTERN = re.compile(r'\s+-\s+')
SALES_GROUP_PATTERN = re.compile(r'^(?:sale\s*)?(\d+)(?:\.0+)?$', re.IGNORECASE)
SALES_GROUP_FORMAT = 'SALE {number}'


def normalize_rows(form: Form, table: FormTable, rows: list[CleanRow]) -> list[CleanRow]:
    if not has_normalized_columns(table):
        return rows
    for row in rows:
        row.values = normalize_values(form, table, row.values)
    return rows


def normalize_values(form: Form, table: FormTable, values: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(values)
    for column in table.columns:
        if column.normalize is None:
            continue
        text = clean_text(values.get(column.normalize.source or column.name))
        value = _apply_rule(column.normalize.rule, text, form.customer_aliases) if text else None
        normalized[column.name] = value or messages.NO_INFORMATION
    return normalized


def has_normalized_columns(table: FormTable) -> bool:
    return any(column.normalize is not None for column in table.columns)


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    return WHITESPACE_PATTERN.sub(' ', str(value)).strip() or None


def _apply_rule(rule: str, text: str, customer_aliases: dict[str, str]) -> str | None:
    if rule == NORMALIZE_SPLIT_HEAD:
        return SPLIT_PATTERN.split(text, maxsplit=1)[0].strip()
    if rule == NORMALIZE_SPLIT_TAIL:
        parts = SPLIT_PATTERN.split(text, maxsplit=1)
        return parts[1].strip() if len(parts) == 2 else None
    if rule == NORMALIZE_SALES_GROUP:
        match = SALES_GROUP_PATTERN.match(text)
        return SALES_GROUP_FORMAT.format(number=int(match.group(1))) if match else text
    if rule == NORMALIZE_CUSTOMER_CODE:
        return customer_aliases.get(customer_name_key(text), text)
    return text
