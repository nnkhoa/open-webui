-- =============================================================================
--  Một nhóm thông tin có thể có nhiều loại tệp (bộ bảng) — bản chiếu ở kho
--
--  HQ-MAU-GC nhận hai loại tệp (đặc tả 5.1). Khoá chính đổi từ (domain_id) sang
--  (domain_id, form_id); mỗi bộ bảng vẫn chỉ thuộc tối đa một nhóm (UNIQUE form_id).
--  `thu_tu` chép từ sổ tay.
-- =============================================================================

ALTER TABLE ctl.domain_form DROP CONSTRAINT domain_form_pkey;
ALTER TABLE ctl.domain_form ADD PRIMARY KEY (domain_id, form_id);
-- Thứ tự loại tệp trong nhóm, theo domains.yaml (ô chọn Loại tệp, màn Dữ liệu).
ALTER TABLE ctl.domain_form ADD COLUMN thu_tu int NOT NULL DEFAULT 1;
