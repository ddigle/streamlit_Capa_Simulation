-- Purpose: B/N Top5 막대가 표현하는 확보율 구간을 시나리오와 독립된 공용 프로필로 저장한다.

-- 소유 컬럼(`scenario_id`·`dataset_id`·`revision_id`)을 두지 않는다. 두면 `_owned_tables`
-- 자동 발견이 시나리오 소유로 판정해 시나리오 삭제가 이 단일 행을 함께 지운다.
CREATE TABLE IF NOT EXISTS app_meta.global_top5_band (
    profile_id INTEGER PRIMARY KEY CHECK (profile_id = 1),
    min_rate DOUBLE NOT NULL CHECK (min_rate >= 0),
    max_rate DOUBLE NOT NULL CHECK (max_rate > min_rate),
    version INTEGER NOT NULL CHECK (version > 0),
    source VARCHAR NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);
