-- Purpose: HOME 주요공정 히트맵이 그릴 공정 목록을 시나리오와 독립된 공용 프로필로 저장한다.

-- 소유 컬럼(`scenario_id`·`dataset_id`·`revision_id`)을 두지 않는다. 두면 `_owned_tables`
-- 자동 발견이 시나리오 소유로 판정해 시나리오 삭제가 이 공용 목록을 함께 지운다.
CREATE TABLE IF NOT EXISTS app_meta.global_key_process (
    profile_id INTEGER PRIMARY KEY CHECK (profile_id = 1),
    version INTEGER NOT NULL CHECK (version > 0),
    source VARCHAR NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

-- `표시순서` 는 히트맵 행 순서다. 화면에서 다시 정렬하지 않고 고른 차례를 그대로 쓴다.
CREATE TABLE IF NOT EXISTS app_meta.global_key_process_item (
    profile_id INTEGER NOT NULL CHECK (profile_id = 1),
    "공정" VARCHAR NOT NULL CHECK ("공정" <> ''),
    "표시순서" INTEGER NOT NULL CHECK ("표시순서" >= 0),
    PRIMARY KEY (profile_id, "공정")
);
