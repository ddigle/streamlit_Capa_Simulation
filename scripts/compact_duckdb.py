# Purpose: 회수되지 않은 DuckDB 사공간을 재구축으로 걷어내고 결과를 검증한다.

"""회수되지 않은 DuckDB 사공간을 재구축으로 걷어내고 결과를 검증한다.

DuckDB 는 삭제·재작성으로 생긴 free 블록을 파일 안쪽에 남겨 두고 CHECKPOINT 나 VACUUM 으로
파일을 줄이지 않는다. 공간을 실제로 회수하는 유일한 방법은 ATTACH 로 새 파일을 열어
COPY FROM DATABASE 로 전체를 옮겨 담는 것이다. 이 스크립트는 그 재구축을 하고,
바꿔치기 전에 테이블 목록과 행 수가 정확히 같은지 확인한다.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import duckdb

from capa_simulation.persistence._sql_helpers import DUCKDB_BLOCK_SIZE
from capa_simulation.settings import DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH

MIB = 1024 * 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        action="append",
        help="재구축할 DuckDB 파일. 여러 번 줄 수 있다. 생략하면 운영 DB 두 개를 모두 처리한다.",
    )
    parser.add_argument(
        "--block-size",
        type=int,
        default=DUCKDB_BLOCK_SIZE,
        help=f"새 파일의 블록 크기 바이트. 16384~262144 의 2의 거듭제곱. 기본 {DUCKDB_BLOCK_SIZE}.",
    )
    parser.add_argument(
        "--storage-version",
        default=None,
        help="새 파일의 스토리지 버전. 지정하면 그보다 낮은 DuckDB 로는 열 수 없다.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="재구축 결과 크기만 재고 원본을 바꾸지 않는다.",
    )
    parser.add_argument(
        "--keep-backup",
        action="store_true",
        help="바꿔치기한 원본을 <파일명>.before_compact 로 남긴다.",
    )
    return parser.parse_args()


def table_row_counts(database_path: Path) -> dict[str, int]:
    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        tables = connection.execute(
            "SELECT schema_name, table_name FROM duckdb_tables() ORDER BY 1, 2"
        ).fetchall()
        counts: dict[str, int] = {}
        for schema_name, table_name in tables:
            row = connection.execute(
                f'SELECT COUNT(*) FROM "{schema_name}"."{table_name}"'
            ).fetchone()
            counts[f"{schema_name}.{table_name}"] = 0 if row is None else int(row[0])
        return counts
    finally:
        connection.close()


def rebuild(source: Path, target: Path, block_size: int, storage_version: str | None) -> None:
    options = [f"BLOCK_SIZE {block_size}"]
    if storage_version:
        options.append(f"STORAGE_VERSION '{storage_version}'")
    connection = duckdb.connect()
    try:
        connection.execute(f"ATTACH '{source}' AS compact_source (READ_ONLY)")
        connection.execute(f"ATTACH '{target}' AS compact_target ({', '.join(options)})")
        connection.execute("COPY FROM DATABASE compact_source TO compact_target")
        connection.execute("DETACH compact_target")
        connection.execute("DETACH compact_source")
    finally:
        connection.close()


def compact(database_path: Path, args: argparse.Namespace) -> bool:
    """한 파일을 재구축한다. 원본을 바꿔치기했으면 True 를 돌려준다."""
    if not database_path.exists():
        print(f"[건너뜀] 파일이 없습니다: {database_path}")
        return False

    write_ahead_log = database_path.with_name(database_path.name + ".wal")
    if write_ahead_log.exists():
        raise SystemExit(
            f"[중단] {write_ahead_log.name} 이 남아 있습니다. "
            "앱이 실행 중이거나 비정상 종료했습니다.\n"
            "       앱을 정상 종료해 WAL 이 사라진 뒤 다시 실행하세요."
        )

    before_bytes = database_path.stat().st_size
    before_counts = table_row_counts(database_path)

    target = database_path.with_name(database_path.name + ".compact")
    if target.exists():
        target.unlink()
    rebuild(database_path, target, args.block_size, args.storage_version)

    after_bytes = target.stat().st_size
    after_counts = table_row_counts(target)
    saved = before_bytes - after_bytes
    ratio = (saved / before_bytes * 100) if before_bytes else 0.0
    print(
        f"{database_path.name}: {before_bytes / MIB:.2f} MiB -> {after_bytes / MIB:.2f} MiB "
        f"({saved / MIB:+.2f} MiB, {ratio:.0f}% 감소) · 블록 {args.block_size} B"
    )

    if before_counts != after_counts:
        missing = sorted(set(before_counts) - set(after_counts))
        added = sorted(set(after_counts) - set(before_counts))
        changed = sorted(
            name
            for name in set(before_counts) & set(after_counts)
            if before_counts[name] != after_counts[name]
        )
        target.unlink()
        raise SystemExit(
            "[중단] 재구축 결과가 원본과 다릅니다. 원본을 그대로 두고 중단합니다.\n"
            f"       빠진 표 {missing}\n       늘어난 표 {added}\n       행 수가 다른 표 {changed}"
        )
    print(f"  검증 통과: 표 {len(after_counts)}개 · 행 {sum(after_counts.values()):,}개 일치")

    if args.dry_run:
        target.unlink()
        print("  --dry-run 이므로 원본을 바꾸지 않았습니다.")
        return False

    backup = database_path.with_name(database_path.name + ".before_compact")
    if backup.exists():
        backup.unlink()
    shutil.move(str(database_path), str(backup))
    shutil.move(str(target), str(database_path))
    if args.keep_backup:
        print(f"  원본을 {backup.name} 으로 남겼습니다.")
    else:
        backup.unlink()
    return True


def main() -> None:
    args = parse_args()
    if args.block_size < 16384 or args.block_size > 262144:
        raise SystemExit("[중단] --block-size 는 16384 이상 262144 이하여야 합니다.")
    if args.block_size & (args.block_size - 1):
        raise SystemExit("[중단] --block-size 는 2의 거듭제곱이어야 합니다.")

    targets = args.database or [DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH]
    replaced = 0
    for database_path in targets:
        if compact(database_path.resolve(), args):
            replaced += 1
    if replaced:
        print(f"\n{replaced}개 파일을 재구축본으로 교체했습니다.")


if __name__ == "__main__":
    sys.exit(main())
