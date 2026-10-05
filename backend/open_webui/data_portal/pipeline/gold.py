from __future__ import annotations

from psycopg import sql

from ..db import sql as warehouse_sql
from ..registry.schema import FormTable
from .context import LoadContext


def build(ctx: LoadContext, table: FormTable) -> int:
    gold = sql.Identifier('gold', table.name)
    silver = sql.Identifier('silver', table.name)
    surrogate_key = sql.Identifier(table.sk_column)
    columns = table.column_names

    inserted = warehouse_sql.execute(
        ctx.conn,
        sql.SQL(
            'INSERT INTO {gold} ({columns}, domain_id, silver_sk, load_id, batch_id, '
            '                    source_sheet, source_row) '
            'SELECT {selected}, s.domain_id, s.{sk}, s.load_id, s.batch_id, '
            '       s.source_sheet, s.source_row '
            '  FROM {silver} s '
            ' WHERE s.batch_id = %s AND s.is_current'
        ).format(
            gold=gold,
            silver=silver,
            sk=surrogate_key,
            columns=warehouse_sql.column_list(columns),
            selected=sql.SQL(', ').join(sql.SQL('s.{}').format(sql.Identifier(c)) for c in columns),
        ),
        (ctx.batch_id,),
    )
    warehouse_sql.execute(
        ctx.conn,
        sql.SQL(
            'UPDATE {gold} g SET is_current = false '
            '  FROM {silver} s '
            ' WHERE g.silver_sk = s.{sk} AND g.is_current AND NOT s.is_current'
        ).format(gold=gold, silver=silver, sk=surrogate_key),
    )
    ctx.table_result(table).rows_gold = warehouse_sql.scalar(
        ctx.conn,
        sql.SQL('SELECT count(*) FROM {} WHERE batch_id = %s AND is_current').format(gold),
        (ctx.batch_id,),
    )
    return inserted
