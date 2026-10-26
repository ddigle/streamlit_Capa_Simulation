# Purpose: 버튼 + 직접 입력 칸의 켜진 버튼 주의 색 CSS 와 한 회차에 겹친 두 콜백의 차례를 본다.

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
from capa_simulation.components.preset_number_field import (
    ACTIVE_PILL_SELECTOR,
    _pick_number,
    _pick_preset,
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
    monkeypatch.setattr(preset_number_field, "st", SimpleNamespace(session_state=state))

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
    monkeypatch.setattr(preset_number_field, "st", SimpleNamespace(session_state=state))
    _pick_number(_VALUE, _INPUT, f"{_INPUT}__2", True)
    assert state[_VALUE] == 175
    assert state[f"{_INPUT}__generation"] == 2
