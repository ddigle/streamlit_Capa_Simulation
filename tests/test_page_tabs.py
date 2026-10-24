# Purpose: app.py 탭 줄의 data·이동·상한·자리와 탭 왕복에 남는 보기 조건을 AppTest 로 시험한다.

"""탭 줄 컴포넌트는 JS 라 AppTest 가 돌리지 못한다. 컴포넌트 한 겹만 기록 대역으로 바꿔 받은
data 를 보고, 누름은 두 겹으로 잰다 — 콜백 함수는 가짜 세션에서 직접 부르고, 콜백이 남기는
결과(목록 칸·이동 대기 칸)는 AppTest 세션에 적고 `run()` 해 `app.py` 가 실제로 옮기는지 본다.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from capa_simulation import page_tabs_state
from capa_simulation.components import page_tabs
from capa_simulation.navigation import (
    CAPA_CHATBOT,
    HOME,
    LOAD_CONVERSION,
    SCENARIO_MANAGEMENT,
    SPACE_STATUS,
    WIP_STATUS,
)
from capa_simulation.page_tabs_state import (
    PAGE_TABS_COMPONENT_KEY,
    PAGE_TABS_OPEN_KEY,
    PAGE_TABS_PINNED_KEY,
    PAGE_TABS_QUEUED_KEY,
    PAGE_TABS_REENTRY_KEY,
    TabStrip,
)
from capa_simulation.sidebar_status import CONDITION_DIALOG_SINK_KEY

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "app.py"
H, A, B = HOME.path, LOAD_CONVERSION.path, SCENARIO_MANAGEMENT.path
PROBE = "page-tabs-probe"


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """탭 줄 기록 대역. 받은 인자를 쌓고 자리 표지 한 줄을 그린다(자리 시험용)."""
    calls: list[dict[str, Any]] = []

    def record(**kwargs: Any) -> SimpleNamespace:
        calls.append(kwargs)
        st.markdown(PROBE)
        return SimpleNamespace(select=None, close=None, pin=None)

    monkeypatch.setattr(page_tabs, "_PAGE_TABS", record)
    return calls


@pytest.fixture
def _app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sent: list[dict[str, Any]]) -> AppTest:
    """빈 DuckDB 를 보는 `app.py`. 내장 시드가 부트스트랩을 채운다(`test_app_navigation` 꼴)."""
    import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
    import capa_simulation.components.intro_overlay as intro_overlay
    import capa_simulation.components.intro_summary as intro_summary
    import capa_simulation.components.month_range_picker as month_range_picker
    import capa_simulation.settings as settings

    monkeypatch.setattr(settings, "DUCKDB_PATH", tmp_path / "scenario.duckdb")
    monkeypatch.setattr(settings, "EQUIPMENT_DUCKDB_PATH", tmp_path / "equipment.duckdb")
    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda *a, **k: None)
    monkeypatch.setattr(intro_overlay, "render_intro_overlay", lambda: None)
    monkeypatch.setattr(intro_summary, "_SUMMARY", lambda **kwargs: None)
    monkeypatch.setattr(
        month_range_picker, "_MONTH_RANGE_APPLY", lambda **kwargs: SimpleNamespace(apply=None)
    )
    return AppTest.from_file(str(APP_PATH), default_timeout=300)


def _ok(app: AppTest) -> AppTest:
    assert not list(app.exception), [element.message for element in app.exception]
    return app


def _data(sent: list[dict[str, Any]]) -> dict[str, Any]:
    return dict(sent[-1]["data"])


def _ids(sent: list[dict[str, Any]]) -> list[str]:
    return [tab["id"] for tab in _data(sent)["tabs"]]


def _tab(sent: list[dict[str, Any]], path: str) -> dict[str, Any]:
    return next(tab for tab in _data(sent)["tabs"] if tab["id"] == path)


def test_opening_two_pages_lists_both_with_home_pinned_first(
    _app: AppTest, sent: list[dict[str, Any]]
) -> None:
    app = _ok(_app.run())
    assert _ids(sent) == [H]
    assert _data(sent)["active"] == H

    _ok(app.switch_page(A).run())

    assert _ids(sent) == [H, A]
    assert _data(sent)["active"] == A
    home, plan = _tab(sent, H), _tab(sent, A)
    assert (home["pinned"], home["closable"], home["label"], home["icon"]) == (
        True,
        False,
        "HOME",
        "home",
    )
    assert (plan["pinned"], plan["closable"], plan["label"], plan["icon"]) == (
        False,
        True,
        "생산 계획",
        "scale",
    )
    assert plan["href"] == "load_conversion" and home["href"] == ""
    assert sent[-1]["key"] == PAGE_TABS_COMPONENT_KEY


def test_a_tab_label_drops_only_the_implementing_suffix(
    _app: AppTest, sent: list[dict[str, Any]]
) -> None:
    app = _ok(_app.run())
    _ok(app.switch_page(WIP_STATUS.path).run())
    wip = _tab(sent, WIP_STATUS.path)
    assert wip["label"] == "표준 대비 재공 현황"
    assert wip["title"] == WIP_STATUS.title


def test_a_queued_tab_switches_the_page(_app: AppTest, sent: list[dict[str, Any]]) -> None:
    app = _ok(_app.run())
    _ok(app.switch_page(A).run())

    app.session_state[PAGE_TABS_QUEUED_KEY] = H
    _ok(app.run())

    assert _data(sent)["active"] == H
    assert [element.value for element in app.title][:1] == ["Capa LOB Summary"]
    assert PAGE_TABS_QUEUED_KEY not in app.session_state
    assert _ids(sent) == [H, A]


def test_closing_the_active_tab_moves_to_its_right_neighbour(
    _app: AppTest, sent: list[dict[str, Any]]
) -> None:
    app = _ok(_app.run())
    _ok(app.switch_page(A).run())
    _ok(app.switch_page(B).run())
    _ok(app.switch_page(A).run())
    assert _ids(sent) == [H, A, B]

    # `_on_close(A)` 가 남기는 결과 — 목록에서 빼고 오른쪽 이웃을 대기 칸에.
    app.session_state[PAGE_TABS_OPEN_KEY] = (H, B)
    app.session_state[PAGE_TABS_QUEUED_KEY] = B
    _ok(app.run())

    assert _data(sent)["active"] == B
    assert _ids(sent) == [H, B]


def test_reentering_an_open_tab_marks_reentry_but_a_new_page_does_not(
    _app: AppTest, sent: list[dict[str, Any]]
) -> None:
    app = _ok(_app.run())
    _ok(app.switch_page(A).run())
    assert app.session_state[PAGE_TABS_REENTRY_KEY] is None
    _ok(app.switch_page(H).run())
    assert app.session_state[PAGE_TABS_REENTRY_KEY] == H

    app.session_state[PAGE_TABS_QUEUED_KEY] = A
    _ok(app.run())

    assert app.session_state[PAGE_TABS_REENTRY_KEY] == A
    # AppTest 는 회차 안의 `st.switch_page` 를 다음 `run()` 의 화면으로 기억하지 않는다 — 브라우저는
    # 주소가 바뀌어 그 화면에 머문다. 같은 화면의 다음 회차를 그렇게 흉내 낸다.
    _ok(app.switch_page(A).run())
    assert app.session_state[PAGE_TABS_REENTRY_KEY] is None


def test_an_eleventh_page_is_refused_and_the_previous_page_stays(
    _app: AppTest, sent: list[dict[str, Any]]
) -> None:
    from capa_simulation.navigation import ALL_SPECS

    app = _ok(_app.run())
    others = [spec.path for spec in ALL_SPECS if spec.path not in {H, CAPA_CHATBOT.path}]
    full = (H, *others[:9])
    app.session_state[PAGE_TABS_OPEN_KEY] = full
    app.session_state[PAGE_TABS_PINNED_KEY] = (H,)
    _ok(app.run())

    _ok(app.switch_page(CAPA_CHATBOT.path).run())

    assert _data(sent)["active"] == H
    assert tuple(_ids(sent)) == full
    notice = _data(sent)["notice"]
    assert notice is not None and "안 쓰는 탭을 닫아 주세요" in notice["text"]
    # 알림은 한 회차만 싣는다. 브라우저는 되돌린 화면(HOME)에 머문다 — AppTest 는 회차 안의 이동을
    # 다음 `run()` 의 화면으로 기억하지 않아 직접 옮긴다.
    _ok(app.switch_page(H).run())
    assert _data(sent)["notice"] is None
    assert tuple(_ids(sent)) == full


def test_the_tab_strip_stands_at_a_fixed_place_before_the_page(
    _app: AppTest, sent: list[dict[str, Any]]
) -> None:
    """탭 줄 앞 본문 칸은 늘 서는 칸뿐이다 — 화면마다·경고가 서는 회차에도 순번이 같다."""

    def probe_place(app: AppTest) -> int:
        children = list(app.main.children.values())
        probes = [
            index
            for index, child in enumerate(children)
            if getattr(child, "type", "") == "markdown" and getattr(child, "value", "") == PROBE
        ]
        assert len(probes) == 1
        before = children[probes[0] - 1]
        assert str(before.proto.id).endswith(CONDITION_DIALOG_SINK_KEY)
        return probes[0]

    app = _ok(_app.run())
    places = {probe_place(app)}
    for path in (A, SPACE_STATUS.path, H):
        _ok(app.switch_page(path).run())
        places.add(probe_place(app))
    assert len(places) == 1


def test_the_callbacks_only_write_the_list_and_the_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    """콜백은 칸만 적는다 — 옮기는 것은 회차 본문이다(`st.switch_page` 를 부르지 않는다)."""
    fake = SimpleNamespace(session_state={}, switch_page=None)
    monkeypatch.setattr(page_tabs, "st", fake)
    monkeypatch.setattr(page_tabs_state, "st", fake)
    page_tabs_state.store_strip(TabStrip((H, A, B), frozenset({H})))

    fake.session_state[PAGE_TABS_COMPONENT_KEY] = {"select": {"id": B, "epoch": 1}}
    page_tabs._on_select()
    assert fake.session_state[PAGE_TABS_QUEUED_KEY] == B

    fake.session_state.pop(PAGE_TABS_QUEUED_KEY)
    fake.session_state[PAGE_TABS_COMPONENT_KEY] = SimpleNamespace(select={"id": "app_pages/x.py"})
    page_tabs._on_select()
    assert PAGE_TABS_QUEUED_KEY not in fake.session_state

    fake.session_state[PAGE_TABS_COMPONENT_KEY] = {"close": {"id": B, "epoch": 1}}
    page_tabs._on_close(A)
    assert fake.session_state[PAGE_TABS_OPEN_KEY] == (H, A)
    assert PAGE_TABS_QUEUED_KEY not in fake.session_state

    fake.session_state[PAGE_TABS_COMPONENT_KEY] = {"close": {"id": A, "epoch": 2}}
    page_tabs._on_close(A)
    assert fake.session_state[PAGE_TABS_OPEN_KEY] == (H,)
    assert fake.session_state[PAGE_TABS_QUEUED_KEY] == H

    # 고정 탭(HOME)은 닫지 않는다. 고정을 풀면 닫을 수 있지만 마지막 하나는 남는다.
    fake.session_state[PAGE_TABS_COMPONENT_KEY] = {"close": {"id": H, "epoch": 3}}
    page_tabs._on_close(H)
    assert fake.session_state[PAGE_TABS_OPEN_KEY] == (H,)
    fake.session_state[PAGE_TABS_COMPONENT_KEY] = {"pin": {"id": H, "pinned": False}}
    page_tabs._on_pin()
    assert fake.session_state[PAGE_TABS_PINNED_KEY] == ()
    page_tabs._on_close(H)
    assert fake.session_state[PAGE_TABS_OPEN_KEY] == (H,)


def test_the_tab_strip_reads_no_database_on_a_rerun(
    _app: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """탭 줄은 세션·선언만 읽는다 — 그리는 동안 저장소·연결 호출이 0 이다."""
    import capa_simulation.persistence._sql_helpers as sql_helpers
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    calls: list[str] = []
    inside: list[int] = []
    for name, value in list(vars(DuckDBScenarioRepository).items()):
        if name.startswith("__") or not callable(value):
            continue

        def counted(
            *args: object, __name: str = name, __func: Any = value, **kwargs: object
        ) -> Any:
            if inside:
                calls.append(__name)
            return __func(*args, **kwargs)

        monkeypatch.setattr(DuckDBScenarioRepository, name, counted)
    original_connect = sql_helpers.connect

    def counted_connect(*args: Any, **kwargs: Any) -> Any:
        if inside:
            calls.append("connect")
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(sql_helpers, "connect", counted_connect)
    original = page_tabs.render_page_tabs
    rendered: list[int] = []

    def watched(*args: Any, **kwargs: Any) -> None:
        inside.append(1)
        try:
            original(*args, **kwargs)
        finally:
            inside.pop()
        rendered.append(1)

    monkeypatch.setattr(page_tabs, "render_page_tabs", watched)

    app = _ok(_app.run())
    _ok(app.switch_page(A).run())

    assert len(rendered) == 2
    assert calls == []


# ------------------------------------------------------------------ 점·떠나기 확인

_REGISTRY_KEY = "scenario_pending_edit_registry"
_EDITED = {"edited_rows": {0: {"202608": 1.0}}, "added_rows": [], "deleted_rows": []}


def _has_theme_unsaved_marker(app: AppTest) -> bool:
    from capa_simulation.components.theme_toggle import UNSAVED_EDITS_CSS_VARIABLE

    marker = f"{UNSAVED_EDITS_CSS_VARIABLE}:1"
    return any(marker in element.proto.body for element in app.get("html"))


def test_a_staged_paste_marks_the_production_plan_tab_from_any_page(
    _app: AppTest, sent: list[dict[str, Any]]
) -> None:
    app = _ok(_app.run())
    _ok(app.switch_page(A).run())
    _ok(app.switch_page(H).run())
    app.session_state["test_staged_paste"] = "붙여넣은 표"
    app.session_state[_REGISTRY_KEY] = {
        "load_conversion.py": ("생산 계획", {}, {"test_staged_paste": "PKG PLAN 붙여넣기"}, None)
    }
    _ok(app.run())

    plan = _tab(sent, A)
    assert plan["dirty"] is True
    assert "생산 계획 · PKG PLAN 붙여넣기" in plan["title"]
    assert _tab(sent, H)["dirty"] is False
    # 붙여넣기 대기는 떠나도 남는다 — 묻지 않는다.
    assert _data(sent)["leave"] == ""


def test_unsaved_equipment_edits_mark_both_equipment_tabs(
    _app: AppTest, sent: list[dict[str, Any]]
) -> None:
    from capa_simulation.components.equipment_data_workspace import PENDING_FAB_KEY
    from capa_simulation.navigation import AVAILABLE_EQUIPMENT_STATUS

    app = _ok(_app.run())
    app.session_state[PAGE_TABS_OPEN_KEY] = (H, AVAILABLE_EQUIPMENT_STATUS.path, SPACE_STATUS.path)
    app.session_state[PENDING_FAB_KEY] = {"canvas": None, "marks": (), "base": (None, "")}
    _ok(app.run())

    assert _tab(sent, AVAILABLE_EQUIPMENT_STATUS.path)["dirty"] is True
    assert _tab(sent, SPACE_STATUS.path)["dirty"] is True
    assert _tab(sent, H)["dirty"] is False


def test_past_data_and_scenario_table_drafts_mark_their_tabs_and_the_theme_button(
    _app: AppTest, sent: list[dict[str, Any]]
) -> None:
    """테마 단추의 「저장 안 함」 확인도 탭 점과 같은 판정이다 — 전에 빠져 있던 두 초안이 든다."""
    from capa_simulation.components.past_data_management import PAST_DRAFT_KEY
    from capa_simulation.components.pick_edit_table import TableDraft, draft_session_key
    from capa_simulation.components.scenario_management import LIST_EDITOR_KEY

    # 초안을 그리는 화면 밖에서 본다 — 점은 그 화면을 그리기 전 세션 값으로 정해진다.
    app = _ok(_app.run())
    _ok(app.switch_page(B).run())
    assert not _has_theme_unsaved_marker(app)

    app.session_state[PAST_DRAFT_KEY] = {"past_month": "읽어 둔 표"}
    _ok(app.switch_page(B).run())
    assert _tab(sent, H)["dirty"] is True
    assert _tab(sent, B)["dirty"] is False
    assert _has_theme_unsaved_marker(app)

    app.session_state[PAST_DRAFT_KEY] = {}
    app.session_state[draft_session_key(LIST_EDITOR_KEY)] = TableDraft(names={"s1": "새 이름"})
    _ok(app.switch_page(H).run())
    assert _tab(sent, H)["dirty"] is False
    assert _tab(sent, B)["dirty"] is True
    assert _has_theme_unsaved_marker(app)


def test_editor_edits_mark_only_the_current_tab_and_ask_before_leaving(
    _app: AppTest, sent: list[dict[str, Any]]
) -> None:
    """편집표 편집은 위젯 상태라 화면을 떠나면 사라진다 — 지금 탭에만 찍고 떠날 때 묻는다."""
    app = _ok(_app.run())
    _ok(app.switch_page(A).run())
    _ok(app.switch_page(H).run())
    app.session_state["test_home_editor"] = _EDITED
    app.session_state[_REGISTRY_KEY] = {
        "home.py": ("HOME", {"test_home_editor": "시험 표"}, {}, None)
    }
    _ok(app.run())

    assert _tab(sent, H)["dirty"] is True
    assert _data(sent)["leave"] == "HOME · 시험 표"

    _ok(app.switch_page(A).run())
    assert _tab(sent, H)["dirty"] is False
    assert _data(sent)["leave"] == ""
