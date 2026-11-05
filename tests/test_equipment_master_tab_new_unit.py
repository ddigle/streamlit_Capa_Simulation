# Purpose: 설비 마스터 탭 「새 호기」 칸의 열기·초안·체크·가져오기·호기 추가와 저장의 넣기를 본다.

"""탭 ① 「설비 마스터」 오른쪽 「새 호기」 칸(개편 명세 4-6 나·10장 C).

표 대역(`tests/grid_fake.py`)으로 불러오기 「+ 새 호기」·상세 「이 호기로 새 호기 만들기」·「새
호기」 칸의 초안(`draft`)·가져오기(`copy`)·「호기 추가」(출납 `add`)를 보내고, 「리비전 저장」 이
새 호기를 늘 다른 설비 시나리오에 함께 넣는지 본다(옛 판 세션의 고름이 남아 있어도). 설비 시나리오는
「운영 일정」(공식) 과 그 복제 「셋업 실무」 둘이다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from alert_marks import successes
from grid_fake import Calls, install_fake_grid, last, send, send_ops
from streamlit.testing.v1 import AppTest
from test_equipment_assumption_rawdata import _grouped_fleet, _two_scenarios
from test_equipment_pages import PROJECT_ROOT, _page_script
from test_equipment_scenario_repository import _request, _scenario, _session, _set, _value

from capa_simulation import alerts
from capa_simulation.components import equipment_master_grid as emg
from capa_simulation.components.equipment_data_workspace import (
    BUFFER_GENERATION_KEY,
    BUFFER_KEY,
    GRID_DETAIL_KEY,
    GRID_LOADED_KEY,
    LAYOUT_ROLE_KEY,
    NEW_UNIT_DRAFT_KEY,
)
from capa_simulation.components.equipment_master_tab import (
    NEW_UNIT_OVERLAY_NOTE,
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
SPACE_PAGE = PROJECT_ROOT / "app_pages" / "space_status.py"
OPERATIONS = "operations"
NEW_KEY = emg.side_key("new")
# 옛 판이 세션에 남긴 호기별 고름 칸 — 지금 판은 읽지 않는다.
OLD_CHOICE_KEY = "equipment_new_unit_propagate_v1"


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


def _send_draft(app: AppTest, values: list[str], *, seq: int) -> AppTest:
    return _ok(send(app, NEW_KEY, "draft", {"seq": seq, "values": values}))


def _add(
    app: AppTest,
    grid: Calls,
    values: list[str],
    *,
    draft_seq: int | None = None,
) -> AppTest:
    """「호기 추가」 op — 초안 번호는 브라우저처럼 세션 초안 번호를 따른다(처음은 5, 넣은 뒤에는
    파이썬이 올린 번호). `draft_seq` 를 주면 그 번호(두 번 누름처럼 옛 번호)."""
    if draft_seq is None:
        session = (
            app.session_state[NEW_UNIT_DRAFT_KEY] if NEW_UNIT_DRAFT_KEY in app.session_state else {}
        )
        draft_seq = max(5, int(session.get("seq", 0)))
    return _ok(
        send_ops(app, grid, {"op": "add", "draftSeq": draft_seq, "draft": values}, key=NEW_KEY)
    )


def _enter_elsewhere(app: AppTest, name: str, *, move: str | None = None) -> None:
    """설비 마스터 탭 밖의 길(엑셀·CSV 넣기·Space 새 호기)로 든 새 호기 — 첫 호기를 본뜬 한 줄을
    자리 없이 편집본에 잇고 편집본 세대를 올린다(`replace_equipment_buffer` 와 같은 세대 규칙).
    `move` 를 주면 그 있던 호기의 X좌표도 옮긴다(Space 저장 상자가 서는 배치 변경)."""
    frames = app.session_state[BUFFER_KEY]
    master = _with_copy_of_first(frames[1], name)
    if move is not None:
        master.loc[master["설비명"].eq(move), "X좌표"] = 70.0
    app.session_state[BUFFER_KEY] = (frames[0], master, frames[2])
    generation = (
        app.session_state[BUFFER_GENERATION_KEY]
        if BUFFER_GENERATION_KEY in app.session_state
        else 0
    )
    app.session_state[BUFFER_GENERATION_KEY] = int(generation) + 1


def _with_copy_of_first(master: pd.DataFrame, name: str) -> pd.DataFrame:
    """첫 호기를 본뜬 새 호기 한 줄(자리 없이)을 끝에 이은 사본 — 칸 dtype 그대로."""
    grown = master.reindex(range(len(master) + 1))
    end = len(master)
    for column in master.columns:
        grown.at[end, column] = master.iloc[0][column]
    grown.at[end, "설비명"] = name
    for column in ("동", "층", "X좌표", "Y좌표"):
        grown.at[end, column] = None
    return grown.astype(master.dtypes.to_dict())


def _save(app: AppTest) -> AppTest:
    app.session_state[SIDE_KEY] = SIDE_CHANGES
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
    assert set(panel["draft"]) == {"seq", "values"}


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

    _add(app, grid, _draft(설비명="EQ-09", 공정소분류="Process-A", 동="C2", 층="3F"))

    master = app.session_state[BUFFER_KEY][1]
    assert len(master) == before + 1 and master.iloc[-1]["설비명"] == "EQ-09"
    assert app.session_state[GRID_LOADED_KEY][0] == "n:EQ-09"
    assert app.session_state[GRID_DETAIL_KEY] == "n:EQ-09"
    assert app.session_state[SIDE_KEY] == SIDE_DETAIL
    detail = last(grid, emg.side_key("detail"))
    assert detail["unit"]["id"] == "n:EQ-09" and detail["unit"]["tag"] == "new"
    assert detail["toast"]["text"].startswith("EQ-09를 표 맨 위에 넣었습니다")
    assert detail["toast"]["undo"]
    draft = app.session_state[NEW_UNIT_DRAFT_KEY]
    assert draft["values"] == _draft(공정소분류="Process-A", 동="C2", 층="3F")
    assert draft["seq"] > 5 and set(draft) == {"seq", "values"}


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


def test_every_new_unit_spreads_when_saved_and_the_result_says_how_many(
    tmp_path: Path, grid: Calls
) -> None:
    """「새 호기」 칸에서 넣은 호기는 늘 다른 설비 시나리오에 같은 일정으로 들어가고 결과 알림이 그
    대수를 적는다(2026-11-05 사용자 답 — 호기별 체크를 걷었다)."""
    repository, setup = _two_scenarios(tmp_path)
    app = _page(repository, OPERATIONS)
    _open_new(app)
    _add(app, grid, _draft(설비명="EQ-08", 공정소분류="Process-A", 반입일정="2026-11-02"))
    app.session_state[SIDE_KEY] = SIDE_NEW
    _ok(app.run())
    _add(app, grid, _draft(설비명="EQ-09", 공정소분류="Process-A"))

    _save(app)

    message = " ".join(str(item.value) for item in successes(app))
    assert "설비 데이터를 저장했습니다" in message
    assert "다른 설비 시나리오 1개에 호기 2대" in message
    assert "「새 호기」 칸에서" not in message
    other = _session(repository, setup)
    assert other.unscheduled_units == frozenset()
    assert {"EQ-08", "EQ-09"} <= set(other.equipment["설비명"])
    assert _value(other, "EQ-08", "반입일정") == pd.Timestamp("2026-11-02")


def test_a_unit_left_off_by_the_old_choice_still_spreads_and_nothing_breaks(
    tmp_path: Path, grid: Calls
) -> None:
    """옛 판에서 함께 넣기를 끄고 넣어 저장 전 편집에 남은 호기 — 옛 고름 칸 · 옛 꼴 초안 · 옛 꼴
    op(`propagate` 칸)가 그대로 있어도 칸이 그려지고 저장되며 늘 넣는다. 이름을 바꾼 뒤에도 같고,
    다른 길로 든 새 호기와 섞여도 같다."""
    repository, setup = _two_scenarios(tmp_path)
    app = _page(repository, OPERATIONS)
    _open_new(app)
    old_draft = _draft(공정소분류="Process-A")
    app.session_state[NEW_UNIT_DRAFT_KEY] = {"seq": 5, "values": old_draft, "propagate": False}
    _ok(app.run())
    assert _panel(grid)["draft"] == {"seq": 5, "values": old_draft}

    typed = _draft(설비명="EQ-07", 공정소분류="Process-A")
    _ok(send(app, NEW_KEY, "draft", {"seq": 6, "values": typed, "propagate": False}))
    assert _panel(grid)["draft"] == {"seq": 6, "values": typed}

    _ok(
        send_ops(
            app,
            grid,
            {"op": "add", "draftSeq": 6, "draft": typed, "propagate": False},
            key=NEW_KEY,
        )
    )
    app.session_state[OLD_CHOICE_KEY] = {"EQ-07": False}
    send_ops(app, grid, {"op": "cell", "id": "n:EQ-07", "col": "설비명", "text": "EQ-09"})
    _enter_elsewhere(app, "EQ-08")

    _save(app)

    message = " ".join(str(item.value) for item in successes(app))
    assert "다른 설비 시나리오 1개에 호기 2대" in message
    assert "「새 호기」 칸에서" not in message
    other = _session(repository, setup)
    assert other.unscheduled_units == frozenset()
    assert {"EQ-08", "EQ-09"} <= set(other.equipment["설비명"])


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
    typed = {"seq": 3, "values": _draft(설비명="EQ-30", 반입일정="2026-12-01")}

    _ok(send(app, NEW_KEY, "copy", {"query": "없는", "draft": typed}))
    missed = _panel(grid)
    assert missed["toast"]["text"] == "「없는」 설비명을 찾지 못했습니다"
    assert missed["draft"]["values"][eg.NAME_INDEX] == "EQ-30"

    _ok(send(app, NEW_KEY, "copy", {"query": "eq-0", "draft": typed}))
    values = _panel(grid)["draft"]["values"]
    assert _panel(grid)["draft"]["seq"] == 4
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


def test_an_assumption_session_notes_the_place_and_has_no_spread_warning(
    tmp_path: Path, grid: Calls
) -> None:
    repository, setup = _two_scenarios(tmp_path)
    app = _page(repository, setup)
    app.session_state[SIDE_KEY] = SIDE_NEW
    _ok(app.run())
    panel = _panel(grid)

    assert "propagateWarning" not in panel and "propagateDefault" not in panel
    # 가정 배치 안내는 표지 + 풍선 짝이다(설계 규칙 UI-TXT-01 — 브라우저는 표지만 그린다).
    assert ["가정 배치 · 공식에는 자리 없이", NEW_UNIT_OVERLAY_NOTE] in panel["notes"]
    assert "가정 설비 시나리오" in NEW_UNIT_OVERLAY_NOTE


def test_a_new_unit_saved_in_an_assumption_session_has_no_official_place(
    tmp_path: Path, grid: Calls
) -> None:
    """설계 Q1 — 가정 설비 시나리오에서 넣은 새 호기의 동·층은 그 시나리오의 배치 차이로만 저장되고
    공식 배치(공통 대장)에는 자리 없이 들어간다."""
    repository, setup = _two_scenarios(tmp_path)
    app = _page(repository, setup)
    app.session_state[SIDE_KEY] = SIDE_NEW
    _ok(app.run())

    _add(app, grid, _draft(설비명="EQ-09", 공정소분류="Process-A", 동="C2", 층="3F"))
    _save(app)

    assert any("설비 데이터를 저장했습니다" in str(item.value) for item in successes(app))
    official = _session(repository, OPERATIONS).equipment.set_index("설비명")
    mine = _session(repository, setup).equipment.set_index("설비명")
    assert pd.isna(official.loc["EQ-09", "동"]) and pd.isna(official.loc["EQ-09", "층"])
    assert (mine.loc["EQ-09", "동"], mine.loc["EQ-09", "층"]) == ("C2", "3F")


def test_adding_a_unit_stamps_the_layout_role_of_the_session(tmp_path: Path, grid: Calls) -> None:
    """새 호기 자리(동·층·레이아웃표시)는 배치 편집이다 — 「호기 추가」 도 붙여넣기 새 행·엑셀·CSV
    넣기처럼 그때의 역할을 찍는다(설계 6-2). 그래야 넣은 뒤 저장 전에 공식 설비 시나리오가 바뀌면
    화면 잠금·저장소 대조가 선다(가정 세션의 자리가 공식 대장으로 새지 않게 — Q1)."""
    repository, setup = _two_scenarios(tmp_path)
    mine = _page(repository, setup)
    mine.session_state[SIDE_KEY] = SIDE_NEW
    _ok(mine.run())
    assert LAYOUT_ROLE_KEY not in mine.session_state

    _add(mine, grid, _draft(설비명="EQ-09", 공정소분류="Process-A", 동="C2", 층="3F"))

    assert mine.session_state[LAYOUT_ROLE_KEY] == "overlay"
    official = _page(repository, OPERATIONS)
    _open_new(official)
    _add(official, grid, _draft(설비명="EQ-09", 공정소분류="Process-A", 동="C2", 층="3F"))
    assert official.session_state[LAYOUT_ROLE_KEY] == "official"


def test_a_second_add_in_a_later_run_is_dropped_and_keeps_the_kept_draft(
    tmp_path: Path, grid: Calls
) -> None:
    """두 번 누른 「호기 추가」 의 둘째 op 가 다음 회차에 따로 와도(같은 `draftSeq`, 「새 호기」
    칸이 아직 서 있음) 말없이 버린다 — 「아직 추가할 수 없습니다」 토스트도, 넣은 뒤 남긴
    초안(공정·동·층)을 옛 초안 전부로 같은 번호에 덮는 것도 없다(다시 열면 「이미 있는 호기」
    오류가 서던 길)."""
    repository, _ = _two_scenarios(tmp_path)
    app = _page(repository, OPERATIONS)
    _open_new(app)
    values = _draft(설비명="EQ-09", 공정소분류="Process-A", 동="C2", 층="3F")
    _add(app, grid, values, draft_seq=5)
    assert last(grid, emg.side_key("detail"))["toast"]["undo"]
    kept = dict(app.session_state[NEW_UNIT_DRAFT_KEY])
    before = len(app.session_state[BUFFER_KEY][1])
    app.session_state[SIDE_KEY] = SIDE_NEW
    _ok(app.run())

    _add(app, grid, values, draft_seq=5)

    assert len(app.session_state[BUFFER_KEY][1]) == before
    assert app.session_state[NEW_UNIT_DRAFT_KEY] == kept
    panel = _panel(grid)
    assert panel["toast"] is None
    assert panel["draft"]["values"][eg.NAME_INDEX] == ""
    assert str(eg.NAME_INDEX) not in panel["errors"] or "이미 있는" not in str(panel["errors"])


def test_a_module_added_in_an_assumption_session_takes_its_groups_floor_officially(
    tmp_path: Path, grid: Calls
) -> None:
    """설계 Q1 — 가정 설비 시나리오의 「새 호기」 칸으로 있는 묶음에 드는 모듈을 넣으면 공식
    배치(공통 대장)에는 좌표 없이 그 묶음의 동·층으로 들어간다(비모듈 새 호기는 자리 없이 — 위
    시험). 좌표·크기는 묶음 몫이라 칸에서 잠긴다."""
    repository, setup = _grouped_fleet(tmp_path)
    app = _page(repository, setup)
    app.session_state[GRID_DETAIL_KEY] = "s:MOD-1A"
    _ok(app.run())
    _ok(send(app, emg.side_key("detail"), "copy", {"id": "s:MOD-1A"}))
    values = list(_panel(grid)["draft"]["values"])
    values[eg.NAME_INDEX] = "MOD-1E"
    values[eg.COLUMN_INDEX["Main 설비"]] = "MOD-1"
    _send_draft(app, values, seq=_panel(grid)["draft"]["seq"] + 1)
    panel = _panel(grid)
    assert not panel["blocked"], panel["errors"]
    assert {eg.COLUMN_INDEX[c] for c in ("X좌표", "Y좌표", "Xsize", "Ysize")} <= {
        int(k) for k in panel["locks"]
    }

    _add(app, grid, values)
    _save(app)

    assert any("설비 데이터를 저장했습니다" in str(item.value) for item in successes(app))
    official = _session(repository, OPERATIONS).equipment.set_index("설비명")
    mine = _session(repository, setup).equipment.set_index("설비명")
    group = (official.loc["MOD-1A", "동"], official.loc["MOD-1A", "층"])
    assert (official.loc["MOD-1E", "동"], official.loc["MOD-1E", "층"]) == group
    assert pd.isna(official.loc["MOD-1E", "X좌표"]) and pd.isna(official.loc["MOD-1E", "Y좌표"])
    assert (mine.loc["MOD-1E", "동"], mine.loc["MOD-1E", "층"]) == group


def test_making_a_unit_from_a_vanished_detail_says_so_with_the_right_particle(
    tmp_path: Path, grid: Calls
) -> None:
    repository, _ = _two_scenarios(tmp_path)
    app = _page(repository, OPERATIONS)
    app.session_state[GRID_DETAIL_KEY] = "s:EQ-01"
    _ok(app.run())

    _ok(send(app, emg.side_key("detail"), "copy", {"id": "s:EQ-99"}))

    assert last(grid, emg.side_key("detail"))["toast"]["text"] == "그 호기를 찾지 못했습니다"


def test_an_assumption_tab_save_publishes_what_it_spreads_to_the_official(
    tmp_path: Path, grid: Calls
) -> None:
    """가정 설비 시나리오 세션의 탭 저장 — 「새 호기」 칸에서 넣은 호기는 공식 설비 시나리오에 새
    리비전을 만들고 체크 없이 공식 vN 을 내며 결과 알림이 그것을 적는다(저장소 기본값 그대로 —
    검수표 11/02 equip-13)."""
    repository, setup = _two_scenarios(tmp_path)
    app = _page(repository, setup)
    app.session_state[SIDE_KEY] = SIDE_NEW
    _ok(app.run())
    _add(app, grid, _draft(설비명="EQ-09", 공정소분류="Process-A"))
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    _ok(app.run())

    assert not list(app.checkbox)
    before = repository.latest_equipment_release()
    assert before is not None
    app.button(key=SAVE_BUTTON_KEY).click()
    _ok(app.run())

    message = " ".join(str(item.value) for item in successes(app))
    assert "설비 데이터를 저장했습니다" in message
    assert "EQ-09" in _session(repository, OPERATIONS).equipment["설비명"].tolist()
    after = repository.latest_equipment_release()
    assert after is not None and after.release_no == before.release_no + 1
    assert f"공식 v{after.release_no} 발행" in message


def test_an_assumption_tab_save_that_reaches_nothing_official_publishes_nothing(
    tmp_path: Path, grid: Calls
) -> None:
    """가정 설비 시나리오 세션에서 그 시나리오 일정만 고친 저장은 공식 설비 시나리오에 새 리비전을
    만들지 않는다 — 저장해도 공식 발행은 그대로다(옛 체크가 서지 않던 길과 같은 결과, I53). 저장소
    판정(`_plan_publish`)이 그렇게 가른다."""
    repository, setup = _two_scenarios(tmp_path)
    app = _page(repository, setup)
    send_ops(app, grid, {"op": "cell", "id": "s:EQ-02", "col": "시나리오 메모", "text": "가정"})
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    _ok(app.run())

    before = repository.latest_equipment_release()
    assert before is not None
    app.button(key=SAVE_BUTTON_KEY).click()
    _ok(app.run())

    message = " ".join(str(item.value) for item in successes(app))
    assert "설비 데이터를 저장했습니다" in message and "공식 v" not in message
    after = repository.latest_equipment_release()
    assert after is not None and after.release_no == before.release_no


def test_an_assumption_space_save_spreads_a_new_unit_to_the_official(tmp_path: Path) -> None:
    """가정 세션 Space 「배치 저장」 도 새 호기를 다른 설비 시나리오에 같은 일정으로 넣는다(설비
    마스터 탭·사이드바 팝업과 같음 — 저장 칸 체크는 없다, 검수표 11/02 equip-13). 호기 목록은 공통
    대장 하나라 공식에도 그 호기가 있고 일정도 같아 「일정 없음」 이 아니다. 공식으로 발행한다.
    자리는 그 가정 시나리오의 배치에만 있다(Q1)."""
    repository, setup = _two_scenarios(tmp_path)
    clear_equipment_repository()
    app = AppTest.from_string(
        _page_script(SPACE_PAGE, repository.database_path), default_timeout=90
    )
    app.session_state[SELECTION_KEY] = {"scenario_id": setup, "schedule_revision_id": None}
    app.session_state["space_status_selected_building"] = "C1"
    app.session_state["space_status_selected_floor"] = "1F"
    _ok(app.run())
    _enter_elsewhere(app, "EQ-09", move="EQ-02")
    _ok(app.run())
    before = repository.latest_equipment_release()
    assert before is not None
    assert not [box for box in app.checkbox if "space_layout_save_fields" in str(box.key)]

    app.button(key="space_layout_save").click()
    _ok(app.run())

    official = _session(repository, OPERATIONS)
    mine = _session(repository, setup)
    assert "EQ-09" in official.equipment["설비명"].tolist()
    assert official.unscheduled_units == frozenset() == mine.unscheduled_units
    for column in ("반입일정", "Qual일정"):
        assert _value(official, "EQ-09", column) == _value(mine, "EQ-09", column), column
    after = repository.latest_equipment_release()
    assert after is not None and after.release_no == before.release_no + 1


def _captions(app: AppTest) -> list[str]:
    return [str(item.value) for item in app.caption]


@pytest.mark.parametrize("scenario", [OPERATIONS, None], ids=["official", "assumption"])
def test_the_tab_save_section_has_only_note_saver_and_buttons(
    tmp_path: Path, grid: Calls, scenario: str | None
) -> None:
    """검수표 11/02 equip-13 — 저장 구획에 체크 · 경고 · 설명 줄이 없다. 지운 호기 · 함께 넣기 ·
    발행의 말은 Guide · 결과 알림이고 「리비전 저장」 풍선은 어디로 저장되나 한 줄이다."""
    repository, setup = _two_scenarios(tmp_path)
    app = _page(repository, scenario or setup)
    _open_new(app)
    _add(app, grid, _draft(설비명="EQ-09", 공정소분류="Process-A"))
    send_ops(app, grid, {"op": "delete", "ids": ["s:EQ-02"]})
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    _ok(app.run())

    assert not list(app.checkbox)
    assert not list(app.warning)
    captions = _captions(app)
    assert not any(
        "공식 가용대수" in text or "새 리비전으로 저장됩니다" in text for text in captions
    )
    assert not any("「새 호기」 칸에서" in text for text in captions)
    save = app.button(key=SAVE_BUTTON_KEY)
    assert "공통 칸은 모든 설비 시나리오에" in str(save.help)
    for gone in ("새 호기", "새 비가동", "공식으로 발행", "지운 호기"):
        assert gone not in str(save.help), gone
    assert app.text_input(key="equipment_workspace_save_saved_by").label == "저장자(선택)"


def _popup_save_box(database: str) -> None:
    """설비 화면 한 회차의 편집본 + 사이드바 설비 시나리오 팝업 본문(「저장」 구획)."""
    from pathlib import Path

    from capa_simulation.components.equipment_data_workspace import ensure_equipment_drafts
    from capa_simulation.components.equipment_scenario_status import (
        render_equipment_scenario_dialog_body,
    )
    from capa_simulation.equipment_scenario_activation import resolve_equipment_session

    ensure_equipment_drafts(resolve_equipment_session(database).snapshot)
    render_equipment_scenario_dialog_body(Path(database), page_file="available_equipment_status.py")


def test_the_assumption_sidebar_popup_save_has_no_checks_or_warning(tmp_path: Path) -> None:
    """검수표 11/02 equip-13 — 가정 설비 시나리오 세션의 사이드바 팝업 「저장」 도 체크 · 공식
    가용대수 경고가 없고 변경 메모 · 저장자 · 저장 단추만이다. 공식 세션도 같다."""
    from capa_simulation.components.equipment_scenario_status import (
        EQUIPMENT_SCENARIO_DIALOG_MODE_KEY,
        SAVE_MODE,
    )

    repository, setup = _two_scenarios(tmp_path)

    def popup(scenario_id: str) -> AppTest:
        clear_equipment_repository()
        app = AppTest.from_function(
            _popup_save_box, args=(str(repository.database_path),), default_timeout=60
        )
        app.session_state[EQUIPMENT_SCENARIO_DIALOG_MODE_KEY] = SAVE_MODE
        app.session_state[SELECTION_KEY] = {
            "scenario_id": scenario_id,
            "schedule_revision_id": None,
        }
        return _ok(app.run())

    for scenario_id in (setup, OPERATIONS):
        app = popup(scenario_id)
        assert not list(app.checkbox)
        assert "공식 가용대수" not in " ".join(_captions(app))


def _popup_with_panel_unit(database: str) -> None:
    """설비 화면 한 회차 + 사이드바 설비 시나리오 팝업 본문 — 처음 한 번 옛 판 「새 호기」 칸에서
    끄고 넣은 것처럼 새 호기 하나와 옛 고름 칸을 둔다."""
    from pathlib import Path

    import streamlit as st

    from capa_simulation.components.equipment_data_workspace import (
        ensure_equipment_drafts,
        replace_equipment_buffer,
    )
    from capa_simulation.components.equipment_scenario_status import (
        render_equipment_scenario_dialog_body,
    )
    from capa_simulation.equipment_scenario_activation import resolve_equipment_session

    session = resolve_equipment_session(database)
    frames = ensure_equipment_drafts(session.snapshot)
    if not st.session_state.get("added"):
        master = frames[1].reindex(range(len(frames[1]) + 1))
        for column in frames[1].columns:
            master.at[len(frames[1]), column] = frames[1].iloc[0][column]
        master.at[len(frames[1]), "설비명"] = "EQ-09"
        master = master.astype(frames[1].dtypes.to_dict())
        replace_equipment_buffer((frames[0], master, frames[2]))
        st.session_state["equipment_new_unit_propagate_v1"] = {"EQ-09": False}
        st.session_state["added"] = True
    render_equipment_scenario_dialog_body(Path(database), page_file="available_equipment_status.py")


def test_the_sidebar_popup_save_counts_a_unit_left_off_before(tmp_path: Path) -> None:
    """팝업 저장도 옛 판에서 끄고 넣은 호기까지 함께 넣고 결과 알림(알림창 · Alarm)이 그 대수를
    적는다 — 저장 전에 서던 한 줄은 없다."""
    from capa_simulation.components.equipment_scenario_status import (
        EQUIPMENT_SCENARIO_DIALOG_MODE_KEY,
        FLASH_KEY,
        SAVE_BUTTON_KEY,
        SAVE_MODE,
    )

    repository, setup = _two_scenarios(tmp_path)
    app = AppTest.from_function(
        _popup_with_panel_unit, args=(str(repository.database_path),), default_timeout=60
    )
    app.session_state[EQUIPMENT_SCENARIO_DIALOG_MODE_KEY] = SAVE_MODE
    _ok(app.run())
    assert not any("「새 호기」 칸에서" in text for text in _captions(app))

    app.button(key=SAVE_BUTTON_KEY).click()
    _ok(app.run())

    note = app.session_state[FLASH_KEY]
    assert note.popup_only and alerts.FLASH_CODES[note.kind] == "FL-01"
    assert "다른 설비 시나리오 1개에 호기 1대" in note.message
    assert "「새 호기」 칸에서" not in note.message
    other = _session(repository, setup)
    assert other.unscheduled_units == frozenset()
    assert "EQ-09" in other.equipment["설비명"].tolist()
