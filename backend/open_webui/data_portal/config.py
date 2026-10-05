from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from . import messages

PACKAGE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv('DATA_DIR', PACKAGE_DIR.parents[1] / 'data'))


@dataclass(frozen=True)
class Settings:
    default_database_url: str | None
    catalog_path: Path
    catalog_migrations_dir: Path
    registry_dir: Path
    warehouse_migrations_dir: Path
    upload_dir: Path

    def validate(self) -> None:
        if self.default_database_url and not self.default_database_url.startswith('postgres'):
            raise ValueError(messages.CONFIG_INVALID_DATABASE_URL.format(value=self.default_database_url))
        required_dirs = (
            (messages.CONFIG_DIR_CATALOG_MIGRATIONS, self.catalog_migrations_dir),
            (messages.CONFIG_DIR_DEFINITIONS, self.registry_dir),
            (messages.CONFIG_DIR_WAREHOUSE_MIGRATIONS, self.warehouse_migrations_dir),
        )
        for name, path in required_dirs:
            if not path.is_dir():
                raise ValueError(messages.CONFIG_MISSING_DIR.format(name=name, path=path))
        self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    data_dir = Path(os.getenv('DATA_PORTAL_DIR', DATA_DIR / 'data_portal'))
    settings = Settings(
        default_database_url=os.getenv('DATA_PORTAL_DATABASE_URL') or None,
        catalog_path=data_dir / 'catalog.db',
        catalog_migrations_dir=PACKAGE_DIR / 'migrations' / 'catalog',
        registry_dir=PACKAGE_DIR / 'definitions',
        warehouse_migrations_dir=PACKAGE_DIR / 'migrations' / 'warehouse',
        upload_dir=data_dir / 'uploads',
    )
    settings.validate()
    return settings
