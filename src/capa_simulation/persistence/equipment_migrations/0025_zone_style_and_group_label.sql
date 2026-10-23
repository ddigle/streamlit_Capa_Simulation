-- Purpose: Space 영역 요소의 테두리 모양·이름표 정렬 칸과 층마다 Main 설비 모듈 묶음 이름표 위치 표를 더한다.

-- 영역(zone) 요소의 테두리 모양(`border_style` — dashed 점선·solid 실선)과 이름표 정렬(`label_align` — left 왼쪽·
-- center 가운데·right 오른쪽)을 층·FAB 요소 표 둘에 NULL 허용으로 더한다(DuckDB 는 `ADD COLUMN` 에 NOT NULL·CHECK 를
-- 받지 않는다 — 0017 과 같다). 이미 저장된 요소는 NULL 로 읽혀 지금 모습(점선·왼쪽)으로 그린다. 영역이 아닌 요소는
-- 늘 NULL 이다. 허용값은 서비스 검증(`services/floor_layout_mark.zone_border_style`·`zone_label_align`)이 맡는다 —
-- 목록을 DDL 에 박지 않는다.
ALTER TABLE equipment_ops.floor_layout_mark
ADD COLUMN border_style VARCHAR;

ALTER TABLE equipment_ops.floor_layout_mark
ADD COLUMN label_align VARCHAR;

ALTER TABLE equipment_ops.fab_layout_mark
ADD COLUMN border_style VARCHAR;

ALTER TABLE equipment_ops.fab_layout_mark
ADD COLUMN label_align VARCHAR;

-- 층 도면에서 Main 설비 모듈 묶음(모듈 둘 이상)의 이름표 위치 — 묶음 범위의 위(top)·아래(bottom). 가운데(기본)는
-- 행을 두지 않는다. 설비 마스터 칸이 아니라 도면 요소처럼 설비 리비전과 무관한 층 현행값이고, 저장은 그 층 행 전체를
-- 갈아 끼운다(DELETE + INSERT). 같은 트랜잭션에서 같은 키를 지웠다 다시 넣으므로 PK 를 두지 않는다(0011 과 같다).
-- 위치 허용값·층 안 Main 설비 유일성은 서비스 검증(`services/floor_layout_mark.prepare_group_labels`)이 맡는다.
CREATE TABLE IF NOT EXISTS equipment_ops.floor_layout_group_label (
    building VARCHAR NOT NULL,
    floor_name VARCHAR NOT NULL,
    parent_equipment_id VARCHAR NOT NULL,
    label_position VARCHAR NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);
