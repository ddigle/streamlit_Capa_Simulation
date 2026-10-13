# Purpose: rerun 동안 DuckDB 인스턴스를 잡아 두는 게으른 핀(첫 연결 때 잡기·겹침·풀림)을 고정한다.

import threading
from pathlib import Path
from typing import Any

import duckdb
import pytest

from capa_simulation.persistence import _sql_helpers
from capa_simulation.persistence._sql_helpers import connect, pinned_connections


def _fresh_database(tmp_path: Path) -> tuple[Path, Path]:
    database = tmp_path / "pin.duckdb"
    with connect(database) as connection:
        connection.execute("CREATE TABLE probe(x INTEGER)")
    wal = tmp_path / "pin.duckdb.wal"
    assert not wal.exists()
    return database, wal


def _insert(database: Path, value: int) -> None:
    with connect(database) as connection:
        connection.execute("INSERT INTO probe VALUES (?)", [value])


def _count(database: Path) -> int:
    with connect(database) as connection:
        row = connection.execute("SELECT count(*) FROM probe").fetchone()
    assert row is not None
    return int(row[0])


def test_pin_keeps_the_instance_alive_and_checkpoints_when_released(tmp_path: Path) -> None:
    """핀이 있는 동안 짧은 연결을 닫아도 인스턴스가 살아 있고, 풀리면 체크포인트가 돈다."""
    database, wal = _fresh_database(tmp_path)

    with pinned_connections(database):
        _insert(database, 1)
        # 인스턴스가 내려가지 않았으므로 체크포인트가 미뤄져 WAL 이 남아 있다. 핀이 없으면
        # 연결을 닫는 순간 인스턴스가 내려가며 WAL 이 사라진다 — 그것이 지금까지의 동작이다.
        assert wal.exists()

    assert not wal.exists()
    assert _count(database) == 1


def test_pin_releases_when_the_block_raises(tmp_path: Path) -> None:
    """st.stop()·st.rerun() 은 예외로 빠져나간다. 그때도 핀이 남아 상시 앵커가 되면 안 된다."""
    database, wal = _fresh_database(tmp_path)

    with pytest.raises(RuntimeError), pinned_connections(database):
        _insert(database, 1)
        raise RuntimeError("rerun")

    assert not wal.exists()
    assert _count(database) == 1


def test_pin_skips_files_it_cannot_open(tmp_path: Path) -> None:
    """열지 못하는 파일은 건너뛴다. 오류는 뒤의 실제 연결이 그 자리의 안내와 함께 낸다."""
    database, _ = _fresh_database(tmp_path)

    with pinned_connections(tmp_path / "missing" / "nowhere.duckdb", database):
        assert _count(database) == 0


# ----------------------------------------------------------------- 게으른 핀
#
# 핀은 블록 시작이 아니라 그 파일의 첫 `connect()` 때 잡는다. DB 를 한 번도 읽지 않는 rerun 은
# 인스턴스를 만들지 않고(블록 시작에 열면 회차마다 20ms 안팎), 읽는 rerun 은 인스턴스 하나를
# 나눠 쓰다 블록 끝에 닫혀 체크포인트가 돈다.


def _counting(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """`duckdb.connect` 실호출(실제 연결과 핀 모두)을 경로와 함께 적는다."""
    opened: list[str] = []
    real_connect = duckdb.connect

    def counted(*args: Any, **kwargs: Any) -> duckdb.DuckDBPyConnection:
        opened.append(str(args[0]))
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(duckdb, "connect", counted)
    return opened


def test_a_block_that_reads_nothing_opens_no_instance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """읽지 않는 화면의 rerun 은 DB 를 열지 않는다. 없는 파일을 만들지도 않는다."""
    database, wal = _fresh_database(tmp_path)
    missing = tmp_path / "never.duckdb"
    opened = _counting(monkeypatch)

    with pinned_connections(database, missing):
        pass

    assert opened == []
    assert not wal.exists()
    assert not missing.exists()


def test_the_pin_is_taken_once_on_the_first_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """첫 읽기 = 실제 연결 + 핀 하나, 그 뒤 읽기는 실제 연결뿐이다(인스턴스는 하나)."""
    database, wal = _fresh_database(tmp_path)
    opened = _counting(monkeypatch)

    with pinned_connections(database):
        assert opened == []
        _insert(database, 1)
        assert len(opened) == 2
        assert _count(database) == 1
        assert len(opened) == 3
        assert wal.exists()

    assert not wal.exists()


def test_relative_and_absolute_paths_share_one_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """app.py 는 `DUCKDB_PATH` 를 그대로, 저장소는 `resolve()` 한 경로로 연다 — 같은 핀이다."""
    database, wal = _fresh_database(tmp_path)
    monkeypatch.chdir(tmp_path)

    with pinned_connections(Path("sub") / ".." / database.name):
        _insert(database.resolve(), 1)
        assert wal.exists()

    assert not wal.exists()
    assert _count(database) == 1


def test_an_inner_block_does_not_release_the_outer_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """실행 핀 안의 팝업 본문 핀처럼 겹치면, 안쪽이 먼저 연 핀도 바깥 블록 끝까지 산다."""
    database, wal = _fresh_database(tmp_path)
    (tmp_path / "other").mkdir()
    other, other_wal = _fresh_database(tmp_path / "other")
    opened = _counting(monkeypatch)

    with pinned_connections(database):
        with pinned_connections(database), pinned_connections(other):
            _insert(database, 1)
            _insert(other, 1)
        # 안쪽 블록이 끝났다 — 같은 파일의 핀은 남고, 안쪽만의 파일 핀은 풀렸다.
        assert wal.exists()
        assert not other_wal.exists()
        _insert(database, 2)
        assert opened.count(str(database)) == 3

    assert not wal.exists()
    assert _count(database) == 2


def test_other_threads_do_not_take_this_threads_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """핀 대상은 스레드마다 따로다. 다른 세션·다른 스레드의 연결은 이 블록의 핀을 걸지 않는다."""
    database, wal = _fresh_database(tmp_path)
    opened = _counting(monkeypatch)

    with pinned_connections(database):
        worker = threading.Thread(target=_insert, args=(database, 1))
        worker.start()
        worker.join()
        assert opened == [str(database)]
        assert not wal.exists()


def test_a_pin_that_fails_to_open_still_returns_the_real_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """핀은 덤이다. 핀 연결이 실패해도 실제 연결은 그대로 쓰이고 블록도 깨끗이 끝난다."""
    database, _ = _fresh_database(tmp_path)
    real_connect = duckdb.connect
    calls: list[int] = []

    def pin_fails(*args: Any, **kwargs: Any) -> duckdb.DuckDBPyConnection:
        calls.append(1)
        if len(calls) == 2:
            raise duckdb.IOException("pin failed")
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(duckdb, "connect", pin_fails)

    with pinned_connections(database):
        _insert(database, 1)
        assert _count(database) == 1
    assert _count(database) == 1


def test_a_block_left_by_an_exception_forgets_its_targets(tmp_path: Path) -> None:
    """st.stop()·st.rerun() 으로 빠져도 대상이 남지 않는다 — 남으면 블록 밖 연결이 핀을 잡아
    rerun 사이에도 인스턴스를 쥐는 상시 앵커가 된다."""
    database, wal = _fresh_database(tmp_path)

    with pytest.raises(RuntimeError), pinned_connections(database):
        raise RuntimeError("rerun")

    assert _sql_helpers._PIN_TARGETS.slots == {}
    _insert(database, 1)
    assert not wal.exists()


def test_reads_are_the_same_with_or_without_the_pin(tmp_path: Path) -> None:
    """핀은 인스턴스를 여는 시점만 바꾼다 — 같은 쿼리는 핀 밖·첫 읽기·겹친 블록에서 같은 값이다."""
    database, _ = _fresh_database(tmp_path)
    for value in (3, 1, 2):
        _insert(database, value)

    def rows() -> list[tuple[Any, ...]]:
        with connect(database) as connection:
            return connection.execute(
                "SELECT x, count(*) FROM probe GROUP BY x ORDER BY x"
            ).fetchall()

    unpinned = rows()
    with pinned_connections(database):
        first = rows()
        with pinned_connections(database):
            _insert(database, 4)
            nested = rows()
    after = rows()

    assert unpinned == first == [(1, 1), (2, 1), (3, 1)]
    assert nested == after == [(1, 1), (2, 1), (3, 1), (4, 1)]
