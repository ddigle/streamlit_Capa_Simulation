# Purpose: 늦게 온 옛 화면 회차 막이의 판정과 탭 · 링크 · 합쳐진 요청 · 뒤로가기 차례를 시험한다.

from __future__ import annotations

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
