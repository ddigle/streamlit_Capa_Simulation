# Purpose: 기준 정보 편집 그리드의 세션 칸·종류 id·호스트 key 상수를 둔다(UI 모름).

"""기준 정보 화면(`app_pages/reference_data.py`)이 범용 편집 그리드에 쓰는 이름 — 편집 표 횡전개
(2026-11-02 사용자 결정).

UI 를 모르는 모듈이라 `scenario_activation`(시나리오를 바꾸면 지울 칸)·`components/page_tabs`(떠나기
붙들기가 보는 호스트 key)가 화면 모듈을 거꾸로 import 하지 않고 이 이름을 읽는다.

- **종류 단추**(`DATASET_KEY` — 네이티브 `st.segmented_control`)는 옛 탭·안쪽 탭을 한 줄로
  편 것이다. 편집 표 9개 + 읽기 보기 둘(「설비대수 현황」·「STEP 구성」).
- **그리드 마운트는 하나**(`GRID_HOST`) — 종류를 바꿔도 같은 key·같은 자리라 다시 마운트되지
  않고 표만 바꿔 싣는다.
- **초안은 표마다 세션 칸**(`cells_key`·`history_key`) — 업무 키 + 월이라 그리지 않는 표의 편집도
  남고 줄 차례(공용 표시순서)만 바뀐 회차에도 같은 칸에 붙는다. 시나리오를 바꾸면 `SESSION_KEYS` 를
  지운다.
"""

from __future__ import annotations

from typing import Final

# 그리드 호스트 key — CCv2 key 라 `__` 를 쓰지 않는다(트리거 id 구분자).
GRID_HOST: Final = "reference_grid"
DATASET_KEY: Final = "reference_dataset"
# 읽기 보기(편집 표가 아닌 종류).
EQUIPMENT_OVERVIEW: Final = "EQP_OVERVIEW"
STEP_VIEW: Final = "STEP"
# 종류 id → 단추 글. 차례는 옛 탭 차례(UPEH · 설비대수 › 보유·대여·가용·현황 · 효율 · 여유율 · 일수
# · Lot측정률 · WF측정률 · STEP 구성)이고 기본은 UPEH 다. 단추 글에는 아이콘을 넣지 않는다 — 열한
# 개가 넓은 본문 한 줄에 들게.
DATASETS: Final[dict[str, str]] = {
    "RQ_UPEH": "UPEH",
    "RQ_EQP_OWN": "설비대수 보유",
    "RQ_EQP_LENT": "설비대수 대여",
    "RQ_EQP_AVBL": "설비대수 가용",
    EQUIPMENT_OVERVIEW: "설비대수 현황",
    "RQ_RUN_RATE": "효율",
    "RQ_VITAL": "여유율",
    "RQ_RUN_DAY": "일수",
    "RQ_LOT_RATIO": "Lot측정률",
    "RQ_WF_RATIO": "WF측정률",
    STEP_VIEW: "STEP 구성",
}
DEFAULT_DATASET: Final = "RQ_UPEH"
# 편집 표 아홉(읽기 보기 둘을 뺀 종류 id).
EDIT_TABLES: Final = tuple(
    dataset for dataset in DATASETS if dataset not in (EQUIPMENT_OVERVIEW, STEP_VIEW)
)
# 콜백이 쌓은 op(아직 반영 전), 마운트 → 마지막 seq(최근 8개), 마지막 토스트, 「편집 취소」 로
# 버린 이력 `gen`(그 직전에 보낸 op 를 알림 없이 버린다), 초안이 있는 표의 양식 지문(다른 화면의
# 적용이 그 표를 바꿨는지 가른다 — `app_pages/reference_data.py`).
INBOX_KEY: Final = "reference_grid_inbox"
APPLIED_KEY: Final = "reference_grid_applied"
TOAST_KEY: Final = "reference_grid_toast"
DISCARDED_KEY: Final = "reference_grid_discarded"
TEMPLATE_DIGESTS_KEY: Final = "reference_grid_template_digests"


def cells_key(table: str) -> str:
    """그 표의 초안 칸 — 고친 것이 없으면 None(또는 칸 없음)."""
    return f"reference_grid_cells__{table}"


def history_key(table: str) -> str:
    """그 표의 되돌리기 이력 칸(`gen`·undo·redo)."""
    return f"reference_grid_history__{table}"


# 시나리오를 바꾸면 지우는 칸 — 앞 시나리오 양식에 붙은 초안·이력과 아직 반영하지 않은 op.
SESSION_KEYS: Final = (
    *(cells_key(table) for table in EDIT_TABLES),
    *(history_key(table) for table in EDIT_TABLES),
    INBOX_KEY,
    APPLIED_KEY,
    TOAST_KEY,
    DISCARDED_KEY,
    TEMPLATE_DIGESTS_KEY,
)
