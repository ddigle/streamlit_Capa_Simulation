# Purpose: 시험 파일을 크기로 고르게 N 조각으로 나눠 CI 가 그중 한 조각만 pytest 로 돌린다.

"""CI 시험 조각 실행기(`.github/workflows/ci.yml`).

시험이 15,000 건을 넘어 러너 한 대로는 작업 제한 시간 안에 끝나지 못한다. 그러면 초록도 빨강도
나오지 않는다. `uv.lock` 을 사내가 그대로 쓰므로 `pytest-xdist` 를 더하지 않고, 작업을 조각마다 러너
한 대로 나눈다.

    python scripts/run_test_shard.py --shard 3 --of 8          # 3 조각을 `pytest -q` 로 돈다
    python scripts/run_test_shard.py --shard 3 --of 8 --list   # 나누기만 하고 파일을 찍는다

- **고르게** — 무거운 파일부터 지금 가장 가벼운 조각에 넣는다. 무게는 파일 크기다. `.gitattributes`
  가 `.py` 를 LF 로 묶어 두 OS 의 크기가 같아서, Linux · Windows 의 같은 번호 조각은 같은 파일이다.
- **빠짐없이** — 인자 없는 `pytest` 가 줍는 꼴(`tests/` 아래 `test_*.py` · `*_test.py`)을 다 나눈다.
- 조각 안의 차례는 경로 차례고, 종료 코드는 pytest 의 것을 그대로 낸다.
- 시험 하나가 `HANG_REPORT_SECONDS` 를 넘기면 내장 faulthandler 가 스레드별 위치를 표준 오류에
  찍는다 — 작업이 시간 제한으로 끊겨도 어디서 멈췄는지 남는다.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_PATTERNS = ("test_*.py", "*_test.py")
HANG_REPORT_SECONDS = 600


def discover_files(root: Path = PROJECT_ROOT) -> list[Path]:
    """`root` 아래 `tests/` 에서 pytest 가 시험으로 줍는 파일을 저장소 상대 경로로."""
    found = {
        path.relative_to(root)
        for pattern in TEST_PATTERNS
        for path in (root / "tests").rglob(pattern)
    }
    return sorted(found)


def split_files(weights: dict[Path, int], pieces: int) -> list[list[Path]]:
    """무거운 파일부터 가벼운 조각에 넣는다. 같은 입력이면 늘 같은 조각이다."""
    shards: list[list[Path]] = [[] for _ in range(pieces)]
    loads = [0] * pieces
    for path in sorted(weights, key=lambda item: (-weights[item], item)):
        lightest = loads.index(min(loads))
        shards[lightest].append(path)
        loads[lightest] += weights[path]
    return [sorted(shard) for shard in shards]


def shard_of(shard: int, pieces: int, root: Path = PROJECT_ROOT) -> list[Path]:
    """`shard` 번(1 부터) 조각의 파일."""
    weights = {path: (root / path).stat().st_size for path in discover_files(root)}
    return split_files(weights, pieces)[shard - 1]


def pytest_command(files: Sequence[Path]) -> list[str]:
    return [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-o",
        f"faulthandler_timeout={HANG_REPORT_SECONDS}",
        *(path.as_posix() for path in files),
    ]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="시험 파일을 N 조각으로 나눠 한 조각을 돈다")
    parser.add_argument("--shard", type=int, required=True, help="돌릴 조각(1 부터)")
    parser.add_argument("--of", type=int, required=True, help="조각 수")
    parser.add_argument("--list", action="store_true", help="돌리지 않고 파일만 찍는다")
    options = parser.parse_args(argv)
    if not 1 <= options.shard <= options.of:
        parser.error("--shard 는 1 이상 --of 이하입니다.")
    return options


def main(argv: list[str] | None = None) -> int:
    options = parse_args(argv)
    files = shard_of(options.shard, options.of)
    if not files:
        print(f"조각 {options.shard}/{options.of} 에 시험 파일이 없습니다.", file=sys.stderr)
        return 2
    if options.list:
        print("\n".join(path.as_posix() for path in files))
        return 0
    print(f"조각 {options.shard}/{options.of} · 파일 {len(files)}개", flush=True)
    return subprocess.run(pytest_command(files), cwd=PROJECT_ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
