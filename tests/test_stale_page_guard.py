# Purpose: 늦게 온 옛 화면 회차 막이의 판정 · 회차 차례와 읽는 Streamlit 내부를 시험한다.

from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from capa_simulation import session_slot, stale_page_guard
from capa_simulation.stale_page_guard import (
    GUARD_KEY,
    GuardRecord,
    admitted,
    body_widgets_before,
    note_body_widgets,
    note_page,
    note_switch,
    stale_target,
    stale_verdict,
)

# 화면 해시 둘 · 본문 위젯 id 와 앱 칸(`app.py` 가 페이지 밖에 그린) 위젯 id.
SPACE, EXEC = "hash-space", "hash-exec"
SPACE_BODY = frozenset({"$$ID-aa-space_floor_state_editor__g2", "$$ID-bb-space_floor_state_edit"})
EXEC_BODY = frozenset({"$$ID-cc-execution_tab"})
APP = frozenset({"$$ID-dd-page_tabs_strip", "$$ID-ee-sidebar_box"})


def test_a_page_change_request_carrying_only_app_widgets_is_not_stale() -> None:
    """사이드바 링크 · 뒤로가기는 앱 칸 값만 싣는다 — 떠났던 화면으로 돌아가는 사람의 이동이다."""
    record = GuardRecord(page=EXEC, widgets={SPACE: SPACE_BODY})

    assert stale_verdict(record, SPACE, APP) == ""


def test_an_old_page_message_carrying_its_body_widgets_goes_back_to_the_new_page() -> None:
    record = GuardRecord(page=EXEC, widgets={SPACE: SPACE_BODY, EXEC: EXEC_BODY})

    assert stale_verdict(record, SPACE, APP | SPACE_BODY) == EXEC


def test_a_switch_overwritten_before_its_run_started_is_still_the_target() -> None:
    """탭 고르기 회차가 `st.switch_page` 한 뒤 옮긴 화면 회차가 서기 전에 옛 메시지가 합쳐졌다 —
    들인 화면은 아직 떠나는 화면이지만 옮기러 간 화면이 있다."""
    record = GuardRecord(page=SPACE, pending=EXEC, widgets={SPACE: SPACE_BODY})

    assert stale_verdict(record, SPACE, APP | SPACE_BODY) == EXEC


def test_the_current_page_an_unknown_page_and_an_address_load_are_never_stale() -> None:
    record = GuardRecord(page=EXEC, widgets={SPACE: SPACE_BODY})

    assert stale_verdict(record, EXEC, APP | EXEC_BODY) == ""
    # 본문 위젯을 적지 않은 화면 — 가를 근거가 없다.
    assert stale_verdict(record, "hash-other", APP | SPACE_BODY) == ""
    # 주소로 연 회차(요청에 화면 해시가 없다).
    assert stale_verdict(record, "", APP | SPACE_BODY) == ""
    # 처음 회차 — 들인 화면이 없다.
    assert stale_verdict(GuardRecord(widgets={SPACE: SPACE_BODY}), SPACE, SPACE_BODY) == ""


def test_admitting_a_run_drops_the_pending_switch_and_keeps_an_address_load() -> None:
    record = GuardRecord(page=SPACE, pending=EXEC, widgets={SPACE: SPACE_BODY})

    assert admitted(record, EXEC) == GuardRecord(page=EXEC, widgets={SPACE: SPACE_BODY})
    assert admitted(record, "") is record


class _Ids:
    def __init__(self) -> None:
        self.ids: set[str] = set()

    def snapshot(self) -> frozenset[str]:
        return frozenset(self.ids)


class _Pages:
    def __init__(self, root: Path) -> None:
        self.intended_page_script_hash = ""
        self.pages = {
            SPACE: {"script_path": str(root / "app_pages" / "space_status.py")},
            EXEC: {"script_path": str(root / "app_pages" / "execution_management.py")},
        }

    def get_pages(self) -> dict[str, dict[str, str]]:
        return self.pages


class _Runtime:
    """가짜 실행 문맥 — 회차 요청(화면 해시 · 실은 위젯 id)을 받고 `app.py` 차례대로 막이를
    부른다."""

    def __init__(self, root: Path) -> None:
        self.ids = _Ids()
        self.pages = _Pages(root)
        self.ctx = SimpleNamespace(
            page_script_hash="",
            main_script_path=str(root / "app.py"),
            pages_manager=self.pages,
            shared=SimpleNamespace(widget_ids_this_run=self.ids),
        )
        self.incoming: frozenset[str] = frozenset()
        self.session_state: dict[str, Any] = {}

    def run(
        self, page: str, carried: frozenset[str], *, body: frozenset[str] = frozenset()
    ) -> str | None:
        """회차 하나 — 막이면 다시 보낼 경로를, 아니면 None 을 돌려주고 그 화면 본문을 돌린다."""
        self.pages.intended_page_script_hash = page
        self.incoming = carried
        self.ids.ids = set()
        target: str | None = stale_target()
        if target is not None:
            return target
        self.ctx.page_script_hash = page
        note_page()
        self.ids.ids |= set(APP)
        before = body_widgets_before()
        self.ids.ids |= set(body)
        note_body_widgets(before)
        return None


@pytest.fixture
def runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> _Runtime:
    rt = _Runtime(tmp_path)
    monkeypatch.setattr(session_slot, "st", SimpleNamespace(session_state=rt.session_state))
    monkeypatch.setattr(stale_page_guard, "get_script_run_ctx", lambda **_: rt.ctx)
    monkeypatch.setattr(stale_page_guard, "_incoming_widget_ids", lambda: rt.incoming)
    return rt


def test_a_tab_press_whose_echo_arrives_after_the_new_page_started_goes_back(
    runtime: _Runtime,
) -> None:
    """Space 편집 회차 → 탭 고르기(`st.switch_page`) → 실행 관리 회차 → 편집표 메아리(옛 Space)."""
    assert runtime.run(SPACE, APP | SPACE_BODY, body=SPACE_BODY) is None
    note_switch("app_pages/execution_management.py")
    assert runtime.run(EXEC, frozenset(), body=EXEC_BODY) is None

    assert runtime.run(SPACE, APP | SPACE_BODY) == "app_pages/execution_management.py"
    # 다시 보낸 회차는 들인다 — 막이 기록은 실행 관리 그대로다.
    assert runtime.run(EXEC, frozenset(), body=EXEC_BODY) is None
    record = runtime.session_state[GUARD_KEY]
    assert (record.page, record.pending) == (EXEC, "")


def test_an_echo_merged_into_the_switch_request_goes_back(runtime: _Runtime) -> None:
    """옮긴 화면 회차가 서기 전에 메아리가 `st.switch_page` 요청과 합쳐져 화면 주소를 덮었다."""
    assert runtime.run(SPACE, APP | SPACE_BODY, body=SPACE_BODY) is None
    note_switch("app_pages/execution_management.py")

    assert runtime.run(SPACE, APP | SPACE_BODY) == "app_pages/execution_management.py"


def test_a_sidebar_link_whose_echo_arrives_later_goes_back(runtime: _Runtime) -> None:
    """링크는 프런트가 옮기는 요청을 보낸다(앱 칸 값만) — 그 뒤 온 옛 Space 메시지는 막는다."""
    assert runtime.run(SPACE, APP | SPACE_BODY, body=SPACE_BODY) is None
    assert runtime.run(EXEC, APP, body=EXEC_BODY) is None

    assert runtime.run(SPACE, APP | SPACE_BODY) == "app_pages/execution_management.py"


def test_going_back_by_link_or_history_is_never_sent_away(runtime: _Runtime) -> None:
    assert runtime.run(SPACE, APP | SPACE_BODY, body=SPACE_BODY) is None
    assert runtime.run(EXEC, APP, body=EXEC_BODY) is None

    # 뒤로가기 · 사이드바 링크로 Space 에 돌아옴 — 앱 칸 값만 싣는다.
    assert runtime.run(SPACE, APP, body=SPACE_BODY) is None
    # 돌아온 Space 에서 칸을 고친 회차도 그대로 돈다.
    assert runtime.run(SPACE, APP | SPACE_BODY, body=SPACE_BODY) is None


def test_a_press_on_another_page_after_a_switch_is_admitted(runtime: _Runtime) -> None:
    """탭으로 옮기러 간 사이 사람이 사이드바 링크로 다른 화면을 골랐다 — 옮기러 간 화면을 걷는다."""
    assert runtime.run(SPACE, APP | SPACE_BODY, body=SPACE_BODY) is None
    note_switch("app_pages/execution_management.py")

    assert runtime.run("hash-other", APP) is None
    record = runtime.session_state[GUARD_KEY]
    assert (record.page, record.pending) == ("hash-other", "")


def test_unreadable_internals_never_send_a_run_away(
    runtime: _Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert runtime.run(SPACE, APP | SPACE_BODY, body=SPACE_BODY) is None
    assert runtime.run(EXEC, APP, body=EXEC_BODY) is None
    monkeypatch.setattr(stale_page_guard, "_incoming_widget_ids", lambda: None)

    assert runtime.run(SPACE, APP | SPACE_BODY) is None


def test_the_redirect_takes_the_tab_switch_road_keeping_the_theme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """다시 보내기는 탭 이동과 같은 길(`page_tabs_state._switch` — 테마 인자 유지)이다."""
    from capa_simulation import page_tabs_state

    switched: list[tuple[str, Any]] = []
    fake = SimpleNamespace(
        query_params={"theme": "dark"},
        switch_page=lambda page, *, query_params=None: switched.append((page, query_params)),
    )
    monkeypatch.setattr(page_tabs_state, "st", fake)

    page_tabs_state.switch_back_to("app_pages/execution_management.py")

    assert switched == [("app_pages/execution_management.py", {"theme": "dark"})]


def test_app_checks_for_stale_runs_before_navigation_and_notes_body_widgets() -> None:
    """`app.py` 차례 — 막이는 `st.navigation()` 앞(떠난 화면 주소가 기록에 쌓이지 않게), 본문 위젯은
    페이지 앞뒤."""
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")

    check = source.index("stale_target = stale_page_target()")
    assert check < source.index("st.set_page_config(") < source.index("navigation = st.navigation(")
    assert source.index("navigation = st.navigation(") < source.index("    note_page()")
    before = source.index("body_before = body_widgets_before()")
    assert before < source.index("run_core_page(") < source.index("note_body_widgets(body_before)")


def test_the_real_streamlit_internals_still_show_the_request_and_body_widgets() -> None:
    """판을 올려 Streamlit 내부가 바뀌면 막이는 말없이 꺼진다(못 읽으면 막지 않는다) — 실제 실행에서
    요청이 실은 위젯 id 와 회차에 등록한 위젯 id 를 읽는지 본다."""
    from streamlit.testing.v1 import AppTest

    def app() -> None:
        import streamlit as st

        from capa_simulation import stale_page_guard as guard

        st.session_state["probe_incoming"] = guard._incoming_widget_ids()
        before = guard.body_widgets_before()
        st.text_input("이름", key="guard_probe_text")
        st.session_state["probe_before"] = before
        st.session_state["probe_after"] = guard.body_widgets_before()

    at = AppTest.from_function(app)
    at.run()
    at.text_input(key="guard_probe_text").input("a").run()

    incoming = at.session_state["probe_incoming"]
    assert incoming is not None
    assert any(widget.endswith("guard_probe_text") for widget in incoming)
    before, after = at.session_state["probe_before"], at.session_state["probe_after"]
    assert before is not None and after is not None
    assert any(widget.endswith("guard_probe_text") for widget in after - before)


_NAV_APP = """\
import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx

from capa_simulation import stale_page_guard as guard

incoming = guard._incoming_page()
navigation = st.navigation([st.Page("app_pages/one.py"), st.Page("app_pages/two.py")])
guard.note_page()
ctx = get_script_run_ctx()
st.session_state["probe_runs"] = [
    *st.session_state.get("probe_runs", []),
    {
        "incoming": incoming,
        "run_hash": "" if ctx is None else ctx.page_script_hash,
        "incoming_path": guard._page_path(incoming) if incoming else None,
        "two_hash": guard._page_hash("app_pages/two.py"),
    },
]
before = guard.body_widgets_before()
navigation.run()
guard.note_body_widgets(before)
"""


def test_the_real_streamlit_internals_still_show_the_page_of_a_navigation_run(
    tmp_path: Path,
) -> None:
    """화면 쪽 내부 — 회차 요청의 화면 해시(`intended_page_script_hash`), `st.navigation()` 이
    적은 화면 목록의 `script_path` · 앱 스크립트 자리(`main_script_path`), 이번 회차 화면
    (`page_script_hash`)도 못 읽으면 막이가 말없이 꺼진다 — `st.navigation` 앱을 실제로 돌려
    옮긴 회차의 화면 해시 · 경로를 읽는지 본다.

    `app.py` 는 화면 해시를 경로로 바꾸는 일(`_page_path`)을 `st.navigation()` **앞**에서 한다 —
    같은 세션의 앞 회차가 적은 화면 목록을 읽는다(세션 하나가 화면 목록 칸 하나를 회차마다
    넘긴다 — 아래 마지막 단언). AppTest 는 회차마다 그 칸을 새로 만들어 여기서는 `st.navigation()`
    뒤에 읽고, 그 차례 자체는 브라우저 인수 확인(0/N)이 본다."""
    from streamlit.runtime.app_session import AppSession
    from streamlit.testing.v1 import AppTest

    pages = tmp_path / "app_pages"
    pages.mkdir()
    (pages / "one.py").write_text(
        'import streamlit as st\n\nst.text_input("하나", key="probe_one_text")\n', encoding="utf-8"
    )
    (pages / "two.py").write_text(
        'import streamlit as st\n\nst.text_input("둘", key="probe_two_text")\n', encoding="utf-8"
    )
    (tmp_path / "app.py").write_text(_NAV_APP, encoding="utf-8")

    at = AppTest.from_file(str(tmp_path / "app.py"))
    at.run()
    at.switch_page("app_pages/two.py").run()

    assert not at.exception
    first, moved = at.session_state["probe_runs"]
    # 주소로 연 첫 회차는 요청에 화면 해시가 없다(막이가 보지 않는 회차).
    assert first["incoming"] == "" and first["run_hash"]
    # 옮긴 회차 — 요청의 화면 해시가 서고, `st.navigation()` 이 정한 화면 · 경로로 찾은 화면과
    # 같다.
    assert moved["incoming"]
    assert moved["incoming"] == moved["run_hash"] == moved["two_hash"]
    assert moved["incoming_path"] == "app_pages/two.py"
    record = at.session_state[GUARD_KEY]
    assert record.page == moved["incoming"]
    assert any(widget.endswith("probe_two_text") for widget in record.widgets[moved["incoming"]])
    # 실제 서버는 세션(`AppSession`)이 가진 화면 목록 칸 하나를 회차마다 넘긴다 — 앞 회차 목록을
    # `st.navigation()` 앞에서 읽을 수 있는 까닭이다.
    assert "pages_manager=self._pages_manager" in inspect.getsource(AppSession._create_scriptrunner)
