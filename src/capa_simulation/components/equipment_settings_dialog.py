# Purpose: 가용설비 현황 머리 「설정」 단추와 그 팝업(공정별 Cut-off)의 열림 칸·호스트를 둔다.

"""가용설비 현황 「설정」 팝업(2026-10-24 사용자 결정 — 두 탭 개편, 그 전에는 `Preference` 탭).

- **자리**: 제목 줄 끝 칸의 「설정」 단추(`render_page_header(trailing=)`) → 큰 팝업. 안은 묶음 머리
  「공정별 Cut-off」 하나(`render_cutoff_management` 그대로)다 — 나중 설정은 같은 팝업에 묶음 머리로
  붙인다(D14).
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
from capa_simulation.page_bootstrap import PAGE_DIALOG_SUFFIX, forget_page_dialogs
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository

__all__ = [
    "EQUIPMENT_DIALOG_KEY",
    "IMPORT_DIALOG",
    "SETTINGS_BUTTON_KEY",
    "SETTINGS_DIALOG",
    "SETTINGS_DIALOG_TITLE",
    "open_equipment_settings",
    "render_equipment_dialog_host",
    "render_equipment_settings_button",
]

# 가용설비 현황의 팝업 칸(페이지에 한 칸). 값이 팝업을 가른다.
EQUIPMENT_DIALOG_KEY = f"available_equipment{PAGE_DIALOG_SUFFIX}"
SETTINGS_DIALOG = "settings"
SETTINGS_DIALOG_TITLE = "설정"
SETTINGS_BUTTON_KEY = "equipment_settings_open_v1"
# 엑셀·CSV 팝업 열림 값(`equipment_import_dialog.IMPORT_DIALOG` 와 같은 글 — 그 모듈이 이 모듈을
# 불러오므로 거꾸로 부르지 않는다).
IMPORT_DIALOG = "import"


def open_equipment_settings() -> None:
    """「설정」 단추·「설정에서 보기」 의 콜백 — 다른 팝업 칸(사이드바 조건 팝업 등)부터 비우고,
    지난번 열었을 때의 Cut-off 초안을 걷어 최신 저장본에서 연다(`forget_cutoff_draft`)."""
    forget_page_dialogs()
    forget_cutoff_draft()
    st.session_state[EQUIPMENT_DIALOG_KEY] = SETTINGS_DIALOG


def _close_dialog() -> None:
    st.session_state.pop(EQUIPMENT_DIALOG_KEY, None)


def render_equipment_settings_button() -> None:
    """제목 줄 끝 칸의 「설정」 단추(`render_page_header(trailing=)`)."""
    st.button(
        SETTINGS_DIALOG_TITLE,
        icon=":material/settings:",
        key=SETTINGS_BUTTON_KEY,
        on_click=open_equipment_settings,
        help=(
            "공정별 Cut-off(모든 설비 시나리오 공용) — 월별 가용대수를 세는 W/D 구간의 기준입니다."
        ),
    )


@st.dialog(
    SETTINGS_DIALOG_TITLE, width="large", icon=":material/settings:", on_dismiss=_close_dialog
)
def _settings_dialog(
    repository: DuckDBEquipmentRepository,
    equipment_processes: list[str],
    process_labels: ProcessLabels | None,
    locked_reason: str | None,
) -> None:
    st.caption(
        "가용설비 현황 계산에 쓰는 공용 설정입니다 — 모든 설비 시나리오가 함께 씁니다. 표를 "
        "고친 뒤 닫기 전에 저장합니다(저장하지 않고 닫으면 고친 칸은 사라집니다)."
    )
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
