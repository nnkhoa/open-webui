from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import customer_report_layout as layout
from .base import normalize_name
from .xlsx_verify import Grid, VerifyTable, XlsxXmlReader

FlatRow = dict[str, str | None]


@dataclass(frozen=True)
class _SummaryColumns:
    month: int | None
    business_group: int | None
    customer_code: int | None
    customer_name: int | None
    results: dict[str, int | None]
    costs: list[int | None]
    cost_codes: dict[int, str]


class CustomerReportVerifyReader:
    def __init__(self, path: Path) -> None:
        reader = XlsxXmlReader(path)
        try:
            results, costs = _read_summary(reader.grid(layout.SUMMARY_SHEET))
            customers = _read_catalog(reader.grid(layout.CUSTOMER_LIST_SHEET), layout.CUSTOMER_CATALOG)
            cost_items = _read_catalog(reader.grid(layout.COST_ITEM_SHEET), layout.COST_ITEM_CATALOG)
        finally:
            reader.close()
        self._tables: dict[str, list[FlatRow]] = {
            layout.RESULTS_TABLE: results,
            layout.COSTS_TABLE: costs,
            layout.CUSTOMERS_TABLE: customers,
            layout.COST_ITEMS_TABLE: [
                row | {'nhom_chi_phi': layout.cost_group(row['ma_khoan_cp'])} for row in cost_items
            ],
        }

    def close(self) -> None:
        return None

    def read_table(self, sheet_name: str) -> VerifyTable:
        name = next(table for table in layout.FLAT_TABLES if normalize_name(table) == normalize_name(sheet_name))
        headers = dict(enumerate(layout.FLAT_TABLES[name], start=1))
        rows = {
            row_number: {index: row[column] for index, column in headers.items() if row.get(column) is not None}
            for row_number, row in enumerate(self._tables[name], start=2)
        }
        return VerifyTable(headers, rows)


def _find_header_row(grid: Grid, *headers: str) -> int | None:
    required = {normalize_name(header) for header in headers}
    for row_number in sorted(grid):
        if row_number > layout.HEADER_SEARCH_ROWS:
            break
        if required <= {normalize_name(value) for value in grid[row_number].values()}:
            return row_number
    return None


def _column(cells: dict[int, str], header: str, start: int = 0) -> int | None:
    matches = [
        column for column, value in cells.items() if normalize_name(value) == normalize_name(header) and column >= start
    ]
    return min(matches) if matches else None


def _summary_columns(grid: Grid, header_row: int) -> _SummaryColumns:
    headers = grid[header_row]
    cost_codes = {column: value.strip() for column, value in grid.get(header_row - 1, {}).items()}
    cost_groups = {column: value.strip() for column, value in grid.get(header_row - 2, {}).items()}
    results: dict[str, int | None] = {
        name: next((column for column, value in cost_codes.items() if value == code), None)
        for name, code in layout.RESULT_COLUMNS_BY_CODE.items()
    }
    for name, (header, anchor) in layout.RESULT_COLUMNS_BY_HEADER.items():
        anchor_column = _column(headers, anchor) if anchor else None
        results[name] = _column(headers, header, anchor_column + 1 if anchor_column else 0)
    return _SummaryColumns(
        month=_column(headers, layout.MONTH_HEADER),
        business_group=_column(headers, layout.BUSINESS_GROUP_HEADER),
        customer_code=_column(headers, layout.CUSTOMER_CODE_HEADER),
        customer_name=_column(headers, layout.CUSTOMER_NAME_HEADER),
        results=results,
        costs=sorted(cost_groups) + [_column(headers, header) for header in layout.UNGROUPED_COST_HEADERS],
        cost_codes=cost_codes,
    )


def _read_summary(grid: Grid) -> tuple[list[FlatRow], list[FlatRow]]:
    header_row = _find_header_row(grid, layout.MONTH_HEADER, layout.CUSTOMER_CODE_HEADER)
    if header_row is None:
        return [], []
    columns = _summary_columns(grid, header_row)
    cumulative_marker = normalize_name(layout.CUMULATIVE_MARKER)
    results: list[FlatRow] = []
    costs: list[FlatRow] = []
    for row_number in sorted(row for row in grid if row > header_row):
        cells = grid[row_number]
        if layout.is_marker_row(list(cells.values())):
            continue
        month = cells.get(columns.month)
        if month is not None and normalize_name(month) == cumulative_marker:
            break
        customer_code, customer_name = cells.get(columns.customer_code), cells.get(columns.customer_name)
        if month is None or (customer_code is None and customer_name is None):
            continue
        if layout.is_total_row(customer_code, customer_name):
            continue
        common = {'ky_thang': month, 'ma_khach': customer_code, 'ma_nhom_kd': cells.get(columns.business_group)}
        results.append(
            common
            | {'ten_khach': customer_name}
            | {name: cells.get(column) for name, column in columns.results.items()}
        )
        costs.extend(
            common
            | {
                'ma_khoan_cp': columns.cost_codes.get(column),
                'cap_phan_bo': layout.ALLOCATION_LEVEL,
                'so_tien': cells.get(column),
            }
            for column in columns.costs
        )
    return results, costs


def _read_catalog(grid: Grid, catalog: layout.CatalogSheet) -> list[FlatRow]:
    header_row = _find_header_row(grid, catalog.code_header, catalog.name_header)
    if header_row is None:
        return []
    code_column = _column(grid[header_row], catalog.code_header)
    name_column = _column(grid[header_row], catalog.name_header)
    rows: list[FlatRow] = []
    for row_number in sorted(row for row in grid if row > header_row):
        if layout.is_marker_row(list(grid[row_number].values())):
            continue
        values = (grid[row_number].get(code_column), grid[row_number].get(name_column))
        if any(value is not None for value in values):
            rows.append(dict(zip(catalog.columns, values, strict=True)))
    return rows
