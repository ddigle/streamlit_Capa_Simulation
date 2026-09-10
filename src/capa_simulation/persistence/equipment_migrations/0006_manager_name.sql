-- Purpose: 설비 마스터 스냅샷에 담당자 컬럼을 추가한다.
ALTER TABLE equipment_ops.equipment_master_snapshot
ADD COLUMN manager_name VARCHAR;
