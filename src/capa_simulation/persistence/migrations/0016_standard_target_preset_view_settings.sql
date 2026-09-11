-- Purpose: 표준 목표 Capa 「조회·집계 설정」을 리비전 프리셋 스칼라 컬럼으로 저장한다.

ALTER TABLE app_meta.scenario_preset ADD COLUMN IF NOT EXISTS standard_target_start_date DATE;
ALTER TABLE app_meta.scenario_preset ADD COLUMN IF NOT EXISTS standard_target_end_date DATE;
ALTER TABLE app_meta.scenario_preset ADD COLUMN IF NOT EXISTS standard_target_show_detail BOOLEAN;
ALTER TABLE app_meta.scenario_preset ADD COLUMN IF NOT EXISTS standard_target_detail_level VARCHAR;
ALTER TABLE app_meta.scenario_preset ADD COLUMN IF NOT EXISTS standard_target_output_metric VARCHAR;
