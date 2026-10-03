-- Purpose: Space S.PKG FAB 전체 도면의 캔버스·배경 도면과 층 블록·도면 요소를 리비전과 무관한 현행값으로 보관한다.

-- 층 표(0007·0011)에 「FAB」 같은 가짜 동·층 키를 넣지 않는다 — 층 저장 입구의 키 검사, RawData
-- 좌표 상한(층 캔버스 최댓값), 층 열거가 모두 그 키를 걸러 내야 한다. 그래서 따로 둔다.
-- `fab_layout_profile` 은 한 행뿐이다(`layout_key = 'FAB'`). 도면 BLOB 을 다시 쓰지 않도록 캔버스는
-- UPDATE 로만 고친다(0007 과 같다).
CREATE TABLE IF NOT EXISTS equipment_ops.fab_layout_profile (
    layout_key VARCHAR PRIMARY KEY CHECK (layout_key = 'FAB'),
    canvas_width DOUBLE NOT NULL CHECK (canvas_width > 0),
    canvas_height DOUBLE NOT NULL CHECK (canvas_height > 0),
    image_mime VARCHAR,
    image_name VARCHAR,
    image_payload BLOB,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

-- 0011 `floor_layout_mark` 와 같은 열(동·층 제외)에 층 블록의 연결 대상 두 칸을 더한다. 연결은 둘 다
-- 있거나 둘 다 NULL 이고, 층 블록은 연결이 필수다 — 종류·색·회전·캔버스 범위·연결 검사는 서비스
-- (`services/fab_layout.prepare_fab_layout_marks`)가 맡는다(DuckDB 는 CHECK 를 고칠 수 없어 종류를
-- 더할 때 표를 다시 만들어야 하므로 DDL 에 목록을 박지 않는다). 저장은 전체 교체(DELETE + INSERT)라
-- PK 를 두지 않는다. `source_row_no` 가 그리는 순서다.
CREATE TABLE IF NOT EXISTS equipment_ops.fab_layout_mark (
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
    link_building VARCHAR,
    link_floor VARCHAR,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);
