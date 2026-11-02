# Purpose: 범용 편집 그리드 JS 의 순수 구획을 떼어 node(없으면 bun)로 돌리는 시험 도우미다.

"""AppTest 는 그리드 JS 를 돌리지 못한다. DOM 을 모르는 순수 구획(`// <eg-…>` ~ `// </eg-…>`)을 자산
파일에서 떼어 이어 붙이고 러너 글을 뒤에 붙여 node 로 돌린다(설비 마스터 표 자산 시험 꼴). node·bun
이 없으면 건너뛰고 CI(`GITHUB_ACTIONS`)에서는 실패다. 스크립트는 임시 `.cjs` 파일로 넘긴다 —
명령줄에 실으면 사내 Windows 명령줄 상한(32,767자)을 넘는다. 입력은 표준 입력 JSON 이다.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

ASSETS = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "capa_simulation"
    / "components"
    / "edit_grid_assets"
)


def asset(name: str) -> str:
    """자산 파일 글."""
    return (ASSETS / name).read_text(encoding="utf-8")


def section(text: str, name: str) -> str:
    """`// <name>` ~ `// </name>` 사이 글. 없으면 시험 실패."""
    match = re.search(rf"// <{re.escape(name)}>\n(?P<body>.*?)// </{re.escape(name)}>", text, re.S)
    assert match, f"// <{name}> 구획이 없습니다"
    return match.group("body")


def sections(text: str, names: Sequence[str]) -> str:
    """여러 구획을 차례로 이은 글."""
    return "\n".join(section(text, name) for name in names)


def runtime() -> str | None:
    return shutil.which("node") or shutil.which("bun")


def need_runtime() -> str:
    """node(없으면 bun) 경로 — 없으면 건너뛴다(CI 는 실패)."""
    found = runtime()
    if found is None:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            pytest.fail("CI 러너에 node 가 없다 — 편집 그리드 JS 대조를 건너뛸 수 없다")
        pytest.skip("node·bun 이 없다 — CI 에서 돈다")
    return found


def run_node(source: str, runner: str, payload: object) -> Any:
    """`source` 뒤에 `runner` 를 붙여 돌리고 표준 출력 JSON 을 돌려준다(`.cjs` — CommonJS)."""
    node = need_runtime()
    with tempfile.TemporaryDirectory() as folder:
        script = Path(folder) / "edit_grid_case.cjs"
        script.write_text(source + "\n" + runner, encoding="utf-8", newline="\n")
        completed = subprocess.run(
            [node, str(script)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            check=False,
        )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def check_module(source: str) -> subprocess.CompletedProcess[str]:
    """ES 모듈 글을 node `--check` 로 읽힌다(문법만)."""
    node = need_runtime()
    with tempfile.TemporaryDirectory() as folder:
        script = Path(folder) / "edit_grid_module.mjs"
        script.write_text(source, encoding="utf-8", newline="\n")
        return subprocess.run(
            [node, "--check", str(script)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            check=False,
        )


# 러너 머리 — 표준 입력 JSON 을 `input` 으로, 결과는 `done(value)` 로 낸다.
RUNNER_HEAD = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const done = (value) => process.stdout.write(JSON.stringify(value, (key, item) => {
  if (item instanceof Map) return Array.from(item.entries())
  if (ArrayBuffer.isView(item)) return Array.from(item, (x) => (Number.isNaN(x) ? null : x))
  return item
}))
"""
