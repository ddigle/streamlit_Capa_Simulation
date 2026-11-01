# Purpose: Actions 워크플로의 Windows pytest 작업이 막지 않고 Linux 와 같은 설치를 쓰는지 검사한다.

"""`.github/workflows/ci.yml` 의 작업 계약(2026-11-01 사용자 결정 A7 「추가 · 처음엔 막지 않음」).

사내는 Windows 에서 4관문을 돈다. 사외 CI 가 Linux 뿐이라 Windows 에서만 깨지는 시험(경로
구분자 · 명령줄 길이 · 권한 비트 — 사내 리뷰 202610271800 발견 2 의 16개)이 리뷰 한 바퀴 뒤에야
보였다. 그래서 둘째 작업이 Windows 에서 pytest 를 돌리되 작업 단위 `continue-on-error` 로
워크플로를 막지 않고, 설치는 Linux 작업과 같은 줄이어야 Windows 차이와 설치 차이를 가를 수 있다.

Actions 는 여기서 돌릴 수 없고 개발 환경에 YAML 해석기가 없어, 작업 덩어리를 들여쓰기로 잘라 줄을
견준다 — 이 파일의 들여쓰기 꼴(작업 두 칸 · 키 네 칸 · 단계 여섯 칸)이 계약이다.
"""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
LINUX_JOB = "verify"
WINDOWS_JOB = "windows-pytest"
JOB_HEAD = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")


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
    """설치 몫 — uv 를 까는 액션 줄과 그 설정, 파이썬 · 의존성 설치 `run:` 줄(테스트 앞까지)."""
    picked: list[str] = []
    for line in block:
        text = line.strip()
        if "pytest" in text or "ruff" in text or "mypy" in text:
            break
        if text.startswith(("uses: astral-sh/setup-uv", "- uses: astral-sh/setup-uv")):
            picked.append(text.removeprefix("- "))
        elif text.startswith(("enable-cache:", "cache-dependency-glob:", "fetch-depth:")):
            picked.append(text)
        elif text.startswith("run: uv "):
            picked.append(text)
    return picked


def _run_lines(block: list[str]) -> list[str]:
    return [line.strip() for line in block if line.strip().startswith("run: ")]


def test_the_workflow_has_a_windows_pytest_job_that_does_not_block() -> None:
    jobs = _jobs()
    assert set(jobs) == {LINUX_JOB, WINDOWS_JOB}

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


def test_the_windows_job_runs_the_same_pytest_line_and_only_pytest() -> None:
    jobs = _jobs()
    pytest_line = "run: uv run --no-sync python -m pytest -q"

    assert pytest_line in _run_lines(jobs[LINUX_JOB])
    windows_runs = _run_lines(jobs[WINDOWS_JOB])
    assert pytest_line in windows_runs
    assert not any("ruff" in line or "mypy" in line for line in windows_runs)
    assert any(line.strip() == "PYTHONIOENCODING: utf-8" for line in jobs[WINDOWS_JOB])
