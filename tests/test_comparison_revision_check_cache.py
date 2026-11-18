# Purpose: HOME 비교 짝 확인이 세대 캐시로 DB 를 덜 열되 늦은 리비전 · 삭제를 놓치지 않는지 본다.

"""비교 시나리오의 리비전 목록은 비교 대상 프로필과 같은 쓰기 세대로
캐시한다(`scenario_has_revision` — 다시 도는 범위 C2 (나)).

리비전은 append-only 라 목록에 든 리비전은 보관 · 영구 삭제 전까지 든다 — 그 둘은 비교 세대를
올린다(`clear_global_comparison_scenario_cache`). 새로 저장한 리비전은 세대를 올리지 않으므로 목록에
없으면 DB 로 한 번 더 본다. 저장소는 부른 횟수를 세는 대역이다.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from uuid import uuid4

import pytest

import capa_simulation.persistence.cache as scenario_cache


class _Repository:
    def __init__(self) -> None:
        self.revisions: dict[str, list[str]] = {"S": ["r1"]}
        self.calls = 0

    def list_revisions(self, scenario_id: str) -> list[SimpleNamespace]:
        self.calls += 1
        return [SimpleNamespace(revision_id=item) for item in self.revisions.get(scenario_id, [])]


@pytest.fixture
def repository(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Repository]:
    fake = _Repository()
    monkeypatch.setattr(scenario_cache, "get_scenario_repository", lambda _path: fake)
    yield fake


def _path() -> str:
    # 캐시는 프로세스 전역이다 — 시험마다 다른 경로 키를 쓴다.
    return f"test-revision-check-{uuid4().hex}"


def test_a_listed_revision_is_answered_from_the_cache(repository: _Repository) -> None:
    path = _path()
    assert scenario_cache.scenario_has_revision(path, "S", "r1")
    assert scenario_cache.scenario_has_revision(path, "S", "r1")
    assert repository.calls == 1


def test_a_revision_saved_after_the_cache_is_found_in_the_database(
    repository: _Repository,
) -> None:
    """새로 저장한 리비전은 세대를 올리지 않는다 — 캐시 목록에 없으면 DB 로 한 번 더 본다."""
    path = _path()
    assert scenario_cache.scenario_has_revision(path, "S", "r1")
    repository.revisions["S"].append("r2")

    assert scenario_cache.scenario_has_revision(path, "S", "r2")
    assert repository.calls == 2


def test_a_revision_of_another_scenario_is_always_checked_against_the_database(
    repository: _Repository,
) -> None:
    """아니라는 답은 늘 지금 DB 의 답이다(캐시 목록 · DB 둘 다 본다)."""
    path = _path()
    assert not scenario_cache.scenario_has_revision(path, "S", "elsewhere")
    assert not scenario_cache.scenario_has_revision(path, "S", "elsewhere")
    assert repository.calls == 3


def test_removing_the_scenario_bumps_the_comparison_generation_and_the_answer(
    repository: _Repository,
) -> None:
    """보관 · 영구 삭제는 비교 세대를 올린다(`clear_global_comparison_scenario_cache`) — 그 뒤에는
    지운 시나리오의 리비전을 아니라고 한다. 세대를 올리기 전에는 캐시 목록이 답한다(그 사이는
    `load_scenario_plan` 의 `KeyError` 와 비교 후보 목록이 거른다)."""
    path = _path()
    assert scenario_cache.scenario_has_revision(path, "S", "r1")
    repository.revisions["S"] = []
    assert scenario_cache.scenario_has_revision(path, "S", "r1")

    scenario_cache.clear_global_comparison_scenario_cache()

    assert not scenario_cache.scenario_has_revision(path, "S", "r1")
