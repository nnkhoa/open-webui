-- =============================================================================
--  Bảng fact_may_mau: SAMPLE DESCRIPTION giữ một cột sample_description như tệp
--
--    sample, description → sample_description   (không tách)
--
--  Bronze giữ ô gốc ở cột sample, đổi tên thành sample_description. Silver, Gold
--  lấy lại giá trị từ ô gốc ở Bronze (gộp khoảng trắng). View và chỉ mục khoá
--  nghiệp vụ dựng lại theo tên mới.
-- =============================================================================

DROP VIEW IF EXISTS analytics.v_fact_may_mau;
DROP INDEX IF EXISTS silver.silver_fact_may_mau_bk_idx;

ALTER TABLE bronze.fact_may_mau RENAME COLUMN sample TO sample_description;
ALTER TABLE bronze.fact_may_mau DROP COLUMN description;

ALTER TABLE silver.fact_may_mau ADD COLUMN sample_description text;
UPDATE silver.fact_may_mau s
   SET sample_description = coalesce(nullif(trim(regexp_replace(b.sample_description, '\s+', ' ', 'g')), ''),
                                     'Không có thông tin')
  FROM bronze.fact_may_mau b
 WHERE b.row_id = s.bronze_id;
ALTER TABLE silver.fact_may_mau DROP COLUMN sample;
ALTER TABLE silver.fact_may_mau DROP COLUMN description;

ALTER TABLE gold.fact_may_mau ADD COLUMN sample_description text;
UPDATE gold.fact_may_mau g
   SET sample_description = s.sample_description
  FROM silver.fact_may_mau s
 WHERE s.fact_may_mau_sk = g.silver_sk;
ALTER TABLE gold.fact_may_mau DROP COLUMN sample;
ALTER TABLE gold.fact_may_mau DROP COLUMN description;

CREATE INDEX silver_fact_may_mau_bk_idx
    ON silver.fact_may_mau (domain_id, nam, khach_hang, coalesce(sample_description, '')) WHERE is_current;

-- May mẫu chào hàng
CREATE VIEW analytics.v_fact_may_mau AS
    SELECT t.nam,
           t.thang,
           t.nhom,
           t.khach_hang,
           t.men_lady_others,
           t.sample_description,
           t.don_gia,
           t.so_luong,
           t.thanh_tien_usd,
           t.thanh_tien_vnd,
           t.domain_id,
           t.load_id,
           t.batch_id,
           t.source_sheet,
           t.source_row
      FROM gold.fact_may_mau t
     WHERE t.is_current;
