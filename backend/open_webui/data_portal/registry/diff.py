from __future__ import annotations

import re
from dataclasses import dataclass, field

from psycopg import sql

from .. import messages
from ..db import sql as warehouse_sql
from .ddl import (
    SECTION_RULE,
    add_column_ddl,
    drop_not_null_ddl,
    new_table_ddl,
    rebuild_business_key_ddl,
    rebuild_view_ddl,
)
from .schema import Form, FormColumn, FormTable

RISK_SAFE = 'safe'
RISK_REVIEW = 'review'
RISK_BLOCKED = 'blocked'

SYSTEM_COLUMNS = {
    'domain_id',
    'load_id',
    'batch_id',
    'bronze_id',
    'source_sheet',
    'source_row',
    'row_hash',
    'valid_from',
    'valid_to',
    'is_current',
    'superseded_by_batch_id',
    'supersedes_sk',
    'silver_sk',
    'row_id',
}

IDENTIFIER_PATTERN = re.compile(r'[a-z_][a-z0-9_]*')


@dataclass(frozen=True)
class Change:
    kind: str
    risk: str
    table: str
    description: str
    column: str | None = None
    reason: str | None = None
    ddl: str = ''


@dataclass
class MigrationPlan:
    form_code: str
    changes: list[Change] = field(default_factory=list)

    @property
    def blocked(self) -> list[Change]:
        return [change for change in self.changes if change.risk == RISK_BLOCKED]

    @property
    def ddl_changes(self) -> list[Change]:
        return [change for change in self.changes if change.ddl]

    def to_sql(self) -> str:
        parts = [
            SECTION_RULE,
            f'--  Nâng cấp bảng theo khai báo {self.form_code}',
            '--  TỆP NÀY SINH TỰ ĐỘNG bởi lệnh manage makemigration. Không sửa bằng tay.',
            SECTION_RULE,
            '',
        ]
        for change in self.ddl_changes:
            parts += [f'-- {change.description}', change.ddl, '']
        return '\n'.join(parts).rstrip() + '\n'


def compare(conn, form: Form) -> MigrationPlan:
    plan = MigrationPlan(form_code=form.code)
    for table in form.tables_by_dependency:
        existing = _existing_columns(conn, 'silver', table.name)
        if existing:
            plan.changes += _compare_table(conn, table, existing)
        else:
            plan.changes.append(
                Change(
                    kind='add_table',
                    risk=RISK_SAFE,
                    table=table.name,
                    description=messages.REGISTRY_CHANGE_ADD_TABLE.format(label=table.label, table=table.name),
                    ddl=new_table_ddl(table),
                )
            )
    plan.changes += _removed_tables(conn, form)
    return plan


def _compare_table(conn, table: FormTable, existing: dict[str, str]) -> list[Change]:
    business_columns = {
        name: sql_type for name, sql_type in existing.items() if name not in SYSTEM_COLUMNS and name != table.sk_column
    }
    row_count = _row_count(conn, 'silver', table.name)
    not_null = _not_null_columns(conn, 'silver', table.name) | _not_null_columns(conn, 'gold', table.name)

    changes: list[Change] = []
    for column in table.columns:
        current_type = business_columns.pop(column.name, None)
        changes += _compare_column(table, column, current_type, column.name in not_null, row_count)
    if any(change.kind == 'add_column' for change in changes):
        changes.append(
            Change(
                kind='rebuild_view',
                risk=RISK_SAFE,
                table=table.name,
                description=messages.REGISTRY_CHANGE_REBUILD_VIEW.format(table=table.name),
                ddl=rebuild_view_ddl(table),
            )
        )
    changes += [_dropped_column(table, name, row_count) for name in business_columns]
    business_key_change = _business_key_change(conn, table)
    if business_key_change:
        changes.append(business_key_change)
    return changes


def _compare_column(
    table: FormTable, column: FormColumn, current_type: str | None, is_not_null: bool, row_count: int
) -> list[Change]:
    changes: list[Change] = []
    if is_not_null and not column.required:
        changes.append(
            Change(
                kind='drop_not_null',
                risk=RISK_SAFE,
                table=table.name,
                column=column.name,
                description=messages.REGISTRY_CHANGE_DROP_NOT_NULL.format(
                    label=column.label, column=column.name, table=table.name
                ),
                ddl=drop_not_null_ddl(table, column),
            )
        )
    if current_type is None:
        reason = _with_row_count(messages.REGISTRY_CHANGE_ADD_COLUMN_REASON, row_count) if row_count > 0 else None
        changes.append(
            Change(
                kind='add_column',
                risk=RISK_SAFE,
                table=table.name,
                column=column.name,
                description=messages.REGISTRY_CHANGE_ADD_COLUMN.format(
                    label=column.label, column=column.name, table=table.name
                ),
                reason=reason,
                ddl=add_column_ddl(table, column),
            )
        )
    elif current_type.split('(')[0] != column.silver_sql_type.split('(')[0]:
        changes.append(_type_change(table, column, current_type, row_count))
    return changes


def _type_change(table: FormTable, column: FormColumn, current_type: str, row_count: int) -> Change:
    has_rows = row_count > 0
    return Change(
        kind='change_type',
        risk=RISK_BLOCKED if has_rows else RISK_REVIEW,
        table=table.name,
        column=column.name,
        description=messages.REGISTRY_CHANGE_TYPE.format(
            label=column.label, column=column.name, current=current_type, target=column.silver_sql_type
        ),
        reason=(
            _with_row_count(messages.REGISTRY_CHANGE_TYPE_REASON, row_count)
            if has_rows
            else messages.REGISTRY_CHANGE_TYPE_EMPTY
        ),
    )


def _dropped_column(table: FormTable, name: str, row_count: int) -> Change:
    has_rows = row_count > 0
    return Change(
        kind='drop_column',
        risk=RISK_BLOCKED if has_rows else RISK_REVIEW,
        table=table.name,
        column=name,
        description=messages.REGISTRY_CHANGE_DROP_COLUMN.format(column=name, table=table.name),
        reason=(
            _with_row_count(messages.REGISTRY_CHANGE_DROP_COLUMN_REASON, row_count)
            if has_rows
            else messages.REGISTRY_CHANGE_DROP_COLUMN_EMPTY
        ),
    )


def _business_key_change(conn, table: FormTable) -> Change | None:
    if not table.business_key:
        return None
    definition = _business_key_index(conn, table.name)
    if not definition or _business_key_matches(definition, table):
        return None
    return Change(
        kind='change_business_key',
        risk=RISK_REVIEW,
        table=table.name,
        description=messages.REGISTRY_CHANGE_BUSINESS_KEY.format(
            table=table.name, columns=', '.join(table.business_key)
        ),
        reason=messages.REGISTRY_CHANGE_BUSINESS_KEY_REASON,
        ddl=rebuild_business_key_ddl(table),
    )


def _removed_tables(conn, form: Form) -> list[Change]:
    declared = {table.name for table in form.tables}
    rows = warehouse_sql.query(
        conn,
        """
        SELECT ft.name FROM ctl.form_table ft
          JOIN ctl.form f ON f.form_id = ft.form_id
         WHERE f.code = %s
        """,
        (form.code,),
    )
    changes = []
    for row in rows:
        name = row['name']
        if name in declared:
            continue
        exists = bool(_existing_columns(conn, 'silver', name))
        row_count = _row_count(conn, 'silver', name) if exists else 0
        changes.append(
            Change(
                kind='drop_table',
                risk=RISK_BLOCKED if row_count else RISK_REVIEW,
                table=name,
                description=messages.REGISTRY_CHANGE_DROP_TABLE.format(table=name),
                reason=(
                    _with_row_count(messages.REGISTRY_CHANGE_DROP_TABLE_REASON, row_count)
                    if row_count
                    else messages.REGISTRY_CHANGE_DROP_TABLE_EMPTY
                ),
            )
        )
    return changes


def _with_row_count(template: str, row_count: int) -> str:
    return template.format(row_count=row_count).replace(',', '.')


def _existing_columns(conn, schema: str, table_name: str) -> dict[str, str]:
    rows = warehouse_sql.query(
        conn,
        """
        SELECT a.attname                                       AS name,
               pg_catalog.format_type(a.atttypid, a.atttypmod) AS sql_type
          FROM pg_attribute a
          JOIN pg_class c     ON c.oid = a.attrelid
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = %s AND c.relname = %s
               AND a.attnum > 0 AND NOT a.attisdropped
         ORDER BY a.attnum
        """,
        (schema, table_name),
    )
    return {row['name']: row['sql_type'] for row in rows}


def _not_null_columns(conn, schema: str, table_name: str) -> set[str]:
    rows = warehouse_sql.query(
        conn,
        """
        SELECT a.attname AS name
          FROM pg_attribute a
          JOIN pg_class c     ON c.oid = a.attrelid
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = %s AND c.relname = %s
               AND a.attnum > 0 AND NOT a.attisdropped AND a.attnotnull
        """,
        (schema, table_name),
    )
    return {row['name'] for row in rows}


def _row_count(conn, schema: str, table_name: str) -> int:
    statement = sql.SQL('SELECT count(*) FROM {}').format(warehouse_sql.table_identifier(schema, table_name))
    return int(warehouse_sql.scalar(conn, statement) or 0)


def _business_key_index(conn, table_name: str) -> str:
    return (
        warehouse_sql.scalar(
            conn,
            "SELECT indexdef FROM pg_indexes WHERE schemaname = 'silver' AND indexname = %s",
            (f'silver_{table_name}_bk_idx',),
        )
        or ''
    )


def _business_key_matches(definition: str, table: FormTable) -> bool:
    known_columns = set(table.column_names) | {'domain_id'}
    expected = ['domain_id', *table.business_key]
    return _index_columns(definition, known_columns) == expected


def _index_columns(definition: str, known_columns: set[str]) -> list[str]:
    columns = []
    for part in _split_top_level(_index_body(definition)):
        match = next((word for word in IDENTIFIER_PATTERN.findall(part.lower()) if word in known_columns), None)
        if match:
            columns.append(match)
    return columns


def _index_body(definition: str) -> str:
    body = definition[definition.find('(') + 1 :]
    return body[: body.rfind(')')]


def _split_top_level(text: str) -> list[str]:
    parts, current, depth = [], '', 0
    for char in text:
        if char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
        if char == ',' and depth == 0:
            parts.append(current)
            current = ''
        else:
            current += char
    parts.append(current)
    return parts
