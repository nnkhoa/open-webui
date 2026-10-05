from __future__ import annotations

from pathlib import Path

from .. import messages
from ..errors import MigrationError
from ..registry.diff import compare
from ..registry.schema import Form


def next_version(migrations_dir: Path) -> int:
    paths = [*migrations_dir.glob('*.sql'), *(migrations_dir / 'auto').glob('*.sql')]
    versions = [int(path.name[:4]) for path in paths if path.name[:4].isdigit()]
    return (max(versions) + 1) if versions else 1


def generate_migration(conn, form: Form, migrations_dir: Path) -> Path | None:
    plan = compare(conn, form)
    if plan.blocked:
        items = '\n'.join(
            messages.MIGRATION_BLOCKED_ITEM.format(description=change.description, reason=change.reason)
            for change in plan.blocked
        )
        raise MigrationError(messages.MIGRATION_BLOCKED + items)
    if not plan.ddl_changes:
        return None
    auto_dir = migrations_dir / 'auto'
    auto_dir.mkdir(parents=True, exist_ok=True)
    target = auto_dir / f'{next_version(migrations_dir):04d}_form_{form.code.lower()}_v{form.version}.sql'
    target.write_text(plan.to_sql(), encoding='utf-8')
    return target
