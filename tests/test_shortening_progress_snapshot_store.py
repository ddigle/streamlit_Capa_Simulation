# Purpose: 누적 진척 넣기 스냅숏(설비 0037)의 한 트랜잭션 저장 · 왕복 · 지움 · 손 고침을 본다.

"""누적 진척 넣기 스냅숏의 저장(`persistence/shortening_progress_snapshot_store.py` · 저장소
메서드).

「이번 주 값 넣기」 로 기록을 저장하면 그 화면 호기 표가 기록 줄과 같은 쓰기 트랜잭션에 남고, 기록을
지우면 함께 지워진다. 손으로 적은 주는 스냅숏이 없다. 표는 합성 호기 표(공정 `PRC-xx`)다.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import pytest
from test_shortening_progress_reasons import NEED, _day, _draft, _real, _virtual

from capa_simulation.persistence import equipment_cache, equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.shortening_baseline import BaselineProvenance
from capa_simulation.services.shortening_progress_log import (
    ProgressLogConflictError,
    ProgressWeek,
)
from capa_simulation.services.shortening_progress_reasons import (
    TAG_MANUAL,
    TAG_QUAL_EARLIER,
    TAG_SCOPE,
    ProgressSnapshotDraft,
    explain_week_changes,
)

W46, W47 = ProgressWeek(2026, 46), ProgressWeek(2026, 47)
CHILDREN = ("shortening_progress_snapshot_process", "shortening_progress_snapshot_unit")


@pytest.fixture()
def repository(tmp_path: Path) -> DuckDBEquipmentRepository:
    repo = DuckDBEquipmentRepository(tmp_path / "equipment.duckdb")
    repo.initialize()
    return repo


def _counts(repository: DuckDBEquipmentRepository) -> tuple[int, ...]:
    """(머리, 범위 공정, 호기) 행 수."""
    counts: list[int] = []
    with duckdb.connect(str(repository.database_path), read_only=True) as connection:
        for table in ("shortening_progress_snapshot", *CHILDREN):
            row = connection.execute(f"SELECT count(*) FROM equipment_ops.{table}").fetchone()
            counts.append(0 if row is None else int(row[0]))
    return tuple(counts)


def _week_draft(secure: int, *, extra: bool = False) -> ProgressSnapshotDraft:
    rows = [_real("PRC-01", "EQ-01", NEED, _day(secure)), _real("PRC-02", "EQ-02", NEED, None)]
    if extra:
        rows.append(_real("PRC-02", "EQ-03", NEED, _day(4)))
    return _draft(
        rows,
        ("PRC-01", "PRC-02"),
        provenance=BaselineProvenance(
            scenario_id="DEMO-s", scenario_revision_id="DEMO-r3", scenario_revision_no=3
        ),
    )


def test_a_filled_save_keeps_the_screen_table_in_the_same_write_and_reads_it_back(
    repository: DuckDBEquipmentRepository,
) -> None:
    """넣기 저장은 기록 줄과 스냅숏을 한 트랜잭션에서 쓴다 — 읽으면 같은 표 · 합 · 범위 · Cut-off ·
    출처 · 구성 글이고, 머리의 기록 시각은 그 기록 줄의 저장 시각이다. 손으로 적은 주는 없다."""
    draft = _week_draft(30)
    assert repository.save_shortening_progress_entry(
        W47, draft.days, expected_days=None, recorded_by="DEMO", snapshot=draft
    )
    assert repository.save_shortening_progress_entry(W46, 31, expected_days=None)
    (snapshot,) = repository.load_shortening_progress_snapshots()
    entry = repository.load_shortening_progress_log().entries[1]
    assert snapshot.week == entry.week == W47
    assert snapshot.log_updated_at == entry.updated_at is not None
    assert snapshot.captured_by == "DEMO"
    got = snapshot.draft
    assert (got.days, got.level_percent, got.basis, got.selected) == (30, 100, "Static", False)
    assert (got.today, got.months, got.processes) == (draft.today, draft.months, draft.processes)
    assert got.cutoff_days == (None, None) and got.digest == draft.digest
    assert got.provenance == draft.provenance
    pd.testing.assert_frame_equal(got.units, draft.units, check_dtype=False)
    cached = equipment_cache.load_shortening_progress_snapshots(str(repository.database_path))
    assert set(cached) == {W47}
    pd.testing.assert_frame_equal(cached[W47].draft.units, draft.units, check_dtype=False)
    equipment_cache.clear_shortening_progress_cache()


def test_a_refused_save_writes_neither_the_record_nor_the_snapshot(
    repository: DuckDBEquipmentRepository,
) -> None:
    """겹친 저장(UI-STA-05) — 대조에서 지면 기록도 스냅숏도 쓰지 않는다."""
    assert repository.save_shortening_progress_entry(W47, 20, expected_days=None)
    draft = _week_draft(30)
    with pytest.raises(ProgressLogConflictError):
        repository.save_shortening_progress_entry(W47, 30, expected_days=None, snapshot=draft)
    assert repository.load_shortening_progress_log().days_of(W47) == 20
    assert _counts(repository) == (0, 0, 0)


@pytest.mark.parametrize(
    "step", ["write_progress_snapshot", "carry_progress_snapshot", "delete_progress_snapshot"]
)
def test_a_failing_snapshot_step_rolls_back_the_record_of_the_same_write(
    repository: DuckDBEquipmentRepository, monkeypatch: pytest.MonkeyPatch, step: str
) -> None:
    """기록 줄과 스냅숏은 **같은 쓰기 트랜잭션**이다 — 스냅숏 쓰기(넣기 저장) · 옮기기(넣기 없이
    고침) · 지우기(기록 지우기)가 실패하면 기록 줄도 바뀌지 않는다. 스냅숏 단계를 트랜잭션 밖(저장
    뒤 따로 부름 등)으로 옮겨 하나만 남는 꼴이 되면 여기서 걸린다."""
    repository.save_shortening_progress_entry(W46, 30, expected_days=None, snapshot=_week_draft(30))
    before = [
        (entry.week, entry.days, entry.updated_at)
        for entry in repository.load_shortening_progress_log().entries
    ]
    counts = _counts(repository)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError(step)

    monkeypatch.setattr(equipment_repository, step, fail)
    with pytest.raises(RuntimeError, match=step):
        if step == "write_progress_snapshot":
            repository.save_shortening_progress_entry(
                W47, 22, expected_days=None, snapshot=_week_draft(22)
            )
        elif step == "carry_progress_snapshot":
            repository.save_shortening_progress_entry(W46, 27, expected_days=30)
        else:
            repository.delete_shortening_progress_entry(W46, expected_days=30)
    after = [
        (entry.week, entry.days, entry.updated_at)
        for entry in repository.load_shortening_progress_log().entries
    ]
    assert after == before
    assert _counts(repository) == counts


def test_deleting_the_record_deletes_its_snapshot(repository: DuckDBEquipmentRepository) -> None:
    draft = _week_draft(30)
    repository.save_shortening_progress_entry(W47, 30, expected_days=None, snapshot=draft)
    assert _counts(repository) == (1, 2, 2)
    assert repository.delete_shortening_progress_entry(W47, expected_days=30)
    assert _counts(repository) == (0, 0, 0)
    assert repository.load_shortening_progress_snapshots() == ()


def test_a_hand_edit_keeps_the_fill_snapshot_and_reads_as_a_hand_edit(
    repository: DuckDBEquipmentRepository,
) -> None:
    """넣기로 저장한 주를 나중에 넣기 없이 고치면 스냅숏은 넣기 때 화면 그대로 남아 새 기록 시각으로
    옮겨지고, 그 차이는 까닭 「손 고침」 이다."""
    repository.save_shortening_progress_entry(W46, 30, expected_days=None, snapshot=_week_draft(30))
    repository.save_shortening_progress_entry(W47, 22, expected_days=None, snapshot=_week_draft(22))
    assert repository.save_shortening_progress_entry(W47, 19, expected_days=22)
    snapshots = {
        snapshot.week: snapshot for snapshot in repository.load_shortening_progress_snapshots()
    }
    log = repository.load_shortening_progress_log()
    assert set(snapshots) == {W46, W47}
    assert snapshots[W47].log_updated_at == log.entries[1].updated_at
    change = explain_week_changes(log, snapshots)[W47]
    assert [(item.tag, item.days) for item in change.items] == [
        (TAG_QUAL_EARLIER, -8),
        (TAG_MANUAL, -3),
    ]
    assert change.balanced and change.change == -11


def test_the_same_value_with_another_screen_rewrites_only_the_snapshot(
    repository: DuckDBEquipmentRepository,
) -> None:
    """같은 수 · 같은 구성의 넣기는 쓰지 않는다(바뀐 것이 없음). 같은 수라도 구성이 다른 넣기는
    스냅숏만 갈아 쓰고 — 새 id 의 자식이 서고 옛 자식은 지워진다 — 기록 줄은 그대로다."""
    first = _week_draft(30)
    repository.save_shortening_progress_entry(W47, 30, expected_days=None, snapshot=first)
    stamp = repository.load_shortening_progress_log().entries[0].updated_at
    assert not repository.save_shortening_progress_entry(
        W47, 30, expected_days=30, snapshot=_week_draft(30)
    )
    other = _week_draft(26, extra=True)
    assert other.days == first.days and other.digest != first.digest
    assert repository.save_shortening_progress_entry(W47, 30, expected_days=30, snapshot=other)
    assert _counts(repository) == (1, 2, 3)
    (snapshot,) = repository.load_shortening_progress_snapshots()
    assert snapshot.draft.digest == other.digest
    assert (
        snapshot.log_updated_at
        == stamp
        == repository.load_shortening_progress_log().entries[0].updated_at
    )


def test_a_header_left_by_code_that_does_not_know_0037_is_ignored_and_dropped(
    repository: DuckDBEquipmentRepository,
) -> None:
    """옛 코드(0037 을 모르는 판)가 그 주 기록을 고치면 기록 시각이 어긋나 스냅숏을 읽지 않는다.
    그 뒤 넣기 없이 그 주를 저장하면 그 낡은 머리 · 자식은 지워진다 — 엉뚱한 기록에 붙지 않는다."""
    repository.save_shortening_progress_entry(W47, 30, expected_days=None, snapshot=_week_draft(30))
    with duckdb.connect(str(repository.database_path)) as connection:
        connection.execute(
            "UPDATE equipment_ops.shortening_progress_log SET shortening_days = 28, "
            "updated_at = updated_at + INTERVAL 1 MINUTE WHERE iso_year = 2026 AND iso_week = 47"
        )
    assert repository.load_shortening_progress_snapshots() == ()
    assert _counts(repository) == (1, 2, 2)
    assert repository.save_shortening_progress_entry(W47, 27, expected_days=28)
    assert _counts(repository) == (0, 0, 0)


def test_the_cached_reasons_equal_the_direct_count_and_skip_the_snapshots_on_a_hit(
    repository: DuckDBEquipmentRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """「주차별」 까닭은 캐시 경계(`load_shortening_progress_reasons`)에서 받는다 — 다시 세운 값이
    직접 센 `explain_week_changes` 와 같고(덧말 칸까지 — 빠진 칸이 있으면 여기서 어긋난다), 맞은
    회차는 스냅숏 표를 다시 읽지 않는다. 저장 뒤 캐시를 비우면 새 기록으로 다시 센다."""
    past = _draft(
        [
            _real("PRC-01", "EQ-01", NEED, _day(30)),
            _real("PRC-02", "EQ-02", NEED, _day(20)),
            _real("PRC-04", "EQ-04", NEED, _day(10)),
            _virtual("PRC-01", "추가1", NEED),
        ],
        ("PRC-01", "PRC-02", "PRC-04"),
        cutoff_days={"PRC-01": 10},
        provenance=BaselineProvenance(scenario_revision_id="DEMO-r3", scenario_revision_no=3),
    )
    current = _draft(
        [
            _real("PRC-01", "EQ-01", NEED, _day(22)),
            _real("PRC-02", "EQ-09", NEED, _day(15)),
            _real("PRC-03", "EQ-03", NEED, _day(6)),
            _virtual("PRC-01", "추가1", NEED),
            _virtual("PRC-01", "추가2", NEED),
        ],
        ("PRC-01", "PRC-02", "PRC-03"),
        months=(202701, 202709),
        cutoff_days={"PRC-01": 12},
        provenance=BaselineProvenance(scenario_revision_id="DEMO-r4", scenario_revision_no=4),
    )
    repository.save_shortening_progress_entry(W46, past.days, expected_days=None, snapshot=past)
    repository.save_shortening_progress_entry(
        W47, current.days, expected_days=None, snapshot=current
    )
    path = str(repository.database_path)
    equipment_cache.clear_shortening_progress_cache()
    direct = explain_week_changes(
        repository.load_shortening_progress_log(),
        {snapshot.week: snapshot for snapshot in repository.load_shortening_progress_snapshots()},
    )
    cached = equipment_cache.load_shortening_progress_reasons(path)
    assert cached == direct and set(cached) == {W47}
    change = cached[W47]
    assert change.renamed == ("PRC-02",) and change.virtual == (1, 2)
    assert change.cutoffs == (("PRC-01", 10, 12),) and len(change.inputs) == 2
    assert any(item.tag == TAG_SCOPE and item.parts for item in change.items)

    def refuse(_path: str) -> object:
        raise AssertionError("맞은 회차는 스냅숏을 읽지 않는다")

    monkeypatch.setattr(equipment_cache, "load_shortening_progress_snapshots", refuse)
    assert equipment_cache.load_shortening_progress_reasons(path) == direct
    monkeypatch.undo()
    assert repository.save_shortening_progress_entry(
        W47, current.days - 3, expected_days=current.days
    )
    equipment_cache.clear_shortening_progress_cache()
    again = equipment_cache.load_shortening_progress_reasons(path)[W47]
    assert again.change == change.change - 3 and again.balanced
    assert (TAG_MANUAL, -3) in [(item.tag, item.days) for item in again.items]
    equipment_cache.clear_shortening_progress_cache()
