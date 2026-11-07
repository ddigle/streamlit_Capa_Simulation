# Purpose: HOME 사이드바 「HOME 설정」 상자와 그 팝업(쓰는 묶음 다섯 탭)을 둔다.

"""HOME 「설정」 팝업(2026-11-02 사용자 요청 — 전에는 HOME 본문의 `Preference`·`Past Data` 탭).

- **자리**: 사이드바 조회 조건 패널 바로 밑, 「LOB 표시 조건」 카드 **위**에 따로 선 상자
  「HOME 설정」. 카드는 주요 Case 칩 때문에 처음 펼친 채 서서(약 370px) 그 밑에 두면 1280×800 ·
  1500×950 에서 상자가 사이드바 첫 화면 밖으로 밀린다 — 팝업에 닿는 길이 이 상자 하나뿐이다. 펼치는
  확장 패널이 아니라 상자 자체가 단추라 한 번 누르면 팝업이 뜬다 — 오른쪽 끝 `⇕` 는 「이 자리에서
  팝업이 뜨는 칸」 표식이다(`sidebar_style` — 조건 패널 값 칸과 같은 기호). 공용 설정(모든 사용자가
  DB 로 함께 쓰는 값)이 세션 조회 조건(패널·카드)과 상자 단위로 갈려 읽힌다. HOME 본문에는 탭 줄도
  설정 단추도 남지 않아 화면 탭 줄 바로 밑에서 Summary 가 시작한다. 상자 한 칸은 사이드바 설정 상자
  공용 꼴(`components/settings_box.py` — 2026-11-03 가용설비 현황 「가용설비 설정」 도 같은 꼴)로
  그린다.
- **팝업 안**: 쓰는 묶음 다섯 탭(`stateful_tabs` — 닫았다 다시 열면 그 탭, 2026-11-04 사용자 검수
  home-u01 — 전에는 옮겨 온 `Preference`·`Past Data` 두 탭이라 상자 아홉이 한 탭에 세로로 섰다).
  `비교 · 주요 Case` · `판정 기준` · `선행 · 보정` · `공지 · 표시` 는 Preference 편집기, `Past Data`
  는 과거 구간 편집기다(라벨은 `home_state`). 머리 안내 글은 두지 않는다 — 「모든 사용자가 함께 쓰는
  공용 설정 · 저장하지 않고 닫으면 고친 칸은 사라짐」 은 저장 단추 풍선이 말한다
  (`home_preference.SHARED_SAVE_HELP` · `past_data_management.PAST_SHARED_HELP`). 본문은
  `app_pages/home.py` 가 넘긴 함수 둘이다 — 앞 넷의 탭을 라벨로 받는 Preference 함수와 `Past Data`
  탭 본문 함수. 이 모듈은 편집기를 들이지 않는다(주요 Case 칩이 이 모듈의 여는 콜백을 쓰고, 편집기
  쪽이 칩을 그리므로 들이면 순환한다).
- **열림 칸**: HOME 한 칸(`home_state.HOME_DIALOG_KEY` — 값 `settings`). 여는 콜백은
  `forget_page_dialogs()` 부터 부른다(AGENTS 9장 「팝업과 콜백」 — 한 실행에 팝업 하나). 주요 Case
  의 미지정 칩도 이 콜백으로 `비교 · 주요 Case` 탭을 연다(그 Case 칸을 잠깐 강조 —
  `home_main_cases`).
- **호스트**: 이벤트 칸에 늘 한 자리 — 열렸으면 팝업, 아니면 빈 스타일 자리표시자. 팝업 본문은
  이벤트 칸에 쓰지 않는다(편집기는 스타일만 든 `st.html`·토스트를 쓰지 않는다 — 주요 Case 칸 강조
  서식은 그 칸 머리 줄과 한 `st.html` 에 실려 본문 칸이다).
- **저장 뒤에도 팝업을 열어 둔다** — 가용설비 현황 「가용설비 설정」(`equipment_settings_dialog`)과
  같은 AGENTS 9장 「팝업 안 저장이 성공하면 열림 키를 지우고 `st.rerun()`」 의 예외다. 폼 저장(판정
  기준·프리셋·Past Data 등)은 앱 범위 `st.rerun()` 이라 사이드바(주요공정 히트맵 칸·대기 띠)도 그
  회차에 새 값으로 서고, 저장 결과(flash)가 누른 단추 바로 아래에 선다. 고르면 곧 저장되는 두 선택
  상자(비교 시나리오·주요 Case)는 `on_change` 콜백뿐이라 팝업(프래그먼트)만 다시 돌고,
  사이드바(GAP 토글이 잠기는지·주요 Case 칩)는 닫는 회차에 바뀐다 — 고를 때마다 앱 전체를 돌리면
  비교 계획까지 그때마다 새로 읽는데, 둘 다 모달 뒤라 열린 동안 쓸 일이 없다(2026-11-02 검토). 그
  회차의 Main 그림은 팝업을 열기 전에 그린 그림을 그대로 쓰고(`app_pages/home.py` 「팝업이 열린
  회차」), 닫는 회차(`on_dismiss` — 앱 전체)에 지금 조건으로 한 번 만든다.
- **팝업 안 표에는 전체 화면 단추가 없다** — Streamlit 이 `st.dialog` 안 표의 도구 막대에서 전체
  화면을 숨긴다(전에는 HOME 본문 Preference 탭의 편집표 넷 — 판정 기준 월별·선행 B/O·선행
  입고·확보율 보정 — 에 있었다). 달이 많은 표는 팝업(`width="large"`) 안에서 가로로 넘긴다. Guide 가
  알린다.
- **닫으면 제출하지 않은 폼 편집은 사라진다** — Preference 편집기는 모두 폼이라 서버가 제출 전
  편집을 모르고, 닫힌 동안 마운트되지 않는다(Guide 「닫기 전에 저장합니다」). 그래서 상자·화면 탭
  줄의 점이나 떠나기 확인 대상이 아니다. 팝업 안 탭을 옮기는 것은 닫기가 아니다 — 탭 본문은 숨은
  채 모두 그려져 고친 칸이 남는다(`stateful_tabs`). Past Data 의 읽어 둔 표(대기)는 세션 칸이라
  닫아도 남고, 상자 왼쪽 주황 띠·팝업 안 `Past Data` 탭 점·화면 탭 줄 HOME 점이 말한다.
- **계산이 멈춘 회차에는 상자를 잠근다** — 팝업 본문이 계산 결과(월 축·공정 목록)를 쓴다. 상자는
  잠긴 채 같은 자리에 서서 사이드바가 회차마다 흔들리지 않는다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

import streamlit as st

from capa_simulation.components.past_data_management import forget_past_paste
from capa_simulation.components.settings_box import (
    SETTINGS_ICON,
    render_settings_box,
)
from capa_simulation.components.settings_box import (
    settings_box_key as _settings_box_key,
)
from capa_simulation.components.tab_marks import mark_pending_tabs
from capa_simulation.components.tab_state import OpenTab, remember_open_tab, stateful_tabs
from capa_simulation.home_state import (
    HOME_DIALOG_KEY,
    HOME_PAST_TAB,
    HOME_PREFERENCE_TABS,
    HOME_SETTINGS_DIALOG,
    HOME_SETTINGS_TAB_KEY,
    HOME_SETTINGS_TAB_LABELS,
)
from capa_simulation.page_bootstrap import forget_page_dialogs

__all__ = [
    "SETTINGS_BOX_KEY",
    "SETTINGS_BUTTON_KEY",
    "SETTINGS_TITLE",
    "close_home_settings",
    "home_settings_open",
    "open_home_settings",
    "render_home_dialog_host",
    "render_home_settings_box",
    "settings_box_key",
]

SETTINGS_TITLE = "HOME 설정"
# 상자 이름 — 상자(컨테이너) key 는 사이드바 설정 상자 공용 꼴(`settings_box.settings_box_key` —
# 서식이 접두어로 고른다)이고, 읽어 두고 저장하지 않은 Past Data 가 있으면 끝에 `PENDING_SUFFIX` 를
# 단다(왼쪽 주황 띠 — 조건 칸과 같은 꼴).
SETTINGS_BOX_NAME = "home_settings"
SETTINGS_BOX_KEY = _settings_box_key(SETTINGS_BOX_NAME)
SETTINGS_BUTTON_KEY = "home_settings_open"
SETTINGS_HELP = (
    "HOME 공용 설정(모든 사용자가 함께 씀) — 비교 · 주요 Case / 판정 기준 / 선행 · 보정: "
    "선행 B/O · 선행 입고 실적 · 확보율 보정 / 공지 · 표시: 공지 · Top5 구간 · "
    "주요공정 프리셋 / Past Data: 과거 구간"
)
PENDING_HELP = "읽어 두고 저장하지 않은 Past Data 가 있습니다 — 팝업의 Past Data 탭에서 저장합니다."
STOPPED_HELP = "계산이 멈춰 열 수 없습니다 — Alarm 의 오류를 먼저 고칩니다."


def settings_box_key(*, pending: bool) -> str:
    """상자 key — 대기가 있으면 끝에 `PENDING_SUFFIX`."""
    return _settings_box_key(SETTINGS_BOX_NAME, pending=pending)


def home_settings_open() -> bool:
    """이번 회차에 「설정」 팝업이 열려 있는가(열림 칸 값)."""
    return st.session_state.get(HOME_DIALOG_KEY) == HOME_SETTINGS_DIALOG


def open_home_settings(tab: str | None = None) -> None:
    """「HOME 설정」 상자·주요 Case 미지정 칩의 콜백 — 다른 팝업 칸부터 비우고 팝업을 연다.

    `tab` 을 주면 그 안쪽 탭으로 연다(미지정 칩 → `비교 · 주요 Case`). 탭 위젯은 이 회차에 아직
    그려지지 않았으므로(콜백은 스크립트보다 먼저 돈다) 위젯 칸과 기억 칸을 함께 적는다. 지난번에 편
    Past Data 붙여넣기 칸은 걷는다 — 새로 열면 표 상자만 선다.
    """
    forget_page_dialogs()
    forget_past_paste()
    if tab is not None:
        st.session_state[HOME_SETTINGS_TAB_KEY] = tab
        remember_open_tab(HOME_SETTINGS_TAB_KEY, tab)
    st.session_state[HOME_DIALOG_KEY] = HOME_SETTINGS_DIALOG


def close_home_settings() -> None:
    """팝업을 닫는다(`on_dismiss` — 닫는 회차는 앱 전체). 편 붙여넣기 칸도 걷는다."""
    st.session_state.pop(HOME_DIALOG_KEY, None)
    forget_past_paste()


def render_home_settings_box(*, pending: bool, stopped: bool = False) -> None:
    """사이드바 「HOME 설정」 상자(조회 조건 패널 바로 밑 · `LOB 표시 조건` 카드 위) — 누르면 팝업.

    `pending` 은 읽어 두고 저장하지 않은 Past Data 가 있는가 — 상자 왼쪽 주황 띠와 팝업 안 `Past
    Data` 탭 점(스타일만 든 `st.html` 하나 — 찍을 것이 없어도 매 회차 그려 앞 회차의 점을 덮는다).
    `stopped` 는 계산이 멈춘 회차다 — 상자는 잠긴 채 같은 자리에 선다.
    """
    render_settings_box(
        SETTINGS_TITLE,
        name=SETTINGS_BOX_NAME,
        button_key=SETTINGS_BUTTON_KEY,
        on_click=open_home_settings,
        tooltip=STOPPED_HELP if stopped else (PENDING_HELP if pending else SETTINGS_HELP),
        disabled=stopped,
        pending=pending,
    )
    mark_pending_tabs(
        HOME_SETTINGS_TAB_KEY, HOME_SETTINGS_TAB_LABELS, {HOME_PAST_TAB} if pending else set()
    )


@st.dialog(SETTINGS_TITLE, width="large", icon=SETTINGS_ICON, on_dismiss=close_home_settings)
def _settings_dialog(
    preference: Callable[[Mapping[str, OpenTab]], None],
    past_data: Callable[[], None],
) -> None:
    tabs = dict(
        zip(
            HOME_SETTINGS_TAB_LABELS,
            stateful_tabs(HOME_SETTINGS_TAB_LABELS, key=HOME_SETTINGS_TAB_KEY),
            strict=True,
        )
    )
    preference({label: tabs[label] for label in HOME_PREFERENCE_TABS})
    with tabs[HOME_PAST_TAB]:
        past_data()


def render_home_dialog_host(
    *,
    preference: Callable[[Mapping[str, OpenTab]], None],
    past_data: Callable[[], None],
) -> None:
    """열린 팝업을 그린다 — 이벤트 칸에 늘 한 자리(열렸으면 팝업, 아니면 빈 스타일 자리표시자).

    `preference` 는 앞 네 탭(`home_state.HOME_PREFERENCE_TABS` — 라벨 → 탭)의 본문을 그린다 — 상자를
    제 탭 안에 넣고, 숨은 회차에 DB 를 읽지 않으려는 상자(주요 Case)가 제 탭을 본다. `past_data` 는
    `Past Data` 탭 본문이다.
    """
    if home_settings_open():
        _settings_dialog(preference, past_data)
    else:
        st.html("<style></style>")
