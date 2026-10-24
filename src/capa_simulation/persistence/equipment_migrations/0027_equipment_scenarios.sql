-- Purpose: 설비 마스터를 공통 호기 대장과 설비 시나리오 일정으로 나누는 표를 만들고, 기존 리비전을 「운영 일정」 시나리오 리비전으로 가리켜 옮기며, 이관 시점 최신을 공식 v1 로 발행하고 이관 경계 번호를 남긴다.

-- 이 파일이 넣는 id 는 모두 결정적 글이다('operations'·'legacy-'||revision_id·'release-1'·경계 1). 동기화로 받은 DB 를 다른 PC 가
-- 다시 이관해도 같은 행이 나오게 uuid 로 바꾸지 않는다.

-- 공통 대장 리비전의 저장자(E9, 선택 입력). 리비전명은 시나리오 리비전에만 둔다.
ALTER TABLE equipment_ops.revision ADD COLUMN saved_by VARCHAR;
-- 호기 키. 옛 행은 NULL 이고 읽을 때 'n' || md5(equipment_id) 로 본다(UPDATE 하지 않는다).
ALTER TABLE equipment_ops.equipment_master_snapshot ADD COLUMN unit_key VARCHAR;

-- 진척 비교 기준선의 설비 쪽 출처(공식 발행 쌍에서만 저장 — E5). 가리키기만 하고 소유 칸 이름과 다르게 둔다.
ALTER TABLE equipment_ops.shortening_baseline ADD COLUMN equipment_schedule_revision_ref VARCHAR;
ALTER TABLE equipment_ops.shortening_baseline ADD COLUMN equipment_schedule_revision_no INTEGER;
ALTER TABLE equipment_ops.shortening_baseline ADD COLUMN equipment_scenario_name VARCHAR;
ALTER TABLE equipment_ops.shortening_baseline ADD COLUMN equipment_release_no INTEGER;

CREATE TABLE IF NOT EXISTS equipment_ops.equipment_scenario (
    equipment_scenario_id VARCHAR PRIMARY KEY,
    -- 이름 중복은 보관본까지 저장소가 쓰기 잠금 안에서 막는다(시뮬레이션과 같다). UNIQUE 를 걸지 않는다 — 이름을 고칠 수 있어야 한다.
    scenario_name VARCHAR NOT NULL CHECK (trim(scenario_name) <> ''),
    status VARCHAR NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'ARCHIVED')),
    list_order INTEGER,
    source_schedule_revision_id VARCHAR,
    created_by VARCHAR,
    created_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS equipment_ops.equipment_schedule_revision (
    schedule_revision_id VARCHAR PRIMARY KEY,
    equipment_scenario_id VARCHAR NOT NULL,
    revision_no INTEGER NOT NULL CHECK (revision_no > 0),
    revision_name VARCHAR,
    note VARCHAR,
    saved_by VARCHAR,
    -- legacy · save · clone · propagate · restore. 허용값은 서비스가 본다(DuckDB 는 CHECK 를 고칠 수 없다).
    origin VARCHAR NOT NULL,
    common_revision_id VARCHAR,
    legacy_revision_id VARCHAR,
    schedule_hash VARCHAR,
    downtime_hash VARCHAR,
    created_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    UNIQUE (equipment_scenario_id, revision_no)
);

CREATE TABLE IF NOT EXISTS equipment_ops.equipment_schedule_snapshot (
    schedule_revision_id VARCHAR NOT NULL,
    unit_key VARCHAR NOT NULL,
    vibration_table_date DATE,
    logistics_date DATE,
    arrival_date DATE,
    qual_date DATE,
    removal_date DATE,
    relocation_date DATE,
    scenario_memo VARCHAR,
    PRIMARY KEY (schedule_revision_id, unit_key)
);

CREATE TABLE IF NOT EXISTS equipment_ops.equipment_schedule_downtime_snapshot (
    schedule_revision_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL CHECK (source_row_no > 0),
    unit_key VARCHAR NOT NULL,
    downtime_type VARCHAR NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE,
    detail VARCHAR,
    note VARCHAR,
    PRIMARY KEY (schedule_revision_id, source_row_no),
    UNIQUE (schedule_revision_id, unit_key, downtime_type, start_date)
);

CREATE TABLE IF NOT EXISTS equipment_ops.equipment_official_release (
    release_id VARCHAR PRIMARY KEY,
    release_no INTEGER NOT NULL UNIQUE CHECK (release_no > 0),
    equipment_scenario_id VARCHAR NOT NULL,
    schedule_revision_id VARCHAR NOT NULL,
    released_by VARCHAR,
    note VARCHAR,
    released_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

-- 옛 배포로 저장한 공통 리비전을 가려내는 경계. 「revision_no > 마지막 행의 through_revision_no 이면서 계약 v3 이하」 가 그 흔적이다.
-- 시각(created_at)은 트랜잭션 시작 시각이고 PC 시계에 흔들려 쓰지 않는다. 덧붙이기만 한다.
CREATE TABLE IF NOT EXISTS equipment_ops.equipment_legacy_boundary (
    boundary_no INTEGER PRIMARY KEY CHECK (boundary_no > 0),
    through_revision_no INTEGER NOT NULL CHECK (through_revision_no >= 0),
    note VARCHAR,
    recorded_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

INSERT INTO equipment_ops.equipment_scenario (equipment_scenario_id, scenario_name, list_order)
VALUES ('operations', '운영 일정', 0);

-- 리비전 rK 마다 「운영 일정」 rK 머리 한 행. 스냅샷 행은 옮기지 않는다 — legacy_revision_id 가 옛 행을 가리킨다.
INSERT INTO equipment_ops.equipment_schedule_revision (
    schedule_revision_id, equipment_scenario_id, revision_no, note, origin,
    common_revision_id, legacy_revision_id, created_at
)
SELECT 'legacy-' || revision_id, 'operations', revision_no, note, 'legacy',
       revision_id, revision_id, created_at
FROM equipment_ops.revision;

-- 공식 = 이관 시점 최신. 리비전이 없으면(빈 DB) 행이 없다 — 첫 저장이 공식 v1 을 함께 낸다.
INSERT INTO equipment_ops.equipment_official_release (
    release_id, release_no, equipment_scenario_id, schedule_revision_id, note
)
SELECT 'release-1', 1, 'operations', 'legacy-' || revision_id, '이관 시점 최신 리비전'
FROM equipment_ops.revision
ORDER BY revision_no DESC
LIMIT 1;

INSERT INTO equipment_ops.equipment_legacy_boundary (boundary_no, through_revision_no, note)
SELECT 1, COALESCE(MAX(revision_no), 0), '0027 이관' FROM equipment_ops.revision;
