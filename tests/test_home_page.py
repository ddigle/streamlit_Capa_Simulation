# Purpose: HOME 대시보드가 내장 시드 시나리오에서 렌더링되는 현재 동작을 고정한다.

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

HOME_PAGE = Path("app_pages/home.py").resolve()

# 이 파일은 특성화(characterization) 테스트다. 아래 값들은 "이래야 한다"는 규범이 아니라
# 리팩토링 전 HOME의 관측된 현재 동작이다. 의도적으로 화면을 바꿀 때는 이 기대값도 함께
# 바꾸고, 의도하지 않았다면 리팩토링이 무언가를 깨뜨린 것이다.


def _home_script(database_path: Path) -> str:
    """app.py의 전역 준비 단계만 재현한 뒤 HOME 페이지를 실행한다.

    AppTest에는 plotly_chart 접근자가 없어 st.plotly_chart를 감싸 호출별 trace 수를
    session_state에 기록한다. Components v2 위젯은 모듈 import 시점에 한 번 등록되므로
    AppTest 인스턴스를 새로 만들면 레지스트리에 남아 있지 않다. 가로 스크롤바는
    특성화 대상이 아니므로 호출 횟수만 세는 스텁으로 대체한다.
    """
    return f"""
from pathlib import Path

import streamlit as st

import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
import capa_simulation.settings as settings

settings.DUCKDB_PATH = Path({str(database_path)!r})

from capa_simulation.scenario_activation import bootstrap_latest_official_scenario
from capa_simulation.scenario_preset_state import apply_pending_scenario_preset

bootstrap_latest_official_scenario(str(settings.DUCKDB_PATH))
apply_pending_scenario_preset()

st.session_state["spy_traces"] = []
st.session_state["spy_scrollbars"] = 0
_original_plotly_chart = st.plotly_chart
_original_scrollbar = horizontal_scrollbar.render_horizontal_scrollbar


def _spy_plotly_chart(figure, *args, **kwargs):
    st.session_state["spy_traces"] = st.session_state["spy_traces"] + [
        len(getattr(figure, "data", []) or [])
    ]
    return _original_plotly_chart(figure, *args, **kwargs)


def _spy_scrollbar(*_args, **_kwargs):
    st.session_state["spy_scrollbars"] = st.session_state["spy_scrollbars"] + 1
    return None


st.plotly_chart = _spy_plotly_chart
horizontal_scrollbar.render_horizontal_scrollbar = _spy_scrollbar
try:
    page_source = Path({str(HOME_PAGE)!r}).read_text(encoding="utf-8")
    exec(compile(page_source, {str(HOME_PAGE)!r}, "exec"), {{"__name__": "__main__"}})
finally:
    st.plotly_chart = _original_plotly_chart
    horizontal_scrollbar.render_horizontal_scrollbar = _original_scrollbar
"""


@pytest.fixture(scope="module")
def seeded_database(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """내장 시드 부트스트랩은 멱등이므로 모듈 안에서 DuckDB 하나를 재사용한다."""
    return tmp_path_factory.mktemp("home") / "scenario.duckdb"


def _run(seeded_database: Path) -> AppTest:
    app = AppTest.from_string(_home_script(seeded_database), default_timeout=300).run()
    assert not list(app.exception)
    return app


def test_home_renders_summary_dashboard_from_the_builtin_seed(seeded_database: Path) -> None:
    app = _run(seeded_database)

    assert [element.value for element in app.title] == ["S.PKG Capa Simulation"]
    # 내장 시드 프리셋이 복원한 조회기간과 판정 기준
    assert app.session_state["production_month_range_v2"] == ("2026-01", "2026-12")
    assert [(widget.label, widget.value) for widget in app.sidebar.number_input] == [
        ("확보 기준 (%)", 109.5),
        ("경고 기준 (%)", 99.5),
    ]

    # 기본 진입은 요약 Figure만 만든다: 좌측 라벨(trace 0) + 월별 본문(trace 3)
    assert app.session_state["spy_traces"] == [0, 3]
    assert app.session_state["spy_scrollbars"] == 1

    assert [widget.label for widget in app.main.toggle] == ["계획·B/N 상세표 표시"]
    assert [widget.label for widget in app.sidebar.toggle] == ["HOME 성능 진단"]
    assert [widget.label for widget in app.button] == ["판정 기준 적용", "공정 선택창 열기"]


def test_home_detail_toggle_adds_plan_and_bottleneck_figures(seeded_database: Path) -> None:
    app = _run(seeded_database)
    assert app.session_state["spy_traces"] == [0, 3]

    app.main.toggle[0].set_value(True).run()

    assert not list(app.exception)
    # 상세 토글은 계획 세부수량과 B/N 상세 시트를 추가로 만든다.
    assert app.session_state["spy_traces"] == [0, 1, 1, 3, 1, 1]


def test_home_reuses_cached_figures_on_an_unchanged_rerun(seeded_database: Path) -> None:
    app = _run(seeded_database)

    app.sidebar.toggle[0].set_value(True).run()

    assert not list(app.exception)
    assert _cache_state(app) == "적중"
    assert "공정 선택 · 3 / 3개 포함" in [element.value for element in app.caption]


def _cache_state(app: AppTest) -> str:
    states = [
        element.value.removeprefix("Figure 캐시: ")
        for element in app.caption
        if element.value.startswith("Figure 캐시: ")
    ]
    assert len(states) == 1, f"Figure 캐시 캡션이 하나여야 한다: {states}"
    return states[0]


def test_home_rebuilds_figures_when_a_threshold_changes(seeded_database: Path) -> None:
    app = _run(seeded_database)
    app.sidebar.toggle[0].set_value(True).run()
    assert _cache_state(app) == "적중"

    # 판정 기준은 Figure 캐시 키에 포함되어야 한다(AGENTS.md 5장 불변조건 7).
    app.sidebar.number_input[1].set_value(95.0)
    app.button[0].click().run()

    assert not list(app.exception)
    assert [widget.value for widget in app.sidebar.number_input] == [109.5, 95.0]
    assert _cache_state(app) == "생성"

    # 조건이 그대로면 다시 캐시를 재사용한다.
    app.run()

    assert _cache_state(app) == "적중"
