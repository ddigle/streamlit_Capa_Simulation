# Purpose: HOME 칸 그림 둘째 누름 거름 스크립트의 판정 구획을 node 로, 듣개 계약을 글자로 고정한다.

"""HOME 칸 그림의 둘째 누름 거름(`components/cell_press_guard.py`).

칸을 사람 속도로 더블클릭하면(0.08~0.15초) 둘째 누름이 떠나는 HOME 프래그먼트의 회차를 청해,
옮긴 공정 Capa 상세 본문이 빈 채 남았다(2026-10-27 E2E). AppTest 는 프래그먼트 회차와 화면
옮기기의 경합도, 부모 문서의 듣개도 돌리지 못한다 — DOM 을 모르는 판정
구획(`// <cell-press-hold>`)은 node(없으면 bun)로 떼어 돌리고, 듣개 계약은 글자로 붙잡는다.
브라우저 동작은 사본 앱으로 본다.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from typing import Any

import pytest

from capa_simulation.components.cell_press_guard import (
    HANDLER_NAME,
    HELD_EVENTS,
    HOLD_MAX_MS,
    HOLD_MIN_MS,
    cell_press_guard_script,
)
from capa_simulation.components.home_rendering import HOME_CELL_CHART_KEYS
from capa_simulation.components.plotly_touch_scroll import touch_scroll_selector

SCRIPT = cell_press_guard_script(HOME_CELL_CHART_KEYS)


def _node(runner: str) -> Any:
    match = re.search(r"// <cell-press-hold>\n(?P<body>.*?)\n// </cell-press-hold>", SCRIPT, re.S)
    assert match, "cell_press_guard 스크립트에 // <cell-press-hold> 구획이 없습니다"
    runtime = shutil.which("node") or shutil.which("bun")
    if runtime is None:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            pytest.fail("CI 러너에 node 가 없다 — 칸 누름 거름 JS 구획 시험을 건너뛸 수 없다")
        pytest.skip("node·bun 이 없다 — CI 에서 돈다")
    completed = subprocess.run(
        [runtime, "-e", match.group("body") + "\n" + runner],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


_HOLD_RUNNER = f"""
const MIN = {HOLD_MIN_MS}
const MAX = {HOLD_MAX_MS}
const out = {{}}
// 첫 누름 — 앞 누름이 없으니 지나간다(그 누름이 창을 연다).
out.first = pressHeld(null, 1000, false, MIN, MAX)
// 사람 더블클릭 — 0.08~0.15초 뒤 둘째 누름. 회차가 서기 전이라도 거른다.
out.double = [80, 120, 150].map((gap) => pressHeld(1000, 1000 + gap, false, MIN, MAX))
// 옮기는 회차·옮긴 화면 회차가 도는 동안은 창 밖이라도 거른다.
out.running = [pressHeld(1000, 1600, true, MIN, MAX), pressHeld(1000, 4000, true, MIN, MAX)]
// 회차가 끝났고 창이 지났다(옮기지 않은 누름 — 과거 칸) — 다음 누름은 지나간다.
out.settled = pressHeld(1000, 1000 + MIN, false, MIN, MAX)
// 회차가 끝없이 돌아도 기다림 끝을 넘지 않는다.
out.capped = pressHeld(1000, 1000 + MAX, true, MIN, MAX)
// 시계가 뒤로 간 것은 거르지 않는다.
out.backwards = pressHeld(1000, 900, true, MIN, MAX)
process.stdout.write(JSON.stringify(out))
"""


def test_a_second_press_while_the_first_cell_press_moves_the_page_is_held() -> None:
    """첫 누름 뒤 `HOLD_MIN_MS` 안, 그리고 앱 회차가 도는 동안 온 누름은 거른다 — 그 누름이 떠나는
    HOME 프래그먼트 회차를 청해 옮긴 화면 본문을 비웠다. 회차가 끝나고 창이 지나면 다시 받는다."""
    out = _node(_HOLD_RUNNER)

    assert out["first"] is False
    assert out["double"] == [True, True, True]
    assert out["running"] == [True, True]
    assert out["settled"] is False
    assert out["capped"] is False
    assert out["backwards"] is False


def test_the_guard_holds_only_presses_on_the_home_cell_charts_and_never_the_first_release() -> None:
    """HOME 세 월 그림만 고른다. 거르는 것은 누름(`pointerdown`·`mousedown`·`dblclick`)뿐이다 —
    첫 누름의 `mouseup` 을 막으면 Plotly 가 클릭을 끝내지 못해 첫 칸도 열리지 않는다. 창은 지나간
    `mousedown` 이 연다(그보다 앞선 `pointerdown` 이 열면 같은 누름의 `mousedown` 이 걸린다)."""
    assert json.dumps(touch_scroll_selector(HOME_CELL_CHART_KEYS)) in SCRIPT
    for key in HOME_CELL_CHART_KEYS:
        assert f".st-key-{key} .js-plotly-plot" in SCRIPT
    assert HELD_EVENTS == ("pointerdown", "mousedown", "dblclick")
    assert json.dumps(list(HELD_EVENTS)) in SCRIPT
    assert "mouseup" not in json.dumps(list(HELD_EVENTS))
    assert "click" not in [event for event in HELD_EVENTS]
    assert 'if (event.type === "mousedown") armedAt = now;' in SCRIPT
    held = SCRIPT.index("if (pressHeld(armedAt, now, running(),")
    assert held < SCRIPT.index("event.stopPropagation();") < SCRIPT.index("armedAt = now;")
    # 회차 표지는 Streamlit 뿌리의 1.63 프런트 속성이다(탭 줄 `<tabs-queue>` 와 같은 읽기).
    assert 'getAttribute("data-test-script-state")' in SCRIPT
    assert 'run === "running" || run === "rerunRequested"' in SCRIPT
    # 기본 동작은 막지 않는다 — 터치 스크롤·포커스는 그대로다.
    assert ".preventDefault(" not in SCRIPT
    assert "%(" not in SCRIPT


def test_a_recreated_iframe_replaces_its_old_listeners() -> None:
    """iframe 이 다시 만들어지면 옛 iframe 의 함수는 브라우저가 부르지 않는다 — 창에 남긴 옛 듣개를
    모든 사건에서 떼고 새로 단다."""
    remove = f"var previous = parentWindow.{HANDLER_NAME};"
    assert remove in SCRIPT
    assert "doc.removeEventListener(events[index], previous, true);" in SCRIPT
    assert SCRIPT.index(remove) < SCRIPT.index("doc.addEventListener(events[index], guard, true);")
    assert f"parentWindow.{HANDLER_NAME} = guard;" in SCRIPT


def test_the_script_is_the_same_text_on_every_run() -> None:
    """테마 버튼 iframe 내용은 회차마다 같아야 한다 — 바뀌면 iframe 을 새로 만든다."""
    assert cell_press_guard_script(HOME_CELL_CHART_KEYS) == cell_press_guard_script(
        list(HOME_CELL_CHART_KEYS)
    )
