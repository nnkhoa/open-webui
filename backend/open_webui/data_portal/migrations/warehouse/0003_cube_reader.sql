-- =============================================================================
--  Tài khoản đăng nhập cho semantic layer (Cube)
--
--  `ai_reader` (0001) là vai trò NOLOGIN, chỉ đọc schema analytics. Cube cần
--  một tài khoản đăng nhập được, nên tạo `cube_reader` thừa hưởng `ai_reader`.
--
--  Mật khẩu không ghi ở đây. Đặt một lần sau khi migrate:
--      ALTER ROLE cube_reader PASSWORD '...';
--  rồi điền cùng giá trị vào CUBE_DB_PASS ở .env.
-- =============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cube_reader') THEN
        CREATE ROLE cube_reader LOGIN INHERIT IN ROLE ai_reader;
    END IF;
END $$;
