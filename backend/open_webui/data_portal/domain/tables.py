from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from psycopg import sql

from .. import messages
from ..db import sql as warehouse_sql
from ..errors import NotFound
from ..registry.loader import FormRegistry
from ..registry.schema import Form, FormColumn, FormTable

LAYERS = ('gold', 'silver', 'bronze')
CURRENT_LAYERS = ('gold', 'silver')
SEARCHABLE_TYPES = ('text', 'enum')


@dataclass
class TableStats:
    row_count: int
    periods: list
    updated_at: dt.datetime | None


@dataclass
class TableSummary:
    table: FormTable
    form: Form
    stats: TableStats
    load_id: int | None


@dataclass
class TableQuery:
    layer: str
    year: int | None
    period: str = ''
    query: str = ''
    page: int = 1
    page_size: int | None = None


@dataclass
class TableRows:
    columns: list[FormColumn]
    rows: list[list]
    total: int
    total_row: list | None


def table_domain(conn, table_name: str) -> dict | None:
    return warehouse_sql.query_one(
        conn,
        'SELECT d.domain_id, d.code, d.name, ft.form_id FROM ctl.dataset ds '
        '  JOIN ctl.form_table ft ON ft.table_id = ds.table_id '
        '  JOIN ctl.domain d ON d.domain_id = ds.domain_id '
        " WHERE ft.name = %s AND ds.is_visible AND d.status = 'active' LIMIT 1",
        (table_name,),
    )


def table_stats(conn, table: FormTable, domain_id: int, year: int | None) -> TableStats:
    year_condition, year_params = _year_condition(table, year, 'gold')
    period_column = table.partition_column
    select_periods = (
        sql.SQL(', array_agg(DISTINCT t.{}) AS periods').format(sql.Identifier(period_column.name))
        if period_column is not None
        else sql.SQL('')
    )
    source = sql.Identifier('gold', table.name)
    row = warehouse_sql.query_one(
        conn,
        sql.SQL(
            'SELECT count(*) AS row_count{periods} FROM {source} t WHERE t.domain_id = %s AND t.is_current{year}'
        ).format(periods=select_periods, source=source, year=year_condition),
        [domain_id, *year_params],
    )
    periods = sorted(period for period in (row.get('periods') or []) if period is not None) if period_column else []
    updated_at = None
    if row['row_count']:
        updated_at = warehouse_sql.scalar(
            conn,
            sql.SQL(
                'SELECT max(l.finished_at) FROM ctl.load l WHERE l.load_id IN '
                '(SELECT DISTINCT t.load_id FROM {source} t '
                '  WHERE t.domain_id = %s AND t.is_current{year})'
            ).format(source=source, year=year_condition),
            [domain_id, *year_params],
        )
    return TableStats(row['row_count'], periods, updated_at)


def latest_year(conn, table: FormTable, domain_id: int, years: Sequence[int]) -> int | None:
    column = table.year_column
    if column is None:
        return None
    year = warehouse_sql.scalar(
        conn,
        sql.SQL(
            'SELECT max(t.{column}) FROM {source} t WHERE t.domain_id = %s AND t.is_current AND t.{column} = ANY(%s)'
        ).format(column=sql.Identifier(column.name), source=sql.Identifier('gold', table.name)),
        [domain_id, list(years)],
    )
    return None if year is None else int(year)


def latest_load_id(conn, domain_id: int, form_id: int, year: int | None) -> int | None:
    condition, params = '', [domain_id, form_id]
    if year is not None:
        condition, params = ' AND year = %s', [*params, year]
    return warehouse_sql.scalar(
        conn,
        f"SELECT max(load_id) FROM ctl.load WHERE domain_id = %s AND form_id = %s AND status = 'success'{condition}",
        params,
    )


def list_tables(conn, registry: FormRegistry, domain_id: int, year: int | None) -> list[TableSummary]:
    rows = warehouse_sql.query(
        conn,
        'SELECT ft.name, ft.form_id, f.code AS form_code FROM ctl.dataset ds '
        '  JOIN ctl.form_table ft ON ft.table_id = ds.table_id '
        '  JOIN ctl.form f ON f.form_id = ft.form_id '
        '  LEFT JOIN ctl.domain_form df ON df.domain_id = ds.domain_id '
        '                              AND df.form_id = ft.form_id '
        ' WHERE ds.domain_id = %s AND ds.is_visible '
        ' ORDER BY df.position, ds.display_order, ft.name',
        (domain_id,),
    )
    summaries = []
    for row in rows:
        table = registry.table(row['name'])
        table_year = year if table.year_column is not None else None
        summaries.append(
            TableSummary(
                table=table,
                form=registry.form(row['form_code']),
                stats=table_stats(conn, table, domain_id, year),
                load_id=latest_load_id(conn, domain_id, row['form_id'], table_year),
            )
        )
    return summaries


def read_rows(conn, table: FormTable, domain_id: int, query: TableQuery) -> TableRows:
    if query.layer not in LAYERS:
        raise NotFound(messages.TABLE_UNKNOWN_LAYER.format(layer=query.layer))
    columns = [column for column in table.columns if column.show_in_table]
    where, params = _filter_clause(table, domain_id, query)
    source = sql.SQL('{} t').format(sql.Identifier(query.layer, table.name))
    total = warehouse_sql.scalar(conn, sql.SQL('SELECT count(*) FROM {} WHERE {}').format(source, where), params)

    limit = sql.SQL('')
    page_params: list = []
    if query.page_size is not None:
        limit = sql.SQL(' LIMIT %s OFFSET %s')
        page_params = [query.page_size, (query.page - 1) * query.page_size]
    rows = warehouse_sql.query(
        conn,
        sql.SQL('SELECT {columns} FROM {source} WHERE {where} ORDER BY {order}{limit}').format(
            columns=sql.SQL(', ').join(sql.SQL('t.{}').format(sql.Identifier(column.name)) for column in columns),
            source=source,
            where=where,
            order=_order_clause(table),
            limit=limit,
        ),
        [*params, *page_params],
    )
    return TableRows(
        columns=columns,
        rows=[[_to_number(row[column.name]) for column in columns] for row in rows],
        total=total,
        total_row=_total_row(conn, columns, source, where, params, query),
    )


def column_descriptions(table: FormTable, tables: list[FormTable]) -> list[dict]:
    return [
        {
            'name': column.name,
            'source_name': column.label,
            'type': column.type,
            'type_label': column.type_label,
            'required': column.is_business_key or column.required,
            'meaning': column.meaning,
            'purpose': column_purpose(table, column, tables),
            'example': column.example,
            'is_measure': column.is_measure,
        }
        for column in table.columns
        if column.show_in_table
    ]


def column_purpose(table: FormTable, column: FormColumn, tables: list[FormTable]) -> str:
    parts: list[str] = []
    if column.is_business_key:
        others = [key for key in table.business_key if key != column.name]
        parts.append(
            messages.TABLE_PURPOSE_KEY_WITH.format(columns=', '.join(others)) if others else messages.TABLE_PURPOSE_KEY
        )
    if column.name in table.partition_by:
        parts.append(messages.TABLE_PURPOSE_PERIOD)
    if table.kind == 'fact':
        dimensions = [other for other in tables if other.is_dim and other.business_key == [column.name]]
        if dimensions:
            parts.append(messages.TABLE_PURPOSE_JOIN.format(table=dimensions[0].name, label=dimensions[0].label))
    if column.type == 'ratio':
        parts.append(messages.TABLE_PURPOSE_RATIO)
    elif column.is_measure:
        parts.append(messages.TABLE_PURPOSE_MEASURE)
    elif not parts:
        parts.append(messages.TABLE_PURPOSE_ATTRIBUTE)
    return ' '.join(parts)


def _year_condition(table: FormTable, year: int | None, layer: str) -> tuple[sql.Composable, list]:
    column = table.year_column
    if column is None or year is None:
        return sql.SQL(''), []
    if layer == 'bronze':
        return sql.SQL(' AND t.{}::text = %s').format(sql.Identifier(column.name)), [str(year)]
    return sql.SQL(' AND t.{} = %s').format(sql.Identifier(column.name)), [year]


def _to_number(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


def _order_clause(table: FormTable) -> sql.Composable:
    return sql.SQL(', ').join(
        sql.SQL('t.{}').format(sql.Identifier(name)) for name in (table.order or table.business_key)
    ) or sql.SQL('1')


def _total_row(
    conn, columns: list[FormColumn], source: sql.Composable, where: sql.Composable, params: list, query: TableQuery
) -> list | None:
    measures = [column for column in columns if column.is_measure]
    if not (query.period or query.query) or not measures or query.layer == 'bronze':
        return None
    totals = (
        warehouse_sql.query_one(
            conn,
            sql.SQL('SELECT {} FROM {} WHERE {}').format(
                sql.SQL(', ').join(
                    sql.SQL('coalesce(sum(t.{name}), 0) AS {name}').format(name=sql.Identifier(column.name))
                    for column in measures
                ),
                source,
                where,
            ),
            params,
        )
        or {}
    )
    return [_to_number(totals.get(column.name)) if column.is_measure else None for column in columns]


def _filter_clause(table: FormTable, domain_id: int, query: TableQuery) -> tuple[sql.Composed, list]:
    conditions = [sql.SQL('t.domain_id = %s')]
    params: list = [domain_id]
    if query.layer in CURRENT_LAYERS:
        conditions.append(sql.SQL('t.is_current'))
    year_condition, year_params = _year_condition(table, query.year, query.layer)
    if year_params:
        conditions.append(sql.SQL('TRUE{}').format(year_condition))
        params += year_params
    if query.period and table.partition_by:
        condition, value = _period_condition(table, query.period, query.layer)
        conditions.append(condition)
        params.append(value)
    if query.query:
        search, search_params = _search_conditions(table, query.query, query.layer)
        if search:
            conditions.append(sql.SQL('({})').format(sql.SQL(' OR ').join(search)))
            params += search_params
    return sql.SQL(' AND ').join(conditions), params


def _period_condition(table: FormTable, period: str, layer: str) -> tuple[sql.Composable, object]:
    column = table.partition_column
    parsed = column.handler.parse(period)
    if parsed.ok and parsed.value is not None and layer != 'bronze':
        return sql.SQL('t.{} = %s').format(sql.Identifier(column.name)), parsed.value
    return sql.SQL('t.{}::text = %s').format(sql.Identifier(column.name)), period


def _search_conditions(table: FormTable, text: str, layer: str) -> tuple[list[sql.Composable], list[str]]:
    conditions: list[sql.Composable] = []
    pattern = f'%{text}%'
    for column in table.columns:
        if column.type in SEARCHABLE_TYPES or (layer == 'bronze' and column.type == 'date'):
            conditions.append(sql.SQL('t.{}::text ILIKE %s').format(sql.Identifier(column.name)))
        elif column.type == 'date':
            conditions.append(sql.SQL("to_char(t.{}, 'DD/MM/YYYY') ILIKE %s").format(sql.Identifier(column.name)))
    return conditions, [pattern] * len(conditions)
