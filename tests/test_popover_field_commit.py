# Purpose: 팝오버 글 칸 Esc 확정 스크립트의 대상 · 듣는 단계 · 듣개 교체 계약을 고정한다.

"""팝오버 글 칸의 Esc 확정(`components/popover_field_commit.py`).

AppTest 는 브라우저 포커스도 부모 창의 듣개도 돌리지 못한다. 가짜 부모 창 위에서 스크립트를 돌려
대상 · 듣는 단계를 보고, 실제 저장까지 이어지는지는 사본 앱을 브라우저로 잰다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from js_runner import run_js_json

from capa_simulation.components.popover_field_commit import (
    ESC_COMMIT_PREFIX,
    HANDLER_NAME,
    popover_field_commit_script,
)

SCRIPT = popover_field_commit_script()
ROOT = Path(__file__).resolve().parents[1]

_RUNNER = """
const listeners = []
const parent = {
  addEventListener: (name, fn, capture) => listeners.push({ name, fn, capture }),
  removeEventListener: (name, fn) => {
    const at = listeners.findIndex((item) => item.name === name && item.fn === fn)
    if (at >= 0) listeners.splice(at, 1)
  },
}
const window = { parent }
const field = (matched) => {
  const node = { blurred: 0, blur() { this.blurred += 1 } }
  node.matches = (selector) => matched && selector.includes('st-key-%(prefix)s')
  return node
}
const script = %(script)s
const run = () => new Function('window', script)(window)
run()
const key = (name, target) => listeners.forEach((item) => item.fn({ key: name, target }))
const inside = field(true)
const outside = field(false)
key('Escape', inside)
key('Enter', inside)
key('Escape', outside)
key('Escape', null)
key('Escape', {})
const first = listeners.slice()
run()
process.stdout.write(JSON.stringify({
  inside: inside.blurred,
  outside: outside.blurred,
  count: listeners.length,
  name: listeners[0].name,
  capture: listeners[0].capture,
  replaced: first[0].fn !== listeners[0].fn,
  installed: typeof parent.%(handler)s,
}))
"""


def _run() -> dict[str, Any]:
    source = _RUNNER % {
        "prefix": ESC_COMMIT_PREFIX,
        "handler": HANDLER_NAME,
        "script": json.dumps(SCRIPT),
    }
    result: dict[str, Any] = run_js_json(source, what="팝오버 글 칸 Esc 확정 시험")
    return result


def test_escape_blurs_only_a_field_in_a_marked_box_before_streamlit_closes_the_popover() -> None:
    """Streamlit 팝오버는 `document` capture 에서 Esc 를 듣는다 — 창 capture 라야 등록 차례와
    상관없이 앞선다. 다른 키 · 표시 없는 칸은 건드리지 않는다."""
    result = _run()
    assert result["inside"] == 1
    assert result["outside"] == 0
    assert result["name"] == "keydown"
    assert result["capture"] is True


def test_a_rebuilt_iframe_replaces_the_old_listener() -> None:
    result = _run()
    assert result["count"] == 1
    assert result["replaced"] is True
    assert result["installed"] == "function"


def test_the_script_is_one_fixed_string() -> None:
    assert popover_field_commit_script() == SCRIPT
    assert "%(" not in SCRIPT
    assert f'[class*="st-key-{ESC_COMMIT_PREFIX}"]' in SCRIPT


def test_the_app_loads_the_script_with_the_other_toolbar_scripts() -> None:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    start = source.index("render_theme_toggle(")
    assert "popover_field_commit_script()," in source[start : source.index("\n)\n", start)]
