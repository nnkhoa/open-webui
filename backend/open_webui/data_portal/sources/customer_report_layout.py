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
CUMULATIVE_MARKER = 'LK'
TOTAL_ROW_PREFIX = 'TỔNG CỘNG'
MARKER_CELL = 'x'

RESULT_COLUMNS_BY_CODE = {'doanh_thu': 'DA01', 'gia_von': 'CA00', 'thu_nhap_khac': 'DA02'}
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
    CUSTOMERS_TABLE: ('ma_khach', 'ten_khach'),
    COST_ITEMS_TABLE: ('ma_khoan_cp', 'ten_khoan', 'nhom_chi_phi'),
}

SOURCE_SHEET_BY_TABLE: dict[str, str] = {
    RESULTS_TABLE: SUMMARY_SHEET,
    COSTS_TABLE: SUMMARY_SHEET,
    CUSTOMERS_TABLE: CUSTOMER_LIST_SHEET,
    COST_ITEMS_TABLE: COST_ITEM_SHEET,
}


@dataclass(frozen=True)
class CatalogSheet:
    sheet: str
    table: str
    code_header: str
    name_header: str
    columns: tuple[str, str]


CUSTOMER_CATALOG = CatalogSheet(
    CUSTOMER_LIST_SHEET, CUSTOMERS_TABLE, 'Mã Trung Tâm Phí', 'Trung Tâm Phí', ('ma_khach', 'ten_khach')
)
COST_ITEM_CATALOG = CatalogSheet(
    COST_ITEM_SHEET, COST_ITEMS_TABLE, 'MÃ KHOẢN MỤC', 'KHOẢN MỤC', ('ma_khoan_cp', 'ten_khoan')
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


def cost_group(cost_item_code: str | None) -> str | None:
    return COST_GROUP_BY_CODE.get((cost_item_code or '').strip())
