"""Cấu hình kết nối tới kho dữ liệu — Quản trị ▸ Cấu hình database.

Một dòng duy nhất trong sổ tay SQLite. Đây là mảnh cấu hình không thể nằm trong
PostgreSQL: nó chính là câu trả lời cho "PostgreSQL ở đâu".

Mật khẩu được cất nguyên văn trong tệp sổ tay. Không mã hoá, và nói thẳng ra
như vậy thay vì bọc một lớp che mắt: khoá giải mã sẽ phải nằm cạnh tệp thì mới
tự khởi động được, nên nó chỉ đổi chỗ vấn đề chứ không giải quyết. Lớp bảo vệ
thật là quyền tệp — `Catalog.open()` đặt sổ tay ở chế độ 0600.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg
from psycopg import conninfo

from ..db import catalog_sql as qs
from ..errors import InvalidInput

CAC_SSLMODE = ("disable", "allow", "prefer", "require", "verify-ca", "verify-full")


@dataclass(frozen=True)
class KetNoi:
    host: str
    port: int
    database: str
    username: str
    password: str
    sslmode: str

    @property
    def dsn(self) -> str:
        """Chuỗi kết nối. Dùng bộ dựng của psycopg để thoát ký tự cho đúng —
        mật khẩu có dấu cách hay dấu nháy là chuyện bình thường."""
        return conninfo.make_conninfo(
            host=self.host, port=self.port, dbname=self.database,
            user=self.username, password=self.password, sslmode=self.sslmode)

    @property
    def mo_ta(self) -> str:
        """Hiện lên màn hình — không bao giờ kèm mật khẩu."""
        return f"{self.username}@{self.host}:{self.port}/{self.database}"


def doc(so) -> KetNoi | None:
    """Cấu hình đang lưu, hoặc None nếu chưa ai cấu hình."""
    hang = qs.query_one(
        so, "SELECT host, port, database, username, password, sslmode "
              "FROM ctl_ket_noi_kho WHERE id = 1")
    return None if hang is None else KetNoi(**hang)


def doc_day_du(so) -> dict | None:
    """Cả cấu hình lẫn kết quả lần thử gần nhất — cho màn hình vẽ."""
    return qs.query_one(
        so, "SELECT host, port, database, username, sslmode, ghi_chu, "
              "       thu_luc, thu_dat, thu_thong_diep, cap_nhat_luc, cap_nhat_boi "
              "FROM ctl_ket_noi_kho WHERE id = 1")


def kiem_tra_dau_vao(host: str, port: str, database: str, username: str,
                     sslmode: str) -> tuple[str, int, str, str, str]:
    """Soi từng ô trước khi thử kết nối, để lỗi hiện ngay cạnh ô sai."""
    loi: dict[str, str] = {}
    host = host.strip()
    database = database.strip()
    username = username.strip()
    sslmode = (sslmode or "prefer").strip()

    if not host:
        loi["host"] = "Chưa nhập địa chỉ máy chủ."
    if not database:
        loi["database"] = "Chưa nhập tên cơ sở dữ liệu."
    if not username:
        loi["username"] = "Chưa nhập tên đăng nhập."
    if sslmode not in CAC_SSLMODE:
        loi["sslmode"] = f"Chỉ nhận: {', '.join(CAC_SSLMODE)}."

    so_cong = 0
    raw = (port or "").strip()
    if not raw:
        loi["port"] = "Chưa nhập cổng."
    else:
        try:
            so_cong = int(raw)
        except ValueError:
            loi["port"] = "Cổng phải là số."
        else:
            if not 1 <= so_cong <= 65535:
                loi["port"] = "Cổng phải nằm trong khoảng 1–65535."

    if loi:
        raise InvalidInput("Cấu hình kết nối chưa hợp lệ.", loi)
    return host, so_cong, database, username, sslmode


def thu(ket_noi: KetNoi) -> tuple[bool, str]:
    """Mở một kết nối thật rồi đóng ngay. Trả (được không, câu giải thích).

    Không nuốt lỗi: mọi `psycopg.Error` được dịch sang câu tiếng Việt và trả
    về cho màn hình, vì "sai mật khẩu" và "máy chủ không chạy" là hai việc
    người dùng phải xử lý khác nhau.
    """
    try:
        with psycopg.connect(ket_noi.dsn, connect_timeout=8) as conn:
            phien_ban = conn.execute("SELECT version()").fetchone()
    except psycopg.OperationalError as e:
        return False, doc_loi(e)
    except psycopg.Error as e:
        return False, f"Cơ sở dữ liệu từ chối: {e}".strip()
    ten = (phien_ban[0] if phien_ban else "").split(" on ")[0]
    return True, f"Kết nối được. {ten}"


# Câu lỗi của psycopg là tiếng Anh, nhiều dòng, và lặp lại một lỗi cho từng địa
# chỉ nó đã thử (IPv4 rồi IPv6). Đổ nguyên si ra màn hình thì người dùng phải
# đọc mười dòng để tìm ra ba chữ có nghĩa. Bảng dưới đây dịch những trường hợp
# thật sự gặp; cái nào chưa có thì rút gọn còn dòng đầu, xem `_gon`.
DICH_LOI: tuple[tuple[tuple[str, ...], str], ...] = (
    (("no password supplied",),
     "Chưa nhập mật khẩu. Cơ sở dữ liệu này bắt buộc phải có mật khẩu."),
    (("password authentication failed",),
     "Sai tên đăng nhập hoặc mật khẩu."),
    (("role", "does not exist"),
     "Không có tên đăng nhập này trên máy chủ."),
    (("database", "does not exist"),
     "Không có cơ sở dữ liệu tên này trên máy chủ."),
    (("connection refused",),
     "Không có gì đang chạy ở cổng đó — kiểm tra container đã chạy chưa, "
     "và số cổng có đúng không."),
    (("could not translate host name",),
     "Không tìm ra máy chủ với tên này."),
    (("timeout",),
     "Máy chủ không trả lời trong 8 giây."),
    (("no pg_hba.conf entry",),
     "Máy chủ từ chối kết nối từ máy này — cần sửa `pg_hba.conf` bên đó."),
)


def doc_loi(e: Exception) -> str:
    thap = str(e).lower()
    for dau_hieu, cau in DICH_LOI:
        if all(d in thap for d in dau_hieu):
            return cau
    return _gon(str(e))



def _gon(cau: str) -> str:
    """Lỗi chưa dịch: lấy dòng đầu, bỏ phần liệt kê từng địa chỉ đã thử."""
    dau = cau.split("Multiple connection attempts failed")[0]
    dong = [d.strip() for d in dau.splitlines() if d.strip()]
    return dong[0] if dong else "Không kết nối được."


def luu(so, ket_noi: KetNoi, *, ghi_chu: str, dat: bool, thong_diep: str,
        nguoi: str) -> None:
    """Ghi đè dòng cấu hình duy nhất, kèm kết quả lần thử vừa rồi."""
    qs.execute(
        so,
        "INSERT INTO ctl_ket_noi_kho "
        "  (id, host, port, database, username, password, sslmode, ghi_chu,"
        "   thu_luc, thu_dat, thu_thong_diep, cap_nhat_luc, cap_nhat_boi) "
        "VALUES (1, ?, ?, ?, ?, ?, ?, ?, "
        "        strftime('%Y-%m-%dT%H:%M:%fZ','now'), ?, ?, "
        "        strftime('%Y-%m-%dT%H:%M:%fZ','now'), ?) "
        "ON CONFLICT (id) DO UPDATE SET "
        "  host = excluded.host, port = excluded.port, database = excluded.database,"
        "  username = excluded.username, password = excluded.password,"
        "  sslmode = excluded.sslmode, ghi_chu = excluded.ghi_chu,"
        "  thu_luc = excluded.thu_luc, thu_dat = excluded.thu_dat,"
        "  thu_thong_diep = excluded.thu_thong_diep,"
        "  cap_nhat_luc = excluded.cap_nhat_luc, cap_nhat_boi = excluded.cap_nhat_boi",
        (ket_noi.host, ket_noi.port, ket_noi.database, ket_noi.username,
         ket_noi.password, ket_noi.sslmode, ghi_chu.strip() or None,
         1 if dat else 0, thong_diep, nguoi))


def xoa(so) -> None:
    qs.execute(so, "DELETE FROM ctl_ket_noi_kho WHERE id = 1")
