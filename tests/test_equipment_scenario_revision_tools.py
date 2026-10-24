# Purpose: 설비 시나리오 일정 리비전의 리비전명·되돌리기·여기서 새 시나리오(E7)를 검증한다.

"""E7 — 일정 리비전 도구 셋(2026-10-24 사용자 답 「권장대로」).

- **리비전명** — 이름표만 고친다(비교 후 쓰기, 비우면 지움). 내용은 append-only 그대로이고, 불변
  본문 캐시는 이름을 싣지 않으며 리비전 목록 캐시는 쓰기 세대로 새 이름을 읽는다(AGENTS 5장 8).
- **이 리비전으로 되돌리기** — 고른 리비전의 일정(날짜 여섯·시나리오 메모·비가동)을 지금 공통 대장과
  합쳐 같은 시나리오의 새 리비전으로 다시 저장한다. 공통 대장은 그대로, 그 리비전 뒤에 든 호기는
  일정 없음, 공식 시나리오면 저장과 같은 발행 규칙.
- **여기서 새 시나리오** — 1단계 복제와 같되 출처가 어느 리비전이든 된다.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import pytest
from test_equipment_availability import _downtime, _equipment
from test_equipment_scenario_repository import (
    OPERATIONS,
    _assert_same_merged,
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
    marked,
)

from capa_simulation.persistence import equipment_cache
from capa_simulation.persistence.equipment_cache import (
    clear_equipment_repository,
    clear_equipment_scenario_cache,
    load_equipment_schedule_revisions,
    load_merged_equipment_snapshot,
    load_schedule_restore_preview,
)
from capa_simulation.persistence.equipment_repository import (
    SCHEDULE_REVISION_NAME_MAX_CHARS,
    DuckDBEquipmentRepository,
    EquipmentLegacyTraceError,
    EquipmentRevisionConflict,
    EquipmentScenarioIncompatible,
    EquipmentScheduleRevisionNameMoved,
    EquipmentScheduleRevisionSummary,
    EquipmentSnapshot,
)
from capa_simulation.services.equipment_scenario import (
    ScheduleRestorePreview,
    legacy_unit_key,
    merge_equipment,
    schedule_restore_preview,
    split_downtime,
    split_equipment,
)

__all__ = ["marked"]


def _revisions(
    repository: DuckDBEquipmentRepository, scenario_id: str = OPERATIONS
) -> dict[int, EquipmentScheduleRevisionSummary]:
    return {item.revision_no: item for item in repository.list_schedule_revisions(scenario_id)}


def _schedule_id(
    repository: DuckDBEquipmentRepository, revision_no: int, scenario_id: str = OPERATIONS
) -> str:
    return _revisions(repository, scenario_id)[revision_no].schedule_revision_id


def _latest_common(repository: DuckDBEquipmentRepository) -> str:
    common = repository.latest_revision_id()
    assert common is not None
    return common


def _restore(
    repository: DuckDBEquipmentRepository,
    revision_no: int,
    scenario_id: str = OPERATIONS,
    **options: Any,
) -> Any:
    """그 시나리오 rN 으로 되돌린다 — 확인을 보인 때의 공통 최신·시나리오 최신을 그대로 넘긴다."""
    latest = _revisions(repository, scenario_id)
    return repository.restore_schedule_revision(
        latest[revision_no].schedule_revision_id,
        expected_common_revision_id=_latest_common(repository),
        expected_latest_schedule_revision_id=latest[max(latest)].schedule_revision_id,
        **options,
    )


def _merged(
    repository: DuckDBEquipmentRepository, revision_no: int, scenario_id: str = OPERATIONS
) -> EquipmentSnapshot:
    """지금 공통 대장 + 그 시나리오 rN."""
    return repository.load_merged_snapshot(
        _latest_common(repository), _schedule_id(repository, revision_no, scenario_id)
    )


def _changed_qual(repository: DuckDBEquipmentRepository) -> None:
    """「운영 일정」 r2 — EQ-02 의 Qual일정을 옮기고 EQ-02 에 비가동 하나를 더한다(공식 v2)."""
    session = _session(repository)
    repository.save_equipment(
        _request(
            session,
            equipment=_set(session.equipment, "EQ-02", "Qual일정", "2026-08-24"),
            downtime=_with_downtime(session.downtime, "EQ-02", "공사", "2026-09-05"),
        )
    )


# ── 판정(순수) ───────────────────────────────────────────────────────────────────────


def _pure_view(schedule_edit: Any = None, downtime: pd.DataFrame | None = None) -> Any:
    equipment = _equipment()
    keys = {str(name): legacy_unit_key(str(name)) for name in equipment["설비명"]}
    common, schedule = split_equipment(equipment, keys)
    if schedule_edit is not None:
        schedule = schedule_edit(schedule)
    events = split_downtime(_downtime() if downtime is None else downtime, keys)
    return merge_equipment(common, schedule, events), keys


def test_the_restore_preview_counts_units_by_schedule_and_downtime_regardless_of_order() -> None:
    """일정 칸 하나가 다른 호기·일정 행이 빠지는 호기를 세고, 비가동은 차례와 무관하게 견준다.
    그때의 공통 대장에 없던 키는 「그 뒤에 든 호기」 다."""
    current, keys = _pure_view()
    first, second = list(keys)[:2]

    def edited(schedule: pd.DataFrame) -> pd.DataFrame:
        result = schedule.copy()
        result.loc[result["unit_key"].eq(keys[first]), "물류일정"] = pd.Timestamp("2026-07-01")
        return result.loc[~result["unit_key"].eq(keys[second])].reset_index(drop=True)

    restored, _ = _pure_view(edited)
    preview = schedule_restore_preview(current, restored, source_unit_keys=[keys[first]])

    assert preview == ScheduleRestorePreview(
        changed_units=2,
        downtime_rows_before=len(current.downtime),
        downtime_rows_after=len(restored.downtime),
        unscheduled_after=1,
        newly_unscheduled=1,
        added_since=1,
    )
    assert not preview.identical
    two = _with_downtime(_downtime(), first, "공사", "2026-09-05")
    left, _ = _pure_view(downtime=two)
    right, _ = _pure_view(downtime=two.iloc[::-1].reset_index(drop=True))
    assert schedule_restore_preview(left, right, source_unit_keys=keys.values()).identical
    shifted = replace(right, unit_key_pairs=tuple(reversed(right.unit_key_pairs)))
    with pytest.raises(ValueError, match="공통 대장이 달라"):
        schedule_restore_preview(current, shifted, source_unit_keys=())


# ── 리비전명 ─────────────────────────────────────────────────────────────────────────


def test_a_revision_name_is_a_label_that_can_be_set_changed_and_cleared(
    tmp_path: Path, marked: list[Path]
) -> None:
    repository = _seeded(tmp_path)
    _changed_qual(repository)
    first = _revisions(repository)[1]
    before = _merged(repository, 1)
    counts = _counts(repository)

    named = repository.rename_schedule_revision(
        first.schedule_revision_id, name="  셋업 전 일정 ", expected_name=None
    )
    assert named.revision_name == "셋업 전 일정"
    assert _revisions(repository)[1].revision_name == "셋업 전 일정"
    assert _revisions(repository)[2].revision_name is None
    renamed = repository.rename_schedule_revision(
        first.schedule_revision_id, name="첫 일정", expected_name="셋업 전 일정"
    )
    assert renamed.revision_name == "첫 일정"
    # 같은 이름은 다른 리비전에도 받는다(번호가 늘 가른다).
    repository.rename_schedule_revision(
        _schedule_id(repository, 2), name="첫 일정", expected_name=None
    )
    marked.clear()
    same = repository.rename_schedule_revision(
        first.schedule_revision_id, name="첫 일정", expected_name="첫 일정"
    )
    assert same == renamed and marked == []
    cleared = repository.rename_schedule_revision(
        first.schedule_revision_id, name="  ", expected_name="첫 일정"
    )
    assert cleared.revision_name is None

    # 이름표만 바뀐다 — 번호·메모·저장자·시각·출처·행 수와 내용·리비전 수·발행이 그대로다.
    assert (cleared.revision_no, cleared.note, cleared.created_at, cleared.origin) == (
        first.revision_no,
        first.note,
        first.created_at,
        first.origin,
    )
    assert (cleared.unit_row_count, cleared.downtime_row_count) == (
        first.unit_row_count,
        first.downtime_row_count,
    )
    _assert_same_merged(_merged(repository, 1), before)
    assert _counts(repository) == counts


def test_a_revision_name_is_compared_with_what_was_seen_before_it_is_written(
    tmp_path: Path,
) -> None:
    repository = _seeded(tmp_path)
    first = _schedule_id(repository, 1)
    repository.rename_schedule_revision(first, name="남이 붙인 이름", expected_name=None)

    with pytest.raises(EquipmentScheduleRevisionNameMoved, match="지금: 남이 붙인 이름") as caught:
        repository.rename_schedule_revision(first, name="내 이름", expected_name=None)
    assert caught.value.current == "남이 붙인 이름"
    repository.rename_schedule_revision(first, name=None, expected_name="남이 붙인 이름")
    with pytest.raises(EquipmentScheduleRevisionNameMoved, match="지금: 이름 없음"):
        repository.rename_schedule_revision(first, name="내 이름", expected_name="남이 붙인 이름")
    assert _revisions(repository)[1].revision_name is None


def test_a_revision_name_over_the_limit_is_refused_by_the_repository_too(
    tmp_path: Path, marked: list[Path]
) -> None:
    """리비전명 글자 수 한도는 화면 칸(`max_chars`)만이 아니다 — 저장소도 리비전명 고치기와 되돌리기
    모두에서 자르지 않고 쓰기 전에 거절한다. 앞뒤 공백은 세지 않는다."""
    repository = _seeded(tmp_path)
    _changed_qual(repository)
    first = _schedule_id(repository, 1)
    counts = _counts(repository)
    too_long = "가" * (SCHEDULE_REVISION_NAME_MAX_CHARS + 1)
    refusal = rf"리비전명은 {SCHEDULE_REVISION_NAME_MAX_CHARS}자까지입니다\(지금 "
    marked.clear()

    with pytest.raises(ValueError, match=refusal):
        repository.rename_schedule_revision(first, name=too_long, expected_name=None)
    with pytest.raises(ValueError, match=refusal):
        _restore(repository, 1, revision_name=too_long)
    assert _counts(repository) == counts and marked == []
    assert _revisions(repository)[1].revision_name is None

    exact = "가" * SCHEDULE_REVISION_NAME_MAX_CHARS
    named = repository.rename_schedule_revision(first, name=f"  {exact}  ", expected_name=None)
    assert named.revision_name == exact
    restored = _restore(repository, 1, revision_name=exact)
    assert restored.schedule is not None and restored.schedule.revision_name == exact


def test_a_rename_reaches_the_cached_list_through_the_write_generation_not_the_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """리비전 목록 캐시는 쓰기 세대(`clear_equipment_scenario_cache`)로 새 이름을 읽는다 — stat
    이 못 잡는 경우(같은 DB 를 연 다른 길)를 흉내 내려고 stat 을 고정해도 그렇다. 불변 본문 캐시는
    이름을 싣지 않아 이름을 바꾼 뒤에도 옛 이름을 내지 않는다(늘 None)."""
    clear_equipment_repository()
    repository = _seeded(tmp_path)
    database = str(repository.database_path)
    monkeypatch.setattr(equipment_cache, "database_stamp", lambda _path: (None, None))
    try:
        first = load_equipment_schedule_revisions(database, OPERATIONS)[0]
        body = load_merged_equipment_snapshot(
            database, _latest_common(repository), first.schedule_revision_id
        )
        assert first.revision_name is None
        assert body.schedule is not None and body.schedule.revision_name is None

        repository.rename_schedule_revision(
            first.schedule_revision_id, name="공식 첫 일정", expected_name=None
        )
        stale = load_equipment_schedule_revisions(database, OPERATIONS)[0]
        assert stale.revision_name is None  # 비우기 전 — 세대가 그대로라 캐시 그대로
        clear_equipment_scenario_cache()
        fresh = load_equipment_schedule_revisions(database, OPERATIONS)[0]
        again = load_merged_equipment_snapshot(
            database, _latest_common(repository), first.schedule_revision_id
        )

        assert fresh.revision_name == "공식 첫 일정"
        assert again.schedule is not None and again.schedule.revision_name is None
        assert again.token == body.token
    finally:
        clear_equipment_repository()


# ── 이 리비전으로 되돌리기 ─────────────────────────────────────────────────────────────


def test_restoring_saves_a_new_revision_whose_schedule_equals_the_chosen_one(
    tmp_path: Path,
) -> None:
    """r1 로 되돌리면 r3 이 생기고 그 일정·비가동은 r1 과 같다. 공통 대장은 그대로이고, 공식
    시나리오에서 발행 기본값대로 공식 v3 이 된다."""
    repository = _seeded(tmp_path)
    _changed_qual(repository)
    counts = _counts(repository)
    source = _merged(repository, 1)

    result = _restore(repository, 1, saved_by="홍길동", note="셋업 취소", revision_name="원복")

    assert result.schedule is not None
    created = result.schedule
    assert (created.revision_no, created.origin, created.saved_by) == (3, "restore", "홍길동")
    assert created.note == "r1 일정으로 되돌림 — 셋업 취소"
    assert created.revision_name == "원복"
    assert created.common_revision_id == _latest_common(repository)
    assert result.preview.changed_units == 1 and result.release_no == 3
    assert not result.release_withheld
    _assert_same_merged(_merged(repository, 3), source)
    assert _value(_merged(repository, 3), "EQ-02", "Qual일정") == pd.Timestamp("2026-08-21")
    # 공통 리비전은 늘지 않고, 일정 리비전·발행이 하나씩 는다. 옛 r1·r2 는 그대로다.
    assert _counts(repository) == (counts[0], counts[1] + 1, counts[2] + 1)
    assert [item.origin for item in _revisions(repository).values()] == [
        "restore",
        "save",
        "save",
    ]
    official = repository.load_official_snapshot()
    assert official is not None and official.schedule is not None
    assert official.schedule.schedule_revision_id == created.schedule_revision_id


def test_units_added_after_the_revision_become_unscheduled_when_restoring(
    tmp_path: Path,
) -> None:
    """r1 뒤에 공통 대장에 든 EQ-NEW 는 r1 에 일정이 없다 — 확인 재료가 그 수를 세고, 되돌린 뒤 그
    시나리오에서 일정 없음(계산에서 빠짐)이다. 공통 대장에는 그대로 있다."""
    repository = _seeded(tmp_path)
    session = _session(repository)
    repository.save_equipment(
        _request(
            session,
            equipment=_with_unit(session.equipment, "EQ-NEW", 70.0),
        )
    )
    first, second = _schedule_id(repository, 1), _schedule_id(repository, 2)

    preview = repository.preview_schedule_restore(
        first,
        common_revision_id=_latest_common(repository),
        current_schedule_revision_id=second,
    )
    assert (preview.added_since, preview.newly_unscheduled, preview.unscheduled_after) == (1, 1, 1)
    assert preview.changed_units == 1

    result = _restore(repository, 1)
    restored = _merged(repository, 3)

    assert result.preview == preview
    assert restored.unscheduled_units == frozenset({"EQ-NEW"})
    assert "EQ-NEW" in restored.equipment["설비명"].tolist()
    assert "EQ-NEW" not in restored.calculation_frames()[1]["설비명"].tolist()


def test_restoring_a_schedule_equal_to_the_latest_writes_nothing(
    tmp_path: Path, marked: list[Path]
) -> None:
    repository = _seeded(tmp_path)
    session = _session(repository)
    repository.save_equipment(
        _request(session, equipment=_set(session.equipment, "EQ-02", "Qual일정", "2026-08-24"))
    )
    session = _session(repository)
    repository.save_equipment(
        _request(session, equipment=_set(session.equipment, "EQ-02", "Qual일정", "2026-08-21"))
    )
    counts = _counts(repository)
    marked.clear()

    result = _restore(repository, 1)

    assert result.schedule is None and result.preview.identical
    assert result.release_no is None
    assert _counts(repository) == counts and marked == []


def test_restoring_is_refused_when_the_latest_schedule_or_common_moved_after_the_confirm(
    tmp_path: Path,
) -> None:
    repository = _seeded(tmp_path)
    first = _schedule_id(repository, 1)
    common = _latest_common(repository)
    _changed_qual(repository)
    counts = _counts(repository)

    with pytest.raises(EquipmentRevisionConflict, match="「운영 일정」 r2") as moved:
        repository.restore_schedule_revision(
            first, expected_common_revision_id=common, expected_latest_schedule_revision_id=first
        )
    assert moved.value.side == "schedule"
    with pytest.raises(EquipmentRevisionConflict) as common_moved:
        repository.restore_schedule_revision(
            first,
            expected_common_revision_id="그때 본 공통",
            expected_latest_schedule_revision_id=_schedule_id(repository, 2),
        )
    assert common_moved.value.side == "common"
    assert _counts(repository) == counts


def test_restoring_the_official_scenario_withholds_publishing_over_an_unpublished_revision(
    tmp_path: Path,
) -> None:
    """공식 시나리오의 발행 규칙은 저장과 같다 — 발행 안 한 더 새 리비전(r2)이 있으면 되돌린 r3 을
    발행하지 않고 알린다. 체크를 끄면 발행도 알림도 없다."""
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
    repository.save_equipment(
        _request(
            session,
            equipment=_set(session.equipment, "EQ-02", "Qual일정", "2026-08-26"),
            publish_official=False,
        )
    )

    withheld = _restore(repository, 2)
    assert withheld.schedule is not None and withheld.schedule.revision_no == 4
    assert (withheld.release_no, withheld.release_withheld) == (None, True)
    quiet = _restore(repository, 1, publish_official=False)
    assert quiet.schedule is not None and quiet.schedule.revision_no == 5
    assert (quiet.release_no, quiet.release_withheld) == (None, False)
    release = repository.latest_equipment_release()
    assert release is not None and release.release_no == 1


def test_restoring_an_assumption_scenario_leaves_the_official_alone(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    setup = _clone(repository)
    mine = _session(repository, setup.equipment_scenario_id)
    repository.save_equipment(
        _request(
            mine,
            setup.equipment_scenario_id,
            equipment=_set(mine.equipment, "EQ-02", "Qual일정", "2026-08-26"),
        )
    )
    official_before = repository.load_official_snapshot()

    result = _restore(repository, 1, setup.equipment_scenario_id)

    assert result.schedule is not None and result.schedule.revision_no == 3
    assert result.release_no is None and not result.release_withheld
    _assert_same_merged(
        _merged(repository, 3, setup.equipment_scenario_id),
        _merged(repository, 1, setup.equipment_scenario_id),
    )
    official_after = repository.load_official_snapshot()
    assert official_before is not None and official_after is not None
    assert official_after.token == official_before.token
    assert len(_revisions(repository)) == 1


def test_a_restore_of_a_legacy_revision_keeps_its_conversions_and_unknown_units(
    tmp_path: Path,
) -> None:
    """이관 r2(Qual 자리표, r3 의 두 호기를 모름)로 되돌리면 r4 는 그것을 지금 공통과 합친 것과 같다
    — 자리표는 빈칸, 모르는 두 호기는 그 뒤에 든 호기라 일정 없음."""
    repository = _migrated(tmp_path)
    source = _merged(repository, 2)
    preview = repository.preview_schedule_restore(
        "legacy-r2",
        common_revision_id=_latest_common(repository),
        current_schedule_revision_id="legacy-r3",
    )

    result = _restore(repository, 2)

    assert preview.added_since == 2 and preview.unscheduled_after == 2
    assert result.schedule is not None and result.schedule.revision_no == 4
    restored = _merged(repository, 4)
    _assert_same_merged(restored, source)
    assert pd.isna(_value(restored, "설비01", "Qual일정"))
    assert restored.unscheduled_units == frozenset({"EQ-OLD", "EQ-OUT"})


def test_a_revision_that_no_longer_merges_cannot_be_restored(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    first = _session(repository)
    repository.save_equipment(
        _request(first, equipment=_set(first.equipment, "EQ-02", "Qual일정", None))
    )
    session = _session(repository)
    repository.save_equipment(
        _request(session, equipment=_set(session.equipment, "EQ-02", "Qual상태", None))
    )
    counts = _counts(repository)

    with pytest.raises(EquipmentScenarioIncompatible, match="「운영 일정」 r1"):
        repository.preview_schedule_restore(
            _schedule_id(repository, 1),
            common_revision_id=_latest_common(repository),
            current_schedule_revision_id=_schedule_id(repository, 2),
        )
    with pytest.raises(EquipmentScenarioIncompatible, match="「운영 일정」 r1"):
        _restore(repository, 1)
    assert _counts(repository) == counts


def test_a_legacy_trace_blocks_restoring_like_any_equipment_save(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    _changed_qual(repository)
    expected_common = _latest_common(repository)
    latest = _schedule_id(repository, 2)
    with duckdb.connect(str(repository.database_path)) as connection:
        connection.execute(
            """
            INSERT INTO equipment_ops.revision (
                revision_id, revision_no, note, baseline_hash, schedule_hash,
                equipment_hash, downtime_hash, equipment_contract_version
            ) VALUES ('old', 9, '옛 판', 'b', 's', 'e', 'd', 3)
            """
        )

    with pytest.raises(EquipmentLegacyTraceError):
        repository.restore_schedule_revision(
            _schedule_id(repository, 1),
            expected_common_revision_id=expected_common,
            expected_latest_schedule_revision_id=latest,
        )


def test_the_restore_preview_cache_is_keyed_by_the_three_revisions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """확인 재료는 불변 리비전 셋이 키다 — 같은 셋이면 저장소를 다시 부르지 않고, 최신이 바뀌면 새
    셋이라 다시 잰다."""
    clear_equipment_repository()
    repository = _seeded(tmp_path)
    _changed_qual(repository)
    database = str(repository.database_path)
    calls: list[str] = []
    original = DuckDBEquipmentRepository.preview_schedule_restore

    def counted(self: DuckDBEquipmentRepository, revision: str, **kwargs: Any) -> Any:
        calls.append(revision)
        return original(self, revision, **kwargs)

    monkeypatch.setattr(DuckDBEquipmentRepository, "preview_schedule_restore", counted)
    try:
        first, second = _schedule_id(repository, 1), _schedule_id(repository, 2)
        common = _latest_common(repository)
        one = load_schedule_restore_preview(database, common, second, first)
        two = load_schedule_restore_preview(database, common, second, first)
        assert one == two and one.changed_units == 1 and len(calls) == 1

        _restore(repository, 1)
        third = _schedule_id(repository, 3)
        after = load_schedule_restore_preview(database, common, third, first)
        assert after.identical and len(calls) == 2
    finally:
        clear_equipment_repository()


# ── 여기서 새 시나리오 ─────────────────────────────────────────────────────────────────


def test_a_new_scenario_can_start_from_any_revision_not_only_the_latest_or_official(
    tmp_path: Path,
) -> None:
    """r1 은 최신도 공식도 아니다(r2 가 둘 다) — 그래도 그 일정으로 새 시나리오 r1 을 만든다. 그 뒤
    공통 대장에 든 호기는 새 시나리오에서 일정 없음이다."""
    repository = _seeded(tmp_path)
    session = _session(repository)
    repository.save_equipment(
        _request(
            session,
            equipment=_with_unit(
                _set(session.equipment, "EQ-02", "Qual일정", "2026-08-24"), "EQ-NEW", 70.0
            ),
        )
    )
    source = _merged(repository, 1)

    branch = repository.clone_equipment_scenario(
        _schedule_id(repository, 1), name="r1 가지", created_by="홍길동"
    )

    assert (branch.latest_revision_no, branch.revision_count) == (1, 1)
    copied = _merged(repository, 1, branch.equipment_scenario_id)
    _assert_same_merged(copied, source)
    assert copied.unscheduled_units == frozenset({"EQ-NEW"})
    assert _value(copied, "EQ-02", "Qual일정") == pd.Timestamp("2026-08-21")
    revision = _revisions(repository, branch.equipment_scenario_id)[1]
    assert (revision.origin, revision.note) == ("clone", "「운영 일정」 r1에서 복제")
    # 출처 시나리오는 그대로다.
    assert len(_revisions(repository)) == 2
