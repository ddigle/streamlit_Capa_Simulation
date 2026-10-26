# Purpose: 미리 정한 값 버튼과 직접 입력 숫자 칸을 한 세션 값으로 묶어 그린다.

"""버튼 + 직접 입력 — 한 값을 두 위젯으로 고른다(제약 시뮬레이션 D10).

**정본은 위젯이 아닌 한 칸**(`value_key`)이다. 두 위젯은 그 칸에서 매 회차 다시 선다.

- **버튼**(`st.pills`, 한 개 고름, `required=False`) — 정본이 버튼 값이면 그 버튼이 켜지고, 맞춤
  값이면 보이는 버튼은 모두 꺼진다. 콜백은 받은 버튼 값으로 정본을 적는다. **켜진 버튼을 다시
  누르면** 프런트가 그 버튼을 풀어 `None` 을 보내는데, 그것은 「그 버튼을 다시 누름」 이다 —
  콜백은 서버가 마지막으로 켠 버튼(`_lit_key` 칸 — 맞춤 값이 되어도 지우지 않는다)으로 정본을
  적고, 그리기가 그 버튼을 다시 켠다. `required=True` 는 켜진 버튼 누름을 프런트가 삼켜 콜백이
  없었다 — 칸에 치고 Enter 없이 켜진 버튼을 누르면 친 값이 이겼다(2026-10-26 E2E).
- **맞춤 값은 숨은 버튼 하나가 켜진 꼴이다**(`CUSTOM_OPTION` — 버튼 줄 끝, CSS 로 숨긴다). 버튼
  칸이 `None` 이 되는 것은 켜진 버튼을 풀었을 때뿐이라야 그 `None` 이 늘 「바뀜」 으로 콜백에
  닿는다. 맞춤 값을 `None` 으로 두면, 사람 손 빠르기의 누름(누르고 떼기 사이 0.1초 남짓)에서는 칸
  확정 회차가 버튼 칸을 먼저 `None` 으로 적고, 프런트가 그 회차를 받기 전에 뗀 누름이 켜진 버튼을
  풀어 같은 `None` 을 보내 콜백이 없었다(2026-10-26 사본 앱 — 즉시 누름·0.6초 누름은 버튼이
  이겼고 0.15초 누름만 친 값이 이겼다).
- **숫자 칸**(`st.number_input`, 라벨 접음) — 늘 지금 값을 보인다(정본이 `None` 이면 `fallback`).
  콜백이 정본을 그 값으로 적고, 범위는 위젯이 막는다. 버튼 값과 같으면 그 버튼이 켜진 꼴로 다시
  선다.
- **세션 칸이 그 값과 다를 때만 적는다** — 같아도 매 회차 적으면 `set_value` 가 회차마다 가서 다른
  위젯이 돌린 앱 전체 회차가 숫자 칸에 치다 만 글을 덮는다. 두 위젯 모두 값으로 주고받아(버튼은 늘
  같은 라벨 글자) 라벨 되보냄 함정이 없다. 버튼 줄에는 `default=` 를 주지 않는다(AGENTS 9장).
- **숫자 칸은 적지 않은 회차에만 지금 값을 `value=` 로 싣는다.** 새 key 의 칸은 그 key 를 처음
  적은 회차가 `set_value` 로 값을 실어 보내는데, 그 회차가 보내기 전에 다음 누름에 끊기면 다음
  회차는 같은 값이라 적지 않아 `set_value` 없이 칸이 닿는다 — 브라우저는 처음 보는 칸을 기본값
  (`value=` 가 없으면 최소값 50)으로 세우고 다음 조작에 그 50 을 되보내 정본이 말없이 50 이 됐다
  (2026-10-27 E2E — 켜진 버튼 빠른 두 번 누름 뒤 더블클릭, 서버가 붐빌 때). 기본값이 지금 값이면
  `set_value` 없이 닿아도 그 값으로 선다. 적은 회차에는 싣지 않는다 — 둘을 함께 주면 Streamlit 이
  「기본값과 세션 API 를 함께 썼다」고 경고하고, 그 회차는 `set_value` 가 값을 싣는다. key 가 같은
  칸의 기본값이 바뀌어도 브라우저는 쥔 값을 그대로 둔다(기본값은 처음 세울 때만 쓴다).
- **친 값은 칸이 보이는 자리까지 접는다**(`number_format` 의 소수 자리 — `%.1f` 면 첫째 자리, 반은
  올림). 칸은 그 자리까지만 보이므로 112.34 를 그대로 정본에 두면 칸은 112.3 · 머리·판정 글·그래프는
  112.34% 로 갈렸다(2026-10-27 E2E). 반 올림은 브라우저 칸의 `toFixed` 와 같은 꼴이다(112.25 →
  112.3). 0.5 단위로 맞추지는 않는다(+/− 단추만 `step` 씩이다).
- **버튼을 누르면 숫자 칸을 새 key 로 다시 세운다**(`_input_widget_key` — 세대 칸을 올린다).
  1.63 숫자 칸은 범위 밖 글(예: 301)을 치고 칸을 떠나면 그 글을 확정하지 않은 채 쥐고, 쥔 동안은
  서버가 보낸 새 값(`set_value`)을 무시한다 — 같은 key 로는 버튼 값이 칸에 서지 않고 빨간 범위 밖
  표시가 남는다. 새 key 면 프런트가 칸을 새로 그려 쥔 글이 사라진다. 숫자 칸 콜백은 세대를 올리지
  않는다(치는 칸이 회차마다 새로 서면 초점이 풀린다).
- **칸에 치고 Enter 없이 버튼을 누르면 버튼이 이긴다.** 버튼을 누르는 순간 칸을 떠나 친 글이
  확정되고, 그 확정과 버튼 누름이 한 회차로 합쳐지면 두 콜백이 함께 돈다 — 차례는 프레임워크가
  정한다(1.63 은 버튼이 먼저라 숫자 칸 콜백이 버튼 값을 덮었다, 2026-10-26 E2E). 숫자 칸 콜백은 자기
  key 가 지금 세대의 key 와 다르면(같은 회차에 버튼 콜백이 먼저 세대를 올렸으면) 적지 않고, 버튼
  콜백이 나중이면 그것이 덮으므로 어느 차례든 마지막에 누른 버튼이 정본이 된다. 누른 버튼이 이미
  켜져 있던 것이어도 같다(위 「다시 누름」) — 칸 확정이 먼저 회차를 돌려 버튼이 꺼져도 마지막으로 켠
  버튼은 남아 있다.
- `persist_state` 는 주지 않는다 — 정본이 위젯 아닌 칸이라 페이지를 오가도 남고, 위젯 칸은 매 회차
  정본에서 다시 선다.

`None` 버튼(「HOME 기준」 같은 「값 없음」 버튼)은 버튼 칸에 글자 표지(`NONE_OPTION`)로 든다 — 버튼
칸의 `None` 은 「모두 꺼짐」 이라 겹치지 않게. 그때 숫자 칸은 `fallback` 을 보이고, 그 값을 그대로
다시 적으면 값이 안 바뀌어 콜백이 없으므로 정본은 `None` 그대로다(Guide 한 줄). 그 함정이
자연스럽게 생기는 칸(동시 개조 상한 — 「없음」 일 때 보일 값이 마땅치 않고, 다른 입력을 따라
움직이면 「지금 그 값」 을 치는 일이 잦다)은 `none_placeholder` 를 준다 — 정본이 `None` 이면 숫자
칸이 **비고** 자리표시 글을 보여, 어떤 수를 쳐도 값이 바뀌어 콜백이 돈다.

`step` 이 정수면 정본·숫자 칸 모두 `int` 로 접는다(위젯은 min·max·step 의 수 형이 같아야 한다).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from decimal import ROUND_HALF_UP, Decimal
from typing import Final, Literal

import streamlit as st

from capa_simulation.components.widget_generation import bump, widget_key
from capa_simulation.design import tokens

__all__ = ["CUSTOM_OPTION", "NONE_OPTION", "render_preset_number_field"]

NONE_OPTION: Final = "__none__"
"""버튼 칸에서 `None` 버튼을 가리키는 글자 표지."""

CUSTOM_OPTION: Final = "__custom__"
"""버튼 칸에서 맞춤 값(버튼에 없는 값)을 가리키는 숨은 버튼 표지 — 버튼 줄 끝, CSS 로 숨긴다."""

_MISSING: Final = object()

PresetTone = Literal["accent", "warning"]


def _number(value: float, integer: bool, decimals: int | None = None) -> float | int:
    """정수 칸이면 `int`, 소수 자리(`decimals`)를 주면 그 자리까지 반 올림으로 접은 `float`."""
    if integer:
        return int(round(value))
    if decimals is None:
        return float(value)
    # 브라우저 칸은 `toFixed` 로 보인다 — 2진 값 그대로의 반 올림이라 `Decimal(float)` 로 견준다.
    step = Decimal(1).scaleb(-decimals)
    return float(Decimal(float(value)).quantize(step, rounding=ROUND_HALF_UP))


_FIXED_DECIMALS: Final = re.compile(r"\.(\d+)[fF]$")


def _shown_decimals(number_format: str) -> int | None:
    """숫자 칸이 보이는 소수 자리(`%.1f` → 1). 자리를 정하지 않은 꼴이면 `None` 이다."""
    match = _FIXED_DECIMALS.search(number_format)
    return int(match.group(1)) if match else None


def _valid(
    value: object, *, minimum: float, maximum: float, presets: Sequence[float | None]
) -> bool:
    if value is None:
        return None in presets
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return minimum <= float(value) <= maximum


def _option_of(value: float | None, presets: Sequence[float | None]) -> float | str:
    """정본 값이 버튼 값이면 그 버튼(`None` 은 표지), 아니면 숨은 맞춤 버튼(보이는 버튼은 꺼짐)."""
    if value is None:
        return NONE_OPTION if None in presets else CUSTOM_OPTION
    for preset in presets:
        if preset is not None and float(preset) == float(value):
            return preset
    return CUSTOM_OPTION


def _generation_key(input_key: str) -> str:
    return f"{input_key}__generation"


def _lit_key(pills_key: str) -> str:
    """서버가 마지막으로 켠 버튼 칸 — 켜진 버튼을 다시 누르면(`None` 이 온다) 이 버튼이다."""
    return f"{pills_key}__lit"


def _input_widget_key(input_key: str) -> str:
    """숫자 칸이 지금 서는 위젯 key — 버튼을 누를 때마다 세대가 올라 새 key 가 된다(`x__1` 꼴)."""
    return widget_key(input_key, _generation_key(input_key), style="__")


def _write_if_changed(key: str, value: object) -> bool:
    """칸이 없거나 그 값과 다를 때만 적고 적었는지 돌려준다 — 같은 값을 다시 적으면 `set_value` 가
    회차마다 간다."""
    if st.session_state.get(key, _MISSING) != value:
        st.session_state[key] = value
        return True
    return False


def _pick_preset(value_key: str, pills_key: str, input_key: str, integer: bool) -> None:
    """버튼 콜백 — 누른 버튼 값으로 정본을 적는다(`None` 버튼은 `None`).

    버튼 칸이 `None` 이면 켜진 버튼을 다시 누른 것이다(프런트가 풀었다) — 서버가 마지막으로 켠
    버튼을 누른 값으로 본다. 정본을 적으면 숫자 칸 세대도 올린다 — 칸이 쥐고 있던 글(범위 밖 글,
    같은 회차에 확정된 친 값)을 버리고 버튼 값으로 선다.
    """
    picked = st.session_state.get(pills_key)
    if picked is None:
        picked = st.session_state.get(_lit_key(pills_key))
    if picked is None or picked == CUSTOM_OPTION:
        return
    if picked == NONE_OPTION:
        st.session_state[value_key] = None
    elif isinstance(picked, (int, float)) and not isinstance(picked, bool):
        st.session_state[value_key] = _number(float(picked), integer)
    else:
        return
    bump(_generation_key(input_key))


def _pick_number(
    value_key: str,
    input_key: str,
    widget_key: str,
    integer: bool,
    decimals: int | None = None,
) -> None:
    """숫자 칸 콜백 — 정본을 그 값으로(범위는 위젯이 막는다). 칸이 보이는 소수 자리(`decimals`)까지
    접는다 — 칸과 머리·판정 글이 같은 수를 보이게(모듈 머리말).

    `widget_key` 는 이 칸이 그려질 때의 세대 key 다. 같은 회차에 버튼 콜백이 먼저 돌아 세대를
    올렸으면 이 칸은 옛 세대라 적지 않는다 — 친 글을 확정하며 누른 버튼이 이긴다(모듈 머리말).
    """
    if _input_widget_key(input_key) != widget_key:
        return
    typed = st.session_state.get(widget_key)
    if isinstance(typed, (int, float)) and not isinstance(typed, bool):
        st.session_state[value_key] = _number(float(typed), integer, decimals)


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


# 버튼 줄의 단추 — 1.63 pills 는 `role="radiogroup"` 아래 단추가 고를 값 차례대로 바로 선다.
PILL_BUTTONS_SELECTOR: Final = '[role="radiogroup"] > button'


def _custom_style(pills_key: str) -> str:
    """버튼 줄 끝의 맞춤 버튼(`CUSTOM_OPTION`)을 숨긴다 — 켜져도 보이지 않고 누를 수 없다."""
    return (
        f"<style>.st-key-{pills_key} {PILL_BUTTONS_SELECTOR}:last-child "
        "{ display: none !important; }</style>"
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
    none_placeholder: str | None = None,
) -> float | None:
    """버튼 줄과 숫자 칸을 지금 컨테이너에 그리고 정본 값을 돌려준다.

    정본 칸이 없거나 쓸 수 없는 값이면 `default` 를 심는다. `fallback` 은 정본이 `None` 일 때 숫자
    칸이 보일 값이다(HOME 기준이면 기본 확보 기준 %). `none_placeholder` 를 주면 정본이 `None` 일 때
    숫자 칸을 비우고 그 글을 자리표시로 보인다(`fallback` 은 쓰지 않는다).
    """
    integer = float(step).is_integer() and float(minimum).is_integer()
    held = st.session_state.get(value_key, _MISSING)
    if held is _MISSING or not _valid(held, minimum=minimum, maximum=maximum, presets=presets):
        st.session_state[value_key] = None if default is None else _number(float(default), integer)
    value = st.session_state.get(value_key)
    canonical: float | None = None if value is None else float(value)

    widget_key = _input_widget_key(input_key)
    lit = _option_of(canonical, presets)
    _write_if_changed(pills_key, lit)
    if lit != CUSTOM_OPTION:
        _write_if_changed(_lit_key(pills_key), lit)
    field_value: float | int | None
    if canonical is None and none_placeholder is not None:
        field_value = None
    else:
        shown = canonical if canonical is not None else float(fallback)
        shown = min(max(shown, float(minimum)), float(maximum))
        field_value = _number(shown, integer)
    # 적지 않은 회차에만 지금 값을 기본값으로 싣는다 — 끊긴 회차가 `set_value` 를 보내지 못한 새 key
    # 칸도 최소값이 아니라 이 값으로 선다(모듈 머리말). 적은 회차에 함께 주면 Streamlit 이 경고한다.
    # 자리표시 칸(`none_placeholder`)의 빈 값은 싣지 않는다 — 세션 칸이 `None` 이면 Streamlit 이
    # 기본값을 `None` 으로 바꿔 빈 칸으로 세운다.
    written = _write_if_changed(widget_key, field_value)
    field_default: float | int | Literal["min"] = (
        "min" if written or field_value is None else field_value
    )

    options: list[float | str] = [
        *(NONE_OPTION if preset is None else preset for preset in presets),
        CUSTOM_OPTION,
    ]

    def format_option(option: float | str) -> str:
        if option == CUSTOM_OPTION:
            return "맞춤"
        return preset_label(None if option == NONE_OPTION else float(option))

    st.html(_custom_style(pills_key) + _tone_style(pills_key, tone))
    st.pills(
        label,
        options,
        selection_mode="single",
        # 켜진 버튼 누름도 콜백에 닿게 풀 수 있게 둔다 — 풀린 `None` 은 콜백이 그 버튼으로 되돌린다.
        required=False,
        format_func=format_option,
        key=pills_key,
        on_change=_pick_preset,
        args=(value_key, pills_key, input_key, integer),
        disabled=disabled,
        help=help,
    )
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.number_input(
            f"{label} 직접 입력",
            min_value=_number(minimum, integer),
            max_value=_number(maximum, integer),
            value=field_default,
            step=_number(step, integer),
            format=number_format,
            key=widget_key,
            on_change=_pick_number,
            args=(value_key, input_key, widget_key, integer, _shown_decimals(number_format)),
            disabled=disabled,
            label_visibility="collapsed",
            placeholder=none_placeholder,
            width=132,
        )
        st.caption(f"{unit} 직접 입력", width="content")
    return canonical
