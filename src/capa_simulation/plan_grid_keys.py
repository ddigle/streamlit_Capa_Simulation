# Purpose: 생산 계획 편집 그리드(PKG PLAN · 수율)의 호스트 key · 세션 칸 이름을 둔다(UI 모름).

"""생산 계획 화면(`app_pages/load_conversion.py`)이 범용 편집 그리드에 쓰는 이름 — 2026-11-12 시안
보드 답 k-a1 · k-a2(기준 정보와 같은 편집기를 생산 계획에도).

UI 를 모르는 모듈이라 `scenario_activation`(시나리오를 바꾸면 지울 칸)·`components/page_tabs`(떠나기
붙들기가 보는 호스트 key)가 화면 모듈을 거꾸로 import 하지 않고 이 이름을 읽는다.

- **탭마다 그리드 하나**(PKG PLAN · 수율) — 마운트 key 는 표마다 따로라 탭을 오가도 다시 마운트되지
  않는다.
- **초안은 표마다 세션 칸**(`cells_key` · `history_key`) — 업무 키 + 월이라 줄 차례(공용 표시순서)만
  바뀐 회차에도 같은 칸에 붙는다. 출납 받은 칸(`inbox` · `applied` · `toast` · `discarded`)도 표마다
  따로다 — 한 탭의 토스트가 다른 탭 그리드에 서지 않는다.
"""

from __future__ import annotations

from typing import Final

PLAN_TABLE: Final = "RQ_PKG_PLAN"
YIELD_TABLE: Final = "RQ_YLD"
TABLES: Final = (PLAN_TABLE, YIELD_TABLE)
# 그리드 호스트 key — CCv2 key 라 `__` 를 쓰지 않는다(트리거 id 구분자).
HOSTS: Final = {PLAN_TABLE: "plan_grid", YIELD_TABLE: "yield_grid"}


def cells_key(table: str) -> str:
    """그 표의 초안 칸 — 고친 것이 없으면 None(또는 칸 없음)."""
    return f"plan_grid_cells__{table}"


def history_key(table: str) -> str:
    """그 표의 되돌리기 이력 칸(`gen`·undo·redo)."""
    return f"plan_grid_history__{table}"


def inbox_key(table: str) -> str:
    """콜백이 쌓은 op(아직 반영 전)."""
    return f"plan_grid_inbox__{table}"


def applied_key(table: str) -> str:
    """마운트 → 마지막 seq."""
    return f"plan_grid_applied__{table}"


def toast_key(table: str) -> str:
    """마지막 토스트(번호는 세션 동안 오르기만 한다 — 시나리오를 바꿔도 지우지 않는다)."""
    return f"plan_grid_toast__{table}"


def discarded_key(table: str) -> str:
    """「편집 취소」 로 버린 이력 `gen` — 그 직전에 보낸 op 를 알림 없이 버린다."""
    return f"plan_grid_discarded__{table}"


def last_key(table: str) -> str:
    """그 표에 마지막으로 보낸 (껍데기, feed) — 닫힌 탭 회차에 그대로 다시 보낸다(보기 상태라
    시나리오를 바꿔도 지우지 않는다 — 열면 지금 표로 바뀐다)."""
    return f"plan_grid_last__{table}"


# 이 세션에 그리드를 세운 표 — 한 번도 연 적 없는 탭은 그리드(등록 JS · CSS 를 싣는 무거운 요소)를
# 세우지 않는다. 보기 상태라 시나리오를 바꿔도 지우지 않는다.
MOUNTED_KEY: Final = "plan_grid_mounted"
# 초안이 있는 표의 양식 지문 — 다른 화면의 적용이 그 표를 바꿨는지 가른다(`app_pages/
# load_conversion.py` — 기준 정보 `reference_grid_keys.TEMPLATE_DIGESTS_KEY` 와 같은 꼴).
TEMPLATE_DIGESTS_KEY: Final = "plan_grid_template_digests"


# 시나리오를 바꾸면 지우는 칸 — 앞 시나리오 양식에 붙은 초안·이력과 아직 반영하지 않은 op, 그 양식
# 지문. 토스트 칸은 넣지 않는다(`reference_grid_keys.SESSION_KEYS` 와 같은 까닭).
SESSION_KEYS: Final = (
    *(
        key
        for table in TABLES
        for key in (
            cells_key(table),
            history_key(table),
            inbox_key(table),
            applied_key(table),
            discarded_key(table),
        )
    ),
    TEMPLATE_DIGESTS_KEY,
)
