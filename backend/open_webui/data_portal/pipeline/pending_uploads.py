from __future__ import annotations

import dataclasses
import datetime as dt
import json
import re
import secrets
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

PENDING_ID_PATTERN = re.compile(r'^[0-9a-f]{32}$')
PENDING_DIR_NAME = 'pending'
UPLOAD_FILE_NAME = 'upload.xlsx'
METADATA_FILE_NAME = 'metadata.json'
CLAIMED_SUFFIX = '.writing'
RETENTION_HOURS = 24
COPY_BUFFER_SIZE = 1 << 20


@dataclass
class PendingMetadata:
    domain_id: int
    domain: str
    form_id: int
    file_type: str
    year: int
    file_name: str
    user_id: str
    user: str
    created_at: str
    sha256: str | None = None
    size_bytes: int | None = None
    file_check: dict | None = None


@dataclass
class PendingUpload:
    pending_id: str
    directory: Path
    metadata: PendingMetadata

    @property
    def file_path(self) -> Path:
        return self.directory / UPLOAD_FILE_NAME

    @property
    def is_claimed(self) -> bool:
        return self.directory.name.endswith(CLAIMED_SUFFIX)


def pending_dir(upload_dir: Path) -> Path:
    return upload_dir / PENDING_DIR_NAME


def save(upload_dir: Path, source: BinaryIO, metadata: PendingMetadata) -> PendingUpload:
    pending_id = secrets.token_hex(16)
    directory = pending_dir(upload_dir) / pending_id
    directory.mkdir(parents=True)
    with (directory / UPLOAD_FILE_NAME).open('wb') as target:
        shutil.copyfileobj(source, target, COPY_BUFFER_SIZE)
    pending = PendingUpload(pending_id, directory, metadata)
    write_metadata(pending)
    return pending


def write_metadata(pending: PendingUpload) -> None:
    (pending.directory / METADATA_FILE_NAME).write_text(
        json.dumps(dataclasses.asdict(pending.metadata), ensure_ascii=False, default=str), encoding='utf-8'
    )


def get_pending(upload_dir: Path, pending_id: str) -> PendingUpload | None:
    if not PENDING_ID_PATTERN.match(pending_id or ''):
        return None
    directory = pending_dir(upload_dir) / pending_id
    metadata_file = directory / METADATA_FILE_NAME
    if not (directory / UPLOAD_FILE_NAME).is_file() or not metadata_file.is_file():
        return None
    metadata = PendingMetadata(**json.loads(metadata_file.read_text(encoding='utf-8')))
    return PendingUpload(pending_id, directory, metadata)


def delete(pending: PendingUpload) -> None:
    shutil.rmtree(pending.directory, ignore_errors=True)


def claim(pending: PendingUpload) -> PendingUpload | None:
    claimed = pending.directory.with_name(pending.pending_id + CLAIMED_SUFFIX)
    try:
        pending.directory.rename(claimed)
    except OSError:
        return None
    return PendingUpload(pending.pending_id, claimed, pending.metadata)


def release(pending: PendingUpload) -> None:
    try:
        pending.directory.rename(pending.directory.with_name(pending.pending_id))
    except OSError:
        return


def delete_expired(upload_dir: Path) -> None:
    root = pending_dir(upload_dir)
    if not root.is_dir():
        return
    cutoff = dt.datetime.now(dt.UTC).timestamp() - RETENTION_HOURS * 3600
    for path in root.iterdir():
        if path.is_dir() and path.stat().st_mtime < cutoff:
            shutil.rmtree(path, ignore_errors=True)
