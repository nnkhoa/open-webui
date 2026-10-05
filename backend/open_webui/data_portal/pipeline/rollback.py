"""Gỡ dữ liệu của một lần nạp, và xoá lịch sử của lần nạp không còn dữ liệu.

Chi phí tỉ lệ với **kích thước lô**, không tỉ lệ với kích thước kho: chỉ đụng
các dòng mang `batch_id` của lô và các dòng mà lô đó đã thay thế.

Gỡ là **xoá hẳn** mọi thứ của lần nạp: các dòng ở cả ba lớp Bronze, Silver,
Gold, kết quả đối chiếu, bản ghi lần nạp và tệp đã tải lên. Dòng mà lô này đã
thay (cùng tháng hoặc cùng mã, của lần nạp trước) được dùng lại.
"""

from __future__ import annotations

from psycopg import sql

from ..db import sql as q
from ..db.lock import acquire_write_locks
from ..errors import InvalidInput
from ..registry.loader import FormRegistry

# Trạng thái lần nạp xoá được khỏi lịch sử: không có dòng dữ liệu nào.
# `rolled_back` là lần nạp gỡ từ trước khi gỡ xoá hẳn bản ghi — còn sót lại.
XOA_DUOC = ("rejected", "mismatch", "rolled_back")


def co_go_duoc(conn, load_id: int) -> tuple[bool, str]:
    """Chỉ gỡ được lần nạp thành công và là lô **mới nhất** của nhóm thông tin. Muốn gỡ
    lần nạp cũ hơn thì gỡ các lần sau trước."""
    lan_nap = q.query_one(
        conn, "SELECT load_id, status, batch_id, domain_id, form_id FROM ctl.load "
              "WHERE load_id = %s", (load_id,))
    if lan_nap is None:
        return False, "Không tìm thấy lần nạp này."
    if lan_nap["status"] != "success":
        return False, "Chỉ gỡ được lần nạp đã thành công."

    sau_do = q.scalar(
        conn,
        """
        SELECT count(*) FROM ctl.batch b
         WHERE b.domain_id = %s AND b.form_id = %s AND b.state = 'current'
           AND b.batch_id > %s
        """,
        (lan_nap["domain_id"], lan_nap["form_id"], lan_nap["batch_id"]),
    )
    if sau_do:
        return False, (f"Có {sau_do} lần nạp sau lần này trên cùng nhóm thông tin. "
                       f"Hãy gỡ các lần nạp sau trước.")
    return True, ""


def go(conn, registry: FormRegistry, load_id: int) -> dict:
    duoc, ly_do = co_go_duoc(conn, load_id)
    if not duoc:
        raise InvalidInput(ly_do)

    lan_nap = q.query_one(
        conn, "SELECT load_id, batch_id, domain_id, form_id FROM ctl.load WHERE load_id = %s",
        (load_id,))
    batch_id = lan_nap["batch_id"]
    acquire_write_locks(conn, [(lan_nap["domain_id"], lan_nap["form_id"])])

    form = registry.form(
        q.scalar(conn, "SELECT code FROM ctl.form WHERE form_id = %s", (lan_nap["form_id"],))
    )
    da_go = 0
    da_tra_lai = 0

    for table in reversed(form.tables_theo_thu_tu):     # số liệu trước, danh mục sau
        bronze_t = sql.Identifier("bronze", table.name)
        silver_t = sql.Identifier("silver", table.name)
        gold_t = sql.Identifier("gold", table.name)

        # Xoá dòng của lô: Gold trỏ vào Silver, Silver trỏ vào Bronze — xoá theo
        # thứ tự đó. Xoá trước rồi mới trả lại dòng cũ, để khoá nghiệp vụ đang
        # hiệu lực không bị trùng giữa dòng mới và dòng cũ.
        q.execute(conn, sql.SQL("DELETE FROM {} WHERE batch_id = %s").format(gold_t),
                  (batch_id,))
        da_go += q.execute(conn, sql.SQL("DELETE FROM {} WHERE batch_id = %s").format(silver_t),
                           (batch_id,))
        q.execute(conn, sql.SQL("DELETE FROM {} WHERE batch_id = %s").format(bronze_t),
                  (batch_id,))

        # Trả lại các dòng lô này đã thay thế.
        da_tra_lai += q.execute(
            conn,
            sql.SQL("UPDATE {} SET is_current = true, valid_to = NULL, "
                    "superseded_by_batch_id = NULL WHERE superseded_by_batch_id = %s"
                    ).format(silver_t),
            (batch_id,),
        )
        q.execute(
            conn,
            sql.SQL("UPDATE {gold} g SET is_current = true FROM {silver} s "
                    "WHERE g.silver_sk = s.{sk} AND s.is_current "
                    "AND s.superseded_by_batch_id IS NULL AND NOT g.is_current"
                    ).format(gold=gold_t, silver=silver_t,
                             sk=sql.Identifier(table.sk_column)),
        )

    tep = _xoa_ban_ghi(conn, load_id)
    return {"da_go": da_go, "da_tra_lai": da_tra_lai, "tep": tep}


def _xoa_ban_ghi(conn, load_id: int) -> str | None:
    """Xoá bản ghi lần nạp ở ctl: lô, kỳ của lô, kết quả đối chiếu, lần nạp và
    tệp tải lên. Trả đường dẫn tệp trên đĩa để tầng gọi xoá sau khi chốt."""
    lan_nap = q.query_one(conn, "SELECT batch_id, upload_id FROM ctl.load WHERE load_id = %s",
                          (load_id,))
    tep = q.scalar(conn, "SELECT storage_uri FROM ctl.upload WHERE upload_id = %s",
                   (lan_nap["upload_id"],))
    # ctl.load và ctl.batch trỏ vòng vào nhau: gỡ con trỏ ở load trước.
    q.execute(conn, "UPDATE ctl.load SET batch_id = NULL WHERE load_id = %s", (load_id,))
    # batch_partition và recon_result tự xoá theo (ON DELETE CASCADE).
    q.execute(conn, "DELETE FROM ctl.batch WHERE load_id = %s", (load_id,))
    q.execute(conn, "DELETE FROM ctl.load WHERE load_id = %s", (load_id,))
    con_dung = q.scalar(conn, "SELECT count(*) FROM ctl.load WHERE upload_id = %s",
                        (lan_nap["upload_id"],))
    if not con_dung:
        q.execute(conn, "DELETE FROM ctl.upload WHERE upload_id = %s", (lan_nap["upload_id"],))
    return tep


def xoa_lich_su(conn, load_id: int) -> str | None:
    """Xoá bản ghi lịch sử của lần nạp không còn dòng dữ liệu nào: bị từ chối,
    lệch đối chiếu (giao dịch đã huỷ), hoặc đã gỡ. Trả đường dẫn tệp để xoá."""
    lan_nap = q.query_one(conn, "SELECT status FROM ctl.load WHERE load_id = %s", (load_id,))
    if lan_nap is None:
        raise InvalidInput("Không tìm thấy lần nạp này.")
    if lan_nap["status"] not in XOA_DUOC:
        raise InvalidInput("Chỉ xoá được lịch sử của lần nạp không còn dữ liệu.")
    return _xoa_ban_ghi(conn, load_id)
