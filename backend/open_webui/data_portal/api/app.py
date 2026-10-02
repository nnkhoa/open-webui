"""API JSON của Data Portal (mục 9 đặc tả) — gắn vào Open WebUI ở `/api/v1/data-portal`.

Ứng dụng FastAPI con, chạy ngay trong process Open WebUI, có bộ bắt lỗi riêng: mọi
lỗi trả JSON `{"detail": "<câu tiếng Việt>"}` với mã 401 / 403 / 404 / 409 / 422 /
503, không lẫn với cách trả lỗi của phần còn lại của Open WebUI.

Người gọi là tài khoản Open WebUI đang đăng nhập: `tao_api` nhận hàm xác thực của
Open WebUI và gắn vào `nguoi_dung_hien_tai`.

Tầng này không chạm thẳng psycopg hay openpyxl: dữ liệu đi qua `domain`,
`pipeline`, `sources`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.datastructures import State
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..container import Container, dung
from ..errors import (
    ChuaCauHinhKho,
    ChuaSanSang,
    DuLieuVaoSai,
    KhongTimThay,
    NguonDuLieuError,
    PortalError,
    RegistryError,
)
from ..logging import MA_YEU_CAU
from .deps import NguoiGoi, nguoi_dung_hien_tai, nguoi_goi
from .routes import bang, cau_hinh_db, lan_nap, nap, nhom

DANG_KY = [nhom, nap, lan_nap, bang, cau_hinh_db]

LOI_CHUNG = ("Hệ thống gặp sự cố. Yêu cầu chưa được thực hiện và dữ liệu không bị thay "
             "đổi. Hãy thử lại; nếu vẫn lỗi, gửi mã yêu cầu cho quản trị.")

log = logging.getLogger("data_portal")


def _loi(ma_http: int, thong_diep: str, **them) -> JSONResponse:
    return JSONResponse({"detail": thong_diep, **them}, status_code=ma_http)


def tao_api(xac_thuc: Callable, state: State | None = None,
            container: Container | None = None) -> FastAPI:
    """`xac_thuc`: phụ thuộc FastAPI trả tài khoản đang đăng nhập (có `id`, `name`,
    `email`, `role`). `state`: dùng chung `app.state` của Open WebUI, để hàm xác thực
    thấy đúng những gì nó thấy ở các API khác (Redis kiểm token đã thu hồi…).
    `container` để trống thì gọi `khoi_dong` lúc Open WebUI lên."""
    api = FastAPI(title="Data Portal API", docs_url=None, redoc_url=None, openapi_url=None)
    if state is not None:
        api.state = state
    api.state.data_portal = container
    api.dependency_overrides[nguoi_dung_hien_tai] = xac_thuc
    for mo_dun in DANG_KY:
        api.include_router(mo_dun.router)

    # Đường dẫn không có: vẫn kiểm danh tính trước (401 / 403), rồi mới 404 — người
    # gọi không đăng nhập hay không có quyền không dò được đường dẫn nào tồn tại.
    @api.api_route("/{duong_dan:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                   include_in_schema=False)
    def _khong_co(duong_dan: str, nguoi: NguoiGoi = Depends(nguoi_goi)):
        raise KhongTimThay("Không tìm thấy.")

    _bat_loi(api)
    return api


def khoi_dong(api: FastAPI) -> None:
    """Mở sổ tay, chép khai báo, nối kho. Chạy trong luồng riêng lúc Open WebUI lên;
    kho chưa cấu hình hay đang tắt thì vẫn lên, màn Cấu hình database báo lý do."""
    try:
        api.state.data_portal = dung()
    except Exception:
        log.exception("Data Portal không khởi động được")


def dung_lai(api: FastAPI) -> None:
    container = getattr(api.state, "data_portal", None)
    if container is not None:
        container.dong()
        api.state.data_portal = None


def _bat_loi(api: FastAPI) -> None:
    @api.exception_handler(ChuaSanSang)
    async def _chua_san_sang(request: Request, exc: ChuaSanSang):
        return _loi(503, str(exc))

    @api.exception_handler(ChuaCauHinhKho)
    async def _chua_kho(request: Request, exc: ChuaCauHinhKho):
        return _loi(503, exc.ly_do or "Chưa cấu hình cơ sở dữ liệu.")

    @api.exception_handler(DuLieuVaoSai)
    async def _vao_sai(request: Request, exc: DuLieuVaoSai):
        them = {"theo_o": exc.theo_truong} if exc.theo_truong else {}
        return _loi(422, str(exc), **them)

    @api.exception_handler(NguonDuLieuError)
    async def _nguon(request: Request, exc: NguonDuLieuError):
        return _loi(422, str(exc))

    @api.exception_handler(RegistryError)
    async def _registry(request: Request, exc: RegistryError):
        return _loi(404, "Không tìm thấy.")

    @api.exception_handler(PortalError)
    async def _portal(request: Request, exc: PortalError):
        if exc.ma_http >= 500:
            log.exception("Lỗi nghiệp vụ chưa xử lý riêng: %s", exc)
            return _loi(exc.ma_http, LOI_CHUNG, ma_yeu_cau=MA_YEU_CAU.get())
        return _loi(exc.ma_http, str(exc))

    @api.exception_handler(RequestValidationError)
    async def _tham_so(request: Request, exc: RequestValidationError):
        return _loi(422, "Dữ liệu gửi lên chưa hợp lệ.")

    @api.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            return _loi(404, "Không tìm thấy.")
        if exc.status_code == 405:
            return _loi(405, "Phương thức không được hỗ trợ.")
        return _loi(exc.status_code, str(exc.detail))

    @api.exception_handler(Exception)
    async def _chung(request: Request, exc: Exception):
        log.exception("Lỗi ngoài dự kiến ở API: %s", exc)
        return _loi(500, LOI_CHUNG, ma_yeu_cau=MA_YEU_CAU.get())
