# Purpose: GAP 비교 대상 공용 프로필의 저장·복원과 그 경계 조건을 고정한다.

"""비교 대상은 시나리오와 분리된 공용 프로필이다.

고른 시나리오·리비전이 세션에만 있으면 브라우저를 새로 열 때마다 사라진다. 표시순서·선행
물량·과거 구간과 같은 결로 단일 행 프로필에 둔다.

**토글은 담지 않는다.** 켜고 끄는 것은 지금 보는 사람의 상태이고 시나리오를 바꾸면 꺼지는
값이라, 공용으로 남기면 남의 화면까지 켜진다.
"""

from pathlib import Path

import pytest

from capa_simulation.persistence.repository import DuckDBScenarioRepository


def _repository(tmp_path: Path) -> DuckDBScenarioRepository:
    repository = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    repository.initialize()
    return repository


def test_an_unsaved_profile_reads_as_empty(tmp_path: Path) -> None:
    """한 번도 저장하지 않은 상태가 정상이다. 여기서 죽으면 첫 저장 전까지 HOME 이 안 열린다."""
    profile = _repository(tmp_path).load_global_comparison_scenario()

    assert profile.version == 0
    assert profile.updated_at is None
    assert profile.scenario_id is None
    assert profile.revision_id is None


def test_the_choice_round_trips_and_bumps_its_version(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    saved = repository.replace_global_comparison_scenario("SCN-1", "REV-9", source="테스트")
    assert (saved.scenario_id, saved.revision_id, saved.version) == ("SCN-1", "REV-9", 1)

    reloaded = repository.load_global_comparison_scenario()
    assert (reloaded.scenario_id, reloaded.revision_id) == ("SCN-1", "REV-9")

    again = repository.replace_global_comparison_scenario("SCN-2", "REV-2", source="테스트")
    assert (again.scenario_id, again.version) == ("SCN-2", 2)


def test_clearing_the_choice_is_a_normal_save(tmp_path: Path) -> None:
    """해제도 저장이고 version 이 올라야 한다 — 캐시 키가 version 을 본다."""
    repository = _repository(tmp_path)
    repository.replace_global_comparison_scenario("SCN-1", "REV-9", source="테스트")

    cleared = repository.replace_global_comparison_scenario(None, None, source="해제")

    assert cleared.scenario_id is None
    assert cleared.revision_id is None
    assert cleared.version == 2


def test_a_revision_without_its_scenario_is_rejected(tmp_path: Path) -> None:
    """어느 시나리오의 리비전인지 모르면 화면이 복원할 수 없다."""
    with pytest.raises(ValueError, match="시나리오를 함께"):
        _repository(tmp_path).replace_global_comparison_scenario(None, "REV-9", source="테스트")


def test_a_scenario_without_a_revision_is_allowed(tmp_path: Path) -> None:
    """시나리오만 고르고 리비전을 아직 안 고른 중간 상태가 실제로 생긴다."""
    saved = _repository(tmp_path).replace_global_comparison_scenario("SCN-1", None, source="테스트")

    assert (saved.scenario_id, saved.revision_id) == ("SCN-1", None)
