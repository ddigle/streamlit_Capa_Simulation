# Purpose: 설비 마스터 탭 ① 진입 — 페이지가 넘긴 재료와 자리에서 다시 세운 재료가 같고, 저장 토큰 ·
# 머리 표지가 무엇에 움직이는지 본다.

"""설비 마스터 탭 ① 진입(`equipment_master_tab.render_equipment_master`).

탭 본문은 작은 인자(한 번만 쓰는 표지 `drafts_replaced`)만 받는 한 함수
(`render_equipment_master_scope`)로 들어간다. 표 · 스냅숏을 든 재료는 페이지가 그 회차에 세운 것을
스레드 칸으로 넘기고, 넘긴 것이 없는 회차는 마지막 페이지 회차가 적은 자리(DB 자리 · 저장본 쌍 id ·
스냅숏 뺀 세션)로 캐시에서 다시 세운다 — 세션을 옮기거나 편집본을 세우지 않는다.

- 다시 세운 재료는 그 페이지 회차가 넘긴 재료와 같다(공식 · 가정 설비 시나리오 — 확인용 공식 스냅숏
  포함).
- 저장 토큰(`saved_pair_token`)은 남이 공통 대장을 저장하면 바뀐다(DB 를 다시 열지 않는 캐시 읽기).
- 머리 표지(`master_head`)는 탭 밖이 그리는 값 — 미저장 편집 · 팝업 열림 칸 — 이 바뀔 때 바뀐다.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from grid_fake import Calls, install_fake_grid, last, load, send_ops
from streamlit.testing.v1 import AppTest
from test_equipment_assumption_rawdata import _two_scenarios
from test_equipment_master_tab import _RUN_HEAD, RUN_HEAD_KEY
from test_equipment_pages import PROJECT_ROOT, _page_script
from test_equipment_scenario_repository import _request, _session, _set

from capa_simulation.components import equipment_master_grid as emg
from capa_simulation.components import equipment_master_tab as emt
from capa_simulation.components.equipment_settings_dialog import EQUIPMENT_DIALOG_KEY
from capa_simulation.equipment_scenario_activation import SELECTION_KEY
from capa_simulation.navigation import EQUIPMENT_MASTER_TAB, EQUIPMENT_TAB_KEY
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.session_slot import SessionSlot

PAGE = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
OPERATIONS = "operations"
# 페이지 뒤 꼬리 — 그 회차가 적은 자리에서 재료를 다시 세워 넘겨 둔 목록에 담는다.
REBUILD_KEY = "test_master_scope_rebuild"
_REBUILD_TAIL = f"""
import streamlit as st
from capa_simulation.components import equipment_master_tab

_rebuilt = st.session_state.pop({REBUILD_KEY!r}, None)
if _rebuilt is not None:
    _rebuilt.append(equipment_master_tab._rebuilt_materials())
"""


@pytest.fixture(autouse=True)
def _release_repository() -> Any:
    clear_equipment_repository()
    yield
    clear_equipment_repository()


@pytest.fixture
def grid(monkeypatch: pytest.MonkeyPatch) -> Calls:
    return install_fake_grid(monkeypatch)


def _ok(app: AppTest) -> AppTest:
    assert not app.exception, [item.message for item in app.exception]
    return app


def _page(repository: DuckDBEquipmentRepository, scenario_id: str, *, tail: str = "") -> AppTest:
    """그 설비 시나리오 세션으로 연 가용설비 현황 탭 ① (표 대역)."""
    clear_equipment_repository()
    script = _RUN_HEAD + _page_script(PAGE, repository.database_path) + tail
    app = AppTest.from_string(script, default_timeout=90)
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_MASTER_TAB
    app.session_state[SELECTION_KEY] = {"scenario_id": scenario_id, "schedule_revision_id": None}
    return _ok(app.run())


def _same_materials(handed: dict[str, Any], rebuilt: emt.MasterMaterials) -> None:
    """페이지가 본문에 넘긴 인자와 다시 세운 재료가 같다 — 스냅숏은 쌍 토큰으로, 세션은 스냅숏 ·
    한 회차 알림을 뺀 값으로."""
    assert rebuilt.repository is handed["repository"]
    snapshot = rebuilt.session.snapshot
    assert snapshot is not None and handed["latest_snapshot"] is not None
    assert snapshot.token == handed["latest_snapshot"].token
    assert replace(rebuilt.session, snapshot=None) == replace(
        handed["session"], snapshot=None, notice=None, head_dropped=False
    )
    assert rebuilt.floor_canvases == handed["floor_canvases"]
    assert rebuilt.layout_mode == handed["layout_mode"]
    assert rebuilt.today == handed["today"]
    official = handed["confirmation_official"]
    if official is None:
        assert rebuilt.confirmation_official is None
    else:
        assert rebuilt.confirmation_official is not None
        assert rebuilt.confirmation_official.token == official.token


@pytest.mark.parametrize("scenario", ["official", "assumption"])
def test_the_rebuilt_materials_are_the_ones_the_page_handed_over(
    tmp_path: Path, grid: Calls, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    """넘긴 재료가 없는 회차는 마지막 페이지 회차가 적은 자리에서 같은 재료를 다시 세운다 — 공식
    세션과, 확인용 공식 스냅숏을 함께 드는 가정 설비 시나리오 세션 모두."""
    repository, assumption = _two_scenarios(tmp_path)
    scenario_id = OPERATIONS if scenario == "official" else assumption
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(emt, "render_equipment_master_tab", lambda **kwargs: seen.append(kwargs))
    app = _page(repository, scenario_id, tail=_REBUILD_TAIL)
    seen.clear()
    rebuilt: list[emt.MasterMaterials] = []
    app.session_state[REBUILD_KEY] = rebuilt
    _ok(app.run())

    (handed,) = seen
    assert (handed["confirmation_official"] is None) is (scenario == "official")
    _same_materials(handed, rebuilt[0])


def test_rebuilding_without_a_page_run_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """자리를 적은 페이지 회차가 없으면 다시 세울 수 없다 — 세션을 옮기거나 편집본을 세우지
    않는다."""
    monkeypatch.setattr(emt, "_PLACE", SessionSlot("test_master_scope_no_place", emt._MasterPlace))
    with pytest.raises(RuntimeError, match="페이지 회차를 먼저"):
        emt._rebuilt_materials()


def _theirs_common_save(repository: DuckDBEquipmentRepository) -> None:
    """다른 사용자가 공식 세션에서 공통 칸(담당자)을 고쳐 공통 대장을 저장한다."""
    theirs = _session(repository)
    repository.save_equipment(
        _request(theirs, equipment=_set(theirs.equipment, "EQ-01", "담당자", "남의 값"))
    )


def test_the_saved_pair_token_moves_when_someone_else_saves_the_common_ledger(
    tmp_path: Path, grid: Calls
) -> None:
    """저장 토큰은 (공통 대장 최신, 세션 설비 시나리오의 최신 일정) 리비전 쌍이다 — 페이지 회차가
    적은 자리의 DB 를 캐시로 읽는다. 남이 공통 대장을 저장하면 앞쪽이 바뀐다."""
    repository, _ = _two_scenarios(tmp_path)
    app = _page(repository, OPERATIONS)
    tokens: list[object] = []
    app.session_state[RUN_HEAD_KEY] = lambda: tokens.append(emt.saved_pair_token())
    _ok(app.run())
    before = tokens[-1]
    assert isinstance(before, tuple) and before[0] == repository.latest_revision_id()

    _theirs_common_save(repository)
    app.session_state[RUN_HEAD_KEY] = lambda: tokens.append(emt.saved_pair_token())
    _ok(app.run())
    after = tokens[-1]
    assert isinstance(after, tuple)
    assert after[0] == repository.latest_revision_id() != before[0]
    assert after[1] == before[1], "일정 쪽은 그대로다"


def test_the_head_marks_move_with_what_is_drawn_outside_the_tab(
    tmp_path: Path, grid: Calls
) -> None:
    """머리 표지는 탭 밖이 그리는 값을 담는다 — 첫 칸 고침(미저장 편집)과 팝업 열림 칸에 바뀌고,
    아무것도 바꾸지 않은 회차에는 그대로다."""
    repository, _ = _two_scenarios(tmp_path)
    app = _page(repository, OPERATIONS)
    marks: list[tuple[object, ...]] = []

    def mark() -> None:
        marks.append(emt.master_head())

    app.session_state[RUN_HEAD_KEY] = mark
    _ok(app.run())
    app.session_state[RUN_HEAD_KEY] = mark
    _ok(app.run())
    assert marks[0] == marks[1]

    load(app, [], kind="all")
    send_ops(app, grid, {"op": "cell", "id": "s:EQ-01", "col": "담당자", "text": "내 값"})
    assert last(grid, emg.GRID_KEY)["ack"] is not None
    app.session_state[RUN_HEAD_KEY] = mark
    _ok(app.run())
    edited = marks[-1]
    assert edited != marks[0]
    assert edited[1] is True, "미저장 편집"

    app.session_state[EQUIPMENT_DIALOG_KEY] = "import"
    app.session_state[RUN_HEAD_KEY] = mark
    _ok(app.run())
    assert marks[-1] != edited
