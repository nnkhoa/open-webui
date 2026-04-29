import os
from pathlib import Path
from .connection import get_connection

_cached_schema_context = None


def reset_schema_cache() -> None:
    global _cached_schema_context
    _cached_schema_context = None


def _fallback_column_description(column_name: str) -> str:
    return f"Mô tả: dữ liệu của cột `{column_name}`."


def _render_schema_context(rows: list[tuple[str, str, str, str]]) -> str:
    lines = []
    current_table = None
    for table_name, column_name, data_type, column_comment in rows:
        if table_name != current_table:
            if current_table is not None:
                lines.append("")
            lines.append(f"TABLE: `{table_name}`")
            current_table = table_name
        description = (column_comment or "").strip() or _fallback_column_description(column_name)
        lines.append(f"- `{column_name}` | type={data_type} | {description}")
    return "\n".join(lines).strip()


def _get_metadata(pool_key: str | None = None) -> dict[str, dict]:
    meta = {"tables": {}, "columns": {}}
    conn = get_connection(pool_key=pool_key)
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("SELECT table_name, description_vi FROM _meta_tables")
        for row in cursor.fetchall():
            meta["tables"][row["table_name"]] = row["description_vi"]
    except Exception:
        pass

    try:
        cursor.execute("SELECT table_name, column_name, description_vi FROM _meta_columns")
        for row in cursor.fetchall():
            key = f"{row['table_name']}.{row['column_name']}"
            meta["columns"][key] = row["description_vi"]
    except Exception:
        pass

    cursor.close()
    conn.close()
    return meta


def get_schema_context(allowed_tables: list[str] | None = None, pool_key: str | None = None) -> str:
    global _cached_schema_context
    normalized_allowed = [str(t).strip().strip("`").lower() for t in (allowed_tables or []) if str(t).strip()]

    if _cached_schema_context is not None and not normalized_allowed and pool_key is None:
        return _cached_schema_context

    meta = _get_metadata(pool_key=pool_key)

    conn = get_connection(pool_key=pool_key)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT table_name, column_name, data_type, column_comment
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name NOT LIKE %s
        ORDER BY table_name, ordinal_position
        """,
        ("%\\_meta%",),
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if normalized_allowed:
        allowed_set = set(normalized_allowed)
        rows = [row for row in rows if str(row[0]).strip().lower() in allowed_set]

    lines = []
    current_table = None
    for table_name, column_name, data_type, column_comment in rows:
        if table_name != current_table:
            if current_table is not None:
                lines.append("")
            table_desc = meta["tables"].get(table_name, "")
            header = f"TABLE: `{table_name}`"
            if table_desc:
                header += f" | Mô tả: {table_desc}"
            lines.append(header)
            current_table = table_name

        col_key = f"{table_name}.{column_name}"
        description = meta["columns"].get(col_key) or (column_comment or "").strip() or _fallback_column_description(column_name)
        lines.append(f"- `{column_name}` | type={data_type} | {description}")

    rendered = "\n".join(lines).strip()
    if not normalized_allowed and pool_key is None:
        _cached_schema_context = rendered
    return rendered


def get_all_tables(pool_key: str | None = None):
    conn = get_connection(pool_key=pool_key)
    cursor = conn.cursor()
    cursor.execute("SHOW TABLES")
    table_names = [row[0] for row in cursor.fetchall()]
    max_preview_rows = int(os.getenv("TABLE_PREVIEW_LIMIT", "100"))
    tables = {}
    for name in table_names:
        cursor.execute(f"SELECT * FROM `{name}` LIMIT {max_preview_rows}")
        cols = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        tables[name] = {"columns": cols, "rows": rows}
    cursor.close()
    conn.close()
    return tables


def get_tables_schema(allowed_tables: list[str] | None = None, pool_key: str | None = None):
    meta = _get_metadata(pool_key=pool_key)

    conn = get_connection(pool_key=pool_key)

    cursor = conn.cursor()
    cursor.execute("SHOW TABLES")
    table_names = [row[0] for row in cursor.fetchall()]
    cursor.close()

    normalized_allowed = [str(t).strip().strip("`").lower() for t in (allowed_tables or []) if str(t).strip()]
    if normalized_allowed:
        allowed_set = set(normalized_allowed)
        table_names = [name for name in table_names if str(name).strip().lower() in allowed_set]

    tables = []
    for table_name in table_names:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                column_name,
                data_type,
                column_type,
                is_nullable,
                column_default,
                column_comment,
                ordinal_position
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table_name,),
        )
        columns = []
        for row in cursor.fetchall():
            (
                column_name,
                data_type,
                column_type,
                is_nullable,
                column_default,
                column_comment,
                ordinal_position,
            ) = row

            col_key = f"{table_name}.{column_name}"
            description = meta["columns"].get(col_key) or (column_comment or "").strip() or _fallback_column_description(column_name)

            columns.append({
                "name": column_name,
                "data_type": data_type,
                "full_type": column_type,
                "nullable": is_nullable == "YES",
                "default": column_default,
                "description": description,
                "position": ordinal_position,
            })
        cursor.close()

        cursor_count = conn.cursor()
        cursor_count.execute(f"SELECT COUNT(*) FROM `{table_name}`")
        row_count = cursor_count.fetchone()[0]
        cursor_count.close()

        tables.append({
            "name": table_name,
            "description": meta["tables"].get(table_name, ""),
            "column_count": len(columns),
            "row_count": row_count,
            "columns": columns,
        })

    conn.close()
    return tables
