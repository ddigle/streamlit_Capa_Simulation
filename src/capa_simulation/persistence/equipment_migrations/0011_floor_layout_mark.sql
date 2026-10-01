-- Purpose: 동·층별 Space 배치도의 비설비 도면 요소(반입구·문·영역·기둥·글자·동선)를 리비전과 무관한 현행값으로 보관한다.

-- 호기 마스터의 행이 아니다. `floor_layout_profile` 의 캔버스처럼 설비 리비전을 저장해도
-- 복제되지 않는 층 단위 현행값이고, 저장은 그 층 요소 전체를 갈아 끼운다(DELETE + INSERT).
-- `source_row_no` 가 그리는 순서다. 종류·색·회전·캔버스 범위·층 안 id 유일성은
-- `services/floor_layout_mark.prepare_floor_layout_marks` 가 맡는다 — DuckDB 는 CHECK 를
-- 고칠 수 없어 종류 하나를 더할 때 표를 다시 만들어야 하므로 DDL 에 목록을 박지 않는다.
-- 같은 트랜잭션에서 같은 키를 지웠다 다시 넣으므로 PK 를 두지 않는다(`process_cutoff` 와 같다).
CREATE TABLE IF NOT EXISTS equipment_ops.floor_layout_mark (
    building VARCHAR NOT NULL,
    floor_name VARCHAR NOT NULL,
    mark_id VARCHAR NOT NULL,
    source_row_no BIGINT NOT NULL CHECK (source_row_no > 0),
    mark_kind VARCHAR NOT NULL,
    x_coordinate DOUBLE NOT NULL CHECK (x_coordinate >= 0),
    y_coordinate DOUBLE NOT NULL CHECK (y_coordinate >= 0),
    x_size DOUBLE NOT NULL CHECK (x_size > 0),
    y_size DOUBLE NOT NULL CHECK (y_size > 0),
    rotation_deg INTEGER NOT NULL DEFAULT 0,
    label VARCHAR,
    color_key VARCHAR,
    hatch BOOLEAN NOT NULL DEFAULT FALSE,
    keep_out BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);
