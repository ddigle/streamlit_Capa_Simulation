# Purpose: Admin 「부대공정」 앱 작성 편집기 화면(그리드 넷 · 새 줄 · 참조 후보 · 판 만들기)이
# 받은 판 상자를 지나 적용되는 왕복과 양식 · 바뀐 것 없음 · 통째 옮김 지우기 · 잠금 · 닫힌 탭 ·
# 탭 점을 본다.

"""편집기 화면(`components/extra_process_editor.py` — 받은 판 상자는 `extra_process_admin`).

그리드는 대역(`edit_grid_fake.install_fake_edit_grid(early=True)` — 진짜처럼 출납 콜백이 회차 맨
앞에서 돈다)이다. 표 넷이 한 마운트라 op 는 종류 단추를 그 표로 옮긴 뒤 보낸다(마지막 feed 의 표 ·
`gen`). 쓰기 잠금은 C-DEP 꼴을 흉내 내 갈아 끼운다(`write_lock_reason`). 빈 시작(판 없음)이 주
길이라 첫 시험은 판이 없는 DB 에서 출발한다. 견본 판(판 1)의 두 공정은 모두 통째 옮김이다. 새
공정은 공정 표 빈 새 줄(`n1` …)에 이름 · 참조공정을 적어 더한다. 내장 합성 시드의 참조공정은 모두
조합이 하나라, 조합이 둘인 경우 · 다른 시나리오 후보는 맥락을 갈아 끼워 본다(`references`).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from alert_marks import alert_notes, flashed
from auto_update_fakes import new_repository
from edit_grid_fake import (
    FAKE_EVENT_KEY,
    Calls,
    deliver_ops,
    install_fake_edit_grid,
    last,
    outbox,
    shell_frame,
)
from extra_process_fixtures import bump_version, template_files, zip_files
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
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.extra_process_intake import SourceFetch, StagedPack, stage_pack
from capa_simulation.persistence.models import EXTRA_EDITOR_PLACE, EXTRA_KIND_REVISION
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.extra_process_editor import (
    EditorContext,
    ReferenceChoice,
)
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


def _suggested(calls: Calls, column: str = editor.REFERENCE_COLUMN) -> list[str]:
    """공정 표 껍데기의 「글 + 후보」 칸 후보 — 넣을 글(보이는 글이 다르면 [보이는 글, 넣을 글])."""
    items = _shell(calls)["suggest"][column]["items"]
    return [item if isinstance(item, str) else item[1] for item in items]


def _add_line(
    app: AppTest, calls: Calls, name: str = NAME, line: str = "n1", reference: str | None = None
) -> tuple[AppTest, str]:
    """새 공정 — 공정 표 빈 새 줄에 이름과 참조공정(주지 않으면 첫 후보)을 적는다(고른 참조공정을
    돌려준다)."""
    app = _kind(app, "공정")
    chosen = _suggested(calls)[0] if reference is None else reference
    app = _send(app, calls, _write([line], ["공정", "참조공정"], [[name, chosen]]))
    return app, chosen


def _form(calls: Calls, line: str) -> dict[str, Any]:
    """공정 표 껍데기에서 그 줄의 양식 값(초안 아님)."""
    shell = _shell(calls)
    frame = shell_frame(shell)
    return dict(frame.iloc[shell["ids"].index(line)])


def _line_draft(app: AppTest, line: str) -> dict[str, Any]:
    key = editor.LINE_CELLS_KEY
    draft = app.session_state[key] if key in app.session_state else None
    return {} if not draft else dict(draft["cells"].get(line, {}))


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


def _context_of(app: AppTest) -> EditorContext:
    """그 앱 세션이 센 편집기 맥락(시나리오 그대로 — 갈아 끼운 후보는 들지 않는다)."""
    context = app.session_state[editor.CONTEXT_KEY][1]
    assert isinstance(context, EditorContext)
    return context


def _table(app: AppTest, columns: tuple[str, ...]) -> pd.DataFrame | None:
    """그 칸들로 된 표(팝오버 안 포함) — 없으면 None."""
    found = [item.value for item in app.dataframe if tuple(item.value.columns) == columns]
    assert len(found) <= 1
    return found[0] if found else None


def _check_table(app: AppTest) -> pd.DataFrame:
    frame = _table(app, editor.CHECK_COLUMNS)
    assert frame is not None, "「확인할 칸 n」 이 선다"
    return frame


@pytest.fixture
def references(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """다른 시나리오 흉내 손잡이 — `references["shape"]` 가 함수면 맥락의 참조공정 후보(이름 →
    `ReferenceChoice`)를 그 함수로 바꾼 맥락이다(맥락 열쇠도 바뀐다). None 이면 그대로다."""
    knob: dict[str, Any] = {"shape": None}
    original = editor._context

    def shaped(repository: Any) -> Any:
        key, context = original(repository)
        shape = knob["shape"]
        if shape is None:
            return key, context
        return (*key, "shaped", id(shape)), replace(
            context, references=shape(dict(context.references))
        )

    monkeypatch.setattr(editor, "_context", shaped)
    return knob


def test_an_empty_start_adds_a_process_makes_a_pack_and_applies_it(
    database: Path, calls: Calls
) -> None:
    """빈 시작(판 없음 — 주 길): 진입 → 새 줄에 이름 · 참조공정 → STEP · MCP 양식(조합 하나) → 달
    값 → 판 만들기 → 받은 판 상자 → 적용."""
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    assert _opened(app)
    # 공정이 없어도 빈 새 줄이 서 새 공정을 적을 자리가 보인다(UI-LAY-10). 적지 않은 새 줄은
    # 편집기 줄이 아니다(탭 점 없음). 옮김 줄이 없으면 「옮김」 칸도 없다(UI-TXT-08).
    empty = _shell(calls)
    assert empty["ids"] == ["n1", "n2", "n3"]
    assert list(shell_frame(empty)["No."]) == ["새 1", "새 2", "새 3"]
    assert empty["valueCols"][0] == "공정" and editor.CARRY_COLUMN not in empty["valueCols"]
    assert empty["texts"]["rowRemoveHint"] == editor.ROW_REMOVE_HINT, "저장이 아니라 판 만들기"
    assert not _dirty(app)

    app, reference = _add_line(app, calls)
    lines = _shell(calls)
    assert lines["ids"] == ["n1", "n2", "n3", "n4"], "채운 새 줄 뒤로 늘 빈 새 줄 셋"
    assert _dirty(app), "더한 공정만으로도 펼친 판과 다르다"
    # 참조공정의 조합이 하나면 STEP · MCP 는 양식이다 — 초안에 쓰지 않는다(참조를 되돌리면 걷힌다).
    choice = _context_of(app).references[reference]
    ((step, mcp),) = choice.steps
    form = _form(calls, "n1")
    assert (form["STEP_SEQ"], form["MCP_SEQ"], form["소요기준"]) == (step, mcp, choice.basis)
    assert form["참조공정"] is None and form["공정"] is None, "고른 참조 · 이름은 초안"
    assert set(_line_draft(app, "n1")) == {"공정", "참조공정"}
    app = _fill_new_line(app, calls)

    app = _press(app, editor.MAKE_BUTTON_KEY)
    staged = _staged(app)
    assert staged is not None and staged.editor is not None and staged.applicable
    pack = staged.reading.pack
    assert pack is not None and pack.info.version_no == 1
    assert [process.name for process in pack.processes] == [NAME]
    assert [(route.reference, route.step, route.mcp) for route in pack.routes] == [
        (reference, step, mcp)
    ]
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
    assert lines["ids"] == ["b1", "b2", "n1", "n2", "n3"] and lines["locks"]
    assert not _dirty(app), "견본 두 공정은 통째 옮김(잠김) · 빈 새 줄은 줄이 아니다"
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
    first, second, *_ = _shell(calls)["ids"]
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
    app, _ = _add_line(app, calls)
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
    app, _ = _add_line(app, calls)
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
    app, _ = _add_line(app, calls)
    assert _dirty(app)
    app = _send(app, calls, {"op": "remove", "rows": ["n1"]})
    assert not _dirty(app), "더한 줄을 지우면 펼친 판과 같다"
    app = _send(app, calls, {"op": "undo"})
    assert _dirty(app)


def test_a_memo_only_change_is_its_own_value_part(database: Path, calls: Calls) -> None:
    """01 메모만 바꾼 판은 칸 · 공정 수가 그대로라 값 줄에 「01 메모 · 차례만 바뀜」 이 붙는다."""
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    app, _ = _add_line(app, calls)
    app = _fill_new_line(app, calls)
    app = _press(app, editor.MAKE_BUTTON_KEY)
    app = _press(app, APPLY_BUTTON_KEY)

    app = _press(app, editor.OPEN_BUTTON_KEY)
    line, *_ = _shell(calls)["ids"]
    app = _send(app, calls, _write([line], ["메모"], [["DEMO 고친 메모"]]))
    app = _press(app, editor.MAKE_BUTTON_KEY)

    staged = _staged(app)
    assert staged is not None and staged.applicable
    assert any(ORDER_ONLY_PART in text for text in _captions(app))
    assert read_pack_zip(staged.fetch.data).pack is not None


def test_changing_the_reference_rewrites_the_route_of_that_line(
    database: Path, calls: Calls
) -> None:
    """참조공정 칸에 같은 소요기준의 다른 참조공정을 적으면 그 줄의 경로와 양식(STEP · MCP ·
    Area)이 그 참조를 따른다. 양식과 다르게 적은 칸(모듈수 2)은 그대로다 — 양식과 같은 값을 적은
    칸(Area)은 초안이 아니라 양식을 따른다(보인 값을 다시 적으면 바뀐 것 없음)."""
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    app, first = _add_line(app, calls)
    app = _fill_new_line(app, calls)
    references = _context_of(app).references
    others = [
        name
        for name, choice in references.items()
        if name != first and choice.basis == references[first].basis
    ]
    assert others, "합성 시드에 같은 소요기준의 다른 참조공정이 있다"
    app = _kind(app, "공정")
    app = _send(app, calls, _write(["n1"], ["참조공정"], [[others[0]]]))
    ((step, mcp),) = references[others[0]].steps
    assert (_form(calls, "n1")["STEP_SEQ"], _form(calls, "n1")["MCP_SEQ"]) == (step, mcp)

    app = _press(app, editor.MAKE_BUTTON_KEY)
    staged = _staged(app)
    assert staged is not None and staged.reading.pack is not None
    assert [(route.reference, route.step, route.mcp) for route in staged.reading.pack.routes] == [
        (others[0], step, mcp)
    ]
    assert [(process.area, process.modules) for process in staged.reading.pack.processes] == [
        (references[others[0]].area, 2.0)
    ]


def test_a_pack_made_after_another_pack_was_applied_cannot_be_applied(
    database: Path, calls: Calls
) -> None:
    """펼친 뒤 판 이력이 움직였으면 받은 판은 적용할 수 없는 판이다(펼친 차례 대조 — 남의 판을
    말없이 지우지 않는다)."""
    repository = new_repository(database)
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    app, _ = _add_line(app, calls)
    app = _fill_new_line(app, calls)
    apply_template(repository)

    app = _press(app, editor.MAKE_BUTTON_KEY)

    staged = _staged(app)
    assert staged is not None and staged.judgement is not None
    assert not staged.applicable and staged.judgement.reason == editor.MOVED_REASON
    assert [str(item.value) for item in app.error] == [editor.MOVED_REASON]
    # 알림창 한 줄은 「새 판 n」 으로 읽히지 않는다(곁에는 그리지 않아 오류 상자는 하나).
    assert editor.MADE_MOVED.format(n=staged.reading.version_no) in _flashes(app)


def test_the_entry_is_locked_without_an_active_scenario(database: Path, calls: Calls) -> None:
    """활성 시나리오가 없으면 진입을 잠근다(계획 월 · 참조공정 후보를 셀 표가 없다)."""
    app = _app(database, no_scenario=True)

    entry = app.button(key=editor.OPEN_BUTTON_KEY)
    assert entry.disabled and entry.help not in (None, editor.OPEN_HELP, NOT_PRODUCTION_REASON)


def _applied_one(app: AppTest, calls: Calls) -> AppTest:
    """빈 시작에서 공정 하나를 적용하고 다시 펼친다(그 공정은 펼친 줄 `b1` — 편집기 몫)."""
    app = _press(app, editor.OPEN_BUTTON_KEY)
    app, _ = _add_line(app, calls)
    app = _fill_new_line(app, calls)
    app = _press(app, editor.MAKE_BUTTON_KEY)
    app = _press(app, APPLY_BUTTON_KEY)
    return _press(app, editor.OPEN_BUTTON_KEY)


def test_changing_the_reference_of_an_opened_line_and_undoing_it_restores_its_form(
    database: Path, calls: Calls
) -> None:
    """펼친 줄의 참조공정을 바꾸면 STEP · MCP 양식이 새 참조의 조합이 된다 — 초안에 쓰지 않아,
    참조 칸을 되돌리면 펼친 값으로 돌아오고 그리드에서 고친 모듈수도 되돌리면 「바뀐 것 없음」
    이다(eee9e9cf)."""
    app = _applied_one(_app(database), calls)
    assert _shell(calls)["ids"][0] == "b1"
    opened = _form(calls, "b1")
    references = _context_of(app).references
    other = next(
        name
        for name, choice in references.items()
        if name != opened["참조공정"] and choice.basis == opened["소요기준"]
    )
    app = _send(app, calls, _write(["b1"], ["모듈수"], [[5]]))
    app = _send(app, calls, _write(["b1"], ["참조공정"], [[other]]))
    ((step, mcp),) = references[other].steps
    changed = _form(calls, "b1")
    assert (changed["STEP_SEQ"], changed["MCP_SEQ"]) == (step, mcp)
    assert changed["참조공정"] == opened["참조공정"], "참조공정 칸 양식은 펼친 값"
    assert set(_line_draft(app, "b1")) == {"모듈수", "참조공정"}

    app = _send(app, calls, {"op": "undo"})
    restored = _form(calls, "b1")
    assert (restored["STEP_SEQ"], restored["MCP_SEQ"]) == (opened["STEP_SEQ"], opened["MCP_SEQ"])
    app = _send(app, calls, {"op": "undo"})
    assert not _line_draft(app, "b1")
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
    app, _ = _add_line(app, calls)
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
    app, _ = _add_line(app, calls)
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
    app, _ = _add_line(app, calls)
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
    app, _ = _add_line(app, calls)
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
    app, _ = _add_line(app, calls)
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
    app, _ = _add_line(app, calls)
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
    app, _ = _add_line(app, calls)
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


def test_a_half_filled_new_line_is_an_input_problem_and_never_an_exception(
    database: Path, calls: Calls
) -> None:
    """I6 — 이름만 적은 새 줄(참조 · 조합 없음)도 편집기 줄이다. 값 표에는 그 줄 값 줄이 빈칸으로
    서고(시작월 양식 = 첫 계획 월), 빈칸은 「확인할 칸 n」 의 입력 문제다. 판 만들기는 막지 않고
    관문이 거절한다(예외 없음 · 곁 오류 없음)."""
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    app = _send(app, calls, _write(["n1"], ["공정"], [[NAME]]))

    assert _dirty(app)
    form = _form(calls, "n1")
    assert form["시작월"] == str(_context_of(app).months[0])
    assert form["참조공정"] is None and form["STEP_SEQ"] is None and form["소요기준"] is None
    reasons = set(_check_table(app)["까닭"])
    assert {"참조공정 빈칸", "STEP_SEQ · MCP_SEQ 빈칸", "Area_Name 은 Main · MI"} <= reasons
    app = _kind(app, "생산성")
    assert "n1|03|양산|UPEH" in _shell(calls)["ids"]
    assert set(shell_frame(_shell(calls)).iloc[0, 2:].dropna()) == set(), "값 칸은 빈칸"

    app = _press(app, editor.MAKE_BUTTON_KEY)
    staged = _staged(app)
    assert staged is not None and not staged.reading.accepted
    assert not app.error


def test_a_reference_with_two_step_pairs_leaves_the_pair_blank_until_one_is_picked(
    database: Path, calls: Calls, references: dict[str, Any]
) -> None:
    """R3 — 참조공정의 조합이 둘 이상이면 STEP · MCP 양식은 빈칸이고 입력 문제다. 후보는 그 줄
    참조공정 글로 고르는 조합 표(「STEP · MCP」 를 보이고 제 칸 몫을 넣음)이고, 고른 값이 판에
    든다."""
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    reference = _suggested(calls)[0]
    ((step, mcp),) = _context_of(app).references[reference].steps
    second = ("DEMO-P101", "DEMO-1B")

    def two_pairs(found: dict[str, ReferenceChoice]) -> dict[str, ReferenceChoice]:
        found[reference] = replace(found[reference], steps=((step, mcp), second))
        return found

    references["shape"] = two_pairs
    app, _ = _add_line(app, calls, reference=reference)
    form = _form(calls, "n1")
    assert form["STEP_SEQ"] is None and form["MCP_SEQ"] is None
    assert "STEP_SEQ · MCP_SEQ 빈칸" in set(_check_table(app)["까닭"])
    suggest = _shell(calls)["suggest"]
    assert suggest["STEP_SEQ"]["by"] == suggest["MCP_SEQ"]["by"] == "참조공정"
    assert suggest["STEP_SEQ"]["table"][reference] == [
        [f"{step} · {mcp}", step],
        [f"{second[0]} · {second[1]}", second[0]],
    ]
    assert [item[1] for item in suggest["MCP_SEQ"]["table"][reference]] == [mcp, second[1]]

    app = _send(app, calls, _write(["n1"], ["STEP_SEQ", "MCP_SEQ"], [list(second)]))
    app = _fill_new_line(app, calls)
    app = _press(app, editor.MAKE_BUTTON_KEY)
    staged = _staged(app)
    assert staged is not None and staged.applicable and staged.reading.pack is not None
    assert [(route.step, route.mcp) for route in staged.reading.pack.routes] == [second]


def test_a_typed_reference_stays_as_text_when_the_scenario_candidates_change(
    database: Path, calls: Calls, references: dict[str, Any]
) -> None:
    """참조공정 칸은 고른 차례 번호가 아니라 글이다 — 후보가 다른 시나리오로 바꿔도 칸에 그 글이
    남고(후보 밖 — R-02 알림 · STEP · MCP 양식 빈칸), 돌아오면 양식도 돌아온다."""
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    app, reference = _add_line(app, calls)
    app = _fill_new_line(app, calls)
    ((step, mcp),) = _context_of(app).references[reference].steps

    references["shape"] = lambda found: {
        name: choice for name, choice in found.items() if name != reference
    }
    app = _kind(app, "공정")
    assert _line_draft(app, "n1")["참조공정"] == reference
    assert reference not in _suggested(calls)
    assert _form(calls, "n1")["STEP_SEQ"] is None
    reasons = set(_check_table(app)["까닭"])
    assert "R-02 · 참조공정이 이번 기준 데이터 후보에 없음 — 등록 때 빠짐" in reasons

    references["shape"] = None
    app = _run(app)
    assert _line_draft(app, "n1")["참조공정"] == reference
    assert (_form(calls, "n1")["STEP_SEQ"], _form(calls, "n1")["MCP_SEQ"]) == (step, mcp)


def test_an_opened_reference_outside_the_candidates_stays_in_its_cell_and_the_pack(
    database: Path, calls: Calls, references: dict[str, Any]
) -> None:
    """C12 — 펼친 판의 참조공정이 이번 후보 밖이어도 칸 양식은 그 글이고(목록에는 없음) STEP ·
    MCP 도 펼친 값이다. 다른 칸을 고친 판에 그 참조 · 조합이 그대로 든다."""
    app = _applied_one(_app(database), calls)
    opened = _form(calls, "b1")
    references["shape"] = lambda found: {
        name: choice for name, choice in found.items() if name != opened["참조공정"]
    }
    app = _kind(app, "공정")
    form = _form(calls, "b1")
    assert (form["참조공정"], form["STEP_SEQ"], form["MCP_SEQ"]) == (
        opened["참조공정"],
        opened["STEP_SEQ"],
        opened["MCP_SEQ"],
    )
    assert opened["참조공정"] not in _suggested(calls)

    app = _send(app, calls, _write(["b1"], ["메모"], [["DEMO 메모 고침"]]))
    app = _press(app, editor.MAKE_BUTTON_KEY)
    staged = _staged(app)
    assert staged is not None and staged.applicable and staged.reading.pack is not None
    assert [(route.reference, route.step, route.mcp) for route in staged.reading.pack.routes] == [
        (opened["참조공정"], opened["STEP_SEQ"], opened["MCP_SEQ"])
    ]


def test_a_pack_resting_on_a_form_default_is_taken_back_when_the_scenario_moves_it(
    database: Path, calls: Calls, references: dict[str, Any]
) -> None:
    """새 줄 기본값(조합 하나의 STEP · MCP)은 양식이라 지금 시나리오 후보로 다시 센다 — 다른
    시나리오에서 그 양식이 바뀌면 보이는 값 = 판 값이 달라져 만든 판을 걷는다(`_drop_stale`)."""
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    app, reference = _add_line(app, calls)
    app = _fill_new_line(app, calls)
    app = _press(app, editor.MAKE_BUTTON_KEY)
    assert _staged(app) is not None

    references["shape"] = lambda found: {
        **found,
        reference: replace(found[reference], steps=(("DEMO-P777", "DEMO-7A"),)),
    }
    app = _kind(app, "공정")

    assert (_form(calls, "n1")["STEP_SEQ"], _form(calls, "n1")["MCP_SEQ"]) == (
        "DEMO-P777",
        "DEMO-7A",
    )
    assert _staged(app) is None and editor.STALE_STAGED in _all_flashes(app)


def test_the_reference_candidates_show_the_display_name_and_put_the_original(
    database: Path, calls: Calls, monkeypatch: pytest.MonkeyPatch
) -> None:
    """UI-DAT-10 — 참조공정 후보는 표시명이 있으면 「표시명 (원본)」 을 보이고 원본을 넣는다.
    지금 편집기 줄 이름은 후보에서 빠진다(V-06)."""
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    first, *rest = _suggested(calls)
    monkeypatch.setattr(
        editor, "get_process_labels", lambda: ProcessLabels(1, {first: "DEMO 표시명"})
    )
    app = _run(app)
    items = _shell(calls)["suggest"]["참조공정"]["items"]
    assert items[0] == [f"DEMO 표시명 ({first})", first]
    assert items[1:] == rest

    app = _send(app, calls, _write(["n1"], ["공정"], [[rest[0]]]))
    assert rest[0] not in _suggested(calls), "편집기 줄 이름은 참조공정 후보 밖"


def test_the_follow_popover_lists_each_line_with_its_pair_and_follow_counts(
    database: Path, calls: Calls
) -> None:
    """「따라올 제품」 — 늘 서는 표 위 팝오버. 편집기 몫 줄마다 공정 · 참조공정 · STEP · MCP ·
    따라올 제품 · 줄 · Buffer 밖(합치기와 같은 몸통 — 메모), 줄이 없으면 빈 상태 한 마디."""
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    assert _table(app, editor.FOLLOW_COLUMNS) is None
    assert editor.EMPTY_LINES in _captions(app)

    app, reference = _add_line(app, calls)
    frame = _table(app, editor.FOLLOW_COLUMNS)
    assert frame is not None and len(frame) == 1
    ((step, mcp),) = _context_of(app).references[reference].steps
    row = frame.iloc[0]
    assert (row["공정"], row["참조공정"], row["STEP · MCP"]) == (NAME, reference, f"{step} · {mcp}")
    (preview,) = app.session_state[editor.FOLLOW_KEY].values()
    assert preview.rows > 0
    assert (row["따라올 제품"], row["줄"], row["Buffer 밖"]) == (
        preview.products,
        preview.rows,
        preview.uncounted,
    )
    assert editor.EMPTY_LINES not in _captions(app)


def test_removing_a_new_line_clears_it_and_undo_brings_it_back_with_its_values(
    database: Path, calls: Calls
) -> None:
    """새 줄 지우기는 그 줄 칸을 비운다(빈 새 줄 규칙). 값 표 초안은 남아(「판에 안 든 칸 입력」)
    되돌리면 공정째 돌아오고, 같은 새 줄에 다른 공정을 적으면 그 공정에 붙는다(업무 키가 줄 id)."""
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    app, reference = _add_line(app, calls)
    app = _fill_new_line(app, calls)
    app = _kind(app, "공정")

    app = _send(app, calls, {"op": "remove", "rows": ["n1"]})
    assert not _line_draft(app, "n1") and not _dirty(app)
    assert _shell(calls)["ids"] == ["n1", "n2", "n3"]
    assert _value_draft(app, "n1|03|양산|UPEH")
    assert any(text.startswith("판에 안 든 칸 입력") for text in _check_table(app)["까닭"])

    app = _send(app, calls, {"op": "undo"})
    assert _dirty(app) and {"공정", "참조공정"} <= set(_line_draft(app, "n1"))
    app = _send(app, calls, {"op": "redo"})
    app, _ = _add_line(app, calls, name="DEMO_Other", reference=reference)
    app = _press(app, editor.MAKE_BUTTON_KEY)
    staged = _staged(app)
    assert staged is not None and staged.applicable and staged.reading.pack is not None
    pack = staged.reading.pack
    assert [process.name for process in pack.processes] == ["DEMO_Other"]
    assert 30000.0 in [row.upeh for row in pack.productivity]


def test_adding_a_process_marks_the_close_as_losing_edits_on_the_redrawn_run(
    database: Path, calls: Calls
) -> None:
    """새 줄에 적기만 한 회차 — 그 회차의 「작성 닫기」 가 이미 확인 팝오버다(출납 콜백이 표지를
    먼저 켠다 — 화면 탭 점 · 새로고침 확인도 같은 표지를 그 회차에 읽는다)."""
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    assert editor.CLOSE_BUTTON_KEY in [button.key for button in app.button]

    app, _ = _add_line(app, calls)

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


# --------------------------------------------------------------------------- 만들기 결과 · 닫기


def _imported(database: Path) -> StagedPack:
    """가져온 CSV 판(견본 판의 판 번호만 올린 판 2) — 받은 판 자리에 둘 것."""
    repository = DuckDBScenarioRepository(database)
    fetched = SourceFetch(data=zip_files(bump_version(template_files(), 2)), place="가짜")
    staged = stage_pack(
        repository.load_extra_process_state(), fetched, now=datetime(2026, 11, 27, 9, 0)
    )
    assert staged.applicable and staged.editor is None
    return staged


def test_making_a_pack_says_its_result_in_the_alarm_too(database: Path, calls: Calls) -> None:
    """G3 — 공정이 있으면 그리드가 화면 높이를 채워 받은 판 상자가 첫 화면 밖에 선다. 「만들기」
    결과를 알림창 한 줄로도 낸다 — 새 판이면 그 번호, 거절이면 거절 수(거절 표는 받은 판 상자 —
    곁에는 그리지 않는다)."""
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    app = _press(app, editor.MAKE_BUTTON_KEY)
    refused = _staged(app)
    assert refused is not None and not refused.reading.accepted, "빈 판은 「공정이 하나도 없음」"
    count = len(refused.reading.problems)
    assert editor.MADE_REJECTED.format(n=f"{count:,}") in _flashes(app)
    assert not app.error and not app.warning

    app, _ = _add_line(app, calls)
    app = _fill_new_line(app, calls)
    app = _press(app, editor.MAKE_BUTTON_KEY)
    made = _staged(app)
    assert made is not None and made.applicable
    assert editor.MADE_PACK.format(n=1) in _flashes(app)


def test_closing_the_editor_takes_back_the_pack_it_made(database: Path, calls: Calls) -> None:
    """걷기 물음 1 — 「버리고 닫기」 뒤에도 편집기 판 상자가 남아 버린 초안의 판을 「새 판 적용」
    으로 넣을 수 있었다. 작성을 닫으면(고친 것 없는 「작성 닫기」 도) 받은 판 자리의 편집기 판을
    걷는다."""
    app = _app(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)
    app, _ = _add_line(app, calls)
    app = _fill_new_line(app, calls)
    app = _press(app, editor.MAKE_BUTTON_KEY)
    assert _staged(app) is not None

    app = _press(app, editor.CLOSE_CONFIRM_KEY)

    assert not _opened(app) and _staged(app) is None
    assert APPLY_BUTTON_KEY not in [button.key for button in app.button]
    assert _applied_versions(database) == 0

    # 빈 판을 고치지 않고 만든 거절 판 — 고친 것이 없어 묻지 않는 닫기도 걷는다.
    app = _press(app, editor.OPEN_BUTTON_KEY)
    app = _press(app, editor.MAKE_BUTTON_KEY)
    assert _staged(app) is not None and not _dirty(app)
    app = _press(app, editor.CLOSE_BUTTON_KEY)
    assert not _opened(app) and _staged(app) is None


def test_closing_the_editor_keeps_an_imported_pack(database: Path, calls: Calls) -> None:
    """작성을 닫아도 가져온 CSV 판(편집기 밖 출처)은 받은 판 자리에 그대로다."""
    apply_template(new_repository(database))
    imported = _imported(database)
    app = _app(database)
    app.session_state[STAGED_KEY] = imported
    app = _press(app, editor.OPEN_BUTTON_KEY)
    first, *_ = _shell(calls)["ids"]
    app = _send(app, calls, {"op": "remove", "rows": [first]})
    assert _dirty(app)

    app = _press(app, editor.CLOSE_CONFIRM_KEY)

    assert not _opened(app) and _staged(app) == imported


def test_an_untouched_make_says_it_cleared_the_held_pack(database: Path, calls: Calls) -> None:
    """규칙 Q4 — 받아 둔 판이 있을 때 고친 것 없이 「만들기」 를 누르면 「바뀐 것 없음」 과 함께
    그 판이 비워진다. 비운 판이 있을 때만 알림 글이 그 말을 붙인다."""
    apply_template(new_repository(database))
    app = _app(database)
    app.session_state[STAGED_KEY] = _imported(database)
    app = _press(app, editor.OPEN_BUTTON_KEY)

    app = _press(app, editor.MAKE_BUTTON_KEY)

    assert _staged(app) is None
    assert editor.UNCHANGED_CLEARED in _flashes(app)

    app = _press(app, editor.MAKE_BUTTON_KEY)
    shown = _flashes(app)
    assert editor.UNCHANGED_EDITOR in shown and editor.UNCHANGED_CLEARED not in shown
