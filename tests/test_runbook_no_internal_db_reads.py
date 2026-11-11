# Purpose: 사내 런북 일반 장이 사내 DB 를 여는 줄을 에이전트 대신 사용자 별도 창에 주는지 본다.

"""런북 0장 — 에이전트는 사내 DB(BigDataQuery · 운영 DB · 사본)를 여는 명령을 스스로 치지 않는다.

데이터가 꼭 필요하면 사용자에게 먼저 요청하고, 사용자가 Claude 밖의 별도 PowerShell 창에서
돌린 결과 파일만 읽는다. 그래서 BigDataQuery 를 묻는 줄(8-5 `--only bdq`) · 즉석 코드로 사본을
여는 탐색(9장) · 사본 앱 헤드리스로 B 를 먼저 채우던 대행(6-3)은 런북에 실행 지시로 남지 않아야
하고, 8-0 · 6-2 · 6-3 의 DB 를 여는 줄은 그 자리에 「별도 PowerShell 창」 을 적어야 한다.

7장은 배포마다 새로 쓰이고, 지금 판은 이미 사내로 나간 배포의 것이라 이 시험은 7장을 떼고 본다 —
다음 7장은 `docs/TODO.md` 「다음 배포 7장에 넣을 줄」 이 맞춘다.
"""

import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = PROJECT_ROOT / "docs" / "internal_update_runbook.md"
DUAL_ENV = PROJECT_ROOT / "docs" / "dual_env_workflow.md"
TEMPLATE = PROJECT_ROOT / "docs" / "internal_claude_settings.json"
PRINCIPLE = "에이전트는 사내 DB(BigDataQuery · 운영 DB · 사본)를 여는 명령을 스스로 치지 않는다"
USER_WINDOW = "별도 PowerShell 창"
# 사내 DB 를 여는 스크립트 · 코드 조각. `--check-summary` · `--list` 줄은 DB 를 열지 않는다.
OPENS_A_DATABASE = (
    "inspect_real_data_checks.py",
    "inspect_revision_calculations.py",
    "benchmark_home.py",
    "benchmark_upeh_assumption.py",
    "check_deploy_screens.py",
    "inspect_wf_division.py",
    "duckdb.connect",
)
DOES_NOT_OPEN = ("--check-summary", "--list")


def _without_chapter_seven() -> str:
    text = RUNBOOK.read_text(encoding="utf-8")
    head, rest = text.split("\n## 7. ", 1)
    return head + "\n## 8. " + rest.split("\n## 8. ", 1)[1]


def _section(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    return text[begin : text.index(end, begin + len(start))]


def _pieces(text: str) -> list[tuple[bool, str]]:
    """본문과 펜스 코드 블록을 차례대로 가른다 — `(펜스인가, 글)`."""
    pieces: list[tuple[bool, str]] = []
    inside = False
    current: list[str] = []
    for line in text.splitlines():
        if line.strip().startswith("```"):
            pieces.append((inside, "\n".join(current)))
            current = []
            inside = not inside
            continue
        current.append(line)
    pieces.append((inside, "\n".join(current)))
    return pieces


def _opens_a_database(block: str) -> bool:
    return any(
        any(name in line for name in OPENS_A_DATABASE)
        and not any(flag in line for flag in DOES_NOT_OPEN)
        for line in block.splitlines()
    )


def _chunks(text: str) -> list[str]:
    """문단과 글머리표 하나하나 — 한 결정을 말하는 가장 작은 덩어리."""
    return [chunk for part in text.split("\n\n") for chunk in re.split(r"\n(?=\s*- )", part)]


def test_no_bigdataquery_line_is_left_to_run() -> None:
    text = _without_chapter_seven()
    fenced = [block for is_fence, block in _pieces(text) if is_fence]

    assert not [block for block in fenced if "bdq" in block]
    for chunk in _chunks(text):
        if "--only bdq" in chunk:
            assert "걷" in chunk, chunk
    chapter_eight = _section(text, "## 8. 실데이터 확인", "### 8-0.")
    row = next(line for line in chapter_eight.splitlines() if line.startswith("| 8-5 | `bdq` |"))
    assert "걷음" in row and "부르지 않는다" in row
    assert "부르지 않는다" in _section(text, "### 8-5. `bdq`", "### 8-9.")


def test_database_lines_of_eight_zero_and_six_two_six_three_name_the_users_window() -> None:
    """DB 를 여는 펜스마다 그 앞뒤 글(앞 블록 · 머리부터 다음 블록 · 머리까지)이 사용자 별도
    창이라고 적는다. 그 절에는 에이전트가 백그라운드로 돌리거나 `!` 로 주라는 지시가 없다."""
    text = _without_chapter_seven()
    sections = (
        _section(text, "### 8-0.", "### 8-1."),
        _section(text, "## 6-2.", "## 6-3."),
        _section(text, "## 6-3.", "## 6-4."),
    )
    checked = 0
    for section in sections:
        for part in re.split(r"\n(?=#{2,4} )", section):
            pieces = _pieces(part)
            for index, (is_fence, block) in enumerate(pieces):
                if not is_fence or not _opens_a_database(block):
                    continue
                around = pieces[index - 1][1] + pieces[index + 1][1]
                assert USER_WINDOW in " ".join(around.split()), block
                checked += 1
        assert "백그라운드로 돌리고" not in section
        assert "`! ` 를" not in section
    assert checked >= 6, checked


def test_the_exploration_chapter_and_the_proxy_are_withdrawn() -> None:
    text = _without_chapter_seven()
    chapter_nine = _section(text, "## 9. ", "## 10. ")

    assert "걷음" in chapter_nine
    assert not [is_fence for is_fence, _ in _pieces(chapter_nine) if is_fence]
    assert "[Opus 구간" not in chapter_nine
    assert not re.search(r"^### 9-", text, re.MULTILINE)
    for chunk in _chunks(text):
        if "B 대행" in chunk or "`@a`" in chunk or "9장" in chunk:
            assert "걷" in chunk, chunk

    order = _section(text, "**압축본 줄 — 이 차례로**", "**B 세는 법**")
    assert "`탐색`" not in order
    assert "u<u> a<a>" not in order


def test_chapter_zero_and_the_workflow_state_the_principle() -> None:
    chapter_zero = " ".join(_section(_without_chapter_seven(), "## 0. ", "## 0-1. ").split())
    dual_env = " ".join(DUAL_ENV.read_text(encoding="utf-8").split())

    for document in (chapter_zero, dual_env):
        assert PRINCIPLE in document
        assert "사용자에게 먼저 요청" in document
    assert USER_WINDOW in chapter_zero and "`!` 로 치지 않는다" in chapter_zero
    assert "런북 9장 「사내 탐색」 이다" not in dual_env


def test_the_settings_template_opens_no_database_script() -> None:
    allow = json.loads(TEMPLATE.read_text(encoding="utf-8"))["permissions"]["allow"]
    scripts = [rule for rule in allow if "scripts/" in rule]

    for rule in scripts:
        named = [name for name in OPENS_A_DATABASE if name in rule]
        if named == ["inspect_real_data_checks.py"]:
            assert "--check-summary *)" in rule, rule
        else:
            assert not named, rule
