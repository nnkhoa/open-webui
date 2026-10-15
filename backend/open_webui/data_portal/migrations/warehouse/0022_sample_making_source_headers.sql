-- =============================================================================
--  Bảng fact_may_mau theo tệp THONG KE MAY MAU 2026 - FPT: tên cột là tên tiêu đề
--  của tệp, lấy đủ 9 cột, giá trị y như tệp
--
--    ky_thang     → thang              (THÁNG)
--    ma_nhom_kd   → nhom               (NHÓM)
--    ma_khach     → khach_hang         (KHÁCH HÀNG)
--    men_lady     → men_lady_others    (MEN / LADY / OTHERS)
--    don_gia_usd  → don_gia            (ĐƠN GIÁ)
--    sample, description → sample_description   (SAMPLE DESCRIPTION, không tách)
--    thêm thanh_tien_usd, thanh_tien_vnd         (THÀNH TIỀN USD, THÀNH TIỀN VNĐ)
--
--  Dữ liệu đã nạp giữ nguyên; sample_description của các dòng cũ lấy lại từ ô gốc
--  ở bronze. View và chỉ mục khoá nghiệp vụ dựng lại theo tên mới.
-- =============================================================================

DROP VIEW IF EXISTS analytics.v_fact_may_mau;
DROP INDEX IF EXISTS silver.silver_fact_may_mau_bk_idx;

ALTER TABLE bronze.fact_may_mau RENAME COLUMN ky_thang TO thang;
ALTER TABLE silver.fact_may_mau RENAME COLUMN ky_thang TO thang;
ALTER TABLE gold.fact_may_mau RENAME COLUMN ky_thang TO thang;

ALTER TABLE bronze.fact_may_mau RENAME COLUMN ma_nhom_kd TO nhom;
ALTER TABLE silver.fact_may_mau RENAME COLUMN ma_nhom_kd TO nhom;
ALTER TABLE gold.fact_may_mau RENAME COLUMN ma_nhom_kd TO nhom;

ALTER TABLE bronze.fact_may_mau RENAME COLUMN ma_khach TO khach_hang;
ALTER TABLE silver.fact_may_mau RENAME COLUMN ma_khach TO khach_hang;
ALTER TABLE gold.fact_may_mau RENAME COLUMN ma_khach TO khach_hang;

ALTER TABLE bronze.fact_may_mau RENAME COLUMN men_lady TO men_lady_others;
ALTER TABLE silver.fact_may_mau RENAME COLUMN men_lady TO men_lady_others;
ALTER TABLE gold.fact_may_mau RENAME COLUMN men_lady TO men_lady_others;

ALTER TABLE bronze.fact_may_mau RENAME COLUMN don_gia_usd TO don_gia;
ALTER TABLE silver.fact_may_mau RENAME COLUMN don_gia_usd TO don_gia;
ALTER TABLE gold.fact_may_mau RENAME COLUMN don_gia_usd TO don_gia;

ALTER TABLE bronze.fact_may_mau RENAME COLUMN sample TO sample_description;
ALTER TABLE bronze.fact_may_mau DROP COLUMN description;

ALTER TABLE silver.fact_may_mau ADD COLUMN sample_description text;
UPDATE silver.fact_may_mau s
   SET sample_description = coalesce(regexp_replace(trim(b.sample_description), '\s+', ' ', 'g'), 'Không có thông tin')
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

ALTER TABLE bronze.fact_may_mau ADD COLUMN thanh_tien_usd text;
ALTER TABLE silver.fact_may_mau ADD COLUMN thanh_tien_usd numeric;
ALTER TABLE gold.fact_may_mau   ADD COLUMN thanh_tien_usd numeric;

ALTER TABLE bronze.fact_may_mau ADD COLUMN thanh_tien_vnd text;
ALTER TABLE silver.fact_may_mau ADD COLUMN thanh_tien_vnd numeric;
ALTER TABLE gold.fact_may_mau   ADD COLUMN thanh_tien_vnd numeric;

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
