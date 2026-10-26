# Purpose: 버튼 + 직접 입력 칸의 켜진 버튼 주의 색 CSS · 한 회차에 겹친 두 콜백의 차례 · 친 값
# 접기를 본다.

"""`components/preset_number_field.py` 의 켜진 버튼 색(`_tone_style`).

값 주고받기(버튼 ↔ 숫자 칸 ↔ 정본)는 제약 시뮬레이션 화면
시험(`tests/test_constraint_simulation_page.py`)이 AppTest 로 본다. 여기서는 브라우저에서만 드러나는
CSS 를 본다 — 선택자가 1.63 의 DOM 과 어긋나 주황이 한 번도 서지 않았던 일(2026-10-25 리뷰, 사본
앱에서 `pillsActive` 일치 0개)을 막는다.

콜백 차례(`_pick_preset`·`_pick_number`)도 여기서 본다 — 칸 확정과 버튼 누름이 한 회차에 겹칠 때
프레임워크가 어느 차례로 부르든 버튼이 이겨야 한다. AppTest 는 그린 차례 하나만 재현하므로 반대
차례는 세션 칸을 사전으로 바꿔 콜백을 직접 부른다.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from test_design_tokens import contrast_ratio

import capa_simulation.components.preset_number_field as preset_number_field
import capa_simulation.components.widget_generation as widget_generation
import capa_simulation.components.write_guard as write_guard
from capa_simulation.components.preset_number_field import (
    ACTIVE_PILL_SELECTOR,
    CUSTOM_OPTION,
    PILL_BUTTONS_SELECTOR,
    _custom_style,
    _number,
    _option_of,
    _pick_number,
    _pick_preset,
    _shown_decimals,
    _tone_style,
)
from capa_simulation.design import theme, tokens


@pytest.fixture(autouse=True)
def _light_theme() -> Iterator[None]:
    """어둡게를 켠 시험이 남긴 테마를 되돌린다(테스트는 Streamlit 밖이라 밝게다)."""
    theme._LOCAL.mode = "light"
    yield
    theme._LOCAL.mode = "light"


def test_the_warning_tone_targets_the_checked_radio_pill_of_streamlit_163() -> None:
    """1.63 pills(한 개 고름)는 react-aria 토글 단추 — 켜진 단추는 `role="radio"`·
    `aria-checked="true"` 이고 `data-testid="stBaseButton-pillsActive"` 는 그리지 않는다."""
    style = _tone_style("constraint_sim_target_pills", "warning")
    assert ACTIVE_PILL_SELECTOR == 'button[role="radio"][aria-checked="true"]'
    assert f".st-key-constraint_sim_target_pills {ACTIVE_PILL_SELECTOR} {{" in style
    assert "pillsActive" not in style
    assert _tone_style("constraint_sim_general_pills", "accent") == ""


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_the_warning_pill_puts_readable_text_on_the_warning_face(mode: str) -> None:
    """주의 색은 글자를 얹는 면색이다 — 글자는 `TEXT` 이고 두 테마 모두 4.5:1 이상이다(면 위
    `SURFACE` 는 어두운 테마에서 3.0:1 이었다)."""
    theme._LOCAL.mode = mode
    palette = tokens._PALETTES[mode]
    style = _tone_style("constraint_sim_target_pills", "warning")
    assert f"background: {palette['STATUS_WARNING']} !important" in style
    assert f"color: {palette['TEXT']} !important" in style
    assert contrast_ratio(palette["TEXT"], palette["STATUS_WARNING"]) >= 4.5


def _fake_session(monkeypatch: pytest.MonkeyPatch, state: dict[str, object]) -> None:
    # 숫자 칸 key 세대는 `widget_generation`(세대 읽기는 `write_guard`)이 짓는다.
    fake = SimpleNamespace(session_state=state)
    for module in (preset_number_field, widget_generation, write_guard):
        monkeypatch.setattr(module, "st", fake)


_VALUE = "value"
_PILLS = "value_pills"
_INPUT = "value_input"


@pytest.mark.parametrize("generation", [0, 3])
@pytest.mark.parametrize("preset_first", [True, False])
def test_a_button_and_a_typed_value_in_one_rerun_leave_the_button_value_either_order(
    monkeypatch: pytest.MonkeyPatch, generation: int, preset_first: bool
) -> None:
    """칸에 175 를 치고 Enter 없이 140% 를 누르면 두 콜백이 한 회차에 돈다 — 어느 차례든 정본은
    140 이고 칸 세대가 하나 오른다(2026-10-26 E2E — 버튼이 먼저 돌면 숫자 칸 콜백이 덮었다)."""
    widget_key = _INPUT if generation == 0 else f"{_INPUT}__{generation}"
    state: dict[str, object] = {_VALUE: 120, _PILLS: 140, widget_key: 175}
    if generation:
        state[f"{_INPUT}__generation"] = generation
    _fake_session(monkeypatch, state)

    def press() -> None:
        _pick_preset(_VALUE, _PILLS, _INPUT, True)

    def commit() -> None:
        _pick_number(_VALUE, _INPUT, widget_key, True)

    for callback in (press, commit) if preset_first else (commit, press):
        callback()
    assert state[_VALUE] == 140
    assert state[f"{_INPUT}__generation"] == generation + 1


def test_a_typed_value_alone_still_becomes_the_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """버튼을 누르지 않은 회차의 숫자 칸 콜백은 그대로 정본을 적는다(세대는 그대로)."""
    state: dict[str, object] = {_VALUE: 120, _PILLS: 120, f"{_INPUT}__2": 175.4}
    state[f"{_INPUT}__generation"] = 2
    _fake_session(monkeypatch, state)
    _pick_number(_VALUE, _INPUT, f"{_INPUT}__2", True)
    assert state[_VALUE] == 175
    assert state[f"{_INPUT}__generation"] == 2


_LIT = f"{_PILLS}__lit"


@pytest.mark.parametrize("preset_first", [True, False])
def test_the_lit_button_pressed_after_typing_wins_either_order(
    monkeypatch: pytest.MonkeyPatch, preset_first: bool
) -> None:
    """켜진 120% 를 다시 누르면 프런트가 풀어 버튼 칸이 `None` 이다 — 같은 회차에 친 166 이 확정돼도
    어느 차례든 정본은 마지막으로 켠 120 이고 칸 세대가 오른다(2026-10-26 E2E)."""
    state: dict[str, object] = {_VALUE: 120, _PILLS: None, _LIT: 120, _INPUT: 166}
    _fake_session(monkeypatch, state)

    def press() -> None:
        _pick_preset(_VALUE, _PILLS, _INPUT, True)

    def commit() -> None:
        _pick_number(_VALUE, _INPUT, _INPUT, True)

    for callback in (press, commit) if preset_first else (commit, press):
        callback()
    assert state[_VALUE] == 120
    assert state[f"{_INPUT}__generation"] == 1


def test_the_lit_button_survives_a_typed_value_committed_in_an_earlier_rerun(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """칸 확정이 먼저 회차를 돌려 정본이 166 · 버튼이 모두 꺼진 뒤에 「다시 누름」(`None`)이 와도
    마지막으로 켠 버튼(「HOME 기준」 표지 포함)으로 선다 — 맞춤 값이 되어도 그 칸은 남는다."""
    state: dict[str, object] = {_VALUE: 166, _PILLS: None, _LIT: preset_number_field.NONE_OPTION}
    _fake_session(monkeypatch, state)
    _pick_preset(_VALUE, _PILLS, _INPUT, True)
    assert state[_VALUE] is None
    assert state[f"{_INPUT}__generation"] == 1


def test_nothing_lit_and_no_button_leaves_the_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """켠 적 없는 버튼 칸이 `None` 이면 정본도 세대도 그대로다."""
    state: dict[str, object] = {_VALUE: 166, _PILLS: None}
    _fake_session(monkeypatch, state)
    _pick_preset(_VALUE, _PILLS, _INPUT, True)
    assert state[_VALUE] == 166
    assert f"{_INPUT}__generation" not in state


def test_a_custom_value_lights_the_hidden_last_button() -> None:
    """맞춤 값은 버튼 칸이 `None` 이 아니라 숨은 맞춤 버튼이다 — `None` 은 켜진 버튼을 풀었을 때만
    온다. 그 버튼은 버튼 줄 끝이고 CSS 가 숨긴다(1.63 pills 는 `radiogroup` 아래 단추가 차례로)."""
    presets = (100.0, None, 120.0)
    assert _option_of(120.0, presets) == 120.0
    assert _option_of(None, presets) == preset_number_field.NONE_OPTION
    assert _option_of(125.0, presets) == CUSTOM_OPTION
    assert _option_of(None, (100.0, 120.0)) == CUSTOM_OPTION
    assert PILL_BUTTONS_SELECTOR == '[role="radiogroup"] > button'
    style = _custom_style("constraint_sim_target_pills")
    assert (
        f".st-key-constraint_sim_target_pills {PILL_BUTTONS_SELECTOR}:last-child "
        "{ display: none !important; }"
    ) in style


def test_the_hidden_custom_button_is_never_taken_as_a_press(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """숨은 맞춤 버튼 값이 와도(누를 수 없지만) 정본·세대를 건드리지 않는다."""
    state: dict[str, object] = {_VALUE: 166, _PILLS: CUSTOM_OPTION, _LIT: 120}
    _fake_session(monkeypatch, state)
    _pick_preset(_VALUE, _PILLS, _INPUT, True)
    assert state[_VALUE] == 166
    assert f"{_INPUT}__generation" not in state


@pytest.mark.parametrize(
    ("number_format", "decimals"), [("%.1f", 1), ("%0.2f", 2), ("%d", None), ("%f", None)]
)
def test_the_shown_decimals_come_from_the_field_format(
    number_format: str, decimals: int | None
) -> None:
    assert _shown_decimals(number_format) == decimals


@pytest.mark.parametrize(
    ("value", "folded"),
    [(112.34, 112.3), (112.25, 112.3), (112.35, 112.3), (107.3, 107.3), (199.96, 200.0)],
)
def test_a_value_folds_half_up_on_its_binary_value_like_the_browser_field(
    value: float, folded: float
) -> None:
    """브라우저 칸은 `toFixed` 로 보인다 — 2진 값 그대로 반 올림이다(112.25 는 정확히 112.25 라
    112.3, 112.35 는 2진으로 112.3499… 라 112.3). 파이썬 `round` 는 112.25 를 112.2 로 내린다."""
    assert _number(value, False, 1) == folded
    assert _number(value, False) == value
    assert _number(175.4, True, 1) == 175


def test_a_typed_value_folds_to_the_digits_the_field_shows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """숫자 칸 콜백은 칸이 보이는 자리까지 접어 적는다 — 칸(112.3)과 머리·판정 글(112.34%)이 갈리지
    않게(2026-10-27 E2E). 자리를 주지 않으면 그대로다."""
    state: dict[str, object] = {_VALUE: None, _PILLS: CUSTOM_OPTION, _INPUT: 112.34}
    _fake_session(monkeypatch, state)
    _pick_number(_VALUE, _INPUT, _INPUT, False, 1)
    assert state[_VALUE] == 112.3
    _pick_number(_VALUE, _INPUT, _INPUT, False)
    assert state[_VALUE] == 112.34
