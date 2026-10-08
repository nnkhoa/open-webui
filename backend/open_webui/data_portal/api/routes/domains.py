from __future__ import annotations

from fastapi import APIRouter, Depends

from ...registry.schema import Form
from ..deps import RequestContext, get_context

router = APIRouter()

SUBTITLE_SEPARATOR = ' · '


def file_type_json(form: Form) -> dict:
    return {'code': form.code, 'name': form.label, 'subtitle': form.subtitle, 'month_required': form.needs_month}


############################
# GetDomains
############################


@router.get('/domains')
def get_domains(ctx: RequestContext = Depends(get_context)) -> list[dict]:
    result = []
    for domain in ctx.domains():
        forms = [form for _, form in ctx.forms(domain)]
        subtitle = domain.code + (SUBTITLE_SEPARATOR + ', '.join(form.label for form in forms) if forms else '')
        result.append(
            {
                'code': domain.code,
                'name': domain.name,
                'subtitle': subtitle,
                'file_types': [file_type_json(form) for form in forms],
            }
        )
    return result
