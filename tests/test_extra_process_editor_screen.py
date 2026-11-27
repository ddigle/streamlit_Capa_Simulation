# Purpose: Admin 「부대공정」 앱 작성 편집기 화면(그리드 넷 · 공정 더하기 · 판 만들기)이 받은 판
# 상자를 지나 적용되는 왕복과 바뀐 것 없음 · 통째 옮김 지우기 · 잠금 · 닫힌 탭 · 탭 점을 본다.

"""편집기 화면(`components/extra_process_editor.py` — 받은 판 상자는 `extra_process_admin`).

그리드는 대역(`edit_grid_fake.install_fake_edit_grid(early=True)` — 진짜처럼 출납 콜백이 회차 맨
앞에서 돈다)이다. 표 넷이 한 마운트라 op 는 종류 단추를 그 표로 옮긴 뒤 보낸다(마지막 feed 의 표 ·
`gen`). 쓰기 잠금은 C-DEP 꼴을 흉내 내 갈아 끼운다(`write_lock_reason`). 빈 시작(판 없음)이 주
길이라 첫 시험은 판이 없는 DB 에서 출발한다. 견본 판(판 1)의 두 공정은 모두 통째 옮김이다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from alert_marks import flashed
from auto_update_fakes import new_repository
from edit_grid_fake import FAKE_EVENT_KEY, Calls, deliver_ops, install_fake_edit_grid, last, outbox
from streamlit.testing.v1 import AppTest
from test_extra_process_registration import apply_template

from capa_simulation.components import extra_process_editor as editor
from capa_simulation.components.extra_process_admin import (
    APPLY_BUTTON_KEY,
    NOT_PRODUCTION_REASON,
    ORDER_ONLY_PART,
    REMOVED_CONFIRM_KEY,
    STAGED_KEY,
)
from capa_simulation.extra_process_intake import StagedPack
from capa_simulation.persistence.models import EXTRA_EDITOR_PLACE, EXTRA_KIND_REVISION
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.extra_process_pack import read_pack_zip

OPEN_KEY = "__editor_open__"
HIDDEN_KEY = "__editor_hidden__"
NAME = "DEMO_New_Sort"


def _script(database: Path) -> str:
    return f"""
from pathlib import Path

import streamlit as st

import capa_simulation.components.extra_process_admin as admin
import capa_simulation.settings as settings
from capa_simulation.persistence.cache import get_scenario_repository
from capa_simulation.scenario_activation import bootstrap_latest_official_scenario

original_path = settings.DUCKDB_PATH
original_lock = admin.write_lock_reason
settings.DUCKDB_PATH = Path({str(database)!r})
if st.session_state.get({OPEN_KEY!r}):
    admin.write_lock_reason = lambda: None
try:
    bootstrap_latest_official_scenario(str(settings.DUCKDB_PATH))
    repository = get_scenario_repository(str(settings.DUCKDB_PATH))
    # 닫힌 탭 흉내 — 탭 본문을 부르지 않는다(`app_pages/admin_area.py`).
    if not st.session_state.get({HIDDEN_KEY!r}):
        admin.render_extra_process_admin(repository, alert_tab="부대공정")
finally:
    admin.write_lock_reason = original_lock
    settings.DUCKDB_PATH = original_path
"""


@pytest.fixture
def database(tmp_path: Path) -> Path:
    return tmp_path / "editor_screen.duckdb"


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> Calls:
    return install_fake_edit_grid(monkeypatch, early=True)


def _run(app: AppTest) -> AppTest:
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    return app


def _app(database: Path, *, open_place: bool = True) -> AppTest:
    app = AppTest.from_string(_script(database), default_timeout=120)
    app.session_state[OPEN_KEY] = open_place
    app.session_state[HIDDEN_KEY] = False
    return _run(app)


def _press(app: AppTest, key: str) -> AppTest:
    app.button(key=key).click()
    return _run(app)


def _kind(app: AppTest, label: str) -> AppTest:
    app.session_state[editor.KIND_KEY] = label
    return _run(app)


def _write(rows: list[str], cols: list[str], values: list[list[Any]]) -> dict[str, Any]:
    return {"op": "write", "rows": rows, "cols": cols, "values": values}


def _send(app: AppTest, calls: Calls, *ops: dict[str, Any]) -> AppTest:
    app = deliver_ops(app, calls, *ops, host=editor.HOST)
    return _run(app)


def _shell(calls: Calls) -> dict[str, Any]:
    return last(calls, editor.HOST)


def _new_form(app: AppTest) -> str:
    """새 공정 칸 key 꼬리(`form_key`) — 그 앱 세션의 씨앗으로 센 다음 줄 id."""
    seeds = app.session_state[editor.LINES_KEY] if editor.LINES_KEY in app.session_state else {}
    numbers = [int(key[1:]) for key in seeds if key.startswith("n") and key[1:].isdigit()]
    return f"n{max(numbers, default=0) + 1}"


def _add_line(app: AppTest, name: str = NAME) -> tuple[AppTest, str]:
    """「공정 더하기」 — 새 줄 이름과 첫 참조공정 후보 · 첫 조합으로 더한다(고른 참조공정을
    돌려준다)."""
    form = _new_form(app)
    app.text_input(key=f"{editor.NAME_INPUT_KEY}-{form}").input(name)
    app = _run(app)
    box = app.selectbox(key=f"{editor.REFERENCE_PICK_KEY}-{form}")
    reference = str(box.options[0])
    box.select_index(0)
    app = _run(app)
    return _press(app, editor.LINE_BUTTON_KEY), reference


def _fill_new_line(app: AppTest, calls: Calls, line: str = "n1") -> AppTest:
    """새 줄 한 달씩 — 공정 표(Area · 모듈수) · 생산성 양산 · 설비 보유 · 효율 양산 효율 · 편중률.
    바탕 없는 달은 채움이 잇는다(ER 은 양산을 따름 · 대여 0)."""
    app = _send(app, calls, _write([line], ["Area_Name", "모듈수"], [["Main", 2]]))
    app = _kind(app, "생산성")
    first = _shell(calls)["valueCols"][0]
    app = _send(app, calls, _write([f"{line}|03|양산|UPEH"], [first], [[30000]]))
    app = _kind(app, "설비")
    app = _send(app, calls, _write([f"{line}|04||설비보유"], [first], [[2]]))
    app = _kind(app, "효율")
    return _send(
        app,
        calls,
        _write(
            [f"{line}|05|양산|CAPA_RUN_RATE", f"{line}|05|양산|편중률"],
            [first],
            [[0.85], [1.0]],
        ),
    )


def _staged(app: AppTest) -> StagedPack | None:
    value = app.session_state[STAGED_KEY] if STAGED_KEY in app.session_state else None
    return value if isinstance(value, StagedPack) else None


def _opened(app: AppTest) -> bool:
    """편집기가 열려 있나(그 앱 세션의 펼친 판 칸)."""
    return (
        editor.EDITOR_KEY in app.session_state and app.session_state[editor.EDITOR_KEY] is not None
    )


def _dirty(app: AppTest) -> bool:
    """탭 점 술어(`editor_has_edits`)를 그 앱 세션에서 읽는다."""
    return (
        _opened(app)
        and editor.DIRTY_KEY in app.session_state
        and bool(app.session_state[editor.DIRTY_KEY])
    )


def _flashes(app: AppTest) -> list[str]:
    return [shown.value for shown in flashed(app)]


def _captions(app: AppTest) -> list[str]:
    return [str(item.value) for item in app.caption]


def test_an_empty_start_adds_a_process_makes_a_pack_and_applies_it(
    database: Path, calls: Calls
) -> None:
    """빈 시작(판 없음 — 주 길): 진입 → 공정 더하기 → 달 값 → 판 만들기 → 받은 판 상자 → 적용."""
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    assert _opened(app)
    # 공정이 없는 빈 표도 마운트는 선다(표 없는 껍데기 — 줄 규칙 등록).
    assert _shell(calls).get("valueCols") is None
    assert not _dirty(app)

    app, reference = _add_line(app)
    lines = _shell(calls)
    assert lines["ids"] == ["n1"] and lines["valueCols"][0] == "공정"
    assert _dirty(app), "더한 공정만으로도 펼친 판과 다르다"
    app = _fill_new_line(app, calls)

    app = _press(app, editor.MAKE_BUTTON_KEY)
    staged = _staged(app)
    assert staged is not None and staged.editor is not None and staged.applicable
    pack = staged.reading.pack
    assert pack is not None and pack.info.version_no == 1
    assert [process.name for process in pack.processes] == [NAME]
    assert [route.reference for route in pack.routes] == [reference]
    assert any(text.startswith("더한 공정 1 · 뺀 공정 0") for text in _captions(app))

    app = _press(app, APPLY_BUTTON_KEY)
    state = DuckDBScenarioRepository(database).load_extra_process_state()
    active = state.active
    assert active is not None and active.version_no == 1 and active.kind == EXTRA_KIND_REVISION
    assert active.source_place == EXTRA_EDITOR_PLACE
    assert not _opened(app), "적용하면 작성을 닫는다"
    assert any("부대공정 판 1 적용 — 앱 입력" in text for text in _flashes(app))


def test_making_an_untouched_pack_says_nothing_changed(database: Path, calls: Calls) -> None:
    """견본 판을 펼쳐 고치지 않고 판 만들기 — 받은 판을 두지 않고 「바뀐 것 없음」(UI-STA-01)."""
    apply_template(new_repository(database))
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    lines = _shell(calls)
    assert len(lines["ids"]) == 2 and lines["locks"], "견본 두 공정은 통째 옮김(잠김)"

    app = _press(app, editor.MAKE_BUTTON_KEY)

    assert _staged(app) is None
    assert any(editor.UNCHANGED_EDITOR in text for text in _flashes(app))


def test_a_carried_line_can_only_be_removed_and_its_removal_asks_to_confirm(
    database: Path, calls: Calls
) -> None:
    """통째 옮김 줄은 지우기만 열린다 — 지운 판은 「뺀 공정」 확인 칸을 채워야 적용된다."""
    apply_template(new_repository(database))
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    first, second = _shell(calls)["ids"]
    # 잠긴 칸에 쓰기는 건너뛴다(통째 옮김 — 이름을 고치지 않는다).
    app = _send(app, calls, _write([first], ["공정"], [["DEMO_RENAMED"]]))
    assert not _dirty(app)
    app = _send(app, calls, {"op": "remove", "rows": [first]})
    assert _dirty(app)

    app = _press(app, editor.MAKE_BUTTON_KEY)
    staged = _staged(app)
    assert staged is not None and staged.changes is not None
    assert len(staged.changes.removed) == 1
    pack = staged.reading.pack
    assert pack is not None and len(pack.processes) == 1
    apply = app.button(key=APPLY_BUTTON_KEY)
    assert apply.disabled, "뺀 공정을 확인하기 전에는 잠김"

    app.checkbox(key=REMOVED_CONFIRM_KEY).check()
    app = _run(app)
    app = _press(app, APPLY_BUTTON_KEY)
    active = DuckDBScenarioRepository(database).load_extra_process_state().active
    assert active is not None and active.version_no == 2 and active.process_count == 1
    assert second


def test_the_entry_and_the_make_button_are_locked_off_the_production_server(
    database: Path, calls: Calls
) -> None:
    """C-3 — C-DEP 밖(쓰기 잠금)이면 진입이 잠기고 풍선이 까닭이다. 작성 중에 잠기면 「판 만들기」
    도 잠긴다(UI-INP-07)."""
    app = _app(database, open_place=False)
    entry = app.button(key=editor.OPEN_BUTTON_KEY)
    assert entry.disabled and entry.help == NOT_PRODUCTION_REASON

    app.session_state[OPEN_KEY] = True
    app = _press(_run(app), editor.OPEN_BUTTON_KEY)
    app.session_state[OPEN_KEY] = False
    app = _run(app)
    make = app.button(key=editor.MAKE_BUTTON_KEY)
    assert make.disabled and make.help == NOT_PRODUCTION_REASON


def test_the_entry_is_locked_when_the_active_pack_cannot_be_read(
    database: Path, calls: Calls, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G1 — 판이 있는데 내용을 못 읽으면 빈 판으로 펴지 않는다(통째 교체라 공정이 모두 빠진다)."""
    apply_template(new_repository(database))
    monkeypatch.setattr(
        DuckDBScenarioRepository, "load_extra_process_content", lambda self, sha: b"broken"
    )
    app = _app(database)

    entry = app.button(key=editor.OPEN_BUTTON_KEY)
    assert entry.disabled and entry.help == editor.UNREADABLE_REASON


def test_edits_sent_while_the_tab_is_closed_are_absorbed_when_it_opens(
    database: Path, calls: Calls
) -> None:
    """닫힌 탭은 그리지 않는다 — 그 회차에 온 op 는 inbox 에 남고 다시 연 회차가 반영한다."""
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    app, _ = _add_line(app)
    value = outbox(calls, _write(["n1"], ["모듈수"], [[3]]), host=editor.HOST)

    app.session_state[HIDDEN_KEY] = True
    app.session_state[FAKE_EVENT_KEY] = (editor.HOST, value)
    app = _run(app)
    assert app.session_state[editor.INBOX_KEY], "닫힌 회차는 반영하지 않는다"
    assert _dirty(app)

    app.session_state[HIDDEN_KEY] = False
    app = _run(app)
    draft = app.session_state[editor.LINE_CELLS_KEY]
    assert draft["cells"]["n1"]["모듈수"] == 3.0
    assert editor.INBOX_KEY not in app.session_state or not app.session_state[editor.INBOX_KEY]


def test_an_edit_arriving_with_the_press_is_in_the_pack(database: Path, calls: Calls) -> None:
    """G2 — 칸 고침과 「판 만들기」 누름이 한 회차에 와도 그 고침이 판에 든다."""
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    app, _ = _add_line(app)
    app = _fill_new_line(app, calls)
    app = _kind(app, "공정")
    value = outbox(calls, _write(["n1"], ["메모"], [["DEMO 메모"]]), host=editor.HOST)

    app.session_state[FAKE_EVENT_KEY] = (editor.HOST, value)
    app = _press(app, editor.MAKE_BUTTON_KEY)

    staged = _staged(app)
    assert staged is not None and staged.reading.pack is not None
    assert [process.memo for process in staged.reading.pack.processes] == ["DEMO 메모"]


def test_the_tab_mark_follows_real_edits_not_the_draft(database: Path, calls: Calls) -> None:
    """G3 — 펼치기만은 점 없음, 한 칸 고치면 점, 그 칸을 되돌리면 걷힌다."""
    apply_template(new_repository(database))
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    assert not _dirty(app)
    app, _ = _add_line(app)
    assert _dirty(app)
    app = _send(app, calls, {"op": "remove", "rows": ["n1"]})
    assert not _dirty(app), "더한 줄을 지우면 펼친 판과 같다"
    app = _send(app, calls, {"op": "undo"})
    assert _dirty(app)


def test_a_memo_only_change_is_its_own_value_part(database: Path, calls: Calls) -> None:
    """01 메모만 바꾼 판은 칸 · 공정 수가 그대로라 값 줄에 「01 메모 · 차례만 바뀜」 이 붙는다."""
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    app, _ = _add_line(app)
    app = _fill_new_line(app, calls)
    app = _press(app, editor.MAKE_BUTTON_KEY)
    app = _press(app, APPLY_BUTTON_KEY)

    app = _press(app, editor.OPEN_BUTTON_KEY)
    (line,) = _shell(calls)["ids"]
    app = _send(app, calls, _write([line], ["메모"], [["DEMO 고친 메모"]]))
    app = _press(app, editor.MAKE_BUTTON_KEY)

    staged = _staged(app)
    assert staged is not None and staged.applicable
    assert any(ORDER_ONLY_PART in text for text in _captions(app))
    assert read_pack_zip(staged.fetch.data).pack is not None


def test_changing_the_reference_rewrites_the_route_of_that_line(
    database: Path, calls: Calls
) -> None:
    """「참조 바꾸기」 — 있는 줄을 고르고 같은 소요기준의 다른 참조공정으로 바꾸면 그 줄의 경로가
    바뀐다(고르기 값은 누름에만 든다)."""
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    app, first = _add_line(app)
    app = _fill_new_line(app, calls)
    app.selectbox(key=editor.LINE_PICK_KEY).select("n1")
    app = _run(app)
    box = app.selectbox(key=f"{editor.REFERENCE_PICK_KEY}-n1")
    assert box.value == first, "있는 줄은 지금 참조공정에서 시작한다"
    others = [str(option) for option in box.options if str(option) != first]
    if not others:
        pytest.skip("합성 표본에 같은 소요기준의 다른 참조공정이 없다")
    box.select(others[0])
    app = _run(app)
    app = _press(app, editor.LINE_BUTTON_KEY)

    app = _press(app, editor.MAKE_BUTTON_KEY)
    staged = _staged(app)
    assert staged is not None and staged.reading.pack is not None
    assert [route.reference for route in staged.reading.pack.routes] == [others[0]]


def test_a_pack_made_after_another_pack_was_applied_cannot_be_applied(
    database: Path, calls: Calls
) -> None:
    """펼친 뒤 판 이력이 움직였으면 받은 판은 적용할 수 없는 판이다(펼친 차례 대조 — 남의 판을
    말없이 지우지 않는다)."""
    repository = new_repository(database)
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    app, _ = _add_line(app)
    app = _fill_new_line(app, calls)
    apply_template(repository)

    app = _press(app, editor.MAKE_BUTTON_KEY)

    staged = _staged(app)
    assert staged is not None and staged.judgement is not None
    assert not staged.applicable and staged.judgement.reason == editor.MOVED_REASON
    assert [str(item.value) for item in app.error] == [editor.MOVED_REASON]
