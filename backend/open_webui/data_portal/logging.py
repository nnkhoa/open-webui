"""Nhật ký JSON có mã định danh yêu cầu.

Ghi có cấu trúc ở ranh giới: yêu cầu vào, yêu cầu ra, gọi dịch vụ ngoài. Không
ghi dữ liệu nhạy cảm, không ghi mật khẩu, không ghi nội dung tệp.
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from contextvars import ContextVar

MA_YEU_CAU: ContextVar[str] = ContextVar("ma_yeu_cau", default="-")


def ma_yeu_cau_moi() -> str:
    ma = uuid.uuid4().hex[:16]
    MA_YEU_CAU.set(ma)
    return ma


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ban_ghi = {
            "luc": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "muc": record.levelname,
            "nguon": record.name,
            "thong_diep": record.getMessage(),
            "ma_yeu_cau": MA_YEU_CAU.get(),
        }
        for khoa, gia_tri in getattr(record, "them", {}).items():
            ban_ghi[khoa] = gia_tri
        if record.exc_info:
            ban_ghi["ngoai_le"] = self.formatException(record.exc_info)
        return json.dumps(ban_ghi, ensure_ascii=False, default=str)


def cai_dat(muc: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    goc = logging.getLogger()
    goc.handlers[:] = [handler]
    goc.setLevel(muc)


def log(ten: str = "data_portal") -> logging.Logger:
    return logging.getLogger(ten)


def ghi(logger: logging.Logger, muc: int, thong_diep: str, **them) -> None:
    logger.log(muc, thong_diep, extra={"them": them})
