"""Phân quyền theo cột Quyền của bảng 9.2 (PCN-01, NT-03): User 403 mọi đường dẫn,
Data Loader 403 ở đường dẫn chỉ Admin, chưa đăng nhập 401."""

from __future__ import annotations

import pytest

from open_webui.data_portal.api.deps import KHONG_CO_QUYEN

from .conftest import Goi

DUONG_DAN_AL = [
    ("GET", "/domains"), ("GET", "/loads?nhom=HQKD"), ("GET", "/loads/1"),
    ("GET", "/loads/1/reconcile"), ("GET", "/loads/1/errors.csv"),
    ("GET", "/loads/1/file"), ("GET", "/loads/1/file/sheets"),
    ("GET", "/loads/1/file/sheets/1"), ("POST", "/uploads"),
    ("GET", "/uploads/" + "0" * 32), ("DELETE", "/uploads/" + "0" * 32),
    ("POST", "/uploads/" + "0" * 32 + "/confirm"), ("GET", "/tables?nhom=HQKD"),
    ("GET", "/tables/fact_ket_qua_kd"), ("GET", "/tables/fact_ket_qua_kd/export.xlsx"),
]
DUONG_DAN_A = [
    ("DELETE", "/loads/1"), ("GET", "/db-config"), ("POST", "/db-config/test"),
    ("PUT", "/db-config"), ("DELETE", "/db-config"),
]


@pytest.mark.parametrize(("method", "url"), DUONG_DAN_AL + DUONG_DAN_A)
def test_user_nhan_403_moi_duong_dan(client, method, url):
    r = Goi(client, role="user", user_id="u-user", user_name="user")(method, url)
    assert r.status_code == 403
    assert r.json()["detail"] == KHONG_CO_QUYEN


@pytest.mark.parametrize(("method", "url"), DUONG_DAN_A)
def test_data_loader_nhan_403_duong_dan_chi_admin(loader, method, url):
    assert loader(method, url).status_code == 403


def test_data_loader_vao_duoc_duong_dan_a_l(loader):
    assert loader("GET", "/domains").status_code == 200
    assert loader("GET", "/loads?nhom=HQKD").status_code == 200


def test_chua_dang_nhap_401(client):
    r = client.get("/domains")
    assert r.status_code == 401
    assert r.json()["detail"] == "Not authenticated"
