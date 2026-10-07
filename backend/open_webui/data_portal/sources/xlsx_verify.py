from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import NamedTuple
from xml.etree import ElementTree

from .. import messages
from ..errors import SourceFileError
from .base import column_index, normalize_name

SPREADSHEET_NAMESPACE = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
RELATIONSHIP_NAMESPACE = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
CELL_REFERENCE_PATTERN = re.compile(r'^([A-Z]+)(\d+)$')
SHARED_STRINGS_PATH = 'xl/sharedStrings.xml'
WORKBOOK_PATH = 'xl/workbook.xml'
WORKBOOK_RELATIONSHIPS_PATH = 'xl/_rels/workbook.xml.rels'

Grid = dict[int, dict[int, str]]


class VerifyTable(NamedTuple):
    headers: dict[int, str]
    rows: dict[int, dict[int, str | None]]


class XlsxXmlReader:
    def __init__(self, path: Path) -> None:
        try:
            self._zip = zipfile.ZipFile(path)
        except Exception as exc:
            raise SourceFileError(messages.SOURCE_REOPEN_FAILED.format(error=exc)) from None
        self._shared_strings = self._read_shared_strings()
        self._sheet_paths: dict[str, str] = {}
        self._sheet_visibility: list[tuple[str, bool]] = []
        self._read_sheet_index()

    def close(self) -> None:
        self._zip.close()

    def visible_sheets(self) -> list[str]:
        return [name for name, visible in self._sheet_visibility if visible]

    def grid(self, sheet_name: str) -> Grid:
        grid: Grid = {}
        for row in self._sheet_rows(sheet_name):
            values = self._row_values(row)
            if values:
                grid[int(row.get('r'))] = values
        return grid

    def hidden_rows(self, sheet_name: str) -> set[int]:
        return {int(row.get('r')) for row in self._sheet_rows(sheet_name) if row.get('hidden') in ('1', 'true')}

    def _sheet_rows(self, sheet_name: str) -> list[ElementTree.Element]:
        path = self._sheet_paths.get(normalize_name(sheet_name))
        if path is None:
            raise SourceFileError(messages.SOURCE_REREAD_MISSING_SHEET.format(sheet=sheet_name))
        return list(ElementTree.fromstring(self._zip.read(path)).iter(f'{SPREADSHEET_NAMESPACE}row'))

    def _read_shared_strings(self) -> list[str]:
        if SHARED_STRINGS_PATH not in self._zip.namelist():
            return []
        root = ElementTree.fromstring(self._zip.read(SHARED_STRINGS_PATH))
        return [
            ''.join(text.text or '' for text in item.iter(f'{SPREADSHEET_NAMESPACE}t'))
            for item in root.findall(f'{SPREADSHEET_NAMESPACE}si')
        ]

    def _read_sheet_index(self) -> None:
        workbook = ElementTree.fromstring(self._zip.read(WORKBOOK_PATH))
        relationships = ElementTree.fromstring(self._zip.read(WORKBOOK_RELATIONSHIPS_PATH))
        targets = {relationship.get('Id'): relationship.get('Target') for relationship in relationships}
        for sheet in workbook.iter(f'{SPREADSHEET_NAMESPACE}sheet'):
            path = targets.get(sheet.get(f'{RELATIONSHIP_NAMESPACE}id'), '')
            if path and not path.startswith('/'):
                path = 'xl/' + path.lstrip('./')
            self._sheet_paths[normalize_name(sheet.get('name'))] = path.lstrip('/')
            state = sheet.get('state')
            self._sheet_visibility.append((sheet.get('name'), state is None or state == 'visible'))

    def _row_values(self, row: ElementTree.Element) -> dict[int, str]:
        values: dict[int, str] = {}
        for cell in row.findall(f'{SPREADSHEET_NAMESPACE}c'):
            match = CELL_REFERENCE_PATTERN.match(cell.get('r') or '')
            if not match:
                continue
            value = self._cell_value(cell)
            if value is not None and str(value).strip():
                values[column_index(match.group(1))] = value
        return values

    def _cell_value(self, cell: ElementTree.Element) -> str | None:
        cell_type = cell.get('t')
        if cell_type == 'inlineStr':
            inline = cell.find(f'{SPREADSHEET_NAMESPACE}is')
            text = ''.join(t.text or '' for t in inline.iter(f'{SPREADSHEET_NAMESPACE}t')) if inline is not None else ''
            return text or None
        node = cell.find(f'{SPREADSHEET_NAMESPACE}v')
        if node is None or node.text is None:
            return None
        raw = node.text
        if cell_type == 's':
            index = int(raw)
            return self._shared_strings[index] if index < len(self._shared_strings) else None
        if cell_type == 'b':
            return 'TRUE' if raw == '1' else 'FALSE'
        return raw
