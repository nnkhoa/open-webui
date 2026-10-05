-- ===========================================================================
--  Nâng cấp bảng theo khai báo BAO_CAO_HQKH
--  TỆP NÀY SINH TỰ ĐỘNG bởi manage.py makemigration. Không sửa bằng tay.
-- ===========================================================================

-- Thêm cột Khách hàng (ten_khach) vào fact_ket_qua_kd
ALTER TABLE bronze.fact_ket_qua_kd ADD COLUMN ten_khach text;
ALTER TABLE silver.fact_ket_qua_kd ADD COLUMN ten_khach text;
ALTER TABLE gold.fact_ket_qua_kd   ADD COLUMN ten_khach text;

-- Thêm cột Thu nhập khác- từ DBN (thu_nhap_khac) vào fact_ket_qua_kd
ALTER TABLE bronze.fact_ket_qua_kd ADD COLUMN thu_nhap_khac text;
ALTER TABLE silver.fact_ket_qua_kd ADD COLUMN thu_nhap_khac numeric;
ALTER TABLE gold.fact_ket_qua_kd   ADD COLUMN thu_nhap_khac numeric;

-- Dựng lại view phục vụ analytics.v_fact_ket_qua_kd với các cột mới
DROP VIEW IF EXISTS analytics.v_fact_ket_qua_kd;
-- Kết quả kinh doanh
CREATE VIEW analytics.v_fact_ket_qua_kd AS
    SELECT t.ky_thang,
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
