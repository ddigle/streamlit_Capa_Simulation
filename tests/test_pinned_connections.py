# Purpose: rerun 동안 DuckDB 인스턴스를 잡아 두는 핀의 동작(살아 있을 때·풀린 뒤)을 고정한다.

from pathlib import Path

import pytest

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
