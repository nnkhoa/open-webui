-- =============================================================================
--  Sổ tay của portal — SQLite
--
--  Phần portal phải biết **trước khi** có bất kỳ PostgreSQL nào: ai được đăng
--  nhập, có những domain nào, bộ bảng khai ra sao, và kho dữ liệu nằm ở đâu.
--  Nếu những thứ này nằm trong chính kho dữ liệu thì thành vòng luẩn quẩn —
--  không đăng nhập được để mà đi cấu hình kho.
--
--      sổ tay (tệp này)      | kho dữ liệu (PostgreSQL)
--      ----------------------+----------------------------------------------
--      tài khoản, phiên      | bronze / silver / gold / analytics
--      domain, bộ bảng       | ctl.upload, ctl.load, ctl.batch
--      cấu hình kết nối kho  | ctl.recon_result, ctl.dataset
--      nhật ký thao tác      | ctl.schema_migration
--
--  Sổ ghi mỗi lần nạp nằm **cùng bên** với dữ liệu: SQLite và PostgreSQL không
--  chung một giao dịch được, đặt sổ cạnh dữ liệu thì "nạp hết hoặc không" vẫn
--  là một lệnh COMMIT.
--
--  Quy ước kiểu: thời điểm là text ISO-8601 UTC khai kiểu TEXT_TS (đọc ra
--  thành `datetime`), boolean là integer 0/1, mảng và JSON là text chứa JSON.
-- =============================================================================

-- ------------------------------------------------------------ tài khoản ---- --

CREATE TABLE auth_app_user (
    user_id              integer PRIMARY KEY AUTOINCREMENT,
    username             text    NOT NULL UNIQUE
                                 CHECK (username NOT GLOB '*[^a-z0-9._-]*'
                                        AND length(username) BETWEEN 3 AND 50),
    display_name         text    NOT NULL,
    password_hash        text    NOT NULL,
    role                 text    NOT NULL CHECK (role IN ('quan_tri', 'nguoi_nap')),
    is_active            integer NOT NULL DEFAULT 1,
    must_change_password integer NOT NULL DEFAULT 0,
    failed_attempts      integer NOT NULL DEFAULT 0,
    locked_until         TEXT_TS,
    created_at           TEXT_TS NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    created_by           text,
    last_login_at        TEXT_TS
);

-- ---------------------------------------------------- domain và bộ bảng ---- --
--  Chép từ `registry/domains.yaml` và `registry/forms/*.yaml` mỗi lần khởi
--  động. Sổ tay giữ số hiệu ổn định (domain_id, form_id, table_id) để sổ ghi
--  mỗi lần nạp bên kho trỏ vào.

CREATE TABLE ctl_domain (
    domain_id   integer PRIMARY KEY AUTOINCREMENT,
    code        text    NOT NULL UNIQUE
                        CHECK (code NOT GLOB '*[^A-Z0-9-]*' AND length(code) BETWEEN 2 AND 20),
    name        text    NOT NULL,
    description text,
    -- 'suspended': domain đã bỏ khỏi registry/domains.yaml — ẩn, giữ dữ liệu.
    status      text    NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
    created_at  TEXT_TS NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE auth_session (
    token_hash     text    PRIMARY KEY,
    user_id        integer NOT NULL REFERENCES auth_app_user(user_id) ON DELETE CASCADE,
    domain_id_last integer REFERENCES ctl_domain(domain_id) ON DELETE SET NULL,
    csrf_token     text    NOT NULL,
    created_at     TEXT_TS NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    expires_at     TEXT_TS NOT NULL
);
CREATE INDEX auth_session_user_idx ON auth_session (user_id);

CREATE TABLE ctl_form (
    form_id         integer PRIMARY KEY AUTOINCREMENT,
    code            text    NOT NULL UNIQUE,
    label           text    NOT NULL,
    description     text,
    current_version integer NOT NULL,
    yaml_sha256     text    NOT NULL,
    policy          text    NOT NULL DEFAULT '{}'           -- JSON
);

-- Mỗi domain tối đa một bộ bảng, mỗi bộ bảng tối đa một domain.
CREATE TABLE ctl_domain_form (
    domain_id integer PRIMARY KEY REFERENCES ctl_domain(domain_id) ON DELETE CASCADE,
    form_id   integer NOT NULL UNIQUE REFERENCES ctl_form(form_id) ON DELETE CASCADE
);

CREATE TABLE ctl_form_table (
    table_id         integer PRIMARY KEY AUTOINCREMENT,
    form_id          integer NOT NULL REFERENCES ctl_form(form_id) ON DELETE CASCADE,
    name             text    NOT NULL UNIQUE,
    kind             text    NOT NULL CHECK (kind IN ('dim', 'fact')),
    sheet            text    NOT NULL,
    label            text    NOT NULL,
    card_label       text,
    description      text,
    card_description text,
    grain            text,
    business_key     text    NOT NULL DEFAULT '[]',          -- JSON mảng
    merge_strategy   text    NOT NULL,
    partition_by     text    NOT NULL DEFAULT '[]',          -- JSON mảng
    order_by         text    NOT NULL DEFAULT '[]',          -- JSON mảng
    display_order    integer NOT NULL DEFAULT 0
);

CREATE TABLE ctl_form_column (
    table_id        integer NOT NULL REFERENCES ctl_form_table(table_id) ON DELETE CASCADE,
    name            text    NOT NULL,
    ordinal         integer NOT NULL,
    type            text    NOT NULL,
    required        integer NOT NULL DEFAULT 0,
    is_business_key integer NOT NULL DEFAULT 0,
    label           text    NOT NULL,
    meaning         text    NOT NULL,
    how             text,
    example         text,
    enum_values     text,                                    -- JSON mảng
    role            text,
    display_width   integer,
    show_in_table   integer NOT NULL DEFAULT 1,
    PRIMARY KEY (table_id, name)
);

-- ------------------------------------------------------- kết nối kho ---- --
--  Đúng một dòng, sửa ở màn Quản trị ▸ Cấu hình database.

CREATE TABLE ctl_ket_noi_kho (
    id             integer PRIMARY KEY CHECK (id = 1),
    host           text    NOT NULL,
    port           integer NOT NULL DEFAULT 5432,
    database       text    NOT NULL,
    username       text    NOT NULL,
    password       text    NOT NULL DEFAULT '',
    sslmode        text    NOT NULL DEFAULT 'prefer',
    ghi_chu        text,
    -- Kết quả lần bấm "Kiểm tra kết nối" gần nhất.
    thu_luc        TEXT_TS,
    thu_dat        integer,
    thu_thong_diep text,
    cap_nhat_luc   TEXT_TS NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    cap_nhat_boi   text
);

-- ------------------------------------------------------ nhật ký thao tác ---- --

CREATE TABLE ctl_audit_event (
    event_id       integer PRIMARY KEY AUTOINCREMENT,
    at             TEXT_TS NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    actor_user_id  integer,
    actor_username text,
    domain_id      integer,
    action         text    NOT NULL,
    object_type    text,
    object_id      text,
    request_id     text,
    ip             text,
    user_agent     text,
    detail         text                                      -- JSON
);
CREATE INDEX ctl_audit_event_at_idx ON ctl_audit_event (at DESC);
