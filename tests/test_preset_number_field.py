# Purpose: 버튼 + 직접 입력 칸의 켜진 버튼 주의 색 CSS 가 1.63 pills 에 걸리고 읽히는지 본다.

"""`components/preset_number_field.py` 의 켜진 버튼 색(`_tone_style`).

값 주고받기(버튼 ↔ 숫자 칸 ↔ 정본)는 제약 시뮬레이션 화면
시험(`tests/test_constraint_simulation_page.py`)이 AppTest 로 본다. 여기서는 브라우저에서만 드러나는
CSS 를 본다 — 선택자가 1.63 의 DOM 과 어긋나 주황이 한 번도 서지 않았던 일(2026-10-25 리뷰, 사본
앱에서 `pillsActive` 일치 0개)을 막는다.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from test_design_tokens import contrast_ratio

from capa_simulation.components.preset_number_field import ACTIVE_PILL_SELECTOR, _tone_style
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
