from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Query, Request

from open_webui.models.ai4bi_sidebar import sidebar_cache
from open_webui.models.users import UserModel
from open_webui.utils.auth import get_verified_user

from .sidebar_runtime import (
    PERSISTENT_CACHE_TTL_SECONDS,
    _pick_mcp_connection,
    connection_cache_key,
    is_generating,
    schedule_regenerate,
)


router = APIRouter()


def _empty_response(offset: int, error: str = '', is_configured: bool = False, is_generating_flag: bool = False) -> dict:
    return {
        'items': [],
        'total': 0,
        'offset': offset,
        'nextOffset': offset,
        'hasMore': False,
        'isConfigured': is_configured,
        'isGenerating': is_generating_flag,
        'error': error,
    }


@router.get('/signals')
async def get_signals(
    request: Request,
    limit: int = Query(default=4, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    instruction: str = '',
    user: UserModel = Depends(get_verified_user),
):
    connection = _pick_mcp_connection(request, user)
    if not connection:
        return _empty_response(offset, error='Chưa kết nối DBHub.')

    connection_id = connection_cache_key(connection)
    if not connection_id:
        return _empty_response(offset, error='MCP connection thiếu identifier.', is_configured=True)

    cached = sidebar_cache.get_signals(user.id, connection_id)
    latest = sidebar_cache.latest_generated_at(user.id, connection_id)
    now = int(time.time())
    has_data = bool(cached)
    is_stale = bool(latest) and (now - latest) > PERSISTENT_CACHE_TTL_SECONDS

    # Empty → must generate before user sees anything; stale → refresh in background but serve stale.
    if not has_data or is_stale:
        schedule_regenerate(request, user, connection_id, instruction)

    items = [
        {
            'id': item.id,
            'rank': item.rank,
            'type': item.type,
            'title': item.title,
            'desc': item.desc,
            'createdAt': item.generated_at,
        }
        for item in cached
    ]
    sliced = items[offset : offset + limit]
    next_offset = offset + len(sliced)
    return {
        'items': sliced,
        'total': len(items),
        'offset': offset,
        'nextOffset': next_offset,
        'hasMore': next_offset < len(items),
        'isConfigured': True,
        'isGenerating': (not has_data) and is_generating(user.id, connection_id, instruction),
        'error': '',
    }


@router.get('/heartbeat')
async def get_heartbeat(
    request: Request,
    limit: int = Query(default=4, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    instruction: str = '',
    user: UserModel = Depends(get_verified_user),
):
    connection = _pick_mcp_connection(request, user)
    if not connection:
        return _empty_response(offset, error='Chưa kết nối DBHub.')

    connection_id = connection_cache_key(connection)
    if not connection_id:
        return _empty_response(offset, error='MCP connection thiếu identifier.', is_configured=True)

    cached = sidebar_cache.get_heartbeat(user.id, connection_id)
    latest = sidebar_cache.latest_generated_at(user.id, connection_id)
    now = int(time.time())
    has_data = bool(cached)
    is_stale = bool(latest) and (now - latest) > PERSISTENT_CACHE_TTL_SECONDS

    if not has_data or is_stale:
        schedule_regenerate(request, user, connection_id, instruction)

    items = [
        {
            'id': item.id,
            'rank': item.rank,
            'label': item.label,
            'value': item.value,
            'delta': item.delta or '',
            'trend': item.trend,
            'createdAt': item.generated_at,
        }
        for item in cached
    ]
    sliced = items[offset : offset + limit]
    next_offset = offset + len(sliced)
    return {
        'items': sliced,
        'total': len(items),
        'offset': offset,
        'nextOffset': next_offset,
        'hasMore': next_offset < len(items),
        'isConfigured': True,
        'isGenerating': (not has_data) and is_generating(user.id, connection_id, instruction),
        'error': '',
    }
