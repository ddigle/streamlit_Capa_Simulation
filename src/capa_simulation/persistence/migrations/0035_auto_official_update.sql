-- Purpose: 공식버전 자동 갱신의 공용 설정 프로필·설정 변경 기록·실행 기록·자동 off 공정 기록을 저장한다.

-- 네 표 모두 소유 컬럼(`scenario_id`·`dataset_id`·`revision_id`)을 두지 않는다. 두면 `_owned_tables`
-- 자동 발견이 시나리오 소유로 판정해 시나리오 삭제가 기록을 함께 지운다. 실행이 만든 시나리오·리비전·
-- 공식버전은 `created_scenario_id`·`base_revision_id`·`filtered_revision_id`·`official_release_id` 로
-- 가리키기만 한다 — 시나리오를 지워도 그날 무엇을 했는지는 남는다.

-- 설정은 다른 공용 프로필처럼 헤더 한 행이다. 기준 확보율은 비율이다(80% 는 0.8).
CREATE TABLE IF NOT EXISTS app_meta.global_auto_official_update (
    profile_id INTEGER PRIMARY KEY CHECK (profile_id = 1),
    version INTEGER NOT NULL CHECK (version > 0),
    source VARCHAR NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    enabled BOOLEAN NOT NULL,
    check_time TIME NOT NULL,
    keyword VARCHAR NOT NULL CHECK (trim(keyword) <> ''),
    threshold DOUBLE NOT NULL CHECK (threshold > 0)
);

-- 설정을 바꿀 때마다 한 행. 헤더는 현재본만 남기므로 언제·무엇을 바꿨는지는 여기서만 읽힌다.
CREATE TABLE IF NOT EXISTS app_meta.auto_official_update_setting_log (
    version INTEGER PRIMARY KEY CHECK (version > 0),
    changed_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    changed_by VARCHAR,
    change_text VARCHAR NOT NULL CHECK (change_text <> '')
);

-- 실행 한 회차가 한 행이다. `run_key` 가 회차 선점이다 — 예약 회차는 날짜로 만들어 같은 날 두 번
-- 돌지 않고, 「지금 실행」은 누를 때마다 새 키다. 단계가 진행될 때마다 같은 행을 고쳐 쓴다.
CREATE TABLE IF NOT EXISTS app_meta.auto_official_update_run (
    run_id VARCHAR PRIMARY KEY,
    run_key VARCHAR NOT NULL UNIQUE,
    trigger_kind VARCHAR NOT NULL CHECK (trigger_kind IN ('SCHEDULED', 'MANUAL')),
    run_date DATE NOT NULL,
    status VARCHAR NOT NULL
        CHECK (status IN ('RUNNING', 'SKIPPED', 'PUBLISHED', 'PUBLISH_SKIPPED', 'ERROR')),
    stage VARCHAR NOT NULL,
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    keyword VARCHAR NOT NULL,
    threshold DOUBLE NOT NULL,
    settings_version INTEGER NOT NULL,
    baseline_release_no INTEGER,
    baseline_week INTEGER,
    candidate_count INTEGER,
    simulation_code VARCHAR,
    simulation_name VARCHAR,
    simulation_week INTEGER,
    source_registered_at TIMESTAMP,
    detail_window VARCHAR,
    created_scenario_id VARCHAR,
    created_scenario_name VARCHAR,
    base_revision_id VARCHAR,
    filtered_revision_id VARCHAR,
    official_release_id VARCHAR,
    official_release_no INTEGER,
    auto_off_count INTEGER,
    inherited_off_count INTEGER,
    reason VARCHAR
);

-- 실행이 공정 필터에서 뺀 공정. `AUTO` 는 그 회차가 확보율로 판정해 뺀 것이고 `INHERITED` 는 직전
-- 공식버전에서 사람이 손으로 뺀 것을 이어받은 것이다. 리비전 2 를 저장하지 못한 회차는
-- `filtered_revision_id` 가 비어 있다.
CREATE TABLE IF NOT EXISTS app_meta.auto_official_update_exclusion (
    run_id VARCHAR NOT NULL,
    filtered_revision_id VARCHAR,
    "공정" VARCHAR NOT NULL CHECK ("공정" <> ''),
    kind VARCHAR NOT NULL CHECK (kind IN ('AUTO', 'INHERITED')),
    min_rate DOUBLE,
    min_month INTEGER CHECK (min_month IS NULL OR min_month % 100 BETWEEN 1 AND 12),
    PRIMARY KEY (run_id, "공정")
);
