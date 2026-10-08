from __future__ import annotations

from dataclasses import dataclass

from ..db import sql as warehouse_sql
from ..registry.loader import FormRegistry

STATUSES = ('success', 'rejected', 'mismatch', 'rolled_back')
STATUS_SUCCESS = 'success'


@dataclass
class LoadFilter:
    year: int | None = None
    form_id: int | None = None
    status: str = ''
    user: str = ''
    query: str = ''
    page: int = 1
    page_size: int = 25


def list_loads(conn, domain_id: int, load_filter: LoadFilter) -> tuple[list[dict], int]:
    where, params = _filter_clause(domain_id, load_filter)
    total = warehouse_sql.scalar(
        conn,
        f'SELECT count(*) FROM ctl.load l JOIN ctl.upload u ON u.upload_id = l.upload_id WHERE {where}',
        params,
    )
    rows = warehouse_sql.query(
        conn,
        f"""
        SELECT l.load_id, l.status, l.rows_read, l.started_at, l.year, l.month, l.form_id,
               u.file_name, f.code AS form_code, f.label AS form_label,
               coalesce(l.actor_username, '—') AS user_name
          FROM ctl.load l
          JOIN ctl.upload u ON u.upload_id = l.upload_id
          JOIN ctl.form f   ON f.form_id = l.form_id
         WHERE {where}
         ORDER BY l.load_id DESC
         LIMIT %s OFFSET %s
        """,
        [*params, load_filter.page_size, (load_filter.page - 1) * load_filter.page_size],
    )
    return rows, total


def list_uploaders(conn, domain_id: int) -> list[str]:
    rows = warehouse_sql.query(
        conn,
        'SELECT DISTINCT actor_username AS user_name FROM ctl.load '
        ' WHERE domain_id = %s AND actor_username IS NOT NULL ORDER BY 1',
        (domain_id,),
    )
    return [row['user_name'] for row in rows]


def get_load(conn, load_id: int) -> dict | None:
    return warehouse_sql.query_one(
        conn,
        """
        SELECT l.load_id, l.status, l.rows_read, l.rows_written, l.sheets_count,
               l.started_at, l.finished_at, l.errors, l.report, l.batch_id,
               l.domain_id, l.form_id, l.year, l.month, l.file_check, l.steps, l.reconciliation,
               u.file_name, u.size_bytes, u.storage_uri,
               f.code AS form_code, d.code AS domain_code,
               coalesce(l.actor_username, '—') AS user_name
          FROM ctl.load l
          JOIN ctl.upload u ON u.upload_id = l.upload_id
          JOIN ctl.form f   ON f.form_id = l.form_id
          JOIN ctl.domain d ON d.domain_id = l.domain_id
         WHERE l.load_id = %s AND l.status <> 'running'
        """,
        (load_id,),
    )


def month_range(load: dict) -> str | None:
    if load['status'] != STATUS_SUCCESS:
        return None
    if load.get('month') is not None:
        return str(load['month'])
    tables = (load.get('file_check') or {}).get('tables', [])
    months = sorted(
        {int(period) for table in tables for period in (table.get('by_period') or {}) if str(period).isdigit()}
    )
    if not months:
        return None
    return str(months[0]) if len(months) == 1 else f'{months[0]} → {months[-1]}'


def rows_written(load: dict) -> int:
    if load['status'] != STATUS_SUCCESS:
        return 0
    tables = ((load.get('report') or {}).get('tables') or {}).values()
    return sum(int(table.get('rows_silver', 0)) + int(table.get('rows_unchanged', 0)) for table in tables)


def primary_table(registry: FormRegistry, form_code: str) -> str | None:
    form = registry.form(form_code)
    facts = [table for table in form.tables_by_display_order if not table.is_dim]
    return (facts or form.tables_by_display_order)[0].name


def error_rows(load: dict) -> list[dict]:
    return [
        {
            'sheet': error.get('sheet'),
            'location': error.get('location'),
            'issue': error.get('issue'),
            'resolution': error.get('resolution'),
        }
        for error in (load.get('errors') or [])
    ]


def _filter_clause(domain_id: int, load_filter: LoadFilter) -> tuple[str, list]:
    conditions = ['l.domain_id = %s', "l.status <> 'running'"]
    params: list = [domain_id]
    if load_filter.year is not None:
        conditions.append('l.year = %s')
        params.append(load_filter.year)
    if load_filter.form_id is not None:
        conditions.append('l.form_id = %s')
        params.append(load_filter.form_id)
    if load_filter.status:
        conditions.append('l.status = %s')
        params.append(load_filter.status)
    if load_filter.user:
        conditions.append('l.actor_username = %s')
        params.append(load_filter.user)
    if load_filter.query:
        conditions.append('(l.load_id::text ILIKE %s OR u.file_name ILIKE %s)')
        params += [f'%{load_filter.query.lstrip("#")}%', f'%{load_filter.query}%']
    return ' AND '.join(conditions), params
