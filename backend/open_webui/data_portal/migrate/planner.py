from __future__ import annotations

from pathlib import Path

from .. import messages
from ..errors import MigrationError
from ..registry.khac_biet import so_sanh
from ..registry.schema import Form


def next_version(migrations_dir: Path) -> int:
    paths = [*migrations_dir.glob('*.sql'), *(migrations_dir / 'auto').glob('*.sql')]
    versions = [int(path.name[:4]) for path in paths if path.name[:4].isdigit()]
    return (max(versions) + 1) if versions else 1


def generate_migration(conn, form: Form, migrations_dir: Path) -> Path | None:
    plan = so_sanh(conn, form)
    if plan.bi_chan:
        items = '\n'.join(
            messages.MIGRATION_BLOCKED_ITEM.format(description=change.mo_ta, reason=change.ly_do)
            for change in plan.bi_chan
        )
        raise MigrationError(messages.MIGRATION_BLOCKED + items)
    if not plan.can_ddl:
        return None
    auto_dir = migrations_dir / 'auto'
    auto_dir.mkdir(parents=True, exist_ok=True)
    target = auto_dir / f'{next_version(migrations_dir):04d}_form_{form.code.lower()}_v{form.version}.sql'
    target.write_text(plan.sinh_ddl(), encoding='utf-8')
    return target
