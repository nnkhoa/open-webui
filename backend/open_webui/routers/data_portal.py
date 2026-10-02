"""Data Portal — router chuyển tiếp `/api/v1/data-portal/*` sang portal.

Trình duyệt chỉ gọi Open WebUI. Router này kiểm phiên đăng nhập và vai trò ở phía
máy chủ, rồi chuyển yêu cầu tới `{DATA_PORTAL_URL}/api/...` kèm danh tính người dùng
có chữ ký HMAC-SHA256 bằng khoá dùng chung `DATA_PORTAL_SHARED_SECRET`
(đặc tả Data Portal, mục 3.4, 8.3, 9).
"""

import hashlib
import hmac
import logging
import os
import re
import time
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response, StreamingResponse
from open_webui.utils.auth import get_current_user

log = logging.getLogger(__name__)

router = APIRouter()

DATA_PORTAL_URL = os.environ.get('DATA_PORTAL_URL', 'http://portal:8000').rstrip('/')
DATA_PORTAL_SHARED_SECRET = os.environ.get('DATA_PORTAL_SHARED_SECRET', '')
DATA_PORTAL_TIMEOUT = float(os.environ.get('DATA_PORTAL_TIMEOUT', '600'))

VAI_TRO_DATA_PORTAL = {'admin', 'data_uploader'}

# Đường dẫn chỉ Admin được gọi (cột Quyền = "Chỉ A" ở bảng 9.2).
CHI_ADMIN = [
    (re.compile(r'^db-config(/.*)?$'), None),
    (re.compile(r'^loads/[^/]+$'), {'DELETE'}),
]

# Header được chuyển tiếp hai chiều.
HEADER_GUI = ('content-type', 'accept')
HEADER_NHAN = ('content-type', 'content-disposition', 'cache-control', 'x-so-dong')

KHONG_CO_QUYEN = 'Bạn không có quyền vào Data Portal. Liên hệ Admin nếu cần nạp dữ liệu.'


def _chi_admin(path: str, method: str) -> bool:
    for mau, cac_phuong_thuc in CHI_ADMIN:
        if mau.match(path) and (cac_phuong_thuc is None or method in cac_phuong_thuc):
            return True
    return False


def _ky(user_id: str, user_name: str, role: str, timestamp: str, method: str, path: str) -> str:
    chuoi = f'{user_id}|{user_name}|{role}|{timestamp}|{method}|{path}'
    return hmac.new(DATA_PORTAL_SHARED_SECRET.encode(), chuoi.encode(), hashlib.sha256).hexdigest()


@router.api_route('/{path:path}', methods=['GET', 'POST', 'PUT', 'DELETE'])
async def chuyen_tiep(path: str, request: Request, user=Depends(get_current_user)):
    if user.role not in VAI_TRO_DATA_PORTAL:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=KHONG_CO_QUYEN)

    method = request.method.upper()
    if user.role != 'admin' and _chi_admin(path, method):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=KHONG_CO_QUYEN)

    if not DATA_PORTAL_SHARED_SECRET:
        log.error('DATA_PORTAL_SHARED_SECRET chưa được đặt')
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Data Portal chưa được cấu hình.')

    duong_dan = f'/api/{path}'
    timestamp = str(int(time.time()))
    # Header HTTP chỉ nên chở ASCII: tên có dấu được mã hoá phần trăm, portal ký và giải mã đúng chuỗi này.
    user_name = quote(user.name or user.email or '', safe='')
    headers = {k: v for k, v in request.headers.items() if k.lower() in HEADER_GUI}
    headers.update(
        {
            'X-DP-User-Id': str(user.id),
            'X-DP-User-Name': user_name,
            'X-DP-Role': user.role,
            'X-DP-Timestamp': timestamp,
            'X-DP-Signature': _ky(str(user.id), user_name, user.role, timestamp, method, duong_dan),
        }
    )

    client = httpx.AsyncClient(timeout=DATA_PORTAL_TIMEOUT)
    try:
        yeu_cau = client.build_request(
            method,
            f'{DATA_PORTAL_URL}{duong_dan}',
            params=request.query_params,
            headers=headers,
            content=await request.body() if method in ('POST', 'PUT') else None,
        )
        tra_loi = await client.send(yeu_cau, stream=True)
    except httpx.HTTPError as e:
        await client.aclose()
        log.warning('Không gọi được portal: %s', e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail='Mất kết nối, chưa xác định được kết quả xử lý.',
        )

    headers_tra = {k: v for k, v in tra_loi.headers.items() if k.lower() in HEADER_NHAN}

    async def noi_dung():
        try:
            async for khoi in tra_loi.aiter_raw():
                yield khoi
        finally:
            await tra_loi.aclose()
            await client.aclose()

    if tra_loi.status_code == status.HTTP_204_NO_CONTENT:
        await tra_loi.aclose()
        await client.aclose()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return StreamingResponse(noi_dung(), status_code=tra_loi.status_code, headers=headers_tra)
