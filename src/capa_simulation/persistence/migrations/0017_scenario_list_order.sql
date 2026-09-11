-- Purpose: 시나리오 목록의 사용자 지정 누적 순서를 담고 남아 있던 보관 상태를 활성으로 되돌린다.

ALTER TABLE app_meta.scenario ADD COLUMN IF NOT EXISTS list_order BIGINT;

UPDATE app_meta.scenario SET status = 'ACTIVE' WHERE status <> 'ACTIVE';
UPDATE app_meta.dataset SET status = 'READY' WHERE status = 'ARCHIVED';
