# Purpose: Static Capa 화면의 판정 기준 안내 카드와 Guide 가 사용자 결정대로 서는지 고정한다.

"""Static Capa — 판정 기준은 HOME → Preference(2026-10-06), 설명은 Guide(2026-09-29 사용자 결정)."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from test_load_conversion_plan_apply import _isolated_custom_renderers  # noqa: F401

from capa_simulation.components.home_preference import THRESHOLD_POINTER
from capa_simulation.components.page_guide import GUIDE_TRIGGER_KEY, load_guide
from capa_simulation.sidebar_status import CONDITION_CARD_PREFIX

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "app_pages" / "static_capa.py"
CARD_KEY = f"{CONDITION_CARD_PREFIX}static_capa"


def _script(database_path: Path) -> str:
    return f"""
from pathlib import Path

import capa_simulation.settings as settings

settings.DUCKDB_PATH = Path({str(database_path)!r})

from capa_simulation.scenario_activation import bootstrap_latest_official_scenario
from capa_simulation.scenario_preset_state import apply_pending_scenario_preset

bootstrap_latest_official_scenario(str(settings.DUCKDB_PATH))
apply_pending_scenario_preset()

exec(
    compile(Path({str(PAGE)!r}).read_text(encoding="utf-8"), {str(PAGE)!r}, "exec"),
    {{"__name__": "__main__"}},
)
"""


@pytest.fixture(scope="module")
def app_script(tmp_path_factory: pytest.TempPathFactory) -> str:
    return _script(tmp_path_factory.mktemp("static_capa_layout") / "scenario.duckdb")


def test_the_threshold_card_only_points_to_the_home_preference(app_script: str) -> None:
    """판정 기준 입력은 없앴다(2026-10-06 사용자 결정). 카드는 지금 기준과 정하는 곳만 말한다."""
    app = AppTest.from_string(app_script, default_timeout=300).run()
    assert not list(app.exception), [element.message for element in app.exception]

    assert list(app.number_input) == []
    captions = [element.value for element in app.sidebar.caption]
    assert THRESHOLD_POINTER in captions
    # 저장 전에는 공식버전 프리셋 값(109.5%·99.5%)을 사사오입 정수로 적는다. 월별 예외가 없으면
    # 예외 수를 덧붙이지 않는다.
    assert "확보 기준 110% · 경고 기준 100%" in captions
    assert app.session_state[CARD_KEY] is False
    # 본문에는 결과 두 상자만 남는다 — 목적·계산식은 Guide 로 갔다.
    assert "추가 필요대수 계산 기준" not in {expander.label for expander in app.main.expander}
    assert app.button(key=GUIDE_TRIGGER_KEY)


def test_the_guide_carries_what_left_the_body() -> None:
    guide = load_guide("static_capa")
    for text in (
        "HOME → Preference",
        "확보 기준",
        "경고 기준",
        "ceil(max(소요대수 × 경고 기준 − 가용대수, 0))",
        "경고까지 필요 + 확보까지 추가 = 총 추가 필요",
        "GO팀",
        "기술팀",
    ):
        assert text in guide, text
