# Purpose: DuckDB 스냅샷 내보내기·검증·설치의 정상·예외 동작을 실제 DuckDB 로 검증한다.

from __future__ import annotations

from pathlib import Path

import pytest

from capa_simulation.persistence import snapshot_export
from capa_simulation.persistence._sql_helpers import connect


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """`data/temp/objectstore` 를 임시 경로로 옮긴다. 개발 PC 의 실제 DB 를 건드리지 않는다."""
    monkeypatch.setattr(snapshot_export.settings, "DATA_DIR", tmp_path)
    return tmp_path


def _seed_database(path: Path, rows: int = 100) -> None:
    with connect(path) as connection:
        connection.execute("CREATE SCHEMA IF NOT EXISTS app_meta")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS app_meta.schema_migration "
            "(version INTEGER PRIMARY KEY, name TEXT, checksum TEXT)"
        )
        connection.execute("INSERT INTO app_meta.schema_migration VALUES (1, '0001_initial', 'x')")
        connection.execute("CREATE TABLE demo AS SELECT range AS id FROM range(?)", [rows])


def test_export_succeeds_while_a_connection_is_still_open(workspace: Path) -> None:
    """앱의 핀이 열린 채로도 스냅샷을 만들 수 있어야 한다 — 이 설계의 전제다."""
    database = workspace / "capa_simulation.duckdb"
    _seed_database(database)
    destination = workspace / "snapshot.duckdb"

    with connect(database):  # 핀 역할
        result = snapshot_export.export_snapshot(database, destination)

    assert destination.exists()
    assert result.size_bytes == destination.stat().st_size
    assert len(result.sha256_hex) == 64
    assert result.migration_version == 1


def test_export_includes_a_commit_made_while_the_pin_is_open(workspace: Path) -> None:
    """핀이 열린 동안 COMMIT 은 `.wal` 에만 있다. 그래도 스냅샷에는 들어 있어야 한다.

    이게 라이브 파일을 그대로 올리면 안 되는 이유다 — 그 파일에는 이 행이 없다.
    """
    database = workspace / "capa_simulation.duckdb"
    _seed_database(database)
    destination = workspace / "snapshot.duckdb"

    with connect(database):  # 핀
        with connect(database) as writer:
            writer.execute("BEGIN")
            writer.execute("INSERT INTO demo VALUES (999999)")
            writer.execute("COMMIT")
        result = snapshot_export.export_snapshot(database, destination)

    with connect(result.path) as reader:
        found = reader.execute("SELECT COUNT(*) FROM demo WHERE id = 999999").fetchone()
    assert found is not None and int(found[0]) == 1


def test_export_output_has_no_wal_and_reopens_cleanly(workspace: Path) -> None:
    database = workspace / "capa_simulation.duckdb"
    _seed_database(database)
    destination = workspace / "snapshot.duckdb"

    result = snapshot_export.export_snapshot(database, destination)

    assert not snapshot_export.wal_path(result.path).exists()
    with connect(result.path) as reader:
        tables = reader.execute("SELECT COUNT(*) FROM duckdb_tables()").fetchone()
    assert tables is not None and int(tables[0]) >= 2


def test_digest_file_reports_matching_sha_md5_and_size(workspace: Path) -> None:
    target = workspace / "payload.bin"
    target.write_bytes(b"capa" * 1024)

    sha256_hex, md5_hex, md5_base64, size = snapshot_export.digest_file(target)

    assert size == 4096
    assert len(sha256_hex) == 64
    assert len(md5_hex) == 32
    assert md5_base64.endswith("==") or len(md5_base64) == 24


def test_code_migration_version_follows_the_files_not_a_constant() -> None:
    """마이그레이션을 추가하면 자동으로 따라가야 한다. 숫자를 박으면 조용히 어긋난다."""
    assert snapshot_export.code_migration_version("simulation") >= 14
    assert snapshot_export.code_migration_version("equipment") >= 5


def test_verify_rejects_a_snapshot_whose_hash_differs(workspace: Path) -> None:
    database = workspace / "capa_simulation.duckdb"
    _seed_database(database)
    destination = workspace / "snapshot.duckdb"
    result = snapshot_export.export_snapshot(database, destination)

    with pytest.raises(RuntimeError, match="sha256"):
        snapshot_export.verify_snapshot(
            result.path,
            dataset="simulation",
            expected_sha256="0" * 64,
            expected_size=result.size_bytes,
            code_version=99,
        )

    # 거부한 파일은 제자리에 두지 않고 이름을 바꿔 남긴다.
    assert not result.path.exists()
    assert result.path.with_name(result.path.name + ".rejected").exists()


def test_verify_rejects_a_snapshot_from_a_newer_deployment(workspace: Path) -> None:
    """받은 파일이 더 최신이면 열지 않는다. 열면 더 늦게, 더 알아보기 어려운 오류가 난다."""
    database = workspace / "capa_simulation.duckdb"
    _seed_database(database)
    destination = workspace / "snapshot.duckdb"
    result = snapshot_export.export_snapshot(database, destination)

    with pytest.raises(RuntimeError, match="최신"):
        snapshot_export.verify_snapshot(
            result.path,
            dataset="simulation",
            expected_sha256=result.sha256_hex,
            expected_size=result.size_bytes,
            code_version=0,
        )


def test_verify_passes_for_a_healthy_snapshot(workspace: Path) -> None:
    database = workspace / "capa_simulation.duckdb"
    _seed_database(database)
    destination = workspace / "snapshot.duckdb"
    result = snapshot_export.export_snapshot(database, destination)

    version = snapshot_export.verify_snapshot(
        result.path,
        dataset="simulation",
        expected_sha256=result.sha256_hex,
        expected_size=result.size_bytes,
        code_version=99,
    )

    assert version == 1
    assert result.path.exists()


def test_install_moves_the_stale_wal_out_of_the_way(workspace: Path) -> None:
    """고아 `.wal` 이 남으면 남의 스냅샷 위에 재생돼 두 계보가 섞인다."""
    database = workspace / "capa_simulation.duckdb"
    _seed_database(database)
    stale_wal = snapshot_export.wal_path(database)
    stale_wal.write_bytes(b"stale")
    incoming = workspace / "incoming.duckdb"
    _seed_database(incoming, rows=5)

    snapshot_export.install_snapshot(incoming, database)

    assert not stale_wal.exists()
    assert not incoming.exists()
    moved = list(snapshot_export.backup_dir().glob("*.wal.*"))
    assert len(moved) == 1


def test_install_keeps_the_replaced_database_as_a_backup(workspace: Path) -> None:
    database = workspace / "capa_simulation.duckdb"
    _seed_database(database, rows=100)
    incoming = workspace / "incoming.duckdb"
    _seed_database(incoming, rows=5)

    backup = snapshot_export.install_snapshot(incoming, database)

    assert backup.exists()
    with connect(backup) as reader:
        rows = reader.execute("SELECT COUNT(*) FROM demo").fetchone()
    assert rows is not None and int(rows[0]) == 100
    with connect(database) as reader:
        rows = reader.execute("SELECT COUNT(*) FROM demo").fetchone()
    assert rows is not None and int(rows[0]) == 5


def test_install_works_when_no_local_database_exists(workspace: Path) -> None:
    database = workspace / "capa_simulation.duckdb"
    incoming = workspace / "incoming.duckdb"
    _seed_database(incoming, rows=5)

    snapshot_export.install_snapshot(incoming, database)

    assert database.exists()


def test_clear_scratch_keeps_backups_by_default(workspace: Path) -> None:
    scratch = snapshot_export.prepare_scratch()
    (scratch / "leftover.duckdb").write_bytes(b"x")
    snapshot_export.backup_dir().mkdir(parents=True, exist_ok=True)
    (snapshot_export.backup_dir() / "old.duckdb").write_bytes(b"y")

    snapshot_export.clear_scratch()

    assert not (scratch / "leftover.duckdb").exists()
    assert (snapshot_export.backup_dir() / "old.duckdb").exists()


def test_author_and_timestamp_are_shaped_for_keys() -> None:
    assert "@" in snapshot_export.author_label()
    stamp = snapshot_export.utc_timestamp()
    assert stamp.endswith("Z") and "T" in stamp
