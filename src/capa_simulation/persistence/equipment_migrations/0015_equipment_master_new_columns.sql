-- Purpose: 설비 마스터 스냅샷에 투자Capa·반입/Qual 이력·메모1~3 선택 컬럼을 추가한다.

-- 모두 빈칸을 허용하는 글자 값이라 NULL 허용으로 둔다(DuckDB 는 `ADD COLUMN` 에 NOT NULL·CHECK 를
-- 받지 않는다 — 0008 참고). 이미 쌓인 리비전은 모두 NULL 이고, 그것이 곧 「적지 않음」이다.
--
-- 옛 `투자기준` 을 담던 `investment_basis` 는 지우지 않는다. 계약에서 빠져 읽지도 쓰지도 않지만
-- 되살릴 수 있게 값을 남긴다. `투자Capa` 는 그 값을 이어받지 않는 별개의 컬럼이다.
ALTER TABLE equipment_ops.equipment_master_snapshot
ADD COLUMN investment_capa VARCHAR;

ALTER TABLE equipment_ops.equipment_master_snapshot
ADD COLUMN arrival_qual_history VARCHAR;

ALTER TABLE equipment_ops.equipment_master_snapshot
ADD COLUMN memo_1 VARCHAR;

ALTER TABLE equipment_ops.equipment_master_snapshot
ADD COLUMN memo_2 VARCHAR;

ALTER TABLE equipment_ops.equipment_master_snapshot
ADD COLUMN memo_3 VARCHAR;
