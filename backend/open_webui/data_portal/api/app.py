from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.datastructures import State
from starlette.exceptions import HTTPException as StarletteHTTPException

from .. import messages
from ..container import Container, build_container
from ..errors import (
    InvalidInput,
    NotFound,
    NotReady,
    PortalError,
    RegistryError,
    SourceFileError,
    WarehouseNotConfigured,
)
from ..logs import REQUEST_ID
from .deps import PortalUser, get_current_user, get_portal_user
from .routes import db_config, domains, loads, tables, uploads

log = logging.getLogger(__name__)

ROUTERS = (domains, uploads, loads, tables, db_config)
CATCH_ALL_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']


def create_api(get_user: Callable, state: State | None = None, container: Container | None = None) -> FastAPI:
    api = FastAPI(title='Data Portal API', docs_url=None, redoc_url=None, openapi_url=None)
    if state is not None:
        api.state = state
    api.state.data_portal = container
    api.dependency_overrides[get_current_user] = get_user
    for module in ROUTERS:
        api.include_router(module.router)

    @api.api_route('/{path:path}', methods=CATCH_ALL_METHODS, include_in_schema=False)
    def not_found(path: str, user: PortalUser = Depends(get_portal_user)):
        raise NotFound(messages.API_NOT_FOUND)

    _register_exception_handlers(api)
    return api


def start(api: FastAPI) -> None:
    try:
        api.state.data_portal = build_container()
    except Exception:
        log.exception('Data Portal failed to start')


def stop(api: FastAPI) -> None:
    container = getattr(api.state, 'data_portal', None)
    if container is not None:
        container.close()
        api.state.data_portal = None


def _error_response(status_code: int, detail: str, **extra) -> JSONResponse:
    return JSONResponse({'detail': detail, **extra}, status_code=status_code)


def _register_exception_handlers(api: FastAPI) -> None:
    handlers = (
        (NotReady, _not_ready_handler),
        (WarehouseNotConfigured, _warehouse_not_configured_handler),
        (InvalidInput, _invalid_input_handler),
        (SourceFileError, _source_file_handler),
        (RegistryError, _registry_handler),
        (PortalError, _portal_error_handler),
        (RequestValidationError, _request_validation_handler),
        (StarletteHTTPException, _http_exception_handler),
        (Exception, _unexpected_error_handler),
    )
    for exception_class, handler in handlers:
        api.add_exception_handler(exception_class, handler)


async def _not_ready_handler(request: Request, exc: NotReady) -> JSONResponse:
    return _error_response(503, str(exc))


async def _warehouse_not_configured_handler(request: Request, exc: WarehouseNotConfigured) -> JSONResponse:
    return _error_response(503, exc.reason or messages.API_WAREHOUSE_NOT_CONFIGURED)


async def _invalid_input_handler(request: Request, exc: InvalidInput) -> JSONResponse:
    extra = {'field_errors': exc.field_errors} if exc.field_errors else {}
    return _error_response(422, str(exc), **extra)


async def _source_file_handler(request: Request, exc: SourceFileError) -> JSONResponse:
    return _error_response(422, str(exc))


async def _registry_handler(request: Request, exc: RegistryError) -> JSONResponse:
    return _error_response(404, messages.API_NOT_FOUND)


async def _portal_error_handler(request: Request, exc: PortalError) -> JSONResponse:
    if exc.status_code >= 500:
        log.exception('Unhandled portal error: %s', exc)
        return _error_response(exc.status_code, messages.API_UNEXPECTED_ERROR, request_id=REQUEST_ID.get())
    return _error_response(exc.status_code, str(exc))


async def _request_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _error_response(422, messages.API_INVALID_REQUEST)


async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code == 404:
        return _error_response(404, messages.API_NOT_FOUND)
    if exc.status_code == 405:
        return _error_response(405, messages.API_METHOD_NOT_ALLOWED)
    return _error_response(exc.status_code, str(exc.detail))


async def _unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception('Unexpected Data Portal API error: %s', exc)
    return _error_response(500, messages.API_UNEXPECTED_ERROR, request_id=REQUEST_ID.get())
