from __future__ import annotations

from collections.abc import Iterable

from psycopg import sql

LOCK_NAMESPACE = 0x4E4243


def acquire_write_locks(conn, scopes: Iterable[tuple[int, int]]) -> None:
    with conn.cursor() as cur:
        for domain_id, form_id in sorted(set(scopes)):
            cur.execute(
                sql.SQL('SELECT pg_advisory_xact_lock(%s, %s)'),
                (LOCK_NAMESPACE, (int(domain_id) << 16) | int(form_id)),
            )
