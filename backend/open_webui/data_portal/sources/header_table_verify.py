from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from .base import normalize_name
from .xlsx_verify import Grid, VerifyTable, XlsxXmlReader

if TYPE_CHECKING:
    from ..registry.schema import Form

HEADER_SEARCH_ROWS = 30
TOTAL_ROW_PREFIXES = ('total', 'tổng cộng')
TOTAL_LABEL_PATTERN = re.compile(r'^(total|tổng cộng)\s*:?$')


class HeaderTableVerifyReader:
    def __init__(self, path: Path, form: Form) -> None:
        table = form.tables[0]
        required_headers = list(dict.fromkeys(column.file_header for column in table.file_columns))
        self._data_row_offset = int(form.source_options.get('data_row_offset', 1))
        self._headers: dict[int, str] = {}
        self._rows: dict[int, dict[int, str]] = {}
        reader = XlsxXmlReader(path)
        try:
            self._read(reader, required_headers)
        finally:
            reader.close()

    def close(self) -> None:
        return None

    def read_table(self, sheet_name: str) -> VerifyTable:
        return VerifyTable(dict(self._headers), dict(self._rows))

    def _read(self, reader: XlsxXmlReader, required_headers: list[str]) -> None:
        required = {normalize_name(header) for header in required_headers}
        for sheet_name in reader.visible_sheets():
            grid = reader.grid(sheet_name)
            found = _find_header_row(grid, required)
            if found is not None:
                header_row, columns_by_name = found
                headers = {columns_by_name[normalize_name(header)]: header for header in required_headers}
                self._collect_rows(grid, reader.hidden_rows(sheet_name), header_row, headers)
                return

    def _collect_rows(self, grid: Grid, hidden_rows: set[int], header_row: int, headers: dict[int, str]) -> None:
        self._headers = headers
        for row_number in range(header_row + self._data_row_offset, max(grid, default=0) + 1):
            if row_number in hidden_rows:
                continue
            if row_number not in grid:
                break
            cells = {column: grid[row_number][column] for column in headers if column in grid[row_number]}
            if cells and not _is_total_row(cells.values(), grid[row_number].values()):
                self._rows[row_number] = cells


def _is_total_row(values: Iterable[str], row_cells: Iterable[str]) -> bool:
    if any(normalize_name(value).startswith(TOTAL_ROW_PREFIXES) for value in values):
        return True
    return any(TOTAL_LABEL_PATTERN.match(normalize_name(cell)) for cell in row_cells)


def _find_header_row(grid: Grid, required: set[str]) -> tuple[int, dict[str, int]] | None:
    for row_number in sorted(row for row in grid if row <= HEADER_SEARCH_ROWS):
        columns_by_name: dict[str, int] = {}
        for column in sorted(grid[row_number]):
            columns_by_name.setdefault(normalize_name(grid[row_number][column]), column)
        if required <= set(columns_by_name):
            return row_number, columns_by_name
    return None
