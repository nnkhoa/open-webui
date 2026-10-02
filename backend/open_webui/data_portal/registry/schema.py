"""Mô hình khai báo bộ bảng và nhóm thông tin, kèm kiểm tra hợp lệ.

`Form` là dạng đối tượng của một tệp `khai_bao/forms/*.yaml`; `KhaiBaoDomain`
là một mục của `khai_bao/domains.yaml`. Không chạm cơ sở dữ liệu, không chạm
tệp: nhận `dict` đã đọc từ YAML, trả đối tượng đã kiểm tra, hoặc ném
`RegistryError` kèm câu chỉ rõ chỗ sai.

Không cột nào bắt buộc trừ khi khai `required: true` — kể cả cột khoá nghiệp
vụ: ô trống mã là dữ liệu thật của tệp, không phải lỗi.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..errors import RegistryError
from . import types as coltypes

MA_DOMAIN = re.compile(r"^[A-Z0-9-]{2,20}$")
MA_FORM = re.compile(r"^[A-Z0-9_]{2,40}$")
MA_BANG = re.compile(r"^[a-z][a-z0-9_]{2,50}$")
MA_COT = re.compile(r"^[a-z][a-z0-9_]{1,50}$")

# `replace_all`: nạp lại thay **toàn bộ** dữ liệu của cùng (loại tệp, năm) — tệp là
# bản theo dõi luỹ kế, mỗi bản liệt kê lại mọi dòng (QT-10, HQ-MAU-GC).
MERGE_HOP_LE = {"upsert", "replace_partition", "append", "replace_all"}
POLICY_HOP_LE = {"reject", "ignore"}
ROLE_HOP_LE = {"partition", "measure", "attribute", "degenerate"}
KIND_HOP_LE = {"dim", "fact"}
# Cột không lấy từ ô dữ liệu của tệp: `nam_du_lieu` lấy từ ô Năm dữ liệu chọn lúc
# nạp (QT-02); `trong` là cột có trong phiếu khảo sát mà tệp không có — giữ cột, để
# trống (QT-21); `tieu_de` lấy phần trong ngoặc của tiêu đề cột `header` (ví dụ
# "GIÁ TIỀN (USD)" → "USD").
LAY_TU_HOP_LE = {"nam_du_lieu", "trong", "tieu_de"}
LAY_TU_NAM = "nam_du_lieu"

@dataclass
class FormColumn:
    name: str
    type: str
    label: str
    meaning: str
    ordinal: int
    required: bool = False
    is_business_key: bool = False
    # Tên cột mà bộ đọc trả về, khi khác tên kỹ thuật. Mặc định trùng `name`.
    header: str | None = None
    how: str | None = None
    example: str | None = None
    values: list[str] = field(default_factory=list)
    role: str | None = None
    display_width: int | None = None
    show_in_table: bool = True
    total_label: str | None = None
    # None = lấy từ tệp; xem `LAY_TU_HOP_LE`.
    lay_tu: str | None = None

    def __post_init__(self) -> None:
        self._type = coltypes.build(self.type, self)

    @property
    def tieu_de(self) -> str:
        """Tên cột mà bộ đọc tìm ở dòng tiêu đề của tệp."""
        return self.header or self.name

    @property
    def tu_tep(self) -> bool:
        """Cột có trong tệp — bộ đọc tìm nó ở dòng tiêu đề."""
        return self.lay_tu is None

    @property
    def tu_tieu_de(self) -> bool:
        """Cột lấy giá trị từ tiêu đề cột `header` (đơn vị trong ngoặc)."""
        return self.lay_tu == "tieu_de"

    @property
    def la_nam(self) -> bool:
        """Cột `nam` của bảng số liệu — lấy từ ô Năm dữ liệu, không từ tệp."""
        return self.lay_tu == LAY_TU_NAM

    @property
    def handler(self) -> coltypes.ColumnType:
        return self._type

    @property
    def silver_sql_type(self) -> str:
        return self._type.silver_sql_type

    @property
    def align(self) -> str:
        return self._type.align

    @property
    def type_label_vi(self) -> str:
        return self._type.label_vi

    @property
    def is_measure(self) -> bool:
        """Cột nào được cộng ở hàng "Tổng dữ liệu đang lọc" — P08, do khai báo
        quyết định chứ không viết cứng."""
        return self.role == "measure" and self._type.summable

    def display(self, value: Any) -> str:
        return self._type.display(value)


@dataclass
class FormTable:
    name: str
    kind: str
    sheet: str
    label: str
    description: str
    grain: str
    columns: list[FormColumn]
    business_key: list[str] = field(default_factory=list)
    merge: str = "upsert"
    partition_by: list[str] = field(default_factory=list)
    order: list[str] = field(default_factory=list)
    display_order: int = 0
    card_label: str | None = None
    card_description: str | None = None
    # Bảng dùng để làm gì — trích phiếu khảo sát, in ở sheet THONG_TIN khi tải về.
    purpose: str = ""

    @property
    def nhan_the(self) -> str:
        """Tiêu đề trên thẻ ở P07 — ngắn hơn `label` khi cần."""
        return self.card_label or self.label

    @property
    def is_dim(self) -> bool:
        return self.kind == "dim"

    @property
    def sk_column(self) -> str:
        return f"{self.name}_sk"

    def column(self, name: str) -> FormColumn:
        for col in self.columns:
            if col.name == name:
                return col
        raise RegistryError(f"Bảng {self.name!r} không có cột {name!r}.")

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    @property
    def anh_xa_tieu_de(self) -> dict[str, str]:
        """`{tên kỹ thuật: tên cột trong tệp}` — bộ đọc dùng để tìm cột. Chỉ cột
        lấy từ tệp: cột `nam` và cột để trống không có ở dòng tiêu đề."""
        return {c.name: c.tieu_de for c in self.columns if c.tu_tep}

    @property
    def cot_tu_tep(self) -> list[FormColumn]:
        return [c for c in self.columns if c.tu_tep]

    @property
    def cot_nam(self) -> FormColumn | None:
        """Cột năm dữ liệu (QT-02), hoặc None với bảng danh mục."""
        return next((c for c in self.columns if c.la_nam), None)

    @property
    def cot_tien(self) -> list[FormColumn]:
        """Cột tiền — cộng vào "Tổng tiền trong tệp" và các thẻ đối chiếu tổng."""
        return [c for c in self.columns if c.type in ("money", "currency")]

    @property
    def measures(self) -> list[FormColumn]:
        return [c for c in self.columns if c.is_measure]

    @property
    def partition_column(self) -> FormColumn | None:
        return self.column(self.partition_by[0]) if self.partition_by else None


@dataclass
class FormPolicy:
    unknown_sheet: str = "reject"
    unknown_column: str = "reject"
    missing_column: str = "reject"


@dataclass
class Form:
    code: str
    version: int
    label: str
    description: str
    tables: list[FormTable]
    policy: FormPolicy
    source_kind: str
    header_row: int = 1
    yaml_sha256: str = ""
    # Tuỳ chọn riêng của bộ đọc (khối `source` trong YAML, trừ `kind`, `header_row`).
    source_opts: dict = field(default_factory=dict)
    # Chữ phụ của loại tệp ở ô chọn (ví dụ "SAMPLE MAKING SCHEDULE"); None nếu không có.
    chu_phu: str | None = None

    def table(self, name: str) -> FormTable:
        for table in self.tables:
            if table.name == name:
                return table
        raise RegistryError(f"Bộ bảng {self.code!r} không có bảng {name!r}.")

    @property
    def tables_theo_thu_tu(self) -> list[FormTable]:
        """Danh mục trước, số liệu sau."""
        return sorted(self.tables, key=lambda t: (t.kind != "dim", t.display_order, t.name))

    @property
    def tables_hien_thi(self) -> list[FormTable]:
        """Thứ tự hiển thị trên giao diện, theo `display_order`."""
        return sorted(self.tables, key=lambda t: (t.display_order, t.name))


# --------------------------------------------------------------------------- #
#  Dựng từ dict và kiểm tra hợp lệ
# --------------------------------------------------------------------------- #


def _doi(gia_tri: Any, ten: str, kieu: type, bat_buoc: bool = True,
         mac_dinh: Any = None) -> Any:
    if gia_tri is None:
        if bat_buoc:
            raise RegistryError(f"Thiếu {ten}.")
        return mac_dinh
    if not isinstance(gia_tri, kieu):
        raise RegistryError(f"{ten} phải là {kieu.__name__}, đang là {type(gia_tri).__name__}.")
    return gia_tri


def _khop(mau: re.Pattern, gia_tri: str, ten: str) -> str:
    if not mau.match(gia_tri):
        raise RegistryError(f"{ten} {gia_tri!r} không khớp {mau.pattern}.")
    return gia_tri


def dung_column(raw: dict, ordinal: int, business_key: list[str], ten_bang: str) -> FormColumn:
    name = _khop(MA_COT, _doi(raw.get("name"), f"{ten_bang}: columns[].name", str), "Tên cột")
    type_name = _doi(raw.get("type"), f"{ten_bang}.{name}: type", str)
    if type_name not in coltypes.TYPES:
        raise RegistryError(
            f"{ten_bang}.{name}: kiểu {type_name!r} chưa đăng ký. "
            f"Các kiểu có sẵn: {', '.join(sorted(coltypes.TYPES))}."
        )
    role = raw.get("role")
    if role is not None and role not in ROLE_HOP_LE:
        raise RegistryError(f"{ten_bang}.{name}: role phải thuộc {sorted(ROLE_HOP_LE)}.")
    values = [str(v) for v in (raw.get("values") or [])]
    if type_name == "enum" and not values:
        raise RegistryError(f"{ten_bang}.{name}: kiểu enum bắt buộc khai `values`.")

    lay_tu = raw.get("lay_tu")
    if lay_tu is not None and lay_tu not in LAY_TU_HOP_LE:
        raise RegistryError(f"{ten_bang}.{name}: lay_tu phải thuộc {sorted(LAY_TU_HOP_LE)}.")

    la_khoa = name in business_key
    # Không cột nào bắt buộc trừ khi khai báo nói rõ `required: true`, kể cả cột
    # khoá: ô trống mã là dữ liệu thật của tệp, không phải lỗi.
    bat_buoc = bool(raw.get("required"))

    return FormColumn(
        name=name,
        type=type_name,
        label=_doi(raw.get("label"), f"{ten_bang}.{name}: label", str),
        meaning=_doi(raw.get("meaning"), f"{ten_bang}.{name}: meaning", str).strip(),
        ordinal=ordinal,
        required=bat_buoc,
        is_business_key=la_khoa,
        header=raw.get("header"),
        how=raw.get("how"),
        example=None if raw.get("example") is None else str(raw["example"]),
        values=values,
        role=role,
        display_width=raw.get("display_width"),
        show_in_table=bool(raw.get("show_in_table", True)),
        total_label=raw.get("total_label"),
        lay_tu=lay_tu,
    )


def dung_table(raw: dict) -> FormTable:
    name = _khop(MA_BANG, _doi(raw.get("name"), "tables[].name", str), "Tên bảng")
    kind = _doi(raw.get("kind"), f"{name}: kind", str)
    if kind not in KIND_HOP_LE:
        raise RegistryError(f"{name}: kind phải là 'dim' hoặc 'fact'.")
    merge = raw.get("merge", "upsert")
    if merge not in MERGE_HOP_LE:
        raise RegistryError(f"{name}: merge phải thuộc {sorted(MERGE_HOP_LE)}.")

    business_key = [str(c) for c in (raw.get("business_key") or [])]
    if merge != "append" and not business_key:
        raise RegistryError(
            f"{name}: thiếu business_key (chỉ merge 'append' mới được bỏ trống).")
    partition_by = [str(c) for c in (raw.get("partition_by") or [])]
    if merge == "replace_partition" and not partition_by:
        raise RegistryError(f"{name}: merge 'replace_partition' bắt buộc khai partition_by.")

    cot_raw = raw.get("columns") or []
    if not cot_raw:
        raise RegistryError(f"{name}: bảng không có cột nào.")
    columns = [dung_column(c, i, business_key, name) for i, c in enumerate(cot_raw, start=1)]

    ten_cot = [c.name for c in columns]
    trung = {c for c in ten_cot if ten_cot.count(c) > 1}
    if trung:
        raise RegistryError(f"{name}: tên cột bị lặp: {', '.join(sorted(trung))}.")
    for khoa in business_key:
        if khoa not in ten_cot:
            raise RegistryError(
                f"{name}: business_key nhắc tới cột {khoa!r} không có trong bảng.")
    for cot in partition_by:
        if cot not in ten_cot:
            raise RegistryError(
                f"{name}: partition_by nhắc tới cột {cot!r} không có trong bảng.")
    if sum(1 for c in columns if c.la_nam) > 1:
        raise RegistryError(f"{name}: chỉ được một cột lay_tu: {LAY_TU_NAM}.")
    if kind == "fact" and not raw.get("grain"):
        raise RegistryError(f"{name}: bảng số liệu bắt buộc khai `grain`.")

    return FormTable(
        name=name,
        kind=kind,
        sheet=_doi(raw.get("sheet"), f"{name}: sheet", str),
        label=_doi(raw.get("label"), f"{name}: label", str),
        description=_doi(raw.get("description"), f"{name}: description", str, bat_buoc=False,
                         mac_dinh=""),
        grain=str(raw.get("grain") or ""),
        columns=columns,
        business_key=business_key,
        merge=merge,
        partition_by=partition_by,
        order=[str(c) for c in (raw.get("order") or business_key)],
        display_order=int(raw.get("display_order", 0)),
        card_label=raw.get("card_label"),
        card_description=raw.get("card_description"),
        purpose=str(raw.get("purpose") or ""),
    )


def dung_form(raw: dict, yaml_sha256: str = "") -> Form:
    """Dựng `Form` từ nội dung một tệp YAML, kiểm tra hợp lệ toàn bộ."""
    if not isinstance(raw, dict) or "form" not in raw:
        raise RegistryError("Tệp khai báo phải có khối `form` ở mức cao nhất.")
    head = raw["form"]
    code = _khop(MA_FORM, _doi(head.get("code"), "form.code", str), "form.code")

    policy_raw = head.get("policy") or {}
    for khoa in ("unknown_sheet", "unknown_column", "missing_column"):
        gia_tri = policy_raw.get(khoa, "reject")
        if gia_tri not in POLICY_HOP_LE:
            raise RegistryError(f"{code}: policy.{khoa} phải thuộc {sorted(POLICY_HOP_LE)}.")
    policy = FormPolicy(
        unknown_sheet=policy_raw.get("unknown_sheet", "reject"),
        unknown_column=policy_raw.get("unknown_column", "reject"),
        missing_column=policy_raw.get("missing_column", "reject"),
    )

    bang_raw = raw.get("tables") or []
    if not bang_raw:
        raise RegistryError(f"{code}: bộ bảng không có bảng nào.")
    tables = [dung_table(t) for t in bang_raw]

    ten_bang = [t.name for t in tables]
    trung = {t for t in ten_bang if ten_bang.count(t) > 1}
    if trung:
        raise RegistryError(f"{code}: tên bảng bị lặp: {', '.join(sorted(trung))}.")
    sheet = [t.sheet.lower() for t in tables]
    trung_sheet = {s for s in sheet if sheet.count(s) > 1}
    if trung_sheet:
        raise RegistryError(
            f"{code}: hai bảng cùng trỏ vào sheet {', '.join(sorted(trung_sheet))}.")

    source = head.get("source") or {}
    return Form(
        code=code,
        version=int(_doi(head.get("version"), "form.version", int)),
        label=_doi(head.get("label"), "form.label", str),
        description=str(head.get("description") or "").strip(),
        tables=tables,
        policy=policy,
        source_kind=_doi(source.get("kind"), "form.source.kind", str),
        header_row=int(source.get("header_row", 1)),
        yaml_sha256=yaml_sha256,
        source_opts={k: v for k, v in source.items() if k not in ("kind", "header_row")},
        chu_phu=(str(head.get("chu_phu") or "").strip() or None),
    )


@dataclass(frozen=True)
class KhaiBaoDomain:
    """Một nhóm thông tin khai trong `khai_bao/domains.yaml`."""

    code: str
    name: str
    description: str | None = None
    # Mã các bộ bảng (loại tệp) theo thứ tự khai; rỗng = chưa có bộ bảng. HQKD có
    # một loại tệp, HQ-MAU-GC có hai (mục 5.1).
    cac_bo_bang: tuple[str, ...] = ()

    @property
    def bo_bang(self) -> str | None:
        """Bộ bảng đầu tiên — cho các chỗ chỉ biết một bộ bảng mỗi nhóm (tầng API)."""
        return self.cac_bo_bang[0] if self.cac_bo_bang else None


def dung_domains(raw: Any, ma_bo_bang: set[str]) -> list[KhaiBaoDomain]:
    """Dựng danh sách nhóm thông tin, kiểm tra mã, tên và bộ bảng tham chiếu."""
    if not isinstance(raw, dict) or not isinstance(raw.get("domains"), list):
        raise RegistryError("domains.yaml phải có danh sách `domains` ở mức cao nhất.")
    ds: list[KhaiBaoDomain] = []
    for muc in raw["domains"]:
        if not isinstance(muc, dict):
            raise RegistryError("Mỗi mục trong `domains` phải là bản ghi {code, name}.")
        code = _khop(MA_DOMAIN, _doi(muc.get("code"), "domains[].code", str),
                     "Mã nhóm thông tin")
        raw_bo = muc.get("bo_bang")
        cac_bo = [raw_bo] if isinstance(raw_bo, str) else list(raw_bo or [])
        for bo_bang in cac_bo:
            if not isinstance(bo_bang, str) or bo_bang not in ma_bo_bang:
                raise RegistryError(
                    f"{code}: bo_bang {bo_bang!r} không có trong khai_bao/forms/.")
        ds.append(KhaiBaoDomain(
            code=code,
            name=_doi(muc.get("name"), f"{code}: name", str).strip(),
            description=(str(muc.get("description") or "").strip() or None),
            cac_bo_bang=tuple(cac_bo),
        ))
    if not ds:
        raise RegistryError("domains.yaml chưa khai nhóm thông tin nào.")
    for ten, gia_tri in (("Mã nhóm thông tin", [d.code for d in ds]),
                         ("Bộ bảng", [b for d in ds for b in d.cac_bo_bang])):
        trung = {v for v in gia_tri if gia_tri.count(v) > 1}
        if trung:
            raise RegistryError(
                f"{ten} bị dùng ở hai nhóm thông tin: {', '.join(sorted(trung))}.")
    return ds
