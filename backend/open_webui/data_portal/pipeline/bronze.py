from __future__ import annotations

import datetime as dt

from psycopg import sql

from ..db import sql as warehouse_sql
from ..registry.schema import FormTable
from ..sources.base import SourceRow
from .context import BronzeRow, LoadContext
from .dedup import hash_row


def fill_derived_columns(
    table: FormTable, row: SourceRow, year: int | None, month: int | None, reader=None
) -> SourceRow:
    derived: dict[str, str | None] = {}
    for column in table.columns:
        if column.is_year:
            derived[column.name] = None if year is None else str(year)
        elif column.is_month:
            derived[column.name] = None if month is None else str(month)
        elif column.from_header and reader is not None and hasattr(reader, 'header_value'):
            derived[column.name] = reader.header_value(column.file_header)
    return SourceRow(row.number, {**row.values, **derived}) if derived else row


def write(ctx: LoadContext, table: FormTable) -> list[BronzeRow]:
    columns = table.column_names
    rows = [
        fill_derived_columns(table, row, ctx.year, ctx.month, ctx.reader)
        for row in ctx.reader.rows(table.sheet, table.header_map)
    ]
    result = ctx.table_result(table)
    result.rows_file = len(rows)

    if not rows:
        result.rows_bronze = 0
        return []

    loaded_at = dt.datetime.now(dt.UTC)
    statement = sql.SQL(
        'INSERT INTO {} ({}, domain_id, load_id, batch_id, source_sheet, source_row, '
        'loaded_at, row_hash) VALUES ({}, %s, %s, %s, %s, %s, %s, %s) RETURNING row_id'
    ).format(
        sql.Identifier('bronze', table.name),
        warehouse_sql.column_list(columns),
        warehouse_sql.placeholders(len(columns)),
    )

    written: list[BronzeRow] = []
    with ctx.conn.cursor() as cur:
        for row in rows:
            row_hash = hash_row(table.sheet, row.values, columns)
            params = [row.values.get(column) for column in columns]
            params += [ctx.domain_id, ctx.load_id, ctx.batch_id, table.sheet, row.number, loaded_at, row_hash]
            cur.execute(statement, params)
            bronze_id = cur.fetchone()[0]
            written.append(BronzeRow(bronze_id, row.number, row_hash, row.values))

    result.rows_bronze = len(written)
    return written
