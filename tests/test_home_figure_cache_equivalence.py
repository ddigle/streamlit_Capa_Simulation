# Purpose: HOME 묶음별 Figure 캐시를 거친 그림이 같은 조건에서 새로 만든 그림과 같은지 본다.

"""캐시를 거친 그림 == 캐시 없이 새로 만든 그림.

Figure 캐시는 묶음(LOB·계획 세부수량·주요공정·상세 B/N)마다 제 몫의 조건만 키로 쓴다. 키에서
조건 하나를 잘못 빼면 그 조건을 바꿔도 **옛 그림이 오류 없이** 나온다 — 느린 것보다 훨씬 나쁜
결함이고, 단위 테스트(키 정의만 보는)로는 「그 조건이 정말 그 묶음에 닿지 않는가」를 확인할 수
없다. 여기서는 실제 HOME 페이지를 돌려 확인한다.

- 토글 일곱(선행 B/O·선행 입고·실행 Loss·GAP·상세 계획·EDP 포함·Past Data 포함)·제품별 비중
  단위·주요공정 프리셋·테마를 **무작위 차례로** 바꾸고, 자주 되돌린다(되돌릴 때 캐시가 맞는다).
  켜고 끄는 차례가 달라도 낡은 묶음이 섞여 나오지 않아야 한다.
- 걸음마다 같은 세션 상태로 한 번 더 돌리되 캐시를 꺼서(꺼내지도 넣지도 않는다) 새로 만든
  그림과 Plotly JSON 이 한 글자도 다르지 않은지 본다. 덤벨(접힌 비교 상자)도 같다.
- 데이터는 토글이 실제로 그림을 바꾸도록 준비한다: EDP 제품 행(EDP 만 있는 달 하나 — 끄면 월
  축에서 그 달이 빠진다), 비교 시나리오, 선행 B/O·실행 Loss·선행 입고 실적, 과거 구간 두 달,
  주요공정 프리셋 셋(하나는 이 화면에 없는 공정).
- 새 세션이 공용 칸에서 복원한 그림, 편집 중인 세션(공용 칸에 넣지 않는다)도 본다.

합성 시드 위의 수치는 표본이다. 이 시험이 보는 것은 값이 아니라 **두 경로의 같음**이다.
"""

import json
import random
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.components.home_rendering import (
    BOTTLENECK_FIGURES,
    KEY_PROCESS_FIGURES,
    LOB_FIGURES,
    PLAN_DETAIL_FIGURES,
)
from capa_simulation.home_state import (
    ADVANCE_SHIPMENT_TOGGLE_KEY,
    ADVANCE_TOGGLE_KEY,
    COMPARISON_TOGGLE_KEY,
    EDP_TOGGLE_KEY,
    EXECUTION_TOGGLE_KEY,
    PAST_DATA_TOGGLE_KEY,
    PLAN_DETAIL_CUSTOMER_KEY,
    PRODUCT_SHARE_BASIS_KEY,
)
from capa_simulation.services.simulation_cache import shared_home_figure_store

HOME_PAGE = Path(__file__).resolve().parents[1] / "app_pages" / "home.py"
PRESET_KEY = "home_key_process_preset"
THEME_KEY = "spy_theme"
FRESH_KEY = "spy_fresh"
PRESETS = ("주요 A", "주요 B", "없는 공정")
TOGGLES = (
    ADVANCE_TOGGLE_KEY,
    ADVANCE_SHIPMENT_TOGGLE_KEY,
    EXECUTION_TOGGLE_KEY,
    COMPARISON_TOGGLE_KEY,
    PLAN_DETAIL_CUSTOMER_KEY,
    EDP_TOGGLE_KEY,
    PAST_DATA_TOGGLE_KEY,
)
DUMBBELL_CHART_KEY = "home_plan_comparison_dumbbell"
EDP_ONLY_MONTH = 202612


def _script(database_path: Path) -> str:
    """HOME 을 한 번 돌린다. 그린 Figure 를 JSON 으로 모으고 테마·캐시 끄기를 세션에서 받는다.

    캐시를 끈 회차는 묶음을 꺼내지도 넣지도 않는다 — 그 회차가 캐시를 데우면 다음 걸음의 「캐시를
    거친 그림」이 사실은 방금 새로 만든 그림이 되어 시험이 아무것도 보지 못한다.
    """
    return f"""
from pathlib import Path

import streamlit as st

import capa_simulation.components.home_rendering as home_rendering
import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
import capa_simulation.settings as settings
from capa_simulation.design import theme

settings.DUCKDB_PATH = Path({str(database_path)!r})

from capa_simulation.scenario_activation import bootstrap_latest_official_scenario
from capa_simulation.scenario_preset_state import apply_pending_scenario_preset

bootstrap_latest_official_scenario(str(settings.DUCKDB_PATH))
apply_pending_scenario_preset()

theme._LOCAL.mode = st.session_state.get({THEME_KEY!r}, "light")
st.session_state["spy_figures"] = {{}}
_original_chart = st.plotly_chart
_original_scrollbar = horizontal_scrollbar.render_horizontal_scrollbar
_original_take = home_rendering.take_home_figures
_original_store = home_rendering.store_home_figures


def _spy_chart(figure, *args, **kwargs):
    st.session_state["spy_figures"] = {{
        **st.session_state["spy_figures"],
        kwargs.get("key"): figure.to_json(),
    }}
    return _original_chart(figure, *args, **kwargs)


st.plotly_chart = _spy_chart
horizontal_scrollbar.render_horizontal_scrollbar = lambda *_args, **_kwargs: None
if st.session_state.get({FRESH_KEY!r}):
    home_rendering.take_home_figures = lambda *_args, **_kwargs: None
    home_rendering.store_home_figures = lambda *_args, **_kwargs: None
try:
    page_source = Path({str(HOME_PAGE)!r}).read_text(encoding="utf-8")
    exec(compile(page_source, {str(HOME_PAGE)!r}, "exec"), {{"__name__": "__main__"}})
finally:
    st.plotly_chart = _original_chart
    horizontal_scrollbar.render_horizontal_scrollbar = _original_scrollbar
    home_rendering.take_home_figures = _original_take
    home_rendering.store_home_figures = _original_store
    theme._LOCAL.mode = None
"""


def _prepare_database(database_path: Path) -> None:
    """토글마다 그림이 실제로 달라지도록 합성 시드 위에 조건을 얹는다."""
    from capa_simulation.application_bootstrap import ensure_initial_scenario
    from capa_simulation.persistence.models import ScenarioCreate
    from capa_simulation.persistence.repository import DuckDBScenarioRepository
    from capa_simulation.services.builtin_seed import load_builtin_display_order
    from capa_simulation.services.product_type import EDP_PRODUCT_TYPE, PRODUCT_TYPE_COLUMN

    repository = DuckDBScenarioRepository(database_path)
    repository.initialize()
    repository.initialize_global_display_order(load_builtin_display_order())
    seed = ensure_initial_scenario(repository).release
    assert seed is not None
    snapshot = repository.load_revision(seed.revision_id)
    tables = dict(snapshot.tables)
    plan = tables["RQ_PKG_PLAN"].copy()
    mass = plan["양산구분"].astype("string").str.strip().eq("양산")
    # EDP 제품 행: 양산 제품을 거래선만 바꿔 복제한다. 기준정보는 제품·Stack 으로 찾으므로 그대로
    # 환산되고, 「EDP 포함」 을 끄면 이 행만 빠진다.
    edp_rows = plan.loc[mass].copy()
    edp_rows["Customer"] = "DEMO_CUSTOMER_EDP"
    edp_rows[PRODUCT_TYPE_COLUMN] = EDP_PRODUCT_TYPE
    edp_rows["생산수량"] = pd.to_numeric(edp_rows["생산수량"]) * 0.4
    # 마지막 달은 양산이 EDP 뿐이다 — 「EDP 포함」 을 끄면 월 축에서 그 달이 빠진다.
    months = pd.to_numeric(plan["생산계획년월"])
    plan = plan.loc[~(mass & months.eq(EDP_ONLY_MONTH))]
    plan = pd.concat([plan, edp_rows], ignore_index=True)
    tables["RQ_PKG_PLAN"] = plan

    def metadata(name: str, code: str) -> ScenarioCreate:
        return ScenarioCreate(
            scenario_name=name,
            source_simulation_code=code,
            source_simulation_name="동등성 시험",
            source_type="DUCKDB_SCENARIO_CLONE",
            pipeline_version="duckdb-rq-snapshot-v3",
        )

    current = repository.create_scenario(
        metadata("EDP 포함", "EQ-CURRENT"), tables, snapshot.preset
    )
    repository.publish_official_revision(
        current.scenario.scenario_id, current.revision.revision_id, release_name="동등성 시험"
    )
    compared = dict(tables)
    compared_plan = plan.copy()
    compared_plan["생산수량"] = pd.to_numeric(compared_plan["생산수량"]) * 0.8
    compared["RQ_PKG_PLAN"] = compared_plan
    comparison = repository.create_scenario(
        metadata("비교", "EQ-COMPARE"), compared, snapshot.preset
    )
    repository.replace_global_comparison_scenario(
        comparison.scenario.scenario_id, comparison.revision.revision_id, source="시험"
    )
    processes = list(snapshot.preset.included_processes)
    repository.replace_global_advance_load(
        pd.DataFrame({"생산계획년월": [202512, 202601, 202603], "선행 물량": [0.5, 2.5, 1.0]}),
        source="시험",
    )
    repository.replace_global_execution_capacity(
        pd.DataFrame(
            {
                "생산계획년월": [202602, 202604],
                "공정": [processes[0], processes[1]],
                "증감 확보율": [-30.0, 15.0],
                "비고": ["시험", "시험"],
            }
        ),
        source="시험",
    )
    repository.replace_global_advance_shipment(
        pd.DataFrame({"생산계획년월": [202512, 202601], "선행 입고": [1.2, -0.5]}), source="시험"
    )
    repository.replace_global_past_data(
        {
            "월별": pd.DataFrame(
                {
                    "생산계획년월": [202511, 202512],
                    "Density": [9.0, 9.5],
                    "Wafer Total": [120_000.0, 121_000.0],
                }
            ),
            "계획": pd.DataFrame(
                {
                    "생산계획년월": [202511, 202512],
                    "제품정보": ["DEMO PRODUCT A", "DEMO PRODUCT A"],
                    "Stack": ["8H", "8H"],
                    "Customer": ["DEMO_CUSTOMER_A", "DEMO_CUSTOMER_A"],
                    "생산수량": [110.0, 115.0],
                }
            ),
            "확보율": pd.DataFrame(
                {
                    "생산계획년월": [202511, 202512, 202512],
                    "공정": [processes[0], processes[0], processes[2]],
                    "확보율": [1.05, 0.98, 1.2],
                }
            ),
        },
        source="시험",
    )
    repository.replace_global_key_process_presets(
        [
            (PRESETS[0], [processes[0], processes[2]]),
            (PRESETS[1], [processes[1]]),
            (PRESETS[2], ["DEMO_NOT_ON_THIS_SCREEN"]),
        ],
        source="시험",
    )


@pytest.fixture(scope="module")
def database(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("figure_equivalence") / "scenario.duckdb"
    _prepare_database(path)
    return path


def _open(database_path: Path, state: dict[str, Any] | None = None) -> AppTest:
    """새 세션. 첫 회차 뒤에 조회기간을 과거 구간까지 넓힌다(첫 회차는 프리셋이 덮는다)."""
    app = AppTest.from_string(_script(database_path), default_timeout=300)
    app.run()
    _assert_clean(app)
    app.session_state["production_month_range_v2"] = ("2025-11", "2026-12")
    app.session_state["dashboard_show_performance"] = True
    for key, value in (state or {}).items():
        app.session_state[key] = value
    return app


def _assert_clean(app: AppTest) -> None:
    assert not list(app.exception), [element.message for element in app.exception]
    assert not list(app.error), [element.value for element in app.error]


def _plotly_spec(value: Any) -> Any:
    """Plotly JSON 을 같음을 잴 모양으로. 빈 dict 칸은 지운다.

    공용 칸 복원(`to_dict()` → `go.Figure(..., _validate=False)`)은 `title: {}` 같은 빈 칸을 떨구고
    칸 차례도 다르다. Plotly 에게 빈 칸과 없는 칸은 같은 그림이라 그 차이만 걷어 낸다 — 값이 든
    칸은 하나도 건드리지 않는다.
    """
    if isinstance(value, dict):
        pruned = {key: _plotly_spec(item) for key, item in value.items()}
        return {key: item for key, item in pruned.items() if item != {}}
    if isinstance(value, list):
        return [_plotly_spec(item) for item in value]
    return value


def _drawn(app: AppTest, *, fresh: bool) -> dict[str, Any]:
    app.session_state[FRESH_KEY] = fresh
    app.run()
    _assert_clean(app)
    app.session_state[FRESH_KEY] = False
    return {
        key: _plotly_spec(json.loads(spec))
        for key, spec in app.session_state["spy_figures"].items()
    }


def _rebuilt(app: AppTest) -> set[str]:
    """성능 진단이 적은 「새로 만든 묶음」. 다 맞았으면 빈 집합이다."""
    for element in app.caption:
        if element.value.startswith("새로 만든 묶음: "):
            return set(element.value.removeprefix("새로 만든 묶음: ").split(" · "))
    return set()


def _assert_same_as_fresh(app: AppTest, label: str) -> tuple[dict[str, Any], set[str]]:
    cached = _drawn(app, fresh=False)
    rebuilt = _rebuilt(app)
    fresh = _drawn(app, fresh=True)
    assert set(cached) == set(fresh), label
    different = sorted(key for key in cached if cached[key] != fresh[key])
    assert not different, f"{label}: 캐시를 거친 그림이 새로 만든 그림과 다르다 — {different}"
    return cached, rebuilt


def _state(app: AppTest) -> dict[str, Any]:
    keys = (*TOGGLES, PRODUCT_SHARE_BASIS_KEY, PRESET_KEY, THEME_KEY)
    return {key: app.session_state[key] for key in keys if key in app.session_state}


def _flip(app: AppTest, dimension: str, rng: random.Random) -> None:
    if dimension in TOGGLES:
        app.session_state[dimension] = not bool(app.session_state[dimension])
    elif dimension == PRODUCT_SHARE_BASIS_KEY:
        current = app.session_state[PRODUCT_SHARE_BASIS_KEY]
        app.session_state[PRODUCT_SHARE_BASIS_KEY] = "PKG" if current == "Wafer" else "Wafer"
    elif dimension == PRESET_KEY:
        current = app.session_state[PRESET_KEY]
        app.session_state[PRESET_KEY] = rng.choice([name for name in PRESETS if name != current])
    else:
        dark = app.session_state[THEME_KEY] == "dark"
        app.session_state[THEME_KEY] = "light" if dark else "dark"


DIMENSIONS = (*TOGGLES, PRODUCT_SHARE_BASIS_KEY, PRESET_KEY, THEME_KEY)


def test_the_conditions_really_change_the_figures(database: Path) -> None:
    """시험 데이터가 맹물이면 아래 동등성은 아무것도 보지 못한다. 조건마다 그림이 바뀌는지 본다."""
    app = _open(database, {THEME_KEY: "light"})
    base = _drawn(app, fresh=True)
    assert app.session_state[PRESET_KEY] == PRESETS[0]
    for dimension in DIMENSIONS:
        before = _state(app)
        _flip(app, dimension, random.Random(0))
        changed = _drawn(app, fresh=True)
        assert changed != base, dimension
        for key, value in before.items():
            app.session_state[key] = value
    # EDP 를 끄면(기본) 양산이 EDP 뿐인 달이 축에서 빠진다 — 축이 토글을 따라 움직이는 데이터다.
    assert '"26.12"' not in json.dumps(base["key_process_heatmap_months"])
    app.session_state[EDP_TOGGLE_KEY] = True
    with_edp = _drawn(app, fresh=True)
    assert '"26.12"' in json.dumps(with_edp["key_process_heatmap_months"])


@pytest.mark.parametrize("seed", [11, 23, 37])
def test_random_toggle_orders_never_serve_a_stale_bundle(database: Path, seed: int) -> None:
    """무작위 차례로 켜고 끄며, 걸음마다 캐시를 거친 그림 == 캐시 없이 새로 만든 그림."""
    rng = random.Random(seed)
    app = _open(database, {THEME_KEY: "light"})
    _assert_same_as_fresh(app, f"seed {seed} 시작")
    history: list[dict[str, Any]] = []
    partial_hits = 0
    for step in range(22):
        history.append(_state(app))
        if len(history) > 2 and rng.random() < 0.35:
            # 몇 걸음 전 상태로 돌아간다 — 다른 차례로 같은 조합에 닿는다(캐시가 맞는 자리).
            target = history[rng.randrange(len(history) - 1)]
            for key, value in target.items():
                app.session_state[key] = value
            label = f"seed {seed} 걸음 {step}: 되돌림"
        else:
            dimension = rng.choice(DIMENSIONS)
            _flip(app, dimension, rng)
            label = f"seed {seed} 걸음 {step}: {dimension}"
        _, rebuilt = _assert_same_as_fresh(app, label)
        if rebuilt and len(rebuilt) < 4:
            partial_hits += 1
    # 묶음을 가른 보람이 실제로 있었는지 — 일부 묶음만 다시 만든 걸음이 있어야 한다.
    assert partial_hits > 0


def test_a_single_toggle_rebuilds_only_the_bundles_it_reaches(database: Path) -> None:
    """의존 표가 페이지에서도 그대로인지. 켤 때 새로 만드는 묶음과 끌 때 모두 적중을 본다.

    앞 시험들이 같은 공식 리비전으로 공용 칸을 채워 두었으므로 비우고 시작한다 — 남아 있으면
    처음 보는 조합도 공용 칸에서 복원되어 「새로 만든 묶음」이 비어 버린다.
    """
    shared_home_figure_store.clear()
    app = _open(
        database,
        {
            THEME_KEY: "light",
            ADVANCE_TOGGLE_KEY: False,
            COMPARISON_TOGGLE_KEY: False,
            EDP_TOGGLE_KEY: False,
        },
    )
    _assert_same_as_fresh(app, "시작")
    lob = LOB_FIGURES.title
    plan = PLAN_DETAIL_FIGURES.title
    heatmap = KEY_PROCESS_FIGURES.title
    bottleneck = BOTTLENECK_FIGURES.title
    expectations: list[tuple[str, Any, set[str]]] = [
        (ADVANCE_SHIPMENT_TOGGLE_KEY, True, {lob}),
        (PRODUCT_SHARE_BASIS_KEY, "PKG", {lob}),
        (PLAN_DETAIL_CUSTOMER_KEY, True, {plan}),
        (COMPARISON_TOGGLE_KEY, True, {lob, plan}),
        (EXECUTION_TOGGLE_KEY, True, {lob, heatmap, bottleneck}),
        # 선행 B/O 가 꺼져 있으면 EDP 는 히트맵에 닿지 않는다. 다만 이 데이터는 EDP 만 있는 달이
        # 있어 월 축이 바뀌므로 네 묶음이 모두 다시 그려진다 — 축이 키에 있는 까닭이다.
        (EDP_TOGGLE_KEY, True, {lob, plan, heatmap, bottleneck}),
        (ADVANCE_TOGGLE_KEY, True, {lob, heatmap, bottleneck}),
        (PRESET_KEY, PRESETS[1], {heatmap}),
        (THEME_KEY, "dark", {lob, plan, heatmap, bottleneck}),
    ]
    for key, value, expected in expectations:
        before = app.session_state[key]
        app.session_state[key] = value
        _, rebuilt = _assert_same_as_fresh(app, f"{key} → {value}")
        assert rebuilt == expected, key
        # 되돌리면 모두 적중이다.
        app.session_state[key] = before
        _, rebuilt = _assert_same_as_fresh(app, f"{key} → {before}")
        assert rebuilt == set(), key
        app.session_state[key] = value
        _assert_same_as_fresh(app, f"{key} → {value} 다시")


def test_a_new_session_restores_every_bundle_from_the_shared_store(database: Path) -> None:
    """편집 없는 공식 리비전이다. 같은 조건의 새 세션은 공용 칸에서 네 묶음을 복원한다."""
    state: dict[str, Any] = {
        THEME_KEY: "dark",
        ADVANCE_TOGGLE_KEY: True,
        COMPARISON_TOGGLE_KEY: True,
        PLAN_DETAIL_CUSTOMER_KEY: True,
        PRODUCT_SHARE_BASIS_KEY: "PKG",
    }
    first = _open(database, state)
    first_figures, _ = _assert_same_as_fresh(first, "첫 세션")

    second = _open(database, state)
    second_figures, rebuilt = _assert_same_as_fresh(second, "새 세션")

    assert rebuilt == set()
    assert second_figures == first_figures
    assert DUMBBELL_CHART_KEY in second_figures


def test_an_edited_session_does_not_share_its_figures(database: Path) -> None:
    """편집 중인 세션(내용 토큰이 `pristine-` 가 아니다)의 그림은 공용 칸에 넣지 않는다."""
    from capa_simulation.scenario_state import ACTIVE_SCENARIO_KEY

    state: dict[str, Any] = {THEME_KEY: "light", EXECUTION_TOGGLE_KEY: True}
    edited = _open(database, state)
    edited.session_state[ACTIVE_SCENARIO_KEY] = {
        **edited.session_state[ACTIVE_SCENARIO_KEY],
        "content_token": "edited-equivalence",
    }
    _assert_same_as_fresh(edited, "편집 세션")

    other = _open(database, state)
    other.session_state[ACTIVE_SCENARIO_KEY] = {
        **other.session_state[ACTIVE_SCENARIO_KEY],
        "content_token": "edited-equivalence",
    }
    _, rebuilt = _assert_same_as_fresh(other, "다른 세션의 같은 편집 토큰")
    assert rebuilt == {
        LOB_FIGURES.title,
        PLAN_DETAIL_FIGURES.title,
        KEY_PROCESS_FIGURES.title,
        BOTTLENECK_FIGURES.title,
    }
