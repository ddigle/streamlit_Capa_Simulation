# Purpose: 공용 공정 그룹 프로필의 저장소 읽기 · 교체 · 버전 대조 · 벽 · 감사 줄 · 캐시를 지킨다.

"""공정 그룹 저장소(`repository.load_global_process_group` · `replace_global_process_group`).

한 번도 저장하지 않은 상태가 정상이고(version 0 · 빈 대응, 예외 · 쓰기 없음), 교체마다 version 이
오른다(0행 교체 포함). 편집 시작 version 이 다르면 아무것도 쓰지 않고, 검증은 쓰기 잠금 전에 끝난다.
시나리오 삭제 · 보관은 이 공용 프로필을 건드리지 않는다. 벽은 `data_profile_save` 의 바닥이다 — HOME
설정에서 관리자가 저장할 수 있어야 한다. 공정 이름은 모두 합성(`DEMO_*`)이다.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import NoReturn

import duckdb
import pytest
from grade_support import action_of
from test_duckdb_repository import _metadata, _reference_tables

import capa_simulation.persistence.cache as scenario_cache
from capa_simulation.audit import recorder
from capa_simulation.persistence._sql_helpers import ProfileVersionConflict
from capa_simulation.persistence.models import ScenarioPreset
from capa_simulation.persistence.process_group_store import (
    PROCESS_GROUP_HEADER_TABLE,
    PROCESS_GROUP_ITEM_TABLE,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository

ACTOR = "demo.writer"


@pytest.fixture()
def repository(tmp_path: Path) -> DuckDBScenarioRepository:
    repo = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    repo.initialize()
    return repo


def _row_counts(repository: DuckDBScenarioRepository) -> tuple[int, int]:
    with duckdb.connect(str(repository.database_path)) as connection:
        header = connection.execute(
            f"SELECT count(*) FROM app_meta.{PROCESS_GROUP_HEADER_TABLE}"
        ).fetchone()
        items = connection.execute(
            f"SELECT count(*) FROM app_meta.{PROCESS_GROUP_ITEM_TABLE}"
        ).fetchone()
    assert header is not None and items is not None
    return int(header[0]), int(items[0])


def test_the_profile_is_absent_until_the_first_save(repository: DuckDBScenarioRepository) -> None:
    profile = repository.load_global_process_group()

    assert profile.version == 0
    assert profile.source == ""
    assert profile.updated_at is None
    assert profile.assignments == ()
    assert _row_counts(repository) == (0, 0)


def test_replacing_saves_normalized_assignments_and_raises_the_version(
    repository: DuckDBScenarioRepository,
) -> None:
    first = repository.replace_global_process_group(
        [("DEMO_WB", "pkg"), (" DEMO_DA ", "FRONT"), ("DEMO_SAW", None)], source="TEST 붙여넣기"
    )

    assert first.version == 1
    assert first.source == "TEST 붙여넣기"
    assert first.updated_at is not None
    assert first.assignments == (("DEMO_DA", "FRONT"), ("DEMO_WB", "PKG"))
    assert repository.load_global_process_group() == first


def test_clearing_every_assignment_still_raises_the_version(
    repository: DuckDBScenarioRepository,
) -> None:
    repository.replace_global_process_group([("DEMO_DA", "FRONT")], source="TEST")

    cleared = repository.replace_global_process_group([], source="TEST 모두 비움")

    assert cleared.version == 2
    assert cleared.assignments == ()
    assert _row_counts(repository) == (1, 0)


def test_the_same_process_can_change_group_in_one_replace(
    repository: DuckDBScenarioRepository,
) -> None:
    """같은 트랜잭션에서 같은 공정 행을 지웠다 다시 넣는 통째 교체가 열쇠에 걸리지 않는다."""
    repository.replace_global_process_group(
        [("DEMO_DA", "FRONT"), ("DEMO_WB", "PKG")], source="TEST"
    )

    moved = repository.replace_global_process_group(
        [("DEMO_DA", "PKG"), ("DEMO_WB", "PKG")], source="TEST"
    )
    again = repository.replace_global_process_group(
        [("DEMO_DA", "FRONT"), ("DEMO_WB", "PKG")], source="TEST"
    )

    assert moved.assignments == (("DEMO_DA", "PKG"), ("DEMO_WB", "PKG"))
    assert again.version == 3
    assert again.assignments == (("DEMO_DA", "FRONT"), ("DEMO_WB", "PKG"))


def test_a_stale_expected_version_writes_nothing(repository: DuckDBScenarioRepository) -> None:
    repository.replace_global_process_group(
        [("DEMO_DA", "FRONT")], source="TEST", expected_version=0
    )
    stored = repository.load_global_process_group()

    with pytest.raises(ProfileVersionConflict) as caught:
        repository.replace_global_process_group(
            [("DEMO_DA", "PKG")], source="TEST", expected_version=0
        )

    assert (caught.value.expected, caught.value.stored) == (0, 1)
    assert "공정 그룹을 저장해" in str(caught.value)
    assert repository.load_global_process_group() == stored


@contextmanager
def _no_write_lock(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    def refuse(self: DuckDBScenarioRepository) -> NoReturn:
        raise AssertionError("검증 전에 쓰기 잠금을 잡았다")

    with monkeypatch.context() as patch:
        patch.setattr(DuckDBScenarioRepository, "_write_transaction", refuse)
        yield


@pytest.mark.parametrize(
    ("assignments", "source", "message"),
    [
        ([("DEMO_DA", "DEMO_X")], "TEST", "가운데 하나입니다: DEMO_X"),
        ([("DEMO_DA", "FRONT"), ("DEMO_DA", "PKG")], "TEST", "같은 공정이 두 줄"),
        ([("DEMO_DA", "FRONT")], "   ", "공정 그룹 변경 출처는 비어 있을 수 없습니다"),
    ],
    ids=["unknown-group", "duplicate-process", "blank-source"],
)
def test_a_bad_save_is_refused_before_the_write_lock(
    repository: DuckDBScenarioRepository,
    monkeypatch: pytest.MonkeyPatch,
    assignments: list[tuple[object, object]],
    source: str,
    message: str,
) -> None:
    with _no_write_lock(monkeypatch), pytest.raises(ValueError, match=message):
        repository.replace_global_process_group(assignments, source=source)

    assert repository.load_global_process_group().version == 0


def test_removing_or_archiving_a_scenario_keeps_the_assignments(
    repository: DuckDBScenarioRepository,
) -> None:
    preset = ScenarioPreset(202608, 202608, ("Process-A",))
    hidden = repository.create_scenario(_metadata("Hidden"), _reference_tables(), preset)
    doomed = repository.create_scenario(_metadata("Doomed"), _reference_tables(), preset)
    saved = repository.replace_global_process_group(
        [("Process-A", "FRONT"), ("DEMO_LOG", "물류")], source="TEST"
    )

    repository.archive_scenario(hidden.scenario.scenario_id)
    repository.delete_scenario(doomed.scenario.scenario_id)

    assert repository.load_global_process_group() == saved


def test_the_write_wall_is_the_home_settings_floor() -> None:
    """`action=` 을 주지 않아 `data_profile_save` 의 바닥이 벽이다 — HOME 설정의 형제 쓰기와 같고,
    Admin 몫 공용 프로필(공정 표시명)의 `admin.area` 가 아니다."""
    owner = DuckDBScenarioRepository

    assert action_of(owner.replace_global_key_process_presets) == "home.settings"
    assert action_of(owner.replace_global_process_group) == "home.settings"
    assert action_of(owner.replace_global_process_rename) == "admin.area"


def test_a_save_leaves_one_profile_line_without_process_names(
    repository: DuckDBScenarioRepository,
) -> None:
    recorder.start(env="cdep", version="test", inst="cdcdcdcdcdcd")
    recorder.set_resolver(lambda: recorder.Actor(ACTOR, True, "user"))

    repository.replace_global_process_group(
        [("DEMO_DA", "FRONT"), ("DEMO_WB", "PKG")], source="TEST"
    )

    lines = [line for line in recorder.take_pending() if line["ev"].startswith("data_")]
    assert [line["ev"] for line in lines] == ["data_profile_save"]
    assert lines[0]["tgt"] == {"type": "profile", "id": "process_group"}
    assert lines[0]["det"] == {
        "profile": "process_group",
        "version_to": 1,
        "source": "TEST",
        "rows": 2,
    }
    assert "DEMO_DA" not in json.dumps(lines, ensure_ascii=False)


def test_the_cached_profile_is_read_again_only_after_a_clear(
    repository: DuckDBScenarioRepository,
) -> None:
    path = str(repository.database_path)
    scenario_cache.clear_global_process_group_cache()
    assert scenario_cache.load_global_process_group(path).version == 0

    repository.replace_global_process_group([("DEMO_DA", "FRONT")], source="TEST")
    stale = scenario_cache.load_global_process_group(path)
    scenario_cache.clear_global_process_group_cache()
    fresh = scenario_cache.load_global_process_group(path)

    assert stale.version == 0
    assert fresh.version == 1
    assert fresh.assignments == (("DEMO_DA", "FRONT"),)
