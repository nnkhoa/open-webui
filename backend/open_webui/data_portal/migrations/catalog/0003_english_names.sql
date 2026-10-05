-- =============================================================================
--  Tên bảng và cột tiếng Anh cho cấu hình kết nối kho và thứ tự loại tệp
-- =============================================================================

ALTER TABLE ctl_ket_noi_kho RENAME TO ctl_warehouse_connection;
ALTER TABLE ctl_warehouse_connection RENAME COLUMN ghi_chu        TO note;
ALTER TABLE ctl_warehouse_connection RENAME COLUMN thu_luc        TO tested_at;
ALTER TABLE ctl_warehouse_connection RENAME COLUMN thu_dat        TO test_ok;
ALTER TABLE ctl_warehouse_connection RENAME COLUMN thu_thong_diep TO test_message;
ALTER TABLE ctl_warehouse_connection RENAME COLUMN cap_nhat_luc   TO updated_at;
ALTER TABLE ctl_warehouse_connection RENAME COLUMN cap_nhat_boi   TO updated_by;

ALTER TABLE ctl_domain_form RENAME COLUMN thu_tu TO position;
