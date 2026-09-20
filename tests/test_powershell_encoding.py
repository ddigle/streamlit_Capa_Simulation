# Purpose: PowerShell 스크립트가 조용히 깨진 채로 저장되는 것을 막는다.

"""오류도 종료코드도 정상인데 내용만 망가지는 두 가지를 잡는다.

**하나. Windows PowerShell 5.1 은 BOM 이 없는 `.ps1` 을 ANSI 로 읽는다.** 이 PC 의 ANSI 는
cp949 라, BOM 없이 UTF-8 로 저장한 `.ps1` 안의 한글이 **파일을 읽는 시점에** 깨진다. 주석만
깨지면 눈에 거슬리는 정도지만, 문자열 리터럴이 깨지면 그 글자가 그대로 화면에 나가고
**파일로도 쓰인다.** 실제로 `scripts/new_worktree.ps1` 이 만든 작업 폴더 실행기(`run.ps1`)의
주석이 통째로 깨져 저장됐다. 스크립트는 정상 종료했고 포트 값도 맞았다.

**둘. 줄 안에 홀로 박힌 캐리지 리턴이 문자열을 두 줄로 쪼갠다.** 도구가 백슬래시 이스케이프를
한 겹 먹으면 넣으려던 경로 구분자가 진짜 CR 이 되어 들어간다. PowerShell 은 큰따옴표 문자열이
여러 줄에 걸치는 것을 허용하므로 **문법 오류가 나지 않는다.** 화면에 찍힐 때만 커서가 줄
앞으로 돌아가 앞글자를 덮어쓴다 — 안내 문구의 경로가 통째로 잘려 나갔는데 스크립트는
성공으로 끝났다.

파이썬 쪽은 둘 다 문제가 없다(`.py` 는 UTF-8 이 기본이고 이스케이프를 파서가 잡는다).
`.ps1` 만 본다.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BOM = b"\xef\xbb\xbf"
CR = "\r"
LF = "\n"


def _powershell_files() -> list[Path]:
    """저장소가 **소유한** `.ps1` 만. `rglob` 은 `.venv` 안의 `activate.ps1` 까지 훑는다."""
    completed = subprocess.run(
        ["git", "ls-files", "*.ps1"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [PROJECT_ROOT / line.strip() for line in completed.stdout.splitlines() if line.strip()]


def test_powershell_scripts_start_with_a_byte_order_mark() -> None:
    files = _powershell_files()
    assert files, "`.ps1` 을 하나도 못 찾았습니다 — 이 검사가 헛돌고 있습니다."

    missing = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in files
        if not path.read_bytes().startswith(BOM)
    ]

    assert not missing, (
        "BOM 없이 저장된 PowerShell 스크립트가 있습니다. Windows PowerShell 5.1 이 이런 "
        "파일을 cp949 로 읽어 **안의 한글이 파싱 시점에 깨집니다**. 오류는 나지 않고 "
        "깨진 글자가 화면과 생성 파일에 그대로 나갑니다. UTF-8 with BOM 으로 저장하세요:\n  "
        + "\n  ".join(missing)
    )


def test_powershell_scripts_have_no_stray_carriage_return() -> None:
    """줄 **안**에 있는 CR 만 본다. 줄 끝의 CR 은 CRLF 라 정상이다."""
    offenders: list[str] = []
    for path in _powershell_files():
        text = path.read_bytes().decode("utf-8-sig")
        for number, line in enumerate(text.split(LF), 1):
            if CR in line.rstrip(CR):
                offenders.append(f"{path.relative_to(PROJECT_ROOT).as_posix()}:{number}")

    assert not offenders, (
        "줄 안에 캐리지 리턴이 박힌 PowerShell 스크립트가 있습니다. 문법 오류도 나지 않고 "
        "종료코드도 0 이라 검사로만 잡힙니다:\n  " + "\n  ".join(offenders)
    )


def test_powershell_scripts_are_valid_utf8() -> None:
    """BOM 을 붙이면서 내용이 깨지지 않았는지 함께 본다."""
    broken: list[str] = []
    for path in _powershell_files():
        try:
            path.read_bytes().decode("utf-8-sig")
        except UnicodeDecodeError as error:
            broken.append(f"{path.relative_to(PROJECT_ROOT).as_posix()}: {error}")

    assert not broken, "UTF-8 로 읽히지 않는 PowerShell 스크립트가 있습니다:\n  " + "\n  ".join(
        broken
    )
