-- Purpose: Space 층·FAB 도면 요소와 가정 배치 차이 행에 요소 모양 값(화살표 머리·선·뒤집기 — 정규 JSON 글) 칸을 더한다.

-- 도면 요소의 모양 값(`look_json`, 2026-11-03 사용자 요청 — U자 베이 화살표·화살표 머리 크기)을 층·FAB 요소 표와
-- 가정 설비 시나리오의 요소 차이 표(0031)에 NULL 허용 글 칸 하나로 더한다(DuckDB 는 `ADD COLUMN` 에 NOT NULL·CHECK 를
-- 받지 않는다 — 0017·0025 와 같다). 값은 처음 값이 아닌 키만 든 정규 JSON(키 차례대로, 빈칸 없음)이고 NULL 은 모두 처음
-- 값이다 — 이미 저장된 요소는 NULL 로 읽혀 지금 모습으로 그린다. 받는 키·값은 종류마다 다르고 서비스 검증
-- (`services/floor_layout_mark.mark_look`)이 맡는다 — 목록을 DDL 에 박지 않는다. 종류가 늘어도 이 칸 하나로 담는다.
ALTER TABLE equipment_ops.floor_layout_mark
ADD COLUMN look_json VARCHAR;

ALTER TABLE equipment_ops.fab_layout_mark
ADD COLUMN look_json VARCHAR;

ALTER TABLE equipment_ops.equipment_schedule_layout_mark
ADD COLUMN look_json VARCHAR;
