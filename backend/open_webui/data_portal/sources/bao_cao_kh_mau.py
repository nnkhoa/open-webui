"""Bố cục báo cáo "HIỆU QUẢ TỪNG KHÁCH HÀNG" và bốn bảng nó được tách thành.

NBC điền số liệu vào báo cáo `FORM MAU - HIEU QUA TUNG KHACH HANG NAM ….xlsx`:
sheet TỔNG HỢP mỗi khách hàng một dòng, chi phí trải ngang thành cột; hai sheet
danh mục khách hàng và khoản chi phí. Bốn bảng phẳng có các cột của tệp
`20260921_NBC-QTTM_Bieu_mau_nhap_du_lieu.xlsx`, thêm:

* `nhom_chi_phi` ở danh mục khoản chi phí;
* `ten_khach` (cột "Khách hàng") và `thu_nhap_khac` (mã DA02) ở KET_QUA_KD —
  báo cáo có khách chỉ ghi tên không ghi mã, và LỢI NHUẬN NET của báo cáo cộng
  thêm thu nhập khác, nên thiếu hai cột này thì không đối được lợi nhuận ròng.

Mô-đun này chỉ **khai báo** bố cục — tên sheet, tên cột, bảng phẳng. Hai đường
đọc dùng chung khai báo này nhưng không dùng chung mã đọc:

* `bao_cao_kh.py`         đọc bằng openpyxl, ghi vào lớp gốc
* `bao_cao_kh_verify.py`  đọc thẳng XML, chỉ dùng cho đối chiếu R1

Cột nhận theo **tên** (chuẩn hoá bằng `base.chuan_ten`), không theo vị trí.
"""

from __future__ import annotations

KIND = "bao_cao_hieu_qua_kh"

SHEET_TONG_HOP = "TỔNG HỢP"
SHEET_DS_KHACH = "DANH SACH KHACH HANG THEO HDX"
SHEET_DM_CP = "DANH MỤC CHI PHÍ"

# Sheet TỔNG HỢP: dòng tiêu đề là dòng có ô "THÁNG". Dòng ngay trên là mã khoản
# mục (DA01, CG02…), dòng trên nữa là nhóm chi phí.
TIM_TIEU_DE_TRONG = 10
TD_THANG = "THÁNG"
TD_NHOM_KD = "NHÓM KINH DOANH"
TD_MA_KHACH = "MÃ KHÁCH HÀNG"
TD_TEN_KHACH = "Khách hàng"
DAU_LUY_KE = "LK"          # cột THÁNG ghi LK: từ đây là phần lũy kế, không đọc
# Dòng tổng của từng tháng ("TỔNG CỘNG THÁNG 1 NĂM 2026"): có THÁNG, không có mã,
# cột "Khách hàng" ghi chữ này. Là dòng cộng các nhóm, không phải khách hàng.
DAU_DONG_TONG = "TỔNG CỘNG"

# Cột của KET_QUA_KD: theo mã khoản mục nếu cột có mã, còn lại theo tiêu đề.
# Tiêu đề lặp ("Tỷ lệ lãi/DT" có hai cột) thì nêu thêm cột neo — lấy cột đầu
# tiên mang tiêu đề đó **nằm sau** cột neo.
KQKD_THEO_MA = {"doanh_thu": "DA01", "gia_von": "CA00", "thu_nhap_khac": "DA02"}
KQKD_THEO_TIEU_DE: dict[str, tuple[str, str | None]] = {
    "lai_rong": ("LỢI NHUẬN NET", None),
    "lai_gop": ("Lợi Nhuận Gộp (doanh thu-giá vốn)", None),
    "ty_le_lai_gop": ("Tỷ lệ (LN Gộp/Doanh Thu)", None),
    "ty_le_lai_rong_dt": ("Tỷ lệ lãi/DT", "LỢI NHUẬN NET"),
    "ty_le_lai_tren_von": ("Tỷ lệ lãi trên vốn", None),
    "ty_trong_dt": ("Tỷ trọng đóng góp doanh thu", None),
    "ty_trong_lai_rong": ("Tỷ trọng đóng góp lợi nhuận ròng", None),
    "chenh_gop_rong": ("Mức chênh lệch giữa lợi nhuận gộp và lợi nhuận ròng", None),
}

# Cột của CHI_PHI: mọi cột có nhóm chi phí ở dòng trên cùng, cộng hai cột trích
# không nằm trong nhóm nào (không có mã khoản — `ma_khoan_cp` để trống).
CP_NGOAI_NHOM = ("Trích Chi Phí Trả Lương Khối Văn Phòng", "Trích Chi Phí Chung")

# `cap_phan_bo` của CHI_PHI: báo cáo không có cột này. Phiếu khảo sát
# 20260915_NBC-QTTM_Bieu_mau_du_lieu_va_Khao_sat, sheet "3. Chi phi", NBC trả
# lời mọi khoản "được phân bổ tới từng khách hàng" — ghi cố định theo đó.
CAP_PHAN_BO = "khách hàng"

# `nhom_chi_phi` của DM_KHOAN_CP: nhóm ghi ở dòng trên cùng sheet TỔNG HỢP, trên
# mỗi cột chi phí. Khai cố định theo mã; mã không có ở đây thì để trống.
TRUC_TIEP_KH = "Chi phí trực tiếp khách hàng"
NHOM_CON_LAI = "Chi phí nhóm còn lại"
NHOM_CHI_PHI: dict[str, str] = {
    **dict.fromkeys(("CG02", "CG03", "CG04", "CG09.1", "CG09", "CG10", "CG11", "CH06",
                     "CH01", "CH02", "CK01", "CJ03"), TRUC_TIEP_KH),
    **dict.fromkeys(("CL03", "CF02", "CL14", "CL15", "CB01", "CHUNG"), NHOM_CON_LAI),
}

TD_DS_MA = "Mã Trung Tâm Phí"
TD_DS_TEN = "Trung Tâm Phí"
TD_DM_MA = "MÃ KHOẢN MỤC"
TD_DM_TEN = "KHOẢN MỤC"

# Bảng phẳng: tên sheet → tên cột, đúng thứ tự.
KET_QUA_KD = "KET_QUA_KD"
CHI_PHI = "CHI_PHI"
DM_KHACH_HANG = "DM_KHACH_HANG"
DM_KHOAN_CP = "DM_KHOAN_CP"
BANG_PHANG: dict[str, tuple[str, ...]] = {
    KET_QUA_KD: ("ky_thang", "ma_khach", "ten_khach", "ma_nhom_kd", "doanh_thu", "gia_von",
                 "thu_nhap_khac", "lai_rong", "lai_gop", "ty_le_lai_gop", "ty_le_lai_rong_dt",
                 "ty_le_lai_tren_von", "ty_trong_dt", "ty_trong_lai_rong", "chenh_gop_rong"),
    CHI_PHI: ("ky_thang", "ma_khoan_cp", "cap_phan_bo", "ma_khach", "ma_nhom_kd", "so_tien"),
    DM_KHACH_HANG: ("ma_khach", "ten_khach"),
    DM_KHOAN_CP: ("ma_khoan_cp", "ten_khoan", "nhom_chi_phi"),
}


# Sheet của tệp NBC mà mỗi bảng phẳng được tách ra — cột "Lấy từ sheet" ở màn
# Xác nhận và liên kết mở Tệp gốc đúng sheet.
SHEET_GOC: dict[str, str] = {
    KET_QUA_KD: SHEET_TONG_HOP,
    CHI_PHI: SHEET_TONG_HOP,
    DM_KHACH_HANG: SHEET_DS_KHACH,
    DM_KHOAN_CP: SHEET_DM_CP,
}


def la_dong_tong(ma_khach: str | None, ten_khach: str | None) -> bool:
    """Dòng tổng của tháng — không mã khách, tên bắt đầu bằng "TỔNG CỘNG"."""
    return (ma_khach is None and ten_khach is not None
            and " ".join(ten_khach.split()).upper().startswith(DAU_DONG_TONG))


def la_dong_danh_dau(o: list) -> bool:
    """Dòng chỉ gồm chữ x (dòng đánh dấu bộ lọc dưới tiêu đề) — không phải dữ liệu."""
    co = [v for v in o if v is not None and str(v).strip()]
    return bool(co) and all(str(v).strip().lower() == "x" for v in co)
