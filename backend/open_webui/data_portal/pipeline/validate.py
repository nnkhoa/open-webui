"""Ép kiểu từng ô của các dòng đã ghi ở lớp gốc, trước khi vào lớp chuẩn hoá.

Portal nạp hết hoặc không nạp gì, nên không có dòng nào bị loại riêng:

· Ô không ép được kiểu thì để trống ở lớp chuẩn hoá (lớp gốc vẫn giữ văn bản
  y như tệp). Cột `enum` giữ nguyên văn bản gốc.
· Chỉ cột khai `required: true` mới được kiểm tra có giá trị; thiếu ở dòng nào
  thì **từ chối cả tệp**, nêu đúng dòng.
· Bảng danh mục: dòng giống hệt một dòng trước nó trong cùng tệp (mọi cột bằng
  nhau) chỉ giữ một. Bảng số liệu giữ đủ mọi dòng — mỗi dòng là một ô tiền
  riêng trong tệp, dù hai ô có thể cùng giá trị.
"""

from __future__ import annotations

from typing import Any

from ..errors import StructureError
from ..registry.schema import FormTable
from ..registry.types import CODE_ENUM_UNKNOWN
from .context import DongSach
from .structure import dong_loi


def kiem_tra(table: FormTable, hang_goc: list[tuple[int, int, str, dict]],
             o_hong: dict[str, dict[str, int]] | None = None
             ) -> tuple[list[DongSach], list[DongSach]]:
    """Trả `(dòng vào lớp chuẩn hoá, dòng trùng y hệt đã bỏ)`. Có lỗi thì ném
    `StructureError`.

    `o_hong` (nếu truyền) nhận số ô không đổi được kiểu, theo cột rồi theo giá
    trị trong tệp — ô đó để trống ở lớp chuẩn hoá và chỉ được đếm (QT-11)."""
    dat: list[DongSach] = []
    loi: list[dict] = []

    for bronze_id, source_row, row_hash, raw in hang_goc:
        gia_tri: dict[str, Any] = {}
        for col in table.columns:
            tho = raw.get(col.name)
            phan = col.handler.parse(tho)
            if phan.ok:
                gia_tri[col.name] = phan.value
            elif phan.code == CODE_ENUM_UNKNOWN:
                gia_tri[col.name] = tho
            else:
                gia_tri[col.name] = None
                if o_hong is not None and tho is not None:
                    theo_gia_tri = o_hong.setdefault(col.name, {})
                    theo_gia_tri[tho] = theo_gia_tri.get(tho, 0) + 1
            if col.required and gia_tri[col.name] is None:
                loi.append(dong_loi(table.label, f"Dòng {source_row}", "MISSING_REQUIRED",
                                    ten=col.label))
        dat.append(DongSach(source_row=source_row, bronze_id=bronze_id,
                            row_hash=row_hash, values=gia_tri))
    if loi:
        raise StructureError(loi)
    return _bo_dong_trung(dat) if table.is_dim else (dat, [])


def _bo_dong_trung(dong: list[DongSach]) -> tuple[list[DongSach], list[DongSach]]:
    """Giữ dòng đầu của mỗi nhóm dòng y hệt nhau (cùng mã băm nội dung)."""
    da_co: set[str] = set()
    giu: list[DongSach] = []
    bo: list[DongSach] = []
    for d in dong:
        (bo if d.row_hash in da_co else giu).append(d)
        da_co.add(d.row_hash)
    return giu, bo
