# Purpose: HOME 주요 Case 공용 프로필(0036)의 저장·복원·version 대조와 생명주기 정리를 고정한다.

"""주요 Case(Case1·Case2)는 시나리오와 분리된 공용 프로필이다(2026-10-23 사용자 요청).

슬롯 1 은 지금 최신 공식버전이라 담지 않는다. Case 하나를 바꿔도 다른 Case 는 그대로여야 하고
— 두 사람이 서로 다른 Case 를 고르는 일이 흔하다 — 가리키던 시나리오를 보관·영구 삭제하면 그
Case 만 비고 행은 남아 version 이 오른다. 칸 이름이 `scenario_id` 가 아니라 `_owned_tables` 자동
발견이 행을 통째로 지우지 않는다.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from capa_simulation.persistence._sql_helpers import ProfileVersionConflict
from capa_simulation.persistence.models import ScenarioCreate
from capa_simulation.persistence.repository import DuckDBScenarioRepository


def _repository(tmp_path: Path) -> DuckDBScenarioRepository:
    repository = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    repository.initialize()
    return repository


def _scenarios(repository: DuckDBScenarioRepository, *names: str) -> list[tuple[str, str]]:
    """내장 시드(공식) 다음에 시나리오를 `names` 차례로 복제해 만든다. [(시나리오, 리비전)]."""
    from capa_simulation.application_bootstrap import ensure_initial_scenario

    release = ensure_initial_scenario(repository).release
    assert release is not None
    base = repository.load_revision(release.revision_id)
    made: list[tuple[str, str]] = []
    for index, name in enumerate(names):
        created = repository.create_scenario(
            ScenarioCreate(
                scenario_name=name,
                source_simulation_code=f"CASE-{index}",
                source_simulation_name=name,
                source_type="DUCKDB_SCENARIO_CLONE",
                pipeline_version="duckdb-rq-snapshot-v3",
            ),
            {table: frame.copy() for table, frame in base.tables.items()},
            base.preset,
        )
        made.append((str(created.scenario.scenario_id), str(created.revision.revision_id)))
    return made


def test_an_unsaved_profile_reads_as_four_blanks(tmp_path: Path) -> None:
    """한 번도 저장하지 않은 상태가 정상이다. 여기서 죽으면 첫 저장 전까지 HOME 이 안 열린다."""
    profile = _repository(tmp_path).load_global_main_cases()

    assert (profile.version, profile.updated_at, profile.source) == (0, None, "")
    assert profile.case(1) == (None, None)
    assert profile.case(2) == (None, None)


def test_one_case_round_trips_and_leaves_the_other_alone(tmp_path: Path) -> None:
    """Case 하나를 바꾸는 저장은 다른 Case 칸을 그대로 옮겨 적는다 — 통째 교체가 아니다."""
    repository = _repository(tmp_path)

    first = repository.replace_global_main_case(1, "S1", "R1", source="테스트")
    assert (first.case(1), first.case(2), first.version) == (("S1", "R1"), (None, None), 1)

    second = repository.replace_global_main_case(2, "S2", "R2", source="다른 사용자")
    assert (second.case(1), second.case(2), second.version) == (("S1", "R1"), ("S2", "R2"), 2)
    assert second.source == "다른 사용자"

    reloaded = repository.load_global_main_cases()
    assert (reloaded.case(1), reloaded.case(2)) == (("S1", "R1"), ("S2", "R2"))


def test_clearing_a_case_is_a_normal_save(tmp_path: Path) -> None:
    """지정 해제도 저장이고 version 이 올라야 한다 — 다른 세션 캐시가 version 을 본다."""
    repository = _repository(tmp_path)
    repository.replace_global_main_case(1, "S1", "R1", source="테스트")
    repository.replace_global_main_case(2, "S2", "R2", source="테스트")

    cleared = repository.replace_global_main_case(1, None, None, source="해제")

    assert (cleared.case(1), cleared.case(2), cleared.version) == ((None, None), ("S2", "R2"), 3)


def test_a_revision_without_its_scenario_and_a_third_case_are_rejected(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    with pytest.raises(ValueError, match="시나리오를 함께"):
        repository.replace_global_main_case(1, None, "R1", source="테스트")
    with pytest.raises(ValueError, match="1·2 뿐"):
        repository.replace_global_main_case(3, "S1", "R1", source="테스트")
    assert repository.load_global_main_cases().version == 0


def test_the_table_itself_refuses_a_revision_without_its_scenario(tmp_path: Path) -> None:
    """저장소 검증을 거치지 않는 쓰기(스크립트)도 짝 없는 리비전을 남기지 못한다(0036 `CHECK`)."""
    database = tmp_path / "scenario.duckdb"
    DuckDBScenarioRepository(database).initialize()

    with duckdb.connect(str(database)) as connection, pytest.raises(duckdb.ConstraintException):
        connection.execute(
            "INSERT INTO app_meta.global_main_cases"
            " (profile_id, case2_revision_id, version, source) VALUES (1, 'R', 1, 'x')"
        )


def test_a_stale_expected_version_writes_nothing(tmp_path: Path) -> None:
    """화면이 스스로 메우는 쓰기는 본 version 을 대조한다 — 그 사이 남이 고른 값을 덮지 않는다."""
    repository = _repository(tmp_path)
    seen = repository.replace_global_main_case(1, "S1", None, source="본 값")
    repository.replace_global_main_case(1, "S9", "R9", source="다른 사용자")

    with pytest.raises(ProfileVersionConflict):
        repository.replace_global_main_case(
            1, "S1", "R1", source="메움", expected_version=seen.version
        )

    after = repository.load_global_main_cases()
    assert (after.case(1), after.version) == (("S9", "R9"), 2)
    filled = repository.replace_global_main_case(
        1, "S9", "R8", source="메움", expected_version=after.version
    )
    assert filled.case(1) == ("S9", "R8")


def test_renaming_a_pointed_scenario_bumps_only_the_version(tmp_path: Path) -> None:
    """슬롯 글자가 시나리오 이름을 쓴다 — 이름만 바꿔도 version 이 올라야 그 키의 캐시가 풀린다.

    가리키지 않는 시나리오 이름은 건드리지 않는다. 목록 편집(C안)의 이름 바꾸기도 같은 길이다.
    """
    repository = _repository(tmp_path)
    (pointed, pointed_revision), (other, _) = _scenarios(repository, "가리킨 것", "다른 것")
    repository.replace_global_main_case(2, pointed, pointed_revision, source="테스트")

    repository.rename_scenario(pointed, "새 이름")
    renamed = repository.load_global_main_cases()
    assert (renamed.case(2), renamed.version) == ((pointed, pointed_revision), 2)

    repository.rename_scenario(other, "다른 새 이름")
    assert repository.load_global_main_cases().version == 2

    repository.apply_scenario_list_edits({pointed: ("새 이름", "또 새 이름")})
    assert repository.load_global_main_cases().version == 3


@pytest.mark.parametrize("action", ["archive_scenario", "delete_scenario"])
def test_removing_a_scenario_clears_only_the_cases_pointing_at_it(
    tmp_path: Path, action: str
) -> None:
    """보관·영구 삭제는 그 시나리오를 가리키는 Case 만 비우고 행은 남긴다(version+1).

    자동 발견이 이 표를 시나리오 소유로 보면 영구 삭제가 단일 행을 통째로 지워 다른 Case 까지
    사라지고 version 도 오르지 않는다.
    """
    repository = _repository(tmp_path)
    (doomed, doomed_revision), (kept, kept_revision) = _scenarios(repository, "지울 것", "남길 것")
    repository.replace_global_main_case(1, doomed, doomed_revision, source="테스트")
    before = repository.replace_global_main_case(2, kept, kept_revision, source="테스트")

    getattr(repository, action)(doomed)

    after = repository.load_global_main_cases()
    assert after.case(1) == (None, None)
    assert after.case(2) == (kept, kept_revision)
    assert after.version == before.version + 1


def test_removing_a_scenario_that_both_cases_point_at_clears_both(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    ((doomed, doomed_revision),) = _scenarios(repository, "둘이 가리킨 것")
    repository.replace_global_main_case(1, doomed, doomed_revision, source="테스트")
    repository.replace_global_main_case(2, doomed, doomed_revision, source="테스트")

    repository.archive_scenario(doomed)
    after = repository.load_global_main_cases()
    assert (after.case(1), after.case(2), after.version) == ((None, None), (None, None), 3)

    # 되돌려도 지정은 돌아오지 않는다 — 비교 시나리오와 같다.
    repository.restore_scenario(doomed)
    assert repository.load_global_main_cases().case(1) == (None, None)


def test_removing_an_unpointed_scenario_writes_nothing(tmp_path: Path) -> None:
    """가리키지 않는 시나리오의 보관·삭제·화면 비우기는 version 을 올리지 않는다(조건부 UPDATE)."""
    repository = _repository(tmp_path)
    (pointed, pointed_revision), (other, _) = _scenarios(repository, "가리킨 것", "무관한 것")
    before = repository.replace_global_main_case(1, pointed, pointed_revision, source="테스트")

    repository.delete_scenario(other)
    repository.clear_global_main_case_scenario("없는-시나리오")

    assert repository.load_global_main_cases() == before
