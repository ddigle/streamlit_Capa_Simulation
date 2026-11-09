# Purpose: app.py 탭 줄의 data·이동·상한·자리와 탭 왕복에 남는 보기 조건을 AppTest 로 시험한다.

"""탭 줄 컴포넌트는 JS 라 AppTest 가 돌리지 못한다. 컴포넌트 한 겹만 기록 대역으로 바꿔 받은
data 를 보고, 누름은 두 겹으로 잰다 — 콜백 함수는 가짜 세션에서 직접 부르고, 콜백이 남기는
결과(목록 칸·이동 대기 칸)는 AppTest 세션에 적고 `run()` 해 `app.py` 가 실제로 옮기는지 본다.
"""

from __future__ import annotations

import json
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from capa_simulation import page_tabs_state
from capa_simulation.components import page_tabs
from capa_simulation.components.sample_data import SAMPLE_TOGGLE_KEY
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
    PAGE_TABS_ORDER_SEQ_KEY,
    PAGE_TABS_PINNED_KEY,
    PAGE_TABS_QUEUED_KEY,
    PAGE_TABS_REENTRY_KEY,
    TabStrip,
)
from capa_simulation.sidebar_status import CONDITION_DIALOG_SINK_KEY, SIDEBAR_TOGGLE_FRAGMENT_KEY

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
    """탭 이름은 「(구현중)」 을 떼고, 그 말은 이름 곁 「구현중」 표지 + 풍선이 한다(2026-11-09 보드
    T8 (가) — 본문 머리에는 배지 줄을 두지 않는다). 풍선은 선언의 원천 이름이고, 샘플을 켠 동안만
    「합성 샘플로 미리 봄」 을 붙인다."""
    app = _ok(_app.run())
    _ok(app.switch_page(WIP_STATUS.path).run())
    wip = _tab(sent, WIP_STATUS.path)
    assert wip["label"] == "표준 대비 재공 현황"
    assert wip["title"] == WIP_STATUS.title
    assert wip["wip"] == "구현 중 — 재공 실적 DB 미연결 · 화면은 합성 샘플로 미리 봄"
    assert _tab(sent, H)["wip"] == ""
    app.session_state[SAMPLE_TOGGLE_KEY] = False
    _ok(app.run())
    assert _tab(sent, WIP_STATUS.path)["wip"] == "구현 중 — 재공 실적 DB 미연결"


def test_every_implementing_screen_declares_its_pending_source_as_the_page_says_it() -> None:
    """「구현중」 표지 · 합성 샘플 표지의 선언(`PageSpec.pending_source`)은 라벨에 「(구현중)」 이
    붙은 코어 화면 모두와 Dynamic Capa 에 있고, 글자는 그 화면이 「샘플 데이터」 줄에 주는 원천
    이름과 같다 — 실적 셋은 화면 파일이 넘기는 지표 사양(`MetricSpec.source`)이 그 이름을 든다."""
    from capa_simulation.navigation import DYNAMIC_CAPA, IMPLEMENTING_SUFFIX
    from capa_simulation.services import performance_actuals

    metrics = {
        name: value
        for name, value in vars(performance_actuals).items()
        if isinstance(value, performance_actuals.MetricSpec)
    }

    suffixed = {spec.path for spec in ALL_SPECS if spec.title.endswith(IMPLEMENTING_SUFFIX)}
    declared = {spec.path for spec in ALL_SPECS if spec.pending_source is not None}
    assert declared == suffixed | {DYNAMIC_CAPA.path}
    assert all(spec.implementing for spec in ALL_SPECS if spec.path in declared)
    assert not HOME.implementing and not SPACE_STATUS.implementing
    for spec in ALL_SPECS:
        if spec.pending_source is None:
            continue
        source = (PROJECT_ROOT / spec.path).read_text(encoding="utf-8")
        given = {metric.source for name, metric in metrics.items() if name in source}
        assert f'"{spec.pending_source}"' in source or spec.pending_source in given, (
            spec.path,
            spec.pending_source,
        )


def test_the_production_progress_slots_carry_the_implementing_mark_only() -> None:
    """생산 진도 · 그 샘플 페이지 셋은 원천도 라벨 「(구현중)」 도 없지만 만드는 중인 화면이라 탭
    「구현중」 표지(풍선 「구현 중」)가 성숙도를 말한다 — 머리에는 배지 줄을 두지 않는다(2026-11-09
    보드 T8 (가)). 사이드바 라벨은 그대로이고 원천 선언이 없어 머리 띠 「합성 샘플」 표지도 서지
    않는다."""
    from capa_simulation.navigation import (
        IMPLEMENTING_SUFFIX,
        PRODUCTION_PROGRESS,
        PRODUCTION_PROGRESS_SUBPAGES,
    )

    for spec in (PRODUCTION_PROGRESS, *PRODUCTION_PROGRESS_SUBPAGES):
        assert spec.implementing and spec.in_progress, spec.path
        assert spec.pending_source is None and not spec.title.endswith(IMPLEMENTING_SUFFIX)
        assert page_tabs.wip_title(spec) == page_tabs.WIP_TITLE == "구현 중"
    assert not any(spec.in_progress for spec in ALL_SPECS if spec.pending_source is not None)


def _marks_script() -> None:
    import streamlit as st

    from capa_simulation import shared_process
    from capa_simulation.components import page_tabs
    from capa_simulation.page_tabs_state import TabStrip

    for name, args, *entered in st.session_state.pop("ops", []):
        if entered:
            getattr(shared_process, name)(*args, entered=entered[0])
        else:
            getattr(shared_process, name)(*args)
    paths = tuple(st.session_state["test_paths"])
    data = page_tabs.tabs_data(
        TabStrip(paths, frozenset({paths[0]})),
        active=paths[0],
        hrefs={path: path for path in paths},
        marks={},
        leave="",
        epoch=0,
        notice=None,
    )
    st.session_state["data"] = data


def test_screens_that_follow_the_shared_process_carry_a_funnel_mark() -> None:
    """화면 탭 표지(2026-11-09 보드 C1 (라)) — 공용 공정 값이 있을 때 따라가는 화면(선언 한 곳
    `shared_process.FOLLOWERS`)의 탭에만 선다. 아직 그리지 않은 화면은 청록(`miss` 거짓), 마지막으로
    그린 선택지에 없는 공정이 있으면 주황이고 풍선이 그 공정을 풀어 쓴다. 하나 따라감 화면은 값이
    하나일 때만 따른다."""
    from capa_simulation.navigation import CONSTRAINT_SIMULATION

    calculation = "app_pages/calculation_result.py"
    paths = [H, calculation, SPACE_STATUS.path, CONSTRAINT_SIMULATION.path]
    app = AppTest.from_function(_marks_script)
    app.session_state["test_paths"] = paths
    app.run()
    assert not app.exception
    assert [tab["proc"] for tab in app.session_state["data"]["tabs"]] == [None] * 4

    app.session_state["ops"] = [
        ("publish", (["Mold", "Underfill", "PMC"], "산출 결과")),
        ("note_drawn", ("Space", "multi", ["Mold", "Underfill", "Die Attach"])),
    ]
    app.run()
    tabs = {tab["id"]: tab["proc"] for tab in app.session_state["data"]["tabs"]}
    assert tabs[H] is None
    assert tabs[calculation] == {
        "miss": False,
        "title": "공정 Mold · Underfill · PMC — 산출 결과 에서",
    }
    assert tabs[SPACE_STATUS.path] == {
        "miss": True,
        "title": "공정 Mold · Underfill — 산출 결과 에서\nPMC 는 이 화면에 없음",
    }
    assert tabs[CONSTRAINT_SIMULATION.path] is None
    first = app.session_state["data"]
    app.run()
    assert app.session_state["data"] == first

    app.session_state["ops"] = [("pick_single", ("제약 시뮬레이션", "Mold"))]
    app.run()
    tabs = {tab["id"]: tab["proc"] for tab in app.session_state["data"]["tabs"]}
    assert tabs[CONSTRAINT_SIMULATION.path] == {
        "miss": False,
        "title": "공정 Mold — 제약 시뮬레이션 에서",
    }

    # 하나 고름 화면이 들어온 길로 다른 공정을 보고 있으면 걸린 것이 아니다 — 표지가 없다.
    app.session_state["ops"] = [
        ("follow_single", ("제약 시뮬레이션", ["WF", "Mold"]), True),
        ("note_drawn", ("제약 시뮬레이션", "single", ["WF", "Mold"], "WF")),
    ]
    app.run()
    tabs = {tab["id"]: tab["proc"] for tab in app.session_state["data"]["tabs"]}
    assert tabs[CONSTRAINT_SIMULATION.path] is None


def test_a_queued_tab_switches_the_page(_app: AppTest, sent: list[dict[str, Any]]) -> None:
    app = _ok(_app.run())
    _ok(app.switch_page(A).run())

    app.session_state[PAGE_TABS_QUEUED_KEY] = H
    _ok(app.run())

    assert _data(sent)["active"] == H
    assert [element.value for element in app.title][:1] == ["Capa LOB Summary"]
    assert PAGE_TABS_QUEUED_KEY not in app.session_state
    assert _ids(sent) == [H, A]


def test_a_tab_pressed_while_home_computes_moves_before_home_computes_again(
    _app: AppTest, sent: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """HOME 계산 중에 누른 탭은 서버가 곧바로 세운 새 회차(`runner.fastReruns`)의 맨 앞
    (`st.navigation()` 바로 뒤)에서 옮긴다 — 그 회차는 HOME 본문(`get_home_simulation`)을 부르지
    않는다(사내 리뷰 202610271800 발견 3). 콜백이 적은 대기 칸을 그 회차에 적어 재현한다."""
    import capa_simulation.services.simulation_cache as simulation_cache

    app = _ok(_app.run())
    _ok(app.switch_page(A).run())
    _ok(app.switch_page(H).run())
    assert _data(sent)["active"] == H

    calls: list[str] = []
    original = simulation_cache.get_home_simulation

    def counted(**kwargs: Any) -> Any:
        calls.append("home")
        return original(**kwargs)

    monkeypatch.setattr(simulation_cache, "get_home_simulation", counted)
    app.session_state[PAGE_TABS_QUEUED_KEY] = A
    _ok(app.run())

    assert _data(sent)["active"] == A
    assert calls == []
    # 대조 — HOME 을 그리는 회차는 그 계산을 부른다(위 빈 목록이 헛것이 아니다).
    _ok(app.switch_page(H).run())
    assert calls == ["home"]


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

    def schema_warning(notice: object, **_: object) -> None:
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
    keys = (
        PAGE_TABS_OPEN_KEY,
        PAGE_TABS_PINNED_KEY,
        PAGE_TABS_EPOCH_KEY,
        PAGE_TABS_QUEUED_KEY,
        PAGE_TABS_ORDER_SEQ_KEY,
    )
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


def test_moving_a_tab_through_the_app_keeps_the_new_order_and_the_page(
    _app: AppTest, sent: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """끌어서 차례 바꾸기(2026-11-02 사용자 요청) — 고정하지 않은 탭을 옮긴 그림(`order`)이 오면
    다음 회차의 data 가 그 차례와 받은 번호(`seq`)를 싣고, 지금 화면은 그대로다. 고정 탭(HOME)은
    그림이 어디에 두든 고정 묶음에 남는다."""
    app = _ok(_app.run())
    _ok(app.switch_page(A).run())
    _ok(app.switch_page(B).run())
    assert _ids(sent) == [H, A, B] and _data(sent)["seq"] == 0

    _press(
        app, monkeypatch, page_tabs._on_move, {"move": {"order": [H, B, A], "pins": [H], "seq": 1}}
    )
    _ok(app.switch_page(B).run())
    assert _ids(sent) == [H, B, A] and _data(sent)["active"] == B and _data(sent)["seq"] == 1

    _press(
        app, monkeypatch, page_tabs._on_move, {"move": {"order": [A, B, H], "pins": [H], "seq": 2}}
    )
    _ok(app.switch_page(B).run())
    assert _ids(sent) == [H, A, B] and _data(sent)["seq"] == 2


@pytest.fixture
def strip_session(monkeypatch: pytest.MonkeyPatch) -> tuple[SimpleNamespace, list[tuple[str, ...]]]:
    """가짜 세션 위의 탭 콜백과, 빈 프래그먼트 다시 돌리기(`rerun_fragment_if_alone`) 기록."""
    fake = SimpleNamespace(session_state={})
    monkeypatch.setattr(page_tabs, "st", fake)
    monkeypatch.setattr(page_tabs_state, "st", fake)
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(page_tabs, "rerun_fragment_if_alone", lambda *args: calls.append(args))
    page_tabs_state.store_strip(TabStrip((H, A, B), frozenset({H})))
    return fake, calls


_SINK = (SIDEBAR_TOGGLE_FRAGMENT_KEY, PAGE_TABS_COMPONENT_KEY)


def test_strip_only_presses_rerun_only_the_empty_fragment(
    strip_session: tuple[SimpleNamespace, list[tuple[str, ...]]],
) -> None:
    """고정·차례·다른 탭 닫기는 화면을 옮기지 않는다 — JS 가 누르자마자 그린 차례(`order`·`pins`)와
    서버 목록이 같으면 페이지를 다시 돌리지 않고 빈 프래그먼트만 돌린다(2026-11-02 사용자 요청 — 핀
    고정에 HOME 진행 막대가 떴다)."""
    fake, calls = strip_session
    state = fake.session_state

    state[PAGE_TABS_COMPONENT_KEY] = {
        "pin": {"id": B, "pinned": True, "order": [H, B, A], "pins": [H, B], "epoch": 1}
    }
    page_tabs._on_pin()
    assert state[PAGE_TABS_OPEN_KEY] == (H, B, A) and state[PAGE_TABS_PINNED_KEY] == (H, B)
    assert calls == [_SINK]

    state[PAGE_TABS_COMPONENT_KEY] = {
        "pin": {"id": B, "pinned": False, "order": [H, B, A], "pins": [H], "epoch": 1}
    }
    page_tabs._on_pin()
    state[PAGE_TABS_COMPONENT_KEY] = {
        "move": {"order": [H, A, B], "pins": [H], "seq": 1, "epoch": 1}
    }
    page_tabs._on_move()
    assert state[PAGE_TABS_OPEN_KEY] == (H, A, B)
    assert calls == [_SINK] * 3

    # 지금 탭(B)이 아닌 탭 닫기도 화면을 옮기지 않는다.
    state[PAGE_TABS_COMPONENT_KEY] = {"close": {"id": A, "order": [H, B], "pins": [H], "epoch": 1}}
    page_tabs._on_close(B)
    assert state[PAGE_TABS_OPEN_KEY] == (H, B)
    assert PAGE_TABS_QUEUED_KEY not in state
    assert calls == [_SINK] * 4


def test_a_drawing_the_server_did_not_take_resyncs_through_a_full_run(
    strip_session: tuple[SimpleNamespace, list[tuple[str, ...]]],
) -> None:
    """서버 목록이 JS 그림과 다르면(그 사이 목록이 바뀌어 서버가 받지 않았다) 프래그먼트만 돌리지
    않는다 — 앱 전체 회차가 탭 줄 data 로 다시 그린다. 목록이 그대로여도 epoch 를 올려 그 data 가
    달라지게 한다."""
    fake, calls = strip_session
    state = fake.session_state
    epoch = state[PAGE_TABS_EPOCH_KEY]

    state[PAGE_TABS_COMPONENT_KEY] = {
        "move": {"order": ["app_pages/gone.py", H, A, B], "pins": [H], "seq": 1, "epoch": 1}
    }
    page_tabs._on_move()
    assert state[PAGE_TABS_OPEN_KEY] == (H, A, B)
    assert state[PAGE_TABS_EPOCH_KEY] == epoch + 1
    # 차례 정보가 없는 트리거(옛 탭 줄)도 앱 전체 회차다.
    state[PAGE_TABS_COMPONENT_KEY] = {"pin": {"id": A, "pinned": True, "epoch": 1}}
    page_tabs._on_pin()
    assert state[PAGE_TABS_OPEN_KEY] == (H, A, B) and state[PAGE_TABS_PINNED_KEY] == (H, A)
    # 지금 탭 닫기는 화면을 옮긴다 — 대기 칸에 이웃을 적고 앱 전체 회차다.
    state[PAGE_TABS_COMPONENT_KEY] = {
        "close": {"id": B, "order": [H, A], "pins": [H, A], "epoch": 1}
    }
    page_tabs._on_close(B)
    assert state[PAGE_TABS_QUEUED_KEY] == A
    assert calls == []


def test_a_batched_order_is_adopted_whole_and_the_same_order_writes_nothing(
    strip_session: tuple[SimpleNamespace, list[tuple[str, ...]]],
) -> None:
    """연달아 옮긴 차례는 JS 가 묶어 마지막 그림 하나로 보낸다(2026-11-03 사용자 검수 — 연달아
    옮기면 불필요한 로딩). 서버는 한 칸씩을 다시 밟지 않고 그림 전체를 입힌다 — 그 사이 빠진 누름이
    있어도 마지막 그림이 선다. 같은 차례면 목록 칸·epoch 를 건드리지 않고, 어느 쪽이든 빈
    프래그먼트만 돈다. 받은 번호는 더 큰 것만 적는다."""
    fake, calls = strip_session
    state = fake.session_state
    state[PAGE_TABS_OPEN_KEY] = (H, A, B, SPACE_STATUS.path, WIP_STATUS.path)
    epoch = state[PAGE_TABS_EPOCH_KEY]
    s, w = SPACE_STATUS.path, WIP_STATUS.path

    # 끝 탭(w)을 다섯 칸 왼쪽으로 옮긴 마지막 그림 — 한 번에 선다.
    state[PAGE_TABS_COMPONENT_KEY] = {"move": {"order": [H, w, A, B, s], "pins": [H], "seq": 7}}
    page_tabs._on_move()
    assert state[PAGE_TABS_OPEN_KEY] == (H, w, A, B, s)
    assert state[PAGE_TABS_EPOCH_KEY] == epoch + 1 and state[PAGE_TABS_ORDER_SEQ_KEY] == 7
    assert calls == [_SINK]

    # 같은 그림이 다시 오면 아무것도 적지 않는다. 늦게 닿은 앞 번호는 번호를 되돌리지 않는다.
    state[PAGE_TABS_COMPONENT_KEY] = {"move": {"order": [H, w, A, B, s], "pins": [H], "seq": 3}}
    page_tabs._on_move()
    assert state[PAGE_TABS_EPOCH_KEY] == epoch + 1 and state[PAGE_TABS_ORDER_SEQ_KEY] == 7
    assert calls == [_SINK] * 2

    # HOME 을 고정 묶음 뒤로 둔 그림이어도 고정은 서버 것 — HOME 은 왼쪽에 남는다.
    state[PAGE_TABS_COMPONENT_KEY] = {"move": {"order": [A, H, w, B, s], "pins": [H], "seq": 8}}
    page_tabs._on_move()
    assert state[PAGE_TABS_OPEN_KEY] == (H, A, w, B, s)


def test_pin_close_and_select_take_an_unsent_order_along(
    strip_session: tuple[SimpleNamespace, list[tuple[str, ...]]],
) -> None:
    """쉼이 끝나기 전에 고정·닫기·고르기를 누르면 그 트리거가 지금 그림(`order`)과 번호를 싣는다 —
    서버는 그 차례를 먼저 입힌 뒤 고정·닫기·옮기기를 한다(`_adopted`). 차례를 따로 보내지 않아도 그
    그림이 목록에 들어가고, 그림과 같으면 페이지를 다시 돌리지 않는다."""
    fake, calls = strip_session
    state = fake.session_state
    s = SPACE_STATUS.path
    state[PAGE_TABS_OPEN_KEY] = (H, A, B, s)

    # B 를 A 앞으로 옮긴 채(보내지 않음) s 를 고정 — 그림 [H, s, B, A].
    state[PAGE_TABS_COMPONENT_KEY] = {
        "pin": {"id": s, "pinned": True, "order": [H, s, B, A], "pins": [H, s], "seq": 1}
    }
    page_tabs._on_pin()
    assert state[PAGE_TABS_OPEN_KEY] == (H, s, B, A) and calls == [_SINK]

    # A 를 B 앞으로 되돌린 채(보내지 않음) 지금 탭이 아닌 s 의 고정을 풀고 닫기 — 그림 [H, A, B].
    state[PAGE_TABS_PINNED_KEY] = (H,)
    state[PAGE_TABS_COMPONENT_KEY] = {"close": {"id": s, "order": [H, A, B], "pins": [H], "seq": 2}}
    page_tabs._on_close(B)
    assert state[PAGE_TABS_OPEN_KEY] == (H, A, B) and calls == [_SINK] * 2

    # B 를 앞으로 옮긴 채 A 를 고르면 — 옮기기 전에 그 차례가 들어간다.
    state[PAGE_TABS_COMPONENT_KEY] = {
        "select": {"id": A, "order": [H, B, A], "pins": [H], "seq": 3}
    }
    page_tabs._on_select()
    assert state[PAGE_TABS_OPEN_KEY] == (H, B, A) and state[PAGE_TABS_QUEUED_KEY] == A
    assert state[PAGE_TABS_ORDER_SEQ_KEY] == 3
    # 차례를 싣지 않은 고르기(담긴 차례 없음)는 목록을 그대로 둔다.
    state[PAGE_TABS_COMPONENT_KEY] = {"select": {"id": B, "epoch": 4}}
    page_tabs._on_select()
    assert state[PAGE_TABS_OPEN_KEY] == (H, B, A) and state[PAGE_TABS_QUEUED_KEY] == B


def test_closing_the_active_tab_right_after_moving_it_goes_to_the_drawn_neighbour(
    strip_session: tuple[SimpleNamespace, list[tuple[str, ...]]],
) -> None:
    """지금 탭을 옮긴 직후(쉼 안 — 차례를 아직 보내지 않음) 닫으면 이웃은 사용자가 본 그림의
    오른쪽 이웃이다. 탭 줄 JS 는 닫는 탭을 숨기기 전에 그림을 담아 그 탭이 제자리에 있고, 서버는
    그 차례를 먼저 입힌 뒤 닫는다(`_on_close`). 서버 목록으로 이웃을 고르면 옮기기 전 자리의
    이웃으로 갔다."""
    fake, _calls = strip_session
    state = fake.session_state
    s = SPACE_STATUS.path
    state[PAGE_TABS_OPEN_KEY] = (H, A, B, s)

    # 끝 탭 s 를 A 앞으로 옮긴 그림 [H, s, A, B] 에서 지금 탭 s 를 닫는다 — 오른쪽 이웃 A 로.
    state[PAGE_TABS_COMPONENT_KEY] = {
        "close": {"id": s, "order": [H, s, A, B], "pins": [H], "seq": 5, "epoch": 1}
    }
    page_tabs._on_close(s)
    assert state[PAGE_TABS_OPEN_KEY] == (H, A, B)
    assert state[PAGE_TABS_QUEUED_KEY] == A
    assert state[PAGE_TABS_ORDER_SEQ_KEY] == 5


def test_closing_a_background_tab_with_the_drawing_that_still_holds_it_keeps_the_page(
    strip_session: tuple[SimpleNamespace, list[tuple[str, ...]]],
) -> None:
    """탭 줄 JS 는 닫는 탭을 숨기기 전에 그림을 담아 그 그림에 닫는 탭이 아직 있다. 지금 탭이 아닌
    탭을 닫으면 서버는 닫은 탭을 뺀 그림으로 맞대 같으면 빈 프래그먼트만 돌린다 — 그대로 맞대면 늘
    어긋나 epoch 를 올리고 앱 전체 회차로 갔다(HOME 진행 막대 · 본문 흐림)."""
    fake, calls = strip_session
    state = fake.session_state
    s = SPACE_STATUS.path
    state[PAGE_TABS_OPEN_KEY] = (H, A, B, s)
    epoch = state[PAGE_TABS_EPOCH_KEY]

    # s 를 A 앞으로 옮긴 채(보내지 않음) 지금 탭(B)이 아닌 A 를 닫는다 — 그림 [H, s, A, B].
    state[PAGE_TABS_COMPONENT_KEY] = {
        "close": {"id": A, "order": [H, s, A, B], "pins": [H], "seq": 6, "epoch": 1}
    }
    page_tabs._on_close(B)
    assert state[PAGE_TABS_OPEN_KEY] == (H, s, B)
    assert PAGE_TABS_QUEUED_KEY not in state
    assert state[PAGE_TABS_EPOCH_KEY] == epoch + 1 and state[PAGE_TABS_ORDER_SEQ_KEY] == 6
    assert calls == [_SINK]

    # 옮긴 것 없이 닫아도 같다. 닫을 수 없는 고정 탭(H)은 목록에 남아 그림 그대로 맞댄다.
    state[PAGE_TABS_COMPONENT_KEY] = {"close": {"id": s, "order": [H, s, B], "pins": [H], "seq": 7}}
    page_tabs._on_close(B)
    state[PAGE_TABS_COMPONENT_KEY] = {"close": {"id": H, "order": [H, B], "pins": [H], "seq": 8}}
    page_tabs._on_close(B)
    assert state[PAGE_TABS_OPEN_KEY] == (H, B) and PAGE_TABS_QUEUED_KEY not in state
    assert calls == [_SINK] * 3


def _live_strip(monkeypatch: pytest.MonkeyPatch) -> None:
    """탭 줄을 이 AppTest 회차 **안에서** 등록해 진짜 트리거 칸을 세운다. 모듈을 읽을 때 등록한 것은
    AppTest 실행 밖이라 그 실행에서 「미등록」이다(모듈 설명)."""
    assets = page_tabs._ASSETS

    def live(**kwargs: Any) -> Any:
        component = st.components.v2.component(
            "capa_page_tabs",
            html=(assets / "page_tabs.html").read_text(encoding="utf-8"),
            css=(assets / "page_tabs.css").read_text(encoding="utf-8"),
            js=(assets / "page_tabs.js").read_text(encoding="utf-8"),
        )
        return component(**kwargs)

    monkeypatch.setattr(page_tabs, "_PAGE_TABS", live)


def _strip_widget_id(app: AppTest) -> str:
    for element in app._tree.children[0].children.values():
        proto = getattr(element, "proto", None)
        widget_id = str(getattr(proto, "id", ""))
        if getattr(element, "type", None) == "bidi_component" and widget_id.endswith(
            f"-{PAGE_TABS_COMPONENT_KEY}"
        ):
            return widget_id
    raise AssertionError("탭 줄 부품이 그려지지 않았다")


def _press_strip(app: AppTest, event: str, value: dict[str, Any]) -> None:
    """브라우저처럼 탭 줄 트리거 하나를 보낸 회차 — AppTest 는 Components v2 트리거를 보내지 못해
    위젯 상태에 상태 칸(바뀌지 않음)과 트리거 모음 칸(Streamlit `_make_trigger_id(<부품 id>,
    "events")`)을 더해 돌린다."""
    from streamlit.components.v2.bidi_component.main import _make_trigger_id
    from streamlit.proto.WidgetStates_pb2 import WidgetState

    strip_id = _strip_widget_id(app)
    events_id = _make_trigger_id(strip_id, "events")
    states = app._tree.get_widget_states()
    states.widgets.append(WidgetState(id=strip_id, json_value="{}"))
    states.widgets.append(
        WidgetState(id=events_id, json_trigger_value=json.dumps([{"event": event, "value": value}]))
    )
    app._run(states)


def test_pinning_on_a_finished_home_reruns_only_the_empty_fragment(
    _app: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """진짜 프래그먼트 회차로 본다 — HOME 이 끝까지 돈 뒤 다른 탭을 고정하면 콜백만 도는 회차와 빈
    프래그먼트 회차만 돌고 HOME 본문은 다시 오지 않는다(바탕 3aad85d 는 앱 전체 회차 — 사본에서 델타
    259개·HOME 진행 막대 12/12). 고정은 세션 목록에 들어 다음 앱 전체 회차의 data 가 싣는다."""
    from fragment_browser import install_fragment_browser

    browser = install_fragment_browser(monkeypatch)
    _live_strip(monkeypatch)
    app = _ok(_app.run())
    _ok(app.switch_page(A).run())
    _ok(app.switch_page(H).run())
    sink = browser.fragment_keyed(SIDEBAR_TOGGLE_FRAGMENT_KEY)

    _press_strip(app, "pin", {"id": A, "pinned": True, "order": [H, A], "pins": [H, A], "epoch": 2})

    _ok(app)
    assert browser.started == [[], [sink]]
    assert all(
        message.delta.fragment_id
        for message in browser.messages
        if message.WhichOneof("type") == "delta"
    )
    assert app.session_state[PAGE_TABS_PINNED_KEY] == (H, A)

    # 끌어서 옮기기도 같은 길이다 — 고정을 풀고 A 를 HOME 앞에 두려 해도 고정 묶음 뒤에 선다.
    _ok(app.switch_page(H).run())
    _press_strip(app, "pin", {"id": A, "pinned": False, "order": [H, A], "pins": [H], "epoch": 3})
    assert browser.started == [[], [sink]]
    _ok(app.switch_page(B).run())
    _press_strip(app, "move", {"order": [H, B, A], "pins": [H], "seq": 1, "epoch": 4})
    assert browser.started == [[], [sink]]
    assert app.session_state[PAGE_TABS_OPEN_KEY] == (H, B, A)
    assert app.session_state[PAGE_TABS_ORDER_SEQ_KEY] == 1
    # 같은 차례가 다시 와도(서버가 이미 아는 그림) 목록 칸·epoch 는 그대로이고 빈 프래그먼트만 돈다.
    _ok(app.switch_page(B).run())
    epoch = app.session_state[PAGE_TABS_EPOCH_KEY]
    _press_strip(app, "move", {"order": [H, B, A], "pins": [H], "seq": 2, "epoch": 4})
    assert browser.started == [[], [sink]]
    assert app.session_state[PAGE_TABS_EPOCH_KEY] == epoch


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
    from capa_simulation.components.scenario_list_state import DRAFT_KEY
    from capa_simulation.services.scenario_list_edits import ListDraft, NameEdit

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
    app.session_state[DRAFT_KEY] = ListDraft(scenarios={"s1": NameEdit("옛 이름", "새 이름")})
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


_VOC_PAGE = "app_pages/voc.py"


def _kept_reply_marks_script() -> None:
    import streamlit as st

    from capa_simulation.components.change_summary import session_changes
    from capa_simulation.components.page_tabs import leave_notice, page_unsaved_marks

    page = st.session_state["test_page_file"]
    st.session_state["test_marks"] = page_unsaved_marks(page)
    st.session_state["test_leave"] = leave_notice(page)
    st.session_state["test_changes"] = session_changes(page, hrefs={"app_pages/voc.py": "voc"})


@pytest.mark.parametrize("page_file", ["home.py", "voc.py"])
def test_a_kept_voc_reply_marks_the_voc_tab_and_the_change_chip_from_any_page(
    page_file: str,
) -> None:
    """VOC 「적어 둔 답변」 은 세션 칸이라 화면을 옮겨도 남지만 새로고침 · 테마 전환에는 사라진다 —
    「잃을 것」 이다(아침 보드 X1). 어느 화면에서나 VOC 탭에 점, 머리 변경 칩 「저장 안 함」 에 한
    줄이 선다. 떠나도 남으므로 떠나기 확인 글에는 들지 않는다. 닫으면 둘 다 걷힌다."""
    from capa_simulation.components.voc_draft_keeper import KEPT_REPLY_KEY

    app = AppTest.from_function(_kept_reply_marks_script)
    app.session_state["test_page_file"] = page_file
    app.session_state[KEPT_REPLY_KEY] = ("남지 못한 답변", "또 남지 못한 답변")
    _ok(app.run())

    assert app.session_state["test_marks"] == {_VOC_PAGE: "적어 둔 답변 2건"}
    assert app.session_state["test_leave"] == ""
    assert [
        (item["group"], item["page"], item["text"], item["top"], item["href"])
        for item in app.session_state["test_changes"]
    ] == [("keep", "VOC", "적어 둔 답변 2건", "VOC 적어 둔 답변", "voc")]

    del app.session_state[KEPT_REPLY_KEY]
    _ok(app.run())
    assert app.session_state["test_marks"] == {}
    assert app.session_state["test_changes"] == []


def test_a_kept_voc_reply_marks_the_voc_tab_and_the_theme_button(
    _app: AppTest, sent: list[dict[str, Any]]
) -> None:
    """적어 둔 답변이 있으면 다른 화면에서도 VOC 탭에 점이 서고 테마 단추 · 떠나기 확인 표지가
    선다 — 새로고침 · 테마 전환이 확인 없이 지우지 않는다(아침 보드 X1)."""
    from capa_simulation.components.voc_draft_keeper import KEPT_REPLY_KEY

    app = _ok(_app.run())
    app.session_state[PAGE_TABS_OPEN_KEY] = (H, _VOC_PAGE, B)
    _ok(app.switch_page(B).run())
    assert _tab(sent, _VOC_PAGE)["dirty"] is False
    assert not _has_theme_unsaved_marker(app)

    app.session_state[KEPT_REPLY_KEY] = ("남지 못한 답변",)
    _ok(app.switch_page(B).run())
    voc = _tab(sent, _VOC_PAGE)
    assert voc["dirty"] is True
    assert voc["title"] == "VOC — 적어 둔 답변 1건"
    assert _tab(sent, B)["dirty"] is False
    assert _has_theme_unsaved_marker(app)


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
    query = next(label for label in labels if label.endswith("DB 등록"))
    app.session_state[key] = query
    _ok(app.switch_page(B).run())
    assert app.session_state[remembered_tab_key(key)] == query

    _via_tab(app, B, H)
    _via_tab(app, H, B)

    assert app.session_state[remembered_tab_key(key)] == query
    assert app.session_state[key] == query


# ------------------------------------------------------------------ 모듈 화면


def test_a_module_page_becomes_a_tab_without_server_paths(
    _app: AppTest, sent: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    from capa_simulation import module_registry, settings

    monkeypatch.setenv(
        module_registry.ROOT_ENV_VAR, str(PROJECT_ROOT / "tests" / "fixtures" / "modules")
    )
    page = "tests/fixtures/modules/demo_ok/demo_ok_page.py"
    app = _ok(_app.run())
    _ok(app.switch_page(page).run())

    assert _ids(sent) == [H, page]
    tab = _tab(sent, page)
    assert (tab["label"], tab["icon"], tab["href"]) == (
        "데모 화면",
        "extension",
        "mod-demo_ok-main",
    )
    data = _data(sent)
    assert data["active"] == page
    assert data["pages"]["mod-demo_ok-main"] == "데모 화면"
    assert len(data["pages"]) == len(ALL_SPECS) + 5
    assert str(settings.PROJECT_ROOT) not in json.dumps(data, ensure_ascii=False)
