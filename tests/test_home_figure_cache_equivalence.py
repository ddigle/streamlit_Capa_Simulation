# Purpose: HOME 묶음별 Figure 캐시를 거친 그림이 같은 조건에서 새로 만든 그림과 같은지 본다.

"""캐시를 거친 그림 == 캐시 없이 새로 만든 그림.

Figure 캐시는 묶음(LOB·계획 세부수량·주요공정·상세 B/N)마다 제 몫의 조건만 키로 쓴다. 키에서
조건 하나를 잘못 빼면 그 조건을 바꿔도 **옛 그림이 오류 없이** 나온다 — 느린 것보다 훨씬 나쁜
결함이고, 단위 테스트(키 정의만 보는)로는 「그 조건이 정말 그 묶음에 닿지 않는가」를 확인할 수
없다. 여기서는 실제 HOME 페이지를 돌려 확인한다.

- 토글 일곱(선행 B/O·선행 입고·실행 Loss·GAP·상세 계획·EDP 포함·Past Data 포함)·제품별 비중
  단위·주요공정 프리셋·B/N 집계 공정·조회기간·테마를 **무작위 차례로** 바꾸고, 자주 되돌린다
  (되돌릴 때 캐시가 맞는다). 켜고 끄는 차례가 달라도 낡은 묶음이 섞여 나오지 않아야 한다.
- 서로 얽히는 조건 다섯(선행 B/O·EDP·조회기간·실행 Loss·Past Data)은 서른두 조합을 그레이 코드
  차례로 모두 지난다 — 무작위 걸음이 놓치는 드문 모서리를 막는다.
- 걸음마다 같은 세션 상태로 한 번 더 돌리되 캐시를 꺼서(꺼내지도 넣지도 않는다) 새로 만든
  그림과 Plotly JSON 이 한 글자도 다르지 않은지 본다. 덤벨(접힌 비교 상자)도 같다.
- 데이터는 토글이 실제로 그림을 바꾸도록 준비한다: EDP 제품 행(EDP 만 있는 달 하나 — 끄면 월
  축에서 그 달이 빠진다), 비교 시나리오, 선행 B/O·실행 Loss·선행 입고 실적, 과거 구간 두 달,
  주요공정 프리셋 셋(하나는 이 화면에 없는 공정).
- 공용 프로필을 저장하는 조건(판정 기준·공정 표시명·Top5 구간·선행 B/O·실행 Loss·선행 입고·
  주요공정 프리셋 내용·과거 구간)과 비교 리비전 교체는 세션 토글이 아니라 저장이라 따로 본다 —
  저장마다 프로필 캐시를 비우고 「캐시 경유 == 새로 만든 그림」·「새로 만든 묶음 = 의존 표」.
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
from capa_simulation.persistence import cache as persistence_cache
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_preset_state import PROCESS_SELECTION_KEY
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
# 조회기간. 끝을 EDP 만 있는 달(26.12) 앞에서 자르면 EDP 가 월 축을 움직이지 않는다 — 그래야 축
# 변화에 가려지지 않고 「EDP 가 정말 그 묶음에 닿는가」(선행 B/O 를 켠 히트맵, 상세 B/N 의 Wafer
# Capa)를 따로 본다. 그래서 이 범위도 무작위로 바꾸는 조건 하나다.
RANGE_KEY = "production_month_range_v2"
FULL_RANGE = ("2025-11", "2026-12")
SHORT_RANGE = ("2025-11", "2026-11")
# B/N 집계 공정. 페이지가 직전 회차의 공정 목록을 이 키에 남긴다 — 전체와 「첫 공정을 뺀 부분
# 집합」 사이를 오간다. 시드의 공정이 셋뿐이라 하나만 빼도 B/N Top 5·상세 B/N 이 바뀐다.
PROCESS_SEEN_KEY = "dashboard_bottleneck_process_seen"
LOB = LOB_FIGURES.title
PLAN = PLAN_DETAIL_FIGURES.title
HEATMAP = KEY_PROCESS_FIGURES.title
BOTTLENECK = BOTTLENECK_FIGURES.title
ALL_BUNDLES = {LOB, PLAN, HEATMAP, BOTTLENECK}


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
    app.session_state[RANGE_KEY] = FULL_RANGE
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
    keys = (*TOGGLES, PRODUCT_SHARE_BASIS_KEY, PRESET_KEY, THEME_KEY, RANGE_KEY)
    state = {key: app.session_state[key] for key in keys if key in app.session_state}
    state[PROCESS_SELECTION_KEY] = list(app.session_state[PROCESS_SELECTION_KEY])
    return state


def _restore(app: AppTest, state: dict[str, Any]) -> None:
    for key, value in state.items():
        app.session_state[key] = list(value) if isinstance(value, list) else value


def _process_subset(app: AppTest) -> list[str]:
    """B/N 집계 공정의 부분 집합 — 전체에서 첫 공정을 뺀다."""
    return list(app.session_state[PROCESS_SEEN_KEY])[1:]


def _flip(app: AppTest, dimension: str, rng: random.Random) -> None:
    if dimension in TOGGLES:
        app.session_state[dimension] = not bool(app.session_state[dimension])
    elif dimension == PRODUCT_SHARE_BASIS_KEY:
        current = app.session_state[PRODUCT_SHARE_BASIS_KEY]
        app.session_state[PRODUCT_SHARE_BASIS_KEY] = "PKG" if current == "Wafer" else "Wafer"
    elif dimension == PRESET_KEY:
        current = app.session_state[PRESET_KEY]
        app.session_state[PRESET_KEY] = rng.choice([name for name in PRESETS if name != current])
    elif dimension == RANGE_KEY:
        short = tuple(app.session_state[RANGE_KEY]) == SHORT_RANGE
        app.session_state[RANGE_KEY] = FULL_RANGE if short else SHORT_RANGE
    elif dimension == PROCESS_SELECTION_KEY:
        full = list(app.session_state[PROCESS_SEEN_KEY])
        whole = list(app.session_state[PROCESS_SELECTION_KEY]) == full
        app.session_state[PROCESS_SELECTION_KEY] = _process_subset(app) if whole else full
    else:
        dark = app.session_state[THEME_KEY] == "dark"
        app.session_state[THEME_KEY] = "light" if dark else "dark"


DIMENSIONS = (
    *TOGGLES,
    PRODUCT_SHARE_BASIS_KEY,
    PRESET_KEY,
    THEME_KEY,
    RANGE_KEY,
    PROCESS_SELECTION_KEY,
)


def test_the_conditions_really_change_the_figures(database: Path) -> None:
    """시험 데이터가 맹물이면 아래 동등성은 아무것도 보지 못한다. 조건마다 그림이 바뀌는지 본다."""
    app = _open(database, {THEME_KEY: "light"})
    base = _drawn(app, fresh=True)
    assert app.session_state[PRESET_KEY] == PRESETS[0]
    # 조회기간은 EDP 를 끈(기본) 동안에는 그림을 바꾸지 않는다 — 26.12 가 어차피 축에 없다. 아래
    # EDP 단락이 범위의 몫을 본다.
    for dimension in (item for item in DIMENSIONS if item != RANGE_KEY):
        before = _state(app)
        _flip(app, dimension, random.Random(0))
        changed = _drawn(app, fresh=True)
        assert changed != base, dimension
        _restore(app, before)
    # EDP 를 끄면(기본) 양산이 EDP 뿐인 달이 축에서 빠진다 — 축이 토글을 따라 움직이는 데이터다.
    assert '"26.12"' not in json.dumps(base["key_process_heatmap_months"])
    app.session_state[EDP_TOGGLE_KEY] = True
    with_edp = _drawn(app, fresh=True)
    assert '"26.12"' in json.dumps(with_edp["key_process_heatmap_months"])

    # 축을 움직이지 않는 범위에서 EDP 가 닿는 곳. 선행 B/O 를 끄면 히트맵은 그대로, 켜면 바뀐다
    # (변동률이 화면 계획 기준). 상세 B/N 은 Wafer Capa 때문에 늘 바뀐다.
    app.session_state[RANGE_KEY] = SHORT_RANGE
    for advance in (False, True):
        app.session_state[ADVANCE_TOGGLE_KEY] = advance
        app.session_state[EDP_TOGGLE_KEY] = False
        without = _drawn(app, fresh=True)
        app.session_state[EDP_TOGGLE_KEY] = True
        within = _drawn(app, fresh=True)
        assert (
            without["production_lob_months"]["layout"]["xaxis"]["ticktext"]
            == (within["production_lob_months"]["layout"]["xaxis"]["ticktext"])
        )
        assert without["bottleneck_detail_months"] != within["bottleneck_detail_months"]
        heatmap_moved = (
            without["key_process_heatmap_months"] != within["key_process_heatmap_months"]
        )
        assert heatmap_moved is advance, advance


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
            _restore(app, history[rng.randrange(len(history) - 1)])
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


# 서로 얽히는 조건 다섯. 선행 B/O 는 EDP 를 히트맵까지 끌고 가고(변동률), 조회기간은 EDP 가 월 축을
# 움직이는지를 정하며, 실행 Loss·Past Data 는 확보율과 축을 바꾼다. 무작위 걸음은 이 조합의 드문
# 모서리(선행 켬·짧은 범위에서 EDP 를 뒤집는 것)를 놓칠 수 있다 — 실제로 히트맵 키에서 EDP 를 뺀
# 변이를 무작위 세 시드는 놓치고 아래 두 시험은 잡았다. 상세 B/N 키에서 집계 공정을 뺀 변이는 아래
# 「한 조건씩」·「저장」 시험과 시드 37 이 잡는다.
INTERACTING = (
    ADVANCE_TOGGLE_KEY,
    EDP_TOGGLE_KEY,
    RANGE_KEY,
    EXECUTION_TOGGLE_KEY,
    PAST_DATA_TOGGLE_KEY,
)


def test_a_gray_code_sweep_over_the_interacting_conditions(database: Path) -> None:
    """얽히는 조건 다섯의 서른두 조합을 그레이 코드 차례로 모두 지난다 — 걸음마다 하나만 바뀐다.

    한 조건을 뒤집은 바로 다음 회차는 앞 조합의 묶음이 칸에 남아 있으므로, 그 조건을 키에서 잘못
    뺀 묶음이 있으면 앞 그림이 그대로 나와 여기서 걸린다. 서른두 조합 모두에서 그 조건 저마다를
    여러 배경으로 뒤집는다.
    """
    app = _open(
        database,
        {
            THEME_KEY: "light",
            ADVANCE_TOGGLE_KEY: False,
            EDP_TOGGLE_KEY: False,
            EXECUTION_TOGGLE_KEY: False,
            PAST_DATA_TOGGLE_KEY: True,
            COMPARISON_TOGGLE_KEY: True,
        },
    )
    _assert_same_as_fresh(app, "그레이 코드 시작")
    rng = random.Random(0)
    for step in range(1, 2 ** len(INTERACTING)):
        dimension = INTERACTING[(step & -step).bit_length() - 1]
        _flip(app, dimension, rng)
        _assert_same_as_fresh(app, f"그레이 코드 {step}: {dimension}")


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
    lob, plan, heatmap, bottleneck = LOB, PLAN, HEATMAP, BOTTLENECK
    expectations: list[tuple[str, Any, set[str]]] = [
        (ADVANCE_SHIPMENT_TOGGLE_KEY, True, {lob}),
        # B/N 순위를 읽는 두 묶음만. 히트맵은 집계 공정이 아니라 주요공정 목록을 그린다.
        (PROCESS_SELECTION_KEY, _process_subset(app), {lob, bottleneck}),
        (PRODUCT_SHARE_BASIS_KEY, "PKG", {lob}),
        (PLAN_DETAIL_CUSTOMER_KEY, True, {plan}),
        (COMPARISON_TOGGLE_KEY, True, {lob, plan}),
        (EXECUTION_TOGGLE_KEY, True, {lob, heatmap, bottleneck}),
        # 전체 범위에서는 EDP 만 있는 달(26.12)이 EDP 를 따라 축에서 빠지고 들어오므로 네 묶음이
        # 모두 다시 그려진다 — 축이 키에 있는 까닭이다.
        (EDP_TOGGLE_KEY, True, {lob, plan, heatmap, bottleneck}),
        # 그 달 앞에서 자르면 축이 그대로다. 선행 B/O 가 꺼져 있으면 EDP 는 히트맵에 닿지 않는다.
        (RANGE_KEY, SHORT_RANGE, {lob, plan, heatmap, bottleneck}),
        (EDP_TOGGLE_KEY, False, {lob, plan, bottleneck}),
        (ADVANCE_TOGGLE_KEY, True, {lob, heatmap, bottleneck}),
        # 선행 B/O 를 켜면 변동률이 화면 계획 기준이라 EDP 가 히트맵에도 닿는다. 세부수량은 두 걸음
        # 앞(짧은 범위·EDP 켬)에서 같은 조건으로 만들어 두어 적중한다.
        (EDP_TOGGLE_KEY, True, {lob, heatmap, bottleneck}),
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
        # 다음 조건은 이 값 위에 쌓는다. 두 조합 모두 방금 그렸으므로 따로 돌려 보지 않는다.
        app.session_state[key] = value


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


@pytest.fixture(scope="module")
def saving_database(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str, str]:
    """프로필을 저장해 가며 고치는 시험의 DB. 다른 시험과 나누면 저장한 프로필이 그쪽에 샌다.

    두 번째 비교 시나리오를 미리 만들어 둔다 — 목록에 실린 뒤에야 고를 수 있다.
    """
    from capa_simulation.persistence.models import ScenarioCreate

    path = tmp_path_factory.mktemp("figure_equivalence_saves") / "scenario.duckdb"
    _prepare_database(path)
    repository = DuckDBScenarioRepository(path)
    comparison = repository.load_global_comparison_scenario()
    assert comparison.revision_id is not None
    snapshot = repository.load_revision(comparison.revision_id)
    tables = dict(snapshot.tables)
    plan = tables["RQ_PKG_PLAN"].copy()
    plan["생산수량"] = pd.to_numeric(plan["생산수량"]) * 1.3
    tables["RQ_PKG_PLAN"] = plan
    other = repository.create_scenario(
        ScenarioCreate(
            scenario_name="비교 2",
            source_simulation_code="EQ-COMPARE-2",
            source_simulation_name="동등성 시험",
            source_type="DUCKDB_SCENARIO_CLONE",
            pipeline_version="duckdb-rq-snapshot-v3",
        ),
        tables,
        snapshot.preset,
    )
    return path, str(other.scenario.scenario_id), str(other.revision.revision_id)


def _clear_profile_caches() -> None:
    """공용 프로필 캐시를 모두 비운다. 화면의 저장 단추가 저장 뒤에 하는 일과 같다."""
    for name in dir(persistence_cache):
        if name.startswith("clear_global_") and name.endswith("_cache"):
            getattr(persistence_cache, name)()


def _saved(app: AppTest, label: str) -> set[str]:
    _clear_profile_caches()
    _, rebuilt = _assert_same_as_fresh(app, label)
    return rebuilt


def test_saved_profiles_and_a_new_comparison_revision_rebuild_what_they_reach(
    saving_database: tuple[Path, str, str],
) -> None:
    """세션 토글이 아니라 **저장**으로 바뀌는 조건. 저장마다 캐시 경유 == 새로 만든 그림이고, 새로
    만든 묶음이 의존 표와 같다. 선행 B/O·실행·선행 입고는 켠 채로 저장한다 — 꺼져 있으면 version 이
    0 으로 접혀 아무것도 다시 그리지 않아야 한다(마지막 단락).
    """
    from capa_simulation.components.home_preference import (
        COMPARISON_REVISION_KEY,
        COMPARISON_SCENARIO_KEY,
    )

    database, other_scenario, other_revision = saving_database
    shared_home_figure_store.clear()
    repository = DuckDBScenarioRepository(database)
    app = _open(
        database,
        {
            THEME_KEY: "light",
            COMPARISON_TOGGLE_KEY: True,
            ADVANCE_TOGGLE_KEY: True,
            EXECUTION_TOGGLE_KEY: True,
            ADVANCE_SHIPMENT_TOGGLE_KEY: True,
        },
    )
    _assert_same_as_fresh(app, "시작")
    processes = list(app.session_state[PROCESS_SEEN_KEY])

    # B/N 집계 공정 — EDP 를 켜고 끈 두 배경에서.
    for edp in (False, True):
        app.session_state[EDP_TOGGLE_KEY] = edp
        _assert_same_as_fresh(app, f"EDP {edp}")
        app.session_state[PROCESS_SELECTION_KEY] = processes[1:]
        _, rebuilt = _assert_same_as_fresh(app, f"집계 공정 줄임 · EDP {edp}")
        assert rebuilt == {LOB, BOTTLENECK}
        app.session_state[PROCESS_SELECTION_KEY] = processes
        _, rebuilt = _assert_same_as_fresh(app, f"집계 공정 되돌림 · EDP {edp}")
        assert rebuilt == set()

    threshold = repository.load_global_securement_threshold()
    repository.replace_global_securement_threshold(
        1.3,
        1.1,
        pd.DataFrame({"생산계획년월": [202602], "확보 기준": [2.0], "경고 기준": [1.8]}),
        source="시험",
        expected_version=threshold.version,
    )
    assert _saved(app, "판정 기준 저장") == {LOB, HEATMAP, BOTTLENECK}

    repository.replace_global_process_rename(
        pd.DataFrame({"공정": [processes[0], processes[2]], "표시명": ["표시 A", "표시 C"]}),
        source="시험",
    )
    assert _saved(app, "공정 표시명 저장") == {LOB, HEATMAP, BOTTLENECK}

    repository.replace_global_top5_band(0.5, 3.0, source="시험")
    assert _saved(app, "Top5 구간 저장") == {LOB}

    repository.replace_global_advance_load(
        pd.DataFrame({"생산계획년월": [202602, 202604], "선행 물량": [3.0, 1.5]}), source="시험"
    )
    assert _saved(app, "선행 B/O 저장") == {LOB, HEATMAP, BOTTLENECK}

    repository.replace_global_execution_capacity(
        pd.DataFrame(
            {
                "생산계획년월": [202603],
                "공정": [processes[2]],
                "증감 확보율": [-40.0],
                "비고": ["시험"],
            }
        ),
        source="시험",
    )
    assert _saved(app, "실행 Loss 저장") == {LOB, HEATMAP, BOTTLENECK}

    repository.replace_global_advance_shipment(
        pd.DataFrame({"생산계획년월": [202603], "선행 입고": [2.2]}), source="시험"
    )
    assert _saved(app, "선행 입고 저장") == {LOB}

    # 같은 프리셋 이름, 다른 공정.
    repository.replace_global_key_process_presets(
        [
            (PRESETS[0], list(reversed(processes))),
            (PRESETS[1], [processes[1]]),
            (PRESETS[2], ["DEMO_NOT_ON_THIS_SCREEN"]),
        ],
        source="시험",
    )
    assert _saved(app, "주요공정 프리셋 저장") == {HEATMAP}

    past = repository.load_global_past_data()
    monthly = past.monthly.copy()
    monthly.loc[monthly.index[0], "Density"] = 4.0
    repository.replace_global_past_data(
        {"월별": monthly, "계획": past.plan_detail, "확보율": past.securement}, source="시험"
    )
    assert _saved(app, "과거 구간 저장") == ALL_BUNDLES

    # 비교 리비전 교체 — 계획만 다른 다른 시나리오의 리비전으로. 시나리오 상자로 고른다. 리비전은
    # 그 회차의 Preference 피커가 따라 잡는데 피커는 Figure **뒤에** 서므로, 고른 회차의 그림은 아직
    # 앞 리비전이 그 시나리오 것이 아니라 비교 없이 그려진다(Main 은 그때 숨은 탭이다). 한 회차를
    # 넘긴 뒤에 본다.
    app.selectbox(key=COMPARISON_SCENARIO_KEY).set_value(other_scenario).run()
    _assert_clean(app)
    _, rebuilt = _assert_same_as_fresh(app, "비교 리비전 교체")
    assert app.session_state[COMPARISON_REVISION_KEY] == other_revision
    assert rebuilt == {LOB, PLAN}

    # 켜지 않은 프로필은 version 이 0 으로 접힌다 — 저장해도 다시 그리지 않는다.
    app.session_state[ADVANCE_TOGGLE_KEY] = False
    _assert_same_as_fresh(app, "선행 B/O 끔")
    repository.replace_global_advance_load(
        pd.DataFrame({"생산계획년월": [202602], "선행 물량": [9.0]}), source="시험"
    )
    assert _saved(app, "끈 선행 B/O 저장") == set()
