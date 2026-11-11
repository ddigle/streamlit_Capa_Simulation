# Purpose: 시나리오 목록 관리 초안의 세션 칸과 탭 줄 · 변경 칩이 읽는 판정을 등록 없이 둔다.

"""목록 관리 초안의 세션 칸(`services/scenario_list_edits.ListDraft`).

표 컴포넌트 모듈(`scenario_list_grid`)은 읽을 때 등록하므로 화면 탭 줄 · 변경 칩이 부르지 않는다 —
탭 줄이 읽는 것은 이 모듈뿐이고 세션만 본다(DB 없음). 초안은 세션이 끝나면 사라지고, 칸을 고치는
동안 회차가 돌아 탭 점 · 변경 칩이 바로 바뀐다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final
from uuid import uuid4

import streamlit as st

from capa_simulation.services.scenario_list_edits import (
    ListDraft,
    edit_count,
    has_edits,
    rebased_for_created,
)

if TYPE_CHECKING:
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

DRAFT_KEY: Final = "scenario_list_draft"
# 지난 회차에 그린 저장 차례 — `move` 의 `token` 을 대조하고 처음 옮길 때의 `order_base` 가 된다.
SHOWN_ORDER_KEY: Final = "scenario_list_shown_order"
# 네 마운트 key — 화면 탭 줄의 떠나기 붙들기(`page_tabs.EDIT_HOST_KEYS`)도 읽는다. 「점검」 칸의
# 리비전 표(`CHECKS_KEY`)는 이름을 고치지 않고 고름만 보낸다 — 「상세」 칸 리비전 표와 같은
# 고름이다.
TABLE_KEY: Final = "scenario_list_table"
REVISIONS_KEY: Final = "scenario_list_revisions"
CHANGES_KEY: Final = "scenario_list_changes"
CHECKS_KEY: Final = "scenario_list_checks"
MOUNT_KEYS: Final = (TABLE_KEY, REVISIONS_KEY, CHANGES_KEY, CHECKS_KEY)
# 오른쪽 칸 고르기 · 받기 콜백이 고른 칸 — 맨 위 알림 칸이 표 모듈을 읽지 않고 본다(이름은
# `scenario_list_grid.LIST_SIDE` 와 같다 — 시험이 맞댄다).
SIDE_CHOICE_KEY: Final = "scenario_list_side_v1"
SIDE_NEXT_KEY: Final = "scenario_list_side_next_v1"
# 시나리오 관리 「시나리오 작업」 첫째 칸과 오른쪽 칸 「점검」 의 글 — 화면 위젯과 그리로 데려가는
# 다른 화면의 알림 탭 길(`required_exclusion_notice.REQUIRED_TAB_GOTO`)이 함께 쓴다(화면 모듈을
# 읽으면 순환이라 여기 둔다).
LIST_MODE: Final = "목록 관리"
SIDE_CHECK: Final = "점검"
# 저장 · 지정 · 복제 · 자동 갱신 뒤 「소요대수에 들지 않은 수요」 경고가 가리키는 리비전 — (시나리오
# id, 리비전 id). 「점검」 칸이 서는 목록 관리 회차에 한 번 그 리비전을 고르고 비운다
# (`queue_check_target` · `take_check_target`).
CHECK_TARGET_KEY: Final = "scenario_list_check_target"


def peek_draft() -> ListDraft | None:
    """세션의 초안. 아직 없으면 None — 세션 칸을 만들지 않는다."""
    held = st.session_state.get(DRAFT_KEY)
    return held if isinstance(held, ListDraft) else None


def load_draft() -> ListDraft:
    """세션의 초안. 처음이면 세션 표지를 지어 세운다 — 세션이 바뀐 뒤 프런트가 다시 보낸 옛 값을
    가른다."""
    held = peek_draft()
    if held is not None:
        return held
    draft = ListDraft(session=uuid4().hex[:6])
    st.session_state[DRAFT_KEY] = draft
    return draft


def store_draft(draft: ListDraft) -> None:
    st.session_state[DRAFT_KEY] = draft


def list_has_edits() -> bool:
    """저장하지 않은 이름 · 순서 고침이 초안에 남았는가(화면 탭 줄의 점 · 머리 변경 칩)."""
    draft = peek_draft()
    return draft is not None and has_edits(draft)


def pending_count() -> int:
    """「저장 전 변경 n건」."""
    draft = peek_draft()
    return 0 if draft is None else edit_count(draft)


def follow_created_scenario(repository: DuckDBScenarioRepository, scenario_id: str) -> None:
    """이 세션이 시나리오를 더한 뒤 미저장 순서의 본 차례를 옮긴다 — 안 옮기면 「다른 곳에서
    바뀌었습니다」 로 막히는데 거짓이다. 순서 고침이 없으면 저장소를 더 읽지 않는다."""
    draft = peek_draft()
    if draft is None or draft.order is None:
        return
    order = tuple(item.scenario_id for item in repository.list_scenarios())
    store_draft(rebased_for_created(draft, order, scenario_id))


def shown_order() -> tuple[str, ...]:
    """지난 회차에 그린 저장 차례. 그린 적이 없으면 빈 차례다(`move` 가 지문에서 걸린다)."""
    value = st.session_state.get(SHOWN_ORDER_KEY)
    return value if isinstance(value, tuple) else ()


def remember_shown_order(order: tuple[str, ...]) -> None:
    st.session_state[SHOWN_ORDER_KEY] = order


def queue_check_target(scenario_id: str, revision_id: str) -> None:
    """경고가 가리키는 리비전을 적는다 — 다음에 「점검」 칸이 서는 목록 관리 회차가 그 시나리오를
    열고 그 리비전을 고른다(2026-11-11 입력 점검 검토 보드 F4 (나)). 새 경고가 앞 것을 덮는다."""
    st.session_state[CHECK_TARGET_KEY] = (scenario_id, revision_id)


def take_check_target() -> tuple[str, str] | None:
    """적어 둔 리비전을 꺼내고 비운다. 없거나 꼴이 맞지 않으면 None."""
    held = st.session_state.pop(CHECK_TARGET_KEY, None)
    if (
        isinstance(held, tuple)
        and len(held) == 2
        and all(isinstance(part, str) and part for part in held)
    ):
        return held[0], held[1]
    return None
