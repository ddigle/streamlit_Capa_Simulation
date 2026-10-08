-- Purpose: 필요단축일정 진척 비교의 기준선(그때 계획의 다섯 목표 호기 결과를 얼린 공용 기록)을 머리·공정·호기 세 표로 저장한다.

-- 기준선은 고칠 수 없다 — 새로 저장하거나 통째로 지운다. 이름은 공용 목록에서 고르는 글이라 겹치지
-- 않는다. 머리 한 행에 저장 시각·이름·그날 오늘·조회 시작·끝 월과 계산의 출처(설비 리비전, 활성
-- 시나리오·리비전·내용 토큰)를 남긴다. 설비 리비전이 NULL 이면 저장본이 없었던 것이다.
CREATE TABLE IF NOT EXISTS equipment_ops.shortening_baseline (
    baseline_id VARCHAR PRIMARY KEY,
    baseline_name VARCHAR NOT NULL UNIQUE CHECK (trim(baseline_name) <> ''),
    saved_at TIMESTAMP NOT NULL,
    saved_by VARCHAR,
    plan_today DATE NOT NULL,
    start_month INTEGER NOT NULL CHECK (start_month % 100 BETWEEN 1 AND 12),
    end_month INTEGER NOT NULL CHECK (end_month % 100 BETWEEN 1 AND 12),
    equipment_revision_id VARCHAR,
    equipment_revision_no INTEGER,
    reference_version BIGINT,
    scenario_id VARCHAR,
    scenario_name VARCHAR,
    scenario_revision_id VARCHAR,
    scenario_revision_no INTEGER,
    scenario_content_token VARCHAR,
    CHECK (start_month <= end_month)
);

-- 그때 맞댄 공정(시나리오 소요와 호기 마스터에 함께 있던 공정)과 Cut-off 일수. 호기 행만으로는 목표를
-- 채워 단축할 호기가 없던 공정이 보이지 않아 「지금 범위 밖」·「범위가 다름」을 가릴 수 없다.
CREATE TABLE IF NOT EXISTS equipment_ops.shortening_baseline_process (
    baseline_id VARCHAR NOT NULL,
    process_name VARCHAR NOT NULL CHECK (process_name <> ''),
    sort_order INTEGER NOT NULL CHECK (sort_order >= 0),
    cutoff_days INTEGER,
    PRIMARY KEY (baseline_id, process_name)
);

-- 목표(90·100·110·120·130%)마다 당긴 호기와 가상 호기 「추가N」 한 줄씩. 호기는 설비키(모듈 묶음은
-- Main 설비)이고 설비명은 묶음의 모듈 행을 이은 글이다. 기존 Qual 은 확보 시점, 목표 Qual 은 필요
-- 시점이다. 가상 호기는 기존 Qual·단축일수·설비명·환산비가 NULL 이다. 달은 `YYYYMM` 정수, 해소 기여
-- 월은 계산 결과의 글 그대로(`YYYYMM, YYYYMM`)다.
CREATE TABLE IF NOT EXISTS equipment_ops.shortening_baseline_unit (
    baseline_id VARCHAR NOT NULL,
    target_level INTEGER NOT NULL CHECK (target_level > 0),
    sort_order INTEGER NOT NULL CHECK (sort_order >= 0),
    process_name VARCHAR NOT NULL CHECK (process_name <> ''),
    unit_name VARCHAR NOT NULL CHECK (unit_name <> ''),
    unit_kind VARCHAR NOT NULL CHECK (unit_kind IN ('단축', '신규')),
    equipment_ids VARCHAR,
    module_count INTEGER NOT NULL CHECK (module_count > 0),
    conversion_ratio DOUBLE,
    original_qual DATE,
    target_qual DATE NOT NULL,
    shortening_days INTEGER,
    gained_units DOUBLE NOT NULL,
    target_month INTEGER,
    contributed_months VARCHAR,
    PRIMARY KEY (baseline_id, target_level, process_name, unit_kind, unit_name)
);
