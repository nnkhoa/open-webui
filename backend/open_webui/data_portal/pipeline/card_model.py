from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .. import messages
from ..registry.schema import FormTable
from .context import LoadContext

ZERO = Decimal(0)

ROW_COUNT_CARD = 'so_dong'
TOTALS_CARD = 'tong'
AMOUNT_BY_GROUP_CARD = 'tien_theo_nhom'
EMPTY_CELLS_CARD = 'o_trong'
BY_DIMENSION_CARD = 'theo_chieu'
CODES_CARD = 'ma'
BEFORE_AFTER_CARD = 'truoc_sau'
REJECTED_CARD = 'tu_choi'
CARD_ORDER = (
    ROW_COUNT_CARD,
    TOTALS_CARD,
    AMOUNT_BY_GROUP_CARD,
    EMPTY_CELLS_CARD,
    BY_DIMENSION_CARD,
    CODES_CARD,
    BEFORE_AFTER_CARD,
)

TABLE_OPTION = 'bang'
COLUMN_OPTION = 'cot'
GROUP_BY_OPTION = 'chia_theo'
ALL_COLUMNS = 'tat_ca'

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
        link: dict = {'bang': self.table, 'lop': self.layer}
        if self.year is not None:
            link['nam'] = self.year
        if self.period is not None:
            link['ky'] = self.period
        if self.query is not None:
            link['tim'] = self.query
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
        cell: dict = {'v': self.value}
        if self.link is not None:
            cell['mo'] = self.link.to_json()
        return cell


@dataclass
class CardColumn:
    label: str
    align_right: bool = False

    def to_json(self) -> dict:
        return {'t': self.label, 'r': True} if self.align_right else {'t': self.label}


@dataclass
class CardRow:
    cells: list[CellValue | Cell]
    verdict: str
    note: str | None = None
    link: Link | None = None
    verdict_note: str | None = None

    def to_json(self) -> dict:
        row: dict = {
            'o': [cell.to_json() if isinstance(cell, Cell) else cell for cell in self.cells],
            'ket_luan': self.verdict,
        }
        if self.note is not None:
            row['phu'] = self.note
        if self.link is not None:
            row['mo'] = self.link.to_json()
        if self.verdict_note is not None:
            row['ket_luan_phu'] = self.verdict_note
        return row


@dataclass
class OptionChoice:
    value: str
    label: str

    def to_json(self) -> dict:
        return {'v': self.value, 't': self.label}


@dataclass
class CardOption:
    name: str
    label: str
    value: str
    default: str
    choices: list[OptionChoice]

    def to_json(self) -> dict:
        return {
            'ten': self.name,
            'nhan': self.label,
            'gia_tri': self.value,
            'mac': self.default,
            'lua_chon': [choice.to_json() for choice in self.choices],
        }


@dataclass
class Pagination:
    page: int
    page_size: int
    total: int

    def to_json(self) -> dict:
        return {'trang': self.page, 'moi': self.page_size, 'tong': self.total}


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
    table_labels: list[str] | None = None

    @property
    def has_mismatch(self) -> bool:
        return any(row.verdict in MISMATCH_VERDICTS for row in self.rows)

    def to_json(self) -> dict:
        card: dict = {'ma': self.key, 'tieu_de': self.title}
        if self.message is not None:
            card['thong_bao'] = self.message
        card['cot'] = [column.to_json() for column in self.columns]
        card['dong'] = [row.to_json() for row in self.rows]
        if self.count is not None:
            card['so'] = self.count
        if self.options is not None:
            card['tuy_chon'] = [option.to_json() for option in self.options]
        if self.totals is not None:
            card['tong'] = list(self.totals)
        if self.pagination is not None:
            card['trang'] = self.pagination.to_json()
        if self.table_labels is not None:
            card['cac_bang'] = list(self.table_labels)
        return card


def stored_card_view(card_json: dict, *, cancelled: bool) -> dict:
    view = {key: value for key, value in card_json.items() if key != 'cac_bang'}
    if cancelled:
        view = {**view, 'dong': [], 'thong_bao': messages.CARD_CANCELLED_NOTICE}
    return view


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
