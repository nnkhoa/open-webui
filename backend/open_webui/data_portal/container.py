from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import psycopg

from . import messages
from .config import Settings, load_settings
from .db.catalog import Catalog
from .db.warehouse import BACKGROUND_CONNECT_TIMEOUT, INTERACTIVE_CONNECT_TIMEOUT, Warehouse
from .domain import warehouse_config
from .errors import MigrationError, WarehouseNotConfigured
from .migrate import ledger
from .registry import sync
from .registry.loader import FormRegistry, load_definitions


@dataclass
class Container:
    settings: Settings
    catalog: Catalog
    warehouse: Warehouse
    registry: FormRegistry

    def close(self) -> None:
        self.warehouse.close()

    def reconnect_warehouse(self, catalog_conn, timeout: float = INTERACTIVE_CONNECT_TIMEOUT) -> None:
        saved = warehouse_config.get_connection(catalog_conn)
        if saved is None:
            self.warehouse.disconnect(messages.WAREHOUSE_NOT_SET, forget_target=True)
            return
        target = saved.description
        try:
            self.warehouse.connect(saved.dsn, timeout=timeout)
        except psycopg.Error as e:
            reason = warehouse_config.describe_error(e)
            self.warehouse.disconnect(messages.WAREHOUSE_CONNECT_FAILED.format(target=target, reason=reason).strip())
            return
        try:
            self.build_warehouse(catalog_conn)
        except (psycopg.Error, MigrationError) as e:
            self.warehouse.disconnect(messages.WAREHOUSE_SCHEMA_FAILED.format(target=target, error=e))

    def reconnect_if_needed(self, catalog_conn) -> None:
        if self.warehouse.should_retry():
            self.reconnect_warehouse(catalog_conn, timeout=BACKGROUND_CONNECT_TIMEOUT)

    @contextmanager
    def warehouse_transaction(self) -> Iterator[psycopg.Connection]:
        if not self.warehouse.is_configured:
            raise WarehouseNotConfigured(reason=self.warehouse.reason)
        try:
            with self.warehouse.transaction() as conn:
                yield conn
        except psycopg.OperationalError as e:
            reason = warehouse_config.describe_error(e)
            self.warehouse.disconnect(messages.WAREHOUSE_CONNECTION_FAILED.format(reason=reason))
            raise WarehouseNotConfigured(reason=self.warehouse.reason) from e

    def build_warehouse(self, catalog_conn) -> None:
        with self.warehouse.transaction() as conn:
            ledger.apply(conn, self.settings.warehouse_migrations_dir, applied_by='portal')
            sync.mirror_to_warehouse(catalog_conn, conn)


def build_container(settings: Settings | None = None) -> Container:
    settings = settings or load_settings()
    container = Container(
        settings=settings,
        catalog=Catalog(settings.catalog_path, settings.catalog_migrations_dir),
        warehouse=Warehouse(),
        registry=load_definitions(settings.registry_dir),
    )
    container.catalog.open()
    with container.catalog.transaction() as catalog_conn:
        sync.sync_definitions(catalog_conn, None, container.registry)
        container.reconnect_warehouse(catalog_conn)
    return container
