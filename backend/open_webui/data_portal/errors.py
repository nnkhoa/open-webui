from __future__ import annotations

from typing import TYPE_CHECKING

from . import messages

if TYPE_CHECKING:
    from .pipeline.reconcile import Mismatch


class PortalError(Exception):
    status_code = 500


class RegistryError(PortalError):
    pass


class MigrationError(PortalError):
    pass


class SourceFileError(PortalError):
    status_code = 400


class StructureError(PortalError):
    status_code = 400

    def __init__(self, errors: list[dict]) -> None:
        super().__init__(messages.ERROR_STRUCTURE.format(count=len(errors)))
        self.errors = errors


class ReconcileError(PortalError):
    def __init__(
        self,
        mismatches: list[Mismatch],
        steps: list[dict] | None = None,
        reconciliation: dict | None = None,
    ) -> None:
        super().__init__(messages.ERROR_RECONCILE_MISMATCH.format(count=len(mismatches)))
        self.mismatches = mismatches
        self.steps = steps
        self.reconciliation = reconciliation


class PermissionDenied(PortalError):
    status_code = 403

    def __init__(self, message: str = messages.ERROR_PERMISSION_DENIED) -> None:
        super().__init__(message)


class WarehouseNotConfigured(PortalError):
    status_code = 503

    def __init__(self, reason: str = '') -> None:
        super().__init__(messages.ERROR_WAREHOUSE_NOT_CONFIGURED)
        self.reason = reason


class NotFound(PortalError):
    status_code = 404


class NotReady(PortalError):
    status_code = 503

    def __init__(self, message: str = messages.ERROR_NOT_READY) -> None:
        super().__init__(message)


class Conflict(PortalError):
    status_code = 409


class InvalidInput(PortalError):
    status_code = 400

    def __init__(self, message: str, field_errors: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.field_errors = field_errors or {}
