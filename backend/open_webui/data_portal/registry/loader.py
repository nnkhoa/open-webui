from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

from .. import messages
from ..errors import RegistryError
from .schema import DomainDefinition, Form, FormTable, parse_domains, parse_form


class FormRegistry:
    def __init__(self, forms: list[Form], domains: list[DomainDefinition]) -> None:
        self._forms_by_code: dict[str, Form] = {}
        self._tables_by_name: dict[str, FormTable] = {}
        for form in forms:
            self._add_form(form)
        self.domains = domains

    def form(self, code: str) -> Form:
        try:
            return self._forms_by_code[code]
        except KeyError:
            raise RegistryError(messages.REGISTRY_FORM_NOT_FOUND.format(code=code)) from None

    def table(self, name: str) -> FormTable:
        try:
            return self._tables_by_name[name]
        except KeyError:
            raise RegistryError(messages.REGISTRY_TABLE_NOT_FOUND.format(table=name)) from None

    @property
    def forms(self) -> list[Form]:
        return list(self._forms_by_code.values())

    @property
    def tables(self) -> list[FormTable]:
        return list(self._tables_by_name.values())

    def _add_form(self, form: Form) -> None:
        if form.code in self._forms_by_code:
            raise RegistryError(messages.REGISTRY_DUPLICATE_FORM_CODE.format(code=form.code))
        self._forms_by_code[form.code] = form
        for table in form.tables:
            if table.name in self._tables_by_name:
                raise RegistryError(messages.REGISTRY_TABLE_IN_TWO_FORMS.format(table=table.name))
            self._tables_by_name[table.name] = table


def load_definitions(definitions_dir: Path) -> FormRegistry:
    forms_dir = definitions_dir / 'forms'
    if not forms_dir.is_dir():
        raise RegistryError(messages.REGISTRY_MISSING_FORMS_DIR.format(path=forms_dir))
    forms = [_load_form(path) for path in sorted(forms_dir.glob('*.yaml'))]
    domains_file = definitions_dir / 'domains.yaml'
    if not domains_file.is_file():
        raise RegistryError(messages.REGISTRY_MISSING_DOMAINS_FILE.format(path=domains_file))
    domains = parse_domains(_read_yaml(domains_file), {form.code for form in forms})
    return FormRegistry(forms, domains)


def _load_form(path: Path) -> Form:
    try:
        return parse_form(_read_yaml(path), hashlib.sha256(path.read_bytes()).hexdigest())
    except RegistryError as e:
        raise RegistryError(f'{path.name}: {e}') from None


def _read_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding='utf-8'))
    except yaml.YAMLError as e:
        raise RegistryError(messages.REGISTRY_INVALID_YAML.format(file=path.name, error=e)) from None
