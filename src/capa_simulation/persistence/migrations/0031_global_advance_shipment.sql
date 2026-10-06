-- Purpose: 시나리오와 독립된 공용 선행 입고 실적 프로필(월별 억Gb, 화면 표시 전용)을 저장한다.

-- 선행 B/O(0018)와 같은 모양이다 — 헤더 한 행(version)과 월 N행. 값은 입력한 부호 그대로이고
-- 0 은 「없음」이라 행을 두지 않는다. 소유 컬럼(`scenario_id`·`dataset_id`·`revision_id`)을 두지
-- 않는다. 두면 `_owned_tables` 자동 발견이 시나리오 소유로 판정해 시나리오 삭제가 함께 지운다.
CREATE TABLE IF NOT EXISTS app_meta.global_advance_shipment (
    profile_id INTEGER PRIMARY KEY CHECK (profile_id = 1),
    version INTEGER NOT NULL CHECK (version > 0),
    source VARCHAR NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS app_meta.global_advance_shipment_month (
    profile_id INTEGER NOT NULL CHECK (profile_id = 1),
    "생산계획년월" INTEGER NOT NULL CHECK ("생산계획년월" % 100 BETWEEN 1 AND 12),
    "선행 입고" DOUBLE NOT NULL,
    PRIMARY KEY (profile_id, "생산계획년월")
);
