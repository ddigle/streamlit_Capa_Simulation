# Purpose: Actions 작업의 시험 조각 · 판정 · Windows 작업의 설치가 약속대로인지 검사한다.

"""`.github/workflows/ci.yml` 의 작업 계약(2026-11-01 사용자 결정 A7 「추가 · 처음엔 막지 않음」).

사내는 Windows 에서 4관문을 돈다. 사외 CI 가 Linux 뿐이라 Windows 에서만 깨지는 시험(경로
구분자 · 명령줄 길이 · 권한 비트 — 사내 리뷰 202610271800 발견 2 의 16개)이 리뷰 한 바퀴 뒤에야
보였다. 그래서 둘째 작업이 Windows 에서 pytest 를 돌리되 작업 단위 `continue-on-error` 로
워크플로를 막지 않고, 설치는 Linux 작업과 같은 줄이어야 Windows 차이와 설치 차이를 가를 수 있다.

시험은 두 작업 모두 같은 수의 조각으로 나눈다(`scripts/run_test_shard.py`). 한 러너로는 시간 안에
끝나지 못해 초록도 빨강도 나오지 않았다 — 끝나지 못한 판이 Windows 실패를 사내까지 보냈다.

Actions 는 여기서 돌릴 수 없고 개발 환경에 YAML 해석기가 없어, 작업 덩어리를 들여쓰기로 잘라 줄을
견준다 — 이 파일의 들여쓰기 꼴(작업 두 칸 · 키 네 칸 · 단계 여섯 칸)이 계약이다.
"""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
LINUX_JOB = "verify"
WINDOWS_JOB = "windows-pytest"
VERDICT_JOB = "verify-result"
JOB_HEAD = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
SHARD_RUN = (
    "run: uv run --no-sync python scripts/run_test_shard.py "
    "--shard ${{ matrix.shard }} --of ${{ strategy.job-total }}"
)


def _jobs() -> dict[str, list[str]]:
    """`jobs:` 아래 작업 이름 → 그 덩어리의 줄(주석 · 빈 줄 뺌)."""
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    start = lines.index("jobs:") + 1
    jobs: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines[start:]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            break
        head = JOB_HEAD.match(line)
        if head is not None:
            current = head.group(1)
            jobs[current] = []
        elif current is not None:
            jobs[current].append(line.rstrip())
    return jobs


def _job_keys(block: list[str]) -> dict[str, str]:
    """작업 바로 아래 키(네 칸 들여쓰기) → 값."""
    keys: dict[str, str] = {}
    for line in block:
        found = re.match(r"^    ([A-Za-z-]+):\s*(.*)$", line)
        if found is not None:
            keys[found.group(1)] = found.group(2)
    return keys


def _install_lines(block: list[str]) -> list[str]:
    """설치 몫 — uv 를 까는 액션 줄과 그 설정, 파이썬 · 의존성 설치 `run:` 줄."""
    picked: list[str] = []
    for line in block:
        text = line.strip()
        if text.startswith(("uses: astral-sh/setup-uv", "- uses: astral-sh/setup-uv")):
            picked.append(text.removeprefix("- "))
        elif text.startswith(("enable-cache:", "cache-dependency-glob:", "fetch-depth:")):
            picked.append(text)
        elif text.startswith(("run: uv python ", "run: uv sync ")):
            picked.append(text)
    return picked


def _run_lines(block: list[str]) -> list[str]:
    return [line.strip() for line in block if line.strip().startswith("run: ")]


def _matrix_shards(block: list[str]) -> list[int]:
    [line] = [line.strip() for line in block if line.strip().startswith("shard: [")]
    return [int(item) for item in line.removeprefix("shard: [").removesuffix("]").split(",")]


def _steps_guarded_to_the_first_shard(block: list[str]) -> list[str]:
    """`if: matrix.shard == 1` 이 걸린 단계의 이름."""
    named = [
        line.strip().removeprefix("- name: ")
        for line, following in zip(block, block[1:], strict=False)
        if line.strip().startswith("- name: ") and following.strip() == "if: matrix.shard == 1"
    ]
    return named


def test_the_workflow_has_a_windows_pytest_job_that_does_not_block() -> None:
    jobs = _jobs()
    assert set(jobs) == {LINUX_JOB, WINDOWS_JOB, VERDICT_JOB}

    linux, windows = _job_keys(jobs[LINUX_JOB]), _job_keys(jobs[WINDOWS_JOB])
    assert windows["runs-on"] == "windows-latest"
    # 작업 단위 — 단계 단위면 실패가 초록 단계로 묻힌다. Linux 작업은 그대로 판정이다.
    assert windows["continue-on-error"] == "true"
    assert "continue-on-error" not in linux
    # Windows 러너는 같은 시험이 더 느리다.
    assert int(windows["timeout-minutes"]) >= int(linux["timeout-minutes"])
    # 사외 저장소에서만 — 배포 세트에 실려 사내 GitHub 에서 돌면 지울 수 없는 빨간 X 가 남는다.
    assert windows["if"] == linux["if"]


def test_the_windows_job_installs_exactly_like_the_linux_job() -> None:
    jobs = _jobs()
    linux, windows = _install_lines(jobs[LINUX_JOB]), _install_lines(jobs[WINDOWS_JOB])

    assert windows == linux
    assert "run: uv python install 3.10.11" in windows
    assert "run: uv sync --frozen --python 3.10.11" in windows
    assert "fetch-depth: 0" in windows


def test_the_windows_job_runs_the_same_shard_line_and_only_tests() -> None:
    jobs = _jobs()

    assert SHARD_RUN in _run_lines(jobs[LINUX_JOB])
    windows_runs = _run_lines(jobs[WINDOWS_JOB])
    assert SHARD_RUN in windows_runs
    assert not any("ruff" in line or "mypy" in line for line in windows_runs)
    assert any(line.strip() == "PYTHONIOENCODING: utf-8" for line in jobs[WINDOWS_JOB])


def test_both_jobs_cut_the_tests_into_the_same_shards() -> None:
    """같은 번호가 같은 파일이어야 Windows 빨간 조각을 Linux 같은 번호와 견준다."""
    jobs = _jobs()
    linux, windows = _matrix_shards(jobs[LINUX_JOB]), _matrix_shards(jobs[WINDOWS_JOB])

    assert linux == windows
    assert linux == list(range(1, len(linux) + 1))
    assert len(linux) > 1


def test_no_job_runs_the_whole_suite_on_one_runner() -> None:
    """옛 줄이 돌아오면 다시 시간 안에 못 끝나 초록도 빨강도 나오지 않는다."""
    runs = [line for block in _jobs().values() for line in _run_lines(block)]

    assert not any("-m pytest" in line for line in runs)


def test_every_shard_finishes_with_its_own_result() -> None:
    """앞 조각이 빨갛다고 뒤 조각을 끊으면 그 뒤로 결과가 없다."""
    jobs = _jobs()

    for name in (LINUX_JOB, WINDOWS_JOB):
        assert any(line.strip() == "fail-fast: false" for line in jobs[name]), name


def test_the_static_checks_run_once_not_on_every_shard() -> None:
    assert _steps_guarded_to_the_first_shard(_jobs()[LINUX_JOB]) == [
        "1/4 포맷",
        "2/4 린트",
        "3/4 타입",
    ]


def test_the_verdict_stands_on_every_linux_shard_and_also_when_they_stop() -> None:
    jobs = _jobs()
    verdict = _job_keys(jobs[VERDICT_JOB])

    assert verdict["needs"] == LINUX_JOB
    assert verdict["if"].startswith("always() && ")
    assert verdict["if"].endswith(_job_keys(jobs[LINUX_JOB])["if"])
    block = "\n".join(jobs[VERDICT_JOB])
    assert "needs.verify.result" in block
    assert "exit 1" in block


def test_each_shard_says_which_shard_it_was_in_the_summary() -> None:
    jobs = _jobs()

    for name in (LINUX_JOB, WINDOWS_JOB):
        summary = [line for line in jobs[name] if "조각 ${{ matrix.shard }}/" in line]
        assert len(summary) == 2, name
