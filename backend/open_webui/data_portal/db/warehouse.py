from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg_pool import ConnectionPool, PoolTimeout

from .. import messages
from ..errors import WarehouseNotConfigured

RETRY_INTERVAL_SECONDS = 5.0
BACKGROUND_CONNECT_TIMEOUT = 3.0
INTERACTIVE_CONNECT_TIMEOUT = 10.0


class Warehouse:
    def __init__(self) -> None:
        self._pool: ConnectionPool | None = None
        self._target_dsn: str | None = None
        self._last_attempt_at = 0.0
        self._reason: str = messages.WAREHOUSE_NOT_SET
        self._lock = threading.Lock()

    @property
    def is_configured(self) -> bool:
        return self._pool is not None

    @property
    def reason(self) -> str:
        return self._reason

    def should_retry(self) -> bool:
        return (
            self._pool is None
            and self._target_dsn is not None
            and time.monotonic() - self._last_attempt_at >= RETRY_INTERVAL_SECONDS
        )

    def connect(self, dsn: str, timeout: float = INTERACTIVE_CONNECT_TIMEOUT) -> None:
        self._last_attempt_at = time.monotonic()
        self._target_dsn = dsn
        pool = ConnectionPool(dsn, min_size=1, max_size=8, open=False, kwargs={'autocommit': False})
        try:
            pool.open(wait=True, timeout=timeout)
        except BaseException:
            pool.close()
            raise
        with self._lock:
            previous, self._pool = self._pool, pool
            self._reason = ''
        if previous is not None:
            previous.close()

    def disconnect(self, reason: str, forget_target: bool = False) -> None:
        with self._lock:
            previous, self._pool = self._pool, None
            self._reason = reason
            if forget_target:
                self._target_dsn = None
        if previous is not None:
            previous.close()

    def close(self) -> None:
        self.disconnect(messages.WAREHOUSE_SHUTTING_DOWN, forget_target=True)

    def is_alive(self) -> bool:
        with self._lock:
            pool = self._pool
        if pool is None:
            return False
        try:
            with pool.connection() as conn:
                conn.execute('SELECT 1')
        except (psycopg.Error, PoolTimeout) as e:
            self.disconnect(messages.WAREHOUSE_CONNECTION_LOST.format(reason=_first_line(e)))
            return False
        return True

    def require_pool(self) -> ConnectionPool:
        with self._lock:
            if self._pool is None:
                raise WarehouseNotConfigured(reason=self._reason)
            return self._pool

    @contextmanager
    def transaction(self) -> Iterator[psycopg.Connection]:
        with self.require_pool().connection() as conn:
            yield conn


def _first_line(error: Exception) -> str:
    lines = [line.strip() for line in str(error).splitlines() if line.strip()]
    return lines[0] if lines else error.__class__.__name__
