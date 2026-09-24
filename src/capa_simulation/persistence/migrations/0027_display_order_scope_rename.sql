-- Purpose: 표시순서 구분자를 실제 페이지·탭 이름으로 옮긴다.

-- `페이지 구분` 이 어느 것도 실제 페이지 이름이 아니었다(2026-09-24 확인). 호출부 일곱
-- 곳에 문자열이 흩어져 있어 화면 이름이 바뀌는 동안 아무도 따라오지 않았다.
--
-- 단순 개명이 아니다. **옛 구분자 하나가 여러 페이지에 걸쳐 있었다** — `공정별 Capa` 는
-- `기준 정보` 의 여섯 탭과 `산출 결과` 의 `대당 Capa` 를 한 통에 담았고, `공정별 확보율`
-- 도 두 페이지에 걸쳐 있었다. 그래서 `(옛 페이지, 탭)` 쌍마다 갈 곳을 따로 정한다.
--
-- **`표준 목표` 는 두 화면이 함께 쓴다.** `표준 목표` 와 `표준 대비 재공 현황` 이 같은
-- 목표 Capa 축을 보므로 규칙을 한 벌만 둔다(2026-09-24 사용자 결정). 나누면 같은 축의
-- 순서가 두 화면에서 조용히 갈라진다.
--
-- 대응은 `services/display_order_scopes.LEGACY_SCOPE_RENAMES` 와 글자까지 같아야 하고
-- `config/bootstrap_display_order.json` 도 같은 대응으로 옮겼다. 셋이 갈라지면 저장된
-- 규칙이 어느 탭에도 걸리지 않아 **조용히 무시된다** — 오류가 아니라 정렬만 기본값으로
-- 돌아가는 종류라 눈치채기 어렵다.
--
-- 이미 옮긴 값에는 다시 걸리지 않는다(옛 이름만 찾는다). 두 번 돌려도 결과가 같다.

UPDATE app_meta.global_display_order_rule
SET "페이지 구분" = '기준 정보'
WHERE "페이지 구분" = '공정별 Capa'
  AND "탭 구분" = 'Lot측정률';

UPDATE app_meta.global_display_order_rule
SET "페이지 구분" = '기준 정보'
WHERE "페이지 구분" = '공정별 Capa'
  AND "탭 구분" = 'UPEH';

UPDATE app_meta.global_display_order_rule
SET "페이지 구분" = '기준 정보'
WHERE "페이지 구분" = '공정별 Capa'
  AND "탭 구분" = 'WF측정률';

UPDATE app_meta.global_display_order_rule
SET "페이지 구분" = '산출 결과'
WHERE "페이지 구분" = '공정별 Capa'
  AND "탭 구분" = '대당 Capa';

UPDATE app_meta.global_display_order_rule
SET "페이지 구분" = '기준 정보'
WHERE "페이지 구분" = '공정별 Capa'
  AND "탭 구분" = '여유율';

UPDATE app_meta.global_display_order_rule
SET "페이지 구분" = '기준 정보'
WHERE "페이지 구분" = '공정별 Capa'
  AND "탭 구분" = '일수';

UPDATE app_meta.global_display_order_rule
SET "페이지 구분" = '기준 정보'
WHERE "페이지 구분" = '공정별 Capa'
  AND "탭 구분" = '효율';

UPDATE app_meta.global_display_order_rule
SET "페이지 구분" = '기준 정보'
WHERE "페이지 구분" = '공정별 확보율'
  AND "탭 구분" = '설비대수';

UPDATE app_meta.global_display_order_rule
SET "페이지 구분" = '산출 결과'
WHERE "페이지 구분" = '공정별 확보율'
  AND "탭 구분" = '소요대수';

UPDATE app_meta.global_display_order_rule
SET "페이지 구분" = '산출 결과'
WHERE "페이지 구분" = '공정별 확보율'
  AND "탭 구분" = '확보율';

UPDATE app_meta.global_display_order_rule
SET "페이지 구분" = '생산 계획'
WHERE "페이지 구분" = '부하량'
  AND "탭 구분" = 'PKG PLAN';

UPDATE app_meta.global_display_order_rule
SET "페이지 구분" = '생산 계획'
WHERE "페이지 구분" = '부하량'
  AND "탭 구분" = '수율';

UPDATE app_meta.global_display_order_rule
SET "페이지 구분" = '생산 계획'
WHERE "페이지 구분" = '부하량'
  AND "탭 구분" = '환산';

UPDATE app_meta.global_display_order_rule
SET "페이지 구분" = '표준 목표'
WHERE "페이지 구분" = '표준 목표 Capa'
  AND "탭 구분" = '목표 Capa';
