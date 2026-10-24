# Purpose: Space 가 세션 설비 시나리오의 배치를 그리고 역할대로 편집·잠그는 흐름(설비 시나리오 2단계
# S3)을 본다.

"""설비 시나리오 2단계 S3 — Space 현황(LY3·LY4·G5·Q1·Q3).

- 그리는 한 벌은 세션 설비 시나리오다 — 가정이면 그 리비전의 배치 차이가 얹히고 머리 알림·사이드바
  「가정 배치」 배지가 선다. 뷰어 epoch 는 잠긴 회차에도 쌍 토큰을 담는다(검토 F1).
- 편집 권한은 `space_edit_mode` 한 판정 — 가정 최신은 그 시나리오의 배치 차이를, 가정·낡음은 배치
  지문이 같으면 빨리 감기로, 다르면 잠금(「최신 rM 불러오기」), 공식 시나리오의 가정이던 때 리비전은
  잠금. FAB 전체·층 캔버스·층 사용은 공식 시나리오에서만.
- Space 저장 상자의 「새 호기를 다른 설비 시나리오에도 넣기」 는 가정 세션에서 기본 끔(Q1).
- `app_pages/space_status.py` 에는 공식 층 요소·이름표 직접 읽기가 없다(검토 F15).

편집기 JS 는 AppTest 가 돌리지 못해 `_EDITOR` 를 대역으로 바꿔 받은 data 를 적어 둔다
(`test_space_layout_editor_page.py` 와 같은 꼴).
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from test_equipment_pages import PROJECT_ROOT, _page_script
from test_equipment_scenario_repository import (
    OPERATIONS,
    _clone,
    _request,
    _seeded,
    _session,
    _set,
)

from capa_simulation.components import space_layout_editor
from capa_simulation.components.equipment_data_workspace import (
    LAYOUT_ROLE_KEY,
    _csv_scenario_mismatch,
)
from capa_simulation.components.equipment_save_fields import (
    EquipmentSaveFields,
)
from capa_simulation.equipment_scenario_activation import SELECTION_KEY
from capa_simulation.navigation import SPACE_STATUS
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.korean_particle import subject_particle

PAGE = PROJECT_ROOT / "app_pages" / "space_status.py"
FAKE_APPLY_KEY = "test_fake_editor_apply"


@pytest.fixture(autouse=True)
def _fresh_caches() -> Any:
    clear_equipment_repository()
    yield
    clear_equipment_repository()


@pytest.fixture
def editor_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def _stub(**kwargs: Any) -> SimpleNamespace:
        import streamlit as st

        calls.append(kwargs["data"])
        return SimpleNamespace(apply=st.session_state.pop(FAKE_APPLY_KEY, None))

    monkeypatch.setattr(space_layout_editor, "_EDITOR", _stub)
    return calls


def _scenario(repository: DuckDBEquipmentRepository, scenario_id: str) -> Any:
    return next(
        item
        for item in repository.list_equipment_scenarios()
        if item.equipment_scenario_id == scenario_id
    )


def _overlay(tmp_path: Path) -> tuple[DuckDBEquipmentRepository, str]:
    """「운영 일정」 r1(공식 v1) + 복제한 「셋업 실무」 — r2 에서 EQ-01 을 X=50 으로 옮긴 가정
    배치."""
    repository = _seeded(tmp_path)
    clone = _clone(repository)
    mine = _session(repository, clone.equipment_scenario_id)
    repository.save_equipment(
        _request(
            mine,
            clone.equipment_scenario_id,
            equipment=_set(mine.equipment, "EQ-01", "X좌표", 50.0),
        )
    )
    assert _scenario(repository, clone.equipment_scenario_id).latest_layout_unit_count == 1
    return repository, clone.equipment_scenario_id


def _space(
    tmp_path: Path, scenario_id: str, schedule_revision_id: str | None = None, *, floor: bool = True
) -> AppTest:
    app = AppTest.from_string(_page_script(PAGE, tmp_path / "equipment.duckdb"), default_timeout=60)
    app.session_state[SELECTION_KEY] = {
        "scenario_id": scenario_id,
        "schedule_revision_id": schedule_revision_id,
    }
    if floor:
        app.session_state["space_status_selected_building"] = "C1"
        app.session_state["space_status_selected_floor"] = "1F"
    return app


def _ok(app: AppTest) -> AppTest:
    assert not app.exception, [item.message for item in app.exception]
    return app


def _texts(app: AppTest) -> list[str]:
    return [
        str(item.value)
        for kind in ("caption", "info", "warning", "success", "error", "markdown")
        for item in getattr(app, kind)
    ]


def _viewer(calls: list[dict[str, Any]]) -> dict[str, Any]:
    return next(call for call in reversed(calls) if call.get("mode") == "view")


def _x_of(data: dict[str, Any], name: str) -> float:
    return float(next(item for item in data["items"] if item["id"] == name)["x"])


def test_space_is_declared_on_the_session_equipment_scenario() -> None:
    assert SPACE_STATUS.equipment_scenario == "session"


def test_the_space_page_reads_floor_layout_only_through_the_merge() -> None:
    """공식 층 요소·이름표를 직접 읽는 자리가 하나라도 남으면 가정 회차의 경고·편집 기준이 공식으로
    판정된다(검토 F15·M7) — 모두 `effective_floor_layout` 를 지난다."""
    source = PAGE.read_text(encoding="utf-8")
    assert not re.search(r"load_floor_layout_marks|load_floor_group_labels", source)
    assert "effective_floor_layout(" in source
    assert "official_session" not in source and "FIXED_LOCK_REASON" not in source


def test_an_assumption_session_draws_its_layout_with_the_notice_and_badge(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    _, setup = _overlay(tmp_path)
    app = _ok(_space(tmp_path, setup).run())

    assert _x_of(_viewer(editor_calls), "EQ-01") == 50.0
    assert any("가정 배치 · 공식과 다른 호기 1대" in str(item.value) for item in app.info)
    assert any("가정 배치" in str(item.value) for item in app.sidebar.caption)
    # 층 배치 편집이 열린다(LY4 — 1단계 「공식 발행 쌍에서만」 잠금은 걷었다).
    assert not app.toggle(key="space_layout_edit_mode").disabled

    official = _ok(_space(tmp_path, OPERATIONS).run())
    assert not any("가정 배치" in str(item.value) for item in official.info)


def test_the_viewer_epoch_follows_the_pair_even_while_editing_is_locked(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """잠긴 회차에도 epoch 가 쌍 토큰을 담는다 — 같은 epoch 회차에 브라우저는 상자 기하를 쥔 것대로
    지키므로, 잠긴 두 쌍을 오갈 때 epoch 가 같으면 옛 좌표가 남는다(검토 F1·H1)."""
    repository, setup = _overlay(tmp_path)
    second = _scenario(repository, setup)
    mine = _session(repository, setup)
    repository.save_equipment(
        _request(mine, setup, equipment=_set(mine.equipment, "EQ-02", "X좌표", 70.0))
    )
    first_id = next(
        item.schedule_revision_id
        for item in repository.list_schedule_revisions(setup)
        if item.revision_no == 1
    )
    app = _ok(_space(tmp_path, setup, second.latest_schedule_revision_id).run())
    locked = _viewer(editor_calls)
    assert app.toggle(key="space_layout_edit_mode_locked").disabled
    app.session_state[SELECTION_KEY] = {"scenario_id": setup, "schedule_revision_id": first_id}
    _ok(app.run())
    older = _viewer(editor_calls)

    # 쌍 토큰(「공통|일정」)이 epoch 안에 든다 — 일정 쪽이 달라 epoch 가 갈린다.
    assert second.latest_schedule_revision_id in locked["epoch"]
    assert first_id in older["epoch"] and locked["epoch"] != older["epoch"]
    assert (_x_of(locked, "EQ-01"), _x_of(older, "EQ-01")) == (50.0, 10.0)


def test_an_assumption_layout_apply_saves_as_that_scenarios_revision(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    repository, setup = _overlay(tmp_path)
    app = _ok(_space(tmp_path, setup).run())
    app.toggle(key="space_layout_edit_mode").set_value(True).run()
    data = editor_calls[-1]
    # 층 캔버스는 공용 값이라 가정 세션 편집기에서 끈다(설계 8-4).
    assert data["canvasEditable"] is False and data["canvasLock"]
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": data["epoch"],
        "changes": [{"id": "EQ-02", "placed": True, "x": 60, "y": 20, "w": 12, "h": 7}],
        "canvas": None,
        "marks": None,
    }
    _ok(app.run())
    assert app.session_state[LAYOUT_ROLE_KEY] == "overlay"
    assert any("의 새 리비전(가정 배치)으로 저장합니다" in text for text in _texts(app))
    # 저장 칸 — 가정 세션은 함께 넣기 기본 끔이고 발행 체크는 켰을 때만(Q1).
    propagate = app.checkbox(key="space_layout_save_fields_propagate_units_assumption")
    assert propagate.value is False
    assert not [box for box in app.checkbox if str(box.key).endswith("_publish_assumption")]

    app.button(key="space_layout_save").click().run()
    _ok(app)
    scenario = _scenario(repository, setup)
    assert scenario.latest_revision_no == 3 and scenario.latest_layout_unit_count == 2
    official = repository.load_official_snapshot()
    assert official is not None
    assert official.equipment.set_index("설비명").loc["EQ-02", "X좌표"] != 60.0
    assert any("가정 배치를 저장했습니다(공식과 다른 호기 2대)" in text for text in _texts(app))
    assert LAYOUT_ROLE_KEY not in app.session_state


def test_a_stale_assumption_with_the_same_layout_fast_forwards(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """남이 그 시나리오에 일정만 저장했다(배치 지문 같음) — 배치 편집은 이어지고 저장은 최신의 일정
    위 새 리비전이다(설계 6-1 빨리 감기)."""
    repository, setup = _overlay(tmp_path)
    pinned = _scenario(repository, setup).latest_schedule_revision_id
    theirs = _session(repository, setup)
    repository.save_equipment(
        _request(theirs, setup, equipment=_set(theirs.equipment, "EQ-02", "Qual일정", "2026-09-01"))
    )
    app = _ok(_space(tmp_path, setup, pinned).run())
    assert any("더 새롭지만 배치는 같습니다" in text for text in _texts(app))
    app.toggle(key="space_layout_edit_mode").set_value(True).run()
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": editor_calls[-1]["epoch"],
        "changes": [{"id": "EQ-02", "placed": True, "x": 60, "y": 20, "w": 12, "h": 7}],
        "canvas": None,
        "marks": None,
    }
    _ok(app.run())
    app.button(key="space_layout_save").click().run()
    _ok(app)

    scenario = _scenario(repository, setup)
    assert scenario.latest_revision_no == 4
    latest = _session(repository, setup).equipment.set_index("설비명")
    assert latest.loc["EQ-02", "X좌표"] == 60.0
    assert str(latest.loc["EQ-02", "Qual일정"])[:10] == "2026-09-01"


def test_a_stale_assumption_with_another_layout_locks_and_loads_the_latest(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    repository, setup = _overlay(tmp_path)
    pinned = _scenario(repository, setup).latest_schedule_revision_id
    theirs = _session(repository, setup)
    repository.save_equipment(
        _request(theirs, setup, equipment=_set(theirs.equipment, "EQ-02", "X좌표", 70.0))
    )
    app = _ok(_space(tmp_path, setup, pinned).run())

    assert any("r3 에 다른 배치가 저장됐습니다" in text for text in _texts(app))
    assert app.toggle(key="space_layout_edit_mode_locked").disabled
    app.button(key="space_load_latest").click().run()
    _ok(app)
    latest = _scenario(repository, setup).latest_schedule_revision_id
    assert app.session_state[SELECTION_KEY]["schedule_revision_id"] == latest
    assert not app.toggle(key="space_layout_edit_mode").disabled


def test_an_official_revision_from_its_assumption_days_is_locked_with_a_notice(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """가정이던 「셋업 실무」 의 배치 차이를 지우고 공식으로 낸 뒤, 차이가 있던 옛 리비전을 연
    회차 — 합친 본문은 그 차이를 그대로 그리므로 알리고(검토 M8) 배치 편집을 잠근다(설계 8-4)."""
    repository, setup = _overlay(tmp_path)
    overlaid = _scenario(repository, setup).latest_schedule_revision_id
    cleared = repository.clear_layout_overlay(setup, expected_latest_schedule_revision_id=overlaid)
    assert cleared is not None
    repository.publish_equipment_release(
        cleared.schedule_revision_id, released_by=None, note=None, expected_latest_release_no=1
    )
    app = _ok(_space(tmp_path, setup, overlaid).run())

    assert any("이 리비전은 공식과 다른 배치" in str(item.value) for item in app.info)
    assert any("가정이던 때의 배치 차이" in text for text in _texts(app))
    assert app.toggle(key="space_layout_edit_mode_locked").disabled
    assert _x_of(_viewer(editor_calls), "EQ-01") == 50.0


def test_an_assumption_session_locks_fab_canvas_and_floor_use(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """FAB 전체·층 캔버스·층 사용은 공식 설비 시나리오에서만(G5·Q3) — 꺼진 단추와 까닭 풍선."""
    _, setup = _overlay(tmp_path)
    fab = _ok(_space(tmp_path, setup, floor=False).run())
    toggle = fab.toggle(key="space_fab_edit_mode")
    assert toggle.disabled and "공식 설비 시나리오에서만" in str(toggle.help)
    floor_use = fab.toggle(key="space_floor_state_edit")
    assert floor_use.disabled and "층 사용은 공식 설비 시나리오에서" in str(floor_use.help)
    assert not fab.button(key="space_switch_to_official").disabled

    detail = _ok(_space(tmp_path, setup).run())
    drawing = next(button for button in detail.button if "_open_" in str(button.key))
    assert drawing.disabled and "층 캔버스·배경 도면은 공식 설비 시나리오에서" in str(drawing.help)

    official = _ok(_space(tmp_path, OPERATIONS, floor=False).run())
    assert not official.toggle(key="space_fab_edit_mode").disabled
    assert not official.toggle(key="space_floor_state_edit").disabled


def test_the_floor_use_confirm_counts_units_an_assumption_put_on_the_floor(
    tmp_path: Path,
) -> None:
    repository, setup = _overlay(tmp_path)
    assert repository.layout_overlay_floor_counts("C1", "1F") == (("셋업 실무", 1),)
    assert repository.layout_overlay_floor_counts("C1", "2F") == ()


def test_the_assumption_space_save_fields_read_back_with_propagation_off() -> None:
    script = AppTest.from_string(
        """
import streamlit as st
from capa_simulation.components.equipment_save_fields import (
    render_equipment_save_fields, save_fields_from_state,
)
st.session_state["seen"] = render_equipment_save_fields("p", assumption=True)
st.session_state["read"] = save_fields_from_state("p", assumption=True)
""",
        default_timeout=30,
    ).run()
    assert not script.exception
    seen = script.session_state["seen"]
    assert isinstance(seen, EquipmentSaveFields)
    assert (seen.propagate_new_units, seen.publish_official) == (False, False)
    script.checkbox(key="p_propagate_units_assumption").check().run()
    assert any("공식 가용대수에 셉니다" in str(item.value) for item in script.caption)
    publish = script.checkbox(key="p_publish_assumption")
    assert publish.label == "함께 넣은 공식 리비전 발행" and publish.value is True
    read = script.session_state["read"]
    assert (read.propagate_new_units, read.publish_official) == (True, True)


def test_the_assumption_fields_default_when_nothing_was_drawn() -> None:
    script = AppTest.from_string(
        """
import streamlit as st
from capa_simulation.components.equipment_save_fields import save_fields_from_state
st.session_state["read"] = save_fields_from_state("p", assumption=True)
""",
        default_timeout=30,
    ).run()
    read = script.session_state["read"]
    assert (read.propagate_new_units, read.publish_official) == (False, False)


def test_a_common_save_by_someone_else_names_the_dropped_assumption_layout_edits(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """남이 공통을 저장하면 편집본을 다시 세운다 — 버림 알림이 가정 배치 편집 수를 따로 적는다(S3 —
    다시 얹기는 S4, 설계 9장)."""
    repository, setup = _overlay(tmp_path)
    app = _ok(_space(tmp_path, setup).run())
    app.toggle(key="space_layout_edit_mode").set_value(True).run()
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": editor_calls[-1]["epoch"],
        "changes": [{"id": "EQ-02", "placed": True, "x": 60, "y": 20, "w": 12, "h": 7}],
        "canvas": None,
        "marks": None,
    }
    _ok(app.run())
    theirs = _session(repository)
    repository.save_equipment(
        _request(theirs, equipment=_set(theirs.equipment, "EQ-02", "설비이력", "남의 공통 편집"))
    )
    clear_equipment_repository()
    _ok(app.run())
    assert any("가정 배치 편집 1대도 버렸습니다" in str(item.value) for item in app.warning)


def test_a_current_data_csv_from_another_scenario_is_named() -> None:
    assert _csv_scenario_mismatch(None, "셋업 실무") is None
    assert (
        _csv_scenario_mismatch("equipment_master_셋업_실무_r3_c5_20261024.csv", "셋업 실무") is None
    )
    other = _csv_scenario_mismatch(
        "equipment_master_운영_일정_r3_c5_edited_20261024.csv", "셋업 실무"
    )
    assert other is not None and "「운영 일정」" in other and "「셋업 실무」" in other
    assert _csv_scenario_mismatch("my_upload.csv", "셋업 실무") is None


def test_the_subject_particle_reads_the_final_sound() -> None:
    assert subject_particle("「셋업 실무」") == "가"
    assert subject_particle("운영 일정") == "이"
    assert subject_particle("r3") == "이"
    assert subject_particle("r2") == "가"
    assert subject_particle("ABC") == "이(가)"


def test_the_session_snapshot_frames_match_the_drawn_layout(tmp_path: Path) -> None:
    """계산 프레임은 배치 차이를 얹은 그대로다(설계 7-3 — 단축 레이어·필요 단축 일정 「도면에서
    보기」 가 Space 가 그리는 층과 같아야 한다)."""
    repository, setup = _overlay(tmp_path)
    snapshot = _session(repository, setup)
    _, frame, _ = snapshot.calculation_frames()
    assert frame.set_index("설비명").loc["EQ-01", "X좌표"] == 50.0
    assert isinstance(frame, pd.DataFrame)
