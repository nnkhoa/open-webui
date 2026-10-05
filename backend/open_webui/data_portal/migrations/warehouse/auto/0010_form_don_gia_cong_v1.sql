-- ===========================================================================
--  Nâng cấp bảng theo khai báo DON_GIA_CONG
--  TỆP NÀY SINH TỰ ĐỘNG bởi manage.py makemigration. Không sửa bằng tay.
-- ===========================================================================

-- Tạo mới bảng Đơn gia công ngoài (fact_gia_cong) ở cả bốn lớp
-- Đơn gia công ngoài — dữ liệu gốc, y nguyên như tệp
CREATE TABLE bronze.fact_gia_cong (
    row_id                     bigserial   PRIMARY KEY,
    nam                        text,
    ma_dong                    text,
    ky_thang                   text,
    ma_don_vi_gc               text,
    khu_vuc                    text,
    ma_khach                   text,
    ten_khach                  text,
    ma_nhom_kd                 text,
    ma_hang                    text,
    ma_don_hang                text,
    mau                        text,
    so_luong                   text,
    don_gia_gia_cong           text,
    don_gia_chao_hang          text,
    ma_tien_te                 text,
    loai_ban_ghi               text,
    domain_id                  smallint    NOT NULL REFERENCES ctl.domain(domain_id),
    load_id                    bigint      NOT NULL REFERENCES ctl.load(load_id),
    batch_id                   bigint      NOT NULL REFERENCES ctl.batch(batch_id),
    source_sheet               text        NOT NULL,
    source_row                 int         NOT NULL,
    loaded_at                  timestamptz NOT NULL,
    row_hash                   char(64)    NOT NULL,
    UNIQUE (load_id, source_sheet, source_row)
);

CREATE INDEX bronze_fact_gia_cong_batch_idx ON bronze.fact_gia_cong (batch_id);
CREATE INDEX bronze_fact_gia_cong_hash_idx ON bronze.fact_gia_cong (row_hash);

-- Đơn gia công ngoài — đã ép kiểu, có phiên bản theo lô
CREATE TABLE silver.fact_gia_cong (
    fact_gia_cong_sk           bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nam                        bigint,
    ma_dong                    text,
    ky_thang                   text,
    ma_don_vi_gc               text  NOT NULL,
    khu_vuc                    text,
    ma_khach                   text,
    ten_khach                  text,
    ma_nhom_kd                 text,
    ma_hang                    text  NOT NULL,
    ma_don_hang                text,
    mau                        text,
    so_luong                   numeric,
    don_gia_gia_cong           numeric,
    don_gia_chao_hang          numeric,
    ma_tien_te                 text,
    loai_ban_ghi               text,
    domain_id                  smallint    NOT NULL REFERENCES ctl.domain(domain_id),
    load_id                    bigint      NOT NULL REFERENCES ctl.load(load_id),
    batch_id                   bigint      NOT NULL REFERENCES ctl.batch(batch_id),
    bronze_id                  bigint      NOT NULL REFERENCES bronze.fact_gia_cong(row_id),
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
CREATE INDEX silver_fact_gia_cong_bk_idx
    ON silver.fact_gia_cong (domain_id, nam, ma_don_vi_gc, ma_hang) WHERE is_current;
CREATE INDEX silver_fact_gia_cong_batch_idx ON silver.fact_gia_cong (batch_id);
CREATE INDEX silver_fact_gia_cong_bronze_idx ON silver.fact_gia_cong (bronze_id);

-- Đơn gia công ngoài — bản chép lớp chuẩn hoá
CREATE TABLE gold.fact_gia_cong (
    fact_gia_cong_sk           bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nam                        bigint,
    ma_dong                    text,
    ky_thang                   text,
    ma_don_vi_gc               text  NOT NULL,
    khu_vuc                    text,
    ma_khach                   text,
    ten_khach                  text,
    ma_nhom_kd                 text,
    ma_hang                    text  NOT NULL,
    ma_don_hang                text,
    mau                        text,
    so_luong                   numeric,
    don_gia_gia_cong           numeric,
    don_gia_chao_hang          numeric,
    ma_tien_te                 text,
    loai_ban_ghi               text,
    domain_id                  smallint    NOT NULL REFERENCES ctl.domain(domain_id),
    silver_sk                  bigint      NOT NULL REFERENCES silver.fact_gia_cong(fact_gia_cong_sk),
    load_id                    bigint      NOT NULL REFERENCES ctl.load(load_id),
    batch_id                   bigint      NOT NULL REFERENCES ctl.batch(batch_id),
    source_sheet               text        NOT NULL,
    source_row                 int         NOT NULL,
    is_current                 boolean     NOT NULL DEFAULT true
);

CREATE UNIQUE INDEX gold_fact_gia_cong_silver_idx
    ON gold.fact_gia_cong (silver_sk);
CREATE INDEX gold_fact_gia_cong_batch_idx ON gold.fact_gia_cong (batch_id);

-- Đơn gia công ngoài
CREATE VIEW analytics.v_fact_gia_cong AS
    SELECT t.nam,
           t.ma_dong,
           t.ky_thang,
           t.ma_don_vi_gc,
           t.khu_vuc,
           t.ma_khach,
           t.ten_khach,
           t.ma_nhom_kd,
           t.ma_hang,
           t.ma_don_hang,
           t.mau,
           t.so_luong,
           t.don_gia_gia_cong,
           t.don_gia_chao_hang,
           t.ma_tien_te,
           t.loai_ban_ghi,
           t.domain_id,
           t.load_id,
           t.batch_id,
           t.source_sheet,
           t.source_row
      FROM gold.fact_gia_cong t
     WHERE t.is_current;
