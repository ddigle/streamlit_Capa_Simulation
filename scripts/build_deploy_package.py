# Purpose: 사내 배포용 ZIP 을 배포 세트 규칙대로 만들고 금지·제외 파일을 검사한다.

"""사내 배포 ZIP 만들기.

배포 세트는 `git ls-files` 전체에 운영에 필요한 몇 개를 더한 것이다. `tests/`·`scripts/` 도
넣는다 — 사내 PC 에서 단독으로 돌려 보고 검증할 수 있어야 한다.

**`pyproject.toml` 과 `uv.lock` 은 빼고 보낸다.** 사내 PC 의 `pyproject.toml` 에는 삼성
Artifactory 인덱스 설정이 손으로 들어가 있고, 그 선언에서 나온 `uv.lock` 에는 `bigdataquery`
가 박혀 있다. 저장소에도 두 파일이 있지만 사외 기준이라(사내 인덱스도 `bigdataquery` 도
없다) 덮어쓰는 쪽이 항상 손해다.

**둘은 짝이라 함께 빼야 한다.** 하나만 보내면 사내에서 선언과 잠금이 어긋나 `uv sync` 가
락을 다시 만들려 들고, 그 순간 사내 전용 패키지가 환경에서 빠진다.

그래서 **의존성을 바꾸면 ZIP 만으로는 사내에 반영되지 않는다.** 그때는 바뀐 줄을 따로 알려
사내 PC 의 `pyproject.toml` 을 손으로 맞추고 거기서 `uv lock` 을 다시 돌려야 한다. 스크립트가
실행할 때마다 그 사실을 알린다.

사용:

    .\\.venv\\Scripts\\python.exe scripts\\build_deploy_package.py --out C:\\Dev\\배포
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import zipfile
from collections.abc import Iterable, Sequence
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# `git ls-files` 에 없지만 운영에 필요한 파일. 공용 표시순서의 부트스트랩 입력이다.
EXTRA_FILES: tuple[str, ...] = ("data/input/RQ_DISPLAY_ORDER.csv",)

# 추적되지만 보내지 않는 파일. 선언(`pyproject.toml`)과 그 잠금(`uv.lock`)은 짝이므로 둘
# 다 사내 것을 남긴다 — 하나만 덮으면 어긋난 채로 `uv sync` 가 락을 다시 만든다.
EXCLUDED_FILES: frozenset[str] = frozenset(
    {
        # 사내 PC 에만 있는 Artifactory 인덱스 설정을 덮지 않기 위해서다.
        "pyproject.toml",
        # 그 선언에서 나온 잠금. 사내 락에는 `bigdataquery` 가 박혀 있다.
        "uv.lock",
    }
)

# 들어가면 안 되는 것. `git ls-files` 로 시작하므로 보통은 걸릴 일이 없지만, 한 번 새면
# 되돌릴 수 없는 종류라(실데이터·비밀값) 보내기 전에 다시 본다.
FORBIDDEN_SUFFIXES: tuple[str, ...] = (".xlsb", ".xlsx", ".xlsm", ".duckdb", ".db", ".wal")
FORBIDDEN_NAMES: tuple[str, ...] = (".env", "secrets.toml")
FORBIDDEN_PREFIXES: tuple[str, ...] = ("data/output/", "data/temp/")

# 위 폴더 아래여도 보내는 파일. 빈 폴더를 만들어 두는 자리표이지 데이터가 아니다.
PLACEHOLDER_NAMES: tuple[str, ...] = (".gitkeep",)


def tracked_files(root: Path) -> list[str]:
    """`git ls-files` 결과. 경로 구분자는 git 이 쓰는 `/` 그대로 둔다."""
    completed = subprocess.run(
        ["git", "ls-files"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def deploy_set(tracked: Iterable[str], *, extras: Sequence[str] = EXTRA_FILES) -> list[str]:
    """보낼 파일 목록. 제외 목록을 빼고 추가 파일을 더한 뒤 한 번만 남긴다."""
    selected = [path for path in tracked if path not in EXCLUDED_FILES]
    for extra in extras:
        if extra not in selected:
            selected.append(extra)
    return sorted(set(selected))


def forbidden_entries(paths: Iterable[str]) -> list[str]:
    """배포하면 안 되는 경로. 빈 목록이어야 보낼 수 있다."""
    flagged: list[str] = []
    for path in paths:
        lowered = path.lower()
        name = lowered.rsplit("/", 1)[-1]
        if name in PLACEHOLDER_NAMES:
            continue
        if (
            lowered.endswith(FORBIDDEN_SUFFIXES)
            or name in FORBIDDEN_NAMES
            or lowered.startswith(FORBIDDEN_PREFIXES)
        ):
            flagged.append(path)
    return flagged


def build_archive(root: Path, paths: Sequence[str], destination: Path) -> int:
    """ZIP 을 만들고 넣은 항목 수를 돌려준다. 없는 파일은 그 자리에서 멈춘다."""
    missing = [path for path in paths if not (root / path).is_file()]
    if missing:
        raise FileNotFoundError(f"배포 세트에 없는 파일이 있습니다: {', '.join(missing[:5])}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(root / path, arcname=path)
    return len(paths)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="사내 배포 ZIP 을 만든다.")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="ZIP 을 둘 폴더. 파일 이름은 `YYYYMMDDHHMM.zip` 으로 짓는다.",
    )
    parser.add_argument(
        "--stamp",
        default=None,
        help="파일 이름에 쓸 시각. 생략하면 지금 시각을 쓴다.",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="ZIP 을 만들지 않고 보낼 목록만 출력한다.",
    )
    args = parser.parse_args(argv)

    paths = deploy_set(tracked_files(PROJECT_ROOT))
    flagged = forbidden_entries(paths)
    if flagged:
        print("배포하면 안 되는 파일이 세트에 있습니다:", file=sys.stderr)
        for path in flagged:
            print(f"  - {path}", file=sys.stderr)
        return 1

    if args.list_only:
        for path in paths:
            print(path)
        print(f"\n총 {len(paths):,}개")
        return 0

    if args.out is None:
        parser.error("ZIP 을 만들려면 --out 이 필요합니다(--list-only 는 예외).")
    stamp = args.stamp or datetime.now().strftime("%Y%m%d%H%M")
    destination = args.out / f"{stamp}.zip"
    count = build_archive(PROJECT_ROOT, paths, destination)
    size = destination.stat().st_size
    print(f"{destination} ({size:,} bytes, 엔트리 {count:,}개)")
    print(f"제외: {', '.join(sorted(EXCLUDED_FILES))}")
    print(
        "의존성을 바꿨다면 이 ZIP 만으로는 사내에 반영되지 않습니다 — "
        "`pyproject.toml`·`uv.lock` 은 보내지 않으므로 바뀐 줄을 따로 알리고 "
        "사내에서 `uv lock` 을 다시 돌려야 합니다."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
