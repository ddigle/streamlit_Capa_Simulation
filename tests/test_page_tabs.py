# Purpose: app.py 탭 줄의 data·이동·상한·자리와 탭 왕복에 남는 보기 조건을 AppTest 로 시험한다.

"""탭 줄 컴포넌트는 JS 라 AppTest 가 돌리지 못한다. 컴포넌트 한 겹만 기록 대역으로 바꿔 받은
data 를 보고, 누름은 두 겹으로 잰다 — 콜백 함수는 가짜 세션에서 직접 부르고, 콜백이 남기는
결과(목록 칸·이동 대기 칸)는 AppTest 세션에 적고 `run()` 해 `app.py` 가 실제로 옮기는지 본다.
"""

from __future__ import annotations

from functools import partial
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from capa_simulation import page_tabs_state
from capa_simulation.components import page_tabs
from capa_simulation.navigation import (
    ALL_SPECS,
    CAPA_CHATBOT,
    HOME,
    LOAD_CONVERSION,
    SCENARIO_MANAGEMENT,
    SPACE_STATUS,
    WIP_STATUS,
)
from capa_simulation.page_tabs_state import (
    MAX_TABS,
    PAGE_TABS_COMPONENT_KEY,
    PAGE_TABS_EPOCH_KEY,
    PAGE_TABS_NOTICE_KEY,
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
    # JS 가 상한에서 화면 링크 누름을 거를 때 읽는 것 — 상한, 모든 화면의 주소 → 탭 이름.
    data = _data(sent)
    assert data["max"] == MAX_TABS
    assert len(data["pages"]) == len(ALL_SPECS)
    assert data["pages"][""] == "HOME" and data["pages"]["load_conversion"] == "생산 계획"


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
    # 주소가 바뀌어 그 화면에 머문다. 같은 화면의 다음 회차를 그렇게 흉내 낸다. 머무는 동안 표지는
    # 그대로다(다시 들어온 첫 회차가 끊겨도 이어 본다).
    _ok(app.switch_page(A).run())
    assert app.session_state[PAGE_TABS_REENTRY_KEY] == A
    _ok(app.switch_page(B).run())
    assert app.session_state[PAGE_TABS_REENTRY_KEY] is None


def test_an_eleventh_page_is_refused_and_the_previous_page_stays(
    _app: AppTest, sent: list[dict[str, Any]]
) -> None:
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


def _full_strip_without(*paths: str) -> tuple[str, ...]:
    """HOME 을 맨 앞에 둔 10개 탭 — `paths` 는 넣지 않는다."""
    others = [spec.path for spec in ALL_SPECS if spec.path not in {H, *paths}]
    return (H, *others[: MAX_TABS - 1])


def test_a_home_cell_at_the_limit_is_refused_before_moving(
    _app: AppTest, sent: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """HOME 칸은 옮기기 **전에** 상한을 본다 — 공정 Capa 상세로 옮겼다가 `app.py` 가 되돌리면
    브라우저 기록에 두 화면이 쌓여 뒤로가기가 그 화면에 갇힌다. 전달 칸도 적지 않는다."""
    from capa_simulation.navigation import PROCESS_CAPA_DETAIL
    from capa_simulation.process_detail_state import (
        PROCESS_DETAIL_QUEUED_KEY,
        PROCESS_DETAIL_REQUEST_KEY,
        ProcessDetailRequest,
    )

    sent_back: list[str] = []
    original = page_tabs_state._switch

    def recorded(target: str) -> None:
        sent_back.append(target)
        original(target)

    monkeypatch.setattr(page_tabs_state, "_switch", recorded)
    app = _ok(_app.run())
    full = _full_strip_without(PROCESS_CAPA_DETAIL.path)
    app.session_state[PAGE_TABS_OPEN_KEY] = full
    app.session_state[PAGE_TABS_PINNED_KEY] = (H,)
    _ok(app.run())

    app.session_state[PROCESS_DETAIL_QUEUED_KEY] = ProcessDetailRequest(process="DEMO", month=None)
    _ok(app.run())

    assert sent_back == []
    assert _data(sent)["active"] == H
    assert tuple(_ids(sent)) == full
    notice = _data(sent)["notice"]
    assert notice is not None and "「공정 Capa 상세」" in notice["text"]
    assert PROCESS_DETAIL_QUEUED_KEY not in app.session_state
    assert PROCESS_DETAIL_REQUEST_KEY not in app.session_state


def _detail_next_screen_app() -> None:
    import streamlit as st

    from capa_simulation.components.process_capa_view import (
        open_availability_gap,
        open_shortening_page,
    )

    call = st.session_state.pop("test_call", None)
    if call == "shortening":
        open_shortening_page("DEMO-A")
    elif call == "gap":
        open_availability_gap()


def test_detail_next_screen_buttons_write_nothing_at_the_limit() -> None:
    """공정 Capa 상세의 다음 화면 단추도 옮기기 전에 상한을 본다 — 실패한 클릭의 강조 공정·탭
    기억이 남으면 나중에 사이드바로 연 그 화면이 「공정 Capa 상세에서 연 공정」 강조를 단다."""
    from capa_simulation.components.shortening_board import SHORTENING_HIGHLIGHT_KEY
    from capa_simulation.components.tab_state import remembered_tab_key
    from capa_simulation.navigation import (
        AVAILABLE_EQUIPMENT_STATUS,
        EQUIPMENT_TAB_KEY,
        REQUIRED_SHORTENING,
    )

    app = AppTest.from_function(_detail_next_screen_app, default_timeout=60).run()
    full = _full_strip_without(REQUIRED_SHORTENING.path, AVAILABLE_EQUIPMENT_STATUS.path)
    app.session_state[PAGE_TABS_OPEN_KEY] = full
    app.session_state[PAGE_TABS_PINNED_KEY] = (H,)

    app.session_state["test_call"] = "shortening"
    _ok(app.run())
    assert SHORTENING_HIGHLIGHT_KEY not in app.session_state
    notice = app.session_state[PAGE_TABS_NOTICE_KEY]
    assert notice[2] is True and "「필요 단축 일정」" in notice[1]

    app.session_state["test_call"] = "gap"
    _ok(app.run())
    assert remembered_tab_key(EQUIPMENT_TAB_KEY) not in app.session_state
    assert "「가용설비 현황」" in app.session_state[PAGE_TABS_NOTICE_KEY][1]

    # 자리가 있으면 지금처럼 칸을 적는다(단독 실행이라 옮기지는 못한다).
    app.session_state[PAGE_TABS_OPEN_KEY] = full[:-1]
    app.session_state["test_call"] = "shortening"
    _ok(app.run())
    assert SHORTENING_HIGHLIGHT_KEY in app.session_state


def test_the_tab_strip_stands_at_a_fixed_place_before_the_page(
    _app: AppTest, sent: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """탭 줄 앞 본문 칸은 늘 서는 칸뿐이다 — 화면마다·경고가 서는 회차에도 순번이 같다. 생겼다
    사라지는 스키마 경고는 탭 줄 **뒤**에 선다."""
    import capa_simulation.page_bootstrap as page_bootstrap

    warn: list[int] = []

    def schema_warning(notice: object) -> None:
        if warn:
            st.warning("schema-ahead-probe")

    monkeypatch.setattr(page_bootstrap, "render_schema_ahead_warning", schema_warning)

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

    def warning_place(app: AppTest) -> int:
        children = list(app.main.children.values())
        return next(
            index
            for index, child in enumerate(children)
            if getattr(child, "type", "") == "warning"
            and getattr(child, "value", "") == "schema-ahead-probe"
        )

    app = _ok(_app.run())
    places = {probe_place(app)}
    for path in (A, SPACE_STATUS.path, H):
        _ok(app.switch_page(path).run())
        places.add(probe_place(app))
    warn.append(1)
    for path in (H, A):
        _ok(app.switch_page(path).run())
        places.add(probe_place(app))
        assert warning_place(app) > probe_place(app)
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
    # `app.py` 가 따로 부르는 점 판정·떠나기 글도 탭 줄 몫이다 — 셋 다 감싼다.
    rendered: list[str] = []
    for name in ("render_page_tabs", "page_unsaved_marks", "leave_notice"):
        original = getattr(page_tabs, name)

        def watched(*args: Any, __name: str = name, __func: Any = original, **kwargs: Any) -> Any:
            inside.append(1)
            try:
                return __func(*args, **kwargs)
            finally:
                inside.pop()
                rendered.append(__name)

        monkeypatch.setattr(page_tabs, name, watched)

    app = _ok(_app.run())
    _ok(app.switch_page(A).run())

    assert sorted(rendered) == sorted(
        ["render_page_tabs", "page_unsaved_marks", "leave_notice"] * 2
    )
    assert calls == []


def _press(
    app: AppTest, monkeypatch: pytest.MonkeyPatch, callback: Any, payload: dict[str, Any]
) -> None:
    """탭 줄 콜백 하나를 AppTest 세션의 탭 칸으로 돌리고 그 결과를 세션에 옮겨 적는다 — AppTest 는
    컴포넌트 트리거를 보내지 못한다. 다음 `run()` 이 `app.py` 로 그 결과를 그린다."""
    keys = (PAGE_TABS_OPEN_KEY, PAGE_TABS_PINNED_KEY, PAGE_TABS_EPOCH_KEY, PAGE_TABS_QUEUED_KEY)
    fake = SimpleNamespace(
        session_state={key: app.session_state[key] for key in keys if key in app.session_state}
    )
    fake.session_state[PAGE_TABS_COMPONENT_KEY] = payload
    with monkeypatch.context() as patch:
        patch.setattr(page_tabs, "st", fake)
        patch.setattr(page_tabs_state, "st", fake)
        callback()
    for key in keys:
        if key in fake.session_state:
            app.session_state[key] = fake.session_state[key]


def test_pinning_and_unpinning_through_the_app_keep_pinned_tabs_left(
    _app: AppTest, sent: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """고정한 탭은 왼쪽으로 가고 × 가 없다. HOME 도 고정을 풀면 닫힌다. 다른 화면으로 옮겨도 고정은
    남고, 닫은 HOME 을 사이드바로 다시 열면 끝에 고정 없이 붙는다."""
    app = _ok(_app.run())
    _ok(app.switch_page(A).run())
    _ok(app.switch_page(B).run())
    assert _ids(sent) == [H, A, B]

    _press(app, monkeypatch, page_tabs._on_pin, {"pin": {"id": B, "pinned": True, "epoch": 1}})
    _ok(app.switch_page(B).run())
    assert _ids(sent) == [H, B, A]
    assert (_tab(sent, B)["pinned"], _tab(sent, B)["closable"]) == (True, False)

    # 고정 탭은 × 가 와도 닫지 않는다.
    _press(app, monkeypatch, partial(page_tabs._on_close, B), {"close": {"id": B, "epoch": 2}})
    _ok(app.switch_page(B).run())
    assert _ids(sent) == [H, B, A] and _data(sent)["active"] == B

    _press(app, monkeypatch, page_tabs._on_pin, {"pin": {"id": H, "pinned": False, "epoch": 3}})
    _ok(app.switch_page(B).run())
    assert _ids(sent) == [B, H, A]
    assert (_tab(sent, H)["pinned"], _tab(sent, H)["closable"]) == (False, True)

    _press(app, monkeypatch, partial(page_tabs._on_close, B), {"close": {"id": H, "epoch": 4}})
    _ok(app.switch_page(B).run())
    assert _ids(sent) == [B, A] and _data(sent)["active"] == B

    _ok(app.switch_page(A).run())
    assert _ids(sent) == [B, A] and _tab(sent, B)["pinned"] is True
    _ok(app.switch_page(H).run())
    assert _ids(sent) == [B, A, H]
    assert (_tab(sent, H)["pinned"], _tab(sent, H)["closable"]) == (False, True)


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


def test_an_equipment_buffer_ahead_of_its_seed_marks_both_equipment_tabs(
    _app: AppTest, sent: list[dict[str, Any]]
) -> None:
    """설비 편집본 세대가 세운 세대보다 앞서면(RawData 제출·Space 적용) 두 탭에 점 — FAB 대기 칸
    없이 세대 길만으로도 찍는다. 세대가 같아지면(저장) 점이 걷힌다."""
    from capa_simulation.components.equipment_data_workspace import (
        _SEEDED_GENERATION_KEY,
        BUFFER_GENERATION_KEY,
    )
    from capa_simulation.navigation import AVAILABLE_EQUIPMENT_STATUS

    app = _ok(_app.run())
    app.session_state[PAGE_TABS_OPEN_KEY] = (H, AVAILABLE_EQUIPMENT_STATUS.path, SPACE_STATUS.path)
    app.session_state[_SEEDED_GENERATION_KEY] = 3
    app.session_state[BUFFER_GENERATION_KEY] = 4
    _ok(app.run())
    assert _tab(sent, AVAILABLE_EQUIPMENT_STATUS.path)["dirty"] is True
    assert _tab(sent, SPACE_STATUS.path)["dirty"] is True
    assert "저장하지 않은 설비 편집" in _tab(sent, SPACE_STATUS.path)["title"]
    assert _tab(sent, H)["dirty"] is False

    app.session_state[_SEEDED_GENERATION_KEY] = 4
    _ok(app.run())
    assert _tab(sent, AVAILABLE_EQUIPMENT_STATUS.path)["dirty"] is False
    assert _tab(sent, SPACE_STATUS.path)["dirty"] is False


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


def _floor_state_marks_script() -> None:
    import streamlit as st

    from capa_simulation.components.page_tabs import leave_notice, page_unsaved_marks

    page = st.session_state["test_page_file"]
    st.session_state["test_marks"] = page_unsaved_marks(page)
    st.session_state["test_leave"] = leave_notice(page)


@pytest.mark.parametrize(
    ("page_file", "toggle", "draft", "dirty"),
    [
        ("space_status.py", True, {"C1 3F": "UNUSED"}, True),
        ("space_status.py", True, {}, False),
        ("space_status.py", False, {"C1 3F": "UNUSED"}, False),
        ("home.py", True, {"C1 3F": "UNUSED"}, False),
    ],
    ids=["Space·켜짐·다름", "Space·켜짐·같음", "Space·꺼짐", "다른 화면"],
)
def test_a_floor_state_draft_marks_only_the_space_tab_and_asks_before_leaving(
    page_file: str, toggle: bool, draft: dict[str, str], dirty: bool
) -> None:
    """Space 층 사용 편집 초안은 `사용 편집` 토글(위젯 상태)이 화면을 떠나면 꺼져 버려진다 — 편집표
    편집처럼 Space 가 지금 화면일 때만 점을 찍고 떠날 때 묻는다. 테마 표지도 이 점으로 본다."""
    from capa_simulation.components.space_floor_list import BASE_KEY, DRAFT_KEY, EDIT_TOGGLE_KEY

    app = AppTest.from_function(_floor_state_marks_script)
    app.session_state["test_page_file"] = page_file
    app.session_state[EDIT_TOGGLE_KEY] = toggle
    app.session_state[DRAFT_KEY] = draft
    app.session_state[BASE_KEY] = (0, ())
    _ok(app.run())

    marks = app.session_state["test_marks"]
    leave = app.session_state["test_leave"]
    if dirty:
        assert marks == {SPACE_STATUS.path: "저장하지 않은 층 사용 편집"}
        assert leave == page_tabs.FLOOR_STATE_LEAVE_LABEL == "Space 현황 · 층 사용 편집"
    else:
        assert marks == {}
        assert leave == ""


# ------------------------------------------------------------------ 탭 왕복에 남는 보기 조건

_CALCULATION_RESULT = "app_pages/calculation_result.py"


def _via_tab(app: AppTest, here: str, target: str) -> AppTest:
    """`here` 화면의 탭 줄에서 `target` 탭을 누른 회차 — 콜백이 남긴 대기 칸을 `app.py` 가
    옮긴다."""
    app.session_state[PAGE_TABS_QUEUED_KEY] = target
    return _ok(app.switch_page(here).run())


def test_conditions_survive_a_tab_round_trip(_app: AppTest, sent: list[dict[str, Any]]) -> None:
    """산출 결과 「표시 방식」은 같은 카드의 「집계 수준」처럼 다른 탭에 갔다 와도 남는다."""
    app = _ok(_app.run())
    _ok(app.switch_page(_CALCULATION_RESULT).run())
    _ok(app.selectbox(key="unit_capacity_detail_level").set_value("양산").run())
    _ok(app.segmented_control(key="unit_capacity_view_mode").set_value("STEP별").run())

    _via_tab(app, _CALCULATION_RESULT, H)
    assert _data(sent)["active"] == H
    _via_tab(app, H, _CALCULATION_RESULT)

    assert _data(sent)["active"] == _CALCULATION_RESULT
    assert app.segmented_control(key="unit_capacity_view_mode").value == "STEP별"
    assert app.selectbox(key="unit_capacity_detail_level").value == "양산"


def test_closing_a_background_tab_keeps_the_page_and_its_conditions(
    _app: AppTest, sent: list[dict[str, Any]]
) -> None:
    """다른 탭을 닫아도 지금 화면은 그대로이고, 닫은 화면을 다시 열면 보던 조건이 이어진다."""
    app = _ok(_app.run())
    _ok(app.switch_page(_CALCULATION_RESULT).run())
    _ok(app.segmented_control(key="unit_capacity_view_mode").set_value("STEP별").run())
    _via_tab(app, _CALCULATION_RESULT, H)

    # `_on_close(산출 결과)` 를 HOME 에서 누른 결과 — 목록에서만 빠지고 이동은 없다.
    app.session_state[PAGE_TABS_OPEN_KEY] = (H,)
    _ok(app.switch_page(H).run())
    assert _ids(sent) == [H] and _data(sent)["active"] == H

    _ok(app.switch_page(_CALCULATION_RESULT).run())
    assert _ids(sent) == [H, _CALCULATION_RESULT]
    assert app.segmented_control(key="unit_capacity_view_mode").value == "STEP별"


def test_the_scenario_management_tab_is_remembered_across_a_tab_round_trip(
    _app: AppTest, sent: list[dict[str, Any]]
) -> None:
    from capa_simulation.components.tab_state import remembered_tab_key

    key = "scenario_management_tabs"
    app = _ok(_app.run())
    _ok(app.switch_page(B).run())
    labels = [tab.label for tab in app.tabs]
    query = next(label for label in labels if "BigDataQuery" in label)
    app.session_state[key] = query
    _ok(app.switch_page(B).run())
    assert app.session_state[remembered_tab_key(key)] == query

    _via_tab(app, B, H)
    _via_tab(app, H, B)

    assert app.session_state[remembered_tab_key(key)] == query
    assert app.session_state[key] == query
