from __future__ import annotations

import datetime as dt
import json
import time
from dataclasses import dataclass
from pathlib import Path

from .. import messages
from ..db import sql as warehouse_sql
from ..db.lock import acquire_write_locks
from ..errors import ReconcileError, StructureError
from ..formatting import format_integer
from ..registry.schema import Form, FormTable
from ..sources import customer_report, header_table  # noqa: F401
from ..sources.base import open_reader
from . import bronze, doi_chieu_the, gold, reconcile, silver, steps
from .context import LoadContext
from .file_check import check_file
from .reconcile import Mismatch
from .steps import StepOutcome
from .structure import check_structure
from .validate import validate_rows

STEP_OF_RULE = {'R1': 'B1', 'R2': 'B2', 'R4a': 'B2', 'R3': 'B3', 'R4c': 'B4'}
R1_DIFFERENCE_KEYS = ('o_lech', 'thieu_o_goc', 'thua_o_goc')


@dataclass
class LoadRequest:
    domain_id: int
    domain_code: str
    form_id: int
    upload_id: int
    upload_path: Path
    file_name: str
    actor_username: str
    request_id: str
    year: int | None = None
    file_check: dict | None = None
    a4_result: str | None = None
    actor_user_id: int | None = None


def run_load(conn, form: Form, request: LoadRequest) -> int:
    started = time.monotonic()
    ctx = _open_load(conn, form, request)
    table_ids = _table_ids(conn, request.form_id)
    acquire_write_locks(conn, [(request.domain_id, request.form_id)])
    ctx.reader = open_reader(form.source_kind, request.upload_path, form)
    try:
        return _run_locked(ctx, table_ids, started, request.file_check, request.a4_result)
    finally:
        ctx.reader.close()


def _open_load(conn, form: Form, request: LoadRequest) -> LoadContext:
    load_id = warehouse_sql.scalar(
        conn,
        """
        INSERT INTO ctl.load (upload_id, domain_id, form_id, form_version, status,
                              actor_user_id, actor_username, request_id, nam)
             VALUES (%s, %s, %s, %s, 'running', %s, %s, %s, %s)
          RETURNING load_id
        """,
        (
            request.upload_id,
            request.domain_id,
            request.form_id,
            form.version,
            request.actor_user_id,
            request.actor_username,
            request.request_id,
            request.year,
        ),
    )
    batch_id = warehouse_sql.scalar(
        conn,
        "INSERT INTO ctl.batch (load_id, domain_id, form_id, state) VALUES (%s, %s, %s, 'open') RETURNING batch_id",
        (load_id, request.domain_id, request.form_id),
    )
    warehouse_sql.execute(conn, 'UPDATE ctl.load SET batch_id = %s WHERE load_id = %s', (batch_id, load_id))
    return LoadContext(
        conn=conn,
        form=form,
        domain_id=request.domain_id,
        domain_code=request.domain_code,
        form_id=request.form_id,
        load_id=load_id,
        batch_id=batch_id,
        upload_path=request.upload_path,
        file_name=request.file_name,
        actor_user_id=request.actor_user_id,
        actor_username=request.actor_username,
        request_id=request.request_id,
        year=request.year,
    )


def _table_ids(conn, form_id: int) -> dict[str, int]:
    rows = warehouse_sql.query(conn, 'SELECT table_id, name FROM ctl.form_table WHERE form_id = %s', (form_id,))
    return {row['name']: row['table_id'] for row in rows}


def _run_locked(
    ctx: LoadContext, table_ids: dict[str, int], started: float, file_check: dict | None, a4_result: str | None
) -> int:
    errors = check_structure(ctx.reader, ctx.form)
    if errors:
        raise StructureError(errors)
    if file_check is None:
        file_check = check_file(ctx.form, ctx.upload_path, ctx.year)
    ctx.sheets_count = _matched_sheet_count(ctx)

    before = doi_chieu_the.chup_truoc(ctx)
    _write_layers(ctx, table_ids)

    mismatches = reconcile.run_reconciliation(ctx, table_ids)
    cards = doi_chieu_the.tinh(ctx, before, file_check)
    load_steps = _load_steps(ctx, file_check, a4_result, cards, mismatches)
    if mismatches or cards['lech']:
        mismatches += [
            Mismatch('B4', None, doi_chieu_the.TIEU_DE.get(key, key), messages.RECONCILE_STEP_CARDS)
            for key in cards['lech']
        ]
        raise ReconcileError(mismatches, steps=load_steps, reconciliation=cards['the'])

    _commit(ctx, started, file_check, load_steps, cards['the'])
    return ctx.load_id


def _matched_sheet_count(ctx: LoadContext) -> int:
    return sum(
        1 for table in ctx.form.tables if any(sheet.lower() == table.sheet.lower() for sheet in ctx.reader.sheets())
    )


def _write_layers(ctx: LoadContext, table_ids: dict[str, int]) -> None:
    for table in ctx.form.tables_by_dependency:
        bronze_rows = bronze.write(ctx, table)
        ctx.clean_rows[table.name], duplicates = validate_rows(table, bronze_rows)
        ctx.table_result(table).rows_duplicate = len(duplicates)
        _record_periods(ctx, table)

    for table in ctx.form.tables_by_dependency:
        silver.merge(ctx, table, ctx.clean_rows[table.name])
        gold.build(ctx, table)
        silver.write_partitions(ctx, table, table_ids[table.name])


def _record_periods(ctx: LoadContext, table: FormTable) -> None:
    if not table.partition_by:
        return
    column = table.partition_column
    periods = set()
    for row in ctx.clean_rows.get(table.name, []):
        value = row.values.get(column.name)
        if value is not None:
            periods.add(column.display(value) if column.type == 'month' else str(value))
    ctx.touched_periods[table.name] = periods


def _commit(ctx: LoadContext, started: float, file_check: dict, load_steps: list[dict], cards) -> None:
    duration_ms = int((time.monotonic() - started) * 1000)
    warehouse_sql.execute(
        ctx.conn,
        """
        UPDATE ctl.load
           SET status = 'success', rows_read = %s,
               rows_written = %s, sheets_count = %s, finished_at = %s,
               duration_ms = %s, report = %s, message = NULL,
               kiem_tra = %s, cac_buoc = %s, doi_chieu = %s
         WHERE load_id = %s
        """,
        (
            ctx.rows_read,
            ctx.rows_written,
            ctx.sheets_count,
            dt.datetime.now(dt.UTC),
            duration_ms,
            _json(ctx.report()),
            _json(file_check),
            _json(load_steps),
            _json(cards),
            ctx.load_id,
        ),
    )
    warehouse_sql.execute(
        ctx.conn,
        "UPDATE ctl.batch SET state = 'current', closed_at = now() WHERE batch_id = %s",
        (ctx.batch_id,),
    )


def _load_steps(
    ctx: LoadContext, file_check: dict, a4_result: str | None, cards: dict, mismatches: list[Mismatch]
) -> list[dict]:
    single_table = len(ctx.form.tables) == 1
    check = steps.check_steps(file_check, user=ctx.actor_username, a4_result=a4_result, single_table=single_table)

    mismatched = _mismatched_tables_by_step(mismatches)
    results = _results_by_rule(ctx)
    to_write = {table['bang']: table['se_ghi'] for table in file_check.get('bang', [])}
    tables = [table for table in ctx.form.tables_by_display_order if ctx.table_result(table).rows_bronze]
    outcomes = [
        _b1_outcome(results.get('R1', []), mismatched),
        _b2_outcome(ctx, tables, to_write, results, mismatched),
        _b3_outcome(ctx, tables, results.get('R3', []), mismatched),
        _b4_outcome(results.get('R4c', []), cards),
    ]
    return check + steps.write_steps(
        outcomes, commit_result=_commit_result(ctx, file_check), b4_step_name=steps.b4_name(file_check)
    )


def _mismatched_tables_by_step(mismatches: list[Mismatch]) -> dict[str, list[str]]:
    by_step: dict[str, list[str]] = {}
    for mismatch in mismatches:
        by_step.setdefault(STEP_OF_RULE.get(mismatch.step, 'B4'), []).append(mismatch.label)
    return by_step


def _results_by_rule(ctx: LoadContext) -> dict[str, list[dict]]:
    by_rule: dict[str, list[dict]] = {}
    for result in reconcile.load_results(ctx.conn, ctx.load_id):
        by_rule.setdefault(result['step'], []).append(result)
    return by_rule


def _b1_outcome(results: list[dict], mismatched: dict[str, list[str]]) -> StepOutcome:
    file_rows = sum(int(result['expected'] or 0) for result in results)
    bronze_rows = sum(int(result['actual'] or 0) for result in results)
    failed = [result for result in results if not result['passed']]
    failed_labels = {result['table_label'] for result in failed}
    details = [
        messages.STEP_B1_TABLE_CELLS_DIFFER.format(
            table=result['table_label'], count=format_integer(_difference_count(result))
        )
        for result in failed
    ]
    details += [
        messages.STEP_B1_TABLE_DIFFERS.format(table=label)
        for label in mismatched.get('B1', [])
        if label not in failed_labels
    ]
    return StepOutcome(
        'B1',
        not failed and 'B1' not in mismatched,
        messages.STEP_B1_MATCH.format(file_rows=format_integer(file_rows), bronze_rows=format_integer(bronze_rows)),
        messages.STEP_B1_MISMATCH.format(details='; '.join(details)),
    )


def _b2_outcome(
    ctx: LoadContext,
    tables: list[FormTable],
    to_write: dict[str, int],
    results: dict[str, list[dict]],
    mismatched: dict[str, list[str]],
) -> StepOutcome:
    details = _b2_details(ctx, tables, to_write, results, mismatched)
    expected = sum(to_write.get(table.name, 0) for table in tables)
    actual = sum(_written_rows(ctx, table) for table in tables)
    return StepOutcome(
        'B2',
        not details,
        messages.STEP_B2_MATCH.format(expected=format_integer(expected), actual=format_integer(actual)),
        messages.STEP_B2_MISMATCH.format(details=', '.join(details)),
    )


def _b2_details(
    ctx: LoadContext,
    tables: list[FormTable],
    to_write: dict[str, int],
    results: dict[str, list[dict]],
    mismatched: dict[str, list[str]],
) -> list[str]:
    details: list[str] = []
    for table in tables:
        written = _written_rows(ctx, table)
        if written != to_write.get(table.name, written):
            difference = format_integer(abs(written - to_write[table.name]))
            details.append(messages.STEP_B2_TABLE_ROWS_DIFFER.format(table=table.label, count=difference))
    for result in results.get('R2', []) + results.get('R4a', []):
        if result['passed']:
            continue
        difference = format_integer(abs(int(result['diff'] or 0)))
        detail = messages.STEP_B2_TABLE_ROWS_DIFFER.format(table=result['table_label'], count=difference)
        if detail not in details:
            details.append(detail)
    for label in mismatched.get('B2', []):
        prefix = messages.STEP_TABLE.format(table=label) + ' '
        if not any(detail.startswith(prefix) for detail in details):
            details.append(messages.STEP_B2_TABLE_DIFFERS.format(table=label))
    return details


def _b3_outcome(
    ctx: LoadContext, tables: list[FormTable], results: list[dict], mismatched: dict[str, list[str]]
) -> StepOutcome:
    failed = [result for result in results if not result['passed']]
    failed_labels = {result['table_label'] for result in failed}
    unchanged = sum(ctx.table_result(table).rows_unchanged for table in tables)
    expected = sum(int(result['expected'] or 0) for result in results) + unchanged
    actual = sum(int(result['actual'] or 0) for result in results) + unchanged
    details = [
        messages.STEP_B3_TABLE_ROWS_DIFFER.format(
            table=result['table_label'],
            expected=format_integer(int(result['expected'] or 0)),
            actual=format_integer(int(result['actual'] or 0)),
        )
        for result in failed
    ]
    details += [
        messages.STEP_B3_TABLE_DIFFERS.format(table=label)
        for label in mismatched.get('B3', [])
        if label not in failed_labels
    ]
    return StepOutcome(
        'B3',
        not details,
        messages.STEP_B3_MATCH.format(expected=format_integer(expected), actual=format_integer(actual)),
        '; '.join(details) + '.',
    )


def _b4_outcome(results: list[dict], cards: dict) -> StepOutcome:
    failed = [result for result in results if not result['passed']]
    mismatch_result = cards['b4']
    if failed and not cards['lech']:
        tables = ', '.join(result['table_label'] for result in failed)
        mismatch_result = messages.STEP_B4_CONTROL_TOTAL_MISMATCH.format(tables=tables)
    return StepOutcome('B4', not failed and not cards['lech'], cards['b4'], mismatch_result)


def _written_rows(ctx: LoadContext, table: FormTable) -> int:
    result = ctx.table_result(table)
    return result.rows_silver + result.rows_unchanged


def _difference_count(result: dict) -> int:
    detail = result['detail'] or {}
    return sum(len(detail.get(key, [])) for key in R1_DIFFERENCE_KEYS)


def _commit_result(ctx: LoadContext, file_check: dict) -> str:
    if file_check.get('cau_chot'):
        return file_check['cau_chot']
    months = sorted(
        {
            int(period)
            for table in file_check.get('bang', [])
            for period in (table.get('theo_ky') or {})
            if str(period).isdigit()
        }
    )
    year = messages.STEP_B5_YEAR.format(year=ctx.year) if ctx.year else ''
    if not months:
        return messages.STEP_B5_EFFECTIVE.format(year=year)
    month_range = str(months[0]) if len(months) == 1 else f'{months[0]}–{months[-1]}'
    return messages.STEP_B5_MONTHS_EFFECTIVE.format(months=month_range, year=year)


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
