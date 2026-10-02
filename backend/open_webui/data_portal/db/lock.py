"""Khoá theo cặp (nhóm thông tin, khai báo bảng)

Khoá đúng phạm vi ghi:

    · nhóm thông tin A nạp, nhóm thông tin B nạp          → song song
    · nhóm thông tin A nạp hai tệp               → tuần tự (đúng, vì cùng vùng ghi)

Khoá lấy theo **thứ tự tăng dần** để hai tiến trình cần cùng bộ khoá không kẹt
khoá chéo nhau.
"""

from __future__ import annotations

from collections.abc import Iterable

from psycopg import sql

# Không gian khoá riêng của portal, tránh đụng advisory lock của thứ khác.
KHONG_GIAN = 0x4E4243  # 'NBC'


def khoa_ghi(conn, cap: Iterable[tuple[int, int]]) -> None:
    """Lấy khoá trong phạm vi giao dịch cho từng cặp `(domain_id, form_id)`.

    Tự nhả khi giao dịch kết thúc, dù COMMIT hay ROLLBACK.
    """
    sap_xep = sorted(set(cap))
    with conn.cursor() as cur:
        for domain_id, form_id in sap_xep:
            cur.execute(
                sql.SQL("SELECT pg_advisory_xact_lock(%s, %s)"),
                (KHONG_GIAN, (int(domain_id) << 16) | int(form_id)),
            )

