# Purpose: LOB 표시 조건 카드의 주요 Case 칩 — 누르면 사이드바와 같은 길로 그 리비전을 올린다.

"""HOME 주요 Case 칩(2026-10-23 사용자 결정 — 시안 C · 동작 (가)).

**자리는 사이드바 「LOB 표시 조건」 카드의 첫 항목이다**(2026-11-02 사용자 요청 — 전에는 본문 제목
줄 끝). 이름 줄 「주요 Case」 밑에 칩 셋이 카드 폭을 같은 폭으로 나눠 서고, 그 밑에 칩 알림
칸(늘 서 있는 빈 칸 — 알림은 알림창 · Alarm 으로만 간다), 얇은 선 뒤로 토글들이 온다. 본문 맨
위에는 칩 줄이 남지 않아 화면 탭 줄 바로 밑에서 Summary 가 시작한다. 카드는 HOME 에서 처음 펼친
채 선다(`condition_card(default=True)` — 접으면 칩이 보이지 않는다).

슬롯은 셋으로 고정이다 — `공식 vN`(지금 최신 공식버전) · `Case1` · `Case2`(「HOME 설정」 팝업
`비교 · 주요 Case` 탭의 「주요 Case」 에서 지정 — `home_main_cases`). **칩 글자는 이것뿐이다.** 어느
시나리오·리비전인지는 마우스를 올리면 뜨는 풍선(단추 `help`)이 말하고, 지금 적용된 시나리오는 머리
띠(`app_header`)가 말하므로 칩 옆에 다시 적지 않는다.

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

**콜백은 누르는 순간 슬롯을 다시 푼다.** Streamlit 은 콜백 인자를 그린 회차의 값 그대로 넘긴다 — 그
사이 다른 세션이 Case 를 다시 지정했거나 가리키던 시나리오를 보관했으면 그린 짝은 낡았다. 그래서
칩은 (슬롯 차례, 그린 짝)만 넘기고, 콜백이 같은 재료(`_slot_chips_now`)로 지금 짝을 풀어 그린 것과
다르면 아무것도 올리지 않고 알림창 · Alarm 에 알린다 — 사이드바가 고를 수 없는 보관 시나리오를
칩이 올리는 일이 없다. 칩 경고(그린 짝이 낡음 · 주요 Case 나 공식버전을 읽지 못함 · 불러오지 못함)는
칩 줄 밑 자리에 그리지 않는다 — 누른 동작은 끝났고 그 자리에 고칠 입력이 없다(설계 규칙 UI-NTF-02 ·
AMB-05 (나)). 누를 수 없는 칩의 까닭은 그 칩 풍선이 말한다. 뒤이은 회차가 새 칩을 그린다. 공식
칩은 세션 값이 그린 짝과 함께 낡을 수 있어 저장소의 지금 공식버전과 한 번 더
대조한다(`_official_still_current`).

상태마다(2026-10-23 사용자 결정 — 제안대로):

- 세션 활성 시나리오·**리비전까지** 같은 슬롯을 칠한다(primary). 저장하지 않은 편집이 있으면 칠하지
  않는다 — 머리 띠·사이드바 배지처럼 「미저장」이 먼저다. 칠한 칩을 다시 눌러도 편집이 없으면
  아무것도 하지 않는다 — 이미 그 Case 를 보고 있다(다시 불러오면 조회기간·공정 필터가 리비전
  프리셋으로 돌아간다). 편집이 있으면 팝업 확인을 거쳐 저장본으로 되돌리는 길이 된다.
- 어느 슬롯과도 같지 않으면 이름 줄 오른쪽 끝에 작은 회색 「슬롯 밖」 한 마디뿐이다. 머리 띠는
  가상요소라 HOME 만의 상태를 실을 자리가 없고 모든 화면이 함께 쓴다. 이름 줄은 늘 서 있으므로 그
  글자가 나타나고 사라져도 칩 줄은 움직이지 않는다(제목 줄에 있던 때의 숨은 자리표시자는 걷었다).
- 미지정 Case 는 점선 칩이고(풍선 「Case2 · 지정 안 함」) 누르면 「HOME 설정」 팝업을 `비교 · 주요
  Case` 탭으로 연다(`home_settings.open_home_settings`) — 「주요 Case」 상자는 그 탭 오른쪽
  상자이고, 누른 Case 칸(시나리오 · 리비전 상자)이 한 번 강조된다(`home_main_cases.focus_main_case`
  — 2026-11-04 사용자 검수 home-u03). 설정 상자 밖에서 설정 팝업을 여는 유일한 자리다(사이드바
  「LOB 표시 조건」 카드) — 칩의 일은 시나리오 불러오기이고 비어 있을 때만 채우는 곳으로
  데려간다(설계 규칙 UI-LAY-01 의 예외 · UI-NAV-01, 그물 `tests/test_settings_button_sites.py`).
  가리키던 시나리오를 보관·영구 삭제하면 저장소가 그 Case 를 비우므로 이 점선 칩이 된다. 계산이
  멈춘 회차에는 팝업을 열 수 없어(본문이 계산 결과를 쓴다) 이 칩을 잠그고 풍선이 까닭을 말한다.
- 가리키는 시나리오·리비전을 목록에서 찾지 못하면(저장소 밖에서 고친 DB 등 — 보관·삭제는 위처럼
  비운다) 누를 수 없고 풍선이 다시 지정하라고 한다. 공식버전이 없으면(내장 시드 등) 공식 칩도 누를
  수 없다.

**회차마다 DB 를 보지 않는다**(HOME 을 무겁게 하지 않는다 — 2026-10-03 사용자 원칙, AGENTS 규칙 23).
공식버전은 입장 화면 요약이 세션에 둔 값(`intro_summary.latest_official_identity` — 머리 띠 「공식
vN」 과 같은 값)이고, Case 는 주요 Case 쓰기 세대를 키로 한
캐시(`persistence/cache.load_main_case_targets`)다.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import streamlit as st

from capa_simulation.components.condition_field import condition_name_row
from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.home_main_cases import UNSET_CHOICE, focus_main_case
from capa_simulation.components.home_settings import open_home_settings
from capa_simulation.components.intro_summary import (
    forget_intro_summary_check,
    latest_official_identity,
)
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.scenario_edit_bar import pending_edit_labels
from capa_simulation.components.scenario_status import (
    load_saved_revision,
    open_scenario_dialog_on,
)
from capa_simulation.design import tokens
from capa_simulation.home_state import HOME_CASES_TAB
from capa_simulation.navigation import HOME
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence._sql_helpers import pinned_connections
from capa_simulation.persistence.cache import get_scenario_repository, load_main_case_targets
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
    case_title,
    main_case_slots,
)

# 칩 필드(이름 줄 + 칩 줄 + 알림 칸)·칩 줄 컨테이너와 칩 셋의 key. 칩 모양 CSS 가 `st-key-<key>`
# 클래스로 잡는다 — CSS 로 고르는 컨테이너 key 는 계약이다(AGENTS 9장).
CHIP_FIELD_KEY = "home_main_case_field"
CHIP_FIELD_NAME = "주요 Case"
CHIP_ROW_KEY = "home_main_case_chips"
OFFICIAL_CHIP_KEY = "home_main_case_chip_official"
CASE1_CHIP_KEY = "home_main_case_chip_case1"
CASE2_CHIP_KEY = "home_main_case_chip_case2"
# 칩으로 불러오지 못했을 때의 알림 칸. 다음 회차의 칩 줄 밑 늘 서 있는 칸이 알림창 · Alarm 으로
# 보낸다(그 칸에는 그리지 않는다 — `popup_only`).
CHIP_NOTICE_KEY = "home_main_case_chip_notice"
OFFICIAL_CHIP_TEXT = "공식"
OUTSIDE_SLOTS_TEXT = "슬롯 밖"
MISSING_REVISION_HELP = "리비전 없음 — HOME 설정 → 비교 · 주요 Case 탭에서 다시 지정"
# 계산이 멈춘 회차의 미지정 칩 풍선 꼬리 — 그 회차에는 「HOME 설정」 팝업을 열 수 없다.
STOPPED_UNSET_HELP = "계산이 멈춰 HOME 설정을 열 수 없습니다"
# 올릴 리비전이 없는 칩(미지정·잠김)의 짝. 미지정 칩은 누르면 「HOME 설정」 팝업의
# `비교 · 주요 Case` 탭을 연다. 잠긴 칩은 눌리지 않는다 — 그린 뒤에 잠길 상태가 된 칩을 누르면
# 콜백이 다시 풀어 알림만 남긴다.
_NO_TARGET: tuple[str | None, str | None] = (None, None)
_CASE_CHIP_KEYS = (CASE1_CHIP_KEY, CASE2_CHIP_KEY)
# 칩 셋에서 공식 칩의 차례.
_OFFICIAL_SLOT = 0
# 알림이 칩을 부르는 이름(슬롯 차례). 공식 칩 글자 `공식 vN` 은 그사이 바뀌었을 수 있어 번호를 뺀다.
_SLOT_NAMES = (OFFICIAL_CHIP_TEXT, *(case_title(case_no) for case_no in MAIN_CASE_NUMBERS))
HOME_PAGE_FILE = Path(HOME.path).name


@dataclass(frozen=True)
class SlotChip:
    """칩 하나. `target` 은 누르면 올릴 (시나리오 id, 리비전 id) — 없으면 「HOME 설정」 팝업의
    `비교 · 주요 Case` 탭을 연다."""

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
    """슬롯 셋(`main_case_slots`)을 칩 셋으로. `active` 는 칠할 기준 (시나리오 id, 리비전 id).

    칠하기는 시나리오와 **리비전까지** 같을 때만이다(2026-10-23 사용자 결정). 부르는 쪽은 저장하지
    않은 편집이 있으면 `active` 를 `(None, None)` 으로 넘겨 아무것도 칠하지 않는다. 공식 슬롯은
    지정하는 칸이 없으므로 「미지정」이 곧 공식버전 없음이다 — 점선이 아니라 잠근다.
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
    """미지정(점선, 누르면 「HOME 설정」 → `비교 · 주요 Case`)·찾지 못함(잠금) Case 칩."""
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
    """칠할 기준 리비전이 있는데 어느 칩도 칠하지 않았는가 — 이름 줄 끝 「슬롯 밖」."""
    return active[1] is not None and not any(chip.painted for chip in chips)


def painting_reference() -> tuple[str | None, str | None]:
    """칩을 칠할 기준 — 세션 활성 (시나리오 id, 리비전 id). 저장하지 않은 편집이 있으면 없다.

    미저장 편집본은 어느 저장 리비전과도 같은 내용이 아니다. 머리 띠·사이드바 배지가 「미저장
    변경」을 먼저 말하는 것과 같은 차례로, 칩도 「그 리비전을 보고 있다」고 칠하지 않고 「슬롯
    밖」도 붙이지 않는다.
    """
    if has_unsaved_scenario_changes():
        return _NO_TARGET
    return active_persisted_scenario_id(), active_persisted_revision_id()


def _slot_chips_now(
    database_path: str, *, active: tuple[str | None, str | None]
) -> tuple[SlotChip, SlotChip, SlotChip]:
    """지금 재료로 푼 칩 셋. 그리기와 콜백이 같은 함수로 풀어야 둘이 같은 짝을 본다.

    공식버전은 이 세션이 확인한 값(`latest_official_identity`), Case 는 쓰기 세대 캐시라 DB 를 다시
    읽는 것은 누가 주요 Case 를 고친 뒤 처음 한 번뿐이다. 읽지 못하면 `BOOTSTRAP_ERRORS` 를 올린다.
    """
    targets = load_main_case_targets(database_path)
    official = latest_official_identity()
    slots = main_case_slots(
        official=official,
        cases=[targets.profile.case(case_no) for case_no in MAIN_CASE_NUMBERS],
        scenarios=targets.scenarios,
        revisions=targets.revisions,
    )
    return slot_chips(
        slots,
        official_release_no=None if official is None else official.release_no,
        active=active,
    )


def stopped_chips(chips: tuple[SlotChip, ...]) -> tuple[SlotChip, ...]:
    """계산이 멈춘 회차의 칩 셋 — 미지정 칩(누르면 팝업을 여는 칩)만 잠그고 풍선에 까닭을 붙인다.

    올릴 리비전이 있는 칩은 그대로 누를 수 있다 — 다른 Case 로 옮기는 것이 멈춘 화면에서 벗어나는
    길이기도 하다.
    """
    return tuple(
        replace(chip, disabled=True, help=f"{chip.help} — {STOPPED_UNSET_HELP}")
        if chip.dashed and not chip.disabled
        else chip
        for chip in chips
    )


def render_main_case_chips(database_path: str, *, settings_ready: bool = True) -> None:
    """「LOB 표시 조건」 카드 맨 위의 칩 필드 — 이름 줄 「주요 Case」(슬롯 밖이면 오른쪽 끝에 그
    한 마디), 같은 폭 칩 셋, 칩 알림 칸.

    Case 재료를 읽지 못하면 칩 필드를 세우지 않는다 — 같은 오류는 「HOME 설정」 팝업 `비교 · 주요
    Case` 탭의 「주요 Case」 상자가 알린다. `settings_ready` 가 거짓이면(계산이 멈춘 회차) 미지정
    칩을 잠근다(`stopped_chips`).
    """
    active = painting_reference()
    try:
        chips = _slot_chips_now(database_path, active=active)
    except BOOTSTRAP_ERRORS:
        return
    shown = chips if settings_ready else stopped_chips(chips)
    st.html(chip_style(shown))
    with st.container(key=CHIP_FIELD_KEY, gap=None):
        condition_name_row(
            CHIP_FIELD_NAME,
            slug="main_case",
            status=OUTSIDE_SLOTS_TEXT if outside_slots(chips, active) else None,
        )
        with st.container(
            key=CHIP_ROW_KEY,
            horizontal=True,
            vertical_alignment="center",
            gap="small",
        ):
            for index, chip in enumerate(shown):
                st.button(
                    chip.text,
                    key=chip.key,
                    # 풍선은 마크다운으로 그려진다 — 사람이 적은 이름을 글자 그대로 싣는다.
                    help=literal_markdown(chip.help),
                    type="primary" if chip.painted else "secondary",
                    disabled=chip.disabled,
                    on_click=_open_slot,
                    args=(database_path, index, chip.target, chip.key),
                    width="stretch",
                )
        # 칩으로 불러오지 못한 까닭은 알림창 · Alarm 으로만 낸다. 표지를 보내는 칸은 늘 세운다
        # (AGENTS 9장) — 칸이 있고 없음으로 아래 토글이 밀리지 않게 한다(빈 칸은 높이가 없다).
        render_flash(CHIP_NOTICE_KEY)


def _notify(text: str) -> None:
    """칩 콜백의 경고를 담는다 — 다음 회차에 한 번 알림창 · Alarm 으로만 낸다(`flash` 의
    `popup_only` — 칩 줄 밑 자리에는 그리지 않는다, 설계 규칙 AMB-05 (나)). 단계는 확인
    필요(`FL-03`)다."""
    queue_flash(CHIP_NOTICE_KEY, text, kind="warning", icon=":material/info:", popup_only=True)


def changed_slot_notice(index: int) -> str:
    """누른 칩의 짝이 그린 뒤 바뀌었을 때의 알림(슬롯 차례 `index` — 공식·Case1·Case2).

    알림창에만 가는 글이라 짧은 글 한도(`alerts.SHORT_LIMIT`) 안에 끝까지 든다(설계 규칙
    UI-NTF-06 — 무엇을 · 어디서)."""
    return (
        f"{_SLOT_NAMES[index]} 칩 지정이 그사이 바뀌어 불러오지 않았습니다 — 새로 그린 칩의 "
        "풍선을 보고 다시 누르세요."
    )


def _open_slot(
    database_path: str,
    index: int,
    drawn: tuple[str | None, str | None],
    widget_key: str | None = None,
) -> None:
    """칩의 콜백. 그린 짝이 낡았으면 알림, 미지정이면 「HOME 설정」 팝업(`비교 · 주요 Case` 탭 —
    그 Case 칸 강조), 편집이
    있으면 사이드바 팝업, 아니면 곧바로 올린다. `widget_key` 는 누른 칩의 key 다 — 「HOME 설정」 을
    여는 갈래가 HOME 팝업 호스트만 다시 돌린다(`open_home_settings` — HOME 을 다시 계산하지 않는다).

    짝은 누르는 순간 다시 푼다(모듈 설명 — 콜백 인자는 그린 회차의 값이다). 팝업 열림 칸과 안쪽 탭
    key 를 적는 것은 탭 위젯이 그려지기 전(콜백)이라 그 회차의 팝업이 그 탭으로 선다. 적용 전 편집은
    사이드바 팝업이 세는 것과 같은 함수로 센다(`pending_edit_labels`). 곧바로 올릴 때는 콜백이
    `app.py` 의 실행 핀 밖에서 돌므로 여기서 DB 핀을 잡는다(팝업 본문과 같다).
    """
    try:
        chip = _slot_chips_now(database_path, active=_NO_TARGET)[index]
    except BOOTSTRAP_ERRORS as exc:
        _notify(f"주요 Case 를 읽지 못했습니다: {bootstrap_error_message(exc)}")
        return
    if chip.disabled or chip.target != drawn:
        _notify(changed_slot_notice(index))
        return
    if index == _OFFICIAL_SLOT and not _official_still_current(database_path, chip.target):
        return
    scenario_id, revision_id = chip.target
    if scenario_id is None or revision_id is None:
        # 그 Case 칸을 강조해 어디서 고르는지 짚어 준다(2026-11-04 사용자 검수 home-u03).
        focus_main_case(MAIN_CASE_NUMBERS[index - 1])
        open_home_settings(HOME_CASES_TAB, widget_key)
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
        _notify(failure)


def _official_still_current(database_path: str, target: tuple[str | None, str | None]) -> bool:
    """공식 칩의 짝이 저장소의 지금 공식버전인가. 아니면 알리고 세션의 공식버전을 버린다.

    공식 칩을 푸는 세션 값(`latest_official_identity`)은 입장 화면 요약이 30초마다 다시 보는
    값이라 그사이 다른 곳에서 새 공식버전을 발행했으면 낡았다 — 그린 짝과 다시 푼 짝이 함께 낡아
    위의 대조로 잡히지 않는다. 누를 때만 도는 콜백이라 저장소를 바로 읽는다(회차마다 읽지 않는
    규칙 23 과 무관). 낡았으면 `forget_intro_summary_check` 로 다음 회차가 공식버전을 곧바로 다시
    확인해 칩을 새로 그린다.
    """
    try:
        with pinned_connections(Path(database_path)):
            release = get_scenario_repository(database_path).latest_official_release()
    except BOOTSTRAP_ERRORS as exc:
        _notify(f"공식버전을 읽지 못했습니다: {bootstrap_error_message(exc)}")
        return False
    if release is not None and (release.scenario_id, release.revision_id) == target:
        return True
    forget_intro_summary_check()
    _notify(changed_slot_notice(_OFFICIAL_SLOT))
    return False


def chip_style(chips: tuple[SlotChip, ...]) -> str:
    """칩 필드 모양 — 이름 줄, 같은 폭 작은 알약 칩, 미지정은 점선 테두리, 칠한 칩 글자는 강조 면 위
    글자색, 필드 밑 얇은 선(토글과 가른다).

    색은 Streamlit 단추 테마 그대로이고 칠한 칩의 **글자색만** 토큰(`ACCENT_TEXT`)으로 다시
    건다 — 어두운 테마의 강조색(`[theme.dark] primaryColor`)은 밝아서 Streamlit 의 흰 글자로는
    대비가 1.9:1 이다. 칩은 늘 하나 칠해져 있다. 점선은 그 회차의 미지정 칩 key 에만 건다
    (`st-key-<key>`). 칩 글은 자르지 않는다 — 칩 칸(Streamlit 이 `flex: 1 1 fit-content`·`min-width:
    14px` 를 건 `stElementContainer`)의 최소 폭을 글 폭(`max-content`)으로 두고 줄은 감싸
    내린다(`flex-wrap: wrap`). 보통 폭(사이드바 256px 이상)에서는 셋이 카드 폭을 나눠 한 줄이고,
    사이드바를 끌어 200~220px 로 줄이면 들지 않는 칩이 다음 줄로 내려가 그 줄을 채운다(전에는
    `nowrap` 이라 칩이 글보다 좁아져 「공…」 · 「C..」 로 잘렸다 — 2026-11-02 검토). 「공식 v12」
    같은 글도 칸 안에 들게 글자·좌우 여백을 줄였다. 이름 줄은 조회 조건 패널의 이름 줄과 같은 작은
    보조 글이다(패널 서식은 패널 안만 고르므로 여기서 같은 값을 건다 — 캡션 칸의 아래 음수 여백과
    흐림을 걷는다). 스타일만 든 `st.html` 이라 본문 자리를 먹지 않는다.
    """
    field = f".st-key-{CHIP_FIELD_KEY}"
    row = f".st-key-{CHIP_ROW_KEY}"
    name_row = f"{field} .st-key-condition_name_main_case"
    dashed = ", ".join(f".st-key-{chip.key} button" for chip in chips if chip.dashed)
    painted = f'{row} button[kind="primary"]'
    rules = [
        f"{field} {{ gap: 0.3rem; padding-bottom: 0.6rem;"
        f" border-bottom: 1px solid {tokens.BORDER}; }}",
        f"{name_row} {{ min-height: 1.15rem; flex-wrap: nowrap; }}",
        f'{name_row} [data-testid="stCaptionContainer"] {{ margin-bottom: 0; opacity: 1; }}',
        f'{name_row} [data-testid="stCaptionContainer"] p {{ margin: 0; font-size: 0.75rem;'
        f" line-height: 1.25; color: {tokens.TEXT_MUTED}; white-space: nowrap; }}",
        f'{name_row} > [data-testid="stElementContainer"]:first-child p {{ font-weight: 600; }}',
        f"{row} {{ flex-wrap: wrap; row-gap: 0.35rem; }}",
        f'{row} > [data-testid="stElementContainer"] {{ min-width: max-content; }}',
        f"{row} button {{"
        " min-height: 1.75rem; padding: 0.1rem 0.35rem; border-radius: 999px;"
        " font-size: 0.8rem; font-weight: 600; line-height: 1.2; }",
        f"{row} button p {{ font-size: inherit; font-weight: inherit; color: inherit;"
        " white-space: nowrap; }",
        f"{painted}, {painted}:hover, {painted}:active, {painted}:focus, {painted}:focus-visible"
        f" {{ color: {tokens.ACCENT_TEXT}; }}",
    ]
    if dashed:
        rules.append(f"{dashed} {{ border-style: dashed; }}")
    return "<style>" + "\n".join(rules) + "</style>"
