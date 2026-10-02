"""Nhật ký hoạt động — `ctl_audit_event` trong sổ tay.

Nguồn duy nhất của bảng "Hoạt động gần đây" ở P02. Ghi ai, làm gì,
lúc nào, trên nhóm thông tin nào — không ghi dữ liệu nhạy cảm, không ghi mật khẩu,
không ghi nội dung tệp.

Nhật ký nằm ở **sổ tay**, không nằm trong kho dữ liệu. "Ai đã đổi chuỗi kết nối
lúc nào" là câu hỏi chỉ trả lời được khi nhật ký không nằm trong chính cái kho
vừa bị đổi. Đổi lại, dòng nhật ký về một lần nạp không nối thẳng sang
`ctl.load` được nữa — phần đó lấy ở bước thứ hai, xem `gan_day`.
"""

from __future__ import annotations

import ipaddress
import json
from typing import Any

from ..db import sql as q
from ..db import sql_sotay as qs


def _dia_chi(gia_tri: str | None) -> str | None:
    """Chuẩn hoá địa chỉ gọi tới, hoặc bỏ trống nếu không phải địa chỉ IP.

    Ghi nhật ký là việc phụ; nó **không được phép** làm hỏng việc chính là đăng
    nhập hay nạp dữ liệu. Không nhận diện được thì bỏ trống, phần còn lại vẫn
    ghi đủ. (SQLite không có kiểu `inet` như PostgreSQL, nhưng vẫn chuẩn hoá ở
    đây để nhật ký không lẫn chuỗi rác.)
    """
    if not gia_tri:
        return None
    try:
        return str(ipaddress.ip_address(gia_tri.strip()))
    except ValueError:
        return None

# Nhãn tiếng Việt của từng hành động, dùng ở cột Trạng thái của bảng Hoạt động
# gần đây. Thêm hành động mới thì thêm một dòng ở đây.
NHAN: dict[str, str] = {
    "auth.login": "Đăng nhập",
    "auth.logout": "Đăng xuất",
    "load.success": "Nạp thành công",
    "load.rejected": "Tệp bị từ chối",
    "load.mismatch": "Lỗi đối chiếu",
    "load.duplicate": "Tệp đã xử lý trước đó",
    "load.rollback": "Gỡ dữ liệu",
    "load.delete_history": "Xoá lịch sử",
    "domain.create": "Tạo nhóm thông tin",
    "domain.delete": "Xoá nhóm thông tin",
    "kho.cau_hinh": "Đổi cấu hình database",
    "kho.ngat": "Bỏ cấu hình database",
    "user.create": "Tạo tài khoản",
    "user.reset_password": "Đặt lại mật khẩu",
    "user.lock": "Khoá tài khoản",
    "user.unlock": "Mở khoá tài khoản",
}


def ghi(so, *, action: str, actor_user_id: int | None, actor_username: str | None,
        domain_id: int | None = None, object_type: str | None = None,
        object_id: str | None = None, request_id: str | None = None,
        ip: str | None = None, user_agent: str | None = None,
        detail: dict[str, Any] | None = None) -> None:
    qs.execute(
        so,
        """
        INSERT INTO ctl_audit_event (actor_user_id, actor_username, domain_id, action,
                                     object_type, object_id, request_id, ip, user_agent,
                                     detail)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (actor_user_id, actor_username, domain_id, action, object_type, object_id,
         request_id, _dia_chi(ip), (user_agent or "")[:500],
         json.dumps(detail or {}, ensure_ascii=False, default=str)),
    )


def xoa_theo_doi_tuong(so, object_type: str, object_id: str) -> None:
    """Xoá mọi dòng nhật ký về một đối tượng — dùng khi đối tượng bị xoá hẳn
    (lần nạp bị gỡ), để không còn dòng nào trỏ tới thứ không còn tồn tại."""
    qs.execute(so, "DELETE FROM ctl_audit_event WHERE object_type = ? AND object_id = ?",
               (object_type, object_id))


def gan_day(so, conn_kho, domain_id: int, gioi_han: int = 5) -> list[dict]:
    """5 dòng mới nhất cho bảng "Hoạt động gần đây" ở P02.

    Hai bước, vì nhật ký ở sổ tay còn lần nạp ở kho — một câu `JOIN` không bắc
    qua hai cơ sở dữ liệu được:

    1. Đọc nhật ký từ sổ tay.
    2. Với những dòng gắn vào một lần nạp, hỏi kho lấy mã, trạng thái, tên tệp.

    `conn_kho` là `None` khi chưa cấu hình kho hoặc kho đang tắt. Khi đó bảng
    vẫn hiện đủ ai làm gì lúc nào, chỉ trống hai cột Mã và Tệp — thà thiếu hai
    cột còn hơn trắng cả bảng.
    """
    rows = qs.query(
        so,
        """
        SELECT e.event_id, e.at, e.action, e.object_type, e.object_id,
               coalesce(u.display_name, e.actor_username) AS nguoi
          FROM ctl_audit_event e
          LEFT JOIN auth_app_user u ON u.user_id = e.actor_user_id
         WHERE e.domain_id = ?
         ORDER BY e.at DESC
         LIMIT ?
        """,
        (domain_id, gioi_han),
    )
    for r in rows:
        r["nhan_hanh_dong"] = NHAN.get(r["action"], r["action"])
        r["load_id"] = r["status"] = r["file_name"] = None
    _gan_lan_nap(conn_kho, rows)
    return rows


def _gan_lan_nap(conn_kho, rows: list[dict]) -> None:
    """Bổ sung cột Mã và Tệp từ kho cho những dòng nhật ký trỏ vào một lần nạp."""
    if conn_kho is None:
        return
    ma = {int(r["object_id"]): r for r in rows
          if r["object_type"] == "load" and str(r["object_id"] or "").isdigit()}
    if not ma:
        return
    for hang in q.query(
        conn_kho,
        "SELECT l.load_id, l.status, up.file_name "
        "  FROM ctl.load l LEFT JOIN ctl.upload up ON up.upload_id = l.upload_id "
        " WHERE l.load_id = ANY(%s)",
        (list(ma),),
    ):
        dong = ma[hang["load_id"]]
        dong["load_id"] = hang["load_id"]
        dong["status"] = hang["status"]
        dong["file_name"] = hang["file_name"]
