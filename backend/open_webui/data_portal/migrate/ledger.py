from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from pathlib import Path

from psycopg import sql

from .. import messages
from ..db import sql as warehouse_sql
from ..errors import MigrationError

FILE_NAME_PATTERN = re.compile(r'^(\d{4})_([a-z0-9_]+)\.sql$')


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql_text: str
    source: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql_text.encode('utf-8')).hexdigest()

    @property
    def label(self) -> str:
        return f'{self.version:04d}_{self.name}'


def read_migrations(migrations_dir: Path) -> list[Migration]:
    files = [(path, 'manual') for path in sorted(migrations_dir.glob('*.sql'))]
    files += [(path, 'generated') for path in sorted((migrations_dir / 'auto').glob('*.sql'))]
    migrations = [_read_migration(path, source) for path, source in files]
    versions = [migration.version for migration in migrations]
    duplicates = {version for version in versions if versions.count(version) > 1}
    if duplicates:
        raise MigrationError(messages.MIGRATION_DUPLICATE_VERSIONS.format(versions=sorted(duplicates)))
    return sorted(migrations, key=lambda migration: migration.version)


def applied_checksums(conn) -> dict[int, str]:
    has_ledger = warehouse_sql.scalar(
        conn,
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'ctl' AND table_name = 'schema_migration'",
    )
    if not has_ledger:
        return {}
    rows = warehouse_sql.query(conn, 'SELECT version, checksum FROM ctl.schema_migration')
    return {row['version']: row['checksum'] for row in rows}


def apply(conn, migrations_dir: Path, applied_by: str = 'cli') -> list[str]:
    migrations = read_migrations(migrations_dir)
    applied = applied_checksums(conn)
    labels: list[str] = []
    for migration in migrations:
        checksum = applied.get(migration.version)
        if checksum is not None:
            if checksum != migration.checksum:
                raise MigrationError(messages.MIGRATION_CHANGED.format(label=migration.label))
            continue
        run_migration(conn, migration, applied_by)
        conn.commit()
        labels.append(migration.label)
    return labels


def run_migration(conn, migration: Migration, applied_by: str) -> None:
    started_at = time.monotonic()
    with conn.cursor() as cur:
        cur.execute(migration.sql_text)
    duration_ms = int((time.monotonic() - started_at) * 1000)
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL(
                'INSERT INTO ctl.schema_migration '
                '(version, name, checksum, source, applied_by, duration_ms) '
                'VALUES (%s, %s, %s, %s, %s, %s)'
            ),
            (migration.version, migration.name, migration.checksum, migration.source, applied_by, duration_ms),
        )


def _read_migration(path: Path, source: str) -> Migration:
    match = FILE_NAME_PATTERN.match(path.name)
    if not match:
        raise MigrationError(messages.MIGRATION_INVALID_FILE_NAME.format(name=path.name))
    return Migration(int(match.group(1)), match.group(2), path.read_text(encoding='utf-8'), source)
