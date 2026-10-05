"""Cấu hình database (MH-40) — chỉ Admin, không trả mật khẩu (PCN-02)."""

from __future__ import annotations

from .conftest import DSN


def test_xem_cau_hinh_khi_chua_luu(admin):
    d = admin("GET", "/db-config").json()
    assert d == {"config": None, "connection": None, "last_tested_at": None, "saved_at": None}


def test_kiem_tra_dau_vao_422(admin):
    r = admin("POST", "/db-config/test",
              json={"host": "", "port": "abc", "database": "x", "username": "u"})
    assert r.status_code == 422
    assert r.json()["field_errors"] == {"host": "Chưa nhập địa chỉ máy chủ.",
                                  "port": "Cổng phải là số."}
    r = admin("POST", "/db-config/test",
              json={"host": "h", "port": 70000, "database": "x", "username": "u"})
    assert r.json()["field_errors"] == {"port": "Cổng phải nằm trong khoảng 1–65535."}


def test_thu_khong_ket_noi_duoc(admin):
    r = admin("POST", "/db-config/test",
              json={"host": "127.0.0.1", "port": 1, "database": "x", "username": "u"})
    assert r.status_code == 200
    assert r.json()["ok"] is False and r.json()["message"]
    r = admin("PUT", "/db-config",
              json={"host": "127.0.0.1", "port": 1, "database": "x", "username": "u"})
    assert r.json()["ok"] is False
    assert admin("GET", "/db-config").json()["config"] is None


def test_luu_va_bo_cau_hinh(admin, sach):
    from psycopg import conninfo

    phan = conninfo.conninfo_to_dict(DSN)
    import getpass

    vao = {"host": phan.get("host") or "/tmp", "port": phan.get("port") or 5432,
           "database": phan["dbname"], "username": phan.get("user") or getpass.getuser(),
           "password": "", "note": "kiểm thử"}
    r = admin("POST", "/db-config/test", json=vao)
    assert r.json()["ok"] is True and r.json()["message"].startswith("Kết nối được.")
    r = admin("PUT", "/db-config", json=vao)
    assert r.json() == {"ok": True, "message":
                        f"Đã lưu và nối tới {vao['username']}@{vao['host']}:{vao['port']}/"
                        f"{vao['database']}."}
    d = admin("GET", "/db-config").json()
    assert d["config"]["database"] == vao["database"] and "password" not in d["config"]
    assert d["connection"]["ok"] is True and d["saved_at"]
    r = admin("DELETE", "/db-config")
    assert r.json() == {"message": "Đã bỏ cấu hình. Dữ liệu trong cơ sở dữ liệu đó không "
                                     "bị đụng tới."}
    assert admin("GET", "/loads?domain=HQKD").status_code in (200, 503)
    # Nối lại kho cho các kiểm thử sau.
    with sach.catalog.transaction() as so:
        sach.reconnect_warehouse(so)
    assert sach.warehouse.is_configured
