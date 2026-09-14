-- Purpose: HOME 상단에 띄우는 Summary 공지를 시나리오와 독립된 공용 프로필로 저장한다.

-- 소유 컬럼(`scenario_id`·`dataset_id`·`revision_id`)을 두지 않는다. 두면 `_owned_tables`
-- 자동 발견이 시나리오 소유로 판정해 시나리오 삭제가 이 단일 행을 함께 지운다.
--
-- 공지는 **비어 있는 것도 뜻이 있는 값**이다(내려 둔 상태). 그래서 빈 문자열을 막지
-- 않고, 프로필 자체가 없는 상태(version = 0)와 구분한다.
CREATE TABLE IF NOT EXISTS app_meta.global_summary_note (
    profile_id INTEGER PRIMARY KEY CHECK (profile_id = 1),
    note VARCHAR NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    source VARCHAR NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);
