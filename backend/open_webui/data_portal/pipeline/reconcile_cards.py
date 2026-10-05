from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import NamedTuple

from psycopg import sql

from .. import messages
from ..db import sql as warehouse_sql
from ..formatting import format_amount, format_integer
from ..registry.schema import FormTable
from ..sources import header_table
from . import sample_subcon_cards
from .card_model import (
    ALL_COLUMNS,
    AMOUNT_BY_GROUP_CARD,
    BEFORE_AFTER_CARD,
    BY_DIMENSION_CARD,
    CARD_ORDER,
    CODES_CARD,
    COLUMN_OPTION,
    EMPTY_CELLS_CARD,
    GROUP_BY_OPTION,
    ROW_COUNT_CARD,
    TABLE_OPTION,
    TOTALS_CARD,
    ZERO,
    Card,
    CardColumn,
    CardOption,
    CardRow,
    Cell,
    OptionChoice,
    SheetLink,
    as_number,
    before_after_columns,
    codes_columns,
    column_total,
    comparison_columns,
    gold_link,
    group_count_columns,
    stored_card_view,
    table_link,
    totals_row,
    verdict,
)
from .context import LoadContext
from .sample_subcon_cards import DimensionMatrix

RESULTS_TABLE = 'fact_ket_qua_kd'
COSTS_TABLE = 'fact_chi_phi'
CUSTOMERS_TABLE = 'dim_khach_hang'
COST_ITEMS_TABLE = 'dim_khoan_cp'
MONTH_COLUMN = 'ky_thang'
CUSTOMER_CODE_COLUMN = 'ma_khach'
CUSTOMER_NAME_COLUMN = 'ten_khach'
COST_ITEM_CODE_COLUMN = 'ma_khoan_cp'
COST_ITEM_NAME_COLUMN = 'ten_khoan'

CARD_TITLES = {
    ROW_COUNT_CARD: messages.CARD_TITLE_ROW_COUNT,
    TOTALS_CARD: messages.CARD_TITLE_AMOUNT_TOTALS,
    EMPTY_CELLS_CARD: messages.CARD_TITLE_EMPTY_CELLS,
    BY_DIMENSION_CARD: messages.CARD_TITLE_BY_DIMENSION,
    CODES_CARD: messages.CARD_TITLE_CODES,
    BEFORE_AFTER_CARD: messages.CARD_TITLE_MONTHS_BEFORE_AFTER,
    AMOUNT_BY_GROUP_CARD: messages.CARD_TITLE_AMOUNT_BY_GROUP,
}
UNFILLED_TITLE_PLACEHOLDERS = {'year': '{nam}', 'dimension': '{chia_theo}'}

GROUP_BY_LABELS = {
    MONTH_COLUMN: messages.CARD_GROUP_MONTH,
    'ma_nhom_kd': messages.CARD_GROUP_BUSINESS_GROUP,
    COST_ITEM_CODE_COLUMN: messages.CARD_GROUP_COST_ITEM,
}

DISTINCT_CODE_ROWS = (
    (RESULTS_TABLE, CUSTOMER_CODE_COLUMN, messages.CARD_CODES_RESULT_CUSTOMERS),
    (RESULTS_TABLE, 'ma_nhom_kd', messages.CARD_CODES_RESULT_GROUPS),
    (COSTS_TABLE, CUSTOMER_CODE_COLUMN, messages.CARD_CODES_COST_CUSTOMERS),
    (COSTS_TABLE, COST_ITEM_CODE_COLUMN, messages.CARD_CODES_COST_ITEMS),
)


@dataclass
class PeriodTotals:
    row_count: int
    total: Decimal


@dataclass
class LoadSnapshot:
    periods: dict[str, dict[str, PeriodTotals]]
    domain_row_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class AmountGroup:
    file_rows: int
    db_rows: int
    file_amounts: dict[str, Decimal]
    db_amounts: dict[str, Decimal]

    @property
    def has_mismatch(self) -> bool:
        return self.file_rows != self.db_rows or self.file_amounts != self.db_amounts

    def to_json(self) -> dict:
        return {
            'file_rows': self.file_rows,
            'db_rows': self.db_rows,
            'file_amounts': {column: str(amount) for column, amount in self.file_amounts.items()},
            'db_amounts': {column: str(amount) for column, amount in self.db_amounts.items()},
        }

    @classmethod
    def from_json(cls, data: dict) -> AmountGroup:
        return cls(
            data['file_rows'],
            data['db_rows'],
            {column: Decimal(amount) for column, amount in data['file_amounts'].items()},
            {column: Decimal(amount) for column, amount in data['db_amounts'].items()},
        )


@dataclass
class AmountTable:
    label: str
    columns: list[OptionChoice]
    groupings: dict[str, dict[str, AmountGroup]]
    grouping_order: list[str]

    def to_json(self) -> dict:
        return {
            'label': self.label,
            'columns': [column.to_json() for column in self.columns],
            'groupings': {
                group_by: {key: group.to_json() for key, group in groups.items()}
                for group_by, groups in self.groupings.items()
            },
            'grouping_order': list(self.grouping_order),
        }

    @classmethod
    def from_json(cls, data: dict) -> AmountTable:
        groupings = {
            group_by: {key: AmountGroup.from_json(group) for key, group in groups.items()}
            for group_by, groups in data['groupings'].items()
        }
        return cls(
            data['label'],
            [OptionChoice(column['value'], column['label']) for column in data['columns']],
            groupings,
            data.get('grouping_order') or list(groupings),
        )


@dataclass
class AmountMatrix:
    tables: dict[str, AmountTable]
    table_order: list[str]
    cost_item_names: dict[str, str]
    has_mismatch: bool
    year: int | None

    def to_json(self) -> dict:
        return {
            'key': AMOUNT_BY_GROUP_CARD,
            'tables': {name: table.to_json() for name, table in self.tables.items()},
            'table_order': list(self.table_order),
            'cost_item_names': dict(self.cost_item_names),
            'has_mismatch': self.has_mismatch,
            'year': self.year,
        }

    @classmethod
    def from_json(cls, data: dict) -> AmountMatrix:
        tables = {name: AmountTable.from_json(table) for name, table in data.get('tables', {}).items()}
        return cls(
            tables,
            data.get('table_order') or list(tables),
            data.get('cost_item_names', {}),
            data.get('has_mismatch', False),
            data.get('year'),
        )


@dataclass
class ReconcileCards:
    cards: dict[str, Card | AmountMatrix | DimensionMatrix]
    mismatched: list[str]
    b4_result: str

    def to_json(self) -> dict:
        return {key: card.to_json() for key, card in self.cards.items()}


@dataclass
class CardSelection:
    card: str = ''
    table: str | None = None
    column: str | None = None
    group_by: str | None = None
    page: int = 1
    page_size: int = 25


class _LayerCounts(NamedTuple):
    file: int
    bronze: int
    silver: int
    gold: int
    duplicates: int


@dataclass
class _UnlistedCustomer:
    name: str | None = None
    months: set = field(default_factory=set)


@dataclass
class _AmountView:
    matrix: AmountMatrix
    table: str
    group_by: str
    summed_columns: list[str]


@dataclass
class _MonthSides:
    tables: list[FormTable]
    before: dict[str, dict[str, PeriodTotals]]
    after: dict[str, dict[str, PeriodTotals]]
    in_file: dict[str, dict[str, int]]


def snapshot_before(ctx: LoadContext) -> LoadSnapshot:
    periods = {
        table.name: _gold_period_totals(ctx, table)
        for table in ctx.form.tables
        if not table.is_dim and table.year_column is not None
    }
    snapshot = LoadSnapshot(periods)
    if _is_header_table(ctx):
        snapshot.domain_row_counts = sample_subcon_cards.domain_row_counts(ctx)
    return snapshot


def build_cards(ctx: LoadContext, before: LoadSnapshot, file_check: dict) -> ReconcileCards:
    file_rows = {table.name: _file_rows(ctx, table) for table in ctx.form.tables}
    db_rows = {table.name: _db_rows(ctx, table, file_rows[table.name]) for table in ctx.form.tables}
    cards: dict[str, Card | AmountMatrix | DimensionMatrix] = {ROW_COUNT_CARD: _row_count_card(ctx, file_check)}
    if _is_header_table(ctx):
        cards.update(_header_table_cards(ctx, before, file_check, file_rows, db_rows))
    else:
        cards[TOTALS_CARD] = _amount_totals_card(ctx, file_rows, db_rows)
        cards[AMOUNT_BY_GROUP_CARD] = _amount_matrix(ctx, file_rows, db_rows)
        cards[CODES_CARD] = _codes_card(ctx, file_rows, db_rows)
        cards[BEFORE_AFTER_CARD] = _months_before_after_card(ctx, before, file_rows)
    mismatched = [key for key, card in cards.items() if card.has_mismatch]
    if _is_header_table(ctx):
        result = sample_subcon_cards.b4_result(cards, mismatched, file_check, ctx.form.tables[0].name)
    else:
        result = _amounts_b4_result(cards, mismatched)
    return ReconcileCards(cards, mismatched, result)


def mismatch_label(card_key: str) -> str:
    title = CARD_TITLES.get(card_key)
    return card_key if title is None else title.format(**UNFILLED_TITLE_PLACEHOLDERS)


def render_cards(stored: dict, selection: CardSelection, *, cancelled: bool) -> list[dict]:
    cards = []
    for key in CARD_ORDER:
        if key not in stored or (selection.card and selection.card != key):
            continue
        if key == AMOUNT_BY_GROUP_CARD:
            card = _amount_card(stored[key], selection).to_json()
        elif key == BY_DIMENSION_CARD:
            card = sample_subcon_cards.dimension_card(
                stored[key], group_by=selection.group_by, page=selection.page, page_size=selection.page_size
            ).to_json()
        else:
            card = stored_card_view(stored[key], cancelled=cancelled and key == BEFORE_AFTER_CARD)
        cards.append(card)
    return cards


def _is_header_table(ctx: LoadContext) -> bool:
    return ctx.form.source_kind == header_table.KIND


def _header_table_cards(
    ctx: LoadContext, before: LoadSnapshot, file_check: dict, file_rows: dict, db_rows: dict
) -> dict[str, Card | DimensionMatrix]:
    table = ctx.form.tables[0]
    table_file_rows, table_db_rows = file_rows[table.name], db_rows[table.name]
    cards: dict[str, Card | DimensionMatrix] = {
        TOTALS_CARD: sample_subcon_cards.totals_card(ctx, table, table_file_rows, table_db_rows, file_check)
    }
    empty_cells = sample_subcon_cards.empty_cells_card(file_check)
    if empty_cells is not None:
        cards[EMPTY_CELLS_CARD] = empty_cells
    cards[BY_DIMENSION_CARD] = sample_subcon_cards.dimension_matrix(ctx, table, table_file_rows, table_db_rows)
    cards[CODES_CARD] = sample_subcon_cards.codes_card(table, table_file_rows, table_db_rows)
    cards[BEFORE_AFTER_CARD] = sample_subcon_cards.before_after_card(
        ctx,
        table,
        before.domain_row_counts,
        sample_subcon_cards.domain_row_counts(ctx),
        sample_subcon_cards.domain_tables(ctx),
    )
    return cards


def _typed_value(table: FormTable, column: str, raw):
    if raw is None:
        return None
    parsed = table.column(column).handler.parse(raw)
    return parsed.value if parsed.ok else None


def _file_rows(ctx: LoadContext, table: FormTable) -> list[dict]:
    statement = sql.SQL('SELECT {} FROM {} WHERE load_id = %s').format(
        warehouse_sql.column_list(table.column_names), sql.Identifier('bronze', table.name)
    )
    rows = warehouse_sql.query(ctx.conn, statement, (ctx.load_id,))
    return [{column: _typed_value(table, column, row[column]) for column in table.column_names} for row in rows]


def _load_scope(ctx: LoadContext, table: FormTable, file_rows: list[dict]) -> tuple[sql.Composed, list]:
    conditions = [sql.SQL('t.domain_id = %s'), sql.SQL('t.is_current')]
    params: list = [ctx.domain_id]
    if table.year_column is not None:
        conditions.append(sql.SQL('t.{} IS NOT DISTINCT FROM %s').format(sql.Identifier(table.year_column.name)))
        params.append(ctx.year)
    if table.partition_by:
        column = table.partition_column.name
        conditions.append(sql.SQL('t.{} = ANY(%s)').format(sql.Identifier(column)))
        params.append(sorted({row[column] for row in file_rows if row[column] is not None}))
    return sql.SQL(' AND ').join(conditions), params


def _db_rows(ctx: LoadContext, table: FormTable, file_rows: list[dict]) -> list[dict]:
    condition, params = _load_scope(ctx, table, file_rows)
    statement = sql.SQL('SELECT {} FROM {} t WHERE {}').format(
        warehouse_sql.column_list(table.column_names), sql.Identifier('gold', table.name), condition
    )
    rows = warehouse_sql.query(ctx.conn, statement, params)
    if table.is_dim and table.business_key:
        keys = {tuple(row[column] for column in table.business_key) for row in file_rows}
        rows = [row for row in rows if tuple(row[column] for column in table.business_key) in keys]
    return rows


def _gold_period_totals(ctx: LoadContext, table: FormTable) -> dict[str, PeriodTotals]:
    amount_columns = [column.name for column in table.amount_columns]
    if amount_columns:
        total = sql.SQL(' + ').join(
            sql.SQL('coalesce(sum(t.{}), 0)').format(sql.Identifier(column)) for column in amount_columns
        )
    else:
        total = sql.SQL('0')
    if table.partition_by:
        period = sql.SQL('t.{}::text').format(sql.Identifier(table.partition_column.name))
    else:
        period = sql.SQL("'*'")
    statement = sql.SQL(
        'SELECT {period} AS period, count(*) AS row_count, {total} AS total FROM {table} t '
        ' WHERE t.domain_id = %s AND t.is_current AND t.{year} IS NOT DISTINCT FROM %s '
        ' GROUP BY 1'
    ).format(
        period=period,
        total=total,
        table=sql.Identifier('gold', table.name),
        year=sql.Identifier(table.year_column.name),
    )
    rows = warehouse_sql.query(ctx.conn, statement, (ctx.domain_id, ctx.year))
    return {row['period']: PeriodTotals(row['row_count'], Decimal(str(row['total']))) for row in rows if row['period']}


def _row_count_card(ctx: LoadContext, file_check: dict) -> Card:
    sheet_numbers = {name: number for number, name in enumerate(file_check.get('sheets', []), start=1)}
    sheet_by_table = {table['table']: table['sheet'] for table in file_check.get('tables', [])}
    rows, totals = [], [0, 0, 0, 0, 0]
    for table in ctx.form.tables_by_display_order:
        counts = _layer_counts(ctx, table)
        sheet = sheet_numbers.get(sheet_by_table.get(table.name, ''))
        rows.append(_row_count_row(ctx, table, counts, sheet))
        totals = [total + count for total, count in zip(totals, counts)]
    columns = [
        CardColumn(messages.CARD_COLUMN_TABLE),
        CardColumn(messages.CARD_COLUMN_EXTRACTED, align_right=True),
        CardColumn(messages.CARD_COLUMN_BRONZE, align_right=True),
        CardColumn(messages.CARD_COLUMN_SILVER, align_right=True),
        CardColumn(messages.CARD_COLUMN_GOLD, align_right=True),
        CardColumn(messages.CARD_COLUMN_DUPLICATES_REMOVED, align_right=True),
        CardColumn(messages.CARD_COLUMN_VERDICT),
    ]
    totals_cells = [messages.CARD_TOTAL, *totals, None]
    return Card(ROW_COUNT_CARD, messages.CARD_TITLE_ROW_COUNT, columns, rows, totals=totals_cells)


def _layer_counts(ctx: LoadContext, table: FormTable) -> _LayerCounts:
    result = ctx.table_result(table)
    return _LayerCounts(
        result.rows_file,
        result.rows_bronze,
        result.rows_silver + result.rows_unchanged,
        result.rows_gold + result.rows_unchanged,
        result.rows_duplicate,
    )


def _row_count_row(ctx: LoadContext, table: FormTable, counts: _LayerCounts, sheet: int | None) -> CardRow:
    expected = counts.bronze - counts.duplicates
    if counts.bronze == counts.file and counts.silver == expected and counts.gold == counts.silver:
        row_verdict = messages.CARD_VERDICT_COMPLETE
        note = None
        if counts.duplicates:
            note = messages.CARD_COMPLETE_AFTER_DEDUP.format(count=format_integer(counts.duplicates))
    else:
        differences = (counts.bronze - counts.file, counts.silver - expected, counts.gold - counts.silver)
        difference = min(differences, key=lambda value: (value == 0, value))
        row_verdict = messages.CARD_VERDICT_MISSING if difference < 0 else messages.CARD_VERDICT_EXTRA
        note = None
        if counts.silver != expected:
            note = messages.CARD_BRONZE_SILVER_DIFFERENCE.format(count=format_integer(abs(counts.silver - expected)))
    cells = [
        table.label,
        Cell(counts.file, SheetLink(sheet) if sheet else None),
        Cell(counts.bronze, table_link(ctx, table, 'bronze')),
        Cell(counts.silver, table_link(ctx, table, 'silver')),
        Cell(counts.gold, table_link(ctx, table, 'gold')),
        counts.duplicates,
    ]
    return CardRow(cells, row_verdict, note=table.name, link=table_link(ctx, table, 'gold'), verdict_note=note)


def _amount_totals_card(ctx: LoadContext, file_rows: dict, db_rows: dict) -> Card:
    rows = []
    tables = (table for table in ctx.form.tables if table.amount_columns and not table.is_dim)
    for table in sorted(tables, key=lambda table: table.name):
        columns = [column.name for column in table.amount_columns]
        file_total = column_total(file_rows[table.name], columns)
        db_total = column_total(db_rows[table.name], columns)
        cells = [table.label, as_number(file_total), as_number(db_total), as_number(db_total - file_total)]
        rows.append(CardRow(cells, verdict(file_total == db_total), link=table_link(ctx, table, 'gold')))
    columns = comparison_columns(
        messages.CARD_COLUMN_TABLE, messages.CARD_COLUMN_FILE_TOTAL, messages.CARD_COLUMN_DB_TOTAL
    )
    return Card(TOTALS_CARD, messages.CARD_TITLE_AMOUNT_TOTALS, columns, rows)


def _amount_matrix(ctx: LoadContext, file_rows: dict, db_rows: dict) -> AmountMatrix:
    tables = {
        table.name: _amount_table(table, file_rows[table.name], db_rows[table.name])
        for table in ctx.form.tables_by_display_order
        if not table.is_dim and table.amount_columns
    }
    has_mismatch = any(
        group.has_mismatch
        for table in tables.values()
        for groups in table.groupings.values()
        for group in groups.values()
    )
    return AmountMatrix(tables, list(tables), _cost_item_names(ctx, file_rows), has_mismatch, ctx.year)


def _cost_item_names(ctx: LoadContext, file_rows: dict) -> dict[str, str]:
    names: dict[str, str] = {}
    for table in ctx.form.tables:
        if not table.is_dim or not {COST_ITEM_CODE_COLUMN, COST_ITEM_NAME_COLUMN} <= set(table.column_names):
            continue
        for row in file_rows[table.name]:
            if row[COST_ITEM_CODE_COLUMN] is not None and row[COST_ITEM_NAME_COLUMN] is not None:
                names.setdefault(str(row[COST_ITEM_CODE_COLUMN]), str(row[COST_ITEM_NAME_COLUMN]))
    return names


def _amount_table(table: FormTable, file_rows: list[dict], db_rows: list[dict]) -> AmountTable:
    columns = [column.name for column in table.amount_columns]
    groupings = {
        group_by: _amount_groups(group_by, columns, file_rows, db_rows)
        for group_by in GROUP_BY_LABELS
        if group_by in table.column_names
    }
    choices = [OptionChoice(column.name, column.label) for column in table.amount_columns]
    return AmountTable(table.label, choices, groupings, list(groupings))


def _amount_groups(
    group_by: str, columns: list[str], file_rows: list[dict], db_rows: list[dict]
) -> dict[str, AmountGroup]:
    groups: dict[str, AmountGroup] = {}
    for row in file_rows:
        group = _amount_group(groups, row[group_by], columns)
        group.file_rows += 1
        _add_amounts(group.file_amounts, row, columns)
    for row in db_rows:
        group = _amount_group(groups, row[group_by], columns)
        group.db_rows += 1
        _add_amounts(group.db_amounts, row, columns)
    return groups


def _amount_group(groups: dict[str, AmountGroup], value, columns: list[str]) -> AmountGroup:
    key = '' if value is None else str(value)
    if key not in groups:
        groups[key] = AmountGroup(0, 0, dict.fromkeys(columns, ZERO), dict.fromkeys(columns, ZERO))
    return groups[key]


def _add_amounts(amounts: dict[str, Decimal], row: dict, columns: list[str]) -> None:
    for column in columns:
        if row.get(column) is not None:
            amounts[column] += Decimal(row[column])


def _amount_card(stored: dict, selection: CardSelection) -> Card:
    matrix = AmountMatrix.from_json(stored)
    if not matrix.tables:
        return Card(AMOUNT_BY_GROUP_CARD, messages.CARD_TITLE_AMOUNT_BY_GROUP, options=[])
    table_name = selection.table if selection.table in matrix.tables else matrix.table_order[0]
    amount_table = matrix.tables[table_name]
    column_choices = list(amount_table.columns)
    if len(column_choices) > 1:
        column_choices.append(OptionChoice(ALL_COLUMNS, messages.CARD_ALL_AMOUNT_COLUMNS))
    column_values = [choice.value for choice in column_choices]
    column = selection.column if selection.column in column_values else column_values[0]
    group_by = selection.group_by if selection.group_by in amount_table.groupings else amount_table.grouping_order[0]
    summed = [choice.value for choice in amount_table.columns] if column == ALL_COLUMNS else [column]
    view = _AmountView(matrix, table_name, group_by, summed)
    groups = amount_table.groupings[group_by]
    keys = sorted(groups, key=_group_sort_key)
    table_choices = [OptionChoice(name, matrix.tables[name].label) for name in matrix.table_order]
    group_by_choices = [OptionChoice(name, GROUP_BY_LABELS[name]) for name in amount_table.grouping_order]
    options = [
        CardOption(TABLE_OPTION, messages.CARD_OPTION_TABLE, table_name, matrix.table_order[0], table_choices),
        CardOption(COLUMN_OPTION, messages.CARD_OPTION_AMOUNT_COLUMN, column, column_values[0], column_choices),
        CardOption(
            GROUP_BY_OPTION, messages.CARD_OPTION_GROUP_BY, group_by, amount_table.grouping_order[0], group_by_choices
        ),
    ]
    return Card(
        AMOUNT_BY_GROUP_CARD,
        messages.CARD_TITLE_AMOUNT_BY_GROUP,
        group_count_columns(GROUP_BY_LABELS[group_by], messages.CARD_COLUMN_FILE_TOTAL, messages.CARD_COLUMN_DB_TOTAL),
        [_amount_row(view, key, groups[key]) for key in keys],
        options=options,
        totals=_amount_totals(view, [groups[key] for key in keys]),
    )


def _group_sort_key(key: str) -> tuple:
    return (key == '', int(key) if key.isdigit() else 0, key)


def _summed_amounts(view: _AmountView, group: AmountGroup) -> tuple[Decimal, Decimal]:
    file_amount = sum((group.file_amounts[column] for column in view.summed_columns), ZERO)
    db_amount = sum((group.db_amounts[column] for column in view.summed_columns), ZERO)
    return file_amount, db_amount


def _amount_row(view: _AmountView, key: str, group: AmountGroup) -> CardRow:
    file_amount, db_amount = _summed_amounts(view, group)
    matches = group.file_rows == group.db_rows and file_amount == db_amount
    if view.group_by == MONTH_COLUMN:
        label = messages.CARD_MONTH.format(month=key) if key else messages.CARD_EMPTY_VALUE
        link = gold_link(view.table, view.matrix.year, period=int(key)) if key.isdigit() else None
    else:
        label = key or messages.CARD_EMPTY_VALUE
        link = gold_link(view.table, view.matrix.year, query=key) if key else None
    note = None
    if view.group_by == COST_ITEM_CODE_COLUMN:
        note = view.matrix.cost_item_names.get(key)
    cells = [
        label,
        group.file_rows,
        group.db_rows,
        as_number(file_amount),
        as_number(db_amount),
        as_number(db_amount - file_amount),
    ]
    return CardRow(cells, verdict(matches), note=note, link=link)


def _amount_totals(view: _AmountView, groups: list[AmountGroup]) -> list:
    file_rows = db_rows = 0
    file_total = db_total = ZERO
    for group in groups:
        file_amount, db_amount = _summed_amounts(view, group)
        file_rows += group.file_rows
        db_rows += group.db_rows
        file_total += file_amount
        db_total += db_amount
    return totals_row(file_rows, db_rows, file_total, db_total)


def _codes_card(ctx: LoadContext, file_rows: dict, db_rows: dict) -> Card:
    present = {table.name for table in ctx.form.tables}
    rows = []
    if RESULTS_TABLE in present:
        rows.append(_result_months_row(file_rows[RESULTS_TABLE], db_rows[RESULTS_TABLE]))
    for table_name, column, label in DISTINCT_CODE_ROWS:
        if table_name in present:
            rows.append(_distinct_count_row(label, file_rows[table_name], db_rows[table_name], column))
    if CUSTOMERS_TABLE in present:
        rows.append(_customer_catalog_row(file_rows[CUSTOMERS_TABLE], db_rows[CUSTOMERS_TABLE]))
    if COST_ITEMS_TABLE in present:
        rows.append(
            _distinct_count_row(
                messages.CARD_CODES_COST_ITEM_CATALOG,
                file_rows[COST_ITEMS_TABLE],
                db_rows[COST_ITEMS_TABLE],
                COST_ITEM_CODE_COLUMN,
            )
        )
    if CUSTOMERS_TABLE in present and (RESULTS_TABLE in present or COSTS_TABLE in present):
        rows.append(_unlisted_customers_row(file_rows))
        rows.append(_customers_with_many_names_row(file_rows[CUSTOMERS_TABLE]))
    return Card(CODES_CARD, messages.CARD_TITLE_CODES, codes_columns(), rows)


def _distinct(rows: list[dict], column: str) -> set:
    return {row[column] for row in rows if row.get(column) is not None}


def _codes_row(label: str, file_value, db_value, matches: bool) -> CardRow:
    return CardRow([label, file_value, db_value], verdict(matches, messages.CARD_VERDICT_MATCH))


def _distinct_count_row(label: str, file_rows: list[dict], db_rows: list[dict], column: str) -> CardRow:
    file_codes, db_codes = _distinct(file_rows, column), _distinct(db_rows, column)
    return _codes_row(label, len(file_codes), len(db_codes), file_codes == db_codes)


def _month_list(months: list) -> str:
    if not months:
        return '0'
    return messages.CARD_MONTH_LIST.format(count=len(months), months=', '.join(str(month) for month in months))


def _result_months_row(file_rows: list[dict], db_rows: list[dict]) -> CardRow:
    file_months = sorted(_distinct(file_rows, MONTH_COLUMN))
    db_months = sorted(_distinct(db_rows, MONTH_COLUMN))
    return _codes_row(
        messages.CARD_CODES_RESULT_MONTHS, _month_list(file_months), _month_list(db_months), file_months == db_months
    )


def _customer_catalog_row(file_rows: list[dict], db_rows: list[dict]) -> CardRow:
    file_codes = _distinct(file_rows, CUSTOMER_CODE_COLUMN)
    db_codes = _distinct(db_rows, CUSTOMER_CODE_COLUMN)
    file_text = messages.CARD_CODES_WITH_ROWS.format(
        codes=format_integer(len(file_codes)), rows=format_integer(len(file_rows))
    )
    db_text = messages.CARD_CODES_WITH_ROWS.format(
        codes=format_integer(len(db_codes)), rows=format_integer(len(db_rows))
    )
    return _codes_row(messages.CARD_CODES_CUSTOMER_CATALOG, file_text, db_text, file_codes == db_codes)


def _noted_row(label: str, description: str, count: int) -> CardRow:
    if count:
        return CardRow([label, description, count], messages.CARD_VERDICT_NOTED)
    return CardRow([label, '0', 0], messages.CARD_VERDICT_MATCH)


def _unlisted_customers_row(file_rows: dict) -> CardRow:
    catalog = _distinct(file_rows[CUSTOMERS_TABLE], CUSTOMER_CODE_COLUMN)
    unlisted: dict[str, _UnlistedCustomer] = {}
    for table_name in (RESULTS_TABLE, COSTS_TABLE):
        for row in file_rows.get(table_name, []):
            code = row.get(CUSTOMER_CODE_COLUMN)
            if code is None or code in catalog:
                continue
            customer = unlisted.setdefault(code, _UnlistedCustomer())
            if row.get(CUSTOMER_NAME_COLUMN) and not customer.name:
                customer.name = row[CUSTOMER_NAME_COLUMN]
            if row.get(MONTH_COLUMN) is not None:
                customer.months.add(row[MONTH_COLUMN])
    description = '; '.join(_unlisted_description(code, customer) for code, customer in sorted(unlisted.items()))
    return _noted_row(messages.CARD_CODES_UNLISTED_CUSTOMERS, description, len(unlisted))


def _unlisted_description(code: str, customer: _UnlistedCustomer) -> str:
    description = code
    if customer.name:
        description += messages.CARD_UNLISTED_CUSTOMER_NAME.format(name=customer.name)
    if customer.months:
        months = ', '.join(str(month) for month in sorted(customer.months))
        description += messages.CARD_UNLISTED_CUSTOMER_MONTHS.format(months=months)
    return description


def _customers_with_many_names_row(catalog_rows: list[dict]) -> CardRow:
    names_by_code: dict[str, list[str]] = {}
    for row in catalog_rows:
        if row.get(CUSTOMER_CODE_COLUMN) is None or row.get(CUSTOMER_NAME_COLUMN) is None:
            continue
        names = names_by_code.setdefault(row[CUSTOMER_CODE_COLUMN], [])
        if row[CUSTOMER_NAME_COLUMN] not in names:
            names.append(row[CUSTOMER_NAME_COLUMN])
    many = {code: names for code, names in names_by_code.items() if len(names) > 1}
    description = '; '.join(f'{code}: {" / ".join(names)}' for code, names in sorted(many.items()))
    return _noted_row(messages.CARD_CODES_CUSTOMERS_WITH_MANY_NAMES, description, len(many))


def _months_before_after_card(ctx: LoadContext, before: LoadSnapshot, file_rows: dict) -> Card:
    tables = [
        table
        for table in ctx.form.tables_by_display_order
        if not table.is_dim and table.year_column is not None and table.partition_by
    ]
    card = Card(
        BEFORE_AFTER_CARD,
        messages.CARD_TITLE_MONTHS_BEFORE_AFTER.format(year=ctx.year or ''),
        before_after_columns(messages.CARD_COLUMN_MONTH),
    )
    if not tables:
        return card
    sides = _MonthSides(
        tables,
        before.periods,
        {table.name: _gold_period_totals(ctx, table) for table in tables},
        {table.name: _file_period_counts(table, file_rows[table.name]) for table in tables},
    )
    card.rows = [_month_row(ctx, sides, month) for month in range(1, 13)]
    return card


def _file_period_counts(table: FormTable, file_rows: list[dict]) -> dict[str, int]:
    column = table.partition_column.name
    counts: dict[str, int] = defaultdict(int)
    for row in file_rows:
        if row[column] is not None:
            counts[str(row[column])] += 1
    return counts


def _period_row_count(periods: dict[str, PeriodTotals], period: str) -> int:
    totals = periods.get(period)
    return totals.row_count if totals else 0


def _period_totals(periods: dict[str, PeriodTotals], period: str) -> tuple[int, Decimal]:
    totals = periods.get(period)
    return (totals.row_count, totals.total) if totals else (0, Decimal('0'))


def _month_row(ctx: LoadContext, sides: _MonthSides, month: int) -> CardRow:
    period = str(month)
    names = [table.name for table in sides.tables]
    in_file = any(sides.in_file[name].get(period) for name in names)
    rows_before = [_period_row_count(sides.before.get(name, {}), period) for name in names]
    rows_after = [_period_row_count(sides.after[name], period) for name in names]
    if in_file:
        write_mode = messages.CARD_WRITE_OVERWRITE if any(rows_before) else messages.CARD_WRITE_APPEND
        written = all(
            _period_row_count(sides.after[name], period) == sides.in_file[name].get(period, 0) for name in names
        )
        row_verdict = verdict(written)
    else:
        write_mode = messages.CARD_WRITE_UNTOUCHED
        kept = all(
            _period_totals(sides.before.get(name, {}), period) == _period_totals(sides.after[name], period)
            for name in names
        )
        row_verdict = verdict(kept, messages.CARD_VERDICT_UNCHANGED)
    cells = [
        messages.CARD_MONTH_OF_YEAR.format(month=month, year=ctx.year),
        messages.CARD_YES if in_file else messages.CARD_NO,
        ' / '.join(format_integer(count) for count in rows_before),
        ' / '.join(format_integer(count) for count in rows_after),
        write_mode,
    ]
    link = table_link(ctx, sides.tables[0], 'gold', period=month) if any(rows_after) else None
    return CardRow(cells, row_verdict, link=link)


def _amounts_b4_result(cards: dict, mismatched: list[str]) -> str:
    if mismatched:
        titles = '; '.join(CARD_TITLES[key].format(year='') if key in CARD_TITLES else key for key in mismatched)
        return messages.CARD_B4_MISMATCH.format(cards=titles)
    totals = cards[TOTALS_CARD].rows if TOTALS_CARD in cards else []
    details = '; '.join(f'{row.cells[0]} {format_amount(Decimal(str(row.cells[1])))}' for row in totals)
    return messages.CARD_B4_AMOUNTS_MATCH.format(count=len(totals), details=details)
