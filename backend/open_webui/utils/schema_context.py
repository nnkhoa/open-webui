"""AI4BI: preload DB metadata vào system prompt mỗi chat.

Theo cấu hình TOOL_SERVER_CONNECTIONS trong Admin → Tool Servers,
module này tự discover các DBHub MCP đang BẬT, gọi `search_objects` để
tìm các bảng `_meta_*` trong mọi schema, query chúng, rồi inject toàn
bộ vào system prompt. LLM "thuộc" schema từ message đầu tiên — không
cần gọi list_tables/describe_table khi user hỏi.

Cache key bám theo danh sách URL DBHub → đổi setup DBHub thì cache tự
invalidate ở lần fetch kế.

Env vars:
- AI4BI_SCHEMA_INJECTION  : "true"/"false" (default: true)
- AI4BI_METADATA_TABLE    : Tên bảng metadata cốt lõi (default: _meta_tables)
- AI4BI_METADATA_EXTRA    : Comma-list bảng metadata bổ sung
                             (default: _meta_columns,_meta_kpi,_meta_glossary)
- AI4BI_SCHEMA_TTL        : TTL cache, giây (default: 3600)
- AI4BI_DBHUB_URL_FALLBACK: URL DBHub dùng khi không có TOOL_SERVER_CONNECTIONS
                             (default: rỗng → tắt)
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
METADATA_EXTRA = [
    t.strip()
    for t in os.environ.get(
        'AI4BI_METADATA_EXTRA', '_meta_columns,_meta_kpi,_meta_glossary'
    ).split(',')
    if t.strip()
]
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


def _discover_dbhubs(request) -> list[dict]:
    """Đọc TOOL_SERVER_CONNECTIONS, trả về list DBHub MCP đang enable.

    Mỗi item: {url, name, id}.
    """
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
        info = conn.get('info') or {}
        servers.append({
            'url': url,
            'name': info.get('name') or info.get('id') or url,
            'id': info.get('id') or url,
        })
    return servers


async def _mcp_call(url: str, tool: str, args: dict, timeout: float = 15.0) -> Optional[Any]:
    """Gọi 1 JSON-RPC tools/call tới MCP server."""
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
                        url,
                        tool,
                        resp.status,
                        text[:200],
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
            c.get('text', '')
            for c in content
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


def _extract_schemas(search_result: Any, table_name: str) -> list[str]:
    """Từ kết quả search_objects, trả về list schema có bảng table_name."""
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
    """Discover các schema có _meta_tables, fetch tất cả metadata table.

    Returns: {name, url, schemas: [{schema, tables: {table_name: rows}}]} hoặc None
    """
    url = server['url']

    # B1: tìm các schema chứa METADATA_TABLE
    discovery = await _mcp_call(
        url,
        'search_objects',
        {
            'object_type': 'table',
            'pattern': METADATA_TABLE,
            'detail_level': 'names',
        },
    )
    schemas = _extract_schemas(discovery, METADATA_TABLE)
    if not schemas:
        log.info('schema_context: %s không có bảng %s', url, METADATA_TABLE)
        return None

    # B2: với mỗi schema, fetch METADATA_TABLE + các bảng EXTRA (nếu tồn tại)
    schemas_out = []
    for schema in schemas:
        tables_out: dict[str, Any] = {}
        for table in [METADATA_TABLE, *METADATA_EXTRA]:
            qualified = _qualified(schema, table)
            if not qualified:
                continue
            rows = await _mcp_call(
                url, 'execute_sql', {'sql': f'SELECT * FROM {qualified}'}
            )
            if rows is not None:
                tables_out[table] = rows
        if tables_out:
            schemas_out.append({'schema': schema or 'default', 'tables': tables_out})

    if not schemas_out:
        return None

    return {'name': server['name'], 'url': url, 'schemas': schemas_out}


def _format_combined(server_blocks: list[dict]) -> str:
    """Ghép các fragment thành 1 block lớn cho system prompt."""
    sections = []
    for sb in server_blocks:
        schema_parts = []
        for s in sb['schemas']:
            tables_json = json.dumps(s['tables'], ensure_ascii=False, indent=2)
            schema_parts.append(
                f'### Schema `{s["schema"]}` (DBHub: {sb["name"]})\n```json\n{tables_json}\n```'
            )
        sections.append('\n\n'.join(schema_parts))

    body = '\n\n'.join(sections)

    return (
        '<bi_schema_metadata>\n'
        'Bạn là trợ lý phân tích dữ liệu (BI) cho doanh nghiệp. Dưới đây là '
        'metadata mô tả TOÀN BỘ bảng/cột/KPI/glossary của các database mà bạn '
        'có quyền truy vấn, đã được preload sẵn ngay khi mở phiên chat này. '
        'Hãy dựa vào đây để chọn đúng bảng/cột và sinh SQL — KHÔNG cần gọi '
        'search_objects / list_tables / describe_table khi user hỏi.\n\n'
        f'{body}\n'
        '</bi_schema_metadata>'
    )


def _cache_key(servers: list[dict]) -> str:
    fingerprint = ','.join(sorted(s['url'] for s in servers))
    digest = hashlib.sha256(fingerprint.encode()).hexdigest()[:16]
    return f'ai4bi:schema_block:v2:{digest}'


async def get_schema_block(request=None) -> Optional[str]:
    """Trả về schema block đã preload (cached hoặc fetch). None nếu tắt/không có DBHub."""
    if not ENABLED:
        return None

    servers = _discover_dbhubs(request)
    if not servers:
        return None

    key = _cache_key(servers)
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
        return block


async def warm_schema_cache(request=None) -> None:
    """Fire-and-forget: gọi khi user tạo chat/workspace mới."""
    try:
        await get_schema_block(request)
    except Exception as e:
        log.warning('schema_context: warm-up failed: %s', e)
