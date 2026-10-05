from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from ... import messages
from ...domain import excel_export, tables
from ...domain.excel_export import ExportInfo
from ...domain.tables import TableQuery, TableSummary
from ...errors import InvalidInput, NotFound
from ...pipeline.upload import YEARS
from ...registry.schema import Form, FormTable
from ..deps import RequestContext, get_context, parse_pagination, parse_year
from ..serialization import serialize
from .domains import file_type_json

router = APIRouter()

XLSX_MEDIA_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
DEFAULT_LAYER = 'gold'
TABLE_PAGE_SIZE = 50


############################
# GetTables
############################


@router.get('/tables')
def get_tables(domain: str = '', year: str = '', ctx: RequestContext = Depends(get_context)) -> list[dict]:
    selected_domain = ctx.domain(domain)
    selected_year = parse_year(year)
    summaries = tables.list_tables(ctx.warehouse(), ctx.registry, selected_domain.domain_id, selected_year)
    return serialize([_table_item(summary, selected_year) for summary in summaries])


############################
# GetTable
############################


@router.get('/tables/{table}')
def get_table(
    table: str,
    layer: str = '',
    year: str = '',
    period: str = '',
    query: str = '',
    page: int = 1,
    page_size: int | None = None,
    ctx: RequestContext = Depends(get_context),
) -> dict:
    domain, form_table, form = _visible_table(ctx, table)
    layer, selected_year = _parse_filters(layer, year, form_table)
    page, page_size = parse_pagination(page, page_size, TABLE_PAGE_SIZE)
    conn = ctx.warehouse()
    stats = tables.table_stats(conn, form_table, domain['domain_id'], selected_year)
    table_query = TableQuery(layer, selected_year, period.strip(), query.strip(), page, page_size)
    data = tables.read_rows(conn, form_table, domain['domain_id'], table_query)
    return serialize(
        {
            'table': form_table.name,
            'name': form_table.label,
            'description': form_table.description,
            'grain': form_table.grain,
            'domain': domain['code'],
            'kind': form_table.kind,
            'file_type': file_type_json(form),
            'layer': layer,
            'year': selected_year,
            'latest_month': _latest_month(conn, form_table, domain, selected_year, stats.periods),
            'updated_at': stats.updated_at,
            'has_period': bool(form_table.partition_by),
            'periods': [str(period) for period in stats.periods],
            'columns': tables.column_descriptions(form_table, form.tables),
            'total': data.total,
            'rows': data.rows,
            'total_row': data.total_row,
        }
    )


############################
# ExportTable
############################


@router.get('/tables/{table}/export.xlsx')
def export_table(
    table: str,
    layer: str = '',
    year: str = '',
    period: str = '',
    query: str = '',
    ctx: RequestContext = Depends(get_context),
) -> Response:
    domain, form_table, form = _visible_table(ctx, table)
    layer, selected_year = _parse_filters(layer, year, form_table)
    period, query = period.strip(), query.strip()
    table_query = TableQuery(layer, selected_year, period, query)
    data = tables.read_rows(ctx.warehouse(), form_table, domain['domain_id'], table_query)
    info = ExportInfo(
        domain=f'{domain["code"]} — {domain["name"]}',
        layer=layer,
        filters=excel_export.describe_filters(selected_year, period, query),
    )
    content = excel_export.build_workbook(form_table, data, info, tables.column_descriptions(form_table, form.tables))
    file_name = excel_export.file_name(domain['code'], form_table, layer, selected_year)
    return Response(
        content,
        media_type=XLSX_MEDIA_TYPE,
        headers={'Content-Disposition': f'attachment; filename="{file_name}"', 'X-Row-Count': str(data.total)},
    )


def _table_item(summary: TableSummary, year: int | None) -> dict:
    table = summary.table
    is_fact = not table.is_dim
    return {
        'table': table.name,
        'name': table.label,
        'description': table.description,
        'kind': table.kind,
        'year': year if is_fact else None,
        'months': _month_range(summary.stats.periods) if is_fact else None,
        'file_type': file_type_json(summary.form),
        'load_id': summary.load_id,
        'row_count': summary.stats.row_count,
        'updated_at': summary.stats.updated_at,
    }


def _month_range(periods: list) -> str | None:
    if not periods:
        return None
    return str(periods[0]) if len(periods) == 1 else f'{periods[0]} → {periods[-1]}'


def _visible_table(ctx: RequestContext, name: str) -> tuple[dict, FormTable, Form]:
    domain = tables.table_domain(ctx.warehouse(), name)
    if domain is None:
        raise NotFound(messages.TABLE_NOT_FOUND)
    table = ctx.registry.table(name)
    form = next(form for form in ctx.registry.forms if table in form.tables)
    return domain, table, form


def _parse_filters(layer: str, year: str, table: FormTable) -> tuple[str, int | None]:
    layer = layer or DEFAULT_LAYER
    if layer not in tables.LAYERS:
        raise InvalidInput(messages.TABLE_INVALID_LAYER)
    return layer, (parse_year(year) if table.year_column is not None else None)


def _latest_month(conn, table: FormTable, domain: dict, year: int | None, periods: list) -> str | None:
    if not periods or table.year_column is None:
        return None
    last_year = year if year is not None else _latest_year(conn, table, domain)
    return f'{periods[-1]}/{last_year}' if last_year else None


def _latest_year(conn, table: FormTable, domain: dict) -> int | None:
    for year in reversed(YEARS):
        if tables.table_stats(conn, table, domain['domain_id'], year).row_count:
            return year
    return None
