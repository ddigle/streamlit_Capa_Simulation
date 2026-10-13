# Purpose: HOME Main 탭이 숨은 회차는 그림을 미루고 Main 을 여는 회차에 같은 그림을 만드는지 본다.

"""숨은 Main 은 그림을 미루고, 돌아오는 회차에 지금 조건으로 한 번 만든다.

Preference·Past Data 에서 저장하면 공용 프로필 version 이 바뀌어 묶음 키가 빗나간다. 전에는 그
회차에 숨은 Main 의 그림까지 만들었다(화면에 나가지 않는 그림). 이제는 Main 을 여는 회차에 만든다.
여기서 지키는 것:

- 숨은 회차에는 그림 생성기를 하나도 부르지 않는다(저장을 여러 번 해도).
- Main 으로 돌아온 회차의 그림 == 같은 세션 상태에서 캐시 없이 새로 만든 그림(Plotly JSON).
- 저장한 값이 그 그림의 키에 실제로 들어간다(Top5 구간·판정 기준·과거 구간·미저장 편집·비교 리비전).
- 진행 막대가 숨은 회차에도 같은 단계 수를 넘긴다.

합성 시드 위의 수치는 표본이다. 이 시험이 보는 것은 값이 아니라 **두 경로의 같음**이다.
"""

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.components.home_rendering import (
    LOB_FIGURES,
    LobFigureKey,
    latest_home_figure_key,
)
from capa_simulation.io.reference_cache import HOME_FIGURE_CACHE_KEY
from capa_simulation.persistence import cache as persistence_cache
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_state import ACTIVE_SCENARIO_KEY
from capa_simulation.services.simulation_cache import shared_home_figure_store

HOME_PAGE = Path(__file__).resolve().parents[1] / "app_pages" / "home.py"
TAB_KEY = "home_active_tab"
MAIN = ":material/dashboard: Main"
PREFERENCE = ":material/tune: Preference"
PAST = ":material/history: Past Data"
FRESH_KEY = "spy_fresh"
LOB = "build_lob_summary_figures"
PLAN = "build_plan_detail_figures"
HEATMAP = "build_key_process_heatmap_figures"
BOTTLENECK = "build_bottleneck_detail_figures"
BUILDERS = (LOB, PLAN, HEATMAP, BOTTLENECK)
DUMBBELL_CHART_KEY = "home_plan_comparison_dumbbell"


def _script(database_path: Path) -> str:
    """HOME 을 한 번 돌린다. 생성기 호출·그린 Figure·진행 막대 단계를 세션에 적는다.

    생성기 호출과 진행 막대 기록은 **시험이 비운다** — 저장은 제출 회차와 `st.rerun` 회차 두 번을
    한 `run()` 안에서 도므로, 스크립트가 비우면 앞 회차의 호출을 놓친다.
    """
    return f"""
from pathlib import Path

import streamlit as st

import capa_simulation.components.home_figures as home_figures
import capa_simulation.components.home_rendering as home_rendering
import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
import capa_simulation.components.loading_progress as loading_progress
import capa_simulation.settings as settings

settings.DUCKDB_PATH = Path({str(database_path)!r})

from capa_simulation.scenario_activation import bootstrap_latest_official_scenario
from capa_simulation.scenario_preset_state import apply_pending_scenario_preset

bootstrap_latest_official_scenario(str(settings.DUCKDB_PATH))
apply_pending_scenario_preset()

st.session_state["spy_figures"] = {{}}
st.session_state.setdefault("spy_builds", [])
st.session_state.setdefault("spy_progress", [])
_builders = {{name: getattr(home_figures, name) for name in {BUILDERS!r}}}
_original_chart = st.plotly_chart
_original_scrollbar = horizontal_scrollbar.render_horizontal_scrollbar
_original_take = home_rendering.take_home_figures
_original_store = home_rendering.store_home_figures
_original_advance = loading_progress.LoadingProgress.advance
_original_close = loading_progress.LoadingProgress.close


def _counted(name):
    def builder(*args, **kwargs):
        st.session_state["spy_builds"] = [*st.session_state["spy_builds"], name]
        return _builders[name](*args, **kwargs)

    return builder


def _advance(self):
    st.session_state["spy_progress"] = [*st.session_state["spy_progress"], "advance"]
    return _original_advance(self)


def _close(self):
    st.session_state["spy_progress"] = [*st.session_state["spy_progress"], "close"]
    return _original_close(self)


def _spy_chart(figure, *args, **kwargs):
    st.session_state["spy_figures"] = {{
        **st.session_state["spy_figures"],
        kwargs.get("key"): figure.to_json(),
    }}
    return _original_chart(figure, *args, **kwargs)


for _name in _builders:
    setattr(home_figures, _name, _counted(_name))
st.plotly_chart = _spy_chart
horizontal_scrollbar.render_horizontal_scrollbar = lambda *_args, **_kwargs: None
loading_progress.LoadingProgress.advance = _advance
loading_progress.LoadingProgress.close = _close
if st.session_state.get({FRESH_KEY!r}):
    home_rendering.take_home_figures = lambda *_args, **_kwargs: None
    home_rendering.store_home_figures = lambda *_args, **_kwargs: None
try:
    page_source = Path({str(HOME_PAGE)!r}).read_text(encoding="utf-8")
    exec(compile(page_source, {str(HOME_PAGE)!r}, "exec"), {{"__name__": "__main__"}})
finally:
    for _name, _builder in _builders.items():
        setattr(home_figures, _name, _builder)
    st.plotly_chart = _original_chart
    horizontal_scrollbar.render_horizontal_scrollbar = _original_scrollbar
    home_rendering.take_home_figures = _original_take
    home_rendering.store_home_figures = _original_store
    loading_progress.LoadingProgress.advance = _original_advance
    loading_progress.LoadingProgress.close = _original_close
"""


def _assert_clean(app: AppTest) -> None:
    assert not list(app.exception), [element.message for element in app.exception]
    assert not list(app.error), [element.value for element in app.error]


def _open(database_path: Path) -> AppTest:
    # 다른 시험이 같은 프로세스의 공용 칸을 채워 두었을 수 있다. 남아 있으면 처음 보는 조합도
    # 복원되어 「생성기를 불렀나」를 볼 수 없다.
    shared_home_figure_store.clear()
    app = AppTest.from_string(_script(database_path), default_timeout=300)
    app.run()
    _assert_clean(app)
    return app


def _step(app: AppTest) -> AppTest:
    """한 조작을 돈다. 그 조작(저장이면 제출·rerun 두 회차)의 생성기 호출만 남긴다."""
    app.session_state["spy_builds"] = []
    app.session_state["spy_progress"] = []
    app.run()
    _assert_clean(app)
    return app


def _builds(app: AppTest) -> list[str]:
    return list(app.session_state["spy_builds"])


def _lob_key(app: AppTest) -> LobFigureKey:
    key = latest_home_figure_key(app.session_state[HOME_FIGURE_CACHE_KEY], LOB_FIGURES)
    assert key is not None
    return key


def _plotly_spec(value: Any) -> Any:
    """Plotly JSON 을 같음을 잴 모양으로. 빈 dict 칸만 지운다(공용 칸 복원이 떨구는 칸)."""
    if isinstance(value, dict):
        pruned = {key: _plotly_spec(item) for key, item in value.items()}
        return {key: item for key, item in pruned.items() if item != {}}
    if isinstance(value, list):
        return [_plotly_spec(item) for item in value]
    return value


def _figures(app: AppTest) -> dict[str, Any]:
    return {
        key: _plotly_spec(json.loads(spec))
        for key, spec in app.session_state["spy_figures"].items()
    }


def _assert_same_as_fresh(app: AppTest, label: str) -> dict[str, Any]:
    """방금 Main 이 그린 그림 == 같은 세션 상태에서 캐시를 끄고 새로 만든 그림."""
    drawn = _figures(app)
    assert len(drawn) >= 8, label
    app.session_state[FRESH_KEY] = True
    _step(app)
    app.session_state[FRESH_KEY] = False
    fresh = _figures(app)
    assert set(drawn) == set(fresh), label
    different = sorted(key for key in drawn if drawn[key] != fresh[key])
    assert not different, f"{label}: 미뤘다가 만든 그림이 새로 만든 그림과 다르다 — {different}"
    return drawn


def _clear_profile_caches() -> None:
    """공용 프로필 캐시를 모두 비운다 — 다른 세션이 저장했을 때 저장 단추가 하는 일과 같다."""
    for name in dir(persistence_cache):
        if name.startswith("clear_global_") and name.endswith("_cache"):
            getattr(persistence_cache, name)()


def _save_top5(app: AppTest, maximum: float) -> AppTest:
    """Top5 구간의 상한을 저장한다. 상한은 축 위끝이라 늘 그림을 바꾼다(하한은 시드 확보율이
    모두 그보다 커서 막대를 바꾸지 못할 수 있다)."""
    next(widget for widget in app.main.number_input if widget.label == "상한(%)").set_value(maximum)
    next(button for button in app.button if button.label == "확보율 구간 저장").click()
    return _step(app)


def _open_tab(app: AppTest, label: str) -> AppTest:
    app.session_state[TAB_KEY] = label
    return _step(app)


def test_a_save_on_preference_draws_nothing_and_main_draws_it_on_return(tmp_path: Path) -> None:
    """Top5 저장은 숨은 Main 의 그림을 만들지 않는다. 돌아온 Main 이 새 구간으로 한 번 만든다."""
    database_path = tmp_path / "scenario.duckdb"
    app = _open(database_path)
    assert set(_builds(app)) == set(BUILDERS)
    before = _lob_key(app)
    first_figures = _figures(app)

    _open_tab(app, PREFERENCE)
    assert _builds(app) == []
    assert app.session_state["spy_figures"] == {}

    app.session_state["dashboard_show_performance"] = True
    _save_top5(app, 150.0)
    assert _builds(app) == []
    assert app.session_state["spy_figures"] == {}
    # 숨은 회차는 캐시를 보지도 않는다 — 가장 최근 키가 저장 전 그대로다.
    assert _lob_key(app) == before
    assert [
        caption.value for caption in app.caption if caption.value.startswith("Figure 캐시: ")
    ] == ["Figure 캐시: 건너뜀"]
    app.session_state["dashboard_show_performance"] = False

    _open_tab(app, MAIN)
    # Top5 구간은 LOB 묶음에만 닿는다(의존 표).
    assert _builds(app) == [LOB]
    saved = DuckDBScenarioRepository(database_path).load_global_top5_band()
    after = _lob_key(app)
    assert after.top5_max_rate == pytest.approx(1.5)
    assert after.top5_band_version == saved.version
    assert after.top5_band_version != before.top5_band_version
    drawn = _assert_same_as_fresh(app, "Top5 저장 뒤 Main")
    # 실제로 그림이 바뀌었다 — 같음 시험이 맹물이 아니다.
    assert drawn["production_lob_months"] != first_figures["production_lob_months"]


def test_several_saves_on_preference_build_once_when_main_opens(tmp_path: Path) -> None:
    """저장을 세 번 해도 숨은 동안에는 만들지 않고, Main 을 열 때 마지막 값으로 한 번 만든다."""
    database_path = tmp_path / "scenario.duckdb"
    app = _open(database_path)
    _open_tab(app, PREFERENCE)
    for maximum in (150.0, 120.0, 180.0):
        _save_top5(app, maximum)
        assert _builds(app) == [], maximum

    _open_tab(app, MAIN)
    assert _builds(app) == [LOB]
    assert _lob_key(app).top5_max_rate == pytest.approx(1.8)
    _assert_same_as_fresh(app, "Top5 세 번 저장 뒤 Main")

    # 같은 조건으로 다시 돌면 적중이다.
    _step(app)
    assert _builds(app) == []


def test_profiles_saved_elsewhere_and_unsaved_edits_reach_main_on_return(tmp_path: Path) -> None:
    """숨은 동안 바뀐 것(다른 세션이 저장한 판정 기준·과거 구간, 이 세션의 미저장 편집)이
    돌아온 Main 의 그림에 들어간다. 다시 만드는 묶음은 의존 표와 같다."""
    database_path = tmp_path / "scenario.duckdb"
    app = _open(database_path)
    repository = DuckDBScenarioRepository(database_path)
    processes = list(app.session_state["dashboard_bottleneck_process_seen"])
    base = _figures(app)

    # 판정 기준 — 다른 세션의 저장처럼 저장소에 쓰고 프로필 캐시를 비운다.
    _open_tab(app, PREFERENCE)
    threshold = repository.load_global_securement_threshold()
    # 합성 시드의 확보율은 수천 % 대라 기준을 그만큼 올려야 색이 바뀐다(표본 관측).
    repository.replace_global_securement_threshold(
        500.0,
        300.0,
        pd.DataFrame({"생산계획년월": [202602], "확보 기준": [800.0], "경고 기준": [600.0]}),
        source="시험",
        expected_version=threshold.version,
    )
    _clear_profile_caches()
    _step(app)
    assert _builds(app) == []
    _open_tab(app, MAIN)
    assert set(_builds(app)) == {LOB, HEATMAP, BOTTLENECK}
    after_threshold = _assert_same_as_fresh(app, "판정 기준 저장 뒤 Main")
    # 시드에는 주요공정 프리셋이 없어 히트맵은 비어 있다 — 판정 색은 상세 B/N 에서 본다.
    assert after_threshold["bottleneck_detail_months"] != base["bottleneck_detail_months"]

    # 과거 구간 — 네 묶음 모두의 월 축에 닿는다.
    _open_tab(app, PAST)
    repository.replace_global_past_data(
        {
            "월별": pd.DataFrame(
                {"생산계획년월": [202510], "Density": [9.0], "Wafer Total": [120_000.0]}
            ),
            "계획": pd.DataFrame(
                {
                    "생산계획년월": [202510],
                    "제품정보": ["DEMO PRODUCT A"],
                    "Stack": ["8H"],
                    "Customer": ["DEMO_CUSTOMER_A"],
                    "생산수량": [110.0],
                }
            ),
            "확보율": pd.DataFrame(
                {"생산계획년월": [202510], "공정": [processes[0]], "확보율": [1.05]}
            ),
        },
        source="시험",
    )
    _clear_profile_caches()
    _step(app)
    assert _builds(app) == []
    app.session_state["production_month_range_v2"] = ("2025-10", "2026-12")
    _open_tab(app, MAIN)
    assert set(_builds(app)) == set(BUILDERS)
    after_past = _assert_same_as_fresh(app, "과거 구간 저장 뒤 Main")
    assert '"25.10"' in json.dumps(after_past["production_lob_months"])

    # 미저장 편집 — 이 세션의 계획을 바꾸고 내용 토큰을 새로 낸다(편집 적용이 하는 일).
    _open_tab(app, PREFERENCE)
    active = app.session_state[ACTIVE_SCENARIO_KEY]
    tables = dict(active["tables"])
    plan = tables["RQ_PKG_PLAN"].copy()
    plan["생산수량"] = pd.to_numeric(plan["생산수량"]) * 1.5
    tables["RQ_PKG_PLAN"] = plan
    app.session_state[ACTIVE_SCENARIO_KEY] = {
        **active,
        "tables": tables,
        "content_token": "edited-hidden-main",
    }
    _step(app)
    assert _builds(app) == []
    _open_tab(app, MAIN)
    assert set(_builds(app)) == set(BUILDERS)
    edited = _assert_same_as_fresh(app, "미저장 편집 뒤 Main")
    assert edited["production_lob_months"] != after_past["production_lob_months"]


def test_a_comparison_picked_on_preference_is_drawn_when_main_opens(tmp_path: Path) -> None:
    """비교 시나리오를 Preference 에서 고르면 숨은 동안은 만들지 않고, Main 이 GAP·덤벨을 그린다."""
    from capa_simulation.components.home_preference import (
        COMPARISON_REVISION_KEY,
        COMPARISON_SCENARIO_KEY,
    )
    from capa_simulation.home_state import COMPARISON_TOGGLE_KEY
    from capa_simulation.persistence.cache import load_scenario_snapshot
    from capa_simulation.persistence.models import ScenarioCreate

    database_path = tmp_path / "scenario.duckdb"
    app = _open(database_path)
    repository = DuckDBScenarioRepository(database_path)
    official = repository.latest_official_release()
    assert official is not None
    snapshot = load_scenario_snapshot(str(database_path), official.revision_id)
    tables = dict(snapshot.tables)
    plan = tables["RQ_PKG_PLAN"].copy()
    plan["생산수량"] = pd.to_numeric(plan["생산수량"], errors="coerce") * 0.5
    tables["RQ_PKG_PLAN"] = plan
    created = repository.create_scenario(
        ScenarioCreate(
            scenario_name="비교용",
            source_simulation_code="COMPARE-HIDDEN",
            source_simulation_name="비교용",
            source_type="DUCKDB_SCENARIO_CLONE",
            pipeline_version="duckdb-rq-snapshot-v3",
        ),
        tables,
        snapshot.preset,
    )
    scenario_id = str(created.scenario.scenario_id)

    _open_tab(app, PREFERENCE)
    app.session_state[COMPARISON_TOGGLE_KEY] = True
    app.selectbox(key=COMPARISON_SCENARIO_KEY).set_value(scenario_id)
    _step(app)
    assert app.session_state[COMPARISON_REVISION_KEY] == str(created.revision.revision_id)
    assert _builds(app) == []
    assert app.session_state["spy_figures"] == {}

    _open_tab(app, MAIN)
    # 비교는 LOB(Density·Wafer 증감)와 계획 세부수량(+덤벨)에만 닿는다.
    assert set(_builds(app)) == {LOB, PLAN}
    assert _lob_key(app).comparison_revision_id == str(created.revision.revision_id)
    drawn = _assert_same_as_fresh(app, "비교 고른 뒤 Main")
    assert DUMBBELL_CHART_KEY in drawn

    # 비교가 붙은 채 다시 숨겨도 덤벨 상자가 오류 없이 선다(묶음이 없는 회차).
    _open_tab(app, PREFERENCE)
    assert _builds(app) == []
    assert DUMBBELL_CHART_KEY not in app.session_state["spy_figures"]
    assert any(expander.label == "시나리오 비교 · 차이 큰 분류" for expander in app.expander)


def test_the_loading_bar_takes_the_same_steps_whether_main_is_open_or_hidden(
    tmp_path: Path,
) -> None:
    """입장 화면이 `HOME_LOADING_STAGES` 퍼센트를 읽는다. 숨은 회차도 같은 단계를 지난다."""
    app = _open(tmp_path / "scenario.duckdb")
    steps: dict[str, list[str]] = {}
    for label in (PREFERENCE, PAST, MAIN):
        _open_tab(app, label)
        steps[label] = list(app.session_state["spy_progress"])
    assert steps[MAIN] == ["advance"] * 4 + ["close"]
    assert steps[PREFERENCE] == steps[MAIN]
    assert steps[PAST] == steps[MAIN]
