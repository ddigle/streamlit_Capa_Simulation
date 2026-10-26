# Purpose: 낡은 세션의 설비 저장이 세 저장 길 모두에서 쓰기 전에 같은 판정으로 멈추는지 본다.

"""낡은 세션의 낡기 전 편집 — 저장 전 검사 한 곳(`equipment_data_workspace.save_equipment_buffer`).

가정 설비 시나리오 세션에서 일정·시나리오 메모 칸(시나리오 칸)과 배치 칸을 고친 뒤 남이 그
시나리오에 저장해 낡은 세션이 됐다. 일정이 바뀐 저장은 저장소가 공통 칸까지 늘 거부하고 그
문구(「다른 사용자가 먼저 … 화면을 다시 불러와」)는 고칠 칸을 말하지 않는다 — 다시 불러오면 공통
편집까지 잃는다. 설비 마스터 탭만 고칠 것 줄로 막고, 사이드바 설비 시나리오 팝업 「저장」·Space
「배치 저장」 은 저장소 거부로 끝났다(2026-10-26 E2E). 세 길은 이제 같은
판정(`stale_save_reasons`)으로 설비 쪽을 쓰기 전에 멈춘다 — 탭은 고칠 것 줄(「아래 목록에서」), 표
밖 두 자리는 거부 글(「가용설비 현황 › 설비 마스터 「저장 전 변경」 에서」)이고 고칠 길(되돌리면
공통 칸은 저장된다)은 같다. 설비 저장은 0건이다. FAB 전체 배치 대기분은 별도 쓰기라 그 앞에서
저장되고 거부 글이 그 사실을 함께 말한다(설비 저장이 막혀도 FAB 는 막지 않는다 — 9장).
"""

from __future__ import annotations

import ast
import warnings
from collections.abc import Iterator
from pathlib import Path

import pytest
from grid_fake import Calls, install_fake_grid, last
from streamlit.testing.v1 import AppTest
from test_equipment_assumption_rawdata import _two_scenarios
from test_equipment_scenario_repository import _request, _scenario, _session, _set
from test_equipment_scenario_session import _popup_with_edits

from capa_simulation.components import equipment_master_grid as emg
from capa_simulation.components.equipment_data_workspace import (
    STALE_SCENARIO_EDITS_ELSEWHERE,
    STALE_SCENARIO_EDITS_TAB,
)
from capa_simulation.components.equipment_master_tab import (
    SAVE_BUTTON_KEY,
    SIDE_CHANGES,
    SIDE_KEY,
)
from capa_simulation.components.equipment_scenario_status import (
    EQUIPMENT_SCENARIO_DIALOG_MODE_KEY,
    SAVE_MODE,
)
from capa_simulation.components.equipment_scenario_status import (
    SAVE_BUTTON_KEY as POPUP_SAVE_BUTTON_KEY,
)
from capa_simulation.equipment_scenario_activation import SELECTION_KEY
from capa_simulation.navigation import (
    AVAILABLE_EQUIPMENT_STATUS,
    EQUIPMENT_MASTER_TAB,
    EQUIPMENT_TAB_KEY,
)
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TAB_PAGE = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
SPACE_PAGE = PROJECT_ROOT / "app_pages" / "space_status.py"
# 세 길이 함께 쓰는 판정의 몸통 — 고칠 자리만 길마다 다르다.
CORE = "낡은 세션이 되기 전에 고친 일정·시나리오 메모 칸 1개(호기 1대)는 저장되지 않습니다"
WAY_OUT = "그 칸을 되돌리면(↶) 공통 칸은 저장됩니다"
EDITS = [("EQ-01", "시나리오 메모", "낡기 전 메모"), ("EQ-01", "X좌표", 41.0)]


@pytest.fixture(autouse=True)
def _release_repository() -> Iterator[None]:
    clear_equipment_repository()
    yield
    clear_equipment_repository()


def _page_with_edits(page: Path, database: Path) -> str:
    """편집본에 `edits`((설비명, 칸, 값))를 처음 한 번 넣고 실제 페이지를 돌리는 스크립트. 세션 칸
    `fab` 이 있으면 그 이름의 FAB 블록 하나도 대기분으로 함께 둔다."""
    simulation = database.with_name(f"{database.stem}_simulation.duckdb")
    return f"""
from pathlib import Path

import streamlit as st

import capa_simulation.settings as settings

settings.EQUIPMENT_DUCKDB_PATH = Path({str(database)!r})
settings.DUCKDB_PATH = Path({str(simulation)!r})

from capa_simulation.components.equipment_data_workspace import (
    ensure_equipment_drafts,
    replace_equipment_buffer,
)
from capa_simulation.equipment_scenario_activation import resolve_equipment_session

edits = st.session_state.get("edits") or []
if edits and not st.session_state.get("edited"):
    frames = ensure_equipment_drafts(resolve_equipment_session({str(database)!r}).snapshot)
    edited = frames[1].copy()
    for name, column, value in edits:
        edited.loc[edited["설비명"].eq(name), column] = value
    replace_equipment_buffer((frames[0], edited, frames[2]))
    fab = st.session_state.get("fab")
    if fab:
        from capa_simulation.components.equipment_data_workspace import stage_fab_layout
        from capa_simulation.services.fab_layout import (
            fab_marks_fingerprint,
            prepare_fab_layout_marks,
        )

        stage_fab_layout(
            None,
            prepare_fab_layout_marks(
                [{{"id": fab, "kind": "block", "x": 1, "y": 1, "w": 5, "h": 3, "link": "C1 2F"}}],
                (101.0, 62.0),
            ),
            base=(None, fab_marks_fingerprint(())),
        )
    st.session_state["edited"] = True
page_source = Path({str(page)!r}).read_text(encoding="utf-8")
exec(compile(page_source, {str(page)!r}, "exec"), {{"__name__": "__main__"}})
"""


def _stale(repository: DuckDBEquipmentRepository, scenario_id: str) -> None:
    """남이 그 시나리오에 일정만 바꿔 저장한다 — 배치 지문은 그대로라 Space 배치는 빨리 감기로
    열린다."""
    theirs = _session(repository, scenario_id)
    repository.save_equipment(
        _request(
            theirs,
            scenario_id,
            equipment=_set(theirs.equipment, "EQ-02", "Qual일정", "2026-09-01"),
        )
    )


def _start(app: AppTest, scenario_id: str, revision_id: str | None) -> AppTest:
    app.session_state[SELECTION_KEY] = {
        "scenario_id": scenario_id,
        "schedule_revision_id": revision_id,
    }
    app.session_state["edits"] = EDITS
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    return app


def _errors(app: AppTest) -> list[str]:
    return [str(item.value) for item in app.error]


@pytest.fixture
def grid(monkeypatch: pytest.MonkeyPatch) -> Calls:
    return install_fake_grid(monkeypatch)


def test_the_master_tab_lists_the_stale_cells_and_saves_nothing(
    tmp_path: Path, grid: Calls
) -> None:
    repository, setup = _two_scenarios(tmp_path)
    pinned = _scenario(repository, setup).latest_schedule_revision_id
    app = AppTest.from_string(
        _page_with_edits(TAB_PAGE, repository.database_path), default_timeout=90
    )
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_MASTER_TAB
    _start(app, setup, pinned)
    _stale(repository, setup)
    before = len(repository.list_revisions())
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    app.run()

    line = STALE_SCENARIO_EDITS_TAB.format(cells=1, units=1)
    assert CORE in line and WAY_OUT in line
    changes = last(grid, emg.side_key("changes"))
    assert any(line in " ".join(map(str, item)) for item in changes["errors"])
    app.button(key=SAVE_BUTTON_KEY).click().run()

    assert not app.exception, [item.message for item in app.exception]
    assert any("고쳐야 저장됩니다" in text for text in _errors(app)), _errors(app)
    assert len(repository.list_revisions()) == before


def test_the_sidebar_popup_save_refuses_with_the_same_judgement(tmp_path: Path) -> None:
    repository, setup = _two_scenarios(tmp_path)
    pinned = _scenario(repository, setup).latest_schedule_revision_id
    app = AppTest.from_function(
        _popup_with_edits,
        args=(str(repository.database_path), Path(AVAILABLE_EQUIPMENT_STATUS.path).name),
        default_timeout=60,
    )
    _start(app, setup, pinned)
    _stale(repository, setup)
    before = len(repository.list_revisions())
    app.session_state[EQUIPMENT_SCENARIO_DIALOG_MODE_KEY] = SAVE_MODE
    app.run()
    app.button(key=POPUP_SAVE_BUTTON_KEY).click().run()

    assert not app.exception, [item.message for item in app.exception]
    line = STALE_SCENARIO_EDITS_ELSEWHERE.format(cells=1, units=1)
    assert CORE in line and WAY_OUT in line
    assert _errors(app) == [f"저장하지 못했습니다: {line}"]
    assert len(repository.list_revisions()) == before


def test_the_space_layout_save_refuses_with_the_same_judgement(tmp_path: Path) -> None:
    """Space 「배치 저장」 — 배치는 빨리 감기로 저장할 수 있는 세션이라 단추가 서지만, 낡기 전에
    고친 시나리오 칸이 있으면 쓰기 전에 같은 글로 멈춘다(예전에는 「다른 사용자가 먼저 …
    저장해」)."""
    repository, setup = _two_scenarios(tmp_path)
    pinned = _scenario(repository, setup).latest_schedule_revision_id
    app = AppTest.from_string(
        _page_with_edits(SPACE_PAGE, repository.database_path), default_timeout=90
    )
    _start(app, setup, pinned)
    _stale(repository, setup)
    before = len(repository.list_revisions())
    app.run()
    button = app.button(key="space_layout_save")
    assert not button.disabled
    button.click().run()

    assert not app.exception, [item.message for item in app.exception]
    line = STALE_SCENARIO_EDITS_ELSEWHERE.format(cells=1, units=1)
    assert any(line in text for text in _errors(app)), _errors(app)
    assert not any("다른 사용자가 먼저" in text for text in _errors(app))
    assert len(repository.list_revisions()) == before


def test_a_stale_space_layout_save_still_writes_the_pending_fab_layout(tmp_path: Path) -> None:
    """낡은 세션의 Space 「배치 저장」 에 FAB 전체 배치 대기분이 있으면 FAB 는 저장하고 설비 쪽만
    같은 글로 막는다 — FAB 는 설비 리비전과 무관한 별도 쓰기라 설비 저장의 거부가 막지 않는다(예전
    그대로). 낡은 세션 검사를 FAB 쓰기 **앞**으로 올리면 FAB 대기분도 쓰지 않고 멈춰 이 시험이
    실패한다 — 그 차례 바꿈은 사용자 확인 전이다(2026-10-26 리뷰)."""
    from capa_simulation.components.equipment_data_workspace import PENDING_FAB_KEY

    repository, setup = _two_scenarios(tmp_path)
    pinned = _scenario(repository, setup).latest_schedule_revision_id
    app = AppTest.from_string(
        _page_with_edits(SPACE_PAGE, repository.database_path), default_timeout=90
    )
    app.session_state["fab"] = "MINE"
    _start(app, setup, pinned)
    assert PENDING_FAB_KEY in app.session_state
    _stale(repository, setup)
    before = len(repository.list_revisions())
    app.run()
    app.button(key="space_layout_save").click().run()

    assert not app.exception, [item.message for item in app.exception]
    line = STALE_SCENARIO_EDITS_ELSEWHERE.format(cells=1, units=1)
    errors = _errors(app)
    assert any(line in text and "FAB 전체 배치는 저장했지만" in text for text in errors), errors
    assert [mark.mark_id for mark in repository.load_fab_layout_marks()] == ["MINE"]
    assert PENDING_FAB_KEY not in app.session_state
    assert len(repository.list_revisions()) == before


def test_only_the_workspace_calls_the_repository_equipment_save() -> None:
    """설비 리비전 쓰기(`repository.save_equipment`)는 `save_equipment_buffer` 한 곳만 부른다 — 다른
    자리가 부르면 저장 전 검사(칸 초안·예시 행·낡은 세션)와 제 저장 판정을 건너뛴다."""
    callers: list[str] = []
    for path in sorted(
        [
            PROJECT_ROOT / "app.py",
            *(PROJECT_ROOT / "app_pages").rglob("*.py"),
            *(PROJECT_ROOT / "scripts").rglob("*.py"),
            *(PROJECT_ROOT / "src" / "capa_simulation").rglob("*.py"),
        ]
    ):
        if "persistence" in path.parts:
            continue
        with warnings.catch_warnings():
            # 옛 스크립트의 정규식 글자(「\.」)가 파싱 때 경고를 낸다 — 이 그물과 상관없다.
            warnings.simplefilter("ignore", SyntaxWarning)
            warnings.simplefilter("ignore", DeprecationWarning)
            tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "save_equipment"
            ):
                callers.append(f"{path.relative_to(PROJECT_ROOT)}:{node.lineno}")
    assert [caller.split(":")[0] for caller in callers] == [
        "src/capa_simulation/components/equipment_data_workspace.py"
    ], callers
