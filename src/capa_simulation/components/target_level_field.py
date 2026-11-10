# Purpose: 필요 단축 목표 확보율의 사이드바 조회 조건 패널 줄(값 칸)과 고르는 팝업 한 벌을 그린다.

"""필요 단축 목표 확보율 줄 — Space 「필요 단축」 보기와 필요 단축 일정이 **같은 부품**을 쓴다(검수
보드 p-target-form — Space, 2차 보드 Q2-26 — 필요 단축 일정).

- **자리** — 사이드바 조회 조건 패널의 페이지 칸 `LEVEL_SLOT`(첫째 칸은 공용 공정 칸)에 다른 조건
  줄과 같은 이름 줄 + 값 칸(`condition_field`)으로 선다. 처음 값이 무엇인지는 그 화면 Guide 가
  말한다(이름 줄에 길 안내를 적지 않는다 — 설계 규칙 UI-TXT-03). 잠근 회차의 까닭은 값 칸
  풍선이다(UI-INP-07).
- **팝업** — 값 칸을 누르면 그 화면의 팝업 호스트(`DialogHost` — 화면당 하나)만 돌아 목표 다섯
  (`TARGET_LEVELS`) 라디오가 열린다(설계 규칙 UI-PRF-01). 고르면 곧바로 세션 칸에 적고 닫힌 뒤 앱
  전체를 다시 돌린다(`DialogHost.finish` — 값 칸 글과 본문이 함께 새 목표로 선다, HOME 주요공정
  히트맵 팝업과 같은 꼴). 견주는 값은 세션의 지금 값이라 다시 도는 회차에 같아져 되풀이되지 않는다.
  다섯 목표는 미리 계산돼 있어 공용 저장값을 다시 읽을 것이 없다.
- **값** — 화면마다 세션 칸 하나다(`state_key` — 위젯 key 가 아니고 공용 프로필에 쓰지 않는다). 칸이
  없거나 다섯 가운데 하나가 아니면 `seed_keys` 차례로 다섯 가운데 하나인 값 → 110% 로 심는다.

쓰는 쪽은 그 화면의 호스트를 매 앱 전체 회차 세우며 `dialogs` 를 함께 넘긴다(라디오 key 는 닫으면
지운다 — `DialogHost` 지키는 것 5).
"""

from __future__ import annotations

import math
from typing import Final

import streamlit as st

from capa_simulation.components.condition_field import condition_field
from capa_simulation.components.dialog_host import DialogBody, DialogHost
from capa_simulation.services.required_shortening import (
    DEFAULT_TARGET_LEVEL,
    TARGET_LEVELS,
    level_percent,
)
from capa_simulation.sidebar_status import keeps_app_run_open, page_condition_slot

__all__ = [
    "LEVEL_ICON",
    "LEVEL_LABEL",
    "LEVEL_SLOT",
    "TargetLevelField",
    "level_text",
    "target_level",
]

# 조회 조건 패널의 둘째 페이지 칸(첫째는 공용 공정 칸 — `process_field`).
LEVEL_SLOT: Final = 1
LEVEL_LABEL: Final = "목표 확보율"
LEVEL_ICON: Final = ":material/flag:"


def target_level(value: object) -> float | None:
    """다섯 목표 가운데 하나면 그 값(선택지와 같은 float), 아니면 None."""
    try:
        number = float(str(value))
    except ValueError:
        return None
    return next((level for level in TARGET_LEVELS if math.isclose(level, number)), None)


def level_text(level: float) -> str:
    """값 칸 · 라디오 글 — 「110%」."""
    return f"{level_percent(level)}%"


class TargetLevelField:
    """화면 하나의 목표 확보율 줄 — 세션 칸 · 값 칸 · 팝업 라디오 · 그 화면 팝업 호스트."""

    def __init__(
        self,
        *,
        state_key: str,
        field_key: str,
        slug: str,
        pick_key: str,
        dialog: str,
        host: DialogHost,
        seed_keys: tuple[str, ...] = (),
    ) -> None:
        self.state_key = state_key
        self.field_key = field_key
        self.slug = slug
        self.pick_key = pick_key
        self.dialog = dialog
        self.host = host
        self.seed_keys = seed_keys
        self._body: DialogBody = st.dialog(
            LEVEL_LABEL, width="small", icon=LEVEL_ICON, on_dismiss=host.close
        )(keeps_app_run_open(self._pick))

    @property
    def dialogs(self) -> dict[str, tuple[DialogBody, tuple[str, ...]]]:
        """그 화면 호스트가 함께 여는 팝업(열림 값 → (팝업, 입력 위젯 key))."""
        return {self.dialog: (self._body, (self.pick_key,))}

    def current(self) -> float:
        """지금 목표 — 세션 칸이 다섯 가운데 하나가 아니면 110%(심지 않는다)."""
        return target_level(st.session_state.get(self.state_key)) or DEFAULT_TARGET_LEVEL

    def ensure(self) -> float:
        """세션 칸을 다섯 가운데 하나로 맞추고 돌려준다 — 없거나 어긋났으면 `seed_keys` 차례로 다섯
        가운데 하나인 값 → 110% 로 심는다."""
        level = target_level(st.session_state.get(self.state_key))
        if level is None:
            seeds = (target_level(st.session_state.get(key)) for key in self.seed_keys)
            level = next((seed for seed in seeds if seed is not None), DEFAULT_TARGET_LEVEL)
            st.session_state[self.state_key] = level
        return level

    def render(self, *, help: str | None = None, disabled: bool = False) -> float:
        """패널 칸(`LEVEL_SLOT`)에 이름 줄 + 값 칸을 그리고 지금 목표를 돌려준다. `disabled` 면 값
        칸을 잠그고 `help` 가 그 까닭 풍선이다."""
        level = self.ensure()
        with page_condition_slot(LEVEL_SLOT).container():
            condition_field(
                LEVEL_LABEL,
                level_text(level),
                slug=self.slug,
                key=self.field_key,
                icon=LEVEL_ICON,
                help=help,
                disabled=disabled,
                on_click=self.open,
            )
        return level

    def open(self) -> None:
        """값 칸의 콜백 — 라디오 초안을 지금 목표로 적고 그 화면 팝업 호스트로 연다(다른 팝업 칸부터
        비운다 — `DialogHost.open`)."""
        st.session_state[self.pick_key] = self.current()
        self.host.open(self.dialog, self.field_key)

    def _pick(self) -> None:
        """목표 다섯 라디오 — **고르면 곧바로 적용하고 닫힌다**. 라디오 조작은 팝업(프래그먼트)만
        다시 돌리고, 돌려받은 값이 지금 목표와 다르면 세션에 적고 열림 칸을 지운 뒤 앱 전체를 다시
        돌린다(`DialogHost.finish`)."""
        choice = st.radio(
            LEVEL_LABEL,
            options=list(TARGET_LEVELS),
            format_func=level_text,
            key=self.pick_key,
            label_visibility="collapsed",
        )
        picked = target_level(choice)
        if picked is not None and picked != self.current():
            st.session_state[self.state_key] = picked
            self.host.finish()
