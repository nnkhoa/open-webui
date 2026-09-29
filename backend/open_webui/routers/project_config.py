import logging
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from open_webui.config import UPLOAD_DIR
from open_webui.models.config import Config
from open_webui.utils.auth import get_admin_user
from pydantic import BaseModel

router = APIRouter()

log = logging.getLogger(__name__)

PROJECT_LOGO_DIR = UPLOAD_DIR / 'project_logo'

# Config key <-> response field. The keys are the ones the 0.8.x builds used,
# so settings carried over by the legacy config import keep working.
CONFIG_KEYS = {
    'logo_url': 'aibi.project.logo_url',
    'model_display_names': 'aibi.project.model_display_names',
    'brand_color': 'aibi.project.brand_color',
    'org_name': 'aibi.project.org_name',
    'org_subtitle': 'aibi.project.org_subtitle',
    'app_name': 'aibi.project.app_name',
    'enable_new_chat_on_model_change': 'ui.enable_new_chat_on_model_change',
}

ALLOWED_LOGO_TYPES = {
    'image/png',
    'image/jpeg',
    'image/svg+xml',
    'image/webp',
    'image/gif',
}


############################
# Project Config Models
############################


class ProjectConfigForm(BaseModel):
    logo_url: Optional[str] = None
    model_display_names: Optional[dict[str, str]] = None
    brand_color: Optional[str] = None
    org_name: Optional[str] = None
    org_subtitle: Optional[str] = None
    app_name: Optional[str] = None
    enable_new_chat_on_model_change: Optional[bool] = None


async def get_project_config_values() -> dict:
    values = await Config.get_many(*CONFIG_KEYS.values())
    return {field: values.get(key) for field, key in CONFIG_KEYS.items()}


def resolve_logo_path(logo_url: str) -> Optional[Path]:
    """Map a stored logo url to its file, refusing anything outside the logo dir."""
    filename = Path(logo_url).name
    if not filename or filename in ('.', '..'):
        return None

    file_path = (PROJECT_LOGO_DIR / filename).resolve()
    if file_path.parent != PROJECT_LOGO_DIR.resolve():
        return None

    return file_path


############################
# GET /api/v1/configs/project
############################


@router.get('/project')
async def get_project_config(user=Depends(get_admin_user)):
    return await get_project_config_values()


############################
# POST /api/v1/configs/project
############################


@router.post('/project')
async def set_project_config(
    form_data: ProjectConfigForm,
    user=Depends(get_admin_user),
):
    # exclude_unset: a field the client left out keeps its stored value instead
    # of being wiped to None.
    data = form_data.model_dump(exclude_unset=True)

    updates = {CONFIG_KEYS[field]: value for field, value in data.items() if field in CONFIG_KEYS}
    if updates:
        await Config.upsert(updates)

    return await get_project_config_values()


############################
# POST /api/v1/configs/project/logo — Upload logo
############################


@router.post('/project/logo')
async def upload_project_logo(
    file: UploadFile = File(...),
    user=Depends(get_admin_user),
):
    if file.content_type not in ALLOWED_LOGO_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f'Invalid file type: {file.content_type}. Allowed: {ALLOWED_LOGO_TYPES}',
        )

    content = await file.read()

    ext = Path(file.filename or 'logo.png').suffix or '.png'
    PROJECT_LOGO_DIR.mkdir(parents=True, exist_ok=True)

    filename = f'{uuid.uuid4().hex}{ext}'
    with open(PROJECT_LOGO_DIR / filename, 'wb') as f:
        f.write(content)

    logo_url = f'/api/v1/files/project_logo/{filename}'
    await Config.upsert({CONFIG_KEYS['logo_url']: logo_url})

    return {'logo_url': logo_url}


############################
# DELETE /api/v1/configs/project/logo — Remove logo
############################


@router.delete('/project/logo')
async def delete_project_logo(user=Depends(get_admin_user)):
    current_url = await Config.get(CONFIG_KEYS['logo_url'])
    if current_url:
        try:
            file_path = resolve_logo_path(current_url)
            if file_path and file_path.exists():
                file_path.unlink()
        except Exception as e:
            log.warning(f'Failed to delete project logo file: {e}')

    await Config.upsert({CONFIG_KEYS['logo_url']: ''})

    return {'logo_url': None}
