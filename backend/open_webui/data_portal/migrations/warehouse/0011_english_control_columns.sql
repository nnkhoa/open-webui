-- =============================================================================
--  Tên cột tiếng Anh cho sổ ghi lần nạp và bản chiếu nhóm thông tin
--
--  Chỉ Data Portal trong Open WebUI đọc các cột này (Cube chỉ đọc ctl.domain và
--  schema analytics). Nội dung JSON của lần nạp cũ không được chuyển đổi.
-- =============================================================================

ALTER TABLE ctl.load RENAME COLUMN nam       TO year;
ALTER TABLE ctl.load RENAME COLUMN kiem_tra  TO file_check;
ALTER TABLE ctl.load RENAME COLUMN cac_buoc  TO steps;
ALTER TABLE ctl.load RENAME COLUMN doi_chieu TO reconciliation;
ALTER INDEX ctl.load_domain_nam_idx RENAME TO load_domain_year_idx;

ALTER TABLE ctl.domain_form RENAME COLUMN thu_tu TO position;
