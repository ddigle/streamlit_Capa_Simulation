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

import pytest
from grade_support import as_grade, judge_spy, operational_sso_off, unrestricted
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
from capa_simulation.persistence.equipment_repository import (
    DuckDBEquipmentRepository,
    EquipmentSaveRequest,
)

WALL = ("equipment.save", grades.EDITOR)


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
    official = repository.load_official_snapshot()
    assert official is not None and len(official.downtime) == 2


def test_an_editor_saving_downtime_on_an_assumption_also_puts_it_into_the_official(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _seeded(tmp_path)
    setup = _clone(repository)
    other = _session(repository, setup.equipment_scenario_id)
    as_grade(monkeypatch, grades.EDITOR)

    result = repository.save_equipment(
        _request(
            other,
            setup.equipment_scenario_id,
            downtime=_with_downtime(other.downtime, "EQ-02", "점검", "2026-09-20"),
        )
    )

    assert result.schedule is not None and result.common is None
    assert [item.scenario_name for item in result.propagated] == ["운영 일정"]
    official = repository.load_official_snapshot()
    assert official is not None
    assert ("EQ-02", "점검") in set(
        map(tuple, official.downtime[["설비명", "비가동유형"]].values.tolist())
    )


def test_an_editor_may_add_downtime_to_a_unit_without_a_schedule_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """출발 일정에 없던 호기의 비가동 — 그 호기의 빈 일정 행이 함께 끌려 와도 일곱 칸은 비어
    있다."""
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
    as_grade(monkeypatch, grades.EDITOR)

    result = repository.save_equipment(
        _request(
            other,
            setup.equipment_scenario_id,
            downtime=_with_downtime(other.downtime, "EQ-03", "공사", "2026-09-12"),
            propagate_new_downtime=False,
        )
    )

    assert result.schedule is not None and result.common is None
    saved = _session(repository, setup.equipment_scenario_id)
    assert "EQ-03" in set(saved.downtime["설비명"])


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
