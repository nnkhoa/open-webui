"""NT-13: hai lần nạp cùng (nhóm, loại tệp) cùng lúc chạy lần lượt, không hỏng dữ
liệu (QT-12, khoá `pg_advisory_xact_lock`). Tầng web Jinja cũ vẫn chạy cạnh API."""

from __future__ import annotations

import threading

from open_webui.data_portal.pipeline import nap, tep_cho
from .conftest import can_tep_mau, dem, tai_len


def test_hai_lan_xac_nhan_cung_luc(admin, sach):
    ma = [tai_len(admin, can_tep_mau()).json()["ma_tep_cho"] for _ in range(2)]
    form = sach.registry.form("BAO_CAO_HQKH")
    ket_qua: list[dict] = []

    def chay(m: str) -> None:
        tep = tep_cho.doc(sach.settings.upload_dir, m)
        ket_qua.append(nap.xac_nhan(sach.kho, sach.so_tay, sach.settings, form, tep,
                                    domain_code="HQKD", request_id=f"thu-{m[:6]}"))

    luong = [threading.Thread(target=chay, args=(m,)) for m in ma]
    for t in luong:
        t.start()
    for t in luong:
        t.join()
    assert sorted(k["status"] for k in ket_qua) == ["success", "success"]
    assert dem(sach, "SELECT count(*) FROM gold.fact_ket_qua_kd WHERE is_current") == 348
    assert dem(sach, "SELECT count(*) FROM gold.fact_chi_phi WHERE is_current") == 6960
    assert dem(sach, "SELECT count(*) FROM ctl.batch WHERE state = 'current'") == 2


def test_xac_nhan_hai_lan_cung_tep_cho(admin, sach):
    ma = tai_len(admin, can_tep_mau()).json()["ma_tep_cho"]
    assert admin("POST", f"/uploads/{ma}/confirm").json()["status"] == "success"
    r = admin("POST", f"/uploads/{ma}/confirm")
    assert r.status_code == 404
    assert r.json()["detail"] == ("Tệp này đã được nạp hoặc đã quá hạn chờ xác nhận. Hãy xem "
                                  "Lịch sử nạp, hoặc chọn lại tệp.")
    assert dem(sach, "SELECT count(*) FROM ctl.load") == 1


def test_duong_dan_khong_co_chua_dang_nhap_401(client):
    r = client.get("/khong-co")
    assert r.status_code == 401 and r.headers["content-type"] == "application/json"


def test_duong_dan_khong_co_van_kiem_quyen(client, admin):
    from .conftest import Goi

    assert Goi(client, role="user")("GET", "/khong-co").status_code == 403
    r = admin("GET", "/khong-co")
    assert r.status_code == 404 and r.json()["detail"] == "Không tìm thấy."
