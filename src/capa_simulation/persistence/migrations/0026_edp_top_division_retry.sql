-- Purpose: 0014 가 놓친 EDP-TSV 행의 `WF 구분` `TOP` 을 `Top_e` 로 다시 맞춘다.

-- `build_q_core_data` 가 EDP-TSV 의 Top 을 `Top_e` 로 가르기 전에 적재된 기준정보·리비전
-- 스냅샷만 옛 값을 들고 있다. 같은 조인 키가 두 이름으로 갈리면 수율·Chip·경로가 조용히
-- 안 붙는다. `0014` 가 그 일을 하려다 **운영 데이터에서 한 행도 바꾸지 못했다.**
--
-- 놓친 까닭이 둘인데 크기가 다르다.
--
--   (1) **대소문자.** 원천 `WF 구분` 표기는 대문자 `TOP` 인데(2026-09-18 사용자 확인,
--       AGENTS.md 「product_type」 절) `0014` 는 `trim("WF 구분") = 'Top'` 으로 맞댔다.
--       이 하나로 두 형태 모두 0행이 된다 — **이것이 주 원인이다.** 로컬 합성 표본만
--       `Top` 이라 검사도 조용히 통과했다.
--   (2) **제품명 표기.** 두 번째 형태는 원천 이름을 파생 표에 직접 붙이는데, 파생 단계가
--       `제품정보` 를 정규화한다(`services/core_data_derivation.py`). 이름에 `_` 나 `*_`
--       가 있는 제품에서 조인이 빗나간다. (1) 이 고쳐져야 비로소 드러나는 **부차 원인**이다.
--
-- 적용된 마이그레이션은 버전으로 체크섬을 대조하므로 `0014` 를 고칠 수 없다. 새 번호로
-- 다시 한다. 여기서 고치는 것은 셋이고, 셋 다 `scripts/inspect_top_remigration.py` 의
-- 모의 계산과 **같은 식**을 쓴다 — 사내가 먼저 재는 수와 실제로 바뀌는 수가 갈리면
-- 「크게 다르면 멈춘다」는 사전 점검이 쓸모없어진다.
--
--   (a) 값 대조를 **대소문자로 가리지 않는다.** `upper(trim(...))` 로 줄여 맞댄다.
--       `WF 구분` 은 `'TOP'`, `제품타입` 은 `'EDP-TSV'` 와 맞댄다. 앱 쪽 대조가 지나는
--       `frame_contracts.match_key`(strip + casefold)와 같은 규칙이다.
--   (b) 조인 전에 파생과 **같은 정규화**를 건다. NBSP → ' ', `*_` → ' ', `_` → ' ',
--       연속 공백 → 한 칸, 앞뒤 공백 제거. NBSP 를 따로 바꾸는 것은 DuckDB 의 RE2 에서
--       `\s` 가 ASCII 공백만 뜻해 NBSP 를 잡지 못하기 때문이다 — 파이썬 `re` 는 잡으므로
--       그 한 글자에서 파생과 갈린다.
--   (c) **한 제품이 한 타입일 때만 바꾼다.** 원천에 `제품타입` 이 비거나 공백뿐인 행이
--       있고(사내 실측 37개), 제품 단위로 판별하면서 걸러 내지 않으면 같은 제품의 HBM
--       행까지 함께 바뀐다 — 되돌릴 수 없는 오염이다. 세 뷰가 그 자리다.
--
-- **쓰는 값은 `Top_e` 그대로다.** 원천에 없는 이름이라 앱이 표기까지 정한다
-- (`services/product_type.EDP_TOP_DIVISION`). 나머지 행은 원천 표기를 그대로 둔다 —
-- `TOP` 은 `TOP` 으로 남는다.
--
-- **두 번 돌려도 결과가 같다.** 이미 바뀐 행은 `Top_e` 라 `upper(trim(...)) = 'TOP'` 에
-- 걸리지 않는다(`TOP_E` ≠ `TOP`).
--
-- 예상 변경 규모: 사내 모의 계산 40,484행은 **계획 형태만** 센 수다
-- (`inspect_top_remigration.py` §4 가 그 형태만 돌았다). 이 파일은 원천 형태도 돌므로
-- 사내에서 실제로 바뀌는 수는 그보다 **크거나 같다.** 적용 전에 갱신된 스크립트로 다시
-- 재고, 두 수가 크게 다르면 적용하지 말고 리뷰 문서로 낸다.

-- 원천 제품명을 파생과 같은 규칙으로 정규화한 뒤, **한 타입뿐인 EDP-TSV 제품**만 남긴다.
CREATE OR REPLACE TEMP VIEW _edp_source_products AS
SELECT
    trim(regexp_replace(
        replace(replace(replace("제품정보", chr(160), ' '), '*_', ' '), '_', ' '),
        '\s+', ' ', 'g'
    )) AS "제품정보"
FROM raw_data.core_data
WHERE "제품타입" IS NOT NULL
  AND trim("제품타입") <> ''
GROUP BY 1
HAVING count(DISTINCT upper(trim("제품타입"))) = 1
   AND min(upper(trim("제품타입"))) = 'EDP-TSV';

-- 계획에 적힌 EDP-TSV 제품. `제품정보` 는 이미 파생 이름이라 정규화하지 않는다.
-- 한 데이터셋 안에서 타입이 갈리는 제품은 판별할 수 없으므로 빠진다.
CREATE OR REPLACE TEMP VIEW _edp_plan_products AS
SELECT dataset_id, "제품정보"
FROM ref_data.rq_pkg_plan
WHERE "제품타입" IS NOT NULL
  AND trim("제품타입") <> ''
GROUP BY dataset_id, "제품정보"
HAVING count(DISTINCT upper(trim("제품타입"))) = 1
   AND min(upper(trim("제품타입"))) = 'EDP-TSV';

CREATE OR REPLACE TEMP VIEW _edp_plan_products_rev AS
SELECT revision_id, "제품정보"
FROM rev_data.rq_pkg_plan
WHERE "제품타입" IS NOT NULL
  AND trim("제품타입") <> ''
GROUP BY revision_id, "제품정보"
HAVING count(DISTINCT upper(trim("제품타입"))) = 1
   AND min(upper(trim("제품타입"))) = 'EDP-TSV';

-- -------------------------------------------------------------------------
-- ref_data — 계획에 있는 제품, 계획에 없는 제품 두 벌씩.
-- -------------------------------------------------------------------------
-- ref_data.rq_chip_eq
UPDATE ref_data.rq_chip_eq AS target
SET "WF 구분" = 'Top_e'
FROM _edp_plan_products AS edp
WHERE target.dataset_id = edp.dataset_id
  AND target."제품정보" = edp."제품정보"
  AND upper(trim(target."WF 구분")) = 'TOP';

-- 계획에 없는 제품은 원천 매핑으로 한 번 더 훑는다.
UPDATE ref_data.rq_chip_eq AS target
SET "WF 구분" = 'Top_e'
FROM _edp_source_products AS mapped
WHERE target."제품정보" = mapped."제품정보"
  AND upper(trim(target."WF 구분")) = 'TOP';

-- ref_data.rq_chip_qty
UPDATE ref_data.rq_chip_qty AS target
SET "WF 구분" = 'Top_e'
FROM _edp_plan_products AS edp
WHERE target.dataset_id = edp.dataset_id
  AND target."제품정보" = edp."제품정보"
  AND upper(trim(target."WF 구분")) = 'TOP';

-- 계획에 없는 제품은 원천 매핑으로 한 번 더 훑는다.
UPDATE ref_data.rq_chip_qty AS target
SET "WF 구분" = 'Top_e'
FROM _edp_source_products AS mapped
WHERE target."제품정보" = mapped."제품정보"
  AND upper(trim(target."WF 구분")) = 'TOP';

-- ref_data.rq_lot_ratio
UPDATE ref_data.rq_lot_ratio AS target
SET "WF 구분" = 'Top_e'
FROM _edp_plan_products AS edp
WHERE target.dataset_id = edp.dataset_id
  AND target."제품정보" = edp."제품정보"
  AND upper(trim(target."WF 구분")) = 'TOP';

-- 계획에 없는 제품은 원천 매핑으로 한 번 더 훑는다.
UPDATE ref_data.rq_lot_ratio AS target
SET "WF 구분" = 'Top_e'
FROM _edp_source_products AS mapped
WHERE target."제품정보" = mapped."제품정보"
  AND upper(trim(target."WF 구분")) = 'TOP';

-- ref_data.rq_reqb
UPDATE ref_data.rq_reqb AS target
SET "WF 구분" = 'Top_e'
FROM _edp_plan_products AS edp
WHERE target.dataset_id = edp.dataset_id
  AND target."제품정보" = edp."제품정보"
  AND upper(trim(target."WF 구분")) = 'TOP';

-- 계획에 없는 제품은 원천 매핑으로 한 번 더 훑는다.
UPDATE ref_data.rq_reqb AS target
SET "WF 구분" = 'Top_e'
FROM _edp_source_products AS mapped
WHERE target."제품정보" = mapped."제품정보"
  AND upper(trim(target."WF 구분")) = 'TOP';

-- ref_data.rq_upeh
UPDATE ref_data.rq_upeh AS target
SET "WF 구분" = 'Top_e'
FROM _edp_plan_products AS edp
WHERE target.dataset_id = edp.dataset_id
  AND target."제품정보" = edp."제품정보"
  AND upper(trim(target."WF 구분")) = 'TOP';

-- 계획에 없는 제품은 원천 매핑으로 한 번 더 훑는다.
UPDATE ref_data.rq_upeh AS target
SET "WF 구분" = 'Top_e'
FROM _edp_source_products AS mapped
WHERE target."제품정보" = mapped."제품정보"
  AND upper(trim(target."WF 구분")) = 'TOP';

-- ref_data.rq_wf_ratio
UPDATE ref_data.rq_wf_ratio AS target
SET "WF 구분" = 'Top_e'
FROM _edp_plan_products AS edp
WHERE target.dataset_id = edp.dataset_id
  AND target."제품정보" = edp."제품정보"
  AND upper(trim(target."WF 구분")) = 'TOP';

-- 계획에 없는 제품은 원천 매핑으로 한 번 더 훑는다.
UPDATE ref_data.rq_wf_ratio AS target
SET "WF 구분" = 'Top_e'
FROM _edp_source_products AS mapped
WHERE target."제품정보" = mapped."제품정보"
  AND upper(trim(target."WF 구분")) = 'TOP';

-- ref_data.rq_yld
UPDATE ref_data.rq_yld AS target
SET "WF 구분" = 'Top_e'
FROM _edp_plan_products AS edp
WHERE target.dataset_id = edp.dataset_id
  AND target."제품정보" = edp."제품정보"
  AND upper(trim(target."WF 구분")) = 'TOP';

-- 계획에 없는 제품은 원천 매핑으로 한 번 더 훑는다.
UPDATE ref_data.rq_yld AS target
SET "WF 구분" = 'Top_e'
FROM _edp_source_products AS mapped
WHERE target."제품정보" = mapped."제품정보"
  AND upper(trim(target."WF 구분")) = 'TOP';

-- -------------------------------------------------------------------------
-- rev_data — 계획에 있는 제품, 계획에 없는 제품 두 벌씩.
-- -------------------------------------------------------------------------
-- rev_data.rq_chip_eq
UPDATE rev_data.rq_chip_eq AS target
SET "WF 구분" = 'Top_e'
FROM _edp_plan_products_rev AS edp
WHERE target.revision_id = edp.revision_id
  AND target."제품정보" = edp."제품정보"
  AND upper(trim(target."WF 구분")) = 'TOP';

-- 계획에 없는 제품은 원천 매핑으로 한 번 더 훑는다.
UPDATE rev_data.rq_chip_eq AS target
SET "WF 구분" = 'Top_e'
FROM _edp_source_products AS mapped
WHERE target."제품정보" = mapped."제품정보"
  AND upper(trim(target."WF 구분")) = 'TOP';

-- rev_data.rq_chip_qty
UPDATE rev_data.rq_chip_qty AS target
SET "WF 구분" = 'Top_e'
FROM _edp_plan_products_rev AS edp
WHERE target.revision_id = edp.revision_id
  AND target."제품정보" = edp."제품정보"
  AND upper(trim(target."WF 구분")) = 'TOP';

-- 계획에 없는 제품은 원천 매핑으로 한 번 더 훑는다.
UPDATE rev_data.rq_chip_qty AS target
SET "WF 구분" = 'Top_e'
FROM _edp_source_products AS mapped
WHERE target."제품정보" = mapped."제품정보"
  AND upper(trim(target."WF 구분")) = 'TOP';

-- rev_data.rq_lot_ratio
UPDATE rev_data.rq_lot_ratio AS target
SET "WF 구분" = 'Top_e'
FROM _edp_plan_products_rev AS edp
WHERE target.revision_id = edp.revision_id
  AND target."제품정보" = edp."제품정보"
  AND upper(trim(target."WF 구분")) = 'TOP';

-- 계획에 없는 제품은 원천 매핑으로 한 번 더 훑는다.
UPDATE rev_data.rq_lot_ratio AS target
SET "WF 구분" = 'Top_e'
FROM _edp_source_products AS mapped
WHERE target."제품정보" = mapped."제품정보"
  AND upper(trim(target."WF 구분")) = 'TOP';

-- rev_data.rq_reqb
UPDATE rev_data.rq_reqb AS target
SET "WF 구분" = 'Top_e'
FROM _edp_plan_products_rev AS edp
WHERE target.revision_id = edp.revision_id
  AND target."제품정보" = edp."제품정보"
  AND upper(trim(target."WF 구분")) = 'TOP';

-- 계획에 없는 제품은 원천 매핑으로 한 번 더 훑는다.
UPDATE rev_data.rq_reqb AS target
SET "WF 구분" = 'Top_e'
FROM _edp_source_products AS mapped
WHERE target."제품정보" = mapped."제품정보"
  AND upper(trim(target."WF 구분")) = 'TOP';

-- rev_data.rq_upeh
UPDATE rev_data.rq_upeh AS target
SET "WF 구분" = 'Top_e'
FROM _edp_plan_products_rev AS edp
WHERE target.revision_id = edp.revision_id
  AND target."제품정보" = edp."제품정보"
  AND upper(trim(target."WF 구분")) = 'TOP';

-- 계획에 없는 제품은 원천 매핑으로 한 번 더 훑는다.
UPDATE rev_data.rq_upeh AS target
SET "WF 구분" = 'Top_e'
FROM _edp_source_products AS mapped
WHERE target."제품정보" = mapped."제품정보"
  AND upper(trim(target."WF 구분")) = 'TOP';

-- rev_data.rq_wf_ratio
UPDATE rev_data.rq_wf_ratio AS target
SET "WF 구분" = 'Top_e'
FROM _edp_plan_products_rev AS edp
WHERE target.revision_id = edp.revision_id
  AND target."제품정보" = edp."제품정보"
  AND upper(trim(target."WF 구분")) = 'TOP';

-- 계획에 없는 제품은 원천 매핑으로 한 번 더 훑는다.
UPDATE rev_data.rq_wf_ratio AS target
SET "WF 구분" = 'Top_e'
FROM _edp_source_products AS mapped
WHERE target."제품정보" = mapped."제품정보"
  AND upper(trim(target."WF 구분")) = 'TOP';

-- rev_data.rq_yld
UPDATE rev_data.rq_yld AS target
SET "WF 구분" = 'Top_e'
FROM _edp_plan_products_rev AS edp
WHERE target.revision_id = edp.revision_id
  AND target."제품정보" = edp."제품정보"
  AND upper(trim(target."WF 구분")) = 'TOP';

-- 계획에 없는 제품은 원천 매핑으로 한 번 더 훑는다.
UPDATE rev_data.rq_yld AS target
SET "WF 구분" = 'Top_e'
FROM _edp_source_products AS mapped
WHERE target."제품정보" = mapped."제품정보"
  AND upper(trim(target."WF 구분")) = 'TOP';

-- 뷰는 세션에 남기지 않는다.
DROP VIEW IF EXISTS _edp_plan_products_rev;
DROP VIEW IF EXISTS _edp_plan_products;
DROP VIEW IF EXISTS _edp_source_products;
