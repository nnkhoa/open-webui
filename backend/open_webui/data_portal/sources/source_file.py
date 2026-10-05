from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from openpyxl.cell.cell import Cell
from openpyxl.worksheet.worksheet import Worksheet

from .xlsx import is_blank, open_workbook

DECIMALS_PATTERN = re.compile(r'\.(0+)')
GENERAL_FORMAT = 'General'
DATE_FORMAT = '%d/%m/%Y'
DATE_TIME_FORMAT = '%d/%m/%Y %H:%M'


@dataclass(frozen=True)
class SourceSheet:
    name: str
    hidden: bool
    grid: tuple[tuple[str | None, ...], ...]
    hidden_rows: frozenset[int]
    column_count: int


def list_sheets(path: Path) -> list[dict[str, Any]]:
    return [
        {
            'index': index,
            'name': sheet.name,
            'row_count': len(sheet.grid),
            'hidden': sheet.hidden,
            'hidden_row_count': len(sheet.hidden_rows),
        }
        for index, sheet in enumerate(_read_sheets(path), start=1)
    ]


def sheet_page(path: Path, index: int, page: int, page_size: int) -> dict[str, Any] | None:
    sheets = _read_sheets(path)
    if not 1 <= index <= len(sheets):
        return None
    sheet = sheets[index - 1]
    offset = (page - 1) * page_size
    return {
        'index': index,
        'name': sheet.name,
        'hidden': sheet.hidden,
        'columns': [_column_letter(column) for column in range(1, sheet.column_count + 1)],
        'total': len(sheet.grid),
        'hidden_row_count': len(sheet.hidden_rows),
        'rows': [
            {'row_number': offset + i, 'cells': list(cells), 'hidden': (offset + i) in sheet.hidden_rows}
            for i, cells in enumerate(sheet.grid[offset : offset + page_size], start=1)
        ],
    }


def _read_sheets(path: Path) -> tuple[SourceSheet, ...]:
    return _read_sheets_cached(str(path), path.stat().st_mtime)


def _display_value(cell: Cell) -> str | None:
    value = cell.value
    if is_blank(value):
        return None
    if isinstance(value, bool):
        return 'TRUE' if value else 'FALSE'
    if isinstance(value, dt.datetime):
        return value.strftime(DATE_FORMAT if value.time() == dt.time() else DATE_TIME_FORMAT)
    if isinstance(value, dt.date):
        return value.strftime(DATE_FORMAT)
    if isinstance(value, (int, float)):
        return _format_number(value, cell.number_format)
    return str(value)


@lru_cache(maxsize=4)
def _read_sheets_cached(path: str, _mtime: float) -> tuple[SourceSheet, ...]:
    workbook = open_workbook(Path(path))
    try:
        return tuple(_read_sheet(worksheet) for worksheet in workbook.worksheets)
    finally:
        workbook.close()


def _read_sheet(worksheet: Worksheet) -> SourceSheet:
    values: dict[tuple[int, int], str] = {}
    for (row, column), cell in worksheet._cells.items():
        value = _display_value(cell)
        if value is not None:
            values[(row, column)] = value
    last_row = max((row for row, _ in values), default=0)
    column_count = max((column for _, column in values), default=0)
    grid = tuple(
        tuple(values.get((row, column)) for column in range(1, column_count + 1)) for row in range(1, last_row + 1)
    )
    hidden_rows = frozenset(
        row for row, dimension in worksheet.row_dimensions.items() if dimension.hidden and row <= last_row
    )
    return SourceSheet(
        name=worksheet.title,
        hidden=worksheet.sheet_state != 'visible',
        grid=grid,
        hidden_rows=hidden_rows,
        column_count=column_count,
    )


def _format_number(value: float | int, number_format: str) -> str:
    section = (number_format or GENERAL_FORMAT).split(';')[0]
    is_percent = '%' in section
    if is_percent:
        value = value * 100
    if section == GENERAL_FORMAT:
        if isinstance(value, int) or float(value).is_integer():
            return str(int(value))
        return repr(float(value)).replace('.', ',')
    decimals_match = DECIMALS_PATTERN.search(section)
    decimals = len(decimals_match.group(1)) if decimals_match else 0
    integer_part, _, fraction = f'{value:.{decimals}f}'.partition('.')
    if ',' in section.split('.')[0]:
        integer_part = _group_thousands(integer_part)
    text = integer_part + (',' + fraction if fraction else '')
    return text + ('%' if is_percent else '')


def _group_thousands(integer_part: str) -> str:
    negative = integer_part.startswith('-')
    digits = integer_part.lstrip('-')
    groups = []
    while len(digits) > 3:
        groups.insert(0, digits[-3:])
        digits = digits[:-3]
    groups.insert(0, digits)
    return ('-' if negative else '') + '.'.join(groups)


def _column_letter(index: int) -> str:
    letters = ''
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters
