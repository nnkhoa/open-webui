-- =============================================================================
--  Danh mục khách hàng theo hợp đồng xuất
--
--  Từ BAO_CAO_HQKH v5, khoá của dim_khach_hang là (ma_khach, hop_dong_xuat): mỗi
--  dòng một cặp mã khách – hợp đồng. Dòng nạp bằng phiên bản trước chưa có hợp
--  đồng, khoá cũ chỉ là ma_khach nên lần nạp mới không thay được chúng. Thôi
--  hiệu lực các dòng đó; nạp lại tệp BAO_CAO_HQKH sau khi chạy migrate.
-- =============================================================================

UPDATE silver.dim_khach_hang s
   SET is_current = false,
       valid_to   = now()
  FROM ctl.load l
 WHERE l.load_id = s.load_id
   AND l.form_version < 5
   AND s.is_current;

UPDATE gold.dim_khach_hang g
   SET is_current = false
  FROM ctl.load l
 WHERE l.load_id = g.load_id
   AND l.form_version < 5
   AND g.is_current;
