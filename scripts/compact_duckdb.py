# Purpose: 회수되지 않은 DuckDB 사공간을 재구축으로 걷어내고 결과를 검증한다.

"""회수되지 않은 DuckDB 사공간을 재구축으로 걷어내고 결과를 검증한다.

DuckDB 는 삭제·재작성으로 생긴 free 블록을 파일 안쪽에 남겨 두고 CHECKPOINT 나 VACUUM 으로
파일을 줄이지 않는다. 공간을 실제로 회수하는 유일한 방법은 ATTACH 로 새 파일을 열어
COPY FROM DATABASE 로 전체를 옮겨 담는 것이다. 이 스크립트는 그 재구축을 하고,
바꿔치기 전에 테이블 목록과 행 수가 정확히 같은지 확인한다.

**앱 서버를 내린 뒤에 실행한다.** 앱은 rerun 이 끝나면 DB 연결을 닫으므로 유휴 상태의 앱은
잠금도 WAL 도 남기지 않아 이 스크립트가 알아보지 못한다. 그래서 두 겹으로 줄인다.

- 원본 행 수를 세는 순간부터 복사·검증이 끝날 때까지 원본을 한 연결에서 READ_ONLY 로
  붙들고 있다. 그동안 앱의 쓰기 연결은 잠금으로 곧바로 실패하므로, 복사 뒤의 저장이
  원본에만 남았다가 교체로 사라지는 대신 앱 쪽 오류가 된다. Windows 는 열린 파일을 옮길 수
  없어 교체 직전에 닫아야 하므로 닫고 옮기는 수 ms 의 틈은 남는다.
- managed 모드의 앱은 DB 옆 동기화 사이드카에 심장박동을 남긴다. 살아 있는 심장박동이
  보이면 시작 전에 중단한다. 다만 심장박동은 rerun 때만 적히므로 최근 90초 안에 rerun 한
  앱만 잡는다. managed 모드라도 유휴 상태의 앱은 보이지 않고, 사이드카가 없는 로컬 모드에서는
  아무것도 막지 못한다. 그래서 실행 중인 앱을 찾지 못하면 늘 직접 확인하라고 알린다.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import duckdb

from capa_simulation.persistence import sync_state
from capa_simulation.persistence._sql_helpers import DUCKDB_BLOCK_SIZE
from capa_simulation.services.korean_particle import with_direction_particle
from capa_simulation.settings import DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH

MIB = 1024 * 1024


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
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
    return parser.parse_args(argv)


def table_row_counts(connection: duckdb.DuckDBPyConnection, catalog: str) -> dict[str, int]:
    """붙인 카탈로그 하나의 표별 행 수. 키는 카탈로그를 뺀 `schema.table` 이다."""
    tables = connection.execute(
        "SELECT schema_name, table_name FROM duckdb_tables() WHERE database_name = ? ORDER BY 1, 2",
        [catalog],
    ).fetchall()
    counts: dict[str, int] = {}
    for schema_name, table_name in tables:
        row = connection.execute(
            f'SELECT COUNT(*) FROM "{catalog}"."{schema_name}"."{table_name}"'
        ).fetchone()
        counts[f"{schema_name}.{table_name}"] = 0 if row is None else int(row[0])
    return counts


def rebuild(
    source: Path, target: Path, block_size: int, storage_version: str | None
) -> tuple[dict[str, int], dict[str, int]]:
    """원본을 READ_ONLY 로 붙든 한 연결 안에서 세고, 옮기고, 다시 연 사본을 센다.

    원본 잠금은 돌려줄 때 풀린다. 사본은 한 번 닫았다 다시 붙여 세므로 파일에 실제로 적힌
    내용을 검증한다. 돌려주는 값은 (원본 행 수, 사본 행 수)다.
    """
    options = [f"BLOCK_SIZE {block_size}"]
    if storage_version:
        options.append(f"STORAGE_VERSION '{storage_version}'")
    connection = duckdb.connect()
    try:
        connection.execute(f"ATTACH '{source}' AS compact_source (READ_ONLY)")
        before_counts = table_row_counts(connection, "compact_source")
        connection.execute(f"ATTACH '{target}' AS compact_target ({', '.join(options)})")
        connection.execute("COPY FROM DATABASE compact_source TO compact_target")
        connection.execute("DETACH compact_target")
        connection.execute(f"ATTACH '{target}' AS compact_target (READ_ONLY)")
        after_counts = table_row_counts(connection, "compact_target")
        connection.execute("DETACH compact_target")
        connection.execute("DETACH compact_source")
    finally:
        connection.close()
    return before_counts, after_counts


def compact(database_path: Path, args: argparse.Namespace) -> bool:
    """한 파일을 재구축한다. 원본을 바꿔치기했으면 True 를 돌려준다."""
    if not database_path.exists():
        print(f"[건너뜀] 파일이 없습니다: {database_path}")
        return False

    instance = sync_state.live_instance(database_path)
    if instance is not None:
        raise SystemExit(
            f"[중단] {database_path.name} — 앱이 이 PC 에서 실행 중입니다(인스턴스 {instance}).\n"
            "       앱을 끈 뒤 다시 실행하세요."
        )
    print(
        f"[확인] {database_path.name} — 실행 중인 앱을 찾지 못했습니다. 심장박동 검사는 managed "
        f"모드에서 최근 {sync_state.HEARTBEAT_STALE_SECONDS:.0f}초 안에 rerun 한 앱만 잡으므로\n"
        "       유휴 상태의 앱과 로컬 모드의 앱은 보이지 않습니다.\n"
        "       앱 서버를 내렸는지 직접 확인하세요."
    )

    write_ahead_log = database_path.with_name(database_path.name + ".wal")
    if write_ahead_log.exists():
        raise SystemExit(
            f"[중단] {write_ahead_log.name} 이 남아 있습니다. "
            "앱이 실행 중이거나 비정상 종료했습니다.\n"
            "       앱을 정상 종료해 WAL 이 사라진 뒤 다시 실행하세요."
        )

    before_bytes = database_path.stat().st_size

    target = database_path.with_name(database_path.name + ".compact")
    if target.exists():
        target.unlink()
    before_counts, after_counts = rebuild(
        database_path, target, args.block_size, args.storage_version
    )

    after_bytes = target.stat().st_size
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
        print(f"  원본을 {with_direction_particle(backup.name)} 남겼습니다.")
    else:
        backup.unlink()
    return True


def main(argv: list[str] | None = None) -> int:
    """종료 코드를 돌려준다. `--database` 로 지정한 파일이 없으면 1 이다.

    생략했을 때의 운영 DB 두 개는 없을 수 있다(가용설비 DB 는 그 화면을 처음 열 때 생긴다).
    그러나 직접 지정한 파일이 없는 것은 대개 경로 오타라, 건너뛰고 0 으로 끝내면 아무것도
    하지 않았는데 성공으로 보인다.
    """
    args = parse_args(argv)
    if args.block_size < 16384 or args.block_size > 262144:
        raise SystemExit("[중단] --block-size 는 16384 이상 262144 이하여야 합니다.")
    if args.block_size & (args.block_size - 1):
        raise SystemExit("[중단] --block-size 는 2의 거듭제곱이어야 합니다.")

    requested = bool(args.database)
    targets = args.database or [DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH]
    replaced = 0
    missing = 0
    for database_path in targets:
        resolved = database_path.resolve()
        if requested and not resolved.exists():
            missing += 1
        if compact(resolved, args):
            replaced += 1
    if replaced:
        print(f"\n{replaced}개 파일을 재구축본으로 교체했습니다.")
    if missing:
        print(f"\n[실패] 지정한 파일 {missing}개를 찾지 못했습니다. 경로를 확인하세요.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
