"""Cây ngoại lệ của portal.

Nguyên tắc: lỗi nghiệp vụ là exception có kiểu rõ ràng, lỗi hạ tầng được map ở
adapter. Không `except: pass` ở bất kỳ đâu.

Bộ bắt lỗi tập trung ở `web/errors.py` dịch cây này sang trang P12.
"""

from __future__ import annotations


class PortalError(Exception):
    """Gốc của mọi lỗi portal tự sinh ra."""

    ma_http = 500


class RegistryError(PortalError):
    """Khai báo trong `khai_bao/` sai — phát hiện lúc `registry validate`, không lúc chạy."""


class MigrationError(PortalError):
    """Nâng cấp schema hỏng."""


class NguonDuLieuError(PortalError):
    """Không đọc được tệp nguồn: hỏng, sai định dạng, có mật khẩu."""

    ma_http = 400


class CauTrucError(PortalError):
    """Tệp sai cấu trúc ⇒ từ chối cả tệp. Mang theo danh sách lỗi."""

    ma_http = 400

    def __init__(self, loi: list[dict]) -> None:
        super().__init__(f"Tệp có {len(loi)} lỗi cấu trúc.")
        self.loi = loi


class DoiChieuError(PortalError):
    """Đối chiếu R1–R4 lệch ⇒ huỷ cả giao dịch."""

    def __init__(self, lech: list[dict], cac_buoc: list[dict] | None = None,
                 doi_chieu: dict | None = None) -> None:
        super().__init__(f"Đối chiếu lệch ở {len(lech)} bước.")
        self.lech = lech
        # Các bước A1–B5 và thẻ đối chiếu đã tính trong giao dịch bị huỷ — giữ
        # lại để ghi vào bản ghi lần nạp "Lỗi đối chiếu" ở giao dịch mới.
        self.cac_buoc = cac_buoc
        self.doi_chieu = doi_chieu


class KhongCoQuyen(PortalError):
    """403 — không tiết lộ đối tượng có tồn tại hay không."""

    ma_http = 403

    def __init__(self, thong_diep: str = "Bạn không có quyền thực hiện thao tác này") -> None:
        super().__init__(thong_diep)


class ChuaCoBoBang(PortalError):
    """Domain đang chọn chưa được gắn bộ bảng nào trong `khai_bao/domains.yaml`.

    Là **tình trạng**, không phải lỗi: nhóm thông tin vẫn hiện trong ô chọn, chỉ chưa
    nạp và chưa xem dữ liệu được. Bộ bắt lỗi nói rõ điều đó trong khung ứng dụng.
    """

    def __init__(self, ten_domain: str) -> None:
        super().__init__(f"Nhóm thông tin {ten_domain} chưa có bộ bảng")
        self.ten_domain = ten_domain


class ChuaCauHinhKho(PortalError):
    """Chưa trỏ portal tới cơ sở dữ liệu nào — **không phải thiếu quyền**.

    Sổ tay SQLite luôn có; kho dữ liệu PostgreSQL thì không. Lần đầu dựng
    portal, hoặc khi máy chủ cơ sở dữ liệu tắt, mọi màn đụng tới dữ liệu đều
    không chạy được. Tách hẳn thành một kiểu riêng để bộ bắt lỗi đưa Quản trị
    thẳng tới màn Cấu hình database, thay vì trả một trang 500 không nói gì.

    `ly_do` là câu psycopg trả về khi thử kết nối — nói thẳng "sai mật khẩu"
    hay "máy chủ từ chối" hữu ích hơn nhiều so với "không kết nối được".
    """

    ma_http = 503

    def __init__(self, la_quan_tri: bool = False, ly_do: str = "") -> None:
        super().__init__("Chưa cấu hình cơ sở dữ liệu")
        self.la_quan_tri = la_quan_tri
        self.ly_do = ly_do


class KhongTimThay(PortalError):
    ma_http = 404


class ChuaSanSang(PortalError):
    """503 — Data Portal chưa khởi động xong (đang mở sổ tay, nối kho)."""

    ma_http = 503

    def __init__(self, thong_diep: str = "Data Portal đang khởi động. Thử lại sau ít giây."
                 ) -> None:
        super().__init__(thong_diep)


class XungDot(PortalError):
    """409 — thao tác không hợp với trạng thái hiện tại (ví dụ gỡ lần nạp không
    phải mới nhất, QT-17)."""

    ma_http = 409


class DuLieuVaoSai(PortalError):
    """Người dùng nhập sai ở biểu mẫu. `theo_truong` để hiện lỗi cạnh từng ô."""

    ma_http = 400

    def __init__(self, thong_diep: str, theo_truong: dict[str, str] | None = None) -> None:
        super().__init__(thong_diep)
        self.theo_truong = theo_truong or {}
