from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from .. import messages
from ..errors import StructureError
from ..registry.schema import Form, FormTable
from ..sources import customer_report, header_table  # noqa: F401
from ..sources.base import open_reader
from ..sources.header_table import HeaderTableInfo
from ..sources.xlsx import sheet_names
from .bronze import fill_derived_columns
from .context import BronzeRow, CleanRow
from .dedup import hash_row
from .normalize import normalize_rows
from .structure import check_structure
from .validate import UnparsedCells, validate_rows

TOTAL_KIND_QUANTITY = 'quantity'
TOTAL_KIND_AMOUNT = 'amount'
QUANTITY_COLUMN = 'so_luong'
CONFIRM_GROUPING = {
    'fact_may_mau': 'ma_nhom_kd',
    'fact_gia_cong': 'ma_don_vi_gc',
}


@dataclass
class _GroupTotals:
    row_count: int = 0
    quantity: Decimal = Decimal(0)


@dataclass
class _PeriodTotals:
    row_count: int = 0
    total: Decimal = Decimal(0)
    columns: set[str] = field(default_factory=set)


def total_columns(table: FormTable) -> list[str]:
    kind = _total_kind(table)
    if kind == TOTAL_KIND_QUANTITY:
        return [QUANTITY_COLUMN]
    if kind == TOTAL_KIND_AMOUNT:
        return [column.name for column in table.amount_columns]
    return []


def check_file(form: Form, path: Path, year: int | None) -> dict:
    sheets = sheet_names(path)
    result: dict = {'sheet_count': len(sheets), 'sheets': sheets, 'errors': [], 'failed_step': None, 'tables': []}

    reader = open_reader(form.source_kind, path, form)
    try:
        errors = check_structure(reader, form)
        if errors:
            result.update(_structure_failure(form, errors))
            return result
        row_errors: list[dict] = []
        for table in form.tables_by_display_order:
            result['tables'].append(_check_table(reader, form, table, year, row_errors))
        if row_errors:
            result['errors'], result['failed_step'] = row_errors, 'A3'
        result['data_sheet'] = _data_sheet(reader, form)
        info = getattr(reader, 'info', None)
        if info is not None:
            result.update(_header_table_fields(info))
        if len(form.tables) == 1 and form.tables[0].merge == 'replace_all' and year:
            result['commit_result'] = _commit_result(form, year, info)
        return result
    finally:
        reader.close()


def check_form_match(form: Form, path: Path) -> list[dict]:
    reader = open_reader(form.source_kind, path, form)
    try:
        return check_structure(reader, form)
    finally:
        reader.close()


def _total_kind(table: FormTable) -> str | None:
    if any(column.name == QUANTITY_COLUMN and column.role == 'measure' for column in table.columns):
        return TOTAL_KIND_QUANTITY
    if table.amount_columns:
        return TOTAL_KIND_AMOUNT
    return None


def _source_sheet(reader, table: FormTable) -> str:
    resolve = getattr(reader, 'source_sheet', None)
    return resolve(table.sheet) if resolve else table.sheet


def _structure_failure(form: Form, errors: list[dict]) -> dict:
    failure: dict = {'errors': errors, 'failed_step': 'A2'}
    if any(error.get('reason_code') == 'NO_DATA_SHEET' for error in errors):
        failure['a2_error'] = messages.CHECK_NO_DATA_SHEET.format(
            count=len(form.tables[0].file_columns), form=form.label
        )
    return failure


def _commit_result(form: Form, year: int, info: HeaderTableInfo | None) -> str:
    version = ''
    if info is not None and info.report_date:
        version = messages.CHECK_REPORT_VERSION.format(date=info.report_date)
    return messages.CHECK_DATA_EFFECTIVE.format(form=form.label, year=year, version=version)


def _header_table_fields(info: HeaderTableInfo) -> dict:
    fields: dict = {
        'header_row': info.header_row,
        'required_column_count': info.required_column_count,
        'first_row': info.first_row,
        'last_row': info.last_row,
    }
    if info.total_cell is not None:
        fields['total_cell'] = {
            'reference': info.total_cell.reference,
            'value': info.total_cell.value,
            'header': info.total_cell.header,
            'informational': info.total_cell.informational,
        }
    if info.report_date is not None:
        fields['report_date'] = info.report_date
    fields['hidden_row_count'] = info.hidden_row_count
    fields['visible_row_count'] = info.visible_row_count
    return fields


def _data_sheet(reader, form: Form) -> str | None:
    sheets = {_source_sheet(reader, table) for table in form.tables}
    return sheets.pop().strip() if len(sheets) == 1 and len(form.tables) == 1 else None


def _read_rows(reader, table: FormTable, year: int | None) -> list[BronzeRow]:
    rows = []
    for row in reader.rows(table.sheet, table.header_map):
        row = fill_derived_columns(table, row, year, reader)
        rows.append(BronzeRow(0, row.number, hash_row(table.sheet, row.values, table.column_names), row.values))
    return rows


def _check_table(reader, form: Form, table: FormTable, year: int | None, errors: list[dict]) -> dict:
    rows = _read_rows(reader, table, year)
    unparsed: UnparsedCells = {}
    try:
        kept, duplicates = validate_rows(table, rows, unparsed)
        kept = normalize_rows(form, table, kept)
        missing_required = 0
    except StructureError as exc:
        errors += exc.errors
        missing_required = len(exc.errors)
        kept, duplicates = [], []

    summed_columns = total_columns(table)
    total = sum(
        (Decimal(row.values[c]) for row in kept for c in summed_columns if row.values.get(c) is not None),
        Decimal(0),
    )
    check = {
        'table': table.name,
        'table_name': table.label,
        'kind': table.kind,
        'sheet': _source_sheet(reader, table),
        'read': len(rows),
        'missing_required': missing_required,
        'duplicates': len(duplicates),
        'empty_cells': sum(sum(by_value.values()) for by_value in unparsed.values()),
        'empty_cell_details': [
            {
                'column': column,
                'cell_count': sum(by_value.values()),
                'values': [{'value': value, 'cell_count': count} for value, count in by_value.items()],
            }
            for column, by_value in unparsed.items()
        ],
        'to_write': len(kept),
        'total_kind': _total_kind(table),
        'total': str(total) if summed_columns else None,
        'total_column_count': len(table.file_columns),
        'verdict': messages.CHECK_INVALID if missing_required else messages.CHECK_VALID,
    }
    if table.partition_by:
        check['by_period'] = _by_period(table, kept, summed_columns)
    if table.name in CONFIRM_GROUPING:
        check['by_group'] = _by_group(table, kept)
    return check


def _by_group(table: FormTable, kept: list[CleanRow]) -> dict:
    column = CONFIRM_GROUPING[table.name]
    groups: dict[str, _GroupTotals] = {}
    for row in kept:
        value = row.values.get(column)
        key = '' if value is None else str(value)
        totals = groups.setdefault(key, _GroupTotals())
        totals.row_count += 1
        if row.values.get(QUANTITY_COLUMN) is not None:
            totals.quantity += Decimal(row.values[QUANTITY_COLUMN])
    return {
        'column': column,
        'order': list(groups),
        'groups': {
            key: {'row_count': totals.row_count, 'quantity': str(totals.quantity)} for key, totals in groups.items()
        },
    }


def _by_period(table: FormTable, rows: list[CleanRow], summed_columns: list[str]) -> dict[str, dict]:
    period_column = table.partition_column
    file_columns = [column.name for column in table.file_columns]
    periods: dict[str, _PeriodTotals] = {}
    for row in rows:
        value = row.values.get(period_column.name)
        if value is None:
            continue
        period = period_column.display(value) if period_column.type == 'month' else str(value)
        totals = periods.setdefault(period, _PeriodTotals())
        totals.row_count += 1
        totals.total += sum((row.values[c] for c in summed_columns if row.values.get(c) is not None), Decimal(0))
        totals.columns.update(c for c in file_columns if row.values.get(c) is not None)
    return {
        period: {'row_count': totals.row_count, 'total': str(totals.total), 'column_count': len(totals.columns)}
        for period, totals in periods.items()
    }
