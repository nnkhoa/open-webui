-- =============================================================================
--  Đổi tên các cột phiếu khảo sát không có mã cột về đúng tên cột gốc của tệp
--
--    fact_gia_cong  so_luong_cat → actual_cut   (cột Actual cut, TOTAL PO SUBCON)
--    fact_gia_cong  khu_vuc      → location     (cột Location, TOTAL PO SUBCON)
--    fact_may_mau   doi_tuong    → men_lady     (cột MEN / LADY, SAMPLE MAKING SCHEDULE)
--
--  Dữ liệu đã nạp giữ nguyên; hai view dựng lại để lộ tên mới.
-- =============================================================================

DROP VIEW IF EXISTS analytics.v_fact_gia_cong;
DROP VIEW IF EXISTS analytics.v_fact_may_mau;

ALTER TABLE bronze.fact_gia_cong RENAME COLUMN so_luong_cat TO actual_cut;
ALTER TABLE silver.fact_gia_cong RENAME COLUMN so_luong_cat TO actual_cut;
ALTER TABLE gold.fact_gia_cong RENAME COLUMN so_luong_cat TO actual_cut;

ALTER TABLE bronze.fact_gia_cong RENAME COLUMN khu_vuc TO location;
ALTER TABLE silver.fact_gia_cong RENAME COLUMN khu_vuc TO location;
ALTER TABLE gold.fact_gia_cong RENAME COLUMN khu_vuc TO location;

ALTER TABLE bronze.fact_may_mau RENAME COLUMN doi_tuong TO men_lady;
ALTER TABLE silver.fact_may_mau RENAME COLUMN doi_tuong TO men_lady;
ALTER TABLE gold.fact_may_mau RENAME COLUMN doi_tuong TO men_lady;

CREATE VIEW analytics.v_fact_gia_cong AS
    SELECT t.nam,
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

CREATE VIEW analytics.v_fact_may_mau AS
    SELECT t.nam,
           t.ma_khach,
           t.men_lady,
           t.sample,
           t.description,
           t.ma_nhom_kd,
           t.so_luong,
           t.don_gia,
           t.domain_id,
           t.load_id,
           t.batch_id,
           t.source_sheet,
           t.source_row
      FROM gold.fact_may_mau t
     WHERE t.is_current;
