-- ===========================================================================
--  Nâng cấp bảng theo khai báo BAO_CAO_HQKH
--  TỆP NÀY SINH TỰ ĐỘNG bởi lệnh manage makemigration. Không sửa bằng tay.
-- ===========================================================================

-- Thêm cột HỢP ĐỒNG XUẤT (hop_dong_xuat) vào dim_khach_hang
ALTER TABLE bronze.dim_khach_hang ADD COLUMN hop_dong_xuat text;
ALTER TABLE silver.dim_khach_hang ADD COLUMN hop_dong_xuat text;
ALTER TABLE gold.dim_khach_hang   ADD COLUMN hop_dong_xuat text;

-- Dựng lại view phục vụ analytics.v_dim_khach_hang với các cột mới
DROP VIEW IF EXISTS analytics.v_dim_khach_hang;
-- Danh mục khách hàng
CREATE VIEW analytics.v_dim_khach_hang AS
    SELECT t.ma_khach,
           t.ten_khach,
           t.hop_dong_xuat,
           t.domain_id,
           t.load_id,
           t.batch_id,
           t.source_sheet,
           t.source_row
      FROM gold.dim_khach_hang t
     WHERE t.is_current;

-- Đổi khoá nghiệp vụ của dim_khach_hang thành (ma_khach, hop_dong_xuat)
DROP INDEX IF EXISTS silver.silver_dim_khach_hang_bk_idx;
CREATE INDEX silver_dim_khach_hang_bk_idx
    ON silver.dim_khach_hang (domain_id, coalesce(ma_khach, ''), coalesce(hop_dong_xuat, '')) WHERE is_current;

-- Thêm cột CM Gia Công (cm_gia_cong) vào fact_ket_qua_kd
ALTER TABLE bronze.fact_ket_qua_kd ADD COLUMN cm_gia_cong text;
ALTER TABLE silver.fact_ket_qua_kd ADD COLUMN cm_gia_cong numeric;
ALTER TABLE gold.fact_ket_qua_kd   ADD COLUMN cm_gia_cong numeric;

-- Thêm cột Nguyên phụ liệu (nguyen_phu_lieu) vào fact_ket_qua_kd
ALTER TABLE bronze.fact_ket_qua_kd ADD COLUMN nguyen_phu_lieu text;
ALTER TABLE silver.fact_ket_qua_kd ADD COLUMN nguyen_phu_lieu numeric;
ALTER TABLE gold.fact_ket_qua_kd   ADD COLUMN nguyen_phu_lieu numeric;

-- Thêm cột Thêu + In + Wash (theu_in_wash) vào fact_ket_qua_kd
ALTER TABLE bronze.fact_ket_qua_kd ADD COLUMN theu_in_wash text;
ALTER TABLE silver.fact_ket_qua_kd ADD COLUMN theu_in_wash numeric;
ALTER TABLE gold.fact_ket_qua_kd   ADD COLUMN theu_in_wash numeric;

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
           t.cm_gia_cong,
           t.nguyen_phu_lieu,
           t.theu_in_wash,
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
