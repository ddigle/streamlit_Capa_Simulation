# Purpose: 가용설비 현황 「가용설비 설정」 사이드바 상자와 팝업(Cut-off)의 열림 칸·호스트를 둔다.

"""가용설비 현황 「가용설비 설정」 팝업(2026-10-24 사용자 결정 — 두 탭 개편, 그 전에는 `Preference`
탭).

- **자리**: 사이드바 「가용설비 설정」 상자(조회 조건 패널 바로 밑 · `설비 조회 조건` 카드 위 —
  사이드바 설정 상자 공용 꼴 `components/settings_box.py`) → 큰 팝업(2026-11-03 사용자 지시 —
  「설정 버튼은 사이드바 상자로」, 전에는 제목 줄 끝 칸의 「설정」 단추). 탭에 매이지 않은 화면
  설정이라 세 탭 모두에서 같은 자리에 선다. 안은 묶음 머리 「공정별 Cut-off」
  하나(`render_cutoff_management` 그대로)다 — 나중 설정은 같은 팝업에 묶음 머리로 붙인다(D14).
- **잠금**: 설비 DB 를 읽지 못한 회차(페이지가 오류를 알리고 멈춘다)에는 팝업 본문의 저장소가 없어
  상자가 잠긴 채 같은 자리에 선다(`render_equipment_settings_box(disabled=True)`).
- **열림 칸**: 페이지에 한 칸(`available_equipment_open_dialog`) — 값이 팝업을 가른다(`settings` ·
  `import` — 엑셀·CSV 팝업은 `equipment_import_dialog`, 호스트는 여기 하나). 여는 콜백은
  `forget_page_dialogs()` 부터 부른다(AGENTS 9장 「팝업과 콜백」 — 한 실행에 팝업 하나).
- **호스트**: 이벤트 칸에 늘 한 자리를 쓴다 — 열렸으면 팝업, 아니면 빈 스타일 자리표시자. 팝업
  본문도 이벤트 칸에 쓰지 않는다(`render_cutoff_management` 는 스타일만 든 `st.html`·토스트를 쓰지
  않는다).
- **저장 뒤에도 팝업을 열어 둔다** — AGENTS 9장 「팝업 안 저장이 성공하면 열림 키를 지우고
  `st.rerun()`」 의 예외다. Cut-off 저장·「설비 공정으로 채우기」 는 앱 범위 `st.rerun()` 이라 바깥
  화면(Static 대비 일정)도 그 회차에 새 Cut-off 로 다시 그려지고, 열림 칸이 남아 저장 결과(flash)가
  누른 단추 바로 아래에 선다.
- **닫으면 제출하지 않은 표 편집은 사라진다** — 팝업 안 편집표는 닫힌 동안 마운트되지 않는다(초안
  `CUTOFF_DRAFT_KEY` 는 마지막 저장 시도·「설비 공정으로 채우기」 까지만 든다). 새로 열면 그 초안도
  걷어(`forget_cutoff_draft`) 최신 저장본에서 연다 — 걷지 않으면 남의 저장 뒤 다시 열어도 옛 값이
  보였다(2026-10-27 E2E). Guide 가 「닫기 전에 저장합니다」 라고 적는다. 화면 탭 줄의 점·떠나기
  확인 대상이 아니다(Cut-off 초안은 판정 함수가 없다).
- **머리 안내 글은 두지 않는다** — 「모든 설비 시나리오가 함께 쓰는 공용 설정 · 저장하지 않고 닫으면
  고친 칸은 사라짐」 은 상자 풍선(`SETTINGS_HELP`)과 「Cut-off 저장」 단추 풍선
  (`cutoff_management.CUTOFF_SAVE_HELP`)이 말한다(HOME 설정 팝업과 같은 꼴).
- 가정 설비 시나리오면 표가 읽기 전용이다(`PREFERENCE_LOCK_MESSAGE` — Cut-off 는 모든 설비 시나리오
  공용, E3).
"""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

from capa_simulation.components.cutoff_management import (
    forget_cutoff_draft,
    render_cutoff_management,
)
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.components.settings_box import (
    SETTINGS_ICON,
    render_settings_box,
    settings_box_key,
)
from capa_simulation.page_bootstrap import PAGE_DIALOG_SUFFIX, forget_page_dialogs
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository

__all__ = [
    "EQUIPMENT_DIALOG_KEY",
    "IMPORT_DIALOG",
    "SETTINGS_BOX_KEY",
    "SETTINGS_BUTTON_KEY",
    "SETTINGS_DIALOG",
    "SETTINGS_DIALOG_TITLE",
    "open_equipment_settings",
    "render_equipment_dialog_host",
    "render_equipment_settings_box",
]

# 가용설비 현황의 팝업 칸(페이지에 한 칸). 값이 팝업을 가른다.
EQUIPMENT_DIALOG_KEY = f"available_equipment{PAGE_DIALOG_SUFFIX}"
SETTINGS_DIALOG = "settings"
# 상자 글과 팝업 제목은 한 글이다(HOME 「HOME 설정」 과 같은 꼴 — 사이드바에서 어느 화면의
# 설정인지 읽힌다).
SETTINGS_DIALOG_TITLE = "가용설비 설정"
SETTINGS_BUTTON_KEY = "equipment_settings_open_v1"
SETTINGS_BOX_NAME = "equipment_settings"
SETTINGS_BOX_KEY = settings_box_key(SETTINGS_BOX_NAME)
SETTINGS_HELP = (
    "가용설비 현황 공용 설정(모든 설비 시나리오가 함께 씀) — 공정별 Cut-off: 월별 가용대수를 세는 "
    "W/D 구간의 기준입니다."
)
LOCKED_HELP = "설비 DB 를 읽지 못해 열 수 없습니다 — Alarm 의 오류를 먼저 고칩니다."
# 엑셀·CSV 팝업 열림 값(`equipment_import_dialog.IMPORT_DIALOG` 와 같은 글 — 그 모듈이 이 모듈을
# 불러오므로 거꾸로 부르지 않는다).
IMPORT_DIALOG = "import"


def open_equipment_settings() -> None:
    """「가용설비 설정」 상자의 콜백 — 다른 팝업 칸(사이드바 조건 팝업 등)부터
    비우고, 지난번 열었을 때의 Cut-off 초안을 걷어 최신 저장본에서 연다(`forget_cutoff_draft`)."""
    forget_page_dialogs()
    forget_cutoff_draft()
    st.session_state[EQUIPMENT_DIALOG_KEY] = SETTINGS_DIALOG


def _close_dialog() -> None:
    st.session_state.pop(EQUIPMENT_DIALOG_KEY, None)


def render_equipment_settings_box(*, disabled: bool = False) -> None:
    """사이드바 「가용설비 설정」 상자(조회 조건 패널 바로 밑 · `설비 조회 조건` 카드 위) — 누르면
    팝업.

    페이지가 카드보다 **먼저** 부른다(사이드바는 부른 차례로 선다). `disabled` 는 설비 DB 를 읽지
    못한 회차다 — 상자는 잠긴 채 같은 자리에 선다.
    """
    render_settings_box(
        SETTINGS_DIALOG_TITLE,
        name=SETTINGS_BOX_NAME,
        button_key=SETTINGS_BUTTON_KEY,
        on_click=open_equipment_settings,
        tooltip=LOCKED_HELP if disabled else SETTINGS_HELP,
        disabled=disabled,
    )


@st.dialog(SETTINGS_DIALOG_TITLE, width="large", icon=SETTINGS_ICON, on_dismiss=_close_dialog)
def _settings_dialog(
    repository: DuckDBEquipmentRepository,
    equipment_processes: list[str],
    process_labels: ProcessLabels | None,
    locked_reason: str | None,
) -> None:
    render_cutoff_management(
        repository,
        equipment_processes=equipment_processes,
        process_labels=process_labels,
        locked_reason=locked_reason,
    )


def render_equipment_dialog_host(
    repository: DuckDBEquipmentRepository,
    *,
    equipment_processes: list[str],
    process_labels: ProcessLabels | None,
    locked_reason: str | None,
    import_dialog: Callable[[], None] | None = None,
) -> None:
    """열린 팝업을 그린다 — 이벤트 칸에 늘 한 자리(열렸으면 팝업, 아니면 빈 스타일 자리표시자).
    `import_dialog` 는 열림 칸이 `import` 일 때 부를 엑셀·CSV 팝업(없으면 그 칸은 빈 자리)."""
    opened = st.session_state.get(EQUIPMENT_DIALOG_KEY)
    if opened == SETTINGS_DIALOG:
        _settings_dialog(repository, equipment_processes, process_labels, locked_reason)
    elif opened == IMPORT_DIALOG and import_dialog is not None:
        import_dialog()
    else:
        st.html("<style></style>")
