-- Purpose: 가정 설비 시나리오의 Space 배치(호기 위치·층 도면 요소·Main 설비명 위치)를 공식 배치와 다른 것만 일정 리비전마다 담는 표 셋과 리비전의 배치 차이 지문 칸을 더한다.

-- 공식 배치는 공통 대장의 배치 일곱 칸과 층 현행값(0007·0011·0025)이다 — 이 표들은 그 위의 차이만 든다. 일정 리비전처럼 넣기만 하고
-- 고치지 않는다(append-only). 외래 키는 두지 않는다(0027 과 같은 까닭 — 한 트랜잭션 삭제·copy_database 차례). 공식 설비 시나리오의
-- 최신·최신 발행 리비전에는 행이 없다 — 저장소가 지킨다. 허용값(`set`·`drop`, 위치 `top`·`bottom`·`center`, 리비전 출처 `origin` 에 더하는
-- `layout_clear`)은 서비스가 본다(DuckDB 는 CHECK 를 고칠 수 없다). `layout_hash` 는 이 번호 뒤의 코드가 모든 새 리비전에 채운다(빈 차이도
-- 고정 지문) — NULL 은 이관 리비전이거나 이 번호를 모르는 코드가 쓴 리비전이다. 마이그레이션은 아무것도 옮기지 않는다(세 표 모두 0행).

ALTER TABLE equipment_ops.equipment_schedule_revision ADD COLUMN layout_hash VARCHAR;

CREATE TABLE IF NOT EXISTS equipment_ops.equipment_schedule_layout_unit (
    schedule_revision_id VARCHAR NOT NULL,
    unit_key VARCHAR NOT NULL,
    -- 저장 당시 이 호기의 Main 설비(앞뒤 공백을 걷은 값, 없으면 NULL). 묶음 소속이 그 뒤 공식에서 바뀌었는지 읽을 때 가른다.
    parent_equipment_id VARCHAR,
    building VARCHAR,
    floor_name VARCHAR,
    x_coordinate DOUBLE,
    y_coordinate DOUBLE,
    x_size DOUBLE,
    y_size DOUBLE,
    layout_display_flag VARCHAR NOT NULL,
    PRIMARY KEY (schedule_revision_id, unit_key)
);

CREATE TABLE IF NOT EXISTS equipment_ops.equipment_schedule_layout_mark (
    schedule_revision_id VARCHAR NOT NULL,
    building VARCHAR NOT NULL,
    floor_name VARCHAR NOT NULL,
    mark_id VARCHAR NOT NULL,
    change_kind VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL CHECK (source_row_no > 0),
    mark_kind VARCHAR,
    x_coordinate DOUBLE,
    y_coordinate DOUBLE,
    x_size DOUBLE,
    y_size DOUBLE,
    rotation_deg INTEGER,
    label VARCHAR,
    color_key VARCHAR,
    hatch BOOLEAN,
    keep_out BOOLEAN,
    font_size INTEGER,
    font_color VARCHAR,
    border_style VARCHAR,
    label_align VARCHAR,
    PRIMARY KEY (schedule_revision_id, building, floor_name, mark_id)
);

CREATE TABLE IF NOT EXISTS equipment_ops.equipment_schedule_layout_label (
    schedule_revision_id VARCHAR NOT NULL,
    building VARCHAR NOT NULL,
    floor_name VARCHAR NOT NULL,
    parent_equipment_id VARCHAR NOT NULL,
    -- NULL 은 「공식의 위치 행을 지움(그 모양의 처음 위치)」 이다.
    label_position VARCHAR,
    PRIMARY KEY (schedule_revision_id, building, floor_name, parent_equipment_id)
);
