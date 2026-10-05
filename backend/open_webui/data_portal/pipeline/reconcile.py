from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from psycopg import sql

from .. import messages
from ..db import sql as warehouse_sql
from ..registry.schema import FormTable
from ..sources.base import normalize_name
from ..sources.customer_report_verify import CustomerReportVerifyReader
from ..sources.header_table import KIND as HEADER_TABLE_KIND
from ..sources.header_table_verify import HeaderTableVerifyReader
from .context import LoadContext
from .silver import staging_table_name

EXCEL_EPOCH = dt.date(1899, 12, 30)
EXCEL_MAX_SERIAL = 2_958_465
MAX_REPORTED_DIFFERENCES = 20
MONEY_TYPES = ('money', 'currency')
NUMERIC_SUM = (
    "coalesce(sum(CASE WHEN {column} ~ '^[+-]?([0-9]+(\\.[0-9]*)?|\\.[0-9]+)([eE][+-]?[0-9]+)?$' "
    'THEN {column}::numeric ELSE 0 END), 0)'
)

STEP_LABELS = {
    'R1': messages.RECONCILE_STEP_R1,
    'R2': messages.RECONCILE_STEP_R2,
    'R3': messages.RECONCILE_STEP_R3,
    'R4a': messages.RECONCILE_STEP_R4A,
    'R4c': messages.RECONCILE_STEP_R4C,
}


@dataclass
class Mismatch:
    step: str
    table: str | None
    label: str
    step_label: str


@dataclass
class _Check:
    step: str
    table_id: int
    metric: str
    expected: object
    actual: object
    passed: bool
    detail: dict | None = None


def reconcile_file_to_bronze(ctx: LoadContext, table: FormTable, table_id: int) -> bool:
    headers, file_rows = _reread_table(ctx, table)
    index_by_name = {normalize_name(name): index for index, name in headers.items()}
    column_index = {c.name: index_by_name.get(normalize_name(c.file_header)) for c in table.file_columns}

    bronze_rows = warehouse_sql.query(
        ctx.conn,
        sql.SQL('SELECT source_row, {columns} FROM {source} WHERE load_id = %s').format(
            columns=warehouse_sql.column_list(table.column_names), source=sql.Identifier('bronze', table.name)
        ),
        (ctx.load_id,),
    )
    by_row = {row['source_row']: row for row in bronze_rows}
    file_row_numbers = {
        number
        for number, cells in file_rows.items()
        if any(cells.get(index) is not None for index in column_index.values() if index)
    }
    missing_in_bronze = sorted(file_row_numbers - set(by_row))
    extra_in_bronze = sorted(set(by_row) - file_row_numbers)
    differences = _cell_differences(by_row, file_rows, column_index)

    passed = not (differences or missing_in_bronze or extra_in_bronze)
    detail = {
        'o_lech': differences,
        'thieu_o_goc': missing_in_bronze[:MAX_REPORTED_DIFFERENCES],
        'thua_o_goc': extra_in_bronze[:MAX_REPORTED_DIFFERENCES],
    }
    _record(ctx, _Check('R1', table_id, 'so_dong', len(file_row_numbers), len(by_row), passed, detail))
    return passed


def reconcile_bronze_to_silver(ctx: LoadContext, table: FormTable, table_id: int) -> bool:
    result = ctx.table_result(table)
    inserted = _batch_row_count(ctx, table)
    expected = result.rows_bronze
    actual = inserted + result.rows_unchanged + result.rows_duplicate
    passed = expected == actual
    detail = {
        'vao_chuan_hoa': inserted,
        'khong_doi': result.rows_unchanged,
        'trung_trong_tep': result.rows_duplicate,
    }
    _record(ctx, _Check('R2', table_id, 'ket_cuc_tung_dong', expected, actual, passed, detail))
    return passed


def reconcile_silver_to_gold(ctx: LoadContext, table: FormTable, table_id: int) -> bool:
    statement = sql.SQL(
        'WITH s AS (SELECT {columns} FROM {silver} WHERE batch_id = %s AND is_current), '
        '     g AS (SELECT {columns} FROM {gold} WHERE batch_id = %s AND is_current) '
        'SELECT (SELECT count(*) FROM (SELECT * FROM s EXCEPT ALL SELECT * FROM g) x) '
        '       AS missing_in_gold, '
        '       (SELECT count(*) FROM (SELECT * FROM g EXCEPT ALL SELECT * FROM s) y) '
        '       AS extra_in_gold, '
        '       (SELECT count(*) FROM s) AS silver_rows, '
        '       (SELECT count(*) FROM g) AS gold_rows'
    ).format(
        columns=warehouse_sql.column_list(table.column_names),
        silver=sql.Identifier('silver', table.name),
        gold=sql.Identifier('gold', table.name),
    )
    row = warehouse_sql.query_one(ctx.conn, statement, (ctx.batch_id, ctx.batch_id))

    passed = row['missing_in_gold'] == 0 and row['extra_in_gold'] == 0
    detail = {'thieu_o_gold': row['missing_in_gold'], 'thua_o_gold': row['extra_in_gold']}
    _record(ctx, _Check('R3', table_id, 'so_dong', row['silver_rows'], row['gold_rows'], passed, detail))
    return passed


def reconcile_row_retention(ctx: LoadContext, table: FormTable, table_id: int) -> bool:
    result = ctx.table_result(table)
    actual = _batch_row_count(ctx, table)
    expected = result.rows_bronze - result.rows_unchanged - result.rows_duplicate
    passed = actual == expected
    detail = {'business_key': table.business_key}
    _record(ctx, _Check('R4a', table_id, 'dong_giu_lai', expected, actual, passed, detail))
    return passed


def reconcile_control_total(ctx: LoadContext, table: FormTable, table_id: int) -> bool:
    money_columns = [c.name for c in table.measures if c.type in MONEY_TYPES]
    if not money_columns:
        return True

    file_total = _bronze_total(ctx, table, money_columns)
    silver_total = _silver_total(ctx, table, money_columns)
    unchanged_total = _unchanged_rows_total(ctx, table, money_columns)

    written_total = Decimal(silver_total) + Decimal(unchanged_total)
    difference = Decimal(file_total) - written_total
    passed = difference == 0
    detail = {
        'cot': money_columns,
        'tong_tep': str(file_total),
        'tong_chuan_hoa': str(silver_total),
        'tong_khong_doi': str(unchanged_total),
        'lech': str(difference),
    }
    _record(ctx, _Check('R4c', table_id, 'tong_kiem_soat', file_total, written_total, passed, detail))
    return passed


def run_reconciliation(ctx: LoadContext, table_ids: dict[str, int]) -> list[Mismatch]:
    rules = (
        ('R1', reconcile_file_to_bronze),
        ('R2', reconcile_bronze_to_silver),
        ('R3', reconcile_silver_to_gold),
        ('R4a', reconcile_row_retention),
        ('R4c', reconcile_control_total),
    )
    mismatches: list[Mismatch] = []
    for table in ctx.form.tables_by_dependency:
        table_id = table_ids[table.name]
        if ctx.table_result(table).rows_bronze == 0:
            continue
        for step, rule in rules:
            if not rule(ctx, table, table_id):
                mismatches.append(Mismatch(step, table.name, table.label, STEP_LABELS[step]))
    return mismatches


def load_results(conn, load_id: int) -> list[dict]:
    return warehouse_sql.query(
        conn,
        """
        SELECT r.step, r.metric, r.expected, r.actual, r.diff, r.passed, r.detail,
               ft.label AS table_label, ft.name AS table_name
          FROM ctl.recon_result r
          LEFT JOIN ctl.form_table ft ON ft.table_id = r.table_id
         WHERE r.load_id = %s
         ORDER BY ft.display_order, r.step
        """,
        (load_id,),
    )


def _values_equal(left: str | None, right: str | None) -> bool:
    if left is None and right is None:
        return True
    if left is None or right is None:
        return False
    if str(left).strip() == str(right).strip():
        return True
    left_number, right_number = _to_decimal(left), _to_decimal(right)
    if left_number is not None and right_number is not None:
        return _numbers_equal(left_number, right_number)
    return _excel_date_matches(left_number, right) or _excel_date_matches(right_number, left)


def _record(ctx: LoadContext, check: _Check) -> None:
    expected = None if check.expected is None else Decimal(str(check.expected))
    actual = None if check.actual is None else Decimal(str(check.actual))
    difference = None if (expected is None or actual is None) else actual - expected
    warehouse_sql.execute(
        ctx.conn,
        """
        INSERT INTO ctl.recon_result (load_id, step, table_id, metric, expected, actual,
                                      diff, passed, detail)
             VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (load_id, step, table_id, metric) DO UPDATE
                SET expected = EXCLUDED.expected, actual = EXCLUDED.actual,
                    diff = EXCLUDED.diff, passed = EXCLUDED.passed,
                    detail = EXCLUDED.detail
        """,
        (
            ctx.load_id,
            check.step,
            check.table_id,
            check.metric,
            expected,
            actual,
            difference,
            check.passed,
            json.dumps(check.detail or {}, ensure_ascii=False, default=str),
        ),
    )


def _to_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None


def _numbers_equal(left: Decimal, right: Decimal) -> bool:
    if left == right:
        return True
    try:
        return float(left) == float(right)
    except (OverflowError, ValueError):
        return False


def _excel_date_matches(serial: Decimal | None, text: str) -> bool:
    if serial is None or serial <= 0 or serial > EXCEL_MAX_SERIAL:
        return False
    try:
        date = EXCEL_EPOCH + dt.timedelta(days=int(serial))
    except (OverflowError, ValueError):
        return False
    return str(text).strip().startswith(date.isoformat())


def _reread_table(ctx: LoadContext, table: FormTable):
    reader = (
        HeaderTableVerifyReader(ctx.upload_path, ctx.form)
        if ctx.form.source_kind == HEADER_TABLE_KIND
        else CustomerReportVerifyReader(ctx.upload_path)
    )
    try:
        return reader.read_table(table.sheet)
    finally:
        reader.close()


def _cell_differences(by_row: dict[int, dict], file_rows: dict, column_index: dict[str, int | None]) -> list[dict]:
    differences: list[dict] = []
    for number, bronze_row in by_row.items():
        cells = file_rows.get(number, {})
        for name, index in column_index.items():
            in_file = cells.get(index) if index else None
            if not _values_equal(in_file, bronze_row[name]):
                differences.append({'source_row': number, 'column': name, 'tep': in_file, 'goc': bronze_row[name]})
                if len(differences) >= MAX_REPORTED_DIFFERENCES:
                    return differences
    return differences


def _batch_row_count(ctx: LoadContext, table: FormTable) -> int:
    return warehouse_sql.scalar(
        ctx.conn,
        sql.SQL('SELECT count(*) FROM {} WHERE batch_id = %s').format(sql.Identifier('silver', table.name)),
        (ctx.batch_id,),
    )


def _sum_expression(columns: list[str], alias: str | None = None) -> sql.Composed:
    template = 'coalesce(sum({}), 0)' if alias is None else f'coalesce(sum({alias}.{{}}), 0)'
    return sql.SQL(' + ').join(sql.SQL(template).format(sql.Identifier(c)) for c in columns)


def _bronze_total(ctx: LoadContext, table: FormTable, money_columns: list[str]) -> Decimal:
    expression = sql.SQL(' + ').join(
        sql.SQL(NUMERIC_SUM).format(column=sql.Identifier(column)) for column in money_columns
    )
    return warehouse_sql.scalar(
        ctx.conn,
        sql.SQL('SELECT {expression} FROM {source} WHERE load_id = %s').format(
            expression=expression, source=sql.Identifier('bronze', table.name)
        ),
        (ctx.load_id,),
    ) or Decimal(0)


def _silver_total(ctx: LoadContext, table: FormTable, money_columns: list[str]) -> Decimal:
    return warehouse_sql.scalar(
        ctx.conn,
        sql.SQL('SELECT {expression} FROM {source} WHERE batch_id = %s').format(
            expression=_sum_expression(money_columns), source=sql.Identifier('silver', table.name)
        ),
        (ctx.batch_id,),
    ) or Decimal(0)


def _unchanged_rows_total(ctx: LoadContext, table: FormTable, money_columns: list[str]) -> Decimal:
    if table.merge in ('append', 'replace_all') or not table.business_key:
        return Decimal(0)
    staging_name = staging_table_name(table)
    if warehouse_sql.scalar(ctx.conn, 'SELECT to_regclass(%s)', (f'pg_temp.{staging_name}',)) is None:
        return Decimal(0)
    match = sql.SQL(' AND ').join(
        sql.SQL('c.{c} IS NOT DISTINCT FROM g.{c}').format(c=sql.Identifier(c)) for c in table.business_key
    )
    total = warehouse_sql.scalar(
        ctx.conn,
        sql.SQL(
            'SELECT {expression} FROM {staging} g '
            ' WHERE EXISTS (SELECT 1 FROM {silver} c '
            '                WHERE c.domain_id = %s AND c.is_current AND {match} '
            '                  AND c.row_hash = g.row_hash AND c.batch_id <> %s)'
        ).format(
            expression=_sum_expression(money_columns, 'g'),
            staging=sql.Identifier(staging_name),
            silver=sql.Identifier('silver', table.name),
            match=match,
        ),
        (ctx.domain_id, ctx.batch_id),
    )
    return Decimal(total or 0)
