from __future__ import annotations

import ipaddress
import json
from typing import Any

from ..db import catalog_sql


def record_event(
    catalog_conn,
    *,
    action: str,
    actor_user_id: int | None,
    actor_username: str | None,
    domain_id: int | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    request_id: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    catalog_sql.execute(
        catalog_conn,
        """
        INSERT INTO ctl_audit_event (actor_user_id, actor_username, domain_id, action,
                                     object_type, object_id, request_id, ip, user_agent,
                                     detail)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            actor_user_id,
            actor_username,
            domain_id,
            action,
            object_type,
            object_id,
            request_id,
            _normalize_ip(ip),
            (user_agent or '')[:500],
            json.dumps(detail or {}, ensure_ascii=False, default=str),
        ),
    )


def _normalize_ip(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None
