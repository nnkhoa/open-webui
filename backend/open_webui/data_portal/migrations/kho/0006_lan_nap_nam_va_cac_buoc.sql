-- =============================================================================
--  Lần nạp ghi thêm năm dữ liệu, kết quả kiểm tra, các bước và thẻ đối chiếu
--
--  Phục vụ API JSON của Data Portal trong Open WebUI (đặc tả mục 9, 17, 18):
--
--    nam        Năm dữ liệu chọn lúc nạp (QT-02). Lần nạp cũ từ trước khi có ô
--               Năm để trống.
--    kiem_tra   kết quả bước Kiểm tra tệp (A1–A3): số dòng đọc được, thiếu giá
--               trị bắt buộc, dòng trùng sẽ bỏ, ô để trống, tổng tiền / số lượng.
--    cac_buoc   các bước A1–A5, B1–B5, mỗi bước một dòng kết quả và kết luận.
--    doi_chieu  dữ liệu các thẻ "Đối chiếu tệp gốc ↔ database", tính trong giao
--               dịch ghi — giữ được cả khi giao dịch bị huỷ vì lệch.
-- =============================================================================

ALTER TABLE ctl.load ADD COLUMN nam       smallint;
ALTER TABLE ctl.load ADD COLUMN kiem_tra  jsonb;
ALTER TABLE ctl.load ADD COLUMN cac_buoc  jsonb;
ALTER TABLE ctl.load ADD COLUMN doi_chieu jsonb;

CREATE INDEX load_domain_nam_idx ON ctl.load (domain_id, nam);
