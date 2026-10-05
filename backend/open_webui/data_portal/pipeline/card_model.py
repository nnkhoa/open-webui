from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .. import messages
from ..registry.schema import FormTable
from .context import LoadContext

ZERO = Decimal(0)

ROW_COUNT_CARD = 'row_count'
TOTALS_CARD = 'totals'
AMOUNT_BY_GROUP_CARD = 'amount_by_group'
EMPTY_CELLS_CARD = 'empty_cells'
BY_DIMENSION_CARD = 'by_dimension'
CODES_CARD = 'codes'
BEFORE_AFTER_CARD = 'before_after'
REJECTED_CARD = 'rejected'
CARD_ORDER = (
    ROW_COUNT_CARD,
    TOTALS_CARD,
    AMOUNT_BY_GROUP_CARD,
    EMPTY_CELLS_CARD,
    BY_DIMENSION_CARD,
    CODES_CARD,
    BEFORE_AFTER_CARD,
)

TABLE_OPTION = 'table'
COLUMN_OPTION = 'column'
GROUP_BY_OPTION = 'group_by'
ALL_COLUMNS = 'all'

MISMATCH_VERDICTS = (messages.CARD_VERDICT_MISSING, messages.CARD_VERDICT_EXTRA, messages.CARD_VERDICT_MISMATCH)

CellValue = int | float | str | None


@dataclass
class Link:
    table: str
    layer: str
    year: int | None = None
    period: int | None = None
    query: str | None = None

    def to_json(self) -> dict:
        link: dict = {'table': self.table, 'layer': self.layer}
        if self.year is not None:
            link['year'] = self.year
        if self.period is not None:
            link['period'] = self.period
        if self.query is not None:
            link['query'] = self.query
        return link


@dataclass
class SheetLink:
    sheet: int

    def to_json(self) -> dict:
        return {'sheet': self.sheet}


@dataclass
class Cell:
    value: CellValue
    link: Link | SheetLink | None = None

    def to_json(self) -> dict:
        cell: dict = {'value': self.value}
        if self.link is not None:
            cell['link'] = self.link.to_json()
        return cell


@dataclass
class CardColumn:
    label: str
    align_right: bool = False

    def to_json(self) -> dict:
        return {'label': self.label, 'align_right': True} if self.align_right else {'label': self.label}


@dataclass
class CardRow:
    cells: list[CellValue | Cell]
    verdict: str
    note: str | None = None
    link: Link | None = None
    verdict_note: str | None = None

    def to_json(self) -> dict:
        row: dict = {
            'cells': [cell.to_json() if isinstance(cell, Cell) else cell for cell in self.cells],
            'verdict': self.verdict,
        }
        if self.note is not None:
            row['note'] = self.note
        if self.link is not None:
            row['link'] = self.link.to_json()
        if self.verdict_note is not None:
            row['verdict_note'] = self.verdict_note
        return row


@dataclass
class OptionChoice:
    value: str
    label: str

    def to_json(self) -> dict:
        return {'value': self.value, 'label': self.label}


@dataclass
class CardOption:
    name: str
    label: str
    value: str
    default: str
    choices: list[OptionChoice]

    def to_json(self) -> dict:
        return {
            'name': self.name,
            'label': self.label,
            'value': self.value,
            'default': self.default,
            'choices': [choice.to_json() for choice in self.choices],
        }


@dataclass
class Pagination:
    page: int
    page_size: int
    total: int

    def to_json(self) -> dict:
        return {'page': self.page, 'page_size': self.page_size, 'total': self.total}


@dataclass
class Card:
    key: str
    title: str
    columns: list[CardColumn] = field(default_factory=list)
    rows: list[CardRow] = field(default_factory=list)
    message: str | None = None
    count: int | None = None
    options: list[CardOption] | None = None
    totals: list[CellValue] | None = None
    pagination: Pagination | None = None

    @property
    def has_mismatch(self) -> bool:
        return any(row.verdict in MISMATCH_VERDICTS for row in self.rows)

    def to_json(self) -> dict:
        card: dict = {'key': self.key, 'title': self.title}
        if self.message is not None:
            card['message'] = self.message
        card['columns'] = [column.to_json() for column in self.columns]
        card['rows'] = [row.to_json() for row in self.rows]
        if self.count is not None:
            card['count'] = self.count
        if self.options is not None:
            card['options'] = [option.to_json() for option in self.options]
        if self.totals is not None:
            card['totals'] = list(self.totals)
        if self.pagination is not None:
            card['pagination'] = self.pagination.to_json()
        return card


def stored_card_view(card_json: dict, *, cancelled: bool) -> dict:
    if cancelled:
        return {**card_json, 'rows': [], 'message': messages.CARD_CANCELLED_NOTICE}
    return card_json


def rejected_card() -> dict:
    return Card(REJECTED_CARD, messages.CARD_TITLE_REJECTED, message=messages.CARD_REJECTED_NOTICE).to_json()


def as_number(value) -> int | float:
    number = Decimal(value)
    return int(number) if number == number.to_integral_value() else float(number)


def table_link(ctx: LoadContext, table: FormTable, layer: str, period: int | None = None) -> Link:
    year = ctx.year if table.year_column is not None else None
    return Link(table.name, layer, year=year, period=period)


def column_total(rows: list[dict], columns: list[str]) -> Decimal:
    return sum((Decimal(row[column]) for row in rows for column in columns if row.get(column) is not None), ZERO)


def gold_link(table_name: str, year: int | None, query: str | None = None, period: int | None = None) -> Link:
    return Link(table_name, 'gold', year=year or None, period=period, query=query)


def verdict(matches: bool, match_word: str = messages.CARD_VERDICT_CORRECT) -> str:
    return match_word if matches else messages.CARD_VERDICT_MISMATCH


def comparison_columns(first: str, file_label: str, db_label: str) -> list[CardColumn]:
    return [CardColumn(first), *_difference_columns(file_label, db_label)]


def group_count_columns(first: str, file_label: str, db_label: str) -> list[CardColumn]:
    return [
        CardColumn(first),
        CardColumn(messages.CARD_COLUMN_FILE_ROW_COUNT, align_right=True),
        CardColumn(messages.CARD_COLUMN_DB_ROW_COUNT, align_right=True),
        *_difference_columns(file_label, db_label),
    ]


def before_after_columns(first: str) -> list[CardColumn]:
    return [
        CardColumn(first),
        CardColumn(messages.CARD_COLUMN_IN_FILE),
        CardColumn(messages.CARD_COLUMN_ROWS_BEFORE, align_right=True),
        CardColumn(messages.CARD_COLUMN_ROWS_AFTER, align_right=True),
        CardColumn(messages.CARD_COLUMN_WRITE_MODE),
        CardColumn(messages.CARD_COLUMN_VERDICT),
    ]


def codes_columns() -> list[CardColumn]:
    return [
        CardColumn(messages.CARD_COLUMN_CONTENT),
        CardColumn(messages.CARD_COLUMN_FILE, align_right=True),
        CardColumn(messages.CARD_COLUMN_DB, align_right=True),
        CardColumn(messages.CARD_COLUMN_VERDICT),
    ]


def totals_row(file_rows: int, db_rows: int, file_total: Decimal, db_total: Decimal) -> list[CellValue]:
    return [
        messages.CARD_TOTAL,
        file_rows,
        db_rows,
        as_number(file_total),
        as_number(db_total),
        as_number(db_total - file_total),
        None,
    ]


def _difference_columns(file_label: str, db_label: str) -> list[CardColumn]:
    return [
        CardColumn(file_label, align_right=True),
        CardColumn(db_label, align_right=True),
        CardColumn(messages.CARD_COLUMN_DIFFERENCE, align_right=True),
        CardColumn(messages.CARD_COLUMN_VERDICT),
    ]
