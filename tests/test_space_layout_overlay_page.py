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
from test_equipment_migration_0027_scenarios import build_legacy_database
from test_equipment_pages import PROJECT_ROOT, _page_script
from test_equipment_scenario_repository import (
    OPERATIONS,
    _add_unmergeable_trace,
    _clone,
    _request,
    _seeded,
    _session,
    _set,
)
from test_space_floor_state_page import _editor_key as _floor_editor_key
from test_space_layout_edit import _master as _layout_master
from test_space_module_group import _js_decl, _node
from widget_browser import BrowserTables

from capa_simulation import equipment_scenario_activation
from capa_simulation.components import space_layout_editor
from capa_simulation.components.app_header import EQUIPMENT_HEADER_LABEL_KEY
from capa_simulation.components.equipment_data_workspace import (
    EDITOR_MODULE_LAYOUTS_KEY,
    LAYOUT_ROLE_KEY,
    _csv_scenario_mismatch,
    official_confirmation_master,
    save_result_message,
)
from capa_simulation.components.equipment_save_fields import (
    EquipmentSaveFields,
)
from capa_simulation.components.space_floor_list import (
    CONFIRM_BUTTON_KEY,
    CONFIRM_KEY,
    EDIT_TOGGLE_KEY,
)
from capa_simulation.components.space_floor_list import (
    SAVE_BUTTON_KEY as FLOOR_SAVE_BUTTON_KEY,
)
from capa_simulation.equipment_scenario_activation import SELECTION_KEY
from capa_simulation.navigation import SPACE_STATUS
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import (
    DuckDBEquipmentRepository,
    EquipmentSaveResult,
    EquipmentScheduleRevisionSummary,
)
from capa_simulation.services.fab_layout import FLOOR_KEYS
from capa_simulation.services.korean_particle import subject_particle
from capa_simulation.services.schedule_confirmation import (
    UNCONFIRMED,
    confirmation_counts,
    schedule_confirmation_issues,
)

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


def _overlay(tmp_path: Path, name: str = "셋업 실무") -> tuple[DuckDBEquipmentRepository, str]:
    """「운영 일정」 r1(공식 v1) + 복제한 「셋업 실무」(`name`) — r2 에서 EQ-01 을 X=50 으로 옮긴
    가정 배치."""
    repository = _seeded(tmp_path)
    clone = _clone(repository, name)
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


def test_the_fast_forward_line_is_written_once_beside_an_unsaved_layout(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """적용해 둔 배치 변경이 있는 채 그 시나리오에 남의 일정 저장이 들어왔다(빨리 감기) — 저장 안
    한 배치 상자 캡션과 바로 아래 ▸▸ 줄이 같은 빨리 감기 글을 두 번 적지 않는다(한 화면에 한 번 —
    E2E r3, 잠금 까닭과 같은 꼴)."""
    repository, setup = _overlay(tmp_path)
    app = _ok(_space(tmp_path, setup).run())
    _apply_eq02(app, editor_calls)
    theirs = _session(repository, setup)
    repository.save_equipment(
        _request(theirs, setup, equipment=_set(theirs.equipment, "EQ-02", "Qual일정", "2026-09-01"))
    )
    clear_equipment_repository()
    _ok(app.run())

    texts = _texts(app)
    assert any("의 새 리비전(가정 배치)으로 저장합니다" in text for text in texts)
    assert sum(text.count("더 새롭지만 배치는 같습니다") for text in texts) == 1, texts


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


def _settled_old_official(tmp_path: Path) -> tuple[DuckDBEquipmentRepository, str, str]:
    """「셋업 실무」 r2 의 차이(EQ-01 X=50)를 공식에서도 같은 자리로 옮긴 뒤 r2 를 발행한 저장소 —
    발행이 차이를 비운 정리 리비전 r3 을 공식으로 냈다. (저장소, 셋업 id, 옛 r2 id)."""
    repository, setup = _overlay(tmp_path)
    overlaid = _scenario(repository, setup).latest_schedule_revision_id
    assert overlaid is not None
    official = _session(repository)
    repository.save_equipment(
        _request(official, equipment=_set(official.equipment, "EQ-01", "X좌표", 50.0))
    )
    release = repository.latest_equipment_release()
    assert release is not None
    repository.publish_equipment_release(
        overlaid, released_by=None, note=None, expected_latest_release_no=release.release_no
    )
    newest = _scenario(repository, setup)
    assert newest.latest_revision_no == 3 and newest.latest_layout_unit_count == 0
    return repository, setup, overlaid


def test_an_old_official_revision_whose_difference_now_matches_says_it_once(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """E2E r5 — 가정이던 때의 차이가 지금 공식과 같아졌고 정리는 최신 r3 에서 끝났다. 옛 r2 를 연
    머리 알림은 「공식과 다른 배치(저장된 차이)를 담고 있습니다」 와 「공식과 같아진 것은 다음
    저장·발행 때 정리됩니다」 를 한 줄에 붙여 서로 어긋나게 말하지 않고, 저장된 차이가 지금 공식과
    같다는 것 하나만 말한다(그리는 배치도 공식과 같다)."""
    _, setup, overlaid = _settled_old_official(tmp_path)
    app = _ok(_space(tmp_path, setup, overlaid).run())

    texts = _texts(app)
    head = [text for text in texts if "가정이던 때의 배치안" in text]
    assert len(head) == 1, texts
    assert "이 리비전에 저장된 배치 차이(호기 1대)는 지금 공식과 같습니다" in head[0], head
    assert not any("공식과 다른 배치" in text for text in texts), texts
    assert not any("정리됩니다" in text for text in texts), texts
    assert not any("가정이던 때의 배치안" in str(item.value) for item in app.info)
    assert _x_of(_viewer(editor_calls), "EQ-01") == 50.0


def test_an_old_official_revision_tail_does_not_promise_a_cleanup(tmp_path: Path) -> None:
    """공식 시나리오의 옛 리비전(가정이던 때)은 불변이라 「다음 저장·발행 때 정리됩니다」 가 맞지
    않는다 — 실효 차이가 남고 저장된 행 일부만 공식과 같아졌으면 꼬리는 그 나머지가 지금 공식과
    같다고만 적는다(E2E r5)."""
    from dataclasses import replace

    from capa_simulation.components.space_floor_layout import space_layout_notices
    from capa_simulation.equipment_scenario_activation import EquipmentSession

    repository, setup, overlaid = _settled_old_official(tmp_path)
    snapshot = _session(repository, setup, overlaid)
    assert snapshot.schedule is not None
    # 저장된 도면 요소 2개 가운데 1개만 지금도 공식과 다르다(실효 1).
    snapshot = replace(snapshot, schedule=replace(snapshot.schedule, layout_mark_count=2))
    catalog = repository.load_scenario_catalog()
    session = EquipmentSession(catalog, catalog.scenario(setup), overlaid, snapshot=snapshot)
    assert not session.is_assumption

    ((line, kind), *_) = space_layout_notices(session, (1, 0))

    assert kind == "info"
    assert line.startswith("이 리비전은 공식과 다른 배치(도면 요소 1개)를 담고 있습니다"), line
    assert line.endswith("(저장된 차이 호기 1대·요소 2개 가운데 나머지는 지금 공식과 같습니다)"), (
        line
    )
    assert "정리됩니다" not in line


# 물결표가 둘인 설비 시나리오 이름 — 막지 않으면 「가정<del>R3</del>X」 로 그려진다. 막힌 꼴은
# `\~`(마크다운이 물결표 글자 그대로 그린다)다.
TILDE_NAME = "가정~R3~X"
TILDE_ESCAPED = "가정\\~R3\\~X"


def _assert_tildes_escaped(app: AppTest) -> None:
    """이름이 실린 마크다운 글(본문·사이드바 글·풍선) 모두가 물결표를 막았다."""
    texts = [
        *_texts(app),
        *(str(item.help) for item in app.toggle if item.help),
        *(str(item.help) for item in app.button if item.help),
    ]
    named = [text for text in texts if "R3" in text]
    assert named
    bare = [text for text in named if re.search(r"(?<!\\)~", text)]
    assert not bare, bare


def test_a_deleted_units_difference_is_named_once_in_the_space_head(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """E2E r3 — 가정 배치 차이가 공통 대장에서 지운 호기의 것뿐이면 머리 첫 줄은 「배치는 공식과
    같습니다」 뿐이고(「공식과 같아진 것은 … 정리됩니다」 꼬리 없음), 그 행은 둘째 줄 「지운 호기의
    배치 차이 1행은 버렸습니다」 가 한 번 말한다."""
    repository, setup = _overlay(tmp_path)
    theirs = _session(repository)
    kept = theirs.equipment.loc[~theirs.equipment["설비명"].eq("EQ-01")].reset_index(drop=True)
    downtime = theirs.downtime.loc[~theirs.downtime["설비명"].eq("EQ-01")].reset_index(drop=True)
    repository.save_equipment(_request(theirs, equipment=kept, downtime=downtime))
    app = _ok(_space(tmp_path, setup).run())

    texts = _texts(app)
    assert any("가정 설비 시나리오 · 배치는 공식과 같습니다" in text for text in texts), texts
    assert any("지운 호기의 배치 차이 1행은 버렸습니다" in text for text in texts), texts
    assert not any("공식과 같아진 것은" in text for text in texts), texts


def test_a_tilde_scenario_name_keeps_its_tildes_in_the_apply_box_and_save_notices(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """설비 시나리오 이름 「가정~R3~X」 — 적용 알림·저장 안 한 배치 상자 캡션·저장 알림(이름이 두 번
    나와 물결표 하나짜리 이름도 짝이 맞는다)이 물결표를 막아 지움선이 되지 않는다(E2E r3)."""
    _, setup = _overlay(tmp_path, TILDE_NAME)
    app = _ok(_space(tmp_path, setup).run())
    _apply_eq02(app, editor_calls)

    assert any(
        f"저장하면 「{TILDE_ESCAPED}」의 가정 배치로" in str(item.value) for item in app.success
    )
    assert any(
        f"「{TILDE_ESCAPED}」의 새 리비전(가정 배치)으로 저장합니다" in str(item.value)
        for item in app.caption
    )
    _assert_tildes_escaped(app)

    app.button(key="space_layout_save").click().run()
    _ok(app)
    saved = next(str(item.value) for item in app.success if "저장했습니다" in str(item.value))
    assert saved.count(f"「{TILDE_ESCAPED}」") >= 2, saved
    _assert_tildes_escaped(app)


def test_a_tilde_scenario_name_keeps_its_tildes_in_the_fast_forward_and_editor_lines(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """낡은 가정 세션(배치 같음 — 빨리 감기)의 ▸▸ 줄과 편집기 위 「새 호기를 넣지 않습니다」 줄이
    이름의 물결표를 막는다."""
    repository, setup = _overlay(tmp_path, TILDE_NAME)
    pinned = _scenario(repository, setup).latest_schedule_revision_id
    theirs = _session(repository, setup)
    repository.save_equipment(
        _request(theirs, setup, equipment=_set(theirs.equipment, "EQ-02", "Qual일정", "2026-09-01"))
    )
    app = _ok(_space(tmp_path, setup, pinned).run())
    assert any(
        f"「{TILDE_ESCAPED}」 r3" in str(item.value)
        and "더 새롭지만 배치는 같습니다" in str(item.value)
        for item in app.caption
    )
    _assert_tildes_escaped(app)

    app.toggle(key="space_layout_edit_mode").set_value(True).run()
    _ok(app)
    assert any(
        f"「{TILDE_ESCAPED}」" in str(item.value) and "새 호기를 넣지 않습니다" in str(item.value)
        for item in app.caption
    )
    _assert_tildes_escaped(app)


def test_a_tilde_scenario_name_keeps_its_tildes_in_the_lock_line_and_its_popover(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """낡은 가정 세션(남이 다른 배치를 저장 — 잠금)의 잠금 줄·꺼진 「배치 편집」 풍선·「최신 r3
    불러오기」 팝오버 글이 이름의 물결표를 막는다."""
    repository, setup = _overlay(tmp_path, TILDE_NAME)
    pinned = _scenario(repository, setup).latest_schedule_revision_id
    theirs = _session(repository, setup)
    repository.save_equipment(
        _request(theirs, setup, equipment=_set(theirs.equipment, "EQ-02", "X좌표", 70.0))
    )
    app = _ok(_space(tmp_path, setup, pinned).run())

    assert any(
        f"「{TILDE_ESCAPED}」 r3 에 다른 배치가 저장됐습니다" in str(item.value)
        for item in app.caption
    )
    locked = app.toggle(key="space_layout_edit_mode_locked")
    assert TILDE_ESCAPED in str(locked.help)
    assert any(f"세션을 「{TILDE_ESCAPED} · r2」 에서" in str(item.value) for item in app.caption)
    _assert_tildes_escaped(app)


def test_a_tilde_scenario_name_keeps_its_tildes_in_an_old_official_revision_head(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """가정이던 때의 리비전을 연 공식 시나리오 세션 — 머리 알림(「…이(가) 가정이던 때의
    배치안입니다」)과 잠금 줄이 이름의 물결표를 막는다."""
    repository, setup = _overlay(tmp_path, TILDE_NAME)
    overlaid = _scenario(repository, setup).latest_schedule_revision_id
    cleared = repository.clear_layout_overlay(setup, expected_latest_schedule_revision_id=overlaid)
    assert cleared is not None
    repository.publish_equipment_release(
        cleared.schedule_revision_id, released_by=None, note=None, expected_latest_release_no=1
    )
    app = _ok(_space(tmp_path, setup, overlaid).run())

    assert any(
        f"「{TILDE_ESCAPED}」" in str(item.value) and "가정이던 때의 배치안" in str(item.value)
        for item in app.info
    )
    _assert_tildes_escaped(app)


# 별표가 둘인 설비 시나리오 이름 — 물결표만 막으면 「가정<em>R6</em>B」 로 기울어 별표가 사라진다
# (2026-10-26 E2E r5). 막힌 꼴은 `\*` 다.
STAR_NAME = "가정*R6*B"
STAR_ESCAPED = "가정\\*R6\\*B"


def _assert_stars_escaped(app: AppTest) -> None:
    """이름이 실린 마크다운 글(본문·풍선) 모두가 별표를 막았다."""
    texts = [
        *_texts(app),
        *(str(item.help) for item in app.toggle if item.help),
        *(str(item.help) for item in app.button if item.help),
    ]
    named = [text for text in texts if "R6" in text]
    assert named
    bare = [text for text in named if re.search(r"(?<!\\)\*", text)]
    assert not bare, bare


def test_an_asterisk_scenario_name_stays_literal_in_the_apply_box_and_notice(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """설비 시나리오 이름 「가정*R6*B」 — 적용 알림(「저장하면 「…」의 가정 배치로」)과 저장 안 한
    배치 상자 캡션이 별표를 막는다(물결표만 막아 기울임이 됐다 — E2E r5)."""
    _, setup = _overlay(tmp_path, STAR_NAME)
    app = _ok(_space(tmp_path, setup).run())
    _apply_eq02(app, editor_calls)

    assert any(
        f"저장하면 「{STAR_ESCAPED}」의 가정 배치로" in str(item.value) for item in app.success
    )
    assert any(
        f"「{STAR_ESCAPED}」의 새 리비전(가정 배치)으로 저장합니다" in str(item.value)
        for item in app.caption
    )
    _assert_stars_escaped(app)


def test_an_asterisk_scenario_name_stays_literal_in_the_fast_forward_and_editor_lines(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """낡은 가정 세션(배치 같음 — 빨리 감기)의 ▸▸ 줄과 편집기 위 「새 호기를 넣지 않습니다」 줄이
    이름의 별표를 막는다(E2E r5)."""
    repository, setup = _overlay(tmp_path, STAR_NAME)
    pinned = _scenario(repository, setup).latest_schedule_revision_id
    theirs = _session(repository, setup)
    repository.save_equipment(
        _request(theirs, setup, equipment=_set(theirs.equipment, "EQ-02", "Qual일정", "2026-09-01"))
    )
    app = _ok(_space(tmp_path, setup, pinned).run())
    assert any(
        f"「{STAR_ESCAPED}」 r3" in str(item.value)
        and "더 새롭지만 배치는 같습니다" in str(item.value)
        for item in app.caption
    )
    _assert_stars_escaped(app)

    app.toggle(key="space_layout_edit_mode").set_value(True).run()
    _ok(app)
    assert any(
        f"「{STAR_ESCAPED}」" in str(item.value) and "새 호기를 넣지 않습니다" in str(item.value)
        for item in app.caption
    )
    _assert_stars_escaped(app)


def test_an_asterisk_scenario_name_stays_literal_in_the_lock_line_and_its_popover(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """낡은 가정 세션(남이 다른 배치를 저장 — 잠금)의 잠금 줄·꺼진 「배치 편집」 풍선·「최신 r3
    불러오기」 팝오버 글이 이름의 별표를 막는다(E2E r5)."""
    repository, setup = _overlay(tmp_path, STAR_NAME)
    pinned = _scenario(repository, setup).latest_schedule_revision_id
    theirs = _session(repository, setup)
    repository.save_equipment(
        _request(theirs, setup, equipment=_set(theirs.equipment, "EQ-02", "X좌표", 70.0))
    )
    app = _ok(_space(tmp_path, setup, pinned).run())

    assert any(
        f"「{STAR_ESCAPED}」 r3 에 다른 배치가 저장됐습니다" in str(item.value)
        for item in app.caption
    )
    locked = app.toggle(key="space_layout_edit_mode_locked")
    assert STAR_ESCAPED in str(locked.help)
    assert any(f"세션을 「{STAR_ESCAPED} · r2」 에서" in str(item.value) for item in app.caption)
    _assert_stars_escaped(app)


def test_an_asterisk_scenario_name_stays_literal_in_an_old_official_revision_lock(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """가정이던 때의 리비전을 연 공식 시나리오 세션 — 머리 알림과 잠금 줄(「이 리비전에는
    「…」이(가) 가정이던 때의 …」)이 이름의 별표를 막는다(E2E r5)."""
    repository, setup = _overlay(tmp_path, STAR_NAME)
    overlaid = _scenario(repository, setup).latest_schedule_revision_id
    cleared = repository.clear_layout_overlay(setup, expected_latest_schedule_revision_id=overlaid)
    assert cleared is not None
    repository.publish_equipment_release(
        cleared.schedule_revision_id, released_by=None, note=None, expected_latest_release_no=1
    )
    app = _ok(_space(tmp_path, setup, overlaid).run())

    assert any(
        f"이 리비전에는 「{STAR_ESCAPED}」" in str(item.value) and "잠갔습니다" in str(item.value)
        for item in app.caption
    )
    _assert_stars_escaped(app)


def test_the_canvas_dialog_words_keep_tildes_in_scenario_and_unit_names() -> None:
    """층 캔버스 팝업의 경고 재료 — 가정 설비 시나리오 이름과 이탈 호기 설비명의 물결표를 막는다."""
    from capa_simulation.components.floor_layout_upload import (
        _unit_names,
        overlay_mark_words,
        overlay_unit_words,
    )

    assert overlay_unit_words((("10~12월 증설", 2),)) == "가정 배치 「10\\~12월 증설」 호기 2대"
    assert "가정 배치 「10\\~12월 증설」 의 요소도 밖입니다" in overlay_mark_words(
        ("10~12월 증설",)
    )
    assert _unit_names(["NEW~01~", "EQ-02"]) == "NEW\\~01\\~, EQ-02(2대)"


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


def _apply_eq02(app: AppTest, editor_calls: list[dict[str, Any]], x: float = 60) -> None:
    """가정 세션 층 상세 편집기에서 EQ-02 를 (x, 20) 으로 옮겨 적용한다."""
    app.toggle(key="space_layout_edit_mode").set_value(True).run()
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": editor_calls[-1]["epoch"],
        "changes": [{"id": "EQ-02", "placed": True, "x": x, "y": 20, "w": 12, "h": 7}],
        "canvas": None,
        "marks": None,
    }
    _ok(app.run())


def _buffer_x(app: AppTest, name: str) -> float:
    from capa_simulation.components.equipment_data_workspace import BUFFER_KEY

    frame = app.session_state[BUFFER_KEY][1]
    return float(frame.loc[frame["설비명"].eq(name), "X좌표"].iloc[0])


def test_a_common_save_by_someone_else_reapplies_the_assumption_layout_edits(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """남이 공통을 저장하면 편집본을 다시 세우되, 가정 역할로 찍힌 배치 일곱 칸 편집은 새 저장본
    위에 다시 얹고 찍힌 역할을 남긴다(S4 — 설계 9장·검토 M4). 남의 공통 편집(설비이력)은 새
    저장본에서 온다. 알림이 다시 얹은 수를 적는다."""
    repository, setup = _overlay(tmp_path)
    app = _ok(_space(tmp_path, setup).run())
    _apply_eq02(app, editor_calls)
    assert app.session_state[LAYOUT_ROLE_KEY] == "overlay"
    theirs = _session(repository)
    repository.save_equipment(
        _request(theirs, equipment=_set(theirs.equipment, "EQ-02", "설비이력", "남의 공통 편집"))
    )
    clear_equipment_repository()
    _ok(app.run())

    assert any(
        "가정 배치 편집 1대(호기 위치)는 그 위에 다시 얹었습니다" in str(item.value)
        for item in app.warning
    )
    assert _buffer_x(app, "EQ-02") == 60.0
    assert app.session_state[LAYOUT_ROLE_KEY] == "overlay"
    from capa_simulation.components.equipment_data_workspace import BUFFER_KEY

    frame = app.session_state[BUFFER_KEY][1]
    assert frame.loc[frame["설비명"].eq("EQ-02"), "설비이력"].iloc[0] == "남의 공통 편집"
    # 다시 얹은 편집도 저장된다 — 그 시나리오의 새 리비전(가정 배치), 공통 리비전은 남의 것 그대로.
    common_before = repository.latest_revision_id()
    app.button(key="space_layout_save").click().run()
    _ok(app)
    assert repository.latest_revision_id() == common_before
    newest = _scenario(repository, setup)
    assert newest.latest_layout_unit_count == 2


def test_a_unit_someone_else_deleted_is_left_out_of_the_reapplied_edits(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """남이 그 사이 공통 대장에서 지운 호기의 편집은 다시 얹지 않고 알림에 이름을 적는다. 다른
    호기의 편집은 얹는다."""
    repository, setup = _overlay(tmp_path)
    app = _ok(_space(tmp_path, setup).run())
    app.toggle(key="space_layout_edit_mode").set_value(True).run()
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": editor_calls[-1]["epoch"],
        "changes": [
            {"id": "EQ-01", "placed": True, "x": 70, "y": 40, "w": 12, "h": 7},
            {"id": "EQ-02", "placed": True, "x": 60, "y": 20, "w": 12, "h": 7},
        ],
        "canvas": None,
        "marks": None,
    }
    _ok(app.run())
    theirs = _session(repository)
    kept = theirs.equipment.loc[~theirs.equipment["설비명"].eq("EQ-01")].reset_index(drop=True)
    downtime = theirs.downtime.loc[~theirs.downtime["설비명"].eq("EQ-01")].reset_index(drop=True)
    repository.save_equipment(_request(theirs, equipment=kept, downtime=downtime))
    clear_equipment_repository()
    _ok(app.run())

    notice = next(str(item.value) for item in app.warning if "다시 얹었습니다" in str(item.value))
    assert "가정 배치 편집 1대(호기 위치)" in notice
    assert "빠진 호기 1대(EQ-01)의 편집은 뺐습니다" in notice
    assert _buffer_x(app, "EQ-02") == 60.0


def test_a_reapplied_editor_group_keeps_its_approval_and_saves(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """숨은 모듈(레이아웃표시 N)이 든 묶음을 가정 세션 편집기로 다른 층에 보낸 뒤 남이 공통을
    저장하면, 다시 얹은 묶음의 편집기 모양 승인도 남아 그대로 저장된다(S4 리뷰 — 승인을 버리면
    「설비 마스터 표·붙여넣기로 바꾼 값」 으로 막혔다). 알림의 수는 설비 단위(묶음 1대)다."""
    module = {"Main 설비": "GRP-1", "Xsize": 10, "Ysize": 7}
    master = _layout_master(
        {**module, "설비명": "G1-A", "X좌표": 50.0, "Y좌표": 37.0},
        {**module, "설비명": "G1-B", "X좌표": 60.0, "Y좌표": 37.0, "레이아웃표시": "N"},
        {**module, "설비명": "G1-C", "X좌표": 50.0, "Y좌표": 30.0},
        {**module, "설비명": "G1-D", "X좌표": 60.0, "Y좌표": 30.0},
    )
    repository = _seeded(tmp_path, master)
    setup = _clone(repository).equipment_scenario_id
    app = _ok(_space(tmp_path, setup).run())
    app.toggle(key="space_layout_edit_mode").set_value(True).run()
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": editor_calls[-1]["epoch"],
        "changes": [
            {"id": "G1-A", "placed": True, "x": 50, "y": 37, "w": 10, "h": 7, "moveTo": "C2 2F"},
            {"id": "G1-C", "placed": True, "x": 50, "y": 30, "w": 10, "h": 7, "moveTo": "C2 2F"},
            {"id": "G1-D", "placed": True, "x": 60, "y": 30, "w": 10, "h": 7, "moveTo": "C2 2F"},
        ],
        "ghosts": [],
        "canvas": None,
        "marks": None,
    }
    _ok(app.run())
    assert "GRP-1" in app.session_state[EDITOR_MODULE_LAYOUTS_KEY]
    theirs = _session(repository)
    repository.save_equipment(
        _request(theirs, equipment=_set(theirs.equipment, "EQ-02", "설비이력", "남의 공통 편집"))
    )
    clear_equipment_repository()
    _ok(app.run())

    notice = next(str(item.value) for item in app.warning if "다시 얹었습니다" in str(item.value))
    assert "가정 배치 편집 1대(호기 위치)" in notice
    assert "GRP-1" in app.session_state[EDITOR_MODULE_LAYOUTS_KEY]
    common_before = repository.latest_revision_id()
    app.button(key="space_layout_save").click().run()

    _ok(app)
    assert not app.error, [item.value for item in app.error]
    assert repository.latest_revision_id() == common_before
    newest = _scenario(repository, setup)
    assert newest.latest_layout_unit_count == 4
    floors = _session(repository, setup).equipment.set_index("설비명").loc[["G1-A", "G1-C"], "층"]
    assert set(floors) == {"2F"}


def test_an_official_layout_edit_is_still_dropped_on_someone_elses_common_save(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """공식 역할의 배치 편집은 공통 대장에 들어갈 편집이라 다시 얹지 않고 지금처럼 버린다."""
    repository, _ = _overlay(tmp_path)
    app = _ok(_space(tmp_path, OPERATIONS).run())
    _apply_eq02(app, editor_calls)
    assert app.session_state[LAYOUT_ROLE_KEY] == "official"
    theirs = _session(repository)
    repository.save_equipment(
        _request(theirs, equipment=_set(theirs.equipment, "EQ-02", "설비이력", "남의 공통 편집"))
    )
    clear_equipment_repository()
    _ok(app.run())

    assert any(
        "저장하지 않은 설비 편집(설비 마스터·Space 배치)을 버리고" in str(item.value)
        for item in app.warning
    )
    assert _buffer_x(app, "EQ-02") != 60.0
    assert LAYOUT_ROLE_KEY not in app.session_state


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


def _moved_floor(tmp_path: Path, name: str = "셋업 실무") -> tuple[DuckDBEquipmentRepository, str]:
    """「셋업 실무」(`name`) 의 가정 배치에서 EQ-01 만 C1 2F 로 옮겼다(공식 C1 2F 는 비었다)."""
    repository = _seeded(tmp_path)
    clone = _clone(repository, name)
    mine = _session(repository, clone.equipment_scenario_id)
    repository.save_equipment(
        _request(
            mine,
            clone.equipment_scenario_id,
            equipment=_set(mine.equipment, "EQ-01", "층", "2F"),
        )
    )
    return repository, clone.equipment_scenario_id


def _placed_on(app: AppTest, floor: str) -> float:
    (table,) = [item.value for item in app.dataframe if "미배치대수" in item.value.columns]
    row = table.loc[table["동"].eq("C1") & table["층"].eq(floor)]
    return float(row["배치대수"].iloc[0])


def test_the_floor_list_counts_the_drawn_scenarios_floors(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """FAB 층 목록의 배치대수는 세션 시나리오의 배치로 센다(S3 — 1단계는 늘 공식). 계산 프레임도
    배치 차이를 얹은 그대로다(설계 7-3 — 단축 레이어·필요 단축 일정 「도면에서 보기」 가 Space 가
    그리는 층과 같아야 한다)."""
    repository, setup = _moved_floor(tmp_path)
    mine = _ok(_space(tmp_path, setup, floor=False).run())
    official = _ok(_space(tmp_path, OPERATIONS, floor=False).run())

    assert (_placed_on(mine, "1F"), _placed_on(mine, "2F")) == (1.0, 1.0)
    assert (_placed_on(official, "1F"), _placed_on(official, "2F")) == (2.0, 0.0)
    _, frame, _ = _session(repository, setup).calculation_frames()
    assert frame.set_index("설비명").loc["EQ-01", "층"] == "2F"
    assert isinstance(frame, pd.DataFrame)


def test_turning_off_a_floor_only_an_assumption_uses_asks_with_the_overlay_line(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """공식 배치에는 호기가 없어도 가정 배치가 그 층에 호기를 두었으면 끄기 전에 확인하고 그
    시나리오를 덧줄로 적는다 — 층 사용은 공통이라 그 시나리오 목록·도면에서도 숨는다(설계 13-2·Q3,
    S3 리뷰)."""
    repository, _ = _moved_floor(tmp_path)
    assert repository.layout_overlay_floor_counts("C1", "2F") == (("셋업 실무", 1),)
    app = _space(tmp_path, OPERATIONS, floor=False)
    tables = BrowserTables(app)
    _ok(tables.run())
    app.toggle(key=EDIT_TOGGLE_KEY).set_value(True)
    _ok(tables.run())
    tables.edit(_floor_editor_key(app), FLOOR_KEYS.index(("C1", "2F")), "사용", False)
    _ok(tables.run())
    app.button(key=FLOOR_SAVE_BUTTON_KEY).click()
    _ok(tables.run())

    assert CONFIRM_KEY in app.session_state
    assert repository.load_floor_states().inactive == {}
    assert any("공식 배치에는 이 층에 호기가 없지만" in str(item.value) for item in app.warning)
    assert any(
        "가정 설비 시나리오 「셋업 실무」 의 배치에서 C1 2F 에 놓인 호기 1대도" in str(item.value)
        for item in app.caption
    )
    app.button(key=CONFIRM_BUTTON_KEY).click()
    _ok(tables.run())
    assert repository.load_floor_states().inactive == {("C1", "2F"): "UNUSED"}


def test_the_floor_off_overlay_line_keeps_tildes_in_the_scenario_name(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """E2E r3 같은 꼴 — 층 끄기 확인의 덧줄(「가정 설비 시나리오 「…」 의 배치에서 …」)이 설비
    시나리오 이름의 물결표를 막는다(「가정<del>R3</del>X」 가 되지 않게)."""
    repository, _ = _moved_floor(tmp_path, TILDE_NAME)
    app = _space(tmp_path, OPERATIONS, floor=False)
    tables = BrowserTables(app)
    _ok(tables.run())
    app.toggle(key=EDIT_TOGGLE_KEY).set_value(True)
    _ok(tables.run())
    tables.edit(_floor_editor_key(app), FLOOR_KEYS.index(("C1", "2F")), "사용", False)
    _ok(tables.run())
    app.button(key=FLOOR_SAVE_BUTTON_KEY).click()
    _ok(tables.run())

    assert CONFIRM_KEY in app.session_state
    assert any(
        f"가정 설비 시나리오 「{TILDE_ESCAPED}」 의 배치에서 C1 2F 에 놓인 호기 1대도"
        in str(item.value)
        for item in app.caption
    )
    _assert_tildes_escaped(app)


def test_the_sidebar_row_keeps_tildes_in_its_save_flash_and_session_notice(
    tmp_path: Path, editor_calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """E2E r3 같은 꼴 — Space 사이드바 설비 시나리오 줄의 팝업 저장 알림(가정 배치 저장은 이름이
    두 번 나와 물결표 하나짜리 이름도 짝이 맞는다)과 세션 이동 알림이 이름의 물결표를 막는다."""
    from dataclasses import replace
    from datetime import datetime

    import capa_simulation.equipment_scenario_activation as activation
    from capa_simulation.components.equipment_scenario_status import FLASH_KEY as ROW_FLASH_KEY

    _, setup = _overlay(tmp_path, TILDE_NAME)
    schedule = EquipmentScheduleRevisionSummary("s3", setup, 3, "save", datetime(2026, 10, 26))
    saved = save_result_message(
        EquipmentSaveResult(
            common=None, schedule=schedule, layout_overlay_written=True, layout_overlay_units=1
        ),
        scenario_name=TILDE_NAME,
    )
    # 저장 결과 글은 이름을 quoted 로 막아 짓는다(그리는 자리에서 다시 막아도 같다).
    assert saved.count(f"「{TILDE_ESCAPED}」") >= 2, saved
    notice = (
        f"「{TILDE_NAME}」 r1 을 지금 공통 대장과 합칠 수 없어 「{TILDE_NAME}」 r2 로 열었습니다 — "
        "저장하지 않은 설비 편집은 버렸습니다."
    )
    resolve = activation.resolve_equipment_session
    monkeypatch.setattr(
        activation,
        "resolve_equipment_session",
        lambda path: replace(resolve(path), notice=notice),
    )
    app = _space(tmp_path, setup)
    app.session_state[ROW_FLASH_KEY] = saved
    _ok(app.run())

    flashes = [str(item.value) for item in app.sidebar.success]
    notices = [str(item.value) for item in app.sidebar.warning]
    assert any(text.count(f"「{TILDE_ESCAPED}」") >= 2 for text in flashes), flashes
    assert any(f"「{TILDE_ESCAPED}」 r2 로 열었습니다" in text for text in notices), notices
    bare = [text for text in [*flashes, *notices] if re.search(r"(?<!\\)~", text)]
    assert not bare, bare


def test_the_sidebar_session_notice_keeps_the_asterisks_of_the_scenario_name(
    tmp_path: Path, editor_calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """세션 이동 알림(평문 표 잠금 글에도 가는 글)이 이름의 별표를 막는다 — 물결표만 막아
    「가정<em>R6</em>B」 로 기울었다(E2E r5)."""
    from dataclasses import replace

    import capa_simulation.equipment_scenario_activation as activation

    _, setup = _overlay(tmp_path, STAR_NAME)
    notice = (
        f"「{STAR_NAME}」 r1 을 지금 공통 대장과 합칠 수 없어 「{STAR_NAME}」 r2 로 열었습니다 — "
        "저장하지 않은 설비 편집은 버렸습니다."
    )
    resolve = activation.resolve_equipment_session
    monkeypatch.setattr(
        activation,
        "resolve_equipment_session",
        lambda path: replace(resolve(path), notice=notice),
    )
    app = _ok(_space(tmp_path, setup).run())

    notices = [str(item.value) for item in app.sidebar.warning]
    assert any(f"「{STAR_ESCAPED}」 r2 로 열었습니다" in text for text in notices), notices
    bare = [text for text in notices if re.search(r"(?<!\\)\*", text)]
    assert not bare, bare


def test_an_assumption_save_of_marks_only_names_what_it_saved() -> None:
    """요소·이름표만 옮긴 가정 배치 저장의 결과 문구가 「호기 0대」 로만 읽히지 않는다 — 설계 8-2 의
    셈 꼴(0 인 항목은 뺀다). 차이를 모두 걷은 저장은 공식과 같아졌다고 말한다(S3 리뷰)."""
    from datetime import datetime

    schedule = EquipmentScheduleRevisionSummary("s2", "setup", 2, "save", datetime(2026, 10, 25))
    marks_only = save_result_message(
        EquipmentSaveResult(
            common=None,
            schedule=schedule,
            layout_overlay_written=True,
            layout_overlay_marks=1,
            layout_overlay_labels=2,
        ),
        scenario_name="셋업 실무",
    )
    assert (
        "「셋업 실무」의 가정 배치를 저장했습니다(도면 요소 1개 · Main 설비명 위치 2개)"
        in marks_only
    )
    assert "호기 0대" not in marks_only
    cleared = save_result_message(
        EquipmentSaveResult(common=None, schedule=schedule, layout_overlay_written=True),
        scenario_name="셋업 실무",
    )
    assert "「셋업 실무」의 가정 배치를 저장했습니다 — 이제 공식 배치와 같습니다." in cleared


def test_an_assumption_canvas_value_from_an_old_browser_is_refused(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """칸을 껐어도 옛 브라우저가 캔버스 값을 보내면 서버가 거부한다(두 겹 — 설계 8-4). 다른 변경도
    적용하지 않는다."""
    _, setup = _overlay(tmp_path)
    app = _ok(_space(tmp_path, setup).run())
    app.toggle(key="space_layout_edit_mode").set_value(True).run()
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": editor_calls[-1]["epoch"],
        "changes": [{"id": "EQ-02", "placed": True, "x": 60, "y": 20, "w": 12, "h": 7}],
        "canvas": {"width": 130, "height": 60},
        "marks": None,
    }
    _ok(app.run())

    assert any(
        "적용하지 못했습니다" in str(item.value) and "층 캔버스·배경 도면은" in str(item.value)
        for item in app.error
    )
    assert LAYOUT_ROLE_KEY not in app.session_state
    assert not any("저장 안 한 배치 변경" in str(item.value) for item in app.markdown)


def _unconfirmed_of(master: pd.DataFrame) -> int:
    from datetime import date

    issues = schedule_confirmation_issues(master, today=date.today())
    return int(confirmation_counts(issues)[UNCONFIRMED])


def test_an_assumption_space_counts_unconfirmed_by_the_official_schedule(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """가정 세션 FAB 「미확인 N대」 는 공식 시나리오 일정 기준이다(설계 8-1 — 가용설비 Main 과 같은
    규칙). 가정 일정으로 세면 다른 수가 나오는 DB 로 본다."""
    repository = _seeded(tmp_path)
    clone = _clone(repository)
    mine = _session(repository, clone.equipment_scenario_id)
    repository.save_equipment(
        _request(
            mine,
            clone.equipment_scenario_id,
            equipment=_set(mine.equipment, "EQ-01", "Qual일정", "2027-01-01"),
        )
    )
    session = _session(repository, clone.equipment_scenario_id)
    official = repository.load_official_snapshot()
    assert official is not None
    expected = _unconfirmed_of(official_confirmation_master(session.equipment, official))
    assert expected != _unconfirmed_of(session.equipment)

    _ok(_space(tmp_path, clone.equipment_scenario_id, floor=False).run())
    fab = next(
        call
        for call in reversed(editor_calls)
        if call.get("mode") == "view" and call.get("scope") == "fab"
    )
    assert fab["unconfirmed"] == expected


def test_another_save_does_not_leave_the_badge_one_run_behind(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """남의 공통 저장으로 편집본을 버린 회차에 사이드바 배지·머리 띠 꼬리가 「미저장 변경」 을
    말하지 않는다 — 줄은 편집본을 세운 뒤 그린다(가용설비 현황과 같은 차례, S3 리뷰). S4 부터 가정
    배치 편집은 다시 얹으므로, 남이 옮긴 호기 자체를 지워 다시 얹을 것이 없게 한다."""
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
    assert str(app.session_state[EQUIPMENT_HEADER_LABEL_KEY]["suffix"]).endswith("미저장 변경")
    theirs = _session(repository)
    kept = theirs.equipment.loc[~theirs.equipment["설비명"].eq("EQ-02")].reset_index(drop=True)
    downtime = theirs.downtime.loc[~theirs.downtime["설비명"].eq("EQ-02")].reset_index(drop=True)
    repository.save_equipment(_request(theirs, equipment=kept, downtime=downtime))
    clear_equipment_repository()
    _ok(app.run())

    assert any("버렸습니다" in str(item.value) for item in app.warning)
    assert str(app.session_state[EQUIPMENT_HEADER_LABEL_KEY]["suffix"]).endswith("가정 배치")
    assert not any("미저장 변경" in str(item.value) for item in app.sidebar.caption)
    assert not any("미저장 변경" in str(item.value) for item in app.sidebar.markdown)


def _unmerged_assumption(tmp_path: Path) -> tuple[Path, str]:
    """옛 배포 흔적이 공식과도 합쳐지지 않는 DB 위의 가정 「셋업 실무」(일정 없이 연다)."""
    path = tmp_path / "equipment.duckdb"
    build_legacy_database(path)
    repository = DuckDBEquipmentRepository(path)
    repository.initialize()
    clone = _clone(repository)
    _add_unmergeable_trace(repository)
    clear_equipment_repository()
    return path, clone.equipment_scenario_id


def test_an_unmerged_assumption_has_no_switch_to_official(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """일정 없이 연 가정 세션에는 「공식으로 바꾸기」 가 서지 않는다 — 공식으로 옮겨도 같은 까닭으로
    합쳐지지 않는다(1단계 규칙, S3 리뷰). FAB 편집은 그대로 잠긴다."""
    _, setup = _unmerged_assumption(tmp_path)
    app = _ok(_space(tmp_path, setup, floor=False).run())

    assert any("일정 없이 연 상태" in text for text in _texts(app))
    assert not [button for button in app.button if button.key == "space_switch_to_official"]
    assert app.toggle(key="space_fab_edit_mode").disabled


def test_a_failed_scenario_switch_is_not_called_a_failed_save(
    tmp_path: Path, editor_calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """시나리오 바꾸기 실패 글은 저장 오류와 따로 잠금 줄 자리에 선다 — 저장 안 한 상자가 있는
    회차에도 「배치를 저장하지 못했습니다」 로 읽히지 않는다(S3 리뷰). 실패는 콜백이 담고 그 칸이
    한 번 그린다(`flash`) — 다음 회차에는 없다."""
    _, setup = _overlay(tmp_path)
    app = _ok(_space(tmp_path, setup).run())
    app.toggle(key="space_layout_edit_mode").set_value(True).run()
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": editor_calls[-1]["epoch"],
        "changes": [{"id": "EQ-02", "placed": True, "x": 60, "y": 20, "w": 12, "h": 7}],
        "canvas": None,
        "marks": None,
    }
    _ok(app.run())
    # 페이지는 회차마다 이 이름을 모듈에서 다시 읽는다 — 콜백은 그 회차의 이름을 부른다.
    monkeypatch.setattr(
        equipment_scenario_activation,
        "select_equipment_scenario",
        lambda *_args, **_kwargs: "시험 실패",
    )
    # 「공식으로 바꾸기」 는 FAB 자리에 선다 — 층을 떠나도 저장 안 한 배치 상자는 남는다.
    _ok(app.button(key="space_status_fab_breadcrumb").click().run())
    _ok(app.checkbox(key="space_switch_to_official_discard").check().run())
    _ok(app.button(key="space_switch_to_official").click().run())

    errors = [str(item.value) for item in app.error]
    assert "설비 시나리오를 바꾸지 못했습니다: 시험 실패" in errors
    assert not any("저장하지 못했습니다" in text for text in errors)

    _ok(app.run())
    assert not any("바꾸지 못했습니다" in str(item.value) for item in app.error)


def test_the_editor_turns_the_canvas_controls_off_when_told() -> None:
    """가정 세션 편집기는 「편집 영역」 칸을 끈다 — JS 가 칸을 끄고 `setCanvas` 도 막는다(옛 단축키·
    되돌리기 길). 서버도 적용의 캔버스 값을 거부한다(두 겹 —
    `test_an_assumption_canvas_value_from_an_old_browser_is_refused`)."""
    script = (space_layout_editor._ASSETS / "editor.js").read_text(encoding="utf-8")
    guard = script.index("function setCanvas(")
    assert "data.canvasEditable === false" in script[guard : guard + 400]
    assert "q('.sle-area').querySelectorAll('input, button')" in script


_LOCK_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const control = (title) => ({ disabled: false, title, dataset: {} })
const controls = [control('놓인 호기·요소가 다 들어가는 가장 작은 크기'), control('')]
const toggle = { disabled: false, title: '', attrs: {}, setAttribute(k, v) { this.attrs[k] = v } }
const form = { hidden: false }
const seen = () => ({
  controls: controls.map((c) => [c.disabled, c.title]),
  toggle: [toggle.disabled, toggle.title, form.hidden],
})
const out = []
for (const step of input.steps) {
  lockCanvasControls(controls, step.locked, '잠금 까닭')
  lockNewUnitToggle(toggle, form, step.newUnit)
  out.push(seen())
}
process.stdout.write(JSON.stringify({ steps: out }))
"""


def test_the_editor_locks_follow_each_run_and_come_back_off() -> None:
    """편집 영역 칸·새 호기 단추 잠금은 회차마다 받은 값대로 켜고 끈다 — 가정 세션에서 끈 칸이 공식
    세션으로 돌아와도(편집기 key·DOM 이 같다) 꺼진 채 남지 않고, 풀면 처음 풍선 글로 돌아간다(S3
    리뷰)."""
    source = "\n".join(
        _js_decl(head) for head in ("function lockCanvasControls(", "function lockNewUnitToggle(")
    )
    result = _node(
        source + _LOCK_RUNNER,
        {
            "steps": [
                {"locked": True, "newUnit": "더 새 리비전이 있어 새 호기를 넣지 않습니다"},
                {"locked": False, "newUnit": None},
            ]
        },
    )
    locked, unlocked = result["steps"]
    assert locked["controls"] == [[True, "잠금 까닭"], [True, "잠금 까닭"]]
    assert locked["toggle"] == [True, "더 새 리비전이 있어 새 호기를 넣지 않습니다", True]
    assert unlocked["controls"] == [
        [False, "놓인 호기·요소가 다 들어가는 가장 작은 크기"],
        [False, ""],
    ]
    assert unlocked["toggle"][:2] == [False, ""]


def _load_section(database: str) -> None:
    """사이드바 설비 시나리오 팝업 「불러오기」 구획 한 회차(Space 화면에서 연 꼴)."""
    from pathlib import Path

    from capa_simulation.components.equipment_scenario_status import (
        render_equipment_scenario_dialog_body,
    )
    from capa_simulation.navigation import SPACE_STATUS

    render_equipment_scenario_dialog_body(Path(database), page_file=Path(SPACE_STATUS.path).name)


def test_loading_an_assumption_asks_before_dropping_a_floor_use_draft(tmp_path: Path) -> None:
    """Space 층 사용 편집 초안은 공식 설비 시나리오에서만 산다(Q3) — 가정 시나리오를 불러오면 그
    초안을 버리므로 「변경을 버리고 불러오기」 를 묻는다. 공식의 다른 리비전은 묻지 않는다(설계
    9장, S3 리뷰)."""
    from capa_simulation.components.equipment_scenario_status import (
        DIALOG_SCENARIO_KEY,
        DISCARD_KEY,
        LOAD_BUTTON_KEY,
    )
    from capa_simulation.components.space_floor_list import BASE_KEY, DRAFT_KEY

    repository, setup = _overlay(tmp_path)
    app = AppTest.from_function(
        _load_section, args=(str(repository.database_path),), default_timeout=60
    )
    app.session_state[EDIT_TOGGLE_KEY] = True
    app.session_state[DRAFT_KEY] = {"C2 3F": "UNUSED"}
    app.session_state[BASE_KEY] = (0, ())
    app.session_state[DIALOG_SCENARIO_KEY] = setup
    _ok(app.run())

    assert app.button(key=LOAD_BUTTON_KEY).disabled
    assert any("저장하지 않은 Space 층 사용 편집이 있습니다" in str(c.value) for c in app.caption)
    app.checkbox(key=DISCARD_KEY).check()
    _ok(app.run())
    assert not app.button(key=LOAD_BUTTON_KEY).disabled

    official = AppTest.from_function(
        _load_section, args=(str(repository.database_path),), default_timeout=60
    )
    official.session_state[EDIT_TOGGLE_KEY] = True
    official.session_state[DRAFT_KEY] = {"C2 3F": "UNUSED"}
    official.session_state[BASE_KEY] = (0, ())
    official.session_state[DIALOG_SCENARIO_KEY] = OPERATIONS
    _ok(official.run())
    assert not official.button(key=LOAD_BUTTON_KEY).disabled
    assert not [box for box in official.checkbox if box.key == DISCARD_KEY]


def _marks_then_load_section(database: str) -> None:
    """`app.py` 처럼 Space 탭 점·떠나기 확인을 팝업·페이지보다 **먼저** 세어 적고 「불러오기」
    구획을 그린다(`_load_section` 과 같은 한 회차 — 함수 본문만 도므로 이름은 안에서 들인다)."""
    from pathlib import Path

    import streamlit as st

    from capa_simulation.components.equipment_scenario_status import (
        render_equipment_scenario_dialog_body,
    )
    from capa_simulation.components.page_tabs import leave_notice, page_unsaved_marks
    from capa_simulation.navigation import SPACE_STATUS

    page = Path(SPACE_STATUS.path).name
    st.session_state["test_marks"] = page_unsaved_marks(page)
    st.session_state["test_leave"] = leave_notice(page)
    render_equipment_scenario_dialog_body(Path(database), page_file=page)


@pytest.mark.parametrize("assumption", [True, False], ids=["가정", "공식"])
def test_loading_an_assumption_drops_the_floor_use_draft_before_the_tab_marks(
    tmp_path: Path, assumption: bool
) -> None:
    """묻고 버린 층 사용 초안은 불러온 회차에 팝업이 버린다 — Space 가 잠그며 버리기(탭 줄 뒤)를
    기다리면 다음 회차 `app.py` 의 탭 점·떠나기 확인이 버린 초안을 한 회차 더 셌다(E2E — 거짓 「이
    화면을 떠날까요?」). 공식의 다른 리비전은 초안이 산다(묻지 않고 남긴다)."""
    from capa_simulation.components.equipment_scenario_status import (
        DIALOG_SCENARIO_KEY,
        DISCARD_KEY,
        LOAD_BUTTON_KEY,
    )
    from capa_simulation.components.space_floor_list import BASE_KEY, DRAFT_KEY

    repository, setup = _overlay(tmp_path)
    app = AppTest.from_function(
        _marks_then_load_section, args=(str(repository.database_path),), default_timeout=60
    )
    app.session_state[EDIT_TOGGLE_KEY] = True
    app.session_state[DRAFT_KEY] = {"C2 3F": "UNUSED"}
    app.session_state[BASE_KEY] = (0, ())
    app.session_state[DIALOG_SCENARIO_KEY] = setup if assumption else OPERATIONS
    _ok(app.run())
    dirty = {SPACE_STATUS.path: "저장하지 않은 층 사용 편집"}
    assert app.session_state["test_marks"] == dirty
    if assumption:
        app.checkbox(key=DISCARD_KEY).check()
        _ok(app.run())
    app.button(key=LOAD_BUTTON_KEY).click()
    _ok(app.run())

    assert app.session_state[SELECTION_KEY]["scenario_id"] == (setup if assumption else OPERATIONS)
    if assumption:
        assert app.session_state[EDIT_TOGGLE_KEY] is False
        assert DRAFT_KEY not in app.session_state and BASE_KEY not in app.session_state
        assert app.session_state["test_marks"] == {}
        assert app.session_state["test_leave"] == ""
    else:
        assert app.session_state[EDIT_TOGGLE_KEY] is True
        assert app.session_state[DRAFT_KEY] == {"C2 3F": "UNUSED"}
        assert app.session_state["test_marks"] == dirty


def test_the_canvas_dialog_previews_the_hypothetical_layout_before_shrinking(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """S4 — 설계 6-4·7-2. 공식 세션의 층 캔버스 팝업이 가정 설비 시나리오 배치의 이 층 차이
    요소(밖이면 저장 단추를 끔 — 저장소가 막는다)와 차이 호기(경고 뒤 확인 체크)를 미리 말한다."""
    from test_equipment_layout_overlay_repository import _floor_base, _mark

    repository = _seeded(tmp_path)
    clone = _clone(repository)
    mine = _session(repository, clone.equipment_scenario_id)
    assert mine.schedule is not None
    repository.save_equipment(
        _request(
            mine,
            clone.equipment_scenario_id,
            equipment=_set(mine.equipment, "EQ-01", "X좌표", 85.0),
            floor_marks={("C1", "1F"): [_mark("MK-FAR", x=90.0).editor_payload()]},
            floor_layout_bases={
                ("C1", "1F"): _floor_base(repository, mine.schedule.schedule_revision_id)
            },
        )
    )
    clear_equipment_repository()
    app = _ok(_space(tmp_path, OPERATIONS).run())
    app.button(key="space_floor_layout_open_C1_1F").click().run()
    app.checkbox(key="space_floor_layout_auto_C1_1F").uncheck().run()
    app.number_input(key="space_floor_layout_width_C1_1F_manual_100x60").set_value(95.0).run()
    _ok(app)

    warnings = [str(item.value) for item in app.warning]
    assert any("가정 배치 「셋업 실무」 호기 1대가 범위를 벗어납니다" in text for text in warnings)
    assert not any("도면 요소가 범위를 벗어나" in text for text in warnings)
    assert app.button(key="space_floor_layout_save_C1_1F").disabled
    app.checkbox(key="space_floor_layout_shrink_C1_1F").check().run()
    assert not app.button(key="space_floor_layout_save_C1_1F").disabled

    app.number_input(key="space_floor_layout_width_C1_1F_manual_100x60").set_value(80.0).run()
    warnings = [str(item.value) for item in app.warning]
    assert any(
        "도면 요소가 범위를 벗어나" in text and "가정 배치 「셋업 실무」 의 요소도 밖입니다" in text
        for text in warnings
    )
    assert app.button(key="space_floor_layout_save_C1_1F").disabled
