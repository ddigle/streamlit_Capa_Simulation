# Purpose: 목록 「변경 저장」 더블클릭 · 끊긴 첫 저장 뒤 성공 알림과 뒷정리가 남는지 본다.

"""시나리오 관리 › Capa 시나리오 › 목록 관리의 저장 단추 하나(2026-10-26 E2E) — 시나리오명 ·
리비전명을 같은 시험에 싣는다.

사람 속도(0.15~0.2초)로 두 번 누르면 둘째 누름은 옛 화면의 단추에 닿는다. 저장은 한 번 되는데
둘째 회차가 첫 누름의 성공 알림을 지워 알림이 사라지거나 「고친 것이 없습니다.」 만 남았다. 둘째
누름이 닿는 꼴은 셋이다.

- **그린 뒤 닿은 누름** — 첫 회차가 다 돈 뒤 닿은 누름(`_press_again`). 단추를 잠그지 않으므로
  콜백이 고친 것 없이 돈다.
- **그리기 전 닿은 누름** — 첫 회차가 콜백만 마치고 화면을 다시 그리기 전에 닿은 누름은 옛 세대를
  인자로 든다(`_first_callback` 로 첫 콜백만 부른 뒤 같은 화면을 보낸다).
- **끊긴 첫 콜백** — 첫 콜백이 쓴 뒤 고침을 비우기 전에 끊기면 둘째 콜백이 같은 고침을 다시 보낸다.
  저장소에 다시 가지 않고 뒷정리(머리 띠 이름표 · 스냅샷 캐시)를 잇는다. 그 창이 지났어도 제 저장
  짝이면 뒷정리를 한다.

쓰기 직후 적은 알림(`write_guard.note_notice`)은 창(`TRAILING_PRESS_SECONDS`) 안이면 그 칸의
`render_flash` 가 같은 아이콘으로 다시 그린다. 창은 시험이 정한다 — 0 이면 옛 동작(알림 없음)이다.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, NamedTuple
from uuid import uuid4

import pytest
from alert_marks import infos, place_errors, successes
from scenario_list_fake import Calls, ListBrowser, install_fake_list_grid
from streamlit.proto.WidgetStates_pb2 import WidgetStates
from streamlit.runtime.scriptrunner_utils.exceptions import StopException
from streamlit.runtime.state import session_state_proxy
from streamlit.runtime.state.safe_session_state import SafeSessionState
from streamlit.testing.v1 import AppTest
from test_all_pages_render import _page_script
from test_scenario_management_page import PAGE_PATH, _check_row

import capa_simulation.components.write_guard as write_guard
from capa_simulation.components.scenario_management import (
    LIST_NOTICE_KEY,
    SIDE_CHANGES,
    SIDE_DETAIL,
    SIDE_KEY,
)
from capa_simulation.persistence.cache import load_scenario_snapshot
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_activation import ACTIVE_SCENARIO_LABEL_KEY

SUCCESS_ICON = ":material/check_circle:"
SAVED = {"scenario": "시나리오명 1건을 저장했습니다.", "revision": "리비전명 1건을 저장했습니다."}
KINDS = ("scenario", "revision")


class Pressed(NamedTuple):
    """저장 단추를 누른 화면 — 앱, 브라우저 대역, 보내지 않은 누른 화면, 고친 대상, 저장소."""

    app: AppTest
    browser: ListBrowser
    calls: Calls
    pressed: WidgetStates
    kind: str
    target_id: str
    repository: DuckDBScenarioRepository
    name: str


def _page(tmp_path: Path) -> tuple[str, DuckDBScenarioRepository]:
    """새 DB 로 연 시나리오 관리 화면 스크립트. DB 파일 이름은 시험마다 새로 짓는다 — 저장소 캐시
    (`get_scenario_repository`)는 경로가 열쇠라, 지운 tmp 폴더 이름이 다음 시험에 다시 쓰이면 앞
    시험의 저장소(새 파일에는 마이그레이션이 없다)를 돌려준다."""
    token = uuid4().hex
    database_path = tmp_path / f"scenario-{token}.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / f"equipment-{token}.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    return script, DuckDBScenarioRepository(database_path)


def _pressed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str, name: str) -> Pressed:
    """이름 한 칸을 고치고 「변경 저장」 을 누른 화면(아직 돌리지 않았다)."""
    script, repository = _page(tmp_path)
    release = repository.latest_official_release()
    assert release is not None
    calls = install_fake_list_grid(monkeypatch)
    app = AppTest.from_string(script, default_timeout=120)
    browser = ListBrowser(app, calls)
    _check_row(app, release.scenario_id)
    app.session_state[SIDE_KEY] = SIDE_DETAIL
    browser.run()
    if kind == "scenario":
        target = release.scenario_id
        browser.rename_scenario(target, name)
    else:
        target = release.revision_id
        browser.rename_revision(target, name)
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    browser.run()
    app.button(key="scenario_list_save").click()
    return Pressed(
        app,
        browser,
        calls,
        app._tree.get_widget_states(),
        kind,
        target,
        repository,
        name,
    )


def _stored_name(case: Pressed) -> str:
    if case.kind == "scenario":
        names = {item.scenario_id: item.scenario_name for item in case.repository.list_scenarios()}
        return names[case.target_id]
    return case.repository.load_revision(case.target_id).revision.revision_name


def _label_name(case: Pressed) -> str:
    """이 세션 머리 띠 이름표 — 첫 콜백이 끊기면 옛 이름으로 남는다."""
    label = case.app.session_state[ACTIVE_SCENARIO_LABEL_KEY]
    return str(label["scenario_name" if case.kind == "scenario" else "revision_name"])


def _cached_name(case: Pressed, database_path: str) -> str:
    release = case.repository.latest_official_release()
    assert release is not None
    snapshot = load_scenario_snapshot(database_path, release.revision_id)
    if case.kind == "scenario":
        return snapshot.scenario.scenario_name
    return snapshot.revision.revision_name


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


def _successes(app: AppTest, kind: str) -> list[tuple[str, str]]:
    """저장 성공 알림(글, 아이콘) — 화면의 다른 성공 상자는 뺀다."""
    return [
        (str(item.value), str(item.icon))
        for item in successes(app)
        if str(item.value) == SAVED[kind]
    ]


def _nothing_changed(app: AppTest) -> list[str]:
    return [str(item.value) for item in infos(app) if "고친 것" in str(item.value)]


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize(("window", "kept"), [(3600.0, True), (0.0, False)])
def test_a_second_press_after_the_first_run_keeps_the_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str, window: float, kept: bool
) -> None:
    """첫 회차가 다 돈 뒤 닿은 둘째 누름 — 단추를 잠그지 않으므로 콜백이 고친 것 없이 돈다. 창
    안이면 첫 성공이 남고 「고친 것이 없습니다.」 로 덮지 않는다(E2E — 0.3초 섰다가 사라짐). 창이
    지나면 새 누름이다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", window)
    case = _pressed(tmp_path, monkeypatch, kind, "더블클릭 이름")
    case.browser.run()
    assert _successes(case.app, kind) == [(SAVED[kind], SUCCESS_ICON)]

    _press_again(case.app, case.pressed)

    assert _successes(case.app, kind) == ([(SAVED[kind], SUCCESS_ICON)] if kept else [])
    assert _nothing_changed(case.app) == ([] if kept else ["고친 것이 없습니다."])
    assert _stored_name(case) == "더블클릭 이름"


@pytest.mark.parametrize("kind", KINDS)
def test_a_second_press_before_the_redraw_keeps_the_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    """첫 회차가 콜백만 마치고 화면을 다시 그리기 전에 닿은 둘째 누름 — 그 누름은 옛 세대를 인자로
    들어 쓰지 않는다. 창 안이면 방금 성공을 다시 그린다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    case = _pressed(tmp_path, monkeypatch, kind, "열린 단추 이름")
    _first_callback(case.app, monkeypatch, "_save_list_edits")
    # 첫 회차가 그 알림을 이미 꺼내 그렸다.
    del case.app.session_state[LIST_NOTICE_KEY]

    _press_again(case.app, case.pressed)

    assert _nothing_changed(case.app) == []
    assert _successes(case.app, kind) == [(SAVED[kind], SUCCESS_ICON)]
    assert _stored_name(case) == "열린 단추 이름"


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("window", [3600.0, 0.0])
def test_a_cut_first_save_is_finished_by_the_second_press_without_a_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str, window: float
) -> None:
    """첫 콜백이 쓴 뒤 고침을 비우기 전에 끊기면 둘째 콜백이 같은 고침을 다시 보내 「다른 사용자가
    먼저 이름을 바꿨습니다」 로 거부했다(제 저장). 창 안이면 같은 지문이라 저장소에 다시 가지 않고,
    창이 지났으면 맞추기가 「같아진 고침」 을 내어 제 저장 짝으로 알아본다 — 어느 쪽이든 뒷정리를
    잇는다. 성공 글은 표지로 다시 그려지므로 머리 띠 이름표 · 스냅샷 캐시로 뒷정리를 본다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", window)
    case = _pressed(tmp_path, monkeypatch, kind, "끊긴 저장 이름")
    database_path = str(case.repository.database_path)
    cached_before = _cached_name(case, database_path)
    assert cached_before != "끊긴 저장 이름"
    _first_callback(
        case.app,
        monkeypatch,
        "_save_list_edits",
        cut_after=(DuckDBScenarioRepository, "apply_scenario_list_edits"),
    )
    assert _stored_name(case) == "끊긴 저장 이름"
    assert _label_name(case) != "끊긴 저장 이름"

    _press_again(case.app, case.pressed)

    assert place_errors(case.app) == []
    assert _successes(case.app, kind) == [(SAVED[kind], SUCCESS_ICON)]
    assert _stored_name(case) == "끊긴 저장 이름"
    assert _label_name(case) == "끊긴 저장 이름"
    assert _cached_name(case, database_path) == "끊긴 저장 이름"


@pytest.mark.parametrize("kind", KINDS)
def test_a_cut_first_save_is_finished_by_the_next_run_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    """둘째 누름이 아닌 다른 조작이 첫 콜백을 끊어도 다음 회차 맞추기가 제 저장 짝을 알아보고
    뒷정리한다 — 머리 띠가 옛 이름으로 남지 않고, 고침은 빠진다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    case = _pressed(tmp_path, monkeypatch, kind, "다음 회차 이름")
    _first_callback(
        case.app,
        monkeypatch,
        "_save_list_edits",
        cut_after=(DuckDBScenarioRepository, "apply_scenario_list_edits"),
    )
    assert _label_name(case) != "다음 회차 이름"

    case.browser.run()

    assert _label_name(case) == "다음 회차 이름"
    assert place_errors(case.app) == []


def test_a_cut_outbox_callback_is_folded_by_the_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """콜백이 끊기면 같은 값으로는 다시 돌지 않는다(값이 바뀌어야 콜백이 돈다) — 본문 머리가 같은
    접기를 부르므로 그 회차에 반영되고, 두 번 접혀도 한 번이다."""
    from capa_simulation.components.scenario_list_grid import TABLE_KEY
    from capa_simulation.components.scenario_list_state import DRAFT_KEY

    script, repository = _page(tmp_path)
    (summary,) = repository.list_scenarios()
    calls = install_fake_list_grid(monkeypatch)
    app = AppTest.from_string(script, default_timeout=120)
    browser = ListBrowser(app, calls)
    browser.run()
    browser.prepared(
        TABLE_KEY,
        {
            "op": "name",
            "kind": "scenario",
            "id": summary.scenario_id,
            "text": "끊긴 콜백의 고침",
            "seen": summary.scenario_name,
        },
    )
    browser.run()
    draft = app.session_state[DRAFT_KEY]
    assert draft.scenarios[summary.scenario_id].text == "끊긴 콜백의 고침"
    applied = dict(draft.applied)
    browser.run()
    assert app.session_state[DRAFT_KEY].applied == applied
