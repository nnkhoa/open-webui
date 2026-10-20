-- =============================================================================
--  Bảng fact_may_mau: thêm cột id và style
--
--    id     mã định danh riêng của từng dòng, sinh ngẫu nhiên (UUID) lúc nạp
--    style  chưa có thông tin, để trống
--
--  Dòng đã nạp: id sinh ở Bronze, Silver và Gold lấy lại theo dòng Bronze gốc.
--  View dựng lại với hai cột mới.
-- =============================================================================

DROP VIEW IF EXISTS analytics.v_fact_may_mau;

ALTER TABLE bronze.fact_may_mau ADD COLUMN id text;
ALTER TABLE silver.fact_may_mau ADD COLUMN id text;
ALTER TABLE gold.fact_may_mau   ADD COLUMN id text;

ALTER TABLE bronze.fact_may_mau ADD COLUMN style text;
ALTER TABLE silver.fact_may_mau ADD COLUMN style text;
ALTER TABLE gold.fact_may_mau   ADD COLUMN style text;

UPDATE bronze.fact_may_mau SET id = gen_random_uuid()::text;

UPDATE silver.fact_may_mau s
   SET id = b.id
  FROM bronze.fact_may_mau b
 WHERE b.row_id = s.bronze_id;

UPDATE gold.fact_may_mau g
   SET id = s.id
  FROM silver.fact_may_mau s
 WHERE s.fact_may_mau_sk = g.silver_sk;

-- May mẫu chào hàng
CREATE VIEW analytics.v_fact_may_mau AS
    SELECT t.id,
           t.nam,
           t.thang,
           t.nhom,
           t.khach_hang,
           t.men_lady_others,
           t.sample_description,
           t.don_gia,
           t.so_luong,
           t.thanh_tien_usd,
           t.thanh_tien_vnd,
           t.style,
           t.domain_id,
           t.load_id,
           t.batch_id,
           t.source_sheet,
           t.source_row
      FROM gold.fact_may_mau t
     WHERE t.is_current;
