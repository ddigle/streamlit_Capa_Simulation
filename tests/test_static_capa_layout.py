# Purpose: Static Capa 의 판정 기준 카드·Guide·소요대수 미포함 수요 줄을 사용자 결정대로 고정한다.

"""Static Capa — 판정 기준은 HOME → Preference(2026-10-06), 설명은 Guide(2026-09-29 사용자 결정)."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from test_load_conversion_plan_apply import _isolated_custom_renderers  # noqa: F401
from test_reference_data_page import TEST_SCRIPT

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
        "자원운영팀",
        "기술팀",
        "실행 관리",
    ):
        assert text in guide, text


def _calculated_script(*, unrouted: bool) -> str:
    """계산을 실제로 돌리는 작은 시나리오의 Static Capa.

    `unrouted` 면 경로 없는 계획 한 줄을 더한다."""
    script = (
        TEST_SCRIPT.replace('PAGE_NAME = "reference_data.py"', 'PAGE_NAME = "static_capa.py"')
        .replace("STUB_CALCULATIONS = True", "STUB_CALCULATIONS = False")
        .replace(
            '"test-capacity-standards-page"',
            f'"test-static-capa-uncounted-{"unrouted" if unrouted else "clean"}"',
        )
    )
    if unrouted:
        script = script.replace("ADD_UNROUTED_PLAN = False", "ADD_UNROUTED_PLAN = True")
    assert 'PAGE_NAME = "static_capa.py"' in script
    return script


def test_the_summary_says_how_much_demand_the_required_count_left_out() -> None:
    """경로에 닿지 않은 계획 부하는 소요대수에 들지 않아 미달 건수·필요대수가 그만큼 작다 — 산출
    결과에만 있던 그 건수를 현황 요약 맨 위에도 조회기간으로 적는다(E2E r2 static — PKG PLAN 을
    고쳤는데 현황 요약 수가 그대로라 헷갈렸다). 들지 않은 수요가 없으면 줄이 없다."""
    app = AppTest.from_string(_calculated_script(unrouted=True), default_timeout=120).run()
    assert not list(app.exception), [element.message for element in app.exception]
    warnings = [str(element.value) for element in app.main.warning]
    assert any(
        "소요대수에 들지 않은 수요가 있습니다(조회기간)" in text
        and "RQ_REQB 경로에 닿지 않은 계획 부하 1건" in text
        and "산출 결과 → 소요대수 탭" in text
        for text in warnings
    ), warnings

    clean = AppTest.from_string(_calculated_script(unrouted=False), default_timeout=120).run()
    assert not list(clean.exception), [element.message for element in clean.exception]
    assert not any(
        "소요대수에 들지 않은 수요" in str(element.value) for element in clean.main.warning
    )


def test_the_summary_leaves_the_route_side_count_to_the_alert_board(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """현황 요약 맨 위 줄은 계획 쪽 건수만 싣는다 — 경로 쪽(대당 Capa 가 없어 뺀 부하 경로)은 계획을
    고치지 않아도 늘 있을 수 있어(사내 실데이터에서 0 이 아니었다) 열 때마다 서는 경고가 된다. 경로
    쪽만 있으면 줄이 없고, 함께 있으면 계획 쪽만 적는다(페이지는 exec 때 이름을 집으므로 모듈 속성을
    바꾸면 그 셈이 들어간다)."""
    import capa_simulation.services.required_equipment as required_equipment

    counts = [required_equipment.RequiredExclusionCounts(excluded_routes=7)]

    def counted(*_lists: object) -> required_equipment.RequiredExclusionCounts:
        return counts[0]

    monkeypatch.setattr(required_equipment, "count_required_exclusions", counted)
    routes_only = AppTest.from_string(_calculated_script(unrouted=False), default_timeout=120).run()
    assert not list(routes_only.exception), [item.message for item in routes_only.exception]
    assert not any(
        "소요대수에 들지 않은 수요" in str(element.value) for element in routes_only.main.warning
    )

    counts[0] = required_equipment.RequiredExclusionCounts(unrouted_loads=2, excluded_routes=7)
    both = AppTest.from_string(_calculated_script(unrouted=False), default_timeout=120).run()
    assert not list(both.exception), [item.message for item in both.exception]
    warnings = [str(element.value) for element in both.main.warning]
    assert any("RQ_REQB 경로에 닿지 않은 계획 부하 2건" in text for text in warnings), warnings
    assert not any("대당 Capa 가 없어 뺀 부하 경로" in text for text in warnings), warnings
