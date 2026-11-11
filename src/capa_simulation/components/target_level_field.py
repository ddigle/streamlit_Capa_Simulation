# Purpose: 필요 단축 목표 확보율의 사이드바 패널 줄(값 칸)과 고르거나 직접 넣는 팝업을 그린다.

"""필요 단축 목표 확보율 줄 — Space 「필요 단축」 보기와 필요 단축 일정이 **같은 부품**을 쓴다(검수
보드 p-target-form — Space, 2차 보드 Q2-26 — 필요 단축 일정).

- **자리** — 사이드바 조회 조건 패널의 페이지 칸 `LEVEL_SLOT`(첫째 칸은 공용 공정 칸)에 다른 조건
  줄과 같은 이름 줄 + 값 칸(`condition_field`)으로 선다. 처음 값이 무엇인지는 그 화면 Guide 가
  말한다(이름 줄에 길 안내를 적지 않는다 — 설계 규칙 UI-TXT-03). 잠근 회차의 까닭은 값 칸
  풍선이다(UI-INP-07).
- **팝업** — 값 칸을 누르면 그 화면의 팝업 호스트(`DialogHost` — 화면당 하나)만 돌아 목표 다섯
  (`TARGET_LEVELS`) 라디오와 그 밑 직접 입력 칸이 열린다(설계 규칙 UI-PRF-01 · UI-INP-05 —
  2026-11-11 사용자 고칠 것 Q2-26 「목표 확보율 5개 프리셋 외에 직접 입력도 가능하도록」). 라디오를
  고르거나 칸에 넣고 Enter(칸을 떠나도)를 누르면 곧바로 세션 칸에 적고 닫힌 뒤 앱 전체를 다시 돌린다
  (`DialogHost.finish` — 값 칸 글과 본문이 함께 새 목표로 선다, HOME 주요공정 히트맵 팝업과 같은
  꼴). 견주는 값은 세션의 지금 값이라 다시 도는 회차에 같아져 되풀이되지 않는다. 칸에 치고 Enter
  없이 라디오를 누르면 라디오가 이긴다(「버튼 + 직접 입력」 칸 `preset_number_field` 와 같은 규칙 —
  세대 key 없이도 2026-11-11 사본 앱 브라우저에서 누름 길이 0 · 0.15 · 0.6초 여섯 번 모두 라디오).
  숫자 칸의 − · + 단추와 ↑/↓ 키도 한 걸음이 곧 확정이라 그 값을 적용하고 닫힌다.
- **직접 입력** — 퍼센트 숫자 칸이다. 걸음 · 자릿수는 판정 기준 기본 칸(HOME 설정 › 판정 기준 —
  `home_preference.DEFAULT_THRESHOLD_STEP` · `DEFAULT_THRESHOLD_FORMAT`)과 같은 1 · `%.0f` 이고,
  받는 범위는 판정 기준 저장 · 제약 확보율과 한 값 50 ~
  300%(`securement_threshold.THRESHOLD_RANGE`)다. 소수를 치면 사사오입한 정수 % 다(109.5 → 110 —
  `whole_percent`, 판정 기준 칸과 한 규칙). 칸에는 하한 · 상한을 두지 않는다 — 음수를 포함한 범위 밖
  값이 서버에 닿아야 그 까닭을 칸 곁에 적는다(하한을 두면 그 밑 값은 브라우저 칸 검증이 먼저 막아
  영어 풍선만 선다 — 하한 0 을 두는 판정 기준 기본 칸과 여기서 다르다). 범위 밖 · 빈 칸은 칸 바로 밑
  거부 한 줄이고 팝업은 열린 채다(설계 규칙 UI-NTF-03 — 팝업 안 검증 거부는 곁만, 알림창 · 기록
  없음). 받는 범위를 한참 넘는 값(주소 인자 · 칸에 친 아주 긴 수)은 사사오입 전에 거른다
  (`Decimal.quantize` 는 28 자리를 넘으면 멈춘다).
- **지금 값 한 꼴** — 숫자 칸은 늘 지금 목표를 보이고, 라디오는 지금 목표가 다섯 가운데 하나일 때만
  그것이 켜진다(직접 넣은 값이면 라디오는 모두 꺼짐 — `preset_number_field` 의 버튼 줄과 같은 꼴).
  값 칸 글은 다섯이든 직접 넣은 값이든 「115%」 꼴이다(`level_text`).
- **값** — 화면마다 세션 칸 하나다(`state_key` — 위젯 key 가 아니고 공용 프로필에 쓰지 않는다). 칸이
  없거나 받을 수 없는 값(범위 밖 · 숫자 아님)이면 `seed_keys` 차례로 받을 수 있는 값 → 110% 로
  심는다. 다섯 밖의 값은 그 값 하나를 따로
  계산한다(`shortening_source.load_official_shortening(level=)` — 다섯은 미리 계산해 둔 것 그대로).

쓰는 쪽은 그 화면의 호스트를 매 앱 전체 회차 세우며 `dialogs` 를 함께 넘긴다(라디오 · 숫자 칸 key 는
닫으면 지운다 — `DialogHost` 지키는 것 5).
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
    target_preset,
)
from capa_simulation.services.securement_threshold import THRESHOLD_RANGE, threshold_range_text
from capa_simulation.services.threshold_label import threshold_percent, whole_percent
from capa_simulation.sidebar_status import keeps_app_run_open, page_condition_slot

__all__ = [
    "ENTRY_EMPTY",
    "ENTRY_FORMAT",
    "ENTRY_NOT_A_NUMBER",
    "ENTRY_STEP",
    "LEVEL_ICON",
    "LEVEL_LABEL",
    "LEVEL_SLOT",
    "TargetLevelField",
    "entry_out_of_range",
    "level_text",
    "read_level_entry",
    "target_level",
]

# 조회 조건 패널의 둘째 페이지 칸(첫째는 공용 공정 칸 — `process_field`).
LEVEL_SLOT: Final = 1
LEVEL_LABEL: Final = "목표 확보율"
LEVEL_ICON: Final = ":material/flag:"
# 직접 입력 칸 — 판정 기준 기본 칸(`home_preference.DEFAULT_THRESHOLD_STEP` ·
# `DEFAULT_THRESHOLD_FORMAT`)과 같은 걸음 · 꼴(정수 %, 소수 칸이라 「109.5」 가 그대로 와
# 사사오입한다).
ENTRY_STEP: Final = 1.0
ENTRY_FORMAT: Final = "%.0f"
# 칸 곁 단위 글 — 「버튼 + 직접 입력」 칸(`preset_number_field` 의 「% 직접 입력」)과 같은 꼴.
ENTRY_UNIT_LABEL: Final = "% 직접 입력"
# 칸 폭 — `preset_number_field` 의 숫자 칸과 같다.
ENTRY_WIDTH: Final = 132
# 숫자 칸은 글자를 받지 않으므로 화면에서 서는 거부는 빈 칸(지우기 · ⊗)이다. 숫자 아님은 글 값을
# 넘길 때(「목표」)뿐이다.
ENTRY_EMPTY: Final = "칸이 비어 받지 않았습니다."
ENTRY_NOT_A_NUMBER: Final = "숫자가 아니라 받지 않았습니다."
# 받는 범위의 정수 %(사사오입) — 판정 기준 저장 검사
# (`securement_threshold.out_of_range_thresholds`)와 같은 견줌이다(49.5 → 50 은 든다).
_LOW_PERCENT, _HIGH_PERCENT = (threshold_percent(bound) for bound in THRESHOLD_RANGE)
# 사사오입(`threshold_percent` · `whole_percent` — `Decimal.quantize`, 28 자리)에 넘기는 수의
# 크기 상한. 받는 범위(50 ~ 300%)를 한참 넘는 값은 반올림 없이 범위 밖이다 — 비율 · 퍼센트 어느
# 쪽으로 읽어도 범위 밖이고, 그 100 배도 28 자리에 한참 못 미친다.
_ROUNDING_LIMIT: Final = 1e6


def entry_out_of_range(percent: float) -> str:
    """범위 밖 거부 한 줄 — 받는 범위와 친 값(사사오입한 정수 %, 사사오입 전에 거른 아주 큰 값은
    `g` 꼴 — 「1e+30%」)."""
    return f"{threshold_range_text()} 밖이라 받지 않았습니다 — {percent:g}%."


def _number(value: object) -> float | None:
    """유한한 수, 아니면 None. 글이면 끝 「%」 를 걷고 읽는다."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(str(value).strip().removesuffix("%").strip())
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _accepted(percent: int) -> float | None:
    """받는 범위 안의 정수 % → 목표(비율 — 다섯 가운데 하나면 그 선택지와 같은 float)."""
    if not _LOW_PERCENT <= percent <= _HIGH_PERCENT:
        return None
    ratio = percent / 100
    return target_preset(ratio) or ratio


def target_level(value: object) -> float | None:
    """받을 수 있는 목표(비율)면 그 값, 아니면 None — 세션 칸 · 주소 인자(`target=1.15`)를 읽는다.

    다섯 가운데 하나면 그 선택지와 같은 float 이고, 그 밖은 사사오입한 정수 %(`threshold_percent` —
    1.153 → 115%)가 받는 범위(50 ~ 300%) 안일 때 그 % 의 비율이다. 숫자가 아니거나 범위 밖이면 None
    — 범위를 한참 넘는 값(`target=1e30`)은 사사오입 전에 None 이다.
    """
    number = _number(value)
    if number is None or abs(number) > _ROUNDING_LIMIT:
        return None
    return target_preset(number) or _accepted(threshold_percent(number))


def read_level_entry(value: object) -> float | str:
    """직접 입력 칸 값(퍼센트)을 목표(비율)로 — 받을 수 없으면 칸 곁에 적을 거부 글.

    소수는 사사오입한 정수 %(`whole_percent` — 109.5 → 110)로 읽고 그 정수로 범위를 견준다. 범위를
    한참 넘는 값은 사사오입 전에 친 값 그대로 범위 밖 거부다.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return ENTRY_EMPTY
    number = _number(value)
    if number is None:
        return ENTRY_NOT_A_NUMBER
    if abs(number) > _ROUNDING_LIMIT:
        return entry_out_of_range(number)
    percent = whole_percent(number)
    accepted = _accepted(percent)
    return entry_out_of_range(percent) if accepted is None else accepted


def level_text(level: float) -> str:
    """값 칸 · 라디오 글 — 「110%」."""
    return f"{level_percent(level)}%"


class TargetLevelField:
    """화면 하나의 목표 확보율 줄 — 세션 칸 · 값 칸 · 팝업(라디오 + 직접 입력) · 그 화면 호스트."""

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
        # 직접 입력 숫자 칸 — 라디오 key 에서 짓는다(팝업의 입력 위젯 key 둘).
        self.entry_key = f"{pick_key}_entry"
        self.dialog = dialog
        self.host = host
        self.seed_keys = seed_keys
        self._body: DialogBody = st.dialog(
            LEVEL_LABEL, width="small", icon=LEVEL_ICON, on_dismiss=host.close
        )(keeps_app_run_open(self._pick))

    @property
    def dialogs(self) -> dict[str, tuple[DialogBody, tuple[str, ...]]]:
        """그 화면 호스트가 함께 여는 팝업(열림 값 → (팝업, 입력 위젯 key))."""
        return {self.dialog: (self._body, (self.pick_key, self.entry_key))}

    def current(self) -> float:
        """지금 목표 — 세션 칸이 받을 수 있는 값이 아니면 110%(심지 않는다)."""
        return target_level(st.session_state.get(self.state_key)) or DEFAULT_TARGET_LEVEL

    def ensure(self) -> float:
        """세션 칸을 받을 수 있는 값으로 맞추고 돌려준다 — 없거나 어긋났으면 `seed_keys` 차례로 받을
        수 있는 값 → 110% 로 심는다. 다섯 밖이라도 받을 수 있는 값이면 그대로 둔다."""
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
        """값 칸의 콜백 — 초안을 지금 목표로 적고 그 화면 팝업 호스트로 연다(다른 팝업 칸부터 비운다
        — `DialogHost.open`). 라디오는 지금 목표가 다섯 가운데 하나일 때만 켜고(아니면 모두 꺼짐),
        숫자 칸은 늘 지금 목표(%)다."""
        level = self.current()
        st.session_state[self.pick_key] = target_preset(level)
        st.session_state[self.entry_key] = float(level_percent(level))
        self.host.open(self.dialog, self.field_key)

    def _pick(self) -> None:
        """목표 다섯 라디오 + 직접 입력 칸 — **고르거나 넣으면 곧바로 적용하고 닫힌다**. 조작은
        팝업(프래그먼트)만 다시 돌리고, 돌려받은 값이 지금 목표와 다르면 세션에 적고 열림 칸을 지운
        뒤 앱 전체를 다시 돌린다(`DialogHost.finish`). 라디오를 먼저 본다 — 칸에 치고 Enter 없이
        라디오를 누른 회차는 라디오가 이긴다. 칸 값을 받을 수 없으면 칸 바로 밑에 까닭 한 줄을 적고
        팝업은 열린 채다."""
        current = self.current()
        choice = st.radio(
            LEVEL_LABEL,
            options=list(TARGET_LEVELS),
            format_func=level_text,
            key=self.pick_key,
            label_visibility="collapsed",
        )
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            typed = st.number_input(
                f"{LEVEL_LABEL} 직접 입력",
                value=None,
                step=ENTRY_STEP,
                format=ENTRY_FORMAT,
                key=self.entry_key,
                label_visibility="collapsed",
                width=ENTRY_WIDTH,
            )
            st.caption(ENTRY_UNIT_LABEL, width="content")
        picked = target_level(choice)
        if picked is not None and not math.isclose(picked, current):
            self._apply(picked)
        entered = read_level_entry(typed)
        if isinstance(entered, str):
            # 입력 곁 거부 — 고칠 칸이 바로 위다(설계 규칙 UI-NTF-03 · UI-INP-05).
            st.error(entered)
        elif not math.isclose(entered, current):
            self._apply(entered)

    def _apply(self, level: float) -> None:
        st.session_state[self.state_key] = level
        self.host.finish()
