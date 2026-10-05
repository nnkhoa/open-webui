from __future__ import annotations

from .schema import Form, FormColumn, FormTable

LAYER_DDL_TITLES = ('lớp gốc', 'lớp chuẩn hoá', 'lớp phân tích', 'tầng phục vụ')
SECTION_RULE = '-- ' + '=' * 75

CONTROL_REFERENCE_COLUMNS = (
    ('domain_id', 'smallint', '    NOT NULL REFERENCES ctl.domain(domain_id)'),
    ('load_id', 'bigint', '      NOT NULL REFERENCES ctl.load(load_id)'),
    ('batch_id', 'bigint', '      NOT NULL REFERENCES ctl.batch(batch_id)'),
)


def business_key_expression(table: FormTable) -> str:
    parts = []
    for name in table.business_key:
        column = table.column(name)
        is_text = column.handler.silver_sql_type == 'text'
        parts.append(name if column.required or not is_text else f"coalesce({name}, '')")
    return ', '.join(parts)


def bronze_ddl(table: FormTable) -> str:
    lines = [_column_line('row_id', 'bigserial', '   PRIMARY KEY')]
    lines += [_column_line(column.name, 'text') for column in table.columns]
    lines += [_column_line(*reference) for reference in CONTROL_REFERENCE_COLUMNS]
    lines += [
        _column_line('source_sheet', 'text', '        NOT NULL'),
        _column_line('source_row', 'int', '         NOT NULL'),
        _column_line('loaded_at', 'timestamptz', ' NOT NULL'),
        _column_line('row_hash', 'char(64)', '    NOT NULL'),
        '    UNIQUE (load_id, source_sheet, source_row)',
    ]
    sql = _create_table(f'bronze.{table.name}', lines, f'{table.label} — dữ liệu gốc, y nguyên như tệp')
    sql += f'\n\nCREATE INDEX bronze_{table.name}_batch_idx ON bronze.{table.name} (batch_id);'
    sql += f'\nCREATE INDEX bronze_{table.name}_hash_idx ON bronze.{table.name} (row_hash);'
    return sql


def silver_ddl(table: FormTable) -> str:
    lines = [_column_line(table.sk_column, 'bigint', '      GENERATED ALWAYS AS IDENTITY PRIMARY KEY')]
    lines += _typed_column_lines(table)
    lines += [_column_line(*reference) for reference in CONTROL_REFERENCE_COLUMNS]
    lines += [
        _column_line('bronze_id', 'bigint', f'      NOT NULL REFERENCES bronze.{table.name}(row_id)'),
        _column_line('source_sheet', 'text', '        NOT NULL'),
        _column_line('source_row', 'int', '         NOT NULL'),
        _column_line('row_hash', 'char(64)', '    NOT NULL'),
        _column_line('valid_from', 'timestamptz', ' NOT NULL'),
        _column_line('valid_to', 'timestamptz'),
        _column_line('is_current', 'boolean', '     NOT NULL DEFAULT true'),
        _column_line('superseded_by_batch_id', 'bigint', '      REFERENCES ctl.batch(batch_id)'),
        _column_line('supersedes_sk', 'bigint'),
    ]
    sql = _create_table(f'silver.{table.name}', lines, f'{table.label} — đã ép kiểu, có phiên bản theo lô')
    if table.business_key:
        sql += (
            '\n\n-- Khoá nghiệp vụ dùng để tra cứu, **không** duy nhất: một dòng trong tệp\n'
            '-- là một dòng ở đây, kể cả khi cột khoá để trống nên hai dòng trùng khoá.\n'
            f'CREATE INDEX silver_{table.name}_bk_idx\n'
            f'    ON silver.{table.name} (domain_id, {business_key_expression(table)}) WHERE is_current;'
        )
    sql += (
        f'\nCREATE INDEX silver_{table.name}_batch_idx ON silver.{table.name} (batch_id);'
        f'\nCREATE INDEX silver_{table.name}_bronze_idx ON silver.{table.name} (bronze_id);'
    )
    return sql + _partition_index('silver', table)


def gold_ddl(table: FormTable) -> str:
    sk = table.sk_column
    lines = [_column_line(sk, 'bigint', '      GENERATED ALWAYS AS IDENTITY PRIMARY KEY')]
    lines += _typed_column_lines(table)
    lines += [
        _column_line(*CONTROL_REFERENCE_COLUMNS[0]),
        _column_line('silver_sk', 'bigint', f'      NOT NULL REFERENCES silver.{table.name}({sk})'),
        _column_line(*CONTROL_REFERENCE_COLUMNS[1]),
        _column_line(*CONTROL_REFERENCE_COLUMNS[2]),
        _column_line('source_sheet', 'text', '        NOT NULL'),
        _column_line('source_row', 'int', '         NOT NULL'),
        _column_line('is_current', 'boolean', '     NOT NULL DEFAULT true'),
    ]
    sql = _create_table(f'gold.{table.name}', lines, f'{table.label} — bản chép lớp chuẩn hoá')
    sql += (
        f'\n\nCREATE UNIQUE INDEX gold_{table.name}_silver_idx\n'
        f'    ON gold.{table.name} (silver_sk);'
        f'\nCREATE INDEX gold_{table.name}_batch_idx ON gold.{table.name} (batch_id);'
    )
    return sql + _partition_index('gold', table)


def analytics_ddl(table: FormTable) -> str:
    selected = [f't.{column.name}' for column in table.columns]
    selected += ['t.domain_id', 't.load_id', 't.batch_id', 't.source_sheet', 't.source_row']
    select_list = ',\n           '.join(selected)
    return (
        f'-- {table.label}\n'
        f'CREATE VIEW analytics.v_{table.name} AS\n'
        f'    SELECT {select_list}\n'
        f'      FROM gold.{table.name} t\n'
        f'     WHERE t.is_current;'
    )


def form_ddl(form: Form) -> str:
    parts: list[str] = [
        SECTION_RULE,
        f'--  Khai báo {form.code} v{form.version} — {form.label}',
        '--  TỆP NÀY SINH TỰ ĐỘNG TỪ definitions/forms/. Không sửa bằng tay.',
        f'--  Nguồn: mã kiểm tra YAML {form.yaml_sha256[:16]}',
        SECTION_RULE,
        '',
    ]
    tables = form.tables_by_dependency
    builders = (bronze_ddl, silver_ddl, gold_ddl, analytics_ddl)
    for title, build in zip(LAYER_DDL_TITLES, builders, strict=True):
        parts.append(f'-- ---------- {title} ' + '-' * (60 - len(title)))
        parts.append('')
        for table in tables:
            parts.append(build(table))
            parts.append('')
    return '\n'.join(parts).rstrip() + '\n'


def new_table_ddl(table: FormTable) -> str:
    return '\n\n'.join([bronze_ddl(table), silver_ddl(table), gold_ddl(table), analytics_ddl(table)])


def add_column_ddl(table: FormTable, column: FormColumn) -> str:
    return '\n'.join(
        [
            f'ALTER TABLE bronze.{table.name} ADD COLUMN {column.name} text;',
            f'ALTER TABLE silver.{table.name} ADD COLUMN {column.name} {column.silver_sql_type};',
            f'ALTER TABLE gold.{table.name}   ADD COLUMN {column.name} {column.silver_sql_type};',
        ]
    )


def drop_not_null_ddl(table: FormTable, column: FormColumn) -> str:
    return '\n'.join(
        f'ALTER TABLE {layer}.{table.name} ALTER COLUMN {column.name} DROP NOT NULL;' for layer in ('silver', 'gold')
    )


def rebuild_view_ddl(table: FormTable) -> str:
    return f'DROP VIEW IF EXISTS analytics.v_{table.name};\n' + analytics_ddl(table)


def rebuild_business_key_ddl(table: FormTable) -> str:
    return '\n'.join(
        [
            f'DROP INDEX IF EXISTS silver.silver_{table.name}_bk_idx;',
            f'CREATE INDEX silver_{table.name}_bk_idx',
            f'    ON silver.{table.name} (domain_id, {business_key_expression(table)}) WHERE is_current;',
        ]
    )


def _column_line(name: str, sql_type: str, suffix: str = '') -> str:
    return f'    {name:<26} {sql_type}{suffix}'


def _typed_column_lines(table: FormTable) -> list[str]:
    return [
        _column_line(column.name, column.silver_sql_type, '  NOT NULL' if column.required else '')
        for column in table.columns
    ]


def _create_table(table_name: str, lines: list[str], comment: str = '') -> str:
    body = ',\n'.join(lines)
    heading = f'-- {comment}\n' if comment else ''
    return f'{heading}CREATE TABLE {table_name} (\n{body}\n);'


def _partition_index(layer: str, table: FormTable) -> str:
    if not table.partition_by:
        return ''
    columns = ', '.join(table.partition_by)
    return (
        f'\nCREATE INDEX {layer}_{table.name}_part_idx\n'
        f'    ON {layer}.{table.name} (domain_id, {columns}) WHERE is_current;'
    )
