from __future__ import annotations

import datetime as dt
import zipfile
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.workbook.workbook import Workbook

from .. import messages
from ..errors import SourceFileError


def is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def cell_text(value: Any) -> str | None:
    if is_blank(value):
        return None
    if isinstance(value, bool):
        return 'TRUE' if value else 'FALSE'
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    if isinstance(value, dt.datetime):
        return value.date().isoformat() if value.time() == dt.time() else value.isoformat(sep=' ')
    if isinstance(value, (dt.date, dt.time)):
        return value.isoformat()
    return str(value)


def sheet_names(path: Path) -> list[str]:
    workbook = open_workbook(path, read_only=True)
    try:
        return list(workbook.sheetnames)
    finally:
        workbook.close()


def open_workbook(path: Path, *, read_only: bool = False) -> Workbook:
    try:
        return load_workbook(path, data_only=True, read_only=read_only)
    except zipfile.BadZipFile:
        raise SourceFileError(messages.SOURCE_NOT_XLSX) from None
    except Exception as exc:
        raise SourceFileError(messages.SOURCE_OPEN_FAILED.format(error=exc)) from None
