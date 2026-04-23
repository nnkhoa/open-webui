from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from open_webui.models.users import UserModel
from open_webui.utils.auth import get_verified_user

from .sidebar_runtime import build_sidebar_snapshot


router = APIRouter()


@router.get("/signals")
async def get_signals(
    request: Request,
    limit: int = Query(default=4, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    instruction: str = "",
    user: UserModel = Depends(get_verified_user),
):
    try:
        snapshot = await build_sidebar_snapshot(request, user, instruction=instruction)
    except Exception as error:
        return {
            "items": [],
            "total": 0,
            "offset": offset,
            "nextOffset": offset,
            "hasMore": False,
            "isConfigured": False,
            "error": str(error),
        }
    if not snapshot.get("configured"):
        return {
            "items": [],
            "total": 0,
            "offset": offset,
            "nextOffset": offset,
            "hasMore": False,
            "isConfigured": False,
            "error": snapshot.get("error") or "Sidebar is not configured.",
        }

    items = snapshot.get("signals") or []
    sliced = items[offset : offset + limit]
    next_offset = offset + len(sliced)
    return {
        "items": sliced,
        "total": len(items),
        "offset": offset,
        "nextOffset": next_offset,
        "hasMore": next_offset < len(items),
        "isConfigured": True,
        "error": "",
    }


@router.get("/heartbeat")
async def get_heartbeat(
    request: Request,
    limit: int = Query(default=4, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    instruction: str = "",
    user: UserModel = Depends(get_verified_user),
):
    try:
        snapshot = await build_sidebar_snapshot(request, user, instruction=instruction)
    except Exception as error:
        return {
            "items": [],
            "total": 0,
            "offset": offset,
            "nextOffset": offset,
            "hasMore": False,
            "isConfigured": False,
            "error": str(error),
        }
    if not snapshot.get("configured"):
        return {
            "items": [],
            "total": 0,
            "offset": offset,
            "nextOffset": offset,
            "hasMore": False,
            "isConfigured": False,
            "error": snapshot.get("error") or "Sidebar is not configured.",
        }

    items = snapshot.get("heartbeat") or []
    sliced = items[offset : offset + limit]
    next_offset = offset + len(sliced)
    return {
        "items": sliced,
        "total": len(items),
        "offset": offset,
        "nextOffset": next_offset,
        "hasMore": next_offset < len(items),
        "isConfigured": True,
        "error": "",
    }
