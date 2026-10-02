"""Sổ tay của portal — SQLite.

Giữ những thứ portal phải biết **trước khi** có bất kỳ PostgreSQL nào: tài
khoản, nhóm thông tin, số hiệu bảng dữ liệu, và chuỗi kết nối tới kho dữ liệu. Cất chuỗi
kết nối tới PostgreSQL ở bên trong chính PostgreSQL đó là vòng luẩn quẩn —
không đăng nhập được để mà đi sửa khi nó sai.

Một yêu cầu web = một kết nối mới = một giao dịch. Kết nối SQLite mở tốn cỡ
micro giây nên không cần nhóm kết nối; đổi lại, không bao giờ dính lỗi dùng
chung kết nối giữa các luồng của uvicorn.

Ghi dùng `BEGIN IMMEDIATE`: SQLite chỉ cho một người ghi tại một thời điểm, và
xin quyền ghi **ngay từ đầu** giao dịch thì hai yêu cầu cùng ghi sẽ xếp hàng
sạch sẽ. Nếu để SQLite tự nâng cấp khoá giữa chừng, người đến sau bị
`SQLITE_BUSY` khi đã đọc xong một nửa — lỗi chỉ hiện dưới tải, khó lần ra.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

# Cột khai kiểu TEXT_TS được trả về thẳng thành `datetime` có múi giờ, nên
# `app/format.py` và các template không phải biết dữ liệu đến từ đâu. Không
# dùng bộ chuyển mặc định của Python (đã bị khai tử từ 3.12).
sqlite3.register_converter(
    "TEXT_TS", lambda raw: datetime.fromisoformat(raw.decode().replace("Z", "+00:00")))
def _ra_chuoi(gt: datetime) -> str:
    """Ghi thời điểm đúng **ba** chữ số phần lẻ giây, như `strftime('%f')` của SQLite.

    Không phải chuyện thẩm mỹ. Giá trị mặc định trong lược đồ do SQLite sinh ra
    ('...:09.922Z'), giá trị do Python ghi vào thì có sáu chữ số
    ('...:09.922000Z'). Hai dạng này so sánh chuỗi ra kết quả **ngược**: ký tự
    '0' đứng trước 'Z' trong bảng mã, nên '...922000Z' < '...922Z'. Mọi câu
    `WHERE expires_at > ...` sẽ sai một cách im lặng, và chỉ sai với những dòng
    vô tình rơi vào đúng mili giây đó. Viết cùng một dạng là hết.
    """
    gt = (gt if gt.tzinfo else gt.replace(tzinfo=UTC)).astimezone(UTC)
    return gt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{gt.microsecond // 1000:03d}Z"


sqlite3.register_adapter(datetime, _ra_chuoi)

# Thời điểm "bây giờ" theo đúng dạng trên, dùng thẳng trong câu SQL.
BAY_GIO = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"


# Tên tệp nâng cấp được ghép thẳng vào câu SQL (giá trị không đặt tham số được
# khi dùng `executescript`), nên soi lại trước khi ghép.
TEN_BUOC = re.compile(r"^[0-9a-z_]+$")


class SoTay:
    """Bọc tệp SQLite. Tạo một lần ở composition root, truyền qua constructor."""

    def __init__(self, duong_dan: Path, thu_muc_nang_cap: Path) -> None:
        self.duong_dan = duong_dan
        self._thu_muc_nang_cap = thu_muc_nang_cap

    def mo(self) -> None:
        """Tạo tệp nếu chưa có, rồi chạy các bước nâng cấp còn thiếu."""
        self.duong_dan.parent.mkdir(parents=True, exist_ok=True)
        with self._ket_noi() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            self._nang_cap(conn)
        # Tệp chứa băm mật khẩu và mật khẩu kết nối kho: chỉ chủ tệp đọc được.
        self.duong_dan.chmod(0o600)

    def dong(self) -> None:
        """Không giữ kết nối nào giữa các yêu cầu nên không có gì để đóng."""

    @contextmanager
    def giao_dich(self) -> Iterator[sqlite3.Connection]:
        """Một giao dịch. Ra khỏi khối không lỗi thì COMMIT."""
        conn = self._ket_noi()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.rollback()
                raise
            conn.commit()
        finally:
            conn.close()

    def _ket_noi(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.duong_dan,
            detect_types=sqlite3.PARSE_DECLTYPES,
            isolation_level=None,        # tự điều khiển BEGIN/COMMIT
            timeout=15.0,                # chờ người ghi khác, thay vì báo bận ngay
            # FastAPI mở giao dịch trong `Depends` (chạy ở threadpool) rồi giao
            # cho hàm route; route khai `async def` thì thân hàm chạy trên luồng
            # event loop — **khác luồng**. Mặc định `sqlite3` chặn việc này và
            # ném `ProgrammingError`, nên mọi thao tác ghi (đều là `async def`
            # vì phải `await` kiểm tra CSRF) sẽ hỏng.
            #
            # Tắt được vì điều kiện an toàn thật sự vẫn giữ: mỗi yêu cầu có
            # kết nối riêng, và trong một yêu cầu không có hai luồng nào dùng
            # nó cùng lúc — `Depends` chạy xong mới tới thân route. Kết nối
            # không bao giờ được cất ra ngoài phạm vi `giao_dich()`.
            check_same_thread=False,
        )
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _nang_cap(self, conn: sqlite3.Connection) -> None:
        """Chạy các bước nâng cấp còn thiếu, mỗi bước là một giao dịch trọn vẹn.

        Hai cái bẫy của `sqlite3` phải tránh ở đây:

        1. `executescript()` **tự COMMIT** mọi giao dịch đang mở trước khi chạy.
           Nên bọc nó trong `BEGIN` ... `rollback()` của Python là vô nghĩa: lỗi
           giữa chừng để lại đúng những gì đã chạy xong, và lần khởi động sau
           gặp "table ... already exists". Cách đúng là để chính đoạn kịch bản
           mang `BEGIN`/`COMMIT` của nó.

        2. Khoá ngoại phải **tắt** trong lúc nâng cấp. SQLite không đổi được
           kiểu cột tại chỗ, nên bước nào đổi kiểu cũng phải dựng bảng mới rồi
           bỏ bảng cũ — mà `DROP TABLE` khi khoá ngoại đang bật sẽ xoá lây sang
           bảng con (`auth_session` biến mất theo `auth_app_user`). `PRAGMA
           foreign_keys` không có tác dụng bên trong giao dịch, nên phải đặt
           trước.
        """
        conn.execute(
            "CREATE TABLE IF NOT EXISTS so_tay_migration ("
            " version integer PRIMARY KEY,"
            " name text NOT NULL,"
            " applied_at TEXT_TS NOT NULL"
            " DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')))")
        da_chay = {r[0] for r in conn.execute("SELECT version FROM so_tay_migration")}

        con_thieu = [t for t in sorted(self._thu_muc_nang_cap.glob("*.sql"))
                     if int(t.name[:4]) not in da_chay]
        if not con_thieu:
            return

        conn.execute("PRAGMA foreign_keys = OFF")
        try:
            for tep in con_thieu:
                so, ten = int(tep.name[:4]), tep.stem
                if not TEN_BUOC.match(ten):
                    raise ValueError(f"Tên bước nâng cấp không hợp lệ: {ten!r}")
                conn.executescript(
                    "BEGIN;\n"
                    + tep.read_text(encoding="utf-8")
                    + f"\nINSERT INTO so_tay_migration (version, name) "
                      f"VALUES ({so}, '{ten}');\nCOMMIT;"
                )
            lech = conn.execute("PRAGMA foreign_key_check").fetchall()
            if lech:
                raise RuntimeError(f"Nâng cấp sổ tay làm hỏng khoá ngoại: {lech[:5]}")
        finally:
            conn.execute("PRAGMA foreign_keys = ON")
