"""Đọc lần nạp cho API JSON — màn Lịch sử nạp (MH-20), Chi tiết lần nạp (MH-21),
Kết quả (MH-12).

Mọi truy vấn danh sách đều giới hạn theo `domain_id` của nhóm thông tin đang chọn.
Số trả về dạng số, thời gian dạng `datetime` (tầng API đổi sang ISO 8601).
"""

from __future__ import annotations

from ..db import sql as q
from ..registry.loader import FormRegistry

TRANG_THAI = ("success", "rejected", "mismatch", "rolled_back")


def danh_sach(conn, domain_id: int, *, nam: int | None = None, form_id: int | None = None,
              trang_thai: str = "", nguoi: str = "", tim: str = "",
              trang: int = 1, moi: int = 25) -> tuple[list[dict], int]:
    """Lần nạp của nhóm, mới nhất ở trên. Trả `(các dòng, tổng số dòng khớp lọc)`."""
    dk = ["l.domain_id = %s", "l.status <> 'running'"]
    tham: list = [domain_id]
    if nam is not None:
        dk.append("l.nam = %s")
        tham.append(nam)
    if form_id is not None:
        dk.append("l.form_id = %s")
        tham.append(form_id)
    if trang_thai:
        dk.append("l.status = %s")
        tham.append(trang_thai)
    if nguoi:
        dk.append("l.actor_username = %s")
        tham.append(nguoi)
    if tim:
        dk.append("(l.load_id::text ILIKE %s OR u.file_name ILIKE %s)")
        tham += [f"%{tim.lstrip('#')}%", f"%{tim}%"]
    where = " AND ".join(dk)
    tong = q.scalar(conn, f"SELECT count(*) FROM ctl.load l "
                          f"JOIN ctl.upload u ON u.upload_id = l.upload_id WHERE {where}", tham)
    hang = q.query(
        conn,
        f"""
        SELECT l.load_id, l.status, l.rows_read, l.started_at, l.nam, l.form_id,
               u.file_name, f.code AS form_code, f.label AS form_label,
               coalesce(l.actor_username, '—') AS nguoi
          FROM ctl.load l
          JOIN ctl.upload u ON u.upload_id = l.upload_id
          JOIN ctl.form f   ON f.form_id = l.form_id
         WHERE {where}
         ORDER BY l.load_id DESC
         LIMIT %s OFFSET %s
        """,
        [*tham, moi, (trang - 1) * moi],
    )
    return hang, tong


def nguoi_nap(conn, domain_id: int) -> list[str]:
    """Các tài khoản đã nạp trong nhóm — ô lọc "Người nạp"."""
    return [r["nguoi"] for r in q.query(
        conn, "SELECT DISTINCT actor_username AS nguoi FROM ctl.load "
              " WHERE domain_id = %s AND actor_username IS NOT NULL ORDER BY 1", (domain_id,))]


def chi_tiet(conn, load_id: int) -> dict | None:
    return q.query_one(
        conn,
        """
        SELECT l.load_id, l.status, l.rows_read, l.rows_written, l.sheets_count,
               l.started_at, l.finished_at, l.errors, l.report, l.batch_id,
               l.domain_id, l.form_id, l.nam, l.kiem_tra, l.cac_buoc, l.doi_chieu,
               u.file_name, u.size_bytes, u.storage_uri,
               f.code AS form_code, d.code AS domain_code,
               coalesce(l.actor_username, '—') AS nguoi
          FROM ctl.load l
          JOIN ctl.upload u ON u.upload_id = l.upload_id
          JOIN ctl.form f   ON f.form_id = l.form_id
          JOIN ctl.domain d ON d.domain_id = l.domain_id
         WHERE l.load_id = %s AND l.status <> 'running'
        """,
        (load_id,),
    )


def pham_vi_thang(lan_nap: dict) -> str | None:
    """"1 → 7" — tháng của lần nạp thành công; lần không thành công không có."""
    if lan_nap["status"] != "success":
        return None
    thang = sorted({int(k) for b in (lan_nap.get("kiem_tra") or {}).get("bang", [])
                    for k in (b.get("theo_ky") or {}) if str(k).isdigit()})
    if not thang:
        return None
    return str(thang[0]) if len(thang) == 1 else f"{thang[0]} → {thang[-1]}"


def so_dong_ghi(lan_nap: dict) -> int:
    """Số dòng đã vào database: dòng ghi mới cộng dòng y hệt bản đang có."""
    if lan_nap["status"] != "success":
        return 0
    bang = ((lan_nap.get("report") or {}).get("tables") or {}).values()
    return sum(int(b.get("rows_silver", 0)) + int(b.get("rows_unchanged", 0)) for b in bang)


def bang_chinh(registry: FormRegistry, form_code: str) -> str | None:
    """Bảng mở bằng nút "Xem dữ liệu vừa nạp": bảng số liệu đầu tiên của loại tệp."""
    form = registry.form(form_code)
    fact = [t for t in form.tables_hien_thi if not t.is_dim]
    return (fact or form.tables_hien_thi)[0].name


def danh_sach_loi(lan_nap: dict) -> list[dict]:
    """Bảng "Lỗi cần sửa": Sheet · Vị trí · Vấn đề · Cách xử lý."""
    return [{"sheet": e.get("sheet"), "vi_tri": e.get("position"),
             "van_de": e.get("issue"), "cach_xu_ly": e.get("fix")}
            for e in (lan_nap.get("errors") or [])]
