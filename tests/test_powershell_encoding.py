# Purpose: PowerShell 스크립트가 BOM 없이 저장돼 한글이 깨지는 것을 막는다.

"""**Windows PowerShell 5.1 은 BOM 이 없는 `.ps1` 을 ANSI 로 읽는다.**

이 PC 의 ANSI 는 cp949 라, BOM 없이 UTF-8 로 저장한 `.ps1` 안의 한글이 **파일을 읽는
시점에** 깨진다. 주석만 깨지면 눈에 거슬리는 정도지만, 문자열 리터럴이 깨지면 그 글자가
그대로 화면에 나가고 **파일로도 쓰인다.**

실제로 그랬다. `scripts/new_worktree.ps1` 이 만든 작업 폴더 실행기(`run.ps1`)의 주석이
통째로 깨져 저장됐다. 스크립트는 정상 종료했고 포트 값도 맞았다 — 오류가 나지 않는 종류의
고장이라 검사로만 잡힌다.

파이썬 쪽은 이 문제가 없다(`.py` 는 UTF-8 이 기본이다). `.ps1` 만 본다.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BOM = b"\xef\xbb\xbf"


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
