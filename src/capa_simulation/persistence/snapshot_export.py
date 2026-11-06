# Purpose: DuckDB 파일을 일관된 스냅샷으로 내보내고 받은 스냅샷을 검증해 제자리에 설치한다.

"""DuckDB 스냅샷을 주고받는 계층.

**스냅샷을 뜨는 길은 둘이다.**

1. **ATTACH 복사가 기본이다**(`export_snapshot` — 사내 PC 의 `init`, 앱을 끈 수동 왕복). `ATTACH`
   한 새 파일로 `_sql_helpers.copy_database()`(구조는 `COPY FROM DATABASE … (SCHEMA)`, 데이터는
   외래 키 부모 표부터 한 트랜잭션 안에서 `INSERT … SELECT`). 트랜잭션 상태를 읽으므로 방금의
   COMMIT 이 포함되고, 핀이 열린 채로도 성공하며, 산출물에는 `.wal` 이 없다. 빈 블록이 빠져 파일이
   준다.
2. **앱 안에서는 쓰기 잠금 · CHECKPOINT · stat 대조 아래서만 바이트로 읽는다**(`checkpoint_copy` —
   저장소의 `export_checkpoint_copy` 가 부른다). ATTACH 복사는 62.8MiB DB 에서 +555MiB 를 써
   메모리 1GiB 컨테이너에서 앱과 함께 돌지 못한다(샘플 관측). 바이트 복사는 +16 ~ 25MiB 이고
   잠금은 1초 안이다.

라이브 파일을 바이트로 읽지 말라던 까닭 둘은 이렇게 풀린다. ① Windows 에서 연결이 열려 있으면 같은
프로세스에서도 `open(path, "rb")` 가 `PermissionError` 다 — 바이트 복사는 컨테이너(Linux)에서만
돈다. ② `app.py` 의 핀이 열린 동안 COMMIT 은 `<이름>.wal` 에만 있어 본 파일에 없다 — CHECKPOINT 로
옮기고, WAL 이 비었고 복사 앞뒤 stat 이 같을 때만 믿는다.

**라이브 파일은 프로세스 수명 동안 닫지 않는 번호로 읽는다**(`_live_handle` · `os.sendfile`).
DuckDB 의 프로세스 잠금은 POSIX 레코드 잠금이라, 같은 프로세스가 그 파일을 어떤 번호로든 열었다
닫으면 잠금이 풀린다 — 저장소가 기대는 「다른 프로세스는 곧바로 실패」 가 조용히 사라진다. 그래서
`shutil.copyfile` 도 `digest_file` 도 라이브 파일에 쓰지 않는다.

DuckDB 를 열 때는 반드시 `_sql_helpers.connect()` 를 쓴다. `duckdb.connect(path,
read_only=True)` 는 같은 프로세스의 다른 연결과 configuration 이 달라 연결 자체가 거부된다.
"""

from __future__ import annotations

import base64
import errno
import hashlib
import os
import re
import shutil
import sys
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, Protocol
from uuid import uuid4

import duckdb

from capa_simulation import settings
from capa_simulation.persistence import sync_state
from capa_simulation.persistence._sql_helpers import (
    DUCKDB_BLOCK_SIZE,
    connect,
    copy_database,
    unique_catalog_alias,
)
from capa_simulation.persistence.equipment_migration_runner import load_equipment_migrations
from capa_simulation.persistence.migration_runner import load_migrations
from capa_simulation.persistence.sync_state import DirtyMark
from capa_simulation.services.korean_particle import with_subject_particle
from capa_simulation.services.object_storage_manifest import (
    FAILURE_CORRUPT,
    FAILURE_SCHEMA_NEWER,
    MIGRATION_SCHEMA,
    DatasetName,
    compare_migration_version,
)

SCRATCH_DIRNAME: Final = "objectstore"
BACKUP_DIRNAME: Final = "superseded"
# superseded 에 남길 최근 설치 수. 받을 때마다 옛 DB(와 WAL)가 쌓여 휘발 디스크를 채우지 않게 한다.
KEEP_SUPERSEDED: Final = 3
# 바이트 복사가 쓰기 잠금을 기다리는 끝. 못 잡으면 다음 회차다 — 저장을 밀어내지 않는다.
LOCK_TIMEOUT_SECONDS: Final = 30.0
_COPY_CHUNK_BYTES: Final = 8 * 1024 * 1024
_BACKUP_STAMP: Final = re.compile(r"^\d{8}T\d{6}Z(?:-\d+)?$")
# 같은 프로세스의 내보내기를 한 줄로 세운다. 스냅샷 하나가 코어를 다 쓰므로 겹쳐 돌 이득도 없다.
_EXPORT_LOCK = threading.Lock()
# 라이브 파일을 읽는 번호. 프로세스가 끝날 때까지 닫지 않는다(모듈 설명).
_LIVE_HANDLES: dict[Path, int] = {}
_LIVE_HANDLES_LOCK = threading.Lock()


class WriteLock(Protocol):
    """저장소의 쓰기 잠금(`threading.RLock`)에서 쓰는 몫."""

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool: ...

    def release(self) -> None: ...


class SnapshotBusy(RuntimeError):
    """쓰기 잠금을 제때 잡지 못했다 — 저장이 길게 도는 중이다. 다음 회차에 다시 뜬다."""


class SnapshotRaced(RuntimeError):
    """복사하는 동안 파일이 움직였다 — 잠금을 비켜 간 쓰기를 잡는 둘째 벽. 사본을 버린다."""


class SnapshotRejected(RuntimeError):
    """스냅샷이 쓸 수 없다. `kind` 는 실패 갈래(`corrupt` · `schema_newer`)다."""

    def __init__(self, message: str, *, kind: str) -> None:
        super().__init__(message)
        self.kind = kind


class DiskSpaceShort(OSError):
    """받을 자리가 모자란다. 받기를 시작하기 전에 낸다."""

    def __init__(self, needed_bytes: int, free_bytes: int) -> None:
        super().__init__(errno.ENOSPC, f"디스크 여유 {free_bytes} < 필요 {needed_bytes}")


@dataclass(frozen=True)
class ExportResult:
    """내보낸 스냅샷 하나와 그 지문."""

    path: Path
    sha256_hex: str
    md5_hex: str
    md5_base64: str
    size_bytes: int
    source_bytes: int
    migration_version: int
    elapsed_seconds: float


@dataclass(frozen=True)
class CheckpointCopy:
    """앱 안 바이트 복사의 결과. `observed` 는 잠금 안에서 읽어 사본이 담은 번호와 정확히 같다."""

    export: ExportResult
    observed: DirtyMark
    lock_seconds: float


@dataclass(frozen=True)
class InstallResult:
    """설치가 밀어낸 파일들. 둘째 DB 설치가 실패하면 첫째를 이 경로로 되돌린다."""

    database_backup: Path | None
    wal_backup: Path | None
    backup_dir: Path


def scratch_dir() -> Path:
    """작업 파일 자리. `settings` 를 호출 시점에 조회해 테스트가 경로를 갈아끼울 수 있다."""
    return settings.DATA_DIR / "temp" / SCRATCH_DIRNAME


def backup_dir() -> Path:
    return scratch_dir() / BACKUP_DIRNAME


def wal_path(database_path: Path) -> Path:
    return database_path.with_name(database_path.name + ".wal")


def export_snapshot(
    database_path: Path,
    destination: Path,
    *,
    block_size: int = DUCKDB_BLOCK_SIZE,
) -> ExportResult:
    """DuckDB 가 스스로 만든 일관된 사본을 `destination` 에 쓴다.

    `BLOCK_SIZE` 를 명시하지 않으면 256 KiB 블록으로 만들어져, 내려받은 쪽에서
    `_sql_helpers.DUCKDB_BLOCK_SIZE` 16 KiB 불변조건이 조용히 깨진다.
    """
    if destination.exists():
        destination.unlink()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with _EXPORT_LOCK:
        started = time.perf_counter()
        source_bytes = database_path.stat().st_size
        alias = unique_catalog_alias("snap")
        with connect(database_path) as connection:
            # 파일 스템이 아니라 DuckDB 가 아는 이름이어야 한다. 파일명이 바뀌어도 따라간다.
            row = connection.execute("SELECT current_database()").fetchone()
            if row is None:
                raise RuntimeError(f"현재 데이터베이스 이름을 읽지 못했습니다: {database_path}")
            name = str(row[0])
            connection.execute(
                f"ATTACH '{_quote(destination)}' AS {alias} (BLOCK_SIZE {int(block_size)})"
            )
            try:
                copy_database(connection, name, alias)
            except BaseException:
                # 깨진 트랜잭션에서는 DETACH 도 실패한다. 그 오류가 원래 원인을 가리지 않게 한다.
                with suppress(duckdb.Error):
                    connection.execute(f"DETACH {alias}")
                raise
            connection.execute(f"DETACH {alias}")
        elapsed = time.perf_counter() - started
    sha256_hex, md5_hex, md5_base64, size_bytes = digest_file(destination)
    return ExportResult(
        path=destination,
        sha256_hex=sha256_hex,
        md5_hex=md5_hex,
        md5_base64=md5_base64,
        size_bytes=size_bytes,
        source_bytes=source_bytes,
        migration_version=read_migration_version(destination, _dataset_of(database_path)),
        elapsed_seconds=elapsed,
    )


def checkpoint_copy(
    database_path: Path,
    destination: Path,
    *,
    write_lock: WriteLock,
    dataset: DatasetName,
    lock_timeout_seconds: float = LOCK_TIMEOUT_SECONDS,
) -> CheckpointCopy:
    """앱이 떠 있는 채로 뜨는 스냅샷 — 쓰기 잠금 + CHECKPOINT + 바이트 복사 + stat 대조.

    잠금을 쥔 동안 변경 번호를 읽으므로 사본이 담은 번호와 정확히 같다. 연결을 쥔 채 복사하므로
    인스턴스가 내려가는 체크포인트도 끼지 못한다. 읽기는 막지 않고 저장만 그 시간 기다린다.

    `SnapshotBusy`(잠금을 못 잡음) · `SnapshotRaced`(파일이 움직임)는 다음 회차에 다시 뜨면 되는
    실패다. 해시와 사본 열기는 잠금 밖이다 — 저장을 그만큼 세우지 않는다.
    """
    if destination.exists():
        destination.unlink()
    destination.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    if not write_lock.acquire(timeout=lock_timeout_seconds):
        raise SnapshotBusy(f"쓰기 잠금을 {lock_timeout_seconds:.0f}초 안에 잡지 못했습니다.")
    locked_at = time.perf_counter()
    try:
        observed = sync_state.read_dirty_mark(database_path)
        with connect(database_path) as connection:
            try:
                connection.execute("CHECKPOINT")
            except duckdb.TransactionException as exc:
                raise SnapshotBusy(f"체크포인트를 시작하지 못했습니다: {exc}") from exc
            before = _file_signature(database_path)
            wal_was_empty = _wal_is_empty(database_path)
            if wal_was_empty:
                _copy_live_bytes(database_path, destination, before[1])
            after = _file_signature(database_path)
            wal_stayed_empty = _wal_is_empty(database_path)
    finally:
        write_lock.release()
    lock_seconds = time.perf_counter() - locked_at
    if not (wal_was_empty and wal_stayed_empty and before == after):
        destination.unlink(missing_ok=True)
        raise SnapshotRaced(f"복사하는 동안 파일이 움직였습니다: {database_path.name}")
    sha256_hex, md5_hex, md5_base64, size_bytes = digest_file(destination)
    if size_bytes != before[1]:
        destination.unlink(missing_ok=True)
        raise SnapshotRaced(f"복사한 크기가 원본과 다릅니다: {size_bytes} != {before[1]}")
    version = _verified_copy_version(destination, dataset)
    return CheckpointCopy(
        export=ExportResult(
            path=destination,
            sha256_hex=sha256_hex,
            md5_hex=md5_hex,
            md5_base64=md5_base64,
            size_bytes=size_bytes,
            source_bytes=before[1],
            migration_version=version,
            elapsed_seconds=time.perf_counter() - started,
        ),
        observed=observed,
        lock_seconds=lock_seconds,
    )


def _file_signature(path: Path) -> tuple[int, int]:
    info = path.stat()
    return info.st_mtime_ns, info.st_size


def _wal_is_empty(database_path: Path) -> bool:
    try:
        return wal_path(database_path).stat().st_size == 0
    except FileNotFoundError:
        return True


def _live_handle(path: Path) -> int:
    """라이브 파일을 읽는 번호. 한 파일에 하나를 두고 **닫지 않는다**(모듈 설명).

    파일이 바뀌었으면(같은 경로의 새 파일) 옛 번호만 닫는다 — 그 번호의 잠금은 이미 쓰지 않는
    옛 파일의 것이다.
    """
    key = path.resolve()
    with _LIVE_HANDLES_LOCK:
        current = os.stat(path)
        handle = _LIVE_HANDLES.get(key)
        if handle is not None:
            held = os.fstat(handle)
            if (held.st_dev, held.st_ino) == (current.st_dev, current.st_ino):
                return handle
            os.close(handle)
        handle = os.open(path, os.O_RDONLY)
        _LIVE_HANDLES[key] = handle
        return handle


def _copy_live_bytes(database_path: Path, destination: Path, size: int) -> None:
    """닫지 않는 번호에서 사본으로 바이트를 옮긴다. 큰 버퍼를 쓰지 않아 메모리가 늘지 않는다."""
    if sys.platform == "win32":
        raise RuntimeError("앱 안 바이트 복사는 컨테이너(Linux)에서만 돕니다.")
    source = _live_handle(database_path)
    with destination.open("wb") as target:
        offset = 0
        while offset < size:
            count = min(size - offset, _COPY_CHUNK_BYTES)
            try:
                sent = os.sendfile(target.fileno(), source, offset, count)
            except OSError as exc:
                if exc.errno not in (errno.EINVAL, errno.ENOSYS):
                    raise
                sent = os.write(target.fileno(), os.pread(source, count, offset))
            if sent == 0:
                raise SnapshotRaced(f"복사하는 동안 파일이 줄었습니다: {database_path.name}")
            offset += sent


def _verified_copy_version(path: Path, dataset: DatasetName) -> int:
    """사본을 열어 표가 있는지 보고 마이그레이션 판을 읽는다. 못 열면 그 예외가 그대로 오른다."""
    with connect(path) as connection:
        tables = connection.execute("SELECT COUNT(*) FROM duckdb_tables()").fetchone()
    if tables is None or int(tables[0]) == 0:
        raise SnapshotRejected("사본에 표가 하나도 없습니다.", kind=FAILURE_CORRUPT)
    return read_migration_version(path, dataset)


def digest_file(path: Path, *, chunk_bytes: int = 4 * 1024 * 1024) -> tuple[str, str, str, int]:
    """(sha256 hex, md5 hex, md5 base64, 크기). md5 는 S3 의 `Content-MD5` 용이다."""
    sha256 = hashlib.sha256()
    md5 = hashlib.md5(usedforsecurity=False)
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_bytes)
            if not chunk:
                break
            size += len(chunk)
            sha256.update(chunk)
            md5.update(chunk)
    return (
        sha256.hexdigest(),
        md5.hexdigest(),
        base64.b64encode(md5.digest()).decode("ascii"),
        size,
    )


def read_migration_version(database_path: Path, dataset: DatasetName) -> int:
    """DB 파일에 적용된 마이그레이션 최고 버전. 표가 없으면 0."""
    table = MIGRATION_SCHEMA[dataset]
    with connect(database_path) as connection:
        exists = connection.execute(
            "SELECT COUNT(*) FROM duckdb_tables() WHERE schema_name = ? AND table_name = ?",
            list(table.split(".")),
        ).fetchone()
        if exists is None or int(exists[0]) == 0:
            return 0
        row = connection.execute(f"SELECT COALESCE(MAX(version), 0) FROM {table}").fetchone()
        return 0 if row is None else int(row[0])


def code_migration_version(dataset: DatasetName) -> int:
    """이 코드가 아는 마이그레이션 최고 버전. 숫자를 상수로 박지 않는다."""
    if dataset == "simulation":
        versions = [migration.version for migration in load_migrations()]
    else:
        versions = [migration.version for migration in load_equipment_migrations()]
    return max(versions) if versions else 0


def verify_snapshot(
    path: Path,
    *,
    dataset: DatasetName,
    expected_sha256: str,
    expected_size: int,
    code_version: int,
    rejected_path: Path | None = None,
) -> int:
    """받은 스냅샷을 설치 전에 검사한다. 실패하면 `.rejected` 로 남기고 예외를 낸다.

    깨진 파일을 제자리에 놓는 것이 이 흐름에서 가장 나쁜 결과라, 크기·해시·내용·버전을
    모두 본 뒤에만 통과시킨다. 남길 자리(`rejected_path`)를 주지 않으면 `<파일>.rejected` 다 —
    작업 파일 이름이 회차마다 다를 때 거부본이 쌓이지 않게 호출자가 고정 이름을 준다.
    갈래는 `SnapshotRejected.kind` 다 — 못 여는 파일도 `corrupt` 로 올린다.
    """
    try:
        actual_sha256, _, _, actual_size = digest_file(path)
        if actual_size != expected_size:
            raise SnapshotRejected(
                f"스냅샷 크기가 다릅니다: {actual_size} != {expected_size}", kind=FAILURE_CORRUPT
            )
        if actual_sha256 != expected_sha256:
            raise SnapshotRejected("스냅샷 sha256 이 포인터와 다릅니다.", kind=FAILURE_CORRUPT)
        try:
            file_version = _verified_copy_version(path, dataset)
        except duckdb.Error as exc:
            raise SnapshotRejected(
                f"스냅샷을 열지 못했습니다: {exc}", kind=FAILURE_CORRUPT
            ) from exc
        comparison = compare_migration_version(file_version=file_version, code_version=code_version)
        if comparison == "newer":
            raise SnapshotRejected(
                f"스냅샷의 마이그레이션 버전 {with_subject_particle(str(file_version))} 이 "
                f"배포본({code_version})보다 "
                "최신입니다. 앱을 최신 배포본으로 올린 뒤 다시 받으세요.",
                kind=FAILURE_SCHEMA_NEWER,
            )
    except Exception:
        rejected = rejected_path or path.with_name(path.name + ".rejected")
        if rejected.exists():
            rejected.unlink()
        if path.exists():
            path.replace(rejected)
        raise
    return file_version


def install_snapshot(source: Path, database_path: Path) -> InstallResult:
    """검증된 스냅샷을 제자리에 놓는다. 순서가 계약이다.

    `.wal` 을 먼저 치우지 않으면, 남의 스냅샷 위에 이전 계보의 WAL 이 재생돼 두 DB 가
    섞인다. 그리고 기존 파일은 지우지 않고 항상 백업으로 옮긴다 — 되돌릴 수 있어야 한다.
    실패하면 DB 와 **앞서 옮긴 WAL 까지** 되돌린다. WAL 에만 있던 커밋(앱이 쓰던 자리)이
    백업에 남은 채 DB 만 돌아오면 그 커밋이 빠진 파일이 된다.
    """
    backup_root = backup_dir()
    backup_root.mkdir(parents=True, exist_ok=True)
    existing_wal = wal_path(database_path)
    stamp = _unique_stamp(backup_root, database_path)

    wal_backup: Path | None = None
    if existing_wal.exists():
        wal_backup = backup_root / f"{existing_wal.name}.{stamp}"
        existing_wal.replace(wal_backup)

    database_backup: Path | None = None
    try:
        if database_path.exists():
            candidate = backup_root / f"{database_path.name}.{stamp}"
            database_path.replace(candidate)
            database_backup = candidate
        source.replace(database_path)
    except OSError:
        # WAL 은 그 DB 의 것이라 DB 를 되돌린 뒤에만 되돌린다.
        if database_backup is not None:
            database_backup.replace(database_path)
        if wal_backup is not None:
            wal_backup.replace(existing_wal)
        raise
    return InstallResult(
        database_backup=database_backup, wal_backup=wal_backup, backup_dir=backup_root
    )


def restore_install(result: InstallResult, database_path: Path) -> None:
    """`install_snapshot` 을 되돌린다 — 둘째 DB 설치가 실패했을 때 첫째를 앞 상태로."""
    if result.database_backup is not None:
        result.database_backup.replace(database_path)
    else:
        database_path.unlink(missing_ok=True)
    if result.wal_backup is not None:
        result.wal_backup.replace(wal_path(database_path))


def require_free_space(folder: Path, needed_bytes: int) -> None:
    """받기 앞 점검. 받다가 디스크가 차면 작업 파일만 남고 실패 갈래가 흐려진다."""
    probe = folder
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    free = shutil.disk_usage(probe).free
    if free < needed_bytes:
        raise DiskSpaceShort(needed_bytes, free)


def _unique_stamp(backup_root: Path, database_path: Path) -> str:
    """백업 이름 꼬리. 같은 초에 두 번 설치해도 앞의 백업을 덮지 않게 `-N` 을 붙인다."""
    base = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stamp = base
    counter = 1
    while any(
        (backup_root / f"{name}.{stamp}").exists()
        for name in (database_path.name, wal_path(database_path).name)
    ):
        counter += 1
        stamp = f"{base}-{counter}"
    return stamp


def prune_superseded_backups(
    database_path: Path, *, keep: int = KEEP_SUPERSEDED
) -> tuple[Path, ...]:
    """이 DB 의 superseded 백업을 최근 `keep` 번 설치 몫만 남기고 지운다. 지운 경로를 돌려준다.

    한 번 설치가 남긴 DB 백업과 WAL 백업은 같은 꼬리(시각)를 쓰므로 한 묶음으로 남기거나 지운다.
    이름이 이 DB 의 백업 꼴이 아닌 파일(다른 DB·사람이 둔 파일)은 건드리지 않는다. 받기(pull)가
    설치를 마친 뒤에 부른다.
    """
    if keep < 1:
        raise ValueError("남길 백업 수는 1 이상이어야 합니다.")
    root = backup_dir()
    if not root.exists():
        return ()
    prefixes = (f"{wal_path(database_path).name}.", f"{database_path.name}.")
    groups: dict[str, list[Path]] = {}
    for entry in root.iterdir():
        if not entry.is_file():
            continue
        for prefix in prefixes:
            if entry.name.startswith(prefix):
                stamp = entry.name[len(prefix) :]
                if _BACKUP_STAMP.match(stamp):
                    groups.setdefault(stamp, []).append(entry)
                break
    removed: list[Path] = []
    for stamp in sorted(groups, key=_stamp_order, reverse=True)[keep:]:
        for entry in groups[stamp]:
            try:
                entry.unlink()
            except OSError:
                # 다른 프로세스가 잡고 있으면 다음 받기에서 지운다. 받기를 실패로 만들 일이 아니다.
                continue
            removed.append(entry)
    return tuple(sorted(removed))


def _stamp_order(stamp: str) -> tuple[str, int]:
    base, _, counter = stamp.partition("-")
    return base, int(counter) if counter else 1


def _dataset_of(database_path: Path) -> DatasetName:
    """경로가 어느 DB 인지. 설비 DB 만 이름이 다르고 나머지는 시뮬레이션으로 본다."""
    return "equipment" if "equipment" in database_path.name else "simulation"


def _quote(path: Path) -> str:
    """DuckDB 문자열 리터럴에 넣을 경로. 작은따옴표만 이스케이프하면 된다."""
    return str(path).replace("'", "''")


def unique_work_path(scratch: Path, dataset: DatasetName, role: str) -> Path:
    """회차마다 다른 작업 파일 이름. 같은 작업 폴더를 쓰는 둘이 서로의 파일을 지우지 않게 한다."""
    return scratch / f"{dataset}-{role}-{uuid4().hex[:12]}.duckdb"


def prepare_scratch() -> Path:
    """작업 디렉터리를 만들고 돌려준다. 오래된 잔여물은 호출자가 정리한다."""
    directory = scratch_dir()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def clear_scratch(*, keep_backups: bool = True) -> None:
    """작업 파일을 지운다. 백업은 기본으로 남긴다 — 되돌릴 수단이라 함께 지우지 않는다."""
    directory = scratch_dir()
    if not directory.exists():
        return
    for entry in directory.iterdir():
        if keep_backups and entry.name == BACKUP_DIRNAME:
            continue
        if entry.is_dir():
            shutil.rmtree(entry, ignore_errors=True)
        else:
            try:
                entry.unlink()
            except OSError:
                # 다른 프로세스가 잡고 있으면 다음 기회에 지운다. 여기서 실패를 올릴 이유가 없다.
                pass


def utc_timestamp() -> str:
    """포인터·키에 쓰는 UTC 시각. `os` 로컬 시각을 쓰지 않는다."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def author_label() -> str:
    """포인터에 남길 작성자. 사람이 누가 올렸는지 알아볼 정도면 된다."""
    user = os.environ.get("USERNAME") or os.environ.get("USER") or "unknown"
    host = os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "unknown-host"
    return f"{user}@{host}"
