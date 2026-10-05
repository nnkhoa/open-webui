-- =============================================================================
--  Lược đồ nền của kho dữ liệu
--
--  ctl        sổ đăng ký (bản chiếu từ sổ tay) và sổ ghi mỗi lần nạp
--  bronze     dữ liệu gốc, văn bản y như tệp          ┐
--  silver     dữ liệu chuẩn hoá, đã đổi kiểu           ├ bảng sinh từ khai báo
--  gold       mô hình sao phục vụ phân tích            ┘ bộ bảng (auto/)
--  analytics  view chỉ đọc cho công cụ BI / semantic layer
--
--  Bảng của từng bộ bảng không viết tay ở đây: `manage.py makemigration` sinh
--  chúng vào `auto/` từ `registry/forms/*.yaml`.
-- =============================================================================

CREATE SCHEMA ctl;
CREATE SCHEMA bronze;
CREATE SCHEMA silver;
CREATE SCHEMA gold;
CREATE SCHEMA analytics;

-- ------------------------------------------------ sổ phiên bản lược đồ ---- --

CREATE TABLE ctl.schema_migration (
    version     int         PRIMARY KEY,
    name        text        NOT NULL,
    checksum    char(64)    NOT NULL,
    source      text        NOT NULL CHECK (source IN ('manual', 'generated')),
    applied_at  timestamptz NOT NULL DEFAULT now(),
    applied_by  text,
    duration_ms int
);

-- ---------------------------------------- domain và bộ bảng (bản chiếu) ---- --
--  Nguồn chuẩn là sổ tay SQLite; các bảng dưới đây chép nguyên số hiệu từ đó
--  để sổ ghi mỗi lần nạp có chỗ trỏ vào. Không sửa thẳng ở đây.

CREATE TABLE ctl.domain (
    domain_id   smallint PRIMARY KEY,
    code        text     NOT NULL UNIQUE,
    name        text     NOT NULL,
    description text,
    status      text     NOT NULL CHECK (status IN ('active', 'suspended'))
);

CREATE TABLE ctl.form (
    form_id         smallint PRIMARY KEY,
    code            text     NOT NULL UNIQUE,
    label           text     NOT NULL,
    description     text,
    current_version int      NOT NULL,
    yaml_sha256     char(64) NOT NULL,
    policy          jsonb    NOT NULL DEFAULT '{}'
);

CREATE TABLE ctl.domain_form (
    domain_id smallint PRIMARY KEY REFERENCES ctl.domain(domain_id) ON DELETE CASCADE,
    form_id   smallint NOT NULL UNIQUE REFERENCES ctl.form(form_id) ON DELETE CASCADE
);

CREATE TABLE ctl.form_table (
    table_id         smallint PRIMARY KEY,
    form_id          smallint NOT NULL REFERENCES ctl.form(form_id) ON DELETE CASCADE,
    name             text     NOT NULL UNIQUE,
    kind             text     NOT NULL CHECK (kind IN ('dim', 'fact')),
    sheet            text     NOT NULL,
    label            text     NOT NULL,
    card_label       text,
    description      text,
    card_description text,
    grain            text,
    business_key     text[]   NOT NULL DEFAULT '{}',
    merge_strategy   text     NOT NULL,
    partition_by     text[]   NOT NULL DEFAULT '{}',
    order_by         text[]   NOT NULL DEFAULT '{}',
    display_order    int      NOT NULL DEFAULT 0
);

CREATE TABLE ctl.form_column (
    table_id        smallint NOT NULL REFERENCES ctl.form_table(table_id) ON DELETE CASCADE,
    name            text     NOT NULL,
    ordinal         int      NOT NULL,
    type            text     NOT NULL,
    required        boolean  NOT NULL DEFAULT false,
    is_business_key boolean  NOT NULL DEFAULT false,
    label           text     NOT NULL,
    meaning         text     NOT NULL,
    how             text,
    example         text,
    enum_values     text[],
    role            text,
    display_width   int,
    show_in_table   boolean  NOT NULL DEFAULT true,
    PRIMARY KEY (table_id, name)
);

-- Mỗi (domain, bảng) là một bộ dữ liệu hiện ở màn Dữ liệu.
CREATE TABLE ctl.dataset (
    dataset_id    serial   PRIMARY KEY,
    domain_id     smallint NOT NULL REFERENCES ctl.domain(domain_id) ON DELETE CASCADE,
    table_id      smallint NOT NULL REFERENCES ctl.form_table(table_id) ON DELETE CASCADE,
    label         text     NOT NULL,
    description   text,
    is_visible    boolean  NOT NULL DEFAULT true,
    display_order int      NOT NULL DEFAULT 0,
    UNIQUE (domain_id, table_id)
);

-- ------------------------------------------------------ sổ ghi lần nạp ---- --

CREATE TABLE ctl.upload (
    upload_id            bigserial   PRIMARY KEY,
    domain_id            smallint    NOT NULL REFERENCES ctl.domain(domain_id),
    form_id              smallint    NOT NULL REFERENCES ctl.form(form_id),
    file_name            text        NOT NULL,
    file_sha256          char(64)    NOT NULL,
    size_bytes           bigint      NOT NULL,
    storage_uri          text        NOT NULL,
    uploaded_at          timestamptz NOT NULL DEFAULT now(),
    uploaded_by          bigint,
    uploaded_by_username text                     -- chép từ sổ tay lúc ghi
);
CREATE INDEX upload_sha_idx ON ctl.upload (domain_id, form_id, file_sha256);

CREATE TABLE ctl.load (
    load_id             bigserial   PRIMARY KEY,
    upload_id           bigint      NOT NULL REFERENCES ctl.upload(upload_id),
    domain_id           smallint    NOT NULL REFERENCES ctl.domain(domain_id),
    form_id             smallint    NOT NULL REFERENCES ctl.form(form_id),
    form_version        int         NOT NULL,
    batch_id            bigint,                   -- khoá ngoại thêm sau ctl.batch
    status              text        NOT NULL
                        CHECK (status IN ('running', 'success', 'rejected',
                                          'mismatch', 'rolled_back')),
    rows_read           int         NOT NULL DEFAULT 0,
    rows_written        int         NOT NULL DEFAULT 0,
    sheets_count        int         NOT NULL DEFAULT 0,
    started_at          timestamptz NOT NULL DEFAULT now(),
    finished_at         timestamptz,
    duration_ms         int,
    actor_user_id       bigint,
    actor_username      text,                     -- chép từ sổ tay lúc ghi
    request_id          text,
    message             text,
    errors              jsonb,                    -- lỗi làm tệp bị từ chối
    report              jsonb                     -- số dòng theo bảng, kỳ bị chạm tới
);
CREATE INDEX load_domain_time_idx ON ctl.load (domain_id, started_at DESC);
CREATE INDEX load_status_idx ON ctl.load (status);

-- Một lô = dữ liệu một lần nạp ghi vào silver/gold. Lô bị thay hoặc gỡ thì
-- đổi trạng thái, dòng của nó hết hiệu lực nhưng vẫn còn để truy vết.
CREATE TABLE ctl.batch (
    batch_id  bigserial   PRIMARY KEY,
    load_id   bigint      NOT NULL,
    domain_id smallint    NOT NULL REFERENCES ctl.domain(domain_id),
    form_id   smallint    NOT NULL REFERENCES ctl.form(form_id),
    state     text        NOT NULL DEFAULT 'open'
              CHECK (state IN ('open', 'current', 'superseded', 'rolled_back')),
    opened_at timestamptz NOT NULL DEFAULT now(),
    closed_at timestamptz
);
CREATE INDEX batch_domain_state_idx ON ctl.batch (domain_id, state);
-- ctl.load và ctl.batch trỏ vòng vào nhau; kiểm tra lúc COMMIT.
ALTER TABLE ctl.batch ADD CONSTRAINT batch_load_fk
    FOREIGN KEY (load_id) REFERENCES ctl.load(load_id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE ctl.load ADD CONSTRAINT load_batch_fk
    FOREIGN KEY (batch_id) REFERENCES ctl.batch(batch_id);

-- Kỳ nào một lô chạm tới — nguồn của bộ lọc Kỳ và của việc thay theo kỳ.
CREATE TABLE ctl.batch_partition (
    batch_id        bigint   NOT NULL REFERENCES ctl.batch(batch_id) ON DELETE CASCADE,
    table_id        smallint NOT NULL REFERENCES ctl.form_table(table_id),
    partition_key   text     NOT NULL,
    rows_written    int      NOT NULL DEFAULT 0,
    rows_superseded int      NOT NULL DEFAULT 0,
    sum_control     jsonb    NOT NULL DEFAULT '{}',
    PRIMARY KEY (batch_id, table_id, partition_key)
);

-- Kết quả đối chiếu R1–R4 của từng bảng trong từng lần nạp.
CREATE TABLE ctl.recon_result (
    load_id  bigint   NOT NULL REFERENCES ctl.load(load_id) ON DELETE CASCADE,
    step     text     NOT NULL CHECK (step IN ('R1', 'R2', 'R3', 'R4a', 'R4c')),
    table_id smallint NOT NULL,
    metric   text     NOT NULL,
    expected numeric,
    actual   numeric,
    diff     numeric,
    passed   boolean  NOT NULL,
    detail   jsonb,
    PRIMARY KEY (load_id, step, table_id, metric)
);

-- -------------------------------------------------------- tầng phục vụ ---- --

-- Có dữ liệu gì: mỗi domain có những bảng nào.
CREATE VIEW analytics.v_data_inventory AS
    SELECT d.domain_id, d.code AS domain_code, d.name AS domain_name,
           ft.table_id, ft.name AS table_name, ft.label AS table_label, ft.kind,
           ds.display_order
      FROM ctl.dataset ds
      JOIN ctl.domain d      ON d.domain_id = ds.domain_id
      JOIN ctl.form_table ft ON ft.table_id = ds.table_id
     WHERE ds.is_visible AND d.status = 'active';

-- Vai trò chỉ đọc cho công cụ BI / semantic layer — chỉ thấy schema analytics.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ai_reader') THEN
        CREATE ROLE ai_reader NOLOGIN;
    END IF;
END $$;
GRANT USAGE ON SCHEMA analytics TO ai_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO ai_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA analytics GRANT SELECT ON TABLES TO ai_reader;
