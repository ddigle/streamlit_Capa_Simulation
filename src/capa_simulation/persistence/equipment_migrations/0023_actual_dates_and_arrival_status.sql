-- Purpose: 설비 마스터 스냅샷에 반입실적·반입상태·Qual실적 선택 컬럼을 추가한다.

-- 모두 빈칸을 허용하는 선택 값이라 NULL 허용으로 둔다(DuckDB 는 `ADD COLUMN` 에 NOT NULL·CHECK 를
-- 받지 않는다 — 0008 참고). 이미 쌓인 리비전은 모두 NULL 이고, 그것이 곧 「적지 않음」이다.
-- 반입상태의 허용값(계획·확정·완료·지연)과 실적의 날짜 규칙은 서비스 검증이 맡는다.
ALTER TABLE equipment_ops.equipment_master_snapshot
ADD COLUMN arrival_actual_date DATE;

ALTER TABLE equipment_ops.equipment_master_snapshot
ADD COLUMN arrival_status VARCHAR;

ALTER TABLE equipment_ops.equipment_master_snapshot
ADD COLUMN qual_actual_date DATE;
