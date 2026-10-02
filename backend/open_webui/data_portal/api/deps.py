"""Phụ thuộc dùng chung của tầng API.

Mỗi yêu cầu có: một mã định danh, người gọi (tài khoản Open WebUI đang đăng nhập),
và hai kết nối mở **khi cần** — sổ tay (SQLite) và kho (PostgreSQL). Không mở
trước: sổ tay ghi dùng `BEGIN IMMEDIATE`, giữ nó suốt một lần nạp dài là chặn mọi
yêu cầu khác. Lỗi trong thân route thì cả hai giao dịch cùng ROLLBACK.

Quyền theo cột Quyền của bảng 9.2: `nguoi_goi` (A, L) cho mọi đường dẫn,
`chi_admin` (A) cho gỡ / xoá lịch sử và cấu hình database. Ẩn nút ở giao diện
không thay được chặn ở đây (PCN-01).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack
from dataclasses import dataclass, field

from fastapi import Depends, Request

from ..container import Container
from ..domain import domains
from ..errors import ChuaCauHinhKho, ChuaSanSang, DuLieuVaoSai, KhongCoQuyen
from ..logging import ma_yeu_cau_moi
from ..registry.schema import Form
from ..security.rbac import Domain, domain_thay_duoc

VAI_TRO = ("admin", "data_uploader")
KHONG_CO_QUYEN = "Bạn không có quyền vào Data Portal. Liên hệ Admin nếu cần nạp dữ liệu."


@dataclass(frozen=True)
class NguoiGoi:
    """Người đang gọi API, theo tài khoản Open WebUI."""

    user_id: str
    user_name: str
    role: str

    @property
    def la_admin(self) -> bool:
        return self.role == "admin"


def nguoi_dung_hien_tai():
    """Tài khoản Open WebUI đang đăng nhập.

    `tao_api` thay hàm này bằng hàm xác thực của Open WebUI (`get_verified_user`),
    để gói này không phụ thuộc vào phần còn lại của Open WebUI.
    """
    raise NotImplementedError("Chưa gắn hàm xác thực của Open WebUI (tao_api).")


def nguoi_goi(user=Depends(nguoi_dung_hien_tai)) -> NguoiGoi:
    if user.role not in VAI_TRO:
        raise KhongCoQuyen(KHONG_CO_QUYEN)
    return NguoiGoi(user_id=str(user.id), user_name=user.name or user.email or "",
                    role=user.role)


def chi_admin(nguoi: NguoiGoi = Depends(nguoi_goi)) -> NguoiGoi:
    if not nguoi.la_admin:
        raise KhongCoQuyen()
    return nguoi


def _container(request: Request) -> Container:
    container = getattr(request.app.state, "data_portal", None)
    if container is None:
        raise ChuaSanSang()
    return container


@dataclass
class NguCanhApi:
    container: Container
    nguoi: NguoiGoi
    ma_yeu_cau: str
    _stack: ExitStack
    _so: object = field(default=None)
    _kho: object = field(default=None)

    @property
    def settings(self):
        return self.container.settings

    @property
    def registry(self):
        return self.container.registry

    def so(self):
        """Giao dịch sổ tay, mở ở lần gọi đầu và giữ tới hết yêu cầu."""
        if self._so is None:
            self._so = self._stack.enter_context(self.container.so_tay.giao_dich())
        return self._so

    def noi_lai_neu_can(self) -> None:
        """Kho vừa sống lại (container Docker khởi động xong) thì nối lại ngay."""
        if not self.container.kho.can_thu_lai():
            return
        if self._so is not None:
            self.container.noi_lai_neu_can(self._so)
            return
        with self.container.so_tay.giao_dich() as so:
            self.container.noi_lai_neu_can(so)

    def bat_buoc_kho_san_sang(self) -> None:
        """Kho đã cấu hình — dùng trước những việc tự mở giao dịch riêng (nạp)."""
        self.noi_lai_neu_can()
        if not self.container.kho.da_cau_hinh:
            raise ChuaCauHinhKho(ly_do=self.container.kho.ly_do)

    def kho(self):
        """Giao dịch kho, mở ở lần gọi đầu; chưa cấu hình ⇒ `ChuaCauHinhKho` (503)."""
        if self._kho is None:
            self.noi_lai_neu_can()
            self._kho = self._stack.enter_context(self.container.giao_dich_kho())
        return self._kho

    # -- nhóm thông tin, loại tệp --------------------------------------------- #
    #
    # Đọc sổ tay bằng giao dịch ngắn nếu yêu cầu chưa mở sổ tay: các route nạp gọi
    # tiếp những việc tự mở giao dịch sổ tay (ghi nhật ký), giữ giao dịch ở đây
    # thì hai bên chờ nhau.

    def _doc_so(self, ham):
        if self._so is not None:
            return ham(self._so)
        with self.container.so_tay.giao_dich() as so:
            return ham(so)

    def cac_nhom(self) -> list[Domain]:
        return self._doc_so(domain_thay_duoc)

    def nhom(self, ma: str) -> Domain:
        """Nhóm thông tin đang hoạt động theo mã; sai ⇒ 422."""
        for d in self.cac_nhom():
            if d.code == ma:
                return d
        raise DuLieuVaoSai("Nhóm thông tin không hợp lệ.")

    def cac_loai_tep(self, nhom: Domain) -> list[tuple[int, Form]]:
        hang = self._doc_so(lambda so: domains.cac_loai_tep(so, nhom.domain_id))
        return [(r["form_id"], self.registry.form(r["code"])) for r in hang]


def mo_ngu_canh(request: Request, nguoi: NguoiGoi = Depends(nguoi_goi)
                ) -> Iterator[NguCanhApi]:
    container = _container(request)
    with ExitStack() as stack:
        yield NguCanhApi(container=container, nguoi=nguoi, ma_yeu_cau=ma_yeu_cau_moi(),
                         _stack=stack)


def mo_ngu_canh_admin(request: Request, nguoi: NguoiGoi = Depends(chi_admin)
                      ) -> Iterator[NguCanhApi]:
    container = _container(request)
    with ExitStack() as stack:
        yield NguCanhApi(container=container, nguoi=nguoi, ma_yeu_cau=ma_yeu_cau_moi(),
                         _stack=stack)
