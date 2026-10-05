"""Đường đọc Excel **độc lập** — chỉ dùng cho đối chiếu R1.

Vì sao phải có đường thứ hai: nếu đối chiếu Tệp ↔ Dữ liệu gốc dùng lại chính bộ
đọc đã ghi dữ liệu, phép đối chiếu chỉ chứng minh bộ đọc nhất quán với chính
nó, không chứng minh được dữ liệu ghi đúng tệp.

Nên mô-đun này **không import openpyxl**. Nó mở tệp .xlsx như một tệp zip và
đọc thẳng XML: hai đường đi khác nhau hoàn toàn, sai sót của đường này khó mà
trùng với sai sót của đường kia.
"""

from __future__ import annotations

import re
import unicodedata
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from ..errors import SourceFileError

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
O_CHI_SO = re.compile(r"^([A-Z]+)(\d+)$")


def _chuan(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", str(value or "")).split()).lower()


def _cot_thanh_so(chu: str) -> int:
    n = 0
    for ky_tu in chu:
        n = n * 26 + (ord(ky_tu) - 64)
    return n


class XlsxDocLai:
    """Đọc lại tệp bằng đường mã nguồn hoàn toàn khác đường đã ghi dữ liệu."""

    def __init__(self, path: Path) -> None:
        try:
            self._zip = zipfile.ZipFile(path)
        except Exception as exc:
            raise SourceFileError(f"Không mở lại được tệp để đối chiếu: {exc}") from None
        self._chuoi = self._doc_bang_chuoi()
        self._trang_thai: list[tuple[str, bool]] = []
        self._sheet = self._doc_danh_sach_sheet()

    def close(self) -> None:
        self._zip.close()

    def _doc_bang_chuoi(self) -> list[str]:
        if "xl/sharedStrings.xml" not in self._zip.namelist():
            return []
        goc = ElementTree.fromstring(self._zip.read("xl/sharedStrings.xml"))
        chuoi: list[str] = []
        for si in goc.findall(f"{NS}si"):
            chuoi.append("".join(t.text or "" for t in si.iter(f"{NS}t")))
        return chuoi

    def _doc_danh_sach_sheet(self) -> dict[str, str]:
        goc = ElementTree.fromstring(self._zip.read("xl/workbook.xml"))
        quan_he = ElementTree.fromstring(self._zip.read("xl/_rels/workbook.xml.rels"))
        dich = {r.get("Id"): r.get("Target") for r in quan_he}
        ra: dict[str, str] = {}
        for sheet in goc.iter(f"{NS}sheet"):
            duong = dich.get(sheet.get(f"{NS_REL}id"), "")
            if duong and not duong.startswith("/"):
                duong = "xl/" + duong.lstrip("./")
            ra[_chuan(sheet.get("name"))] = duong.lstrip("/")
            # `state` vắng mặt nghĩa là sheet đang hiện; "hidden", "veryHidden" là ẩn.
            self._trang_thai.append((sheet.get("name"), sheet.get("state") is None
                                     or sheet.get("state") == "visible"))
        return ra

    def cac_sheet_hien(self) -> list[str]:
        """Tên các sheet đang hiện, theo thứ tự trong tệp."""
        return [ten for ten, hien in self._trang_thai if hien]

    def _gia_tri_o(self, o) -> str | None:
        kieu = o.get("t")
        if kieu == "inlineStr":
            la = o.find(f"{NS}is")
            van_ban = "".join(t.text or "" for t in la.iter(f"{NS}t")) if la is not None else ""
            return van_ban or None
        node = o.find(f"{NS}v")
        if node is None or node.text is None:
            return None
        raw = node.text
        if kieu == "s":
            chi_so = int(raw)
            return self._chuoi[chi_so] if chi_so < len(self._chuoi) else None
        if kieu == "b":
            return "TRUE" if raw == "1" else "FALSE"
        return raw

    def luoi(self, ten_sheet: str) -> dict[int, dict[int, str]]:
        """Mọi ô có giá trị của một sheet: `{số dòng: {chỉ số cột: giá trị}}`.

        Ô công thức trả kết quả Excel đã lưu (`<v>`), không trả công thức.
        """
        duong = self._sheet.get(_chuan(ten_sheet))
        if duong is None:
            raise SourceFileError(f"Đọc lại: tệp không có sheet {ten_sheet!r}.")
        goc = ElementTree.fromstring(self._zip.read(duong))
        hang: dict[int, dict[int, str]] = {}
        for row in goc.iter(f"{NS}row"):
            gia_tri: dict[int, str] = {}
            for o in row.findall(f"{NS}c"):
                khop = O_CHI_SO.match(o.get("r") or "")
                if not khop:
                    continue
                value = self._gia_tri_o(o)
                if value is not None and str(value).strip():
                    gia_tri[_cot_thanh_so(khop.group(1))] = value
            if gia_tri:
                hang[int(row.get("r"))] = gia_tri
        return hang
