-- Purpose: HOME 공정 필터 그룹 단추가 쓰는 공정 → 공정 그룹 대응을 시나리오와 독립된 공용 프로필로 저장한다.

CREATE TABLE IF NOT EXISTS app_meta.global_process_group (
    profile_id INTEGER PRIMARY KEY CHECK (profile_id = 1),
    version INTEGER NOT NULL CHECK (version > 0),
    source VARCHAR NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS app_meta.global_process_group_item (
    profile_id INTEGER NOT NULL CHECK (profile_id = 1),
    "공정" VARCHAR NOT NULL CHECK ("공정" <> ''),
    "공정그룹" VARCHAR NOT NULL CHECK ("공정그룹" <> ''),
    PRIMARY KEY (profile_id, "공정")
);
