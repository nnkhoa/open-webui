"""Dụng cụ chung cho kiểm thử Data Portal (chạy trong `backend/`).

Kiểm thử cần PostgreSQL dùng database **riêng cho kiểm thử** trên máy chủ đang
chạy sẵn, không dựng máy chủ mới:

    DATA_PORTAL_TEST_DATABASE_URL   mặc định postgresql:///ai4bi_portal_test
    DATA_PORTAL_SAMPLE_DIR          thư mục `data_sources` chứa tệp mẫu NBC

Mỗi phiên kiểm thử xoá sạch các schema của Data Portal trong database đó rồi dựng
lại bằng đúng đường khởi động (`container.dung`: áp dụng migration, chép khai báo).
Không kết nối được thì các kiểm thử cần database được bỏ qua, có ghi lý do.

Tài khoản Open WebUI được giả lập bằng header `X-Test-*`: hàm xác thực thật của
Open WebUI được thay bằng `_tai_khoan_thu` khi dựng API.

Sổ tay SQLite và thư mục tệp tải lên nằm trong thư mục tạm của pytest.
"""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from fastapi import HTTPException, Request
from open_webui.data_portal.config import PACKAGE_DIR, load_settings
from open_webui.data_portal.container import build_container

KHAI_BAO = PACKAGE_DIR / "khai_bao"
MAU = Path(os.getenv("DATA_PORTAL_SAMPLE_DIR", "/khong-co-tep-mau"))
TEP_HQKD = (MAU / "2. HQKD - Hieu qua kinh doanh"
            / "FORM MAU - HIEU QUA TUNG KHACH HANG T1-T7.26.xlsx")
THU_MUC_GC = MAU / "3. HQ-MAU-GC - May mau, gia cong ngoai"
TEP_MAY_MAU = THU_MUC_GC / "SAMPLE MAKING SCHEDULE ( 30 Sep ) - OK.xlsx"
TEP_GIA_CONG = THU_MUC_GC / "TOTAL PO SUBCON.xlsx"
DSN = os.getenv("DATA_PORTAL_TEST_DATABASE_URL", "postgresql:///ai4bi_portal_test")
SCHEMA = ("analytics", "gold", "silver", "bronze", "ctl")


def _co_database() -> str | None:
    try:
        with psycopg.connect(DSN, connect_timeout=3):
            return None
    except psycopg.Error as e:
        return f"Không kết nối được database kiểm thử {DSN}: {str(e).splitlines()[0]}"


@pytest.fixture(scope="session")
def container(tmp_path_factory):
    # AI4BI: fixture này DROP SCHEMA ... CASCADE — chỉ chạy trên database dành riêng cho test,
    # không bao giờ trên kho thật (vd aibi_database của nhabe).
    dbname = psycopg.conninfo.conninfo_to_dict(DSN).get("dbname") or ""
    if not dbname.endswith("_test"):
        pytest.exit(f"DATA_PORTAL_TEST_DATABASE_URL phải trỏ tới database tên *_test (đang là '{dbname}')", 2)
    ly_do = _co_database()
    if ly_do:
        pytest.skip(ly_do)
    with psycopg.connect(DSN, autocommit=True) as conn:
        for s in SCHEMA:
            conn.execute(f"DROP SCHEMA IF EXISTS {s} CASCADE")
    thu_muc = tmp_path_factory.mktemp("data_portal")
    settings = replace(load_settings(), default_database_url=DSN,
                       catalog_path=thu_muc / "so-tay.db", upload_dir=thu_muc / "uploads")
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    ct = build_container(settings)
    assert ct.warehouse.is_configured, ct.warehouse.reason
    yield ct
    ct.close()


def xoa_du_lieu(ct) -> None:
    """Xoá mọi lần nạp và dữ liệu ba lớp, giữ khai báo."""
    with ct.warehouse.transaction() as conn:
        bang = [f"{lop}.{t.name}" for lop in ("gold", "silver", "bronze")
                for t in ct.registry.tables]
        conn.execute("TRUNCATE " + ", ".join(bang) + ", ctl.recon_result, "
                     "ctl.batch_partition, ctl.batch, ctl.load, ctl.upload CASCADE")


@pytest.fixture
def sach(container):
    xoa_du_lieu(container)
    yield container


def _tai_khoan_thu(request: Request):
    """Thay `get_verified_user` của Open WebUI: tài khoản lấy từ header `X-Test-*`."""
    role = request.headers.get("x-test-role")
    if not role:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return SimpleNamespace(id=request.headers.get("x-test-user-id", ""),
                           name=request.headers.get("x-test-user-name", ""),
                           email="", role=role)


@pytest.fixture
def client(sach):
    from fastapi.testclient import TestClient
    from open_webui.data_portal.api.app import tao_api

    return TestClient(tao_api(_tai_khoan_thu, container=sach))


class Goi:
    """Gọi API với tư cách một tài khoản Open WebUI."""

    def __init__(self, client, *, role: str = "admin", user_id: str = "u-admin",
                 user_name: str = "admin") -> None:
        self.client = client
        self.h = {"X-Test-Role": role, "X-Test-User-Id": user_id,
                  "X-Test-User-Name": user_name}

    def __call__(self, method: str, url: str, **kw):
        return self.client.request(method, url, headers={**self.h, **kw.pop("headers", {})},
                                   **kw)


@pytest.fixture
def admin(client):
    return Goi(client)


@pytest.fixture
def loader(client):
    return Goi(client, role="data_uploader", user_id="u-loader", user_name="loader")


def can_tep_mau(tep: Path = TEP_HQKD) -> Path:
    if not tep.is_file():
        pytest.skip(f"Không có tệp mẫu NBC: {tep}")
    return tep


def tai_len(goi, tep: Path, *, nhom: str = "HQKD", nam: str = "2026", loai: str = "",
            ten: str | None = None):
    with tep.open("rb") as f:
        return goi("POST", "/uploads", data={"nhom": nhom, "nam": nam, "loai": loai},
                   files={"file": (ten or tep.name, f,
                                   "application/vnd.openxmlformats-officedocument."
                                   "spreadsheetml.sheet")})


def dem(ct, cau: str, tham=()) -> int:
    with ct.warehouse.transaction() as conn:
        return conn.execute(cau, tham).fetchone()[0]
