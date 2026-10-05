from __future__ import annotations

from dataclasses import dataclass

from psycopg import sql

from .. import messages
from ..db import sql as warehouse_sql
from ..db.lock import acquire_write_locks
from ..errors import InvalidInput
from ..registry.loader import FormRegistry
from ..registry.schema import FormTable

DELETABLE_STATUSES = ('rejected', 'mismatch', 'rolled_back')


@dataclass
class RollbackResult:
    rows_removed: int
    rows_restored: int
    file_path: str | None


def can_rollback(conn, load_id: int) -> tuple[bool, str]:
    load = warehouse_sql.query_one(
        conn,
        'SELECT load_id, status, batch_id, domain_id, form_id FROM ctl.load WHERE load_id = %s',
        (load_id,),
    )
    if load is None:
        return False, messages.LOAD_NOT_FOUND
    if load['status'] != 'success':
        return False, messages.LOAD_ROLLBACK_SUCCESS_ONLY

    later_loads = warehouse_sql.scalar(
        conn,
        """
        SELECT count(*) FROM ctl.batch b
         WHERE b.domain_id = %s AND b.form_id = %s AND b.state = 'current'
           AND b.batch_id > %s
        """,
        (load['domain_id'], load['form_id'], load['batch_id']),
    )
    if later_loads:
        return False, messages.LOAD_ROLLBACK_LATER_LOADS.format(count=later_loads)
    return True, ''


def rollback_load(conn, registry: FormRegistry, load_id: int) -> RollbackResult:
    allowed, reason = can_rollback(conn, load_id)
    if not allowed:
        raise InvalidInput(reason)

    load = warehouse_sql.query_one(
        conn, 'SELECT load_id, batch_id, domain_id, form_id FROM ctl.load WHERE load_id = %s', (load_id,)
    )
    acquire_write_locks(conn, [(load['domain_id'], load['form_id'])])
    form = registry.form(warehouse_sql.scalar(conn, 'SELECT code FROM ctl.form WHERE form_id = %s', (load['form_id'],)))
    rows_removed = 0
    rows_restored = 0
    for table in reversed(form.tables_by_dependency):
        removed, restored = _rollback_table(conn, table, load['batch_id'])
        rows_removed += removed
        rows_restored += restored

    return RollbackResult(rows_removed, rows_restored, _delete_load_records(conn, load_id))


def delete_history(conn, load_id: int) -> str | None:
    load = warehouse_sql.query_one(conn, 'SELECT status FROM ctl.load WHERE load_id = %s', (load_id,))
    if load is None:
        raise InvalidInput(messages.LOAD_NOT_FOUND)
    if load['status'] not in DELETABLE_STATUSES:
        raise InvalidInput(messages.LOAD_DELETE_HISTORY_NO_DATA_ONLY)
    return _delete_load_records(conn, load_id)


def _rollback_table(conn, table: FormTable, batch_id: int) -> tuple[int, int]:
    bronze = sql.Identifier('bronze', table.name)
    silver = sql.Identifier('silver', table.name)
    gold = sql.Identifier('gold', table.name)
    delete_batch = sql.SQL('DELETE FROM {} WHERE batch_id = %s')

    warehouse_sql.execute(conn, delete_batch.format(gold), (batch_id,))
    removed = warehouse_sql.execute(conn, delete_batch.format(silver), (batch_id,))
    warehouse_sql.execute(conn, delete_batch.format(bronze), (batch_id,))

    restored = warehouse_sql.execute(
        conn,
        sql.SQL(
            'UPDATE {} SET is_current = true, valid_to = NULL, '
            'superseded_by_batch_id = NULL WHERE superseded_by_batch_id = %s'
        ).format(silver),
        (batch_id,),
    )
    warehouse_sql.execute(
        conn,
        sql.SQL(
            'UPDATE {gold} g SET is_current = true FROM {silver} s '
            'WHERE g.silver_sk = s.{sk} AND s.is_current '
            'AND s.superseded_by_batch_id IS NULL AND NOT g.is_current'
        ).format(gold=gold, silver=silver, sk=sql.Identifier(table.sk_column)),
    )
    return removed, restored


def _delete_load_records(conn, load_id: int) -> str | None:
    load = warehouse_sql.query_one(conn, 'SELECT batch_id, upload_id FROM ctl.load WHERE load_id = %s', (load_id,))
    file_path = warehouse_sql.scalar(
        conn, 'SELECT storage_uri FROM ctl.upload WHERE upload_id = %s', (load['upload_id'],)
    )
    warehouse_sql.execute(conn, 'UPDATE ctl.load SET batch_id = NULL WHERE load_id = %s', (load_id,))
    warehouse_sql.execute(conn, 'DELETE FROM ctl.batch WHERE load_id = %s', (load_id,))
    warehouse_sql.execute(conn, 'DELETE FROM ctl.load WHERE load_id = %s', (load_id,))
    still_used = warehouse_sql.scalar(conn, 'SELECT count(*) FROM ctl.load WHERE upload_id = %s', (load['upload_id'],))
    if not still_used:
        warehouse_sql.execute(conn, 'DELETE FROM ctl.upload WHERE upload_id = %s', (load['upload_id'],))
    return file_path
