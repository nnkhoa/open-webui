"""AI4BI: preload mô tả ngắn bảng/cột vào system prompt mỗi chat.

Quy tắc:
- Chỉ inject metadata của các DBHub MCP mà user CÓ access_grants
  (theo principal_id = user.id hoặc group.id của user). Admin bypass.
- Mỗi schema: lấy `_meta_tables` (table_name, description_vi) +
  `_meta_columns` (column_name, data_type, description_vi).
  KHÔNG lấy `_meta_kpi`, `_meta_glossary`, business_context, example_values.

Env vars:
- AI4BI_SCHEMA_INJECTION  : "true"/"false" (default: true)
- AI4BI_METADATA_TABLE    : Tên bảng metadata cốt (default: _meta_tables)
- AI4BI_COLUMNS_TABLE     : Tên bảng metadata cột (default: _meta_columns)
- AI4BI_SCHEMA_TTL        : TTL cache, giây (default: 3600)
- AI4BI_DBHUB_URL_FALLBACK: URL DBHub fallback nếu không có TOOL_SERVER_CONNECTIONS
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from typing import Any, Optional

import aiohttp

log = logging.getLogger(__name__)

ENABLED = os.environ.get('AI4BI_SCHEMA_INJECTION', 'true').lower() == 'true'
METADATA_TABLE = os.environ.get('AI4BI_METADATA_TABLE', '_meta_tables').strip()
COLUMNS_TABLE = os.environ.get('AI4BI_COLUMNS_TABLE', '_meta_columns').strip()
TTL_SECONDS = int(os.environ.get('AI4BI_SCHEMA_TTL', '3600'))
FALLBACK_URL = os.environ.get('AI4BI_DBHUB_URL_FALLBACK', '').rstrip('/')

_SAFE_IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
_memory_cache: dict[str, tuple[float, str]] = {}
_locks: dict[str, asyncio.Lock] = {}


def _lock_for(key: str) -> asyncio.Lock:
    lock = _locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _locks[key] = lock
    return lock


def _redis_from(request) -> Any:
    try:
        return getattr(request.app.state, 'redis', None) if request is not None else None
    except Exception:
        return None


def _user_principal_ids(user) -> set[str]:
    """user.id + tất cả group.id mà user là member."""
    if user is None:
        return set()
    ids: set[str] = set()
    user_id = getattr(user, 'id', None)
    if user_id:
        ids.add(user_id)
    try:
        from open_webui.models.groups import Groups  # lazy import tránh circular
        for g in Groups.get_groups_by_member_id(user_id) or []:
            gid = getattr(g, 'id', None)
            if gid:
                ids.add(gid)
    except Exception as e:
        log.debug('schema_context: cannot fetch user groups: %s', e)
    return ids


def _has_access(conn: dict, user_principal_ids: set[str], user_role: Optional[str]) -> bool:
    # Admin bypass — admin thấy mọi DBHub đã enable
    if user_role == 'admin':
        return True
    grants = conn.get('config', {}).get('access_grants') or []
    if not grants:
        # Không khai báo grant → coi như public (giống behavior của Open WebUI cho tool)
        return True
    grant_ids = {
        g.get('principal_id')
        for g in grants
        if isinstance(g, dict) and g.get('permission') == 'read'
    }
    return bool(user_principal_ids & grant_ids)


def _discover_dbhubs(request, user=None) -> list[dict]:
    """Đọc TOOL_SERVER_CONNECTIONS, filter theo (enable + type=mcp + access_grants)."""
    if request is None:
        if FALLBACK_URL:
            return [{'url': FALLBACK_URL, 'name': 'fallback', 'id': 'fallback'}]
        return []

    try:
        connections = request.app.state.config.TOOL_SERVER_CONNECTIONS or []
    except Exception as e:
        log.debug('schema_context: cannot read TOOL_SERVER_CONNECTIONS: %s', e)
        if FALLBACK_URL:
            return [{'url': FALLBACK_URL, 'name': 'fallback', 'id': 'fallback'}]
        return []

    principal_ids = _user_principal_ids(user)
    user_role = getattr(user, 'role', None) if user is not None else None

    servers = []
    for conn in connections:
        if not isinstance(conn, dict):
            continue
        if not conn.get('config', {}).get('enable'):
            continue
        if conn.get('type', 'openapi') != 'mcp':
            continue
        url = (conn.get('url') or '').rstrip('/')
        if not url:
            continue
        if not _has_access(conn, principal_ids, user_role):
            continue
        info = conn.get('info') or {}
        servers.append({
            'url': url,
            'name': info.get('name') or info.get('id') or url,
            'id': info.get('id') or url,
        })
    return servers


async def _mcp_call(url: str, tool: str, args: dict, timeout: float = 15.0) -> Optional[Any]:
    payload = {
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'tools/call',
        'params': {'name': tool, 'arguments': args},
    }
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/event-stream',
    }
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout), trust_env=True
        ) as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                text = await resp.text()
                if resp.status != 200:
                    log.warning(
                        'schema_context: %s %s HTTP %s: %s',
                        url, tool, resp.status, text[:200],
                    )
                    return None
    except Exception as e:
        log.warning('schema_context: %s %s failed: %s', url, tool, e)
        return None
    return _parse_mcp_response(text)


def _parse_mcp_response(text: str) -> Optional[Any]:
    if 'data:' in text and ('event:' in text or text.lstrip().startswith('data:')):
        for line in text.splitlines():
            line = line.strip()
            if line.startswith('data:'):
                try:
                    obj = json.loads(line[5:].strip())
                except Exception:
                    continue
                extracted = _extract_result(obj)
                if extracted is not None:
                    return extracted
        return None
    try:
        obj = json.loads(text)
    except Exception:
        return None
    return _extract_result(obj)


def _extract_result(obj: dict) -> Optional[Any]:
    if not isinstance(obj, dict):
        return None
    if obj.get('error'):
        return None
    result = obj.get('result')
    if not result:
        return None
    content = result.get('content') if isinstance(result, dict) else None
    if isinstance(content, list):
        texts = [
            c.get('text', '') for c in content
            if isinstance(c, dict) and c.get('type') == 'text'
        ]
        merged = '\n'.join(t for t in texts if t)
        if merged:
            try:
                return json.loads(merged)
            except Exception:
                return merged
        return result
    return result


def _extract_rows(result: Any) -> list[dict]:
    if not isinstance(result, dict):
        return []
    data = result.get('data')
    if isinstance(data, dict):
        rows = data.get('rows', [])
        return rows if isinstance(rows, list) else []
    return []


def _extract_schemas(search_result: Any, table_name: str) -> list[str]:
    if not search_result:
        return []
    data = search_result.get('data') if isinstance(search_result, dict) else None
    results = data.get('results') if isinstance(data, dict) else None
    if not isinstance(results, list):
        return []
    schemas: list[str] = []
    seen: set[str] = set()
    for r in results:
        if not isinstance(r, dict):
            continue
        if r.get('name') != table_name:
            continue
        schema = r.get('schema') or ''
        if schema in seen:
            continue
        seen.add(schema)
        schemas.append(schema)
    return schemas


def _qualified(schema: str, table: str) -> Optional[str]:
    if not _SAFE_IDENT.match(table):
        return None
    if not schema:
        return table
    if not _SAFE_IDENT.match(schema):
        return None
    return f'{schema}.{table}'


async def _fetch_server(server: dict) -> Optional[dict]:
    """Discover schema, fetch CHỈ tên + mô tả của bảng/cột.

    Returns: {name, url, schemas: [{schema, tables: [(name, desc)], cols: [(table, name, type, desc)]}]}
    """
    url = server['url']

    discovery = await _mcp_call(
        url,
        'search_objects',
        {'object_type': 'table', 'pattern': METADATA_TABLE, 'detail_level': 'names'},
    )
    schemas = _extract_schemas(discovery, METADATA_TABLE)
    if not schemas:
        log.info('schema_context: %s không có bảng %s', url, METADATA_TABLE)
        return None

    schemas_out = []
    for schema in schemas:
        tbl_q = _qualified(schema, METADATA_TABLE)
        if not tbl_q:
            continue

        # Chỉ SELECT các cột cần — không SELECT *
        tables_resp = await _mcp_call(
            url, 'execute_sql',
            {'sql': f'SELECT table_name, description_vi FROM {tbl_q}'},
        )
        tables = [
            (r.get('table_name', ''), (r.get('description_vi') or '').strip())
            for r in _extract_rows(tables_resp)
            if r.get('table_name')
        ]

        col_q = _qualified(schema, COLUMNS_TABLE)
        cols = []
        if col_q:
            cols_resp = await _mcp_call(
                url, 'execute_sql',
                {'sql': f'SELECT table_name, column_name, data_type, description_vi FROM {col_q}'},
            )
            cols = [
                (
                    r.get('table_name', ''),
                    r.get('column_name', ''),
                    (r.get('data_type') or '').strip(),
                    (r.get('description_vi') or '').strip(),
                )
                for r in _extract_rows(cols_resp)
                if r.get('table_name') and r.get('column_name')
            ]

        if not tables and not cols:
            continue
        schemas_out.append({
            'schema': schema or 'default',
            'tables': tables,
            'cols': cols,
        })

    if not schemas_out:
        return None
    return {'name': server['name'], 'url': url, 'schemas': schemas_out}


def _format_combined(server_blocks: list[dict]) -> str:
    sections: list[str] = []
    for sb in server_blocks:
        for s in sb['schemas']:
            lines: list[str] = []
            lines.append(f'## Schema `{s["schema"]}` (DBHub: {sb["name"]})')

            cols_by_table: dict[str, list[tuple]] = {}
            for tname, cname, ctype, cdesc in s.get('cols', []):
                cols_by_table.setdefault(tname, []).append((cname, ctype, cdesc))

            for tname, tdesc in s.get('tables', []):
                # Bỏ qua các bảng metadata khỏi block (tránh self-reference noise)
                if tname.startswith('_meta_'):
                    continue
                header = f'### {tname}'
                if tdesc:
                    header += f' — {tdesc}'
                lines.append('')
                lines.append(header)
                for cname, ctype, cdesc in cols_by_table.get(tname, []):
                    type_part = f' ({ctype.upper()})' if ctype else ''
                    desc_part = f': {cdesc}' if cdesc else ''
                    lines.append(f'- {cname}{type_part}{desc_part}')

            sections.append('\n'.join(lines))

    body = '\n\n'.join(sections)
    return (
        '<bi_schema_metadata>\n'
        'Mô tả ngắn các bảng/cột trong database mà bạn được phép truy vấn '
        '(preload sẵn khi mở chat). Dùng thông tin này để chọn đúng bảng/cột '
        'khi sinh SQL. KHÔNG cần gọi search_objects / list_tables / '
        'describe_table.\n\n'
        f'{body}\n'
        '</bi_schema_metadata>'
    )


def _cache_key(servers: list[dict], user_principal_ids: set[str], user_role: Optional[str]) -> str:
    fp_parts = [','.join(sorted(s['url'] for s in servers))]
    # Admin chia sẻ cache chung; user thường cache theo (servers, groups) — đảm bảo
    # 2 user khác group không lẫn cache.
    if user_role != 'admin':
        fp_parts.append('|'.join(sorted(user_principal_ids)))
    fingerprint = '||'.join(fp_parts)
    digest = hashlib.sha256(fingerprint.encode()).hexdigest()[:16]
    return f'ai4bi:schema_block:v3:{digest}'


async def get_schema_block(request=None, user=None) -> Optional[str]:
    """Trả về schema block (cached/fetch). None nếu tắt/không có DBHub user truy cập được."""
    if not ENABLED:
        return None

    servers = _discover_dbhubs(request, user)
    if not servers:
        return None

    principal_ids = _user_principal_ids(user)
    user_role = getattr(user, 'role', None) if user is not None else None
    key = _cache_key(servers, principal_ids, user_role)
    redis = _redis_from(request)

    if redis is not None:
        try:
            cached = await redis.get(key)
            if cached:
                return cached.decode() if isinstance(cached, bytes) else cached
        except Exception as e:
            log.debug('schema_context: redis get failed: %s', e)

    now = time.time()
    entry = _memory_cache.get(key)
    if entry and now - entry[0] < TTL_SECONDS:
        return entry[1]

    async with _lock_for(key):
        entry = _memory_cache.get(key)
        if entry and time.time() - entry[0] < TTL_SECONDS:
            return entry[1]

        fragments = await asyncio.gather(
            *[_fetch_server(s) for s in servers],
            return_exceptions=True,
        )
        parts = [
            f for f in fragments if isinstance(f, dict) and f.get('schemas')
        ]
        if not parts:
            log.info('schema_context: không server nào trả về metadata')
            return None

        block = _format_combined(parts)
        _memory_cache[key] = (time.time(), block)
        if redis is not None:
            try:
                await redis.set(key, block, ex=TTL_SECONDS)
            except Exception as e:
                log.debug('schema_context: redis set failed: %s', e)

        schema_count = sum(len(p.get('schemas', [])) for p in parts)
        server_names = ', '.join(p.get('name', '?') for p in parts)
        user_label = (
            f'{user_role or "anon"}:{getattr(user, "email", "?")}' if user else 'anon'
        )
        log.info(
            'AI4BI schema injected: %d chars | %d server(s) [%s] | %d schema(s) | user=%s | TTL=%ds',
            len(block), len(parts), server_names, schema_count, user_label, TTL_SECONDS,
        )
        return block


async def warm_schema_cache(request=None, user=None) -> None:
    """Fire-and-forget: gọi khi user tạo chat/workspace mới."""
    try:
        await get_schema_block(request, user)
    except Exception as e:
        log.warning('schema_context: warm-up failed: %s', e)
