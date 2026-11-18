# Purpose: 설비 저장의 비가동 내용 대조 벽 — 실무자는 비가동 일정만 바꾼 저장만 한다(음성 · 양성).

"""설비 저장 비가동 내용 대조 벽(2026-11-18 접속 등급 — 2차 답 「다」).

실무자(editor)는 설비 마스터 「비가동 일정」 표를 고쳐 저장할 수 있다. 같은 「리비전 저장」 이
일정 · 배치 · 비가동을 한 리비전으로 쓰므로 벽은 단추 숨김이 아니라 **저장 순간의 내용 대조**다 —
공통 대장 · 일정 일곱 칸 · 배치 · 이름 가운데 하나라도 출발점과 다르면 통째 거절하고 아무것도
쓰지 않는다(`equipment_repository._save_equipment` 의 등급 벽 ⓐ 요청 꼴 · ⓑ 내용).

모든 등급 시험은 「운영 + 통합인증 켜짐」 판정을 거치고(`grade_support.as_grade`) 판정이 실제로
섰는지 `judge_spy` 로 본다. 값은 모두 합성이다.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from alert_marks import flashed
from grade_support import (
    as_grade,
    grade_page_script,
    judge_spy,
    operational_sso_off,
    preview,
    unrestricted,
)
from grid_fake import Calls, install_fake_grid, last, send_ops
from streamlit.testing.v1 import AppTest
from test_equipment_pages import _page_script
from test_equipment_scenario_repository import (
    _clone,
    _counts,
    _migrated,
    _request,
    _seeded,
    _session,
    _set,
    _value,
    _with_downtime,
    _with_unit,
)

from capa_simulation.audit import recorder
from capa_simulation.auth import grades
from capa_simulation.components import equipment_master_grid as emg
from capa_simulation.components import space_layout_editor
from capa_simulation.components.equipment_data_workspace import BUFFER_KEY
from capa_simulation.components.equipment_master_tab import SAVE_BUTTON_KEY, SIDE_CHANGES, SIDE_KEY
from capa_simulation.navigation import EQUIPMENT_MASTER_TAB, EQUIPMENT_TAB_KEY
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import (
    DuckDBEquipmentRepository,
    EquipmentSaveRequest,
)

ROOT = Path(__file__).resolve().parents[1]
WALL = ("equipment.save", grades.EDITOR)
REFUSED = grades.refusal_text("equipment.save")


@pytest.fixture(autouse=True)
def _release_repository() -> Any:
    yield
    clear_equipment_repository()


def _refused(
    repository: DuckDBEquipmentRepository, request: EquipmentSaveRequest
) -> list[tuple[str, str]]:
    """실무자의 저장이 거절되고 아무것도 쓰지 않았다 — 감사 한 줄(작업 실패 줄 없음)."""
    before = _counts(repository)
    recorder.start(env="cdep", version="test", inst="i-test")
    with judge_spy() as seen, pytest.raises(grades.GradeDenied) as caught:
        repository.save_equipment(request)
    assert (caught.value.action, caught.value.need) == ("equipment.save", grades.MANAGER)
    assert _counts(repository) == before, "공통 · 일정 · 공식 번호 그대로"
    lines = recorder.take_pending()
    assert [line["ev"] for line in lines] == ["authz_fail_grade"], lines
    assert lines[0]["det"] == {"action": "equipment.save", "need": "manager", "have": "editor"}
    return seen


def test_an_editor_changing_one_schedule_cell_saves_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _seeded(tmp_path)
    session = _session(repository)
    as_grade(monkeypatch, grades.EDITOR)

    seen = _refused(
        repository,
        _request(session, equipment=_set(session.equipment, "EQ-02", "Qual일정", "2026-08-25")),
    )

    assert seen == [("equipment.downtime", grades.EDITOR), WALL], "바닥을 지나 내용 대조에서 멈춤"


def test_an_editor_changing_a_common_cell_or_a_place_saves_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _seeded(tmp_path)
    session = _session(repository)
    as_grade(monkeypatch, grades.EDITOR)

    common = _refused(
        repository, _request(session, equipment=_set(session.equipment, "EQ-01", "담당자", "담당B"))
    )
    place = _refused(
        repository, _request(session, equipment=_set(session.equipment, "EQ-01", "X좌표", 44.0))
    )
    added = _refused(
        repository, _request(session, equipment=_with_unit(session.equipment, "EQ-09", 60.0))
    )

    assert WALL in common and WALL in place and WALL in added


def test_an_editor_request_carrying_layout_or_names_stops_before_any_layout_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """요청 꼴(층 값 · 이름 바꿈 · 배치 역할)은 검증보다 먼저 막는다 — 배치 오류 글이 아니라 등급
    거절이다(벽 ⓐ)."""
    repository = _seeded(tmp_path)
    setup = _clone(repository)
    session = _session(repository)
    other = _session(repository, setup.equipment_scenario_id)
    as_grade(monkeypatch, grades.EDITOR)
    renamed = session.equipment.replace({"설비명": {"EQ-01": "EQ-01R"}})
    downtime = session.downtime.replace({"설비명": {"EQ-01": "EQ-01R"}})

    for request in (
        _request(session, equipment=renamed, downtime=downtime, renames={"EQ-01R": "EQ-01"}),
        _request(session, group_renames={"DEMO-MAIN": "DEMO-MAIN2"}),
        _request(session, expected_layout_role="official"),
        # 가정 설비 시나리오의 층 캔버스는 원래 배치 범위 오류로 멈추는 요청이다.
        _request(other, setup.equipment_scenario_id, floor_canvases={("DEMO", "1F"): (100, 80)}),
    ):
        assert _refused(repository, request) == [("equipment.downtime", grades.EDITOR), WALL]


def test_an_editor_changing_an_assumption_place_saves_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """가정 설비 시나리오의 배치 칸은 공통이 아니라 배치 차이로 간다 — 그것도 비가동 밖이다."""
    repository = _seeded(tmp_path)
    setup = _clone(repository)
    other = _session(repository, setup.equipment_scenario_id)
    as_grade(monkeypatch, grades.EDITOR)

    seen = _refused(
        repository,
        _request(
            other,
            setup.equipment_scenario_id,
            equipment=_set(other.equipment, "EQ-01", "X좌표", 44.0),
        ),
    )

    assert WALL in seen


def test_an_editor_saving_only_downtime_on_the_official_scenario_saves_and_publishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _seeded(tmp_path)
    session = _session(repository)
    as_grade(monkeypatch, grades.EDITOR)

    recorder.start(env="cdep", version="test", inst="i-test")
    with judge_spy() as seen:
        result = repository.save_equipment(
            _request(
                session,
                downtime=_with_downtime(session.downtime, "EQ-02", "점검", "2026-09-20"),
                note="DEMO 비가동",
            )
        )

    assert seen == [("equipment.downtime", grades.EDITOR)], "내용 대조는 바닥만으로 지난다"
    assert result.common is None and result.schedule is not None
    assert result.release_no == 2, "공식 설비 시나리오의 저장은 지금처럼 공식으로 발행"
    assert _counts(repository) == (1, 2, 2)
    # 실무자의 저장이 공식 발행을 냈다는 것이 작업 기록 상세에 남는다(번호 · 함께 넣은 수).
    saved = [line for line in recorder.take_pending() if line["ev"] == "data_equipment_save"]
    assert [(line["det"]["release_no"], line["det"]["propagated"]) for line in saved] == [(2, 0)]
    official = repository.load_official_snapshot()
    assert official is not None and len(official.downtime) == 2


def test_an_editor_saving_downtime_on_an_assumption_also_puts_it_into_the_official(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _seeded(tmp_path)
    setup = _clone(repository)
    other = _session(repository, setup.equipment_scenario_id)
    as_grade(monkeypatch, grades.EDITOR)
    recorder.start(env="cdep", version="test", inst="i-test")

    result = repository.save_equipment(
        _request(
            other,
            setup.equipment_scenario_id,
            downtime=_with_downtime(other.downtime, "EQ-02", "점검", "2026-09-20"),
        )
    )

    assert result.schedule is not None and result.common is None
    assert [item.scenario_name for item in result.propagated] == ["운영 일정"]
    assert result.release_no is not None, "함께 넣은 「운영 일정」 리비전이 공식으로 발행"
    saved = [line for line in recorder.take_pending() if line["ev"] == "data_equipment_save"]
    assert [(line["det"]["release_no"], line["det"]["propagated"]) for line in saved] == [
        (result.release_no, 1)
    ]
    official = repository.load_official_snapshot()
    assert official is not None
    assert ("EQ-02", "점검") in set(
        map(tuple, official.downtime[["설비명", "비가동유형"]].values.tolist())
    )


def _unscheduled_setup(tmp_path: Path) -> tuple[DuckDBEquipmentRepository, str]:
    """가정 시나리오에 일정 행이 없는 호기 EQ-03(공식에만 일정)을 둔 저장소와 그 시나리오 id."""
    repository = _seeded(tmp_path)
    setup = _clone(repository)
    session = _session(repository)
    repository.save_equipment(
        _request(
            session,
            equipment=_with_unit(session.equipment, "EQ-03", 50.0),
            propagate_new_units=False,
        )
    )
    other = _session(repository, setup.equipment_scenario_id)
    assert "EQ-03" in other.unscheduled_units
    assert "EQ-03" not in set(other.calculation_frames()[1]["설비명"])
    return repository, setup.equipment_scenario_id


@pytest.mark.parametrize("propagate", [True, False])
def test_an_editor_cannot_pull_a_unit_without_a_schedule_into_the_scenario_by_downtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, propagate: bool
) -> None:
    """출발 일정에 없던 호기의 비가동 — 그 호기의 빈 일정 행이 함께 끌려 오면 그 시나리오의 계산
    대상이 바뀐다(F4 — 일정 행이 있느냐). 일곱 칸이 비었어도 실무자 저장은 통째 거절이고 계산 대상 ·
    일정 없음 호기가 그대로다."""
    repository, scenario_id = _unscheduled_setup(tmp_path)
    other = _session(repository, scenario_id)
    as_grade(monkeypatch, grades.EDITOR)

    seen = _refused(
        repository,
        _request(
            other,
            scenario_id,
            downtime=_with_downtime(other.downtime, "EQ-03", "공사", "2026-09-12"),
            propagate_new_downtime=propagate,
        ),
    )

    assert seen == [("equipment.downtime", grades.EDITOR), WALL], "바닥을 지나 내용 대조에서 멈춤"
    after = _session(repository, scenario_id)
    assert after.unscheduled_units == other.unscheduled_units
    assert "EQ-03" not in set(after.downtime["설비명"])
    assert after.calculation_frames()[1]["설비명"].tolist() == (
        other.calculation_frames()[1]["설비명"].tolist()
    )


def test_a_manager_may_pull_a_unit_without_a_schedule_into_the_scenario_by_downtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """같은 저장을 관리자는 한다 — 호기가 그 시나리오의 계산 대상으로 든다(시나리오 구성 바꿈)."""
    repository, scenario_id = _unscheduled_setup(tmp_path)
    other = _session(repository, scenario_id)
    as_grade(monkeypatch, grades.MANAGER)

    result = repository.save_equipment(
        _request(
            other,
            scenario_id,
            downtime=_with_downtime(other.downtime, "EQ-03", "공사", "2026-09-12"),
            propagate_new_downtime=False,
        )
    )

    assert result.schedule is not None and result.common is None
    saved = _session(repository, scenario_id)
    assert "EQ-03" in set(saved.downtime["설비명"])
    assert "EQ-03" not in saved.unscheduled_units


def test_an_editor_downtime_save_on_an_old_contract_common_still_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """옛 꼴 공통의 첫 저장(값 그대로 v4 옮겨 쓰기)은 공통 변경이 아니다 — 막지 않는다."""
    repository = _migrated(tmp_path)
    session = _session(repository)
    name = str(session.equipment["설비명"].iloc[0])
    as_grade(monkeypatch, grades.EDITOR)

    result = repository.save_equipment(
        _request(session, downtime=_with_downtime(session.downtime, name, "점검", "2026-09-20"))
    )

    assert result.forced_common and result.schedule is not None


def test_a_manager_changing_one_schedule_cell_saves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _seeded(tmp_path)
    session = _session(repository)
    as_grade(monkeypatch, grades.MANAGER)

    with judge_spy() as seen:
        result = repository.save_equipment(
            _request(session, equipment=_set(session.equipment, "EQ-02", "Qual일정", "2026-08-25"))
        )

    assert result.schedule is not None
    assert ("equipment.save", grades.MANAGER) in seen, "관리자도 내용 대조를 지난다"
    official = repository.load_official_snapshot()
    assert official is not None
    assert str(_value(official, "EQ-02", "Qual일정"))[:10] == "2026-08-25"


def test_a_viewer_cannot_save_even_downtime_and_the_wrapper_needs_a_manager(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _seeded(tmp_path)
    session = _session(repository)
    downtime = _with_downtime(session.downtime, "EQ-02", "점검", "2026-09-20")
    as_grade(monkeypatch, grades.VIEWER)
    with pytest.raises(grades.GradeDenied) as viewer:
        repository.save_equipment(_request(session, downtime=downtime))
    assert viewer.value.action == "equipment.downtime"

    as_grade(monkeypatch, grades.EDITOR)
    with pytest.raises(grades.GradeDenied) as wrapper:
        repository.save_snapshot(session.baseline, session.equipment, downtime)
    assert wrapper.value.action == "equipment.save"
    assert _counts(repository) == (1, 1, 1)


@pytest.mark.parametrize("place", ["unrestricted", "operational_sso_off"])
def test_off_the_signed_in_operational_server_the_wall_stays_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, place: str
) -> None:
    """운영 아님(개발 · WebIDE · 사내 PC)과 통합인증 꺼진 운영(관리자까지)은 지금 그대로
    저장한다."""
    repository = _seeded(tmp_path)
    session = _session(repository)
    if place == "unrestricted":
        unrestricted(monkeypatch)
    else:
        operational_sso_off(monkeypatch)

    result = repository.save_equipment(
        _request(session, equipment=_set(session.equipment, "EQ-02", "Qual일정", "2026-08-25"))
    )

    assert result.schedule is not None


# ------------------------------------------------------------------ 화면을 거친 거절(입구 셋)
def _screen_refused(app: AppTest, repository: DuckDBEquipmentRepository, before: Any) -> None:
    """누른 화면이 예외 없이 거절 알림 한 번을 내고 아무것도 쓰지 않았다."""
    assert not list(app.exception), [element.message for element in app.exception]
    assert [item.value for item in flashed(app, "error")] == [REFUSED]
    assert _counts(repository) == before, "공통 · 일정 · 공식 수 그대로"


def _master_app(database: Path) -> AppTest:
    page = ROOT / "app_pages" / "available_equipment_status.py"
    app = AppTest.from_string(grade_page_script(_page_script(page, database)), default_timeout=60)
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_MASTER_TAB
    return app


@pytest.mark.page_failure_card
def test_the_master_tab_save_of_a_schedule_cell_is_refused_for_an_editor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """설비 마스터 「리비전 저장」 — 관리자로 그리고 일정 칸을 고친 뒤 실무자로 내려 누른다(편집본
    거름이 실무자의 일정 고침을 받지 않으므로 그 앞에서 고친다 — 벽에 실제로 닿는다)."""
    grid: Calls = install_fake_grid(monkeypatch)
    repository = _seeded(tmp_path)
    before = _counts(repository)
    as_grade(monkeypatch, grades.MANAGER)
    app = _master_app(repository.database_path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    app.session_state[emg_loaded_key()] = ("s:EQ-01", "s:EQ-02")
    app.run()
    send_ops(app, grid, {"op": "cell", "id": "s:EQ-02", "col": "Qual일정", "text": "2026-08-25"})
    master = app.session_state[BUFFER_KEY][1]
    assert str(master.set_index("설비명").loc["EQ-02", "Qual일정"])[:10] == "2026-08-25"
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    app.run()

    as_grade(monkeypatch, grades.EDITOR)
    with judge_spy() as seen:
        app.button(key=SAVE_BUTTON_KEY).click().run()

    _screen_refused(app, repository, before)
    assert WALL in seen


def emg_loaded_key() -> str:
    from capa_simulation.components.equipment_data_workspace import GRID_LOADED_KEY

    return GRID_LOADED_KEY


SIDEBAR_PAGE = """
import streamlit as st
from pathlib import Path

import capa_simulation.settings as settings
from capa_simulation.components.equipment_data_workspace import (
    ensure_equipment_drafts,
    replace_equipment_buffer,
)
from capa_simulation.components.equipment_scenario_status import show_equipment_scenario_dialog
from capa_simulation.equipment_scenario_activation import resolve_equipment_session

settings.EQUIPMENT_DUCKDB_PATH = Path({database!r})
session = resolve_equipment_session({database!r})
frames = ensure_equipment_drafts(session.snapshot)
if st.session_state.get("edit") and not st.session_state.get("edited"):
    edited = frames[1].copy()
    edited.loc[edited["설비명"].eq("EQ-02"), "시나리오 메모"] = "DEMO 앞당김"
    replace_equipment_buffer((frames[0], edited, frames[2]))
    st.session_state["edited"] = True
show_equipment_scenario_dialog("available_equipment_status.py")
"""


# 비가동 한 줄만 더한 편집본(실무자도 넣는 변경)으로 사이드바 팝업을 그린다.
DOWNTIME_SIDEBAR_PAGE = SIDEBAR_PAGE.replace(
    """    edited = frames[1].copy()
    edited.loc[edited["설비명"].eq("EQ-02"), "시나리오 메모"] = "DEMO 앞당김"
    replace_equipment_buffer((frames[0], edited, frames[2]))""",
    """    import pandas as pd

    row = {{"설비명": "EQ-02", "비가동유형": "점검", "시작일": pd.Timestamp("2026-09-20")}}
    stops = pd.concat([frames[2], pd.DataFrame([row])], ignore_index=True)[frames[2].columns]
    replace_equipment_buffer((frames[0], frames[1], stops))""",
)


@pytest.mark.page_failure_card
def test_the_sidebar_save_of_a_schedule_edit_is_refused_for_an_editor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """사이드바 「설비 데이터 저장」(팝업) — 실무자부터 서지만 비가동 밖 변경은 저장 순간 막는다."""
    from capa_simulation.components.equipment_scenario_status import (
        EQUIPMENT_SCENARIO_DIALOG_MODE_KEY,
        SAVE_MODE,
    )
    from capa_simulation.components.equipment_scenario_status import (
        SAVE_BUTTON_KEY as SIDEBAR_SAVE_KEY,
    )

    repository = _seeded(tmp_path)
    before = _counts(repository)
    as_grade(monkeypatch, grades.MANAGER)
    app = AppTest.from_string(
        grade_page_script(SIDEBAR_PAGE.format(database=str(repository.database_path))),
        default_timeout=60,
    )
    app.session_state["edit"] = True
    app.session_state[EQUIPMENT_SCENARIO_DIALOG_MODE_KEY] = SAVE_MODE
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]

    as_grade(monkeypatch, grades.EDITOR)
    with judge_spy() as seen:
        app.button(key=SIDEBAR_SAVE_KEY).click().run()

    _screen_refused(app, repository, before)
    assert WALL in seen


@pytest.mark.page_failure_card
def test_the_space_layout_save_is_refused_for_an_editor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Space 「배치 저장」 — 관리자로 배치를 적용한 뒤 실무자로 내려 누르면 요청 꼴(배치)에서
    멈춘다."""
    calls: list[dict[str, Any]] = []

    def _stub(**kwargs: Any) -> SimpleNamespace:
        import streamlit as st

        calls.append(kwargs["data"])
        return SimpleNamespace(apply=st.session_state.pop("test_fake_editor_apply", None))

    monkeypatch.setattr(space_layout_editor, "_EDITOR", _stub)
    repository = _seeded(tmp_path)
    before = _counts(repository)
    as_grade(monkeypatch, grades.MANAGER)
    page = ROOT / "app_pages" / "space_status.py"
    app = AppTest.from_string(
        grade_page_script(_page_script(page, repository.database_path)), default_timeout=60
    )
    app.session_state["space_status_selected_building"] = "C1"
    app.session_state["space_status_selected_floor"] = "1F"
    app.run()
    app.toggle(key="space_layout_edit_mode").set_value(True).run()
    assert not list(app.exception), [element.message for element in app.exception]
    data = calls[-1]
    app.session_state["test_fake_editor_apply"] = {
        "epoch": data["epoch"],
        "changes": [{"id": "EQ-02", "placed": True, "x": 60, "y": 20, "w": 12, "h": 7}],
        "canvas": None,
        "marks": None,
    }
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]

    as_grade(monkeypatch, grades.EDITOR)
    with judge_spy() as seen:
        app.button(key="space_layout_save").click().run()

    _screen_refused(app, repository, before)
    assert WALL in seen


# ------------------------------------------------------------------ 편집본 거름(들어오는 길)
def _import_rows(app: AppTest, text: str) -> AppTest:
    """「엑셀·CSV로 한꺼번에」 팝업 — 미리보기 뒤 「편집본에 넣기」."""
    from capa_simulation.components.equipment_data_workspace import (
        CLIPBOARD_KEY,
        PREVIEW_BUTTON_KEY,
    )
    from capa_simulation.components.equipment_import_dialog import IMPORT_APPLY_BUTTON_KEY
    from capa_simulation.components.equipment_settings_dialog import EQUIPMENT_DIALOG_KEY

    app.session_state[EQUIPMENT_DIALOG_KEY] = "import"
    app.run()
    app.text_area(key=CLIPBOARD_KEY).set_value(text)
    app.button(key=PREVIEW_BUTTON_KEY).click().run()
    assert not list(app.exception), [element.message for element in app.exception]
    app.button(key=IMPORT_APPLY_BUTTON_KEY).click().run()
    assert not list(app.exception), [element.message for element in app.exception]
    return app


@pytest.mark.page_failure_card
def test_an_editor_grid_edit_never_reaches_the_buffer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """실무자의 설비 마스터 표 출납(칸 고침)은 편집본에 들지 않는다 — 한 번 들면 그 세션의 비가동
    저장이 모두 거절된다."""
    grid: Calls = install_fake_grid(monkeypatch)
    repository = _seeded(tmp_path)
    as_grade(monkeypatch, grades.EDITOR)
    app = _master_app(repository.database_path).run()
    app.session_state[emg_loaded_key()] = ("s:EQ-01", "s:EQ-02")
    app.run()
    table = last(grid, emg.GRID_KEY)
    assert all("grade" in row["locks"] for row in table["rows"]), "모든 칸이 잠긴 꼴"
    before = app.session_state[BUFFER_KEY][1].copy()

    recorder.start(env="cdep", version="test", inst="i-test")
    send_ops(app, grid, {"op": "cell", "id": "s:EQ-02", "col": "Qual일정", "text": "2026-08-25"})

    assert app.session_state[BUFFER_KEY][1].equals(before)
    assert [item.value for item in flashed(app, "error")] == [REFUSED]
    lines = [line for line in recorder.take_pending() if line["ev"].startswith("authz_fail")]
    assert [(line["ev"], line["det"]) for line in lines] == [
        ("authz_fail_grade", {"action": "equipment.save", "need": "manager", "have": "editor"})
    ], "저장 벽까지 가지 않은 막힌 누름도 감사 한 줄"


@pytest.mark.page_failure_card
def test_a_grid_edit_refused_only_by_the_preview_leaves_no_audit_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """「이 등급으로 보기」 로만 막힌 누름(실제 등급은 개발자)은 보는 등급으로 알리되 감사 줄은
    남기지 않는다 — 막힌 사람이 없다."""
    grid: Calls = install_fake_grid(monkeypatch)
    repository = _seeded(tmp_path)
    preview(monkeypatch, grades.EDITOR)
    app = _master_app(repository.database_path).run()
    app.session_state[emg_loaded_key()] = ("s:EQ-01", "s:EQ-02")
    app.run()
    before = app.session_state[BUFFER_KEY][1].copy()
    recorder.start(env="cdep", version="test", inst="i-test")

    send_ops(app, grid, {"op": "cell", "id": "s:EQ-02", "col": "Qual일정", "text": "2026-08-25"})

    assert app.session_state[BUFFER_KEY][1].equals(before)
    assert [item.value for item in flashed(app, "error")] == [REFUSED]
    assert not [line for line in recorder.take_pending() if line["ev"].startswith("authz_fail")]


@pytest.mark.page_failure_card
def test_an_editor_downtime_for_a_unit_without_a_schedule_never_reaches_the_buffer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """실무자가 「엑셀·CSV로 한꺼번에」 로 이 시나리오에 일정이 없는 호기의 비가동을 넣으면 편집본에
    들지 않는다 — 들면 저장 때 그 호기의 일정 행이 끌려 와 계산 대상이 바뀌므로 저장 벽이 통째
    거절한다(그 세션의 비가동 저장이 모두 막히지 않게 들어오는 길에서 걷는다)."""
    from capa_simulation.equipment_scenario_activation import SELECTION_KEY
    from capa_simulation.services.equipment_csv import downtime_csv_bytes

    install_fake_grid(monkeypatch)
    repository, scenario_id = _unscheduled_setup(tmp_path)
    as_grade(monkeypatch, grades.EDITOR)
    app = _master_app(repository.database_path)
    app.session_state[SELECTION_KEY] = {"scenario_id": scenario_id, "schedule_revision_id": None}
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    current = app.session_state[BUFFER_KEY][2].copy()
    pulled = downtime_csv_bytes(_with_downtime(current, "EQ-03", "공사", "2026-09-12")).decode(
        "utf-8-sig"
    )

    _import_rows(app, pulled.replace(",", "\t"))

    assert app.session_state[BUFFER_KEY][2].equals(current)
    assert [item.value for item in flashed(app, "error")] == [REFUSED]


@pytest.mark.page_failure_card
def test_an_editor_imports_only_downtime_and_saves_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """실무자는 「엑셀·CSV로 한꺼번에」 의 「등록할 표」 가 비가동 일정 하나다 — 비가동만 넣어
    「리비전 저장」 하면 저장된다(양식 · 현재 데이터 왕복과 같은 길)."""
    from capa_simulation.components.equipment_data_workspace import TARGET_KEY
    from capa_simulation.services.equipment_csv import downtime_csv_bytes

    install_fake_grid(monkeypatch)
    repository = _seeded(tmp_path)
    as_grade(monkeypatch, grades.EDITOR)
    app = _master_app(repository.database_path).run()
    current = app.session_state[BUFFER_KEY][2]
    roundtrip = downtime_csv_bytes(_with_downtime(current, "EQ-02", "점검", "2026-09-20")).decode(
        "utf-8-sig"
    )

    from capa_simulation.components.equipment_settings_dialog import EQUIPMENT_DIALOG_KEY

    app.session_state[EQUIPMENT_DIALOG_KEY] = "import"
    app.run()
    assert list(app.selectbox(key=TARGET_KEY).options) == ["비가동 일정"]
    _import_rows(app, roundtrip.replace(",", "\t"))
    assert len(app.session_state[BUFFER_KEY][2]) == len(current) + 1
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    app.run()
    with judge_spy() as seen:
        app.button(key=SAVE_BUTTON_KEY).click().run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert not flashed(app, "error")
    assert seen and WALL not in seen
    assert _counts(repository) == (1, 2, 2), "비가동만 바꾼 저장은 공식 설비 시나리오에 발행"


@pytest.mark.page_failure_card
def test_an_editor_with_a_pending_fab_layout_saves_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """한 누름이 FAB 대기분(설비 · Space 저장 — 관리자부터)과 비가동을 함께 쓰려 하면 첫 쓰기 전에
    통째로 거절한다 — 반쪽 저장이 없다."""
    from capa_simulation.components import equipment_data_workspace as workspace
    from capa_simulation.components.equipment_scenario_status import (
        EQUIPMENT_SCENARIO_DIALOG_MODE_KEY,
        SAVE_MODE,
    )
    from capa_simulation.components.equipment_scenario_status import (
        SAVE_BUTTON_KEY as SIDEBAR_SAVE_KEY,
    )

    written: list[str] = []
    monkeypatch.setattr(workspace, "pending_fab_layout", lambda: SimpleNamespace(marks=()))
    monkeypatch.setattr(workspace, "save_pending_fab_layout", lambda _repo: written.append("fab"))
    repository = _seeded(tmp_path)
    before = _counts(repository)
    page = DOWNTIME_SIDEBAR_PAGE
    as_grade(monkeypatch, grades.EDITOR)
    app = AppTest.from_string(
        grade_page_script(page.format(database=str(repository.database_path))),
        default_timeout=60,
    )
    app.session_state["edit"] = True
    app.session_state[EQUIPMENT_SCENARIO_DIALOG_MODE_KEY] = SAVE_MODE
    app.run()
    with judge_spy() as seen:
        app.button(key=SIDEBAR_SAVE_KEY).click().run()

    _screen_refused(app, repository, before)
    assert written == [], "FAB 대기분도 쓰지 않는다"
    assert seen[0] == WALL, "첫 쓰기 전에 가장 높은 등급 하나로 본다"
