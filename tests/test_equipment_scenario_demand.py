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
from sheet_reader import has_sheet, sheet_cells, sheet_value
from streamlit.testing.v1 import AppTest
from test_equipment_pages import _open_tab
from test_required_shortening_tab import _database, _months

from capa_simulation.components.availability_gap_panel import RESULT_VIEW_KEY
from capa_simulation.components.required_shortening_panel import SHORTENING_START_KEY
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.services.availability_sheet import ROW_STATIC_AVAILABLE
from capa_simulation.services.month_columns import month_label

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
GAP = "Static 대비 일정"
SHORTENING = "필요단축일정"
VALUE_ERROR = "[시험] RQ_UPEH 의 UPEH 가 0 입니다 — 기준 정보에서 고치세요."
PASSING_ERROR = "[시험] 잠깐 못 읽었습니다."


def _script(database_path: Path) -> str:
    """실제 페이지를 띄운다. 시나리오는 세션 값(`test_*`)으로 고른다.

    - `test_token`: 활성 시나리오의 content_token(미저장 편집·리비전 전환이 바꾼다).
    - `test_reference_version`: 활성 기준정보 버전(없으면 1).
    - `test_demand_months`·`test_demand_scale`: 그 시나리오의 소요대수가 있는 달과 값.
    - `test_failure`: `"value"` 면 기준정보 오류(ValueError), `"once"` 면 한 번만 일시 오류.

    소요대수 대역은 부른 키를 `demand_calls` 에, 키를 낸 표 묶음(그 회차의 활성 시나리오 표·
    기준정보)이 아닌 것을 받은 횟수를 `table_mismatches` 에 적는다.
    """
    simulation_path = database_path.with_name(f"{database_path.stem}_simulation.duckdb")
    months = _months()
    first, last = months[0], months[-1]
    return f"""
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import streamlit as st

import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
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
    "RQ_EQP_OWN": static.rename(columns={{"가용대수": "설비보유"}}),
    "RQ_EQP_LENT": static.rename(columns={{"가용대수": "설비대여평가"}}).assign(설비대여평가=0.0),
}}
active = {{"content_token": state["test_token"], "tables": {{}}}}
density = pd.DataFrame({{"생산계획년월": months, "부하량": [12.5] * len(months)}})
wafer = pd.DataFrame({{"생산계획년월": months, "Wafer 부하량": [198000.0] * len(months)}})


def capacity_and_demand(cache_key, *, _scenario_tables, _reference_tables):
    # 프레임을 푼 회차를 센다 — 캐시가 적중하면 이 함수까지 오지 않는다.
    state.setdefault("demand_calls", []).append(cache_key)
    # 키의 content_token 을 낸 바로 그 표 묶음이어야 한다 — 다른 묶음이면 새 토큰에 옛 표가 묶인다.
    if _scenario_tables is not active["tables"] or _reference_tables is not reference_tables:
        state["table_mismatches"] = state.get("table_mismatches", 0) + 1
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
# 시트 위 가로 스크롤바(Components v2)는 AppTest 에서 등록되지 않는다 — 이 회차 동안만 뺀다.
original_scrollbar = horizontal_scrollbar.render_horizontal_scrollbar
horizontal_scrollbar.render_horizontal_scrollbar = lambda **_kwargs: None
reference_cache.get_effective_reference_version = lambda: state.get("test_reference_version", 1)
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
    horizontal_scrollbar.render_horizontal_scrollbar = original_scrollbar
"""


def _app(tmp_path: Path, **state: object) -> AppTest:
    """페이지를 띄워 둔다(아직 돌리지 않는다). content_token 은 테스트마다 다르다 — 캐시는
    프로세스 전역이라 다른 테스트의 칸을 받지 않게."""
    app = AppTest.from_string(_script(_database(tmp_path)), default_timeout=120)
    app.session_state["test_token"] = f"{tmp_path.name}-a"
    for key, value in state.items():
        app.session_state[key] = value
    return app


def _demand_calls(app: AppTest) -> list[tuple[int, str, int, int]]:
    """소요대수 대역이 받은 시나리오 키(차례대로)."""
    if "demand_calls" not in app.session_state:
        return []
    return [tuple(key) for key in app.session_state["demand_calls"]]


def _calls(app: AppTest) -> int:
    return len(_demand_calls(app))


def _table_mismatches(app: AppTest) -> int:
    """키를 낸 표 묶음이 아닌 것으로 소요대수를 꺼낸 횟수 — 늘 0 이어야 한다."""
    if "table_mismatches" not in app.session_state:
        return 0
    return int(app.session_state["table_mismatches"])


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


def _sheet_static(app: AppTest) -> float | None:
    """분류별 내역 시트의 첫 달 Static 가용(「—」 면 None). 시트가 없으면 실패한다."""
    month = min(month for month, _ in sheet_cells(app))
    return sheet_value(app, month, ROW_STATIC_AVAILABLE)


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
    # 오류 확인은 같은 키라 적중이다. 달 범위와 계획이 함께 빗나가도 한 로더를 나눠 한 번만 푼다.
    assert _calls(app) == opened + 2
    app.run()
    app.run()
    assert _calls(app) == opened + 2
    assert _table_mismatches(app) == 0
    clear_equipment_repository()


def test_a_rerun_where_every_cache_misses_reads_the_demand_once(tmp_path: Path) -> None:
    """오류 확인·달 범위·계획(또는 교차검증)이 한 회차에 함께 빗나가도 소요대수는 한 번만 푼다.

    첫 진입과 조회기간을 바꾼 회차가 그 경우다. 키가 바뀐 회차마다 새로 꺼낸다.
    """
    months = _months()
    app = _app(tmp_path).run()
    before = _calls(app)
    _open_tab(app, SHORTENING)
    assert not app.exception, [element.message for element in app.exception]
    assert _calls(app) == before + 1

    app.session_state["test_period"] = (
        f"{months[1] // 100}-{months[1] % 100:02d}",
        f"{months[-1] // 100}-{months[-1] % 100:02d}",
    )
    app.run()
    assert not app.exception, [element.message for element in app.exception]
    assert _calls(app) == before + 2
    assert _demand_calls(app)[-1][2:] == (months[1], months[-1])

    # Static 대비 일정 교차검증을 처음 여는 회차 — 오류 확인과 교차검증이 함께 빗나간다.
    app.session_state["test_token"] = f"{tmp_path.name}-gap"
    _open_tab(app, GAP)
    _view(app, "확보율 교차검증")
    calls = _calls(app)
    app.session_state["test_token"] = f"{tmp_path.name}-gap-2"
    app.run()
    assert not app.exception, [element.message for element in app.exception]
    assert _calls(app) == calls + 1
    assert _demand_calls(app)[-1][1] == f"{tmp_path.name}-gap-2"
    assert _cross_check(app) is not None
    assert _table_mismatches(app) == 0
    clear_equipment_repository()


def test_a_calculation_error_is_told_in_every_view_with_the_same_words(tmp_path: Path) -> None:
    """기준정보 오류는 프레임이 필요 없는 보기에서도 같은 문구로 알린다.

    **지금 동작을 고정한다** — 계산이 멈춰도 Static 은 이미 읽었으므로 비교에 그대로 쓰면서
    「Static 가용대수를 읽지 못해 설비 일정 기준만 표시합니다」 경고를 낸다(분류별 내역에 Static
    행이 남는다). 문구와 맞지 않지만 출력을 조용히 바꾸지 않으려고 그대로 둔다.
    """
    app = _open_tab(_app(tmp_path, test_failure="value").run(), GAP)
    stopped = f"Static 가용대수를 읽지 못해 설비 일정 기준만 표시합니다 — {VALUE_ERROR}"

    assert stopped in _warnings(app)
    _view(app, "분류별 내역")
    assert stopped in _warnings(app)
    assert has_sheet(app), "분류별 내역 시트가 서야 한다"
    static = _sheet_static(app)
    assert static is not None and static > 0, "이미 읽은 Static 을 시트에 쓴다(지금 동작)"
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
    assert _table_mismatches(app) == 0
    clear_equipment_repository()


def test_a_passing_error_is_not_kept(tmp_path: Path) -> None:
    """일시 오류는 캐시에 굳지 않는다 — 같은 시나리오 키라도 다음 회차에 풀린다(두 탭 모두)."""
    app = _open_tab(_app(tmp_path, test_failure="once").run(), GAP)
    passing = f"Static 가용대수를 읽지 못해 설비 일정 기준만 표시합니다 — {PASSING_ERROR}"
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
    assert _table_mismatches(app) == 0
    clear_equipment_repository()


def test_an_edit_or_another_revision_reads_the_new_demand(tmp_path: Path) -> None:
    """content_token·기준정보 버전·조회기간 어느 것이 바뀌어도 두 탭이 새 소요대수를 쓴다.

    필요단축일정의 고를 달은 새 소요대수의 달 범위로, 교차검증의 소요대수 칸은 새 값으로 바뀐다.
    소요대수를 꺼내는 길은 캐시 키(시나리오 키 = 버전·토큰·조회기간)뿐이라 셋을 하나씩 바꿔 본다.
    """
    months = _months()
    app = _open_tab(_app(tmp_path).run(), SHORTENING)
    assert not app.exception, [element.message for element in app.exception]
    assert app.selectbox(key=SHORTENING_START_KEY).options == [month_label(m) for m in months]

    # 편집으로 앞 두 달과 넷째 달의 소요가 사라졌다 — 새 토큰이다. 고를 달은 소요가 있는 첫 달부터
    # 끝 달까지다(사이의 빈 달도 든다).
    app.session_state["test_token"] = f"{tmp_path.name}-edited"
    app.session_state["test_demand_months"] = [months[2], *months[4:]]
    app.run()
    assert not app.exception, [element.message for element in app.exception]
    assert app.selectbox(key=SHORTENING_START_KEY).options == [month_label(m) for m in months[2:]]

    # 조회기간만 좁히면 그 기간으로 자른 소요대수의 범위다 — 좁힌 첫 달(넷째 달)에는 소요가 없어
    # 다섯째 달부터다. 넓은 기간의 범위를 그대로 쓰면 넷째 달이 남는다.
    last = months[-2]
    app.session_state["test_period"] = (
        f"{months[3] // 100}-{months[3] % 100:02d}",
        f"{last // 100}-{last % 100:02d}",
    )
    app.run()
    assert not app.exception, [element.message for element in app.exception]
    assert app.selectbox(key=SHORTENING_START_KEY).options == [month_label(m) for m in months[4:-1]]
    assert _demand_calls(app)[-1][2:] == (months[3], last)

    # 기준정보 버전만 바뀌어도(토큰은 그대로) 그 버전의 소요대수로 고를 달을 다시 정한다.
    del app.session_state["test_period"]
    app.session_state["test_reference_version"] = 2
    app.session_state["test_demand_months"] = months[1:]
    app.run()
    assert not app.exception, [element.message for element in app.exception]
    assert app.selectbox(key=SHORTENING_START_KEY).options == [month_label(m) for m in months[1:]]
    assert _demand_calls(app)[-1][0] == 2

    # 교차검증의 소요대수 칸 — 두 STEP 의 합이다. 모든 달에 소요가 있는 시나리오로 돌아간다.
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

    # 교차검증도 조회기간을 따른다 — 좁힌 기간 밖의 달은 소요대수가 없다(0).
    app.session_state["test_period"] = (
        f"{months[3] // 100}-{months[3] % 100:02d}",
        f"{last // 100}-{last % 100:02d}",
    )
    app.run()
    assert not app.exception, [element.message for element in app.exception]
    narrowed = _cross_check(app)
    assert narrowed is not None and not narrowed.equals(after)
    assert _demand_calls(app)[-1][2:] == (months[3], last)
    inside = {month_label(m) for m in months[3:-1]}
    in_period = narrowed["생산계획년월"].isin(inside)
    assert in_period.any() and (~in_period).any()
    assert set(narrowed.loc[in_period, "소요대수"]) == {18.0}
    assert set(narrowed.loc[~in_period, "소요대수"]) == {0.0}

    # 교차검증도 기준정보 버전만 바뀐 것을 따른다(토큰·조회기간은 그대로).
    app.session_state["test_reference_version"] = 3
    app.session_state["test_demand_scale"] = 5.0
    app.run()
    assert not app.exception, [element.message for element in app.exception]
    versioned = _cross_check(app)
    assert versioned is not None
    assert set(versioned.loc[versioned["생산계획년월"].isin(inside), "소요대수"]) == {10.0}
    assert _demand_calls(app)[-1][0] == 3
    assert _table_mismatches(app) == 0
    clear_equipment_repository()


def test_a_demand_that_stops_after_a_cached_check_is_told_not_raised(tmp_path: Path) -> None:
    """오류 확인이 적중한 뒤 밀려난 소요대수를 다시 꺼내다 멈춰도 예외가 아니라 그 보기의 경고다.

    대역에는 캐시가 없어 「오류 확인은 적중, 소요대수는 다시 계산」을 그대로 흉내 낸다. 교차검증은
    「확보율을 맞대지 못했습니다」, 필요단축일정은 페이지가 잡은 것과 같은 경고로 멈춘다. 오류는
    캐시에 남지 않아 다음 회차에 풀린다.
    """
    app = _open_tab(_app(tmp_path).run(), GAP)
    assert not app.exception, [element.message for element in app.exception]

    app.session_state["test_failure"] = "once"
    _view(app, "확보율 교차검증")
    assert f"확보율을 맞대지 못했습니다 — {PASSING_ERROR}" in _warnings(app)
    assert _cross_check(app) is None
    app.run()
    assert not app.exception, [element.message for element in app.exception]
    assert _cross_check(app) is not None

    app.session_state["test_failure"] = "value"
    _open_tab(app, SHORTENING)
    assert not app.exception, [element.message for element in app.exception]
    assert (
        "활성 시나리오의 소요대수를 읽지 못해 필요단축일정을 계산하지 않았습니다. "
        f"다른 탭은 그대로 쓸 수 있습니다.\n\n{VALUE_ERROR}"
    ) in _warnings(app)
    app.session_state["test_failure"] = None
    app.run()
    assert not app.exception, [element.message for element in app.exception]
    assert app.selectbox(key=SHORTENING_START_KEY).options
    clear_equipment_repository()
