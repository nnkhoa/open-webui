"""Đọc khai báo trong `khai_bao/`: bộ bảng ở `forms/*.yaml`, nhóm thông tin ở `domains.yaml`.

Khai báo là **mã nguồn**: nạp một lần lúc khởi động và giữ trong bộ nhớ, đổi
thì khởi động lại. Không có đường nào sửa khai báo từ giao diện.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from ..errors import RegistryError
from .schema import Form, FormTable, KhaiBaoDomain, dung_domains, dung_form


class FormRegistry:
    """Các bộ bảng và nhóm thông tin đã khai."""

    def __init__(self, forms: list[Form], domains: list[KhaiBaoDomain]) -> None:
        self._theo_ma: dict[str, Form] = {}
        self._bang: dict[str, FormTable] = {}
        for form in forms:
            if form.code in self._theo_ma:
                raise RegistryError(f"Mã bộ bảng {form.code!r} bị khai hai lần.")
            self._theo_ma[form.code] = form
            for table in form.tables:
                if table.name in self._bang:
                    raise RegistryError(
                        f"Tên bảng {table.name!r} bị dùng ở hai bộ bảng. "
                        f"Tên bảng phải duy nhất toàn hệ thống.")
                self._bang[table.name] = table
        self.domains = domains

    def form(self, code: str) -> Form:
        try:
            return self._theo_ma[code]
        except KeyError:
            raise RegistryError(f"Không có bộ bảng nào mã {code!r}.") from None

    def table(self, name: str) -> FormTable:
        try:
            return self._bang[name]
        except KeyError:
            raise RegistryError(f"Không có bảng nào tên {name!r}.") from None

    @property
    def forms(self) -> list[Form]:
        return list(self._theo_ma.values())

    @property
    def tables(self) -> list[FormTable]:
        return list(self._bang.values())


def doc_thu_muc(thu_muc: Path) -> FormRegistry:
    """Đọc `forms/*.yaml` theo thứ tự tên, rồi `domains.yaml`."""
    thu_muc_form = thu_muc / "forms"
    if not thu_muc_form.is_dir():
        raise RegistryError(f"Không thấy thư mục khai báo bộ bảng: {thu_muc_form}")
    forms = [doc_tep(path) for path in sorted(thu_muc_form.glob("*.yaml"))]
    tep_domain = thu_muc / "domains.yaml"
    if not tep_domain.is_file():
        raise RegistryError(f"Không thấy tệp khai báo nhóm thông tin: {tep_domain}")
    domains = dung_domains(_doc_yaml(tep_domain), {f.code for f in forms})
    return FormRegistry(forms, domains)


def doc_tep(path: Path) -> Form:
    try:
        return dung_form(_doc_yaml(path), hashlib.sha256(path.read_bytes()).hexdigest())
    except RegistryError as exc:
        raise RegistryError(f"{path.name}: {exc}") from None


def _doc_yaml(path: Path):
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RegistryError(f"{path.name}: YAML không hợp lệ — {exc}") from None
