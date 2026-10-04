# Purpose: DuckDB 파일을 일관된 스냅샷으로 내보내고 받은 스냅샷을 검증해 제자리에 설치한다.

"""라이브 DuckDB 파일을 바이트로 만지지 않고 스냅샷을 주고받는 계층.

**라이브 `.duckdb` 파일을 절대 읽지 않는다.** 이 저장소에서 실측한 두 가지가 이유다.

1. 연결이 하나라도 열려 있으면 같은 프로세스에서도 `open(path, "rb")` 가
   `PermissionError` 다. Windows 에서 DuckDB 가 공유 읽기 없이 파일을 연다.
2. `app.py` 의 핀이 열려 있는 동안 COMMIT 된 내용은 `<이름>.wal` 에만 있고 본 파일은
   바이트가 변하지 않는다. 그 상태로 파일을 올리면 **방금 저장한 리비전이 통째로 빠진
   파일**이 올라간다.

그래서 DuckDB 자신에게 스냅샷을 만들게 한다 — `ATTACH` + `COPY FROM DATABASE`. 이 경로는
트랜잭션 상태를 읽으므로 방금의 COMMIT 이 포함되고, 핀이 열린 채로도 성공하며, 산출물에는
`.wal` 이 없다. 실측: 67,383,296 B → 21,524,480 B, 3.21초.

DuckDB 를 열 때는 반드시 `_sql_helpers.connect()` 를 쓴다. `duckdb.connect(path,
read_only=True)` 는 같은 프로세스의 다른 연결과 configuration 이 달라 연결 자체가 거부된다.
"""

from __future__ import annotations

import base64
import hashlib
import os
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from capa_simulation import settings
from capa_simulation.persistence._sql_helpers import DUCKDB_BLOCK_SIZE, connect
from capa_simulation.persistence.equipment_migration_runner import load_equipment_migrations
from capa_simulation.persistence.migration_runner import load_migrations
from capa_simulation.services.object_storage_manifest import (
    MIGRATION_SCHEMA,
    DatasetName,
    compare_migration_version,
)

SCRATCH_DIRNAME: Final = "objectstore"
BACKUP_DIRNAME: Final = "superseded"


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
    started = time.perf_counter()
    source_bytes = database_path.stat().st_size
    with connect(database_path) as connection:
        # 파일 스템이 아니라 DuckDB 가 아는 이름이어야 한다. 파일명이 바뀌어도 따라간다.
        row = connection.execute("SELECT current_database()").fetchone()
        if row is None:
            raise RuntimeError(f"현재 데이터베이스 이름을 읽지 못했습니다: {database_path}")
        name = str(row[0])
        connection.execute(f"ATTACH '{_quote(destination)}' AS snap (BLOCK_SIZE {int(block_size)})")
        try:
            connection.execute(f'COPY FROM DATABASE "{name}" TO snap')
        finally:
            connection.execute("DETACH snap")
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
) -> int:
    """받은 스냅샷을 설치 전에 검사한다. 실패하면 `.rejected` 로 남기고 예외를 낸다.

    깨진 파일을 제자리에 놓는 것이 이 흐름에서 가장 나쁜 결과라, 크기·해시·내용·버전을
    모두 본 뒤에만 통과시킨다.
    """
    try:
        actual_sha256, _, _, actual_size = digest_file(path)
        if actual_size != expected_size:
            raise RuntimeError(f"스냅샷 크기가 다릅니다: {actual_size} != {expected_size}")
        if actual_sha256 != expected_sha256:
            raise RuntimeError("스냅샷 sha256 이 포인터와 다릅니다.")
        with connect(path) as connection:
            tables = connection.execute("SELECT COUNT(*) FROM duckdb_tables()").fetchone()
            if tables is None or int(tables[0]) == 0:
                raise RuntimeError("스냅샷에 표가 하나도 없습니다.")
        file_version = read_migration_version(path, dataset)
        comparison = compare_migration_version(file_version=file_version, code_version=code_version)
        if comparison == "newer":
            raise RuntimeError(
                f"스냅샷의 마이그레이션 버전 {file_version} 이 이 배포본({code_version})보다 "
                "최신입니다. 앱을 최신 배포본으로 올린 뒤 다시 받으세요."
            )
    except Exception:
        rejected = path.with_name(path.name + ".rejected")
        if rejected.exists():
            rejected.unlink()
        if path.exists():
            path.replace(rejected)
        raise
    return file_version


def install_snapshot(source: Path, database_path: Path) -> Path:
    """검증된 스냅샷을 제자리에 놓는다. 순서가 계약이다.

    `.wal` 을 먼저 치우지 않으면, 남의 스냅샷 위에 이전 계보의 WAL 이 재생돼 두 DB 가
    섞인다. 그리고 기존 파일은 지우지 않고 항상 백업으로 옮긴다 — 되돌릴 수 있어야 한다.
    """
    backup_root = backup_dir()
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    existing_wal = wal_path(database_path)
    if existing_wal.exists():
        existing_wal.replace(backup_root / f"{existing_wal.name}.{stamp}")

    backup_path = backup_root / f"{database_path.name}.{stamp}"
    moved = False
    if database_path.exists():
        database_path.replace(backup_path)
        moved = True
    try:
        source.replace(database_path)
    except OSError:
        if moved:
            backup_path.replace(database_path)
        raise
    return backup_path if moved else backup_root


def _dataset_of(database_path: Path) -> DatasetName:
    """경로가 어느 DB 인지. 설비 DB 만 이름이 다르고 나머지는 시뮬레이션으로 본다."""
    return "equipment" if "equipment" in database_path.name else "simulation"


def _quote(path: Path) -> str:
    """DuckDB 문자열 리터럴에 넣을 경로. 작은따옴표만 이스케이프하면 된다."""
    return str(path).replace("'", "''")


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
