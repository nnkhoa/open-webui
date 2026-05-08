from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from open_webui.models.ai4bi_sidebar import sidebar_cache
from open_webui.models.users import UserModel
from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui import config as ai4bi_config

from .sidebar_runtime import (
    PERSISTENT_CACHE_TTL_SECONDS,
    _pick_mcp_connection,
    connection_cache_key,
    is_generating,
    schedule_regenerate,
)


router = APIRouter()


class SidebarPromptsForm(BaseModel):
    signals_prompt: str = ''
    heartbeat_prompt: str = ''


@router.get('/admin/sidebar-prompts')
async def get_sidebar_prompts(user=Depends(get_admin_user)):
    return {
        'signals_prompt': ai4bi_config.AI4BI_SIGNALS_PROMPT.value or '',
        'heartbeat_prompt': ai4bi_config.AI4BI_HEARTBEAT_PROMPT.value or '',
    }


@router.post('/admin/sidebar-prompts')
async def set_sidebar_prompts(form: SidebarPromptsForm, user=Depends(get_admin_user)):
    ai4bi_config.AI4BI_SIGNALS_PROMPT.value = form.signals_prompt or ''
    ai4bi_config.AI4BI_SIGNALS_PROMPT.save()
    ai4bi_config.AI4BI_HEARTBEAT_PROMPT.value = form.heartbeat_prompt or ''
    ai4bi_config.AI4BI_HEARTBEAT_PROMPT.save()
    sidebar_cache.clear_all()
    return {
        'signals_prompt': ai4bi_config.AI4BI_SIGNALS_PROMPT.value,
        'heartbeat_prompt': ai4bi_config.AI4BI_HEARTBEAT_PROMPT.value,
    }


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
