from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ... import messages
from ...domain import warehouse_config
from ...domain.warehouse_config import DEFAULT_SSL_MODE, WarehouseConnection
from ...security.audit import record_event
from ..deps import RequestContext, get_admin_context, get_status_context
from ..serialization import serialize

router = APIRouter()

AUDIT_OBJECT_TYPE = 'ket_noi_kho'
AUDIT_ACTION_CONFIGURE = 'kho.cau_hinh'
AUDIT_ACTION_DISCONNECT = 'kho.ngat'
CONFIG_FIELDS = ('host', 'port', 'database', 'username', 'note')


class DbConfigForm(BaseModel):
    host: str = ''
    port: str | int = ''
    database: str = ''
    username: str = ''
    password: str = ''
    note: str = ''


############################
# GetStatus
############################


@router.get('/status')
def get_status(ctx: RequestContext = Depends(get_status_context)) -> dict:
    ctx.reconnect_if_needed()
    warehouse = ctx.container.warehouse
    ready = warehouse.is_alive()
    return {
        'configured': warehouse_config.get_config(ctx.catalog()) is not None,
        'ready': ready,
        'reason': None if ready else warehouse.reason or messages.API_WAREHOUSE_NOT_CONFIGURED,
    }


############################
# GetDbConfig
############################


@router.get('/db-config')
def get_db_config(ctx: RequestContext = Depends(get_admin_context)) -> dict:
    warehouse = ctx.container.warehouse
    warehouse.is_alive()
    saved = warehouse_config.get_config(ctx.catalog())
    if not saved:
        return {'config': None, 'connection': None, 'last_tested_at': None, 'saved_at': None}
    description = f'{saved["username"]}@{saved["host"]}:{saved["port"]}/{saved["database"]}'
    return serialize(
        {
            'config': {key: saved[key] for key in CONFIG_FIELDS},
            'connection': {
                'ok': warehouse.is_configured,
                'description': description,
                'reason': warehouse.reason or None,
            },
            'last_tested_at': saved['tested_at'],
            'saved_at': saved['updated_at'],
        }
    )


############################
# TestDbConfig
############################


@router.post('/db-config/test')
def test_db_config(form_data: DbConfigForm, ctx: RequestContext = Depends(get_admin_context)) -> dict:
    result = warehouse_config.check_connection(_connection(ctx, form_data))
    return {'ok': result.ok, 'message': result.message}


############################
# UpdateDbConfig
############################


@router.put('/db-config')
def update_db_config(form_data: DbConfigForm, ctx: RequestContext = Depends(get_admin_context)) -> dict:
    connection = _connection(ctx, form_data)
    result = warehouse_config.check_connection(connection)
    if not result.ok:
        return {'ok': False, 'message': result.message}
    catalog_conn = ctx.catalog()
    warehouse_config.save_config(catalog_conn, connection, result, note=form_data.note, updated_by=ctx.user.user_name)
    record_event(
        catalog_conn,
        action=AUDIT_ACTION_CONFIGURE,
        actor_user_id=None,
        actor_username=ctx.user.user_name,
        object_type=AUDIT_OBJECT_TYPE,
        object_id=connection.description,
        request_id=ctx.request_id,
        detail={'user_id': ctx.user.user_id, 'description': connection.description},
    )
    ctx.container.reconnect_warehouse(catalog_conn)
    return {'ok': True, 'message': messages.DB_CONFIG_SAVED.format(target=connection.description)}


############################
# DeleteDbConfig
############################


@router.delete('/db-config')
def delete_db_config(ctx: RequestContext = Depends(get_admin_context)) -> dict:
    catalog_conn = ctx.catalog()
    warehouse_config.delete_config(catalog_conn)
    record_event(
        catalog_conn,
        action=AUDIT_ACTION_DISCONNECT,
        actor_user_id=None,
        actor_username=ctx.user.user_name,
        object_type=AUDIT_OBJECT_TYPE,
        object_id='-',
        request_id=ctx.request_id,
        detail={'user_id': ctx.user.user_id},
    )
    ctx.container.warehouse.disconnect(messages.DB_CONFIG_REMOVED_BY_ADMIN, forget_target=True)
    return {'message': messages.DB_CONFIG_REMOVED}


def _connection(ctx: RequestContext, form_data: DbConfigForm) -> WarehouseConnection:
    saved = warehouse_config.get_connection(ctx.catalog())
    fields = warehouse_config.validate_input(
        form_data.host,
        str(form_data.port),
        form_data.database,
        form_data.username,
        saved.sslmode if saved else DEFAULT_SSL_MODE,
    )
    password = form_data.password or (saved.password if saved else '')
    return WarehouseConnection(**fields._asdict(), password=password)
