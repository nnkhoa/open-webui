from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

import psycopg
from psycopg import conninfo

from .. import messages
from ..db import catalog_sql
from ..errors import InvalidInput

SSL_MODES = ('disable', 'allow', 'prefer', 'require', 'verify-ca', 'verify-full')
DEFAULT_SSL_MODE = 'prefer'
CONNECT_TIMEOUT_SECONDS = 8
PORT_RANGE = range(1, 65536)
ERROR_TRANSLATIONS: tuple[tuple[tuple[str, ...], str], ...] = (
    (('no password supplied',), messages.DB_CONFIG_ERROR_NO_PASSWORD),
    (('password authentication failed',), messages.DB_CONFIG_ERROR_WRONG_PASSWORD),
    (('role', 'does not exist'), messages.DB_CONFIG_ERROR_UNKNOWN_USER),
    (('database', 'does not exist'), messages.DB_CONFIG_ERROR_UNKNOWN_DATABASE),
    (('connection refused',), messages.DB_CONFIG_ERROR_CONNECTION_REFUSED),
    (('could not translate host name',), messages.DB_CONFIG_ERROR_UNKNOWN_HOST),
    (('timeout',), messages.DB_CONFIG_ERROR_TIMEOUT),
    (('no pg_hba.conf entry',), messages.DB_CONFIG_ERROR_HOST_REJECTED),
)
MULTIPLE_ATTEMPTS_MARKER = 'Multiple connection attempts failed'


@dataclass(frozen=True)
class WarehouseConnection:
    host: str
    port: int
    database: str
    username: str
    password: str
    sslmode: str

    @property
    def dsn(self) -> str:
        return conninfo.make_conninfo(
            host=self.host,
            port=self.port,
            dbname=self.database,
            user=self.username,
            password=self.password,
            sslmode=self.sslmode,
        )

    @property
    def description(self) -> str:
        return f'{self.username}@{self.host}:{self.port}/{self.database}'


class ConnectionFields(NamedTuple):
    host: str
    port: int
    database: str
    username: str
    sslmode: str


class ConnectionCheck(NamedTuple):
    ok: bool
    message: str


def get_connection(catalog_conn) -> WarehouseConnection | None:
    row = catalog_sql.query_one(
        catalog_conn,
        'SELECT host, port, database, username, password, sslmode FROM ctl_warehouse_connection WHERE id = 1',
    )
    return None if row is None else WarehouseConnection(**row)


def get_config(catalog_conn) -> dict | None:
    return catalog_sql.query_one(
        catalog_conn,
        'SELECT host, port, database, username, sslmode, note, '
        '       tested_at, test_ok, test_message, updated_at, updated_by '
        'FROM ctl_warehouse_connection WHERE id = 1',
    )


def validate_input(host: str, port: str, database: str, username: str, sslmode: str) -> ConnectionFields:
    errors: dict[str, str] = {}
    host = host.strip()
    database = database.strip()
    username = username.strip()
    sslmode = (sslmode or DEFAULT_SSL_MODE).strip()

    if not host:
        errors['host'] = messages.DB_CONFIG_MISSING_HOST
    if not database:
        errors['database'] = messages.DB_CONFIG_MISSING_DATABASE
    if not username:
        errors['username'] = messages.DB_CONFIG_MISSING_USERNAME
    if sslmode not in SSL_MODES:
        errors['sslmode'] = messages.DB_CONFIG_INVALID_SSL_MODE.format(modes=', '.join(SSL_MODES))
    port_number, port_error = _parse_port(port)
    if port_error:
        errors['port'] = port_error

    if errors:
        raise InvalidInput(messages.DB_CONFIG_INVALID, errors)
    return ConnectionFields(host, port_number, database, username, sslmode)


def check_connection(connection: WarehouseConnection) -> ConnectionCheck:
    try:
        with psycopg.connect(connection.dsn, connect_timeout=CONNECT_TIMEOUT_SECONDS) as conn:
            version = conn.execute('SELECT version()').fetchone()
    except psycopg.OperationalError as e:
        return ConnectionCheck(False, describe_error(e))
    except psycopg.Error as e:
        return ConnectionCheck(False, messages.DB_CONFIG_DATABASE_REFUSED.format(error=e).strip())
    server = (version[0] if version else '').split(' on ')[0]
    return ConnectionCheck(True, messages.DB_CONFIG_CONNECTED.format(server=server))


def describe_error(error: Exception) -> str:
    text = str(error).lower()
    for markers, message in ERROR_TRANSLATIONS:
        if all(marker in text for marker in markers):
            return message
    return _first_line(str(error))


def save_config(
    catalog_conn, connection: WarehouseConnection, result: ConnectionCheck, *, note: str, updated_by: str
) -> None:
    catalog_sql.execute(
        catalog_conn,
        'INSERT INTO ctl_warehouse_connection '
        '  (id, host, port, database, username, password, sslmode, note,'
        '   tested_at, test_ok, test_message, updated_at, updated_by) '
        'VALUES (1, ?, ?, ?, ?, ?, ?, ?, '
        "        strftime('%Y-%m-%dT%H:%M:%fZ','now'), ?, ?, "
        "        strftime('%Y-%m-%dT%H:%M:%fZ','now'), ?) "
        'ON CONFLICT (id) DO UPDATE SET '
        '  host = excluded.host, port = excluded.port, database = excluded.database,'
        '  username = excluded.username, password = excluded.password,'
        '  sslmode = excluded.sslmode, note = excluded.note,'
        '  tested_at = excluded.tested_at, test_ok = excluded.test_ok,'
        '  test_message = excluded.test_message,'
        '  updated_at = excluded.updated_at, updated_by = excluded.updated_by',
        (
            connection.host,
            connection.port,
            connection.database,
            connection.username,
            connection.password,
            connection.sslmode,
            note.strip() or None,
            1 if result.ok else 0,
            result.message,
            updated_by,
        ),
    )


def delete_config(catalog_conn) -> None:
    catalog_sql.execute(catalog_conn, 'DELETE FROM ctl_warehouse_connection WHERE id = 1')


def _parse_port(raw: str) -> tuple[int, str | None]:
    raw = (raw or '').strip()
    if not raw:
        return 0, messages.DB_CONFIG_MISSING_PORT
    try:
        port = int(raw)
    except ValueError:
        return 0, messages.DB_CONFIG_PORT_NOT_NUMBER
    if port not in PORT_RANGE:
        return port, messages.DB_CONFIG_PORT_OUT_OF_RANGE
    return port, None


def _first_line(text: str) -> str:
    head = text.split(MULTIPLE_ATTEMPTS_MARKER)[0]
    lines = [line.strip() for line in head.splitlines() if line.strip()]
    return lines[0] if lines else messages.DB_CONFIG_CONNECT_FAILED
