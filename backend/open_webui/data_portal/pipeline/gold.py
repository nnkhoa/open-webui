"""Dựng lớp phân tích (gold): chép các dòng lô vừa ghi ở lớp chuẩn hoá.

Không nối khoá, không thêm dòng, không tính thêm chỉ số — cùng cột, cùng giá trị
với lớp chuẩn hoá. Dòng hết hiệu lực ở lớp chuẩn hoá thì cũng hết ở đây.
"""

from __future__ import annotations

from psycopg import sql

from ..db import sql as q
from ..registry.schema import FormTable
from .context import LoadContext


def dung(ctx: LoadContext, table: FormTable) -> int:
    gold = sql.Identifier("gold", table.name)
    silver = sql.Identifier("silver", table.name)
    sk = sql.Identifier(table.sk_column)
    cot = table.column_names

    so = q.execute(
        ctx.conn,
        sql.SQL(
            "INSERT INTO {gold} ({cot}, domain_id, silver_sk, load_id, batch_id, "
            "                    source_sheet, source_row) "
            "SELECT {chon}, s.domain_id, s.{sk}, s.load_id, s.batch_id, "
            "       s.source_sheet, s.source_row "
            "  FROM {silver} s "
            " WHERE s.batch_id = %s AND s.is_current"
        ).format(
            gold=gold, silver=silver, sk=sk, cot=q.column_list(cot),
            chon=sql.SQL(", ").join(sql.SQL("s.{}").format(sql.Identifier(c)) for c in cot),
        ),
        (ctx.batch_id,),
    )
    q.execute(
        ctx.conn,
        sql.SQL(
            "UPDATE {gold} g SET is_current = false "
            "  FROM {silver} s "
            " WHERE g.silver_sk = s.{sk} AND g.is_current AND NOT s.is_current"
        ).format(gold=gold, silver=silver, sk=sk),
    )
    ctx.bang(table).rows_gold = q.scalar(
        ctx.conn,
        sql.SQL("SELECT count(*) FROM {} WHERE batch_id = %s AND is_current").format(gold),
        (ctx.batch_id,),
    )
    return so
