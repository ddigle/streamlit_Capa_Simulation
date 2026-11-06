# Purpose: 두 Repository 쓰기 경계가 커밋·연결 닫기 뒤 잠금 안에서 변경 표시를 남기는지 검증한다.

"""변경 표시와 쓰기 잠금의 차례.

업로더가 두 쓰기 잠금을 잡고 변경 표시를 읽을 때 「커밋은 됐는데 표시는 아직」인 쓰기가 없어야
「바뀌지 않은 DB」 판단이 맞다. 그래서 표시는 COMMIT 하고 연결을 닫은 **뒤**, 잠금을 놓기
**전**이다.
연결 수명(표시 전에 닫힘)과 잠금 차례(잠금 → 연결)는 그대로여야 한다.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from pathlib import Path
from types import ModuleType

import duckdb
import pytest

from capa_simulation.persistence import equipment_repository, repository, sync_state
from capa_simulation.persistence._sql_helpers import connect
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.persistence.repository import DuckDBScenarioRepository

WriteTransaction = Callable[[], AbstractContextManager[duckdb.DuckDBPyConnection]]


@pytest.fixture(autouse=True)
def _isolated_registry() -> Iterator[None]:
    sync_state.clear_all()
    yield
    sync_state.clear_all()


def _boundaries(tmp_path: Path) -> list[tuple[ModuleType, Path, WriteTransaction]]:
    simulation = DuckDBScenarioRepository(tmp_path / "capa_simulation.duckdb")
    equipment = DuckDBEquipmentRepository(tmp_path / "equipment_availability.duckdb")
    return [
        (repository, simulation.database_path, simulation._write_transaction),
        (equipment_repository, equipment.database_path, equipment._write_transaction),
    ]


def _lock_is_free_elsewhere(lock: threading.RLock) -> bool:
    """다른 스레드에서 잠금을 바로 잡을 수 있는가. RLock 은 잡은 스레드에서는 늘 다시 잡힌다."""
    outcome: list[bool] = []

    def probe() -> None:
        acquired = lock.acquire(blocking=False)
        if acquired:
            lock.release()
        outcome.append(acquired)

    worker = threading.Thread(target=probe)
    worker.start()
    worker.join(5)
    return outcome[0]


class _MarkProbe:
    """`mark_dirty` 자리에서 잠금·연결·커밋 상태를 적는다."""

    def __init__(self, module: ModuleType) -> None:
        self.module = module
        self.connection: duckdb.DuckDBPyConnection | None = None
        self.seen: dict[str, object] = {}

    def __call__(self, path: Path) -> None:
        self.seen["lock_free_elsewhere"] = _lock_is_free_elsewhere(self.module._WRITE_LOCK)
        assert self.connection is not None
        try:
            self.connection.execute("SELECT 1")
            self.seen["connection_open"] = True
        except duckdb.Error:
            self.seen["connection_open"] = False
        with connect(path) as reader:
            row = reader.execute("SELECT COUNT(*) FROM probe_table").fetchone()
        self.seen["committed_rows"] = None if row is None else int(row[0])


def test_the_change_mark_lands_after_close_and_before_the_lock_is_released(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for module, database_path, write_transaction in _boundaries(tmp_path):
        probe = _MarkProbe(module)
        monkeypatch.setattr(sync_state, "mark_dirty", probe)
        with write_transaction() as connection:
            probe.connection = connection
            connection.execute("CREATE TABLE probe_table AS SELECT 1 AS x")

        assert probe.seen == {
            "lock_free_elsewhere": False,
            "connection_open": False,
            "committed_rows": 1,
        }, (module.__name__, database_path)
        assert _lock_is_free_elsewhere(module._WRITE_LOCK)


def test_a_rolled_back_write_leaves_no_mark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marks: list[Path] = []
    monkeypatch.setattr(sync_state, "mark_dirty", marks.append)

    for module, _database_path, write_transaction in _boundaries(tmp_path):
        with pytest.raises(RuntimeError, match="되돌림"):
            with write_transaction() as connection:
                connection.execute("CREATE TABLE rolled_back AS SELECT 1 AS x")
                raise RuntimeError("되돌림")
        assert _lock_is_free_elsewhere(module._WRITE_LOCK)

    assert marks == []


def test_local_mode_writes_create_no_sidecar(tmp_path: Path) -> None:
    """등록이 없으면(개발 PC 기본 local) 저장이 사이드카를 만들지 않는다 — 지금 동작 그대로다."""
    for _module, database_path, write_transaction in _boundaries(tmp_path):
        with write_transaction() as connection:
            connection.execute("CREATE TABLE local_only AS SELECT 1 AS x")

        assert not sync_state.sidecar_path(database_path).exists()


def test_an_official_release_asks_for_an_upload_at_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """공식 발행은 모으지 않는다. 자동 갱신의 발행도 같은 자리를 지난다."""
    source = (Path(repository.__file__)).read_text(encoding="utf-8")
    start = source.index("def publish_official_revision")
    end = source.index("def latest_official_release", start)

    assert "sync_state.request_upload()" in source[start:end]


@pytest.mark.parametrize(
    ("published", "wrote", "expected"),
    [(True, True, ["mark", "upload"]), (False, True, ["mark"]), (False, False, [])],
)
def test_equipment_writes_ask_for_an_upload_only_when_they_published(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    published: bool,
    wrote: bool,
    expected: list[str],
) -> None:
    """설비 발행은 저장 안(마스터 저장 · 되돌리기)에서도 난다 — 한 자리에서 부른다."""
    calls: list[str] = []
    monkeypatch.setattr(sync_state, "mark_dirty", lambda _path: calls.append("mark"))
    monkeypatch.setattr(sync_state, "request_upload", lambda: calls.append("upload"))
    store = DuckDBEquipmentRepository(tmp_path / "equipment_availability.duckdb")
    outcome = equipment_repository._WriteOutcome(wrote=wrote, published=published)

    with store._write_transaction(outcome) as connection:
        connection.execute("SELECT 1")

    assert calls == expected


def test_every_equipment_release_marks_the_outcome() -> None:
    """`insert_release` 를 부르는 자리는 모두 발행 표시를 세운다. 빠지면 그 발행은 모아서 간다."""
    source = Path(equipment_repository.__file__).read_text(encoding="utf-8")

    assert source.count("scenario_store.insert_release(") == 3
    assert source.count("outcome.published = ") == 3
