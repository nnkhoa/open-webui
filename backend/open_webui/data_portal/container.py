"""Composition root — nơi duy nhất tạo và nối các đối tượng dùng chung.

Không biến toàn cục tự quản lý, không Singleton: mọi thứ được tạo ở đây một lần
lúc khởi động và truyền xuống. Thứ gắn với một yêu cầu (kết nối, giao dịch,
người dùng) thì tạo mới mỗi yêu cầu, ở `web/deps.py`.

Hai kho lưu trữ, hai vòng đời khác hẳn nhau:

    so_tay  SQLite, luôn có, luôn mở được. Tài khoản, nhóm thông tin, và địa chỉ
            của kho dữ liệu.
    kho     PostgreSQL, **có thể chưa có**. Bảng bronze/silver/gold và sổ ghi
            mỗi lần nạp. Địa chỉ đọc từ sổ tay, đổi được lúc đang chạy.

Portal khởi động được khi kho chưa cấu hình hoặc đang tắt — nếu không thì
không có đường nào vào màn Cấu hình database để sửa.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import psycopg

from .config import Settings, doc_cau_hinh
from .db import kho_du_lieu
from .db.kho_du_lieu import KhoDuLieu
from .db.sotay import SoTay
from .domain import ket_noi_kho
from .errors import ChuaCauHinhKho, MigrationError
from .migrate import ledger
from .registry import sync
from .registry.loader import FormRegistry, doc_thu_muc


@dataclass
class Container:
    settings: Settings
    so_tay: SoTay
    kho: KhoDuLieu
    registry: FormRegistry

    def dong(self) -> None:
        self.kho.dong()
        self.so_tay.dong()

    def noi_lai_kho(self, so, cho: float = kho_du_lieu.CHO_NGUOI_BAM) -> None:
        """Thử kết nối lại kho theo cấu hình đang lưu trong sổ tay.

        Gọi lúc khởi động và sau mỗi lần quản trị lưu cấu hình mới. Không ném
        lỗi: kho tắt là chuyện bình thường, portal vẫn phải lên để người ta vào
        sửa được. Lý do hỏng được giữ lại trong `kho.ly_do` để hiện ra màn hình.

        Sổ tay chưa có cấu hình thì lùi về `DATA_PORTAL_DATABASE_URL`. Biến môi
        trường là **mồi cho lần đầu**, không phải nguồn chuẩn: từ lúc quản trị bấm
        Lưu ở màn Cấu hình database thì sổ tay thắng.
        """
        cau_hinh = ket_noi_kho.doc(so)
        dsn = cau_hinh.dsn if cau_hinh else self.settings.database_url_mac_dinh
        mo_ta = cau_hinh.mo_ta if cau_hinh else dsn
        if not dsn:
            self.kho.ngat("Chưa trỏ Data Portal tới cơ sở dữ liệu nào.", quen_dia_chi=True)
            return
        try:
            self.kho.thu_va_doi(dsn, cho=cho)
        except psycopg.Error as e:
            ly_do = ket_noi_kho.doc_loi(e)
            self.kho.ngat(f"Không kết nối được tới {mo_ta}: {ly_do}".strip())
            return
        try:
            self.dung_kho(so)
        except (psycopg.Error, MigrationError) as e:
            self.kho.ngat(f"Đã kết nối tới {mo_ta} nhưng không dựng được bảng: {e}")

    def noi_lai_neu_can(self, so) -> None:
        """Thử nối lại kho khi đang đứt — gọi ở mỗi yêu cầu, rẻ.

        Kho chạy trong Docker: nó tắt, khởi động lại, hoặc chưa kịp sẵn sàng
        lúc portal lên là chuyện thường. Không có bước này thì một lần hỏng là
        portal báo "Chưa kết nối" mãi dù kho đã sống lại, và quản trị phải vào bấm
        Lưu một cấu hình không hề đổi.

        `can_thu_lai()` giữ nhịp, nên kho chết thật cũng không làm mỗi lần tải
        trang phải ngồi chờ hết thời gian kết nối.
        """
        if self.kho.can_thu_lai():
            self.noi_lai_kho(so, cho=kho_du_lieu.CHO_TU_THU)

    @contextmanager
    def giao_dich_kho(self) -> Iterator[psycopg.Connection]:
        """Một giao dịch kho cho tầng API; kho chưa cấu hình hoặc vừa đứt kết nối
        thì ném `ChuaCauHinhKho` — tình trạng có lối thoát, không phải lỗi 500.

        Chỉ lỗi **kết nối** mới đánh dấu kho là đứt; lỗi truy vấn đi tiếp tới bộ
        bắt lỗi chung.
        """
        if not self.kho.da_cau_hinh:
            raise ChuaCauHinhKho(ly_do=self.kho.ly_do)
        try:
            with self.kho.giao_dich() as conn:
                yield conn
        except psycopg.OperationalError as e:
            ly_do = ket_noi_kho.doc_loi(e)
            self.kho.ngat(f"Không kết nối được tới cơ sở dữ liệu: {ly_do}")
            raise ChuaCauHinhKho(ly_do=self.kho.ly_do) from e

    def dung_kho(self, so) -> None:
        """Dựng đủ bảng của mọi bộ bảng trên kho, rồi chép khai báo sang.

        Chạy mỗi lần nối được kho: kho mới trỏ tới, hay vừa xoá dựng lại, là có
        ngay các bảng của bộ bảng khai trong mã — người dùng chọn nhóm thông tin là nạp
        được, không phải qua bước khởi tạo nào. Bước đã chạy thì bỏ qua.
        """
        with self.kho.giao_dich() as conn:
            ledger.ap_dung(conn, self.settings.migrations_dir, nguoi_chay="portal")
            sync.chieu_lai(so, conn)


def dung(settings: Settings | None = None, mo_ket_noi: bool = True) -> Container:
    """Khai báo bảng đọc từ `khai_bao/forms/` — nguồn chuẩn duy nhất.

    Mỗi lần khởi động ghi khai báo đó vào sổ tay, để `form_id`, `table_id` có
    sẵn cho sổ ghi mỗi lần nạp trỏ vào.
    """
    settings = settings or doc_cau_hinh()
    container = Container(
        settings=settings,
        so_tay=SoTay(settings.so_tay_path, settings.so_tay_migrations_dir),
        kho=KhoDuLieu(),
        registry=doc_thu_muc(settings.registry_dir),
    )
    if not mo_ket_noi:
        return container

    container.so_tay.mo()
    with container.so_tay.giao_dich() as so:
        sync.dong_bo(so, None, container.registry)
        container.noi_lai_kho(so)
    return container
