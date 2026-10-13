# Purpose: 가용설비 현황 두 탭이 소요대수를 쓰는 보기에서만 풀고 오류·편집을 따르는지 검사한다.

"""가용설비 현황의 시나리오 소요대수 읽기(AppTest).

두 탭은 기준정보 오류를 **모든 보기에서** 알리지만, 소요대수 프레임은 쓰는 곳(확보율 교차검증,
필요단축일정의 계획)이 캐시를 빗나갈 때만 푼다. 오류 확인은 `check_scenario_capacity`(성공만
캐시)라 일시 오류가 굳지 않는다. 시나리오 쪽은 모듈 속성을 갈아 끼워 흉내 낸다 — 소요대수를 내는
`simulation_cache.get_scenario_capacity_and_demand` 가 부른 키를 세션에 적어, 어느 회차에 프레임을
풀었는지 센다.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest
from test_equipment_pages import _open_tab
from test_required_shortening_tab import _database, _months

from capa_simulation.components.availability_gap_panel import RESULT_VIEW_KEY
from capa_simulation.components.required_shortening_panel import SHORTENING_START_KEY
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.services.availability_gap import STATIC_ROW
from capa_simulation.services.month_columns import month_label

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
GAP = "Static/Dynamic"
SHORTENING = "필요단축일정"
VALUE_ERROR = "[시험] RQ_UPEH 의 UPEH 가 0 입니다 — 기준 정보에서 고치세요."
PASSING_ERROR = "[시험] 잠깐 못 읽었습니다."


def _script(database_path: Path) -> str:
    """실제 페이지를 띄운다. 시나리오는 세션 값(`test_*`)으로 고른다.

    - `test_token`: 활성 시나리오의 content_token(미저장 편집·리비전 전환이 바꾼다).
    - `test_demand_months`·`test_demand_scale`: 그 시나리오의 소요대수가 있는 달과 값.
    - `test_failure`: `"value"` 면 기준정보 오류(ValueError), `"once"` 면 한 번만 일시 오류.
    """
    simulation_path = database_path.with_name(f"{database_path.stem}_simulation.duckdb")
    months = _months()
    first, last = months[0], months[-1]
    return f"""
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import streamlit as st

import capa_simulation.components.process_labels as process_labels_module
import capa_simulation.io.reference_cache as reference_cache
import capa_simulation.persistence.cache as persistence_cache
import capa_simulation.scenario_state as scenario_state
import capa_simulation.services.simulation_cache as simulation_cache
import capa_simulation.settings as settings
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.services.equipment_samples import sample_equipment_master
from capa_simulation.services.securement_threshold import SecurementThresholds

settings.EQUIPMENT_DUCKDB_PATH = Path({str(database_path)!r})
settings.DUCKDB_PATH = Path({str(simulation_path)!r})
months = {months!r}
state = st.session_state
processes = sorted(set(sample_equipment_master()["공정소분류"]))
demand_months = list(state.get("test_demand_months", months))
scale = float(state.get("test_demand_scale", 6.0))
required = pd.DataFrame(
    [
        {{"생산계획년월": month, "공정": process, "STEP": step, "소요대수": scale}}
        for month in demand_months
        for process in processes
        for step in ("S1", "S2")
    ]
)
static = pd.DataFrame(
    [
        {{"생산계획년월": month, "공정": process, "가용대수": 4.0}}
        for month in months
        for process in processes
    ]
)
display_order = pd.DataFrame(
    columns=["페이지 구분", "탭 구분", "정렬우선순위", "분류컬럼", "정렬방식", "분류값",
             "값표시순서", "활성여부"]
)
reference_tables = {{
    "RQ_DISPLAY_ORDER": display_order,
    "RQ_PKG_PLAN": pd.DataFrame({{"생산계획년월": months}}),
    "RQ_EQP_AVBL": static,
}}
active = {{"content_token": state["test_token"], "tables": {{}}}}
density = pd.DataFrame({{"생산계획년월": months, "부하량": [12.5] * len(months)}})
wafer = pd.DataFrame({{"생산계획년월": months, "Wafer 부하량": [198000.0] * len(months)}})


def capacity_and_demand(cache_key, **_kwargs):
    # 프레임을 푼 회차를 센다 — 캐시가 적중하면 이 함수까지 오지 않는다.
    state.setdefault("demand_calls", []).append(cache_key)
    failure = state.get("test_failure")
    if failure == "value":
        raise ValueError({VALUE_ERROR!r})
    if failure == "once":
        state["test_failure"] = None
        raise RuntimeError({PASSING_ERROR!r})
    _, _, start, end = cache_key
    return (
        pd.DataFrame(),
        required.loc[required["생산계획년월"].between(start, end)].reset_index(drop=True),
    )


originals = (
    reference_cache.get_effective_reference_version,
    reference_cache.get_effective_reference_tables,
    scenario_state.ensure_active_scenario,
    simulation_cache.get_scenario_capacity_and_demand,
    simulation_cache.get_home_simulation,
    persistence_cache.load_global_securement_threshold,
    persistence_cache.load_global_past_data,
)
original_get_process_labels = process_labels_module.get_process_labels
reference_cache.get_effective_reference_version = lambda: 1
reference_cache.get_effective_reference_tables = lambda: reference_tables
scenario_state.ensure_active_scenario = lambda _tables, _version: active
simulation_cache.get_scenario_capacity_and_demand = capacity_and_demand
simulation_cache.get_home_simulation = lambda **_kwargs: (density, None, wafer, None, None, None)
persistence_cache.load_global_securement_threshold = lambda _path: SimpleNamespace(
    thresholds=SecurementThresholds(1.095, 0.995)
)
persistence_cache.load_global_past_data = lambda _path: SimpleNamespace(
    monthly=pd.DataFrame({{"생산계획년월": []}})
)
process_labels_module.get_process_labels = lambda: ProcessLabels(version=1, labels={{}})
try:
    state["production_month_range_v2"] = tuple(
        state.get("test_period", ("{first // 100}-{first % 100:02d}",
                                  "{last // 100}-{last % 100:02d}"))
    )
    page_source = Path({str(PAGE)!r}).read_text(encoding="utf-8")
    exec(compile(page_source, {str(PAGE)!r}, "exec"), {{"__name__": "__main__"}})
finally:
    (
        reference_cache.get_effective_reference_version,
        reference_cache.get_effective_reference_tables,
        scenario_state.ensure_active_scenario,
        simulation_cache.get_scenario_capacity_and_demand,
        simulation_cache.get_home_simulation,
        persistence_cache.load_global_securement_threshold,
        persistence_cache.load_global_past_data,
    ) = originals
    process_labels_module.get_process_labels = original_get_process_labels
"""


def _app(tmp_path: Path, **state: object) -> AppTest:
    """페이지를 띄워 둔다(아직 돌리지 않는다). content_token 은 테스트마다 다르다 — 캐시는
    프로세스 전역이라 다른 테스트의 칸을 받지 않게."""
    app = AppTest.from_string(_script(_database(tmp_path)), default_timeout=120)
    app.session_state["test_token"] = f"{tmp_path.name}-a"
    for key, value in state.items():
        app.session_state[key] = value
    return app


def _calls(app: AppTest) -> int:
    return len(app.session_state["demand_calls"]) if "demand_calls" in app.session_state else 0


def _view(app: AppTest, value: str) -> AppTest:
    app.segmented_control(key=RESULT_VIEW_KEY).set_value(value).run()
    assert not app.exception, [element.message for element in app.exception]
    return app


def _warnings(app: AppTest) -> list[str]:
    return [str(element.value) for element in app.warning]


def _infos(app: AppTest) -> list[str]:
    return [str(element.value) for element in app.info]


def _cross_check(app: AppTest) -> pd.DataFrame | None:
    """확보율 교차검증 표. 숨은 RawData·Preference 편집표도 있어 칸 이름으로 고른다."""
    for element in app.dataframe:
        value = element.value
        if isinstance(value, pd.DataFrame) and "Static확보율" in value.columns:
            return value
    return None


def _matrix(app: AppTest) -> pd.DataFrame | None:
    """분류별 내역의 대수 표(행 이름에 Static 이 있으면 그것)."""
    for element in app.dataframe:
        value = element.value
        if isinstance(value, pd.DataFrame) and STATIC_ROW in list(value.index):
            return value
    return None


def test_views_that_need_no_demand_do_not_read_it(tmp_path: Path) -> None:
    """가용대수 비교·분류별 내역의 rerun 은 소요대수를 풀지 않는다. 교차검증은 빗나간 회차에 한 번,
    필요단축일정은 달 범위·계획이 빗나간 회차에만 푼다 — 같은 조건의 rerun 은 0번이다."""
    app = _open_tab(_app(tmp_path).run(), GAP)
    assert not app.exception, [element.message for element in app.exception]
    opened = _calls(app)
    assert opened == 1  # 오류 확인이 처음 빗나간 회차

    app.run()
    app.run()
    _view(app, "분류별 내역")
    app.run()
    assert _calls(app) == opened

    _view(app, "확보율 교차검증")
    assert _calls(app) == opened + 1
    assert _cross_check(app) is not None, "교차검증 표가 서야 한다"
    app.run()
    assert _calls(app) == opened + 1

    _open_tab(app, SHORTENING)
    assert not app.exception, [element.message for element in app.exception]
    # 달 범위 하나, 계획 하나. 오류 확인은 같은 키라 적중이다.
    assert _calls(app) == opened + 3
    app.run()
    app.run()
    assert _calls(app) == opened + 3
    clear_equipment_repository()


def test_a_calculation_error_is_told_in_every_view_with_the_same_words(tmp_path: Path) -> None:
    """기준정보 오류는 프레임이 필요 없는 보기에서도 같은 문구로 알린다.

    **지금 동작을 고정한다** — 계산이 멈춰도 Static 은 이미 읽었으므로 비교에 그대로 쓰면서
    「Static 가용대수를 읽지 못해 Dynamic 만 표시합니다」 경고를 낸다(분류별 내역에 Static 행이
    남는다). 문구와 맞지 않지만 출력을 조용히 바꾸지 않으려고 그대로 둔다.
    """
    app = _open_tab(_app(tmp_path, test_failure="value").run(), GAP)
    stopped = f"Static 가용대수를 읽지 못해 Dynamic 만 표시합니다 — {VALUE_ERROR}"

    assert stopped in _warnings(app)
    _view(app, "분류별 내역")
    assert stopped in _warnings(app)
    assert _matrix(app) is not None, "Static 을 쓴 분류별 표가 서야 한다(지금 동작)"
    _view(app, "확보율 교차검증")
    assert stopped in _warnings(app)
    assert "소요대수를 읽지 못해 확보율을 맞댈 수 없습니다." in _infos(app)
    assert _cross_check(app) is None

    _open_tab(app, SHORTENING)
    assert not app.exception, [element.message for element in app.exception]
    assert (
        "활성 시나리오의 소요대수를 읽지 못해 필요단축일정을 계산하지 않았습니다. "
        f"다른 탭은 그대로 쓸 수 있습니다.\n\n{VALUE_ERROR}"
    ) in _warnings(app)
    clear_equipment_repository()


def test_a_passing_error_is_not_kept(tmp_path: Path) -> None:
    """일시 오류는 캐시에 굳지 않는다 — 같은 시나리오 키라도 다음 회차에 풀린다(두 탭 모두)."""
    app = _open_tab(_app(tmp_path, test_failure="once").run(), GAP)
    passing = f"Static 가용대수를 읽지 못해 Dynamic 만 표시합니다 — {PASSING_ERROR}"
    assert passing in _warnings(app)
    app.run()
    assert not any(PASSING_ERROR in text for text in _warnings(app))
    _view(app, "확보율 교차검증")
    assert _cross_check(app) is not None, "풀린 뒤에는 교차검증 표가 서야 한다"

    # 필요단축일정도 같다 — 다른 시나리오(새 토큰)에서 처음 한 번만 실패시킨다.
    app.session_state["test_token"] = f"{tmp_path.name}-b"
    app.session_state["test_failure"] = "once"
    _open_tab(app, SHORTENING)
    assert any(PASSING_ERROR in text for text in _warnings(app))
    app.run()
    assert not any(PASSING_ERROR in text for text in _warnings(app))
    assert app.selectbox(key=SHORTENING_START_KEY).options
    clear_equipment_repository()


def test_an_edit_or_another_revision_reads_the_new_demand(tmp_path: Path) -> None:
    """content_token 이 바뀌면(미저장 편집·리비전 전환) 두 탭이 새 소요대수를 쓴다.

    필요단축일정의 고를 달은 새 소요대수의 달 범위로, 교차검증의 소요대수 칸은 새 값으로 바뀐다.
    조회기간을 바꿔도 그 기간의 소요대수로 다시 잰다.
    """
    months = _months()
    app = _open_tab(_app(tmp_path).run(), SHORTENING)
    assert not app.exception, [element.message for element in app.exception]
    assert app.selectbox(key=SHORTENING_START_KEY).options == [month_label(m) for m in months]

    # 편집으로 앞 두 달의 소요가 사라졌다 — 새 토큰이다.
    app.session_state["test_token"] = f"{tmp_path.name}-edited"
    app.session_state["test_demand_months"] = months[2:]
    app.run()
    assert not app.exception, [element.message for element in app.exception]
    assert app.selectbox(key=SHORTENING_START_KEY).options == [month_label(m) for m in months[2:]]

    # 조회기간을 좁히면 그 기간 안의 달만 남는다.
    last = months[-2]
    app.session_state["test_period"] = (
        f"{months[3] // 100}-{months[3] % 100:02d}",
        f"{last // 100}-{last % 100:02d}",
    )
    app.run()
    assert app.selectbox(key=SHORTENING_START_KEY).options == [month_label(m) for m in months[3:-1]]

    # 교차검증의 소요대수 칸 — 두 STEP 의 합이다. 모든 달에 소요가 있는 시나리오로 돌아간다.
    del app.session_state["test_period"]
    del app.session_state["test_demand_months"]
    app.session_state["test_token"] = f"{tmp_path.name}-full"
    _open_tab(app, GAP)
    _view(app, "확보율 교차검증")
    before = _cross_check(app)
    assert before is not None and set(before["소요대수"]) == {12.0}
    app.session_state["test_token"] = f"{tmp_path.name}-scaled"
    app.session_state["test_demand_scale"] = 9.0
    app.run()
    after = _cross_check(app)
    assert after is not None and set(after["소요대수"]) == {18.0}
    assert list(after["공정"]) == list(before["공정"])
    clear_equipment_repository()
