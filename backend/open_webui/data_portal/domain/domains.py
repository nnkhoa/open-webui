"""Domain và bộ bảng của nó.

Danh sách nhóm thông tin khai cố định ở `khai_bao/domains.yaml` và được ghi vào sổ tay
lúc khởi động (`registry/sync.py`); ở đây chỉ còn phần đọc.
"""

from __future__ import annotations

from ..db import sql_sotay as qs


def cac_loai_tep(so, domain_id: int) -> list[dict]:
    """Các loại tệp (bộ bảng) của nhóm thông tin, theo thứ tự khai: `[{form_id, code}]`.

    HQKD có một loại tệp, HQ-MAU-GC có hai (mục 5.1). Rỗng ⇒ nhóm chưa khai loại
    tệp, hiện màn trống "Chưa có thông tin" (QT-01).
    """
    return qs.query(
        so,
        "SELECT f.form_id, f.code FROM ctl_domain_form df "
        "  JOIN ctl_form f ON f.form_id = df.form_id "
        " WHERE df.domain_id = ? ORDER BY df.thu_tu, f.form_id",
        (domain_id,))


def bo_bang(so, domain_id: int) -> dict | None:
    """Bộ bảng nhóm thông tin dùng: `{form_id, code}`, hoặc None nếu nhóm thông tin chưa có."""
    return qs.query_one(
        so,
        "SELECT f.form_id, f.code FROM ctl_domain_form df "
        "  JOIN ctl_form f ON f.form_id = df.form_id "
        " WHERE df.domain_id = ? ORDER BY df.thu_tu, f.form_id LIMIT 1",
        (domain_id,))
