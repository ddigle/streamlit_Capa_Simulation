# Purpose: HOME 대시보드가 내장 시드 시나리오에서 렌더링되는 현재 동작을 고정한다.

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.components.home_dimensions import (
    DASHBOARD_TITLE_HEIGHT_PX,
    LOB_BOTTOM_MARGIN_PX,
    LOB_TOP_MARGIN_PX,
    LOB_VALUE_FONT_SIZE_PX,
)
from capa_simulation.design import tokens
from capa_simulation.scenario_preset_state import WARNING_THRESHOLD_KEY

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
st.session_state["spy_figures"] = {{}}
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
    st.session_state["spy_figures"] = {{
        **st.session_state["spy_figures"],
        kwargs.get("key"): figure,
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

    # 상세표 표시 여부를 고르던 자리는 탭이 가져갔고, 본문 토글은 표시 기준이다.
    # 「선행」·「GAP」 은 Capa LOB 현황 제목 옆, 「상세」 는 계획 세부수량 제목 옆,
    # 「EDP 포함」 은 Preference 탭에 있다.
    assert [widget.label for widget in app.main.toggle] == [
        "선행",
        "GAP",
        "상세",
        "EDP 포함",
    ]
    assert [widget.label for widget in app.sidebar.toggle] == ["HOME 성능 진단"]
    assert sorted(widget.label for widget in app.button) == [
        "공정 선택창 열기",
        "과거 구간 저장",
        "붙여넣기 읽기",
        "붙여넣기 읽기",
        "붙여넣기 읽기",
        "선행 물량 저장",
        "판정 기준 적용",
    ]
    # 제목 아래 설명 문구와 계획 세부수량 CSV 는 탭 자리를 내주고 사라졌다. 남은 내려받기는
    # Past Data 탭의 양식 세 개뿐이다.
    assert [button.label for button in app.get("download_button")] == ["양식 CSV"] * 3


def test_home_puts_the_charts_in_a_main_tab_next_to_preference(seeded_database: Path) -> None:
    """차트별 설정을 담을 자리를 만들기 위한 탭이다. Main 은 기존 화면 그대로다."""
    app = _run(seeded_database)

    tabs = [tab.label for tab in app.main.tabs]
    assert tabs == [
        ":material/dashboard: Main",
        ":material/tune: Preference",
        ":material/history: Past Data",
    ]
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

    app.sidebar.toggle(key="dashboard_show_performance").set_value(True).run()

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
    app.sidebar.toggle(key="dashboard_show_performance").set_value(True).run()
    assert _cache_state(app) == "적중"

    # 판정 기준은 Figure 캐시 키에 포함되어야 한다(AGENTS.md 5장 불변조건 7).
    # 위젯은 키로 집는다 — 라벨은 화면 문구라 바뀌고, 인덱스는 위젯이 늘면 다른 것을 가리킨다.
    app.sidebar.number_input(key=WARNING_THRESHOLD_KEY).set_value(95.0)
    app.get_by_key("dashboard_threshold_apply").click().run()

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


def test_the_two_display_toggles_are_part_of_the_figure_cache_key(
    seeded_database: Path,
) -> None:
    """EDP 포함 여부와 선행 반영 여부는 그림을 바꾼다. 캐시 키에 없으면 옛 그림이 남는다."""
    app = _run(seeded_database)
    app.sidebar.toggle(key="dashboard_show_performance").set_value(True).run()
    assert _cache_state(app) == "적중"

    # `EDP 포함` 의 기본은 꺼짐이다. 켜면 새로 그려야 한다.
    app.session_state["home_preference_include_edp"] = True
    app.run()
    assert not list(app.exception)
    assert _cache_state(app) == "생성"

    app.session_state["home_preference_include_edp"] = False
    app.run()
    # 되돌리면 다시 만들지 않는다. 두 토글을 오가며 비교하는 화면이라 칸이 넉넉해야 한다.
    assert _cache_state(app) == "적중"

    app.session_state["home_show_advance"] = True
    app.run()
    assert not list(app.exception)
    assert _cache_state(app) == "생성"


def test_advance_scales_the_plan_and_rate_but_leaves_capacity_alone(
    seeded_database: Path,
) -> None:
    """선행은 물량을 앞으로 옮긴 것이라 Capa 가 움직이면 안 된다.

    서비스 단위 시험이 있어도 페이지가 기존 계획과 선행 계획을 뒤바꿔 넘기면 여기서만
    드러난다. 그래서 화면까지 통과한 Figure 값으로 다시 확인한다.
    """
    import capa_simulation.settings as settings
    from capa_simulation.persistence.cache import clear_global_advance_load_cache
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    app = _run(seeded_database)
    before = _lob_traces(app)
    first_month_capacity = before["B/N 공정"].y[0]
    first_month_density = before["Density"].y[0]
    # 첫 달은 시드 프리셋이 정한다. 숫자를 적어 두면 시드가 바뀔 때 엉뚱한 달에 넣는다.
    first_month = 200000 + int(str(before["Density"].customdata[0]).replace(".", ""))

    repository = DuckDBScenarioRepository(settings.DUCKDB_PATH)
    repository.replace_global_advance_load(
        pd.DataFrame({"생산계획년월": [first_month], "선행 물량": [2.5]}),
        source="테스트",
    )
    clear_global_advance_load_cache()
    app.session_state["home_show_advance"] = True
    app.run()

    assert not list(app.exception)
    after = _lob_traces(app)
    # 계획은 넣은 만큼 정확히 늘고, 그 달의 Capa 는 그대로다.
    assert after["Density"].y[0] == pytest.approx(first_month_density + 2.5)
    assert after["B/N 공정"].y[0] == pytest.approx(first_month_capacity)
    # 기존 계획은 표식·라벨 없는 점선으로 함께 남는다.
    assert after["Density (선행 전)"].y[0] == pytest.approx(first_month_density)
    assert after["Density (선행 전)"].mode == "lines"
    assert after["Density (선행 전)"].line.dash == "dot"


def _lob_traces(app: AppTest) -> dict[str, Any]:
    """LOB 월 Figure 의 trace 를 이름으로 찾는다. 순서는 trace 를 더할 때마다 바뀐다."""
    figure = app.session_state["spy_figures"]["production_lob_months"]
    return {trace.name: trace for trace in figure.data}


def _create_comparison_scenario(database_path: Path, factor: float) -> tuple[str, str]:
    """현재 활성 계획의 수량만 바꾼 비교용 시나리오를 만든다.

    계획만 다르고 나머지 기준정보는 같아야 GAP 이 계획 차이만 나타내는지 확인할 수 있다.
    """
    from capa_simulation.persistence.cache import load_scenario_snapshot
    from capa_simulation.persistence.models import ScenarioCreate
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    repository = DuckDBScenarioRepository(database_path)
    official = repository.latest_official_release()
    assert official is not None
    snapshot = load_scenario_snapshot(str(database_path), official.revision_id)
    tables = dict(snapshot.tables)
    plan = tables["RQ_PKG_PLAN"].copy()
    plan["생산수량"] = pd.to_numeric(plan["생산수량"], errors="coerce") * factor
    tables["RQ_PKG_PLAN"] = plan
    created = repository.create_scenario(
        ScenarioCreate(
            scenario_name="비교용",
            source_simulation_code="COMPARE-1",
            source_simulation_name="비교용",
            source_type="DUCKDB_SCENARIO_CLONE",
            pipeline_version="duckdb-rq-snapshot-v3",
        ),
        tables,
        snapshot.preset,
    )
    return str(created.scenario.scenario_id), str(created.revision.revision_id)


def _pick_comparison(app: AppTest, scenario_id: str, revision_id: str) -> None:
    """비교 대상을 고른 상태로 만든다. 목록에 실린 **뒤에** 골라야 한다.

    AppTest 는 다음 실행을 시작할 때 직전 화면의 위젯 옵션으로 세션 값을 되짚는다. 화면이
    한 번도 보여 준 적 없는 시나리오를 세션에 바로 꽂으면 옵션에 없는 값이라며 멈춘다.
    실제 화면에서도 사용자는 목록에 뜬 뒤에야 고를 수 있으므로 한 번 더 돌려 맞춘다.
    """
    app.run()
    app.session_state["home_preference_comparison_scenario"] = scenario_id
    app.session_state["home_preference_comparison_revision"] = revision_id
    app.session_state["home_show_comparison"] = True


def test_comparison_gap_is_written_under_the_value(tmp_path: Path) -> None:
    """비교 GAP 은 값 아래에 붙는다. 선행 GAP(위)과 자리를 나눠 함께 켤 수 있어야 한다."""
    database_path = tmp_path / "scenario.duckdb"
    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    assert not list(app.exception)

    comparison_id, comparison_revision_id = _create_comparison_scenario(database_path, 0.5)
    _pick_comparison(app, comparison_id, comparison_revision_id)
    app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    gaps = _gap_annotations(app)
    # 계획을 절반으로 줄인 시나리오와 견주므로 현재가 더 많다 — 전부 증가여야 한다.
    assert gaps, "비교 GAP 주석이 하나도 없다"
    assert all(text.startswith("+") for text in gaps), gaps


def _gap_annotations(app: AppTest) -> list[str]:
    """LOB 월 Figure 에서 증감으로 적힌 주석만 고른다."""
    figure = app.session_state["spy_figures"]["production_lob_months"]
    return [
        str(annotation.text).strip()
        for annotation in figure.layout.annotations
        if str(annotation.text).strip().startswith(("+", "-"))
    ]


def test_a_comparison_revision_from_another_scenario_is_ignored(tmp_path: Path) -> None:
    """세션에 남은 리비전이 남의 것이면 조용히 비교를 끈다. 화면이 멈추면 안 된다."""
    database_path = tmp_path / "scenario.duckdb"
    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    assert not list(app.exception)

    comparison_id, _ = _create_comparison_scenario(database_path, 0.5)
    _pick_comparison(app, comparison_id, "사라진-리비전")
    app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert _gap_annotations(app) == []


def test_comparison_can_target_another_revision_of_the_same_scenario(tmp_path: Path) -> None:
    """리비전이 달라지며 계획이 얼마나 바뀌었는지가 비교의 중요한 쓰임이다.

    현재 활성 시나리오를 비교 대상에서 빼면 그 비교를 아예 할 수 없고, 시나리오가 하나뿐인
    저장소에서는 고를 것 자체가 없어진다.
    """
    from capa_simulation.persistence.cache import load_scenario_snapshot
    from capa_simulation.persistence.repository import REVISION_TABLES, DuckDBScenarioRepository

    database_path = tmp_path / "scenario.duckdb"
    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    assert not list(app.exception)

    repository = DuckDBScenarioRepository(database_path)
    official = repository.latest_official_release()
    assert official is not None
    base = load_scenario_snapshot(str(database_path), official.revision_id)
    revision_tables = {name: base.tables[name] for name in REVISION_TABLES if name in base.tables}
    halved = revision_tables["RQ_PKG_PLAN"].copy()
    halved["생산수량"] = pd.to_numeric(halved["생산수량"], errors="coerce") * 0.5
    revision_tables["RQ_PKG_PLAN"] = halved
    saved = repository.save_revision(
        official.scenario_id,
        revision_tables,
        base.preset,
        revision_name="계획 절반",
    )

    # 현재 활성은 공식 리비전 그대로 두고, 같은 시나리오의 새 리비전과 견준다.
    _pick_comparison(app, str(official.scenario_id), str(saved.revision.revision_id))
    app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    gaps = _gap_annotations(app)
    # 비교 쪽 계획이 절반이므로 현재가 더 많다 — 전부 증가여야 한다.
    assert gaps, "같은 시나리오의 다른 리비전과 견준 GAP 이 하나도 없다"
    assert all(text.startswith("+") for text in gaps), gaps


def _value_slots(app: AppTest) -> list[tuple[float, float, float]]:
    """LOB 표 세 행의 값 글자가 놓인 자리. 값 자체가 아니라 **자리**만 본다.

    선행을 켜면 값 숫자는 바뀌므로 글자로는 맞출 수 없다. 크기가 값 글자 크기인 주석의
    (x, y, yshift) 를 모으면 그 자리가 그대로인지 볼 수 있다.
    """
    figure = app.session_state["spy_figures"]["production_lob_months"]
    return sorted(
        (float(annotation.x), float(annotation.y), float(annotation.yshift or 0))
        for annotation in figure.layout.annotations
        if annotation.font.size == LOB_VALUE_FONT_SIZE_PX
    )


def test_the_value_never_moves_or_shrinks_when_gaps_are_switched_on(tmp_path: Path) -> None:
    """선행·GAP 을 어떻게 켜도 원 데이터의 크기와 자리는 그대로여야 한다.

    예전에는 증감을 끼우려고 값 글자를 0.85·0.65 배로 줄이고 반대쪽으로 밀었다. 토글 하나에
    표 전체의 숫자가 커졌다 작아졌다 해서 읽던 자리를 놓친다. 지금은 행 높이가 두 줄 자리를
    미리 비워 두므로 값은 언제나 같은 크기로 칸 한가운데에 선다.

    자리 **개수**까지 함께 본다. 값 하나라도 작아지면 그 주석이 이 묶음에서 빠진다.
    """
    database_path = tmp_path / "scenario.duckdb"
    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    assert not list(app.exception)

    before = _value_slots(app)
    assert before, "값 주석을 하나도 찾지 못했다"

    comparison_id, comparison_revision_id = _create_comparison_scenario(database_path, 0.5)
    _pick_comparison(app, comparison_id, comparison_revision_id)
    app.session_state["home_show_advance"] = True
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert _gap_annotations(app), "선행·GAP 을 켰는데 증감이 하나도 없다"

    assert _value_slots(app) == before


def test_every_gap_uses_one_font_size(tmp_path: Path) -> None:
    """증감 글자는 자리마다 다르면 안 된다. 같은 뜻의 표기가 크기로 갈리면 위계로 읽힌다."""
    database_path = tmp_path / "scenario.duckdb"
    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()
    assert not list(app.exception)

    comparison_id, comparison_revision_id = _create_comparison_scenario(database_path, 0.5)
    _pick_comparison(app, comparison_id, comparison_revision_id)
    app.session_state["home_show_advance"] = True
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]

    figure = app.session_state["spy_figures"]["production_lob_months"]
    sizes = {
        int(annotation.font.size)
        for annotation in figure.layout.annotations
        if str(annotation.text).strip().startswith(("+", "-"))
    }
    assert sizes == {tokens.DELTA_FONT_SIZE_PX}, sizes


def test_the_dashboard_is_not_drawn_while_its_tab_is_hidden(seeded_database: Path) -> None:
    """숨은 탭에서 그리면 `go.Table` 머리글이 셀 가운데를 놓치고 그대로 굳는다.

    숨겨진 요소 안에서는 SVG 글자 폭 측정이 0 이라 Plotly 가 가운데 정렬 보정을 못 하고,
    상세 세 Figure 는 `staticPlot` 이라 탭을 열어도 다시 그리지 않는다. Preference 에서
    비교 시나리오를 고르거나 선행 물량을 저장하면 앱이 다시 도는데, 그때 Main 이 닫혀
    있으면 정확히 그 상황이 된다.
    """
    app = _run(seeded_database)
    assert app.session_state["spy_traces"] == [0, 1, 1, 3, 1, 4]

    app.session_state["home_active_tab"] = ":material/tune: Preference"
    app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert app.session_state["spy_traces"] == []


def test_the_detail_toggle_survives_a_hidden_tab(seeded_database: Path) -> None:
    """닫힌 동안 위젯을 그리지 않아도 값은 남아야 한다.

    「상세」 토글은 그림과 함께 건너뛰는 유일한 위젯이다. `persist_state="session"` 이
    그 값을 붙들어 주는데, 그것이 깨지면 탭을 오갈 때마다 분류가 초기화된다.
    """
    app = _run(seeded_database)
    app.session_state["home_preference_plan_detail_customer"] = True
    app.session_state["home_active_tab"] = ":material/tune: Preference"
    app.run()
    assert not list(app.exception)

    app.session_state["home_active_tab"] = ":material/dashboard: Main"
    app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert app.session_state["home_preference_plan_detail_customer"] is True


def test_the_two_columns_keep_paired_children(seeded_database: Path) -> None:
    """왼쪽 라벨 칸과 오른쪽 월 칸은 자식 수·차례가 같아야 행이 맞는다.

    이 계약은 지금까지 브라우저로만 확인할 수 있었다. 한쪽에만 무언가를 끼우면 그 아래
    모든 행이 어긋나는데, 어긋난 픽셀은 눈으로 봐야 보였다. `AppTest` 가 1.63 부터 컨테이너
    key 를 내주므로 여기서 잡는다.
    """
    app = _run(seeded_database)

    label_canvas = app.get_by_key("production_lob_label_canvas")
    month_canvas = app.get_by_key("production_lob_month_canvas")
    assert [child.key for child in label_canvas.children.values()] == [
        "production_lob_labels",
        "plan_detail_title_row",
        "production_detail_labels",
        "bottleneck_title_row",
        "bottleneck_detail_labels",
    ]
    assert [child.key for child in month_canvas.children.values()] == [
        "production_lob_months",
        "plan_detail_title_spacer",
        "production_detail_months",
        "bottleneck_title_spacer",
        "bottleneck_detail_months",
    ]


def test_the_title_spacers_keep_their_pinned_height(seeded_database: Path) -> None:
    """빈 컨테이너는 높이를 주지 않으면 Streamlit 이 아예 그리지 않는다.

    월 칸의 빈 줄이 사라지면 그 칸만 위로 올라붙어 아래 표의 행이 통째로 어긋난다.
    """
    app = _run(seeded_database)

    for key in ("plan_detail_title_spacer", "bottleneck_title_spacer"):
        spacer = app.get_by_key(key)
        assert spacer.proto.height_config.pixel_height == DASHBOARD_TITLE_HEIGHT_PX, key


def test_the_lob_panel_border_closes_on_the_bottom_edge(seeded_database: Path) -> None:
    """아래 테두리는 그림의 맨 아랫줄에 놓여야 한다.

    paper 좌표를 비율로 적어 두면 행 높이를 한 번 올릴 때마다 그림 영역이 함께 커져
    같은 비율이 캔버스 밖으로 밀린다. 그러면 Plotly 는 선을 그리기는 하지만 잘려 나가
    **화면에서는 아래 테두리가 통째로 사라진다.** 오류도 경고도 없다.
    """
    app = _run(seeded_database)
    figure = app.session_state["spy_figures"]["production_lob_labels"]

    plot_area = figure.layout.height - LOB_TOP_MARGIN_PX - LOB_BOTTOM_MARGIN_PX
    horizontals = [
        shape for shape in figure.layout.shapes if shape.type == "line" and shape.y0 == shape.y1
    ]
    assert horizontals, "가로선이 하나도 없다"
    # 패널 맨 아랫줄에는 테두리와 구획 격자선이 함께 놓인다. 굵은 쪽이 테두리다.
    bottom_y = min(shape.y0 for shape in horizontals)
    assert bottom_y < 0, "아래 테두리가 그림 영역 안에 머물러 아래 여백을 감싸지 못한다"

    bottom_px = LOB_TOP_MARGIN_PX + plot_area * (1 - bottom_y)
    assert bottom_px == pytest.approx(figure.layout.height)

    def _widest(target_y: float) -> float:
        return max(shape.line.width for shape in horizontals if shape.y0 == target_y)

    # 맨 끝줄의 획은 절반이 잘린다. 위 테두리와 같은 굵기로 그려야 보이는 두께가 같다.
    assert _widest(bottom_y) == _widest(1)


def test_the_chart_rows_share_the_table_rows_label_color(seeded_database: Path) -> None:
    """`생산계획 LOB`·`B/N Top 5` 도 `Density (억Gb)` 와 같은 구분 칸의 행 이름이다.

    한쪽만 흐리면 같은 칸에 나란히 선 이름들이 서로 다른 위계로 읽힌다.
    """
    app = _run(seeded_database)
    figure = app.session_state["spy_figures"]["production_lob_labels"]

    colors = {annotation.text: annotation.font.color for annotation in figure.layout.annotations}
    row_names = [
        "<b>Density (억Gb)</b>",
        "<b>Wafer 계획</b>",
        "<b>Wafer Capa</b>",
        "<b>생산계획 LOB</b>",
        "<b>B/N Top 5</b>",
    ]
    missing = [name for name in row_names if name not in colors]
    assert not missing, missing
    assert {colors[name] for name in row_names} == {tokens.TEXT}


def test_both_detail_columns_center_when_the_gap_toggle_is_off(seeded_database: Path) -> None:
    """GAP 이 꺼져 있으면 분류 칸과 월 칸의 글자가 같은 눈높이에 선다.

    `go.Table` 은 한 줄짜리 칸의 글자를 칸 위에 붙여 그린다. 증감이 오지 않는데 그 자리에
    세우면 위로 쏠려 보이고, 한쪽만 그러면 같은 행의 두 칸이 어긋나 보인다. 빈 줄 하나를
    붙여 가운데에 세우되 행 높이는 그대로여야 한다.
    """
    app = _run(seeded_database)
    assert not app.session_state["home_show_comparison"], "이 테스트는 GAP 이 꺼진 상태다"
    label_cells = app.session_state["spy_figures"]["production_detail_labels"].data[0].cells
    month_cells = app.session_state["spy_figures"]["production_detail_months"].data[0].cells

    for name, cells in (("분류", label_cells), ("월", month_cells)):
        filled = [value for column in cells.values for value in column if value]
        assert filled, f"{name} 칸이 비어 있다"
        assert all(value.endswith("<br>") for value in filled), name
        # 빈 칸에 빈 줄을 붙이면 없는 값 자리에 줄만 생긴다.
        assert all(value == "" for column in cells.values for value in column if not value), name

    # 빈 줄은 높이를 더하지 않는다. 두 칸의 행이 어긋나면 표 전체가 틀어진다.
    assert label_cells.height == month_cells.height
    label_figure = app.session_state["spy_figures"]["production_detail_labels"]
    month_figure = app.session_state["spy_figures"]["production_detail_months"]
    assert label_figure.layout.height == month_figure.layout.height
