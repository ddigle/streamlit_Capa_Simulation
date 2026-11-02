# Purpose: 사내 모듈의 선언·정적 규칙·ruff·자기 시험을 보고 리뷰 블록과 전송용 요약 한 줄을 찍는다.

"""사내 모듈 점검 — 선언(M01)·정적 규칙(M02 ~ M14·M18 ~ M20)·ruff(M15·M16)·자기 시험(M17).

사외(개발 PC, WSL):

    .venv/bin/python scripts/check_module.py <id> [<id> ...]
    .venv/bin/python scripts/check_module.py --all --root tests/fixtures/modules --no-tests

담당자 클론(사내 PC, PowerShell — 저장소 뿌리에서):

    uv run --no-sync python scripts/check_module.py <id>
    uv run --no-sync python scripts/check_module.py --all

배포 적용(런북 4-5 — `git archive` 사본 트리의 **이** 스크립트를 저장소 `.venv` 로, 운영
저장소에서):

    & $py "$e2e\\scripts\\check_module.py" --all --worktree-of . --output "$HOME\\module_check.md"

선택: `--root <모듈 뿌리>`(기본 <이 트리>/modules — 이름이 `modules` 여야 한다) · `--worktree-of
<운영 저장소>`(그 체크아웃의 `modules/` 아래 커밋 안 한 수정·추적 안 된 파일 수) · `--no-ruff` ·
`--no-tests` · `--output <파일>`(같은 블록을 파일에도).

**이 트리로 본다.** `PROJECT_ROOT` 는 이 스크립트가 놓인 트리다 — 사본 트리의 스크립트를 부르면
사본의 코어·`pyproject.toml`·`requirements.txt` 로 본다. 모듈 시험은 감시
러너(`module_test_runner.py`)가 하위 프로세스로 돌린다 — 코어 `data/` 를 열거나 모듈 폴더·트리
안(상대 경로 쓰기)에 쓰면 실패하고, 같은 폴더 맨이름 import 는 앱처럼 깨진다. 임시 데이터
자리를 쓰므로 앱이 떠 있어도 운영 모듈 데이터를 잠그지 않는다. DB 를 열지 않는다.

**정적 오류가 먼저다.** M01·M06·M07·M10·M11 가운데 오류가 하나라도 있으면 시험을 돌리지
않는다(실패로 센다). `CAPA_MODULES_ROOT`·`CAPA_MODULES_DISABLED` 는 따르지 않는다(앱 실행 때의
일이다) — 값이 있으면 머리 줄에 알린다.

**출력.** 리뷰 전문 「적용 · 관문」 에 그대로 붙이는 블록과 끝의 `전송용 요약:` 한 줄(압축본 `모듈`
칸). 요약 줄에는 모듈 id 를 싣지 않는다 — 블록의 차례 번호 `m<n>` 만 쓴다(id 와 번호의 대응은
전문에만). 값(실데이터)은 찍지 않는다. 종료 코드: 실패 0개면 0, 하나라도 있으면 1, 사용법·뿌리
오류는 2.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import module_check_rules as rules  # noqa: E402

from capa_simulation import module_registry, navigation  # noqa: E402

MODULES_FOLDER_NAME: Final = "modules"
TEST_TIMEOUT_SECONDS: Final = 600
SUMMARY_LABEL: Final = "전송용 요약:"
_RUNNER: Final = Path(__file__).resolve().parent / "module_test_runner.py"
_RUNNER_SUMMARY: Final = re.compile(r"^module-tests (\d+) (\d+) (\d+)\s*$")
_RUNNER_BLOCKED: Final = re.compile(r"^감시가 막은 접근 (\d+)\s*$")
_FAILED_TEST: Final = re.compile(r"^(?:FAILED|ERROR) (\S+)")
_FIRST_PARTY: Final = 'lint.isort.known-first-party = ["capa_simulation", "modules"]'
_SHOWN_PATHS: Final = 20


def _use_utf8_stdout() -> None:
    # Windows 콘솔 기본 코드페이지(cp949)는 이 출력의 기호를 못 쓴다.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


# --- 결과 ----------------------------------------------------------------------------------------


@dataclass
class RuffResult:
    ran: bool
    check_count: int = 0
    format_count: int = 0
    failure: str = ""
    findings: list[rules.Finding] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.check_count + self.format_count


@dataclass
class TestResult:
    # `passed` · `failed` · `blocked`(정적 오류 먼저) · `skipped`(--no-tests) · `missing`(M14) ·
    # `timeout` · `runner`(러너 오류) · `empty`(모은 시험 0)
    state: str
    passed: int = 0
    failed: int = 0
    total: int = 0
    failures: list[str] = field(default_factory=list)
    guard_blocks: int = 0

    @property
    def is_failure(self) -> bool:
        return self.state in ("failed", "blocked", "timeout", "runner", "empty")


@dataclass
class ModuleResult:
    number: int
    record: module_registry.ModuleRecord
    findings: list[rules.Finding] = field(default_factory=list)
    third_party: set[str] = field(default_factory=set)
    ruff: RuffResult = field(default_factory=lambda: RuffResult(ran=False))
    tests: TestResult = field(default_factory=lambda: TestResult(state="skipped"))

    @property
    def label(self) -> str:
        return f"m{self.number}"

    @property
    def manifest_failed(self) -> bool:
        return self.record.state == "failed"

    @property
    def errors(self) -> list[rules.Finding]:
        return [item for item in self.findings if item.level == "error"]

    @property
    def warnings(self) -> list[rules.Finding]:
        return [item for item in self.findings if item.level == "warning"]

    @property
    def status(self) -> str:
        """`통과` · `꺼짐` · `실패`. 꺼짐(enabled=false)은 찾은 것이 있어도 실패로 세지 않는다."""
        if self.manifest_failed:
            return "실패"
        if self.record.state == "off":
            return "꺼짐"
        if self.errors or self.ruff.total or self.ruff.failure or self.tests.is_failure:
            return "실패"
        return "통과"


# --- 모듈 하나 -----------------------------------------------------------------------------------


def _relative_to(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def run_ruff(folder: Path, tree: Path) -> RuffResult:
    """`ruff check`(M15)·`ruff format --check`(M16) — 저장소 규칙(`<트리>/pyproject.toml`)으로."""
    config = ["--config", str(tree / "pyproject.toml"), "--config", _FIRST_PARTY]
    base = [sys.executable, "-m", "ruff"]
    try:
        checked = subprocess.run(
            [*base, "check", "--no-cache", *config, "--output-format", "json", str(folder)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=tree,
            check=False,
        )
        formatted = subprocess.run(
            [
                *base,
                "format",
                "--check",
                "--no-cache",
                *config,
                "--output-format",
                "json",
                str(folder),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=tree,
            check=False,
        )
    except OSError as error:
        return RuffResult(ran=True, failure=type(error).__name__)
    result = RuffResult(ran=True)
    try:
        violations = json.loads(checked.stdout or "[]")
    except ValueError:
        return RuffResult(ran=True, failure=f"ruff check rc={checked.returncode}")
    if checked.returncode not in (0, 1) or not isinstance(violations, list):
        return RuffResult(ran=True, failure=f"ruff check rc={checked.returncode}")
    for item in violations:
        location = item.get("location") or {}
        rel = _relative_to(Path(str(item.get("filename", ""))).resolve(), folder.resolve())
        result.findings.append(
            rules.Finding(
                "M15",
                "error",
                rel,
                int(location.get("row") or 0),
                f"{item.get('code') or '?'} {item.get('message', '')}".strip(),
            )
        )
    result.check_count = len(violations)
    if formatted.returncode not in (0, 1):
        result.failure = f"ruff format rc={formatted.returncode}"
        return result
    try:
        unformatted = json.loads(formatted.stdout or "[]")
    except ValueError:
        # 옛 ruff 의 줄 꼴(`Would reformat: <경로>`)도 읽는다.
        unformatted = [
            {"filename": line.split(":", 1)[1].strip()}
            for line in formatted.stdout.splitlines()
            if line.startswith("Would reformat:")
        ]
    files = sorted(
        {str(item.get("filename", "")) for item in unformatted if isinstance(item, dict)}
    )
    for name in files:
        path = Path(name)
        rel = _relative_to(
            (path if path.is_absolute() else tree / path).resolve(), folder.resolve()
        )
        result.findings.append(
            rules.Finding(
                "M16", "error", rel, 0, "ruff format 과 다릅니다(`ruff format` 으로 맞춤)"
            )
        )
    result.format_count = len(files)
    return result


def run_tests(
    folder: Path, *, root: Path, tree: Path, protect: Sequence[Path], timeout: int
) -> TestResult:
    """모듈 시험을 감시 러너 하위 프로세스로 돌린다(cwd = 트리, 임시 데이터 자리)."""
    work = Path(tempfile.mkdtemp(prefix="capa-module-test-"))
    data_root = work / "data"
    data_root.mkdir()
    try:
        command = [
            sys.executable,
            str(_RUNNER),
            "--modules-root",
            str(root),
            *(item for place in protect for item in ("--protect", str(place))),
            "--workspace",
            str(tree),
            "--data-root",
            str(work),
            "--",
            "-c",
            str(tree / "pyproject.toml"),
            "--rootdir",
            str(tree),
            "-p",
            "no:cacheprovider",
            "--import-mode=importlib",
            f"--basetemp={work / 'pytest'}",
            "-W",
            "ignore::pytest.PytestAssertRewriteWarning",
            "-rfE",
            str(folder / rules.TESTS_DIR),
        ]
        environment = module_test_environment(root=root, tree=tree, data_root=data_root)
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=tree,
                env=environment,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return TestResult(state="timeout")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return parse_runner_output(completed.stdout, completed.returncode)


def module_test_environment(*, root: Path, tree: Path, data_root: Path) -> dict[str, str]:
    """모듈 시험 하위 프로세스의 환경 — `modules.<id>` 가 **점검하는 그 뿌리**로 풀리게."""
    environment = dict(os.environ)
    front = [str(root.parent), str(tree / "src")]
    existing = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = os.pathsep.join([*front, *([existing] if existing else [])])
    environment[module_registry.DATA_ROOT_ENV_VAR] = str(data_root)
    environment[module_registry.ROOT_ENV_VAR] = str(root)
    environment.pop(module_registry.DISABLED_ENV_VAR, None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    return environment


def parse_runner_output(stdout: str, returncode: int) -> TestResult:
    """러너 출력의 마지막 `module-tests <통과> <실패> <전체>` 줄과 실패한 시험 이름을 읽는다."""
    summary: tuple[int, int, int] | None = None
    blocks = 0
    failures: list[str] = []
    for line in stdout.splitlines():
        matched = _RUNNER_SUMMARY.match(line)
        if matched is not None:
            summary = (int(matched.group(1)), int(matched.group(2)), int(matched.group(3)))
            continue
        blocked = _RUNNER_BLOCKED.match(line)
        if blocked is not None:
            blocks = int(blocked.group(1))
            continue
        failed = _FAILED_TEST.match(line)
        if failed is not None:
            node = failed.group(1)
            name = node.split("::", 1)
            failures.append(
                f"{Path(name[0]).name}::{name[1]}" if len(name) == 2 else Path(node).name
            )
    if summary is None:
        return TestResult(state="runner", failures=failures)
    passed, failed_count, total = summary
    if total == 0:
        return TestResult(state="empty", guard_blocks=blocks)
    state = "failed" if failed_count or returncode != 0 or blocks else "passed"
    return TestResult(
        state=state,
        passed=passed,
        failed=failed_count,
        total=total,
        failures=list(dict.fromkeys(failures)),
        guard_blocks=blocks,
    )


def check_one(
    result: ModuleResult,
    *,
    root: Path,
    tree: Path,
    environment: rules.PackageEnvironment,
    git: bool,
    ruff: bool,
    tests: bool,
    protect: Sequence[Path],
    timeout: int,
) -> None:
    record = result.record
    if result.manifest_failed:
        result.findings.append(rules.Finding("M01", "error", "module.json", 0, record.reason))
        return
    manifest = record.manifest
    assert manifest is not None
    folder = record.path
    files = rules.module_files(folder)
    view = rules.git_view(folder, files) if git else None
    static = rules.check_module_folder(
        folder,
        module_id=manifest.id,
        pages=[page.file for page in manifest.pages],
        environment=environment,
        git=view,
    )
    result.findings.extend(static.findings)
    result.third_party.update(static.third_party)
    if ruff:
        result.ruff = run_ruff(folder, tree)
    if not tests:
        result.tests = TestResult(state="skipped")
    elif any(item.rule == "M14" for item in result.errors):
        result.tests = TestResult(state="missing")
    elif any(item.rule in rules.BLOCKING_RULES for item in result.errors):
        result.tests = TestResult(state="blocked")
    else:
        result.tests = run_tests(folder, root=root, tree=tree, protect=protect, timeout=timeout)


def clash_warnings(
    records: Sequence[module_registry.ModuleRecord],
) -> dict[str, list[rules.Finding]]:
    """화면 이름을 먼저 차지해 차례가 뒤인 켜진 모듈을 실패로 만든 모듈 → 그 경고(M01).

    겹침은 차례가 뒤인 모듈 전체를 빼므로, 새 모듈이 기존 모듈을 밀어내도 새 모듈 담당자의 점검은
    통과로만 보인다. 차례가 앞인 쪽에도 알려 둘 중 누가 이름을 바꿀지 담당자끼리 정하게 한다.
    """
    found: dict[str, list[rules.Finding]] = {}
    for record in records:
        clash = record.clash
        if clash is None or not clash.owner:
            continue
        found.setdefault(clash.owner, []).append(
            rules.Finding(
                "M01",
                "warning",
                module_registry.MANIFEST_NAME,
                0,
                f"화면 이름 「{clash.title}」 을 차례가 뒤인 모듈 {record.folder_name} 도 써서 "
                "그 모듈 전체가 실패합니다 — 둘 가운데 하나의 화면 이름을 바꿉니다",
            )
        )
    return found


# --- 운영 체크아웃(--worktree-of) ----------------------------------------------------------------


@dataclass(frozen=True)
class WorktreeState:
    modified: tuple[str, ...]
    untracked: tuple[str, ...]


def _porcelain_paths(raw: bytes) -> list[str]:
    """`git status --porcelain -z` 레코드 — `XY 경로`, 이름 바꿈은 뒤에 옛 경로 레코드가 하나 더
    붙는다.

    앞 칸(`XY`)이 공백일 수 있어(` M modules/…`) `strip()` 하지 않는다.
    """
    records = raw.decode("utf-8", "replace").split("\0")
    paths: list[str] = []
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if len(record) < 4:
            continue
        status, path = record[:2], record[3:]
        paths.append(path)
        if "R" in status or "C" in status:
            index += 1
    return paths


def worktree_state(repository: Path) -> WorktreeState:
    """운영 체크아웃의 `modules/`(대소문자 무시) 아래 커밋 안 한 수정과 추적 안 된 파일."""
    pathspec = ":(icase)modules/"
    status = subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "status",
            "--porcelain",
            "-z",
            "--untracked-files=no",
            "--",
            pathspec,
        ],
        capture_output=True,
        check=True,
    )
    others = subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "ls-files",
            "-z",
            "--others",
            "--exclude-standard",
            "--",
            pathspec,
        ],
        capture_output=True,
        check=True,
    )
    untracked = [item for item in others.stdout.decode("utf-8", "replace").split("\0") if item]
    return WorktreeState(
        modified=tuple(_porcelain_paths(status.stdout)), untracked=tuple(untracked)
    )


# --- 출력 ----------------------------------------------------------------------------------------


def _api(record: module_registry.ModuleRecord) -> str:
    manifest = record.manifest
    return "?" if manifest is None else f"{manifest.api}.{manifest.api_minor}"


def _error_breakdown(errors: Sequence[rules.Finding]) -> str:
    counts: dict[str, int] = {}
    for item in errors:
        counts[item.rule] = counts.get(item.rule, 0) + 1
    if not counts:
        return ""
    return "(" + " · ".join(f"{rule} {counts[rule]}" for rule in sorted(counts)) + ")"


def _ruff_text(ruff: RuffResult) -> str:
    if not ruff.ran:
        return "ruff 안 돎"
    if ruff.failure:
        return f"ruff 실행 실패({ruff.failure})"
    return "ruff ok" if ruff.total == 0 else f"ruff {ruff.total}"


def _tests_text(tests: TestResult) -> str:
    return {
        "passed": f"시험 {tests.passed} 통과",
        "failed": f"시험 실패 {tests.failed}/{tests.total}",
        "blocked": "시험 안 돎 — 정적 오류 먼저",
        "skipped": "시험 건너뜀(--no-tests)",
        "missing": "시험 없음(M14)",
        "timeout": f"시험 시간 넘김({TEST_TIMEOUT_SECONDS}초)",
        "runner": "시험 러너 오류",
        "empty": "모은 시험 0",
    }[tests.state]


def module_line(result: ModuleResult) -> str:
    record = result.record
    head = f"- {result.label} {record.folder_name} {result.status}"
    if result.manifest_failed:
        api = f" · API {_api(record)}" if record.manifest is not None else ""
        return f"{head} · 선언 — {record.reason}{api}"
    manifest = record.manifest
    assert manifest is not None
    parts = [head]
    if record.state == "off":
        parts.append(record.reason)
    errors = result.errors
    parts += [
        manifest.maturity,
        f"API {_api(record)}",
        f"화면 {len(manifest.pages)}",
        f"오류 {len(errors)}{_error_breakdown(errors)}",
        f"경고 {len(result.warnings)}",
        _ruff_text(result.ruff),
        _tests_text(result.tests),
    ]
    return " · ".join(parts)


def _ng_token(result: ModuleResult) -> str:
    if result.manifest_failed:
        return f"{result.label} 선언"
    parts: list[str] = []
    if result.errors:
        parts.append(f"오류{len(result.errors)}")
    if result.ruff.failure:
        parts.append("ruff실패")
    elif result.ruff.total:
        parts.append(f"ruff{result.ruff.total}")
    tests = result.tests
    if tests.state == "failed":
        parts.append(f"시험실패{tests.failed}/{tests.total}")
    elif tests.state == "blocked":
        parts.append("시험안돎")
    elif tests.state == "timeout":
        parts.append("시험시간넘김")
    elif tests.state == "runner":
        parts.append("시험러너오류")
    elif tests.state == "empty":
        parts.append("시험0")
    return f"{result.label} {'.'.join(parts)}"


def _api_distribution(results: Sequence[ModuleResult]) -> list[str]:
    counts: dict[int, int] = {}
    for result in results:
        manifest = result.record.manifest
        if manifest is not None:
            counts[manifest.api] = counts.get(manifest.api, 0) + 1
    return [f"api{major} {counts[major]}" for major in sorted(counts)]


def _detail_lines(results: Sequence[ModuleResult], worktree: WorktreeState | None) -> list[str]:
    lines: list[str] = []
    for result in results:
        prefix = f"  {result.label} {result.record.folder_name}"
        everything = [*result.findings, *result.ruff.findings]
        ordered = sorted(
            everything, key=lambda item: (item.level != "error", item.rule, item.path, item.line)
        )
        lines += [f"{prefix} {item.text()}" for item in ordered]
        for name in result.tests.failures:
            lines.append(f"{prefix} 오류 M17 시험 실패 {name}")
        if result.tests.guard_blocks:
            lines.append(f"{prefix} 오류 M17 감시가 막은 접근 {result.tests.guard_blocks}")
    if worktree is not None:
        for path in worktree.modified[:_SHOWN_PATHS]:
            lines.append(f"  운영 체크아웃 커밋 안 한 수정 {path}")
        for path in worktree.untracked[:_SHOWN_PATHS]:
            lines.append(f"  운영 체크아웃 추적 안 된 파일 {path}")
    return lines


def _root_label(root: Path) -> str:
    return _relative_to(root, PROJECT_ROOT).rstrip("/") + "/"


def _environment_line() -> str | None:
    values = [
        f"{name}={os.environ[name]}"
        for name in (module_registry.ROOT_ENV_VAR, module_registry.DISABLED_ENV_VAR)
        if os.environ.get(name, "").strip()
    ]
    if not values:
        return None
    return f"환경변수 {' · '.join(values)} — 점검은 따르지 않는다(앱 실행 때만 걸린다)"


def build_block(
    results: Sequence[ModuleResult],
    *,
    root: Path,
    worktree: WorktreeState | None,
    git_checked: bool,
    root_warning: bool,
) -> list[str]:
    """리뷰 전문에 붙이는 블록(끝 줄이 전송용 요약)."""
    counts = {
        state: sum(1 for item in results if item.status == state)
        for state in ("통과", "꺼짐", "실패")
    }
    total = len(results)
    lines = [
        f"모듈 점검 — 뿌리 {_root_label(root)} · {total}개 = 통과 {counts['통과']} + "
        f"꺼짐 {counts['꺼짐']} + 실패 {counts['실패']}"
    ]
    if worktree is not None:
        lines.append(
            f"운영 체크아웃 modules/ — 커밋 안 한 수정 {len(worktree.modified)} · "
            f"추적 안 된 파일 {len(worktree.untracked)}"
        )
    environment = _environment_line()
    if environment is not None:
        lines.append(environment)
    if not git_checked:
        lines.append("git 검사 건너뜀(사본)")
    if root_warning:
        lines.append(
            "경고 M13 modules/__init__.py 가 있습니다 — 이름공간 패키지를 가립니다(지웁니다)"
        )
    lines += [module_line(result) for result in results]
    distribution = _api_distribution(results)
    packages = sorted({name for result in results for name in result.third_party})
    lines.append(f"판 분포: {' · '.join(distribution) if distribution else '없음'}")
    lines.append(f"제3자 패키지: {' · '.join(packages) if packages else '없음'}")
    details = _detail_lines(results, worktree)
    lines.append("자세히" if details else "자세히 — 없음")
    lines += details
    failed = [result for result in results if result.status == "실패"]
    summary = [
        f"모듈 {total} = 통과 {counts['통과']} + 꺼짐 {counts['꺼짐']} + 실패 {counts['실패']}",
        ", ".join(distribution) if distribution else "api 없음",
    ]
    if worktree is not None:
        summary.append(f"작업트리 {len(worktree.modified)}+{len(worktree.untracked)}")
    summary.append(f"패키지 {'.'.join(packages)}" if packages else "패키지 없음")
    summary.append(
        "ng " + (", ".join(_ng_token(result) for result in failed) if failed else "없음")
    )
    lines.append(f"{SUMMARY_LABEL} {'; '.join(summary)}")
    return lines


def _empty_block(root: Path, *, exists: bool, worktree: WorktreeState | None) -> list[str]:
    head = (
        f"모듈 점검 — 뿌리 {_root_label(root)} · 모듈 없음"
        if exists
        else f"모듈 점검 — 뿌리 {_root_label(root)} 없음"
    )
    lines = [head]
    summary = "모듈 없음"
    if worktree is not None:
        lines.append(
            f"운영 체크아웃 modules/ — 커밋 안 한 수정 {len(worktree.modified)} · "
            f"추적 안 된 파일 {len(worktree.untracked)}"
        )
        summary += f"; 작업트리 {len(worktree.modified)}+{len(worktree.untracked)}"
    environment = _environment_line()
    if environment is not None:
        lines.append(environment)
    lines.append(f"{SUMMARY_LABEL} {summary}")
    return lines


# --- 진입 ----------------------------------------------------------------------------------------


def _parse(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="사내 모듈의 선언·정적 규칙·ruff·자기 시험을 보고 리뷰에 붙일 블록을 찍는다"
    )
    parser.add_argument("ids", nargs="*", help="볼 모듈 id(폴더 이름)")
    parser.add_argument("--all", action="store_true", help="뿌리 아래 모든 모듈")
    parser.add_argument(
        "--root",
        default=None,
        help="모듈 뿌리(기본 <이 트리>/modules — 이름이 modules 여야 한다)",
    )
    parser.add_argument(
        "--worktree-of", default=None, help="운영 저장소 — modules/ 상태 수를 머리에"
    )
    parser.add_argument("--no-ruff", action="store_true", help="ruff(M15·M16)를 돌리지 않는다")
    parser.add_argument("--no-tests", action="store_true", help="자기 시험(M17)을 돌리지 않는다")
    parser.add_argument("--output", default=None, help="같은 블록을 이 파일에도 쓴다(UTF-8)")
    return parser.parse_args(argv)


def _emit(lines: Iterable[str], output: str | None) -> None:
    text = "\n".join(lines)
    print(text)
    if output is not None:
        Path(output).write_text(text + "\n", encoding="utf-8")


def main(
    argv: Sequence[str] | None = None,
    *,
    environment: rules.PackageEnvironment | None = None,
    distributions: Mapping[str, Sequence[str]] | None = None,
    timeout: int = TEST_TIMEOUT_SECONDS,
) -> int:
    _use_utf8_stdout()
    try:
        args = _parse(argv)
    except SystemExit as stop:
        return stop.code if isinstance(stop.code, int) else 2
    if bool(args.ids) == bool(args.all):
        print("모듈 id 를 주거나 --all 하나만 줍니다", file=sys.stderr)
        return 2
    root = Path(args.root).resolve() if args.root else PROJECT_ROOT / MODULES_FOLDER_NAME
    if root.name != MODULES_FOLDER_NAME:
        print(
            f"--root 의 폴더 이름은 {MODULES_FOLDER_NAME} 여야 합니다"
            f"(`modules.<id>` 가 그 뿌리로 풀린다): {root.name}",
            file=sys.stderr,
        )
        return 2
    worktree: WorktreeState | None = None
    protect = [PROJECT_ROOT / "data"]
    if args.worktree_of is not None:
        repository = Path(args.worktree_of).resolve()
        try:
            worktree = worktree_state(repository)
        except (OSError, subprocess.CalledProcessError) as error:
            print(
                f"--worktree-of 를 git 저장소로 읽지 못했습니다 — {type(error).__name__}",
                file=sys.stderr,
            )
            return 2
        protect.append(repository / "data")
    if not root.is_dir():
        if args.ids:
            print(f"모듈 뿌리가 없습니다: {_root_label(root)}", file=sys.stderr)
            return 2
        _emit(_empty_block(root, exists=False, worktree=worktree), args.output)
        return 0
    scan = module_registry.scan_modules(root, reserved_titles=navigation.core_page_titles())
    if scan.root_error:
        print(scan.root_error, file=sys.stderr)
        return 2
    records = list(scan.records)
    pushed_out = clash_warnings(records)
    if args.ids:
        known = {record.folder_name for record in records}
        missing = [name for name in args.ids if name not in known]
        if missing:
            print(f"그런 모듈 폴더가 없습니다: {', '.join(missing)}", file=sys.stderr)
            return 2
        wanted = set(args.ids)
        records = [record for record in records if record.folder_name in wanted]
    if not records:
        _emit(_empty_block(root, exists=True, worktree=worktree), args.output)
        return 0
    packages = environment or rules.load_environment(PROJECT_ROOT, distributions=distributions)
    git_checked = rules.inside_git_work_tree(root)
    results = [ModuleResult(number=index, record=record) for index, record in enumerate(records, 1)]
    for result in results:
        try:
            check_one(
                result,
                root=root,
                tree=PROJECT_ROOT,
                environment=packages,
                git=git_checked,
                ruff=not args.no_ruff,
                tests=not args.no_tests,
                protect=protect,
                timeout=timeout,
            )
        except Exception as error:  # 한 모듈의 점검 예외가 블록·요약 전체를 지우지 않는다
            result.findings.append(
                rules.Finding(
                    "M13",
                    "error",
                    "*",
                    0,
                    f"점검 중 예외 {type(error).__name__} — 이 모듈만 멈췄습니다(파일 꼴을 봅니다)",
                )
            )
        result.findings.extend(pushed_out.get(result.record.folder_name, ()))
    lines = build_block(
        results,
        root=root,
        worktree=worktree,
        git_checked=git_checked,
        root_warning=(root / "__init__.py").exists(),
    )
    _emit(lines, args.output)
    return 1 if any(result.status == "실패" for result in results) else 0


if __name__ == "__main__":
    sys.exit(main())
