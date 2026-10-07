-- =============================================================================
--  Dựng lại bảng của nhóm HQ-MAU-GC theo khai báo v2
--
--  LICH_MAY_MAU và DON_GIA_CONG v2 chỉ lấy các cột tô vàng của tệp, nên bỏ hẳn bảng
--  v1 cùng mọi lần nạp của hai biểu mẫu này. Migration tự sinh kế tiếp tạo lại bảng
--  ở bốn lớp; dữ liệu nạp lại từ tệp.
-- =============================================================================

DROP VIEW IF EXISTS analytics.v_fact_may_mau;
DROP VIEW IF EXISTS analytics.v_fact_gia_cong;

DROP TABLE IF EXISTS gold.fact_may_mau, silver.fact_may_mau, bronze.fact_may_mau;
DROP TABLE IF EXISTS gold.fact_gia_cong, silver.fact_gia_cong, bronze.fact_gia_cong;

UPDATE ctl.load
   SET batch_id = NULL
 WHERE form_id IN (SELECT form_id FROM ctl.form WHERE code IN ('LICH_MAY_MAU', 'DON_GIA_CONG'));

DELETE FROM ctl.batch
 WHERE form_id IN (SELECT form_id FROM ctl.form WHERE code IN ('LICH_MAY_MAU', 'DON_GIA_CONG'));

DELETE FROM ctl.load
 WHERE form_id IN (SELECT form_id FROM ctl.form WHERE code IN ('LICH_MAY_MAU', 'DON_GIA_CONG'));

DELETE FROM ctl.upload
 WHERE form_id IN (SELECT form_id FROM ctl.form WHERE code IN ('LICH_MAY_MAU', 'DON_GIA_CONG'));
