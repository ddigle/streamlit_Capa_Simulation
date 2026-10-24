# Purpose: 설비 시나리오 저장소의 저장·대조·함께 넣기·교차 검증·발행·복제·이름·이어 쓰기를 검증한다.

"""`DuckDBEquipmentRepository` 의 설비 시나리오 쓰기.

설비 마스터는 공통 호기 대장(번호 전역)과 설비 시나리오 일정(시나리오마다 r1 부터)으로 나뉜다.
화면의 저장 한 번(`save_equipment`)은 바뀐 쪽만 쓰고, 새 호기·새 비가동은 다른 시나리오에 함께
넣으며, 공통을 쓰면 모든 시나리오의 최신과 공식 발행을 지키는지 메모리에서 본 뒤 쓴다. 호환 래퍼
(`save_snapshot`·`save_space_layout`·`load_snapshot`)는 늘 두 쪽을 함께 써 공식으로 발행한다.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from test_equipment_availability import _baseline, _downtime, _equipment
from test_equipment_migration_0027_scenarios import _database_before, build_legacy_database

from capa_simulation.persistence import equipment_scenario_store, sync_state
from capa_simulation.persistence.equipment_repository import (
    EMPTY_REVISION_TOKEN,
    DuckDBEquipmentRepository,
    EquipmentLegacyTraceError,
    EquipmentLegacyTraceUnmergeable,
    EquipmentReleaseMoved,
    EquipmentRevisionConflict,
    EquipmentSaveRequest,
    EquipmentSaveResult,
    EquipmentScenarioGuardError,
    EquipmentScenarioIncompatible,
    EquipmentScenarioNameMoved,
    EquipmentScenarioSummary,
    EquipmentSnapshot,
    LegacyTraceReview,
    PropagatedRevision,
    _read_legacy_snapshot,
)
from capa_simulation.services.equipment_scenario import legacy_unit_key

OPERATIONS = "operations"


def _repository(tmp_path: Path) -> DuckDBEquipmentRepository:
    repository = DuckDBEquipmentRepository(tmp_path / "equipment.duckdb")
    repository.initialize()
    return repository


def _seeded(tmp_path: Path, equipment: pd.DataFrame | None = None) -> DuckDBEquipmentRepository:
    """빈 DB 에 래퍼로 한 번 저장 — 공통 r1 · 「운영 일정」 r1 · 공식 v1."""
    repository = _repository(tmp_path)
    repository.save_snapshot(
        _baseline(), _equipment() if equipment is None else equipment, _downtime(), note="처음"
    )
    return repository


def _migrated(tmp_path: Path) -> DuckDBEquipmentRepository:
    """옛 판이 남긴 v2·v3 리비전 셋(r1~r3)에 0027 을 건 DB — 공식 v1 = 「운영 일정」 r3."""
    path = tmp_path / "legacy.duckdb"
    build_legacy_database(path)
    repository = DuckDBEquipmentRepository(path)
    repository.initialize()
    return repository


def _scenario(repository: DuckDBEquipmentRepository, scenario_id: str) -> EquipmentScenarioSummary:
    return next(
        item
        for item in repository.list_equipment_scenarios()
        if item.equipment_scenario_id == scenario_id
    )


def _session(
    repository: DuckDBEquipmentRepository,
    scenario_id: str = OPERATIONS,
    schedule_revision_id: str | None = None,
) -> EquipmentSnapshot:
    """화면 세션이 드는 한 벌 — 공통 최신 + 그 시나리오의 일정 리비전(주지 않으면 최신)."""
    common = repository.latest_revision_id()
    assert common is not None
    if schedule_revision_id is None:
        schedule_revision_id = _scenario(repository, scenario_id).latest_schedule_revision_id
    return repository.load_merged_snapshot(common, schedule_revision_id)


def _request(
    session: EquipmentSnapshot,
    scenario_id: str = OPERATIONS,
    *,
    equipment: pd.DataFrame | None = None,
    downtime: pd.DataFrame | None = None,
    **options: Any,
) -> EquipmentSaveRequest:
    return EquipmentSaveRequest(
        baseline=session.baseline,
        equipment=session.equipment.copy() if equipment is None else equipment,
        downtime=session.downtime.copy() if downtime is None else downtime,
        equipment_scenario_id=scenario_id,
        base_common_revision_id=session.revision.revision_id,
        base_schedule_revision_id=(
            session.schedule.schedule_revision_id if session.schedule is not None else None
        ),
        **options,
    )


def _clone(
    repository: DuckDBEquipmentRepository, name: str = "셋업 실무"
) -> EquipmentScenarioSummary:
    """공식 발행 리비전에서 복제한 새 시나리오."""
    release = repository.latest_equipment_release()
    assert release is not None
    return repository.clone_equipment_scenario(
        release.schedule_revision_id, name=name, created_by="홍길동"
    )


def _set(frame: pd.DataFrame, name: str, column: str, value: Any) -> pd.DataFrame:
    """한 호기의 한 칸을 바꾼 사본. 날짜 칸에 글자를 주면 날짜로 바꿔 넣는다(칸 형을 흔들지
    않게)."""
    result = frame.copy()
    if isinstance(value, str) and pd.api.types.is_datetime64_any_dtype(result[column]):
        value = pd.Timestamp(value)
    result.loc[result["설비명"].eq(name), column] = value
    return result


def _value(snapshot: EquipmentSnapshot, name: str, column: str) -> Any:
    return snapshot.equipment.set_index("설비명").loc[name, column]


def _with_unit(equipment: pd.DataFrame, name: str, x: float, **values: Any) -> pd.DataFrame:
    """첫 호기를 본뜬 새 호기 한 줄을 더한다(자리는 겹치지 않게 X 만 옮긴다)."""
    records = equipment.to_dict("records")
    row = dict(records[0])
    row.update({"설비명": name, "X좌표": x})
    row.update(values)
    records.append(row)
    return pd.DataFrame(records, columns=equipment.columns)


def _with_downtime(
    downtime: pd.DataFrame, name: str, kind: str, start: str, *, end: str | None = None
) -> pd.DataFrame:
    records = downtime.to_dict("records")
    records.append(
        {
            "설비명": name,
            "비가동유형": kind,
            "시작일": pd.Timestamp(start),
            "종료일": pd.Timestamp(end) if end else pd.NaT,
            "상세사유": None,
            "비고": None,
        }
    )
    return pd.DataFrame(records, columns=downtime.columns)


def _counts(repository: DuckDBEquipmentRepository) -> tuple[int, int, int]:
    """(공통 리비전 수, 일정 리비전 수, 공식 발행 수)."""
    with duckdb.connect(str(repository.database_path), read_only=True) as connection:
        row = connection.execute(
            """
            SELECT (SELECT COUNT(*) FROM equipment_ops.revision),
                   (SELECT COUNT(*) FROM equipment_ops.equipment_schedule_revision),
                   (SELECT COUNT(*) FROM equipment_ops.equipment_official_release)
            """
        ).fetchone()
    assert row is not None
    return int(row[0]), int(row[1]), int(row[2])


@pytest.fixture
def marked(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[Path]]:
    """동기화 dirty 표시를 받아 적는다 — 아무것도 안 쓴 저장은 표시하지 않아야 한다."""
    calls: list[Path] = []
    monkeypatch.setattr(sync_state, "mark_dirty", calls.append)
    yield calls


# ── 호환 래퍼 ─────────────────────────────────────────────────────────────────────────


def test_the_wrapper_raises_common_and_operations_numbers_together_and_publishes(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)

    first = repository.save_snapshot(_baseline(), _equipment(), _downtime(), note="최초 저장")
    changed = _set(_equipment(), "EQ-02", "Qual일정", "2026-08-22")
    second = repository.save_snapshot(_baseline(), changed, _downtime(), note="일정 변경")

    assert first.schedule is not None and second.schedule is not None
    assert (first.revision.revision_no, first.schedule.revision_no) == (1, 1)
    assert (second.revision.revision_no, second.schedule.revision_no) == (2, 2)
    assert second.schedule.equipment_scenario_id == OPERATIONS
    assert second.schedule.common_revision_id == second.revision.revision_id
    release = repository.latest_equipment_release()
    assert release is not None
    assert (release.release_no, release.schedule_revision_id) == (
        2,
        second.schedule.schedule_revision_id,
    )
    assert _value(repository.load_snapshot(first.revision.revision_id), "EQ-02", "Qual일정") == (
        pd.Timestamp("2026-08-21")
    )
    assert [item.revision_no for item in repository.list_revisions()] == [2, 1]
    common = repository.list_revisions()[0]
    assert (common.equipment_row_count, common.downtime_row_count) == (2, 0)
    schedule = repository.list_schedule_revisions(OPERATIONS)[0]
    assert (schedule.unit_row_count, schedule.downtime_row_count) == (2, 1)


def test_a_wrapper_layout_save_without_changes_writes_no_revision(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    session = _session(repository)

    saved = repository.save_space_layout(session.baseline, session.equipment, session.downtime)

    assert saved is None
    assert _counts(repository) == (1, 1, 1)


def test_a_saved_common_is_contract_v4_without_schedule_cells_or_downtime_rows(
    tmp_path: Path,
) -> None:
    repository = _seeded(tmp_path)
    session = _session(repository)

    result = repository.save_equipment(
        _request(
            session,
            equipment=_set(session.equipment, "EQ-01", "담당자", "담당B"),
            saved_by="홍길동",
        )
    )

    assert result.common is not None
    assert (result.common.saved_by, result.common.downtime_row_count) == ("홍길동", 0)
    with duckdb.connect(str(repository.database_path)) as connection:
        version, dated, keyed, events = connection.execute(
            """
            SELECT r.equipment_contract_version,
                   (SELECT COUNT(*) FROM equipment_ops.equipment_master_snapshot e
                    WHERE e.revision_id = r.revision_id
                      AND (e.arrival_date IS NOT NULL OR e.qual_date IS NOT NULL
                           OR e.vibration_table_date IS NOT NULL)),
                   (SELECT COUNT(*) FROM equipment_ops.equipment_master_snapshot e
                    WHERE e.revision_id = r.revision_id AND e.unit_key IS NOT NULL),
                   (SELECT COUNT(*) FROM equipment_ops.downtime_schedule_snapshot d
                    WHERE d.revision_id = r.revision_id)
            FROM equipment_ops.revision r WHERE r.revision_id = ?
            """,
            [result.common.revision_id],
        ).fetchone() or (None, None, None, None)
        with pytest.raises(ValueError, match="옛 길로 읽지 않습니다"):
            _read_legacy_snapshot(connection, result.common.revision_id)

    assert (version, dated, keyed, events) == (4, 0, 2, 0)


# ── 바뀐 쪽만 ───────────────────────────────────────────────────────────────────────


def test_a_schedule_only_save_writes_only_a_scenario_revision(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    session = _session(repository)

    result = repository.save_equipment(
        _request(session, equipment=_set(session.equipment, "EQ-02", "Qual일정", "2026-08-25"))
    )

    assert result.common is None and not result.forced_common
    assert result.schedule is not None and result.schedule.revision_no == 2
    assert result.schedule.origin == "save"
    assert result.schedule.common_revision_id == session.revision.revision_id
    assert _counts(repository) == (1, 2, 2)
    official = repository.load_official_snapshot()
    assert official is not None
    assert (
        official.token == f"{session.revision.revision_id}|{result.schedule.schedule_revision_id}"
    )
    assert _value(official, "EQ-02", "Qual일정") == pd.Timestamp("2026-08-25")


def test_a_common_only_save_writes_only_a_common_revision_and_never_publishes(
    tmp_path: Path,
) -> None:
    repository = _seeded(tmp_path)
    session = _session(repository)

    result = repository.save_equipment(
        _request(session, equipment=_set(session.equipment, "EQ-01", "담당자", "담당B"))
    )

    assert result.schedule is None and result.release_no is None
    assert result.common is not None and result.common.revision_no == 2
    assert _counts(repository) == (2, 1, 1)
    official = repository.load_official_snapshot()
    assert official is not None and session.schedule is not None
    assert official.token == f"{result.common.revision_id}|{session.schedule.schedule_revision_id}"
    assert _value(official, "EQ-01", "담당자") == "담당B"
    assert _value(official, "EQ-02", "Qual일정") == pd.Timestamp("2026-08-21")
    # 이력 「그때 그대로」 는 그 일정 리비전이 함께 본 공통이다.
    assert _value(
        repository.load_saved_pair(session.schedule.schedule_revision_id), "EQ-01", "담당자"
    ) == ("담당A")


def test_a_save_that_changes_both_sides_writes_both(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    session = _session(repository)
    edited = _set(
        _set(session.equipment, "EQ-01", "담당자", "담당B"), "EQ-02", "시나리오 메모", "앞당김"
    )

    result = repository.save_equipment(_request(session, equipment=edited, note="  둘 다  "))

    assert result.common is not None and result.schedule is not None
    assert (result.common.note, result.schedule.note) == ("둘 다", "둘 다")
    assert result.schedule.common_revision_id == result.common.revision_id
    assert result.release_no == 2
    official = repository.load_official_snapshot()
    assert official is not None
    assert _value(official, "EQ-02", "시나리오 메모") == "앞당김"


def test_an_unchanged_save_writes_nothing_and_does_not_mark_the_database_dirty(
    tmp_path: Path, marked: list[Path]
) -> None:
    repository = _seeded(tmp_path)
    marked.clear()
    session = _session(repository)

    result = repository.save_equipment(_request(session))

    assert result == EquipmentSaveResult(common=None, schedule=None)
    assert not result.wrote_revision
    assert marked == []
    assert _counts(repository) == (1, 1, 1)


def test_floor_values_alone_write_no_revision(tmp_path: Path, marked: list[Path]) -> None:
    repository = _seeded(tmp_path)
    marked.clear()
    session = _session(repository)

    result = repository.save_equipment(
        _request(session, floor_canvases={("C1", "1F"): (120.0, 80.0)})
    )

    assert result.floor_values_written and not result.wrote_revision
    assert repository.load_floor_layout_canvases()[("C1", "1F")] == (120.0, 80.0)
    assert _counts(repository) == (1, 1, 1)
    assert marked == [repository.database_path]


def test_the_first_schedule_save_after_0027_also_writes_a_v4_common(tmp_path: Path) -> None:
    """공통 최신이 계약 v3(이관 리비전)인 동안의 첫 저장은 일정만 바꿔도 v4 공통 한 벌을 쓴다 —
    옛 ZIP 으로 되돌렸을 때 옛 판이 이관 직전 일정을 조용히 보이지 않고 빈 설비로 드러나게."""
    repository = _migrated(tmp_path)
    session = _session(repository)

    first = repository.save_equipment(
        _request(session, equipment=_set(session.equipment, "EQ-02", "Qual일정", "2026-08-30"))
    )
    second_session = _session(repository)
    second = repository.save_equipment(
        _request(
            second_session,
            equipment=_set(second_session.equipment, "EQ-02", "Qual일정", "2026-08-31"),
        )
    )

    assert first.forced_common
    assert first.common is not None and first.schedule is not None
    assert (first.common.revision_no, first.schedule.revision_no) == (4, 4)
    assert not second.forced_common and second.common is None
    official = repository.load_official_snapshot()
    assert official is not None
    assert _value(official, "EQ-02", "Qual일정") == pd.Timestamp("2026-08-31")
    unchanged = official.equipment.drop(columns=["Qual일정"])
    assert_frame_equal(unchanged, session.equipment.drop(columns=["Qual일정"]))
    assert official.unit_keys["설비01"] == legacy_unit_key("설비01")


def test_a_failing_insert_rolls_back_every_revision_of_the_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _seeded(tmp_path)
    _clone(repository)
    before = _counts(repository)
    session = _session(repository)
    original = equipment_scenario_store.insert_schedule_revision
    origins: list[str] = []

    def failing(connection: duckdb.DuckDBPyConnection, **kwargs: Any) -> str:
        origins.append(str(kwargs["origin"]))
        if kwargs["origin"] == "propagate":
            raise RuntimeError("함께 넣기 실패")
        return original(connection, **kwargs)

    monkeypatch.setattr(equipment_scenario_store, "insert_schedule_revision", failing)
    with pytest.raises(RuntimeError, match="함께 넣기 실패"):
        repository.save_equipment(
            _request(session, equipment=_with_unit(session.equipment, "EQ-03", 50.0))
        )

    assert origins == ["save", "propagate"]
    assert _counts(repository) == before


# ── 대조 ───────────────────────────────────────────────────────────────────────────


def test_a_stale_common_base_is_refused(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    session = _session(repository)
    repository.save_equipment(
        _request(session, equipment=_set(session.equipment, "EQ-01", "담당자", "담당B"))
    )

    with pytest.raises(EquipmentRevisionConflict, match="공통 대장 r2") as caught:
        repository.save_equipment(
            _request(session, equipment=_set(session.equipment, "EQ-01", "담당자", "담당C"))
        )

    assert caught.value.side == "common"
    assert _counts(repository) == (2, 1, 1)


def test_a_stale_session_cannot_save_its_schedule_but_its_common_save_keeps_the_latest(
    tmp_path: Path,
) -> None:
    """rJ 를 보는 세션 — 일정을 고치면 거부, 공통만 고치면 통과하고 같은 시나리오 최신 rM 이 그대로
    열린다."""
    repository = _seeded(tmp_path)
    stale = _session(repository)
    fresh = _session(repository)
    newer = repository.save_equipment(
        _request(fresh, equipment=_set(fresh.equipment, "EQ-02", "Qual일정", "2026-08-25"))
    )
    assert newer.schedule is not None

    with pytest.raises(EquipmentRevisionConflict, match="「운영 일정」 r2") as caught:
        repository.save_equipment(
            _request(stale, equipment=_set(stale.equipment, "EQ-01", "Qual일정", "2026-08-12"))
        )
    common_only = repository.save_equipment(
        _request(stale, equipment=_set(stale.equipment, "EQ-01", "담당자", "담당B"))
    )

    assert caught.value.side == "schedule"
    assert common_only.common is not None and common_only.schedule is None
    latest = _session(repository)
    assert latest.schedule is not None
    assert latest.schedule.schedule_revision_id == newer.schedule.schedule_revision_id
    assert _value(latest, "EQ-02", "Qual일정") == pd.Timestamp("2026-08-25")
    assert _value(latest, "EQ-01", "담당자") == "담당B"


def test_a_legacy_trace_blocks_every_equipment_save_until_it_is_acknowledged(
    tmp_path: Path,
) -> None:
    """옛 판이 0027 뒤에 저장한 계약 v3 공통(경계 뒤) — 설비 저장을 모두 막는다. 이어 쓰기 뒤에는
    된다. 새 판에서 만든 호기(uuid 키)는 그 공통에서 옛 키로 읽혀 일정 없음이 된다."""
    repository = _seeded(tmp_path)
    with duckdb.connect(str(repository.database_path)) as connection:
        connection.execute(
            """
            INSERT INTO equipment_ops.revision (
                revision_id, revision_no, note, baseline_hash, schedule_hash,
                equipment_hash, downtime_hash, equipment_contract_version
            ) VALUES ('old', 2, '옛 판', 'b', 's', 'e', 'd', 3)
            """
        )
        connection.execute(
            """
            INSERT INTO equipment_ops.equipment_master_snapshot (
                revision_id, source_row_no, equipment_id, process_small,
                long_term_storage_flag, existing_equipment_flag, layout_display_flag
            ) VALUES ('old', 1, 'EQ-01', 'Process-A', 'N', 'N', 'N')
            """
        )
    session = _session(repository)
    # 확인 재료 — 새 판에서 만든 두 호기(uuid 키)는 옛 배포 리비전에 없어 이어 쓰면 빠진다. 합쳐는
    # 진다(옛 키 EQ-01 은 일정 없음이 될 뿐).
    assert repository.legacy_trace_review() == LegacyTraceReview(
        count=1, trace_revision_no=2, dropped_units=2, refusal=None
    )

    with pytest.raises(EquipmentLegacyTraceError, match="1개") as caught:
        repository.save_equipment(
            _request(session, equipment=_set(session.equipment, "EQ-01", "담당자", "담당B"))
        )
    with pytest.raises(EquipmentLegacyTraceError):
        repository.save_snapshot(_baseline(), _equipment(), _downtime())
    with pytest.raises(ValueError, match="흔적 수가 바뀌었습니다"):
        repository.acknowledge_legacy_trace(expected_trace_count=2, note=None)
    boundary = repository.acknowledge_legacy_trace(expected_trace_count=1, note=None)
    session = _session(repository)
    saved = repository.save_equipment(
        _request(session, equipment=_set(session.equipment, "EQ-01", "반입일정", "2026-08-04"))
    )

    assert caught.value.count == 1
    assert boundary == 2 and repository.legacy_trace_count() == 0
    assert session.unscheduled_units == frozenset({"EQ-01"})
    assert repository.legacy_trace_review() == LegacyTraceReview()
    assert saved.schedule is not None
    assert repository.acknowledge_legacy_trace(expected_trace_count=0, note=None) == 2


def _add_unmergeable_trace(repository: DuckDBEquipmentRepository) -> None:
    """0027 뒤 옛 판이 저장한 계약 v3 r4 — 「설비01」 의 Qual일정·Qual상태를 비웠다(옛 판에서는 맞는
    값). 공통으로 읽으면 Qual상태가 비고, 「운영 일정」 r3(옛 r3)의 Qual일정과 합치면 검증에
    막힌다."""
    from test_equipment_migration_0027_scenarios import (
        _MASTER_COLUMNS,
        _insert_revision,
        _master_row,
    )

    with duckdb.connect(str(repository.database_path)) as connection:
        _insert_revision(
            connection, "r4", 4, contract=3, note="옛 배포", created_at="2026-10-24 09:00:00"
        )
        placeholders = ", ".join("?" for _ in _MASTER_COLUMNS)
        connection.execute(
            f"INSERT INTO equipment_ops.equipment_master_snapshot ({', '.join(_MASTER_COLUMNS)}) "
            f"VALUES ({placeholders})",
            list(_master_row("r4", 1, "설비01", qual=None, status=None)),
        )


def test_an_unmergeable_legacy_trace_cannot_be_continued_and_the_review_says_why(
    tmp_path: Path,
) -> None:
    """옛 배포 리비전이 공식 일정과 합쳐지지 않으면 이어 쓰기를 쓰지 않고 거절한다 — 이어 쓰면 그
    리비전이 공통 최신으로 굳어 공식을 다시 읽을 수 없다. 확인 재료가 그 까닭과 빠지는 호기 수(옛
    배포 리비전에 없는 셋)를 말한다."""
    repository = _migrated(tmp_path)
    _add_unmergeable_trace(repository)

    review = repository.legacy_trace_review()
    with pytest.raises(EquipmentLegacyTraceUnmergeable, match="백업을 복원하세요") as caught:
        repository.acknowledge_legacy_trace(expected_trace_count=1, note=None)

    assert (review.count, review.trace_revision_no, review.dropped_units) == (1, 4, 3)
    assert review.refusal is not None and "「운영 일정」 r3 일정과 합치면" in review.refusal
    assert "Qual상태" in review.refusal and "Qual상태" in str(caught.value)
    assert repository.legacy_trace_count() == 1
    with pytest.raises(EquipmentScenarioIncompatible):
        repository.load_official_snapshot()


# ── 번호 ───────────────────────────────────────────────────────────────────────────


def test_common_numbers_are_global_and_each_scenario_counts_from_r1(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    setup = _clone(repository)
    session = _session(repository, setup.equipment_scenario_id)

    common = repository.save_equipment(
        _request(
            session,
            setup.equipment_scenario_id,
            equipment=_set(session.equipment, "EQ-01", "담당자", "담당B"),
        )
    )
    session = _session(repository, setup.equipment_scenario_id)
    schedule = repository.save_equipment(
        _request(
            session,
            setup.equipment_scenario_id,
            equipment=_set(session.equipment, "EQ-02", "Qual일정", "2026-08-27"),
        )
    )

    assert (setup.latest_revision_no, setup.revision_count) == (1, 1)
    assert common.common is not None and common.common.revision_no == 2
    assert schedule.schedule is not None and schedule.schedule.revision_no == 2
    assert _scenario(repository, OPERATIONS).latest_revision_no == 1
    assert schedule.release_no is None


# ── 함께 넣기 ─────────────────────────────────────────────────────────────────────────


def test_a_new_unit_is_put_into_other_scenarios_with_the_same_schedule_by_default(
    tmp_path: Path,
) -> None:
    repository = _seeded(tmp_path)
    setup = _clone(repository)
    session = _session(repository)
    edited = _with_unit(
        session.equipment, "EQ-03", 50.0, 반입일정=pd.Timestamp("2026-09-02"), Qual일정=pd.NaT
    )
    downtime = _with_downtime(session.downtime, "EQ-03", "공사", "2026-09-05")

    result = repository.save_equipment(
        _request(session, equipment=edited, downtime=downtime, saved_by="홍길동")
    )

    assert result.new_units == ("EQ-03",) and result.removed_units == ()
    assert result.propagated == (
        PropagatedRevision(setup.equipment_scenario_id, "셋업 실무", 2, 1, (), 0),
    )
    revision = repository.list_schedule_revisions(setup.equipment_scenario_id)[0]
    assert (revision.origin, revision.saved_by) == ("propagate", "홍길동")
    assert revision.note == "「운영 일정」 저장에서 새 호기 1대 함께 넣음"
    other = _session(repository, setup.equipment_scenario_id)
    assert other.unscheduled_units == frozenset()
    assert _value(other, "EQ-03", "반입일정") == pd.Timestamp("2026-09-02")
    assert other.downtime["설비명"].tolist() == ["EQ-01", "EQ-03"]


def test_with_unit_propagation_off_a_new_unit_is_unscheduled_elsewhere(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    setup = _clone(repository)
    session = _session(repository)

    result = repository.save_equipment(
        _request(
            session,
            equipment=_with_unit(session.equipment, "EQ-03", 50.0),
            propagate_new_units=False,
        )
    )
    other = _session(repository, setup.equipment_scenario_id)

    assert result.propagated == ()
    assert other.schedule is not None and other.schedule.revision_no == 1
    assert other.unscheduled_units == frozenset({"EQ-03"})
    assert "EQ-03" not in other.calculation_frames()[1]["설비명"].tolist()
    assert "EQ-03" in other.equipment["설비명"].tolist()


def test_a_new_downtime_spreads_but_a_duplicate_or_an_unscheduled_unit_is_skipped(
    tmp_path: Path,
) -> None:
    repository = _seeded(tmp_path)
    setup = _clone(repository)
    # 셋업 실무에만 EQ-02 공사 09-10 을 먼저 넣는다(함께 넣기 끔).
    other = _session(repository, setup.equipment_scenario_id)
    repository.save_equipment(
        _request(
            other,
            setup.equipment_scenario_id,
            downtime=_with_downtime(other.downtime, "EQ-02", "공사", "2026-09-10"),
            propagate_new_downtime=False,
        )
    )
    # 운영 일정에 EQ-03 을 넣되 셋업 실무에는 넣지 않는다(그 시나리오에서 일정 없음).
    session = _session(repository)
    repository.save_equipment(
        _request(
            session,
            equipment=_with_unit(session.equipment, "EQ-03", 50.0),
            propagate_new_units=False,
        )
    )
    session = _session(repository)
    downtime = _with_downtime(session.downtime, "EQ-02", "공사", "2026-09-10")
    downtime = _with_downtime(downtime, "EQ-03", "공사", "2026-09-12")
    downtime = _with_downtime(downtime, "EQ-02", "점검", "2026-09-20")

    result = repository.save_equipment(_request(session, downtime=downtime))

    assert result.propagated == (
        PropagatedRevision(
            setup.equipment_scenario_id,
            "셋업 실무",
            3,
            0,
            (("EQ-02", "점검", "2026-09-20"),),
            2,
        ),
    )
    other = _session(repository, setup.equipment_scenario_id)
    assert sorted(map(tuple, other.downtime[["설비명", "비가동유형"]].values.tolist())) == [
        ("EQ-01", "고장"),
        ("EQ-02", "공사"),
        ("EQ-02", "점검"),
    ]
    assert repository.list_schedule_revisions(setup.equipment_scenario_id)[0].note == (
        "「운영 일정」 저장에서 비가동 1건 함께 넣음"
    )


def test_a_downtime_whose_start_date_or_type_was_edited_does_not_spread(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    setup = _clone(repository)
    session = _session(repository)
    moved = session.downtime.copy()
    moved.loc[0, "시작일"] = pd.Timestamp("2026-08-12")

    by_start = repository.save_equipment(_request(session, downtime=moved))
    session = _session(repository)
    retyped = session.downtime.copy()
    retyped.loc[0, "비가동유형"] = "점검"
    by_type = repository.save_equipment(_request(session, downtime=retyped))

    assert by_start.schedule is not None and by_type.schedule is not None
    assert by_start.propagated == () and by_type.propagated == ()
    other = _session(repository, setup.equipment_scenario_id)
    assert other.schedule is not None and other.schedule.revision_no == 1
    assert other.downtime["시작일"].tolist() == [pd.Timestamp("2026-08-10")]


@pytest.mark.parametrize("edit", ["type_and_start", "unit_name"])
def test_a_downtime_edited_in_two_cells_or_moved_to_another_unit_does_not_spread(
    tmp_path: Path, edit: str
) -> None:
    """유형과 시작일을 함께 고친 비가동, 비가동 행의 설비명만 옮긴 비가동도 고침이다 — 다른
    시나리오(셋업 실무)는 옛 비가동 하나 그대로이고 고친 행이 겹쳐 더해지지 않는다."""
    repository = _seeded(tmp_path)
    setup = _clone(repository)
    session = _session(repository)
    edited = session.downtime.copy()
    if edit == "type_and_start":
        edited.loc[0, "비가동유형"] = "개조"
        edited.loc[0, "시작일"] = pd.Timestamp("2026-08-12")
    else:
        edited.loc[0, "설비명"] = "EQ-02"

    result = repository.save_equipment(_request(session, downtime=edited))

    assert result.schedule is not None and result.propagated == ()
    other = _session(repository, setup.equipment_scenario_id)
    assert other.schedule is not None and other.schedule.revision_no == 1
    assert list(zip(other.downtime["설비명"], other.downtime["비가동유형"], strict=True)) == [
        ("EQ-01", "고장")
    ]


def test_a_pasted_schedule_cell_on_an_earlier_row_writes_no_common_revision(
    tmp_path: Path,
) -> None:
    """목록 끝이 아닌 호기의 Qual일정만 붙여넣어 저장해도 공통 대장 리비전은 생기지 않는다 —
    붙여넣기 병합(`merge_equipment_rows`)이 바꾼 행을 제자리에 둔다(끝으로 옮기면 행 차례가 공통
    내용이라 공통 rN 이 새로 생기고 다른 세션의 미저장 편집이 버려진다)."""
    from capa_simulation.services.equipment_csv import merge_equipment_rows

    repository = _seeded(tmp_path)
    session = _session(repository)
    assert session.equipment["설비명"].tolist() == ["EQ-01", "EQ-02"]
    pasted = _set(session.equipment, "EQ-01", "Qual일정", "2026-08-14").iloc[[0]]

    merged = merge_equipment_rows(session.equipment, pasted)
    result = repository.save_equipment(_request(session, equipment=merged))

    assert merged["설비명"].tolist() == ["EQ-01", "EQ-02"]
    assert result.common is None
    assert result.schedule is not None and result.schedule.revision_no == 2
    assert _value(_session(repository), "EQ-01", "Qual일정") == pd.Timestamp("2026-08-14")


def test_a_unit_renamed_through_the_name_map_keeps_its_schedule_in_other_scenarios(
    tmp_path: Path,
) -> None:
    repository = _seeded(tmp_path)
    setup = _clone(repository)
    other = _session(repository, setup.equipment_scenario_id)
    repository.save_equipment(
        _request(
            other,
            setup.equipment_scenario_id,
            equipment=_set(other.equipment, "EQ-02", "Qual일정", "2026-08-28"),
        )
    )
    session = _session(repository)
    renamed = session.equipment.replace({"설비명": {"EQ-01": "EQ-01R"}})
    downtime = session.downtime.replace({"설비명": {"EQ-01": "EQ-01R"}})

    result = repository.save_equipment(
        _request(session, equipment=renamed, downtime=downtime, renames={"EQ-01R": "EQ-01"})
    )
    other = _session(repository, setup.equipment_scenario_id)

    assert result.common is not None and result.schedule is None
    assert (result.new_units, result.removed_units) == ((), ())
    assert other.unscheduled_units == frozenset() and other.orphan_rows == 0
    assert _value(other, "EQ-01R", "반입일정") == pd.Timestamp("2026-08-04")
    assert _value(other, "EQ-02", "Qual일정") == pd.Timestamp("2026-08-28")
    assert other.downtime["설비명"].tolist() == ["EQ-01R"]


def test_a_renamed_unit_and_a_new_unit_with_the_old_name_are_two_units(tmp_path: Path) -> None:
    """「A→B 이름 바꿈 + 새 A」 — B 가 A 의 키를 잇고 새 A 는 새 키라 다른 시나리오에서도 둘이다."""
    repository = _seeded(tmp_path)
    setup = _clone(repository)
    session = _session(repository)
    old_key = session.unit_keys["EQ-01"]
    renamed = session.equipment.replace({"설비명": {"EQ-01": "EQ-09"}})
    downtime = session.downtime.replace({"설비명": {"EQ-01": "EQ-09"}})
    edited = _with_unit(renamed, "EQ-01", 50.0, 반입일정=pd.Timestamp("2026-09-15"))
    edited = _set(edited, "EQ-01", "Qual일정", pd.Timestamp("2026-09-20"))

    result = repository.save_equipment(
        _request(session, equipment=edited, downtime=downtime, renames={"EQ-09": "EQ-01"})
    )
    other = _session(repository, setup.equipment_scenario_id)

    assert (result.new_units, result.removed_units) == (("EQ-01",), ())
    assert other.unit_keys["EQ-09"] == old_key != other.unit_keys["EQ-01"]
    assert _value(other, "EQ-09", "반입일정") == pd.Timestamp("2026-08-04")
    assert _value(other, "EQ-01", "반입일정") == pd.Timestamp("2026-09-15")
    assert other.downtime["설비명"].tolist() == ["EQ-09"]


def test_a_rawdata_name_edit_is_a_removed_unit_and_a_new_unit(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    _clone(repository)
    session = _session(repository)

    result = repository.save_equipment(
        _request(session, equipment=session.equipment.replace({"설비명": {"EQ-02": "EQ-02X"}}))
    )

    assert (result.new_units, result.removed_units) == (("EQ-02X",), ("EQ-02",))
    assert [item.unit_count for item in result.propagated] == [1]


# ── 교차 검증 ─────────────────────────────────────────────────────────────────────────


def _without_eq02_qual() -> pd.DataFrame:
    return _set(_equipment(), "EQ-02", "Qual일정", None)


def test_clearing_a_common_cell_another_scenario_needs_is_refused_with_a_way_out(
    tmp_path: Path,
) -> None:
    repository = _seeded(tmp_path, _without_eq02_qual())
    setup = _clone(repository)
    other = _session(repository, setup.equipment_scenario_id)
    repository.save_equipment(
        _request(
            other,
            setup.equipment_scenario_id,
            equipment=_set(other.equipment, "EQ-02", "Qual일정", "2026-08-28"),
        )
    )
    before = _counts(repository)
    session = _session(repository)

    with pytest.raises(EquipmentScenarioGuardError, match="「셋업 실무」 r2") as caught:
        repository.save_equipment(
            _request(session, equipment=_set(session.equipment, "EQ-02", "Qual상태", None))
        )

    assert (caught.value.scenario_name, caught.value.revision_no) == ("셋업 실무", 2)
    assert "Qual상태" in caught.value.reason and "EQ-02" in caught.value.reason
    assert "「셋업 실무」를 불러와" in caught.value.escape
    assert _counts(repository) == before


def test_the_official_release_is_guarded_even_when_it_is_not_the_latest(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    session = _session(repository)
    unpublished = repository.save_equipment(
        _request(
            session,
            equipment=_set(session.equipment, "EQ-02", "Qual일정", None),
            publish_official=False,
        )
    )
    assert unpublished.release_no is None and not unpublished.release_withheld
    session = _session(repository)

    with pytest.raises(EquipmentScenarioGuardError, match="「운영 일정」 r1") as caught:
        repository.save_equipment(
            _request(session, equipment=_set(session.equipment, "EQ-02", "Qual상태", None))
        )

    assert "다른 리비전을 공식으로 발행한 뒤" in caught.value.escape


def test_a_stale_common_save_that_breaks_the_scenario_latest_is_refused(tmp_path: Path) -> None:
    """낡은 세션(r1)이 공통만 고쳐도 자기 시나리오 최신(r2)을 지킨다 — 거부하고 r2 가 그대로
    열린다."""
    repository = _seeded(tmp_path, _without_eq02_qual())
    stale = _session(repository)
    fresh = _session(repository)
    repository.save_equipment(
        _request(fresh, equipment=_set(fresh.equipment, "EQ-02", "Qual일정", "2026-08-21"))
    )

    with pytest.raises(EquipmentScenarioGuardError, match="「운영 일정」 r2") as caught:
        repository.save_equipment(
            _request(stale, equipment=_set(stale.equipment, "EQ-02", "Qual상태", None))
        )

    assert "최신 r2를 불러와" in caught.value.escape
    latest = _session(repository)
    assert latest.schedule is not None and latest.schedule.revision_no == 2
    assert _value(latest, "EQ-02", "Qual상태") == "확정"


# ── 발행 ───────────────────────────────────────────────────────────────────────────


def test_the_first_save_into_an_empty_database_is_official_v1(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    result = repository.save_equipment(
        EquipmentSaveRequest(
            baseline=_baseline(),
            equipment=_equipment(),
            downtime=_downtime(),
            equipment_scenario_id=OPERATIONS,
            base_common_revision_id=EMPTY_REVISION_TOKEN,
            base_schedule_revision_id=None,
        )
    )

    assert result.common is not None and result.schedule is not None
    assert (result.common.revision_no, result.schedule.revision_no, result.release_no) == (1, 1, 1)
    official = repository.load_official_snapshot()
    assert official is not None and official.equipment["설비명"].tolist() == ["EQ-01", "EQ-02"]


def test_the_first_schedule_revision_is_official_v1_even_with_publishing_unchecked(
    tmp_path: Path,
) -> None:
    """발행이 하나도 없으면 「공식으로 발행」 을 꺼도 이 저장의 일정 리비전이 v1 이다. 끄는 것은
    지금 공식을 남긴다는 뜻인데 남길 공식이 없다 — 발행 없는 상태로 두면 세션은 「운영 일정」 r1 을
    공식 자리로 보는데 공식 스냅샷은 일정 없이 호기 0대가 된다."""
    repository = _repository(tmp_path)

    result = repository.save_equipment(
        EquipmentSaveRequest(
            baseline=_baseline(),
            equipment=_equipment(),
            downtime=_downtime(),
            equipment_scenario_id=OPERATIONS,
            base_common_revision_id=EMPTY_REVISION_TOKEN,
            base_schedule_revision_id=None,
            publish_official=False,
        )
    )

    assert result.release_no == 1
    official = repository.load_official_snapshot()
    assert official is not None and official.schedule is not None
    assert official.unscheduled_units == frozenset()
    assert len(official.calculation_frames()[1]) == 2


def test_a_save_does_not_publish_over_an_unpublished_newer_revision(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    session = _session(repository)
    repository.save_equipment(
        _request(
            session,
            equipment=_set(session.equipment, "EQ-02", "Qual일정", "2026-08-24"),
            publish_official=False,
        )
    )
    session = _session(repository)

    result = repository.save_equipment(
        _request(session, equipment=_set(session.equipment, "EQ-02", "Qual일정", "2026-08-26"))
    )

    assert result.schedule is not None and result.schedule.revision_no == 3
    assert result.release_no is None and result.release_withheld
    release = repository.latest_equipment_release()
    assert release is not None and release.release_no == 1


def test_a_propagated_revision_in_the_official_scenario_is_published_by_the_same_rule(
    tmp_path: Path,
) -> None:
    repository = _seeded(tmp_path)
    setup = _clone(repository)
    session = _session(repository, setup.equipment_scenario_id)

    result = repository.save_equipment(
        _request(
            session,
            setup.equipment_scenario_id,
            equipment=_with_unit(session.equipment, "EQ-03", 50.0),
        )
    )

    assert [(item.scenario_name, item.revision_no) for item in result.propagated] == [
        ("운영 일정", 2)
    ]
    assert result.release_no == 2
    release = repository.latest_equipment_release()
    assert release is not None and release.equipment_scenario_id == OPERATIONS
    official = repository.load_official_snapshot()
    assert official is not None and "EQ-03" in official.equipment["설비명"].tolist()


def test_publishing_checks_the_number_it_saw_and_is_append_only(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    session = _session(repository)
    draft = repository.save_equipment(
        _request(
            session,
            equipment=_set(session.equipment, "EQ-02", "Qual일정", "2026-08-24"),
            publish_official=False,
        )
    )
    assert draft.schedule is not None
    revision_id = draft.schedule.schedule_revision_id

    with pytest.raises(EquipmentReleaseMoved, match="v1"):
        repository.publish_equipment_release(
            revision_id, released_by=None, note=None, expected_latest_release_no=None
        )
    published = repository.publish_equipment_release(
        revision_id, released_by="홍길동", note="검토 끝", expected_latest_release_no=1
    )
    again = repository.publish_equipment_release(
        revision_id, released_by=None, note=None, expected_latest_release_no=2
    )
    session = _session(repository)
    with pytest.raises(EquipmentReleaseMoved):
        repository.save_equipment(
            _request(
                session,
                equipment=_set(session.equipment, "EQ-02", "Qual일정", "2026-08-26"),
                expected_release_no=1,
            )
        )

    assert (published.release_no, published.released_by, published.note) == (2, "홍길동", "검토 끝")
    assert again == published
    assert _counts(repository)[2] == 2


def test_only_publishing_changes_what_the_official_snapshot_shows(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    session = _session(repository)
    draft = repository.save_equipment(
        _request(
            session,
            equipment=_set(session.equipment, "EQ-02", "Qual일정", "2026-08-24"),
            publish_official=False,
        )
    )
    assert draft.schedule is not None
    before = repository.load_official_snapshot()

    repository.publish_equipment_release(
        draft.schedule.schedule_revision_id,
        released_by=None,
        note=None,
        expected_latest_release_no=1,
    )
    after = repository.load_official_snapshot()

    assert before is not None and after is not None
    assert before.revision.revision_id == after.revision.revision_id
    assert before.token != after.token
    assert _value(before, "EQ-02", "Qual일정") == pd.Timestamp("2026-08-21")
    assert _value(after, "EQ-02", "Qual일정") == pd.Timestamp("2026-08-24")


def test_a_revision_that_no_longer_merges_cannot_be_published_or_cloned(tmp_path: Path) -> None:
    """옛 r1(Qual일정 있음)은 최신도 공식도 아니어서 교차 검증이 지키지 않는다 — 공통에서 Qual상태를
    비운 뒤로는 발행·복제할 수 없다."""
    repository = _seeded(tmp_path)
    first = _session(repository)
    assert first.schedule is not None
    repository.save_equipment(
        _request(first, equipment=_set(first.equipment, "EQ-02", "Qual일정", None))
    )
    session = _session(repository)
    repository.save_equipment(
        _request(session, equipment=_set(session.equipment, "EQ-02", "Qual상태", None))
    )

    with pytest.raises(EquipmentScenarioIncompatible, match="「운영 일정」 r1"):
        repository.publish_equipment_release(
            first.schedule.schedule_revision_id,
            released_by=None,
            note=None,
            expected_latest_release_no=2,
        )
    with pytest.raises(ValueError, match="최신도 공식 발행도 아니라"):
        repository.clone_equipment_scenario(
            first.schedule.schedule_revision_id, name="옛 복제", created_by=None
        )
    assert _counts(repository)[2] == 2


# ── 복제·이름 ─────────────────────────────────────────────────────────────────────────


def _assert_same_merged(left: EquipmentSnapshot, right: EquipmentSnapshot) -> None:
    """두 합친 스냅샷의 값이 같다. 날짜 칸은 단위(ns·us)만 다를 수 있다 — 계약 v2 변환은 빈 날짜
    칸을 새로 만들고 새 표 읽기는 DB 의 DATE 칸을 읽는다. 칸 형의 갈래(날짜·글자·수)는 같아야
    한다."""
    for ours, theirs in ((left.equipment, right.equipment), (left.downtime, right.downtime)):
        assert [dtype.kind for dtype in ours.dtypes] == [dtype.kind for dtype in theirs.dtypes]
        assert_frame_equal(ours, theirs, check_dtype=False)
    assert left.unscheduled_units == right.unscheduled_units
    assert left.unit_key_pairs == right.unit_key_pairs


def test_a_clone_of_a_legacy_revision_merges_exactly_like_its_source(tmp_path: Path) -> None:
    repository = _migrated(tmp_path)
    source = _session(repository)

    clone = _clone(repository)
    copied = _session(repository, clone.equipment_scenario_id)

    assert (clone.scenario_name, clone.latest_revision_no, clone.revision_count) == (
        "셋업 실무",
        1,
        1,
    )
    _assert_same_merged(copied, source)
    revision = repository.list_schedule_revisions(clone.equipment_scenario_id)[0]
    assert (revision.origin, revision.saved_by, revision.unit_row_count) == ("clone", "홍길동", 4)
    assert revision.note == "「운영 일정」 r3에서 복제"


def test_a_clone_of_a_placeholder_revision_keeps_the_blank_qual_and_unscheduled_units(
    tmp_path: Path,
) -> None:
    """r2 는 Qual 자리표 2262-04-11 을 든 계약 v3 이고 r3 의 두 호기를 모른다. 공식으로 발행한 뒤
    복제하면 복제 r1 이 출처를 지금 공통과 합친 것과 같다 — 자리표는 빈칸, 모르는 호기는 일정
    없음."""
    repository = _migrated(tmp_path)
    repository.publish_equipment_release(
        "legacy-r2", released_by=None, note=None, expected_latest_release_no=1
    )
    source = _session(repository, OPERATIONS, "legacy-r2")

    clone = _clone(repository, "자리표 복제")
    copied = _session(repository, clone.equipment_scenario_id)

    _assert_same_merged(copied, source)
    assert pd.isna(_value(copied, "설비01", "Qual일정"))
    assert copied.unscheduled_units == frozenset({"EQ-OLD", "EQ-OUT"})
    with duckdb.connect(str(repository.database_path), read_only=True) as connection:
        placeholders = connection.execute(
            "SELECT COUNT(*) FROM equipment_ops.equipment_schedule_snapshot "
            "WHERE qual_date = DATE '2262-04-11'"
        ).fetchone()
    assert placeholders == (0,)


def _v2_database(path: Path) -> None:
    """계약 v2 리비전 하나뿐인 옛 DB — 같은 (설비, 유형, 시작일) 비가동이 둘이다."""
    _database_before(path, 25)
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            """
            INSERT INTO equipment_ops.revision (
                revision_id, revision_no, note, baseline_hash, schedule_hash,
                equipment_hash, downtime_hash, equipment_contract_version
            ) VALUES ('v2', 1, '옛 v2', 'b', 's', 'e', 'd', 2)
            """
        )
        connection.execute(
            """
            INSERT INTO equipment_ops.equipment_snapshot (
                revision_id, source_row_no, equipment_id, process_name, classification,
                building, floor_name, x_coordinate, y_coordinate, width_value,
                arrival_date, production_transition_date
            ) VALUES
                ('v2', 1, 'EQ-V2A', 'Process-A', '전체', 'C1', '1F', 10, 10, 12,
                 DATE '2026-08-01', DATE '2026-08-10'),
                ('v2', 2, 'EQ-V2B', 'Process-A', '전체', NULL, NULL, NULL, NULL, NULL,
                 DATE '2026-08-03', NULL)
            """
        )
        connection.execute(
            """
            INSERT INTO equipment_ops.downtime_snapshot (
                revision_id, source_row_no, downtime_id, equipment_id, downtime_type,
                start_date, detail
            ) VALUES
                ('v2', 1, 'D-1', 'EQ-V2A', '고장', DATE '2026-08-11', '앞'),
                ('v2', 2, 'D-2', 'EQ-V2A', '고장', DATE '2026-08-11', '뒤')
            """
        )


def test_a_clone_of_a_contract_v2_revision_keeps_its_conversions(tmp_path: Path) -> None:
    path = tmp_path / "v2.duckdb"
    _v2_database(path)
    repository = DuckDBEquipmentRepository(path)
    repository.initialize()
    source = _session(repository)

    clone = _clone(repository)
    copied = _session(repository, clone.equipment_scenario_id)

    _assert_same_merged(copied, source)
    assert _value(copied, "EQ-V2A", "Qual상태") == "계획"
    assert _value(copied, "EQ-V2A", "Ysize") == 7.0
    assert copied.downtime["상세사유"].tolist() == ["뒤"]


def test_scenario_names_are_required_unique_and_checked_against_what_was_seen(
    tmp_path: Path, marked: list[Path]
) -> None:
    repository = _seeded(tmp_path)
    setup = _clone(repository)

    with pytest.raises(ValueError, match="같은 이름의 설비 시나리오"):
        _clone(repository, "운영 일정")
    with pytest.raises(ValueError, match="이름을 적으세요"):
        _clone(repository, "  ")
    renamed = repository.rename_equipment_scenario(
        setup.equipment_scenario_id, name=" 현장 일정 ", expected_name="셋업 실무"
    )
    with pytest.raises(EquipmentScenarioNameMoved, match="지금: 현장 일정"):
        repository.rename_equipment_scenario(
            setup.equipment_scenario_id, name="다른 이름", expected_name="셋업 실무"
        )
    with pytest.raises(ValueError, match="같은 이름의 설비 시나리오"):
        repository.rename_equipment_scenario(
            setup.equipment_scenario_id, name="운영 일정", expected_name="현장 일정"
        )
    marked.clear()
    same = repository.rename_equipment_scenario(
        setup.equipment_scenario_id, name="현장 일정", expected_name="현장 일정"
    )

    assert renamed.scenario_name == "현장 일정" == same.scenario_name
    assert marked == []
    assert [item.scenario_name for item in repository.list_equipment_scenarios()] == [
        "운영 일정",
        "현장 일정",
    ]
