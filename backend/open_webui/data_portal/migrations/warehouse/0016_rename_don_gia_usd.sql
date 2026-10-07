-- =============================================================================
--  Đổi tên cột don_gia của bảng fact_may_mau thành don_gia_usd
--
--  Cột PRICE / PC ( USD ) của tệp SAMPLE MAKING SCHEDULE là đơn giá tính bằng USD;
--  tên cột ghi rõ đơn vị. Dữ liệu đã nạp giữ nguyên; view dựng lại để lộ tên mới.
-- =============================================================================

DROP VIEW IF EXISTS analytics.v_fact_may_mau;

ALTER TABLE bronze.fact_may_mau RENAME COLUMN don_gia TO don_gia_usd;
ALTER TABLE silver.fact_may_mau RENAME COLUMN don_gia TO don_gia_usd;
ALTER TABLE gold.fact_may_mau RENAME COLUMN don_gia TO don_gia_usd;

CREATE VIEW analytics.v_fact_may_mau AS
    SELECT t.nam,
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
