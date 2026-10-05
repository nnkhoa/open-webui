-- ===========================================================================
--  Nâng cấp bảng theo khai báo BAO_CAO_HQKH
--  TỆP NÀY SINH TỰ ĐỘNG bởi manage.py makemigration. Không sửa bằng tay.
-- ===========================================================================

-- Thêm cột Nhóm chi phí (nhom_chi_phi) vào dim_khoan_cp
ALTER TABLE bronze.dim_khoan_cp ADD COLUMN nhom_chi_phi text;
ALTER TABLE silver.dim_khoan_cp ADD COLUMN nhom_chi_phi text;
ALTER TABLE gold.dim_khoan_cp   ADD COLUMN nhom_chi_phi text;

DROP VIEW IF EXISTS analytics.v_dim_khoan_cp;
-- Danh mục khoản chi phí
CREATE VIEW analytics.v_dim_khoan_cp AS
    SELECT t.ma_khoan_cp,
           t.ten_khoan,
           t.nhom_chi_phi,
           t.domain_id,
           t.load_id,
           t.batch_id,
           t.source_sheet,
           t.source_row
      FROM gold.dim_khoan_cp t
     WHERE t.is_current;
