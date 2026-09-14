-- Purpose: 설비 마스터 스냅샷에 공정 내 모델별 생산성 환산비를 추가한다.

-- 제약을 걸지 않는 것은 DuckDB 가 `ADD COLUMN` 에 NOT NULL·CHECK 를 아직 받지 않기
-- 때문이다(`Parser Error: Adding columns with constraints not yet supported`). 양수 검사는
-- `services/equipment_validation.prepare_equipment_master` 한 곳이 맡는다.
--
-- 이미 쌓인 리비전은 이 값이 없다. `DEFAULT 1.0` 이 채워 주지만, 프레임에 컬럼이 있고
-- 값이 NaN 이면 NULL 로 들어오므로 읽는 쪽도 1.0 으로 받는다(`_load_equipment_master`).
ALTER TABLE equipment_ops.equipment_master_snapshot
ADD COLUMN conversion_ratio DOUBLE DEFAULT 1.0;
