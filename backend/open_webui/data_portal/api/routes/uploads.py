from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile

from ... import messages
from ...errors import InvalidInput, NotFound, SourceFileError
from ...pipeline import pending_uploads, upload
from ...pipeline.pending_uploads import PendingUpload
from ...pipeline.upload import UploadRequest
from ...registry.schema import Form as PortalForm
from ...security.rbac import Domain
from ..deps import RequestContext, get_context
from ..serialization import serialize

router = APIRouter()

XLSX_SUFFIX = '.xlsx'


############################
# CreateUpload
############################


@router.post('/uploads')
def create_upload(
    domain: str = Form(''),
    year: str = Form(''),
    month: str = Form(''),
    file_type: str = Form(''),
    file: UploadFile | None = File(None),
    ctx: RequestContext = Depends(get_context),
) -> dict:
    if not domain:
        raise InvalidInput(messages.UPLOAD_DOMAIN_REQUIRED)
    selected_domain = ctx.domain(domain)
    selected_year = _parse_upload_year(year)
    form_id, form = _select_form(ctx, selected_domain, file_type)
    selected_month = _parse_upload_month(month) if form.needs_month else None
    file_name = _xlsx_file_name(file)
    ctx.require_warehouse()
    request = UploadRequest(
        domain_id=selected_domain.domain_id,
        domain_code=selected_domain.code,
        form_id=form_id,
        form=form,
        year=selected_year,
        month=selected_month,
        file_name=file_name,
        source=file.file,
        user_id=ctx.user.user_id,
        user_name=ctx.user.user_name,
        request_id=ctx.request_id,
    )
    try:
        return upload.check_upload(ctx.container, request)
    except SourceFileError:
        raise InvalidInput(messages.UPLOAD_XLSX_ONLY) from None


############################
# CheckUploadForm
############################


@router.post('/uploads/form-check')
def check_upload_form(
    domain: str = Form(''),
    file_type: str = Form(''),
    file: UploadFile | None = File(None),
    ctx: RequestContext = Depends(get_context),
) -> dict:
    if not domain:
        raise InvalidInput(messages.UPLOAD_DOMAIN_REQUIRED)
    _, form = _select_form(ctx, ctx.domain(domain), file_type)
    _xlsx_file_name(file)
    try:
        return upload.check_form(ctx.container, form, file.file)
    except SourceFileError:
        raise InvalidInput(messages.UPLOAD_XLSX_ONLY) from None


############################
# GetPendingUpload
############################


@router.get('/uploads/{pending_id}')
def get_pending_upload(pending_id: str, ctx: RequestContext = Depends(get_context)) -> dict:
    pending = _own_pending_upload(ctx, pending_id)
    form = ctx.registry.form(pending.metadata.file_type)
    return serialize(upload.pending_upload_view(ctx.warehouse(), form, pending))


############################
# DeletePendingUpload
############################


@router.delete('/uploads/{pending_id}', status_code=204)
def delete_pending_upload(pending_id: str, ctx: RequestContext = Depends(get_context)) -> Response:
    pending_uploads.delete(_own_pending_upload(ctx, pending_id))
    return Response(status_code=204)


############################
# ConfirmPendingUpload
############################


@router.post('/uploads/{pending_id}/confirm')
def confirm_pending_upload(pending_id: str, ctx: RequestContext = Depends(get_context)) -> dict:
    pending = _own_pending_upload(ctx, pending_id)
    ctx.require_warehouse()
    return upload.confirm_upload(ctx.container, pending, request_id=ctx.request_id)


def _parse_upload_year(year: str) -> int:
    year = (year or '').strip()
    if not year:
        raise InvalidInput(messages.UPLOAD_YEAR_REQUIRED)
    if not year.isdigit() or int(year) not in upload.YEARS:
        raise InvalidInput(messages.UPLOAD_YEAR_OUT_OF_RANGE.format(first=upload.YEARS[0], last=upload.YEARS[-1]))
    return int(year)


def _xlsx_file_name(file: UploadFile | None) -> str:
    if file is None or not file.filename:
        raise InvalidInput(messages.UPLOAD_FILE_REQUIRED)
    file_name = Path(file.filename).name
    if not file_name.lower().endswith(XLSX_SUFFIX):
        raise InvalidInput(messages.UPLOAD_XLSX_ONLY)
    return file_name


def _parse_upload_month(month: str) -> int:
    month = (month or '').strip()
    if not month:
        raise InvalidInput(messages.UPLOAD_MONTH_REQUIRED)
    if not month.isdigit() or int(month) not in upload.MONTHS:
        raise InvalidInput(messages.UPLOAD_MONTH_OUT_OF_RANGE)
    return int(month)


def _select_form(ctx: RequestContext, domain: Domain, file_type: str) -> tuple[int, PortalForm]:
    forms = ctx.forms(domain)
    if not forms:
        raise InvalidInput(messages.UPLOAD_DOMAIN_WITHOUT_FORMS.format(domain=domain.name))
    if file_type:
        for form_id, form in forms:
            if form.code == file_type:
                return form_id, form
        raise InvalidInput(messages.API_INVALID_FILE_TYPE)
    if len(forms) > 1:
        raise InvalidInput(messages.UPLOAD_FILE_TYPE_REQUIRED)
    return forms[0]


def _own_pending_upload(ctx: RequestContext, pending_id: str) -> PendingUpload:
    pending = pending_uploads.get_pending(ctx.settings.upload_dir, pending_id)
    if pending is None or pending.metadata.user_id != ctx.user.user_id:
        raise NotFound(messages.UPLOAD_PENDING_EXPIRED)
    return pending
