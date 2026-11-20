# Purpose: 설비 마스터 「리비전 저장」 직후에 닿은 표 출납이 저장본 위에 이어지는지 본다.

"""저장 직후 입력(rerun-1120 바탕 결함 c6).

브라우저 출납 op 는 그린 편집본의 `base` 를 싣는다. 「리비전 저장」 을 누르고 새 `base` 를 받기 전에
친 칸은 저장 직전 편집본의 `base` 로 온다. 전에는 세 길로 잃었다.

- 저장 콜백이 끝까지 돈 뒤 닿으면 `apply_ops` 가 옛 `base` 라 버렸다(「편집본을 다시 세운 뒤라 …」).
- 저장 콜백이 DB 쓰기 뒤 다음 조작의 회차에 끊기면(fastReruns) 그 회차의 받기 콜백이 이미 저장한 옛
  편집본에 얹고, 본문이 끊긴 제 저장의 뒷정리로 편집본을 다시 세우며 말없이 지웠다.
- 그 다음 회차가 제 저장 알림 창(1초)을 넘겨 오면(바쁜 서버) 제 저장을 남의 저장으로 읽어 「다른
  사용자가 공통 대장 rN 을 저장해 … 버렸습니다」 를 알렸다.

이제 저장 누름이 DB 쓰기 전에 이음 표지(저장한 출발점 · 저장 뒤 id 지도 · 저장에 든 seq)를 적고,
뒷정리 전 회차의 출납은 다시 세운 뒤로 미루며, 다시 세운 편집본(= 그 저장본)에 옮겨 얹는다. 모두
버리기 · 불러오기 · 남의 저장으로 다시 세운 편집본에는 얹지 않는다.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import streamlit as st
from alert_marks import alert_notes
from grid_fake import Calls, grid_results, install_fake_grid, last, send
from streamlit.testing.v1 import AppTest
from test_equipment_master_tab import (
    _RUN_HEAD,
    _TAIL,
    PAGE,
    RUN_HEAD_KEY,
    _import,
    _kept_grid_kwargs,
    _rows,
)
from test_equipment_master_tab_new_unit import _draft
from test_equipment_pages import _page_script
from test_scenario_save_double_press import _first_callback

import capa_simulation.components.write_guard as write_guard
from capa_simulation.components import equipment_master_grid as emg
from capa_simulation.components import equipment_master_tab as emt
from capa_simulation.components.equipment_data_workspace import (
    BUFFER_KEY,
    HEAD_STALE_KEY,
    OWN_SAVE_CARRY_KEY,
    head_stale_if_unsaved_changed,
)
from capa_simulation.components.equipment_master_tab import (
    DISCARD_CONFIRM_KEY,
    SAVE_BUTTON_KEY,
    SIDE_CHANGES,
    SIDE_KEY,
)
from capa_simulation.navigation import EQUIPMENT_MASTER_TAB, EQUIPMENT_TAB_KEY
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services import equipment_grid as eg

MOUNT = "m-race"


@pytest.fixture(autouse=True)
def _release_repository() -> Any:
    yield
    clear_equipment_repository()


@pytest.fixture
def grid(monkeypatch: pytest.MonkeyPatch) -> Calls:
    return install_fake_grid(monkeypatch)


def _app(path: Path) -> AppTest:
    app = AppTest.from_string(_RUN_HEAD + _page_script(PAGE, path) + _TAIL, default_timeout=60)
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_MASTER_TAB
    app.run()
    _import(app, _rows("DA-01", "DA-02"))
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    app.run()
    app.button(key=SAVE_BUTTON_KEY).click().run()
    assert not app.exception, app.exception
    return app


def _save(app: AppTest) -> None:
    """「저장 전 변경」 의 「리비전 저장」(넣기가 오른쪽 칸을 「호기 상세」 로 옮겼어도)."""
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    app.run()
    app.button(key=SAVE_BUTTON_KEY).click().run()
    assert not app.exception, app.exception


def _op(seq: int, base: str, **fields: Any) -> dict[str, Any]:
    return {"seq": seq, "at": seq, "base": base, **fields}


def _before_save_ops(base: str) -> list[dict[str, Any]]:
    """저장 전에 반영할 넣기 · 붙여넣기 — 저장 뒤 같은 출납이 다시 와도 두 번 들면 안 된다."""
    draft = _draft(설비명="NEW-01", 공정소분류="Die Attach")
    return [
        _op(1, base, op="add", draftSeq=9, draft=draft),
        _op(2, base, op="paste", ids=["s:DA-01"], cols=["담당자"], rows=[["붙인 값"]], cut=0)
        | {"skipped": 0},
    ]


def _after_save_ops(base: str) -> list[dict[str, Any]]:
    """저장 직후 친 칸 — 저장 직전 편집본의 `base` · 저장 전 id(새 호기는 n:)로 온다."""
    return [
        _op(3, base, op="cell", id="n:NEW-01", col="메모1", text="저장 직후 새 호기"),
        _op(4, base, op="cell", id="s:DA-02", col="담당자", text="저장 직후 값"),
    ]


def _value(app: AppTest, name: str, column: str) -> object:
    master = app.session_state[BUFFER_KEY][1]
    values = master.loc[master["설비명"].eq(name), column].tolist()
    assert len(values) == 1, values
    return values[0]


def _page_texts(app: AppTest) -> list[str]:
    """화면의 글(마크다운 · 캡션 — 알약은 마크다운 꼴로 온다)."""
    return [str(item.value) for item in (*app.markdown, *app.caption)]


def has_unsaved_equipment_edits_in(app: AppTest) -> bool:
    """세운 세대보다 편집본 세대가 오르고 저장본으로 돌아온 세대가 아닌가(미저장 표시 판정)."""
    seeded = app.session_state["equipment_workspace_seeded_generation_v1"]
    generation = app.session_state["equipment_workspace_buffer_generation_v1"]
    return bool(generation > seeded)


def _no_foreign_blame(app: AppTest) -> None:
    notes = [note for note in alert_notes(app, again=True) if note.get("active") is not False]
    texts = [str(note.get("full") or note.get("text") or "") for note in notes]
    assert not [note for note in notes if note.get("code") == "EQ-05"], texts
    assert not [text for text in texts if "다른 사용자가 공통" in text], texts
    assert not [text for text in grid_results(app) if "반영하지 않았습니다" in text]


def test_a_cell_typed_right_after_my_save_lands_on_the_saved_buffer(
    tmp_path: Path, grid: Calls
) -> None:
    """저장 콜백이 끝까지 돈 뒤 저장 직전 `base` 로 닿은 칸 — 저장본 위에 얹는다(새 호기 id 는
    저장 뒤 id 로). 저장에 든 넣기 · 붙여넣기가 같은 출납으로 다시 와도 두 번 들지 않는다."""
    app = _app(tmp_path / "equipment.duckdb")
    before = last(grid, emg.GRID_KEY)["base"]
    send(app, emg.GRID_KEY, "outbox", {"mount": MOUNT, "ops": _before_save_ops(before)})
    assert _value(app, "NEW-01", "설비명") == "NEW-01"
    _save(app)
    assert last(grid, emg.GRID_KEY)["base"] != before

    ops = [*_before_save_ops(before), *_after_save_ops(before)]
    send(app, emg.GRID_KEY, "outbox", {"mount": MOUNT, "ops": ops})

    assert not app.exception, app.exception
    assert _value(app, "NEW-01", "메모1") == "저장 직후 새 호기"
    assert _value(app, "DA-02", "담당자") == "저장 직후 값"
    assert _value(app, "DA-01", "담당자") == "붙인 값"
    assert last(grid, emg.GRID_KEY)["ack"] == {"mount": MOUNT, "seq": 4}
    _no_foreign_blame(app)


@pytest.mark.parametrize("window", [1.0, 0.0], ids=["in-window", "busy-server"])
def test_a_cell_typed_while_my_save_was_cut_waits_and_lands_after_the_rebuild(
    tmp_path: Path, grid: Calls, monkeypatch: pytest.MonkeyPatch, window: float
) -> None:
    """저장 콜백이 DB 쓰기 뒤에 끊기고(fastReruns) 다음 회차의 받기 콜백에 저장 직후 칸이 닿는다 —
    이미 저장한 옛 편집본에 얹지 않고 다시 세운 편집본으로 미뤄 얹는다. 그 회차가 제 저장 알림
    창(1초)을 넘겨 와도(`busy-server`) 남의 저장으로 읽지 않는다. 새 호기를 넣은 저장은 새 일정
    리비전을 써 다음 회차에 세션을 옮기며 한 번 더 다시 세운다 — 그 사이에도 미뤄 두었다가 마지막
    편집본에 얹는다(이어 받은 옛 출발점 둘)."""
    kept = _kept_grid_kwargs(monkeypatch)
    app = _app(tmp_path / "equipment.duckdb")
    before = last(grid, emg.GRID_KEY)["base"]
    send(app, emg.GRID_KEY, "outbox", {"mount": MOUNT, "ops": _before_save_ops(before)})
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    app.run()
    _first_callback(
        app, monkeypatch, "_save_revision", cut_after=(DuckDBEquipmentRepository, "save_equipment")
    )
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", window)
    ops = [*_before_save_ops(before), *_after_save_ops(before)]

    def head() -> None:
        st.session_state[emg.GRID_KEY] = SimpleNamespace(outbox={"mount": MOUNT, "ops": ops})
        kept[emg.GRID_KEY]["on_outbox_change"]()

    app.session_state[RUN_HEAD_KEY] = head
    app.run()

    assert not app.exception, app.exception
    assert _value(app, "DA-02", "담당자") == "저장 직후 값"
    assert _value(app, "NEW-01", "메모1") == "저장 직후 새 호기"
    assert _value(app, "DA-01", "담당자") == "붙인 값"
    assert len(app.session_state[OWN_SAVE_CARRY_KEY]["froms"]) == 2
    _no_foreign_blame(app)
    app.run()
    assert _value(app, "DA-02", "담당자") == "저장 직후 값"


def test_an_edit_sent_before_discard_all_is_not_brought_back(tmp_path: Path, grid: Calls) -> None:
    """「모두 버리기」 로 다시 세운 편집본에는 그 전 `base` 의 칸을 얹지 않는다 — 버린 것으로 세고
    남의 저장 탓으로 적지 않는다. 앞 「리비전 저장」 의 이음 표지도 걷힌다."""
    app = _app(tmp_path / "equipment.duckdb")
    before = last(grid, emg.GRID_KEY)["base"]
    send(
        app,
        emg.GRID_KEY,
        "outbox",
        {
            "mount": MOUNT,
            "ops": [
                _op(1, before, op="cell") | {"id": "s:DA-01", "col": "담당자", "text": "버릴 값"}
            ],
        },
    )
    assert OWN_SAVE_CARRY_KEY in app.session_state
    app.button(key=DISCARD_CONFIRM_KEY).click().run()
    assert OWN_SAVE_CARRY_KEY not in app.session_state
    late = _op(2, before, op="cell", id="s:DA-02", col="담당자", text="버리기 직전 값")
    send(app, emg.GRID_KEY, "outbox", {"mount": MOUNT, "ops": [late]})

    assert str(_value(app, "DA-02", "담당자")) != "버리기 직전 값"
    assert grid_results(app, "warning")[-1] == eg.DROPPED_TOAST.format(count=1)


# 저장 전에 고칠 DA-01 칸 — 담당자는 공통 대장만 쓰고, 반입일정은 새 일정 리비전을 써서 끊긴 저장
# 뒤 세션을 옮기며 한 번 더 다시 세운다(둘 다 고치면 공통 · 일정 리비전을 함께 쓴다).
_FIRST_CELLS: dict[str, tuple[tuple[str, str], ...]] = {
    "common": (("담당자", "저장 전 값"),),
    "schedule": (("반입일정", "2026-12-01"),),
    "both": (("담당자", "저장 전 값"), ("반입일정", "2026-12-01")),
}


@pytest.mark.parametrize("first_cell", list(_FIRST_CELLS))
@pytest.mark.parametrize("cut", [False, True], ids=["finished", "cut"])
def test_a_cell_landing_on_the_old_buffer_while_my_save_writes_is_taken_again(
    tmp_path: Path, grid: Calls, monkeypatch: pytest.MonkeyPatch, cut: bool, first_cell: str
) -> None:
    """Streamlit 1.63 은 저장 콜백이 DB 에 쓰는 사이 닿은 다음 조작의 회차를 다른 스레드로 세운다 —
    그 회차의 받기 콜백은 아직 쓰기 전이라 저장 직후 칸을 곧 버려질 옛 편집본에 얹고 ack 를
    그린다(브라우저 c6 에서 본 길 — 브라우저는 그 op 를 버린다). 그 op 를 이음 표지에 남겼다가 제
    저장 뒤 다시 세운 편집본에 다시 얹는다 — 저장 콜백이 끝까지 돌든 쓰기 뒤에 끊기든. 끊긴 저장이
    새 일정 리비전을 썼으면 그 op 는 세션을 옮겨 다시 세운 편집본에 얹는다(옮기기 전 편집본에 얹으면
    다시 세울 때 사라진다)."""
    kept = _kept_grid_kwargs(monkeypatch)
    app = _app(tmp_path / "equipment.duckdb")
    before = last(grid, emg.GRID_KEY)["base"]
    cells = _FIRST_CELLS[first_cell]
    first = _op(1, before, op="paste", ids=["s:DA-01"], cols=[c for c, _ in cells], cut=0) | {
        "rows": [[t for _, t in cells]],
        "skipped": 0,
    }
    send(app, emg.GRID_KEY, "outbox", {"mount": MOUNT, "ops": [first]})
    late = _op(2, before, op="cell", id="s:DA-02", col="담당자", text="쓰는 사이 친 값")
    original = DuckDBEquipmentRepository.save_equipment

    def writing(self: DuckDBEquipmentRepository, *args: Any, **kwargs: Any) -> Any:
        st.session_state[emg.GRID_KEY] = SimpleNamespace(
            outbox={"mount": MOUNT, "ops": [first, late]}
        )
        kept[emg.GRID_KEY]["on_outbox_change"]()
        return original(self, *args, **kwargs)

    monkeypatch.setattr(DuckDBEquipmentRepository, "save_equipment", writing)
    stale_marks: list[object] = []
    marking = head_stale_if_unsaved_changed

    def marked(before: bool) -> None:
        marking(before)
        stale_marks.append(st.session_state.get(HEAD_STALE_KEY))

    monkeypatch.setattr(emt, "head_stale_if_unsaved_changed", marked)
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    app.run()
    if cut:
        _first_callback(
            app,
            monkeypatch,
            "_save_revision",
            cut_after=(DuckDBEquipmentRepository, "save_equipment"),
        )
        app.run()
    else:
        app.button(key=SAVE_BUTTON_KEY).click().run()

    assert not app.exception, app.exception
    for column, text in cells:
        assert str(_value(app, "DA-01", column))[: len(text)] == text
    assert _value(app, "DA-02", "담당자") == "쓰는 사이 친 값"
    assert last(grid, emg.GRID_KEY)["ack"] == {"mount": MOUNT, "seq": 2}
    _no_foreign_blame(app)
    # 다시 얹은 칸은 저장하지 않은 편집이다 — 본문에서 얹어 머리(변경 칩 · 탭 점 · 떠나기 확인)가
    # 바뀌므로 그 회차 끝에 한 번 다시 돌 표지를 단다.
    assert has_unsaved_equipment_edits_in(app)
    assert True in stale_marks
    assert any("저장 전 변경 1건" in text for text in _page_texts(app))
