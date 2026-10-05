"""`GET /domains` — ô chọn Nhóm thông tin và Loại tệp (CN-02, QT-01, QT-03)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import NguCanhApi, mo_ngu_canh

router = APIRouter()


def loai_tep_json(form) -> dict:
    return {"ma": form.code, "ten": form.label, "phu": form.subtitle}


@router.get("/domains")
def cac_nhom(ngu_canh: NguCanhApi = Depends(mo_ngu_canh)) -> list[dict]:
    """Mã, tên nhóm, chữ phụ ("HQKD · Báo cáo hiệu quả từng khách hàng"), các loại tệp."""
    ra = []
    for d in ngu_canh.cac_nhom():
        loai = [form for _, form in ngu_canh.cac_loai_tep(d)]
        phu = d.code + (" · " + ", ".join(f.label for f in loai) if loai else "")
        ra.append({"code": d.code, "name": d.name, "phu": phu,
                   "loai_tep": [loai_tep_json(f) for f in loai]})
    return ra
