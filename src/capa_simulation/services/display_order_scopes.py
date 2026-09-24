# Purpose: 표시순서 규칙이 어느 페이지·어느 탭에 걸리는지를 한 곳에서 선언한다.

"""**구분자를 문자열 리터럴로 흩어 두면 화면 이름과 조용히 갈라진다.**

표시순서 규칙은 `(페이지 구분, 탭 구분)` 두 값으로 범위를 정하고, 관리 화면은 그 둘을
차례로 골라 규칙을 보여 준다(`components/display_order_management.py`). 그런데 그 값이
`apply_display_order(...)` 호출부 일곱 곳에 리터럴로 적혀 있었고, 화면 이름이 바뀌는
동안 아무도 따라오지 않아 **어느 것도 실제 페이지 이름이 아니게 됐다**(2026-09-24 확인).

더 나빴던 것은 한 구분자가 **여러 페이지에 걸쳐 있었다**는 점이다. `공정별 Capa` 는
`기준 정보` 의 여섯 탭과 `산출 결과` 의 `대당 Capa` 를 한 통에 담고 있었다. 관리 화면에서
「페이지」를 고르면 다른 페이지의 탭이 함께 나오니, 이름만 고쳐서는 맞출 수 없었다.

여기서 **페이지 이름과 탭 이름을 그대로** 선언하고 호출부가 이것만 쓴다.
`tests/test_display_order_scopes.py` 가 실제 페이지 제목·탭 이름과 대조하므로, 화면
이름을 바꾸면 그 검사가 먼저 걸린다.

**`표준 목표` 는 두 화면이 함께 쓴다.** `표준 목표` 와 `표준 대비 재공 현황` 이 같은
목표 Capa 축을 보므로 규칙을 한 벌만 둔다(2026-09-24 사용자 결정 A안). 나누면 같은 축의
순서가 두 화면에서 조용히 갈라진다.
"""

from __future__ import annotations

from typing import Final

# 페이지 구분 — `navigation.py` 의 페이지 제목과 **글자까지 같아야 한다.**
PAGE_PLAN: Final = "생산 계획"
PAGE_REFERENCE: Final = "기준 정보"
PAGE_CALCULATION: Final = "산출 결과"
PAGE_STANDARD_TARGET: Final = "표준 목표"

# 탭 구분 — 각 페이지의 `TAB_NAMES` 와 같아야 한다(아이콘 접두어는 뺀 이름).
TAB_UPEH: Final = "UPEH"
TAB_EQUIPMENT_COUNT: Final = "설비대수"
TAB_RUN_RATE: Final = "효율"
TAB_VITAL: Final = "여유율"
TAB_RUN_DAY: Final = "일수"
TAB_LOT_RATIO: Final = "Lot측정률"
TAB_WF_RATIO: Final = "WF측정률"
TAB_UNIT_CAPACITY: Final = "대당 Capa"
TAB_REQUIRED: Final = "소요대수"
TAB_SECUREMENT: Final = "확보율"
TAB_CONVERSION: Final = "환산"
TAB_PKG_PLAN: Final = "PKG PLAN"
TAB_YIELD: Final = "수율"
TAB_TARGET_CAPACITY: Final = "목표 Capa"

# 쓰이는 조합 전부. 검사가 이 목록을 실제 화면과 맞댄다.
DISPLAY_ORDER_SCOPES: Final[tuple[tuple[str, str], ...]] = (
    (PAGE_PLAN, TAB_CONVERSION),
    (PAGE_PLAN, TAB_PKG_PLAN),
    (PAGE_PLAN, TAB_YIELD),
    (PAGE_REFERENCE, TAB_UPEH),
    (PAGE_REFERENCE, TAB_EQUIPMENT_COUNT),
    (PAGE_REFERENCE, TAB_RUN_RATE),
    (PAGE_REFERENCE, TAB_VITAL),
    (PAGE_REFERENCE, TAB_RUN_DAY),
    (PAGE_REFERENCE, TAB_LOT_RATIO),
    (PAGE_REFERENCE, TAB_WF_RATIO),
    (PAGE_CALCULATION, TAB_UNIT_CAPACITY),
    (PAGE_CALCULATION, TAB_REQUIRED),
    (PAGE_CALCULATION, TAB_SECUREMENT),
    (PAGE_STANDARD_TARGET, TAB_TARGET_CAPACITY),
)

# 옛 구분자 → 지금 구분자. **탭 이름은 그대로이고 페이지 이름만 바뀐다** — 옛 페이지
# 구분 하나가 두 페이지로 나뉘므로 탭까지 함께 봐야 어디로 가는지 정해진다.
#
# `0027_display_order_scope_rename.sql` 과 `config/bootstrap_display_order.json` 이 같은
# 대응을 쓴다. 셋이 갈라지면 저장된 규칙이 어느 탭에도 걸리지 않아 **조용히 무시된다** —
# 오류가 아니라 정렬만 기본값으로 돌아가는 종류다.
LEGACY_SCOPE_RENAMES: Final[dict[tuple[str, str], tuple[str, str]]] = {
    ("공정별 Capa", TAB_UPEH): (PAGE_REFERENCE, TAB_UPEH),
    ("공정별 Capa", TAB_RUN_RATE): (PAGE_REFERENCE, TAB_RUN_RATE),
    ("공정별 Capa", TAB_VITAL): (PAGE_REFERENCE, TAB_VITAL),
    ("공정별 Capa", TAB_RUN_DAY): (PAGE_REFERENCE, TAB_RUN_DAY),
    ("공정별 Capa", TAB_LOT_RATIO): (PAGE_REFERENCE, TAB_LOT_RATIO),
    ("공정별 Capa", TAB_WF_RATIO): (PAGE_REFERENCE, TAB_WF_RATIO),
    ("공정별 Capa", TAB_UNIT_CAPACITY): (PAGE_CALCULATION, TAB_UNIT_CAPACITY),
    ("공정별 확보율", TAB_EQUIPMENT_COUNT): (PAGE_REFERENCE, TAB_EQUIPMENT_COUNT),
    ("공정별 확보율", TAB_REQUIRED): (PAGE_CALCULATION, TAB_REQUIRED),
    ("공정별 확보율", TAB_SECUREMENT): (PAGE_CALCULATION, TAB_SECUREMENT),
    ("부하량", TAB_CONVERSION): (PAGE_PLAN, TAB_CONVERSION),
    ("부하량", TAB_PKG_PLAN): (PAGE_PLAN, TAB_PKG_PLAN),
    ("부하량", TAB_YIELD): (PAGE_PLAN, TAB_YIELD),
    ("표준 목표 Capa", TAB_TARGET_CAPACITY): (PAGE_STANDARD_TARGET, TAB_TARGET_CAPACITY),
}
