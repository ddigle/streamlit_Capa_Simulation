# Purpose: 사내 런북이 운영 DB · 4-1 의존성 줄을 처음부터 사용자에게 주고 1-3 백업 줄이 서는지 본다.

"""런북 1-3 · 7-8 · 8-0 의 운영 DB 줄은 에이전트가 치지 않고 처음부터 사용자에게 준다.

`202610271800` 리뷰(사외 요청 5)에서 사용자가 고른 auto 모드의 권한 판단이 1-3 백업
복사, 7-8 첫 줄(운영 DB 를 `read_only` 로 연다), 8장 첫 줄, `inspect_wf_division.py` 를
모두 막아 사용자가 `!` 로 쳤다. 7장은 배포마다 다시 쓰이므로 그 규칙이 다음 판에서
빠지지 않게 문서 글자를 견준다 — 문장을 고치면 같이 고친다.

1-3 의 `!` 한 줄은 셸이 Git Bash 든 PowerShell 이든 같은 줄이어야 하고(큰따옴표 · `$` ·
백틱이 없다), 출력은 사내 Windows 콘솔 코드페이지를 거쳐도 깨지지 않게 영문 · 숫자뿐이다.
그 줄을 합성 폴더에서 실제로 돌려 본다.

4-1 의 `uv sync --inexact` 는 운영 DB 줄이 아니지만 같은 길이다 — 권한 템플릿이 `uv sync` 를
막아(deny) 에이전트가 칠 수 없고, `202611041000` 리뷰(사외 요청 2)에서 auto 모드도 막았다.
같은 리뷰(사외 요청 1)의 pandas 충돌이 다시 나면 이 자리에서 보이게 충돌 확인 줄을 함께 둔다.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = PROJECT_ROOT / "docs" / "internal_update_runbook.md"
USER_FROM_THE_START = "처음부터 사용자에게 준다"


def _text() -> str:
    return RUNBOOK.read_text(encoding="utf-8")


def _section(start: str, end: str) -> str:
    text = _text()
    begin = text.index(start)
    return text[begin : text.index(end, begin + len(start))]


def _paragraph_with(section: str, fragment: str) -> str:
    found = [block for block in section.split("\n\n") if fragment in block]
    assert len(found) == 1, f"{fragment!r} 문단이 하나가 아니다: {len(found)}"
    return found[0]


def test_the_backup_the_seven_eight_lines_and_chapter_eight_go_to_the_user() -> None:
    backup = _section("### 1-3.", "### 1-4.")
    seven_eight = _section("### 7-8.", "\n## 8.")
    chapter_eight = _section("### 8-0.", "### 8-1.")

    assert USER_FROM_THE_START in backup
    assert USER_FROM_THE_START in _paragraph_with(seven_eight, "아래 두 줄을")
    wf_division = _paragraph_with(seven_eight, "scripts/inspect_wf_division.py` 를 한 번 돌려")
    assert re.search(r"이 한 줄도 처음부터 사용자에게\s+준다", wf_division)
    assert "권한 판단이 막으면" not in wf_division
    assert USER_FROM_THE_START in chapter_eight
    assert "inspect_wf_division.py" in _paragraph_with(chapter_eight, USER_FROM_THE_START)


def test_the_blocked_lines_table_lists_every_operational_database_line() -> None:
    chapter_six = _section("## 6. 막혔을 때", "## 6-1.")
    rows = {
        line.split("|")[1].strip() for line in chapter_six.splitlines() if line.startswith("| ")
    }

    rule = "운영 DB 를 복사하거나 여는 줄은 막히기를 기다리지 않고 처음부터 사용자에게 준다"
    assert rule in chapter_six
    assert "운영 데이터 백업(1-3)" in rows
    assert "7-8 개수 조회 두 줄 · 그 뒤 `inspect_wf_division.py`" in rows
    assert "`inspect_real_data_checks.py`(8장, 매번 막혔다)" in rows


def test_the_dependency_lines_go_to_the_user_with_the_conflict_check() -> None:
    dependencies = _section("### 4-1.", "### 4-2.")
    chapter_six = _section("## 6. 막혔을 때", "## 6-1.")
    rows = {
        line.split("|")[1].strip() for line in chapter_six.splitlines() if line.startswith("| ")
    }
    template = (PROJECT_ROOT / "docs" / "internal_claude_settings.json").read_text(encoding="utf-8")

    assert USER_FROM_THE_START in dependencies
    lines = dependencies.splitlines()
    assert lines.index("uv sync --inexact") + 1 == lines.index("uv pip check")
    assert "의존성 맞추기(4-1)" in rows
    assert '"Bash(uv sync:*)"' in template and '"PowerShell(uv sync:*)"' in template


def _backup_code() -> str:
    lines = [
        line.strip()
        for line in _section("### 1-3.", "### 1-4.").splitlines()
        if line.startswith('uv run --no-sync python -c "')
    ]
    assert len(lines) == 1, lines
    code = lines[0][len('uv run --no-sync python -c "') : -1]
    assert lines[0].endswith('"')
    assert '"' not in code and "$" not in code and "`" not in code
    assert code.isascii()
    return code


def test_the_backup_line_copies_both_databases_and_the_input_folder(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    (repository / "data" / "input" / "sub").mkdir(parents=True)
    (repository / "data" / "capa_simulation.duckdb").write_bytes(b"s" * 1000)
    (repository / "data" / "equipment_availability.duckdb").write_bytes(b"e" * 300)
    (repository / "data" / "input" / "Core_Data.csv").write_text("a\n", encoding="utf-8")
    (repository / "data" / "input" / "sub" / "x.txt").write_text("b\n", encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home)}

    done = subprocess.run(
        [sys.executable, "-c", _backup_code()],
        cwd=repository,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )

    assert done.returncode == 0, done.stderr
    head, *rows = done.stdout.split("\n")[:-1]
    assert re.fullmatch(r"\d{12}", head), head
    assert rows == [
        "capa_simulation.duckdb 1000 1000",
        "equipment_availability.duckdb 300 300",
    ]
    backup = home / "deploy_backup" / head
    assert (backup / "capa_simulation.duckdb").read_bytes() == b"s" * 1000
    assert (backup / "Core_Data.csv").is_file() and (backup / "sub" / "x.txt").is_file()


def test_the_backup_line_copies_a_leftover_wal_with_its_database(tmp_path: Path) -> None:
    """앱이 저장을 마치지 못한 채 꺼지면 `.wal` 이 운영 DB 의 짝으로 남는다 — 빼고 복사하면 백업이
    마지막 저장을 잃는다. 이름이 비슷한 다른 파일은 따라오지 않는다."""
    repository = tmp_path / "repository"
    (repository / "data").mkdir(parents=True)
    (repository / "data" / "capa_simulation.duckdb").write_bytes(b"s" * 10)
    (repository / "data" / "capa_simulation.duckdb.wal").write_bytes(b"w" * 3)
    (repository / "data" / "capa_simulation.duckdb.bak").write_bytes(b"b")
    home = tmp_path / "home"
    home.mkdir()
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home)}

    done = subprocess.run(
        [sys.executable, "-c", _backup_code()],
        cwd=repository,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )

    assert done.returncode == 0, done.stderr
    head, *rows = done.stdout.split("\n")[:-1]
    assert rows == ["capa_simulation.duckdb 10 10", "capa_simulation.duckdb.wal 3 3"]
    backup = home / "deploy_backup" / head
    assert (backup / "capa_simulation.duckdb.wal").read_bytes() == b"w" * 3
    assert not (backup / "capa_simulation.duckdb.bak").exists()
