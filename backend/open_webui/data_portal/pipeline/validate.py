from __future__ import annotations

from typing import Any

from .. import messages
from ..errors import StructureError
from ..registry.schema import FormTable
from ..registry.types import CODE_ENUM_UNKNOWN
from .context import BronzeRow, CleanRow
from .structure import error_row

UnparsedCells = dict[str, dict[str, int]]


def validate_rows(
    table: FormTable, bronze_rows: list[BronzeRow], unparsed_cells: UnparsedCells | None = None
) -> tuple[list[CleanRow], list[CleanRow]]:
    rows: list[CleanRow] = []
    errors: list[dict] = []
    for bronze_id, source_row, row_hash, raw in bronze_rows:
        values: dict[str, Any] = {}
        for column in table.columns:
            values[column.name] = _parse_cell(column, raw.get(column.name), unparsed_cells)
            if column.required and values[column.name] is None:
                location = messages.SOURCE_LOCATION_ROW.format(row=source_row)
                errors.append(error_row(table.label, location, 'MISSING_REQUIRED', name=column.label))
        rows.append(CleanRow(source_row=source_row, bronze_id=bronze_id, row_hash=row_hash, values=values))
    if errors:
        raise StructureError(errors)
    return _drop_duplicate_rows(rows) if table.is_dim else (rows, [])


def _parse_cell(column, raw: str | None, unparsed_cells: UnparsedCells | None) -> Any:
    parsed = column.handler.parse(raw)
    if parsed.ok:
        return parsed.value
    if parsed.code == CODE_ENUM_UNKNOWN:
        return raw
    if unparsed_cells is not None and raw is not None:
        by_value = unparsed_cells.setdefault(column.name, {})
        by_value[raw] = by_value.get(raw, 0) + 1
    return None


def _drop_duplicate_rows(rows: list[CleanRow]) -> tuple[list[CleanRow], list[CleanRow]]:
    seen: set[str] = set()
    kept: list[CleanRow] = []
    duplicates: list[CleanRow] = []
    for row in rows:
        (duplicates if row.row_hash in seen else kept).append(row)
        seen.add(row.row_hash)
    return kept, duplicates
