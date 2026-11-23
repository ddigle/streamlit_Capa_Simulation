# Purpose: 부하 예외 선언 판 이력(마이그레이션 0040)의 저장 · 대조 · 비움 · 표 없음 읽기와
# 즉시 올림 · 감사 · 공용 프로필 캐시를 본다.

"""부하 예외 선언 저장소(`repository.*route_load_exceptions*` ·
`persistence/route_load_exception_store.py`).

판 이력은 넣기만 하고 마지막 줄이 지금 선언이다. 쓰기는 화면이 본 판 차례와 대조하고, 견줌 키로 같은
선언은 쓰지 않으며, 모르는 산식 id 는 표에 들어가기 전에 멈춘다. 표에는 소유 칸이 없어 시나리오를
지워도 남는다. 쓰기는 공식 발행처럼 COMMIT 뒤에 바로 올림을 청한다. 공정은 합성 `DEMO-*` 다.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import duckdb
import pytest
from auto_update_fakes import new_repository
from before_custom_copy import database_before_custom

from capa_simulation.audit import recorder
from capa_simulation.auth import grades
from capa_simulation.persistence import cache as scenario_cache
from capa_simulation.persistence import sync_state
from capa_simulation.persistence.models import RouteLoadExceptionProfile
from capa_simulation.persistence.repository import DuckDBScenarioRepository, _owned_tables
from capa_simulation.persistence.route_load_exception_store import (
    ROUTE_LOAD_EXCEPTION_SCHEMA,
    ROUTE_LOAD_EXCEPTION_TABLE,
    RouteLoadExceptionMoved,
    RouteLoadExceptionUnchanged,
    has_route_load_exception_table,
    read_route_load_exceptions,
)
from capa_simulation.services.route_load_exceptions import (
    BUFFER_X_CORE_CHIP,
    route_load_declaration_digest,
)

TABLE = f"{ROUTE_LOAD_EXCEPTION_SCHEMA}.{ROUTE_LOAD_EXCEPTION_TABLE}"
TWO = {"DEMO-P2": BUFFER_X_CORE_CHIP, "DEMO-P1": BUFFER_X_CORE_CHIP}


@pytest.fixture
def repository(tmp_path: Path) -> DuckDBScenarioRepository:
    return new_repository(tmp_path / "route.duckdb")


def _append(
    repository: DuckDBScenarioRepository, entries: dict[str, str], *, expected_seq: int
) -> int:
    return repository.append_route_load_exceptions(
        expected_seq=expected_seq,
        entries=entries,
        applied_by="개발자 A",
        source_place="test",
    ).seq


def _rows(repository: DuckDBScenarioRepository) -> list[tuple[Any, ...]]:
    with repository._connect() as connection:
        return connection.execute(
            f"SELECT seq, entries_json, entry_count, digest, applied_by, source_place FROM {TABLE} "
            "ORDER BY seq"
        ).fetchall()


def test_an_empty_store_has_no_declaration(repository: DuckDBScenarioRepository) -> None:
    state = repository.load_route_load_exceptions()
    profile = repository.load_global_route_load_exceptions()

    assert state.history == () and state.current is None
    assert (state.seq, state.entries, state.digest, dict(state.declaration)) == (0, (), "", {})
    assert profile == RouteLoadExceptionProfile(
        seq=0, created_at=None, applied_by=None, entries=(), digest=""
    )


def test_a_version_keeps_the_original_names_and_the_digest_of_the_match_keys(
    repository: DuckDBScenarioRepository,
) -> None:
    state = repository.append_route_load_exceptions(
        expected_seq=0, entries=TWO, applied_by="  개발자 A  ", source_place="test"
    )

    current = state.current
    assert current is not None and state.seq == current.seq == 1
    assert current.entries == (("DEMO-P1", BUFFER_X_CORE_CHIP), ("DEMO-P2", BUFFER_X_CORE_CHIP))
    assert dict(state.declaration) == TWO and current.process_count == 2
    assert current.digest == route_load_declaration_digest(TWO) != ""
    assert current.applied_by == "개발자 A" and current.source_place == "test"
    assert _rows(repository) == [
        (
            1,
            '{"DEMO-P1":"buffer_x_core_chip","DEMO-P2":"buffer_x_core_chip"}',
            2,
            current.digest,
            "개발자 A",
            "test",
        )
    ]
    profile = repository.load_global_route_load_exceptions()
    assert (profile.seq, profile.entries, profile.digest) == (1, current.entries, current.digest)
    assert profile.created_at == current.created_at


def test_the_declaration_is_a_read_only_mapping(repository: DuckDBScenarioRepository) -> None:
    _append(repository, TWO, expected_seq=0)
    declaration = repository.load_global_route_load_exceptions().declaration

    with pytest.raises(TypeError):
        declaration["DEMO-P3"] = BUFFER_X_CORE_CHIP  # type: ignore[index]


def test_clearing_after_a_declaration_is_a_version_of_its_own(
    repository: DuckDBScenarioRepository,
) -> None:
    _append(repository, TWO, expected_seq=0)
    cleared = repository.append_route_load_exceptions(
        expected_seq=1, entries={}, applied_by=None, source_place=None
    )

    assert cleared.seq == 2 and cleared.entries == () and cleared.digest == ""
    assert dict(cleared.declaration) == {}
    assert [item.seq for item in cleared.history] == [1, 2]
    assert _rows(repository)[-1] == (2, "{}", 0, "", None, None)
    assert repository.load_global_route_load_exceptions().entries == ()


@pytest.mark.parametrize(
    ("first", "again"),
    [
        ({}, {}),
        (TWO, dict(TWO)),
        (TWO, {"demo-p1": BUFFER_X_CORE_CHIP, " DEMO-P2 ": BUFFER_X_CORE_CHIP}),
    ],
    ids=["empty-on-empty", "same", "spelling-only"],
)
def test_a_declaration_equal_by_match_keys_writes_nothing(
    repository: DuckDBScenarioRepository, first: dict[str, str], again: dict[str, str]
) -> None:
    """견줌 키로 같은 선언은 쓰지 않는다 — 한 번도 저장하지 않은 표에 비움을 넣는 것도 같다."""
    seen = 0
    if first:
        seen = _append(repository, first, expected_seq=0)
    before = _rows(repository)

    with pytest.raises(RouteLoadExceptionUnchanged) as caught:
        _append(repository, again, expected_seq=seen)

    assert caught.value.current == seen
    assert _rows(repository) == before


def test_a_stale_screen_writes_nothing(repository: DuckDBScenarioRepository) -> None:
    _append(repository, TWO, expected_seq=0)

    with pytest.raises(RouteLoadExceptionMoved) as stale:
        _append(repository, {}, expected_seq=0)
    with pytest.raises(RouteLoadExceptionMoved):
        _append(repository, {}, expected_seq=2)

    assert (stale.value.expected, stale.value.current) == (0, 1)
    assert [row[0] for row in _rows(repository)] == [1]


@pytest.mark.parametrize(
    "entries",
    [
        {"DEMO-P1": "no_such_formula"},
        {"   ": BUFFER_X_CORE_CHIP},
    ],
    ids=["unknown-formula", "blank-process"],
)
def test_an_entry_the_code_does_not_know_is_refused_before_the_write(
    repository: DuckDBScenarioRepository, entries: dict[str, str]
) -> None:
    with pytest.raises(ValueError, match="부하 예외 선언에"):
        _append(repository, entries, expected_seq=0)

    assert _rows(repository) == []


def test_the_history_belongs_to_no_scenario(repository: DuckDBScenarioRepository) -> None:
    """소유 칸이 없다 — 시나리오 영구 삭제가 `_owned_tables` 로 지울 표를 찾을 때 걸리지 않는다."""
    with repository._connect() as connection:
        owned = {(schema, table) for schema, table, _ in _owned_tables(connection)}

    assert (ROUTE_LOAD_EXCEPTION_SCHEMA, ROUTE_LOAD_EXCEPTION_TABLE) not in owned


def test_a_copy_before_the_table_reads_none_and_stays_without_it(tmp_path: Path) -> None:
    """확인 스크립트가 마이그레이션하지 않고 여는 0040 전 사본 — 읽기는 `None` 이고 표를 만들지
    않는다."""
    source = new_repository(tmp_path / "source.duckdb").database_path
    copy = database_before_custom(source, tmp_path / "before.duckdb")

    with duckdb.connect(str(copy), read_only=True) as connection:
        assert read_route_load_exceptions(connection) is None
        assert not has_route_load_exception_table(connection)
    with duckdb.connect(str(source), read_only=True) as connection:
        state = read_route_load_exceptions(connection)
        assert state is not None and state.history == ()


def _sync_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(sync_state, "mark_dirty", lambda _path: calls.append("mark"))
    monkeypatch.setattr(sync_state, "request_upload", lambda: calls.append("upload"))
    return calls


def test_a_new_version_asks_for_an_upload_after_the_commit(
    repository: DuckDBScenarioRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """선언은 모든 시나리오의 숫자를 바꾸는 쓰기라 모으지 않는다 — 변경 표시(COMMIT 뒤) 다음에
    올림."""
    calls = _sync_calls(monkeypatch)

    _append(repository, TWO, expected_seq=0)

    assert calls == ["mark", "upload"]


@pytest.mark.parametrize(
    "write",
    [
        lambda repository: _append(repository, TWO, expected_seq=5),
        lambda repository: _append(repository, {}, expected_seq=0),
        lambda repository: _append(repository, {"DEMO-P1": "no_such_formula"}, expected_seq=0),
    ],
    ids=["moved", "unchanged", "refused"],
)
def test_a_write_that_writes_nothing_marks_and_uploads_nothing(
    repository: DuckDBScenarioRepository,
    monkeypatch: pytest.MonkeyPatch,
    write: Callable[[DuckDBScenarioRepository], int],
) -> None:
    calls = _sync_calls(monkeypatch)

    with pytest.raises(ValueError):
        write(repository)

    assert calls == []


def _audit_lines(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []

    def capture(event: str, **fields: Any) -> None:
        lines.append({"ev": event, **fields})

    monkeypatch.setattr(recorder, "record", capture)
    return lines


def test_the_audit_line_has_the_version_and_the_count_but_no_names(
    repository: DuckDBScenarioRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    lines = _audit_lines(monkeypatch)

    _append(repository, TWO, expected_seq=0)
    with pytest.raises(RouteLoadExceptionUnchanged):
        _append(repository, TWO, expected_seq=1)
    with pytest.raises(RouteLoadExceptionMoved):
        _append(repository, {}, expected_seq=0)

    assert lines == [
        {
            "ev": "admin_route_load_exception",
            "claimed": "개발자 A",
            "det": {"entry": 1, "processes": 2},
        },
        {"ev": "admin_route_load_exception", "out": "fail", "claimed": "개발자 A"},
    ]
    assert "DEMO" not in repr(lines) and route_load_declaration_digest(TWO) not in repr(lines)


def test_the_write_sits_behind_the_admin_wall() -> None:
    write = DuckDBScenarioRepository.append_route_load_exceptions

    assert getattr(write, grades.GATE_ATTRIBUTE) == "admin.area"


def test_the_shared_profile_cache_reads_a_new_version_only_after_its_clear(
    repository: DuckDBScenarioRepository,
) -> None:
    """공용 프로필 캐시는 DB 경로 키다 — 판을 넣은 길이 비워야 새 판을 읽는다(AGENTS 5장 22)."""
    path = str(repository.database_path)
    scenario_cache.clear_global_route_load_exceptions_cache()
    assert scenario_cache.load_global_route_load_exceptions(path).seq == 0

    _append(repository, TWO, expected_seq=0)
    assert scenario_cache.load_global_route_load_exceptions(path).seq == 0

    scenario_cache.clear_global_route_load_exceptions_cache()
    profile = scenario_cache.load_global_route_load_exceptions(path)
    assert isinstance(profile, RouteLoadExceptionProfile)
    assert (profile.seq, dict(profile.declaration)) == (1, TWO)
    assert profile.digest == route_load_declaration_digest(TWO)


@pytest.mark.parametrize(
    ("left", "right", "same"),
    [
        ({}, {}, True),
        (TWO, {"demo-p2 ": BUFFER_X_CORE_CHIP, "Demo-P1": BUFFER_X_CORE_CHIP}, True),
        (TWO, {"DEMO-P1": BUFFER_X_CORE_CHIP}, False),
    ],
    ids=["empty", "spelling", "fewer"],
)
def test_the_digest_follows_the_match_keys(
    left: dict[str, str], right: dict[str, str], same: bool
) -> None:
    assert (route_load_declaration_digest(left) == route_load_declaration_digest(right)) is same
    assert route_load_declaration_digest({}) == ""
