"""Lệnh quản trị Data Portal (chạy trong thư mục `backend/`).

    python -m open_webui.data_portal.manage migrate            áp dụng bước nâng cấp chưa chạy
    python -m open_webui.data_portal.manage makemigration      so khai báo bảng với schema, sinh bước mới
    python -m open_webui.data_portal.manage registry validate  kiểm tra khai báo trong khai_bao/
    python -m open_webui.data_portal.manage registry ddl <mã>  in DDL sinh ra, không chạm cơ sở dữ liệu
    python -m open_webui.data_portal.manage sync-registry      ghi khai báo vào sổ tay + kho

Open WebUI tự áp dụng migration và chép khai báo mỗi lần khởi động; các lệnh này
dùng khi phát triển, chủ yếu là `makemigration` sau khi sửa tệp trong `khai_bao/forms/`.
"""

from __future__ import annotations

import argparse
import sys

from .config import doc_cau_hinh
from .container import dung
from .errors import ChuaCauHinhKho, PortalError
from .migrate import ledger, planner
from .registry import sync
from .registry.ddl import ddl_form


def _in(*phan) -> None:
    print(*phan, file=sys.stdout)


def _kho(container):
    if not container.kho.da_cau_hinh:
        raise ChuaCauHinhKho(ly_do=container.kho.ly_do)
    return container.kho.giao_dich()


def lenh_migrate(container, _) -> int:
    with _kho(container) as conn:
        # `ap_dung` tự chốt từng bước một, để bước hỏng không kéo theo bước trước.
        ap = ledger.ap_dung(conn, container.settings.migrations_dir)
    _in("Đã áp dụng:", ", ".join(ap)) if ap else _in("Schema đã ở phiên bản mới nhất.")
    return 0


def lenh_makemigration(container, _) -> int:
    with _kho(container) as conn:
        sinh = [planner.sinh_buoc(conn, form, container.settings.migrations_dir)
                for form in container.registry.forms]
    sinh = [d for d in sinh if d is not None]
    if not sinh:
        _in("Không có chênh lệch: bảng vật lý đã đúng khai báo.")
        return 0
    for dich in sinh:
        _in(f"Đã sinh {dich}")
    _in("\nHãy đọc lại tệp vừa sinh rồi chạy lệnh migrate.")
    return 0


def lenh_registry(container, args) -> int:
    if args.viec == "validate":
        for form in container.registry.forms:
            _in(f"✓ bộ bảng {form.code} v{form.version} — {len(form.tables)} bảng, "
                f"{sum(len(t.columns) for t in form.tables)} cột")
        for d in container.registry.domains:
            bo = ", ".join(d.cac_bo_bang) or "(chưa có)"
            _in(f"✓ nhóm thông tin {d.code} — {d.name} — bộ bảng {bo}")
        _in("Khai báo hợp lệ.")
        return 0
    if not args.ma:
        _in("Thiếu mã khai báo. Ví dụ: registry ddl BAO_CAO_HQKH")
        return 2
    _in(ddl_form(container.registry.form(args.ma)))
    return 0


def lenh_sync_registry(container, _) -> int:
    with container.so_tay.giao_dich() as so:
        if container.kho.da_cau_hinh:
            with container.kho.giao_dich() as conn:
                sync.dong_bo(so, conn, container.registry)
        else:
            sync.dong_bo(so, None, container.registry)
            _in("Kho chưa cấu hình — chỉ ghi vào sổ tay, sẽ chiếu sang khi nối được.")
    _in("Đã ghi khai báo:", ", ".join(f.code for f in container.registry.forms),
        "·", ", ".join(d.code for d in container.registry.domains))
    return 0


def main() -> int:
    bo_phan = argparse.ArgumentParser(description="Quản trị Data Portal")
    lenh = bo_phan.add_subparsers(dest="lenh", required=True)
    lenh.add_parser("migrate", help="Áp dụng nâng cấp schema chưa chạy")
    lenh.add_parser("makemigration", help="Sinh bước nâng cấp từ khai báo bộ bảng")
    lenh.add_parser("sync-registry", help="Ghi khai báo bộ bảng, nhóm thông tin vào sổ tay và kho")
    p = lenh.add_parser("registry", help="Kiểm tra và in khai báo bảng")
    p.add_argument("viec", choices=["validate", "ddl"])
    p.add_argument("ma", nargs="?")

    args = bo_phan.parse_args()
    container = dung(doc_cau_hinh())
    ham = {
        "migrate": lenh_migrate,
        "makemigration": lenh_makemigration,
        "registry": lenh_registry,
        "sync-registry": lenh_sync_registry,
    }[args.lenh]
    try:
        return ham(container, args)
    except ChuaCauHinhKho as exc:
        _in(f"Lỗi: {exc} — {exc.ly_do}" if exc.ly_do else f"Lỗi: {exc}")
        return 1
    except PortalError as exc:
        _in(f"Lỗi: {exc}")
        return 1
    finally:
        container.dong()


if __name__ == "__main__":
    sys.exit(main())
