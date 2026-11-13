-- Purpose: Space 층 도면의 겹친 순서(호기끼리 그리는 차례 · 호기 위로 올린 영역 · 도형)를 공식 층 현행값으로 저장하는 표를 더한다.

-- 층 하나의 겹친 순서 — 도면 요소(0011)·Main 설비명 위치(0025)처럼 설비 리비전과 무관한 **공식** 층
-- 현행값이다(가정 설비 시나리오의 배치 차이(0031)에는 들지 않는다 — 가정 세션은 공식 순서를 읽기만
-- 한다). 행은 두 꼴이다.
-- - `item_kind = 'unit'`: 호기끼리 그리는 차례. `item_ref` 는 호기 키(설비명이 아니라 이름을 바꿔도
--   따라간다), `stack_no` 는 아래 → 위 1 부터다. 처음 순서를 바꿀 때 그 층 도면의 호기를 모두 적는다.
-- - `item_kind = 'raised'`: 호기 위 겹에 그리는 영역 · 도형. `item_ref` 는 요소 id, `stack_no` 는 0 이다.
--   위 겹 안의 차례는 요소 표의 그리는 순서(`source_row_no`) 그대로다 — 요소 차례는 한 곳에만 둔다.
-- 저장은 그 층 행 전체를 갈아 끼운다(DELETE + INSERT). 같은 트랜잭션에서 같은 키를 지웠다 다시 넣으므로
-- PK 를 두지 않는다(0011 · 0025 와 같다). 허용값 · 층 안 유일 · 개수 상한은 서비스 검증
-- (`services/floor_layout_stack.prepare_floor_stack`)이 맡는다 — DuckDB 는 CHECK 를 고칠 수 없다.
-- 처음에는 0행이고 아무것도 옮기지 않는다 — 행이 없는 층은 지금과 같이 그린다(호기는 설비 마스터 행
-- 차례, 영역 · 도형은 호기 아래).
CREATE TABLE IF NOT EXISTS equipment_ops.floor_layout_stack (
    building VARCHAR NOT NULL,
    floor_name VARCHAR NOT NULL,
    item_kind VARCHAR NOT NULL,
    item_ref VARCHAR NOT NULL,
    stack_no INTEGER NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);
