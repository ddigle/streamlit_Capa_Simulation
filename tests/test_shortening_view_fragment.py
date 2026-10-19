# Purpose: 필요 단축 일정 머리·본문 프래그먼트 회차의 숫자와 다시 읽기를 앱 전체 회차와 견준다.

"""필요 단축 일정 머리(`진척 비교`·`목표 확보율`)·본문은 프래그먼트다(`_render_view`).

조건 카드(시작 월·끝 월·공정)와 계획은 앱 전체 회차가 먼저 끝내고 인자로 넘긴다. 시험은 AppTest 의
러너가 프래그먼트 저장소를 회차 사이에 쥐고 브라우저처럼 `fragment_id_queue` 로 프래그먼트만 돌리는
대역(`tests/fragment_browser.py`)으로 **진짜 프래그먼트 회차**를 돌린다.

- 같은 숫자: 목표를 바꾼 프래그먼트 회차의 KPI·LOB·공정 카드·CSV 세 벌이, 같은 목표의 앱 전체
  회차와 바이트까지 같다.
- 무효화: 조건 카드는 프래그먼트 밖이라 바꾸면 앱 전체 회차로 다시 계산하고, 프래그먼트 회차는 그
  회차의 공정 선택을 쓴다. 기준선 저장은 앱 전체 회차로 바뀌고, 다른 세션이 지운 기준선·바꾼 공용
  판정 기준은 다음 프래그먼트 회차에 보인다.

시나리오 쪽은 `test_required_shortening_tab` 처럼 모듈 속성을 갈아 끼우되, 프래그먼트 회차는
스크립트 머리를 지나지 않으므로 스크립트 안이 아니라 시험의 `monkeypatch` 로 회차 내내 갈아 끼운다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
import streamlit as st
from fragment_browser import FragmentBrowser, install_fragment_browser
from streamlit.testing.v1 import AppTest
from test_required_shortening_tab import _cards, _database, _months
from test_shortening_progress_tab import _name_input, _save_button, _saved_database, _toasts

import capa_simulation.components.process_labels as process_labels_module
import capa_simulation.components.required_shortening_panel as panel
import capa_simulation.io.reference_cache as reference_cache
import capa_simulation.persistence.cache as persistence_cache
import capa_simulation.scenario_state as scenario_state
import capa_simulation.services.simulation_cache as simulation_cache
import capa_simulation.settings as settings
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.components.required_shortening_panel import (
    SHORTENING_END_KEY,
    SHORTENING_LEVEL_KEY,
    SHORTENING_PROCESS_KEY,
    SHORTENING_START_KEY,
)
from capa_simulation.components.shortening_progress_panel import (
    NO_COMPARISON,
    SHORTENING_COMPARE_KEY,
)
from capa_simulation.persistence.equipment_cache import (
    clear_equipment_repository,
    clear_shortening_baseline_cache,
)
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.equipment_samples import sample_equipment_master
from capa_simulation.services.securement_threshold import SecurementThresholds

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE = PROJECT_ROOT / "app_pages" / "required_shortening.py"
FULL_RUNS_KEY = "test_full_app_runs"
CSV_KEYS = (
    "equipment_shortening_units_csv",
    "equipment_shortening_units_all_levels_csv",
    "equipment_shortening_months_csv",
)


@dataclass
class _World:
    """회차 내내 갈아 끼운 시나리오 쪽. 공용 판정 기준은 시험 중에 바꾼다(다른 세션의 저장)."""

    thresholds: SecurementThresholds = field(
        default_factory=lambda: SecurementThresholds(1.095, 0.995)
    )
    downloads: dict[str, bytes] = field(default_factory=dict)


def _install(monkeypatch: pytest.MonkeyPatch, database_path: Path) -> _World:
    world = _World()
    months = _months()
    processes = sorted(set(sample_equipment_master()["공정소분류"]))
    required = pd.DataFrame(
        [
            {"생산계획년월": month, "공정": process, "STEP": step, "소요대수": 6.0}
            for month in months
            for process in processes
            for step in ("S1", "S2")
        ]
    )
    display_order = pd.DataFrame(
        columns=[
            "페이지 구분",
            "탭 구분",
            "정렬우선순위",
            "분류컬럼",
            "정렬방식",
            "분류값",
            "값표시순서",
            "활성여부",
        ]
    )
    reference_tables = {
        "RQ_DISPLAY_ORDER": display_order,
        "RQ_PKG_PLAN": pd.DataFrame({"생산계획년월": months}),
    }
    active = {"content_token": "shortening-fragment-test", "tables": {}}
    density = pd.DataFrame({"생산계획년월": months, "부하량": [12.5 + i for i in range(6)]})
    wafer = pd.DataFrame({"생산계획년월": months, "Wafer 부하량": [198000.0] * len(months)})
    original_download_button = st.download_button

    def record_download_button(label: str, *args: Any, **kwargs: Any) -> Any:
        world.downloads[str(kwargs.get("key"))] = kwargs["data"]
        return original_download_button(label, *args, **kwargs)

    def scenario_demand(cache_key: Any, **_kwargs: Any) -> tuple[pd.DataFrame, pd.DataFrame]:
        return pd.DataFrame(), required.loc[required["생산계획년월"].between(*cache_key[2:4])]

    monkeypatch.setattr(settings, "EQUIPMENT_DUCKDB_PATH", database_path)
    monkeypatch.setattr(
        settings, "DUCKDB_PATH", database_path.with_name(f"{database_path.stem}_sim.duckdb")
    )
    monkeypatch.setattr(reference_cache, "get_effective_reference_version", lambda: 1)
    monkeypatch.setattr(reference_cache, "get_effective_reference_tables", lambda: reference_tables)
    monkeypatch.setattr(scenario_state, "ensure_active_scenario", lambda _t, _v: active)
    monkeypatch.setattr(simulation_cache, "get_scenario_capacity_and_demand", scenario_demand)
    monkeypatch.setattr(
        simulation_cache,
        "get_home_simulation",
        lambda **_kwargs: (density, None, wafer, None, None, None),
    )
    monkeypatch.setattr(
        persistence_cache,
        "load_global_securement_threshold",
        lambda _path: SimpleNamespace(thresholds=world.thresholds),
    )
    monkeypatch.setattr(
        persistence_cache,
        "load_global_past_data",
        lambda _path: SimpleNamespace(monthly=pd.DataFrame({"생산계획년월": []})),
    )
    monkeypatch.setattr(
        process_labels_module, "get_process_labels", lambda: ProcessLabels(version=1, labels={})
    )
    monkeypatch.setattr(st, "download_button", record_download_button)
    return world


def _script(*, begins_theme: bool = False) -> str:
    """페이지를 그대로 돌리되 **앱 전체 회차**만 센다(프래그먼트 회차는 머리를 안 지난다).

    `begins_theme` 이면 `app.py` 처럼 머리에서 테마를 정한다 — 그것도 앱 전체 회차만 지난다.
    """
    months = _months()
    first, last = months[0], months[-1]
    theme_lines = (
        "from capa_simulation.design import theme\ntheme.begin_run()\n" if begins_theme else ""
    )
    return f"""
from pathlib import Path

import streamlit as st

{theme_lines}st.session_state[{FULL_RUNS_KEY!r}] = st.session_state.get({FULL_RUNS_KEY!r}, 0) + 1
st.session_state["production_month_range_v2"] = ("{first // 100}-{first % 100:02d}",
                                                  "{last // 100}-{last % 100:02d}")
page_source = Path({str(PAGE)!r}).read_text(encoding="utf-8")
exec(compile(page_source, {str(PAGE)!r}, "exec"), {{"__name__": "__main__"}})
"""


def _open(runner: FragmentBrowser) -> AppTest:
    app = AppTest.from_string(_script(), default_timeout=180)
    app.run()
    _assert_clean(app)
    assert runner.started == [[]]
    return app


def _runner(request: pytest.FixtureRequest) -> FragmentBrowser:
    """브라우저 대역(`fragment_browser`) — 이 시험 안에서만 러너를 바꾼다."""
    monkeypatch = request.getfixturevalue("monkeypatch")
    assert isinstance(monkeypatch, pytest.MonkeyPatch)
    return install_fragment_browser(monkeypatch)


def _assert_clean(app: AppTest) -> None:
    assert not list(app.exception), [element.message for element in app.exception]
    assert not list(app.error), [element.value for element in app.error]


def _fragment_of(runner: FragmentBrowser, widget_key: str) -> str:
    """그 키의 위젯을 그린 델타의 프래그먼트 id(앱 전체 회차의 바깥 위젯이면 빈 글자)."""
    for message in runner.messages:
        if message.WhichOneof("type") != "delta":
            continue
        delta = message.delta
        if delta.WhichOneof("type") != "new_element":
            continue
        kind = delta.new_element.WhichOneof("type")
        widget = getattr(delta.new_element, kind) if kind else None
        if str(getattr(widget, "id", "")).endswith(f"-{widget_key}"):
            return str(delta.fragment_id)
    raise AssertionError(f"{widget_key} 위젯을 그린 메시지가 없다")


def _screen(app: AppTest, world: _World) -> tuple[list[str], dict[str, bytes]]:
    """머리·본문이 그린 숫자 — 이 탭의 HTML(KPI·LOB·공정 카드)과 CSV 세 벌의 바이트."""
    html = [str(element.proto.body) for element in app.get("html")]
    return [body for body in html if "shk-" in body], {
        key: world.downloads[key] for key in CSV_KEYS
    }


def _run(app: AppTest, world: _World, step: Callable[[AppTest], Any] | None = None) -> None:
    """한 회차. CSV 기록을 비우고 돌려 그 회차가 내보낸 바이트만 남긴다."""
    world.downloads.clear()
    (step(app) if step is not None else app).run()
    _assert_clean(app)


def _choose_level(app: AppTest, world: _World, level: float) -> None:
    _run(app, world, lambda app: app.selectbox(key=SHORTENING_LEVEL_KEY).set_value(level))


def test_switching_the_target_reruns_only_the_view_with_the_full_run_numbers(
    tmp_path: Path, request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _runner(request)
    world = _install(monkeypatch, _database(tmp_path))
    app = _open(runner)
    view = _fragment_of(runner, SHORTENING_LEVEL_KEY)
    assert view, "목표 확보율은 프래그먼트 안이다"
    assert _fragment_of(runner, SHORTENING_COMPARE_KEY) == view
    # 조건 카드는 프래그먼트 밖이다 — 바꾸면 앱 전체 회차로 계획을 다시 세운다.
    for key in (SHORTENING_START_KEY, SHORTENING_END_KEY, SHORTENING_PROCESS_KEY):
        assert _fragment_of(runner, key) == "", key
    full_runs = app.session_state[FULL_RUNS_KEY]
    default = _screen(app, world)

    for level in (0.9, 1.3, 1.1):
        runner.fragment_queue = [view]
        _choose_level(app, world, level)
        assert runner.started == [[view]], level
        assert app.session_state[FULL_RUNS_KEY] == full_runs
        in_fragment = _screen(app, world)
        assert f"목표 {round(level * 100)}% 기준" in " ".join(in_fragment[0])

        # 같은 목표를 앱 전체 회차로 — 숫자가 바이트까지 같다.
        runner.fragment_queue = []
        _run(app, world)
        assert runner.started == [[]]
        full_runs += 1
        assert app.session_state[FULL_RUNS_KEY] == full_runs
        assert _screen(app, world) == in_fragment, level
    # 처음 목표로 돌아오면 처음 화면 그대로다.
    assert _screen(app, world) == default
    clear_equipment_repository()


def test_a_dark_session_draws_the_view_run_in_dark_colors_like_the_full_run(
    tmp_path: Path, request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """어둡게 쓰는 세션의 프래그먼트 회차도 어두운 색이다 — 같은 목표의 앱 전체 회차와 바이트까지
    같다.

    프래그먼트 회차는 머리의 `theme.begin_run()` 을 지나지 않고, AppTest 도 서버처럼 회차마다 새
    스레드에서 돈다. 테마는 조회 인자로 앱 전체 회차에만 싣는다(프래그먼트 회차에는 인자가 없다) —
    프래그먼트 회차가 어둡게를 알 길은 세션에 남은 값뿐이다.
    """
    from capa_simulation.design import tokens

    runner = _runner(request)
    world = _install(monkeypatch, _database(tmp_path))
    app = AppTest.from_string(_script(begins_theme=True), default_timeout=180)
    app.query_params["theme"] = "dark"
    app.run()
    _assert_clean(app)
    view = _fragment_of(runner, SHORTENING_LEVEL_KEY)
    dark_card = f"background:{tokens.palette_value('dark', 'SURFACE')}"
    assert dark_card in " ".join(_screen(app, world)[0])

    runner.fragment_queue = [view]
    _choose_level(app, world, 1.3)
    assert runner.started == [[view]]
    in_fragment = _screen(app, world)
    assert dark_card in " ".join(in_fragment[0])

    # 브라우저는 주소의 인자를 회차마다 싣는다. 대역의 프래그먼트 회차는 인자 없이 돌아 AppTest 가
    # 쥔 인자도 비우므로, 앱 전체 회차 앞에 다시 싣는다.
    runner.fragment_queue = []
    app.query_params["theme"] = "dark"
    _run(app, world)
    assert runner.started == [[]]
    assert _screen(app, world) == in_fragment
    clear_equipment_repository()


def test_the_card_filter_is_a_full_run_and_the_next_view_run_keeps_it(
    tmp_path: Path, request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _runner(request)
    world = _install(monkeypatch, _database(tmp_path))
    app = _open(runner)
    view = _fragment_of(runner, SHORTENING_LEVEL_KEY)
    before = _cards(app)
    unfiltered = _screen(app, world)
    options = list(app.multiselect(key=SHORTENING_PROCESS_KEY).options)
    chosen = next(option for option in options if [option] != before)

    # 공정은 조건 카드다 — 브라우저는 앱 전체 회차를 청한다. 카드가 그 공정 하나로 바뀐다.
    runner.fragment_queue = []
    _run(app, world, lambda app: app.multiselect(key=SHORTENING_PROCESS_KEY).set_value([chosen]))
    assert runner.started == [[]]
    assert _cards(app) == [chosen]
    assert _screen(app, world) != unfiltered

    # 목표만 바꾼 프래그먼트 회차는 직전 앱 전체 회차의 공정 선택을 쓴다.
    runner.fragment_queue = [view]
    _choose_level(app, world, 0.9)
    assert runner.started == [[view]]
    assert _cards(app) == [chosen]
    clear_equipment_repository()


def test_saving_a_baseline_in_the_view_reruns_the_whole_app_and_lists_it(
    tmp_path: Path, request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _runner(request)
    database_path, _ = _saved_database(tmp_path)
    world = _install(monkeypatch, database_path)
    app = _open(runner)
    view = _fragment_of(runner, SHORTENING_LEVEL_KEY)
    full_runs = app.session_state[FULL_RUNS_KEY]

    # 저장 단추는 프래그먼트 안이다 — 누른 회차는 프래그먼트 회차이고, 쓴 뒤 앱 전체 회차로 바뀐다.
    runner.fragment_queue = [view]
    _run(app, world, lambda app: _save_button(app).click())
    assert runner.started == [[view], []]
    assert app.session_state[FULL_RUNS_KEY] == full_runs + 1
    (stored,) = DuckDBEquipmentRepository(database_path).list_shortening_baselines()
    assert "기준선을 저장했습니다" in _toasts(app)
    # 앱 전체 회차가 그린 `진척 비교` 상자에 방금 저장한 기준선이 선다(선택지 글자는 이름 · 저장일).
    assert len(list(app.selectbox(key=SHORTENING_COMPARE_KEY).options)) == 2

    # 그 기준선을 고르면(프래그먼트 회차) 진척 비교로 바뀐다 — 앱 전체를 다시 돌리지 않는다.
    view = _fragment_of(runner, SHORTENING_LEVEL_KEY)
    runner.fragment_queue = [view]
    _run(
        app,
        world,
        lambda app: app.selectbox(key=SHORTENING_COMPARE_KEY).set_value(stored.baseline_id),
    )
    assert runner.started == [[view]]
    assert app.session_state[FULL_RUNS_KEY] == full_runs + 1
    assert any("진척 비교 요약" in body for body in _screen(app, world)[0])

    # 다른 세션이 그 기준선을 지웠다 — 다음 프래그먼트 회차가 목록을 다시 읽어 「비교 안 함」 이다.
    DuckDBEquipmentRepository(database_path).delete_shortening_baseline(stored.baseline_id)
    clear_shortening_baseline_cache()
    _choose_level(app, world, 0.9)
    assert runner.started == [[view]]
    picker = app.selectbox(key=SHORTENING_COMPARE_KEY)
    assert picker.value == NO_COMPARISON and list(picker.options) == ["비교 안 함"]
    assert not any("진척 비교 요약" in body for body in _screen(app, world)[0])
    clear_equipment_repository()


def test_deleting_this_sessions_baseline_reruns_the_whole_app_and_a_failed_save_does_not(
    tmp_path: Path, request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _runner(request)
    database_path, _ = _saved_database(tmp_path)
    world = _install(monkeypatch, database_path)
    app = _open(runner)
    view = _fragment_of(runner, SHORTENING_LEVEL_KEY)
    runner.fragment_queue = [view]
    _run(app, world, lambda app: _save_button(app).click())
    assert runner.started == [[view], []]
    (stored,) = DuckDBEquipmentRepository(database_path).list_shortening_baselines()

    # 같은 이름으로 다시 저장하면 쓰지 않는다 — 프래그먼트 회차만 돌고 알림이 뜬다.
    view = _fragment_of(runner, SHORTENING_LEVEL_KEY)
    full_runs = app.session_state[FULL_RUNS_KEY]
    runner.fragment_queue = [view]
    _run(app, world, lambda app: _name_input(app).set_value(stored.name))
    runner.fragment_queue = [view]
    _run(app, world, lambda app: _save_button(app).click())
    assert runner.started == [[view]]
    assert app.session_state[FULL_RUNS_KEY] == full_runs
    assert "같은 이름" in _toasts(app)

    # 고르고 확인한 뒤 지우면 쓴 회차라 앱 전체 회차로 바뀐다 — 목록이 「비교 안 함」 하나로 선다.
    runner.fragment_queue = [view]
    _run(
        app,
        world,
        lambda app: app.selectbox(key=SHORTENING_COMPARE_KEY).set_value(stored.baseline_id),
    )
    confirm = next(box for box in app.checkbox if box.label == "정말 지웁니다")
    runner.fragment_queue = [view]
    _run(app, world, lambda app: confirm.check())
    assert runner.started == [[view]]
    runner.fragment_queue = [view]
    _run(app, world, lambda app: app.button(key="equipment_shortening_baseline_delete").click())
    assert runner.started == [[view], []]
    assert app.session_state[FULL_RUNS_KEY] == full_runs + 1
    assert DuckDBEquipmentRepository(database_path).list_shortening_baselines() == ()
    assert "기준선을 지웠습니다" in _toasts(app)
    picker = app.selectbox(key=SHORTENING_COMPARE_KEY)
    assert picker.value == NO_COMPARISON and list(picker.options) == ["비교 안 함"]
    clear_equipment_repository()


def test_the_view_reads_the_shared_thresholds_on_every_run(
    tmp_path: Path, request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """공용 판정 기준(HOME Preference)은 프래그먼트 회차마다 다시 읽는다 — 칩 색이 따라 바뀐다."""
    runner = _runner(request)
    world = _install(monkeypatch, _database(tmp_path))
    app = _open(runner)
    view = _fragment_of(runner, SHORTENING_LEVEL_KEY)
    runner.fragment_queue = [view]
    _choose_level(app, world, 0.9)
    strict = _screen(app, world)

    # 다른 세션이 기준을 낮췄다(확보 0% · 경고 0%) — 모든 칩이 확보 색이 된다.
    world.thresholds = SecurementThresholds(0.0, 0.0)
    _choose_level(app, world, 1.1)
    _choose_level(app, world, 0.9)
    assert runner.started == [[view]]
    relaxed = _screen(app, world)
    assert relaxed[0] != strict[0]
    # CSV 는 판정 기준과 상관없다.
    assert relaxed[1] == strict[1]
    # 같은 기준의 앱 전체 회차와 같다.
    runner.fragment_queue = []
    _run(app, world)
    assert _screen(app, world) == relaxed
    clear_equipment_repository()


def test_the_view_is_the_fragment_and_the_card_plan_is_not() -> None:
    assert getattr(panel._render_view, "__wrapped__", None) is not None
    assert getattr(panel._prepare, "__wrapped__", None) is None
