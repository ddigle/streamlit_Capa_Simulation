# Purpose: 사내 런북 6-3(사본 E2E)의 명령이 처음부터 서고 두 스크립트의 인자 계약과 맞는지 본다.

"""런북 6-3 은 사내 에이전트가 그대로 따라가는 정본 절차다 — 명령 한 줄이 틀리면 첫 줄에서 막히거나
사용자 앱을 막는다. 문서 글자를 견주는 시험이라 문장을 고치면 같이 고친다. 아래 자리는 모두 실제로
막혔거나 막을 자리다.

- `git archive -o` 는 상위 폴더를 만들지 않는다 — 처음 따라 할 때는 늘 없다.
- `inspect_revision_calculations.py` 의 `--database` 는 기본값이 없다(운영 DB 를 쥐면 사용자 앱이
  막힌다).
- `benchmark_home.py` 의 출력은 UTF-8 이라 PowerShell 5.1 의 `>` 가 한글을 깨뜨린다 — `--output`.
- `.wal` 만 앞뒤로 보면 복사 도중에 저장과 체크포인트가 다 끝난 사본을 놓친다 — 크기·시각도 본다.
- 6) 적용 전 사본의 대조 줄은 사본에 적용 기록을 쓴다 — `PYTHONPATH` 가 안 먹으면 운영 트리의 적용
  기록을 덮어 다음 적용이 「이미 적용했습니다」로 멈추므로 git 트리면 쓰지 않고 멈춰야 한다.
- 사본 DB 를 여는 줄(a · b · c)은 사용자가 별도 창에서 친다 — 권한 템플릿이 그 줄을 묻지 않고
  통과시키면 에이전트가 사내 DB 를 읽게 된다. 3) 은 경로만 찍어(DB 를 열지 않는다) 에이전트가 친다.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = PROJECT_ROOT / "docs" / "internal_update_runbook.md"
TEMPLATE = PROJECT_ROOT / "docs" / "internal_claude_settings.json"
README = PROJECT_ROOT / "README.md"
COPY_CHECKS = (
    "inspect_revision_calculations.py",
    "benchmark_home.py",
    "benchmark_upeh_assumption.py",
)


def _section(start: str, end: str) -> str:
    text = RUNBOOK.read_text(encoding="utf-8")
    begin = text.index(start)
    return text[begin : text.index(end, begin)]


def _copy_e2e() -> str:
    return _section("## 6-3.", "\n## 7.")


def _code_lines(text: str) -> list[str]:
    """펜스 코드 블록 안의 줄(앞 공백을 뗀다)."""
    lines: list[str] = []
    inside = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            inside = not inside
            continue
        if inside:
            lines.append(line.strip())
    return lines


def _index(lines: list[str], fragment: str) -> int:
    found = [number for number, line in enumerate(lines) if fragment in line]
    assert len(found) == 1, f"{fragment!r} 줄이 하나가 아니다: {found}"
    return found[0]


def test_the_copy_tree_parent_exists_before_git_archive_writes_into_it() -> None:
    lines = _code_lines(_section("### 1) 사본 트리", "### 2)"))

    made = _index(lines, "New-Item -ItemType Directory -Force (Split-Path $e2e)")
    assert _index(lines, "$e2e = ") < made < _index(lines, "git archive --format=zip -o")
    linux = re.search(
        r"`(mkdir -p <사본 폴더> && git archive HEAD \| tar -x -C <사본 폴더>)`", _copy_e2e()
    )
    assert linux is not None, "리눅스 줄도 사본 폴더를 먼저 만든다"


def _fenced_blocks(text: str) -> list[list[str]]:
    """펜스 코드 블록마다의 줄(앞 공백을 뗀다)."""
    blocks: list[list[str]] = []
    current: list[str] | None = None
    for line in text.splitlines():
        if line.strip().startswith("```"):
            if current is not None:
                blocks.append(current)
            current = [] if current is None else None
        elif current is not None:
            current.append(line.strip())
    return blocks


def test_a_git_bash_session_has_its_own_copy_tree_line() -> None:
    """`powershell -Command` 로 넘긴 블록은 Git Bash 가 `$` 를 먼저 풀어 경로가 깨졌다
    (`202611060842` 사외 요청 1)."""
    section = _section("### 1) 사본 트리", "### 2)")

    assert "`powershell -Command` 로 넘기지 않는다" in section
    [line] = [line for line in _code_lines(section) if line.startswith('e2e="$HOME/e2e_copy/')]
    assert 'mkdir -p "$e2e" && git archive HEAD | tar -x -C "$e2e"' in line
    assert line.endswith('cygpath -w "$e2e"'), "2) 의 PowerShell 창에 넣을 값을 찍는다"


def test_the_copy_block_and_chapter_eight_start_at_the_repository_root() -> None:
    """두 블록의 경로는 상대 경로다 — 사용자가 어디서 치는지 물었다(`202611060842` 사외 요청 1)."""
    place = "git rev-parse --show-toplevel"
    copy = _section("### 2) DB 복사", "### 3)")
    chapter_eight = _section("### 8-0.", "### 8-1.")

    for section, marker in (
        (copy, "$db = "),
        (chapter_eight, "scripts/inspect_real_data_checks.py --output"),
    ):
        [block] = [lines for lines in _fenced_blocks(section) if marker in "\n".join(lines)]
        assert block[0] == "Set-Location <저장소>"
        assert place in section


def test_every_revision_inspection_names_the_copy_database() -> None:
    calls = [
        line
        for line in _code_lines(RUNBOOK.read_text(encoding="utf-8"))
        if "inspect_revision_calculations.py" in line
    ]

    assert calls
    for line in calls:
        assert '--database "$e2e\\data\\capa_simulation.duckdb"' in line, line


def test_the_home_benchmark_writes_through_output_not_a_redirect() -> None:
    calls = [
        line
        for line in _code_lines(RUNBOOK.read_text(encoding="utf-8"))
        if "benchmark_home.py" in line
    ]

    assert calls
    for line in calls:
        assert "--output " in line and ">" not in line, line


def test_the_upeh_plan_benchmark_reads_only_the_copy_and_writes_through_output() -> None:
    """가정 계획 1회 시간(6-3 b) — 사본 폴더만 주고 `--output` 으로 받는다(`>` 는 한글을
    깨뜨린다)."""
    calls = [line for line in _code_lines(_copy_e2e()) if "benchmark_upeh_assumption.py" in line]

    assert len(calls) == 1, calls
    assert '--data-dir "$e2e\\data"' in calls[0]
    assert "--output" in calls[0] and ">" not in calls[0]
    script = (PROJECT_ROOT / "scripts" / "benchmark_upeh_assumption.py").read_text(encoding="utf-8")
    assert '"--data-dir",\n        required=True' in script
    assert '"--output"' in script


def _rule_matches(rule: str, command: str) -> bool:
    """권한 규칙 맞춤 — 끝의 `:*` 는 앞부분 맞춤, 그 밖의 `*` 는 아무 글자다(텍스트 맞춤)."""
    if "(" not in rule:
        return False
    body = rule[rule.index("(") + 1 : -1]
    if body.endswith(":*"):
        return command.startswith(body[:-2])
    return re.fullmatch(".*".join(re.escape(part) for part in body.split("*")), command) is not None


def _shell_rules() -> list[str]:
    allow = json.loads(TEMPLATE.read_text(encoding="utf-8"))["permissions"]["allow"]
    return [rule for rule in allow if rule.startswith(("Bash(", "PowerShell("))]


def _as_real_folder(line: str) -> str:
    return (
        line.replace("$e2e", "C:/Users/someone/e2e_copy/202611051200")
        .replace("$HOME", "C:/Users/someone")
        .replace("\\", "/")
    )


def _database_opening_lines() -> list[str]:
    """런북이 사용자 별도 창에 주는, 사내 DB 를 여는 줄 — 6-2 · 6-3 a · b · c · 8-0 의 펜스 줄과
    그것을 실제 폴더로 바꾼 줄, 그리고 걷은 BigDataQuery 줄 · `inspect_wf_division.py`(줄은 7장에
    있다) · 7-8 꼴의 `python -c` 로 DuckDB 를 여는 줄."""
    names = (*COPY_CHECKS, "inspect_real_data_checks.py", "check_deploy_screens.py")
    sections = (
        _copy_e2e(),
        _section("### 8-0.", "### 8-1."),
        _section("## 6-2.", "## 6-3."),
    )
    lines = [
        line
        for section in sections
        for line in _code_lines(section)
        if any(f"scripts/{name}" in line or f"scripts\\{name}" in line for name in names)
        and "--list" not in line
    ]
    prefix = "uv run --no-sync python scripts/"
    walked_back = [
        f"{prefix}inspect_real_data_checks.py --only bdq --output C:/Users/someone/bdq.md",
        f"{prefix}inspect_real_data_checks.py",
        f"{prefix}inspect_wf_division.py",
        f'{prefix}inspect_wf_division.py --database "C:/Users/someone/e2e_copy/1/data/x.duckdb"',
        f"{prefix}inspect_wf_division.py --output C:/Users/someone/wf.md",
        f"{prefix}inspect_db_counts.py --output C:/Users/someone/db_counts.md",
        'uv run --no-sync python -c "import duckdb; duckdb.connect(p, read_only=True)"',
    ]
    return [*lines, *(_as_real_folder(line) for line in lines), *walked_back]


def test_the_settings_template_lets_no_line_that_opens_an_internal_database_through() -> None:
    """사내 DB 를 여는 줄은 에이전트가 치지 않는다(런북 0장). 템플릿이 그 줄을 묻지 않고
    통과시키면 그 규칙이 글뿐이 되므로, 런북의 그런 줄마다 맞는 allow 가 하나도 없어야 한다."""
    lines = _database_opening_lines()
    called = {name for name in COPY_CHECKS if any(f"scripts/{name}" in line for line in lines)}

    assert called == set(COPY_CHECKS), called
    assert any("check_deploy_screens.py" in line for line in lines)
    for command in lines:
        for written in (command, command.replace('"', "")):
            assert not [rule for rule in _shell_rules() if _rule_matches(rule, written)], written


def test_the_settings_template_still_lets_the_agent_recount_a_compressed_review() -> None:
    """`--check-summary` 는 받은 압축본 파일만 다시 센다 — DB 를 열기 전에 끝나므로(`main` 의 첫
    갈래) 에이전트가 묻지 않고 친다(런북 5장 끝 · 8-6). 두 셸이 쌍이다."""
    runbook_line = next(
        line
        for line in _code_lines(RUNBOOK.read_text(encoding="utf-8"))
        if "inspect_real_data_checks.py --check-summary" in line
    )
    filled = runbook_line.replace("<ZIP 파일명>", "202611111500")

    matched = [rule for rule in _shell_rules() if _rule_matches(rule, filled)]
    assert sorted(rule.split("(")[0] for rule in matched) == ["Bash", "PowerShell"]
    script = (PROJECT_ROOT / "scripts" / "inspect_real_data_checks.py").read_text(encoding="utf-8")
    main = script[script.index("def main(") :]
    assert main.index("return _check_summary(") < main.index("_run(args")


def test_the_documents_say_the_database_lines_run_in_the_users_window() -> None:
    copy_e2e = " ".join(_copy_e2e().split())
    readme = " ".join(README.read_text(encoding="utf-8").split())
    blocked = RUNBOOK.read_text(encoding="utf-8")
    blocked = blocked[blocked.index("## 6. 막혔을 때") : blocked.index("## 6-1.")]
    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    explained = " ".join("\n".join(template["_설명"]).split())

    assert "**사용자가 별도 PowerShell 창에서**" in copy_e2e
    assert "| 사본 E2E 의 `git archive`·복사·스크립트(6-3) |" in blocked
    assert "allow 를 걷었다" in blocked
    assert "Claude 밖의 별도 PowerShell 창" in readme
    assert "별도 PowerShell 창" in explained and "--check-summary" in explained
    for name in COPY_CHECKS:
        assert name in readme and name in explained, name


def test_the_copy_compares_size_and_write_time_before_and_after() -> None:
    lines = _code_lines(_section("### 2) DB 복사", "### 3)"))

    copied = _index(lines, "Copy-Item")
    before = _index(lines, "$before = ")
    after = _index(lines, "$after = ")
    assert before < copied < after < _index(lines, "Compare-Object $before $after")
    for stamp in (lines[before], lines[after]):
        assert "Length" in stamp and "LastWriteTimeUtc" in stamp, stamp
    assert "stat -c '%n %s %y' data/*.duckdb" in _copy_e2e()


def test_the_copy_check_before_launch_opens_no_database() -> None:
    """3) 은 경로만 찍는다 — 두 사본을 여는 줄은 걷었고(열리지 않는 사본은 a · b · c 가 바로
    알린다), 전 리비전 계산(수 분)은 4-a 의 몫이다."""
    lines = _code_lines(_section("### 3) 사본이 맞는지", "### 4)"))

    assert not [line for line in lines if "inspect_revision_calculations.py" in line]
    assert not [line for line in lines if "duckdb" in line or "read_only" in line]
    [printed] = [line for line in lines if "DUCKDB_PATH" in line]
    assert printed.startswith('$env:PYTHONPATH = "$e2e\\src"; ')


def _pre_apply_copy() -> str:
    return _section("### 6) (선택) 적용 전 사본", "\n## 7.")


def test_the_pre_apply_copy_is_an_option_that_seven_zero_gates() -> None:
    """적용 전 사본은 기본 흐름이 아니다 — A 를 대신하는 것은 그 배포 7-0 이 허락할 때만이고,
    a · b 는 적용 뒤 저장소에서 부른다(적용 전 저장소의 스크립트는 직전 배포 것이다)."""
    section = _pre_apply_copy()

    assert "**기본 흐름이 아니다" in section
    assert "7-0 이 허락할 때만이다" in section
    assert "a · b 는 **적용 뒤** 저장소에서" in section
    for condition in (
        "`지움    없음`",
        "`manifest N / N`",
        "`deps same`",
        "`git log -2 --format=%h`",
    ):
        assert condition in section, condition
    assert "(6-3 6)" in _section("## 0-1.", "## 1.")


def test_the_pre_apply_copy_records_its_base_before_overlaying_the_zip() -> None:
    lines = _code_lines(_pre_apply_copy())

    base = _index(lines, "git log -1 --format=%h")
    overlay = _index(lines, "Expand-Archive -Force")
    check = _index(lines, "DEPLOY_MANIFEST.json")
    assert base < overlay < check
    assert lines[check].startswith('& $py -c "') and lines[check].endswith('"')


def _check_code() -> str:
    line = next(line for line in _code_lines(_pre_apply_copy()) if "DEPLOY_MANIFEST.json" in line)
    code = line[len('& $py -c "') : -1]
    # PowerShell 큰따옴표 안에서 풀리거나 끊기는 글자가 없어야 셸이 무엇이든 같은 줄이다.
    assert '"' not in code and "$" not in code and "`" not in code
    assert code.isascii()
    return code


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _pre_apply_trees(tmp_path: Path) -> tuple[Path, Path]:
    """사본(설정 모듈 + 송장 + 파일 둘)과 운영 트리(`.git` · 의존성 파일)."""
    copy = tmp_path / "copy"
    package = copy / "src" / "capa_simulation"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    shutil.copyfile(
        PROJECT_ROOT / "src" / "capa_simulation" / "settings.py", package / "settings.py"
    )
    operational = tmp_path / "operational"
    (operational / ".git").mkdir(parents=True)
    files = {"pyproject.toml": b"[project]\n", "uv.lock": b"version = 1\n"}
    for name, data in files.items():
        (copy / name).write_bytes(data)
        (operational / name).write_bytes(data)
    manifest = {
        "stamp": "202601010000",
        "commit": "0" * 40,
        "commit_subject": "합성",
        "file_count": len(files),
        "files": {name: _sha(data) for name, data in files.items()},
    }
    (copy / "DEPLOY_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    return copy, operational


def _run_check(cwd: Path, source: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(source)}
    return subprocess.run(
        [sys.executable, "-c", _check_code()],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )


def test_the_pre_apply_check_matches_the_manifest_and_stamps_only_the_copy(
    tmp_path: Path,
) -> None:
    copy, operational = _pre_apply_trees(tmp_path)

    done = _run_check(operational, copy / "src")

    assert done.returncode == 0, done.stderr
    assert done.stdout.split() == "manifest 2 / 2 ; deps same ; stamp 202601010000".split()
    state = json.loads((copy / ".deploy" / "applied.json").read_text(encoding="utf-8"))
    assert state["stamp"] == "202601010000" and state["file_count"] == 2
    assert not (operational / ".deploy").exists()


def test_the_pre_apply_check_names_a_mismatch_and_writes_nothing(tmp_path: Path) -> None:
    copy, operational = _pre_apply_trees(tmp_path)
    (copy / "pyproject.toml").write_bytes(b"[project]\nname = 'x'\n")
    (operational / "uv.lock").write_bytes(b"version = 2\n")

    done = _run_check(operational, copy / "src")

    assert done.returncode == 0, done.stderr
    assert done.stdout.split() == "manifest 1 / 2 ; deps uv.lock ; stamp not written".split()
    assert not (copy / ".deploy").exists()


def test_the_pre_apply_check_stops_without_writing_outside_a_copy(tmp_path: Path) -> None:
    """설정이 git 트리(운영 트리)를 가리키거나 저장소가 아닌 곳에서 치면 아무것도 쓰지 않는다."""
    copy, operational = _pre_apply_trees(tmp_path)
    (copy / ".git").mkdir()

    pointed_at_git = _run_check(operational, copy / "src")
    (copy / ".git").rmdir()
    outside_repository = _run_check(copy, copy / "src")

    assert pointed_at_git.returncode != 0 and "stop:" in pointed_at_git.stderr
    assert outside_repository.returncode != 0 and "stop:" in outside_repository.stderr
    assert not (copy / ".deploy").exists()
