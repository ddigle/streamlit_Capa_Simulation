CREATE TABLE IF NOT EXISTS app_meta.global_display_order (
    profile_id INTEGER PRIMARY KEY CHECK (profile_id = 1),
    version INTEGER NOT NULL CHECK (version > 0),
    source VARCHAR NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS app_meta.global_display_order_rule (
    profile_id INTEGER NOT NULL CHECK (profile_id = 1),
    source_row_no BIGINT NOT NULL CHECK (source_row_no > 0),
    "페이지 구분" VARCHAR NOT NULL,
    "탭 구분" VARCHAR NOT NULL,
    "정렬우선순위" INTEGER NOT NULL,
    "분류컬럼" VARCHAR NOT NULL,
    "정렬방식" VARCHAR NOT NULL,
    "분류값" VARCHAR,
    "값표시순서" INTEGER,
    "활성여부" VARCHAR NOT NULL,
    PRIMARY KEY (profile_id, source_row_no)
);
