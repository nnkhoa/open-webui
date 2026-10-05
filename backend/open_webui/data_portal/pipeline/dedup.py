from __future__ import annotations

import hashlib
from pathlib import Path

CHUNK_SIZE = 1 << 20
NULL_MARKER = b'\x1e'
VALUE_MARKER = b'\x1f'


def hash_file(path: Path, chunk_size: int = CHUNK_SIZE) -> tuple[str, int]:
    digest = hashlib.sha256()
    size_bytes = 0
    with path.open('rb') as file:
        while chunk := file.read(chunk_size):
            digest.update(chunk)
            size_bytes += len(chunk)
    return digest.hexdigest(), size_bytes


def hash_row(sheet: str, values: dict[str, str | None], columns: list[str]) -> str:
    digest = hashlib.sha256()
    digest.update(sheet.encode('utf-8'))
    for column in columns:
        value = values.get(column)
        if value is None:
            digest.update(NULL_MARKER)
        else:
            digest.update(VALUE_MARKER)
            digest.update(str(value).encode('utf-8'))
    return digest.hexdigest()
