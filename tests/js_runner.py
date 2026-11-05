# Purpose: 시험이 JS 글을 node(없으면 bun)로 돌리는 한 길과 Windows 명령줄 상한 재기를 둔다.

"""자산 JS 의 순수 구획·가짜 DOM 러너를 돌리는 시험은 모두 이 도우미를 지난다.

스크립트는 임시 `.cjs` 파일로, 자료는 표준 입력으로 넘긴다 — 명령줄에 실으면 사내 Windows 에서
상한(32,767자)을 넘어 node 가 뜨지도 못한다(`WinError 206`, 사내 리뷰 `202610271800`과
`202611041000`에서 같은 꼴로 두 번 깨졌다). `.cjs` 라 가까운 `package.json` 이 무엇이든
CommonJS(`require`)로 돈다. node·bun 이 없으면 건너뛰고 CI(`GITHUB_ACTIONS`)에서는 실패다.
`tests/test_js_runner.py` 의 그물이 다른 길(`node -e`·`shutil.which("node")`)을 막고,
`conftest.py` 가 모든 자식 프로세스 명령줄을 Linux 에서도 같은 상한으로 잰다.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

# Windows `CreateProcess` 의 명령줄 상한(UTF-16 글자 수, 끝 NUL 포함).
WINDOWS_COMMAND_LINE_LIMIT = 32_767
# 실행 파일·임시 폴더 경로는 사내 Windows 쪽이 더 길다 — 그만큼 먼저 막는다.
_WINDOWS_PATH_MARGIN = 1_024

Command = str | bytes | os.PathLike[str] | Sequence[str | os.PathLike[str]]


def js_runtime() -> str | None:
    """node(없으면 bun) 경로."""
    return shutil.which("node") or shutil.which("bun")


def need_js_runtime(what: str) -> str:
    """node·bun 경로 — 없으면 건너뛰고 CI 에서는 실패한다. `what` 은 실패 말에 넣는 시험 이름."""
    found = js_runtime()
    if found is None:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            pytest.fail(f"CI 러너에 node 가 없다 — 건너뛸 수 없다: {what}")
        pytest.skip("node·bun 이 없다 — CI 에서 돈다")
    return found


def run_js(
    source: str,
    *,
    what: str,
    stdin: str | None = None,
    timeout: float = 60,
) -> subprocess.CompletedProcess[str]:
    """`source` 를 임시 `.cjs` 파일로 돌린다. 자료는 `stdin` 으로 준다(러너가 fd 0 을 읽는다)."""
    runtime = need_js_runtime(what)
    with tempfile.TemporaryDirectory() as folder:
        script = Path(folder) / "case.cjs"
        script.write_text(source, encoding="utf-8", newline="\n")
        return subprocess.run(
            [runtime, str(script)],
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            check=False,
        )


def run_js_json(
    source: str,
    *,
    what: str,
    stdin: str | None = None,
    timeout: float = 60,
) -> Any:
    """`run_js` 가 끝낸 표준 출력을 JSON 으로 읽는다. 0 이 아닌 종료는 시험 실패다."""
    completed = run_js(source, what=what, stdin=stdin, timeout=timeout)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def windows_command_line_length(args: Command) -> int:
    """`args` 를 Windows 가 짓는 꼴(`list2cmdline`)로 이었을 때의 UTF-16 글자 수."""
    if isinstance(args, str | bytes | os.PathLike):
        text = os.fsdecode(args)
    else:
        text = subprocess.list2cmdline(os.fsdecode(arg) for arg in args)
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def refuse_overlong_command_line(args: Command) -> None:
    """사내 Windows 가 `WinError 206` 으로 거절할 명령줄이면 Linux 에서도 같은 자리에서 실패한다."""
    length = windows_command_line_length(args)
    if length + _WINDOWS_PATH_MARGIN >= WINDOWS_COMMAND_LINE_LIMIT:
        raise OSError(
            f"명령줄이 {length:,}자다 — 사내 Windows 상한 {WINDOWS_COMMAND_LINE_LIMIT:,}자에서 "
            "WinError 206 으로 뜨지도 못한다. 긴 글은 파일·표준 입력으로 넘긴다(AGENTS 2장)"
        )
