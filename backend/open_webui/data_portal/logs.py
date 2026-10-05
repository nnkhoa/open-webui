from __future__ import annotations

import uuid
from contextvars import ContextVar

REQUEST_ID: ContextVar[str] = ContextVar('request_id', default='-')


def new_request_id() -> str:
    request_id = uuid.uuid4().hex[:16]
    REQUEST_ID.set(request_id)
    return request_id
