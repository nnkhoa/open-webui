-- ===========================================================================
--  Nâng cấp bảng theo khai báo DON_GIA_CONG
--  TỆP NÀY SINH TỰ ĐỘNG bởi lệnh manage makemigration. Không sửa bằng tay.
-- ===========================================================================

-- Thêm cột Không có trong tệp — lấy từ ô Tháng dữ liệu chọn lúc nạp (ky_thang) vào fact_gia_cong
ALTER TABLE bronze.fact_gia_cong ADD COLUMN ky_thang text;
ALTER TABLE silver.fact_gia_cong ADD COLUMN ky_thang bigint;
ALTER TABLE gold.fact_gia_cong   ADD COLUMN ky_thang bigint;

-- Dựng lại view phục vụ analytics.v_fact_gia_cong với các cột mới
DROP VIEW IF EXISTS analytics.v_fact_gia_cong;
-- Đơn gia công ngoài
CREATE VIEW analytics.v_fact_gia_cong AS
    SELECT t.nam,
           t.ky_thang,
           t.ma_don_vi_gc,
           t.location,
           t.ma_khach,
           t.so_luong,
           t.actual_cut,
           t.domain_id,
           t.load_id,
           t.batch_id,
           t.source_sheet,
           t.source_row
      FROM gold.fact_gia_cong t
     WHERE t.is_current;
