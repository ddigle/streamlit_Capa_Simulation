-- Purpose: 필요 단축 일정 진척 비교 기준선 머리에 그때 계획의 현재 일정 기준(Static · 설비 마스터) 칸을 더한다.

-- 기준선은 「기준선 저장」 을 누른 그때 계획을 얼린 것이다. 2026-11-20 부터 계획의 현재 일정은 두 기준
-- (Static 역산 · 설비 마스터 Qual일정) 가운데 하나라, 기준이 다른 지금 계획과 견주면 기준 차이가 진척으로
-- 읽힌다. 그래서 머리에 그때 기준을 남기고 진척 비교는 같은 기준의 지금 계획과 견준다.
-- NULL 허용 VARCHAR 이고 아무것도 옮기지 않는다 — 옛 기준선은 NULL 로 읽혀 「설비 마스터」 다. 허용값은
-- 서비스(`services/static_qual_schedule.basis_label`)가 본다(DuckDB 는 ADD COLUMN 에 CHECK 를 받지 않는다).
ALTER TABLE equipment_ops.shortening_baseline ADD COLUMN IF NOT EXISTS schedule_basis VARCHAR;
