from __future__ import annotations

import datetime as dt
import json
import shutil
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import BinaryIO

from psycopg import sql

from .. import messages
from ..container import Container
from ..db import sql as warehouse_sql
from ..errors import NotFound, ReconcileError, SourceFileError, StructureError
from ..registry.schema import Form, FormTable
from ..security.audit import record_event
from ..sources.header_table import KIND as HEADER_TABLE_KIND
from . import dedup, orchestrator, pending_uploads, steps
from .file_check import GROUP_BY_MONTH, check_file
from .orchestrator import LoadRequest
from .pending_uploads import PendingMetadata, PendingUpload
from .reconcile import STEP_LABELS, Mismatch

YEARS = tuple(range(2025, 2032))
STATUS_REJECTED = 'rejected'
STATUS_MISMATCH = 'mismatch'
STATUS_SUCCESS = 'success'
MISMATCH_REASON_CODE = 'RECON_MISMATCH'


@dataclass
class UploadRequest:
    domain_id: int
    domain_code: str
    form_id: int
    form: Form
    year: int
    file_name: str
    source: BinaryIO
    user_id: str
    user_name: str
    request_id: str


@dataclass
class FailedLoad:
    status: str
    errors: list[dict]
    metadata: PendingMetadata
    storage_uri: str
    request_id: str
    file_check: dict | None
    steps: list[dict] | None
    reconciliation: dict | None = None


def check_upload(container: Container, request: UploadRequest) -> dict:
    upload_dir = container.settings.upload_dir
    pending_uploads.delete_expired(upload_dir)
    pending = pending_uploads.save(upload_dir, request.source, _new_metadata(request))
    sha256, size_bytes = dedup.hash_file(pending.file_path)
    try:
        file_check = check_file(request.form, pending.file_path, request.year)
    except SourceFileError:
        pending_uploads.delete(pending)
        raise
    pending.metadata.sha256 = sha256
    pending.metadata.size_bytes = size_bytes
    pending.metadata.file_check = file_check

    if file_check['errors']:
        load_id = _reject_checked_upload(container, request, pending, file_check)
        return {'load_id': load_id, 'status': STATUS_REJECTED}

    pending_uploads.write_metadata(pending)
    return {'pending_id': pending.pending_id}


def confirm_upload(container: Container, pending: PendingUpload, *, request_id: str) -> dict:
    form = container.registry.form(pending.metadata.file_type)
    claimed = pending_uploads.claim(pending)
    if claimed is None:
        raise NotFound(messages.UPLOAD_PENDING_EXPIRED)
    storage_path = _archive(container.settings.upload_dir, claimed)
    try:
        result = _write_claimed(container, form, claimed, storage_path, request_id)
    except BaseException:
        storage_path.unlink(missing_ok=True)
        pending_uploads.release(claimed)
        raise
    finally:
        if claimed.directory.exists() and claimed.is_claimed:
            pending_uploads.delete(claimed)

    if result['status'] == STATUS_SUCCESS:
        with container.catalog.transaction() as catalog_conn:
            _record_load_event(catalog_conn, STATUS_SUCCESS, result['load_id'], claimed.metadata, request_id)
    return result


def pending_upload_view(conn, form: Form, pending: PendingUpload) -> dict:
    metadata = pending.metadata
    file_check = metadata.file_check
    view = {
        'pending_id': pending.pending_id,
        'domain': metadata.domain,
        'year': metadata.year,
        'file_type': {'code': form.code, 'name': form.label, 'subtitle': form.subtitle},
        'file_name': metadata.file_name,
        'size_bytes': metadata.size_bytes,
        'sheet': file_check.get('data_sheet'),
        'checks': [_table_check_view(table) for table in file_check['tables']],
        'identical': _identical_load(conn, metadata.domain_id, metadata.form_id, metadata.year, metadata.sha256),
        'overwrite': [],
        'new': [],
        'previous': None,
    }
    if form.source_kind == HEADER_TABLE_KIND:
        view.update(_header_table_groups(conn, form, metadata.domain_id, metadata.year, file_check))
    else:
        view.update(_monthly_groups(conn, form, metadata.domain_id, metadata.year, file_check))
    return view


def _record_failed_load(container: Container, failed: FailedLoad) -> int:
    metadata = failed.metadata
    with container.warehouse.transaction() as conn:
        upload_id = _insert_upload(conn, metadata, failed.storage_uri)
        load_id = _insert_failed_load(conn, upload_id, failed)
    with container.catalog.transaction() as catalog_conn:
        _record_load_event(catalog_conn, failed.status, load_id, metadata, failed.request_id)
    return load_id


def _mismatch_errors(mismatches: list[Mismatch]) -> list[dict]:
    return [
        {
            'sheet': mismatch.label,
            'location': STEP_LABELS.get(mismatch.step, mismatch.step_label or mismatch.step),
            'issue': messages.RECONCILE_MISMATCH_ISSUE.format(step=mismatch.step),
            'reason_code': MISMATCH_REASON_CODE,
            'resolution': messages.RECONCILE_MISMATCH_RESOLUTION,
            'step': mismatch.step,
            'cell_ref': None,
        }
        for mismatch in mismatches
    ]


def _identical_load(conn, domain_id: int, form_id: int, year: int | None, file_sha256: str) -> dict | None:
    row = warehouse_sql.query_one(
        conn,
        'SELECT l.load_id, l.started_at, l.actor_username FROM ctl.load l '
        '  JOIN ctl.upload u USING (upload_id) '
        ' WHERE l.domain_id = %s AND l.form_id = %s AND u.file_sha256 = %s '
        "   AND l.year IS NOT DISTINCT FROM %s AND l.status = 'success' "
        ' ORDER BY l.load_id DESC LIMIT 1',
        (domain_id, form_id, file_sha256, year),
    )
    return _load_summary(row) if row else None


def _existing_periods(conn, table: FormTable, domain_id: int, year: int | None) -> dict[str, dict]:
    year_condition = sql.SQL('')
    params: list = [domain_id]
    if table.year_column is not None:
        year_condition = sql.SQL(' AND s.{} IS NOT DISTINCT FROM %s').format(sql.Identifier(table.year_column.name))
        params.append(year)
    rows = warehouse_sql.query(
        conn,
        sql.SQL(
            'SELECT s.{column}::text AS period, count(*) AS row_count, max(s.load_id) AS load_id '
            '  FROM {source} s WHERE s.domain_id = %s AND s.is_current{year} GROUP BY 1'
        ).format(
            column=sql.Identifier(table.partition_column.name),
            source=sql.Identifier('silver', table.name),
            year=year_condition,
        ),
        params,
    )
    return _with_load_summaries(conn, rows, 'period')


def _existing_data(conn, table: FormTable, domain_id: int, year: int | None) -> dict | None:
    row = warehouse_sql.query_one(
        conn,
        sql.SQL(
            'SELECT count(*) AS row_count, max(load_id) AS load_id FROM {} '
            ' WHERE domain_id = %s AND is_current AND nam IS NOT DISTINCT FROM %s'
        ).format(sql.Identifier('silver', table.name)),
        (domain_id, year),
    )
    if not row or not row['row_count']:
        return None
    summary = _load_summaries(conn, [row['load_id']]).get(row['load_id']) or {}
    return {'row_count': row['row_count'], **summary}


def _a4_result(conn, form: Form, domain_id: int, year: int | None) -> str:
    if form.source_kind != HEADER_TABLE_KIND:
        return messages.STEP_A4_SHOWN
    previous = _existing_data(conn, form.tables[0], domain_id, year)
    if previous is None:
        return messages.STEP_A4_FIRST_LOAD.format(form=form.label, year=year)
    return messages.STEP_A4_OVERWRITE.format(form=form.label, year=year, load_id=previous['load_id'])


def _new_metadata(request: UploadRequest) -> PendingMetadata:
    return PendingMetadata(
        domain_id=request.domain_id,
        domain=request.domain_code,
        form_id=request.form_id,
        file_type=request.form.code,
        year=request.year,
        file_name=request.file_name,
        user_id=request.user_id,
        user=request.user_name,
        created_at=dt.datetime.now(dt.UTC).isoformat(),
    )


def _reject_checked_upload(
    container: Container, request: UploadRequest, pending: PendingUpload, file_check: dict
) -> int:
    storage_path = _archive(container.settings.upload_dir, pending)
    single_table = len(request.form.tables) == 1
    load_steps = steps.check_steps(
        file_check, user=request.user_name, a4_result=None, single_table=single_table
    ) + steps.rejected_write_steps(file_check['failed_step'], steps.b4_name(file_check))
    failed = FailedLoad(
        STATUS_REJECTED,
        file_check['errors'],
        pending.metadata,
        str(storage_path),
        request.request_id,
        file_check,
        load_steps,
    )
    load_id = _record_failed_load(container, failed)
    pending_uploads.delete(pending)
    return load_id


def _archive(upload_dir: Path, pending: PendingUpload) -> Path:
    name = Path(pending.metadata.file_name).name
    target = upload_dir / f'{dt.datetime.now(dt.UTC):%Y%m%d%H%M%S}_{pending.pending_id[:8]}_{name}'
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pending.file_path, target)
    return target


def _insert_upload(conn, metadata: PendingMetadata, storage_uri: str) -> int:
    return warehouse_sql.scalar(
        conn,
        'INSERT INTO ctl.upload (domain_id, form_id, file_name, file_sha256, '
        'size_bytes, storage_uri, uploaded_by, uploaded_by_username) '
        'VALUES (%s, %s, %s, %s, %s, %s, NULL, %s) RETURNING upload_id',
        (
            metadata.domain_id,
            metadata.form_id,
            metadata.file_name,
            metadata.sha256,
            metadata.size_bytes,
            storage_uri,
            metadata.user,
        ),
    )


def _insert_failed_load(conn, upload_id: int, failed: FailedLoad) -> int:
    metadata = failed.metadata
    form_version = warehouse_sql.scalar(
        conn, 'SELECT current_version FROM ctl.form WHERE form_id = %s', (metadata.form_id,)
    )
    message = (
        messages.UPLOAD_NOTHING_UPDATED if failed.status == STATUS_REJECTED else messages.UPLOAD_ALL_CHANGES_CANCELLED
    )
    return warehouse_sql.scalar(
        conn,
        'INSERT INTO ctl.load (upload_id, domain_id, form_id, form_version, status, '
        'actor_user_id, actor_username, request_id, errors, finished_at, message, '
        'year, file_check, steps, reconciliation, sheets_count) '
        'VALUES (%s, %s, %s, %s, %s, NULL, %s, %s, %s, now(), %s, %s, %s, %s, %s, %s) '
        'RETURNING load_id',
        (
            upload_id,
            metadata.domain_id,
            metadata.form_id,
            form_version,
            failed.status,
            metadata.user,
            failed.request_id,
            _json(failed.errors),
            message,
            metadata.year,
            _json(failed.file_check),
            _json(failed.steps),
            _json(failed.reconciliation),
            (failed.file_check or {}).get('sheet_count', 0),
        ),
    )


def _record_load_event(catalog_conn, status: str, load_id: int, metadata: PendingMetadata, request_id: str) -> None:
    record_event(
        catalog_conn,
        action=f'load.{status}',
        actor_user_id=None,
        actor_username=metadata.user,
        domain_id=metadata.domain_id,
        object_type='load',
        object_id=str(load_id),
        request_id=request_id,
        detail={'user_id': metadata.user_id, 'year': metadata.year},
    )


def _write_claimed(
    container: Container, form: Form, claimed: PendingUpload, storage_path: Path, request_id: str
) -> dict:
    metadata = claimed.metadata
    try:
        with container.warehouse.transaction() as conn:
            upload_id = _insert_upload(conn, metadata, str(storage_path))
            load_request = LoadRequest(
                domain_id=metadata.domain_id,
                domain_code=metadata.domain,
                form_id=metadata.form_id,
                upload_id=upload_id,
                upload_path=storage_path,
                file_name=metadata.file_name,
                actor_username=metadata.user,
                request_id=request_id,
                year=metadata.year,
                file_check=metadata.file_check,
                a4_result=_a4_result(conn, form, metadata.domain_id, metadata.year),
            )
            load_id = orchestrator.run_load(conn, form, load_request)
    except StructureError as exc:
        failed = _write_rejection(form, metadata, storage_path, request_id, exc.errors)
        return {'load_id': _record_failed_load(container, failed), 'status': STATUS_REJECTED}
    except ReconcileError as exc:
        failed = FailedLoad(
            STATUS_MISMATCH,
            _mismatch_errors(exc.mismatches),
            metadata,
            str(storage_path),
            request_id,
            metadata.file_check,
            exc.steps,
            exc.reconciliation,
        )
        return {'load_id': _record_failed_load(container, failed), 'status': STATUS_MISMATCH}
    return {'load_id': load_id, 'status': STATUS_SUCCESS}


def _write_rejection(
    form: Form, metadata: PendingMetadata, storage_path: Path, request_id: str, errors: list[dict]
) -> FailedLoad:
    file_check = {**metadata.file_check, 'errors': errors, 'failed_step': 'A3'}
    load_steps = steps.check_steps(
        file_check, user=metadata.user, a4_result=None, single_table=len(form.tables) == 1
    ) + steps.rejected_write_steps('A3', steps.b4_name(metadata.file_check))
    return FailedLoad(STATUS_REJECTED, errors, metadata, str(storage_path), request_id, file_check, load_steps)


def _table_check_view(table: dict) -> dict:
    return {
        'table': table['table'],
        'table_name': table['table_name'],
        'sheet': table['sheet'],
        'read': table['read'],
        'missing_required': table['missing_required'],
        'duplicates': table['duplicates'],
        'empty_cells': table['empty_cells'],
        'empty_cell_details': [
            {'column': cell['column'], 'cell_count': cell['cell_count']} for cell in table['empty_cell_details']
        ],
        'to_write': table['to_write'],
        'total': _number(table['total']),
        'verdict': table['verdict'],
    }


def _header_table_groups(conn, form: Form, domain_id: int, year: int | None, file_check: dict) -> dict:
    table = form.tables[0]
    checked = file_check['tables'][0]
    grouping = checked.get('by_group') or {'column': None, 'method': '', 'order': [], 'groups': {}}
    previous = _existing_data(conn, table, domain_id, year)
    by_month = grouping['method'] == GROUP_BY_MONTH
    existing = _existing_groups(conn, table, domain_id, year, grouping) if grouping['column'] else {}
    order = sorted(grouping['order'], key=lambda key: (key == '', key)) if by_month else grouping['order']
    rows = [_group_row(key, grouping, existing.get(key), by_month) for key in order]
    title, first_column = (
        (messages.UPLOAD_BY_DELIVERY_MONTH, messages.UPLOAD_DELIVERY_MONTH)
        if by_month
        else (messages.UPLOAD_BY_SUBCONTRACTOR, messages.UPLOAD_SUBCONTRACTOR)
    )
    total = {
        'row_count': checked['read'],
        'quantity': _number(checked['total']),
        'existing': previous['row_count'] if previous else None,
    }
    return {
        'previous': previous,
        'overwrite': [form.label] if previous else [],
        'new': [] if previous else [form.label],
        'by_group': {'title': title, 'first_column': first_column, 'rows': rows, 'total': total},
    }


def _group_row(key: str, grouping: dict, existing: dict | None, by_month: bool) -> dict:
    group = grouping['groups'][key]
    row = {
        'group': key or messages.UPLOAD_EMPTY_GROUP,
        'row_count': group['row_count'],
        'quantity': _number(group['quantity']),
        'existing': existing,
        'write_mode': messages.UPLOAD_WRITE_OVERWRITE if existing else messages.UPLOAD_WRITE_APPEND,
    }
    if by_month and key:
        year, month = key.split('-')
        row['group'] = messages.UPLOAD_MONTH_OF_YEAR.format(month=int(month), year=year)
    elif by_month:
        row['group'] = messages.CHECK_NO_DELIVERY_DATE
        row['subtitle'] = messages.UPLOAD_UNDATED_NOTE.format(
            empty=grouping['empty'], unreadable=grouping['unreadable']
        )
    return row


def _existing_groups(conn, table: FormTable, domain_id: int, year: int | None, grouping: dict) -> dict[str, dict]:
    by_month = grouping['method'] == GROUP_BY_MONTH
    expression = (
        sql.SQL("coalesce(to_char(s.{}, 'YYYY-MM'), '')") if by_month else sql.SQL("coalesce(s.{}::text, '')")
    ).format(sql.Identifier(grouping['column']))
    rows = warehouse_sql.query(
        conn,
        sql.SQL(
            'SELECT {expression} AS group_key, count(*) AS row_count, max(s.load_id) AS load_id FROM {source} s '
            ' WHERE s.domain_id = %s AND s.is_current AND s.nam IS NOT DISTINCT FROM %s '
            ' GROUP BY 1'
        ).format(expression=expression, source=sql.Identifier('silver', table.name)),
        (domain_id, year),
    )
    return _with_load_summaries(conn, rows, 'group_key')


def _monthly_groups(conn, form: Form, domain_id: int, year: int | None, file_check: dict) -> dict:
    checks = {table['table']: table for table in file_check['tables']}
    tables = [table for table in form.tables_by_display_order if table.partition_by and table.name in checks]
    existing = {table.name: _existing_periods(conn, table, domain_id, year) for table in tables}
    periods = sorted(
        {period for table in tables for period in checks[table.name].get('by_period', {})},
        key=lambda period: (len(period), period),
    )
    rows, overwritten, new, total = [], [], [], 0
    for period in periods:
        period_rows = [
            _period_row(period, year, table, checks[table.name], existing[table.name].get(period))
            for table in tables
            if checks[table.name]['by_period'].get(period) is not None
        ]
        rows += period_rows
        total += sum(row['row_count'] for row in period_rows)
        month = int(period) if period.isdigit() else period
        (overwritten if any(row['existing'] for row in period_rows) else new).append(month)
    return {
        'overwrite': overwritten,
        'new': new,
        'by_group': {
            'title': messages.UPLOAD_BY_MONTH,
            'first_column': messages.UPLOAD_MONTH_COLUMN,
            'rows': rows,
            'total': {'row_count': total},
        },
    }


def _period_row(period: str, year: int | None, table: FormTable, check: dict, existing: dict | None) -> dict:
    counts = check['by_period'][period]
    label = (
        messages.UPLOAD_MONTH_OF_YEAR.format(month=period, year=year)
        if year
        else messages.UPLOAD_MONTH.format(month=period)
    )
    return {
        'group': label,
        'data': table.label,
        'row_count': counts['row_count'],
        'column_count': counts['column_count'],
        'total_column_count': check['total_column_count'],
        'existing': existing,
        'write_mode': messages.UPLOAD_WRITE_OVERWRITE if existing else messages.UPLOAD_WRITE_APPEND,
    }


def _with_load_summaries(conn, rows: list[dict], key_column: str) -> dict[str, dict]:
    summaries = _load_summaries(conn, [row['load_id'] for row in rows])
    return {row[key_column]: {'row_count': row['row_count'], **(summaries.get(row['load_id']) or {})} for row in rows}


def _load_summaries(conn, load_ids: list[int]) -> dict[int, dict]:
    if not load_ids:
        return {}
    rows = warehouse_sql.query(
        conn,
        'SELECT load_id, started_at, actor_username FROM ctl.load  WHERE load_id = ANY(%s)',
        (load_ids,),
    )
    return {row['load_id']: _load_summary(row) for row in rows}


def _load_summary(row: dict) -> dict:
    return {'load_id': row['load_id'], 'created_at': row['started_at'], 'user': row['actor_username']}


def _number(value) -> int | float | None:
    if value is None:
        return None
    number = Decimal(str(value))
    return int(number) if number == number.to_integral_value() else float(number)


def _json(value) -> str | None:
    return None if value is None else json.dumps(value, ensure_ascii=False, default=str)
