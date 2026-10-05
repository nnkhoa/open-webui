from __future__ import annotations

from .. import messages
from ..registry.schema import Form, FormTable
from ..sources.base import normalize_name
from .error_codes import error_code

HEADER_ROW = 1


def error_row(sheet: str | None, location: str, code: str, **params) -> dict:
    error = error_code(code)
    return {
        'sheet': sheet,
        'location': location,
        'issue': error.message(**params),
        'reason_code': code,
        'resolution': error.resolution,
        'cell_ref': params.get('cell_ref'),
    }


def check_structure(reader, form: Form) -> list[dict]:
    source_issues = reader.source_issues()
    if source_issues:
        return [error_row(issue.sheet, issue.location, issue.code, **issue.params) for issue in source_issues]

    errors: list[dict] = []
    if form.policy.unknown_sheet == 'reject':
        errors += _unknown_sheets(reader, form)
    file_sheets = {normalize_name(sheet) for sheet in reader.sheets()}
    for table in form.tables:
        if normalize_name(table.sheet) not in file_sheets:
            if form.policy.missing_column == 'reject':
                errors.append(
                    error_row(table.label, messages.SOURCE_LOCATION_WHOLE_SHEET, 'MISSING_SHEET', name=table.sheet)
                )
            continue
        errors += _check_sheet(reader, form, table)
    return errors


def _unknown_sheets(reader, form: Form) -> list[dict]:
    declared = {normalize_name(table.sheet) for table in form.tables}
    return [
        error_row(sheet, messages.SOURCE_LOCATION_WHOLE_SHEET, 'UNKNOWN_SHEET', name=sheet, cell_ref=sheet)
        for key, sheet in {normalize_name(s): s for s in reader.sheets()}.items()
        if key not in declared
    ]


def _check_sheet(reader, form: Form, table: FormTable) -> list[dict]:
    positions, unnamed_columns, duplicate_names = reader.column_layout(table.sheet)
    header_location = messages.SOURCE_LOCATION_ROW.format(row=HEADER_ROW)
    required = {normalize_name(column.file_header): column.file_header for column in table.file_columns}

    errors = [error_row(table.label, header_location, 'DUPLICATE_COLUMN', name=name) for name in duplicate_names]
    if form.policy.missing_column == 'reject':
        errors += [
            error_row(table.label, header_location, 'MISSING_COLUMN', name=name, cell_ref=f'{table.sheet}!1:1')
            for key, name in required.items()
            if key not in positions
        ]
    if form.policy.unknown_column == 'reject':
        errors += _unknown_columns(reader, table, positions, required)
    if not errors and unnamed_columns:
        errors += _cells_in_unnamed_columns(reader, table, unnamed_columns)
    return errors


def _unknown_columns(reader, table: FormTable, positions: dict[str, int], required: dict[str, str]) -> list[dict]:
    errors = []
    for key, index in positions.items():
        if key in required:
            continue
        letter = _column_letter(index)
        errors.append(
            error_row(
                table.label,
                messages.SOURCE_LOCATION_COLUMN.format(column=letter),
                'UNKNOWN_COLUMN',
                name=reader.header(table.sheet)[index - 1],
                cell_ref=f'{table.sheet}!{letter}{HEADER_ROW}',
            )
        )
    return errors


def _cells_in_unnamed_columns(reader, table: FormTable, unnamed_columns) -> list[dict]:
    return [
        error_row(
            table.label,
            messages.SOURCE_LOCATION_CELL.format(row=row, column=letter),
            'DATA_IN_UNNAMED_COLUMN',
            cell_ref=f'{table.sheet}!{letter}{row}',
        )
        for row, letter in reader.cells_outside_columns(table.sheet, unnamed_columns)
    ]


def _column_letter(index: int) -> str:
    letters = ''
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters
