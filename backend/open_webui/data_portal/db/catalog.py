from __future__ import annotations

import datetime as dt
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .. import messages

MIGRATION_NAME_PATTERN = re.compile(r'^[0-9a-z_]+$')


class Catalog:
    def __init__(self, path: Path, migrations_dir: Path) -> None:
        self.path = path
        self._migrations_dir = migrations_dir

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute('PRAGMA journal_mode = WAL')
            self._migrate(conn)
        self.path.chmod(0o600)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            conn.execute('BEGIN IMMEDIATE')
            try:
                yield conn
            except BaseException:
                conn.rollback()
                raise
            conn.commit()
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.path,
            detect_types=sqlite3.PARSE_DECLTYPES,
            isolation_level=None,
            timeout=15.0,
            check_same_thread=False,
        )
        conn.execute('PRAGMA foreign_keys = ON')
        return conn

    def _migrate(self, conn: sqlite3.Connection) -> None:
        pending = self._pending_migrations(conn)
        if not pending:
            return
        conn.execute('PRAGMA foreign_keys = OFF')
        try:
            for path in pending:
                _run_migration(conn, path)
            violations = conn.execute('PRAGMA foreign_key_check').fetchall()
            if violations:
                raise RuntimeError(messages.CATALOG_FOREIGN_KEYS_BROKEN.format(violations=violations[:5]))
        finally:
            conn.execute('PRAGMA foreign_keys = ON')

    def _pending_migrations(self, conn: sqlite3.Connection) -> list[Path]:
        conn.execute(
            'CREATE TABLE IF NOT EXISTS so_tay_migration ('
            ' version integer PRIMARY KEY,'
            ' name text NOT NULL,'
            ' applied_at TEXT_TS NOT NULL'
            " DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')))"
        )
        applied = {row[0] for row in conn.execute('SELECT version FROM so_tay_migration')}
        return [path for path in sorted(self._migrations_dir.glob('*.sql')) if int(path.name[:4]) not in applied]


def _run_migration(conn: sqlite3.Connection, path: Path) -> None:
    version, name = int(path.name[:4]), path.stem
    if not MIGRATION_NAME_PATTERN.match(name):
        raise ValueError(messages.CATALOG_INVALID_MIGRATION_NAME.format(name=name))
    conn.executescript(
        'BEGIN;\n'
        + path.read_text(encoding='utf-8')
        + f"\nINSERT INTO so_tay_migration (version, name) VALUES ({version}, '{name}');\nCOMMIT;"
    )


def _parse_timestamp(raw: bytes) -> dt.datetime:
    return dt.datetime.fromisoformat(raw.decode().replace('Z', '+00:00'))


def _format_timestamp(value: dt.datetime) -> str:
    value = (value if value.tzinfo else value.replace(tzinfo=dt.UTC)).astimezone(dt.UTC)
    return value.strftime('%Y-%m-%dT%H:%M:%S.') + f'{value.microsecond // 1000:03d}Z'


sqlite3.register_converter('TEXT_TS', _parse_timestamp)
sqlite3.register_adapter(dt.datetime, _format_timestamp)
