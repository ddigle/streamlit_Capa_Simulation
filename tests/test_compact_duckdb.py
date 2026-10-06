# Purpose: DuckDB 재구축 스크립트의 행 보존·원본 잠금·실행 중 앱 차단을 검증한다.

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType

import duckdb
import pytest

from capa_simulation.persistence import sync_state

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "compact_duckdb.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("compact_duckdb", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["compact_duckdb"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script() -> ModuleType:
    return _load_script()


def _args(*, dry_run: bool = False, keep_backup: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        block_size=16384, storage_version=None, dry_run=dry_run, keep_backup=keep_backup
    )


def _make_database(path: Path) -> dict[str, int]:
    """지운 행으로 free 블록이 남은 작은 DB 를 만들고 표별 행 수를 돌려준다."""
    connection = duckdb.connect(str(path))
    try:
        connection.execute("CREATE SCHEMA app_meta")
        connection.execute("CREATE TABLE app_meta.scenario AS SELECT range AS id FROM range(5000)")
        connection.execute("CREATE TABLE main.rq AS SELECT range AS id, 'x' AS v FROM range(300)")
        connection.execute("DELETE FROM app_meta.scenario WHERE id >= 1000")
    finally:
        connection.close()
    return {"app_meta.scenario": 1000, "main.rq": 300}


def _row_counts(path: Path) -> dict[str, int]:
    connection = duckdb.connect(str(path), read_only=True)
    try:
        tables = connection.execute(
            "SELECT schema_name, table_name FROM duckdb_tables() ORDER BY 1, 2"
        ).fetchall()
        return {
            f"{schema}.{table}": int(
                connection.execute(f'SELECT COUNT(*) FROM "{schema}"."{table}"').fetchone()[0]  # type: ignore[index]
            )
            for schema, table in tables
        }
    finally:
        connection.close()


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_heartbeat(database_path: Path, beat: datetime) -> None:
    sync_state.write_state(
        database_path,
        sync_state.SyncState(
            dataset="simulation",
            instance_id="other-app",
            heartbeat_utc=beat.strftime("%Y-%m-%dT%H:%M:%SZ"),
        ),
    )


def test_compact_replaces_the_file_with_the_same_tables_and_rows(
    script: ModuleType, tmp_path: Path
) -> None:
    database = tmp_path / "sim.duckdb"
    expected = _make_database(database)

    assert script.compact(database, _args()) is True

    assert _row_counts(database) == expected
    assert sorted(path.name for path in tmp_path.iterdir()) == ["sim.duckdb"]


def test_dry_run_leaves_the_original_untouched(script: ModuleType, tmp_path: Path) -> None:
    database = tmp_path / "sim.duckdb"
    _make_database(database)
    before = _digest(database)

    assert script.compact(database, _args(dry_run=True)) is False

    assert _digest(database) == before
    assert sorted(path.name for path in tmp_path.iterdir()) == ["sim.duckdb"]


def test_source_stays_locked_until_the_copy_is_verified(
    script: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """복사 뒤 사본을 세는 동안에도 앱의 쓰기 연결은 원본을 열지 못해야 한다.

    그 틈에 열리면 거기서 커밋한 저장은 원본에만 남고 교체와 함께 사라진다.
    """
    database = tmp_path / "sim.duckdb"
    _make_database(database)
    original = script.table_row_counts
    attempts: list[int] = []

    def app_write_connect() -> int:
        probe = subprocess.run(
            [sys.executable, "-c", f"import duckdb; duckdb.connect({str(database)!r}).close()"],
            capture_output=True,
            check=False,
        )
        return probe.returncode

    def counting_with_probe(connection: duckdb.DuckDBPyConnection, catalog: str) -> dict[str, int]:
        if catalog == "compact_target":
            attempts.append(app_write_connect())
        result: dict[str, int] = original(connection, catalog)
        return result

    monkeypatch.setattr(script, "table_row_counts", counting_with_probe)

    assert script.compact(database, _args()) is True

    assert len(attempts) == 1
    assert attempts[0] != 0
    assert app_write_connect() == 0


def test_live_heartbeat_stops_before_touching_the_file(script: ModuleType, tmp_path: Path) -> None:
    database = tmp_path / "sim.duckdb"
    _make_database(database)
    _write_heartbeat(database, datetime.now(timezone.utc))
    before = _digest(database)

    with pytest.raises(SystemExit, match="실행 중"):
        script.compact(database, _args())

    assert _digest(database) == before
    assert not database.with_name("sim.duckdb.compact").exists()


def test_stale_heartbeat_does_not_block_but_still_reminds(
    script: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """오래 쉰 managed 앱은 막지 못하므로 사이드카가 있어도 직접 확인하라고 알려야 한다."""
    database = tmp_path / "sim.duckdb"
    expected = _make_database(database)
    _write_heartbeat(database, datetime.now(timezone.utc) - timedelta(minutes=5))

    assert script.compact(database, _args()) is True

    assert "[확인]" in capsys.readouterr().out
    assert _row_counts(database) == expected


def test_missing_sidecar_reminds_to_stop_the_app(
    script: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "sim.duckdb"
    _make_database(database)

    assert script.compact(database, _args(dry_run=True)) is False

    assert "[확인]" in capsys.readouterr().out


def test_main_exit_status_fails_when_a_requested_database_is_missing(
    script: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """직접 지정한 파일이 없는 것은 대개 경로 오타다. 건너뛰고 0 으로 끝나면 성공으로 보인다."""
    database = tmp_path / "sim.duckdb"
    _make_database(database)
    typo = tmp_path / "sim.duckdbb"

    assert script.main(["--database", str(database), "--dry-run"]) == 0
    capsys.readouterr()

    assert script.main(["--database", str(database), "--database", str(typo), "--dry-run"]) == 1
    output = capsys.readouterr().out
    assert "[건너뜀]" in output
    assert "[실패]" in output
