# Purpose: 미리 정한 값 버튼과 직접 입력 숫자 칸을 한 세션 값으로 묶어 그린다.

"""버튼 + 직접 입력 — 한 값을 두 위젯으로 고른다(제약 시뮬레이션 D10).

**정본은 위젯이 아닌 한 칸**(`value_key`)이다. 두 위젯은 그 칸에서 매 회차 다시 선다.

- **버튼**(`st.pills`, 한 개 고름, `required=True`) — 정본이 버튼 값이면 그 버튼이 켜지고, 맞춤
  값이면 모두 꺼진다. 1.63 의 `required=True` 는 고른 버튼을 다시 눌러도 아무 일이 없다(선택 해제를
  프레임워크가 막는다). 콜백은 받은 값이 있을 때만 정본을 그 값으로 적는다.
- **숫자 칸**(`st.number_input`, 라벨 접음) — 늘 지금 값을 보인다(정본이 `None` 이면 `fallback`).
  콜백이 정본을 그 값으로 적고, 범위는 위젯이 막는다. 버튼 값과 같으면 그 버튼이 켜진 꼴로 다시
  선다.
- **세션 칸이 그 값과 다를 때만 적는다** — 같아도 매 회차 적으면 `set_value` 가 회차마다 가서 다른
  위젯이 돌린 앱 전체 회차가 숫자 칸에 치다 만 글을 덮는다. 두 위젯 모두 값으로 주고받아(버튼은 늘
  같은 라벨 글자) 라벨 되보냄 함정이 없다. 위젯에 `default=`·`value=` 를 주지 않는다(AGENTS 9장).
- `persist_state` 는 주지 않는다 — 정본이 위젯 아닌 칸이라 페이지를 오가도 남고, 위젯 칸은 매 회차
  정본에서 다시 선다.

`None` 버튼(「HOME 기준」 같은 「값 없음」 버튼)은 버튼 칸에 글자 표지(`NONE_OPTION`)로 든다 — 버튼
칸의 `None` 은 「모두 꺼짐」 이라 겹치지 않게. 그때 숫자 칸은 `fallback` 을 보이고, 그 값을 그대로
다시 적으면 값이 안 바뀌어 콜백이 없으므로 정본은 `None` 그대로다(Guide 한 줄).

`step` 이 정수면 정본·숫자 칸 모두 `int` 로 접는다(위젯은 min·max·step 의 수 형이 같아야 한다).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Final, Literal

import streamlit as st

from capa_simulation.design import tokens

__all__ = ["NONE_OPTION", "render_preset_number_field"]

NONE_OPTION: Final = "__none__"
"""버튼 칸에서 `None` 버튼을 가리키는 글자 표지."""

_MISSING: Final = object()

PresetTone = Literal["accent", "warning"]


def _number(value: float, integer: bool) -> float | int:
    return int(round(value)) if integer else float(value)


def _valid(
    value: object, *, minimum: float, maximum: float, presets: Sequence[float | None]
) -> bool:
    if value is None:
        return None in presets
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return minimum <= float(value) <= maximum


def _option_of(value: float | None, presets: Sequence[float | None]) -> float | str | None:
    """정본 값이 버튼 값이면 그 버튼(`None` 은 표지), 아니면 None(모두 꺼짐)."""
    if value is None:
        return NONE_OPTION if None in presets else None
    for preset in presets:
        if preset is not None and float(preset) == float(value):
            return preset
    return None


def _write_if_changed(key: str, value: object) -> None:
    """칸이 없거나 그 값과 다를 때만 적는다 — 같은 값을 다시 적으면 `set_value` 가 회차마다 간다."""
    if st.session_state.get(key, _MISSING) != value:
        st.session_state[key] = value


def _pick_preset(value_key: str, pills_key: str, integer: bool) -> None:
    """버튼 콜백 — 고른 버튼이 있을 때만 정본을 그 값으로(`None` 버튼은 `None`)."""
    picked = st.session_state.get(pills_key)
    if picked is None:
        return
    if picked == NONE_OPTION:
        st.session_state[value_key] = None
    elif isinstance(picked, (int, float)) and not isinstance(picked, bool):
        st.session_state[value_key] = _number(float(picked), integer)


def _pick_number(value_key: str, input_key: str, integer: bool) -> None:
    """숫자 칸 콜백 — 정본을 그 값으로(범위는 위젯이 막는다)."""
    typed = st.session_state.get(input_key)
    if isinstance(typed, (int, float)) and not isinstance(typed, bool):
        st.session_state[value_key] = _number(float(typed), integer)


# 켜진 버튼 — 1.63 의 pills 단추는 react-aria 토글 단추라 한 개 고름이면 켜진 단추가
# `role="radio"`·`aria-checked="true"` 다(옛 `stBaseButton-pillsActive` testid 는 그리지 않는다).
ACTIVE_PILL_SELECTOR: Final = 'button[role="radio"][aria-checked="true"]'


def _tone_style(pills_key: str, tone: PresetTone) -> str:
    """켜진 버튼 색 — 주의 색(제약 확보율 — 초안의 주황)일 때만 덮는다. 기본은 앱 강조색이다.

    주의 색은 글자를 얹는 **면색**이라 글자는 `TEXT` 다(밝은 테마 검정 · 어두운 테마 흰색 — 두 테마
    모두 4.5:1 이상, `tokens` 상태색 주석). 면 위에 `SURFACE` 를 얹으면 어두운 테마에서 3.0:1 이다.
    """
    if tone != "warning":
        return ""
    color = tokens.STATUS_WARNING
    return (
        f"<style>.st-key-{pills_key} {ACTIVE_PILL_SELECTOR} "
        f"{{ background: {color} !important; border-color: {color} !important; "
        f"color: {tokens.TEXT} !important; }}</style>"
    )


def render_preset_number_field(
    label: str,
    *,
    value_key: str,
    pills_key: str,
    input_key: str,
    presets: Sequence[float | None],
    default: float | None,
    minimum: float,
    maximum: float,
    step: float,
    unit: str,
    number_format: str,
    fallback: float,
    preset_label: Callable[[float | None], str],
    disabled: bool = False,
    help: str | None = None,
    tone: PresetTone = "accent",
) -> float | None:
    """버튼 줄과 숫자 칸을 지금 컨테이너에 그리고 정본 값을 돌려준다.

    정본 칸이 없거나 쓸 수 없는 값이면 `default` 를 심는다. `fallback` 은 정본이 `None` 일 때 숫자
    칸이 보일 값이다(HOME 기준이면 기본 확보 기준 %).
    """
    integer = float(step).is_integer() and float(minimum).is_integer()
    held = st.session_state.get(value_key, _MISSING)
    if held is _MISSING or not _valid(held, minimum=minimum, maximum=maximum, presets=presets):
        st.session_state[value_key] = None if default is None else _number(float(default), integer)
    value = st.session_state.get(value_key)
    canonical: float | None = None if value is None else float(value)

    shown = canonical if canonical is not None else float(fallback)
    shown = min(max(shown, float(minimum)), float(maximum))
    _write_if_changed(pills_key, _option_of(canonical, presets))
    _write_if_changed(input_key, _number(shown, integer))

    options: list[float | str] = [NONE_OPTION if preset is None else preset for preset in presets]

    def format_option(option: float | str) -> str:
        return preset_label(None if option == NONE_OPTION else float(option))

    style = _tone_style(pills_key, tone)
    if style:
        st.html(style)
    st.pills(
        label,
        options,
        selection_mode="single",
        required=True,
        format_func=format_option,
        key=pills_key,
        on_change=_pick_preset,
        args=(value_key, pills_key, integer),
        disabled=disabled,
        help=help,
    )
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.number_input(
            f"{label} 직접 입력",
            min_value=_number(minimum, integer),
            max_value=_number(maximum, integer),
            step=_number(step, integer),
            format=number_format,
            key=input_key,
            on_change=_pick_number,
            args=(value_key, input_key, integer),
            disabled=disabled,
            label_visibility="collapsed",
            width=132,
        )
        st.caption(f"{unit} 직접 입력", width="content")
    return canonical
