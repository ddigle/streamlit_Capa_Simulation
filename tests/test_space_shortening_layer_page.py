# Purpose: Space 「필요 단축」 보기의 켜고 끔·계획 키 같음·못 읽음·편집·링크 도착·상세 이동을 본다.

"""명세 10-2 T-P1~T-P12(설비 시나리오 2단계 LY6 기준 — 레이어는 Space 가 그리는 세션 설비 시나리오로
계산).

시나리오 쪽은 `tests/shortening_script.py` 가 모듈 속성을 갈아 끼워 흉내 내고(필요 단축 일정 AppTest
와 같은 흉내), 편집기는 `_EDITOR` 대역이 받은 data 를 적는다(`test_space_color_basis_page.py` 꼴).
계획 키·계획 몸통은 `simulation_cache.get_required_shortening`·`plan_required_shortening` 모듈 속성
자리에서 센다.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
from shortening_script import shortening_script
from streamlit.testing.v1 import AppTest
from test_equipment_pages import PROJECT_ROOT, _page_script
from test_equipment_scenario_repository import _clone

import capa_simulation.components.shortening_source as shortening_source
import capa_simulation.io.reference_cache as reference_cache
import capa_simulation.persistence.equipment_cache as equipment_cache
import capa_simulation.scenario_state as scenario_state
import capa_simulation.services.simulation_cache as simulation_cache
from capa_simulation.components import space_layout_editor, space_shortening_view
from capa_simulation.components.shortening_board import (
    HIGHLIGHT_FROM_SPACE,
    SHORTENING_HIGHLIGHT_KEY,
    ShorteningHighlight,
    highlight_badge,
)
from capa_simulation.components.shortening_source import (
    SHORTENING_LEVEL_KEY,
    SHORTENING_START_KEY,
)
from capa_simulation.components.space_shortening_view import (
    PINNED_NOTE,
    SPACE_SHORT_DIM_KEY,
    SPACE_SHORT_LEVEL_KEY,
    UNMERGED_MESSAGE,
    process_chip_key,
)
from capa_simulation.equipment_scenario_activation import SELECTION_KEY
from capa_simulation.navigation import (
    SPACE_COLOR_BASIS_KEY,
    SPACE_DEFAULT_BASIS,
    SPACE_SHORTENING_BASIS,
    SPACE_STATUS,
)
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.equipment_contract import empty_equipment_baseline
from capa_simulation.services.equipment_samples import (
    sample_downtime_schedule,
    sample_equipment_master,
)
from capa_simulation.services.space_color_basis import (
    COLOR_BASIS_LINE_TYPE,
    COLOR_BASIS_SHORTENING,
)

PAGE = PROJECT_ROOT / "app_pages" / "space_status.py"
SHORTENING_PAGE = PROJECT_ROOT / "app_pages" / "required_shortening.py"
AS_OF_KEY = "space_status_as_of"
PICKED_KEY = "space_status_picked_unit"
EDIT_KEY = "space_layout_edit_mode"
# 계획 칸(캐시 래퍼) — 시험이 모듈 속성을 갈아 끼우기 전의 것을 쥐어 둔다(비우기용).
PLAN_CACHE = simulation_cache.get_required_shortening


@pytest.fixture(autouse=True)
def _fresh_caches() -> Any:
    clear_equipment_repository()
    PLAN_CACHE.clear()
    yield
    clear_equipment_repository()
    PLAN_CACHE.clear()


@pytest.fixture
def editor_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def _stub(**kwargs: Any) -> SimpleNamespace:
        calls.append(kwargs["data"])
        return SimpleNamespace(apply=None)

    monkeypatch.setattr(space_layout_editor, "_EDITOR", _stub)
    return calls


@pytest.fixture
def plan_keys(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    """계획 칸이 받은 키와 계획 몸통 부름 — 모듈 속성 자리에서 센다."""
    seen: dict[str, list[Any]] = {"keys": [], "bodies": []}
    cached = simulation_cache.get_required_shortening
    body = getattr(simulation_cache, "plan_required_shortening")  # noqa: B009 — 모듈 속성 자리

    def keyed(cache_key: Any, *args: Any, **kwargs: Any) -> Any:
        seen["keys"].append(cache_key)
        return cached(cache_key, *args, **kwargs)

    def counted(**kwargs: Any) -> Any:
        seen["bodies"].append(kwargs["today"])
        return body(**kwargs)

    monkeypatch.setattr(simulation_cache, "get_required_shortening", keyed)
    monkeypatch.setattr(simulation_cache, "plan_required_shortening", counted)
    return seen


def _cutoff(repository: DuckDBEquipmentRepository) -> None:
    processes = sorted(set(sample_equipment_master()["공정소분류"]))
    repository.save_process_cutoff(
        pd.DataFrame(
            {
                "공정": processes,
                "Cutoff일수": [10.0] * len(processes),
                "비고": [None] * len(processes),
            }
        )
    )


def _empty_database(tmp_path: Path) -> Path:
    """빈 설비 DB(샘플 fleet 화면) + 샘플 공정 Cut-off."""
    path = tmp_path / "equipment.duckdb"
    repository = DuckDBEquipmentRepository(path)
    repository.initialize()
    _cutoff(repository)
    return path


def _saved_database(tmp_path: Path) -> DuckDBEquipmentRepository:
    """오늘에 맞춘 샘플 fleet 을 저장본으로(공통 r1 · 운영 일정 r1 · 공식 v1) + Cut-off."""
    repository = DuckDBEquipmentRepository(tmp_path / "equipment.duckdb")
    repository.initialize()
    today = date.today()
    repository.save_snapshot(
        empty_equipment_baseline(),
        sample_equipment_master(anchor_date=today),
        sample_downtime_schedule(anchor_date=today),
        note="처음",
    )
    _cutoff(repository)
    return repository


def _app(database: Path, page: Path = PAGE, **options: Any) -> AppTest:
    return AppTest.from_string(shortening_script(database, page, **options), default_timeout=120)


def _ok(app: AppTest) -> AppTest:
    assert not app.exception, [item.message for item in app.exception]
    return app


def _texts(app: AppTest) -> list[str]:
    return [
        str(item.value)
        for kind in ("caption", "info", "warning", "error", "markdown")
        for item in getattr(app, kind)
    ]


def _views(calls: list[dict[str, Any]], scope: str) -> list[dict[str, Any]]:
    return [call for call in calls if call.get("mode") == "view" and call.get("scope") == scope]


def _level(app: AppTest) -> Any:
    return next(
        item for item in app.get("button_group") if getattr(item, "label", None) == "목표 확보율"
    )


def _turn_on(app: AppTest) -> AppTest:
    app.sidebar.radio(key=SPACE_COLOR_BASIS_KEY).set_value(COLOR_BASIS_SHORTENING)
    return _ok(app.run())


def _busiest_floor(fab: dict[str, Any]) -> tuple[str, str]:
    """FAB 블록 셋째 줄에서 단축 대수가 가장 많은 층."""
    best = max(
        (label for label, stats in fab["linkStats"].items() if stats.get("short")),
        key=lambda label: int(
            str(fab["linkStats"][label]["short"]).split("단축 ")[1].split("대")[0]
        ),
    )
    building, floor = best.split()
    return building, floor


# ------------------------------------------------------------------ 선언·D4


def test_the_sidebar_rows_follow_the_colour_basis_value() -> None:
    """D4 권장 B — Space 는 색 기준이 필요 단축일 때만 시나리오·조회기간 줄(보기 값으로 가르는
    `ConditionTabs`). 값 글자는 서비스 상수와 같다."""
    assert SPACE_SHORTENING_BASIS == COLOR_BASIS_SHORTENING
    assert SPACE_DEFAULT_BASIS == COLOR_BASIS_LINE_TYPE
    tabs = SPACE_STATUS.condition_tabs
    assert tabs is not None and tabs.key == SPACE_COLOR_BASIS_KEY
    assert not SPACE_STATUS.reads_common_conditions_on(tabs.active_label({}))
    assert not SPACE_STATUS.reads_common_conditions_on(
        tabs.active_label({SPACE_COLOR_BASIS_KEY: "투자Capa"})
    )
    assert SPACE_STATUS.reads_common_conditions_on(
        tabs.active_label({SPACE_COLOR_BASIS_KEY: COLOR_BASIS_SHORTENING})
    )
    assert SPACE_STATUS.reads_scenario and SPACE_STATUS.reads_period
    assert SPACE_STATUS.reads_equipment_scenario_on(tabs.active_label({}))
    assert SPACE_STATUS.has_cards_on(tabs.active_label({}))


# ------------------------------------------------------------------ T-P1·T-P2 끈 동안


def test_the_off_screen_never_touches_the_simulation_side_and_carries_no_layer_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, editor_calls: list[dict[str, Any]]
) -> None:
    """T-P1·T-P2 — 기본(공정구분)·투자Capa 회차는 시뮬레이션 쪽을 한 번도 부르지 않는다(모듈 속성
    자리에서 센다). payload 에는 `layer`·`dim`·`shortBadges`·`asOfPinned`·`linkStats.short` 가 없고
    팔레트만 `short-*` 칸이 더 든다."""
    calls: list[str] = []

    def counter(name: str) -> Any:
        def _called(*_args: Any, **_kwargs: Any) -> Any:
            calls.append(name)
            raise AssertionError(f"{name} 를 끈 회차에 불렀습니다")

        return _called

    for module, name in (
        (reference_cache, "get_effective_reference_tables"),
        (scenario_state, "ensure_active_scenario"),
        (equipment_cache, "load_shortening_filter_profile"),
        (equipment_cache, "load_process_cutoff"),
        (simulation_cache, "get_required_shortening"),
        (shortening_source, "load_shortening_demand"),
    ):
        monkeypatch.setattr(module, name, counter(name))
    _saved_database(tmp_path)
    app = AppTest.from_string(_page_script(PAGE, tmp_path / "equipment.duckdb"), default_timeout=60)
    _ok(app.run())
    app.sidebar.radio(key=SPACE_COLOR_BASIS_KEY).set_value("투자Capa")
    _ok(app.run())
    app.session_state["space_status_selected_building"] = "C1"
    app.session_state["space_status_selected_floor"] = "1F"
    _ok(app.run())
    assert calls == []
    fab = _views(editor_calls, "fab")[-1]
    floor = _views(editor_calls, "floor")[-1]
    assert all("short" not in stats for stats in fab["linkStats"].values())
    for data in (fab, floor):
        assert "shortBadges" not in data and "asOfPinned" not in data
        assert {"short-s-fill", "short-x-ink", "short-imminent"} <= set(data["palette"])
    assert all("layer" not in item and "dim" not in item for item in floor["items"])


# ------------------------------------------------------------------ T-P3·T-P4 켜기·목표


def test_turning_the_layer_on_paints_buckets_pins_today_and_keeps_the_epoch(
    tmp_path: Path, editor_calls: list[dict[str, Any]], plan_keys: dict[str, list[Any]]
) -> None:
    app = _app(_empty_database(tmp_path))
    # 세션 기준일을 다른 날로 둔다 — 켠 동안은 오늘로 고정이고 세션 칸은 그대로다.
    other_day = date.today() + timedelta(days=40)
    app.session_state[AS_OF_KEY] = other_day
    app.session_state[SHORTENING_LEVEL_KEY] = 1.2
    _ok(app.run())
    fab_off = _views(editor_calls, "fab")[-1]
    assert fab_off["asOf"] == other_day.isoformat()
    _turn_on(app)
    assert app.sidebar.radio(key=SPACE_COLOR_BASIS_KEY).value == COLOR_BASIS_SHORTENING
    assert not [box for box in app.sidebar.checkbox if str(box.key).startswith("space_color_")]
    # 목표는 필요 단축 일정 목표(세션 1.2)로 심기고, 흐리게는 켬이다 — 본문 조작 줄.
    assert _level(app).value == 1.2
    assert app.checkbox(key=SPACE_SHORT_DIM_KEY).value is True
    fab = _views(editor_calls, "fab")[-1]
    assert fab["epoch"] == fab_off["epoch"]
    assert fab["asOf"] == date.today().isoformat()
    assert any(stats.get("short") for stats in fab["linkStats"].values())
    assert app.session_state[AS_OF_KEY] == other_day
    assert any("필요 단축 일정과 같은 계산" in text for text in _texts(app))
    bodies = len(plan_keys["bodies"])
    assert bodies == 1

    building, floor = _busiest_floor(fab)
    app.session_state["space_status_selected_building"] = building
    app.session_state["space_status_selected_floor"] = floor
    _ok(app.run())
    view = _views(editor_calls, "floor")[-1]
    assert view["asOfPinned"] == PINNED_NOTE and view["asOf"] == date.today().isoformat()
    marked = [item for item in view["items"] if item.get("layer")]
    badges = view["shortBadges"]
    assert marked and badges
    assert {item["id"] for item in marked} == {name for badge in badges for name in badge["ids"]}
    assert all(item["fill"] == "" for item in marked)
    assert all(item.get("dim") for item in view["items"] if not item.get("layer"))
    by_id = {item["id"]: item["layer"] for item in marked}
    assert all(by_id[badge["ids"][0]] == badge["bucket"] for badge in badges)
    epoch = view["epoch"]

    # T-P4 목표를 바꿔도 epoch 그대로·계획 몸통 그대로(다섯 목표를 한 번에 세운다).
    _level(app).set_value(1.3)
    _ok(app.run())
    changed = _views(editor_calls, "floor")[-1]
    assert changed["epoch"] == epoch
    assert len(plan_keys["bodies"]) == bodies

    # 흐리게를 끄면 단축 없는 호기의 dim 이 빠진다.
    app.checkbox(key=SPACE_SHORT_DIM_KEY).uncheck()
    _ok(app.run())
    plain = _views(editor_calls, "floor")[-1]
    assert not [item for item in plain["items"] if item.get("dim") and not item.get("layer")]

    # 공정구분으로 되돌리면 보던 날·페이더(고정 줄 없음)로 돌아온다.
    app.sidebar.radio(key=SPACE_COLOR_BASIS_KEY).set_value(COLOR_BASIS_LINE_TYPE)
    _ok(app.run())
    back = _views(editor_calls, "floor")[-1]
    assert back["asOf"] == other_day.isoformat() and "asOfPinned" not in back
    assert "shortBadges" not in back and not [item for item in back["items"] if "layer" in item]
    assert back["epoch"] == epoch


# ------------------------------------------------------------------ T-P5·T-P6 키 같음


def test_both_screens_build_the_same_plan_key_for_the_official_session(
    tmp_path: Path, editor_calls: list[dict[str, Any]], plan_keys: dict[str, list[Any]]
) -> None:
    """T-P5 — 같은 설비 DB·같은 흉내로 필요 단축 일정 → Space(레이어 켬). 두 회차의 계획 키가 같고
    계획 몸통은 한 번이다. 세션 기간 칸을 다르게 심으면 키가 갈린다(달이 키에 든다)."""
    _saved_database(tmp_path)
    database = tmp_path / "equipment.duckdb"
    shortening = _ok(_app(database, SHORTENING_PAGE).run())
    assert shortening.session_state[SHORTENING_START_KEY]
    board_key = plan_keys["keys"][-1]
    space = _app(database)
    _turn_on(_ok(space.run()))
    assert plan_keys["keys"][-1] == board_key
    assert len(plan_keys["bodies"]) == 1
    # 설비 쪽 지문(마스터·비가동·기존보유)과 Cut-off 가 같다 — 두 화면이 같은 세 표를 넘긴다.
    assert plan_keys["keys"][-1][1:5] == board_key[1:5]

    later = _app(database)
    later.session_state[SHORTENING_START_KEY] = board_key[5][1]
    _turn_on(_ok(later.run()))
    assert plan_keys["keys"][-1][5] == board_key[5][1:]
    assert plan_keys["keys"][-1] != board_key


def test_an_assumption_session_shares_the_shortening_key_and_names_its_scenario(
    tmp_path: Path, editor_calls: list[dict[str, Any]], plan_keys: dict[str, list[Any]]
) -> None:
    """T-P6(LY6) — 가정 설비 시나리오 세션에서도 Space 키 = 필요 단축 일정 키(두 화면이 같은 세션
    시나리오를 따른다). 기준 캡션은 그 시나리오(「셋업 실무 · r1 · 가정」)이고 「다를 수 있습니다」
    글은 없다."""
    repository = _saved_database(tmp_path)
    clone = _clone(repository)
    database = tmp_path / "equipment.duckdb"
    selection = {"scenario_id": clone.equipment_scenario_id, "schedule_revision_id": None}
    board = _app(database, SHORTENING_PAGE)
    board.session_state[SELECTION_KEY] = selection
    _ok(board.run())
    board_key = plan_keys["keys"][-1]
    space = _app(database)
    space.session_state[SELECTION_KEY] = selection
    _turn_on(_ok(space.run()))
    assert plan_keys["keys"][-1] == board_key
    texts = _texts(space)
    assert any("설비 시나리오 「셋업 실무 · r1 · 가정」 기준" in text for text in texts), texts
    assert not any("다를 수 있습니다" in text for text in texts)


# ------------------------------------------------------------------ T-P7·T-P11 못 읽음


def test_a_missing_scenario_warns_once_and_keeps_space_as_it_is(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    app = _app(_empty_database(tmp_path), fail_scenario=True)
    _turn_on(_ok(app.run()))
    warnings = [str(item.value) for item in app.warning]
    assert any("필요 단축을 칠하지 못했습니다" in text for text in warnings), warnings
    assert any("도면·배치 편집·다른 색 기준은 그대로" in text for text in warnings)
    fab = _views(editor_calls, "fab")[-1]
    assert all("short" not in stats for stats in fab["linkStats"].values())
    assert app.dataframe, "층 목록 표는 그대로 선다"


def test_an_empty_cutoff_stops_with_the_cutoff_first_line(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    path = tmp_path / "equipment.duckdb"
    DuckDBEquipmentRepository(path).initialize()
    app = _app(path)
    _turn_on(_ok(app.run()))
    assert any("Cut-off 를 먼저" in str(item.value) for item in app.warning)


def test_an_unmerged_session_does_not_call_the_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    """T-P11 — 일정 없이 연 회차는 계획을 부르지 않고 그 까닭 한 줄로 멈춘다."""
    calls: list[str] = []
    monkeypatch.setattr(shortening_source, "load_shortening_demand", lambda: calls.append("demand"))
    empty = (pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    stop = space_shortening_view.load_space_layer(
        saved=empty,
        sample=False,
        show_sample=False,
        has_snapshot=True,
        database_path="unused.duckdb",
        today=date.today(),
        level=1.1,
        unmerged=True,
    )
    assert isinstance(stop, shortening_source.ShorteningStop)
    assert stop.message == UNMERGED_MESSAGE and calls == []


# ------------------------------------------------------------------ T-P8 배치 편집


def test_layout_editing_rests_the_layer_and_shows_the_default_colours(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    _saved_database(tmp_path)
    app = _app(tmp_path / "equipment.duckdb")
    _turn_on(_ok(app.run()))
    building, floor = _busiest_floor(_views(editor_calls, "fab")[-1])
    app.session_state["space_status_selected_building"] = building
    app.session_state["space_status_selected_floor"] = floor
    _ok(app.run())
    assert _views(editor_calls, "floor")[-1].get("shortBadges")
    app.toggle(key=EDIT_KEY).set_value(True)
    _ok(app.run())
    editor = editor_calls[-1]
    assert editor.get("mode") != "view" and "canvasEditable" in editor
    assert "shortBadges" not in editor and "asOfPinned" not in editor
    assert all("layer" not in item for item in editor["items"])
    assert any("배치 편집 중에는 필요 단축 보기를 쉽니다" in text for text in _texts(app))
    # 라디오 값은 그대로다(결정 D7) — 끄면 다시 보인다.
    assert app.sidebar.radio(key=SPACE_COLOR_BASIS_KEY).value == COLOR_BASIS_SHORTENING
    app.toggle(key=EDIT_KEY).set_value(False)
    _ok(app.run())
    assert _views(editor_calls, "floor")[-1].get("shortBadges")


# ------------------------------------------------------------------ T-P9·T-P12 도착·칩


def test_the_link_opens_the_floor_the_layer_the_target_and_the_chip(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    database = _empty_database(tmp_path)
    probe = _app(database)
    _turn_on(_ok(probe.run()))
    building, floor = _busiest_floor(_views(editor_calls, "fab")[-1])
    view_probe = _probe_floor(probe, editor_calls, building, floor)
    master = sample_equipment_master(anchor_date=date.today())
    processes = dict(zip(master["설비명"], master["공정소분류"], strict=True))
    process = str(processes[view_probe["shortBadges"][0]["ids"][0]])

    app = _app(database)
    app.session_state["space_status_selected_building"] = "C5"
    app.session_state["space_status_selected_floor"] = "6F"
    app.session_state[EDIT_KEY] = True
    app.query_params["layer"] = "short"
    app.query_params["floor"] = f"{building}-{floor}"
    app.query_params["proc"] = process
    app.query_params["target"] = "1.2"
    app.query_params["theme"] = "dark"
    _ok(app.run())
    assert app.session_state["space_status_selected_building"] == building
    assert app.session_state["space_status_selected_floor"] == floor
    assert app.session_state[SPACE_COLOR_BASIS_KEY] == COLOR_BASIS_SHORTENING
    assert app.session_state[SPACE_SHORT_LEVEL_KEY] == 1.2
    assert app.session_state[EDIT_KEY] is False
    assert app.session_state[process_chip_key((building, floor))] == process
    assert dict(app.query_params) == {"floor": [f"{building}-{floor}"], "theme": ["dark"]} or dict(
        app.query_params
    ) == {"floor": f"{building}-{floor}", "theme": "dark"}
    view = _views(editor_calls, "floor")[-1]
    # 공정 칩이 고른 공정 밖의 배지는 흐리다(T-P12).
    assert all(
        badge["dim"] == (badge["key"] not in _marks_of(view, process))
        for badge in view["shortBadges"]
    )

    # floor 없는 링크는 세션에 층이 열려 있어도 FAB 전체다.
    fab_link = _app(database)
    fab_link.session_state["space_status_selected_building"] = building
    fab_link.session_state["space_status_selected_floor"] = floor
    fab_link.query_params["layer"] = "short"
    fab_link.query_params["proc"] = "없는 공정"
    _ok(fab_link.run())
    assert "space_status_selected_floor" not in fab_link.session_state
    assert _views(editor_calls, "fab")


def _probe_floor(
    app: AppTest, calls: list[dict[str, Any]], building: str, floor: str
) -> dict[str, Any]:
    app.session_state["space_status_selected_building"] = building
    app.session_state["space_status_selected_floor"] = floor
    _ok(app.run())
    return _views(calls, "floor")[-1]


def _marks_of(view: dict[str, Any], process: str) -> set[str]:
    """그 층 보기 배지 가운데 그 공정 호기의 설비키(샘플 fleet 의 공정소분류로 가른다)."""
    master = sample_equipment_master(anchor_date=date.today())
    processes = dict(zip(master["설비명"], master["공정소분류"], strict=True))
    return {
        badge["key"]
        for badge in view["shortBadges"]
        if any(processes.get(name) == process for name in badge["ids"])
    }


def test_a_process_chip_outside_this_floor_is_cleared_before_the_widget(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    database = _empty_database(tmp_path)
    app = _app(database)
    _turn_on(_ok(app.run()))
    building, floor = _busiest_floor(_views(editor_calls, "fab")[-1])
    app.session_state["space_status_selected_building"] = building
    app.session_state["space_status_selected_floor"] = floor
    app.session_state[process_chip_key((building, floor))] = "이 층에 없는 공정"
    _ok(app.run())
    assert app.session_state[process_chip_key((building, floor))] is None
    assert not [badge for badge in _views(editor_calls, "floor")[-1]["shortBadges"] if badge["dim"]]


# ------------------------------------------------------------------ T-P10 상세 → 필요 단축 일정


def test_the_detail_button_queues_the_shortening_page_with_highlight_and_target(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    database = _empty_database(tmp_path)
    app = _app(database)
    _turn_on(_ok(app.run()))
    building, floor = _busiest_floor(_views(editor_calls, "fab")[-1])
    app.session_state["space_status_selected_building"] = building
    app.session_state["space_status_selected_floor"] = floor
    _ok(app.run())
    badge = _views(editor_calls, "floor")[-1]["shortBadges"][0]
    app.session_state[PICKED_KEY] = (building, floor, badge["ids"][0])
    _level(app).set_value(1.2)
    _ok(app.run())
    texts = _texts(app)
    assert any(badge["main"] in text for text in texts), texts
    app.button(key=f"space_shortening_open_board_{building}_{floor}").click()
    _ok(app.run())
    highlight = app.session_state[SHORTENING_HIGHLIGHT_KEY]
    assert highlight[1] == HIGHLIGHT_FROM_SPACE
    assert app.session_state[SHORTENING_LEVEL_KEY] == 1.2
    assert "equipment_shortening_process_filter_v1" not in app.session_state
    assert (
        highlight_badge(ShorteningHighlight(highlight[0], highlight[1])) == "Space 도면에서 연 공정"
    )


# ------------------------------------------------------------------ 필요 단축 일정 → Space


def test_the_shortening_cards_offer_the_drawing_link_only_for_saved_equipment(
    tmp_path: Path,
) -> None:
    """카드 「도면에서 보기」 — 저장본 fleet 이면 카드마다 선다(단독 실행에서는 물러선 글), 샘플
    fleet 이면 숨긴다(결정 D13 — 상세 링크와 같이)."""
    fallback = "사이드바 Space 현황에서 색 기준 「필요 단축」"
    saved_dir = tmp_path / "saved"
    saved_dir.mkdir()
    _saved_database(saved_dir)
    saved = _ok(_app(saved_dir / "equipment.duckdb", SHORTENING_PAGE).run())
    assert any(fallback in str(item.value) for item in saved.caption)
    sample_dir = tmp_path / "sample"
    sample_dir.mkdir()
    sample = _ok(_app(_empty_database(sample_dir), SHORTENING_PAGE).run())
    assert not any(fallback in str(item.value) for item in sample.caption)
