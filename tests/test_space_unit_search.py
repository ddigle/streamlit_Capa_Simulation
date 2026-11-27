# Purpose: Space FAB 「설비 찾기」 의 후보 · 층 열기 · 도면 맞춤 신호 · 도면 밖 알림을 검사한다.

"""2026-11-27 사용자 요청 — Space 현황 FAB 전체 첫 화면에 설비명 찾기 칸을 두고, 친 글로 비슷한
설비명을 띄워 하나를 고르면 그 설비가 있는 자리로 옮긴다.

- 칸은 사이드바 「Space 도면」 상자의 자리 줄 바로 밑 고르기 하나이고 FAB 전체에서만 선다. 후보는
  FAB 블록 · 층 목록 대수와 같은 표에서 층이 정해진 설비명이다(층 미정은 열 층이 없어 뺀다).
- 고르면 콜백이 그 층을 연다(층 사용 초안 규칙은 바로 가기와 같다). **열었을 때만** 도면에 선
  호기면 맞춤 대상을 두고, 그 층 상세를 처음 그리는 회차가 도면 data `focus` ``{"id", "token"}``
  로 한 번 싣는다 — 뒤 회차 · FAB 에 갔다 같은 층을 블록으로 다시 열기에는 없다. 도면에 서지 않은
  호기(미배치 · 레이아웃 제외 · 기준일에 도면 이탈)면 층을 열고 알림창 한 마디다. 고르기 칸은 늘
  비워 같은 설비를 다시 골라도 움직인다.
- 브라우저는 그 토큰마다 한 번 그 호기를 고르고 둘레가 보이게(`LIST_ROW_ZOOM` 까지) 맞춘다 —
  판정은 `editor.js` 의 `// <search-focus>` 구획을 node 로 떼어 돌리고(node·bun 이 없으면 건너뛰고
  CI 에서는 실패), 거는 자리는 자산 글자로 붙잡는다. 실제 확대는 브라우저로 본다.

AppTest 는 JS 를 못 돌린다 — `_EDITOR` 를 대역으로 바꿔 받은 data 를 적고, 블록 누르기는
`navigate` 를 세션에 넣고 콜백을 부른다(대역은 그리는 자리에서 부르므로 층 상세는 다음 회차에
선다).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from alert_marks import flashed
from streamlit.testing.v1 import AppTest
from test_equipment_availability import _baseline, _downtime
from test_equipment_pages import PROJECT_ROOT, _page_script
from test_space_layout_edit import _master
from test_space_module_group import _node
from test_space_shortening_layer_page import PLAN_CACHE, _empty_database, _turn_on, _views
from test_space_shortening_layer_page import _app as _sample_app
from test_space_sidebar_box import _box, _box_order

from capa_simulation.components import space_floor_list, space_layout_editor
from capa_simulation.components.space_layout import (
    SEARCH_EXCLUDED,
    SEARCH_EXITED,
    SEARCH_PLACED,
    SEARCH_UNPLACED,
    UnitSearchTarget,
    unit_search_targets,
)
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository

PAGE = PROJECT_ROOT / "app_pages" / "space_status.py"
JS = (space_layout_editor._ASSETS / "editor.js").read_text(encoding="utf-8")
SEARCH_KEY = "space_status_unit_search"
SEARCH_DISCARD_KEY = f"{SEARCH_KEY}_discard"
FOCUS_KEY = "space_status_unit_focus"
PICKED_KEY = "space_status_picked_unit"
NAVIGATE_KEY = "test_fake_fab_navigate"
_SEARCH_BLOCK = re.compile(r"// <search-focus>\n(?P<body>.*?)\n\s*// </search-focus>", re.S)


# ---------------------------------------------------------------- 후보(순수 함수)


def _rows(*rows: tuple[str, str | None, str | None]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["설비명", "동", "층"])


def test_the_candidates_keep_floor_bound_names_in_natural_order_and_the_first_place_wins() -> None:
    """후보는 FAB 의 층이 정해진 설비명(앞뒤 공백을 걷음)이고 자연 정렬이다 — 층 미정 · FAB 밖 층은
    열 층이 없어 빠진다. 같은 이름이 여러 표에 있으면 앞 표(도면 → 미배치 → 레이아웃 제외 → 도면
    이탈)가 이긴다."""
    targets = unit_search_targets(
        placed=_rows(("DEMO-EQ-10", "C1", "1F"), (" DEMO-EQ-2 ", "C1", "2F")),
        unplaced=_rows(("DEMO-TRAY", "C2", "1F"), ("DEMO-FLOATING", None, None)),
        excluded=_rows(("DEMO-OFF", "C1", "1F"), ("DEMO-EQ-10", "C2", "2F")),
        exited=_rows(("DEMO-GONE", "C1", "3F"), ("DEMO-NOWHERE", "C9", "1F")),
    )
    assert list(targets) == ["DEMO-EQ-2", "DEMO-EQ-10", "DEMO-GONE", "DEMO-OFF", "DEMO-TRAY"]
    assert targets["DEMO-EQ-10"] == UnitSearchTarget(("C1", "1F"), SEARCH_PLACED)
    assert targets["DEMO-EQ-2"] == UnitSearchTarget(("C1", "2F"), SEARCH_PLACED)
    assert targets["DEMO-TRAY"].place == SEARCH_UNPLACED
    assert targets["DEMO-OFF"].place == SEARCH_EXCLUDED
    assert targets["DEMO-GONE"] == UnitSearchTarget(("C1", "3F"), SEARCH_EXITED)


# ---------------------------------------------------------------- 화면(AppTest)


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """`_EDITOR` 대역 — 받은 data 를 적고, `NAVIGATE_KEY` 가 있으면 FAB 블록을 누른 것처럼
    `on_navigate_change` 를 부른다."""
    recorded: list[dict[str, Any]] = []

    def _stub(**kwargs: Any) -> None:
        import streamlit as st

        data = kwargs["data"]
        recorded.append(data)
        payload = st.session_state.pop(NAVIGATE_KEY, None)
        if payload is not None and data.get("scope") == "fab":
            st.session_state[kwargs["key"]] = {"navigate": {"epoch": data["epoch"], **payload}}
            kwargs["on_navigate_change"]()

    monkeypatch.setattr(space_layout_editor, "_EDITOR", _stub)
    return recorded


def _fleet() -> pd.DataFrame:
    """C1 1F — EQ-01·EQ-02 · Main 설비 MOD-1 모듈 둘 · 좌표 없는 TRAY-01 · 레이아웃표시 N 인 N-01 ·
    기준일 전에 반출을 마친 OUT-01, C1 2F — UP-01, 동 · 층 미정 — FLOAT-01."""
    module = {"Main 설비": "MOD-1", "Xsize": 6, "Ysize": 4}
    return _master(
        {**module, "설비명": "MOD-1A", "X좌표": 60.0, "Y좌표": 10.0},
        {**module, "설비명": "MOD-1B", "X좌표": 66.0, "Y좌표": 10.0},
        {"설비명": "UP-01", "층": "2F"},
        {"설비명": "TRAY-01", "X좌표": None, "Y좌표": None},
        {"설비명": "N-01", "레이아웃표시": "N", "X좌표": 70.0},
        {
            "설비명": "OUT-01",
            "X좌표": 84.0,
            "정지일정": "2026-09-20",
            "반출/이설일정": "2026-10-01",
        },
        {"설비명": "FLOAT-01", "동": None, "층": None, "X좌표": None, "Y좌표": None},
    )


def _open(
    tmp_path: Path, *, inactive: dict[tuple[str, str], str] | None = None, **query: str
) -> AppTest:
    database = tmp_path / "space_search.duckdb"
    repository = DuckDBEquipmentRepository(database)
    repository.initialize()
    repository.save_snapshot(_baseline(), _fleet(), _downtime())
    if inactive:
        repository.save_floor_states(inactive, expected_version=0, source="test")
    clear_equipment_repository()
    app = AppTest.from_string(_page_script(PAGE, database), default_timeout=90)
    for name, value in query.items():
        app.query_params[name] = value
    return _ok(app.run())


def _ok(app: AppTest) -> AppTest:
    assert not app.exception, [item.message for item in app.exception]
    return app


def _floor_views(calls: list[dict[str, Any]], since: int = 0) -> list[dict[str, Any]]:
    """층 도면(보기 · 배치 편집) data — `since` 번째 부름부터."""
    return [data for data in calls[since:] if data.get("scope") == "floor"]


def _search(app: AppTest, name: str) -> AppTest:
    app.selectbox(key=SEARCH_KEY).set_value(name)
    return _ok(app.run())


def _focuses(calls: list[dict[str, Any]], since: int = 0) -> list[dict[str, Any]]:
    return [data["focus"] for data in _floor_views(calls, since) if "focus" in data]


def test_the_search_stands_only_on_the_fab_right_under_the_place_row(
    tmp_path: Path, calls: list[dict[str, Any]]
) -> None:
    """FAB 전체에만 — 자리 줄 바로 밑, 배치 편집 토글 위 한 줄. 라벨은 접고 자리 글이 「설비 찾기」
    이며 값은 비어 선다. 선택지는 층이 정해진 설비명(층 미정 FLOAT-01 은 없다)이고 층 · 상태를
    붙이지 않는다. 층 상세에는 서지 않는다."""
    app = _open(tmp_path)
    box = app.selectbox(key=SEARCH_KEY)
    assert box.value is None and box.placeholder == "설비 찾기" and not box.disabled
    assert box.proto.label_visibility.value == box.proto.label_visibility.COLLAPSED
    assert list(box.options) == [
        "EQ-01",
        "EQ-02",
        "MOD-1A",
        "MOD-1B",
        "N-01",
        "OUT-01",
        "TRAY-01",
        "UP-01",
    ]
    order = _box_order(_box(app))
    at = order.index(SEARCH_KEY)
    assert order[at - 1] == "space_status_floor_jump_fab"
    assert order[at + 1] == "space_fab_edit_mode"

    app.selectbox(key="space_status_floor_jump_fab").set_value("C1 1F")
    _ok(app.run())
    assert SEARCH_KEY not in [box.key for box in app.selectbox]


def test_a_placed_unit_opens_its_floor_and_the_drawing_gets_one_focus(
    tmp_path: Path, calls: list[dict[str, Any]]
) -> None:
    """도면에 선 호기 — 그 층이 열리고 그 회차 도면에만 `focus` 가 실린다. 다음 회차 · FAB 에 갔다
    같은 층을 블록으로 다시 연 회차에는 없다(다시 맞추지 않는다). 필요 단축을 끈 동안이라 고른
    호기를 파이썬이 쥐지 않는다."""
    app = _open(tmp_path)
    start = len(calls)
    _search(app, "EQ-02")
    assert app.session_state["space_status_selected_building"] == "C1"
    assert app.session_state["space_status_selected_floor"] == "1F"
    assert app.query_params["floor"] == ["C1-1F"]
    views = _floor_views(calls, start)
    assert views and views[0].get("mode") == "view"
    focus = views[0]["focus"]
    assert focus["id"] == "EQ-02" and focus["token"]
    assert _focuses(calls, start) == [focus]
    assert FOCUS_KEY not in app.session_state
    assert PICKED_KEY not in app.session_state
    assert views[-1]["pickToServer"] is False

    start = len(calls)
    _ok(app.run())
    assert _floor_views(calls, start) and not _focuses(calls, start)

    app.button(key="space_status_fab_breadcrumb").click()
    _ok(app.run())
    start = len(calls)
    app.session_state[NAVIGATE_KEY] = {"target": "C1 1F"}
    _ok(app.run())
    _ok(app.run())
    assert app.session_state["space_status_selected_floor"] == "1F"
    assert _floor_views(calls, start) and not _focuses(calls, start)


def test_the_same_name_again_moves_again_with_a_new_token(
    tmp_path: Path, calls: list[dict[str, Any]]
) -> None:
    """콜백이 고르기 칸을 비운다 — FAB 에 돌아와 같은 설비를 다시 골라도 새 토큰으로 다시
    맞춘다. 모듈은 제 설비명으로 찾는다(브라우저가 묶음째 맞춘다)."""
    app = _open(tmp_path)
    start = len(calls)
    _search(app, "MOD-1B")
    first = _focuses(calls, start)
    assert [focus["id"] for focus in first] == ["MOD-1B"]

    app.button(key="space_status_fab_breadcrumb").click()
    _ok(app.run())
    assert app.selectbox(key=SEARCH_KEY).value is None
    start = len(calls)
    _search(app, "MOD-1B")
    again = _focuses(calls, start)
    assert [focus["id"] for focus in again] == ["MOD-1B"]
    assert again[0]["token"] != first[0]["token"]


@pytest.mark.parametrize(
    ("name", "why"),
    [
        ("TRAY-01", "미배치(좌표 없음)"),
        ("N-01", "레이아웃 제외(레이아웃표시 N)"),
        ("OUT-01", "반출/이설을 마침"),
    ],
)
def test_a_unit_off_the_drawing_opens_its_floor_and_says_why_in_the_alarm(
    tmp_path: Path, calls: list[dict[str, Any]], name: str, why: str
) -> None:
    """도면에 서지 않은 호기 — 그 층은 열고 맞추지 않으며, 알림창 · Alarm 에 안내 한 마디(무엇을 ·
    어디서 · 까닭)다. 버튼 곁 칸에는 그리지 않는다."""
    app = _open(tmp_path)
    start = len(calls)
    _search(app, name)
    assert app.session_state["space_status_selected_floor"] == "1F"
    assert _floor_views(calls, start) and not _focuses(calls, start)
    # 표지 글은 마크다운 원문이다 — 이름의 구두점 막음(`\\-`)을 걷고 읽는다.
    notes = [note.value.replace("\\", "") for note in flashed(app, "info")]
    assert any(f"「{name}」 — C1 1F 도면에 없습니다" in note and why in note for note in notes), (
        notes
    )
    assert not app.info


def test_an_inactive_floor_still_opens_and_takes_the_focus(
    tmp_path: Path, calls: list[dict[str, Any]]
) -> None:
    """비활성 층도 연다(층 목록 표 「비활성 층」 길과 같다 — 배너가 말한다)."""
    app = _open(tmp_path, inactive={("C1", "2F"): "UNUSED"})
    assert "UP-01" in app.selectbox(key=SEARCH_KEY).options
    start = len(calls)
    _search(app, "UP-01")
    assert app.session_state["space_status_selected_floor"] == "2F"
    assert [focus["id"] for focus in _focuses(calls, start)] == ["UP-01"]
    assert any("비활성 층" in str(item.value) for item in app.caption)


def test_a_refused_open_leaves_no_focus_and_still_clears_the_box(
    tmp_path: Path, calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """층 열기가 거절된 고르기(층 사용 초안이 있는데 체크 없이 온 옛 브라우저의 값 — 거름
    `floor_open_allowed` 가 거짓)는 층을 열지 않고 맞춤 대상 · 고른 호기를 남기지 않으며 칸은
    비운다."""
    asked: list[tuple[tuple[str, str], bool]] = []

    def _refuse(target: tuple[str, str], *, discard: bool) -> bool:
        asked.append((target, discard))
        return False

    monkeypatch.setattr(space_floor_list, "floor_open_allowed", _refuse)
    app = _open(tmp_path)
    start = len(calls)
    _search(app, "EQ-01")
    assert asked == [(("C1", "1F"), False)]
    assert "space_status_selected_floor" not in app.session_state
    assert FOCUS_KEY not in app.session_state and PICKED_KEY not in app.session_state
    assert not _floor_views(calls, start)
    assert app.selectbox(key=SEARCH_KEY).value is None


def test_the_search_asks_in_a_popover_while_a_floor_draft_waits(
    tmp_path: Path, calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """층 사용 편집 초안이 있는 동안은 바로 가기와 같은 팝오버 — 「변경을 버리고 열기」 체크 전에는
    고르기가 잠긴다(설계 규칙 UI-STA-02). 체크한 뒤 고르면 연다(버리겠다고 답한 열기)."""
    monkeypatch.setattr(space_floor_list, "floor_state_draft_pending", lambda: True)
    app = _open(tmp_path)
    assert app.selectbox(key=SEARCH_KEY).disabled
    assert not app.checkbox(key=SEARCH_DISCARD_KEY).value

    app.checkbox(key=SEARCH_DISCARD_KEY).check()
    _ok(app.run())
    assert not app.selectbox(key=SEARCH_KEY).disabled
    start = len(calls)
    _search(app, "EQ-01")
    assert app.session_state["space_status_selected_floor"] == "1F"
    assert [focus["id"] for focus in _focuses(calls, start)] == ["EQ-01"]


def test_the_layout_editor_takes_the_same_one_time_focus(
    tmp_path: Path, calls: list[dict[str, Any]]
) -> None:
    """층 배치 편집 토글은 FAB 회차에 걷혀(위젯 상태) 찾기로 연 층은 늘 보기로 선다 — 그래도 맞춤
    대상이 편집 회차에 닿으면 배치 편집기 data 에도 한 번만 실린다."""
    app = _open(tmp_path, floor="C1-1F")
    app.toggle(key="space_layout_edit_mode").set_value(True)
    _ok(app.run())
    app.session_state[FOCUS_KEY] = ("C1", "1F", "EQ-01", "token-edit")
    start = len(calls)
    _ok(app.run())
    views = _floor_views(calls, start)
    assert views and all(view.get("mode") != "view" for view in views)
    assert _focuses(calls, start) == [{"id": "EQ-01", "token": "token-edit"}]
    start = len(calls)
    _ok(app.run())
    assert _floor_views(calls, start) and not _focuses(calls, start)

    # 다른 층의 값은 버린다.
    app.session_state[FOCUS_KEY] = ("C1", "2F", "UP-01", "token-other")
    start = len(calls)
    _ok(app.run())
    assert not _focuses(calls, start) and FOCUS_KEY not in app.session_state


def test_the_shortening_view_also_holds_the_found_unit_on_the_sample_fleet(
    tmp_path: Path, calls: list[dict[str, Any]]
) -> None:
    """색 기준 「필요 단축」 을 켠 동안(설비 합성 샘플 화면) — 찾은 호기를 필요 단축 칸의 고른
    호기로도 쥐어 도면 `picked` 와 `focus` 가 같은 호기다."""
    PLAN_CACHE.clear()
    clear_equipment_repository()
    app = _sample_app(_empty_database(tmp_path))
    _turn_on(_ok(app.run()))
    floor_view = None
    for label in app.selectbox(key="space_status_floor_jump_fab").options:
        app.selectbox(key="space_status_floor_jump_fab").set_value(label)
        _ok(app.run())
        view = _views(calls, "floor")[-1]
        if view.get("shortBadges"):
            floor_view = view
            break
        app.button(key="space_status_fab_breadcrumb").click()
        _ok(app.run())
    assert floor_view is not None
    unit = str(floor_view["shortBadges"][0]["ids"][0])
    building, floor = str(floor_view["floor"]).split()
    app.button(key="space_status_fab_breadcrumb").click()
    _ok(app.run())

    start = len(calls)
    _search(app, unit)
    views = _floor_views(calls, start)
    assert views[0]["focus"]["id"] == unit
    assert views[-1]["picked"] == unit and views[-1]["pickToServer"] is True
    assert app.session_state[PICKED_KEY] == (building, floor, unit)
    PLAN_CACHE.clear()
    clear_equipment_repository()


# ---------------------------------------------------------------- 브라우저(node · 자산 글자)


def _plan(cases: list[dict[str, Any]]) -> list[Any]:
    block = _SEARCH_BLOCK.search(JS)
    assert block, "editor.js 에 // <search-focus> 구획이 없습니다"
    runner = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
process.stdout.write(JSON.stringify(input.cases.map((c) => {
  const seen = new Set(c.seen || [])
  const known = new Set(c.known || [])
  return focusPlan(c.focus, seen, (id) => known.has(id))
})))
"""
    result: Any = _node(block.group("body") + runner, {"cases": cases})
    return list(result)


def test_a_focus_is_taken_once_per_token_and_an_unknown_id_is_quiet() -> None:
    """맞춤 판정 — 새 토큰의 이 도면 호기면 그 호기다. 같은 토큰은 다시 맞추지 않는다(뒤 회차 · 같은
    epoch 다시 그리기). 이 도면에 없는 id 도 토큰은 쓴다(조용히 — 까닭은 파이썬 알림). 빈 값 · 꼴이
    다른 값은 없음이다."""
    focus = {"id": "DEMO-EQ-01", "token": "t1"}
    assert _plan(
        [
            {"focus": focus, "known": ["DEMO-EQ-01"]},
            {"focus": focus, "known": ["DEMO-EQ-01"], "seen": ["t1"]},
            {"focus": {"id": "DEMO-EQ-09", "token": "t2"}, "known": ["DEMO-EQ-01"]},
            {"focus": None},
            {"focus": {"id": "", "token": "t3"}},
            {"focus": {"id": "DEMO-EQ-01"}},
            {"focus": "DEMO-EQ-01"},
        ]
    ) == [
        {"id": "DEMO-EQ-01", "token": "t1", "known": True},
        None,
        {"id": "DEMO-EQ-09", "token": "t2", "known": False},
        None,
        None,
        None,
        None,
    ]


def test_the_focus_selects_and_fits_the_bundle_after_the_stage_is_measured() -> None:
    """거는 자리 — 층 도면만(FAB 아님), 무대 크기를 잰 뒤(`S.onResize()` 다음). 토큰은 id 가 없어도
    쓰고, 이 도면 호기면 고르고 도면에 선 호기면 묶음째(`expanded`) 「호기 정보」 목록 줄 찾아가기와
    같은 배율 상한(`LIST_ROW_ZOOM` — 설계 규칙 UI-NAV-03 300%)으로 맞춘다. 고른 호기를 서버로
    보내지 않는다(필요 단축 칸은 파이썬 콜백이 쥔다)."""
    start = JS.index("  function applyFocus() {")
    body = JS[start : JS.index("\n  }\n", start)]
    assert "if (FAB) return" in body
    assert body.index("S.focusSeen.add(plan.token)") < body.index("if (!plan.known) return")
    assert body.index("select(plan.id)") < body.index("if (!onCanvas(item)) return")
    assert "zoomToBox(bbox(expanded([item])), LIST_ROW_ZOOM)" in body
    assert "notePick" not in body and "setTriggerValue" not in body
    assert "const LIST_ROW_ZOOM = 3" in JS
    assert "focusSeen: new Set()," in JS
    tail = JS[JS.rindex("  S.onResize()\n") :]
    assert tail.startswith("  S.onResize()\n  applyFocus()\n")
