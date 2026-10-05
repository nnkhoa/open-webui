from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .. import messages
from ..errors import RegistryError
from . import types as column_types

DOMAIN_CODE_PATTERN = re.compile(r'^[A-Z0-9-]{2,20}$')
FORM_CODE_PATTERN = re.compile(r'^[A-Z0-9_]{2,40}$')
TABLE_NAME_PATTERN = re.compile(r'^[a-z][a-z0-9_]{2,50}$')
COLUMN_NAME_PATTERN = re.compile(r'^[a-z][a-z0-9_]{1,50}$')

MERGE_STRATEGIES = {'upsert', 'replace_partition', 'append', 'replace_all'}
POLICY_ACTIONS = {'reject', 'ignore'}
POLICY_KEYS = ('unknown_sheet', 'unknown_column', 'missing_column')
COLUMN_ROLES = {'partition', 'measure', 'attribute', 'degenerate'}
TABLE_KINDS = {'dim', 'fact'}
VALUE_FROM_YEAR = 'nam_du_lieu'
VALUE_FROM_EMPTY = 'trong'
VALUE_FROM_HEADER = 'tieu_de'
VALUE_SOURCES = {VALUE_FROM_YEAR, VALUE_FROM_EMPTY, VALUE_FROM_HEADER}
SOURCE_RESERVED_KEYS = ('kind', 'header_row')


@dataclass
class FormColumn:
    name: str
    type: str
    label: str
    meaning: str
    ordinal: int
    required: bool = False
    is_business_key: bool = False
    header: str | None = None
    how: str | None = None
    example: str | None = None
    values: list[str] = field(default_factory=list)
    role: str | None = None
    display_width: int | None = None
    show_in_table: bool = True
    value_from: str | None = None

    def __post_init__(self) -> None:
        self._type = column_types.build(self.type, self)

    @property
    def file_header(self) -> str:
        return self.header or self.name

    @property
    def from_file(self) -> bool:
        return self.value_from is None

    @property
    def from_header(self) -> bool:
        return self.value_from == VALUE_FROM_HEADER

    @property
    def is_year(self) -> bool:
        return self.value_from == VALUE_FROM_YEAR

    @property
    def handler(self) -> column_types.ColumnType:
        return self._type

    @property
    def silver_sql_type(self) -> str:
        return self._type.silver_sql_type

    @property
    def align(self) -> str:
        return self._type.align

    @property
    def type_label(self) -> str:
        return self._type.label

    @property
    def is_measure(self) -> bool:
        return self.role == 'measure' and self._type.summable

    def display(self, value: Any) -> str:
        return self._type.display(value)


@dataclass
class FormTable:
    name: str
    kind: str
    sheet: str
    label: str
    description: str
    grain: str
    columns: list[FormColumn]
    business_key: list[str] = field(default_factory=list)
    merge: str = 'upsert'
    partition_by: list[str] = field(default_factory=list)
    order: list[str] = field(default_factory=list)
    display_order: int = 0
    card_label: str | None = None
    card_description: str | None = None
    purpose: str = ''

    @property
    def card_title(self) -> str:
        return self.card_label or self.label

    @property
    def is_dim(self) -> bool:
        return self.kind == 'dim'

    @property
    def sk_column(self) -> str:
        return f'{self.name}_sk'

    def column(self, name: str) -> FormColumn:
        for column in self.columns:
            if column.name == name:
                return column
        raise RegistryError(messages.REGISTRY_UNKNOWN_COLUMN.format(table=self.name, column=name))

    @property
    def column_names(self) -> list[str]:
        return [column.name for column in self.columns]

    @property
    def header_map(self) -> dict[str, str]:
        return {column.name: column.file_header for column in self.columns if column.from_file}

    @property
    def file_columns(self) -> list[FormColumn]:
        return [column for column in self.columns if column.from_file]

    @property
    def year_column(self) -> FormColumn | None:
        return next((column for column in self.columns if column.is_year), None)

    @property
    def amount_columns(self) -> list[FormColumn]:
        return [column for column in self.columns if column.type in ('money', 'currency')]

    @property
    def measures(self) -> list[FormColumn]:
        return [column for column in self.columns if column.is_measure]

    @property
    def partition_column(self) -> FormColumn | None:
        return self.column(self.partition_by[0]) if self.partition_by else None


@dataclass
class FormPolicy:
    unknown_sheet: str = 'reject'
    unknown_column: str = 'reject'
    missing_column: str = 'reject'


@dataclass
class Form:
    code: str
    version: int
    label: str
    description: str
    tables: list[FormTable]
    policy: FormPolicy
    source_kind: str
    header_row: int = 1
    yaml_sha256: str = ''
    source_options: dict = field(default_factory=dict)
    subtitle: str | None = None

    def table(self, name: str) -> FormTable:
        for table in self.tables:
            if table.name == name:
                return table
        raise RegistryError(messages.REGISTRY_UNKNOWN_TABLE_IN_FORM.format(form=self.code, table=name))

    @property
    def tables_by_dependency(self) -> list[FormTable]:
        return sorted(self.tables, key=lambda table: (table.kind != 'dim', table.display_order, table.name))

    @property
    def tables_by_display_order(self) -> list[FormTable]:
        return sorted(self.tables, key=lambda table: (table.display_order, table.name))


@dataclass(frozen=True)
class DomainDefinition:
    code: str
    name: str
    description: str | None = None
    forms: tuple[str, ...] = ()


def parse_column(raw: dict, ordinal: int, business_key: list[str], table_name: str) -> FormColumn:
    name = _match(
        COLUMN_NAME_PATTERN,
        _require(raw.get('name'), f'{table_name}: columns[].name', str),
        messages.REGISTRY_COLUMN_NAME_LABEL,
    )
    type_name = _require(raw.get('type'), f'{table_name}.{name}: type', str)
    _check_column_settings(raw, table_name, name, type_name)
    return FormColumn(
        name=name,
        type=type_name,
        label=_require(raw.get('label'), f'{table_name}.{name}: label', str),
        meaning=_require(raw.get('meaning'), f'{table_name}.{name}: meaning', str).strip(),
        ordinal=ordinal,
        required=bool(raw.get('required')),
        is_business_key=name in business_key,
        header=raw.get('header'),
        how=raw.get('how'),
        example=None if raw.get('example') is None else str(raw['example']),
        values=_string_list(raw.get('values')),
        role=raw.get('role'),
        display_width=raw.get('display_width'),
        show_in_table=bool(raw.get('show_in_table', True)),
        value_from=raw.get('value_from'),
    )


def parse_table(raw: dict) -> FormTable:
    name = _match(
        TABLE_NAME_PATTERN, _require(raw.get('name'), 'tables[].name', str), messages.REGISTRY_TABLE_NAME_LABEL
    )
    kind = _require(raw.get('kind'), f'{name}: kind', str)
    merge = raw.get('merge', 'upsert')
    business_key = _string_list(raw.get('business_key'))
    partition_by = _string_list(raw.get('partition_by'))
    _check_table_settings(name, kind, merge, business_key, partition_by)

    raw_columns = raw.get('columns') or []
    if not raw_columns:
        raise RegistryError(messages.REGISTRY_TABLE_WITHOUT_COLUMNS.format(table=name))
    columns = [parse_column(column, i, business_key, name) for i, column in enumerate(raw_columns, start=1)]
    _check_table_columns(name, columns, business_key, partition_by)
    if kind == 'fact' and not raw.get('grain'):
        raise RegistryError(messages.REGISTRY_FACT_WITHOUT_GRAIN.format(table=name))

    return FormTable(
        name=name,
        kind=kind,
        sheet=_require(raw.get('sheet'), f'{name}: sheet', str),
        label=_require(raw.get('label'), f'{name}: label', str),
        description=_require(raw.get('description'), f'{name}: description', str, required=False, default=''),
        grain=str(raw.get('grain') or ''),
        columns=columns,
        business_key=business_key,
        merge=merge,
        partition_by=partition_by,
        order=[str(column) for column in (raw.get('order') or business_key)],
        display_order=int(raw.get('display_order', 0)),
        card_label=raw.get('card_label'),
        card_description=raw.get('card_description'),
        purpose=str(raw.get('purpose') or ''),
    )


def parse_form(raw: dict, yaml_sha256: str = '') -> Form:
    if not isinstance(raw, dict) or 'form' not in raw:
        raise RegistryError(messages.REGISTRY_MISSING_FORM_BLOCK)
    head = raw['form']
    code = _match(FORM_CODE_PATTERN, _require(head.get('code'), 'form.code', str), 'form.code')
    policy = _parse_policy(code, head.get('policy') or {})

    raw_tables = raw.get('tables') or []
    if not raw_tables:
        raise RegistryError(messages.REGISTRY_FORM_WITHOUT_TABLES.format(form=code))
    tables = [parse_table(table) for table in raw_tables]
    _check_form_tables(code, tables)

    source = head.get('source') or {}
    return Form(
        code=code,
        version=int(_require(head.get('version'), 'form.version', int)),
        label=_require(head.get('label'), 'form.label', str),
        description=str(head.get('description') or '').strip(),
        tables=tables,
        policy=policy,
        source_kind=_require(source.get('kind'), 'form.source.kind', str),
        header_row=int(source.get('header_row', 1)),
        yaml_sha256=yaml_sha256,
        source_options={key: value for key, value in source.items() if key not in SOURCE_RESERVED_KEYS},
        subtitle=str(head.get('subtitle') or '').strip() or None,
    )


def parse_domains(raw: Any, form_codes: set[str]) -> list[DomainDefinition]:
    if not isinstance(raw, dict) or not isinstance(raw.get('domains'), list):
        raise RegistryError(messages.REGISTRY_MISSING_DOMAINS_LIST)
    domains = [_parse_domain(entry, form_codes) for entry in raw['domains']]
    if not domains:
        raise RegistryError(messages.REGISTRY_NO_DOMAINS)
    _check_unique_across_domains(messages.REGISTRY_DOMAIN_CODE_LABEL, [domain.code for domain in domains])
    _check_unique_across_domains(messages.REGISTRY_FORM_LABEL, [form for domain in domains for form in domain.forms])
    return domains


def _require(value: Any, name: str, expected: type, required: bool = True, default: Any = None) -> Any:
    if value is None:
        if required:
            raise RegistryError(messages.REGISTRY_MISSING_FIELD.format(name=name))
        return default
    if not isinstance(value, expected):
        raise RegistryError(
            messages.REGISTRY_WRONG_TYPE.format(name=name, expected=expected.__name__, actual=type(value).__name__)
        )
    return value


def _match(pattern: re.Pattern, value: str, name: str) -> str:
    if not pattern.match(value):
        raise RegistryError(messages.REGISTRY_PATTERN_MISMATCH.format(name=name, value=value, pattern=pattern.pattern))
    return value


def _string_list(raw: Any) -> list[str]:
    return [str(item) for item in (raw or [])]


def _duplicates(values: list[str]) -> set[str]:
    return {value for value in values if values.count(value) > 1}


def _check_column_settings(raw: dict, table_name: str, name: str, type_name: str) -> None:
    if type_name not in column_types.TYPES:
        raise RegistryError(
            messages.REGISTRY_COLUMN_TYPE_NOT_REGISTERED.format(
                table=table_name, column=name, type=type_name, available=', '.join(sorted(column_types.TYPES))
            )
        )
    role = raw.get('role')
    if role is not None and role not in COLUMN_ROLES:
        raise RegistryError(
            messages.REGISTRY_INVALID_ROLE.format(table=table_name, column=name, allowed=sorted(COLUMN_ROLES))
        )
    if type_name == 'enum' and not raw.get('values'):
        raise RegistryError(messages.REGISTRY_ENUM_WITHOUT_VALUES.format(table=table_name, column=name))
    value_from = raw.get('value_from')
    if value_from is not None and value_from not in VALUE_SOURCES:
        raise RegistryError(
            messages.REGISTRY_INVALID_VALUE_FROM.format(table=table_name, column=name, allowed=sorted(VALUE_SOURCES))
        )


def _check_table_settings(name: str, kind: str, merge: str, business_key: list[str], partition_by: list[str]) -> None:
    if kind not in TABLE_KINDS:
        raise RegistryError(messages.REGISTRY_INVALID_KIND.format(table=name))
    if merge not in MERGE_STRATEGIES:
        raise RegistryError(messages.REGISTRY_INVALID_MERGE.format(table=name, allowed=sorted(MERGE_STRATEGIES)))
    if merge != 'append' and not business_key:
        raise RegistryError(messages.REGISTRY_MISSING_BUSINESS_KEY.format(table=name))
    if merge == 'replace_partition' and not partition_by:
        raise RegistryError(messages.REGISTRY_MISSING_PARTITION_BY.format(table=name))


def _check_table_columns(
    name: str, columns: list[FormColumn], business_key: list[str], partition_by: list[str]
) -> None:
    column_names = [column.name for column in columns]
    duplicates = _duplicates(column_names)
    if duplicates:
        raise RegistryError(messages.REGISTRY_DUPLICATE_COLUMNS.format(table=name, names=', '.join(sorted(duplicates))))
    for key in business_key:
        if key not in column_names:
            raise RegistryError(messages.REGISTRY_UNKNOWN_BUSINESS_KEY_COLUMN.format(table=name, column=key))
    for column in partition_by:
        if column not in column_names:
            raise RegistryError(messages.REGISTRY_UNKNOWN_PARTITION_COLUMN.format(table=name, column=column))
    if sum(1 for column in columns if column.is_year) > 1:
        raise RegistryError(messages.REGISTRY_MULTIPLE_YEAR_COLUMNS.format(table=name, value=VALUE_FROM_YEAR))


def _parse_policy(code: str, raw: dict) -> FormPolicy:
    for key in POLICY_KEYS:
        if raw.get(key, 'reject') not in POLICY_ACTIONS:
            raise RegistryError(
                messages.REGISTRY_INVALID_POLICY.format(form=code, key=key, allowed=sorted(POLICY_ACTIONS))
            )
    return FormPolicy(**{key: raw.get(key, 'reject') for key in POLICY_KEYS})


def _check_form_tables(code: str, tables: list[FormTable]) -> None:
    duplicates = _duplicates([table.name for table in tables])
    if duplicates:
        raise RegistryError(messages.REGISTRY_DUPLICATE_TABLES.format(form=code, names=', '.join(sorted(duplicates))))
    duplicate_sheets = _duplicates([table.sheet.lower() for table in tables])
    if duplicate_sheets:
        raise RegistryError(
            messages.REGISTRY_DUPLICATE_SHEETS.format(form=code, sheets=', '.join(sorted(duplicate_sheets)))
        )


def _parse_domain(entry: Any, form_codes: set[str]) -> DomainDefinition:
    if not isinstance(entry, dict):
        raise RegistryError(messages.REGISTRY_INVALID_DOMAIN_ENTRY)
    code = _match(
        DOMAIN_CODE_PATTERN, _require(entry.get('code'), 'domains[].code', str), messages.REGISTRY_DOMAIN_CODE_LABEL
    )
    raw_forms = entry.get('forms')
    forms = [raw_forms] if isinstance(raw_forms, str) else list(raw_forms or [])
    for form in forms:
        if not isinstance(form, str) or form not in form_codes:
            raise RegistryError(messages.REGISTRY_UNKNOWN_DOMAIN_FORM.format(domain=code, form=form))
    return DomainDefinition(
        code=code,
        name=_require(entry.get('name'), f'{code}: name', str).strip(),
        description=str(entry.get('description') or '').strip() or None,
        forms=tuple(forms),
    )


def _check_unique_across_domains(label: str, values: list[str]) -> None:
    duplicates = _duplicates(values)
    if duplicates:
        raise RegistryError(
            messages.REGISTRY_SHARED_BETWEEN_DOMAINS.format(label=label, values=', '.join(sorted(duplicates)))
        )
