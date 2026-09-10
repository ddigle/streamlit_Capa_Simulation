-- Purpose: 시나리오와 독립된 공용 공정 표시명 프로필(원본 공정 → 화면 표시명)을 저장한다.

CREATE TABLE IF NOT EXISTS app_meta.global_process_rename (
    profile_id INTEGER PRIMARY KEY CHECK (profile_id = 1),
    version INTEGER NOT NULL CHECK (version > 0),
    source VARCHAR NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS app_meta.global_process_rename_rule (
    profile_id INTEGER NOT NULL CHECK (profile_id = 1),
    source_row_no BIGINT NOT NULL CHECK (source_row_no > 0),
    "공정" VARCHAR NOT NULL CHECK ("공정" <> ''),
    "표시명" VARCHAR NOT NULL CHECK ("표시명" <> ''),
    PRIMARY KEY (profile_id, source_row_no),
    UNIQUE (profile_id, "공정"),
    UNIQUE (profile_id, "표시명")
);
