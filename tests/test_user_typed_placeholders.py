# Purpose: 사용자가 치는 문서 줄에 사내 값 꺾쇠 자리표와 따옴표 안 꺾쇠가 없는지 본다.

"""사내 리뷰 202611131000 — `$b = "<C-DEP 표의 CAPA_S3_BUCKET 값>"` 의 꺾쇠 안쪽만 바꿔 넣어
버킷 값이 꺾쇠째 aws 로 갔다. PowerShell 은 따옴표 안 꺾쇠를 글자로 넘겨 말없이 돌고,
`[Environment]::SetEnvironmentVariable` 줄이면 꺾쇠째 사용자 환경변수에 남는다.

그래서 사용자가 치는 펜스(`powershell` · `bash` · 언어 없음)와 본문의 명령 백틱에는 둘을 두지
않는다.

- (i) 사내 값(버킷 · 주소 · 프로필 · 계정 · 토큰 · 비밀 · 메일)을 가리키는 꺾쇠 — 앞 줄
  `Read-Host` · `read -rp` 로 받고 명령에는 변수만 쓴다.
- (ii) 따옴표 안 꺾쇠 — 비밀이 아니면 이름을 박거나 에이전트가 채운 줄로 건넨다.

런북은 `test_runbook_no_internal_db_reads.py` 가 같은 잣대로 본다(이미 나간 7장은 뗀다).
"""

from __future__ import annotations

import re
from pathlib import Path

from test_runbook_no_internal_db_reads import (
    CODE_SPAN,
    IN_HOUSE_PLACEHOLDER,
    QUOTED_PLACEHOLDER,
    _pieces,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = (
    "docs/objectstore_setup.md",
    "README.md",
    "docs/bigdataquery_webide_setup.md",
    "docs/sso_setup.md",
)
COMMAND_FENCES = ("powershell", "bash", "")
# 본문 백틱 가운데 명령으로 보는 꼴 — 이름만 든 백틱(`CAPA_S3_BUCKET`)은 보지 않는다.
COMMAND_SPAN = re.compile(
    r"uv run|python|\bgit |\[Environment\]|Get-|Set-|aws |\$[A-Za-z]|base64|export |"
    r"Expand-Archive|--[a-z]|read -"
)
# 사내 값이 아닌 파일 자리 — 따옴표 밖이라 치면 그 줄에서 멈춘다.
ALLOWED = {("docs/sso_setup.md", "base64 -w0 <토큰 서명 인증서 파일>")}


def placeholder_lines(text: str) -> list[str]:
    """사용자가 치는 줄 가운데 (i) 사내 값 꺾쇠 · (ii) 따옴표 안 꺾쇠가 든 줄(펜스 줄 또는 백틱)."""
    found: list[str] = []
    for language, block in _pieces(text):
        if language is None:
            candidates = [span for span in CODE_SPAN.findall(block) if COMMAND_SPAN.search(span)]
        elif language in COMMAND_FENCES:
            candidates = [line.strip() for line in block.splitlines()]
        else:
            continue
        found.extend(
            line
            for line in candidates
            if IN_HOUSE_PLACEHOLDER.search(line) or QUOTED_PLACEHOLDER.search(line)
        )
    return found


def test_user_typed_lines_carry_no_in_house_or_quoted_placeholder() -> None:
    for name in DOCUMENTS:
        text = (PROJECT_ROOT / name).read_text(encoding="utf-8")
        left = [line for line in placeholder_lines(text) if (name, line) not in ALLOWED]

        assert left == [], (name, left)


def test_the_allowed_places_are_still_there() -> None:
    """허용 자리가 사라지면 목록도 줄인다 — 남은 허용이 새 자리를 덮지 않게."""
    for name, line in ALLOWED:
        text = (PROJECT_ROOT / name).read_text(encoding="utf-8")

        assert line in placeholder_lines(text), (name, line)


def test_the_net_catches_the_reviewed_shapes_and_passes_the_read_host_shapes() -> None:
    """사내 리뷰의 꼴(펜스 · 환경변수 줄 · 본문 백틱)은 잡히고, 그 자리의 `Read-Host` 꼴은
    지난다."""
    set_variable = '[Environment]::SetEnvironmentVariable("X", {value}, "User")'
    caught = [
        '```powershell\n$b = "<C-DEP 표의 CAPA_S3_BUCKET 값>"\n```',
        "```powershell\n" + set_variable.format(value='"<사내 S3 주소>"') + "\n```",
        '```bash\nexport CAPA_BDQ_USER_NAME="<AD 계정>"\n```',
        '```powershell\n$env:CAPA_MODULES_DISABLED="<id>"\n```',
        "받는다 — `git clone <저장소 주소> C:\\dev\\x` 로.",
    ]
    passed = [
        '```powershell\n$b = Read-Host "C-DEP 표의 CAPA_S3_BUCKET 값"\n```',
        "```powershell\n" + set_variable.format(value='(Read-Host "사내 S3 주소")') + "\n```",
        '```bash\nread -rp "AD 계정: " u\n```',
        '`aws configure get endpoint_url --profile (Read-Host "프로필 이름")` 의 출력.',
        "이름만 든 백틱 `<사내 S3 주소>` 은 명령이 아니다.",
    ]

    for text in caught:
        assert placeholder_lines(text), text
    for text in passed:
        assert placeholder_lines(text) == [], text
