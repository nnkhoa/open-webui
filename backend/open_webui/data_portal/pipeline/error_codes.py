from __future__ import annotations

from dataclasses import dataclass

from .. import messages


@dataclass(frozen=True)
class ErrorCode:
    code: str
    template: str
    resolution: str
    kind: str = ''

    def message(self, **params) -> str:
        try:
            return self.template.format(**params)
        except KeyError:
            return self.template


ERROR_CODES: dict[str, ErrorCode] = {
    error.code: error
    for error in [
        ErrorCode(
            'MISSING_SHEET',
            messages.ERROR_CODE_MISSING_SHEET,
            messages.ERROR_CODE_MISSING_SHEET_RESOLUTION,
            messages.ERROR_CODE_MISSING_SHEET_KIND,
        ),
        ErrorCode(
            'UNKNOWN_SHEET',
            messages.ERROR_CODE_UNKNOWN_SHEET,
            messages.ERROR_CODE_UNKNOWN_SHEET_RESOLUTION,
            messages.ERROR_CODE_UNKNOWN_SHEET_KIND,
        ),
        ErrorCode(
            'MISSING_COLUMN',
            messages.ERROR_CODE_MISSING_COLUMN,
            messages.ERROR_CODE_MISSING_COLUMN_RESOLUTION,
            messages.ERROR_CODE_MISSING_COLUMN_KIND,
        ),
        ErrorCode(
            'UNKNOWN_COLUMN',
            messages.ERROR_CODE_UNKNOWN_COLUMN,
            messages.ERROR_CODE_UNKNOWN_COLUMN_RESOLUTION,
            messages.ERROR_CODE_UNKNOWN_COLUMN_KIND,
        ),
        ErrorCode(
            'DUPLICATE_COLUMN',
            messages.ERROR_CODE_DUPLICATE_COLUMN,
            messages.ERROR_CODE_DUPLICATE_COLUMN_RESOLUTION,
            messages.ERROR_CODE_DUPLICATE_COLUMN_KIND,
        ),
        ErrorCode(
            'DATA_IN_UNNAMED_COLUMN',
            messages.ERROR_CODE_DATA_IN_UNNAMED_COLUMN,
            messages.ERROR_CODE_DATA_IN_UNNAMED_COLUMN_RESOLUTION,
            messages.ERROR_CODE_DATA_IN_UNNAMED_COLUMN_KIND,
        ),
        ErrorCode(
            'NO_DATA_SHEET',
            messages.ERROR_CODE_NO_DATA_SHEET,
            messages.ERROR_CODE_NO_DATA_SHEET_RESOLUTION,
            messages.ERROR_CODE_NO_DATA_SHEET_KIND,
        ),
        ErrorCode(
            'MANY_DATA_SHEETS',
            messages.ERROR_CODE_MANY_DATA_SHEETS,
            messages.ERROR_CODE_MANY_DATA_SHEETS_RESOLUTION,
            messages.ERROR_CODE_MANY_DATA_SHEETS_KIND,
        ),
        ErrorCode(
            'MISSING_REQUIRED',
            messages.ERROR_CODE_MISSING_REQUIRED,
            messages.ERROR_CODE_MISSING_REQUIRED_RESOLUTION,
            messages.ERROR_CODE_MISSING_REQUIRED_KIND,
        ),
        ErrorCode(
            'BK_DUPLICATE_IN_BATCH',
            messages.ERROR_CODE_BK_DUPLICATE_IN_BATCH,
            messages.ERROR_CODE_BK_DUPLICATE_IN_BATCH_RESOLUTION,
            messages.ERROR_CODE_BK_DUPLICATE_IN_BATCH_KIND,
        ),
    ]
}


def error_code(code: str) -> ErrorCode:
    return ERROR_CODES.get(code) or ErrorCode(code, code, '')
