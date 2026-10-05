-- ===========================================================================
--  Nâng cấp bảng theo khai báo BAO_CAO_HQKH
--  TỆP NÀY SINH TỰ ĐỘNG bởi manage.py makemigration. Không sửa bằng tay.
-- ===========================================================================

-- Tạo mới bảng Danh mục khách hàng (dim_khach_hang) ở cả bốn lớp
-- Danh mục khách hàng — dữ liệu gốc, y nguyên như tệp
CREATE TABLE bronze.dim_khach_hang (
    row_id                     bigserial   PRIMARY KEY,
    ma_khach                   text,
    ten_khach                  text,
    domain_id                  smallint    NOT NULL REFERENCES ctl.domain(domain_id),
    load_id                    bigint      NOT NULL REFERENCES ctl.load(load_id),
    batch_id                   bigint      NOT NULL REFERENCES ctl.batch(batch_id),
    source_sheet               text        NOT NULL,
    source_row                 int         NOT NULL,
    loaded_at                  timestamptz NOT NULL,
    row_hash                   char(64)    NOT NULL,
    UNIQUE (load_id, source_sheet, source_row)
);

CREATE INDEX bronze_dim_khach_hang_batch_idx ON bronze.dim_khach_hang (batch_id);
CREATE INDEX bronze_dim_khach_hang_hash_idx ON bronze.dim_khach_hang (row_hash);

-- Danh mục khách hàng — đã ép kiểu, có phiên bản theo lô
CREATE TABLE silver.dim_khach_hang (
    dim_khach_hang_sk          bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_khach                   text,
    ten_khach                  text,
    domain_id                  smallint    NOT NULL REFERENCES ctl.domain(domain_id),
    load_id                    bigint      NOT NULL REFERENCES ctl.load(load_id),
    batch_id                   bigint      NOT NULL REFERENCES ctl.batch(batch_id),
    bronze_id                  bigint      NOT NULL REFERENCES bronze.dim_khach_hang(row_id),
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
CREATE INDEX silver_dim_khach_hang_bk_idx
    ON silver.dim_khach_hang (domain_id, coalesce(ma_khach, '')) WHERE is_current;
CREATE INDEX silver_dim_khach_hang_batch_idx ON silver.dim_khach_hang (batch_id);
CREATE INDEX silver_dim_khach_hang_bronze_idx ON silver.dim_khach_hang (bronze_id);

-- Danh mục khách hàng — bản chép lớp chuẩn hoá
CREATE TABLE gold.dim_khach_hang (
    dim_khach_hang_sk          bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_khach                   text,
    ten_khach                  text,
    domain_id                  smallint    NOT NULL REFERENCES ctl.domain(domain_id),
    silver_sk                  bigint      NOT NULL REFERENCES silver.dim_khach_hang(dim_khach_hang_sk),
    load_id                    bigint      NOT NULL REFERENCES ctl.load(load_id),
    batch_id                   bigint      NOT NULL REFERENCES ctl.batch(batch_id),
    source_sheet               text        NOT NULL,
    source_row                 int         NOT NULL,
    is_current                 boolean     NOT NULL DEFAULT true
);

CREATE UNIQUE INDEX gold_dim_khach_hang_silver_idx
    ON gold.dim_khach_hang (silver_sk);
CREATE INDEX gold_dim_khach_hang_batch_idx ON gold.dim_khach_hang (batch_id);

-- Danh mục khách hàng
CREATE VIEW analytics.v_dim_khach_hang AS
    SELECT t.ma_khach,
           t.ten_khach,
           t.domain_id,
           t.load_id,
           t.batch_id,
           t.source_sheet,
           t.source_row
      FROM gold.dim_khach_hang t
     WHERE t.is_current;

-- Tạo mới bảng Danh mục khoản chi phí (dim_khoan_cp) ở cả bốn lớp
-- Danh mục khoản chi phí — dữ liệu gốc, y nguyên như tệp
CREATE TABLE bronze.dim_khoan_cp (
    row_id                     bigserial   PRIMARY KEY,
    ma_khoan_cp                text,
    ten_khoan                  text,
    domain_id                  smallint    NOT NULL REFERENCES ctl.domain(domain_id),
    load_id                    bigint      NOT NULL REFERENCES ctl.load(load_id),
    batch_id                   bigint      NOT NULL REFERENCES ctl.batch(batch_id),
    source_sheet               text        NOT NULL,
    source_row                 int         NOT NULL,
    loaded_at                  timestamptz NOT NULL,
    row_hash                   char(64)    NOT NULL,
    UNIQUE (load_id, source_sheet, source_row)
);

CREATE INDEX bronze_dim_khoan_cp_batch_idx ON bronze.dim_khoan_cp (batch_id);
CREATE INDEX bronze_dim_khoan_cp_hash_idx ON bronze.dim_khoan_cp (row_hash);

-- Danh mục khoản chi phí — đã ép kiểu, có phiên bản theo lô
CREATE TABLE silver.dim_khoan_cp (
    dim_khoan_cp_sk            bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_khoan_cp                text,
    ten_khoan                  text,
    domain_id                  smallint    NOT NULL REFERENCES ctl.domain(domain_id),
    load_id                    bigint      NOT NULL REFERENCES ctl.load(load_id),
    batch_id                   bigint      NOT NULL REFERENCES ctl.batch(batch_id),
    bronze_id                  bigint      NOT NULL REFERENCES bronze.dim_khoan_cp(row_id),
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
CREATE INDEX silver_dim_khoan_cp_bk_idx
    ON silver.dim_khoan_cp (domain_id, coalesce(ma_khoan_cp, '')) WHERE is_current;
CREATE INDEX silver_dim_khoan_cp_batch_idx ON silver.dim_khoan_cp (batch_id);
CREATE INDEX silver_dim_khoan_cp_bronze_idx ON silver.dim_khoan_cp (bronze_id);

-- Danh mục khoản chi phí — bản chép lớp chuẩn hoá
CREATE TABLE gold.dim_khoan_cp (
    dim_khoan_cp_sk            bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_khoan_cp                text,
    ten_khoan                  text,
    domain_id                  smallint    NOT NULL REFERENCES ctl.domain(domain_id),
    silver_sk                  bigint      NOT NULL REFERENCES silver.dim_khoan_cp(dim_khoan_cp_sk),
    load_id                    bigint      NOT NULL REFERENCES ctl.load(load_id),
    batch_id                   bigint      NOT NULL REFERENCES ctl.batch(batch_id),
    source_sheet               text        NOT NULL,
    source_row                 int         NOT NULL,
    is_current                 boolean     NOT NULL DEFAULT true
);

CREATE UNIQUE INDEX gold_dim_khoan_cp_silver_idx
    ON gold.dim_khoan_cp (silver_sk);
CREATE INDEX gold_dim_khoan_cp_batch_idx ON gold.dim_khoan_cp (batch_id);

-- Danh mục khoản chi phí
CREATE VIEW analytics.v_dim_khoan_cp AS
    SELECT t.ma_khoan_cp,
           t.ten_khoan,
           t.domain_id,
           t.load_id,
           t.batch_id,
           t.source_sheet,
           t.source_row
      FROM gold.dim_khoan_cp t
     WHERE t.is_current;

-- Tạo mới bảng Kết quả kinh doanh (fact_ket_qua_kd) ở cả bốn lớp
-- Kết quả kinh doanh — dữ liệu gốc, y nguyên như tệp
CREATE TABLE bronze.fact_ket_qua_kd (
    row_id                     bigserial   PRIMARY KEY,
    ky_thang                   text,
    ma_khach                   text,
    ma_nhom_kd                 text,
    doanh_thu                  text,
    gia_von                    text,
    lai_rong                   text,
    lai_gop                    text,
    ty_le_lai_gop              text,
    ty_le_lai_rong_dt          text,
    ty_le_lai_tren_von         text,
    ty_trong_dt                text,
    ty_trong_lai_rong          text,
    chenh_gop_rong             text,
    domain_id                  smallint    NOT NULL REFERENCES ctl.domain(domain_id),
    load_id                    bigint      NOT NULL REFERENCES ctl.load(load_id),
    batch_id                   bigint      NOT NULL REFERENCES ctl.batch(batch_id),
    source_sheet               text        NOT NULL,
    source_row                 int         NOT NULL,
    loaded_at                  timestamptz NOT NULL,
    row_hash                   char(64)    NOT NULL,
    UNIQUE (load_id, source_sheet, source_row)
);

CREATE INDEX bronze_fact_ket_qua_kd_batch_idx ON bronze.fact_ket_qua_kd (batch_id);
CREATE INDEX bronze_fact_ket_qua_kd_hash_idx ON bronze.fact_ket_qua_kd (row_hash);

-- Kết quả kinh doanh — đã ép kiểu, có phiên bản theo lô
CREATE TABLE silver.fact_ket_qua_kd (
    fact_ket_qua_kd_sk         bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ky_thang                   bigint,
    ma_khach                   text,
    ma_nhom_kd                 text,
    doanh_thu                  numeric,
    gia_von                    numeric,
    lai_rong                   numeric,
    lai_gop                    numeric,
    ty_le_lai_gop              numeric,
    ty_le_lai_rong_dt          numeric,
    ty_le_lai_tren_von         numeric,
    ty_trong_dt                numeric,
    ty_trong_lai_rong          numeric,
    chenh_gop_rong             numeric,
    domain_id                  smallint    NOT NULL REFERENCES ctl.domain(domain_id),
    load_id                    bigint      NOT NULL REFERENCES ctl.load(load_id),
    batch_id                   bigint      NOT NULL REFERENCES ctl.batch(batch_id),
    bronze_id                  bigint      NOT NULL REFERENCES bronze.fact_ket_qua_kd(row_id),
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
CREATE INDEX silver_fact_ket_qua_kd_bk_idx
    ON silver.fact_ket_qua_kd (domain_id, ky_thang, coalesce(ma_khach, ''), coalesce(ma_nhom_kd, '')) WHERE is_current;
CREATE INDEX silver_fact_ket_qua_kd_batch_idx ON silver.fact_ket_qua_kd (batch_id);
CREATE INDEX silver_fact_ket_qua_kd_bronze_idx ON silver.fact_ket_qua_kd (bronze_id);
CREATE INDEX silver_fact_ket_qua_kd_part_idx
    ON silver.fact_ket_qua_kd (domain_id, ky_thang) WHERE is_current;

-- Kết quả kinh doanh — bản chép lớp chuẩn hoá
CREATE TABLE gold.fact_ket_qua_kd (
    fact_ket_qua_kd_sk         bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ky_thang                   bigint,
    ma_khach                   text,
    ma_nhom_kd                 text,
    doanh_thu                  numeric,
    gia_von                    numeric,
    lai_rong                   numeric,
    lai_gop                    numeric,
    ty_le_lai_gop              numeric,
    ty_le_lai_rong_dt          numeric,
    ty_le_lai_tren_von         numeric,
    ty_trong_dt                numeric,
    ty_trong_lai_rong          numeric,
    chenh_gop_rong             numeric,
    domain_id                  smallint    NOT NULL REFERENCES ctl.domain(domain_id),
    silver_sk                  bigint      NOT NULL REFERENCES silver.fact_ket_qua_kd(fact_ket_qua_kd_sk),
    load_id                    bigint      NOT NULL REFERENCES ctl.load(load_id),
    batch_id                   bigint      NOT NULL REFERENCES ctl.batch(batch_id),
    source_sheet               text        NOT NULL,
    source_row                 int         NOT NULL,
    is_current                 boolean     NOT NULL DEFAULT true
);

CREATE UNIQUE INDEX gold_fact_ket_qua_kd_silver_idx
    ON gold.fact_ket_qua_kd (silver_sk);
CREATE INDEX gold_fact_ket_qua_kd_batch_idx ON gold.fact_ket_qua_kd (batch_id);
CREATE INDEX gold_fact_ket_qua_kd_part_idx
    ON gold.fact_ket_qua_kd (domain_id, ky_thang) WHERE is_current;

-- Kết quả kinh doanh
CREATE VIEW analytics.v_fact_ket_qua_kd AS
    SELECT t.ky_thang,
           t.ma_khach,
           t.ma_nhom_kd,
           t.doanh_thu,
           t.gia_von,
           t.lai_rong,
           t.lai_gop,
           t.ty_le_lai_gop,
           t.ty_le_lai_rong_dt,
           t.ty_le_lai_tren_von,
           t.ty_trong_dt,
           t.ty_trong_lai_rong,
           t.chenh_gop_rong,
           t.domain_id,
           t.load_id,
           t.batch_id,
           t.source_sheet,
           t.source_row
      FROM gold.fact_ket_qua_kd t
     WHERE t.is_current;

-- Tạo mới bảng Chi phí (fact_chi_phi) ở cả bốn lớp
-- Chi phí — dữ liệu gốc, y nguyên như tệp
CREATE TABLE bronze.fact_chi_phi (
    row_id                     bigserial   PRIMARY KEY,
    ky_thang                   text,
    ma_khoan_cp                text,
    cap_phan_bo                text,
    ma_khach                   text,
    ma_nhom_kd                 text,
    so_tien                    text,
    domain_id                  smallint    NOT NULL REFERENCES ctl.domain(domain_id),
    load_id                    bigint      NOT NULL REFERENCES ctl.load(load_id),
    batch_id                   bigint      NOT NULL REFERENCES ctl.batch(batch_id),
    source_sheet               text        NOT NULL,
    source_row                 int         NOT NULL,
    loaded_at                  timestamptz NOT NULL,
    row_hash                   char(64)    NOT NULL,
    UNIQUE (load_id, source_sheet, source_row)
);

CREATE INDEX bronze_fact_chi_phi_batch_idx ON bronze.fact_chi_phi (batch_id);
CREATE INDEX bronze_fact_chi_phi_hash_idx ON bronze.fact_chi_phi (row_hash);

-- Chi phí — đã ép kiểu, có phiên bản theo lô
CREATE TABLE silver.fact_chi_phi (
    fact_chi_phi_sk            bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ky_thang                   bigint,
    ma_khoan_cp                text,
    cap_phan_bo                text,
    ma_khach                   text,
    ma_nhom_kd                 text,
    so_tien                    numeric,
    domain_id                  smallint    NOT NULL REFERENCES ctl.domain(domain_id),
    load_id                    bigint      NOT NULL REFERENCES ctl.load(load_id),
    batch_id                   bigint      NOT NULL REFERENCES ctl.batch(batch_id),
    bronze_id                  bigint      NOT NULL REFERENCES bronze.fact_chi_phi(row_id),
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
CREATE INDEX silver_fact_chi_phi_bk_idx
    ON silver.fact_chi_phi (domain_id, ky_thang, coalesce(ma_khoan_cp, ''), coalesce(ma_khach, ''), coalesce(ma_nhom_kd, '')) WHERE is_current;
CREATE INDEX silver_fact_chi_phi_batch_idx ON silver.fact_chi_phi (batch_id);
CREATE INDEX silver_fact_chi_phi_bronze_idx ON silver.fact_chi_phi (bronze_id);
CREATE INDEX silver_fact_chi_phi_part_idx
    ON silver.fact_chi_phi (domain_id, ky_thang) WHERE is_current;

-- Chi phí — bản chép lớp chuẩn hoá
CREATE TABLE gold.fact_chi_phi (
    fact_chi_phi_sk            bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ky_thang                   bigint,
    ma_khoan_cp                text,
    cap_phan_bo                text,
    ma_khach                   text,
    ma_nhom_kd                 text,
    so_tien                    numeric,
    domain_id                  smallint    NOT NULL REFERENCES ctl.domain(domain_id),
    silver_sk                  bigint      NOT NULL REFERENCES silver.fact_chi_phi(fact_chi_phi_sk),
    load_id                    bigint      NOT NULL REFERENCES ctl.load(load_id),
    batch_id                   bigint      NOT NULL REFERENCES ctl.batch(batch_id),
    source_sheet               text        NOT NULL,
    source_row                 int         NOT NULL,
    is_current                 boolean     NOT NULL DEFAULT true
);

CREATE UNIQUE INDEX gold_fact_chi_phi_silver_idx
    ON gold.fact_chi_phi (silver_sk);
CREATE INDEX gold_fact_chi_phi_batch_idx ON gold.fact_chi_phi (batch_id);
CREATE INDEX gold_fact_chi_phi_part_idx
    ON gold.fact_chi_phi (domain_id, ky_thang) WHERE is_current;

-- Chi phí
CREATE VIEW analytics.v_fact_chi_phi AS
    SELECT t.ky_thang,
           t.ma_khoan_cp,
           t.cap_phan_bo,
           t.ma_khach,
           t.ma_nhom_kd,
           t.so_tien,
           t.domain_id,
           t.load_id,
           t.batch_id,
           t.source_sheet,
           t.source_row
      FROM gold.fact_chi_phi t
     WHERE t.is_current;
