"""AI4BI: preload DB metadata into the system prompt of every chat.

Khi user mở chat / workspace mới, hệ thống đọc bảng metadata mô tả các
bảng/cột trong DW một lần qua DBHub MCP, cache lại, rồi prepend vào
system prompt. Các turn sau LLM đã "thuộc" schema, không cần re-đọc.

Env vars:
- AI4BI_SCHEMA_INJECTION  : "true"/"false"  (default: "true")
- AI4BI_DBHUB_URL         : DBHub MCP endpoint (default: http://127.0.0.1:5001/mcp)
- AI4BI_METADATA_TABLE    : Tên bảng metadata (ví dụ: bi_metadata).
                            Không set => tính năng tự tắt im lặng.
- AI4BI_METADATA_SQL      : Override hoàn toàn câu SELECT
                            (default: SELECT * FROM <AI4BI_METADATA_TABLE>)
- AI4BI_SCHEMA_TTL        : TTL cache, giây (default: 3600)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Optional

import aiohttp

log = logging.getLogger(__name__)

ENABLED = os.environ.get('AI4BI_SCHEMA_INJECTION', 'true').lower() == 'true'
DBHUB_URL = os.environ.get('AI4BI_DBHUB_URL', 'http://127.0.0.1:5001/mcp').rstrip('/')
METADATA_TABLE = os.environ.get('AI4BI_METADATA_TABLE', '_meta_tables').strip()
METADATA_SQL_OVERRIDE = os.environ.get('AI4BI_METADATA_SQL', '').strip()
TTL_SECONDS = int(os.environ.get('AI4BI_SCHEMA_TTL', '3600'))

_CACHE_KEY = 'ai4bi:schema_block:v1'
_SAFE_IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$')

_memory_cache: dict[str, tuple[float, str]] = {}
_lock = asyncio.Lock()
_warned_missing_table = False


def _select_sql() -> Optional[str]:
    global _warned_missing_table
    if METADATA_SQL_OVERRIDE:
        return METADATA_SQL_OVERRIDE
    if METADATA_TABLE:
        if not _SAFE_IDENT.match(METADATA_TABLE):
            log.error(
                'schema_context: AI4BI_METADATA_TABLE rejected (unsafe identifier): %r',
                METADATA_TABLE,
            )
            return None
        return f'SELECT * FROM {METADATA_TABLE}'
    if not _warned_missing_table:
        log.info(
            'schema_context: AI4BI_METADATA_TABLE chưa set — schema injection bị tắt.'
        )
        _warned_missing_table = True
    return None


def _redis_from(request) -> Any:
    try:
        return getattr(request.app.state, 'redis', None) if request is not None else None
    except Exception:
        return None


async def get_schema_block(request=None) -> Optional[str]:
    """Trả về schema block (cached hoặc fetch mới). None nếu tắt/lỗi."""
    if not ENABLED:
        return None
    sql = _select_sql()
    if not sql:
        return None

    redis = _redis_from(request)

    if redis is not None:
        try:
            cached = await redis.get(_CACHE_KEY)
            if cached:
                return cached.decode() if isinstance(cached, bytes) else cached
        except Exception as e:
            log.debug('schema_context: redis get failed: %s', e)

    now = time.time()
    entry = _memory_cache.get(_CACHE_KEY)
    if entry and now - entry[0] < TTL_SECONDS:
        return entry[1]

    async with _lock:
        entry = _memory_cache.get(_CACHE_KEY)
        if entry and time.time() - entry[0] < TTL_SECONDS:
            return entry[1]

        block = await _fetch_block(sql)
        if not block:
            return None

        _memory_cache[_CACHE_KEY] = (time.time(), block)
        if redis is not None:
            try:
                await redis.set(_CACHE_KEY, block, ex=TTL_SECONDS)
            except Exception as e:
                log.debug('schema_context: redis set failed: %s', e)
        return block


async def warm_schema_cache(request=None) -> None:
    """Fire-and-forget warm-up. Gọi khi user mở chat/workspace mới."""
    try:
        await get_schema_block(request)
    except Exception as e:
        log.warning('schema_context: warm-up failed: %s', e)


async def _fetch_block(sql: str) -> Optional[str]:
    payload = {
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'tools/call',
        'params': {'name': 'execute_sql', 'arguments': {'sql': sql}},
    }
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/event-stream',
    }
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15), trust_env=True
        ) as session:
            async with session.post(DBHUB_URL, json=payload, headers=headers) as resp:
                text = await resp.text()
                if resp.status != 200:
                    log.warning(
                        'schema_context: DBHub %s -> HTTP %s: %s',
                        DBHUB_URL,
                        resp.status,
                        text[:200],
                    )
                    return None
    except Exception as e:
        log.error('schema_context: DBHub call failed (%s): %s', DBHUB_URL, e)
        return None

    rows = _parse_mcp_response(text)
    if rows is None:
        return None
    return _format_block(rows, sql)


def _parse_mcp_response(text: str) -> Optional[Any]:
    """DBHub có thể trả plain JSON-RPC hoặc SSE-wrapped. Handle cả hai."""
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
        log.error('schema_context: cannot parse DBHub response: %s', text[:200])
        return None
    return _extract_result(obj)


def _extract_result(obj: dict) -> Optional[Any]:
    if not isinstance(obj, dict):
        return None
    if 'error' in obj and obj.get('error'):
        log.warning('schema_context: DBHub error: %s', obj['error'])
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


def _format_block(rows: Any, sql: str) -> str:
    if isinstance(rows, (list, dict)):
        body = json.dumps(rows, ensure_ascii=False, indent=2)
    else:
        body = str(rows)

    return (
        '<bi_schema_metadata>\n'
        'Bạn là trợ lý phân tích dữ liệu (BI). Dưới đây là metadata mô tả '
        'các bảng/cột trong data warehouse, đã được preload sẵn ngay khi mở '
        'phiên chat này. Hãy dựa vào đây để chọn đúng bảng/cột khi sinh SQL — '
        'KHÔNG cần gọi list_tables / describe_table nữa.\n\n'
        f'Nguồn: `{sql}` (DBHub MCP, cached).\n\n'
        f'```json\n{body}\n```\n'
        '</bi_schema_metadata>'
    )
