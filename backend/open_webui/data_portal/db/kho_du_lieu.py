"""Kho dữ liệu PostgreSQL — địa chỉ đến từ sổ tay, đổi được lúc đang chạy.

Khác biệt với `pool.Database`: lớp này chấp nhận **chưa có kho nào**. Portal
phải đăng nhập được, quản lý được tài khoản và nhóm thông tin trước khi
biết cơ sở dữ liệu nằm ở đâu — nếu không thì không có đường nào để đi cấu hình
nó. Màn hình nào cần dữ liệu thật thì gọi `bat_buoc()` và nhận `ChuaCauHinhKho`,
một tình trạng có lối thoát, chứ không phải một trang 500 cụt.

Đổi kết nối là thao tác hiếm (quản trị bấm Lưu ở màn Cấu hình database) nhưng
xảy ra khi portal đang phục vụ. Nhóm kết nối cũ được đóng sau khi nhóm mới đã
mở thành công, nên một cấu hình sai không làm mất kết nối đang dùng được.

Kho **tự nối lại**. Cơ sở dữ liệu chạy trong Docker nên nó tắt, khởi động lại,
hoặc chưa kịp sẵn sàng lúc portal lên là chuyện bình thường. Nếu chỉ thử đúng
một lần lúc khởi động thì portal đứng ở trạng thái "Chưa kết nối" mãi dù kho đã
sống lại, và quản trị phải vào bấm Lưu một cấu hình không hề đổi — vô lý.

Thử lại có nhịp (`CHO_THU_LAI` giây) chứ không thử mỗi yêu cầu: kho chết mà mỗi
lần tải trang lại chờ hết thời gian kết nối thì cả portal đứng theo.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg_pool import ConnectionPool, PoolTimeout

from ..errors import ChuaCauHinhKho

# Khoảng cách tối thiểu giữa hai lần tự thử nối lại.
CHO_THU_LAI = 5.0

# Thời gian chờ khi tự thử lại. Ngắn hơn hẳn lúc quản trị bấm Lưu: lần đó người
# dùng đang ngồi đợi và muốn biết kết quả thật, còn lần này chỉ là thăm dò nền
# — chờ lâu thì mỗi lần tải trang bị treo theo.
CHO_TU_THU = 3.0
CHO_NGUOI_BAM = 10.0


class KhoDuLieu:
    """Bọc nhóm kết nối PostgreSQL có thể vắng mặt hoặc bị thay giữa chừng."""

    def __init__(self) -> None:
        self._pool: ConnectionPool | None = None
        self._dsn: str | None = None
        # Địa chỉ **đáng lẽ** phải nối tới. Giữ cả khi đang đứt, để còn biết
        # đường thử lại mà không phải đọc sổ tay mỗi lần.
        self._dsn_mong_muon: str | None = None
        self._thu_luc = 0.0
        self._ly_do: str = "Chưa trỏ Data Portal tới cơ sở dữ liệu nào."
        # Đổi kết nối và mượn kết nối có thể xảy ra cùng lúc trên hai luồng
        # khác nhau của uvicorn; khoá giữ cho không ai đọc `_pool` ở giữa lúc
        # nó đang bị thay.
        self._khoa = threading.Lock()

    @property
    def da_cau_hinh(self) -> bool:
        return self._pool is not None

    @property
    def ly_do(self) -> str:
        """Vì sao chưa dùng được — hiện thẳng lên màn hình."""
        return self._ly_do

    @property
    def dsn(self) -> str | None:
        return self._dsn

    def can_thu_lai(self) -> bool:
        """Đang đứt, biết địa chỉ cần nối, và đã đủ lâu kể từ lần thử trước."""
        return (self._pool is None
                and self._dsn_mong_muon is not None
                and time.monotonic() - self._thu_luc >= CHO_THU_LAI)

    def thu_va_doi(self, dsn: str, cho: float = CHO_NGUOI_BAM) -> None:
        """Mở nhóm kết nối mới, chỉ bỏ nhóm cũ khi nhóm mới đã chạy được.

        Ném `psycopg.Error` nếu không kết nối được — người gọi dịch sang câu
        tiếng Việt cho màn hình.
        """
        # Ghi mốc **trước** khi thử: hai yêu cầu đến cùng lúc thì chỉ một cái
        # phải chờ, cái còn lại thấy chưa tới nhịp và đi tiếp ngay.
        self._thu_luc = time.monotonic()
        self._dsn_mong_muon = dsn
        moi = ConnectionPool(dsn, min_size=1, max_size=8, open=False,
                             kwargs={"autocommit": False})
        try:
            moi.open(wait=True, timeout=cho)
        except BaseException:
            moi.close()
            raise
        with self._khoa:
            cu, self._pool, self._dsn = self._pool, moi, dsn
            self._ly_do = ""
        if cu is not None:
            cu.close()

    def ngat(self, ly_do: str, quen_dia_chi: bool = False) -> None:
        """Bỏ kết nối hiện tại.

        `quen_dia_chi=True` khi quản trị chủ động xoá cấu hình — lúc đó không
        còn gì để tự thử lại. Kho chỉ tạm chết thì giữ địa chỉ để còn nối lại.
        """
        with self._khoa:
            cu, self._pool, self._dsn = self._pool, None, None
            self._ly_do = ly_do
            if quen_dia_chi:
                self._dsn_mong_muon = None
        if cu is not None:
            cu.close()

    def dong(self) -> None:
        self.ngat("Portal đang tắt.", quen_dia_chi=True)

    def con_song(self) -> bool:
        """Hỏi thật kho một câu, thay vì tin là còn nối.

        `da_cau_hinh` chỉ nói "có nhóm kết nối", không nói máy chủ còn sống:
        tắt container xong màn hình vẫn báo "Đang kết nối" cho tới khi có ai đó
        chạy một truy vấn thật. Màn Cấu hình database là chỗ người dùng vào để
        biết sự thật, nên ở đó phải hỏi.

        Hỏi hỏng thì đánh dấu đứt luôn, **giữ địa chỉ** — `noi_lai_neu_can` sẽ
        tự nối lại khi kho sống dậy.
        """
        with self._khoa:
            pool = self._pool
        if pool is None:
            return False
        try:
            with pool.connection() as conn:
                conn.execute("SELECT 1")
        except (psycopg.Error, PoolTimeout) as e:
            self.ngat(f"Mất kết nối tới cơ sở dữ liệu: {_dong_dau(e)}")
            return False
        return True

    def bat_buoc(self) -> ConnectionPool:
        with self._khoa:
            if self._pool is None:
                raise ChuaCauHinhKho(ly_do=self._ly_do)
            return self._pool

    @contextmanager
    def giao_dich(self) -> Iterator[psycopg.Connection]:
        """Một giao dịch. Ra khỏi khối không lỗi thì COMMIT."""
        with self.bat_buoc().connection() as conn:
            yield conn


def _dong_dau(e: Exception) -> str:
    """Dòng đầu của câu lỗi — phần sau chỉ lặp lại cho từng địa chỉ đã thử."""
    dong = [d.strip() for d in str(e).splitlines() if d.strip()]
    return dong[0] if dong else e.__class__.__name__
