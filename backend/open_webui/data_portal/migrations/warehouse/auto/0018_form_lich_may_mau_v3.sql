-- ===========================================================================
--  Nâng cấp bảng theo khai báo LICH_MAY_MAU
--  TỆP NÀY SINH TỰ ĐỘNG bởi lệnh manage makemigration. Không sửa bằng tay.
-- ===========================================================================

-- Thêm cột Không có trong tệp — lấy từ ô Tháng dữ liệu chọn lúc nạp (ky_thang) vào fact_may_mau
ALTER TABLE bronze.fact_may_mau ADD COLUMN ky_thang text;
ALTER TABLE silver.fact_may_mau ADD COLUMN ky_thang bigint;
ALTER TABLE gold.fact_may_mau   ADD COLUMN ky_thang bigint;

-- Dựng lại view phục vụ analytics.v_fact_may_mau với các cột mới
DROP VIEW IF EXISTS analytics.v_fact_may_mau;
-- May mẫu chào hàng
CREATE VIEW analytics.v_fact_may_mau AS
    SELECT t.nam,
           t.ky_thang,
           t.ma_khach,
           t.men_lady,
           t.sample,
           t.description,
           t.ma_nhom_kd,
           t.so_luong,
           t.don_gia_usd,
           t.domain_id,
           t.load_id,
           t.batch_id,
           t.source_sheet,
           t.source_row
      FROM gold.fact_may_mau t
     WHERE t.is_current;
