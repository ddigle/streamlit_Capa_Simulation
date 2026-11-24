-- Purpose: 제품정보가 든 리비전 표 여덟과 데이터셋 짝 표에 CUSTOM 칸을 더하고 옛 행은 빈 값 표지로 둔다.

-- 옛 행은 원천에서 되채우지 않고 모두 빈 값 표지(`core_data_derivation.CUSTOM_BLANK`)다. 옛 원천은
-- 모든 행이 조회문 상수였고 복제 · 월 병합 · 연도 이동 시나리오는 원천이 0행이라, 되채우면 같은
-- 제품의 다른 부품 계획 행이 한 값으로 묶인다. 한 값이면 리비전 안 조인이 지금과 같아 숫자가 그대로다.
-- DEFAULT 는 칸을 더하는 동안만 두고 곧 걷는다 — 뒤에 CUSTOM 을 빠뜨린 저장이 조용히 표지로
-- 채워지지 않게 한다.

ALTER TABLE rev_data.rq_pkg_plan ADD COLUMN "CUSTOM" VARCHAR DEFAULT '-';
ALTER TABLE rev_data.rq_pkg_plan ALTER COLUMN "CUSTOM" DROP DEFAULT;
ALTER TABLE rev_data.rq_yld ADD COLUMN "CUSTOM" VARCHAR DEFAULT '-';
ALTER TABLE rev_data.rq_yld ALTER COLUMN "CUSTOM" DROP DEFAULT;
ALTER TABLE rev_data.rq_chip_qty ADD COLUMN "CUSTOM" VARCHAR DEFAULT '-';
ALTER TABLE rev_data.rq_chip_qty ALTER COLUMN "CUSTOM" DROP DEFAULT;
ALTER TABLE rev_data.rq_chip_eq ADD COLUMN "CUSTOM" VARCHAR DEFAULT '-';
ALTER TABLE rev_data.rq_chip_eq ALTER COLUMN "CUSTOM" DROP DEFAULT;
ALTER TABLE rev_data.rq_upeh ADD COLUMN "CUSTOM" VARCHAR DEFAULT '-';
ALTER TABLE rev_data.rq_upeh ALTER COLUMN "CUSTOM" DROP DEFAULT;
ALTER TABLE rev_data.rq_lot_ratio ADD COLUMN "CUSTOM" VARCHAR DEFAULT '-';
ALTER TABLE rev_data.rq_lot_ratio ALTER COLUMN "CUSTOM" DROP DEFAULT;
ALTER TABLE rev_data.rq_wf_ratio ADD COLUMN "CUSTOM" VARCHAR DEFAULT '-';
ALTER TABLE rev_data.rq_wf_ratio ALTER COLUMN "CUSTOM" DROP DEFAULT;
ALTER TABLE rev_data.rq_reqb ADD COLUMN "CUSTOM" VARCHAR DEFAULT '-';
ALTER TABLE rev_data.rq_reqb ALTER COLUMN "CUSTOM" DROP DEFAULT;

ALTER TABLE ref_data.rq_pkg_plan ADD COLUMN "CUSTOM" VARCHAR DEFAULT '-';
ALTER TABLE ref_data.rq_pkg_plan ALTER COLUMN "CUSTOM" DROP DEFAULT;
ALTER TABLE ref_data.rq_yld ADD COLUMN "CUSTOM" VARCHAR DEFAULT '-';
ALTER TABLE ref_data.rq_yld ALTER COLUMN "CUSTOM" DROP DEFAULT;
ALTER TABLE ref_data.rq_chip_qty ADD COLUMN "CUSTOM" VARCHAR DEFAULT '-';
ALTER TABLE ref_data.rq_chip_qty ALTER COLUMN "CUSTOM" DROP DEFAULT;
ALTER TABLE ref_data.rq_chip_eq ADD COLUMN "CUSTOM" VARCHAR DEFAULT '-';
ALTER TABLE ref_data.rq_chip_eq ALTER COLUMN "CUSTOM" DROP DEFAULT;
ALTER TABLE ref_data.rq_upeh ADD COLUMN "CUSTOM" VARCHAR DEFAULT '-';
ALTER TABLE ref_data.rq_upeh ALTER COLUMN "CUSTOM" DROP DEFAULT;
ALTER TABLE ref_data.rq_lot_ratio ADD COLUMN "CUSTOM" VARCHAR DEFAULT '-';
ALTER TABLE ref_data.rq_lot_ratio ALTER COLUMN "CUSTOM" DROP DEFAULT;
ALTER TABLE ref_data.rq_wf_ratio ADD COLUMN "CUSTOM" VARCHAR DEFAULT '-';
ALTER TABLE ref_data.rq_wf_ratio ALTER COLUMN "CUSTOM" DROP DEFAULT;
ALTER TABLE ref_data.rq_reqb ADD COLUMN "CUSTOM" VARCHAR DEFAULT '-';
ALTER TABLE ref_data.rq_reqb ALTER COLUMN "CUSTOM" DROP DEFAULT;
