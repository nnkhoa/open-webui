from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import NamedTuple

from psycopg import sql

from .. import messages
from ..db import sql as warehouse_sql
from ..formatting import format_amount, format_integer
from ..registry.schema import FormTable
from .card_model import (
    BEFORE_AFTER_CARD,
    BY_DIMENSION_CARD,
    CODES_CARD,
    EMPTY_CELLS_CARD,
    GROUP_BY_OPTION,
    TOTALS_CARD,
    ZERO,
    Card,
    CardColumn,
    CardOption,
    CardRow,
    OptionChoice,
    Pagination,
    as_number,
    before_after_columns,
    codes_columns,
    column_total,
    comparison_columns,
    gold_link,
    group_count_columns,
    table_link,
    totals_row,
    verdict,
)
from .context import LoadContext
from .file_check import month_key

DELIVERY_DATE_COLUMN = 'ngay_giao_mau'
QUANTITY_COLUMN = 'so_luong'
TOTAL_COLUMNS = (QUANTITY_COLUMN, 'don_gia')


class Dimension(NamedTuple):
    column: str
    label: str


class CodeCount(NamedTuple):
    label: str
    column: str
    short_name: str | None


class DomainTable(NamedTuple):
    name: str
    label: str


DIMENSIONS = {
    'fact_may_mau': [
        Dimension(DELIVERY_DATE_COLUMN, messages.CARD_DIMENSION_DELIVERY_MONTH),
        Dimension('ma_nhom_kd', messages.CARD_DIMENSION_SALES_GROUP),
        Dimension('ten_khach', messages.CARD_DIMENSION_CUSTOMER),
        Dimension('ma_giai_doan_mau', messages.CARD_DIMENSION_SAMPLE_STAGE),
    ],
    'fact_gia_cong': [
        Dimension('ma_don_vi_gc', messages.CARD_DIMENSION_SUBCONTRACTOR),
        Dimension('khu_vuc', messages.CARD_DIMENSION_REGION),
        Dimension('ten_khach', messages.CARD_DIMENSION_CUSTOMER),
        Dimension('ma_hang', messages.CARD_DIMENSION_PRODUCT_CODE),
    ],
}

CODE_COUNTS = {
    'fact_may_mau': [
        CodeCount(messages.CARD_CODES_DELIVERY_MONTHS, DELIVERY_DATE_COLUMN, messages.CARD_CODE_NAME_MONTH),
        CodeCount(messages.CARD_CODES_CUSTOMERS, 'ten_khach', messages.CARD_CODE_NAME_CUSTOMER),
        CodeCount(messages.CARD_CODES_BUSINESS_GROUPS, 'ma_nhom_kd', messages.CARD_CODE_NAME_GROUP),
        CodeCount(messages.CARD_CODES_SAMPLE_CODES, 'ma_mau', messages.CARD_CODE_NAME_PRODUCT),
        CodeCount(messages.CARD_CODES_SAMPLE_STAGES, 'ma_giai_doan_mau', messages.CARD_CODE_NAME_SAMPLE_STAGE),
    ],
    'fact_gia_cong': [
        CodeCount(messages.CARD_CODES_SUBCONTRACTORS, 'ma_don_vi_gc', messages.CARD_CODE_NAME_SUBCONTRACTOR),
        CodeCount(messages.CARD_CODES_REGIONS, 'khu_vuc', None),
        CodeCount(messages.CARD_CODES_CUSTOMERS, 'ten_khach', messages.CARD_CODE_NAME_CUSTOMER),
        CodeCount(messages.CARD_CODES_PRODUCT_CODES, 'ma_hang', messages.CARD_CODE_NAME_PRODUCT),
        CodeCount(messages.CARD_CODES_ORDERS, 'ma_don_hang', messages.CARD_CODE_NAME_ORDER),
        CodeCount(messages.CARD_CODES_COLORS, 'mau', messages.CARD_CODE_NAME_COLOR),
    ],
}


@dataclass
class GroupCounts:
    key: str
    file_rows: int
    db_rows: int
    file_quantity: int | float
    db_quantity: int | float

    @property
    def has_mismatch(self) -> bool:
        return self.file_rows != self.db_rows or Decimal(str(self.file_quantity)) != Decimal(str(self.db_quantity))

    def to_json(self) -> dict:
        return {
            'key': self.key,
            'file_rows': self.file_rows,
            'db_rows': self.db_rows,
            'file_quantity': self.file_quantity,
            'db_quantity': self.db_quantity,
        }

    @classmethod
    def from_json(cls, data: dict) -> GroupCounts:
        return cls(data['key'], data['file_rows'], data['db_rows'], data['file_quantity'], data['db_quantity'])


@dataclass
class DimensionGroups:
    label: str
    groups: list[GroupCounts]

    def to_json(self) -> dict:
        return {'label': self.label, 'groups': [group.to_json() for group in self.groups]}

    @classmethod
    def from_json(cls, data: dict) -> DimensionGroups:
        return cls(data['label'], [GroupCounts.from_json(group) for group in data['groups']])


@dataclass
class DimensionMatrix:
    table: str | None
    year: int | None
    dimensions: dict[str, DimensionGroups]
    order: list[str]
    has_mismatch: bool

    @property
    def title(self) -> str:
        if not self.order:
            return ''
        mismatched = (column for column in self.order if _has_mismatched_group(self.dimensions[column]))
        return _dimension_title(self.dimensions[next(mismatched, self.order[0])].label)

    def to_json(self) -> dict:
        return {
            'key': BY_DIMENSION_CARD,
            'table': self.table,
            'year': self.year,
            'dimensions': {column: groups.to_json() for column, groups in self.dimensions.items()},
            'order': list(self.order),
            'has_mismatch': self.has_mismatch,
        }

    @classmethod
    def from_json(cls, data: dict) -> DimensionMatrix:
        dimensions = {
            column: DimensionGroups.from_json(groups) for column, groups in data.get('dimensions', {}).items()
        }
        return cls(
            data.get('table'),
            data.get('year'),
            dimensions,
            data.get('order') or list(dimensions),
            data.get('has_mismatch', False),
        )


@dataclass
class _GroupTally:
    file_rows: int = 0
    db_rows: int = 0
    file_quantity: Decimal = ZERO
    db_quantity: Decimal = ZERO

    @property
    def has_mismatch(self) -> bool:
        return self.file_rows != self.db_rows or self.file_quantity != self.db_quantity


def totals_card(
    ctx: LoadContext, table: FormTable, file_rows: list[dict], db_rows: list[dict], file_check: dict
) -> Card:
    rows = [
        _column_total_row(ctx, table, column, file_rows, db_rows)
        for column in TOTAL_COLUMNS
        if column in table.column_names
    ]
    total_cell_row = _total_cell_row(db_rows, file_check)
    if total_cell_row is not None:
        rows.append(total_cell_row)
    columns = comparison_columns(messages.CARD_COLUMN_CONTENT, messages.CARD_COLUMN_FILE, messages.CARD_COLUMN_DB)
    return Card(TOTALS_CARD, messages.CARD_TITLE_TOTALS, columns, rows)


def empty_cells_card(file_check: dict) -> Card | None:
    rows = [
        CardRow([column['column'], value['value'], value['cell_count'], None], messages.CARD_VERDICT_NOTED)
        for table in file_check.get('tables', [])
        for column in table['empty_cell_details']
        for value in sorted(column['values'], key=lambda value: -value['cell_count'])
    ]
    if not rows:
        return None
    columns = [
        CardColumn(messages.CARD_COLUMN_COLUMN),
        CardColumn(messages.CARD_COLUMN_FILE_VALUE),
        CardColumn(messages.CARD_COLUMN_CELL_COUNT, align_right=True),
        CardColumn(messages.CARD_COLUMN_DB),
        CardColumn(messages.CARD_COLUMN_VERDICT),
    ]
    count = sum(row.cells[2] for row in rows)
    return Card(EMPTY_CELLS_CARD, messages.CARD_TITLE_EMPTY_CELLS, columns, rows, count=count)


def dimension_matrix(ctx: LoadContext, table: FormTable, file_rows: list[dict], db_rows: list[dict]) -> DimensionMatrix:
    dimensions: dict[str, DimensionGroups] = {}
    has_mismatch = False
    for dimension in DIMENSIONS.get(table.name, []):
        tallies = _tally_groups(dimension.column, file_rows, db_rows)
        has_mismatch = has_mismatch or any(tally.has_mismatch for tally in tallies.values())
        groups = [
            GroupCounts(
                key,
                tally.file_rows,
                tally.db_rows,
                as_number(tally.file_quantity),
                as_number(tally.db_quantity),
            )
            for key, tally in tallies.items()
        ]
        dimensions[dimension.column] = DimensionGroups(dimension.label, groups)
    order = [dimension.column for dimension in DIMENSIONS.get(table.name, [])]
    return DimensionMatrix(table.name, ctx.year, dimensions, order, has_mismatch)


def dimension_card(stored: dict, *, group_by: str | None, page: int, page_size: int) -> Card:
    matrix = DimensionMatrix.from_json(stored)
    if not matrix.order:
        return Card(BY_DIMENSION_CARD, '')
    column = group_by if group_by in matrix.dimensions else matrix.order[0]
    dimension = matrix.dimensions[column]
    groups = _sorted_groups(column, dimension.groups)
    start = (page - 1) * page_size
    label = dimension.label
    choices = [OptionChoice(choice, matrix.dimensions[choice].label) for choice in matrix.order]
    return Card(
        BY_DIMENSION_CARD,
        _dimension_title(label),
        group_count_columns(label, messages.CARD_COLUMN_FILE_QUANTITY, messages.CARD_COLUMN_DB_QUANTITY),
        [_dimension_row(matrix, column, group) for group in groups[start : start + page_size]],
        count=len(groups),
        options=[CardOption(GROUP_BY_OPTION, messages.CARD_OPTION_GROUP_BY, column, matrix.order[0], choices)],
        totals=_dimension_totals(groups),
        pagination=Pagination(page, page_size, len(groups)),
    )


def codes_card(table: FormTable, file_rows: list[dict], db_rows: list[dict]) -> Card:
    rows = []
    for code in CODE_COUNTS.get(table.name, []):
        file_codes = _distinct_keys(file_rows, code.column)
        db_codes = _distinct_keys(db_rows, code.column)
        matches = file_codes == db_codes
        rows.append(
            CardRow([code.label, len(file_codes), len(db_codes)], verdict(matches, messages.CARD_VERDICT_MATCH))
        )
    return Card(CODES_CARD, messages.CARD_TITLE_SAMPLE_SUBCON_CODES, codes_columns(), rows)


def before_after_card(
    ctx: LoadContext,
    table: FormTable,
    before: dict[str, int],
    after: dict[str, int],
    tables: list[DomainTable],
) -> Card:
    written = ctx.table_result(table).rows_silver
    rows = [
        _before_after_row(
            ctx,
            domain_table,
            before.get(domain_table.name, 0),
            after.get(domain_table.name, 0),
            written if domain_table.name == table.name else None,
        )
        for domain_table in tables
    ]
    title = messages.CARD_TITLE_DOMAIN_BEFORE_AFTER.format(domain=ctx.domain_code, year=ctx.year or '')
    return Card(BEFORE_AFTER_CARD, title, before_after_columns(messages.CARD_COLUMN_TABLE), rows)


def b4_result(cards: dict, file_check: dict, table_name: str) -> str:
    parts = _total_parts(cards[TOTALS_CARD], file_check)
    names = [code.short_name for code in CODE_COUNTS.get(table_name, []) if code.short_name]
    if names:
        parts.append(messages.CARD_B4_CODES_MATCH.format(names=', '.join(names)))
    return '; '.join(parts) + '.'


def domain_tables(ctx: LoadContext) -> list[DomainTable]:
    rows = warehouse_sql.query(
        ctx.conn,
        """
        SELECT ft.name, ft.label FROM ctl.dataset ds
          JOIN ctl.form_table ft ON ft.table_id = ds.table_id
          LEFT JOIN ctl.domain_form df ON df.domain_id = ds.domain_id
                                      AND df.form_id = ft.form_id
         WHERE ds.domain_id = %s AND ft.kind = 'fact' AND ds.is_visible
         ORDER BY df.position, ds.display_order, ft.name
        """,
        (ctx.domain_id,),
    )
    return [DomainTable(row['name'], row['label']) for row in rows if row['name'] in ctx.year_columns]


def domain_row_counts(ctx: LoadContext) -> dict[str, int]:
    statement = 'SELECT count(*) FROM {table} WHERE domain_id = %s AND is_current AND {year} = %s'
    return {
        table.name: warehouse_sql.scalar(
            ctx.conn,
            sql.SQL(statement).format(
                table=sql.Identifier('gold', table.name), year=sql.Identifier(ctx.year_columns[table.name])
            ),
            (ctx.domain_id, ctx.year),
        )
        for table in domain_tables(ctx)
    }


def _group_key(column: str, value) -> str:
    if value is None:
        return ''
    return month_key(value) if column == DELIVERY_DATE_COLUMN else str(value)


def _distinct_keys(rows: list[dict], column: str) -> set[str]:
    return {_group_key(column, row.get(column)) for row in rows} - {''}


def _column_total_row(
    ctx: LoadContext, table: FormTable, column: str, file_rows: list[dict], db_rows: list[dict]
) -> CardRow:
    file_total = column_total(file_rows, [column])
    db_total = column_total(db_rows, [column])
    return CardRow(
        [
            messages.CARD_COLUMN_TOTAL.format(column=column),
            as_number(file_total),
            as_number(db_total),
            as_number(db_total - file_total),
        ],
        verdict(file_total == db_total),
        link=table_link(ctx, table, 'gold'),
    )


def _total_cell_row(db_rows: list[dict], file_check: dict) -> CardRow | None:
    total_cell = file_check.get('total_cell')
    if not total_cell or total_cell.get('value') is None:
        return None
    try:
        file_total = Decimal(total_cell['value'])
    except ArithmeticError:
        return None
    db_total = column_total(db_rows, [QUANTITY_COLUMN])
    cells = [
        messages.CARD_TOTAL_CELL.format(cell=total_cell['reference'], header=total_cell['header']),
        as_number(file_total),
        as_number(db_total),
        as_number(db_total - file_total),
    ]
    if not total_cell.get('informational'):
        return CardRow(cells, verdict(file_total == db_total))
    note = messages.CARD_TOTAL_CELL_VISIBLE_ONLY.format(
        visible=format_integer(file_check.get('visible_row_count', 0)),
        hidden=format_integer(file_check.get('hidden_row_count', 0)),
    )
    return CardRow(cells, messages.CARD_VERDICT_NOTED, note=note)


def _tally_groups(column: str, file_rows: list[dict], db_rows: list[dict]) -> dict[str, _GroupTally]:
    tallies: dict[str, _GroupTally] = {}
    for row in file_rows:
        tally = tallies.setdefault(_group_key(column, row.get(column)), _GroupTally())
        tally.file_rows += 1
        if row.get(QUANTITY_COLUMN) is not None:
            tally.file_quantity += Decimal(row[QUANTITY_COLUMN])
    for row in db_rows:
        tally = tallies.setdefault(_group_key(column, row.get(column)), _GroupTally())
        tally.db_rows += 1
        if row.get(QUANTITY_COLUMN) is not None:
            tally.db_quantity += Decimal(row[QUANTITY_COLUMN])
    return tallies


def _dimension_title(label: str) -> str:
    return messages.CARD_TITLE_BY_DIMENSION.format(dimension=label[0].lower() + label[1:])


def _has_mismatched_group(dimension: DimensionGroups) -> bool:
    return any(group.has_mismatch for group in dimension.groups)


def _sorted_groups(column: str, groups: list[GroupCounts]) -> list[GroupCounts]:
    if column == DELIVERY_DATE_COLUMN:
        return sorted(groups, key=lambda group: (group.key == '', group.key))
    return sorted(groups, key=lambda group: (-group.file_quantity, group.key == '', group.key))


def _dimension_row(matrix: DimensionMatrix, column: str, group: GroupCounts) -> CardRow:
    difference = Decimal(str(group.db_quantity)) - Decimal(str(group.file_quantity))
    row = CardRow(
        [
            _group_label(column, group.key),
            group.file_rows,
            group.db_rows,
            group.file_quantity,
            group.db_quantity,
            as_number(difference),
        ],
        verdict(not group.has_mismatch),
    )
    if group.key:
        row.link = gold_link(matrix.table, matrix.year, query=_search_text(column, group.key))
    return row


def _dimension_totals(groups: list[GroupCounts]) -> list:
    return totals_row(
        sum(group.file_rows for group in groups),
        sum(group.db_rows for group in groups),
        sum(Decimal(str(group.file_quantity)) for group in groups),
        sum(Decimal(str(group.db_quantity)) for group in groups),
    )


def _group_label(column: str, key: str) -> str:
    if column != DELIVERY_DATE_COLUMN:
        return key or messages.CARD_EMPTY_VALUE
    if not key:
        return messages.CHECK_NO_DELIVERY_DATE
    year, month = key.split('-')
    return messages.CARD_MONTH_OF_YEAR.format(month=int(month), year=year)


def _search_text(column: str, key: str) -> str:
    if column != DELIVERY_DATE_COLUMN:
        return key
    year, month = key.split('-')
    return f'{month}/{year}'


def _before_after_row(
    ctx: LoadContext, domain_table: DomainTable, before: int, after: int, written: int | None
) -> CardRow:
    if written is not None:
        write_mode = messages.CARD_WRITE_OVERWRITE if before else messages.CARD_WRITE_APPEND
        row_verdict = verdict(after == written)
    else:
        write_mode = messages.CARD_WRITE_UNTOUCHED
        row_verdict = verdict(after == before, messages.CARD_VERDICT_UNCHANGED)
    in_file = messages.CARD_YES if written is not None else messages.CARD_NO
    return CardRow(
        [domain_table.label, in_file, before, after, write_mode],
        row_verdict,
        note=domain_table.name,
        link=gold_link(domain_table.name, ctx.year) if after else None,
    )


def _total_parts(card: Card, file_check: dict) -> list[str]:
    prefix = messages.CARD_COLUMN_TOTAL.format(column='')
    parts: list[str] = []
    for row in card.rows:
        label = row.cells[0]
        if label.startswith(prefix):
            part = messages.CARD_B4_COLUMN_TOTAL.format(
                column=label.removeprefix(prefix),
                file_total=format_amount(Decimal(str(row.cells[1]))),
                db_total=format_amount(Decimal(str(row.cells[2]))),
            )
            parts.append(part if parts else part[0].upper() + part[1:])
        elif row.verdict != messages.CARD_VERDICT_NOTED and parts:
            total_cell = file_check.get('total_cell') or {}
            parts[0] += messages.CARD_B4_EQUALS_TOTAL_CELL.format(cell=total_cell.get('reference', ''))
    return parts
