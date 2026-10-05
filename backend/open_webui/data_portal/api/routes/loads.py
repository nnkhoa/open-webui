from __future__ import annotations

import csv
import io
from pathlib import Path

from fastapi import APIRouter, Depends, Response
from fastapi.responses import FileResponse

from ... import messages
from ...domain import loads
from ...domain.loads import STATUS_SUCCESS, LoadFilter
from ...errors import Conflict, InvalidInput, NotFound
from ...pipeline import rollback
from ...pipeline.card_model import rejected_card
from ...pipeline.reconcile_cards import CardSelection, render_cards
from ...security.audit import record_event
from ...security.rbac import Domain
from ...sources import source_file
from ..deps import RequestContext, get_admin_context, get_context, parse_pagination, parse_year
from ..serialization import serialize
from .domains import file_type_json

router = APIRouter()

XLSX_MEDIA_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
CSV_MEDIA_TYPE = 'text/csv; charset=utf-8'
UTF8_BOM = '\ufeff'
LOADS_PAGE_SIZE = 25
SHEET_PAGE_SIZE = 50
STATUS_REJECTED = 'rejected'
STATUS_MISMATCH = 'mismatch'


############################
# GetLoads
############################


@router.get('/loads')
def get_loads(
    domain: str = '',
    year: str = '',
    file_type: str = '',
    status: str = '',
    user: str = '',
    query: str = '',
    page: int = 1,
    page_size: int | None = None,
    ctx: RequestContext = Depends(get_context),
) -> dict:
    selected_domain = ctx.domain(domain)
    page, page_size = parse_pagination(page, page_size, LOADS_PAGE_SIZE)
    form_id = _form_id(ctx, selected_domain, file_type)
    if status and status not in loads.STATUSES:
        raise InvalidInput(messages.LOAD_INVALID_STATUS)
    conn = ctx.warehouse()
    load_filter = LoadFilter(
        year=parse_year(year),
        form_id=form_id,
        status=status,
        user=user,
        query=query.strip(),
        page=page,
        page_size=page_size,
    )
    rows, total = loads.list_loads(conn, selected_domain.domain_id, load_filter)
    return serialize(
        {
            'total': total,
            'uploaders': loads.list_uploaders(conn, selected_domain.domain_id),
            'items': [_load_item(row) for row in rows],
        }
    )


############################
# GetLoad
############################


@router.get('/loads/{load_id}')
def get_load(load_id: int, ctx: RequestContext = Depends(get_context)) -> dict:
    load = _get_load(ctx, load_id)
    file_check = load['file_check'] or {}
    succeeded = load['status'] == STATUS_SUCCESS
    return serialize(
        {
            'id': load['load_id'],
            'status': load['status'],
            'domain': load['domain_code'],
            'year': load['year'],
            'file_type': file_type_json(ctx.registry.form(load['form_code'])),
            'file_name': load['file_name'],
            'size_bytes': load['size_bytes'],
            'user': load['user_name'],
            'created_at': load['started_at'],
            'months': loads.month_range(load),
            'sheet': file_check.get('data_sheet') if load['status'] != STATUS_REJECTED else None,
            'total_rows': load['rows_read'] if succeeded else 0,
            'rows_written': loads.rows_written(load),
            'sheet_count': file_check.get('sheet_count') or load['sheets_count'],
            'steps': load['steps'] or [],
            'errors': loads.error_rows(load),
            'can_rollback': succeeded and rollback.can_rollback(ctx.warehouse(), load_id)[0],
            'is_active': succeeded,
            'primary_table': loads.primary_table(ctx.registry, load['form_code']),
        }
    )


############################
# GetLoadReconciliation
############################


@router.get('/loads/{load_id}/reconcile')
def get_load_reconciliation(
    load_id: int,
    card: str = '',
    table: str = '',
    column: str = '',
    group_by: str = '',
    page: int = 1,
    page_size: int | None = None,
    ctx: RequestContext = Depends(get_context),
) -> dict:
    load = _get_load(ctx, load_id)
    page, page_size = parse_pagination(page, page_size, LOADS_PAGE_SIZE)
    if load['status'] == STATUS_REJECTED:
        return {'cards': [rejected_card()]}
    selection = CardSelection(
        card=card,
        table=table or None,
        column=column or None,
        group_by=group_by or None,
        page=page,
        page_size=page_size,
    )
    cards = render_cards(load['reconciliation'] or {}, selection, cancelled=load['status'] == STATUS_MISMATCH)
    if card and not cards:
        raise NotFound(messages.LOAD_CARD_NOT_FOUND)
    return serialize({'cards': cards})


############################
# GetLoadErrorsCsv
############################


@router.get('/loads/{load_id}/errors.csv')
def get_load_errors_csv(load_id: int, ctx: RequestContext = Depends(get_context)) -> Response:
    load = _get_load(ctx, load_id)
    buffer = io.StringIO()
    buffer.write(UTF8_BOM)
    writer = csv.writer(buffer)
    writer.writerow(messages.EXPORT_ERRORS_CSV_HEADER)
    for error in loads.error_rows(load):
        writer.writerow([error[key] or '' for key in ('sheet', 'location', 'issue', 'resolution')])
    file_name = messages.EXPORT_ERRORS_CSV_NAME.format(load_id=load_id)
    return Response(
        buffer.getvalue(),
        media_type=CSV_MEDIA_TYPE,
        headers={'Content-Disposition': f'attachment; filename="{file_name}"'},
    )


############################
# GetLoadFile
############################


@router.get('/loads/{load_id}/file')
def get_load_file(load_id: int, ctx: RequestContext = Depends(get_context)) -> FileResponse:
    load, path = _load_file(ctx, load_id)
    return FileResponse(path, media_type=XLSX_MEDIA_TYPE, filename=load['file_name'])


############################
# GetLoadFileSheets
############################


@router.get('/loads/{load_id}/file/sheets')
def get_load_file_sheets(load_id: int, ctx: RequestContext = Depends(get_context)) -> list[dict]:
    _, path = _load_file(ctx, load_id)
    return source_file.list_sheets(path)


############################
# GetLoadFileSheet
############################


@router.get('/loads/{load_id}/file/sheets/{index}')
def get_load_file_sheet(
    load_id: int,
    index: int,
    page: int = 1,
    page_size: int | None = None,
    ctx: RequestContext = Depends(get_context),
) -> dict:
    _, path = _load_file(ctx, load_id)
    page, page_size = parse_pagination(page, page_size, SHEET_PAGE_SIZE)
    sheet = source_file.sheet_page(path, index, page, page_size)
    if sheet is None:
        raise NotFound(messages.LOAD_SHEET_NOT_FOUND)
    return sheet


############################
# DeleteLoad
############################


@router.delete('/loads/{load_id}', status_code=204)
def delete_load(load_id: int, ctx: RequestContext = Depends(get_admin_context)) -> Response:
    container = ctx.container
    ctx.require_warehouse()
    with container.warehouse_transaction() as conn:
        load = loads.get_load(conn, load_id)
        if load is None:
            raise NotFound(messages.LOAD_NOT_FOUND)
        if load['status'] == STATUS_SUCCESS:
            allowed, reason = rollback.can_rollback(conn, load_id)
            if not allowed:
                raise Conflict(reason)
            file_path = rollback.rollback_load(conn, container.registry, load_id).file_path
            action = 'load.rollback'
        else:
            file_path = rollback.delete_history(conn, load_id)
            action = 'load.delete_history'
    if file_path:
        Path(file_path).unlink(missing_ok=True)
    with container.catalog.transaction() as catalog_conn:
        record_event(
            catalog_conn,
            action=action,
            actor_user_id=None,
            actor_username=ctx.user.user_name,
            domain_id=load['domain_id'],
            object_type='load',
            object_id=str(load_id),
            request_id=ctx.request_id,
            detail={'user_id': ctx.user.user_id, 'file_name': load['file_name']},
        )
    return Response(status_code=204)


def _get_load(ctx: RequestContext, load_id: int) -> dict:
    load = loads.get_load(ctx.warehouse(), load_id)
    if load is None:
        raise NotFound(messages.LOAD_NOT_FOUND)
    return load


def _form_id(ctx: RequestContext, domain: Domain, file_type: str) -> int | None:
    if not file_type:
        return None
    form_id = next((form_id for form_id, form in ctx.forms(domain) if form.code == file_type), None)
    if form_id is None:
        raise InvalidInput(messages.API_INVALID_FILE_TYPE)
    return form_id


def _load_item(row: dict) -> dict:
    return {
        'id': row['load_id'],
        'file_name': row['file_name'],
        'year': row['year'],
        'file_type': {'code': row['form_code'], 'name': row['form_label']},
        'user': row['user_name'],
        'created_at': row['started_at'],
        'row_count': row['rows_read'] if row['status'] == STATUS_SUCCESS else 0,
        'status': row['status'],
    }


def _load_file(ctx: RequestContext, load_id: int) -> tuple[dict, Path]:
    load = _get_load(ctx, load_id)
    path = Path(load['storage_uri'] or '')
    if not path.is_file():
        raise NotFound(messages.LOAD_FILE_MISSING)
    return load, path
