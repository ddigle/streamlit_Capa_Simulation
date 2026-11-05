# Purpose: 시험의 JS 실행 도우미·명령줄 상한 재기와 사내 Windows 에서 깨지는 꼴을 막는 그물을 본다.

"""사내 리뷰 `202610271800`과 `202611041000` 에서 Linux 에서는 돌고 Windows 4관문에서만 깨진 시험의
뒤처리다.

명령줄 상한은 `conftest.py` 가 Linux 에서도 같은 자리에서 실패시키고, 그 밖의 꼴(`node -e`·node
찾기를 따로 두기·`str(경로.relative_to(…))`)은 여기 그물이 소스에서 막는다. AGENTS 2장 「시험은 사내
Windows 4관문에서도 돈다」.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import js_runner
import pytest

TESTS = Path(__file__).resolve().parent
# 도우미 자신은 node 를 찾는 한 자리다.
_NET_EXEMPT = {"js_runner.py"}
_JS_RUNTIMES = {"node", "bun"}
_EVAL_FLAGS = {"-e", "--eval", "-p", "--print", "-pe"}


def _dotted(node: ast.expr) -> str:
    """`a.b.c` 꼴 이름. 그 밖의 식은 빈 글이다."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        head = _dotted(node.value)
        return f"{head}.{node.attr}" if head else ""
    return ""


def _js_command_sites(source: str) -> list[str]:
    """JS 를 도우미 밖 길로 띄우는 자리 — 실행 파일을 따로 찾거나 스크립트를 명령줄에 싣는다."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Call)
            and _dotted(node.func).rsplit(".", 1)[-1] == "which"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value in _JS_RUNTIMES
        ):
            found.append(f"{node.lineno} which({node.args[0].value!r})")
        if not isinstance(node, ast.List) or not node.elts:
            continue
        head = node.elts[0]
        if isinstance(head, ast.Constant):
            if head.value in _JS_RUNTIMES:
                found.append(f"{node.lineno} [{head.value!r}, …]")
            continue
        if _dotted(head) == "sys.executable":
            continue
        flags = [
            item.value
            for item in node.elts
            if isinstance(item, ast.Constant) and item.value in _EVAL_FLAGS
        ]
        if flags:
            found.append(f"{node.lineno} {flags[0]!r}")
    return found


def _os_path_texts(source: str) -> list[int]:
    """`str(경로.relative_to(…))` 자리 — Windows 에서 `\\` 로 이어 `/` 꼴 기대와 어긋난다."""
    return [
        node.lineno
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and _dotted(node.func) == "str"
        and node.args
        and isinstance(node.args[0], ast.Call)
        and isinstance(node.args[0].func, ast.Attribute)
        and node.args[0].func.attr == "relative_to"
    ]


def _test_sources() -> list[Path]:
    return [path for path in sorted(TESTS.rglob("*.py")) if path.name not in _NET_EXEMPT]


def test_no_test_starts_js_outside_the_helper() -> None:
    """`node -e` 로 다시 들어오면 사내에서 뜨지도 못한다(스크립트가 자라 상한을 넘는 날에야 깨진다).
    JS 는 `js_runner` 한 길로 — 파일·표준 입력이라 길이가 문제 되지 않는다."""
    found = [
        f"{path.relative_to(TESTS)}:{site}"
        for path in _test_sources()
        for site in _js_command_sites(path.read_text(encoding="utf-8"))
    ]
    assert found == []


@pytest.mark.parametrize(
    ("source", "hits"),
    [
        ('[runtime, "-e", script]', 1),
        ('[_runtime(), "--eval", script]', 1),
        ('["node", path]', 1),
        ('shutil.which("bun")', 1),
        ('which("node")', 1),
        ('[sys.executable, "-c", code, "-p", "plugin"]', 0),
        ('["git", "-c", "core.quotePath=false", "-e"]', 0),
        ("[runtime, path]", 0),
        ('shutil.which("uv")', 0),
    ],
)
def test_the_js_net_catches_the_old_shapes(source: str, hits: int) -> None:
    assert len(_js_command_sites(source)) == hits


def test_no_test_builds_a_path_text_in_the_os_shape() -> None:
    """경로를 글자로 견주는 시험은 `relative_to(…).as_posix()` 로 짓는다(AGENTS 2장 ①)."""
    found = [
        f"{path.relative_to(TESTS)}:{line}"
        for path in _test_sources()
        for line in _os_path_texts(path.read_text(encoding="utf-8"))
    ]
    assert found == []


@pytest.mark.parametrize(
    ("source", "hits"),
    [
        ("str(path.relative_to(root))", 1),
        ("path.relative_to(root).as_posix()", 0),
        ('f"{path.relative_to(root)}: {line}"', 0),
        ("str(path)", 0),
    ],
)
def test_the_path_net_catches_the_old_shape(source: str, hits: int) -> None:
    assert len(_os_path_texts(source)) == hits


def test_the_script_stays_off_the_command_line(monkeypatch: pytest.MonkeyPatch) -> None:
    """스크립트는 임시 파일에 그대로(UTF-8) 있고 명령줄은 Windows 가 짓는 꼴로 재어도 짧다."""
    source = "// " + "가" * 100_000
    seen: list[tuple[list[str], str]] = []

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.append((list(args), Path(args[-1]).read_text(encoding="utf-8")))
        return subprocess.CompletedProcess(args, 0, stdout='{"ok": true}', stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(js_runner, "js_runtime", lambda: "node")

    assert js_runner.run_js_json(source, what="시험") == {"ok": True}

    [(args, script)] = seen
    assert js_runner.windows_command_line_length(args) < 1_000
    assert script == source


def test_a_script_past_the_limit_runs_and_reads_its_data_from_stdin() -> None:
    """상한을 넘는 스크립트도 그대로 돌고, 글자가 깨지지 않으며, 자료는 표준 입력으로 받는다."""
    comment = "// " + "가" * (js_runner.WINDOWS_COMMAND_LINE_LIMIT + 1) + "\n"
    runner = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
process.stdout.write(JSON.stringify({ name: input.name + ' 😀', argv: process.argv.length }))
"""
    result = js_runner.run_js_json(
        comment + runner, what="JS 실행 도우미 시험", stdin=json.dumps({"name": "가"})
    )
    assert result == {"name": "가 😀", "argv": 2}


def test_a_failed_script_fails_the_test_with_its_stderr() -> None:
    with pytest.raises(AssertionError, match="boom"):
        js_runner.run_js_json("throw new Error('boom')", what="JS 실행 도우미 시험")


@pytest.mark.parametrize(
    ("args", "length"),
    [
        (["a b", 'c"d'], 10),
        (["가"], 1),
        (["\U0001f600"], 2),
        ("가 나", 3),
        ([Path("x")], 1),
    ],
)
def test_the_length_is_counted_the_way_windows_builds_the_line(args: Any, length: int) -> None:
    """공백·따옴표는 `list2cmdline` 꼴로 늘고, 상한은 UTF-16 글자라 BMP 밖 글자는 둘로 센다."""
    assert js_runner.windows_command_line_length(args) == length


def test_a_command_line_past_the_windows_limit_is_refused_here_too() -> None:
    """Linux 는 이 길이도 띄우지만 사내 Windows 는 `WinError 206` 으로 뜨지도 못한다 —
    `conftest.py` 가 모든 자식 프로세스에서 같은 자리에 실패시켜 사내까지 가기 전에 드러난다."""
    long_argument = "x" * js_runner.WINDOWS_COMMAND_LINE_LIMIT
    with pytest.raises(OSError, match="WinError 206"):
        subprocess.run([sys.executable, "-c", "pass", long_argument], check=False)

    completed = subprocess.run([sys.executable, "-c", "pass", "short"], check=False)
    assert completed.returncode == 0
