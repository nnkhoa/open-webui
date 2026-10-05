from __future__ import annotations

import json

from ..db import catalog_sql
from ..db import sql as warehouse_sql
from .loader import FormRegistry
from .schema import Form, FormColumn, FormTable


def sync_definitions(catalog_conn, warehouse_conn, registry: FormRegistry) -> None:
    form_ids = {form.code: _upsert_form(catalog_conn, form) for form in registry.forms}
    _delete_stale_forms(catalog_conn, list(form_ids.values()))
    _upsert_domains(catalog_conn, registry, form_ids)
    mirror_to_warehouse(catalog_conn, warehouse_conn)


def mirror_to_warehouse(catalog_conn, warehouse_conn) -> None:
    if warehouse_conn is None:
        return
    _mirror_domains(catalog_conn, warehouse_conn)
    _mirror_forms(catalog_conn, warehouse_conn)
    _mirror_tables(catalog_conn, warehouse_conn)
    _mirror_columns(catalog_conn, warehouse_conn)
    _mirror_domain_forms(catalog_conn, warehouse_conn)
    _mirror_datasets(catalog_conn, warehouse_conn)


def _delete_stale_forms(catalog_conn, kept_form_ids: list[int]) -> None:
    placeholders = ', '.join('?' * len(kept_form_ids))
    catalog_sql.execute(
        catalog_conn, f'DELETE FROM ctl_form WHERE form_id NOT IN ({placeholders})', tuple(kept_form_ids)
    )


def _upsert_domains(catalog_conn, registry: FormRegistry, form_ids: dict[str, int]) -> None:
    for domain in registry.domains:
        domain_id = catalog_sql.scalar(
            catalog_conn,
            """
            INSERT INTO ctl_domain (code, name, description, status)
                 VALUES (?, ?, ?, 'active')
            ON CONFLICT (code) DO UPDATE
                    SET name = excluded.name, description = excluded.description,
                        status = 'active'
              RETURNING domain_id
            """,
            (domain.code, domain.name, domain.description),
        )
        catalog_sql.execute(catalog_conn, 'DELETE FROM ctl_domain_form WHERE domain_id = ?', (domain_id,))
        for position, form_code in enumerate(domain.forms, start=1):
            catalog_sql.execute(
                catalog_conn,
                'INSERT INTO ctl_domain_form (domain_id, form_id, position) VALUES (?, ?, ?)',
                (domain_id, form_ids[form_code], position),
            )

    codes = [domain.code for domain in registry.domains]
    catalog_sql.execute(
        catalog_conn,
        f"UPDATE ctl_domain SET status = 'suspended' WHERE code NOT IN ({', '.join('?' * len(codes))})",
        tuple(codes),
    )


def _upsert_form(catalog_conn, form: Form) -> int:
    policy = {
        'unknown_sheet': form.policy.unknown_sheet,
        'unknown_column': form.policy.unknown_column,
        'missing_column': form.policy.missing_column,
    }
    form_id = catalog_sql.scalar(
        catalog_conn,
        """
        INSERT INTO ctl_form (code, label, description, current_version, yaml_sha256, policy)
             VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (code) DO UPDATE
                SET label = excluded.label,
                    description = excluded.description,
                    current_version = excluded.current_version,
                    yaml_sha256 = excluded.yaml_sha256,
                    policy = excluded.policy
          RETURNING form_id
        """,
        (form.code, form.label, form.description, form.version, form.yaml_sha256, json.dumps(policy)),
    )
    table_ids = {table.name: _upsert_table(catalog_conn, form_id, table) for table in form.tables_by_display_order}
    for table in form.tables_by_display_order:
        _replace_columns(catalog_conn, table_ids[table.name], table)
    return form_id


def _upsert_table(catalog_conn, form_id: int, table: FormTable) -> int:
    return catalog_sql.scalar(
        catalog_conn,
        """
        INSERT INTO ctl_form_table (form_id, name, kind, sheet, label, card_label,
                                    description, card_description, grain, business_key,
                                    merge_strategy, partition_by, order_by, display_order)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (name) DO UPDATE
                SET form_id = excluded.form_id, kind = excluded.kind,
                    sheet = excluded.sheet, label = excluded.label,
                    card_label = excluded.card_label, description = excluded.description,
                    card_description = excluded.card_description, grain = excluded.grain,
                    business_key = excluded.business_key,
                    merge_strategy = excluded.merge_strategy,
                    partition_by = excluded.partition_by, order_by = excluded.order_by,
                    display_order = excluded.display_order
          RETURNING table_id
        """,
        (
            form_id,
            table.name,
            table.kind,
            table.sheet,
            table.label,
            table.card_title,
            table.description,
            table.card_description,
            table.grain,
            _json_list(table.business_key),
            table.merge,
            _json_list(table.partition_by),
            _json_list(table.order),
            table.display_order,
        ),
    )


def _replace_columns(catalog_conn, table_id: int, table: FormTable) -> None:
    catalog_sql.execute(catalog_conn, 'DELETE FROM ctl_form_column WHERE table_id = ?', (table_id,))
    for column in table.columns:
        catalog_sql.execute(
            catalog_conn,
            """
            INSERT INTO ctl_form_column (table_id, name, ordinal, type, required,
                                         is_business_key, label, meaning, how, example,
                                         enum_values, role, display_width, show_in_table)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            _column_row(table_id, column),
        )


def _column_row(table_id: int, column: FormColumn) -> tuple:
    return (
        table_id,
        column.name,
        column.ordinal,
        column.type,
        1 if column.required else 0,
        1 if column.is_business_key else 0,
        column.label,
        column.meaning,
        column.how,
        column.example,
        _json_list(column.values) if column.values else None,
        column.role,
        column.display_width,
        1 if column.show_in_table else 0,
    )


def _json_list(values: list[str]) -> str:
    return json.dumps(list(values), ensure_ascii=False)


def _dataset_pairs(catalog_conn) -> list[dict]:
    return catalog_sql.query(
        catalog_conn,
        """
        SELECT df.domain_id, ft.table_id,
               coalesce(ft.card_label, ft.label)             AS label,
               coalesce(ft.card_description, ft.description) AS description,
               ft.display_order
          FROM ctl_domain_form df
          JOIN ctl_domain d      ON d.domain_id = df.domain_id AND d.status = 'active'
          JOIN ctl_form_table ft ON ft.form_id = df.form_id
        """,
    )


def _mirror_domains(catalog_conn, warehouse_conn) -> None:
    for domain in catalog_sql.query(catalog_conn, 'SELECT domain_id, code, name, description, status FROM ctl_domain'):
        warehouse_sql.execute(
            warehouse_conn,
            """
            INSERT INTO ctl.domain (domain_id, code, name, description, status)
                 VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (domain_id) DO UPDATE
                    SET code = EXCLUDED.code, name = EXCLUDED.name,
                        description = EXCLUDED.description, status = EXCLUDED.status
            """,
            (domain['domain_id'], domain['code'], domain['name'], domain['description'], domain['status']),
        )


def _mirror_forms(catalog_conn, warehouse_conn) -> None:
    forms = catalog_sql.query(
        catalog_conn,
        'SELECT form_id, code, label, description, current_version, yaml_sha256, policy FROM ctl_form',
    )
    for form in forms:
        warehouse_sql.execute(
            warehouse_conn,
            """
            INSERT INTO ctl.form (form_id, code, label, description, current_version,
                                  yaml_sha256, policy)
                 VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (form_id) DO UPDATE
                    SET code = EXCLUDED.code, label = EXCLUDED.label,
                        description = EXCLUDED.description,
                        current_version = EXCLUDED.current_version,
                        yaml_sha256 = EXCLUDED.yaml_sha256, policy = EXCLUDED.policy
            """,
            (
                form['form_id'],
                form['code'],
                form['label'],
                form['description'],
                form['current_version'],
                form['yaml_sha256'],
                form['policy'],
            ),
        )


def _mirror_tables(catalog_conn, warehouse_conn) -> None:
    for table in catalog_sql.query(catalog_conn, 'SELECT * FROM ctl_form_table'):
        warehouse_sql.execute(
            warehouse_conn,
            """
            INSERT INTO ctl.form_table (table_id, form_id, name, kind, sheet, label,
                                        card_label, description, card_description, grain,
                                        business_key, merge_strategy, partition_by, order_by,
                                        display_order)
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (table_id) DO UPDATE
                    SET form_id = EXCLUDED.form_id, name = EXCLUDED.name,
                        kind = EXCLUDED.kind, sheet = EXCLUDED.sheet,
                        label = EXCLUDED.label, card_label = EXCLUDED.card_label,
                        description = EXCLUDED.description,
                        card_description = EXCLUDED.card_description,
                        grain = EXCLUDED.grain, business_key = EXCLUDED.business_key,
                        merge_strategy = EXCLUDED.merge_strategy,
                        partition_by = EXCLUDED.partition_by, order_by = EXCLUDED.order_by,
                        display_order = EXCLUDED.display_order
            """,
            (
                table['table_id'],
                table['form_id'],
                table['name'],
                table['kind'],
                table['sheet'],
                table['label'],
                table['card_label'],
                table['description'],
                table['card_description'],
                table['grain'],
                json.loads(table['business_key']),
                table['merge_strategy'],
                json.loads(table['partition_by']),
                json.loads(table['order_by']),
                table['display_order'],
            ),
        )
        warehouse_sql.execute(warehouse_conn, 'DELETE FROM ctl.form_column WHERE table_id = %s', (table['table_id'],))


def _mirror_columns(catalog_conn, warehouse_conn) -> None:
    for column in catalog_sql.query(catalog_conn, 'SELECT * FROM ctl_form_column ORDER BY table_id, ordinal'):
        warehouse_sql.execute(
            warehouse_conn,
            """
            INSERT INTO ctl.form_column (table_id, name, ordinal, type, required,
                                         is_business_key, label, meaning, how, example,
                                         enum_values, role, display_width, show_in_table)
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                column['table_id'],
                column['name'],
                column['ordinal'],
                column['type'],
                bool(column['required']),
                bool(column['is_business_key']),
                column['label'],
                column['meaning'],
                column['how'],
                column['example'],
                json.loads(column['enum_values']) if column['enum_values'] else None,
                column['role'],
                column['display_width'],
                bool(column['show_in_table']),
            ),
        )


def _mirror_domain_forms(catalog_conn, warehouse_conn) -> None:
    warehouse_sql.execute(warehouse_conn, 'DELETE FROM ctl.domain_form')
    for row in catalog_sql.query(catalog_conn, 'SELECT domain_id, form_id, position FROM ctl_domain_form'):
        warehouse_sql.execute(
            warehouse_conn,
            'INSERT INTO ctl.domain_form (domain_id, form_id, position) VALUES (%s, %s, %s)',
            (row['domain_id'], row['form_id'], row['position']),
        )


def _mirror_datasets(catalog_conn, warehouse_conn) -> None:
    pairs = _dataset_pairs(catalog_conn)
    warehouse_sql.execute(
        warehouse_conn,
        'DELETE FROM ctl.dataset d WHERE NOT EXISTS ('
        '  SELECT 1 FROM unnest(%s::int[], %s::int[]) AS k(domain_id, table_id) '
        '   WHERE k.domain_id = d.domain_id AND k.table_id = d.table_id)',
        ([pair['domain_id'] for pair in pairs], [pair['table_id'] for pair in pairs]),
    )
    for pair in pairs:
        warehouse_sql.execute(
            warehouse_conn,
            """
            INSERT INTO ctl.dataset (domain_id, table_id, label, description, display_order)
                 VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (domain_id, table_id) DO UPDATE
                    SET label = EXCLUDED.label,
                        description = EXCLUDED.description,
                        display_order = EXCLUDED.display_order
            """,
            (pair['domain_id'], pair['table_id'], pair['label'], pair['description'], pair['display_order']),
        )
