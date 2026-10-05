from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from .. import messages
from .base import ColumnLayout, SourceIssue, SourceRow, column_index, normalize_name, register
from .xlsx import cell_text, is_blank, open_workbook

if TYPE_CHECKING:
    from ..registry.schema import Form

KIND = 'bang_theo_tieu_de'
HEADER_SEARCH_ROWS = 30
TOTAL_ROW_PREFIXES = ('total', 'tổng cộng')
CELL_REFERENCE_PATTERN = re.compile(r'^([A-Z]+)(\d+)$')
MONTH_NUMBERS = {
    name: number
    for number, name in enumerate(
        ('jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'), start=1
    )
}
REPORT_DATE_PATTERN = re.compile(r'(\d{1,2})\s*[-/ ]\s*([A-Za-z]{3})[A-Za-z]*\.?\s*[-/ ]?\s*(\d{4})')
HEADER_UNIT_PATTERN = re.compile(r'\(([^()]+)\)\s*$')
REPORT_DATE_FORMAT = '%d/%m/%Y'

Grid = dict[int, dict[int, Any]]


@dataclass(frozen=True)
class TotalCell:
    reference: str
    value: str | None
    header: str
    informational: bool


@dataclass(frozen=True)
class HeaderTableInfo:
    sheet: str
    header_row: int
    required_column_count: int
    first_row: int
    last_row: int
    hidden_row_count: int
    visible_row_count: int
    total_cell: TotalCell | None
    report_date: str | None


@dataclass(frozen=True)
class _HeaderCandidate:
    worksheet: Worksheet
    header_row: int
    headers: dict[str, tuple[int, str]]
    duplicates: set[str]
    grid: Grid


@register
class HeaderTableReader:
    kind = KIND

    def __init__(self, path: Path, form: Form) -> None:
        if form is None or len(form.tables) != 1:
            raise ValueError(messages.SOURCE_HEADER_TABLE_NEEDS_ONE_TABLE)
        self.path = path
        self._form = form
        self._table = form.tables[0]
        self._options = form.source_options
        self._required_headers = list(dict.fromkeys(column.file_header for column in self._table.file_columns))
        self._issues: list[SourceIssue] = []
        self._rows: list[SourceRow] = []
        self._headers: dict[str, tuple[int, str]] = {}
        self.info: HeaderTableInfo | None = None
        workbook = open_workbook(path)
        try:
            self._read(workbook)
        finally:
            workbook.close()

    def close(self) -> None:
        return None

    def source_issues(self) -> list[SourceIssue]:
        return list(self._issues)

    def sheets(self) -> list[str]:
        return [self._table.sheet]

    def header(self, sheet: str) -> list[str | None]:
        return list(self._required_headers)

    def column_layout(self, sheet: str) -> ColumnLayout:
        positions = {normalize_name(header): i for i, header in enumerate(self._required_headers, start=1)}
        return ColumnLayout(positions, [], [])

    def cells_outside_columns(self, sheet: str, unnamed_columns: list[int]) -> list[tuple[int, str]]:
        return []

    def rows(self, sheet: str, header_map: dict[str, str]) -> Iterator[SourceRow]:
        by_header = {normalize_name(header): header for header in self._required_headers}
        for row in self._rows:
            values = {
                name: row.values.get(by_header.get(normalize_name(file_header)))
                for name, file_header in header_map.items()
            }
            yield SourceRow(row.number, values)

    def source_sheet(self, sheet: str) -> str:
        return self.info.sheet if self.info else ''

    def header_value(self, file_header: str) -> str | None:
        header = self._headers.get(normalize_name(file_header))
        return _header_unit(header[1]) if header else None

    def _read(self, workbook: Workbook) -> None:
        candidates = self._find_candidates(workbook)
        if not self._check_candidate_count(candidates):
            return
        candidate = candidates[0]
        for name in sorted(candidate.duplicates):
            self._issues.append(
                SourceIssue(
                    candidate.worksheet.title.strip(),
                    messages.SOURCE_LOCATION_ROW.format(row=candidate.header_row),
                    'DUPLICATE_COLUMN',
                    {'name': ' '.join(name.split())},
                )
            )
        if self._issues:
            return
        self._headers = candidate.headers
        self.info = self._read_data(candidate)

    def _find_candidates(self, workbook: Workbook) -> list[_HeaderCandidate]:
        required = {normalize_name(header) for header in self._required_headers}
        candidates = []
        for worksheet in workbook.worksheets:
            if worksheet.sheet_state != 'visible':
                continue
            candidate = _find_header_row(worksheet, _sheet_grid(worksheet), required)
            if candidate is not None:
                candidates.append(candidate)
        return candidates

    def _check_candidate_count(self, candidates: list[_HeaderCandidate]) -> bool:
        form_label = self._form.label
        if not candidates:
            columns = ', '.join(' '.join(header.split()) for header in self._headers_in_file_order())
            params = {'count': str(len(self._required_headers)), 'form': form_label, 'columns': columns}
            self._issues.append(self._whole_file_issue('NO_DATA_SHEET', params))
            return False
        if len(candidates) > 1:
            params = {
                'sheet_count': str(len(candidates)),
                'count': str(len(self._required_headers)),
                'form': form_label,
                'sheets': ', '.join(candidate.worksheet.title.strip() for candidate in candidates),
            }
            self._issues.append(self._whole_file_issue('MANY_DATA_SHEETS', params))
            return False
        return True

    def _headers_in_file_order(self) -> list[str]:
        ordered = [header for header in self._options.get('required_headers', []) if header in self._required_headers]
        return ordered + [header for header in self._required_headers if header not in ordered]

    def _whole_file_issue(self, code: str, params: dict[str, str]) -> SourceIssue:
        return SourceIssue(messages.SOURCE_LOCATION_WHOLE_FILE, messages.SOURCE_LOCATION_HEADER_ROW, code, params)

    def _read_data(self, candidate: _HeaderCandidate) -> HeaderTableInfo:
        first_row = candidate.header_row + int(self._options.get('data_row_offset', 1))
        last_row, hidden_row_count = self._collect_rows(candidate, first_row)
        return HeaderTableInfo(
            sheet=candidate.worksheet.title,
            header_row=candidate.header_row,
            required_column_count=len(self._required_headers),
            first_row=first_row,
            last_row=last_row,
            hidden_row_count=hidden_row_count,
            visible_row_count=len(self._rows) - hidden_row_count,
            total_cell=self._read_total_cell(candidate),
            report_date=self._read_report_date(candidate.grid),
        )

    def _collect_rows(self, candidate: _HeaderCandidate, first_row: int) -> tuple[int, int]:
        grid = candidate.grid
        column_numbers = [candidate.headers[normalize_name(header)][0] for header in self._required_headers]
        hidden_rows = {
            row_number for row_number, dimension in candidate.worksheet.row_dimensions.items() if dimension.hidden
        }
        last_row = first_row - 1
        hidden_row_count = 0
        row_number = first_row
        while row_number in grid:
            values = [cell_text(grid[row_number].get(column)) for column in column_numbers]
            if not _is_total_row(values) and any(value is not None for value in values):
                self._rows.append(SourceRow(row_number, dict(zip(self._required_headers, values, strict=True))))
                hidden_row_count += row_number in hidden_rows
            last_row = row_number
            row_number += 1
        return last_row, hidden_row_count

    def _read_total_cell(self, candidate: _HeaderCandidate) -> TotalCell | None:
        reference = self._options.get('total_cell')
        if not reference:
            return None
        column, row = _parse_cell_reference(reference)
        header = candidate.grid.get(candidate.header_row, {}).get(column)
        return TotalCell(
            reference=reference,
            value=cell_text(candidate.grid.get(row, {}).get(column)),
            header=' '.join(str(header or '').split()),
            informational=bool(self._options.get('total_cell_informational')),
        )

    def _read_report_date(self, grid: Grid) -> str | None:
        reference = self._options.get('report_date_cell')
        if not reference:
            return None
        column, row = _parse_cell_reference(reference)
        return _parse_report_date(grid.get(row, {}).get(column))


def _sheet_grid(worksheet: Worksheet) -> Grid:
    grid: Grid = {}
    for (row, column), cell in worksheet._cells.items():
        if not is_blank(cell.value):
            grid.setdefault(row, {})[column] = cell.value
    return grid


def _find_header_row(worksheet: Worksheet, grid: Grid, required: set[str]) -> _HeaderCandidate | None:
    for row_number in range(1, HEADER_SEARCH_ROWS + 1):
        headers, duplicates = _row_headers(grid.get(row_number, {}), required)
        if required <= set(headers):
            return _HeaderCandidate(worksheet, row_number, headers, duplicates, grid)
    return None


def _row_headers(cells: dict[int, Any], required: set[str]) -> tuple[dict[str, tuple[int, str]], set[str]]:
    headers: dict[str, tuple[int, str]] = {}
    duplicates: set[str] = set()
    for column, value in sorted(cells.items()):
        if not isinstance(value, str):
            continue
        key = normalize_name(value)
        if key in headers and key in required:
            duplicates.add(value)
        headers.setdefault(key, (column, value))
    return headers, duplicates


def _parse_cell_reference(reference: str) -> tuple[int, int]:
    match = CELL_REFERENCE_PATTERN.match(str(reference))
    return column_index(match.group(1)), int(match.group(2))


def _is_total_row(values: list[str | None]) -> bool:
    return any(value is not None and normalize_name(value).startswith(TOTAL_ROW_PREFIXES) for value in values)


def _parse_report_date(value: Any) -> str | None:
    if isinstance(value, (dt.datetime, dt.date)):
        return value.strftime(REPORT_DATE_FORMAT)
    match = REPORT_DATE_PATTERN.search(str(value or ''))
    if not match or match.group(2).lower()[:3] not in MONTH_NUMBERS:
        return None
    try:
        report_date = dt.date(int(match.group(3)), MONTH_NUMBERS[match.group(2).lower()[:3]], int(match.group(1)))
    except ValueError:
        return None
    return report_date.strftime(REPORT_DATE_FORMAT)


def _header_unit(header: str | None) -> str | None:
    match = HEADER_UNIT_PATTERN.search(' '.join(str(header or '').split()))
    return match.group(1).strip() if match else None
