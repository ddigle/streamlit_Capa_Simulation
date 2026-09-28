-- Purpose: 설비 마스터 스냅샷에 모듈 행을 설비 한 대로 묶는 모체호기를 추가한다.

-- 모듈로 관리하는 공정(CoW Bonder 등)은 설비 한 대를 모듈마다 한 행으로 적고, 같은 설비의
-- 행에 이 값을 똑같이 적어 묶는다. 비모듈 행은 NULL 이다 — 행 하나가 설비 한 대다.
--
-- 이미 쌓인 리비전은 모두 NULL 이 되고, 그것이 곧 「모듈 묶음 없음」이라 옛 리비전의 대수는
-- 바뀌지 않는다. 묶음 규칙(설비 행과 모듈 행의 충돌, 모듈끼리 같아야 하는 컬럼)은
-- `services/equipment_validation.prepare_equipment_master` 한 곳이 맡는다.
ALTER TABLE equipment_ops.equipment_master_snapshot
ADD COLUMN parent_equipment_id VARCHAR;
