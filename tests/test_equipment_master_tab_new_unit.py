# Purpose: 설비 마스터 탭 「새 호기」 칸의 열기·초안·체크·가져오기·호기 추가·저장 함께 넣기를 본다.

"""탭 ① 「설비 마스터」 오른쪽 「새 호기」 칸(개편 명세 4-6 나·10장 C).

표 대역(`tests/grid_fake.py`)으로 불러오기 「+ 새 호기」·상세 「이 호기로 새 호기 만들기」·「새
호기」 칸의 초안(`draft`)·가져오기(`copy`)·「호기 추가」(출납 `add`)를 보내고, 「리비전 저장」 이
그 칸에서 고른 함께 넣기를 호기마다 저장소에 넘기는지(`propagate_units` — D8) 본다. 설비 시나리오는
「운영 일정」(공식) 과 그 복제 「셋업 실무」 둘이다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from grid_fake import Calls, install_fake_grid, last, send, send_ops
from streamlit.testing.v1 import AppTest
from test_equipment_assumption_rawdata import _two_scenarios
from test_equipment_pages import PROJECT_ROOT, _page_script
from test_equipment_scenario_repository import _request, _scenario, _session, _set

from capa_simulation.components import equipment_master_grid as emg
from capa_simulation.components.equipment_data_workspace import (
    BUFFER_KEY,
    GRID_DETAIL_KEY,
    GRID_LOADED_KEY,
    NEW_UNIT_DRAFT_KEY,
    NEW_UNIT_PROPAGATE_KEY,
    SAVE_FIELDS_PREFIX,
)
from capa_simulation.components.equipment_master_tab import (
    SAVE_BUTTON_KEY,
    SIDE_CHANGES,
    SIDE_DETAIL,
    SIDE_KEY,
    SIDE_NEW,
)
from capa_simulation.equipment_scenario_activation import SELECTION_KEY
from capa_simulation.navigation import EQUIPMENT_MASTER_TAB, EQUIPMENT_TAB_KEY
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services import equipment_grid as eg

PAGE = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
OPERATIONS = "operations"
NEW_KEY = emg.side_key("new")


@pytest.fixture(autouse=True)
def _release_repository() -> Any:
    clear_equipment_repository()
    yield
    clear_equipment_repository()


@pytest.fixture
def grid(monkeypatch: pytest.MonkeyPatch) -> Calls:
    return install_fake_grid(monkeypatch)


def _page(
    repository: DuckDBEquipmentRepository, scenario_id: str, schedule_revision_id: str | None = None
) -> AppTest:
    clear_equipment_repository()
    app = AppTest.from_string(_page_script(PAGE, repository.database_path), default_timeout=90)
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_MASTER_TAB
    app.session_state[SELECTION_KEY] = {
        "scenario_id": scenario_id,
        "schedule_revision_id": schedule_revision_id,
    }
    return _ok(app.run())


def _ok(app: AppTest) -> AppTest:
    assert not app.exception, [item.message for item in app.exception]
    return app


def _open_new(app: AppTest) -> dict[str, Any]:
    """불러오기 「+ 새 호기」 — 오른쪽 칸이 「새 호기」 로 선다."""
    _ok(send(app, emg.LOADER_KEY, "new", {}))
    assert app.session_state[SIDE_KEY] == SIDE_NEW
    return (
        dict(app.session_state[NEW_UNIT_DRAFT_KEY])
        if NEW_UNIT_DRAFT_KEY in app.session_state
        else {}
    )


def _panel(grid: Calls) -> dict[str, Any]:
    return last(grid, NEW_KEY)


def _draft(**cells: str) -> list[str]:
    values = eg.blank_draft()
    for column, text in cells.items():
        values[eg.COLUMN_INDEX[column]] = text
    return values


def _send_draft(app: AppTest, values: list[str], *, seq: int, propagate: bool = True) -> AppTest:
    return _ok(send(app, NEW_KEY, "draft", {"seq": seq, "values": values, "propagate": propagate}))


def _add(app: AppTest, grid: Calls, values: list[str], *, propagate: bool = True) -> AppTest:
    return _ok(
        send_ops(
            app,
            grid,
            {"op": "add", "draftSeq": 5, "draft": values, "propagate": propagate},
            key=NEW_KEY,
        )
    )


def _save(app: AppTest, *, spread: bool | None = None) -> AppTest:
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    _ok(app.run())
    if spread is not None:
        app.checkbox(key=f"{SAVE_FIELDS_PREFIX}_propagate_units").set_value(spread)
        _ok(app.run())
    app.button(key=SAVE_BUTTON_KEY).click()
    return _ok(app.run())


def test_the_loader_offers_new_and_the_panel_shows_the_check_bar(
    tmp_path: Path, grid: Calls
) -> None:
    repository, _ = _two_scenarios(tmp_path)
    app = _page(repository, OPERATIONS)
    loader = last(grid, emg.LOADER_KEY)
    assert loader["newEnabled"] is True and loader["newRowsLocked"] is False

    _open_new(app)
    panel = _panel(grid)

    assert panel["panel"] == "new" and panel["locked"] is None
    values = panel["draft"]["values"]
    assert [values[eg.COLUMN_INDEX[c]] for c in ("보관유무", "기존설비여부", "레이아웃표시")] == [
        "N",
        "N",
        "Y",
    ]
    assert panel["blocked"] is True
    assert panel["tiers"]["required"] == [
        [eg.COLUMN_INDEX["설비명"], False],
        [eg.COLUMN_INDEX["공정소분류"], False],
    ]
    assert [k for k, _ in panel["tiers"]["calc"]] == [
        eg.COLUMN_INDEX[c] for c in ("반입일정", "Qual일정", "사용기준")
    ]
    assert panel["draft"]["propagate"] is True and panel["propagateWarning"] is None


def test_a_sent_draft_is_checked_by_the_save_rules(tmp_path: Path, grid: Calls) -> None:
    repository, _ = _two_scenarios(tmp_path)
    app = _page(repository, OPERATIONS)
    _open_new(app)

    _send_draft(app, _draft(설비명="eq-01", 공정소분류="Process-A", Qual일정="2026-11-20"), seq=1)
    panel = _panel(grid)

    assert panel["draft"]["seq"] == 1 and panel["checked"] == 1
    assert panel["errors"][str(eg.COLUMN_INDEX["설비명"])] == "이미 있는 호기입니다: eq-01(EQ-01)"
    assert str(eg.COLUMN_INDEX["Qual상태"]) in panel["errors"]
    # 늦게 온 옛 초안은 새 초안을 덮지 않는다.
    _send_draft(app, _draft(설비명="OLD"), seq=0)
    assert _panel(grid)["draft"]["values"][eg.NAME_INDEX] == "eq-01"


def test_adding_puts_the_unit_on_top_opens_its_detail_and_keeps_process_and_floor(
    tmp_path: Path, grid: Calls
) -> None:
    repository, _ = _two_scenarios(tmp_path)
    app = _page(repository, OPERATIONS)
    _open_new(app)
    before = len(app.session_state[BUFFER_KEY][1])

    _add(
        app, grid, _draft(설비명="EQ-09", 공정소분류="Process-A", 동="C2", 층="3F"), propagate=False
    )

    master = app.session_state[BUFFER_KEY][1]
    assert len(master) == before + 1 and master.iloc[-1]["설비명"] == "EQ-09"
    assert app.session_state[GRID_LOADED_KEY][0] == "n:EQ-09"
    assert app.session_state[GRID_DETAIL_KEY] == "n:EQ-09"
    assert app.session_state[SIDE_KEY] == SIDE_DETAIL
    assert app.session_state[NEW_UNIT_PROPAGATE_KEY] == {"EQ-09": False}
    detail = last(grid, emg.side_key("detail"))
    assert detail["unit"]["id"] == "n:EQ-09" and detail["unit"]["tag"] == "new"
    assert detail["toast"]["text"].startswith("EQ-09를 표 맨 위에 넣었습니다")
    assert detail["toast"]["undo"]
    draft = app.session_state[NEW_UNIT_DRAFT_KEY]
    assert draft["values"] == _draft(공정소분류="Process-A", 동="C2", 층="3F")
    assert draft["seq"] > 5 and draft["propagate"] is False


def test_a_blocked_add_keeps_the_draft_and_says_why(tmp_path: Path, grid: Calls) -> None:
    repository, _ = _two_scenarios(tmp_path)
    app = _page(repository, OPERATIONS)
    _open_new(app)
    before = len(app.session_state[BUFFER_KEY][1])

    _add(app, grid, _draft(설비명="EQ-01", 공정소분류="Process-A"))

    assert len(app.session_state[BUFFER_KEY][1]) == before
    assert app.session_state[SIDE_KEY] == SIDE_NEW
    panel = _panel(grid)
    assert panel["toast"]["text"] == "아직 추가할 수 없습니다 — 설비명 칸을 확인합니다"
    assert panel["draft"]["values"][eg.NAME_INDEX] == "EQ-01" and panel["draft"]["seq"] == 5


def test_each_new_unit_spreads_by_its_own_choice_when_saved(tmp_path: Path, grid: Calls) -> None:
    """「새 호기」 칸에서 넣은 호기는 그 칸의 체크가 저장 칸 체크보다 이긴다(D8) — 끈 호기는 다른
    설비 시나리오에서 일정 없음, 켠 호기는 같은 일정으로 들어간다."""
    repository, setup = _two_scenarios(tmp_path)
    app = _page(repository, OPERATIONS)
    _open_new(app)
    _add(app, grid, _draft(설비명="EQ-08", 공정소분류="Process-A", 반입일정="2026-11-02"))
    app.session_state[SIDE_KEY] = SIDE_NEW
    _ok(app.run())
    _add(app, grid, _draft(설비명="EQ-09", 공정소분류="Process-A"), propagate=False)

    _save(app, spread=False)

    assert any("설비 데이터를 저장했습니다" in str(item.value) for item in app.success)
    # 저장 뒤에는 고름을 비운다(편집본과 함께 산다).
    assert not any("「새 호기」 칸에서 넣은" in str(item.value) for item in app.caption)
    other = _session(repository, setup)
    assert other.unscheduled_units == frozenset({"EQ-09"})
    assert "EQ-08" in other.equipment["설비명"].tolist()
    assert NEW_UNIT_PROPAGATE_KEY not in app.session_state


def test_the_save_section_counts_the_panel_choices(tmp_path: Path, grid: Calls) -> None:
    repository, _ = _two_scenarios(tmp_path)
    app = _page(repository, OPERATIONS)
    _open_new(app)
    _add(app, grid, _draft(설비명="EQ-09", 공정소분류="Process-A"), propagate=False)

    app.session_state[SIDE_KEY] = SIDE_CHANGES
    _ok(app.run())

    assert any(
        "「새 호기」 칸에서 넣은 1대는 그 칸의 체크를 따릅니다 — 다른 설비 시나리오에 같은 "
        "일정으로 0대 · 일정 없음 1대" in str(item.value)
        for item in app.caption
    )


def test_renaming_a_panel_unit_keeps_its_choice(tmp_path: Path, grid: Calls) -> None:
    repository, _ = _two_scenarios(tmp_path)
    app = _page(repository, OPERATIONS)
    _open_new(app)
    _add(app, grid, _draft(설비명="EQ-09", 공정소분류="Process-A"), propagate=False)

    send_ops(app, grid, {"op": "cell", "id": "n:EQ-09", "col": "설비명", "text": "EQ-19"})

    assert app.session_state[NEW_UNIT_PROPAGATE_KEY] == {"EQ-19": False}


def test_make_a_new_unit_from_the_detail_copies_info_and_place(tmp_path: Path, grid: Calls) -> None:
    repository, _ = _two_scenarios(tmp_path)
    app = _page(repository, OPERATIONS)
    app.session_state[GRID_DETAIL_KEY] = "s:EQ-01"
    _ok(app.run())

    _ok(send(app, emg.side_key("detail"), "copy", {"id": "s:EQ-01"}))

    assert app.session_state[SIDE_KEY] == SIDE_NEW
    values = _panel(grid)["draft"]["values"]
    assert values[eg.COLUMN_INDEX["공정소분류"]] == "Process-A"
    assert (values[eg.COLUMN_INDEX["동"]], values[eg.COLUMN_INDEX["층"]]) == ("C1", "1F")
    assert values[eg.NAME_INDEX] == "" and values[eg.COLUMN_INDEX["반입일정"]] == ""
    assert values[eg.COLUMN_INDEX["X좌표"]] == ""
    assert _panel(grid)["toast"]["text"].startswith("EQ-01 의 호기 정보·위치를 가져왔습니다")


def test_copying_by_name_keeps_what_was_typed_and_tells_a_miss(tmp_path: Path, grid: Calls) -> None:
    repository, _ = _two_scenarios(tmp_path)
    app = _page(repository, OPERATIONS)
    _open_new(app)
    typed = {"seq": 3, "values": _draft(설비명="EQ-30", 반입일정="2026-12-01"), "propagate": False}

    _ok(send(app, NEW_KEY, "copy", {"query": "없는", "draft": typed}))
    missed = _panel(grid)
    assert missed["toast"]["text"] == "「없는」 설비명을 찾지 못했습니다"
    assert missed["draft"]["values"][eg.NAME_INDEX] == "EQ-30"

    _ok(send(app, NEW_KEY, "copy", {"query": "eq-0", "draft": typed}))
    values = _panel(grid)["draft"]["values"]
    assert _panel(grid)["draft"]["seq"] == 4 and _panel(grid)["draft"]["propagate"] is False
    assert values[eg.NAME_INDEX] == "EQ-30"
    assert values[eg.COLUMN_INDEX["반입일정"]] == "2026-12-01"
    assert values[eg.COLUMN_INDEX["공정소분류"]] == "Process-A"


def test_a_stale_session_locks_the_panel_and_the_loader_button(tmp_path: Path, grid: Calls) -> None:
    repository, setup = _two_scenarios(tmp_path)
    pinned = _scenario(repository, setup).latest_schedule_revision_id
    theirs = _session(repository, setup)
    repository.save_equipment(
        _request(theirs, setup, equipment=_set(theirs.equipment, "EQ-02", "시나리오 메모", "남의"))
    )
    app = _page(repository, setup, pinned)
    assert last(grid, emg.LOADER_KEY)["newRowsLocked"] is True

    app.session_state[SIDE_KEY] = SIDE_NEW
    _ok(app.run())
    panel = _panel(grid)

    assert panel["locked"] and "더 새롭습니다" in panel["locked"]
    _add(app, grid, _draft(설비명="EQ-09", 공정소분류="Process-A"))
    assert "EQ-09" not in app.session_state[BUFFER_KEY][1]["설비명"].tolist()


def test_an_assumption_session_warns_that_spreading_counts_in_the_official_scenario(
    tmp_path: Path, grid: Calls
) -> None:
    repository, setup = _two_scenarios(tmp_path)
    app = _page(repository, setup)
    app.session_state[SIDE_KEY] = SIDE_NEW
    _ok(app.run())
    panel = _panel(grid)

    assert panel["propagateWarning"] and "공식 가용대수" in panel["propagateWarning"]
    assert any("가정 설비 시나리오" in note for note in panel["notes"])


def test_a_new_unit_saved_in_an_assumption_session_has_no_official_place(
    tmp_path: Path, grid: Calls
) -> None:
    """설계 Q1 — 가정 설비 시나리오에서 넣은 새 호기의 동·층은 그 시나리오의 배치 차이로만 저장되고
    공식 배치(공통 대장)에는 자리 없이 들어간다."""
    repository, setup = _two_scenarios(tmp_path)
    app = _page(repository, setup)
    app.session_state[SIDE_KEY] = SIDE_NEW
    _ok(app.run())

    _add(
        app, grid, _draft(설비명="EQ-09", 공정소분류="Process-A", 동="C2", 층="3F"), propagate=False
    )
    _save(app)

    assert any("설비 데이터를 저장했습니다" in str(item.value) for item in app.success)
    official = _session(repository, OPERATIONS).equipment.set_index("설비명")
    mine = _session(repository, setup).equipment.set_index("설비명")
    assert pd.isna(official.loc["EQ-09", "동"]) and pd.isna(official.loc["EQ-09", "층"])
    assert (mine.loc["EQ-09", "동"], mine.loc["EQ-09", "층"]) == ("C2", "3F")
