-- Purpose: Space 층·FAB 도면 요소에 이름표 글자 크기·글자 색(비우면 자동·기본) 컬럼을 더한다.

-- 둘 다 NULL 허용이다(DuckDB 는 `ADD COLUMN` 에 NOT NULL·CHECK 를 받지 않는다 — 0008 참고). 이미
-- 저장된 요소는 NULL 로 읽혀 지금처럼 그린다 — 크기 NULL 은 「자동」(글자 요소는 상자에 맞추고 나머지는
-- 11px), 색 NULL 은 기본 글자색이다. 허용값(크기 9·11·13·16·20·24, 색은 영역 색 키)은 서비스 검증
-- (`services/floor_layout_mark.mark_font_size`·`mark_font_color`)이 맡는다 — 목록을 DDL 에 박지 않는다.
ALTER TABLE equipment_ops.floor_layout_mark
ADD COLUMN font_size INTEGER;

ALTER TABLE equipment_ops.floor_layout_mark
ADD COLUMN font_color VARCHAR;

ALTER TABLE equipment_ops.fab_layout_mark
ADD COLUMN font_size INTEGER;

ALTER TABLE equipment_ops.fab_layout_mark
ADD COLUMN font_color VARCHAR;
