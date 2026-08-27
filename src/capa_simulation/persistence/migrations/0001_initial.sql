CREATE SCHEMA IF NOT EXISTS app_meta;
CREATE SCHEMA IF NOT EXISTS raw_data;
CREATE SCHEMA IF NOT EXISTS ref_data;
CREATE SCHEMA IF NOT EXISTS rev_data;
CREATE SCHEMA IF NOT EXISTS result_data;

CREATE TABLE IF NOT EXISTS app_meta.schema_migration (
    version INTEGER PRIMARY KEY,
    name VARCHAR NOT NULL,
    checksum VARCHAR NOT NULL,
    applied_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS app_meta.scenario (
    scenario_id VARCHAR PRIMARY KEY,
    scenario_name VARCHAR NOT NULL,
    source_simulation_code VARCHAR NOT NULL,
    source_simulation_name VARCHAR NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'ARCHIVED')),
    active_revision_id VARCHAR,
    created_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS app_meta.dataset (
    dataset_id VARCHAR PRIMARY KEY,
    scenario_id VARCHAR NOT NULL UNIQUE,
    source_type VARCHAR NOT NULL,
    source_registered_at TIMESTAMP,
    imported_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    source_row_count BIGINT NOT NULL DEFAULT 0 CHECK (source_row_count >= 0),
    source_schema_hash VARCHAR,
    source_data_hash VARCHAR,
    pipeline_version VARCHAR NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'LOADING'
        CHECK (status IN ('LOADING', 'READY', 'ARCHIVED'))
);

CREATE TABLE IF NOT EXISTS app_meta.scenario_revision (
    revision_id VARCHAR PRIMARY KEY,
    scenario_id VARCHAR NOT NULL,
    revision_no INTEGER NOT NULL CHECK (revision_no > 0),
    revision_name VARCHAR NOT NULL,
    parent_revision_id VARCHAR,
    note VARCHAR,
    reference_hash VARCHAR NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    UNIQUE (scenario_id, revision_no)
);

CREATE TABLE IF NOT EXISTS app_meta.scenario_preset (
    revision_id VARCHAR PRIMARY KEY,
    start_month INTEGER NOT NULL,
    end_month INTEGER NOT NULL,
    secure_threshold DOUBLE NOT NULL,
    warning_threshold DOUBLE NOT NULL,
    preset_schema_version INTEGER NOT NULL CHECK (preset_schema_version > 0),
    preset_hash VARCHAR NOT NULL,
    CHECK (start_month <= end_month),
    CHECK (start_month % 100 BETWEEN 1 AND 12),
    CHECK (end_month % 100 BETWEEN 1 AND 12),
    CHECK (warning_threshold >= 0),
    CHECK (secure_threshold >= warning_threshold)
);

CREATE TABLE IF NOT EXISTS app_meta.scenario_preset_process (
    revision_id VARCHAR NOT NULL,
    process_name VARCHAR NOT NULL,
    display_order INTEGER NOT NULL CHECK (display_order > 0),
    PRIMARY KEY (revision_id, process_name),
    UNIQUE (revision_id, display_order)
);

CREATE TABLE IF NOT EXISTS raw_data.source_column_profile (
    dataset_id VARCHAR NOT NULL,
    ordinal_position INTEGER NOT NULL CHECK (ordinal_position > 0),
    column_name VARCHAR NOT NULL,
    source_dtype VARCHAR NOT NULL,
    nullable_dtype VARCHAR,
    null_count BIGINT NOT NULL CHECK (null_count >= 0),
    unique_count BIGINT NOT NULL CHECK (unique_count >= 0),
    PRIMARY KEY (dataset_id, ordinal_position),
    UNIQUE (dataset_id, column_name)
);

CREATE TABLE IF NOT EXISTS ref_data.rq_pkg_plan (
    dataset_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "양산구분" VARCHAR,
    "CS" VARCHAR,
    "제품정보" VARCHAR,
    "Stack" VARCHAR,
    "Capa Code" VARCHAR,
    "Customer" VARCHAR,
    "생산수량" DOUBLE,
    PRIMARY KEY (dataset_id, source_row_no)
);

CREATE TABLE IF NOT EXISTS ref_data.rq_yld (
    dataset_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "제품정보" VARCHAR,
    "Stack" VARCHAR,
    "WF 구분" VARCHAR,
    "EDS_수율" DOUBLE,
    "BE_수율" DOUBLE,
    PRIMARY KEY (dataset_id, source_row_no)
);

CREATE TABLE IF NOT EXISTS ref_data.rq_chip_qty (
    dataset_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "제품정보" VARCHAR,
    "Stack" VARCHAR,
    "WF 구분" VARCHAR,
    "구분_Chip" DOUBLE,
    "Net Die" DOUBLE,
    PRIMARY KEY (dataset_id, source_row_no)
);

CREATE TABLE IF NOT EXISTS ref_data.rq_chip_eq (
    dataset_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "제품정보" VARCHAR,
    "Stack" VARCHAR,
    "WF 구분" VARCHAR,
    "구분_Chip" DOUBLE,
    "구분_EQ" DOUBLE,
    PRIMARY KEY (dataset_id, source_row_no)
);

CREATE TABLE IF NOT EXISTS ref_data.rq_display_order (
    dataset_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "페이지 구분" VARCHAR,
    "탭 구분" VARCHAR,
    "정렬우선순위" INTEGER,
    "분류컬럼" VARCHAR,
    "정렬방식" VARCHAR,
    "분류값" VARCHAR,
    "값표시순서" INTEGER,
    "활성여부" VARCHAR,
    PRIMARY KEY (dataset_id, source_row_no)
);

CREATE TABLE IF NOT EXISTS ref_data.rq_eqp_own (
    dataset_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "공정" VARCHAR,
    "설비보유" DOUBLE,
    PRIMARY KEY (dataset_id, source_row_no)
);

CREATE TABLE IF NOT EXISTS ref_data.rq_eqp_lent (
    dataset_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "공정" VARCHAR,
    "설비대여평가" DOUBLE,
    PRIMARY KEY (dataset_id, source_row_no)
);

CREATE TABLE IF NOT EXISTS ref_data.rq_eqp_avbl (
    dataset_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "공정" VARCHAR,
    "가용대수" DOUBLE,
    PRIMARY KEY (dataset_id, source_row_no)
);

CREATE TABLE IF NOT EXISTS ref_data.rq_upeh (
    dataset_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "Area_Name" VARCHAR,
    "공정" VARCHAR,
    "양산구분" VARCHAR,
    "제품정보" VARCHAR,
    "Stack" VARCHAR,
    "WF 구분" VARCHAR,
    "소요기준" VARCHAR,
    "UPEH" DOUBLE,
    "ST" DOUBLE,
    PRIMARY KEY (dataset_id, source_row_no)
);

CREATE TABLE IF NOT EXISTS ref_data.rq_run_rate (
    dataset_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "공정" VARCHAR,
    "양산구분" VARCHAR,
    "CAPA_RUN_RATE" DOUBLE,
    PRIMARY KEY (dataset_id, source_row_no)
);

CREATE TABLE IF NOT EXISTS ref_data.rq_vital (
    dataset_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "공정" VARCHAR,
    "양산구분" VARCHAR,
    "편중률" DOUBLE,
    PRIMARY KEY (dataset_id, source_row_no)
);

CREATE TABLE IF NOT EXISTS ref_data.rq_module (
    dataset_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "공정" VARCHAR,
    "모듈수" DOUBLE,
    PRIMARY KEY (dataset_id, source_row_no)
);

CREATE TABLE IF NOT EXISTS ref_data.rq_run_day (
    dataset_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "공정" VARCHAR,
    "RUN_DAY" DOUBLE,
    PRIMARY KEY (dataset_id, source_row_no)
);

CREATE TABLE IF NOT EXISTS ref_data.rq_lot_ratio (
    dataset_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "공정" VARCHAR,
    "양산구분" VARCHAR,
    "제품정보" VARCHAR,
    "Stack" VARCHAR,
    "WF 구분" VARCHAR,
    "Lot 측정률" DOUBLE,
    PRIMARY KEY (dataset_id, source_row_no)
);

CREATE TABLE IF NOT EXISTS ref_data.rq_wf_ratio (
    dataset_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "공정" VARCHAR,
    "양산구분" VARCHAR,
    "제품정보" VARCHAR,
    "Stack" VARCHAR,
    "WF 구분" VARCHAR,
    "WF측정률" DOUBLE,
    PRIMARY KEY (dataset_id, source_row_no)
);

CREATE TABLE IF NOT EXISTS ref_data.rq_reqb (
    dataset_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "Area_Name" VARCHAR,
    "공정" VARCHAR,
    "양산구분" VARCHAR,
    "제품정보" VARCHAR,
    "Stack" VARCHAR,
    "Capa Code" VARCHAR,
    "Customer" VARCHAR,
    "CS" VARCHAR,
    "WF 구분" VARCHAR,
    "STEP_SEQ" VARCHAR,
    "MCP_SEQ" VARCHAR,
    "소요기준" VARCHAR,
    PRIMARY KEY (dataset_id, source_row_no)
);

CREATE TABLE IF NOT EXISTS rev_data.rq_pkg_plan (
    revision_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "양산구분" VARCHAR,
    "CS" VARCHAR,
    "제품정보" VARCHAR,
    "Stack" VARCHAR,
    "Capa Code" VARCHAR,
    "Customer" VARCHAR,
    "생산수량" DOUBLE,
    PRIMARY KEY (revision_id, source_row_no)
);

CREATE TABLE IF NOT EXISTS rev_data.rq_yld (
    revision_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "제품정보" VARCHAR,
    "Stack" VARCHAR,
    "WF 구분" VARCHAR,
    "EDS_수율" DOUBLE,
    "BE_수율" DOUBLE,
    PRIMARY KEY (revision_id, source_row_no)
);

CREATE TABLE IF NOT EXISTS rev_data.rq_upeh (
    revision_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "Area_Name" VARCHAR,
    "공정" VARCHAR,
    "양산구분" VARCHAR,
    "제품정보" VARCHAR,
    "Stack" VARCHAR,
    "WF 구분" VARCHAR,
    "소요기준" VARCHAR,
    "UPEH" DOUBLE,
    "ST" DOUBLE,
    PRIMARY KEY (revision_id, source_row_no)
);

CREATE TABLE IF NOT EXISTS rev_data.rq_run_rate (
    revision_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "공정" VARCHAR,
    "양산구분" VARCHAR,
    "CAPA_RUN_RATE" DOUBLE,
    PRIMARY KEY (revision_id, source_row_no)
);

CREATE TABLE IF NOT EXISTS rev_data.rq_vital (
    revision_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "공정" VARCHAR,
    "양산구분" VARCHAR,
    "편중률" DOUBLE,
    PRIMARY KEY (revision_id, source_row_no)
);

CREATE TABLE IF NOT EXISTS rev_data.rq_run_day (
    revision_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "공정" VARCHAR,
    "RUN_DAY" DOUBLE,
    PRIMARY KEY (revision_id, source_row_no)
);

CREATE TABLE IF NOT EXISTS rev_data.rq_lot_ratio (
    revision_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "공정" VARCHAR,
    "양산구분" VARCHAR,
    "제품정보" VARCHAR,
    "Stack" VARCHAR,
    "WF 구분" VARCHAR,
    "Lot 측정률" DOUBLE,
    PRIMARY KEY (revision_id, source_row_no)
);

CREATE TABLE IF NOT EXISTS rev_data.rq_wf_ratio (
    revision_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "생산계획년월" INTEGER,
    "공정" VARCHAR,
    "양산구분" VARCHAR,
    "제품정보" VARCHAR,
    "Stack" VARCHAR,
    "WF 구분" VARCHAR,
    "WF측정률" DOUBLE,
    PRIMARY KEY (revision_id, source_row_no)
);

CREATE TABLE IF NOT EXISTS rev_data.rq_display_order (
    revision_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL,
    "페이지 구분" VARCHAR,
    "탭 구분" VARCHAR,
    "정렬우선순위" INTEGER,
    "분류컬럼" VARCHAR,
    "정렬방식" VARCHAR,
    "분류값" VARCHAR,
    "값표시순서" INTEGER,
    "활성여부" VARCHAR,
    PRIMARY KEY (revision_id, source_row_no)
);

CREATE TABLE IF NOT EXISTS result_data.simulation_run (
    run_id VARCHAR PRIMARY KEY,
    scenario_id VARCHAR NOT NULL,
    revision_id VARCHAR NOT NULL,
    status VARCHAR NOT NULL CHECK (status IN ('RUNNING', 'SUCCEEDED', 'FAILED')),
    pipeline_version VARCHAR NOT NULL,
    input_hash VARCHAR NOT NULL,
    preset_hash VARCHAR NOT NULL,
    started_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    completed_at TIMESTAMP,
    error_message VARCHAR
);
