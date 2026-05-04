import logging
import uuid
import shutil
from pathlib import Path
from fastapi import APIRouter, Depends, Request, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional

from open_webui.utils.auth import get_admin_user
from open_webui.config import UPLOAD_DIR

router = APIRouter()

log = logging.getLogger(__name__)


############################
# Project Config Models
############################


class ProjectConfigForm(BaseModel):
    logo_url: Optional[str] = None
    model_display_names: Optional[dict[str, str]] = {}
    brand_color: Optional[str] = None
    org_name: Optional[str] = None
    org_subtitle: Optional[str] = None
    app_name: Optional[str] = None


############################
# GET /api/v1/configs/project
############################


@router.get('/project')
async def get_project_config(request: Request, user=Depends(get_admin_user)):
    return {
        'logo_url': request.app.state.config.AIBI_PROJECT_LOGO,
        'model_display_names': request.app.state.config.AIBI_MODEL_DISPLAY_NAMES,
        'brand_color': request.app.state.config.AIBI_BRAND_COLOR,
        'org_name': request.app.state.config.AIBI_ORG_NAME,
        'org_subtitle': request.app.state.config.AIBI_ORG_SUBTITLE,
        'app_name': request.app.state.config.AIBI_APP_NAME,
    }


############################
# POST /api/v1/configs/project
############################


@router.post('/project')
async def set_project_config(
    request: Request,
    form_data: ProjectConfigForm,
    user=Depends(get_admin_user),
):
    data = form_data.model_dump(exclude_none=False)

    if 'model_display_names' in data:
        request.app.state.config.AIBI_MODEL_DISPLAY_NAMES = data['model_display_names']

    if 'brand_color' in data:
        request.app.state.config.AIBI_BRAND_COLOR = data['brand_color']

    if 'logo_url' in data:
        request.app.state.config.AIBI_PROJECT_LOGO = data['logo_url']

    if 'org_name' in data and data['org_name'] is not None:
        request.app.state.config.AIBI_ORG_NAME = data['org_name']

    if 'org_subtitle' in data and data['org_subtitle'] is not None:
        request.app.state.config.AIBI_ORG_SUBTITLE = data['org_subtitle']

    if 'app_name' in data and data['app_name'] is not None:
        request.app.state.config.AIBI_APP_NAME = data['app_name']

    return {
        'logo_url': request.app.state.config.AIBI_PROJECT_LOGO,
        'model_display_names': request.app.state.config.AIBI_MODEL_DISPLAY_NAMES,
        'brand_color': request.app.state.config.AIBI_BRAND_COLOR,
        'org_name': request.app.state.config.AIBI_ORG_NAME,
        'org_subtitle': request.app.state.config.AIBI_ORG_SUBTITLE,
        'app_name': request.app.state.config.AIBI_APP_NAME,
    }


############################
# POST /api/v1/configs/project/logo — Upload logo
############################


@router.post('/project/logo')
async def upload_project_logo(
    request: Request,
    file: UploadFile = File(...),
    user=Depends(get_admin_user),
):
    allowed_types = {'image/png', 'image/jpeg', 'image/svg+xml', 'image/webp', 'image/gif'}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f'Invalid file type: {file.content_type}. Allowed: {allowed_types}',
        )

    content = await file.read()

    ext = Path(file.filename or 'logo.png').suffix or '.png'
    logo_dir = UPLOAD_DIR / 'project_logo'
    logo_dir.mkdir(parents=True, exist_ok=True)

    filename = f'{uuid.uuid4().hex}{ext}'
    file_path = logo_dir / filename

    with open(file_path, 'wb') as f:
        f.write(content)

    logo_url = f'/api/v1/files/project_logo/{filename}'
    request.app.state.config.AIBI_PROJECT_LOGO = logo_url

    return {'logo_url': logo_url}


############################
# DELETE /api/v1/configs/project/logo — Remove logo
############################


@router.delete('/project/logo')
async def delete_project_logo(request: Request, user=Depends(get_admin_user)):
    current_url = request.app.state.config.AIBI_PROJECT_LOGO
    if current_url:
        try:
            filename = current_url.split('/')[-1]
            file_path = UPLOAD_DIR / 'project_logo' / filename
            if file_path.exists():
                file_path.unlink()
        except Exception as e:
            log.warning(f'Failed to delete project logo file: {e}')

    request.app.state.config.AIBI_PROJECT_LOGO = ''

    return {'logo_url': None}
