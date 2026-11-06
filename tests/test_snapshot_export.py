# Purpose: DuckDB 스냅샷 내보내기·검증·설치의 정상·예외 동작을 실제 DuckDB 로 검증한다.

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

import duckdb
import pytest

from capa_simulation import settings as app_settings
from capa_simulation.persistence import snapshot_export, sync_state
from capa_simulation.persistence._sql_helpers import DUCKDB_BLOCK_SIZE, connect


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """`data/temp/objectstore` 를 임시 경로로 옮긴다. 개발 PC 의 실제 DB 를 건드리지 않는다."""
    monkeypatch.setattr(app_settings, "DATA_DIR", tmp_path)
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


def _seed_foreign_key_database(path: Path) -> dict[str, int]:
    """설비 DB 처럼 부모 표에 외래 키 자식 표들이 달린 DB. 자식 둘은 이름이 부모보다 앞선다."""
    with connect(path) as connection:
        connection.execute("CREATE SCHEMA ops")
        connection.execute("CREATE TABLE ops.revision (revision_id VARCHAR PRIMARY KEY)")
        for child in ("a_master", "baseline", "schedule"):
            connection.execute(
                f"CREATE TABLE ops.{child} (revision_id VARCHAR NOT NULL, v INTEGER, "
                "FOREIGN KEY (revision_id) REFERENCES ops.revision (revision_id))"
            )
        connection.execute("INSERT INTO ops.revision SELECT 'r' || range FROM range(20)")
        for child in ("a_master", "baseline", "schedule"):
            connection.execute(
                f"INSERT INTO ops.{child} SELECT 'r' || (range % 20), range FROM range(300)"
            )
    return {"a_master": 300, "baseline": 300, "revision": 20, "schedule": 300}


def test_export_copies_foreign_key_children_after_their_parent(workspace: Path) -> None:
    """외래 키 자식 행을 부모보다 먼저 넣으면 내보내기가 제약 위반으로 멈춘다(설비 DB 의 꼴)."""
    database = workspace / "equipment_availability.duckdb"
    expected = _seed_foreign_key_database(database)
    destination = workspace / "snapshot.duckdb"

    result = snapshot_export.export_snapshot(database, destination)

    with connect(result.path) as reader:
        counts = {
            table: int(reader.execute(f"SELECT COUNT(*) FROM ops.{table}").fetchone()[0])  # type: ignore[index]
            for table in expected
        }
    assert counts == expected


def test_export_failure_surfaces_the_original_error(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """복사가 트랜잭션을 깨뜨린 채 실패해도 뒤의 DETACH 오류가 원래 원인을 가리면 안 된다."""
    database = workspace / "capa_simulation.duckdb"
    _seed_database(database)

    def broken_copy(
        connection: duckdb.DuckDBPyConnection, source_catalog: str, target_catalog: str
    ) -> None:
        connection.execute("BEGIN")
        connection.execute(f"CREATE TABLE {target_catalog}.main.t (id INTEGER PRIMARY KEY)")
        connection.execute(f"INSERT INTO {target_catalog}.main.t VALUES (1), (1)")

    monkeypatch.setattr(snapshot_export, "copy_database", broken_copy)

    with pytest.raises(duckdb.ConstraintException):
        snapshot_export.export_snapshot(database, workspace / "snapshot.duckdb")


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


def test_verify_passes_when_the_snapshot_version_equals_the_deployment(workspace: Path) -> None:
    """같은 버전은 「최신」이 아니다. 경계에서 막으면 같은 배포본끼리도 주고받지 못한다."""
    database = workspace / "capa_simulation.duckdb"
    _seed_database(database)
    destination = workspace / "snapshot.duckdb"
    result = snapshot_export.export_snapshot(database, destination)
    file_version = snapshot_export.read_migration_version(result.path, "simulation")

    version = snapshot_export.verify_snapshot(
        result.path,
        dataset="simulation",
        expected_sha256=result.sha256_hex,
        expected_size=result.size_bytes,
        code_version=file_version,
    )

    assert version == file_version
    assert result.path.exists()


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

    backup = snapshot_export.install_snapshot(incoming, database).database_backup

    assert backup is not None and backup.exists()
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


def test_install_restores_the_database_and_its_wal_when_the_move_fails(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WAL 에만 있던 커밋이 백업에 남은 채 DB 만 돌아오면 그 커밋이 빠진 파일이 된다."""
    database = workspace / "capa_simulation.duckdb"
    _seed_database(database, rows=100)
    wal = snapshot_export.wal_path(database)
    wal.write_bytes(b"wal")
    incoming = workspace / "incoming.duckdb"
    _seed_database(incoming, rows=5)
    original = Path.replace

    def refuse_install(self: Path, target: Path) -> Path:
        if self == incoming:
            raise OSError(5, "설치 실패 흉내")
        return original(self, target)

    monkeypatch.setattr(Path, "replace", refuse_install)

    with pytest.raises(OSError, match="설치 실패"):
        snapshot_export.install_snapshot(incoming, database)

    assert wal.read_bytes() == b"wal"
    with connect(database) as reader:
        row = reader.execute("SELECT COUNT(*) FROM demo").fetchone()
    assert row is not None and int(row[0]) == 100


def test_restoring_an_install_puts_the_old_files_back(workspace: Path) -> None:
    database = workspace / "capa_simulation.duckdb"
    _seed_database(database, rows=100)
    snapshot_export.wal_path(database).write_bytes(b"wal")
    incoming = workspace / "incoming.duckdb"
    _seed_database(incoming, rows=5)

    result = snapshot_export.install_snapshot(incoming, database)
    snapshot_export.restore_install(result, database)

    assert snapshot_export.wal_path(database).read_bytes() == b"wal"
    with connect(database) as reader:
        row = reader.execute("SELECT COUNT(*) FROM demo").fetchone()
    assert row is not None and int(row[0]) == 100


def test_superseded_backups_keep_only_the_last_installs(workspace: Path) -> None:
    """받을 때마다 옛 DB 가 쌓이면 휘발 디스크가 찬다."""
    database = workspace / "capa_simulation.duckdb"
    _seed_database(database, rows=3)
    for rows in (4, 5, 6, 7):
        incoming = workspace / "incoming.duckdb"
        _seed_database(incoming, rows=rows)
        snapshot_export.install_snapshot(incoming, database)

    removed = snapshot_export.prune_superseded_backups(database)

    assert len(removed) == 1
    assert len(list(snapshot_export.backup_dir().iterdir())) == snapshot_export.KEEP_SUPERSEDED


def test_two_exports_in_one_process_do_not_share_an_attach_alias(workspace: Path) -> None:
    """별칭은 인스턴스 전체에 보여, 고정 이름이면 둘째 ATTACH 가 멈춘다."""
    database = workspace / "capa_simulation.duckdb"
    _seed_database(database)
    results: list[Path] = []

    def export(index: int) -> None:
        results.append(
            snapshot_export.export_snapshot(database, workspace / f"copy-{index}.duckdb").path
        )

    threads = [threading.Thread(target=export, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)

    assert len(results) == 2


def test_verify_names_the_failure_kind(workspace: Path) -> None:
    """시작 화면과 Admin 은 서버 글 대신 갈래 낱말을 싣는다."""
    database = workspace / "capa_simulation.duckdb"
    _seed_database(database)
    export = snapshot_export.export_snapshot(database, workspace / "copy.duckdb")

    with pytest.raises(snapshot_export.SnapshotRejected) as caught:
        snapshot_export.verify_snapshot(
            export.path,
            dataset="simulation",
            expected_sha256=export.sha256_hex,
            expected_size=export.size_bytes,
            code_version=0,
        )

    assert caught.value.kind == "schema_newer"


def test_verify_reads_an_unopenable_file_as_corrupt(workspace: Path) -> None:
    broken = workspace / "broken.duckdb"
    broken.write_bytes(b"not a database" * 100)
    digest = snapshot_export.digest_file(broken)

    with pytest.raises(snapshot_export.SnapshotRejected) as caught:
        snapshot_export.verify_snapshot(
            broken,
            dataset="simulation",
            expected_sha256=digest[0],
            expected_size=digest[3],
            code_version=99,
            rejected_path=workspace / "fixed.rejected",
        )

    assert caught.value.kind == "corrupt"
    assert (workspace / "fixed.rejected").exists()


def test_free_space_check_reads_as_disk_full(workspace: Path) -> None:
    from capa_simulation.io.object_storage import classify_failure

    with pytest.raises(snapshot_export.DiskSpaceShort) as caught:
        snapshot_export.require_free_space(workspace / "not" / "yet", 10**18)

    assert classify_failure(caught.value) == "disk_full"


def _checkpoint_copy(database: Path, destination: Path) -> snapshot_export.CheckpointCopy:
    return snapshot_export.checkpoint_copy(
        database, destination, write_lock=threading.RLock(), dataset="simulation"
    )


def test_checkpoint_copy_carries_a_commit_that_was_only_in_the_wal(workspace: Path) -> None:
    """핀이 열린 채의 COMMIT 은 WAL 에만 있다. 그대로 복사하면 방금 저장이 통째로 빠진다."""
    database = workspace / "capa_simulation.duckdb"
    _seed_database(database, rows=10)

    with connect(database) as pin:
        pin.execute("INSERT INTO demo VALUES (99999)")
        copied = _checkpoint_copy(database, workspace / "copy.duckdb")

    assert not snapshot_export.wal_path(copied.export.path).exists()
    with connect(copied.export.path) as reader:
        row = reader.execute("SELECT COUNT(*) FROM demo").fetchone()
    assert row is not None and int(row[0]) == 11
    assert copied.export.migration_version == 1


def test_checkpoint_copy_keeps_the_block_size_and_can_be_installed(workspace: Path) -> None:
    """바이트 사본을 그대로 받아 앱이 연다. 16KiB 블록 불변조건도 그대로다."""
    database = workspace / "capa_simulation.duckdb"
    _seed_database(database)
    copied = _checkpoint_copy(database, workspace / "copy.duckdb")

    version = snapshot_export.verify_snapshot(
        copied.export.path,
        dataset="simulation",
        expected_sha256=copied.export.sha256_hex,
        expected_size=copied.export.size_bytes,
        code_version=1,
    )
    target = workspace / "installed.duckdb"
    snapshot_export.install_snapshot(copied.export.path, target)

    assert version == 1
    with connect(target) as reader:
        row = reader.execute("SELECT block_size FROM pragma_database_size()").fetchone()
    assert row is not None and int(row[0]) == DUCKDB_BLOCK_SIZE


def test_the_mark_read_under_the_lock_matches_the_copy(workspace: Path) -> None:
    """잠금 안에서 읽어야 「사본이 담은 번호」 와 같다. 이것이 비교 후 지우기의 기준이다."""
    database = workspace / "capa_simulation.duckdb"
    _seed_database(database)
    sync_state.clear_all()
    sync_state.enable({database: "simulation"})
    sync_state.mark_dirty(database)
    sync_state.mark_dirty(database)

    copied = _checkpoint_copy(database, workspace / "copy.duckdb")

    assert copied.observed.dirty_seq == 2
    sync_state.clear_all()


def test_a_held_lock_is_reported_as_busy(workspace: Path) -> None:
    """저장이 길게 돌면 다음 회차다. 잠금을 빼앗지 않는다."""
    database = workspace / "capa_simulation.duckdb"
    _seed_database(database)
    lock = threading.RLock()
    held = threading.Event()
    release = threading.Event()

    def hold() -> None:
        with lock:
            held.set()
            release.wait(10)

    holder = threading.Thread(target=hold)
    holder.start()
    held.wait(5)
    try:
        with pytest.raises(snapshot_export.SnapshotBusy):
            snapshot_export.checkpoint_copy(
                database,
                workspace / "copy.duckdb",
                write_lock=lock,
                dataset="simulation",
                lock_timeout_seconds=0.05,
            )
    finally:
        release.set()
        holder.join(5)


def test_a_file_that_moves_during_the_copy_is_thrown_away(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """잠금을 비켜 간 쓰기를 잡는 둘째 벽 — 앞뒤 stat 이 다르면 사본을 쓰지 않는다."""
    database = workspace / "capa_simulation.duckdb"
    _seed_database(database)
    original = snapshot_export._copy_live_bytes

    def copy_then_touch(source: Path, destination: Path, size: int) -> None:
        original(source, destination, size)
        os.utime(source, ns=(1, 1))

    monkeypatch.setattr(snapshot_export, "_copy_live_bytes", copy_then_touch)
    destination = workspace / "copy.duckdb"

    with pytest.raises(snapshot_export.SnapshotRaced):
        _checkpoint_copy(database, destination)

    assert not destination.exists()


_OPEN_FOR_WRITE = """
import sys

import duckdb

try:
    duckdb.connect(sys.argv[1], config={"default_block_size": 16384}).close()
except duckdb.IOException:
    sys.exit(3)
"""


def test_the_copy_keeps_the_process_lock_on_the_live_file(workspace: Path) -> None:
    """같은 프로세스가 그 파일을 열었다 닫으면 POSIX 잠금이 풀린다. 복사가 그것을 풀면
    「다른 프로세스는 곧바로 실패」 가 프로세스 수명 동안 조용히 사라진다."""
    database = workspace / "capa_simulation.duckdb"
    _seed_database(database)

    with connect(database):
        _checkpoint_copy(database, workspace / "copy.duckdb")
        opened = subprocess.run(
            [sys.executable, "-c", _OPEN_FOR_WRITE, str(database)],
            capture_output=True,
            check=False,
            timeout=60,
        )

    assert opened.returncode == 3


def test_the_live_handle_follows_a_replaced_file(workspace: Path) -> None:
    """같은 경로가 새 파일이 되면(받기) 옛 번호로 읽으면 옛 내용이 나온다."""
    database = workspace / "capa_simulation.duckdb"
    _seed_database(database, rows=5)
    _checkpoint_copy(database, workspace / "first.duckdb")
    incoming = workspace / "incoming.duckdb"
    _seed_database(incoming, rows=7)
    snapshot_export.install_snapshot(incoming, database)

    copied = _checkpoint_copy(database, workspace / "second.duckdb")

    with connect(copied.export.path) as reader:
        row = reader.execute("SELECT COUNT(*) FROM demo").fetchone()
    assert row is not None and int(row[0]) == 7
