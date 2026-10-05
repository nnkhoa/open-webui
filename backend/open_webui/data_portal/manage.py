from __future__ import annotations

import argparse
import sys
from contextlib import AbstractContextManager

from . import messages
from .config import load_settings
from .container import Container, build_container
from .errors import PortalError, WarehouseNotConfigured
from .migrate import ledger, planner
from .registry import sync
from .registry.ddl import ddl_form


def run_migrate(container: Container, _args: argparse.Namespace) -> int:
    with _warehouse_transaction(container) as conn:
        applied = ledger.apply(conn, container.settings.warehouse_migrations_dir)
    if applied:
        _echo(messages.CLI_APPLIED, ', '.join(applied))
    else:
        _echo(messages.CLI_UP_TO_DATE)
    return 0


def run_makemigration(container: Container, _args: argparse.Namespace) -> int:
    with _warehouse_transaction(container) as conn:
        generated = [
            planner.generate_migration(conn, form, container.settings.warehouse_migrations_dir)
            for form in container.registry.forms
        ]
    generated = [path for path in generated if path is not None]
    if not generated:
        _echo(messages.CLI_NO_CHANGES)
        return 0
    for path in generated:
        _echo(messages.CLI_GENERATED.format(path=path))
    _echo(messages.CLI_REVIEW_THEN_MIGRATE)
    return 0


def run_registry(container: Container, args: argparse.Namespace) -> int:
    if args.action == 'validate':
        _print_registry(container)
        return 0
    if not args.code:
        _echo(messages.CLI_MISSING_FORM_CODE)
        return 2
    _echo(ddl_form(container.registry.form(args.code)))
    return 0


def run_sync_registry(container: Container, _args: argparse.Namespace) -> int:
    with container.catalog.transaction() as catalog_conn:
        if container.warehouse.is_configured:
            with container.warehouse.transaction() as conn:
                sync.dong_bo(catalog_conn, conn, container.registry)
        else:
            sync.dong_bo(catalog_conn, None, container.registry)
            _echo(messages.CLI_CATALOG_ONLY)
    _echo(
        messages.CLI_SYNCED,
        ', '.join(form.code for form in container.registry.forms),
        '·',
        ', '.join(domain.code for domain in container.registry.domains),
    )
    return 0


def main() -> int:
    args = _build_parser().parse_args()
    container = build_container(load_settings())
    command = {
        'migrate': run_migrate,
        'makemigration': run_makemigration,
        'registry': run_registry,
        'sync-registry': run_sync_registry,
    }[args.command]
    try:
        return command(container, args)
    except WarehouseNotConfigured as e:
        if e.reason:
            _echo(messages.CLI_ERROR_WITH_REASON.format(error=e, reason=e.reason))
        else:
            _echo(messages.CLI_ERROR.format(error=e))
        return 1
    except PortalError as e:
        _echo(messages.CLI_ERROR.format(error=e))
        return 1
    finally:
        container.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=messages.CLI_DESCRIPTION)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('migrate', help=messages.CLI_HELP_MIGRATE)
    commands.add_parser('makemigration', help=messages.CLI_HELP_MAKEMIGRATION)
    commands.add_parser('sync-registry', help=messages.CLI_HELP_SYNC_REGISTRY)
    registry = commands.add_parser('registry', help=messages.CLI_HELP_REGISTRY)
    registry.add_argument('action', choices=['validate', 'ddl'])
    registry.add_argument('code', nargs='?')
    return parser


def _print_registry(container: Container) -> None:
    for form in container.registry.forms:
        column_count = sum(len(table.columns) for table in form.tables)
        _echo(
            messages.CLI_FORM_VALID.format(
                code=form.code, version=form.version, table_count=len(form.tables), column_count=column_count
            )
        )
    for domain in container.registry.domains:
        forms = ', '.join(domain.cac_bo_bang) or messages.CLI_NO_FORMS
        _echo(messages.CLI_DOMAIN_VALID.format(code=domain.code, name=domain.name, forms=forms))
    _echo(messages.CLI_DEFINITIONS_VALID)


def _warehouse_transaction(container: Container) -> AbstractContextManager:
    if not container.warehouse.is_configured:
        raise WarehouseNotConfigured(reason=container.warehouse.reason)
    return container.warehouse.transaction()


def _echo(*parts: object) -> None:
    print(*parts, file=sys.stdout)


if __name__ == '__main__':
    sys.exit(main())
