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
from shortening_script import months_from_today, shortening_script
from streamlit.testing.v1 import AppTest
from test_equipment_pages import PROJECT_ROOT, _page_script
from test_equipment_scenario_repository import _clone, _request, _set

import capa_simulation.components.shortening_source as shortening_source
import capa_simulation.io.reference_cache as reference_cache
import capa_simulation.persistence.equipment_cache as equipment_cache
import capa_simulation.scenario_state as scenario_state
import capa_simulation.services.simulation_cache as simulation_cache
from capa_simulation.components import space_layout_editor, space_shortening_view
from capa_simulation.components.sample_data import SAMPLE_TOGGLE_KEY
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


def _rest_notes(app: AppTest) -> int:
    """「배치 편집 중에는 필요 단축 보기를 쉽니다」 줄의 수(결정 D7 — 한 화면에 한 줄)."""
    return sum("배치 편집 중에는 필요 단축 보기를 쉽니다" in text for text in _texts(app))


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
    # 복제만 하면 일정이 공식과 같아 공식 스냅샷으로 계산해도 키가 같다(리뷰 — 그러면 이 시험이 LY6
    # 를 지키지 못한다). 가정 시나리오의 Qual 일정 하나를 옮겨 저장해 공식 키와 갈라 둔다.
    common = repository.latest_revision_id()
    assert common is not None and clone.latest_schedule_revision_id is not None
    session = repository.load_merged_snapshot(common, clone.latest_schedule_revision_id)
    qualified = session.equipment.loc[session.equipment["Qual일정"].notna()]
    name = str(qualified["설비명"].iloc[0])
    moved = pd.Timestamp(qualified["Qual일정"].iloc[0]) + pd.Timedelta(days=9)
    repository.save_equipment(
        _request(
            session,
            clone.equipment_scenario_id,
            equipment=_set(session.equipment, name, "Qual일정", moved),
        )
    )
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
    assert any("설비 시나리오 「셋업 실무 · r2 · 가정」 기준" in text for text in texts), texts
    assert not any("다를 수 있습니다" in text for text in texts)
    # 공식 설비 시나리오 세션의 Space 키와는 다르다 — 설비 마스터 지문이 갈린다(가정 일정으로
    # 계산한다).
    official = _app(database)
    _turn_on(_ok(official.run()))
    official_key = plan_keys["keys"][-1]
    assert official_key != board_key
    assert official_key[1] != board_key[1]


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
    # 층 상세 — 배지 없이 기본 회색, 기준일은 켠 동안 오늘 고정(페이더가 움직이지 않게 고정 줄).
    app.session_state["space_status_selected_building"] = "C1"
    app.session_state["space_status_selected_floor"] = "1F"
    _ok(app.run())
    view = _views(editor_calls, "floor")[-1]
    assert "shortBadges" not in view and view.get("asOfPinned") == PINNED_NOTE
    assert not [item for item in view["items"] if "layer" in item]


def _legend(app: AppTest) -> str:
    """층 상세 머리 줄 범례(끝에 「기준 YYYY-MM-DD」)."""
    found = [str(item.value) for item in app.markdown if "기준 20" in str(item.value)]
    assert len(found) == 1, found
    return found[0]


def test_a_stopped_layer_legend_shows_no_fill_swatches_the_drawing_does_not_paint(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """R5·D12 — 켠 동안 계획을 못 읽은 회차는 고정 줄이 실려 뷰어가 모든 호기의 지연·보관 면을 끈다.
    범례도 채우기 칸(그 밖·지연·보관)을 싣지 않고 테·덧표시만이다 — 도면에 없는 빨강·검정 견본을
    세우지 않는다(리뷰: C1 1F 「지연 1대」). 공정구분이면 그 칸이 그대로 선다(대조)."""
    app = _app(_empty_database(tmp_path), fail_scenario=True)
    _ok(app.run())
    delayed_floors = []
    for building, floor in (("C1", "1F"), ("C1", "2F"), ("C2", "2F"), ("C2", "3F"), ("C3", "1F")):
        app.session_state[SPACE_COLOR_BASIS_KEY] = COLOR_BASIS_LINE_TYPE
        app.session_state["space_status_selected_building"] = building
        app.session_state["space_status_selected_floor"] = floor
        _ok(app.run())
        if any(f"{label} " in _legend(app) for label in ("지연", "보관")):
            delayed_floors.append((building, floor))
        app.session_state[SPACE_COLOR_BASIS_KEY] = COLOR_BASIS_SHORTENING
        _ok(app.run())
        assert _views(editor_calls, "floor")[-1].get("asOfPinned") == PINNED_NOTE
        legend = _legend(app)
        for label in ("그 밖", "지연", "보관"):
            assert f"{label} " not in legend, (building, floor, legend)
    assert delayed_floors, "대조 — 합성 fleet 에 지연·보관 호기가 있는 층이 있어야 뜻이 있다"


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
    # 쉬는 까닭은 편집기 위 한 줄뿐이다 — 본문 조작 줄이 같은 글을 거듭 적지 않는다(E2E).
    assert _rest_notes(app) == 1, _texts(app)
    # 라디오 값은 그대로다(결정 D7) — 끄면 다시 보인다.
    assert app.sidebar.radio(key=SPACE_COLOR_BASIS_KEY).value == COLOR_BASIS_SHORTENING
    app.toggle(key=EDIT_KEY).set_value(False)
    _ok(app.run())
    assert _views(editor_calls, "floor")[-1].get("shortBadges")
    assert _rest_notes(app) == 0


def test_fab_layout_editing_rests_the_layer_with_one_note(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """FAB 전체 배치 편집도 보기를 쉰다 — FAB 편집기에는 캡션이 없어 본문 조작 줄이 까닭 한 줄을
    맡는다(층 상세 편집기 캡션과 겹치지 않게 FAB 편집에서만)."""
    _saved_database(tmp_path)
    app = _app(tmp_path / "equipment.duckdb")
    _turn_on(_ok(app.run()))
    assert _rest_notes(app) == 0
    app.toggle(key="space_fab_edit_mode").set_value(True)
    _ok(app.run())
    assert editor_calls[-1].get("scope") == "fab" and editor_calls[-1].get("mode") != "view"
    assert _rest_notes(app) == 1, _texts(app)
    app.toggle(key="space_fab_edit_mode").set_value(False)
    _ok(app.run())
    assert _rest_notes(app) == 0


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


def test_the_contributing_months_read_as_year_month() -> None:
    assert space_shortening_view._months_text("202611, 202612") == "2026-11, 2026-12"
    assert space_shortening_view._months_text("") == ""


# ------------------------------------------------------------------ 리뷰 고침 — 층·도착·표·도움말


def _loose_kinds(app: AppTest) -> list[str]:
    """층 보기 칸 「도면에 자리가 없는 호기」 표의 구분 칸(좌표 없음·추가)."""
    for table in app.dataframe:
        frame = table.value
        if list(frame.columns[:2]) == ["구분", "호기"]:
            return [str(kind) for kind in frame["구분"]]
    return []


def test_an_inactive_floor_detail_keeps_the_view_but_carries_no_virtual_units(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """층 사용 명세 8-2 — 비활성 층 상세에서도 보기는 배너 아래 그대로 선다(그 층에 남은 호기를 열어
    보여 준다). 추가N 은 붙이지 않는다(새 호기를 들일 자리가 아니다). 처음 판은 그 층에서 보기를
    쉬어 페이더·공정구분 색으로 돌아갔다."""
    repository = _saved_database(tmp_path)
    database = tmp_path / "equipment.duckdb"
    app = _app(database)
    _turn_on(_ok(app.run()))
    building, floor = _busiest_floor(_views(editor_calls, "fab")[-1])
    active = _probe_floor(app, editor_calls, building, floor)
    assert active.get("shortBadges")
    assert "추가" in _loose_kinds(app), "대조 — 사용 층이면 이 층 공정의 추가N 이 선다"

    assert repository.save_floor_states(
        {(building, floor): "UNUSED"}, expected_version=0, source="test"
    )
    clear_equipment_repository()
    off = _app(database)
    off.session_state[SPACE_COLOR_BASIS_KEY] = COLOR_BASIS_SHORTENING
    off.session_state["space_status_selected_building"] = building
    off.session_state["space_status_selected_floor"] = floor
    _ok(off.run())
    view = _views(editor_calls, "floor")[-1]
    assert view.get("asOfPinned") == PINNED_NOTE
    assert [badge["key"] for badge in view["shortBadges"]] == [
        badge["key"] for badge in active["shortBadges"]
    ]
    texts = _texts(off)
    assert any("이 층은 비활성" in text for text in texts)
    assert not any("비활성 층에는 필요 단축 보기를 싣지 않습니다" in text for text in texts)
    assert "추가" not in _loose_kinds(off)
    assert any(text.startswith("**:material/event_upcoming: 이 층 ·") for text in texts)


def test_the_floor_view_counts_only_units_drawn_today_like_the_fab_counts(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """켠 동안 기준일은 오늘이다 — 층 보기 칸(공정 칩·추가N)은 오늘 그려지는 행으로 센다. 뷰어
    roster (페이더 범위 합집합)로 세면 지난 12개월 안에 나간 호기의 공정이 그 층 칩·추가N 에 서지만
    FAB 층 대수(오늘 배치 행)에는 없다(리뷰)."""
    repository = DuckDBEquipmentRepository(tmp_path / "equipment.duckdb")
    repository.initialize()
    today = date.today()
    master = sample_equipment_master(anchor_date=today)
    # C1 1F 의 Final Test 호기는 하나다 — 20일 전에 반출을 마쳤다(도면 이탈, 범위 안).
    gone = master["동"].eq("C1") & master["층"].eq("1F") & master["공정소분류"].eq("Final Test")
    assert int(gone.sum()) == 1
    master.loc[gone, "반출/이설일정"] = pd.Timestamp(today - timedelta(days=20))
    repository.save_snapshot(
        empty_equipment_baseline(),
        master,
        sample_downtime_schedule(anchor_date=today),
        note="처음",
    )
    _cutoff(repository)
    app = _app(tmp_path / "equipment.duckdb")
    _turn_on(_ok(app.run()))
    _probe_floor(app, editor_calls, "C1", "1F")
    chips: Any = next(
        item for item in app.get("button_group") if getattr(item, "label", None) == "이 층 공정"
    )
    options = [str(option) for option in chips.options]
    # 칩 글은 「공정 · n대 …」 꼴이라 앞머리로 가른다. 오늘 그려지는 공정만 선다.
    heads = {option.split(" · ")[0] for option in options}
    assert "Final Test" not in heads, options
    assert {"TC Bonding", "Mold"} <= heads, options


def test_the_arrival_filter_note_lives_only_until_the_floor_or_filter_changes(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """T-P9 덧붙임 — 링크 공정이 Space 공정소분류 필터에 걸러졌으면 조작 줄에 알림 한 줄(필터는
    건드리지 않는다). 알림은 도착한 링크에 대한 것이라 그 필터·층이 처음 바뀌면 거두고, 나중에
    사용자가 고른 상관없는 필터에 다시 서지 않는다(리뷰)."""
    database = _empty_database(tmp_path)
    probe = _app(database)
    _turn_on(_ok(probe.run()))
    building, floor = _busiest_floor(_views(editor_calls, "fab")[-1])
    note = "공정소분류 필터에 「Final Test」이(가) 없어"

    app = _app(database)
    app.session_state["space_status_process_filter"] = ["Mold"]
    app.query_params["layer"] = "short"
    app.query_params["floor"] = f"{building}-{floor}"
    app.query_params["proc"] = "Final Test"
    _ok(app.run())
    assert app.session_state["space_status_process_filter"] == ["Mold"]
    assert any(note in text for text in _texts(app)), _texts(app)
    # 같은 층·같은 필터로 한 회차 더(다른 조작) — 그대로 선다.
    _level(app).set_value(1.2)
    _ok(app.run())
    assert any(note in text for text in _texts(app))
    # 필터를 바꾸면 거둔다 — 그 뒤 다른 필터(여전히 Final Test 없음)에도 다시 서지 않는다.
    app.sidebar.multiselect(key="space_status_process_filter").set_value(["Mold", "Burn-In"])
    _ok(app.run())
    assert not any(note in text for text in _texts(app))
    app.sidebar.multiselect(key="space_status_process_filter").set_value(["Underfill"])
    _ok(app.run())
    assert not any(note in text for text in _texts(app))

    # 층을 옮겨도 거둔다.
    moved = _app(database)
    moved.session_state["space_status_process_filter"] = ["Mold"]
    moved.query_params["layer"] = "short"
    moved.query_params["floor"] = f"{building}-{floor}"
    moved.query_params["proc"] = "Final Test"
    _ok(moved.run())
    assert any(note in text for text in _texts(moved))
    other = next(key for key in (("C4", "2F"), ("C1", "2F")) if key != (building, floor))
    moved.session_state["space_status_selected_building"] = other[0]
    moved.session_state["space_status_selected_floor"] = other[1]
    _ok(moved.run())
    assert not any(note in text for text in _texts(moved))
    moved.session_state["space_status_selected_building"] = building
    moved.session_state["space_status_selected_floor"] = floor
    _ok(moved.run())
    assert not any(note in text for text in _texts(moved))


def test_the_floor_list_leaves_the_max_days_blank_on_floors_without_units(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """층 목록 표 「최대 단축(일)」 은 단축 호기가 없는 층에서 비어 있다 — 리터럴 "None" 대신 빈칸
    (`placeholder=""`, 자리 없는 호기 표와 같은 꼴)."""
    app = _app(_empty_database(tmp_path))
    _turn_on(_ok(app.run()))
    table = next(item for item in app.dataframe if "최대 단축(일)" in list(item.value.columns))
    assert table.value["최대 단축(일)"].isna().any()
    assert table.proto.HasField("placeholder") and table.proto.placeholder == ""


def test_both_layout_edit_toggles_say_the_shortening_view_rests_while_editing(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """명세 4-4 — 배치 편집 토글 도움말이 편집 중에는 필요 단축 보기를 쉰다고 켜기 전에
    말한다(FAB·층)."""
    _saved_database(tmp_path)
    app = _app(tmp_path / "equipment.duckdb")
    _turn_on(_ok(app.run()))
    fab_help = str(app.toggle(key="space_fab_edit_mode").help)
    assert "편집하는 동안 그 보기를 쉬고" in fab_help, fab_help
    _probe_floor(app, editor_calls, "C1", "1F")
    floor_help = str(app.toggle(key=EDIT_KEY).help)
    assert "편집하는 동안 그 보기를 쉬고" in floor_help, floor_help


def test_a_screen_without_units_drops_a_left_over_shortening_basis(tmp_path: Path) -> None:
    """호기가 없는 화면(설비 저장본 없음 + 샘플 끔)은 색 기준 라디오를 세우지 않는다 — 세션에 남은
    「필요 단축」 이면 사이드바 시나리오·조회기간 줄을 끌 길이 없다. 페이지가 기본 값으로 적고 회차
    끝에 한 번 더 돌아 줄을 걷는다(리뷰)."""
    app = _app(_empty_database(tmp_path))
    app.session_state[SPACE_COLOR_BASIS_KEY] = COLOR_BASIS_SHORTENING
    app.session_state[SAMPLE_TOGGLE_KEY] = False
    _ok(app.run())
    assert app.session_state[SPACE_COLOR_BASIS_KEY] == COLOR_BASIS_LINE_TYPE
    assert not SPACE_STATUS.reads_common_conditions_on(
        SPACE_STATUS.condition_tabs.active_label(  # type: ignore[union-attr]
            {SPACE_COLOR_BASIS_KEY: app.session_state[SPACE_COLOR_BASIS_KEY]}
        )
    )
    assert not app.get("button_group")
    assert not any("필요 단축을 칠하지 못했습니다" in str(item.value) for item in app.warning)


# ------------------------------------------------------------------ 명세 10-2 빠졌던 시험


def test_without_session_months_both_screens_read_the_shared_profile_months(
    tmp_path: Path, editor_calls: list[dict[str, Any]], plan_keys: dict[str, list[Any]]
) -> None:
    """T-P5 덧붙임 — 공용 조회 조건(0019)의 달을 바꾸고 세션 기간 칸이 없으면 두 화면 모두 그 프로필
    달로 계산한다(같은 심기 규칙 — Space 는 읽기만 한다)."""
    repository = _saved_database(tmp_path)
    database = tmp_path / "equipment.duckdb"
    months = months_from_today()
    assert repository.save_shortening_filter_months(months[2], months[4], source="test")
    clear_equipment_repository()
    board = _ok(_app(database, SHORTENING_PAGE).run())
    board_key = plan_keys["keys"][-1]
    assert board_key[5] == tuple(months[2:5])
    assert board.session_state[SHORTENING_START_KEY] == months[2]
    space = _app(database)
    _turn_on(_ok(space.run()))
    assert plan_keys["keys"][-1] == board_key
    assert SHORTENING_START_KEY not in space.session_state


def test_an_unreadable_shared_profile_falls_back_to_the_code_months_on_both_screens(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    editor_calls: list[dict[str, Any]],
    plan_keys: dict[str, list[Any]],
) -> None:
    """명세 10-2 — 공용 조회 조건을 못 읽으면(저장소가 `duckdb.Error`) 멈추지 않고 두 화면 모두 코드
    기본 달로 계속한다(`shortening_filter_profile_or_default` — Space 만 멈추면 두 화면의 달이
    갈린다)."""
    import duckdb

    repository = _saved_database(tmp_path)
    database = tmp_path / "equipment.duckdb"
    months = months_from_today()
    repository.save_shortening_filter_months(months[2], months[4], source="test")
    clear_equipment_repository()

    def broken(_path: str) -> Any:
        raise duckdb.IOException("잠긴 DB 흉내")

    monkeypatch.setattr(equipment_cache, "load_shortening_filter_profile", broken)
    board = _ok(_app(database, SHORTENING_PAGE).run())
    board_key = plan_keys["keys"][-1]
    assert board_key[5][0] == months[0] and board_key[5][-1] == months[-1]
    space = _app(database)
    _turn_on(_ok(space.run()))
    assert plan_keys["keys"][-1] == board_key
    assert not [
        item for item in space.warning if "필요 단축을 칠하지 못했습니다" in str(item.value)
    ]
    assert board.session_state is not None


def test_a_period_without_demand_stops_with_the_board_reason(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """T-P7 — 조회기간에 소요대수가 없으면 필요 단축 일정과 같은 까닭 글로 멈춘다(경고 한 줄, Space
    는 그대로)."""
    database = _empty_database(tmp_path)
    past: dict[str, Any] = {"sidebar_first": 202001, "sidebar_last": 202003}
    board = _ok(_app(database, SHORTENING_PAGE, **past).run())
    reasons = [
        str(item.value)
        for kind in ("error", "warning", "info")
        for item in getattr(board, kind)
        if "소요대수 산출 기준이 없습니다" in str(item.value)
    ]
    assert reasons, _texts(board)
    space = _app(database, **past)
    _turn_on(_ok(space.run()))
    warnings = [str(item.value) for item in space.warning]
    assert any(
        "필요 단축을 칠하지 못했습니다" in text and "소요대수 산출 기준이 없습니다" in text
        for text in warnings
    ), warnings
    assert all(
        "short" not in stats for stats in _views(editor_calls, "fab")[-1]["linkStats"].values()
    )


def test_a_failing_plan_stops_with_the_calculation_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, editor_calls: list[dict[str, Any]]
) -> None:
    """T-P7 — 계산이 `ValueError` 로 멈추면 그 까닭을 붙인 한 줄(「필요 단축 일정을 계산하지
    못했습니다 — …」)이고 Space 는 그대로다."""

    def failing(**_kwargs: Any) -> Any:
        raise ValueError("계산 실패 흉내")

    monkeypatch.setattr(simulation_cache, "plan_required_shortening", failing)
    app = _app(_empty_database(tmp_path))
    _turn_on(_ok(app.run()))
    warnings = [str(item.value) for item in app.warning]
    assert any(
        "필요 단축 일정을 계산하지 못했습니다 — 계산 실패 흉내" in text for text in warnings
    ), warnings
    assert app.dataframe, "층 목록 표는 그대로 선다"


def test_the_off_payload_carries_no_residue_of_a_layer_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, editor_calls: list[dict[str, Any]]
) -> None:
    """T-P2 — 끈 동안 payload 는 레이어 코드를 지나지 않는다. 필요 단축 전용 함수(표시 얹기·층
    칸·FAB 대수·범례·조작 줄)를 부르면 실패하게 갈아 끼운 끈 회차가 그대로 돌고, 켰다 끈 뒤의 FAB·층
    data 는 처음 끈 회차와 같다(팔레트 `short-*` 칸은 늘 같은 값이라 함께 같다)."""
    import capa_simulation.components.space_layout as space_layout
    import capa_simulation.services.space_shortening_layer as space_shortening_layer

    _saved_database(tmp_path)
    database = tmp_path / "equipment.duckdb"
    app = _app(database)
    _ok(app.run())
    fab_before = _views(editor_calls, "fab")[-1]
    floor_before = _probe_floor(app, editor_calls, "C1", "1F")
    # FAB 으로 돌아간다(세션 층과 주소 `floor` 를 함께 걷는다 — 주소가 남으면 그 층이 다시 열린다).
    del app.session_state["space_status_selected_building"]
    del app.session_state["space_status_selected_floor"]
    app.query_params.clear()
    fab_rounds = len(_views(editor_calls, "fab"))
    _turn_on(_ok(app.run()))
    app.sidebar.radio(key=SPACE_COLOR_BASIS_KEY).set_value(COLOR_BASIS_LINE_TYPE)
    _ok(app.run())
    rounds = _views(editor_calls, "fab")[fab_rounds:]
    assert len(rounds) >= 2
    assert any(
        any(stats.get("short") for stats in view["linkStats"].values()) for view in rounds[:-1]
    ), "대조 — 켠 회차는 단축 줄이 실린다"
    assert rounds[-1] == fab_before
    assert _probe_floor(app, editor_calls, "C1", "1F") == floor_before

    def refuse(name: str) -> Any:
        def _called(*_args: Any, **_kwargs: Any) -> Any:
            raise AssertionError(f"{name} 를 끈 회차에 불렀습니다")

        return _called

    for module, name in (
        (space_layout, "apply_layer_looks"),
        (space_layout, "shortening_legend_markup"),
        (space_shortening_layer, "floor_layer"),
        (space_shortening_layer, "fab_floor_counts"),
        (space_shortening_layer, "fab_layer_summary"),
        (space_shortening_view, "load_space_layer"),
        (space_shortening_view, "render_layer_controls"),
        (space_shortening_view, "render_floor_layer_panel"),
        (space_shortening_view, "render_fab_layer_summary"),
        (space_shortening_view, "layer_table_columns"),
    ):
        monkeypatch.setattr(module, name, refuse(name))
    fresh = _app(database)
    fab_rounds = len(_views(editor_calls, "fab"))
    _ok(fresh.run())
    assert len(_views(editor_calls, "fab")) > fab_rounds
    assert _views(editor_calls, "fab")[-1] == fab_before
    assert _probe_floor(fresh, editor_calls, "C1", "1F") == floor_before


def _floor_panel(chips: dict[str, str], focus: str | None, level: float) -> None:
    """층 보기 칸만 그린다 — 이 층(C1 2F)에 칩 둘, 칩을 고르면 `floor_layer` 가 그 공정으로 좁힌 빈
    재료를 넘긴다(고른 공정에 단축 호기가 없는 목표)."""
    from types import SimpleNamespace

    import streamlit as st

    from capa_simulation.components.space_shortening_view import (
        process_chip_key,
        render_floor_layer_panel,
    )
    from capa_simulation.services.space_shortening_layer import FloorLayer

    st.session_state.setdefault(process_chip_key(("C1", "2F")), focus)
    space_layer: Any = SimpleNamespace(layer=SimpleNamespace(level=level))
    render_floor_layer_panel(
        ("C1", "2F"),
        FloorLayer(chips=chips, focus=focus),
        space_layer,
        picked_unit=None,
        picked_rows=None,
        key_of={},
        picked_key="space_status_picked_unit",
    )


@pytest.mark.parametrize(
    ("focus", "head", "empty"),
    [
        (
            "Laser Grooving",
            "이 층 · Laser Grooving · 목표 90% · 단축 0대",
            "이 층 Laser Grooving 공정에는 목표 90% 에서 단축할 호기가 없습니다",
        ),
        (None, "이 층 · 목표 90% · 단축 0대", "이 층에는 목표 90% 에서 단축할 호기가 없습니다."),
    ],
    ids=["칩 고름", "칩 없음"],
)
def test_the_floor_panel_names_the_chosen_process_when_it_has_nothing_to_shorten(
    focus: str | None, head: str, empty: str
) -> None:
    """칩을 고르면 머리 줄 수와 빈 글은 그 공정만 센다 — 같은 칸의 다른 칩·도면 배지가 이 층 단축
    호기를 보이는데 「이 층에는 … 없습니다」 라고 하지 않게 고른 공정을 말한다(2026-10-26 E2E)."""
    chips = {"Die Attach": "Die Attach · 2대 최대 −81일", "Laser Grooving": "Laser Grooving"}
    app = AppTest.from_function(_floor_panel, args=(chips, focus, 0.9), default_timeout=30).run()
    assert not app.exception, [item.message for item in app.exception]

    texts = [str(item.value) for item in app.markdown]
    assert f"**:material/event_upcoming: {head}**" in texts
    captions = [str(item.value) for item in app.caption]
    assert any(caption.startswith(empty) for caption in captions), captions
