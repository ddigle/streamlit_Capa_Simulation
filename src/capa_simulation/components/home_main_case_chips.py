# Purpose: HOME 제목 줄 끝의 주요 Case 칩 셋 — 누르면 사이드바와 같은 길로 그 리비전을 올린다.

"""HOME `Capa LOB Summary` 제목 줄 끝의 주요 Case 칩(2026-10-23 사용자 결정 — 시안 C · 동작 (가)).

슬롯은 셋으로 고정이다 — `공식 vN`(지금 최신 공식버전) · `Case1` · `Case2`(HOME `Preference`
「주요 Case」 에서 지정 — `home_main_cases`). **칩 글자는 이것뿐이다.** 어느 시나리오·리비전인지는
마우스를 올리면 뜨는 풍선(단추 `help`)이 말하고, 지금 적용된 시나리오는 머리 띠(`app_header`)가
말하므로 칩 옆에 다시 적지 않는다.

**누르면 사이드바에서 그 리비전을 불러온 것과 똑같다.** 불러오기는 사이드바 팝업의 길
(`scenario_status.load_saved_revision`)을 그대로 쓴다 — 세션 활성 시나리오가 바뀌어 다른 화면도 그
Case 를 보고, 사이드바 「시나리오」 칸과 그 아래 「… 불러왔습니다」 알림도 팝업과 같다. 저장하지
않은 편집·적용 전 편집이 있으면 곧바로 올리지 않고 사이드바 팝업을 그 Case 로 미리 골라 연다
(`scenario_status.open_scenario_dialog_on`) — 확인 칸 「변경을 버리고 불러오기」와 「불러오기」
단추가 팝업 그대로다.

**클릭은 콜백이다.** 콜백은 스크립트보다 먼저 돌아 뒤이은 회차가 곧 새 시나리오의 회차다. 본문에서
불러오고 `st.rerun()` 하면 그 회차에 그리지 않은 페이지 위젯 값(탭·필터)이 버려진다(AGENTS 9장).
HOME 토글 기본값 쓰기(`_release_stale_ui_state`)와 리비전 프리셋 걸기도 그 회차의
위젯·`apply_pending_scenario_preset` 보다 앞이라 새 값이 그대로 닿는다.

상태마다(2026-10-23 사용자 결정 — 제안대로):

- 세션 활성 시나리오·**리비전까지** 같은 슬롯을 칠한다(primary). 칠한 칩을 다시 눌러도 편집이
  없으면 아무것도 하지 않는다 — 이미 그 Case 를 보고 있다(다시 불러오면 조회기간·공정 필터가 리비전
  프리셋으로 돌아간다). 편집이 있으면 팝업 확인을 거쳐 저장본으로 되돌리는 길이 된다.
- 어느 슬롯과도 같지 않으면 칩 줄 끝에 작은 회색 「슬롯 밖」 한 마디뿐이다. 머리 띠는 가상요소라
  HOME 만의 상태를 실을 자리가 없고 모든 화면이 함께 쓴다 — 칩 줄 끝이 가장 덜 거슬린다.
- 미지정 Case 는 점선 칩이고(풍선 「Case2 · 지정 안 함」) 누르면 HOME `Preference` 탭으로 옮긴다 —
  「주요 Case」 상자는 그 탭의 둘째 상자라 탭을 열면 위쪽에 보인다.
- 가리키던 리비전이 사라졌으면(보관·삭제는 저장소가 그 Case 를 비우므로 그 밖의 길로 남은 값) 누를
  수 없고 풍선이 다시 지정하라고 한다. 공식버전이 없으면(내장 시드 등) 공식 칩도 누를 수 없다.

**회차마다 DB 를 보지 않는다**(HOME 을 무겁게 하지 않는다 — 2026-10-03 사용자 원칙). 공식버전은 입장
화면 요약이 세션에 둔 값(`intro_summary.latest_official_identity` — 머리 띠 「공식 vN」 과 같은
값)을 부르는 쪽이 넘기고, Case 는 주요 Case 쓰기 세대를 키로 한
캐시(`persistence/cache.load_main_case_targets`)다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import streamlit as st

from capa_simulation.components.home_main_cases import UNSET_CHOICE
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.scenario_edit_bar import pending_edit_labels
from capa_simulation.components.scenario_status import (
    load_saved_revision,
    open_scenario_dialog_on,
)
from capa_simulation.home_state import HOME_PREFERENCE_TAB, HOME_TAB_KEY
from capa_simulation.navigation import HOME
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS
from capa_simulation.persistence._sql_helpers import pinned_connections
from capa_simulation.persistence.cache import load_main_case_targets
from capa_simulation.scenario_activation import (
    active_persisted_revision_id,
    active_persisted_scenario_id,
    has_unsaved_scenario_changes,
)
from capa_simulation.services.main_cases import (
    MAIN_CASE_NUMBERS,
    SLOT_OK,
    SLOT_UNSET,
    MainCaseSlot,
    OfficialPointer,
    main_case_slots,
)

# 칩 줄 컨테이너와 칩 셋의 key. 칩 모양 CSS 가 `st-key-<key>` 클래스로 잡는다.
CHIP_ROW_KEY = "home_main_case_chips"
OFFICIAL_CHIP_KEY = "home_main_case_chip_official"
CASE1_CHIP_KEY = "home_main_case_chip_case1"
CASE2_CHIP_KEY = "home_main_case_chip_case2"
# 칩으로 불러오지 못했을 때의 한 줄. 다음 회차의 제목 줄 밑 칸이 꺼내 보인다.
CHIP_NOTICE_KEY = "home_main_case_chip_notice"
OFFICIAL_CHIP_TEXT = "공식"
OUTSIDE_SLOTS_TEXT = "슬롯 밖"
MISSING_REVISION_HELP = "리비전 없음 — Preference 에서 다시 지정"
# 칩을 누를 수 있는 상태가 아니면 콜백에 넘기는 짝. 잠긴 칩은 눌리지 않지만, 혹시 닿으면
# 미지정 칩처럼 `Preference` 로 옮긴다 — 사라진 Case 를 고치는 곳이 거기다.
_NO_TARGET: tuple[str | None, str | None] = (None, None)
_CASE_CHIP_KEYS = (CASE1_CHIP_KEY, CASE2_CHIP_KEY)
HOME_PAGE_FILE = Path(HOME.path).name


@dataclass(frozen=True)
class SlotChip:
    """칩 하나. `target` 은 누르면 올릴 (시나리오 id, 리비전 id) — 없으면 `Preference` 로 옮긴다."""

    key: str
    text: str
    help: str
    target: tuple[str | None, str | None]
    painted: bool
    disabled: bool
    dashed: bool


def slot_chips(
    slots: tuple[MainCaseSlot, MainCaseSlot, MainCaseSlot],
    *,
    official_release_no: int | None,
    active: tuple[str | None, str | None],
) -> tuple[SlotChip, SlotChip, SlotChip]:
    """슬롯 셋(`main_case_slots`)을 칩 셋으로. `active` 는 세션 활성 (시나리오 id, 리비전 id).

    칠하기는 시나리오와 **리비전까지** 같을 때만이다(2026-10-23 사용자 결정). 공식 슬롯은 지정하는
    칸이 없으므로 「미지정」이 곧 공식버전 없음이다 — 점선이 아니라 잠근다.
    """
    official_slot, *case_slots = slots
    if official_slot.status == SLOT_OK and official_release_no is not None:
        official = _ready_chip(
            OFFICIAL_CHIP_KEY, f"공식 v{official_release_no}", official_slot, active
        )
    else:
        official = SlotChip(
            OFFICIAL_CHIP_KEY,
            OFFICIAL_CHIP_TEXT,
            official_slot.label,
            _NO_TARGET,
            painted=False,
            disabled=True,
            dashed=False,
        )
    cases = [
        _case_chip(key, slot)
        if slot.status != SLOT_OK
        else _ready_chip(key, slot.title, slot, active)
        for key, slot in zip(_CASE_CHIP_KEYS, case_slots, strict=True)
    ]
    return official, cases[0], cases[1]


def _ready_chip(
    key: str, text: str, slot: MainCaseSlot, active: tuple[str | None, str | None]
) -> SlotChip:
    target = (slot.scenario_id, slot.revision_id)
    return SlotChip(
        key,
        text,
        slot.label,
        target,
        painted=active[1] is not None and target == active,
        disabled=False,
        dashed=False,
    )


def _case_chip(key: str, slot: MainCaseSlot) -> SlotChip:
    """미지정(점선, 누르면 `Preference`)·사라짐(잠금) Case 칩."""
    if slot.status == SLOT_UNSET:
        return SlotChip(
            key,
            slot.title,
            f"{slot.title} · {UNSET_CHOICE}",
            _NO_TARGET,
            painted=False,
            disabled=False,
            dashed=True,
        )
    return SlotChip(
        key,
        slot.title,
        f"{slot.title} · {MISSING_REVISION_HELP}",
        _NO_TARGET,
        painted=False,
        disabled=True,
        dashed=False,
    )


def outside_slots(chips: tuple[SlotChip, ...], active: tuple[str | None, str | None]) -> bool:
    """올라온 리비전이 있는데 어느 칩도 칠하지 않았는가 — 칩 줄 끝 「슬롯 밖」."""
    return active[1] is not None and not any(chip.painted for chip in chips)


def render_main_case_chips(database_path: str, *, official: OfficialPointer | None) -> None:
    """제목 줄 끝 칸의 칩 셋(`page_header.render_page_header_with_status` 의 `trailing`).

    `official` 은 이 세션이 확인한 최신 공식버전이다(`intro_summary.latest_official_identity`). Case
    재료를 읽지 못하면 칩 줄을 세우지 않는다 — 같은 오류는 `Preference` 의 「주요 Case」 상자가
    알린다.
    """
    try:
        targets = load_main_case_targets(database_path)
    except BOOTSTRAP_ERRORS:
        return
    slots = main_case_slots(
        official=official,
        cases=[targets.profile.case(case_no) for case_no in MAIN_CASE_NUMBERS],
        scenarios=targets.scenarios,
        revisions=targets.revisions,
    )
    active = (active_persisted_scenario_id(), active_persisted_revision_id())
    chips = slot_chips(
        slots,
        official_release_no=None if official is None else official.release_no,
        active=active,
    )
    st.html(chip_style(chips))
    with st.container(
        key=CHIP_ROW_KEY,
        horizontal=True,
        horizontal_alignment="right",
        vertical_alignment="center",
        gap="small",
    ):
        for chip in chips:
            st.button(
                chip.text,
                key=chip.key,
                # 풍선은 마크다운으로 그려진다 — 사람이 적은 이름을 글자 그대로 싣는다.
                help=literal_markdown(chip.help),
                type="primary" if chip.painted else "secondary",
                disabled=chip.disabled,
                on_click=_open_slot,
                args=(database_path, *chip.target),
            )
        if outside_slots(chips, active):
            # 풍선(`help`)을 달지 않는다 — 물음표 아이콘 하나가 더 서서 칩 줄이
            # 시끄러워진다(브라우저 확인). 어느 시나리오인지는 머리 띠가 말한다.
            st.caption(OUTSIDE_SLOTS_TEXT, width="content")


def render_main_case_chip_notice() -> None:
    """칩으로 불러오지 못한 까닭 한 줄. 제목 줄 바로 밑, 늘 서 있는 칸 안에 그린다(AGENTS 9장).

    알림이 생기고 사라질 때 아래 탭의 자리가 밀리지 않게 한다 — 빈 칸은 높이가 없다.
    """
    notice = st.session_state.pop(CHIP_NOTICE_KEY, None)
    with st.container():
        if isinstance(notice, str):
            st.warning(notice, icon=":material/info:")


def _open_slot(database_path: str, scenario_id: str | None, revision_id: str | None) -> None:
    """칩의 콜백. 미지정이면 `Preference` 탭, 편집이 있으면 사이드바 팝업, 아니면 곧바로 올린다.

    탭 key 를 적는 것은 탭 위젯이 그려지기 전(콜백)이라 그 회차의 `stateful_tabs` 가 그 탭을 연다.
    적용 전 편집은 사이드바 팝업이 세는 것과 같은 함수로 센다(`pending_edit_labels`). 곧바로 올릴
    때는 콜백이 `app.py` 의 실행 핀 밖에서 돌므로 여기서 DB 핀을 잡는다(팝업 본문과 같다).
    """
    if scenario_id is None or revision_id is None:
        st.session_state[HOME_TAB_KEY] = HOME_PREFERENCE_TAB
        return
    if has_unsaved_scenario_changes() or pending_edit_labels(HOME_PAGE_FILE):
        open_scenario_dialog_on(scenario_id, revision_id)
        return
    if (scenario_id, revision_id) == (
        active_persisted_scenario_id(),
        active_persisted_revision_id(),
    ):
        return
    with pinned_connections(Path(database_path)):
        failure = load_saved_revision(database_path, revision_id)
    if failure is not None:
        st.session_state[CHIP_NOTICE_KEY] = failure


def chip_style(chips: tuple[SlotChip, ...]) -> str:
    """칩 모양 — 작은 알약, 미지정은 점선 테두리. 색은 Streamlit 단추 테마 그대로다.

    점선은 그 회차의 미지정 칩 key 에만 건다(`st-key-<key>`). 스타일만 든 `st.html` 이라 본문 자리를
    먹지 않는다.
    """
    dashed = ", ".join(f".st-key-{chip.key} button" for chip in chips if chip.dashed)
    rules = [
        f".st-key-{CHIP_ROW_KEY} button {{"
        " min-height: 1.75rem; padding: 0.1rem 0.8rem; border-radius: 999px;"
        " font-size: 0.85rem; font-weight: 600; line-height: 1.2; }",
        f".st-key-{CHIP_ROW_KEY} button p {{ font-size: inherit; font-weight: inherit; }}",
    ]
    if dashed:
        rules.append(f"{dashed} {{ border-style: dashed; }}")
    return "<style>" + "\n".join(rules) + "</style>"
