# Purpose: Admin 「부대공정」 앱 작성 편집기 화면(그리드 넷 · 공정 더하기 · 판 만들기)이 받은 판
# 상자를 지나 적용되는 왕복과 바뀐 것 없음 · 통째 옮김 지우기 · 잠금 · 닫힌 탭 · 탭 점을 본다.

"""편집기 화면(`components/extra_process_editor.py` — 받은 판 상자는 `extra_process_admin`).

그리드는 대역(`edit_grid_fake.install_fake_edit_grid(early=True)` — 진짜처럼 출납 콜백이 회차 맨
앞에서 돈다)이다. 표 넷이 한 마운트라 op 는 종류 단추를 그 표로 옮긴 뒤 보낸다(마지막 feed 의 표 ·
`gen`). 쓰기 잠금은 C-DEP 꼴을 흉내 내 갈아 끼운다(`write_lock_reason`). 빈 시작(판 없음)이 주
길이라 첫 시험은 판이 없는 DB 에서 출발한다. 견본 판(판 1)의 두 공정은 모두 통째 옮김이다.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from alert_marks import alert_notes, flashed
from auto_update_fakes import new_repository
from edit_grid_fake import FAKE_EVENT_KEY, Calls, deliver_ops, install_fake_edit_grid, last, outbox
from streamlit.testing.v1 import AppTest
from test_extra_process_registration import apply_template

from capa_simulation.components import extra_process_editor as editor
from capa_simulation.components.extra_process_admin import (
    APPLY_BUTTON_KEY,
    IGNORED_PART,
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
NO_SCENARIO_KEY = "__editor_no_scenario__"
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
    if not st.session_state.get({NO_SCENARIO_KEY!r}):
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


def _app(database: Path, *, open_place: bool = True, no_scenario: bool = False) -> AppTest:
    app = AppTest.from_string(_script(database), default_timeout=120)
    app.session_state[OPEN_KEY] = open_place
    app.session_state[HIDDEN_KEY] = False
    app.session_state[NO_SCENARIO_KEY] = no_scenario
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
    # 공정이 없어도 머리 줄만 든 표가 서서 「공정 없음」 이 보인다(UI-LAY-10). 옮김 줄이 없으면
    # 「옮김」 칸도 없다(UI-TXT-08).
    empty = _shell(calls)
    assert empty["ids"] == [] and empty["texts"]["empty"] == editor.EMPTY_LINES
    assert empty["valueCols"][0] == "공정" and editor.CARRY_COLUMN not in empty["valueCols"]
    assert empty["texts"]["rowRemoveHint"] == editor.ROW_REMOVE_HINT, "저장이 아니라 판 만들기"
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
    assert editor.CARRY_COLUMN in lines["valueCols"], "옮김 줄이 있을 때만 「옮김」 칸"

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


def test_the_entry_is_locked_without_an_active_scenario(database: Path, calls: Calls) -> None:
    """활성 시나리오가 없으면 진입을 잠근다(계획 월 · 참조공정 후보를 셀 표가 없다)."""
    app = _app(database, no_scenario=True)

    entry = app.button(key=editor.OPEN_BUTTON_KEY)
    assert entry.disabled and entry.help not in (None, editor.OPEN_HELP, NOT_PRODUCTION_REASON)


def _applied_one(app: AppTest, calls: Calls) -> AppTest:
    """빈 시작에서 공정 하나를 적용하고 다시 펼친다(그 공정은 펼친 줄 `b1` — 편집기 몫)."""
    app = _press(app, editor.OPEN_BUTTON_KEY)
    app, _ = _add_line(app)
    app = _fill_new_line(app, calls)
    app = _press(app, editor.MAKE_BUTTON_KEY)
    app = _press(app, APPLY_BUTTON_KEY)
    return _press(app, editor.OPEN_BUTTON_KEY)


def test_changing_the_reference_of_an_opened_line_keeps_its_grid_edits_undoable(
    database: Path, calls: Calls
) -> None:
    """펼친 줄의 「바꾸기」 는 양식(펼친 값)에서 바꾼다 — 그리드에서 고친 모듈수를 씨앗에 굽지 않아
    되돌리면 펼친 값으로 돌아가고, 같은 참조로 바꾼 판은 「바뀐 것 없음」 이다."""
    app = _applied_one(_app(database), calls)
    assert _shell(calls)["ids"] == ["b1"]
    app = _send(app, calls, _write(["b1"], ["모듈수"], [[5]]))
    app.selectbox(key=editor.LINE_PICK_KEY).select("b1")
    app = _press(_run(app), editor.LINE_BUTTON_KEY)
    assert app.session_state[editor.LINES_KEY]["b1"][3] == 2.0

    app = _send(app, calls, {"op": "undo"})
    assert (
        editor.LINE_CELLS_KEY not in app.session_state
        or not app.session_state[editor.LINE_CELLS_KEY]
    )
    assert not _dirty(app)
    app = _press(app, editor.MAKE_BUTTON_KEY)
    assert _staged(app) is None
    assert any(editor.UNCHANGED_EDITOR in text for text in _flashes(app))


def test_a_module_count_change_is_a_changed_cell_not_a_memo_only_change(
    database: Path, calls: Calls
) -> None:
    """「01 메모 · 차례만 바뀜」 은 칸 · 공정이 그대로일 때만 — 모듈수는 바뀐 칸이다."""
    app = _applied_one(_app(database), calls)
    app = _send(app, calls, _write(["b1"], ["모듈수"], [[5]]))
    app = _press(app, editor.MAKE_BUTTON_KEY)

    staged = _staged(app)
    assert staged is not None and staged.changes is not None
    assert staged.changes.changed_cells == 1
    assert not any(ORDER_ONLY_PART in text for text in _captions(app))


def test_cells_left_outside_the_route_are_counted_on_the_value_line(
    database: Path, calls: Calls
) -> None:
    """경로를 줄여 판에 들지 않게 된 칸 입력은 지우지 않고(경로를 다시 넓히면 산다) 값 줄
    「판에 안 든 칸 입력 n」 으로 센다."""
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    app, _ = _add_line(app)
    app = _fill_new_line(app, calls)
    app = _kind(app, "생산성")
    columns = _shell(calls)["valueCols"]
    last_month = [name for name in columns if not name.endswith("~")][-1]
    app = _send(app, calls, _write(["n1|03|양산|UPEH"], [last_month], [[40000]]))
    first = app.session_state[editor.COLUMNS_KEY][columns[0]][1]
    app = _kind(app, "공정")
    app = _send(app, calls, _write(["n1"], ["끝월"], [[str(first)]]))

    app = _press(app, editor.MAKE_BUTTON_KEY)

    staged = _staged(app)
    assert staged is not None and staged.applicable and staged.editor is not None
    assert staged.editor.ignored == 1
    assert any(IGNORED_PART.format(n="1") in text for text in _captions(app))


# --------------------------------------------------------------------------- 받은 판 · 초안 맞춤


def _applied_versions(database: Path) -> int:
    return len(DuckDBScenarioRepository(database).load_extra_process_state().history)


def test_a_pack_made_before_more_edits_is_taken_back_so_apply_cannot_drop_them(
    database: Path, calls: Calls
) -> None:
    """판을 만든 뒤 표를 더 고치면 받은 판을 걷는다 — 두면 「새 판 적용」 이 만든 때의 판을 넣고
    작성을 닫아 그 뒤 고친 칸을 말없이 버린다. 칸 고침과 「새 판 적용」 누름이 한 회차에 와도
    같다(그 누름은 닿지 않는다)."""
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    app, _ = _add_line(app)
    app = _fill_new_line(app, calls)
    app = _press(app, editor.MAKE_BUTTON_KEY)
    assert _staged(app) is not None
    app = _kind(app, "생산성")
    first = _shell(calls)["valueCols"][0]

    app = _send(app, calls, _write(["n1|03|양산|UPEH"], [first], [[45000]]))

    assert _staged(app) is None and _opened(app)
    assert editor.STALE_STAGED in _all_flashes(app)

    app = _press(app, editor.MAKE_BUTTON_KEY)
    pack = _staged(app).reading.pack  # type: ignore[union-attr]
    assert pack is not None and 45000.0 in [row.upeh for row in pack.productivity]
    value = outbox(calls, _write(["n1|03|양산|UPEH"], [first], [[46000]]), host=editor.HOST)
    app.session_state[FAKE_EVENT_KEY] = (editor.HOST, value)
    app = _press(app, APPLY_BUTTON_KEY)

    assert _applied_versions(database) == 0, "같은 회차 누름은 걷힌 판에 닿지 않는다"
    assert _staged(app) is None and _opened(app)


def test_a_pack_stays_while_nothing_that_shapes_it_changes(
    database: Path, calls: Calls, window: dict[str, int]
) -> None:
    """판을 만든 뒤 종류 단추 · 시나리오(계획 월 창)만 바꾸면 받은 판은 그대로다 — 지문은 줄 ·
    걷은 뒤 남은 고침 · 00 메모라 창과 상관없다."""
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    app, _ = _add_line(app)
    app = _fill_new_line(app, calls)
    app = _press(app, editor.MAKE_BUTTON_KEY)
    made = _staged(app)
    assert made is not None

    app = _kind(app, "설비")
    window["cut"] = 3
    app = _run(app)

    assert _staged(app) is made
    assert editor.STALE_STAGED not in _all_flashes(app)


@pytest.fixture
def window(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """다른 시나리오 흉내 손잡이 — `window["cut"]` 달만큼 계획 월 끝을 뺀 맥락(이후 칸이 그만큼
    앞에 선다). 0 이면 그대로다."""
    cut = {"cut": 0}
    original = editor._context

    def shaped(repository: Any) -> Any:
        key, context = original(repository)
        if not cut["cut"]:
            return key, context
        return (*key, cut["cut"]), replace(context, months=context.months[: -cut["cut"]])

    monkeypatch.setattr(editor, "_context", shaped)
    return cut


def test_a_pack_stays_across_a_closed_tab_with_its_memo(database: Path, calls: Calls) -> None:
    """판 메모를 적고 만든 뒤 탭을 닫았다 열어도 받은 판은 그대로다 — 메모는 지문에 들고 닫힌 탭
    회차에도 남는다(`persist_state`)."""
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    app, _ = _add_line(app)
    app = _fill_new_line(app, calls)
    app.text_input(key=editor.MEMO_KEY).input("DEMO 판 메모")
    app = _press(_run(app), editor.MAKE_BUTTON_KEY)
    made = _staged(app)
    assert made is not None and made.reading.pack is not None
    assert made.reading.pack.info.memo == "DEMO 판 메모"

    app.session_state[HIDDEN_KEY] = True
    app = _run(app)
    app.session_state[HIDDEN_KEY] = False
    app = _run(app)

    assert _staged(app) is made
    assert editor.STALE_STAGED not in _all_flashes(app)


def test_the_check_table_puts_the_reason_second_and_only_table_names_in_the_table_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """「확인할 칸 n」 표 — 까닭이 둘째 칸(좁은 팝오버에서도 먼저 보임), 「표」 칸에는 표 이름만,
    등록 규칙 코드(R-xx)는 까닭 앞머리, 그 밖의 알림 갈래 낱말은 싣지 않는다."""
    from capa_simulation.services.extra_process_editor import (
        EditorWarning,
        InputProblem,
        model_from_pack,
    )

    problem = InputProblem(None, "", None, "공정", (), "공정이 하나도 없음")
    warnings = (
        EditorWarning(None, "R-02", "참조공정이 후보에 없음"),
        EditorWarning(None, "효율", "효율이 1 을 넘음"),
        EditorWarning(None, "고침", "판에 안 든 칸 입력 2칸"),
    )
    monkeypatch.setattr(editor, "input_problems", lambda model: (problem,))
    monkeypatch.setattr(editor, "editor_warnings", lambda model, context: warnings)

    frame = editor.check_frame(model_from_pack(None), None)  # type: ignore[arg-type]

    assert list(frame.columns) == ["공정", "까닭", "표", "칸", "달"]
    assert list(frame["까닭"]) == [
        "공정이 하나도 없음",
        "R-02 · 참조공정이 후보에 없음",
        "효율이 1 을 넘음",
        "판에 안 든 칸 입력 2칸",
    ]
    assert list(frame["표"]) == ["판", "공정", "효율", ""]


def _all_flashes(app: AppTest) -> list[str]:
    """다시 보낸 표지까지 든 결과 알림 글(`_send` 는 op 회차 뒤 한 번 더 돈다)."""
    return [
        str(note.get("markdown", "")) for note in alert_notes(app, again=True) if "flash" in note
    ]


def _value_draft(app: AppTest, row: str) -> dict[str, Any]:
    key = editor.PRODUCTIVITY_CELLS_KEY
    draft = app.session_state[key] if key in app.session_state else None
    return {} if not draft else dict(draft["cells"].get(row, {}))


def test_a_value_typed_in_a_shown_cell_stays_after_other_cells_change(
    database: Path, calls: Calls
) -> None:
    """걷기는 보이지 않는 칸만 — 보이는 칸에 적은 값은 그 값이 양식과 같아져도 남아, 다른 칸을
    바꾸거나 되돌린 뒤에도 사람이 적은 값이다(바탕 없는 달의 ER 따름 · 앞 달 이어 씀)."""
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    app, _ = _add_line(app)
    app = _send(app, calls, _write(["n1"], ["Area_Name", "모듈수"], [["Main", 2]]))
    app = _kind(app, "생산성")
    first, second, third = _shell(calls)["valueCols"][:3]
    mass, er = "n1|03|양산|UPEH", "n1|03|ER|UPEH"

    app = _send(app, calls, _write([er], [first], [[50]]))
    app = _send(app, calls, _write([mass], [first], [[50]]))
    app = _send(app, calls, _write([mass], [first], [[60]]))
    assert _value_draft(app, er) == {first: 50.0}, "ER 50 은 양산을 따라 60 이 되지 않는다"

    app = _send(app, calls, _write([mass], [third], [[100]]))
    app = _send(app, calls, _write([mass], [first], [[50]]))
    app = _send(app, calls, _write([mass], [second], [[100]]))
    app = _send(app, calls, {"op": "undo"})
    assert _value_draft(app, mass) == {first: 50.0, third: 100.0}, "03 에 적은 100 이 남는다"


def _late_line(app: AppTest, calls: Calls, months_after: int = 6) -> tuple[AppTest, int]:
    """시작월이 계획 끝 뒤인 새 공정 한 줄(n1) — 그 시작월."""
    app, _ = _add_line(app)
    app = _kind(app, "생산성")
    roles = app.session_state[editor.COLUMNS_KEY]
    last = max(month for kind, month in roles.values() if kind == "m")
    start = last
    for _ in range(months_after):
        start = start + 1 if start % 100 < 12 else (start // 100 + 1) * 100 + 1
    app = _kind(app, "공정")
    app = _send(
        app, calls, _write(["n1"], ["Area_Name", "모듈수", "시작월"], [["Main", 2, str(start)]])
    )
    return _kind(app, "생산성"), start


def test_an_after_cell_of_a_line_starting_past_the_plan_follows_the_window(
    database: Path, calls: Calls, window: dict[str, int]
) -> None:
    """시작월이 두 창의 계획 끝 뒤인 줄 — 창마다 이후 칸 이름이 달라도 한 열쇠라, 다른 창에서
    적은 값이 이 창 이후 칸에 보인다(보이는 값 = 판 값). 둘 다 적으면 지금 창에 보이는 쪽 하나만
    남는다."""
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    app, _ = _late_line(app, calls)
    row = "n1|03|양산|UPEH"
    wide = _shell(calls)["valueCols"][-1]
    app = _send(app, calls, _write([row], [wide], [[10]]))

    window["cut"] = 3
    app = _run(app)
    narrow = _shell(calls)["valueCols"][-1]
    assert narrow != wide and narrow.endswith("~")
    assert _value_draft(app, row) == {narrow: 10.0}, "다른 창에서 적은 값이 이 창 이후 칸에 선다"
    # 옮긴 초안은 그리드 이력 밖이다 — 옛 칸 이름을 가리킨 되돌리기는 이 창에 없는 칸이라 아무것도
    # 바꾸지 않는다(보이는 값 = 판 값은 그대로).
    app = _send(app, calls, {"op": "undo"})
    assert _value_draft(app, row) == {narrow: 10.0}

    app = _send(app, calls, _write([row], [narrow], [[20]]))
    window["cut"] = 0
    app = _run(app)
    assert _value_draft(app, row) == {wide: 20.0}, "지금 창에 보이는 칸 하나만 남는다"


def test_an_after_cell_locked_as_many_values_does_not_paint_its_old_draft(
    database: Path, calls: Calls, window: dict[str, int]
) -> None:
    """짧은 창 이후 칸에 적고, 긴 창 이후 칸에 다른 값을 적은 뒤 짧은 창으로 돌아오면 그 이후
    칸은 「여러 값」 잠김이다 — 옛 초안은 숨은 짝 칸으로 옮겨 잠긴 칸에 그리지 않고 판에는 그대로
    든다."""
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    app, _ = _add_line(app)
    app = _fill_new_line(app, calls)
    row = "n1|03|양산|UPEH"
    window["cut"] = 3
    app = _kind(app, "생산성")
    short = _shell(calls)["valueCols"][-1]
    app = _send(app, calls, _write([row], [short], [[111]]))
    window["cut"] = 0
    app = _run(app)
    full = _shell(calls)["valueCols"][-1]
    app = _send(app, calls, _write([row], [full], [[222]]))

    window["cut"] = 3
    app = _run(app)

    draft = _value_draft(app, row)
    assert short not in draft and draft[editor.hidden_after(short)] == 111.0
    app = _press(app, editor.MAKE_BUTTON_KEY)
    pack = _staged(app).reading.pack  # type: ignore[union-attr]
    assert pack is not None
    values = {row.upeh for row in pack.productivity if row.mass_class in ("양산", "모두")}
    assert {111.0, 222.0} <= values


# --------------------------------------------------------------------------- 작업 줄 · 곁 거부


def test_a_refused_add_says_why_beside_the_button_and_not_in_the_alarm(
    database: Path, calls: Calls
) -> None:
    """「공정 더하기 · 참조 바꾸기」 팝오버 안 검증 거부(참조공정 없음)는 「더하기」 바로 아래 한
    줄이고 알림창 · Alarm 에는 가지 않는다(UI-NTF-03 · UI-INP-05)."""
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    form = _new_form(app)
    app.text_input(key=f"{editor.NAME_INPUT_KEY}-{form}").input(NAME)
    app = _press(_run(app), editor.LINE_BUTTON_KEY)

    assert [str(item.value) for item in app.error] == [editor.NO_REFERENCE]
    assert editor.NO_REFERENCE not in _flashes(app)
    assert _new_form(app) == form, "거부한 누름은 줄을 더하지 않는다"


def test_adding_a_process_marks_the_close_as_losing_edits_on_the_redrawn_run(
    database: Path, calls: Calls
) -> None:
    """「더하기」 만 한 회차 — 다시 그린 회차의 「작성 닫기」 가 이미 확인 팝오버다(화면 탭 점 ·
    새로고침 확인도 같은 표지를 그 회차에 읽는다)."""
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    assert editor.CLOSE_BUTTON_KEY in [button.key for button in app.button]

    app, _ = _add_line(app)

    keys = [button.key for button in app.button]
    assert editor.CLOSE_BUTTON_KEY not in keys and editor.CLOSE_CONFIRM_KEY in keys


def test_the_make_form_names_its_memo_and_button(database: Path, calls: Calls) -> None:
    """「판 만들기」 팝오버의 메모 칸은 「판 메모 · 예: …」 안내 글로 이름을 말하고 단추는
    「만들기」 다. 팝오버가 표 위 작업 줄에 서는 자리(UI-LAY-03)는 브라우저로만 본다(AppTest 는
    배치를 재지 않는다)."""
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)

    memo = app.text_input(key=editor.MEMO_KEY)
    assert memo.placeholder == editor.MEMO_PLACEHOLDER
    assert memo.placeholder.startswith(f"{editor.MEMO_LABEL} · 예: ")
    make = app.button(key=editor.MAKE_BUTTON_KEY)
    assert make.label == editor.MAKE_BUTTON_LABEL


def test_the_guide_and_the_header_helps_say_what_the_editor_does() -> None:
    """Guide 「앱에서 작성」 · 그리드 머리 풍선이 화면과 같은 말을 한다 — ER 따름은 바탕 값이 없는
    달만, 이전 · 이후 칸은 머리 글 이름, 값 줄 · 팝오버의 낱말(UI-TXT-02 · UI-CON-02)."""
    guide = (Path(editor.__file__).parent.parent / "guides" / "admin_area.md").read_text(
        encoding="utf-8"
    )
    section = guide[guide.index("**앱에서 작성**") : guide.index("#### 공정 그룹")]
    for word in (
        "바탕 값이 없는 달",
        "판에 안 든 칸 입력",
        "Buffer 밖",
        "01 메모 · 차례만 바뀜",
        "STEP · MCP 와 다름",
        "`YY.MM~`",
        "`~YY.MM`",
    ):
        assert word in section, word
    for table, text in editor.VALUE_HELPS.items():
        assert "「YY.MM~」" in text and "이후」" not in text, table
        if table != editor.EQUIPMENT_TABLE:
            assert "바탕 값이 없는 달" in text, table
    assert IGNORED_PART.startswith("판에 안 든 칸 입력")
