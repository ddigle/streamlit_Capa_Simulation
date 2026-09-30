# Purpose: 내려가는 인스턴스와 겹친 같은 프로세스의 연결(자기 PID 잠금)을 기다렸다 여는지 고정한다.

import os
import threading
from pathlib import Path

import duckdb
import pytest

from capa_simulation.persistence import _sql_helpers
from capa_simulation.persistence._sql_helpers import (
    connect,
    is_own_process_lock,
    lock_holder_pid,
)


def _lock_error(pid: int) -> duckdb.IOException:
    """Windows 에서 실측한 잠금 오류의 모양. 앞 문장은 로캘 탓에 깨져 오므로 꼬리만 믿는다."""
    return duckdb.IOException(
        'IO Error: Cannot open file "C:\\app\\data\\capa_simulation.duckdb": ???\r\n\n'
        f"File is already open in \nC:\\Python310\\python.exe (PID {pid})"
    )


def test_lock_holder_is_read_from_the_ascii_tail_of_the_message() -> None:
    assert lock_holder_pid(_lock_error(4321)) == 4321
    # Linux 의 fcntl 잠금 문장도 같은 꼬리를 단다.
    linux = duckdb.IOException(
        'IO Error: Could not set lock on file "/app/data/x.duckdb": Conflicting lock is held '
        "in /usr/bin/python3.10 (PID 77) by user app."
    )
    assert lock_holder_pid(linux) == 77
    assert lock_holder_pid(duckdb.IOException("Could not set lock on file")) is None
    # 잠금 오류가 아닌 예외는 문장에 PID 가 들어 있어도 잠금으로 치지 않는다.
    assert lock_holder_pid(RuntimeError("(PID 77)")) is None
    assert is_own_process_lock(_lock_error(os.getpid()))
    assert not is_own_process_lock(_lock_error(os.getpid() + 1))


def test_connect_waits_out_a_lock_this_process_holds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """내려가는 인스턴스가 체크포인트를 끝내면 열린다. 그 사이의 실패를 사용자에게 올리지 않는다."""
    real_connect = duckdb.connect
    attempts: list[int] = []

    def closing_instance(*args: object, **kwargs: object) -> duckdb.DuckDBPyConnection:
        attempts.append(1)
        if len(attempts) <= 3:
            raise _lock_error(os.getpid())
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(_sql_helpers.duckdb, "connect", closing_instance)
    monkeypatch.setattr(_sql_helpers, "OWN_LOCK_POLL_SECONDS", 0.0)

    with connect(tmp_path / "own.duckdb") as connection:
        assert connection.execute("SELECT 1").fetchone() == (1,)
    assert len(attempts) == 4


@pytest.mark.parametrize(
    "error",
    [
        _lock_error(os.getpid() + 1),
        duckdb.IOException("Could not set lock on file"),
        duckdb.IOException("Cannot open database: directory does not exist"),
    ],
    ids=["other-process", "no-pid", "missing-folder"],
)
def test_connect_raises_every_other_failure_at_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: duckdb.IOException
) -> None:
    """다른 프로세스의 잠금은 기다려도 안 풀린다. 동기화 스크립트와 안내가 빠른 실패에 기댄다."""
    attempts: list[int] = []

    def locked(*_args: object, **_kwargs: object) -> None:
        attempts.append(1)
        raise error

    monkeypatch.setattr(_sql_helpers.duckdb, "connect", locked)

    with pytest.raises(duckdb.IOException):
        connect(tmp_path / "other.duckdb")
    assert len(attempts) == 1


def test_connect_gives_up_after_the_wait_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """자기 잠금이 끝내 안 풀리면 한도에서 원래 오류를 올린다 — 안내가 새로고침을 권한다."""
    attempts: list[int] = []

    def stuck(*_args: object, **_kwargs: object) -> None:
        attempts.append(1)
        raise _lock_error(os.getpid())

    monkeypatch.setattr(_sql_helpers.duckdb, "connect", stuck)
    monkeypatch.setattr(_sql_helpers, "OWN_LOCK_WAIT_SECONDS", 0.05)
    monkeypatch.setattr(_sql_helpers, "OWN_LOCK_POLL_SECONDS", 0.005)

    with pytest.raises(duckdb.IOException) as raised:
        connect(tmp_path / "stuck.duckdb")
    assert is_own_process_lock(raised.value)
    assert len(attempts) >= 2


def test_an_unnamed_sharing_violation_is_retried_briefly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """같은 겹침이 가끔 쥔 프로세스를 적지 않은 공유 위반으로 온다(검토 실측) — 짧게 다시 연다."""
    real_connect = duckdb.connect
    attempts: list[int] = []

    def unnamed_then_open(*args: object, **kwargs: object) -> duckdb.DuckDBPyConnection:
        attempts.append(1)
        if len(attempts) <= 2:
            raise duckdb.IOException('IO Error: Cannot open file "C:/app/data/x.duckdb": ???')
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(_sql_helpers.duckdb, "connect", unnamed_then_open)
    monkeypatch.setattr(_sql_helpers, "OWN_LOCK_POLL_SECONDS", 0.0)

    with connect(tmp_path / "unnamed.duckdb") as connection:
        assert connection.execute("SELECT 1").fetchone() == (1,)
    assert len(attempts) == 3


def test_an_unnamed_failure_in_a_missing_folder_is_raised_at_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """폴더가 없으면 기다려도 열리지 않는다 — 같은 「Cannot open file」 문장이어도 곧바로 올린다."""
    attempts: list[int] = []

    def missing(*_args: object, **_kwargs: object) -> None:
        attempts.append(1)
        raise duckdb.IOException('IO Error: Cannot open file "C:/nowhere/x.duckdb": ???')

    monkeypatch.setattr(_sql_helpers.duckdb, "connect", missing)

    with pytest.raises(duckdb.IOException):
        connect(tmp_path / "no-such-folder" / "x.duckdb")
    assert len(attempts) == 1


def _open_repeatedly(
    database: Path,
    started: threading.Event,
    stop: threading.Event,
    failures: list[BaseException],
) -> None:
    started.set()
    while not stop.is_set():
        try:
            connect(database).close()
        except duckdb.Error as exc:
            failures.append(exc)
        stop.wait(0.001)


def test_a_connect_racing_the_last_close_of_a_large_wal_succeeds(tmp_path: Path) -> None:
    """마지막 연결이 큰 WAL 을 체크포인트하며 닫히는 동안 다른 스레드가 연다(E2E G1-D0 의 자리).

    재시도를 끄면(고치기 전과 같다) Windows 에서 이 테스트가 3번 돌려 3번 「PID <자기 자신>」
    잠금 오류로 실패했다(2026-10-01). 경합이 안 일어난 회차도 통과한다. PID 를 적지 않은 공유
    위반을 곧바로 올리던 동안은 40번 중 4번 실패했다 — 그 경우도 짧게 기다려 연다.
    """
    database = tmp_path / "race.duckdb"
    wal = tmp_path / "race.duckdb.wal"
    failures: list[BaseException] = []

    for _trial in range(3):
        for path in (database, wal):
            path.unlink(missing_ok=True)
        owner = connect(database)
        owner.execute("CREATE TABLE probe(i BIGINT, s VARCHAR)")
        for chunk in range(8):
            owner.execute(
                "INSERT INTO probe SELECT range, md5(range::VARCHAR) FROM range(?, ?)",
                [chunk * 20_000, (chunk + 1) * 20_000],
            )
        assert wal.exists()

        stop = threading.Event()
        started = threading.Event()
        opener = threading.Thread(target=_open_repeatedly, args=(database, started, stop, failures))
        opener.start()
        started.wait()
        owner.close()
        stop.set()
        opener.join()

    assert failures == []
