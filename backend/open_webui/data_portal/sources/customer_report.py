from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from .. import messages
from . import customer_report_layout as layout
from .base import ColumnLayout, SourceIssue, SourceRow, normalize_name, register
from .xlsx import cell_text, is_blank, open_workbook

if TYPE_CHECKING:
    from ..registry.schema import Form

FlatRow = dict[str, str | None]


@dataclass(frozen=True)
class _SummaryColumns:
    month: int
    business_group: int
    customer_code: int
    customer_name: int
    results: dict[str, int]
    costs: list[int]
    cost_codes: list[str | None]


class _Sheet:
    def __init__(self, worksheet: Worksheet) -> None:
        self.worksheet = worksheet
        self.title = worksheet.title

    @property
    def last_row(self) -> int:
        return self.worksheet.max_row

    def cells(self, row_number: int) -> list[Any]:
        return [cell.value for cell in self.worksheet[row_number]]

    def normalized_cells(self, row_number: int) -> list[str | None]:
        return [None if is_blank(value) else normalize_name(value) for value in self.cells(row_number)]

    def find_header_row(self, *headers: str) -> int | None:
        required = {normalize_name(header) for header in headers}
        for row_number in range(1, min(layout.HEADER_SEARCH_ROWS, self.last_row) + 1):
            if required <= {normalize_name(value) for value in self.cells(row_number) if not is_blank(value)}:
                return row_number
        return None


class _ColumnResolver:
    def __init__(
        self,
        sheet: _Sheet,
        header_row: int,
        cost_codes: list[str | None],
        issues: list[SourceIssue],
    ) -> None:
        self._sheet_title = sheet.title
        self._header_row = header_row
        self._headers = sheet.normalized_cells(header_row)
        self._cost_codes = cost_codes
        self._issues = issues

    def by_header(self, header: str, anchor: str | None = None) -> int | None:
        start = 0
        if anchor is not None:
            anchor_column = self.by_header(anchor)
            if anchor_column is None:
                return None
            start = anchor_column + 1
        target = normalize_name(header)
        matches = [i for i, name in enumerate(self._headers) if name == target and i >= start]
        if not matches:
            self._issues.append(_column_issue(self._sheet_title, self._header_row, header, 'MISSING_COLUMN'))
            return None
        if anchor is None and len(matches) > 1:
            self._issues.append(_column_issue(self._sheet_title, self._header_row, header, 'DUPLICATE_COLUMN'))
            return None
        return matches[0]

    def by_code(self, code: str) -> int | None:
        matches = [i for i, value in enumerate(self._cost_codes) if value == code]
        if len(matches) != 1:
            issue_code = 'DUPLICATE_COLUMN' if matches else 'MISSING_COLUMN'
            self._issues.append(_column_issue(self._sheet_title, self._header_row - 1, code, issue_code))
            return None
        return matches[0]


@register
class CustomerReportReader:
    kind = layout.KIND

    def __init__(self, path: Path, form: Form) -> None:
        self.path = path
        self._issues: list[SourceIssue] = []
        self._tables = _empty_tables()
        workbook = open_workbook(path)
        try:
            self._read(workbook)
        finally:
            workbook.close()
        if self._issues:
            self._tables = _empty_tables()

    def close(self) -> None:
        return None

    def source_issues(self) -> list[SourceIssue]:
        return list(self._issues)

    def sheets(self) -> list[str]:
        return list(layout.FLAT_TABLES)

    def header(self, sheet: str) -> list[str | None]:
        return list(layout.FLAT_TABLES[self._table_name(sheet)])

    def column_layout(self, sheet: str) -> ColumnLayout:
        positions = {normalize_name(column): i for i, column in enumerate(self.header(sheet), start=1)}
        return ColumnLayout(positions, [], [])

    def cells_outside_columns(self, sheet: str, unnamed_columns: list[int]) -> list[tuple[int, str]]:
        return []

    def rows(self, sheet: str, header_map: dict[str, str]) -> Iterator[SourceRow]:
        by_header = {normalize_name(column): column for column in self.header(sheet)}
        selected = {
            name: by_header[normalize_name(file_header)]
            for name, file_header in header_map.items()
            if normalize_name(file_header) in by_header
        }
        for row_number, row in enumerate(self._tables[self._table_name(sheet)], start=2):
            values = {name: row.get(column) for name, column in selected.items()}
            if any(value is not None for value in values.values()):
                yield SourceRow(row_number, values)

    def source_sheet(self, sheet: str) -> str:
        return layout.SOURCE_SHEET_BY_TABLE[self._table_name(sheet)]

    def _table_name(self, sheet: str) -> str:
        for name in layout.FLAT_TABLES:
            if normalize_name(name) == normalize_name(sheet):
                return name
        raise KeyError(sheet)

    def _read(self, workbook: Workbook) -> None:
        sheets = self._find_sheets(workbook)
        if self._issues:
            return
        self._read_summary(sheets[layout.SUMMARY_SHEET])
        for catalog in (layout.CUSTOMER_CATALOG, layout.COST_ITEM_CATALOG):
            self._read_catalog(sheets[catalog.sheet], catalog)
        for row in self._tables[layout.COST_ITEMS_TABLE]:
            row['nhom_chi_phi'] = layout.cost_group(row['ma_khoan_cp'])

    def _find_sheets(self, workbook: Workbook) -> dict[str, _Sheet]:
        actual_names = {normalize_name(name): name for name in workbook.sheetnames}
        sheets: dict[str, _Sheet] = {}
        for name in (layout.SUMMARY_SHEET, layout.CUSTOMER_LIST_SHEET, layout.COST_ITEM_SHEET):
            actual = actual_names.get(normalize_name(name))
            if actual is None:
                self._issues.append(
                    SourceIssue(name, messages.SOURCE_LOCATION_WHOLE_SHEET, 'MISSING_SHEET', {'ten': name})
                )
            else:
                sheets[name] = _Sheet(workbook[actual])
        return sheets

    def _read_summary(self, sheet: _Sheet) -> None:
        header_row = sheet.find_header_row(layout.MONTH_HEADER, layout.CUSTOMER_CODE_HEADER)
        if header_row is None:
            self._issues.append(_column_issue(sheet.title, 1, layout.MONTH_HEADER, 'MISSING_COLUMN'))
            return
        columns = self._resolve_summary_columns(sheet, header_row)
        if columns is None:
            return
        for cells, month, customer_code, customer_name in _customer_rows(sheet, header_row, columns):
            common = {
                'ky_thang': month,
                'ma_khach': customer_code,
                'ma_nhom_kd': _cell_at(cells, columns.business_group),
            }
            results = {name: _cell_at(cells, index) for name, index in columns.results.items()}
            self._tables[layout.RESULTS_TABLE].append(common | {'ten_khach': customer_name} | results)
            for index in columns.costs:
                cost_code = columns.cost_codes[index] if index < len(columns.cost_codes) else None
                self._tables[layout.COSTS_TABLE].append(
                    common
                    | {
                        'ma_khoan_cp': cost_code,
                        'cap_phan_bo': layout.ALLOCATION_LEVEL,
                        'so_tien': _cell_at(cells, index),
                    }
                )

    def _resolve_summary_columns(self, sheet: _Sheet, header_row: int) -> _SummaryColumns | None:
        cost_codes = _stripped_cells(sheet, header_row - 1) if header_row > 1 else []
        cost_groups = _stripped_cells(sheet, header_row - 2) if header_row > 2 else []
        issue_count = len(self._issues)
        resolver = _ColumnResolver(sheet, header_row, cost_codes, self._issues)
        month = resolver.by_header(layout.MONTH_HEADER)
        business_group = resolver.by_header(layout.BUSINESS_GROUP_HEADER)
        customer_code = resolver.by_header(layout.CUSTOMER_CODE_HEADER)
        customer_name = resolver.by_header(layout.CUSTOMER_NAME_HEADER)
        results = {name: resolver.by_code(code) for name, code in layout.RESULT_COLUMNS_BY_CODE.items()}
        results |= {
            name: resolver.by_header(header, anchor)
            for name, (header, anchor) in layout.RESULT_COLUMNS_BY_HEADER.items()
        }
        costs = [i for i, group in enumerate(cost_groups) if group is not None]
        costs += [i for i in (resolver.by_header(header) for header in layout.UNGROUPED_COST_HEADERS) if i is not None]
        if len(self._issues) > issue_count:
            return None
        return _SummaryColumns(month, business_group, customer_code, customer_name, results, costs, cost_codes)

    def _read_catalog(self, sheet: _Sheet, catalog: layout.CatalogSheet) -> None:
        header_row = sheet.find_header_row(catalog.code_header, catalog.name_header)
        if header_row is None:
            self._issues.append(_column_issue(sheet.title, 1, catalog.code_header, 'MISSING_COLUMN'))
            return
        headers = sheet.normalized_cells(header_row)
        code_column = headers.index(normalize_name(catalog.code_header))
        name_column = headers.index(normalize_name(catalog.name_header))
        for row_number in range(header_row + 1, sheet.last_row + 1):
            cells = sheet.cells(row_number)
            if layout.is_marker_row(cells):
                continue
            values = [_cell_at(cells, code_column), _cell_at(cells, name_column)]
            if any(value is not None for value in values):
                self._tables[catalog.table].append(dict(zip(catalog.columns, values, strict=True)))


def _empty_tables() -> dict[str, list[FlatRow]]:
    return {name: [] for name in layout.FLAT_TABLES}


def _column_issue(sheet: str, row_number: int, name: str, code: str) -> SourceIssue:
    return SourceIssue(sheet, messages.SOURCE_LOCATION_ROW.format(row=row_number), code, {'ten': name})


def _stripped_cells(sheet: _Sheet, row_number: int) -> list[str | None]:
    return [None if is_blank(value) else str(value).strip() for value in sheet.cells(row_number)]


def _cell_at(cells: list[Any], index: int) -> str | None:
    return cell_text(cells[index]) if index < len(cells) else None


def _customer_rows(
    sheet: _Sheet, header_row: int, columns: _SummaryColumns
) -> Iterator[tuple[list[Any], str, str | None, str | None]]:
    cumulative_marker = normalize_name(layout.CUMULATIVE_MARKER)
    for row_number in range(header_row + 1, sheet.last_row + 1):
        cells = sheet.cells(row_number)
        if layout.is_marker_row(cells):
            continue
        month = _cell_at(cells, columns.month)
        if month is not None and normalize_name(month) == cumulative_marker:
            break
        customer_code = _cell_at(cells, columns.customer_code)
        customer_name = _cell_at(cells, columns.customer_name)
        if month is None or (customer_code is None and customer_name is None):
            continue
        if layout.is_total_row(customer_code, customer_name):
            continue
        yield cells, month, customer_code, customer_name
