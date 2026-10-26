# Purpose: 시나리오 목록 「변경 저장」·리비전 「이름 저장」 더블클릭 뒤 성공 알림이 남는지 본다.

"""시나리오 관리 › 시뮬레이션 시나리오 › 목록 관리의 두 저장 단추(2026-10-26 E2E).

사람 속도(0.15~0.2초)로 두 번 누르면 둘째 누름은 옛 화면의 단추에 닿는다. 저장은 한 번 되는데
둘째 회차가 첫 누름의 성공 알림을 지워 알림이 사라지거나 「고친 것이 없습니다.」 만 남았다. 둘째
누름이 닿는 꼴은 셋이다.

- **잠긴 단추** — 첫 회차가 다 돌아 단추가 잠긴 뒤 닿은 누름은 Streamlit 이 버린다. 그 회차는
  아무것도 하지 않고 앞 회차가 그린 알림만 지운다(`_press_again`).
- **열린 단추** — 첫 회차가 콜백만 마치고 화면을 다시 그리기 전에 닿은 누름은 콜백이 고친 것 없이
  돈다(`_first_callback` 로 첫 콜백만 부른 뒤 같은 화면을 보낸다).
- **끊긴 첫 콜백** — 첫 콜백이 쓴 뒤 편집을 비우기 전에 끊기면 둘째 콜백이 같은 편집을 다시 보낸다
  (목록 「변경 저장」 — 리비전명은 제 저장 판정이 이미 받는다, `tests/test_write_guard_cas.py`).

쓰기 직후 적은 알림(`write_guard.note_notice`)은 창(`TRAILING_PRESS_SECONDS`) 안이면 그 칸의
`render_flash` 가 같은 아이콘으로 다시 그린다. 창은 시험이 정한다 — 0 이면 옛 동작(알림 없음)이다.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, NamedTuple
from uuid import uuid4

import pytest
from streamlit.proto.WidgetStates_pb2 import WidgetStates
from streamlit.runtime.scriptrunner_utils.exceptions import StopException
from streamlit.runtime.state import session_state_proxy
from streamlit.runtime.state.safe_session_state import SafeSessionState
from streamlit.testing.v1 import AppTest
from test_all_pages_render import _page_script
from test_scenario_management_page import PAGE_PATH, _check_row, _shown_key
from widget_browser import BrowserTables

import capa_simulation.components.write_guard as write_guard
from capa_simulation.components.scenario_management import (
    CARD_NOTICE_KEY,
    LIST_EDITOR_KEY,
    LIST_NOTICE_KEY,
    REVISION_EDITOR_KEY,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository

LIST_SAVED = "시나리오명 1건을 저장했습니다."
SUCCESS_ICON = ":material/check_circle:"


class Pressed(NamedTuple):
    """저장 단추를 누른 화면 — 앱, 편집표 대역, 보내지 않은 누른 화면, 고친 대상 id, 저장소."""

    app: AppTest
    tables: BrowserTables
    pressed: WidgetStates
    target_id: str
    repository: DuckDBScenarioRepository


def _page(tmp_path: Path) -> tuple[str, DuckDBScenarioRepository]:
    """새 DB 로 연 시나리오 관리 화면 스크립트. DB 파일 이름은 시험마다 새로 짓는다 — 저장소 캐시
    (`get_scenario_repository`)는 경로가 열쇠라, 지운 tmp 폴더 이름이 다음 시험에 다시 쓰이면 앞
    시험의 저장소(새 파일에는 마이그레이션이 없다)를 돌려준다."""
    token = uuid4().hex
    database_path = tmp_path / f"scenario-{token}.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / f"equipment-{token}.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    return script, DuckDBScenarioRepository(database_path)


def _list_pressed(tmp_path: Path, name: str) -> Pressed:
    """목록 표 첫 행의 시나리오명을 고치고 「변경 저장」 을 누른 화면."""
    script, repository = _page(tmp_path)
    (summary,) = repository.list_scenarios()
    app = AppTest.from_string(script, default_timeout=120)
    tables = BrowserTables(app)
    tables.run()
    tables.edit(_shown_key(app, LIST_EDITOR_KEY), 0, "시나리오명", name)
    tables.run()
    assert not app.button(key="scenario_list_save").disabled
    app.button(key="scenario_list_save").click()
    return Pressed(app, tables, tables._states(), summary.scenario_id, repository)


def _revision_pressed(tmp_path: Path, name: str) -> Pressed:
    """고른 시나리오 카드 리비전 표 첫 행의 리비전명을 고치고 「이름 저장」 을 누른 화면."""
    script, repository = _page(tmp_path)
    release = repository.latest_official_release()
    assert release is not None
    app = AppTest.from_string(script, default_timeout=120)
    tables = BrowserTables(app)
    _check_row(app, release.scenario_id)
    tables.run()
    tables.edit(_shown_key(app, REVISION_EDITOR_KEY), 0, "리비전명", name)
    tables.run()
    app.button(key="scenario_card_save_names").click()
    return Pressed(app, tables, tables._states(), release.revision_id, repository)


def _name_of(case: Pressed) -> str:
    names = {item.scenario_id: item.scenario_name for item in case.repository.list_scenarios()}
    return names[case.target_id]


def _revision_name_of(case: Pressed) -> str | None:
    return case.repository.load_revision(case.target_id).revision.revision_name


def _press_again(app: AppTest, pressed: WidgetStates) -> AppTest:
    """누른 화면을 한 번 더 보낸다 — 첫 회차가 다 돈 뒤 옛 화면의 단추에 닿은 둘째 누름."""
    app._run(widget_state=pressed)
    assert not app.exception, [item.message for item in app.exception]
    return app


def _first_callback(
    app: AppTest,
    monkeypatch: pytest.MonkeyPatch,
    callback: str,
    *,
    cut_after: tuple[type, str] | None = None,
) -> None:
    """누른 화면의 콜백(`callback` 이름)만 회차 없이 부른다 — 첫 누름의 회차가 콜백을 마치고 화면을
    다시 그리기 전에 둘째 누름이 닿은 꼴이라 그 단추는 아직 열린 채 등록되어 있다.

    `cut_after` 의 (저장소 클래스, 메서드) 를 주면 그 쓰기가 끝난 바로 뒤 멈춤이 걸려 첫 콜백이 다음
    세션 칸 접근에서 `StopException` 으로 끊긴다(브라우저에서 둘째 누름이 첫 회차에 거는 멈춤).
    """
    shared = app.session_state._state
    metadata = next(
        meta
        for meta in shared._new_widget_state.widget_metadata.values()
        if getattr(meta.callback, "__name__", None) == callback
    )
    assert metadata.callback is not None
    stopped = threading.Event()

    def first_yield() -> None:
        if stopped.is_set():
            raise StopException()

    state = SafeSessionState(shared, first_yield)
    with monkeypatch.context() as patch:
        patch.setattr(session_state_proxy, "get_session_state", lambda: state)
        if cut_after is not None:
            cls, name = cut_after
            original = getattr(cls, name)

            def written(self: object, *args: Any, **kwargs: Any) -> Any:
                result = original(self, *args, **kwargs)
                stopped.set()
                return result

            patch.setattr(cls, name, written)
        try:
            metadata.callback(*(metadata.callback_args or ()), **(metadata.callback_kwargs or {}))
        except StopException:
            assert cut_after is not None and stopped.is_set()
        else:
            assert cut_after is None


def _successes(app: AppTest) -> list[tuple[str, str]]:
    """목록 결과 칸의 저장 성공 알림(글, 아이콘) — 화면의 다른 성공 상자(최신 공식 줄)는 뺀다."""
    return [
        (str(item.value), str(item.icon))
        for item in app.success
        if str(item.value).startswith("시나리오명")
    ]


# 목록 「변경 저장」 ---------------------------------------------------------------


@pytest.mark.parametrize(("window", "kept"), [(3600.0, True), (0.0, False)])
def test_a_second_press_on_the_locked_list_save_keeps_the_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, window: float, kept: bool
) -> None:
    """첫 회차가 다 돌아 「변경 저장」 이 잠긴 뒤 닿은 둘째 누름은 버려지는데, 그 회차가 앞 회차의
    「시나리오명 1건을 저장했습니다.」 를 지웠다(E2E — 0.3초 섰다가 사라짐)."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", window)
    case = _list_pressed(tmp_path, "더블클릭 이름")
    app, tables, pressed = case.app, case.tables, case.pressed
    tables.run()
    assert _successes(app) == [(LIST_SAVED, SUCCESS_ICON)]
    assert app.button(key="scenario_list_save").disabled

    _press_again(app, pressed)

    assert _successes(app) == ([(LIST_SAVED, SUCCESS_ICON)] if kept else [])
    assert [str(item.value) for item in app.info if "고친 것" in str(item.value)] == []
    assert _name_of(case) == "더블클릭 이름"


def test_a_second_press_on_the_still_open_list_save_does_not_say_nothing_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """첫 회차가 콜백만 마치고 화면을 다시 그리기 전에 닿은 둘째 누름은 열린 단추라 콜백이 고친 것
    없이 돌아 「고친 것이 없습니다.」 만 남았다. 창 안이면 방금 성공을 다시 그린다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    case = _list_pressed(tmp_path, "열린 단추 이름")
    app, pressed = case.app, case.pressed
    _first_callback(app, monkeypatch, "_save_list_edits")
    # 첫 회차가 그 알림을 이미 꺼내 그렸다.
    del app.session_state[LIST_NOTICE_KEY]

    _press_again(app, pressed)

    assert [str(item.value) for item in app.info if "고친 것" in str(item.value)] == []
    assert _successes(app) == [(LIST_SAVED, SUCCESS_ICON)]
    assert _name_of(case) == "열린 단추 이름"


def test_a_cut_first_list_save_is_finished_by_the_second_press_without_a_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """첫 콜백이 쓴 뒤 편집을 비우기 전에 끊기면 둘째 콜백이 같은 편집을 다시 보내 보고 고친 이름이
    이미 바뀌었다며 「다른 사용자가 먼저 이름을 바꿨습니다」 로 거부했다(제 저장). 같은 편집의 둘째
    누름은 저장소에 다시 가지 않고 첫 저장의 뒷정리와 알림을 잇는다(`write_guard.save_once`)."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    case = _list_pressed(tmp_path, "끊긴 저장 이름")
    app, pressed = case.app, case.pressed
    _first_callback(
        app,
        monkeypatch,
        "_save_list_edits",
        cut_after=(DuckDBScenarioRepository, "apply_scenario_list_edits"),
    )

    _press_again(app, pressed)

    assert [str(item.value) for item in app.error] == []
    assert _successes(app) == [(LIST_SAVED, SUCCESS_ICON)]
    assert app.button(key="scenario_list_save").disabled
    assert _name_of(case) == "끊긴 저장 이름"


# 리비전 「이름 저장」 -------------------------------------------------------------


def _revision_saved(app: AppTest) -> list[tuple[str, str]]:
    return [
        (str(item.value), str(item.icon))
        for item in app.success
        if str(item.value).startswith("리비전명을 저장했습니다: ")
    ]


@pytest.mark.parametrize(("window", "kept"), [(3600.0, True), (0.0, False)])
def test_a_second_press_on_the_locked_name_save_keeps_the_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, window: float, kept: bool
) -> None:
    """「이름 저장」 도 같다 — 잠긴 단추의 둘째 누름 회차가 「리비전명을 저장했습니다」 를
    지웠다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", window)
    case = _revision_pressed(tmp_path, "더블클릭 리비전")
    app, tables, pressed = case.app, case.tables, case.pressed
    tables.run()
    first = _revision_saved(app)
    assert len(first) == 1 and first[0][1] == SUCCESS_ICON
    assert app.button(key="scenario_card_save_names").disabled

    _press_again(app, pressed)

    assert _revision_saved(app) == (first if kept else [])
    assert _revision_name_of(case) == "더블클릭 리비전"


def test_a_second_press_on_the_still_open_name_save_does_not_say_nothing_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """열린 단추에 닿은 둘째 누름은 「고친 리비전명이 없습니다.」 만 남겼다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    case = _revision_pressed(tmp_path, "열린 단추 리비전")
    app, pressed = case.app, case.pressed
    _first_callback(app, monkeypatch, "_save_revision_names_clicked")
    first = app.session_state[CARD_NOTICE_KEY]
    del app.session_state[CARD_NOTICE_KEY]

    _press_again(app, pressed)

    assert [str(item.value) for item in app.info if "고친 리비전명" in str(item.value)] == []
    assert _revision_saved(app) == [(first.message, SUCCESS_ICON)]
    assert _revision_name_of(case) == "열린 단추 리비전"
