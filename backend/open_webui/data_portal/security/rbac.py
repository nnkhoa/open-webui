"""Phân quyền: vai trò × nhóm thông tin.

Quy tắc bất di bất dịch: **không route nào truy vấn `bronze`/`silver`/`gold` mà
không kèm `domain_id` của nhóm thông tin đang chọn** trong mệnh đề WHERE — lọc ở tầng
ứng dụng nghĩa là dữ liệu đã rời cơ sở dữ liệu rồi mới bị chặn.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..db import sql_sotay as qs
from ..errors import KhongCoQuyen


@dataclass(frozen=True)
class Domain:
    domain_id: int
    code: str
    name: str
    description: str | None

    @property
    def chu_viet_tat(self) -> str:
        return viet_tat(self.name)


def domain_thay_duoc(so) -> list[Domain]:
    """Các nhóm thông tin đang hoạt động, theo thứ tự khai trong `khai_bao/domains.yaml`.

    Mọi tài khoản thấy mọi nhóm thông tin đang hoạt động; phân quyền theo nhóm thông tin chưa
    có yêu cầu.
    """
    rows = qs.query(
        so,
        "SELECT domain_id, code, name, description FROM ctl_domain "
        " WHERE status = 'active' ORDER BY domain_id",
    )
    return [Domain(**r) for r in rows]


def bat_buoc_domain(cac_domain: list[Domain], code: str) -> Domain:
    """Trả nhóm thông tin, hoặc ném 403 — không tiết lộ nhóm thông tin có tồn tại hay không."""
    for d in cac_domain:
        if d.code == code:
            return d
    raise KhongCoQuyen()


def viet_tat(ten: str) -> str:
    """"Nguyễn Văn A" → "NA"."""
    phan = [p for p in str(ten or "").split() if p]
    if not phan:
        return "?"
    if len(phan) == 1:
        return phan[0][:2].upper()
    return (phan[0][0] + phan[-1][0]).upper()
