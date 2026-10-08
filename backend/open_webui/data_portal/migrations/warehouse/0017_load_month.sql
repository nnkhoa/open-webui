-- =============================================================================
--  Tháng dữ liệu của lần nạp
--
--  Nhóm HQ-MAU-GC chọn Tháng lúc nạp (cột ky_thang của dữ liệu). Sổ ghi lần nạp
--  lưu tháng để hiện ở Lịch sử và để nhận ra tệp đã nạp cùng năm, cùng tháng.
--  Nhóm không chọn tháng thì để trống.
-- =============================================================================

ALTER TABLE ctl.load ADD COLUMN IF NOT EXISTS month smallint CHECK (month BETWEEN 1 AND 12);
