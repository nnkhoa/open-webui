-- ===========================================================================
--  Nâng cấp bảng theo khai báo LICH_MAY_MAU
--  TỆP NÀY SINH TỰ ĐỘNG bởi lệnh manage makemigration. Không sửa bằng tay.
-- ===========================================================================

-- Tạo mới bảng May mẫu chào hàng (fact_may_mau) ở cả bốn lớp
-- May mẫu chào hàng — dữ liệu gốc, y nguyên như tệp
CREATE TABLE bronze.fact_may_mau (
    row_id                     bigserial   PRIMARY KEY,
    nam                        text,
    ma_khach                   text,
    doi_tuong                  text,
    sample                     text,
    description                text,
    ma_nhom_kd                 text,
    so_luong                   text,
    don_gia                    text,
    domain_id                  smallint    NOT NULL REFERENCES ctl.domain(domain_id),
    load_id                    bigint      NOT NULL REFERENCES ctl.load(load_id),
    batch_id                   bigint      NOT NULL REFERENCES ctl.batch(batch_id),
    source_sheet               text        NOT NULL,
    source_row                 int         NOT NULL,
    loaded_at                  timestamptz NOT NULL,
    row_hash                   char(64)    NOT NULL,
    UNIQUE (load_id, source_sheet, source_row)
);

CREATE INDEX bronze_fact_may_mau_batch_idx ON bronze.fact_may_mau (batch_id);
CREATE INDEX bronze_fact_may_mau_hash_idx ON bronze.fact_may_mau (row_hash);

-- May mẫu chào hàng — đã ép kiểu, có phiên bản theo lô
CREATE TABLE silver.fact_may_mau (
    fact_may_mau_sk            bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nam                        bigint,
    ma_khach                   text  NOT NULL,
    doi_tuong                  text,
    sample                     text,
    description                text,
    ma_nhom_kd                 text,
    so_luong                   numeric,
    don_gia                    numeric,
    domain_id                  smallint    NOT NULL REFERENCES ctl.domain(domain_id),
    load_id                    bigint      NOT NULL REFERENCES ctl.load(load_id),
    batch_id                   bigint      NOT NULL REFERENCES ctl.batch(batch_id),
    bronze_id                  bigint      NOT NULL REFERENCES bronze.fact_may_mau(row_id),
    source_sheet               text        NOT NULL,
    source_row                 int         NOT NULL,
    row_hash                   char(64)    NOT NULL,
    valid_from                 timestamptz NOT NULL,
    valid_to                   timestamptz,
    is_current                 boolean     NOT NULL DEFAULT true,
    superseded_by_batch_id     bigint      REFERENCES ctl.batch(batch_id),
    supersedes_sk              bigint
);

-- Khoá nghiệp vụ dùng để tra cứu, **không** duy nhất: một dòng trong tệp
-- là một dòng ở đây, kể cả khi cột khoá để trống nên hai dòng trùng khoá.
CREATE INDEX silver_fact_may_mau_bk_idx
    ON silver.fact_may_mau (domain_id, nam, ma_khach, coalesce(sample, '')) WHERE is_current;
CREATE INDEX silver_fact_may_mau_batch_idx ON silver.fact_may_mau (batch_id);
CREATE INDEX silver_fact_may_mau_bronze_idx ON silver.fact_may_mau (bronze_id);

-- May mẫu chào hàng — bản chép lớp chuẩn hoá
CREATE TABLE gold.fact_may_mau (
    fact_may_mau_sk            bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nam                        bigint,
    ma_khach                   text  NOT NULL,
    doi_tuong                  text,
    sample                     text,
    description                text,
    ma_nhom_kd                 text,
    so_luong                   numeric,
    don_gia                    numeric,
    domain_id                  smallint    NOT NULL REFERENCES ctl.domain(domain_id),
    silver_sk                  bigint      NOT NULL REFERENCES silver.fact_may_mau(fact_may_mau_sk),
    load_id                    bigint      NOT NULL REFERENCES ctl.load(load_id),
    batch_id                   bigint      NOT NULL REFERENCES ctl.batch(batch_id),
    source_sheet               text        NOT NULL,
    source_row                 int         NOT NULL,
    is_current                 boolean     NOT NULL DEFAULT true
);

CREATE UNIQUE INDEX gold_fact_may_mau_silver_idx
    ON gold.fact_may_mau (silver_sk);
CREATE INDEX gold_fact_may_mau_batch_idx ON gold.fact_may_mau (batch_id);

-- May mẫu chào hàng
CREATE VIEW analytics.v_fact_may_mau AS
    SELECT t.nam,
           t.ma_khach,
           t.doi_tuong,
           t.sample,
           t.description,
           t.ma_nhom_kd,
           t.so_luong,
           t.don_gia,
           t.domain_id,
           t.load_id,
           t.batch_id,
           t.source_sheet,
           t.source_row
      FROM gold.fact_may_mau t
     WHERE t.is_current;
