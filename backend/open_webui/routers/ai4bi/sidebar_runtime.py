from __future__ import annotations

import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import Request
from sqlalchemy import inspect, text

from open_webui.internal.db import Base, engine, metadata_obj
from open_webui.models.users import UserModel
from open_webui.utils.access_control import has_connection_access
from open_webui.utils.chat import generate_chat_completion
from open_webui.utils.headers import include_user_info_headers
from open_webui.utils.models import get_all_models

from .prompts import DAILY_HEARTBEAT_PROMPT, DAILY_SIGNALS_PROMPT
from open_webui.utils.mcp.client import MCPClient
from open_webui.env import ENABLE_FORWARD_USER_INFO_HEADERS


_CACHE_TTL_SECONDS = 30
_SNAPSHOT_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}

_EXCLUDED_TABLES = {
    "alembic_version",
    "ai4bi_sidebar_signals",
    "ai4bi_sidebar_heartbeat",
}


def _has_dbhub_connection(request: Request) -> bool:
    """
    Sidebar signals/heartbeat should only be generated when DBHub MCP is connected
    (configured by Admin in Settings -> MCP Servers).
    """
    connections = getattr(getattr(request.app.state, "config", None), "TOOL_SERVER_CONNECTIONS", None) or []
    for connection in connections:
        if not isinstance(connection, dict):
            if hasattr(connection, "model_dump"):
                connection = connection.model_dump()
            elif hasattr(connection, "dict"):
                connection = connection.dict()
            else:
                continue
        if connection.get("type", "openapi") != "mcp":
            continue
        if not (connection.get("config") or {}).get("enable", True):
            continue
        # "Listen" to the MCP URL configured in the UI (don't assume port/domain).
        url = str(connection.get("url") or "").strip()
        # `path` may be empty when the URL already includes `/mcp`.
        if url:
            return True
    return False


def _cache_key(user: UserModel, instruction: str) -> str:
    # Cache must be user-scoped because MCP access control can differ per user.
    uid = str(getattr(user, "id", "") or "").strip()
    return f"{uid}:{re.sub(r'\s+', ' ', (instruction or '')).strip().lower()}"


def _get_cached_snapshot(user: UserModel, instruction: str) -> dict[str, Any] | None:
    key = _cache_key(user, instruction)
    cached = _SNAPSHOT_CACHE.get(key)
    if not cached:
        return None
    ts, payload = cached
    if time.time() - ts > _CACHE_TTL_SECONDS:
        _SNAPSHOT_CACHE.pop(key, None)
        return None
    return payload


def _set_cached_snapshot(user: UserModel, instruction: str, payload: dict[str, Any]) -> None:
    _SNAPSHOT_CACHE[_cache_key(user, instruction)] = (time.time(), payload)
    if len(_SNAPSHOT_CACHE) > 64:
        oldest = sorted(_SNAPSHOT_CACHE.items(), key=lambda item: item[1][0])[:16]
        for key, _ in oldest:
            _SNAPSHOT_CACHE.pop(key, None)


def _quote_ident(dialect: str, name: str) -> str:
    if dialect == "mysql":
        return f"`{(name or '').replace('`', '``')}`"
    # default to ANSI / Postgres quoting
    return f"\"{(name or '').replace('\"', '\"\"')}\""


def _qualified_table_name_mcp(dialect: str, schema: str | None, table_name: str) -> str:
    if schema:
        return f"{_quote_ident(dialect, schema)}.{_quote_ident(dialect, table_name)}"
    return _quote_ident(dialect, table_name)


def _mcp_content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        if "text" in content:
            return str(content.get("text") or "")
        return json.dumps(content, ensure_ascii=False)
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if "text" in item:
                    parts.append(str(item.get("text") or ""))
                else:
                    parts.append(json.dumps(item, ensure_ascii=False))
            else:
                parts.append(str(item))
        return "\n".join([p for p in parts if p.strip()])
    return str(content)


def _strip_code_fences(raw: str) -> str:
    text_value = (raw or "").strip()
    if text_value.startswith("```"):
        text_value = text_value.split("\n", 1)[1]
        text_value = text_value.rsplit("```", 1)[0]
    return text_value.strip()


def _mcp_parse_json(raw: str) -> Any:
    candidate = _strip_code_fences(raw)
    if not candidate:
        return None
    # Try to locate a JSON object/array within a longer text.
    match = re.search(r"\{[\s\S]*\}|\[[\s\S]*\]", candidate)
    candidate = match.group(0) if match else candidate
    try:
        return json.loads(candidate)
    except Exception:
        return None


def _parse_markdown_table(text_value: str) -> list[dict[str, Any]]:
    """
    Best-effort parser for markdown tables, e.g.:
    | a | b |
    |---|---|
    | 1 | 2 |
    Returns list[dict] with lowercased header keys.
    """
    lines = [ln.strip() for ln in (text_value or "").splitlines() if ln.strip()]
    if len(lines) < 3:
        return []

    def is_separator(line: str) -> bool:
        if "|" not in line:
            return False
        stripped = line.replace("|", "").strip()
        return bool(stripped) and all(ch in "-: " for ch in stripped)

    for i in range(len(lines) - 2):
        header_line = lines[i]
        sep_line = lines[i + 1]
        if "|" not in header_line:
            continue
        if not is_separator(sep_line):
            continue
        headers = [h.strip() for h in header_line.strip("|").split("|")]
        headers = [h for h in headers if h]
        if not headers:
            continue
        out: list[dict[str, Any]] = []
        for j in range(i + 2, len(lines)):
            row_line = lines[j]
            if "|" not in row_line:
                break
            cells = [c.strip() for c in row_line.strip("|").split("|")]
            if len(cells) < len(headers):
                break
            row = {headers[k].strip().lower(): cells[k] for k in range(len(headers))}
            out.append(row)
        if out:
            return out
    return []


def _parse_psql_table(text_value: str) -> list[dict[str, Any]]:
    """
    Best-effort parser for psql-style tables, e.g.:
      col_a | col_b
    -------+-------
      1    | 2
    (1 row)
    Returns list[dict] with lowercased header keys.
    """
    raw_lines = (text_value or "").splitlines()
    lines = [ln.rstrip("\n") for ln in raw_lines if ln.strip()]
    if len(lines) < 3:
        return []

    def is_separator(line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        # psql uses dashes + plus signs between columns: "-----+-----"
        return all(ch in "-+ " for ch in stripped) and ("-" in stripped)

    for i in range(len(lines) - 2):
        header_line = lines[i]
        sep_line = lines[i + 1]
        if "|" not in header_line:
            continue
        if not is_separator(sep_line):
            continue
        headers = [h.strip() for h in header_line.split("|")]
        headers = [h for h in headers if h]
        if not headers:
            continue

        out: list[dict[str, Any]] = []
        for j in range(i + 2, len(lines)):
            row_line = lines[j]
            if row_line.strip().startswith("(") and "row" in row_line.lower():
                break
            if "|" not in row_line:
                break
            cells = [c.strip() for c in row_line.split("|")]
            if len(cells) < len(headers):
                # Some outputs wrap or are malformed; stop at first mismatch.
                break
            row = {headers[k].strip().lower(): cells[k] for k in range(len(headers))}
            out.append(row)
        if out:
            return out
    return []


def _mcp_extract_payload(content: Any) -> Any:
    """
    Try to extract structured JSON payload from MCP content blocks.
    Supports:
    - {"type":"json","json": ...}
    - {"type":"text","text":"...json..."} or markdown table

    MCP content blocks (dicts with `type` + `text`/`json`) must be decoded BEFORE
    any "is this already a rows payload?" heuristic — otherwise a single text
    block carrying the real JSON gets mistaken for one data row.
    """
    if content is None:
        return None
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("json"), (dict, list)):
                return item.get("json")
            if item.get("type") == "json" and isinstance(item.get("data"), (dict, list)):
                return item.get("data")
            if item.get("type") == "text" and isinstance(item.get("text"), str):
                parsed = _mcp_parse_json(item["text"])
                if parsed is not None:
                    return parsed
                table_rows = _parse_markdown_table(item["text"])
                if table_rows:
                    return table_rows
                table_rows = _parse_psql_table(item["text"])
                if table_rows:
                    return table_rows
    if isinstance(content, dict):
        if isinstance(content.get("json"), (dict, list)):
            return content.get("json")
        if content.get("type") == "text" and isinstance(content.get("text"), str):
            parsed = _mcp_parse_json(content["text"])
            if parsed is not None:
                return parsed
            table_rows = _parse_markdown_table(content["text"])
            if table_rows:
                return table_rows
            table_rows = _parse_psql_table(content["text"])
            if table_rows:
                return table_rows
    # Fallback: payload may already be a rows-shaped dict/list (no MCP wrapping).
    if isinstance(content, (dict, list)):
        rows = _normalize_mcp_rows(content)
        if rows:
            return rows
    return None


def _normalize_mcp_rows(payload: Any) -> list[dict[str, Any]]:
    """
    Normalize common DBHub/MCP execute_sql outputs into a list of dict rows.
    Accepts:
    - list[dict]
    - dict {columns: [...], rows: [[...], ...]}
    - dict {data: [...]}
    - plain JSON string in text form
    """
    if payload is None:
        return []
    if isinstance(payload, list):
        out: list[dict[str, Any]] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            # DBHub often returns column names in UPPERCASE; normalize keys so
            # downstream code can reliably use lower_snake_case lookups.
            out.append({str(k).strip().lower(): v for k, v in row.items()})
        return out
    if isinstance(payload, dict):
        if isinstance(payload.get("data"), list):
            rows = []
            for row in payload["data"]:
                if isinstance(row, dict):
                    rows.append({str(k).strip().lower(): v for k, v in row.items()})
            return rows
        # DBHub wraps results as {success: true, data: {rows: [...], count, source_id}}.
        data = payload.get("data")
        if isinstance(data, dict):
            nested_rows = data.get("rows")
            if isinstance(nested_rows, list):
                return _normalize_mcp_rows(nested_rows)
            nested = _normalize_mcp_rows(data)
            if nested:
                return nested
        cols = payload.get("columns")
        rows = payload.get("rows")
        if isinstance(cols, list) and isinstance(rows, list):
            out: list[dict[str, Any]] = []
            norm_cols = [str(c).strip().lower() for c in cols]
            for r in rows:
                if isinstance(r, (list, tuple)):
                    out.append({norm_cols[i]: r[i] for i in range(min(len(norm_cols), len(r)))})
                elif isinstance(r, dict):
                    out.append({str(k).strip().lower(): v for k, v in r.items()})
            return out
        # Some servers wrap results under `result`.
        if "result" in payload:
            return _normalize_mcp_rows(payload.get("result"))
    # Try to parse if it's a JSON-ish string
    if isinstance(payload, str):
        parsed = _mcp_parse_json(payload)
        return _normalize_mcp_rows(parsed)
    return []


def _parse_connection_headers(connection: dict) -> dict[str, str]:
    headers = connection.get("headers")
    if isinstance(headers, dict):
        return {str(k): str(v) for k, v in headers.items()}
    if isinstance(headers, str) and headers.strip():
        try:
            parsed = json.loads(headers)
            if isinstance(parsed, dict):
                return {str(k): str(v) for k, v in parsed.items()}
        except Exception:
            return {}
    return {}


def _build_mcp_headers(request: Request, connection: dict, user: UserModel) -> dict[str, str]:
    auth_type = str(connection.get("auth_type") or "none")
    headers: dict[str, str] = {}
    if auth_type == "bearer":
        headers["Authorization"] = f"Bearer {connection.get('key', '')}"
    elif auth_type == "session":
        # Match middleware behavior: forward current session token.
        token = getattr(getattr(request, "state", None), "token", None)
        creds = getattr(token, "credentials", "") if token is not None else ""
        if creds:
            headers["Authorization"] = f"Bearer {creds}"
    elif auth_type == "none":
        pass
    # Merge any configured custom headers.
    headers.update(_parse_connection_headers(connection))
    if ENABLE_FORWARD_USER_INFO_HEADERS and user:
        headers = include_user_info_headers(headers, user)
    return headers


def _mcp_effective_url(connection: dict) -> str:
    """
    MCP connections in Open WebUI store `url` (required) and may include a `path`.
    Most deployments include `/mcp` directly in `url`, but handle the case where
    Admin provided base URL + path.
    """
    url = str(connection.get("url") or "").strip()
    path = str(connection.get("path") or "").strip()
    if not url:
        return ""
    if "/mcp" in url:
        return url
    if path and path not in {"openapi.json", "/openapi.json"}:
        if not path.startswith("/"):
            path = "/" + path
        return url.rstrip("/") + path
    return url


def _pick_mcp_connection(request: Request, user: UserModel) -> dict | None:
    """
    Choose a single MCP connection to act as the DBHub bridge.
    Preference: any enabled MCP connection that user can access; if multiple,
    prefer ones whose id/name contains 'dbhub'.
    """
    connections = getattr(getattr(request.app.state, "config", None), "TOOL_SERVER_CONNECTIONS", None) or []
    candidates: list[tuple[int, dict]] = []
    for connection in connections:
        if not isinstance(connection, dict):
            if hasattr(connection, "model_dump"):
                connection = connection.model_dump()
            elif hasattr(connection, "dict"):
                connection = connection.dict()
            else:
                continue
        if connection.get("type", "openapi") != "mcp":
            continue
        if not (connection.get("config") or {}).get("enable", True):
            continue
        url = str(connection.get("url") or "").strip()
        if not url:
            continue
        if not has_connection_access(user, connection):
            continue
        info = connection.get("info") or {}
        name = str(info.get("name") or "").lower()
        cid = str(info.get("id") or "").lower()
        score = 0
        if "dbhub" in name or "dbhub" in cid:
            score += 10
        candidates.append((score, connection))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _list_mcp_connections(request: Request, user: UserModel) -> list[dict]:
    connections = getattr(getattr(request.app.state, "config", None), "TOOL_SERVER_CONNECTIONS", None) or []
    candidates: list[tuple[int, dict]] = []
    for connection in connections:
        if not isinstance(connection, dict):
            if hasattr(connection, "model_dump"):
                connection = connection.model_dump()
            elif hasattr(connection, "dict"):
                connection = connection.dict()
            else:
                continue
        if connection.get("type", "openapi") != "mcp":
            continue
        if not (connection.get("config") or {}).get("enable", True):
            continue
        url = str(connection.get("url") or "").strip()
        if not url:
            continue
        if not has_connection_access(user, connection):
            continue
        info = connection.get("info") or {}
        name = str(info.get("name") or "").lower()
        cid = str(info.get("id") or "").lower()
        score = 0
        if "dbhub" in name or "dbhub" in cid:
            score += 10
        candidates.append((score, connection))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return [c for _, c in candidates]


async def _mcp_execute_sql(
    client: MCPClient,
    tool_name: str,
    sql: str,
) -> list[dict[str, Any]]:
    result_content = await client.call_tool(tool_name, {"sql": sql})
    # `result_content` is MCP "content" blocks; servers vary in how they encode rows.
    extracted = _mcp_extract_payload(result_content)
    if extracted is not None:
        return _normalize_mcp_rows(extracted)

    raw_text = _mcp_content_to_text(result_content)
    parsed = _mcp_parse_json(raw_text)
    if parsed is not None:
        return _normalize_mcp_rows(parsed)

    table_rows = _parse_markdown_table(raw_text)
    if table_rows:
        return _normalize_mcp_rows(table_rows)
    table_rows = _parse_psql_table(raw_text)
    if table_rows:
        return _normalize_mcp_rows(table_rows)
    return []


async def _detect_mcp_dialect(client: MCPClient, tool_name: str) -> str:
    # Best-effort: try a few lightweight probes.
    probes = [
        ("postgres", "SELECT current_database() AS db;"),
        ("mysql", "SELECT DATABASE() AS db;"),
        ("sqlite", "SELECT sqlite_version() AS ver;"),
    ]
    for dialect, sql in probes:
        try:
            rows = await _mcp_execute_sql(client, tool_name, sql)
            if rows:
                return dialect
        except Exception:
            continue
    return "postgres"


async def _mcp_current_database(dialect: str, client: MCPClient, tool_name: str) -> str:
    """
    Best-effort: return current database/catalog name for troubleshooting.
    """
    sql = None
    if dialect == "mysql":
        sql = "SELECT DATABASE() AS db;"
    elif dialect == "sqlite":
        return ""
    else:
        sql = "SELECT current_database() AS db;"
    try:
        rows = await _mcp_execute_sql(client, tool_name, sql)
        if not rows:
            return ""
        return str((rows[0] or {}).get("db") or "").strip()
    except Exception:
        return ""

def _sql_string_literal(value: str) -> str:
    return "'" + str(value or "").replace("'", "''") + "'"


def _sql_date_literal(dialect: str, value: date) -> str:
    iso = value.isoformat()
    if dialect == "postgres":
        return f"DATE {_sql_string_literal(iso)}"
    return _sql_string_literal(iso)


def _pick_execute_sql_tool(tool_specs: Any) -> str | None:
    """
    DBHub MCP exposes `execute_sql` in our setup docs. Keep this flexible by
    choosing the first SQL-execution-looking tool if names differ.
    """
    specs = tool_specs or []
    if isinstance(specs, dict) and isinstance(specs.get("tools"), list):
        specs = specs["tools"]
    if not isinstance(specs, list):
        return None
    names = []
    for spec in specs:
        if isinstance(spec, dict):
            n = str(spec.get("name") or "").strip()
            if n:
                names.append(n)
    for preferred in ("execute_sql", "run_sql", "query", "execute", "sql"):
        for n in names:
            if n.lower() == preferred:
                return n
    for n in names:
        ln = n.lower()
        if "sql" in ln and ("exec" in ln or "query" in ln or "run" in ln):
            return n
    return names[0] if names else None


def _pick_search_objects_tool(tool_specs: Any) -> str | None:
    specs = tool_specs or []
    if isinstance(specs, dict) and isinstance(specs.get("tools"), list):
        specs = specs["tools"]
    if not isinstance(specs, list):
        return None
    names: list[str] = []
    for spec in specs:
        if isinstance(spec, dict):
            n = str(spec.get("name") or "").strip()
            if n:
                names.append(n)
    for preferred in ("search_objects", "search", "list_objects", "objects"):
        for n in names:
            if n.lower() == preferred:
                return n
    for n in names:
        ln = n.lower()
        if "search" in ln and ("object" in ln or "schema" in ln or "table" in ln):
            return n
    return None


async def _mcp_search_objects_tables(client: MCPClient, tool_name: str) -> list[dict[str, Any]]:
    """
    Best-effort: call a DBHub-like `search_objects` tool to list accessible tables.
    Tool schemas vary, so we try a few common argument shapes.
    """
    attempts: list[dict[str, Any]] = [
        {},
        {"query": ""},
        {"q": ""},
        {"text": ""},
        {"keyword": ""},
        {"search": ""},
        {"limit": 200},
        {"query": "", "limit": 200},
        {"q": "", "limit": 200},
        {"type": "table", "limit": 200},
        {"query": "", "type": "table", "limit": 200},
    ]
    last_error: Exception | None = None
    for args in attempts:
        try:
            result_content = await client.call_tool(tool_name, args)
            extracted = _mcp_extract_payload(result_content)
            payload = extracted if extracted is not None else result_content
            rows = _normalize_mcp_rows(payload)
            tables: list[dict[str, Any]] = []
            for row in rows or []:
                if not isinstance(row, dict):
                    continue
                raw_name = str(
                    row.get("table_name")
                    or row.get("name")
                    or row.get("table")
                    or row.get("object_name")
                    or row.get("object")
                    or ""
                ).strip()
                if not raw_name:
                    continue
                schema = str(row.get("table_schema") or row.get("schema") or "").strip()
                table_name = raw_name
                if "." in raw_name and not schema:
                    left, right = raw_name.split(".", 1)
                    if left and right:
                        schema, table_name = left, right
                row_count_raw = (
                    row.get("row_count")
                    or row.get("rows")
                    or row.get("rowcount")
                    or row.get("so_dong")  # sometimes returned by local wrappers
                    or 0
                )
                try:
                    row_count = int(str(row_count_raw).strip()) if str(row_count_raw).strip() not in {"-", ""} else 0
                except Exception:
                    row_count = 0
                tables.append(
                    {
                        "table_schema": schema or None,
                        "table_name": table_name,
                        "row_count": row_count,
                    }
                )
            if tables:
                return tables
        except Exception as error:
            last_error = error
            continue
    # If the tool exists but all attempts failed, propagate a hint via logs by raising.
    if last_error:
        raise last_error
    return []


async def _mcp_list_candidate_tables(
    dialect: str, client: MCPClient, tool_name: str, limit: int = 50
) -> list[dict[str, Any]]:
    if dialect == "mysql":
        sql = f"""
        SELECT
          table_schema,
          table_name,
          COALESCE(table_rows, 0) AS row_count
        FROM information_schema.tables
        WHERE table_type = 'BASE TABLE'
          AND table_schema = DATABASE()
        ORDER BY row_count DESC, table_name ASC
        LIMIT {int(limit)}
        """
    elif dialect == "sqlite":
        sql = """
        SELECT NULL AS table_schema, name AS table_name, 0 AS row_count
        FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name ASC
        """
    else:  # postgres default
        # Prefer information_schema for broader compatibility with DBHub RBAC layers
        # (some setups block direct pg_catalog/pg_class access).
        sql = f"""
        SELECT
          table_schema,
          table_name,
          0 AS row_count
        FROM information_schema.tables
        WHERE table_type = 'BASE TABLE'
          AND table_schema NOT IN ('pg_catalog', 'information_schema')
        ORDER BY table_schema ASC, table_name ASC
        LIMIT {int(limit)}
        """
    return await _mcp_execute_sql(client, tool_name, sql)


async def _mcp_get_columns(
    dialect: str,
    client: MCPClient,
    tool_name: str,
    schema: str | None,
    table_name: str,
) -> tuple[list[dict[str, Any]], str | None]:
    if dialect == "mysql":
        sql = f"""
        SELECT
          column_name,
          data_type,
          column_type,
          is_nullable,
          column_default,
          ordinal_position,
          column_comment
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = {_sql_string_literal(table_name)}
        ORDER BY ordinal_position ASC
        """
    elif dialect == "sqlite":
        # pragma_table_info returns: cid, name, type, notnull, dflt_value, pk
        sql = f"PRAGMA table_info({_sql_string_literal(table_name)});"
    else:
        # Postgres (default): do not assume schema="public". If schema is not known,
        # search all non-system schemas for the table name.
        schema_filter = ""
        if schema:
            schema_filter = f" AND table_schema = {_sql_string_literal(schema)}"
        sql = f"""
        SELECT
          table_schema,
          column_name,
          data_type,
          udt_name,
          is_nullable,
          column_default,
          ordinal_position
        FROM information_schema.columns
        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
          AND table_name = {_sql_string_literal(table_name)}
          {schema_filter}
        ORDER BY table_schema ASC, ordinal_position ASC
        """

    rows = await _mcp_execute_sql(client, tool_name, sql)
    columns: list[dict[str, Any]] = []
    resolved_schema: str | None = schema or None
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if dialect == "sqlite":
            name = str(row.get("name") or "").strip()
            full_type = str(row.get("type") or "").strip()
            data_type = _normalize_type(full_type)
            nullable = not bool(row.get("notnull") or 0)
            default = row.get("dflt_value")
            description = f"Mo ta du lieu cua cot `{name}`."
        else:
            name = str(row.get("column_name") or "").strip()
            if dialect not in {"mysql", "sqlite"}:
                s = str(row.get("table_schema") or "").strip()
                if resolved_schema is None and s:
                    resolved_schema = s
                # If we had to search across schemas, keep only the first schema we found.
                if resolved_schema is not None and s and s != resolved_schema:
                    continue
            full_type = str(row.get("column_type") or row.get("udt_name") or row.get("data_type") or "").strip()
            data_type = _normalize_type(row.get("data_type") or full_type)
            nullable = str(row.get("is_nullable") or "YES").upper() == "YES"
            default = row.get("column_default")
            comment = str(row.get("column_comment") or "").strip()
            description = comment or f"Mo ta du lieu cua cot `{name}`."
        if not name:
            continue
        columns.append(
            {
                "name": name,
                "data_type": data_type,
                "full_type": full_type,
                "nullable": bool(nullable),
                "default": default,
                "description": description,
                "position": len(columns) + 1,
            }
        )
    return columns, resolved_schema


def _is_excluded_table_name(table_name: str) -> bool:
    name = (table_name or "").strip()
    if not name:
        return True
    if name in _EXCLUDED_TABLES:
        return True
    # Exclude Open WebUI system tables if they exist in the DBHub database.
    if name in _internal_table_names():
        return True
    if name.startswith("sqlite_"):
        return True
    return False


async def _mcp_pick_anchor_table(
    dialect: str,
    client: MCPClient,
    tool_name: str,
    search_tool_name: str | None = None,
) -> tuple[dict[str, Any] | None, dict[str, int]]:
    """
    Pick a "business" table to anchor signals/heartbeat.
    Returns: (anchor_table | None, meta)
    meta includes counts to improve UI error messages.
    """
    tables = await _mcp_list_candidate_tables(dialect, client, tool_name, limit=600)
    meta: dict[str, int] = {"total": 0, "excluded": 0, "non_excluded": 0, "column_errors": 0}
    meta["total"] = len(tables or [])
    if not tables:
        if search_tool_name:
            try:
                tables = await _mcp_search_objects_tables(client, search_tool_name)
            except Exception:
                tables = []
            meta["total"] = len(tables or [])
        if not tables:
            # Fallback: some MCP servers expose accessible tables via resources rather than SQL catalogs.
            try:
                resources = await client.list_resources()
            except Exception:
                resources = []
            inferred: list[dict[str, Any]] = []
            for res in resources or []:
                if not isinstance(res, dict):
                    continue
                name = str(res.get("name") or "").strip()
                uri = str(res.get("uri") or "").strip()
                raw = name or uri
                if not raw:
                    continue
                # Heuristic: accept `schema.table` or `table`-like identifiers
                raw = raw.replace("\\", "/").strip()
                raw = raw.split("/")[-1]
                if not raw or raw.lower() in {"schema", "tables"}:
                    continue
                if "." in raw:
                    schema, table_name = raw.split(".", 1)
                else:
                    schema, table_name = "", raw
                if _is_excluded_table_name(table_name):
                    continue
                inferred.append({"table_schema": schema or None, "table_name": table_name, "row_count": 0})
                if len(inferred) >= 60:
                    break
            tables = inferred
            meta["total"] = len(tables or [])
    candidates: list[tuple[int, dict[str, Any]]] = []

    # We might have lots of Open WebUI system tables; scan enough names to find at least one
    # non-internal business table without issuing too many column queries.
    max_non_excluded_to_profile = 200
    for table in tables or []:
        schema = str(table.get("table_schema") or "").strip() if isinstance(table, dict) else ""
        name = str(table.get("table_name") or "").strip() if isinstance(table, dict) else ""
        if _is_excluded_table_name(name):
            meta["excluded"] += 1
            continue
        meta["non_excluded"] += 1
        if meta["non_excluded"] > max_non_excluded_to_profile:
            break
        try:
            columns, resolved_schema = await _mcp_get_columns(dialect, client, tool_name, schema or None, name)
            if not schema and resolved_schema:
                schema = resolved_schema
        except Exception:
            meta["column_errors"] += 1
            continue
        has_date = any(col.get("data_type") in {"date", "datetime", "timestamp"} for col in columns)

        def _looks_like_id(col_name: str) -> bool:
            lowered = (col_name or "").strip().lower()
            return lowered == "id" or lowered.endswith("_id") or "uuid" in lowered

        # Rank tables by *real* analytics payload, not surface-level "has a number" — an
        # FK-only table like `customers` would otherwise tie with one carrying price/amount.
        real_numeric_cols = [
            col for col in columns
            if col.get("data_type") in {"int", "decimal", "float", "double"}
            and not _looks_like_id(str(col.get("name") or ""))
        ]
        text_dim_cols = [
            col for col in columns
            if str(col.get("data_type") or "").lower() in {"varchar", "char", "text"}
            and not _looks_like_id(str(col.get("name") or ""))
        ]
        score = 0
        if has_date:
            score += 5
        score += min(len(real_numeric_cols) * 4, 20)
        score += min(len(text_dim_cols) * 2, 8)
        try:
            row_count = int(table.get("row_count") or 0)
        except Exception:
            row_count = 0
        score += min(row_count // 100, 10)
        candidates.append(
            (
                score,
                {
                    "schema": schema or None,
                    "name": name,
                    "row_count": row_count,
                    "columns": columns,
                },
            )
        )
    if not candidates:
        return None, meta
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1], meta


async def _mcp_pick_best_date_column(
    dialect: str,
    client: MCPClient,
    tool_name: str,
    schema: str | None,
    table_name: str,
    columns: list[dict[str, Any]],
) -> str | None:
    candidates = [
        str(c.get("name") or "")
        for c in columns
        if c.get("data_type") in {"date", "datetime", "timestamp"} and str(c.get("name") or "")
    ]
    if not candidates:
        return None
    candidates = candidates[:12]
    exprs: list[str] = []
    for idx, col in enumerate(candidates):
        qcol = _quote_ident(dialect, col)
        exprs.append(f"COUNT({qcol}) AS n{idx}")
        exprs.append(f"MAX({qcol}) AS m{idx}")
    qtable = _qualified_table_name_mcp(dialect, schema, table_name)
    row = (await _mcp_execute_sql(client, tool_name, f"SELECT {', '.join(exprs)} FROM {qtable}"))[0]
    best_col = candidates[0]
    best_key = (0, date.min)
    for idx, col in enumerate(candidates):
        try:
            n = int(row.get(f"n{idx}") or 0)
        except Exception:
            n = 0
        mx = _as_date(row.get(f"m{idx}")) or date.min
        key = (n, mx)
        if key > best_key:
            best_key = key
            best_col = col
    return best_col


async def _mcp_detect_as_of(
    dialect: str,
    client: MCPClient,
    tool_name: str,
    schema: str | None,
    table_name: str,
    date_column: str | None,
) -> date:
    if not date_column:
        return datetime.utcnow().date()
    qtable = _qualified_table_name_mcp(dialect, schema, table_name)
    qcol = _quote_ident(dialect, date_column)
    rows = await _mcp_execute_sql(client, tool_name, f"SELECT MAX({qcol}) AS max_d FROM {qtable}")
    if not rows:
        return datetime.utcnow().date()
    d = _as_date((rows[0] or {}).get("max_d"))
    return d or datetime.utcnow().date()


async def _mcp_pick_metric_columns(
    dialect: str,
    client: MCPClient,
    tool_name: str,
    schema: str | None,
    table_name: str,
    date_column: str | None,
    columns: list[dict[str, Any]],
    as_of: date,
    max_n: int = 2,
) -> list[str]:
    numeric_cols: list[str] = []
    for column in columns:
        if column.get("data_type") not in {"int", "decimal", "float", "double"}:
            continue
        name = str(column.get("name") or "").strip()
        if not name:
            continue
        lowered = name.lower()
        if lowered == "id" or lowered.endswith("_id") or "uuid" in lowered:
            continue
        numeric_cols.append(name)

    if not numeric_cols:
        return []

    max_candidates = 80
    candidates = numeric_cols[:max_candidates]

    qtable = _qualified_table_name_mcp(dialect, schema, table_name)
    scored: list[tuple[float, str]] = []

    if date_column:
        current_start, current_end, previous_start, previous_end = _window_bounds(as_of)
        exprs: list[str] = []
        qdate = _quote_ident(dialect, date_column)
        for idx, col in enumerate(candidates):
            qcol = _quote_ident(dialect, col)
            exprs.append(
                "COALESCE(SUM(CASE WHEN "
                f"{qdate} >= {_sql_date_literal(dialect, current_start)} AND {qdate} < {_sql_date_literal(dialect, current_end)} "
                f"THEN {qcol} ELSE 0 END), 0) AS c{idx}"
            )
            exprs.append(
                "COALESCE(SUM(CASE WHEN "
                f"{qdate} >= {_sql_date_literal(dialect, previous_start)} AND {qdate} < {_sql_date_literal(dialect, previous_end)} "
                f"THEN {qcol} ELSE 0 END), 0) AS p{idx}"
            )

        rows = await _mcp_execute_sql(client, tool_name, f"SELECT {', '.join(exprs)} FROM {qtable}")
        row = rows[0] if rows else {}
        for idx, col in enumerate(candidates):
            curr = float((row or {}).get(f"c{idx}") or 0)
            prev = float((row or {}).get(f"p{idx}") or 0)
            delta = curr - prev
            score = abs(delta / prev) if prev not in (0.0, None) else abs(delta)
            scored.append((float(score), col))
    else:
        exprs = [f"COALESCE(SUM({_quote_ident(dialect, col)}), 0) AS s{idx}" for idx, col in enumerate(candidates)]
        rows = await _mcp_execute_sql(client, tool_name, f"SELECT {', '.join(exprs)} FROM {qtable}")
        row = rows[0] if rows else {}
        for idx, col in enumerate(candidates):
            total = float((row or {}).get(f"s{idx}") or 0)
            scored.append((abs(total), col))

    scored.sort(key=lambda item: item[0], reverse=True)
    selected: list[str] = []
    for _, name in scored:
        if name not in selected:
            selected.append(name)
        if len(selected) >= max_n:
            break
    return selected


async def _mcp_count_distinct_sample(
    dialect: str,
    client: MCPClient,
    tool_name: str,
    schema: str | None,
    table_name: str,
    column_name: str,
    date_column: str | None,
    start: date | None,
    end_excl: date | None,
) -> int | None:
    qtable = _qualified_table_name_mcp(dialect, schema, table_name)
    qcol = _quote_ident(dialect, column_name)
    where_sql = ""
    if date_column and start and end_excl:
        qdate = _quote_ident(dialect, date_column)
        where_sql = (
            f" WHERE {qdate} >= {_sql_date_literal(dialect, start)} AND {qdate} < {_sql_date_literal(dialect, end_excl)}"
        )
    sql = (
        f"SELECT COUNT(DISTINCT x) AS n FROM ("
        f"SELECT {qcol} AS x FROM {qtable}{where_sql} LIMIT 50000"
        f") t"
    )
    try:
        rows = await _mcp_execute_sql(client, tool_name, sql)
        if not rows:
            return None
        return int((rows[0] or {}).get("n") or 0)
    except Exception:
        return None


async def _mcp_pick_dimension_columns(
    dialect: str,
    client: MCPClient,
    tool_name: str,
    schema: str | None,
    table_name: str,
    date_column: str | None,
    columns: list[dict[str, Any]],
    as_of: date,
    max_n: int = 6,
) -> list[str]:
    dims: list[str] = []
    for column in columns:
        dt = str(column.get("data_type") or "").lower()
        name = str(column.get("name") or "").strip()
        lname = name.lower()
        if not name:
            continue
        if dt not in {"varchar", "char", "text"}:
            continue
        if lname.endswith("_id") or lname in {"id", "uuid"} or "uuid" in lname:
            continue
        dims.append(name)

    if not dims:
        return []

    current_start, current_end, _, _ = _window_bounds(as_of)
    candidates = dims[:25]
    scored: list[tuple[float, str]] = []
    for name in candidates:
        distinct = await _mcp_count_distinct_sample(
            dialect,
            client,
            tool_name,
            schema,
            table_name,
            name,
            date_column,
            current_start if date_column else None,
            current_end if date_column else None,
        )
        if distinct is None:
            continue
        if distinct < 2 or distinct > 200:
            continue
        score = 100.0 - abs(float(distinct) - 10.0)
        scored.append((score, name))

    if scored:
        scored.sort(key=lambda item: item[0], reverse=True)
        out: list[str] = []
        for _, name in scored:
            if name not in out:
                out.append(name)
            if len(out) >= max_n:
                break
        return out

    return dims[:max_n]


async def _mcp_compute_metrics(
    dialect: str,
    client: MCPClient,
    tool_name: str,
    schema: str | None,
    table_name: str,
    date_column: str | None,
    metric_columns: list[str],
    dimension_columns: list[str],
    as_of: date,
) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    current_start, current_end, previous_start, previous_end = _window_bounds(as_of)
    qtable = _qualified_table_name_mcp(dialect, schema, table_name)

    # Volume (count)
    if date_column:
        qdate = _quote_ident(dialect, date_column)
        sql = f"""
        SELECT
          SUM(CASE WHEN {qdate} >= {_sql_date_literal(dialect, current_start)} AND {qdate} < {_sql_date_literal(dialect, current_end)} THEN 1 ELSE 0 END) AS curr,
          SUM(CASE WHEN {qdate} >= {_sql_date_literal(dialect, previous_start)} AND {qdate} < {_sql_date_literal(dialect, previous_end)} THEN 1 ELSE 0 END) AS prev
        FROM {qtable}
        """
        rows = await _mcp_execute_sql(client, tool_name, sql)
        row = rows[0] if rows else {}
        curr = float((row or {}).get("curr") or 0)
        prev = float((row or {}).get("prev") or 0)
        metrics.append(
            {
                "metric": "count_rows",
                "dimension": "",
                "current": curr,
                "previous": prev,
                "delta": curr - prev,
                "delta_pct": ((curr - prev) / prev) if prev else None,
            }
        )
    else:
        rows = await _mcp_execute_sql(client, tool_name, f"SELECT COUNT(*) AS n FROM {qtable}")
        n = float((rows[0] or {}).get("n") or 0) if rows else 0.0
        metrics.append(
            {
                "metric": "count_rows",
                "dimension": "",
                "current": n,
                "previous": None,
                "delta": None,
                "delta_pct": None,
            }
        )

    # Overall sums
    for metric_name in (metric_columns or [])[:2]:
        qmetric = _quote_ident(dialect, metric_name)
        if date_column:
            qdate = _quote_ident(dialect, date_column)
            sql = f"""
            SELECT
              SUM(CASE WHEN {qdate} >= {_sql_date_literal(dialect, current_start)} AND {qdate} < {_sql_date_literal(dialect, current_end)} THEN {qmetric} ELSE 0 END) AS curr,
              SUM(CASE WHEN {qdate} >= {_sql_date_literal(dialect, previous_start)} AND {qdate} < {_sql_date_literal(dialect, previous_end)} THEN {qmetric} ELSE 0 END) AS prev
            FROM {qtable}
            """
            rows = await _mcp_execute_sql(client, tool_name, sql)
            row = rows[0] if rows else {}
            curr = float((row or {}).get("curr") or 0)
            prev = float((row or {}).get("prev") or 0)
            metrics.append(
                {
                    "metric": metric_name,
                    "dimension": "",
                    "current": curr,
                    "previous": prev,
                    "delta": curr - prev,
                    "delta_pct": ((curr - prev) / prev) if prev else None,
                }
            )
        else:
            rows = await _mcp_execute_sql(client, tool_name, f"SELECT SUM({qmetric}) AS s FROM {qtable}")
            curr = float((rows[0] or {}).get("s") or 0) if rows else 0.0
            metrics.append(
                {
                    "metric": metric_name,
                    "dimension": "",
                    "current": curr,
                    "previous": None,
                    "delta": None,
                    "delta_pct": None,
                }
            )

    # Dimension moves: for EACH metric column, cross with up to 2 usable dimensions.
    # Single-table sidebar needs enough metric variety to feed 8 heartbeat KPIs —
    # only the "primary metric × dims" was computed before.
    if metric_columns and dimension_columns:
        usable_dims: list[str] = []
        for dcol in dimension_columns:
            distinct = await _mcp_count_distinct_sample(
                dialect,
                client,
                tool_name,
                schema,
                table_name,
                dcol,
                date_column,
                current_start if date_column else None,
                current_end if date_column else None,
            )
            if distinct is None:
                continue
            if 2 <= distinct <= 50:
                usable_dims.append(dcol)
            if len(usable_dims) >= 2:
                break

        for mcol in metric_columns[:2]:
            qmetric = _quote_ident(dialect, mcol)
            for dcol in usable_dims:
                qdim = _quote_ident(dialect, dcol)
                # Wrap in subquery so ORDER BY can reference SELECT aliases inside an
                # expression (Postgres/SQLite don't resolve `ABS(curr - prev)` against
                # output aliases otherwise).
                if date_column:
                    qdate = _quote_ident(dialect, date_column)
                    sql = f"""
                    SELECT dimension_value, curr, prev FROM (
                      SELECT
                        COALESCE(CAST({qdim} AS TEXT), '(null)') AS dimension_value,
                        SUM(CASE WHEN {qdate} >= {_sql_date_literal(dialect, current_start)} AND {qdate} < {_sql_date_literal(dialect, current_end)} THEN {qmetric} ELSE 0 END) AS curr,
                        SUM(CASE WHEN {qdate} >= {_sql_date_literal(dialect, previous_start)} AND {qdate} < {_sql_date_literal(dialect, previous_end)} THEN {qmetric} ELSE 0 END) AS prev
                      FROM {qtable}
                      GROUP BY COALESCE(CAST({qdim} AS TEXT), '(null)')
                    ) t
                    ORDER BY ABS(COALESCE(curr,0) - COALESCE(prev,0)) DESC
                    LIMIT 20
                    """
                else:
                    sql = f"""
                    SELECT dimension_value, curr, prev FROM (
                      SELECT
                        COALESCE(CAST({qdim} AS TEXT), '(null)') AS dimension_value,
                        SUM({qmetric}) AS curr,
                        NULL AS prev
                      FROM {qtable}
                      GROUP BY COALESCE(CAST({qdim} AS TEXT), '(null)')
                    ) t
                    ORDER BY ABS(COALESCE(curr,0)) DESC
                    LIMIT 20
                    """
                rows = await _mcp_execute_sql(client, tool_name, sql)
                for row in rows or []:
                    dim_val = str((row or {}).get("dimension_value") or "").strip()
                    curr = float((row or {}).get("curr") or 0)
                    prev_raw = (row or {}).get("prev")
                    prev = float(prev_raw or 0) if prev_raw is not None else None
                    delta = (curr - prev) if prev is not None else None
                    pct = (delta / prev) if (prev not in (None, 0)) else None
                    metrics.append(
                        {
                            "metric": mcol,
                            "dimension": dcol,
                            "dimension_value": dim_val,
                            "current": curr,
                            "previous": prev,
                            "delta": delta,
                            "delta_pct": pct,
                        }
                    )

    return metrics


def _quote(name: str) -> str:
    return engine.dialect.identifier_preparer.quote_identifier(name)


def _qualified_table_name(table_name: str) -> str:
    schema = metadata_obj.schema
    if schema:
        return f"{_quote(schema)}.{_quote(table_name)}"
    return _quote(table_name)


def _normalize_type(raw_type: Any) -> str:
    text_type = str(raw_type or "").lower()
    if "timestamp" in text_type:
        return "timestamp"
    if text_type.startswith("date"):
        return "date"
    if "time" in text_type:
        return "datetime"
    if any(token in text_type for token in ("bigint", "integer", "smallint")):
        return "int"
    if any(token in text_type for token in ("numeric", "decimal")):
        return "decimal"
    if any(token in text_type for token in ("double", "real")):
        return "double"
    if "float" in text_type:
        return "float"
    if any(token in text_type for token in ("varchar", "character varying")):
        return "varchar"
    if any(token in text_type for token in ("char", "character")):
        return "char"
    if any(token in text_type for token in ("text", "json", "jsonb", "uuid")):
        return "text"
    return text_type or "text"


def _internal_table_names() -> set[str]:
    names = set()
    for key in Base.metadata.tables.keys():
        names.add(key.split(".")[-1])
    return names | _EXCLUDED_TABLES


def _business_tables() -> list[dict[str, Any]]:
    schema = metadata_obj.schema
    inspector = inspect(engine)
    internal_tables = _internal_table_names()
    table_names = [
        name
        for name in inspector.get_table_names(schema=schema)
        if name not in internal_tables and not name.startswith("sqlite_")
    ]

    tables: list[dict[str, Any]] = []
    with engine.connect() as conn:
        for table_name in table_names:
            columns_info = inspector.get_columns(table_name, schema=schema)
            columns = []
            for index, column in enumerate(columns_info, start=1):
                columns.append(
                    {
                        "name": column["name"],
                        "data_type": _normalize_type(column.get("type")),
                        "full_type": str(column.get("type") or ""),
                        "nullable": bool(column.get("nullable", True)),
                        "default": column.get("default"),
                        "description": (column.get("comment") or "").strip()
                        or f"Mo ta du lieu cua cot `{column['name']}`.",
                        "position": index,
                    }
                )

            row_count = conn.execute(text(f"SELECT COUNT(*) FROM {_qualified_table_name(table_name)}")).scalar()
            tables.append(
                {
                    "name": table_name,
                    "description": "",
                    "column_count": len(columns),
                    "row_count": int(row_count or 0),
                    "columns": columns,
                }
            )

    tables.sort(key=lambda table: int(table.get("row_count") or 0), reverse=True)
    return tables


def _is_money_metric(metric_name: str) -> bool:
    # Avoid name-token heuristics; without explicit unit metadata from DB,
    # treat all metrics as unitless and let the LLM/UI wording handle currency context.
    return False


def _format_compact_number(value: float, instruction: str = "", money: bool = False) -> str:
    try:
        number = float(value)
    except Exception:
        return str(value)

    absolute = abs(number)
    suffix = ""
    scaled = number
    if absolute >= 1e9:
        scaled = number / 1e9
        suffix = "B"
    elif absolute >= 1e6:
        scaled = number / 1e6
        suffix = "M"
    elif absolute >= 1e3:
        scaled = number / 1e3
        suffix = "K"

    currency = ""
    normalized_instruction = (instruction or "").lower()
    if money and ("vnd" in normalized_instruction or "₫" in normalized_instruction):
        currency = "₫"

    if suffix:
        return f"{scaled:.1f}{suffix}{currency}"
    return f"{scaled:,.0f}{currency}"


def _pick_anchor_table(tables: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates: list[tuple[int, dict[str, Any]]] = []
    for table in tables:
        columns = table.get("columns") or []
        has_date = any(column.get("data_type") in {"date", "datetime", "timestamp"} for column in columns)
        has_numeric = any(column.get("data_type") in {"int", "decimal", "float", "double"} for column in columns)
        score = 0
        if has_date:
            score += 5
        if has_numeric:
            score += 5
        score += min(int(table.get("row_count") or 0) // 1000, 20)
        candidates.append((score, table))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _pick_date_column(columns: list[dict[str, Any]]) -> str | None:
    # Pick any date-like column. Final selection is refined in build_sidebar_snapshot
    # using actual data coverage (non-null counts) to avoid name-based heuristics.
    for column in columns:
        name = str(column.get("name") or "")
        if not name:
            continue
        if column.get("data_type") in {"date", "datetime", "timestamp"}:
            return name
    return None


def _pick_metric_columns(
    table_name: str,
    date_column: str | None,
    columns: list[dict[str, Any]],
    as_of: date,
    max_n: int = 2,
) -> list[str]:
    """
    Choose metric columns purely from DB schema + values (no name-token heuristics).
    Strategy:
    - Consider all numeric columns (excluding obvious id-like columns).
    - Rank by strongest absolute change between current vs previous window (7d vs 7d).
    - Fallback to absolute sum magnitude if no date column.
    """
    numeric_cols: list[str] = []
    for column in columns:
        if column.get("data_type") not in {"int", "decimal", "float", "double"}:
            continue
        name = str(column.get("name") or "")
        if not name:
            continue
        lowered = name.lower()
        if lowered == "id" or lowered.endswith("_id"):
            continue
        numeric_cols.append(name)

    if not numeric_cols:
        return []

    # Avoid generating a massive query; still consider many columns but cap to keep response time sane.
    # This is schema-driven (not domain-driven) and based only on what exists in the DB.
    max_candidates = 80
    candidates = numeric_cols[:max_candidates]

    scored: list[tuple[float, str]] = []
    with engine.connect() as conn:
        if date_column:
            current_start, current_end, previous_start, previous_end = _window_bounds(as_of)

            exprs: list[str] = []
            params: dict[str, Any] = {
                "current_start": current_start,
                "current_end": current_end,
                "previous_start": previous_start,
                "previous_end": previous_end,
            }

            for idx, col in enumerate(candidates):
                exprs.append(
                    f"COALESCE(SUM(CASE WHEN {_quote(date_column)} >= :current_start AND {_quote(date_column)} < :current_end THEN {_quote(col)} ELSE 0 END), 0) AS c{idx}"
                )
                exprs.append(
                    f"COALESCE(SUM(CASE WHEN {_quote(date_column)} >= :previous_start AND {_quote(date_column)} < :previous_end THEN {_quote(col)} ELSE 0 END), 0) AS p{idx}"
                )

            query = text(f"SELECT {', '.join(exprs)} FROM {_qualified_table_name(table_name)}")
            row = conn.execute(query, params).mappings().first() or {}

            for idx, col in enumerate(candidates):
                curr = float(row.get(f"c{idx}") or 0)
                prev = float(row.get(f"p{idx}") or 0)
                delta = curr - prev
                # Prefer percentage change when prev != 0; else fallback to absolute delta.
                score = abs(delta / prev) if prev not in (0.0, None) else abs(delta)
                scored.append((float(score), col))
        else:
            exprs = [f"COALESCE(SUM({_quote(col)}), 0) AS s{idx}" for idx, col in enumerate(candidates)]
            query = text(f"SELECT {', '.join(exprs)} FROM {_qualified_table_name(table_name)}")
            row = conn.execute(query).mappings().first() or {}
            for idx, col in enumerate(candidates):
                total = float(row.get(f"s{idx}") or 0)
                scored.append((abs(total), col))

    scored.sort(key=lambda item: item[0], reverse=True)
    selected: list[str] = []
    for _, name in scored:
        if name not in selected:
            selected.append(name)
        if len(selected) >= max_n:
            break
    return selected


def _pick_dimension_columns(
    table_name: str,
    date_column: str | None,
    columns: list[dict[str, Any]],
    as_of: date,
    max_n: int = 2,
) -> list[str]:
    """
    Pick dimension columns purely based on DB schema + cardinality (no name-token heuristics).
    Prefer low/medium-cardinality text columns.
    """
    text_cols: list[str] = []
    for column in columns:
        data_type = str(column.get("data_type") or "")
        name = str(column.get("name") or "")
        if not name:
            continue
        lowered = name.lower()
        if data_type not in {"varchar", "char", "text"}:
            continue
        if lowered == "id" or lowered.endswith("_id") or "uuid" in lowered:
            continue
        text_cols.append(name)

    if not text_cols:
        return []

    current_start, current_end, _, _ = _window_bounds(as_of)
    ranked: list[tuple[int, str]] = []
    for col in text_cols[:120]:
        n = _count_distinct_sample(
            table_name,
            col,
            date_column,
            current_start if date_column else None,
            current_end if date_column else None,
        )
        if n is None:
            continue
        # Keep a reasonable range so the sidebar doesn't explode into noisy segments.
        if 2 <= int(n) <= 50:
            ranked.append((int(n), col))

    # Prefer smaller cardinality (more readable breakdowns).
    ranked.sort(key=lambda item: item[0])
    selected: list[str] = []
    for _, col in ranked:
        if col not in selected:
            selected.append(col)
        if len(selected) >= max_n:
            break
    return selected


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def _detect_as_of(table_name: str, date_column: str | None) -> date:
    if not date_column:
        return datetime.now(timezone.utc).date()

    query = text(f"SELECT MAX({_quote(date_column)}) AS max_d FROM {_qualified_table_name(table_name)}")
    with engine.connect() as conn:
        result = conn.execute(query).scalar()
    return _as_date(result) or datetime.now(timezone.utc).date()


def _window_bounds(as_of: date) -> tuple[date, date, date, date]:
    current_end = as_of + timedelta(days=1)
    current_start = as_of - timedelta(days=6)
    previous_end = current_start
    previous_start = current_start - timedelta(days=7)
    return current_start, current_end, previous_start, previous_end


def _count_distinct_sample(
    table_name: str,
    column_name: str,
    date_column: str | None,
    start: date | None,
    end_exclusive: date | None,
) -> int | None:
    params: dict[str, Any] = {}
    query = f"SELECT COUNT(DISTINCT x) FROM (SELECT {_quote(column_name)} AS x FROM {_qualified_table_name(table_name)}"
    if date_column and start and end_exclusive:
        query += f" WHERE {_quote(date_column)} >= :start AND {_quote(date_column)} < :end_exclusive"
        params["start"] = start
        params["end_exclusive"] = end_exclusive
    query += " LIMIT 50000) AS sampled"

    try:
        with engine.connect() as conn:
            return int(conn.execute(text(query), params).scalar() or 0)
    except Exception:
        return None


def _compute_metrics(
    table_name: str,
    date_column: str | None,
    metric_columns: list[str],
    dimension_columns: list[str],
    as_of: date,
) -> list[dict[str, Any]]:
    current_start, current_end, previous_start, previous_end = _window_bounds(as_of)
    metrics: list[dict[str, Any]] = []

    with engine.connect() as conn:
        if date_column:
            row = (
                conn.execute(
                    text(
                        f"""
                        SELECT
                            SUM(CASE WHEN {_quote(date_column)} >= :current_start AND {_quote(date_column)} < :current_end THEN 1 ELSE 0 END) AS current_value,
                            SUM(CASE WHEN {_quote(date_column)} >= :previous_start AND {_quote(date_column)} < :previous_end THEN 1 ELSE 0 END) AS previous_value
                        FROM {_qualified_table_name(table_name)}
                        """
                    ),
                    {
                        "current_start": current_start,
                        "current_end": current_end,
                        "previous_start": previous_start,
                        "previous_end": previous_end,
                    },
                )
                .mappings()
                .first()
            )
            current_value = float((row or {}).get("current_value") or 0)
            previous_value = float((row or {}).get("previous_value") or 0)
        else:
            current_value = float(
                conn.execute(text(f"SELECT COUNT(*) FROM {_qualified_table_name(table_name)}")).scalar() or 0
            )
            previous_value = 0.0

        metrics.append(
            {
                "metric": "count_rows",
                "dimension": "",
                "current": current_value,
                "previous": previous_value if date_column else None,
                "delta": current_value - previous_value if date_column else None,
                "delta_pct": ((current_value - previous_value) / previous_value) if date_column and previous_value else None,
            }
        )

        for metric_name in metric_columns[:2]:
            if date_column:
                row = (
                    conn.execute(
                        text(
                            f"""
                            SELECT
                                SUM(CASE WHEN {_quote(date_column)} >= :current_start AND {_quote(date_column)} < :current_end THEN {_quote(metric_name)} ELSE 0 END) AS current_value,
                                SUM(CASE WHEN {_quote(date_column)} >= :previous_start AND {_quote(date_column)} < :previous_end THEN {_quote(metric_name)} ELSE 0 END) AS previous_value
                            FROM {_qualified_table_name(table_name)}
                            """
                        ),
                        {
                            "current_start": current_start,
                            "current_end": current_end,
                            "previous_start": previous_start,
                            "previous_end": previous_end,
                        },
                    )
                    .mappings()
                    .first()
                )
                current_value = float((row or {}).get("current_value") or 0)
                previous_value = float((row or {}).get("previous_value") or 0)
                delta = current_value - previous_value
                delta_pct = (delta / previous_value) if previous_value else None
            else:
                current_value = float(
                    conn.execute(
                        text(f"SELECT SUM({_quote(metric_name)}) FROM {_qualified_table_name(table_name)}")
                    ).scalar()
                    or 0
                )
                previous_value = None
                delta = None
                delta_pct = None

            metrics.append(
                {
                    "metric": metric_name,
                    "dimension": "",
                    "current": current_value,
                    "previous": previous_value,
                    "delta": delta,
                    "delta_pct": delta_pct,
                }
            )

        if metric_columns and dimension_columns:
            primary_metric = metric_columns[0]
            usable_dimensions: list[str] = []
            for dimension_name in dimension_columns:
                distinct_count = _count_distinct_sample(
                    table_name,
                    dimension_name,
                    date_column,
                    current_start if date_column else None,
                    current_end if date_column else None,
                )
                if distinct_count is None:
                    continue
                if 2 <= distinct_count <= 50:
                    usable_dimensions.append(dimension_name)
                if len(usable_dimensions) >= 2:
                    break

            for dimension_name in usable_dimensions:
                if date_column:
                    rows = conn.execute(
                        text(
                            f"""
                            SELECT
                                COALESCE(CAST({_quote(dimension_name)} AS TEXT), '(null)') AS dimension_value,
                                SUM(CASE WHEN {_quote(date_column)} >= :current_start AND {_quote(date_column)} < :current_end THEN {_quote(primary_metric)} ELSE 0 END) AS current_value,
                                SUM(CASE WHEN {_quote(date_column)} >= :previous_start AND {_quote(date_column)} < :previous_end THEN {_quote(primary_metric)} ELSE 0 END) AS previous_value
                            FROM {_qualified_table_name(table_name)}
                            GROUP BY COALESCE(CAST({_quote(dimension_name)} AS TEXT), '(null)')
                            ORDER BY ABS(COALESCE(SUM(CASE WHEN {_quote(date_column)} >= :current_start AND {_quote(date_column)} < :current_end THEN {_quote(primary_metric)} ELSE 0 END), 0) - COALESCE(SUM(CASE WHEN {_quote(date_column)} >= :previous_start AND {_quote(date_column)} < :previous_end THEN {_quote(primary_metric)} ELSE 0 END), 0)) DESC
                            LIMIT 20
                            """
                        ),
                        {
                            "current_start": current_start,
                            "current_end": current_end,
                            "previous_start": previous_start,
                            "previous_end": previous_end,
                        },
                    ).mappings()
                else:
                    rows = conn.execute(
                        text(
                            f"""
                            SELECT
                                COALESCE(CAST({_quote(dimension_name)} AS TEXT), '(null)') AS dimension_value,
                                SUM({_quote(primary_metric)}) AS current_value
                            FROM {_qualified_table_name(table_name)}
                            GROUP BY COALESCE(CAST({_quote(dimension_name)} AS TEXT), '(null)')
                            ORDER BY ABS(COALESCE(SUM({_quote(primary_metric)}), 0)) DESC
                            LIMIT 20
                            """
                        )
                    ).mappings()

                for row in rows:
                    current_value = float(row.get("current_value") or 0)
                    previous_value = row.get("previous_value")
                    previous_float = float(previous_value or 0) if previous_value is not None else None
                    delta = (current_value - previous_float) if previous_float is not None else None
                    delta_pct = (delta / previous_float) if previous_float not in (None, 0) else None
                    metrics.append(
                        {
                            "metric": primary_metric,
                            "dimension": dimension_name,
                            "dimension_value": str(row.get("dimension_value") or "").strip(),
                            "current": current_value,
                            "previous": previous_float,
                            "delta": delta,
                            "delta_pct": delta_pct,
                        }
                    )

    return metrics


def _build_signals_input(as_of: date, metrics: list[dict[str, Any]], limit: int) -> dict[str, Any]:
    return {
        "asOf": as_of.isoformat(),
        "n": int(limit),
        "metrics": [
            {
                "metric": item.get("metric"),
                "dimension": item.get("dimension") or "",
                "dimension_value": item.get("dimension_value") or "",
                "current": item.get("current"),
                "previous": item.get("previous"),
                "delta": item.get("delta"),
                "delta_pct": item.get("delta_pct"),
            }
            for item in metrics[:200]
        ],
    }


def _build_heartbeat_input(
    as_of: date,
    metrics: list[dict[str, Any]],
    limit: int,
    instruction: str,
) -> dict[str, Any]:
    cards: list[dict[str, Any]] = []
    for item in metrics:
        metric_name = str(item.get("metric") or "")
        dimension_name = str(item.get("dimension") or "")
        dimension_value = str(item.get("dimension_value") or "")
        label = metric_name
        if dimension_name and dimension_value:
            label = f"{metric_name} • {dimension_value}"

        cards.append(
            {
                "label": label[:32],
                "value": _format_compact_number(
                    float(item.get("current") or 0),
                    instruction=instruction,
                    money=_is_money_metric(metric_name),
                ),
                "delta": (
                    f"{float(item.get('delta_pct')) * 100:+.1f}% so voi ky truoc"
                    if isinstance(item.get("delta_pct"), (int, float))
                    else ""
                ),
                "delta_pct": item.get("delta_pct"),
            }
        )

    cards.sort(
        key=lambda item: abs(float(item.get("delta_pct") or 0)) if isinstance(item.get("delta_pct"), (int, float)) else 0,
        reverse=True,
    )

    return {
        "asOf": as_of.isoformat(),
        "n": int(limit),
        "metrics": cards[: min(50, len(cards))],
    }


def _extract_message_text(response: dict[str, Any]) -> str:
    choices = response.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") in {"text", "output_text"}:
                parts.append(str(item.get("text") or ""))
        return "".join(parts)
    return str(content)


def _parse_json_array(raw_text: str) -> list[dict[str, Any]]:
    text_value = (raw_text or "").strip()
    if text_value.startswith("```"):
        text_value = text_value.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    match = re.search(r"\[[\s\S]*\]", text_value)
    candidate = match.group(0) if match else text_value
    try:
        parsed = json.loads(candidate)
    except Exception:
        return []
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


async def _pick_model_id(request: Request, user: UserModel) -> str:
    await get_all_models(request, refresh=True, user=user)
    models = request.app.state.MODELS or {}

    default_models = [
        item.strip()
        for item in str(getattr(request.app.state.config, "DEFAULT_MODELS", "") or "").split(",")
        if item.strip()
    ]

    for model_id in default_models:
        model = models.get(model_id)
        if model and model.get("owned_by") != "arena":
            return model_id

    for model_id, model in models.items():
        if model.get("owned_by") != "arena":
            return model_id

    raise RuntimeError("No usable model is available in Open WebUI.")


async def _generate_json_payload(
    request: Request,
    user: UserModel,
    system_prompt: str,
    user_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    model_id = await _pick_model_id(request, user)
    response = await generate_chat_completion(
        request,
        {
            "model": model_id,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
        },
        user,
        bypass_filter=True,
        bypass_system_prompt=True,
    )
    return _parse_json_array(_extract_message_text(response))


def _normalize_signals(raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(raw_items, start=1):
        signal_type = str(item.get("type") or "").strip().lower()
        if signal_type not in {"critical", "watch", "positive"}:
            signal_type = "watch"
        title = str(item.get("title") or "").strip()
        description = str(item.get("desc") or item.get("description") or "").strip()
        if not title or not description:
            continue
        normalized.append(
            {
                "id": index,
                "rank": index,
                "type": signal_type,
                "title": title,
                "desc": description,
                "createdAt": datetime.now(timezone.utc).isoformat(),
            }
        )
    return normalized


def _normalize_heartbeat(raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(raw_items, start=1):
        label = str(item.get("label") or "").strip()
        value = str(item.get("value") or "").strip()
        trend = str(item.get("trend") or "neutral").strip().lower()
        if trend not in {"up", "down", "neutral"}:
            trend = "neutral"
        if not label or not value:
            continue
        normalized.append(
            {
                "id": index,
                "rank": index,
                "label": label,
                "value": value,
                "delta": str(item.get("delta") or "").strip(),
                "trend": trend,
                "createdAt": datetime.now(timezone.utc).isoformat(),
            }
        )
    return normalized


async def build_sidebar_snapshot(request: Request, user: UserModel, instruction: str = "") -> dict[str, Any]:
    if not _has_dbhub_connection(request):
        payload = {
            "configured": False,
            "signals": [],
            "heartbeat": [],
            "error": "DBHub MCP chưa được cấu hình (Admin: Settings → MCP Servers).",
        }
        _set_cached_snapshot(user, instruction, payload)
        return payload

    cached = _get_cached_snapshot(user, instruction)
    if cached is not None:
        return cached

    connections = _list_mcp_connections(request, user)
    if not connections:
        payload = {
            "configured": False,
            "signals": [],
            "heartbeat": [],
            "error": "Bạn chưa được cấp quyền truy cập DBHub MCP.",
        }
        _set_cached_snapshot(user, instruction, payload)
        return payload

    metrics: list[dict[str, Any]] = []
    table_name = ""
    as_of = datetime.utcnow().date()
    last_error = ""
    for connection in connections:
        client = MCPClient()
        try:
            headers = _build_mcp_headers(request, connection, user)
            effective_url = _mcp_effective_url(connection)
            if not effective_url:
                continue
            await client.connect(url=effective_url, headers=headers or None)
            tool_specs = await client.list_tool_specs()
            tool_name = _pick_execute_sql_tool(tool_specs)
            if not tool_name:
                last_error = "DBHub MCP không có tool execute_sql."
                continue
            search_tool = _pick_search_objects_tool(tool_specs)

            # Sanity probe: ensure execute_sql returns parseable rows.
            try:
                probe = await _mcp_execute_sql(client, tool_name, "SELECT 1 AS ok;")
            except Exception as error:
                last_error = str(error) or "DBHub execute_sql lỗi."
                continue
            if not probe:
                last_error = (
                    "DBHub execute_sql không trả về kết quả (không parse được output). "
                    "Kiểm tra tool Inline Visualizer xem DBHub trả về dạng markdown/text hay json."
                )
                continue

            dialect = await _detect_mcp_dialect(client, tool_name)
            db_name = await _mcp_current_database(dialect, client, tool_name)
            anchor_table, anchor_meta = await _mcp_pick_anchor_table(dialect, client, tool_name, search_tool_name=search_tool)
            if not anchor_table:
                total = int((anchor_meta or {}).get("total") or 0)
                non_excl = int((anchor_meta or {}).get("non_excluded") or 0)
                col_errors = int((anchor_meta or {}).get("column_errors") or 0)
                if total > 0 and non_excl == 0:
                    last_error = (
                        "DBHub đã kết nối nhưng database hiện chỉ có bảng hệ thống của Open WebUI "
                        "(auth/chat/memory/rag/...). Sidebar chỉ sinh dữ liệu khi DBHub trỏ tới database nghiệp vụ "
                        "(ví dụ customers/orders/...)."
                    )
                    if db_name:
                        last_error += f" (DB hiện tại: {db_name})"
                elif non_excl > 0 and col_errors >= non_excl:
                    last_error = (
                        "DBHub nhìn thấy danh sách bảng nhưng không đọc được schema/cột từ information_schema. "
                        "Kiểm tra quyền của DB user (SELECT trên information_schema.columns) hoặc cấu hình DBHub RBAC."
                    )
                    if db_name:
                        last_error += f" (DB hiện tại: {db_name})"
                else:
                    last_error = (
                        "DBHub không liệt kê được bảng dữ liệu hợp lệ. "
                        "Có thể user DB không có quyền xem schema/tables hoặc DBHub đang chặn truy cập catalog."
                    )
                    if db_name:
                        last_error += f" (DB hiện tại: {db_name})"
                continue

            schema = anchor_table.get("schema")
            table_name = str(anchor_table.get("name") or "")
            columns = anchor_table.get("columns") or []

            date_column = await _mcp_pick_best_date_column(dialect, client, tool_name, schema, table_name, columns)
            as_of = await _mcp_detect_as_of(dialect, client, tool_name, schema, table_name, date_column)
            metric_columns = await _mcp_pick_metric_columns(
                dialect, client, tool_name, schema, table_name, date_column, columns, as_of, max_n=2
            )
            dimension_columns = await _mcp_pick_dimension_columns(
                dialect, client, tool_name, schema, table_name, date_column, columns, as_of, max_n=6
            )
            metrics = await _mcp_compute_metrics(
                dialect,
                client,
                tool_name,
                schema,
                table_name,
                date_column,
                metric_columns,
                dimension_columns,
                as_of,
            )
            if metrics:
                break
            last_error = "DBHub có kết nối nhưng không lấy được metric."
        except Exception as error:
            last_error = str(error) or "Không kết nối được DBHub MCP."
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass

    if not metrics:
        payload = {
            "configured": False,
            "signals": [],
            "heartbeat": [],
            "error": last_error or "Chưa có thông tin.",
        }
        _set_cached_snapshot(user, instruction, payload)
        return payload

    signal_payload = _build_signals_input(as_of, metrics, 5)
    heartbeat_payload = _build_heartbeat_input(as_of, metrics, 8, instruction)

    signals = _normalize_signals(await _generate_json_payload(request, user, DAILY_SIGNALS_PROMPT, signal_payload))
    heartbeat = _normalize_heartbeat(
        await _generate_json_payload(request, user, DAILY_HEARTBEAT_PROMPT, heartbeat_payload)
    )

    payload = {
        "configured": True,
        "signals": signals,
        "heartbeat": heartbeat,
        "table": table_name,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "error": "",
    }
    _set_cached_snapshot(user, instruction, payload)
    return payload
