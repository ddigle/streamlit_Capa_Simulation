# Purpose: 필요단축일정 공용 조회 조건 프로필의 규칙과 설비 DB(0019) 저장·읽기·무변경을 검사한다.

"""필요단축일정 공용 조회 조건 프로필(설비 DB 0019).

화면 동작(심기·콜백 저장·새 세션)은 `test_required_shortening_tab.py` 가 본다. 여기는 규칙 함수와
Repository 의 왕복이다.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from capa_simulation.persistence.equipment_migration_runner import load_equipment_migrations
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.shortening_filter_profile import (
    ShorteningFilterProfile,
    absent_filter_processes,
    merge_filter_processes,
    normalize_filter_month,
    normalize_filter_processes,
    seeded_filter_month,
)


def _repository(tmp_path: Path) -> DuckDBEquipmentRepository:
    repository = DuckDBEquipmentRepository(tmp_path / "availability.duckdb")
    repository.initialize()
    return repository


# ------------------------------------------------------- 규칙


def test_a_stored_month_seeds_only_when_it_is_an_option() -> None:
    options = [202610, 202611, 202612]
    assert seeded_filter_month(202611, options, options[0]) == 202611
    assert seeded_filter_month(202701, options, options[0]) == 202610
    assert seeded_filter_month(None, options, options[-1]) == 202612


def test_merging_keeps_saved_processes_the_screen_could_not_show() -> None:
    """고른 공정 + 화면에 없던 저장 공정. 화면에 있었는데 빠진 것은 사용자가 뺀 것이다."""
    stored = ("A", "B", "GONE")
    visible = {"A", "B", "C"}
    assert merge_filter_processes(stored, ["C", "A"], visible) == ("C", "A", "GONE")
    assert absent_filter_processes(stored, visible) == ["GONE"]
    # 같은 공정이 겹쳐 와도 한 번만 남는다.
    assert merge_filter_processes(("A", "GONE"), ["A", " A "], {"A"}) == ("A", "GONE")


def test_clearing_the_selection_saves_all_short_processes_not_the_hidden_rest() -> None:
    """모두 비우면 「미선택 = 목표 미달 공정 전체」다 — 숨은 공정만 남기면 뜻이 「그 공정만」이
    된다."""
    assert merge_filter_processes(("A", "GONE"), [], {"A"}) == ()


def test_values_are_normalized() -> None:
    assert normalize_filter_processes([" A ", "", None, "A", "B"]) == ("A", "B")
    assert normalize_filter_month("202611") == 202611
    for bad in (202613, 202600, 20261, "26-11", True):
        with pytest.raises(ValueError, match="YYYYMM"):
            normalize_filter_month(bad)


# ------------------------------------------------------- 설비 DB


def test_migration_0019_creates_the_profile_tables(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    assert 19 in {migration.version for migration in load_equipment_migrations()}
    with duckdb.connect(str(repository.database_path)) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'equipment_ops'
                """
            ).fetchall()
        }
    assert {"shortening_filter_profile", "shortening_filter_process"} <= tables


def test_an_unsaved_profile_is_empty(tmp_path: Path) -> None:
    assert _repository(tmp_path).load_shortening_filter_profile() == ShorteningFilterProfile()


def test_months_and_processes_are_saved_separately(tmp_path: Path) -> None:
    """기간을 쓰면 공정이, 공정을 쓰면 기간이 그대로다. 쓸 때마다 version 이 오른다."""
    repository = _repository(tmp_path)

    assert repository.save_shortening_filter_processes(
        ["P2", "P1"], visible=["P1", "P2"], source="공정"
    )
    profile = repository.load_shortening_filter_profile()
    assert (profile.start_month, profile.end_month) == (None, None)
    assert (profile.processes, profile.version, profile.source) == (("P2", "P1"), 1, "공정")
    assert profile.updated_at is not None

    assert repository.save_shortening_filter_months(202611, 202703, source="기간")
    profile = repository.load_shortening_filter_profile()
    assert (profile.start_month, profile.end_month) == (202611, 202703)
    assert (profile.processes, profile.version, profile.source) == (("P2", "P1"), 2, "기간")

    # 새로 연 저장소(다른 프로세스)도 같은 값을 읽는다.
    reopened = DuckDBEquipmentRepository(repository.database_path)
    assert reopened.load_shortening_filter_profile() == profile


def test_saving_the_same_values_does_not_write(tmp_path: Path) -> None:
    """공용 행이라 같은 값을 다시 쓰면 version 만 오르고 DB 가 dirty 가 된다 — 쓰지 않는다."""
    repository = _repository(tmp_path)
    repository.save_shortening_filter_months(202611, 202612, source="기간")
    repository.save_shortening_filter_processes(["P1"], visible=["P1"], source="공정")

    assert not repository.save_shortening_filter_months(202611, 202612, source="기간")
    assert not repository.save_shortening_filter_processes(["P1"], visible=["P1"], source="공정")
    # 화면에 없던 저장 공정은 남으므로 같은 선택은 같은 목록이다.
    assert not repository.save_shortening_filter_processes(["P1"], visible=["P1", "P2"], source="x")
    assert repository.load_shortening_filter_profile().version == 2
    # 한 번도 공정을 저장하지 않은 프로필에 빈 선택은 이미 같은 값이다.
    fresh = DuckDBEquipmentRepository(tmp_path / "fresh.duckdb")
    fresh.initialize()
    assert not fresh.save_shortening_filter_processes([], visible=["P1"], source="x")
    assert fresh.load_shortening_filter_profile().version == 0


def test_a_reversed_period_is_kept_and_a_bad_month_is_refused(tmp_path: Path) -> None:
    """시작 월이 끝 월보다 늦어도 받는다(화면이 바꿔 읽는다). 달이 아니면 거절하고 쓰지 않는다."""
    repository = _repository(tmp_path)
    assert repository.save_shortening_filter_months(202703, 202611, source="기간")
    profile = repository.load_shortening_filter_profile()
    assert (profile.start_month, profile.end_month) == (202703, 202611)

    with pytest.raises(ValueError, match="YYYYMM"):
        repository.save_shortening_filter_months(202613, 202611, source="기간")
    assert repository.load_shortening_filter_profile() == profile


def test_hidden_saved_processes_survive_a_change_and_clearing_drops_them(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.save_shortening_filter_processes(
        ["P1", "GONE"], visible=["P1", "GONE"], source="공정"
    )

    assert repository.save_shortening_filter_processes(["P2"], visible=["P1", "P2"], source="공정")
    assert repository.load_shortening_filter_profile().processes == ("P2", "GONE")

    assert repository.save_shortening_filter_processes([], visible=["P1", "P2"], source="공정")
    assert repository.load_shortening_filter_profile().processes == ()
