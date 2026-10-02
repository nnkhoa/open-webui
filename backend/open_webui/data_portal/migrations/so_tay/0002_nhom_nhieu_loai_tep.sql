-- =============================================================================
--  Một nhóm thông tin có thể có nhiều loại tệp (bộ bảng)
--
--  HQ-MAU-GC nhận hai loại tệp: Lịch may mẫu và Đơn gia công ngoài (đặc tả 5.1).
--  Trước đây mỗi nhóm tối đa một bộ bảng (khoá chính là domain_id). Mỗi bộ bảng
--  vẫn chỉ thuộc tối đa một nhóm. `thu_tu` giữ thứ tự khai ở domains.yaml — thứ
--  tự trong ô chọn Loại tệp.
--
--  SQLite không đổi được khoá chính tại chỗ: dựng bảng mới, chép, bỏ bảng cũ.
--  Bảng này được chép lại từ registry/domains.yaml mỗi lần khởi động.
-- =============================================================================

CREATE TABLE ctl_domain_form_moi (
    domain_id integer NOT NULL REFERENCES ctl_domain(domain_id) ON DELETE CASCADE,
    form_id   integer NOT NULL UNIQUE REFERENCES ctl_form(form_id) ON DELETE CASCADE,
    thu_tu    integer NOT NULL DEFAULT 1,
    PRIMARY KEY (domain_id, form_id)
);
INSERT INTO ctl_domain_form_moi (domain_id, form_id, thu_tu)
     SELECT domain_id, form_id, 1 FROM ctl_domain_form;
DROP TABLE ctl_domain_form;
ALTER TABLE ctl_domain_form_moi RENAME TO ctl_domain_form;
