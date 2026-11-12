# Purpose: 런북이 사내 DB 를 여는 줄을 사용자 별도 창에 주고 권한 템플릿이 그 줄을 막는지 본다.

"""런북 0장 — 에이전트는 사내 DB(BigDataQuery · 운영 DB · 사본)를 여는 명령을 스스로 치지 않는다.

데이터가 꼭 필요하면 사용자에게 먼저 요청하고, 사용자가 Claude 밖의 별도 PowerShell 창에서
돌린 결과 파일만 읽는다. 그래서 BigDataQuery 를 묻는 줄(8-5 `--only bdq`) · 즉석 코드로 사본을
여는 탐색(9장) · 사본 앱 헤드리스로 B 를 먼저 채우던 대행(6-3)은 런북에 실행 지시로 남지 않아야
하고, DB 를 여는 명령 펜스는 그 곁에 「별도 PowerShell 창」 을 적어야 한다.

검사는 런북 글을 받아 어긋남 목록을 내는 함수(`violations`) 하나다 — 지금 런북이 빈 목록이고,
옛 꼴 글(에이전트가 백그라운드로 돌림 · `!` 로 줌 · BigDataQuery 줄)을 끼워 넣으면 잡힌다.

7장은 배포마다 새로 쓰인다. 7장 머리의 stamp 가 이미 사내로 나간 `202611111500` 인 동안만 7장을
떼고 본다 — 그 판은 이 규칙 전에 쓰였다. stamp 를 바꾸면(다음 배포의 7장) 7장도 같은 규칙으로
본다(`docs/TODO.md` 「다음 배포 7장에 넣을 줄」).

권한 템플릿(`docs/internal_claude_settings.json`)은 사내 세션이 사용자가 고정한 auto 모드라 allow
를 걷는 것만으로는 모자라 런북 꼴의 줄을 deny 로 막는다 — 런북의 DB 를 여는 줄마다 deny 가 맞고
allow 는 맞지 않으며, DB 를 열지 않는 `--check-summary` · `--list` 줄은 deny 에 걸리지 않아야 한다.
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
SHIPPED_SEVEN = "**이 절은 stamp `202611111500` 배포용이다.**"
# 사내 DB 를 여는 스크립트 · 코드 조각. `--check-summary` · `--list` 줄은 DB 를 열지 않는다.
DATABASE_SCRIPTS = (
    "inspect_real_data_checks.py",
    "inspect_revision_calculations.py",
    "benchmark_home.py",
    "benchmark_upeh_assumption.py",
    "check_deploy_screens.py",
    "inspect_wf_division.py",
    "inspect_db_counts.py",
    "sync_object_storage.py",
)
OPENS_A_DATABASE = (*DATABASE_SCRIPTS, "duckdb.connect", "import duckdb")
DOES_NOT_OPEN = ("--check-summary", "--list")
COMMAND_FENCES = ("powershell", "bash", "")
# 에이전트가 치게 하는 꼴 — DB 를 여는 펜스 곁에 있으면 안 된다.
AGENT_RUNS = ("백그라운드로 돌", "에이전트가 친다", "에이전트가 돌린다", "에이전트가 돌리고")
# `!` 로 주는 꼴(부정 「치지 않는다」 · 「아님」 은 걸리지 않는다).
BANG_GIVEN = re.compile(r"`! ?` ?(?:로|를) ?(?:준다|주고|친다|치고|붙여)|`!` 한 줄")
# 본문 안 실행 줄(백틱) — 스크립트를 부르는 꼴만 본다(이름만 든 백틱은 아니다).
INLINE_CALL = re.compile(r"`((?:uv run|& \$py|python)[^`]*)`")
# 다른 문서의 장 번호(`docs/x.md` 9장)는 런북 9장이 아니다.
OTHER_DOCUMENT_CHAPTER = re.compile(r"`[^`]+\.md` \d+장")
WINDOWS = (USER_WINDOW, "별도 창", "사용자 창")


def _chapter_seven_bounds(text: str) -> tuple[int, int]:
    begin = text.index("\n## 7. ")
    return begin, text.index("\n## 8. ", begin)


def general_text(text: str) -> str:
    """이미 나간 판의 7장(stamp `202611111500`)만 뗀다 — 다른 stamp 면 7장도 본다."""
    begin, end = _chapter_seven_bounds(text)
    if SHIPPED_SEVEN in text[begin:end]:
        return text[:begin] + text[end:]
    return text


def _section(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    return text[begin : text.index(end, begin + len(start))]


def _pieces(text: str) -> list[tuple[str | None, str]]:
    """본문과 펜스 코드 블록을 차례대로 가른다 — `(펜스 언어 또는 None, 글)`."""
    pieces: list[tuple[str | None, str]] = []
    language: str | None = None
    current: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            pieces.append((language, "\n".join(current)))
            current = []
            language = stripped[3:].strip() if language is None else None
            continue
        current.append(line)
    pieces.append((language, "\n".join(current)))
    return pieces


def _opens_a_database(block: str) -> bool:
    return any(
        any(name in line for name in OPENS_A_DATABASE)
        and not any(flag in line for flag in DOES_NOT_OPEN)
        for line in block.splitlines()
    )


def _chunks(text: str) -> list[str]:
    """문단 · 글머리표 · 표 줄 하나하나 — 한 결정을 말하는 가장 작은 덩어리."""
    chunks: list[str] = []
    for part in text.split("\n\n"):
        for chunk in re.split(r"\n(?=\s*- )", part):
            rows = [line for line in chunk.splitlines() if line.startswith("|")]
            chunks.extend(rows if rows else [chunk])
    return chunks


def violations(text: str) -> list[str]:
    """런북 글에서 사내 DB 를 에이전트가 열게 하는 지시를 찾는다(어긋남 한 줄씩)."""
    text = general_text(text)
    found: list[str] = []
    for part in re.split(r"\n(?=#{2,4} )", text):
        pieces = _pieces(part)
        for index, (language, block) in enumerate(pieces):
            if language is None or language not in COMMAND_FENCES:
                continue
            if "bdq" in block:
                found.append(f"BigDataQuery 줄이 펜스에 있다: {block.strip()[:80]}")
            if not _opens_a_database(block):
                continue
            around = " ".join((pieces[index - 1][1] + " " + pieces[index + 1][1]).split())
            if USER_WINDOW not in around:
                found.append(
                    f"DB 를 여는 펜스 곁에 「{USER_WINDOW}」 가 없다: {block.strip()[:80]}"
                )
            for phrase in AGENT_RUNS:
                if phrase in around:
                    found.append(f"DB 를 여는 펜스 곁에 「{phrase}」: {block.strip()[:80]}")
            if BANG_GIVEN.search(around):
                found.append(f"DB 를 여는 펜스를 `!` 로 준다: {block.strip()[:80]}")
    prose = "\n".join(block for language, block in _pieces(text) if language is None)
    for chunk in _chunks(prose):
        flat = " ".join(chunk.split())
        if "--only bdq" in flat and "걷" not in flat:
            found.append(f"`--only bdq` 를 걷지 않은 글: {flat[:80]}")
        if any(name in flat for name in DATABASE_SCRIPTS) and BANG_GIVEN.search(flat):
            found.append(f"DB 를 여는 줄을 `!` 로 준다: {flat[:80]}")
        calls = [call for call in INLINE_CALL.findall(flat) if _opens_a_database(call)]
        if calls and not any(window in flat for window in WINDOWS):
            found.append(f"본문의 DB 를 여는 줄에 사용자 창이 없다: {calls[0][:80]}")
        if flat.startswith("|") and "에이전트(스크립트)" in flat:
            found.append(f"표의 확인자가 에이전트(스크립트)다: {flat[:80]}")
        marks = OTHER_DOCUMENT_CHAPTER.sub("", flat)
        if any(mark in marks for mark in ("B 대행", "`@a`", "9장")) and "걷" not in flat:
            found.append(f"걷은 일(B 대행 · 9장)을 걷었다고 하지 않는다: {flat[:80]}")
    if re.search(r"^### 9-", text, re.MULTILINE):
        found.append("9장 탐색 절(`### 9-`)이 남았다")
    return found


def test_the_runbook_leaves_no_internal_database_line_to_the_agent() -> None:
    assert violations(RUNBOOK.read_text(encoding="utf-8")) == []


def test_the_net_catches_old_style_lines_put_back_into_the_general_chapters() -> None:
    """검토에서 넣어 본 옛 꼴 셋 — 넣으면 하나씩 잡혀야 한다."""
    text = RUNBOOK.read_text(encoding="utf-8")
    gate = "### 4-4."
    background = (
        "에이전트가 백그라운드로 돌린다.\n\n```powershell\n"
        "uv run --no-sync python scripts/inspect_wf_division.py\n```\n\n"
    )
    in_four_three = text.replace(gate, background + gate, 1)
    anchor = "**a. 전 리비전 계산**"
    bang = text.replace(
        anchor,
        "막히면 이 줄을 사용자에게 `inspect_revision_calculations.py` 를 `!` 로 준다. " + anchor,
        1,
    )
    bdq = text.replace(
        gate,
        "```powershell\nuv run --no-sync python scripts/inspect_real_data_checks.py --only bdq"
        " --output $HOME/bdq.md\n```\n\n" + gate,
        1,
    )

    assert in_four_three != text and bang != text and bdq != text
    assert any("곁에" in line for line in violations(in_four_three))
    assert any("`!` 로 준다" in line for line in violations(bang))
    assert any("BigDataQuery" in line for line in violations(bdq))


def test_a_new_chapter_seven_is_held_to_the_same_rules() -> None:
    """stamp 를 바꾸면 7장을 떼지 않는다 — 옛 7-8 꼴(`!` 로 차례로 · BigDataQuery 둘째 줄 ·
    확인자 에이전트(스크립트))을 다시 쓰면 잡힌다."""
    text = RUNBOOK.read_text(encoding="utf-8")
    begin, end = _chapter_seven_bounds(text)
    new_head = (
        "## 7. 이번 배포에서 사내가 따로 확인해야 하는 것\n\n"
        "**이 절은 stamp `209901010000` 배포용이다.**\n\n"
    )
    real_data = "uv run --no-sync python scripts/inspect_real_data_checks.py"
    old_style = (
        "### 7-0. 차례\n\n| 차례 | 확인자 |\n|---|---|\n| 1 | 에이전트(스크립트) · 백그라운드 |\n\n"
        "### 7-8. 마지막\n\n아래 두 줄을 처음부터 사용자에게 준다 — 앞에 `! ` 를 붙여 차례로 친다 "
        "(`inspect_real_data_checks.py`).\n\n```powershell\n"
        f"{real_data} --output $HOME/real.md\n"
        f"{real_data} --only bdq --output $HOME/bdq.md\n"
        "```\n"
    )
    compliant = (
        "### 7-8. 마지막\n\n이 줄은 사용자가 Claude 밖의 별도 PowerShell 창에서 친다"
        "(`!` 아님 — 0장).\n\n"
        f"```powershell\n{real_data} --output $HOME/real.md\n```\n"
    )
    rewritten = text[: begin + 1] + new_head + old_style + text[end:]
    clean = text[: begin + 1] + new_head + compliant + text[end:]

    found = violations(rewritten)
    assert any("BigDataQuery" in line for line in found), found
    assert any("「별도 PowerShell 창」 가 없다" in line for line in found), found
    assert any("`!` 로 준다" in line for line in found), found
    assert any("에이전트(스크립트)" in line for line in found), found
    inline_wf = (
        "\n\n이 줄도 처음부터 준다 — `uv run --no-sync python scripts/inspect_wf_division.py`.\n"
    )
    assert any("본문의 DB 를 여는 줄" in line for line in violations(rewritten + inline_wf))
    assert violations(clean) == []


def test_the_bigdataquery_block_is_withdrawn_from_chapter_eight() -> None:
    text = general_text(RUNBOOK.read_text(encoding="utf-8"))
    chapter_eight = _section(text, "## 8. 실데이터 확인", "### 8-0.")
    row = next(line for line in chapter_eight.splitlines() if line.startswith("| 8-5 | `bdq` |"))

    assert "걷음" in row and "부르지 않는다" in row
    assert "부르지 않는다" in _section(text, "### 8-5. `bdq`", "### 8-9.")


def test_the_exploration_chapter_and_the_proxy_are_withdrawn() -> None:
    text = general_text(RUNBOOK.read_text(encoding="utf-8"))
    chapter_nine = _section(text, "## 9. ", "## 10. ")

    assert "걷음" in chapter_nine
    assert not [language for language, _ in _pieces(chapter_nine) if language is not None]
    assert "[Opus 구간" not in chapter_nine
    order = _section(text, "**압축본 줄 — 이 차례로**", "**B 세는 법**")
    assert "`탐색`" not in order
    assert "u<u> a<a>" not in order


def test_chapter_zero_and_the_workflow_state_the_principle_and_asking_first() -> None:
    text = general_text(RUNBOOK.read_text(encoding="utf-8"))
    chapter_zero = " ".join(_section(text, "## 0. ", "## 0-1. ").split())
    dual_env = " ".join(DUAL_ENV.read_text(encoding="utf-8").split())

    for document in (chapter_zero, dual_env):
        assert PRINCIPLE in document
        assert "사용자에게 먼저 요청" in document
        assert "쉬운 말" in document and "사용자 승인 <YYYY-MM-DD>" in document
    assert USER_WINDOW in chapter_zero and "`!` 로 치지 않는다" in chapter_zero
    assert "런북 9장 「사내 탐색」 이다" not in dual_env


def test_the_copy_check_line_the_agent_types_opens_no_database() -> None:
    """6-3 3) 은 경로만 찍는다 — 에이전트가 한 호출에 `PYTHONPATH` 와 함께 친다."""
    text = RUNBOOK.read_text(encoding="utf-8")
    section = _section(text, "### 3) 사본이 맞는지", "### 4)")
    fences = [block for language, block in _pieces(section) if language is not None]

    assert len(fences) == 1
    [line] = [line for line in fences[0].splitlines() if line.strip()]
    assert line.startswith('$env:PYTHONPATH = "$e2e\\src"; & $py -c "')
    assert "duckdb" not in line and "DUCKDB_PATH" in line
    assert "**에이전트가**" in section


def _rule_matches(rule: str, command: str) -> bool:
    """권한 규칙 맞춤 — 끝의 `:*` 는 앞부분 맞춤, 그 밖의 `*` 는 아무 글자다(텍스트 맞춤)."""
    if "(" not in rule:
        return False
    body = rule[rule.index("(") + 1 : -1]
    if body.endswith(":*"):
        return command.startswith(body[:-2])
    return re.fullmatch(".*".join(re.escape(part) for part in body.split("*")), command) is not None


def _permissions() -> dict[str, list[str]]:
    permissions: dict[str, list[str]] = json.loads(TEMPLATE.read_text(encoding="utf-8"))[
        "permissions"
    ]
    return permissions


def _runbook_lines(*, opening: bool) -> list[str]:
    """런북 펜스 가운데 `uv run --no-sync python scripts/…` 꼴로 DB 스크립트를 부르는 줄."""
    lines = []
    for language, block in _pieces(RUNBOOK.read_text(encoding="utf-8")):
        if language not in ("powershell", "bash"):
            continue
        for line in block.splitlines():
            line = line.strip()
            if not line.startswith("uv run --no-sync python scripts/"):
                continue
            if not any(name in line for name in DATABASE_SCRIPTS):
                continue
            if any(flag in line for flag in DOES_NOT_OPEN) != opening:
                lines.append(line)
    return lines


def test_the_settings_template_denies_every_runbook_line_that_opens_a_database() -> None:
    """사용자가 고정한 auto 모드는 allow 가 없어도 묻지 않고 통과시킬 수 있다 — 그래서 deny 다.
    두 셸이 쌍이고, 걷은 BigDataQuery 줄과 인자 차례 그대로의 7장 꼴도 걸린다."""
    permissions = _permissions()
    prefix = "uv run --no-sync python scripts/"
    lines = [
        *_runbook_lines(opening=True),
        f"{prefix}inspect_real_data_checks.py",
        f"{prefix}inspect_real_data_checks.py --only bdq --output C:/Users/someone/bdq.md",
        f"{prefix}inspect_wf_division.py --output C:/Users/someone/wf.md",
        f'{prefix}inspect_wf_division.py --database "C:/Users/someone/e2e_copy/1/data/x.duckdb"',
        f"{prefix}check_deploy_screens.py --items alert_popup --playwright-dir C:/pw",
        f"{prefix}inspect_db_counts.py --output C:/Users/someone/db_counts.md",
        f"{prefix}inspect_db_counts.py",
    ]
    names = {name for name in DATABASE_SCRIPTS if any(name in line for line in lines)}

    assert names == set(DATABASE_SCRIPTS), names
    for line in lines:
        for shell in ("Bash", "PowerShell"):
            denied = [r for r in permissions["deny"] if r.startswith(shell + "(")]
            assert any(_rule_matches(rule, line) for rule in denied), (shell, line)
        allowed = [r for r in permissions["allow"] if r.startswith(("Bash(", "PowerShell("))]
        assert not [rule for rule in allowed if _rule_matches(rule, line)], line


def test_the_settings_template_still_lets_the_lines_that_open_nothing_through() -> None:
    """`--check-summary`(압축본 다시 셈) · `--list`(화면 확인 항목 목록)는 DB 를 열기 전에 끝난다 —
    deny 에 걸리면 안 되고, `--check-summary` 는 두 셸 모두 allow 다."""
    permissions = _permissions()
    lines = [
        *(line.replace("<ZIP 파일명>", "202611111500") for line in _runbook_lines(opening=False)),
        "uv run --no-sync python scripts/check_deploy_screens.py --list",
    ]

    assert any("--check-summary" in line for line in lines)
    for line in lines:
        assert not [rule for rule in permissions["deny"] if _rule_matches(rule, line)], line
        if "--check-summary" in line:
            matched = [rule for rule in permissions["allow"] if _rule_matches(rule, line)]
            assert sorted(rule.split("(")[0] for rule in matched) == ["Bash", "PowerShell"], line


def test_a_broad_allow_would_be_caught() -> None:
    """`:*` 를 앞부분 맞춤으로 읽어야 넓은 allow(`uv run --no-sync python:*`)가 DB 줄을 연다는
    것을 본다."""
    line = "uv run --no-sync python scripts/inspect_wf_division.py --output C:/x.md"

    assert _rule_matches("PowerShell(uv run --no-sync python:*)", line)
    assert _rule_matches(
        "PowerShell(uv run --no-sync python scripts/inspect_wf_division.py:*)", line
    )
    assert not _rule_matches(
        "PowerShell(uv run --no-sync python scripts/benchmark_home.py:*)", line
    )


def test_the_two_lines_that_open_nothing_end_before_any_database() -> None:
    """`--list` 는 `run()` 첫 갈래에서, `--check-summary` 는 `main()` 첫 갈래에서 끝난다 — 앱 ·
    DB 앞."""
    screens = (PROJECT_ROOT / "scripts" / "check_deploy_screens.py").read_text(encoding="utf-8")
    run = screens[screens.index("def run(") :]
    checks = (PROJECT_ROOT / "scripts" / "inspect_real_data_checks.py").read_text(encoding="utf-8")
    main = checks[checks.index("def main(") :]

    assert run.index("if args.list:") < run.index("refused_paths(args)") < run.index("OutputFile(")
    assert main.index("return _check_summary(") < main.index("_run(args")


def test_every_first_argument_of_the_two_partly_open_scripts_has_a_deny_pair() -> None:
    """`inspect_real_data_checks.py` · `check_deploy_screens.py` 는 첫 인자마다 deny 다 — 인자가
    늘면 여기서 빠진 쌍이 드러난다. DB 를 열지 않는 `--check-summary` · `--list` 만 deny 밖이다."""
    deny = set(_permissions()["deny"])
    prefix = "uv run --no-sync python scripts/"
    for name, safe in (
        ("inspect_real_data_checks.py", "--check-summary"),
        ("check_deploy_screens.py", "--list"),
    ):
        source = (PROJECT_ROOT / "scripts" / name).read_text(encoding="utf-8")
        flags = set(re.findall(r'add_argument\(\s*"(--[a-z][a-z-]*)"', source))
        assert safe in flags, name
        for flag in sorted(flags - {safe}):
            for shell in ("Bash", "PowerShell"):
                assert f"{shell}({prefix}{name} {flag}:*)" in deny, (shell, name, flag)
        for shell in ("Bash", "PowerShell"):
            assert f"{shell}({prefix}{name})" in deny, (shell, name)
            assert not [rule for rule in deny if rule.startswith(f"{shell}({prefix}{name} {safe}")]


# 실데이터 · 사본 · 백업 폴더 읽기 막음(2026-11-12 사용자 답 ⑤-5 (가)) — 막는 폴더 이름과 셸의
# 읽는 꼴.
DATA_FOLDERS = ("data", "e2e_copy", "capa-copy", "deploy_backup")
READ_VERBS = {"Bash": ("cat", "head", "tail"), "PowerShell": ("Get-Content", "gc", "cat", "type")}


def _read_rule_matches(rule: str, path: str) -> bool:
    """`Read(…)` 경로 규칙 맞춤 — `//` 는 파일 시스템 뿌리부터(Windows 는 `/c/…` 꼴로 바꾼 뒤),
    슬래시 없는 상대 꼴은 세션 폴더(저장소 뿌리 `/repo`)부터다. `**` 는 몇 마디든, `*` 는 한 마디
    안이다."""
    body = rule[len("Read(") : -1]
    pattern = body[1:] if body.startswith("//") else f"/repo/{body}"
    regex = ""
    index = 0
    while index < len(pattern):
        if pattern.startswith("/**/", index):
            regex += "/(?:.*/)?"
            index += 4
        elif pattern.startswith("**", index):
            regex += ".*"
            index += 2
        elif pattern[index] == "*":
            regex += "[^/]*"
            index += 1
        else:
            regex += re.escape(pattern[index])
            index += 1
    return re.fullmatch(regex, path) is not None


def _windows_path(path: str) -> str:
    """`C:\\Users\\x\\…` → `/c/Users/x/…`(권한 판단이 Windows 경로를 견주는 꼴)."""
    drive, rest = path.split(":", 1)
    return f"/{drive.lower()}{rest.replace(chr(92), '/')}"


def _shell_rule_matches(rule: str, command: str) -> bool:
    """셸 규칙은 줄 전체와 `|` · `;` 로 나눈 조각마다 본다(권한 판단이 이은 명령을 조각으로
    본다)."""
    pieces = [command, *(piece.strip() for piece in re.split(r"[|;]", command))]
    return any(_rule_matches(rule, piece) for piece in pieces if piece)


def test_the_settings_template_denies_reading_the_data_copy_and_backup_folders() -> None:
    """`Read` 도구와 셸의 읽는 꼴 모두 — 저장소 `data/`, 사본(`e2e_copy` · `capa-copy`),
    백업(`deploy_backup`)."""
    deny = _permissions()["deny"]
    reads = [rule for rule in deny if rule.startswith("Read(")]
    blocked_files = (
        "/repo/data/capa_simulation.duckdb",
        "/repo/data/input/Core_Data.csv",
        "/repo/data/modules/demo_x/notes.json",
        _windows_path("C:\\Users\\someone\\e2e_copy\\202611121200\\data\\capa_simulation.duckdb"),
        _windows_path("C:\\Users\\someone\\e2e_copy\\pr-202611121200\\data\\x.duckdb"),
        _windows_path("C:\\capa-copy\\generation.json"),
        _windows_path("C:\\Users\\someone\\deploy_backup\\202611121200\\Core_Data.csv"),
    )
    for path in blocked_files:
        assert any(_read_rule_matches(rule, path) for rule in reads), path
    commands = {
        "Bash": (
            "cat data/input/Core_Data.csv",
            "head -5 /c/Users/someone/e2e_copy/1/data/input/a.csv",
            "tail -n 3 /c/Users/someone/deploy_backup/202611121200/a.csv",
            "cat /c/capa-copy/generation.json",
        ),
        "PowerShell": (
            "Get-Content data\\input\\Core_Data.csv",
            'Get-Content "$e2e\\data\\capa_simulation.duckdb" -TotalCount 1',
            "gc C:\\Users\\someone\\deploy_backup\\202611121200\\a.csv",
            "type C:\\capa-copy\\generation.json",
            "cat ./data/temp/container_start.json",
            "Select-String -Path C:\\Users\\someone\\e2e_copy\\1\\data\\input\\a.csv -Pattern x",
        ),
    }
    for shell, lines in commands.items():
        rules = [rule for rule in deny if rule.startswith(shell + "(")]
        for line in lines:
            assert any(_shell_rule_matches(rule, line) for rule in rules), (shell, line)
    for shell, verbs in READ_VERBS.items():
        for verb in verbs:
            for folder in DATA_FOLDERS:
                assert any(
                    rule.startswith(f"{shell}({verb} ") and folder in rule for rule in deny
                ), (shell, verb, folder)


def _new_read_denies() -> list[str]:
    return [
        rule
        for rule in _permissions()["deny"]
        if rule.startswith(("Bash(", "PowerShell("))
        and any(folder in rule for folder in DATA_FOLDERS)
        and not rule.split("(", 1)[1].startswith("uv run")
    ]


def test_the_result_files_the_user_hands_over_stay_readable() -> None:
    """사용자가 `--output` 으로 준 결과 파일(런북은 `$HOME\\<이름>` 에 둔다)은 막지 않는다 —
    에이전트가 읽는 유일한 것이다."""
    text = RUNBOOK.read_text(encoding="utf-8")
    outputs = set(re.findall(r"--output \"?(\$HOME[\\/][\w.-]+)", text))
    outputs |= {"$HOME\\db_counts.md", "$HOME\\real_data_check.md", "$HOME\\wf_division.md"}
    reads = [rule for rule in _permissions()["deny"] if rule.startswith("Read(")]
    shells = _new_read_denies()

    assert len(outputs) >= 5, outputs
    for output in sorted(outputs):
        windows = output.replace("$HOME", "C:\\Users\\someone").replace("/", "\\")
        assert not [rule for rule in reads if _read_rule_matches(rule, _windows_path(windows))]
        for line in (f"Get-Content {output}", f"Get-Content {windows}", f"type {windows}"):
            assert not [rule for rule in shells if _shell_rule_matches(rule, line)], line


def test_no_runbook_line_is_caught_by_the_folder_read_denies() -> None:
    """에이전트가 치는 런북 줄(펜스 안)이 새 읽기 막음에 걸리지 않는다 — 1-6 의 `git ls-files |
    Select-String -Pattern '…^data/input/…'` 처럼 글자 `data/` 가 든 줄도."""
    shells = _new_read_denies()
    caught = [
        line.strip()
        for language, block in _pieces(RUNBOOK.read_text(encoding="utf-8"))
        if language in ("powershell", "bash", "")
        for line in block.splitlines()
        if line.strip() and any(_shell_rule_matches(rule, line.strip()) for rule in shells)
    ]

    assert caught == []
