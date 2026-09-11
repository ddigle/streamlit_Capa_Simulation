# Purpose: HOME 대시보드가 내장 시드 시나리오에서 렌더링되는 현재 동작을 고정한다.

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

# cwd 가 아니라 이 파일 위치를 기준으로 잡는다. tests/ 안에서 pytest 를 돌려도 같은 페이지를 연다.
HOME_PAGE = Path(__file__).resolve().parents[1] / "app_pages" / "home.py"

# 이 파일은 특성화(characterization) 테스트다. 아래 값들은 "이래야 한다"는 규범이 아니라
# 리팩토링 전 HOME의 관측된 현재 동작이다. 의도적으로 화면을 바꿀 때는 이 기대값도 함께
# 바꾸고, 의도하지 않았다면 리팩토링이 무언가를 깨뜨린 것이다.


def _home_script(database_path: Path) -> str:
    """app.py의 전역 준비 단계만 재현한 뒤 HOME 페이지를 실행한다.

    AppTest에는 plotly_chart 접근자가 없어 st.plotly_chart를 감싸 호출별 trace 수와
    config를 session_state에 기록한다. Components v2 위젯은 모듈 import 시점에 한 번 등록되므로
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
st.session_state["spy_configs"] = {{}}
st.session_state["spy_scrollbars"] = 0
_original_plotly_chart = st.plotly_chart
_original_scrollbar = horizontal_scrollbar.render_horizontal_scrollbar


def _spy_plotly_chart(figure, *args, **kwargs):
    st.session_state["spy_traces"] = st.session_state["spy_traces"] + [
        len(getattr(figure, "data", []) or [])
    ]
    st.session_state["spy_configs"] = {{
        **st.session_state["spy_configs"],
        kwargs.get("key"): dict(kwargs.get("config") or {{}}),
    }}
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

    assert [element.value for element in app.title] == ["Capa LOB Summary"]
    # 내장 시드 프리셋이 복원한 조회기간과 판정 기준
    assert app.session_state["production_month_range_v2"] == ("2026-01", "2026-12")
    assert [(widget.label, widget.value) for widget in app.sidebar.number_input] == [
        ("확보 기준 (%)", 109.5),
        ("경고 기준 (%)", 99.5),
    ]

    # 기본 진입은 상세표까지 펼친다: 요약(좌측 라벨 trace 0 + 월별 본문 trace 3)에
    # 계획 세부수량과 B/N 상세 시트가 더해진다. B/N 상세 월 Figure 의 4는 hover 표적
    # 막대·트랙 막대·확보율 막대·공정명 텍스트다. 값이 커지면 trace 를 늘린 것이다.
    assert app.session_state["spy_traces"] == [0, 1, 1, 3, 1, 4]
    assert app.session_state["spy_scrollbars"] == 1

    # 본문에는 토글이 없다. 상세표 표시 여부를 고르던 자리는 탭 인터페이스가 가져갔다.
    assert [widget.label for widget in app.main.toggle] == []
    assert [widget.label for widget in app.sidebar.toggle] == ["HOME 성능 진단"]
    assert [widget.label for widget in app.button] == ["판정 기준 적용", "공정 선택창 열기"]
    # 제목 아래 설명 문구와 계획 세부수량 CSV 는 탭 자리를 내주고 사라졌다.
    assert not app.get("download_button")


def test_home_puts_the_charts_in_a_main_tab_next_to_preference(seeded_database: Path) -> None:
    """차트별 설정을 담을 자리를 만들기 위한 탭이다. Main 은 기존 화면 그대로다."""
    app = _run(seeded_database)

    tabs = [tab.label for tab in app.main.tabs]
    assert tabs == [":material/dashboard: Main", ":material/tune: Preference"]
    # 차트는 Main 탭 안에서만 그린다.
    assert app.session_state["spy_traces"] == [0, 1, 1, 3, 1, 4]


def test_the_bottleneck_detail_chart_keeps_hover_on(seeded_database: Path) -> None:
    """상세 B/N 월 Figure 의 hover 는 `staticPlot` 을 빼 둔 것이 유일한 근거다.

    같은 캔버스의 상세 두 Figure 중 계획 세부수량 쪽은 `staticPlot: True` 라, 일관성을
    이유로 이 한 곳에 다시 넣으면 hover 가 조용히 죽는다. 그 한 줄을 여기서 고정한다.
    """
    app = _run(seeded_database)
    configs = app.session_state["spy_configs"]

    bottleneck_config = configs["bottleneck_detail_months"]
    assert "staticPlot" not in bottleneck_config
    assert bottleneck_config["displayModeBar"] is False
    # `staticPlot` 을 빼면 기본값으로 돌아오는 둘도 함께 꺼져 있어야 한다.
    assert bottleneck_config["doubleClick"] is False
    assert bottleneck_config["showAxisDragHandles"] is False

    assert configs["production_detail_months"]["staticPlot"] is True
    assert configs["bottleneck_detail_labels"]["staticPlot"] is True


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


def test_home_reports_a_missing_active_revision_instead_of_a_traceback(tmp_path: Path) -> None:
    """공식버전이 없는 저장소로 열면 활성 리비전이 없어 RuntimeError 가 난다.

    14개 페이지 중 HOME 만 이것을 잡지 않아 원문 트레이스백을 그대로 보여 줬다. 안내 한 줄과
    멈춤이어야 한다.
    """
    from capa_simulation.persistence.models import ScenarioCreate, ScenarioPreset
    from capa_simulation.persistence.repository import DuckDBScenarioRepository
    from capa_simulation.services.builtin_seed import (
        BUILTIN_SEED_MONTHS,
        build_builtin_seed_dataset,
        builtin_seed_processes,
    )

    database = tmp_path / "unpublished.duckdb"
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    prepared = build_builtin_seed_dataset()
    repository.create_scenario(
        ScenarioCreate(
            scenario_name="공식버전 없는 시나리오",
            source_simulation_code="USER-SCENARIO-001",
            source_simulation_name="사용자 원천",
            source_type="TEST",
            pipeline_version="test-v1",
        ),
        prepared.reference_tables,
        ScenarioPreset(
            min(BUILTIN_SEED_MONTHS), max(BUILTIN_SEED_MONTHS), builtin_seed_processes()
        ),
        source_data=prepared.source_data,
    )

    app = AppTest.from_string(_home_script(database), default_timeout=300).run()

    assert not list(app.exception)
    assert len(app.error) == 1


def test_home_names_the_data_range_when_the_selection_is_outside_it(seeded_database: Path) -> None:
    """ "데이터가 없습니다" 만으로는 어디로 옮겨야 하는지 알 수 없다. 있는 범위를 같이 말한다."""
    app = _run(seeded_database)

    app.session_state["production_month_range_v2"] = ("2029-01", "2029-03")
    app.run()

    assert not list(app.exception)
    assert len(app.error) == 1
    assert "데이터 범위" in app.error[0].value
