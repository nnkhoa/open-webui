"""Tệp chờ xác nhận — tệp đã qua bước Kiểm tra tệp, chưa ghi gì vào database.

Tệp chờ **không phải lần nạp** (mục 6.2): chưa có mã `#{id}`, không hiện ở Lịch
sử nạp, huỷ thì mất hẳn. Nên nó không nằm trong kho mà nằm trên đĩa, mỗi tệp một
thư mục dưới `{DATA_DIR}/data_portal/uploads/cho/{ma_tep_cho}/`:

    tep.xlsx          tệp người dùng tải lên, y nguyên
    thong_tin.json    nhóm, năm, loại tệp, người tải, kết quả bước Kiểm tra tệp

`ma_tep_cho` là 32 ký tự hex ngẫu nhiên — đoán không ra, và kiểm được bằng biểu
thức nên không bao giờ thoát ra ngoài thư mục chờ.

Xác nhận ghi thì thư mục được **đổi tên** sang `{ma}.dang_ghi` trước khi ghi:
đổi tên là thao tác nguyên tử, nên hai lần bấm xác nhận cùng lúc chỉ một lần
chạy được, lần kia thấy tệp chờ không còn.
"""

from __future__ import annotations

import json
import re
import secrets
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

MA_HOP_LE = re.compile(r"^[0-9a-f]{32}$")
TEN_TEP = "tep.xlsx"
TEN_THONG_TIN = "thong_tin.json"
DANG_GHI = ".dang_ghi"

# Tệp chờ bị bỏ ngang (đóng trình duyệt ở màn Xác nhận) được dọn sau chừng này giờ.
GIO_GIU = 24


@dataclass
class TepCho:
    ma: str
    thu_muc: Path
    thong_tin: dict

    @property
    def duong_dan(self) -> Path:
        return self.thu_muc / TEN_TEP


def thu_muc_cho(upload_dir: Path) -> Path:
    return upload_dir / "cho"


def luu(upload_dir: Path, nguon: BinaryIO, thong_tin: dict) -> TepCho:
    """Chép tệp vào một thư mục chờ mới. `thong_tin` ghi sau, khi đã kiểm tra xong."""
    ma = secrets.token_hex(16)
    thu_muc = thu_muc_cho(upload_dir) / ma
    thu_muc.mkdir(parents=True)
    with (thu_muc / TEN_TEP).open("wb") as ra:
        shutil.copyfileobj(nguon, ra, 1 << 20)
    tep = TepCho(ma, thu_muc, {**thong_tin, "ma_tep_cho": ma})
    ghi_thong_tin(tep)
    return tep


def ghi_thong_tin(tep: TepCho) -> None:
    (tep.thu_muc / TEN_THONG_TIN).write_text(
        json.dumps(tep.thong_tin, ensure_ascii=False, default=str), encoding="utf-8")


def doc(upload_dir: Path, ma: str) -> TepCho | None:
    """Tệp chờ theo mã, hoặc None nếu mã sai dạng, đã huỷ, đã ghi hay đang ghi."""
    if not MA_HOP_LE.match(ma or ""):
        return None
    thu_muc = thu_muc_cho(upload_dir) / ma
    tt = thu_muc / TEN_THONG_TIN
    if not (thu_muc / TEN_TEP).is_file() or not tt.is_file():
        return None
    return TepCho(ma, thu_muc, json.loads(tt.read_text(encoding="utf-8")))


def xoa(tep: TepCho) -> None:
    shutil.rmtree(tep.thu_muc, ignore_errors=True)


def giu_de_ghi(tep: TepCho) -> TepCho | None:
    """Đổi tên thư mục chờ để chỉ một lần xác nhận được ghi. None nếu đã có lần
    khác giữ trước."""
    dich = tep.thu_muc.with_name(tep.ma + DANG_GHI)
    try:
        tep.thu_muc.rename(dich)
    except OSError:
        return None
    return TepCho(tep.ma, dich, tep.thong_tin)


def tra_lai(tep: TepCho) -> None:
    """Ghi hỏng giữa chừng vì lỗi ngoài dự kiến: trả tệp về hàng chờ như cũ."""
    try:
        tep.thu_muc.rename(tep.thu_muc.with_name(tep.ma))
    except OSError:
        return


def don_tep_bo_do(upload_dir: Path) -> None:
    """Xoá tệp chờ quá hạn mà không ai xác nhận hay huỷ."""
    goc = thu_muc_cho(upload_dir)
    if not goc.is_dir():
        return
    han = datetime.now(UTC).timestamp() - GIO_GIU * 3600
    for p in goc.iterdir():
        if p.is_dir() and p.stat().st_mtime < han:
            shutil.rmtree(p, ignore_errors=True)
