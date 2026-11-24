-- Purpose: 누적 진척 기록을 「이번 주 값 넣기」 로 저장한 주의 화면 호기 표 스냅숏을 머리 · 공정 · 호기 세 표로 만든다.

-- 기록 값은 0036 그대로 사람이 적은 수다. 넣기로 그 주를 저장할 때만 그 화면이 보던 호기 표를 같은 쓰기
-- 트랜잭션에서 곁에 남기고(손으로 적은 주는 없다), 그릴 때 바로 앞 기록 주의 스냅숏과 견줘 오르내린 까닭을
-- 센다(까닭은 저장하지 않는다). 머리 한 행 = 기록 주 하나(PK 해 · 주)이고 기록 지우기가 같은 트랜잭션에서
-- 머리와 자식을 지운다. log_updated_at 은 같은 트랜잭션에서 쓴 기록 줄의 updated_at 이다 — 이 표를 모르는
-- 옛 코드가 그 주를 고치거나 지우고 다시 넣으면 값이 어긋나 읽는 쪽이 그 스냅숏을 버린다. 갈아 쓰기는 새
-- snapshot_id 로 한다(머리는 제자리 UPDATE, 자식은 새 id 로 넣고 옛 id 자식을 지움 — 같은 키를 한 트랜잭션에서
-- 지웠다 다시 넣지 않는다). content_digest 는 같은 수 · 같은 구성의 넣기를 가르는 글이고, 출처 칸은 기준선
-- 머리(0021 · 0027)와 같은 이름이다. 리비전 · 설비 시나리오와 무관한 공용 값이라 소유 칸이 없다.
CREATE TABLE IF NOT EXISTS equipment_ops.shortening_progress_snapshot (
    iso_year INTEGER NOT NULL CHECK (iso_year BETWEEN 2000 AND 2999),
    iso_week INTEGER NOT NULL CHECK (iso_week BETWEEN 1 AND 53),
    snapshot_id VARCHAR NOT NULL CHECK (snapshot_id <> ''),
    log_updated_at TIMESTAMP NOT NULL,
    captured_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    captured_by VARCHAR,
    snapshot_days INTEGER NOT NULL CHECK (snapshot_days >= 0),
    target_level INTEGER NOT NULL CHECK (target_level > 0),
    schedule_basis VARCHAR NOT NULL CHECK (schedule_basis <> ''),
    scope_selected BOOLEAN NOT NULL,
    plan_today DATE NOT NULL,
    start_month INTEGER NOT NULL CHECK (start_month % 100 BETWEEN 1 AND 12),
    end_month INTEGER NOT NULL CHECK (end_month % 100 BETWEEN 1 AND 12),
    content_digest VARCHAR NOT NULL,
    equipment_revision_id VARCHAR,
    equipment_revision_no INTEGER,
    reference_version BIGINT,
    scenario_id VARCHAR,
    scenario_name VARCHAR,
    scenario_revision_id VARCHAR,
    scenario_revision_no INTEGER,
    scenario_content_token VARCHAR,
    equipment_schedule_revision_ref VARCHAR,
    equipment_schedule_revision_no INTEGER,
    equipment_scenario_name VARCHAR,
    equipment_release_no INTEGER,
    CHECK (start_month <= end_month),
    PRIMARY KEY (iso_year, iso_week)
);

-- 그 화면의 범위 공정(원본 이름 · 화면 차례)과 Cut-off 일수. 호기 행만으로는 단축할 호기가 없던 범위 공정이
-- 보이지 않아 「범위 바뀜」 을 가릴 수 없다.
CREATE TABLE IF NOT EXISTS equipment_ops.shortening_progress_snapshot_process (
    snapshot_id VARCHAR NOT NULL,
    process_name VARCHAR NOT NULL CHECK (process_name <> ''),
    sort_order INTEGER NOT NULL CHECK (sort_order >= 0),
    cutoff_days INTEGER,
    PRIMARY KEY (snapshot_id, process_name)
);

-- 범위 공정의 당긴 호기와 가상 호기 「추가N」 한 줄씩 — 진척 비교 짝짓기가 읽는 칸만이다. 기존 Qual 은 확보
-- 시점(Static 의 남는 호기 · 추가N 은 NULL), 목표 Qual 은 필요 시점, 단축일수는 확보 − 필요(NULL 은 0일로 센다).
CREATE TABLE IF NOT EXISTS equipment_ops.shortening_progress_snapshot_unit (
    snapshot_id VARCHAR NOT NULL,
    sort_order INTEGER NOT NULL CHECK (sort_order >= 0),
    process_name VARCHAR NOT NULL CHECK (process_name <> ''),
    unit_name VARCHAR NOT NULL CHECK (unit_name <> ''),
    unit_kind VARCHAR NOT NULL CHECK (unit_kind IN ('단축', '신규')),
    module_count INTEGER NOT NULL CHECK (module_count > 0),
    original_qual DATE,
    target_qual DATE NOT NULL,
    shortening_days INTEGER,
    PRIMARY KEY (snapshot_id, process_name, unit_kind, unit_name)
);
