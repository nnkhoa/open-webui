from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import ExitStack
from dataclasses import dataclass, field
from typing import TypeVar

from fastapi import Depends, Request

from open_webui.constants import ADMIN_ROLE, DATA_PORTAL_ROLES

from .. import messages
from ..config import Settings
from ..container import Container
from ..domain import domains
from ..errors import InvalidInput, NotReady, PermissionDenied, WarehouseNotConfigured
from ..logs import new_request_id
from ..registry.loader import FormRegistry
from ..registry.schema import Form
from ..security.rbac import Domain, active_domains

PAGE_SIZES = (25, 50, 100)

T = TypeVar('T')


@dataclass(frozen=True)
class PortalUser:
    user_id: str
    user_name: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == ADMIN_ROLE


@dataclass
class RequestContext:
    container: Container
    user: PortalUser
    request_id: str
    _stack: ExitStack
    _catalog_conn: object = field(default=None)
    _warehouse_conn: object = field(default=None)

    @property
    def settings(self) -> Settings:
        return self.container.settings

    @property
    def registry(self) -> FormRegistry:
        return self.container.registry

    def catalog(self):
        if self._catalog_conn is None:
            self._catalog_conn = self._stack.enter_context(self.container.catalog.transaction())
        return self._catalog_conn

    def warehouse(self):
        if self._warehouse_conn is None:
            self.reconnect_if_needed()
            self._warehouse_conn = self._stack.enter_context(self.container.warehouse_transaction())
        return self._warehouse_conn

    def reconnect_if_needed(self) -> None:
        if not self.container.warehouse.should_retry():
            return
        if self._catalog_conn is not None:
            self.container.reconnect_if_needed(self._catalog_conn)
            return
        with self.container.catalog.transaction() as catalog_conn:
            self.container.reconnect_if_needed(catalog_conn)

    def require_warehouse(self) -> None:
        self.reconnect_if_needed()
        if not self.container.warehouse.is_configured:
            raise WarehouseNotConfigured(reason=self.container.warehouse.reason)

    def domains(self) -> list[Domain]:
        return self._read_catalog(active_domains)

    def domain(self, code: str) -> Domain:
        for domain in self.domains():
            if domain.code == code:
                return domain
        raise InvalidInput(messages.API_INVALID_DOMAIN)

    def forms(self, domain: Domain) -> list[tuple[int, Form]]:
        rows = self._read_catalog(lambda catalog_conn: domains.domain_forms(catalog_conn, domain.domain_id))
        return [(row['form_id'], self.registry.form(row['code'])) for row in rows]

    def _read_catalog(self, read: Callable[[object], T]) -> T:
        if self._catalog_conn is not None:
            return read(self._catalog_conn)
        with self.container.catalog.transaction() as catalog_conn:
            return read(catalog_conn)


def get_current_user():
    raise NotImplementedError('create_api() overrides this dependency with the Open WebUI user dependency.')


def get_portal_user(user=Depends(get_current_user)) -> PortalUser:
    if user.role not in DATA_PORTAL_ROLES:
        raise PermissionDenied(messages.API_NO_PORTAL_ACCESS)
    return PortalUser(user_id=str(user.id), user_name=user.name or user.email or '', role=user.role)


def get_admin_user(user: PortalUser = Depends(get_portal_user)) -> PortalUser:
    if not user.is_admin:
        raise PermissionDenied()
    return user


def get_context(request: Request, user: PortalUser = Depends(get_portal_user)) -> Iterator[RequestContext]:
    for ctx in _open_context(request, user):
        ctx.require_warehouse()
        yield ctx


def get_status_context(request: Request, user: PortalUser = Depends(get_portal_user)) -> Iterator[RequestContext]:
    yield from _open_context(request, user)


def get_admin_context(request: Request, user: PortalUser = Depends(get_admin_user)) -> Iterator[RequestContext]:
    yield from _open_context(request, user)


def parse_pagination(page: int, page_size: int | None, default_page_size: int) -> tuple[int, int]:
    page_size = default_page_size if page_size is None else page_size
    if page < 1 or page_size not in PAGE_SIZES:
        raise InvalidInput(messages.API_INVALID_PAGINATION)
    return page, page_size


def parse_year(year: str) -> int | None:
    if not year:
        return None
    if not year.isdigit():
        raise InvalidInput(messages.API_INVALID_YEAR)
    return int(year)


def _open_context(request: Request, user: PortalUser) -> Iterator[RequestContext]:
    container = getattr(request.app.state, 'data_portal', None)
    if container is None:
        raise NotReady()
    with ExitStack() as stack:
        yield RequestContext(container=container, user=user, request_id=new_request_id(), _stack=stack)
