# Purpose: 가정 설비 시나리오 배치 차이의 저장·빨리 감기·끝 확인·발행 막기·E7·캔버스를 검증한다.

"""설비 시나리오 2단계 S2 — 저장소가 배치를 역할로 가른다(설계 6장).

공식 설비 시나리오 대상 저장은 위치를 공통 대장에, 도면 요소·Main 설비명 위치를 층 현행값에 쓰고
(지금 그대로), 가정 대상 저장은 셋 다 그 시나리오의 새 일정 리비전의 **배치 차이**로 쓴다. 배치
차이가 있는 시나리오는 공식으로 발행하지 않고, E7 되돌리기·여기서 새 시나리오는 차이도 옮긴다.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import pytest
from test_equipment_availability import _baseline, _downtime, _equipment
from test_equipment_scenario_repository import (
    OPERATIONS,
    _clone,
    _counts,
    _request,
    _scenario,
    _session,
    _set,
    _with_unit,
)

from capa_simulation.persistence import equipment_repository, equipment_scenario_store
from capa_simulation.persistence.equipment_repository import (
    DuckDBEquipmentRepository,
    EquipmentLayoutOverflow,
    EquipmentLayoutPublishBlocked,
    EquipmentLayoutRoleChanged,
    EquipmentLayoutScopeError,
    EquipmentRevisionConflict,
    EquipmentScenarioGuardError,
    EquipmentScenarioIncompatible,
    EquipmentSnapshot,
    read_layout_overlay,
)
from capa_simulation.services.equipment_scenario import restore_writes_nothing
from capa_simulation.services.floor_layout_mark import (
    FloorLayoutMark,
    floor_layout_fingerprint,
)
from capa_simulation.services.layout_overlay import (
    EMPTY_LAYOUT_DIGEST,
    MarkChange,
    effective_floor_marks,
    effective_group_labels,
    place_of,
)

FLOOR = ("C1", "1F")


def _seeded(tmp_path: Path, equipment: pd.DataFrame | None = None) -> DuckDBEquipmentRepository:
    repository = DuckDBEquipmentRepository(tmp_path / "equipment.duckdb")
    repository.initialize()
    repository.save_snapshot(
        _baseline(), _equipment() if equipment is None else equipment, _downtime(), note="처음"
    )
    return repository


def _hypothetical(repository: DuckDBEquipmentRepository) -> str:
    return _clone(repository).equipment_scenario_id


def _place(snapshot: EquipmentSnapshot, name: str) -> tuple[Any, ...]:
    rows = snapshot.equipment.loc[snapshot.equipment["설비명"].eq(name).to_numpy(dtype=bool)]
    return place_of(rows.iloc[0])


def _moved(session: EquipmentSnapshot, name: str = "EQ-01", x: float = 50.0) -> pd.DataFrame:
    return _set(session.equipment, name, "X좌표", x)


def _layout_rows(repository: DuckDBEquipmentRepository) -> tuple[int, int, int]:
    with duckdb.connect(str(repository.database_path), read_only=True) as connection:
        row = connection.execute(
            """
            SELECT (SELECT COUNT(*) FROM equipment_ops.equipment_schedule_layout_unit),
                   (SELECT COUNT(*) FROM equipment_ops.equipment_schedule_layout_mark),
                   (SELECT COUNT(*) FROM equipment_ops.equipment_schedule_layout_label)
            """
        ).fetchone()
    assert row is not None
    return int(row[0]), int(row[1]), int(row[2])


def _mark(mark_id: str, *, x: float = 1.0) -> FloorLayoutMark:
    return FloorLayoutMark(
        mark_id=mark_id,
        kind="column",
        x=x,
        y=1.0,
        w=2.0,
        h=2.0,
        rotation=0,
        label="",
        color="",
        hatch=False,
        keep_out=False,
    )


def _floor_base(repository: DuckDBEquipmentRepository, schedule_id: str | None) -> tuple[None, str]:
    """화면이 편집을 시작할 때 본 그 층의 합친 값 지문(캔버스 행 없음)."""
    overlay = repository.load_layout_overlay(schedule_id)
    marks = effective_floor_marks(
        repository.load_floor_layout_marks(*FLOOR), overlay.marks_for(FLOOR)
    )
    labels = effective_group_labels(
        repository.load_floor_group_labels(*FLOOR), overlay.labels_for(FLOOR)
    )
    return None, floor_layout_fingerprint(marks, labels)


# ── 가정 대상 저장 ─────────────────────────────────────────────────────────────────────


def test_moving_a_unit_in_a_hypothetical_scenario_writes_only_its_layout_difference(
    tmp_path: Path,
) -> None:
    repository = _seeded(tmp_path)
    scenario_id = _hypothetical(repository)
    official_before = repository.load_official_snapshot()
    assert official_before is not None
    session = _session(repository, scenario_id)
    before = _counts(repository)

    result = repository.save_equipment(
        _request(session, scenario_id, equipment=_moved(session), expected_layout_role="overlay")
    )

    assert result.common is None and result.schedule is not None
    assert result.layout_overlay_written and result.layout_overlay_units == 1
    assert result.schedule.layout_unit_count == 1
    assert result.schedule.layout_hash not in (None, EMPTY_LAYOUT_DIGEST)
    assert _counts(repository) == (before[0], before[1] + 1, before[2])
    after = _session(repository, scenario_id)
    assert _place(after, "EQ-01")[2] == 50.0
    assert after.layout_overridden_keys == {after.unit_keys["EQ-01"]}
    (official_place,) = (place for _, place in after.layout_official_places)
    assert official_place[2] == 10.0
    official = repository.load_official_snapshot()
    assert official is not None
    assert _place(official, "EQ-01") == _place(official_before, "EQ-01")
    assert official.layout_official_places == ()


def test_moving_a_unit_in_the_official_scenario_writes_the_common_ledger_as_before(
    tmp_path: Path,
) -> None:
    repository = _seeded(tmp_path)
    _hypothetical(repository)
    session = _session(repository)

    result = repository.save_equipment(
        _request(session, equipment=_moved(session), expected_layout_role="official")
    )

    assert result.common is not None and result.schedule is None
    assert not result.layout_overlay_written
    official = repository.load_official_snapshot()
    assert official is not None and _place(official, "EQ-01")[2] == 50.0
    assert _layout_rows(repository) == (0, 0, 0)


def test_an_untouched_unit_in_a_hypothetical_scenario_follows_the_official_move(
    tmp_path: Path,
) -> None:
    """LY2 — 가정에서 손대지 않은 호기는 공식을 따라가고 손댄 호기는 가정 값 그대로다."""
    repository = _seeded(tmp_path)
    scenario_id = _hypothetical(repository)
    session = _session(repository, scenario_id)
    repository.save_equipment(_request(session, scenario_id, equipment=_moved(session)))
    official = _session(repository)
    moved = _set(_moved(official, "EQ-01", 70.0), "EQ-02", "X좌표", 80.0)
    repository.save_equipment(_request(official, equipment=moved))

    after = _session(repository, scenario_id)
    assert _place(after, "EQ-01")[2] == 50.0
    assert _place(after, "EQ-02")[2] == 80.0


def test_a_date_only_save_in_a_hypothetical_scenario_carries_its_layout_difference(
    tmp_path: Path,
) -> None:
    repository = _seeded(tmp_path)
    scenario_id = _hypothetical(repository)
    session = _session(repository, scenario_id)
    first = repository.save_equipment(_request(session, scenario_id, equipment=_moved(session)))
    session = _session(repository, scenario_id)

    second = repository.save_equipment(
        _request(
            session,
            scenario_id,
            equipment=_set(session.equipment, "EQ-02", "Qual일정", "2026-08-25"),
        )
    )

    assert first.schedule is not None and second.schedule is not None
    assert not second.layout_overlay_written
    assert second.schedule.layout_hash == first.schedule.layout_hash
    assert _place(_session(repository, scenario_id), "EQ-01")[2] == 50.0


def test_moving_a_unit_back_to_the_official_place_clears_its_difference(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    scenario_id = _hypothetical(repository)
    session = _session(repository, scenario_id)
    repository.save_equipment(_request(session, scenario_id, equipment=_moved(session)))
    session = _session(repository, scenario_id)

    result = repository.save_equipment(
        _request(session, scenario_id, equipment=_moved(session, x=10.0))
    )

    assert result.schedule is not None and result.layout_overlay_written
    assert result.schedule.layout_hash == EMPTY_LAYOUT_DIGEST
    assert _session(repository, scenario_id).layout_official_places == ()


def _official_cell(repository: DuckDBEquipmentRepository, name: str, column: str) -> Any:
    official = repository.load_official_snapshot()
    assert official is not None
    return official.equipment.set_index("설비명").loc[name, column]


def test_a_hypothetical_move_keeps_the_official_coordinates_exact(tmp_path: Path) -> None:
    """S2 리뷰 — 가정 역할의 공통 쪽은 반올림한 견줄 값(10.2)이 아니라 공통 대장의 원래 값(10.25)을
    둔다. 그러지 않으면 가정 배치 저장이 공식 좌표를 바꾼 공통 리비전을 만든다(I7·LY4)."""
    equipment = _equipment().astype({"X좌표": "float64"})
    equipment.loc[0, "X좌표"] = 10.25
    repository = _seeded(tmp_path, equipment)
    scenario_id = _hypothetical(repository)
    session = _session(repository, scenario_id)
    before = _counts(repository)

    moved = repository.save_equipment(
        _request(session, scenario_id, equipment=_moved(session), expected_layout_role="overlay")
    )

    assert moved.common is None and moved.layout_overlay_written
    assert _counts(repository) == (before[0], before[1] + 1, before[2])
    assert _official_cell(repository, "EQ-01", "X좌표") == 10.25
    # 차이가 있는 호기를 둔 채 다른 까닭(공통 칸 고침)으로 공통을 써도 공식 좌표는 원래 값이다.
    session = _session(repository, scenario_id)
    noted = repository.save_equipment(
        _request(session, scenario_id, equipment=_set(session.equipment, "EQ-02", "메모1", "a"))
    )
    assert noted.common is not None
    assert _official_cell(repository, "EQ-01", "X좌표") == 10.25
    assert _official_cell(repository, "EQ-02", "메모1") == "a"
    assert _place(_session(repository, scenario_id), "EQ-01")[2] == 50.0


def test_marks_and_labels_in_a_hypothetical_scenario_become_its_difference(
    tmp_path: Path,
) -> None:
    repository = _seeded(tmp_path)
    repository.replace_floor_layout_marks(*FLOOR, [_mark("MK-A").editor_payload()])
    scenario_id = _hypothetical(repository)
    session = _session(repository, scenario_id)
    assert session.schedule is not None
    base = _floor_base(repository, session.schedule.schedule_revision_id)

    result = repository.save_equipment(
        _request(
            session,
            scenario_id,
            floor_marks={FLOOR: [_mark("MK-A", x=7.0).editor_payload()]},
            floor_group_labels={FLOOR: {"APW1": "bottom"}},
            floor_layout_bases={FLOOR: base},
        )
    )

    assert result.schedule is not None and not result.floor_values_written
    assert result.layout_overlay_written
    # 결과가 요소·이름표 차이 수를 싣는다 — 화면 결과 문구가 「호기 0대」 만 적지 않게(S3 리뷰).
    assert (
        result.layout_overlay_units,
        result.layout_overlay_marks,
        result.layout_overlay_labels,
    ) == (0, 1, 1)
    overlay = repository.load_layout_overlay(result.schedule.schedule_revision_id)
    assert overlay.marks_for(FLOOR) == (MarkChange("MK-A", "set", _mark("MK-A", x=7.0)),)
    assert overlay.labels_for(FLOOR) == (("APW1", "bottom"),)
    assert repository.load_floor_layout_marks(*FLOOR) == (_mark("MK-A"),)
    assert repository.load_floor_group_labels(*FLOOR) == {}
    # 다시 편집을 시작하면 기대 지문은 공식 ⊕ 그 차이다 — 같은 값을 다시 내면 아무것도 안 쓴다.
    session = _session(repository, scenario_id)
    assert session.schedule is not None
    again = repository.save_equipment(
        _request(
            session,
            scenario_id,
            floor_marks={FLOOR: [_mark("MK-A", x=7.0).editor_payload()]},
            floor_group_labels={FLOOR: {"APW1": "bottom"}},
            floor_layout_bases={
                FLOOR: _floor_base(repository, session.schedule.schedule_revision_id)
            },
        )
    )
    assert not again.wrote_revision and not again.layout_overlay_written


def test_a_hypothetical_canvas_change_is_refused_and_writes_nothing(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    scenario_id = _hypothetical(repository)
    session = _session(repository, scenario_id)
    before = _counts(repository)

    with pytest.raises(EquipmentLayoutScopeError, match="층 캔버스"):
        repository.save_equipment(
            _request(session, scenario_id, floor_canvases={FLOOR: (120.0, 80.0)})
        )

    assert _counts(repository) == before
    assert repository.load_floor_layout_canvases() == {}


def test_a_changed_role_refuses_layout_saves_only(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    scenario_id = _hypothetical(repository)
    session = _session(repository, scenario_id)

    with pytest.raises(EquipmentLayoutRoleChanged, match="공식 배치"):
        repository.save_equipment(
            _request(
                session, scenario_id, equipment=_moved(session), expected_layout_role="official"
            )
        )
    dated = _set(session.equipment, "EQ-02", "Qual일정", "2026-08-25")
    assert repository.save_equipment(_request(session, scenario_id, equipment=dated)).schedule


# ── 낡음·빨리 감기 ────────────────────────────────────────────────────────────────────


def test_a_stale_layout_save_fast_forwards_over_someone_elses_schedule_save(
    tmp_path: Path,
) -> None:
    """검토 F5·H2 — 남의 일정 저장이 내 가정 배치 편집을 막지 않는다(배치 지문이 같으면)."""
    repository = _seeded(tmp_path)
    scenario_id = _hypothetical(repository)
    mine = _session(repository, scenario_id)
    other = _session(repository, scenario_id)
    repository.save_equipment(
        _request(
            other,
            scenario_id,
            equipment=_set(other.equipment, "EQ-02", "Qual일정", "2026-08-25"),
        )
    )

    result = repository.save_equipment(_request(mine, scenario_id, equipment=_moved(mine)))

    assert result.schedule is not None and result.schedule.revision_no == 3
    after = _session(repository, scenario_id)
    assert _place(after, "EQ-01")[2] == 50.0
    qual = after.equipment.set_index("설비명").loc["EQ-02", "Qual일정"]
    assert str(qual)[:10] == "2026-08-25"


def test_mark_differences_have_one_order_so_a_fast_forward_still_matches(
    tmp_path: Path,
) -> None:
    """S2 리뷰 — 편집기 차례(새 요소가 고친 공식 요소보다 앞)로 적은 요소 차이와, 남의 날짜 저장이
    다시 합쳐 적은 차이가 같은 지문이라 그 뒤 배치 빨리 감기가 선다."""
    repository = _seeded(tmp_path)
    repository.replace_floor_layout_marks(
        *FLOOR, [_mark("MK-A").editor_payload(), _mark("MK-B", x=10.0).editor_payload()]
    )
    scenario_id = _hypothetical(repository)
    session = _session(repository, scenario_id)
    assert session.schedule is not None
    drawn = repository.save_equipment(
        _request(
            session,
            scenario_id,
            floor_marks={
                FLOOR: [
                    _mark("MK-NEW", x=20.0).editor_payload(),
                    _mark("MK-A", x=5.0).editor_payload(),
                    _mark("MK-B", x=10.0).editor_payload(),
                ]
            },
            floor_layout_bases={
                FLOOR: _floor_base(repository, session.schedule.schedule_revision_id)
            },
        )
    )
    assert drawn.schedule is not None
    mine = _session(repository, scenario_id)
    other = _session(repository, scenario_id)
    dated = repository.save_equipment(
        _request(
            other,
            scenario_id,
            equipment=_set(other.equipment, "EQ-02", "Qual일정", "2026-08-25"),
        )
    )

    assert dated.schedule is not None
    assert dated.schedule.layout_hash == drawn.schedule.layout_hash
    moved = repository.save_equipment(_request(mine, scenario_id, equipment=_moved(mine)))
    assert moved.schedule is not None and moved.schedule.revision_no == 4
    overlay = repository.load_layout_overlay(moved.schedule.schedule_revision_id)
    assert [change.mark_id for change in overlay.marks_for(FLOOR)] == ["MK-A", "MK-NEW"]


def test_a_stale_layout_save_is_refused_after_someone_elses_layout_save(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    scenario_id = _hypothetical(repository)
    mine = _session(repository, scenario_id)
    other = _session(repository, scenario_id)
    repository.save_equipment(_request(other, scenario_id, equipment=_moved(other, "EQ-02", 60.0)))

    with pytest.raises(EquipmentRevisionConflict):
        repository.save_equipment(_request(mine, scenario_id, equipment=_moved(mine)))


def test_a_stale_schedule_save_is_still_refused(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    scenario_id = _hypothetical(repository)
    mine = _session(repository, scenario_id)
    other = _session(repository, scenario_id)
    repository.save_equipment(_request(other, scenario_id, equipment=_moved(other)))

    with pytest.raises(EquipmentRevisionConflict):
        repository.save_equipment(
            _request(
                mine,
                scenario_id,
                equipment=_set(mine.equipment, "EQ-02", "Qual일정", "2026-08-25"),
            )
        )


# ── 새 호기·묶음 ──────────────────────────────────────────────────────────────────────


def _grouped() -> pd.DataFrame:
    """EQ-01·EQ-02 를 C1 1F 의 모듈 묶음 APW1 로, EQ-X 를 C2 3F 단독으로."""
    equipment = _equipment()
    equipment["Main 설비"] = "APW1"
    equipment.loc[1, "X좌표"] = 22.0
    return _with_unit(equipment, "EQ-X", 5.0, **{"Main 설비": None, "동": "C2", "층": "3F"})


def test_a_new_unit_in_a_hypothetical_scenario_has_no_official_place(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    scenario_id = _hypothetical(repository)
    session = _session(repository, scenario_id)

    result = repository.save_equipment(
        _request(
            session,
            scenario_id,
            equipment=_with_unit(session.equipment, "EQ-NEW", 60.0),
            propagate_new_units=False,
        )
    )

    assert result.common is not None and result.new_units == ("EQ-NEW",)
    official = _session(repository)
    assert official.unscheduled_units == frozenset({"EQ-NEW"})
    official_place = _place(official, "EQ-NEW")
    assert official_place[:4] == (None, None, None, None) and official_place[4:6] == (12.0, 7.0)
    assert _place(_session(repository, scenario_id), "EQ-NEW")[:4] == ("C1", "1F", 60.0, 10.0)


def test_a_new_module_in_a_hypothetical_scenario_takes_its_groups_official_floor(
    tmp_path: Path,
) -> None:
    repository = _seeded(tmp_path, _grouped())
    scenario_id = _hypothetical(repository)
    session = _session(repository, scenario_id)
    equipment = _with_unit(session.equipment, "EQ-03", 34.0, **{"Main 설비": "APW1"})

    result = repository.save_equipment(
        _request(session, scenario_id, equipment=equipment, propagate_new_units=False)
    )

    assert result.common is not None
    assert _place(_session(repository), "EQ-03")[:4] == ("C1", "1F", None, None)
    assert _place(_session(repository, scenario_id), "EQ-03")[:4] == ("C1", "1F", 34.0, 10.0)
    assert result.schedule is not None and result.schedule.layout_unit_count == 3


def test_grouping_a_unit_from_another_official_floor_is_refused_in_a_hypothetical_scenario(
    tmp_path: Path,
) -> None:
    repository = _seeded(tmp_path, _grouped())
    scenario_id = _hypothetical(repository)
    session = _session(repository, scenario_id)
    equipment = _set(session.equipment, "EQ-X", "Main 설비", "APW1")
    equipment = _set(_set(equipment, "EQ-X", "동", "C1"), "EQ-X", "층", "1F")
    before = _counts(repository)

    with pytest.raises(EquipmentLayoutScopeError, match="EQ-X 은 공식 C2 3F"):
        repository.save_equipment(_request(session, scenario_id, equipment=equipment))

    assert _counts(repository) == before


def test_a_unit_placed_only_in_a_hypothetical_scenario_can_join_a_group_there(
    tmp_path: Path,
) -> None:
    """S2 리뷰 — 가정에서 자리 없이 넣은(공식 동·층 미정) 호기는 새 모듈처럼 묶음의 공식 동·층으로
    맞춘다. 공식에는 그 호기 일정이 없어(G2) 거부 글이 가리키는 공식 쪽에서도 고칠 길이 없었다."""
    repository = _seeded(tmp_path, _grouped())
    scenario_id = _hypothetical(repository)
    session = _session(repository, scenario_id)
    repository.save_equipment(
        _request(
            session,
            scenario_id,
            equipment=_with_unit(session.equipment, "EQ-N", 70.0, **{"Main 설비": None}),
            propagate_new_units=False,
        )
    )
    assert _place(_session(repository), "EQ-N")[:4] == (None, None, None, None)
    session = _session(repository, scenario_id)

    joined = repository.save_equipment(
        _request(
            session,
            scenario_id,
            equipment=_set(session.equipment, "EQ-N", "Main 설비", "APW1"),
        )
    )

    assert joined.common is not None and joined.schedule is not None
    official = _session(repository)
    assert _place(official, "EQ-N")[:4] == ("C1", "1F", None, None)
    assert _place(official, "EQ-01")[:4] == ("C1", "1F", 10.0, 10.0)
    assert _place(_session(repository, scenario_id), "EQ-N")[:4] == ("C1", "1F", 70.0, 10.0)


def test_renaming_a_group_moves_the_official_label_key_in_either_role(tmp_path: Path) -> None:
    """검토 F11 — 가정 역할의 묶음 이름 바꾸기도 공식 Main 설비명 위치 행을 새 이름으로 옮긴다."""
    repository = _seeded(tmp_path, _grouped())
    session = _session(repository)
    assert session.schedule is not None
    repository.save_equipment(
        _request(
            session,
            floor_group_labels={FLOOR: {"APW1": "bottom"}},
            floor_layout_bases={FLOOR: _floor_base(repository, None)},
        )
    )
    scenario_id = _hypothetical(repository)
    session = _session(repository, scenario_id)
    renamed = session.equipment.copy()
    renamed.loc[renamed["Main 설비"].eq("APW1").fillna(False), "Main 설비"] = "APW9"

    result = repository.save_equipment(
        _request(session, scenario_id, equipment=renamed, group_renames={"APW9": "APW1"})
    )

    assert result.floor_values_written
    assert repository.load_floor_group_labels(*FLOOR) == {"APW9": "bottom"}


# ── 함께 넣기·교차 검증·끝 확인 ───────────────────────────────────────────────────────


def test_propagating_into_a_hypothetical_scenario_carries_its_latest_difference(
    tmp_path: Path,
) -> None:
    repository = _seeded(tmp_path)
    scenario_id = _hypothetical(repository)
    session = _session(repository, scenario_id)
    repository.save_equipment(_request(session, scenario_id, equipment=_moved(session)))
    official = _session(repository)

    result = repository.save_equipment(
        _request(official, equipment=_with_unit(official.equipment, "EQ-NEW", 80.0))
    )

    (propagated,) = result.propagated
    assert propagated.equipment_scenario_id == scenario_id and propagated.revision_no == 3
    after = _session(repository, scenario_id)
    assert _place(after, "EQ-01")[2] == 50.0
    assert _place(after, "EQ-NEW")[2] == 80.0
    assert after.schedule is not None and after.schedule.layout_unit_count == 1
    official_after = _session(repository)
    assert official_after.schedule is not None
    assert official_after.schedule.layout_hash == EMPTY_LAYOUT_DIGEST


def test_deleting_a_unit_with_a_difference_passes_the_cross_check_and_drops_it(
    tmp_path: Path,
) -> None:
    repository = _seeded(tmp_path)
    scenario_id = _hypothetical(repository)
    session = _session(repository, scenario_id)
    repository.save_equipment(_request(session, scenario_id, equipment=_moved(session)))
    official = _session(repository)
    kept = official.equipment[official.equipment["설비명"].ne("EQ-01")].reset_index(drop=True)
    downtime = official.downtime.iloc[0:0]

    result = repository.save_equipment(_request(official, equipment=kept, downtime=downtime))

    assert result.removed_units == ("EQ-01",)
    after = _session(repository, scenario_id)
    assert after.layout_orphans == 1 and after.layout_official_places == ()


def test_a_failing_final_read_rolls_the_whole_save_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _seeded(tmp_path)
    scenario_id = _hypothetical(repository)
    session = _session(repository, scenario_id)
    before = _counts(repository)
    original = equipment_repository.read_merged
    known = {
        item.schedule_revision_id
        for scenario in repository.list_equipment_scenarios()
        for item in repository.list_schedule_revisions(scenario.equipment_scenario_id)
    }

    def failing(
        connection: duckdb.DuckDBPyConnection, common: str, schedule: str | None
    ) -> EquipmentSnapshot:
        if schedule is not None and schedule not in known:
            raise EquipmentScenarioIncompatible("셋업 실무", 3, "깨진 배치")
        return original(connection, common, schedule)

    monkeypatch.setattr(equipment_repository, "read_merged", failing)
    with pytest.raises(EquipmentScenarioGuardError, match="배치 차이를 얹으면 깨진 배치"):
        repository.save_equipment(_request(session, scenario_id, equipment=_moved(session)))

    assert _counts(repository) == before and _layout_rows(repository) == (0, 0, 0)


def test_an_old_official_revision_with_differences_refuses_layout_edits_only(
    tmp_path: Path,
) -> None:
    """공식 시나리오가 가정이던 때의 리비전(낡은 세션) — 배치 고침은 거부하고, 배치를 건드리지 않은
    공통 칸 저장은 받되 그 리비전의 가정 자리가 공식(공통)으로 새지 않는다(검토 F12)."""
    repository = _seeded(tmp_path)
    scenario_id = _hypothetical(repository)
    session = _session(repository, scenario_id)
    saved = repository.save_equipment(_request(session, scenario_id, equipment=_moved(session)))
    assert saved.schedule is not None
    # 차이가 있는 리비전을 공식으로 낼 수 없으니, 그 시나리오를 공식으로 만든 뒤 옛 리비전을 연다.
    cleared = repository.clear_layout_overlay(
        scenario_id, expected_latest_schedule_revision_id=saved.schedule.schedule_revision_id
    )
    assert cleared is not None
    release = repository.latest_equipment_release()
    assert release is not None
    repository.publish_equipment_release(
        cleared.schedule_revision_id,
        released_by=None,
        note=None,
        expected_latest_release_no=release.release_no,
    )
    old = _session(repository, scenario_id, saved.schedule.schedule_revision_id)

    with pytest.raises(EquipmentLayoutScopeError, match="가정이던 때"):
        repository.save_equipment(_request(old, scenario_id, equipment=_moved(old, x=55.0)))
    noted = repository.save_equipment(
        _request(old, scenario_id, equipment=_set(old.equipment, "EQ-02", "설비이력", "점검"))
    )
    assert noted.common is not None and noted.schedule is None
    official = repository.load_official_snapshot()
    assert official is not None and _place(official, "EQ-01")[2] == 10.0
    assert official.equipment.set_index("설비명").loc["EQ-02", "설비이력"] == "점검"


# ── 캔버스 ────────────────────────────────────────────────────────────────────────────


def test_shrinking_a_canvas_is_refused_when_a_hypothetical_mark_falls_outside(
    tmp_path: Path,
) -> None:
    """검토 F14 — 네 진입점이 가정 배치 요소를 본다. 가정 차이 호기는 막지 않는다."""
    repository = _seeded(tmp_path)
    scenario_id = _hypothetical(repository)
    session = _session(repository, scenario_id)
    assert session.schedule is not None
    repository.save_equipment(
        _request(
            session,
            scenario_id,
            equipment=_moved(session, x=85.0),
            floor_marks={FLOOR: [_mark("MK-FAR", x=90.0).editor_payload()]},
            floor_layout_bases={
                FLOOR: _floor_base(repository, session.schedule.schedule_revision_id)
            },
        )
    )

    with pytest.raises(EquipmentLayoutOverflow, match="「셋업 실무」 .*요소 1개"):
        repository.save_floor_layout_canvas(*FLOOR, 80.0, 60.0)
    with pytest.raises(EquipmentLayoutOverflow):
        repository.save_floor_layout_image(
            *FLOOR, "plan.png", _png(), canvas_width=80.0, canvas_height=60.0
        )
    official = _session(repository)
    with pytest.raises(EquipmentLayoutOverflow):
        repository.save_equipment(_request(official, floor_canvases={FLOOR: (80.0, 60.0)}))
    # 요소가 안이면 줄인다 — 가정 차이 호기(EQ-01 은 x 85 + 12 = 97 로 밖)는 막지 않는다.
    assert repository.save_floor_layout_canvas(*FLOOR, 95.0, 60.0).canvas_width == 95.0


def test_deleting_a_floor_drawing_is_refused_when_a_hypothetical_mark_needs_its_canvas(
    tmp_path: Path,
) -> None:
    """캔버스 넷째 진입점 — 도면을 지우면 캔버스가 기본 크기(100 × 60)로 돌아가므로 가정 배치 요소가
    그 밖이면 막는다(설계 6-4)."""
    repository = _seeded(tmp_path)
    repository.save_floor_layout_canvas(*FLOOR, 150.0, 60.0)
    scenario_id = _hypothetical(repository)
    session = _session(repository, scenario_id)
    assert session.schedule is not None
    _, fingerprint = _floor_base(repository, session.schedule.schedule_revision_id)
    repository.save_equipment(
        _request(
            session,
            scenario_id,
            floor_marks={FLOOR: [_mark("MK-FAR", x=120.0).editor_payload()]},
            floor_layout_bases={FLOOR: ((150.0, 60.0), fingerprint)},
        )
    )

    with pytest.raises(EquipmentLayoutOverflow, match="「셋업 실무」 .*요소 1개"):
        repository.delete_floor_layout_profile(*FLOOR)

    assert repository.load_floor_layout_canvases()[FLOOR] == (150.0, 60.0)


def _png() -> bytes:
    import struct
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x00\x00\x00" * 2 for _ in range(2))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


# ── 공식 발행 ─────────────────────────────────────────────────────────────────────────


def test_a_scenario_with_a_layout_difference_is_not_published_until_it_is_cleared(
    tmp_path: Path,
) -> None:
    repository = _seeded(tmp_path)
    scenario_id = _hypothetical(repository)
    session = _session(repository, scenario_id)
    saved = repository.save_equipment(_request(session, scenario_id, equipment=_moved(session)))
    assert saved.schedule is not None
    release = repository.latest_equipment_release()
    assert release is not None

    with pytest.raises(EquipmentLayoutPublishBlocked, match="호기 1대"):
        repository.publish_equipment_release(
            saved.schedule.schedule_revision_id,
            released_by=None,
            note=None,
            expected_latest_release_no=release.release_no,
        )
    # 차이 없는 옛 리비전(r1)도 최신에 차이가 남아 있으면 막는다(I2 — 저장된 행 기준).
    first = _scenario(repository, scenario_id)
    revisions = repository.list_schedule_revisions(first.equipment_scenario_id)
    with pytest.raises(EquipmentLayoutPublishBlocked):
        repository.publish_equipment_release(
            revisions[-1].schedule_revision_id,
            released_by=None,
            note=None,
            expected_latest_release_no=release.release_no,
        )

    cleared = repository.clear_layout_overlay(
        scenario_id, expected_latest_schedule_revision_id=saved.schedule.schedule_revision_id
    )
    assert cleared is not None and cleared.origin == "layout_clear"
    assert cleared.layout_hash == EMPTY_LAYOUT_DIGEST
    published = repository.publish_equipment_release(
        cleared.schedule_revision_id,
        released_by=None,
        note=None,
        expected_latest_release_no=release.release_no,
    )
    assert published.schedule_revision_id == cleared.schedule_revision_id
    assert (
        repository.clear_layout_overlay(
            scenario_id, expected_latest_schedule_revision_id=cleared.schedule_revision_id
        )
        is None
    )


def test_a_difference_the_official_caught_up_with_is_cleaned_into_a_new_revision_and_published(
    tmp_path: Path,
) -> None:
    """검토 F4 — 저장된 행은 있지만 공식과 같아졌으면 정리한 새 리비전을 발행한다(I2 원시 기준)."""
    repository = _seeded(tmp_path)
    scenario_id = _hypothetical(repository)
    session = _session(repository, scenario_id)
    saved = repository.save_equipment(_request(session, scenario_id, equipment=_moved(session)))
    assert saved.schedule is not None
    official = _session(repository)
    repository.save_equipment(_request(official, equipment=_moved(official)))
    release = repository.latest_equipment_release()
    assert release is not None
    before = _counts(repository)

    published = repository.publish_equipment_release(
        saved.schedule.schedule_revision_id,
        released_by="홍길동",
        note=None,
        expected_latest_release_no=release.release_no,
    )

    assert published.schedule_revision_id != saved.schedule.schedule_revision_id
    assert _counts(repository) == (before[0], before[1] + 1, before[2] + 1)
    newest = _scenario(repository, scenario_id)
    assert newest.latest_schedule_revision_id == published.schedule_revision_id
    assert newest.latest_layout_unit_count == 0
    (cleanup,) = repository.list_schedule_revisions(scenario_id, limit=1)
    assert (cleanup.origin, cleanup.note) == ("layout_clear", "공식과 같아진 배치 차이 정리")


def _latest_common(repository: DuckDBEquipmentRepository) -> str:
    latest = repository.latest_revision_id()
    assert latest is not None
    return latest


def test_the_publish_preview_reads_the_same_judgment_as_publishing(tmp_path: Path) -> None:
    """설계 6-5 — 확인 팝업의 판정(쓰지 않음)이 발행 쓰기와 같다: 차이 없음 → publish, 공식과 다른
    배치 → blocked(실효 수), 공식이 같은 자리로 따라옴 → clean(정리 리비전으로 발행)."""
    repository = _seeded(tmp_path)
    scenario_id = _hypothetical(repository)
    first = _scenario(repository, scenario_id)
    assert first.latest_schedule_revision_id is not None
    plain = repository.preview_layout_publish(
        first.latest_schedule_revision_id,
        common_revision_id=_latest_common(repository),
        newest_schedule_revision_id=first.latest_schedule_revision_id,
    )
    assert (plain.action, plain.stored_rows) == ("publish", 0)

    session = _session(repository, scenario_id)
    saved = repository.save_equipment(_request(session, scenario_id, equipment=_moved(session)))
    assert saved.schedule is not None
    newest = saved.schedule.schedule_revision_id
    blocked = repository.preview_layout_publish(
        newest, common_revision_id=_latest_common(repository), newest_schedule_revision_id=newest
    )
    assert (blocked.action, blocked.units, blocked.stored_units, blocked.newest_rows) == (
        "blocked",
        1,
        1,
        1,
    )
    # 차이 없는 옛 리비전도 그 시나리오 최신에 차이가 남아 있으면 막힌다(I2).
    old = repository.preview_layout_publish(
        first.latest_schedule_revision_id,
        common_revision_id=_latest_common(repository),
        newest_schedule_revision_id=newest,
    )
    assert (old.action, old.stored_rows, old.newest_rows) == ("blocked", 0, 1)

    official = _session(repository)
    repository.save_equipment(_request(official, equipment=_moved(official)))
    before = _counts(repository)
    clean = repository.preview_layout_publish(
        newest, common_revision_id=_latest_common(repository), newest_schedule_revision_id=newest
    )
    assert (clean.action, clean.stored_rows) == ("clean", 1)
    assert _counts(repository) == before


def test_the_canvas_preview_reads_hypothetical_marks_and_units_on_the_floor(
    tmp_path: Path,
) -> None:
    """설계 6-4·7-2 — 캔버스 팝업 미리 보임은 캔버스 저장이 보는 리비전(ACTIVE 최신·최신 공식
    발행)의 그 층 차이 요소 범위와 차이 호기 상자다."""
    repository = _seeded(tmp_path)
    assert repository.layout_overlay_extent(*FLOOR) == equipment_repository.LayoutOverlayExtent()
    scenario_id = _hypothetical(repository)
    session = _session(repository, scenario_id)
    assert session.schedule is not None
    repository.save_equipment(
        _request(
            session,
            scenario_id,
            equipment=_moved(session, x=85.0),
            floor_marks={FLOOR: [_mark("MK-FAR", x=90.0).editor_payload()]},
            floor_layout_bases={
                FLOOR: _floor_base(repository, session.schedule.schedule_revision_id)
            },
        )
    )

    extent = repository.layout_overlay_extent(*FLOOR)

    assert extent.marks == (("셋업 실무", 92.0, 3.0),)
    assert extent.mark_extent() == (92.0, 3.0)
    assert extent.marks_outside((80.0, 60.0)) == ("셋업 실무",)
    assert extent.marks_outside((100.0, 60.0)) == ()
    assert extent.units_outside((90.0, 60.0)) == (("셋업 실무", 1),)
    assert extent.units_outside((100.0, 60.0)) == ()
    assert (
        repository.layout_overlay_extent("C2", "3F") == equipment_repository.LayoutOverlayExtent()
    )


def test_the_scenario_list_counts_the_latest_stored_marks_and_labels(tmp_path: Path) -> None:
    """시나리오 표 「저장된 배치 차이」 재료 — 최신의 저장된 호기·요소·이름표 행 수(원시)."""
    repository = _seeded(tmp_path)
    scenario_id = _hypothetical(repository)
    session = _session(repository, scenario_id)
    assert session.schedule is not None
    repository.save_equipment(
        _request(
            session,
            scenario_id,
            floor_marks={FLOOR: [_mark("MK-NEW", x=5.0).editor_payload()]},
            floor_layout_bases={
                FLOOR: _floor_base(repository, session.schedule.schedule_revision_id)
            },
        )
    )

    summary = _scenario(repository, scenario_id)

    assert summary.latest_layout_rows == (0, 1, 0)
    assert _scenario(repository, OPERATIONS).latest_layout_rows == (0, 0, 0)


# ── E7 되돌리기·여기서 새 시나리오 ────────────────────────────────────────────────────


def test_restoring_a_revision_brings_its_layout_difference_back(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    scenario_id = _hypothetical(repository)
    session = _session(repository, scenario_id)
    saved = repository.save_equipment(_request(session, scenario_id, equipment=_moved(session)))
    assert saved.schedule is not None
    cleared = repository.clear_layout_overlay(
        scenario_id, expected_latest_schedule_revision_id=saved.schedule.schedule_revision_id
    )
    assert cleared is not None
    common = repository.latest_revision_id()
    assert common is not None

    preview = repository.preview_schedule_restore(
        saved.schedule.schedule_revision_id,
        common_revision_id=common,
        current_schedule_revision_id=cleared.schedule_revision_id,
    )
    assert preview.changed_units == 0 and not preview.identical
    assert not restore_writes_nothing(preview, official_scenario=False)
    assert (preview.layout_unit_rows, preview.current_layout_unit_rows) == (1, 0)
    assert preview.current_layout_digest is None

    with pytest.raises(EquipmentLayoutRoleChanged):
        repository.restore_schedule_revision(
            saved.schedule.schedule_revision_id,
            expected_common_revision_id=common,
            expected_latest_schedule_revision_id=cleared.schedule_revision_id,
            expected_layout_role="official",
        )
    restored = repository.restore_schedule_revision(
        saved.schedule.schedule_revision_id,
        expected_common_revision_id=common,
        expected_latest_schedule_revision_id=cleared.schedule_revision_id,
        expected_layout_role="overlay",
    )

    assert restored.schedule is not None and restored.schedule.layout_unit_count == 1
    assert _place(_session(repository, scenario_id), "EQ-01")[2] == 50.0


def test_restoring_into_the_official_scenario_drops_the_layout_difference(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    scenario_id = _hypothetical(repository)
    session = _session(repository, scenario_id)
    saved = repository.save_equipment(_request(session, scenario_id, equipment=_moved(session)))
    assert saved.schedule is not None
    cleared = repository.clear_layout_overlay(
        scenario_id, expected_latest_schedule_revision_id=saved.schedule.schedule_revision_id
    )
    assert cleared is not None
    release = repository.latest_equipment_release()
    assert release is not None
    repository.publish_equipment_release(
        cleared.schedule_revision_id,
        released_by=None,
        note=None,
        expected_latest_release_no=release.release_no,
    )
    common = repository.latest_revision_id()
    assert common is not None

    preview = repository.preview_schedule_restore(
        saved.schedule.schedule_revision_id,
        common_revision_id=common,
        current_schedule_revision_id=cleared.schedule_revision_id,
    )
    # 확인 화면은 저장소와 같은 판정으로 단추를 세우지 않는다(원시 지문은 달라도 — S2 리뷰).
    assert not preview.identical
    assert restore_writes_nothing(preview, official_scenario=True)

    result = repository.restore_schedule_revision(
        saved.schedule.schedule_revision_id,
        expected_common_revision_id=common,
        expected_latest_schedule_revision_id=cleared.schedule_revision_id,
        expected_layout_role="official",
    )

    # 일정은 같고 배치 차이는 공식이라 버려진다 — 되돌릴 것이 없다.
    assert result.schedule is None
    assert _layout_rows(repository)[0] == 1


def test_cloning_from_a_revision_carries_its_normalized_layout_difference(
    tmp_path: Path,
) -> None:
    repository = _seeded(tmp_path)
    scenario_id = _hypothetical(repository)
    session = _session(repository, scenario_id)
    moved = _set(_moved(session), "EQ-02", "X좌표", 70.0)
    saved = repository.save_equipment(_request(session, scenario_id, equipment=moved))
    assert saved.schedule is not None
    official = _session(repository)
    repository.save_equipment(_request(official, equipment=_moved(official, "EQ-02", 70.0)))

    clone = repository.clone_equipment_scenario(
        saved.schedule.schedule_revision_id, name="배치안 2", created_by=None
    )

    branch = _session(repository, clone.equipment_scenario_id)
    assert branch.schedule is not None and branch.schedule.layout_unit_count == 1
    assert _place(branch, "EQ-01")[2] == 50.0 and _place(branch, "EQ-02")[2] == 70.0


# ── 이름 바꾸기·흔적·불변식 ──────────────────────────────────────────────────────────


def test_a_renamed_unit_keeps_its_layout_difference(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    scenario_id = _hypothetical(repository)
    session = _session(repository, scenario_id)
    repository.save_equipment(_request(session, scenario_id, equipment=_moved(session)))
    official = _session(repository)
    renamed = _set(official.equipment, "EQ-01", "설비명", "EQ-11")
    downtime = official.downtime.replace({"설비명": {"EQ-01": "EQ-11"}})

    repository.save_equipment(
        _request(official, equipment=renamed, downtime=downtime, renames={"EQ-11": "EQ-01"})
    )

    assert _place(_session(repository, scenario_id), "EQ-11")[2] == 50.0


def test_an_old_code_revision_after_a_difference_counts_as_a_trace(tmp_path: Path) -> None:
    """검토 F8 — 0031 을 모르는 코드가 저장하면 지문이 NULL 이다. 차이가 있던 리비전 뒤의 NULL 을
    센다(저장은 막지 않는다)."""
    repository = _seeded(tmp_path)
    scenario_id = _hypothetical(repository)
    session = _session(repository, scenario_id)
    repository.save_equipment(_request(session, scenario_id, equipment=_moved(session)))
    assert _scenario(repository, scenario_id).layout_trace_count == 0
    with duckdb.connect(str(repository.database_path)) as connection:
        connection.execute(
            "INSERT INTO equipment_ops.equipment_schedule_revision (schedule_revision_id, "
            "equipment_scenario_id, revision_no, origin) VALUES ('old-code', ?, 9, 'save')",
            [scenario_id],
        )

    summary = _scenario(repository, scenario_id)
    assert summary.layout_trace_count == 1
    assert summary.latest_layout_hash is None and summary.latest_layout_unit_count == 0
    assert _scenario(repository, OPERATIONS).layout_trace_count == 0


def test_the_store_never_updates_the_layout_tables() -> None:
    """I1 — 배치 차이 세 표는 넣기만 한다(합친 본문 캐시가 쌍 키를 믿는 근거)."""
    source = inspect.getsource(equipment_scenario_store)
    assert not re.search(r"UPDATE\s+equipment_ops\.equipment_schedule_layout", source)
    assert not re.search(r"DELETE\s+FROM\s+equipment_ops\.equipment_schedule_layout", source)


def test_schedule_inserts_must_name_their_layout() -> None:
    """검토 F17 — `_insert_schedule` 의 `layout` 은 기본값 없는 키워드다."""
    parameter = inspect.signature(equipment_repository._insert_schedule).parameters["layout"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty
    store = inspect.signature(equipment_scenario_store.insert_schedule_revision).parameters
    assert store["layout"].default is inspect.Parameter.empty


def test_every_table_owned_by_a_schedule_revision_is_listed(tmp_path: Path) -> None:
    repository = DuckDBEquipmentRepository(tmp_path / "equipment.duckdb")
    repository.initialize()
    with duckdb.connect(str(repository.database_path), read_only=True) as connection:
        owned = {
            str(row[0])
            for row in connection.execute(
                "SELECT table_name FROM information_schema.columns "
                "WHERE table_schema = 'equipment_ops' AND column_name = 'schedule_revision_id'"
            ).fetchall()
        }
    # 머리 표와 발행 행(가리키기만 하는 쪽)은 소유 표가 아니다.
    assert owned - {"equipment_schedule_revision", "equipment_official_release"} == set(
        equipment_scenario_store.SCHEDULE_REVISION_OWNED_TABLES
    )


def test_reading_an_empty_or_legacy_revision_runs_no_layout_query(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    session = _session(repository)
    assert session.schedule is not None and session.schedule.layout_hash == EMPTY_LAYOUT_DIGEST

    class Exploding:
        def execute(self, *_: object, **__: object) -> None:
            raise AssertionError("빈 차이를 읽으려 질의했다")

    assert not read_layout_overlay(Exploding(), session.schedule)  # type: ignore[arg-type]
    assert not read_layout_overlay(Exploding(), None)  # type: ignore[arg-type]
