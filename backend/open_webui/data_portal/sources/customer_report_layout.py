from __future__ import annotations

from dataclasses import dataclass
from typing import Any

KIND = 'customer_report'

SUMMARY_SHEET = 'TỔNG HỢP'
CUSTOMER_LIST_SHEET = 'DANH SACH KHACH HANG THEO HDX'
COST_ITEM_SHEET = 'DANH MỤC CHI PHÍ'

HEADER_SEARCH_ROWS = 10
MONTH_HEADER = 'THÁNG'
BUSINESS_GROUP_HEADER = 'NHÓM KINH DOANH'
CUSTOMER_CODE_HEADER = 'MÃ KHÁCH HÀNG'
CUSTOMER_NAME_HEADER = 'Khách hàng'
CONTRACT_HEADER = 'Hợp đồng xuất'
CUMULATIVE_MARKER = 'LK'
TOTAL_ROW_PREFIX = 'TỔNG CỘNG'
MARKER_CELL = 'x'

RESULT_COLUMNS_BY_CODE = {
    'doanh_thu': 'DA01',
    'gia_von': 'CA00',
    'cm_gia_cong': 'CA04',
    'nguyen_phu_lieu': 'CA01',
    'theu_in_wash': 'CF01',
    'thu_nhap_khac': 'DA02',
}
RESULT_COLUMNS_BY_HEADER: dict[str, tuple[str, str | None]] = {
    'lai_rong': ('LỢI NHUẬN NET', None),
    'lai_gop': ('Lợi Nhuận Gộp (doanh thu-giá vốn)', None),
    'ty_le_lai_gop': ('Tỷ lệ (LN Gộp/Doanh Thu)', None),
    'ty_le_lai_rong_dt': ('Tỷ lệ lãi/DT', 'LỢI NHUẬN NET'),
    'ty_le_lai_tren_von': ('Tỷ lệ lãi trên vốn', None),
    'ty_trong_dt': ('Tỷ trọng đóng góp doanh thu', None),
    'ty_trong_lai_rong': ('Tỷ trọng đóng góp lợi nhuận ròng', None),
    'chenh_gop_rong': ('Mức chênh lệch giữa lợi nhuận gộp và lợi nhuận ròng', None),
}

UNGROUPED_COST_HEADERS = ('Trích Chi Phí Trả Lương Khối Văn Phòng', 'Trích Chi Phí Chung')
ALLOCATION_LEVEL = 'khách hàng'

DIRECT_CUSTOMER_COST_GROUP = 'Chi phí trực tiếp khách hàng'
OTHER_COST_GROUP = 'Chi phí nhóm còn lại'
COST_GROUP_BY_CODE: dict[str, str] = {
    **dict.fromkeys(
        ('CG02', 'CG03', 'CG04', 'CG09.1', 'CG09', 'CG10', 'CG11', 'CH06', 'CH01', 'CH02', 'CK01', 'CJ03'),
        DIRECT_CUSTOMER_COST_GROUP,
    ),
    **dict.fromkeys(('CL03', 'CF02', 'CL14', 'CL15', 'CB01', 'CHUNG'), OTHER_COST_GROUP),
}

RESULTS_TABLE = 'KET_QUA_KD'
COSTS_TABLE = 'CHI_PHI'
CUSTOMERS_TABLE = 'DM_KHACH_HANG'
COST_ITEMS_TABLE = 'DM_KHOAN_CP'
FLAT_TABLES: dict[str, tuple[str, ...]] = {
    RESULTS_TABLE: (
        'ky_thang',
        'ma_khach',
        'ten_khach',
        'ma_nhom_kd',
        'doanh_thu',
        'gia_von',
        'cm_gia_cong',
        'nguyen_phu_lieu',
        'theu_in_wash',
        'thu_nhap_khac',
        'lai_rong',
        'lai_gop',
        'ty_le_lai_gop',
        'ty_le_lai_rong_dt',
        'ty_le_lai_tren_von',
        'ty_trong_dt',
        'ty_trong_lai_rong',
        'chenh_gop_rong',
    ),
    COSTS_TABLE: ('ky_thang', 'ma_khoan_cp', 'cap_phan_bo', 'ma_khach', 'ma_nhom_kd', 'so_tien'),
    CUSTOMERS_TABLE: ('ma_khach', 'ten_khach', 'hop_dong_xuat'),
    COST_ITEMS_TABLE: ('ma_khoan_cp', 'ten_khoan', 'nhom_chi_phi'),
}

SOURCE_SHEET_BY_TABLE: dict[str, str] = {
    RESULTS_TABLE: SUMMARY_SHEET,
    COSTS_TABLE: SUMMARY_SHEET,
    CUSTOMERS_TABLE: CUSTOMER_LIST_SHEET,
    COST_ITEMS_TABLE: COST_ITEM_SHEET,
}


@dataclass(frozen=True)
class CatalogColumn:
    name: str
    header: str
    anchor: str | None = None


@dataclass(frozen=True)
class CatalogSheet:
    sheet: str
    table: str
    columns: tuple[CatalogColumn, ...]

    @property
    def headers(self) -> tuple[str, ...]:
        return tuple(column.header for column in self.columns)


# Sheet khách hàng có hai cột cùng tên HỢP ĐỒNG XUẤT (cột A và cột H); lấy cột H nằm
# sau cột Trung Tâm Phí, cùng dòng với mã khách hàng.
CUSTOMER_CATALOG = CatalogSheet(
    CUSTOMER_LIST_SHEET,
    CUSTOMERS_TABLE,
    (
        CatalogColumn('ma_khach', 'Mã Trung Tâm Phí'),
        CatalogColumn('ten_khach', 'Trung Tâm Phí'),
        CatalogColumn('hop_dong_xuat', 'HỢP ĐỒNG XUẤT', 'Trung Tâm Phí'),
    ),
)
COST_ITEM_CATALOG = CatalogSheet(
    COST_ITEM_SHEET,
    COST_ITEMS_TABLE,
    (CatalogColumn('ma_khoan_cp', 'MÃ KHOẢN MỤC'), CatalogColumn('ten_khoan', 'KHOẢN MỤC')),
)


def is_total_row(customer_code: str | None, customer_name: str | None) -> bool:
    return (
        customer_code is None
        and customer_name is not None
        and ' '.join(customer_name.split()).upper().startswith(TOTAL_ROW_PREFIX)
    )


def is_marker_row(cells: list[Any]) -> bool:
    filled = [value for value in cells if value is not None and str(value).strip()]
    return bool(filled) and all(str(value).strip().lower() == MARKER_CELL for value in filled)


def add_summary_contracts(customers: list[dict[str, Any]], summary_rows: list[dict[str, Any]]) -> None:
    """Thêm vào danh mục khách hàng các cặp mã khách – hợp đồng xuất chỉ có ở sheet TỔNG HỢP.

    Tên khách lấy theo danh mục nếu mã đã có, không thì lấy tên ghi ở dòng TỔNG HỢP.
    """
    names: dict[str, Any] = {}
    for row in customers:
        names.setdefault(row['ma_khach'], row['ten_khach'])
    known = {(row['ma_khach'], _stripped(row['hop_dong_xuat'])) for row in customers}
    for row in summary_rows:
        key = (row['ma_khach'], _stripped(row['hop_dong_xuat']))
        if key[1] is None or key in known:
            continue
        known.add(key)
        customers.append(
            {
                'ma_khach': row['ma_khach'],
                'ten_khach': names.get(row['ma_khach'], row['ten_khach']),
                'hop_dong_xuat': row['hop_dong_xuat'],
            }
        )


def _stripped(value: Any) -> str | None:
    return None if value is None else str(value).strip() or None


def cost_group(cost_item_code: str | None) -> str | None:
    return COST_GROUP_BY_CODE.get((cost_item_code or '').strip())
