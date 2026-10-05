from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NamedTuple

from ..registry.schema import Form, FormTable


class BronzeRow(NamedTuple):
    bronze_id: int
    source_row: int
    row_hash: str
    values: dict


@dataclass
class CleanRow:
    source_row: int
    bronze_id: int
    row_hash: str
    values: dict[str, Any]


@dataclass
class TableResult:
    table: str
    label: str
    rows_file: int = 0
    rows_bronze: int = 0
    rows_silver: int = 0
    rows_gold: int = 0
    rows_superseded: int = 0
    rows_unchanged: int = 0
    rows_duplicate: int = 0


@dataclass
class LoadContext:
    conn: Any
    form: Form
    domain_id: int
    domain_code: str
    form_id: int
    load_id: int
    batch_id: int
    upload_path: Path
    file_name: str
    actor_user_id: int | None
    actor_username: str
    request_id: str
    year: int | None = None
    reader: Any = None
    sheets_count: int = 0
    clean_rows: dict[str, list[CleanRow]] = field(default_factory=dict)
    table_results: dict[str, TableResult] = field(default_factory=dict)
    touched_periods: dict[str, set[str]] = field(default_factory=dict)

    def table_result(self, table: FormTable) -> TableResult:
        if table.name not in self.table_results:
            self.table_results[table.name] = TableResult(table.name, table.label)
        return self.table_results[table.name]

    @property
    def rows_read(self) -> int:
        return sum(result.rows_bronze for result in self.table_results.values())

    @property
    def rows_written(self) -> int:
        return sum(result.rows_silver for result in self.table_results.values())

    def report(self) -> dict:
        return {
            'tables': {
                result.table: {
                    'label': result.label,
                    'rows_file': result.rows_file,
                    'rows_bronze': result.rows_bronze,
                    'rows_silver': result.rows_silver,
                    'rows_gold': result.rows_gold,
                    'rows_superseded': result.rows_superseded,
                    'rows_unchanged': result.rows_unchanged,
                    'rows_duplicate': result.rows_duplicate,
                }
                for result in self.table_results.values()
            },
            'partitions': {table: sorted(periods) for table, periods in self.touched_periods.items()},
        }
