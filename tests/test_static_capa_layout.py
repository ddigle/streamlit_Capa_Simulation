# Purpose: Static Capa 화면의 판정 기준 조건 카드와 Guide 가 사용자 결정대로 서는지 고정한다.

"""Static Capa — 판정 기준은 사이드바 조건 카드, 설명은 Guide(2026-09-29 사용자 결정)."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from test_load_conversion_plan_apply import _isolated_custom_renderers  # noqa: F401

from capa_simulation.components.page_guide import GUIDE_TRIGGER_KEY, load_guide
from capa_simulation.scenario_preset_state import SECURE_THRESHOLD_KEY, WARNING_THRESHOLD_KEY
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


def test_the_thresholds_live_in_a_collapsed_sidebar_card(app_script: str) -> None:
    app = AppTest.from_string(app_script, default_timeout=300).run()
    assert not list(app.exception), [element.message for element in app.exception]

    sidebar_keys = {widget.key for widget in app.sidebar.number_input}
    assert {SECURE_THRESHOLD_KEY, WARNING_THRESHOLD_KEY} <= sidebar_keys
    assert not {widget.key for widget in app.main.number_input} & sidebar_keys
    assert app.session_state[CARD_KEY] is False
    # 본문에는 결과 두 상자만 남는다 — 목적·계산식은 Guide 로 갔다.
    assert "추가 필요대수 계산 기준" not in {expander.label for expander in app.main.expander}
    assert app.button(key=GUIDE_TRIGGER_KEY)


def test_the_guide_carries_what_left_the_body() -> None:
    guide = load_guide("static_capa")
    for text in (
        "판정 기준 적용",
        "확보 기준",
        "경고 기준",
        "ceil(max(소요대수 × 경고 기준 − 가용대수, 0))",
        "경고까지 필요 + 확보까지 추가 = 총 추가 필요",
        "GO팀",
        "기술팀",
    ):
        assert text in guide, text
