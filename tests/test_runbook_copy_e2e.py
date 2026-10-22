# Purpose: 사내 런북 6-3(사본 E2E)의 명령이 처음부터 서고 두 스크립트의 인자 계약과 맞는지 본다.

"""런북 6-3 은 사내 에이전트가 그대로 따라가는 정본 절차다 — 명령 한 줄이 틀리면 첫 줄에서 막히거나
사용자 앱을 막는다. 문서 글자를 견주는 시험이라 문장을 고치면 같이 고친다. 아래 자리는 모두 실제로
막혔거나 막을 자리다.

- `git archive -o` 는 상위 폴더를 만들지 않는다 — 처음 따라 할 때는 늘 없다.
- `inspect_revision_calculations.py` 의 `--database` 는 기본값이 없다(운영 DB 를 쥐면 사용자 앱이
  막힌다).
- `benchmark_home.py` 의 출력은 UTF-8 이라 PowerShell 5.1 의 `>` 가 한글을 깨뜨린다 — `--output`.
- `.wal` 만 앞뒤로 보면 복사 도중에 저장과 체크포인트가 다 끝난 사본을 놓친다 — 크기·시각도 본다.
"""

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = PROJECT_ROOT / "docs" / "internal_update_runbook.md"


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


def test_the_copy_compares_size_and_write_time_before_and_after() -> None:
    lines = _code_lines(_section("### 2) DB 복사", "### 3)"))

    copied = _index(lines, "Copy-Item")
    before = _index(lines, "$before = ")
    after = _index(lines, "$after = ")
    assert before < copied < after < _index(lines, "Compare-Object $before $after")
    for stamp in (lines[before], lines[after]):
        assert "Length" in stamp and "LastWriteTimeUtc" in stamp, stamp
    assert "stat -c '%n %s %y' data/*.duckdb" in _copy_e2e()


def test_the_copy_check_before_launch_only_opens_the_two_copies() -> None:
    """3) 은 사본이 열리는지만 본다 — 전 리비전 계산(수 분)은 4-a 의 몫이다."""
    lines = _code_lines(_section("### 3) 사본이 맞는지", "### 4)"))

    assert not [line for line in lines if "inspect_revision_calculations.py" in line]
    opened = lines[_index(lines, "read_only=True")]
    assert "s.DUCKDB_PATH" in opened and "s.EQUIPMENT_DUCKDB_PATH" in opened
