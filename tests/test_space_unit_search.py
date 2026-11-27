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
from datetime import date, timedelta
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
AS_OF_KEY = "space_status_as_of"
NAVIGATE_KEY = "test_fake_fab_navigate"
HIDDEN_KEY = "test_fake_focus_hidden"
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


def test_a_module_off_the_drawing_leads_to_a_standing_sibling_on_its_floor() -> None:
    """도면에 서지 않은 모듈은 같은 층 도면에 선 형제(자연 정렬 처음)를 `lead` 로 단다 — 도면이 그
    묶음으로 맞춘다. 형제가 다른 층에만 섰거나 없으면 `lead` 가 없다. 낱 호기 · 도면에 선 모듈은
    `group` 도 달지 않는다."""

    def modules(*rows: tuple[str, str, str, str | None]) -> pd.DataFrame:
        return pd.DataFrame(rows, columns=["설비명", "동", "층", "Main 설비"])

    targets = unit_search_targets(
        placed=modules(
            ("DEMO-M1-B", "C1", "1F", "DEMO-M1"),
            ("DEMO-M1-A", "C1", "1F", "DEMO-M1"),
            ("DEMO-M2-A", "C2", "1F", "DEMO-M2"),
            ("DEMO-EQ-01", "C1", "1F", None),
        ),
        unplaced=modules(
            ("DEMO-M1-C", "C1", "1F", "DEMO-M1"), ("DEMO-M2-B", "C1", "1F", "DEMO-M2")
        ),
        excluded=modules(("DEMO-M1-D", "C1", "1F", "DEMO-M1"), ("DEMO-OFF", "C1", "1F", None)),
        exited=modules(("DEMO-M3-A", "C1", "1F", "DEMO-M3")),
    )
    assert targets["DEMO-M1-C"] == UnitSearchTarget(
        ("C1", "1F"), SEARCH_UNPLACED, "DEMO-M1", "DEMO-M1-A"
    )
    assert targets["DEMO-M1-D"].lead == "DEMO-M1-A"
    assert targets["DEMO-M2-B"] == UnitSearchTarget(("C1", "1F"), SEARCH_UNPLACED, "DEMO-M2", None)
    assert targets["DEMO-M3-A"].lead is None
    assert targets["DEMO-M1-A"] == UnitSearchTarget(("C1", "1F"), SEARCH_PLACED)
    assert targets["DEMO-OFF"] == UnitSearchTarget(("C1", "1F"), SEARCH_EXCLUDED)


# ---------------------------------------------------------------- 화면(AppTest)


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """`_EDITOR` 대역 — 받은 data 를 적고, `NAVIGATE_KEY` 가 있으면 FAB 블록을 누른 것처럼
    `on_navigate_change` 를, `HIDDEN_KEY` 가 있으면 층 보기가 맞출 호기를 그 날 숨긴 것처럼
    `on_focusHidden_change` 를 부른다."""
    recorded: list[dict[str, Any]] = []

    def _stub(**kwargs: Any) -> None:
        import streamlit as st

        data = kwargs["data"]
        recorded.append(data)
        payload = st.session_state.pop(NAVIGATE_KEY, None)
        if payload is not None and data.get("scope") == "fab":
            st.session_state[kwargs["key"]] = {"navigate": {"epoch": data["epoch"], **payload}}
            kwargs["on_navigate_change"]()
        hidden = st.session_state.pop(HIDDEN_KEY, None)
        if hidden is not None and data.get("mode") == "view" and data.get("scope") == "floor":
            st.session_state[kwargs["key"]] = {"focusHidden": {"epoch": data["epoch"], **hidden}}
            kwargs["on_focusHidden_change"]()

    monkeypatch.setattr(space_layout_editor, "_EDITOR", _stub)
    return recorded


def _fleet() -> pd.DataFrame:
    """C1 1F — EQ-01·EQ-02 · Main 설비 MOD-1 모듈 둘(과 레이아웃표시 N 인 셋째 모듈) · 좌표 없는
    TRAY-01 · 레이아웃표시 N 인 N-01 ·
    기준일 전에 반출을 마친 OUT-01, C1 2F — UP-01, 동 · 층 미정 — FLOAT-01."""
    module = {"Main 설비": "MOD-1", "Xsize": 6, "Ysize": 4}
    return _master(
        {**module, "설비명": "MOD-1A", "X좌표": 60.0, "Y좌표": 10.0},
        {**module, "설비명": "MOD-1B", "X좌표": 66.0, "Y좌표": 10.0},
        {**module, "설비명": "MOD-1C", "레이아웃표시": "N", "X좌표": None, "Y좌표": None},
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
    tmp_path: Path,
    *,
    inactive: dict[tuple[str, str], str] | None = None,
    fleet: pd.DataFrame | None = None,
    **query: str,
) -> AppTest:
    database = tmp_path / "space_search.duckdb"
    repository = DuckDBEquipmentRepository(database)
    repository.initialize()
    repository.save_snapshot(_baseline(), _fleet() if fleet is None else fleet, _downtime())
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


def _short(shown: Any) -> str:
    """표지 알림의 알림창 짧은 글(`alerts.short_text` — 60자 말줄임)."""
    return str((shown.note or {}).get("short", ""))


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
        "MOD-1C",
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
        ("N-01", "레이아웃 제외"),
        ("OUT-01", "반출/이설 마침"),
    ],
)
def test_a_unit_off_the_drawing_opens_its_floor_and_says_why_in_the_alarm(
    tmp_path: Path, calls: list[dict[str, Any]], name: str, why: str
) -> None:
    """도면에 서지 않은 호기 — 그 층은 열고 맞추지 않으며, 알림창 · Alarm 에 안내 한 마디(무엇을 ·
    어디서 · 까닭 — 까닭이 이름 · 층 바로 뒤라 알림창 짧은 글에 남는다)다. 버튼 곁 칸에는 그리지
    않는다."""
    app = _open(tmp_path)
    start = len(calls)
    _search(app, name)
    assert app.session_state["space_status_selected_floor"] == "1F"
    assert _floor_views(calls, start) and not _focuses(calls, start)
    # 표지 글은 마크다운 원문이다 — 이름의 구두점 막음(`\\-`)을 걷고 읽는다.
    notes = [note.value.replace("\\", "") for note in flashed(app, "info")]
    assert any(f"「{name}」 C1 1F · " in note and why in note for note in notes), notes
    assert any(why in _short(note) for note in flashed(app, "info")), notes
    assert not app.info


def test_a_module_off_the_drawing_fits_its_standing_bundle_and_says_so(
    tmp_path: Path, calls: list[dict[str, Any]]
) -> None:
    """도면에 서지 않은 모듈(레이아웃표시 N 인 MOD-1C)은 층을 열고 같은 층 도면에 선 형제(MOD-1A)로
    맞춰 그 묶음을 보이며, 알림창 한 마디가 그 묶음으로 맞췄다고 말한다 — Main 설비 이름은 맨 끝
    괄호라 긴 이름에 짧은 글이 잘려도 「묶음으로 맞춤」 은 남는다."""
    app = _open(tmp_path)
    start = len(calls)
    _search(app, "MOD-1C")
    assert app.session_state["space_status_selected_floor"] == "1F"
    assert [focus["id"] for focus in _focuses(calls, start)] == ["MOD-1A"]
    notes = [note.value.replace("\\", "") for note in flashed(app, "info")]
    assert any(
        "「MOD-1C」 C1 1F · 레이아웃 제외 · 묶음으로 맞춤(Main 설비 「MOD-1」)" in note
        for note in notes
    ), notes


def test_a_long_module_name_keeps_the_bundle_word_in_the_alarm_short_text(
    tmp_path: Path, calls: list[dict[str, Any]]
) -> None:
    """이름이 길어 알림창 짧은 글(60자)이 잘려도 까닭과 「묶음으로 맞춤」 은 남는다 — Main 설비
    이름만 잘린다(설계 규칙 UI-NTF-06)."""
    module = {"Main 설비": "DEMO-MODULE-LONG-01", "Xsize": 6, "Ysize": 4}
    app = _open(
        tmp_path,
        fleet=_master(
            {**module, "설비명": "DEMO-MODULE-LONG-01A", "X좌표": 60.0, "Y좌표": 10.0},
            {
                **module,
                "설비명": "DEMO-MODULE-LONG-01C",
                "레이아웃표시": "N",
                "X좌표": None,
                "Y좌표": None,
            },
        ),
    )
    _search(app, "DEMO-MODULE-LONG-01C")
    shorts = [_short(note) for note in flashed(app, "info")]
    assert any(
        short.startswith("「DEMO-MODULE-LONG-01C」 C1 1F · 레이아웃 제외 · 묶음으로 맞춤")
        and short.endswith("…")
        for short in shorts
    ), shorts


def test_the_search_works_while_the_fab_layout_is_being_edited(
    tmp_path: Path, calls: list[dict[str, Any]]
) -> None:
    """FAB 배치 편집을 켠 동안에도 자리 줄 밑에 서고, 고르면 그 층이 열려 첫 회차 도면이 맞춘다
    (FAB 편집 토글은 층에서 걷혀 층은 보기로 선다)."""
    app = _open(tmp_path)
    app.toggle(key="space_fab_edit_mode").set_value(True)
    _ok(app.run())
    assert any(data.get("scope") == "fab" and data.get("mode") != "view" for data in calls)
    order = _box_order(_box(app))
    assert order[order.index(SEARCH_KEY) + 1] == "space_fab_edit_mode"
    start = len(calls)
    _search(app, "EQ-01")
    assert app.session_state["space_status_selected_floor"] == "1F"
    views = _floor_views(calls, start)
    assert views[0].get("mode") == "view"
    assert [focus["id"] for focus in _focuses(calls, start)] == ["EQ-01"]


def _exiting_fleet(today: date) -> pd.DataFrame:
    """C1 1F — 오늘 뒤 30일에 반출하는 SOON-OUT · 오늘 앞 30일에 반출을 마친 PAST-OUT."""
    return _master(
        {
            "설비명": "SOON-OUT",
            "X좌표": 60.0,
            "정지일정": (today + timedelta(days=20)).isoformat(),
            "반출/이설일정": (today + timedelta(days=30)).isoformat(),
        },
        {
            "설비명": "PAST-OUT",
            "X좌표": 80.0,
            "정지일정": (today - timedelta(days=40)).isoformat(),
            "반출/이설일정": (today - timedelta(days=30)).isoformat(),
        },
    )


def _drawn(view: dict[str, Any], name: str) -> bool:
    """그 도면이 그 기준일(`asOf`)에 그리는 호기인가 — 브라우저 `unitState` 의 보임(도면 이탈일
    없음 또는 기준일 < 도면 이탈일)."""
    item = next((item for item in view["items"] if item.get("id") == name), None)
    return item is not None and (item.get("exitOn") is None or view["asOf"] < item["exitOn"])


@pytest.mark.parametrize("fab_edit", [False, True])
@pytest.mark.parametrize(("shift", "name"), [(60, "SOON-OUT"), (-60, "PAST-OUT")])
def test_the_search_judges_a_unit_on_the_day_the_opened_floor_draws(
    tmp_path: Path, calls: list[dict[str, Any]], fab_edit: bool, shift: int, name: str
) -> None:
    """색 기준 「필요 단축」 이면 연 층은 오늘로 선다 — FAB 배치 편집 중(필요 단축이 쉬어 FAB 은
    세션 기준일)에 찾아도 후보의 자리 · 알림 날은 연 층이 그릴 날이다. 맞춤은 그 도면이 그 날
    그리는 호기에만 실리고, 그 날 빠진 호기는 그 날로 알린다(세션 기준일은 반출일 너머)."""
    today = date.today()
    app = _open(tmp_path, fleet=_exiting_fleet(today))
    app.session_state[AS_OF_KEY] = today + timedelta(days=shift)
    _turn_on(_ok(app.run()))
    if fab_edit:
        app.toggle(key="space_fab_edit_mode").set_value(True)
        _ok(app.run())
    assert name in app.selectbox(key=SEARCH_KEY).options
    start = len(calls)
    _search(app, name)
    views = _floor_views(calls, start)
    assert views[0]["asOf"] == today.isoformat()
    drawn = _drawn(views[0], name)
    assert drawn is (name == "SOON-OUT")
    assert [focus["id"] for focus in _focuses(calls, start)] == ([name] if drawn else [])
    notes = [note.value.replace("\\", "") for note in flashed(app, "info")]
    if drawn:
        assert not notes, notes
    else:
        assert any(f"{today.isoformat()}" in note and "반출/이설" in note for note in notes), notes
        assert PICKED_KEY not in app.session_state


def test_a_unit_the_drawing_hides_that_day_is_said_in_the_alarm(
    tmp_path: Path, calls: list[dict[str, Any]]
) -> None:
    """그 날 도면에 숨은 호기(겹친 반입 예정 — 파이썬은 겹침을 모른다)는 브라우저가 맞추지 않고
    `focusHidden` 을 보내면 알림창 · Alarm 안내 한 마디다(무엇을 · 어디서 · 까닭). 옛 epoch 값 ·
    토큰 없는 값은 버린다."""
    app = _open(tmp_path)
    _search(app, "EQ-01")
    today = date.today().isoformat()
    app.session_state[HIDDEN_KEY] = {"id": "EQ-01", "token": "t", "covered": True}
    _ok(app.run())
    _ok(app.run())
    notes = [note.value.replace("\\", "") for note in flashed(app, "info")]
    assert any(f"「EQ-01」 C1 1F · {today}에 겹쳐 숨긴 반입 예정" in note for note in notes), notes
    assert not app.info

    for stale in ({"id": "EQ-02", "token": "t", "epoch": "old"}, {"id": "EQ-02"}):
        app.session_state[HIDDEN_KEY] = stale
        _ok(app.run())
        _ok(app.run())
        assert not any("「EQ-02」" in note.value for note in flashed(app, "info"))


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
  const hidden = new Set(c.hidden || [])
  return focusPlan(c.focus, seen, (id) => known.has(id), (id) => hidden.has(id))
})))
"""
    result: Any = _node(block.group("body") + runner, {"cases": cases})
    return list(result)


def test_a_focus_is_taken_once_per_token_and_an_unknown_id_is_quiet() -> None:
    """맞춤 판정 — 새 토큰의 이 도면 호기면 그 호기다. 같은 토큰은 다시 맞추지 않는다(뒤 회차 · 같은
    epoch 다시 그리기). 이 도면에 없는 id 도 토큰은 쓴다(조용히 — 까닭은 파이썬 알림). 그 날 숨은
    호기면 `hidden` 이다(고르지도 맞추지도 않음 — 없는 id 는 숨음을 묻지 않는다). 빈 값 · 꼴이 다른
    값은 없음이다."""
    focus = {"id": "DEMO-EQ-01", "token": "t1"}
    assert _plan(
        [
            {"focus": focus, "known": ["DEMO-EQ-01"]},
            {"focus": focus, "known": ["DEMO-EQ-01"], "seen": ["t1"]},
            {"focus": {"id": "DEMO-EQ-09", "token": "t2"}, "known": ["DEMO-EQ-01"]},
            {"focus": focus, "known": ["DEMO-EQ-01"], "hidden": ["DEMO-EQ-01"]},
            {"focus": {"id": "DEMO-EQ-09", "token": "t4"}, "hidden": ["DEMO-EQ-09"]},
            {"focus": None},
            {"focus": {"id": "", "token": "t3"}},
            {"focus": {"id": "DEMO-EQ-01"}},
            {"focus": "DEMO-EQ-01"},
        ]
    ) == [
        {"id": "DEMO-EQ-01", "token": "t1", "known": True, "hidden": False},
        None,
        {"id": "DEMO-EQ-09", "token": "t2", "known": False, "hidden": False},
        {"id": "DEMO-EQ-01", "token": "t1", "known": True, "hidden": True},
        {"id": "DEMO-EQ-09", "token": "t4", "known": False, "hidden": False},
        None,
        None,
        None,
        None,
    ]


def test_the_focus_selects_and_fits_the_bundle_after_the_stage_is_measured() -> None:
    """거는 자리 — 층 도면만(FAB 아님), 무대 크기를 잰 뒤(`S.onResize()` 다음). 토큰은 id 가 없어도
    쓰고, 이 도면 호기면 고르고 도면에 선 호기면 묶음째(`expanded`) 「호기 정보」 목록 줄 찾아가기와
    같은 배율 상한(`LIST_ROW_ZOOM` — 설계 규칙 UI-NAV-03 300%)으로 맞춘다. 보기에서 그 날 숨은
    호기(`__visible === false` — 목록 줄 찾아가기와 같은 거름)는 고르지도 맞추지도 않고 그린 뒤에
    `focusHidden` 만 보낸다. 고른 호기를 서버로 보내지 않는다(필요 단축 칸은 파이썬 콜백이 쥔다)."""
    start = JS.index("  function applyFocus() {")
    body = JS[start : JS.index("\n  }\n", start)]
    assert "if (FAB) return" in body
    assert body.index("S.focusSeen.add(plan.token)") < body.index("if (!plan.known) return")
    assert "(id) => VIEW && S.groups.get(id)?.__visible === false" in body
    hidden = body[
        body.index("if (plan.hidden) {") : body.index("const item = S.items.get(plan.id)")
    ]
    assert body.index("if (!plan.known) return") < body.index("if (plan.hidden) {")
    assert "queueMicrotask" in hidden and "setTriggerValue('focusHidden', body)" in hidden
    assert "return\n" in hidden and "select(" not in hidden and "zoomToBox(" not in hidden
    assert body.index("select(plan.id)") < body.index("if (!onCanvas(item)) return")
    assert "zoomToBox(bbox(expanded([item])), LIST_ROW_ZOOM)" in body
    assert "notePick" not in body and "setTriggerValue('pick'" not in body
    assert body.count("setTriggerValue(") == 1
    assert "const LIST_ROW_ZOOM = 3" in JS
    assert "focusSeen: new Set()," in JS
    tail = JS[JS.rindex("  S.onResize()\n") :]
    assert tail.startswith("  S.onResize()\n  applyFocus()\n")
