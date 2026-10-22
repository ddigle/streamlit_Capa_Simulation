# Purpose: 따라하기 가이드 틀과 예시판이 앱의 테마 값을 대소문자 없이 따르는지 node 로 돌려 잰다.

"""가이드 창의 밝기 — 틀(`guides/howto/template.html`)과 예시판(`static/guides/howto/lob.html`).

앱의 테마 버튼은 `localStorage["capa-theme"]`(`theme_toggle.THEME_APP_KEY`)에 `"Dark"`·`"Light"`
(첫 글자 대문자)를 적는다. 가이드 창은 같은 출처라 그 값을 읽어 `data-theme` 을 소문자로 단다 —
글자 꼴이 달라도 같은 값으로 받아야 하고, 앱 창이 테마를 바꾸면 `storage` 이벤트로 따라와야 한다.

소스 문자열이 아니라 **돌려 본 결과**로 지킨다. 두 파일의 「밝기」 구획을 잘라 node(또는 bun)로
가짜 `localStorage` · `matchMedia` · `document` 위에서 돌린다. 둘 다 없는 PC 는 건너뛰고, GitHub
Actions 에서는 실패한다(`test_intro_scene_behavior` 와 같은 규칙).

예시판은 촬영 그림을 틀의 데이터 자리에 넣은 것이므로 데이터 자리 밖은 틀과 글자 하나까지 같아야
한다 — 틀만 고치고 예시판을 다시 조립하지 않으면 사외 화면의 Guide 창이 옛 틀로 돈다.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from capa_simulation.components.theme_toggle import THEME_APP_KEY

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import page_guide_core as core  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = PROJECT_ROOT / "src" / "capa_simulation" / "guides" / "howto" / "template.html"
EXAMPLE_BOARD = PROJECT_ROOT / "static" / "guides" / "howto" / "lob.html"
BOARDS = {"틀": TEMPLATE, "예시판": EXAMPLE_BOARD}
# 「밝기」 구획 — 다음 구획 머리 줄 앞까지.
THEME_SECTION = re.compile(r"^  // -+ 밝기:[^\n]*\n(?P<body>.*?)^  // -+ ", re.S | re.M)

# 가짜 창 위에서 「밝기」 구획을 돌린다. 경우마다 (처음 단 값, storage 이벤트 뒤 값)을 낸다.
_RUNNER = r"""
const fs = require("fs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const out = [];
for (const c of input.cases) {
  let stored = c.stored;
  const handlers = {};
  const root = { dataset: {} };
  const fake = {
    document: { documentElement: root },
    localStorage: { getItem: (key) => (key === input.key ? stored : null) },
    matchMedia: () => ({ matches: c.osDark }),
    addEventListener: (type, handler) => { handlers[type] = handler; },
    $: () => ({}),
  };
  new Function(...Object.keys(fake), input.body)(...Object.values(fake));
  const first = root.dataset.theme;
  stored = c.next;
  handlers.storage({ key: "다른 키" });
  const untouched = root.dataset.theme;
  handlers.storage({ key: input.key });
  out.push([first, untouched, root.dataset.theme]);
}
process.stdout.write(JSON.stringify(out));
"""

# (저장된 값, OS 가 어두운가, storage 이벤트 뒤 값) → (처음, 이벤트 뒤)
CASES: list[tuple[str | None, bool, str | None, str, str]] = [
    ("Dark", False, "Light", "dark", "light"),
    ("dark", False, "Light", "dark", "light"),
    ("Light", True, "Dark", "light", "dark"),
    ("light", True, "dark", "light", "dark"),
    ("DARK", False, None, "dark", "light"),
    (None, True, "Light", "dark", "light"),
    (None, False, "Dark", "light", "dark"),
    ("System", True, None, "dark", "dark"),
]


def _runtime() -> str | None:
    return shutil.which("node") or shutil.which("bun")


def _theme_section(path: Path) -> str:
    match = THEME_SECTION.search(path.read_text(encoding="utf-8"))
    assert match, f"{path.name} 에 「밝기」 구획이 없습니다"
    return match.group("body")


def _run(body: str) -> list[list[str]]:
    runtime = _runtime()
    if runtime is None:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            pytest.fail("CI 러너에 node 가 없다 — 가이드 밝기 동작 검사를 건너뛸 수 없다")
        pytest.skip("node·bun 이 없다 — CI 에서 돈다")
    cases = [{"stored": stored, "osDark": dark, "next": nxt} for stored, dark, nxt, _, _ in CASES]
    completed = subprocess.run(
        [runtime, "-e", _RUNNER],
        input=json.dumps({"key": THEME_APP_KEY, "body": body, "cases": cases}),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result: list[list[str]] = json.loads(completed.stdout)
    return result


@pytest.mark.parametrize("board", sorted(BOARDS))
def test_guide_window_follows_the_app_theme_whatever_the_letter_case(board: str) -> None:
    """앱이 적는 "Dark"·"Light" 도, 소문자 "dark"·"light" 도 같은 밝기로 받는다. 값이 없거나 모르는
    값이면 OS 설정을 따르고, 앱 창이 테마를 바꾸면(같은 키의 storage 이벤트) 따라온다."""
    results = _run(_theme_section(BOARDS[board]))

    expected = [[first, first, after] for _, _, _, first, after in CASES]
    assert results == expected


def test_the_example_board_is_assembled_from_the_current_template() -> None:
    """예시판에서 데이터 자리를 걷어 내면 틀과 같다. 틀을 고쳤으면 예시판을 다시 조립한다
    (`scripts/build_page_guide.py --example --assemble-only`, 작업 폴더가 없으면 촬영부터)."""
    template = TEMPLATE.read_text(encoding="utf-8")
    board = EXAMPLE_BOARD.read_text(encoding="utf-8")
    head, tail = template.split(core.DATA_SLOT)

    assert board.startswith(head), "예시판의 데이터 자리 앞이 틀과 다릅니다 — 다시 조립합니다"
    assert board.endswith(tail), "예시판의 데이터 자리 뒤가 틀과 다릅니다 — 다시 조립합니다"
    assert _theme_section(EXAMPLE_BOARD) == _theme_section(TEMPLATE)
