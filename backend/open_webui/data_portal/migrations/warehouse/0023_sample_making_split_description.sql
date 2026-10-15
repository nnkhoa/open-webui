-- =============================================================================
--  Bảng fact_may_mau: tách SAMPLE DESCRIPTION thành sample và description
--
--    sample_description → sample        phần trước dấu " - " đầu tiên
--                       → description   phần sau dấu " - " đầu tiên; không có dấu
--                                       thì "Không có thông tin"
--
--  Bronze giữ ô gốc ở cột sample. Dữ liệu đã nạp ở Silver, Gold tách lại từ giá trị
--  đang có. View và chỉ mục khoá nghiệp vụ dựng lại theo tên mới.
-- =============================================================================

DROP VIEW IF EXISTS analytics.v_fact_may_mau;
DROP INDEX IF EXISTS silver.silver_fact_may_mau_bk_idx;

ALTER TABLE bronze.fact_may_mau RENAME COLUMN sample_description TO sample;
ALTER TABLE bronze.fact_may_mau ADD COLUMN description text;

ALTER TABLE silver.fact_may_mau ADD COLUMN sample text;
ALTER TABLE silver.fact_may_mau ADD COLUMN description text;
UPDATE silver.fact_may_mau
   SET sample = trim(split_part(regexp_replace(sample_description, '\s+-\s+', E'\x1f'), E'\x1f', 1)),
       description = coalesce(
           nullif(trim(substr(sample_description, length(substring(sample_description FROM '^.*?\s+-\s+')) + 1)), ''),
           'Không có thông tin')
 WHERE sample_description ~ '\s+-\s+';
UPDATE silver.fact_may_mau
   SET sample = sample_description,
       description = 'Không có thông tin'
 WHERE sample_description !~ '\s+-\s+' OR sample_description IS NULL;
ALTER TABLE silver.fact_may_mau DROP COLUMN sample_description;

ALTER TABLE gold.fact_may_mau ADD COLUMN sample text;
ALTER TABLE gold.fact_may_mau ADD COLUMN description text;
UPDATE gold.fact_may_mau g
   SET sample = s.sample,
       description = s.description
  FROM silver.fact_may_mau s
 WHERE s.fact_may_mau_sk = g.silver_sk;
ALTER TABLE gold.fact_may_mau DROP COLUMN sample_description;

CREATE INDEX silver_fact_may_mau_bk_idx
    ON silver.fact_may_mau (domain_id, nam, khach_hang, coalesce(sample, '')) WHERE is_current;

-- May mẫu chào hàng
CREATE VIEW analytics.v_fact_may_mau AS
    SELECT t.nam,
           t.thang,
           t.nhom,
           t.khach_hang,
           t.men_lady_others,
           t.sample,
           t.description,
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
