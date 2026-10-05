from __future__ import annotations

import datetime as dt
import json

from psycopg import sql

from ..db import sql as warehouse_sql
from ..registry.schema import FormTable
from .context import CleanRow, LoadContext

NO_PERIOD = '—'


def staging_table_name(table: FormTable) -> str:
    return f'stg_{table.name}'


def merge(ctx: LoadContext, table: FormTable, rows: list[CleanRow]) -> None:
    result = ctx.table_result(table)
    _create_staging_table(ctx, table, rows)
    now = dt.datetime.now(dt.UTC)

    if table.merge == 'append' or not table.business_key:
        result.rows_silver = _insert_rows(ctx, table, now, skip_unchanged=False)
        return

    if table.merge == 'replace_all':
        result.rows_superseded = _supersede_all(ctx, table, now)
        result.rows_silver = _insert_rows(ctx, table, now, skip_unchanged=False)
        result.rows_unchanged = 0
        return

    superseded = _supersede_changed(ctx, table, now)
    periods = _typed_periods(ctx, table)
    if table.merge == 'replace_partition' and periods and table.partition_by:
        superseded += _supersede_missing(ctx, table, now, periods)
    inserted = _insert_rows(ctx, table, now, skip_unchanged=True)

    result.rows_silver = inserted
    result.rows_superseded = superseded
    result.rows_unchanged = len(rows) - inserted


def write_partitions(ctx: LoadContext, table: FormTable, table_id: int) -> None:
    labels = sorted(ctx.touched_periods.get(table.name, set()))
    values = _typed_periods(ctx, table)
    periods = list(zip(labels, values, strict=True)) or [(NO_PERIOD, None)]
    result = ctx.table_result(table)
    measure_columns = [column.name for column in table.measures]
    single = len(periods) == 1

    for label, value in periods:
        totals = _period_totals(ctx, table, value, measure_columns) if measure_columns else {}
        warehouse_sql.execute(
            ctx.conn,
            """
            INSERT INTO ctl.batch_partition (batch_id, table_id, partition_key,
                                             rows_written, rows_superseded, sum_control)
                 VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (batch_id, table_id, partition_key) DO UPDATE
                    SET rows_written = EXCLUDED.rows_written,
                        rows_superseded = EXCLUDED.rows_superseded,
                        sum_control = EXCLUDED.sum_control
            """,
            (
                ctx.batch_id,
                table_id,
                label,
                result.rows_silver if single else 0,
                result.rows_superseded if single else 0,
                json.dumps(totals, ensure_ascii=False, default=str),
            ),
        )


def _typed_periods(ctx: LoadContext, table: FormTable) -> list:
    if not table.partition_by:
        return []
    column = table.partition_column
    periods = []
    for period in sorted(ctx.touched_periods.get(table.name, set())):
        parsed = column.handler.parse(period)
        periods.append(parsed.value if parsed.ok else period)
    return periods


def _year_condition(table: FormTable, year: int | None, alias: str) -> tuple[sql.Composable, list]:
    column = table.year_column
    if column is None:
        return sql.SQL(''), []
    condition = sql.SQL(' AND {}.{} IS NOT DISTINCT FROM %s').format(sql.Identifier(alias), sql.Identifier(column.name))
    return condition, [year]


def _staging(table: FormTable) -> sql.Identifier:
    return sql.Identifier(staging_table_name(table))


def _target(table: FormTable) -> sql.Identifier:
    return sql.Identifier('silver', table.name)


def _business_key_match(table: FormTable, left: str, right: str) -> sql.Composed:
    return sql.SQL(' AND ').join(
        sql.SQL('{}.{} IS NOT DISTINCT FROM {}.{}').format(
            sql.Identifier(left),
            sql.Identifier(column),
            sql.Identifier(right),
            sql.Identifier(column),
        )
        for column in table.business_key
    )


def _create_staging_table(ctx: LoadContext, table: FormTable, rows: list[CleanRow]) -> None:
    columns = table.column_names
    definition = sql.SQL(', ').join(
        [sql.SQL('{} {}').format(sql.Identifier(c.name), sql.SQL(c.silver_sql_type)) for c in table.columns]
        + [sql.SQL('row_hash char(64)'), sql.SQL('bronze_id bigint'), sql.SQL('source_row int')]
    )
    name = _staging(table)
    warehouse_sql.execute(ctx.conn, sql.SQL('DROP TABLE IF EXISTS {}').format(name))
    warehouse_sql.execute(ctx.conn, sql.SQL('CREATE TEMP TABLE {} ({}) ON COMMIT DROP').format(name, definition))
    if not rows:
        return
    warehouse_sql.execute_many(
        ctx.conn,
        sql.SQL('INSERT INTO {} ({}, row_hash, bronze_id, source_row) VALUES ({})').format(
            name, warehouse_sql.column_list(columns), warehouse_sql.placeholders(len(columns) + 3)
        ),
        [[row.values.get(c) for c in columns] + [row.row_hash, row.bronze_id, row.source_row] for row in rows],
    )


def _supersede_all(ctx: LoadContext, table: FormTable, now: dt.datetime) -> int:
    year, year_params = _year_condition(table, ctx.year, 's')
    return warehouse_sql.execute(
        ctx.conn,
        sql.SQL(
            'UPDATE {target} s SET is_current = false, valid_to = %s, '
            'superseded_by_batch_id = %s '
            ' WHERE s.domain_id = %s AND s.is_current{year}'
        ).format(target=_target(table), year=year),
        (now, ctx.batch_id, ctx.domain_id, *year_params),
    )


def _supersede_changed(ctx: LoadContext, table: FormTable, now: dt.datetime) -> int:
    return warehouse_sql.execute(
        ctx.conn,
        sql.SQL(
            'UPDATE {target} s SET is_current = false, valid_to = %s, '
            'superseded_by_batch_id = %s '
            ' WHERE s.domain_id = %s AND s.is_current '
            '   AND EXISTS (SELECT 1 FROM {staging} g '
            '                WHERE {match} AND g.row_hash <> s.row_hash)'
        ).format(target=_target(table), staging=_staging(table), match=_business_key_match(table, 'g', 's')),
        (now, ctx.batch_id, ctx.domain_id),
    )


def _supersede_missing(ctx: LoadContext, table: FormTable, now: dt.datetime, periods: list) -> int:
    year, year_params = _year_condition(table, ctx.year, 's')
    return warehouse_sql.execute(
        ctx.conn,
        sql.SQL(
            'UPDATE {target} s SET is_current = false, valid_to = %s, '
            'superseded_by_batch_id = %s '
            ' WHERE s.domain_id = %s AND s.is_current '
            '   AND s.{period_column} = ANY(%s){year} '
            '   AND NOT EXISTS (SELECT 1 FROM {staging} g WHERE {match})'
        ).format(
            target=_target(table),
            staging=_staging(table),
            period_column=sql.Identifier(table.partition_column.name),
            year=year,
            match=_business_key_match(table, 'g', 's'),
        ),
        (now, ctx.batch_id, ctx.domain_id, periods, *year_params),
    )


def _insert_rows(ctx: LoadContext, table: FormTable, now: dt.datetime, skip_unchanged: bool) -> int:
    columns = table.column_names
    selected = sql.SQL(', ').join(sql.SQL('g.{}').format(sql.Identifier(c)) for c in columns)
    condition = sql.SQL('')
    if skip_unchanged:
        condition = sql.SQL(
            ' WHERE NOT EXISTS (SELECT 1 FROM {target} c '
            '                    WHERE c.domain_id = %s AND c.is_current '
            '                      AND {match} AND c.row_hash = g.row_hash)'
        ).format(target=_target(table), match=_business_key_match(table, 'g', 'c'))

    statement = sql.SQL(
        'INSERT INTO {target} ({columns}, domain_id, load_id, batch_id, bronze_id, '
        'source_sheet, source_row, row_hash, valid_from, is_current) '
        'SELECT {selected}, %s, %s, %s, g.bronze_id, %s, g.source_row, g.row_hash, %s, true '
        '  FROM {staging} g{condition}'
    ).format(
        target=_target(table),
        columns=warehouse_sql.column_list(columns),
        selected=selected,
        staging=_staging(table),
        condition=condition,
    )

    params = [ctx.domain_id, ctx.load_id, ctx.batch_id, table.sheet, now]
    if skip_unchanged:
        params.append(ctx.domain_id)
    return warehouse_sql.execute(ctx.conn, statement, params)


def _period_totals(ctx: LoadContext, table: FormTable, period, measure_columns: list[str]) -> dict:
    year, year_params = _year_condition(table, ctx.year, 's')
    if not table.partition_by or period is None:
        condition = sql.SQL('s.domain_id = %s AND s.is_current{}').format(year)
        params = [ctx.domain_id, *year_params]
    else:
        condition = sql.SQL('s.domain_id = %s AND s.is_current AND s.{} = %s{}').format(
            sql.Identifier(table.partition_column.name), year
        )
        params = [ctx.domain_id, period, *year_params]
    selected = sql.SQL(', ').join(
        sql.SQL('coalesce(sum(s.{}), 0) AS {}').format(sql.Identifier(c), sql.Identifier(c)) for c in measure_columns
    )
    row = warehouse_sql.query_one(
        ctx.conn,
        sql.SQL('SELECT {selected} FROM {source} s WHERE {condition}').format(
            selected=selected, source=sql.Identifier('silver', table.name), condition=condition
        ),
        params,
    )
    return {key: str(value) for key, value in (row or {}).items()}
