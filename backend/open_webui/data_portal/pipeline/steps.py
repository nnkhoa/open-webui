from __future__ import annotations

from typing import NamedTuple

from .. import messages
from ..formatting import format_integer
from .error_codes import error_code
from .file_check import TOTAL_KIND_QUANTITY

STATUS_OK = 'ok'
STATUS_ERROR = 'err'
STATUS_SKIPPED = 'skip'

STEP_NAMES = {
    'A1': messages.STEP_NAME_A1,
    'A2': messages.STEP_NAME_A2,
    'A3': messages.STEP_NAME_A3,
    'A4': messages.STEP_NAME_A4,
    'A5': messages.STEP_NAME_A5,
    'B1': messages.STEP_NAME_B1,
    'B2': messages.STEP_NAME_B2,
    'B3': messages.STEP_NAME_B3,
    'B4': messages.STEP_NAME_B4,
    'B5': messages.STEP_NAME_B5,
}
WRITE_STEP_CODES = ('B1', 'B2', 'B3', 'B4', 'B5')


class StepOutcome(NamedTuple):
    code: str
    passed: bool
    match_result: str
    mismatch_result: str


def b4_name(file_check: dict) -> str:
    if any(table.get('loai_tong') == TOTAL_KIND_QUANTITY for table in file_check['bang']):
        return messages.STEP_NAME_B4_QUANTITY
    return STEP_NAMES['B4']


def check_steps(file_check: dict, *, user: str, a4_result: str | None, single_table: bool = False) -> list[dict]:
    failed_step = file_check.get('buoc_loi')
    steps = [
        _step(
            'A1',
            messages.STEP_A1_RESULT.format(count=format_integer(file_check['so_sheet'])),
            messages.STEP_VERDICT_CORRECT,
            STATUS_OK,
        ),
        _a2_step(file_check),
        _a3_step(file_check, single_table),
    ]
    if failed_step:
        steps += [_skipped('A4', failed_step), _skipped('A5', failed_step)]
    else:
        steps.append(_step('A4', a4_result or messages.STEP_A4_SHOWN, messages.STEP_VERDICT_DONE, STATUS_OK))
        steps.append(
            _step('A5', messages.STEP_A5_CONFIRMED.format(user=user), messages.STEP_VERDICT_CONFIRMED, STATUS_OK)
        )
    return steps


def rejected_write_steps(failed_step: str, b4_step_name: str) -> list[dict]:
    return [_skipped(code, failed_step, b4_step_name if code == 'B4' else '') for code in WRITE_STEP_CODES]


def write_steps(outcomes: list[StepOutcome], *, commit_result: str, b4_step_name: str) -> list[dict]:
    steps: list[dict] = []
    mismatched = False
    for outcome in outcomes:
        name = b4_step_name if outcome.code == 'B4' else ''
        if mismatched:
            steps.append(
                _step(
                    outcome.code,
                    messages.STEP_CANCELLED_WITH_PREVIOUS,
                    messages.STEP_VERDICT_CANCELLED,
                    STATUS_SKIPPED,
                    name,
                )
            )
        elif outcome.passed:
            verdict = messages.STEP_VERDICT_CORRECT if outcome.code == 'B4' else messages.STEP_VERDICT_MATCH
            steps.append(_step(outcome.code, outcome.match_result, verdict, STATUS_OK, name))
        else:
            steps.append(
                _step(outcome.code, outcome.mismatch_result, messages.STEP_VERDICT_MISMATCH, STATUS_ERROR, name)
            )
            mismatched = True
    if mismatched:
        steps.append(_step('B5', messages.STEP_NOTHING_SAVED, messages.STEP_VERDICT_CANCELLED, STATUS_SKIPPED))
    else:
        steps.append(_step('B5', commit_result, messages.STEP_VERDICT_COMMITTED, STATUS_OK))
    return steps


def _errors_summary(errors: list[dict]) -> str:
    kinds = _error_kinds(errors)
    count = format_integer(len(errors))
    if kinds:
        return messages.STEP_ERRORS_WITH_KINDS.format(count=count, kinds=kinds)
    return messages.STEP_ERRORS.format(count=count)


def _a3_result(file_check: dict, single_table: bool) -> str:
    tables = file_check['bang']
    parts = [_a3_single_table_read(file_check) if single_table else _a3_read(tables)]
    empty_cells = sum(table['o_trong'] for table in tables)
    if empty_cells:
        parts.append(messages.STEP_A3_EMPTY_CELLS.format(count=format_integer(empty_cells)))
    to_write = sum(table['se_ghi'] for table in tables)
    parts.append(messages.STEP_A3_TO_WRITE.format(count=format_integer(to_write)))
    return ' '.join(parts)


def _step(code: str, result: str, verdict: str, status: str, name: str = '') -> dict:
    return {'ma': code, 'ten': name or STEP_NAMES[code], 'ket_qua': result, 'ket_luan': verdict, 'trang_thai': status}


def _skipped(code: str, failed_step: str, name: str = '') -> dict:
    result = messages.STEP_NOT_RUN.format(step=failed_step)
    return _step(code, result, messages.STEP_VERDICT_NOT_RUN, STATUS_SKIPPED, name)


def _error_kinds(errors: list[dict]) -> str:
    kinds: list[str] = []
    for error in errors:
        kind = error_code(error.get('reason_code') or '').kind
        if kind and kind not in kinds:
            kinds.append(kind)
    return ', '.join(kinds)


def _a2_step(file_check: dict) -> dict:
    if file_check.get('buoc_loi') == 'A2':
        result = file_check.get('cau_loi_a2') or _errors_summary(file_check['loi'])
        return _step('A2', result, messages.STEP_VERDICT_WRONG, STATUS_ERROR)
    if file_check.get('sheet_du_lieu') and file_check.get('dong_tieu_de'):
        result = messages.STEP_A2_HEADER_TABLE.format(
            sheet=file_check['sheet_du_lieu'],
            column_count=format_integer(file_check['so_cot_can']),
            header_row=format_integer(file_check['dong_tieu_de']),
        )
        return _step('A2', result, messages.STEP_VERDICT_CORRECT, STATUS_OK)
    table_sheets = {table['sheet'] for table in file_check['bang']}
    sheets = [sheet for sheet in file_check['cac_sheet'] if sheet in table_sheets]
    result = messages.STEP_A2_SHEETS.format(count=format_integer(len(sheets)), sheets=', '.join(sheets))
    return _step('A2', result, messages.STEP_VERDICT_CORRECT, STATUS_OK)


def _a3_step(file_check: dict, single_table: bool) -> dict:
    failed_step = file_check.get('buoc_loi')
    if failed_step == 'A2':
        return _skipped('A3', 'A2')
    if failed_step == 'A3':
        return _step('A3', _errors_summary(file_check['loi']), messages.STEP_VERDICT_WRONG, STATUS_ERROR)
    return _step('A3', _a3_result(file_check, single_table), messages.STEP_VERDICT_VALID, STATUS_OK)


def _a3_single_table_read(file_check: dict) -> str:
    tables = file_check['bang']
    row_range = ''
    if file_check.get('dong_tu') and file_check.get('dong_den'):
        row_range = messages.STEP_A3_ROW_RANGE.format(
            first=format_integer(file_check['dong_tu']), last=format_integer(file_check['dong_den'])
        )
    read = format_integer(sum(table['doc'] for table in tables))
    duplicates = sum(table['trung_bo'] for table in tables)
    if not duplicates:
        return messages.STEP_A3_READ_NO_DUPLICATES.format(count=read, row_range=row_range)
    return messages.STEP_A3_READ_WITH_DUPLICATES.format(
        count=read, row_range=row_range, duplicates=format_integer(duplicates)
    )


def _a3_read(tables: list[dict]) -> str:
    parts = [messages.STEP_A3_READ.format(count=format_integer(sum(table['doc'] for table in tables)))]
    for table in tables:
        if table['trung_bo']:
            parts.append(
                messages.STEP_A3_TABLE_DUPLICATES.format(
                    duplicates=format_integer(table['trung_bo']),
                    table=table['ten_bang'],
                    read=format_integer(table['doc']),
                    to_write=format_integer(table['se_ghi']),
                )
            )
    return ' '.join(parts)
