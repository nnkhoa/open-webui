from __future__ import annotations

import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple, Protocol

from .. import messages
from ..errors import SourceFileError

if TYPE_CHECKING:
    from ..registry.schema import Form


@dataclass(frozen=True)
class SourceRow:
    number: int
    values: dict[str, str | None]


@dataclass(frozen=True)
class SourceIssue:
    sheet: str
    location: str
    code: str
    params: dict[str, str]


class ColumnLayout(NamedTuple):
    positions: dict[str, int]
    unnamed_columns: list[int]
    duplicate_names: list[str]


class SourceReader(Protocol):
    kind: ClassVar[str]

    def __init__(self, path: Path, form: Form) -> None: ...

    def sheets(self) -> list[str]: ...

    def header(self, sheet: str) -> list[str | None]: ...

    def column_layout(self, sheet: str) -> ColumnLayout: ...

    def cells_outside_columns(self, sheet: str, unnamed_columns: list[int]) -> list[tuple[int, str]]: ...

    def rows(self, sheet: str, header_map: dict[str, str]) -> Iterator[SourceRow]: ...

    def source_sheet(self, sheet: str) -> str: ...

    def source_issues(self) -> list[SourceIssue]: ...

    def close(self) -> None: ...


READERS: dict[str, type[SourceReader]] = {}


def register(cls: type[SourceReader]) -> type[SourceReader]:
    READERS[cls.kind] = cls
    return cls


def open_reader(kind: str, path: Path, form: Form) -> SourceReader:
    cls = READERS.get(kind)
    if cls is None:
        raise SourceFileError(messages.SOURCE_READER_NOT_FOUND.format(kind=kind, available=', '.join(sorted(READERS))))
    return cls(path, form)


def normalize_name(value: Any) -> str:
    return ' '.join(unicodedata.normalize('NFC', str(value or '')).split()).lower()


def column_index(letters: str) -> int:
    index = 0
    for letter in letters:
        index = index * 26 + (ord(letter) - 64)
    return index
