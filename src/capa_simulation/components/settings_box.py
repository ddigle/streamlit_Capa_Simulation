# Purpose: 화면 설정 팝업을 여는 사이드바 「… 설정」 상자 한 칸(패널 밑 · 카드 위)을 그린다.

"""설정 단추는 사이드바 상자다(2026-11-03 사용자 지시 — 「가용설비 설정 버튼을 사이드바 상자로
옮기는데, 설정 버튼이 페이지에 배치된 경우가 다른 페이지에도 있으면 전부 동일하게 사이드바
상자로」).

- **자리**: 사이드바 조회 조건 패널 바로 밑, 그 화면의 조건 카드 **위**. 사이드바는 부른 차례로
  서므로 페이지가 카드(`condition_card`)보다 **먼저** 부른다. 카드는 펼치면 길어(HOME 「LOB 표시
  조건」 약 370px) 그 밑이면 1280×800 · 1500×950 사이드바 첫 화면 밖으로 밀린다 — 팝업에 닿는 길이
  이 상자 하나뿐이다.
- **꼴**: 펼치는 확장 패널이 아니라 상자 자체가 전폭 단추라 한 번 누르면 팝업이 뜬다. 서식은 key
  접두어 (`sidebar_status.DIALOG_BOX_PREFIX`) 하나로 `sidebar_style._dialog_box_style` 이 건다 —
  조건 카드와 같은 면 · 글자에 오른쪽 끝 `⇕`(이 자리에서 팝업이 뜨는 칸). 공용 설정(모든 사용자가 DB
  로 함께 쓰는 값)이 세션 조회 조건(패널 · 카드)과 상자 단위로 갈려 읽힌다.
- **화면 몫**: 열림 칸 · 여는 콜백(`forget_page_dialogs()` 부터) · 팝업 호스트(이벤트 칸 한 자리)는
  그 화면 모듈이 갖는다 — HOME `home_settings`, 가용설비 현황 `equipment_settings_dialog`. 이 모듈은
  상자만 그린다.
- **잠금**: 팝업 본문이 쓰는 재료를 그 회차에 만들지 못했으면(HOME 계산 멈춤 · 설비 DB 를 못 읽음)
  잠긴 채 같은 자리에 선다 — 사이드바가 회차마다 흔들리지 않는다. 잠긴 상자는 표식을 걷는다(서식).
- **대기**: 읽어 두고 저장하지 않은 것이 팝업 안에 있으면 key 끝에 `PENDING_SUFFIX` — 왼쪽 주황
  띠(HOME Past Data). 상자 key 가 바뀌어도 단추 key 는 그대로라 누름은 잃지 않는다.
- **탭에 매인 설정**은 아직 없다 — 생기면 그 탭을 볼 때만 상자를 세우지 않고, 늘 세운 상자의 팝업
  안에서 탭 이름을 단 묶음 머리로 가른다(상자가 탭마다 생겼다 사라지면 사이드바 자리가 흔들린다).
- **도구 팝업도 같은 꼴이다** — 필요 단축 일정 「Qual 마감 계산기」(데이터와 잇지 않는 계산기 —
  설정이 아니다)는 2026-11-09 사용자 검수 g03-1 로 머리 끝 단추에서 이 상자 꼴(`icon` 만 다르다)로
  옮겼다. 팝업을 여는 사이드바 상자 꼴은 하나다(설계 규칙 UI-CON-04).
"""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

from capa_simulation.components.condition_field import PENDING_SUFFIX
from capa_simulation.sidebar_status import DIALOG_BOX_PREFIX

__all__ = ["SETTINGS_ICON", "render_settings_box", "settings_box_key"]

SETTINGS_ICON = ":material/settings:"


def settings_box_key(name: str, *, pending: bool = False) -> str:
    """상자(컨테이너) key — `DIALOG_BOX_PREFIX` + 이름, 대기가 있으면 끝에 `PENDING_SUFFIX`."""
    return f"{DIALOG_BOX_PREFIX}{name}{PENDING_SUFFIX if pending else ''}"


def render_settings_box(
    title: str,
    *,
    name: str,
    button_key: str,
    on_click: Callable[[], None],
    tooltip: str,
    disabled: bool = False,
    pending: bool = False,
    icon: str = SETTINGS_ICON,
) -> None:
    """사이드바 「… 설정」 상자 한 칸 — 누르면 `on_click` 이 그 화면의 팝업 열림 칸을 적는다.

    `name` 은 상자 key 의 이름(화면마다 하나), `button_key` 는 단추 위젯 key(화면 확인 · 시험이
    이 key 로 누른다). `tooltip` 은 마우스를 올렸을 때의 풍선 — 팝업 안에 무엇이 있는지, 왜
    잠겼는지, 무엇이 대기 중인지.
    """
    with st.sidebar.container(key=settings_box_key(name, pending=pending)):
        st.button(
            title,
            icon=icon,
            key=button_key,
            on_click=on_click,
            width="stretch",
            disabled=disabled,
            help=tooltip,
        )
