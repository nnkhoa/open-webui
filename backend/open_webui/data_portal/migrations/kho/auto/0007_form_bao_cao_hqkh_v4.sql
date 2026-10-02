-- ===========================================================================
--  Nâng cấp bảng theo khai báo BAO_CAO_HQKH
--  TỆP NÀY SINH TỰ ĐỘNG bởi manage.py makemigration. Không sửa bằng tay.
-- ===========================================================================

-- Thêm cột Không có trong tệp — lấy từ ô Năm dữ liệu chọn lúc nạp (nam) vào fact_ket_qua_kd
ALTER TABLE bronze.fact_ket_qua_kd ADD COLUMN nam text;
ALTER TABLE silver.fact_ket_qua_kd ADD COLUMN nam bigint;
ALTER TABLE gold.fact_ket_qua_kd   ADD COLUMN nam bigint;

-- Dựng lại view phục vụ analytics.v_fact_ket_qua_kd với các cột mới
DROP VIEW IF EXISTS analytics.v_fact_ket_qua_kd;
-- Kết quả kinh doanh
CREATE VIEW analytics.v_fact_ket_qua_kd AS
    SELECT t.nam,
           t.ky_thang,
           t.ma_khach,
           t.ten_khach,
           t.ma_nhom_kd,
           t.doanh_thu,
           t.gia_von,
           t.thu_nhap_khac,
           t.lai_rong,
           t.lai_gop,
           t.ty_le_lai_gop,
           t.ty_le_lai_rong_dt,
           t.ty_le_lai_tren_von,
           t.ty_trong_dt,
           t.ty_trong_lai_rong,
           t.chenh_gop_rong,
           t.domain_id,
           t.load_id,
           t.batch_id,
           t.source_sheet,
           t.source_row
      FROM gold.fact_ket_qua_kd t
     WHERE t.is_current;

-- Đổi khoá nghiệp vụ của fact_ket_qua_kd thành (nam, ky_thang, ma_khach, ma_nhom_kd)
DROP INDEX IF EXISTS silver.silver_fact_ket_qua_kd_bk_idx;
CREATE INDEX silver_fact_ket_qua_kd_bk_idx
    ON silver.fact_ket_qua_kd (domain_id, nam, ky_thang, coalesce(ma_khach, ''), coalesce(ma_nhom_kd, '')) WHERE is_current;

-- Thêm cột Không có trong tệp — lấy từ ô Năm dữ liệu chọn lúc nạp (nam) vào fact_chi_phi
ALTER TABLE bronze.fact_chi_phi ADD COLUMN nam text;
ALTER TABLE silver.fact_chi_phi ADD COLUMN nam bigint;
ALTER TABLE gold.fact_chi_phi   ADD COLUMN nam bigint;

-- Dựng lại view phục vụ analytics.v_fact_chi_phi với các cột mới
DROP VIEW IF EXISTS analytics.v_fact_chi_phi;
-- Chi phí
CREATE VIEW analytics.v_fact_chi_phi AS
    SELECT t.nam,
           t.ky_thang,
           t.ma_khoan_cp,
           t.cap_phan_bo,
           t.ma_khach,
           t.ma_nhom_kd,
           t.so_tien,
           t.domain_id,
           t.load_id,
           t.batch_id,
           t.source_sheet,
           t.source_row
      FROM gold.fact_chi_phi t
     WHERE t.is_current;

-- Đổi khoá nghiệp vụ của fact_chi_phi thành (nam, ky_thang, ma_khoan_cp, ma_khach, ma_nhom_kd)
DROP INDEX IF EXISTS silver.silver_fact_chi_phi_bk_idx;
CREATE INDEX silver_fact_chi_phi_bk_idx
    ON silver.fact_chi_phi (domain_id, nam, ky_thang, coalesce(ma_khoan_cp, ''), coalesce(ma_khach, ''), coalesce(ma_nhom_kd, '')) WHERE is_current;
