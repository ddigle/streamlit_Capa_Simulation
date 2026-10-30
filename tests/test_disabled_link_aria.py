# Purpose: 꺼진 화면 링크에 aria-disabled 를 다는 툴바 스크립트를 node 가짜 문서에서 검증한다.

"""꺼진 화면 링크의 `aria-disabled`.

Streamlit 1.63 은 `st.page_link(disabled=True)` 를 `<a disabled>` 로 그린다 — `<a>` 의 `disabled` 는
HTML 속성이 아니어서 읽기 도구가 꺼졌다고 읽지 않았다(공정 Capa 상세 「이 공정 제약 시뮬레이션」 —
E2E r3 #115, 개선 거리 I14). 툴바 iframe 의 스크립트(`page_link.disabled_link_aria_script`)가 부모
문서의 그 링크에 `aria-disabled="true"` 를 달고, 다시 켜지면 뗀다. 스크립트를 글자 그대로 node 에서
가짜 부모 문서로 돌린다(node 가 없으면 건너뛰고 CI 에서는 실패 — `test_space_module_group._node`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from test_space_module_group import _node

from capa_simulation.components.page_link import (
    DISABLED_LINK_ARIA_HANDLER,
    disabled_link_aria_script,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const SELECTOR = 'a[data-testid="stPageLink-NavLink"]'
function element(tag, attrs, children) {
  const node = {
    nodeType: 1,
    namespaceURI: tag === 'svg' ? 'http://www.w3.org/2000/svg' : 'http://www.w3.org/1999/xhtml',
    tag,
    attrs: Object.assign({}, attrs || {}),
    children: children || [],
    hasAttribute(name) { return Object.prototype.hasOwnProperty.call(this.attrs, name) },
    getAttribute(name) { return this.hasAttribute(name) ? this.attrs[name] : null },
    setAttribute(name, value) { this.attrs[name] = String(value) },
    removeAttribute(name) { delete this.attrs[name] },
    matches(selector) {
      if (selector !== SELECTOR) throw new Error('모르는 선택자 ' + selector)
      return this.tag === 'a' && this.attrs['data-testid'] === 'stPageLink-NavLink'
    },
    querySelectorAll(selector) {
      const found = []
      const walk = (item) => item.children.forEach((child) => {
        if (child.matches(selector)) found.push(child)
        walk(child)
      })
      walk(this)
      return found
    },
  }
  return node
}
function link(id, disabled) {
  const attrs = { 'data-testid': 'stPageLink-NavLink', id }
  if (disabled) attrs.disabled = ''
  return element('a', attrs)
}
const observers = []
class FakeObserver {
  constructor(callback) {
    this.callback = callback
    this.options = null
    this.connected = false
    observers.push(this)
  }
  observe(target, options) { this.target = target; this.options = options; this.connected = true }
  disconnect() { this.connected = false }
}
const off = link('off', true)
const on = link('on', false)
const plot = element('svg', {}, [link('in-svg', true)])
const body = element('body', {}, [element('div', {}, [off, on]), plot])
const parent = { document: { body }, MutationObserver: FakeObserver }
const run = new Function('window', input.script)
const aria = (node) => node.getAttribute('aria-disabled')
run({ parent })
const first = observers[0]
const out = { initial: { off: aria(off), on: aria(on) }, options: first.options }
// 켜진 링크를 끈다 · 꺼진 링크를 켠다 — React 가 `disabled` 를 바꾼 기록.
on.setAttribute('disabled', '')
off.removeAttribute('disabled')
first.callback([{ type: 'attributes', target: on }, { type: 'attributes', target: off }])
out.flipped = { off: aria(off), on: aria(on) }
// 새로 붙은 칸 안의 꺼진 링크, 그림(SVG) 안은 보지 않는다.
const later = link('later', true)
const svgLink = link('svg-later', true)
const svg = element('svg', {}, [svgLink])
const added = [element('div', {}, [later]), svg, { nodeType: 3 }]
first.callback([{ type: 'childList', addedNodes: added }])
out.added = { later: aria(later), svg: aria(svgLink) }
// iframe 이 다시 만들어지면 옛 듣개를 떼고 새로 단다.
run({ parent })
out.rerun = {
  firstConnected: first.connected,
  count: observers.length,
  handler: parent[input.handler] === observers[1],
}
process.stdout.write(JSON.stringify(out))
"""


def _run() -> dict[str, Any]:
    return _node(
        _RUNNER,
        {"script": disabled_link_aria_script(), "handler": DISABLED_LINK_ARIA_HANDLER},
    )


def test_a_disabled_page_link_is_announced_as_disabled() -> None:
    result = _run()

    assert result["initial"] == {"off": "true", "on": None}
    assert result["options"] == {
        "subtree": True,
        "childList": True,
        "attributes": True,
        "attributeFilter": ["disabled"],
    }


def test_the_mark_follows_the_link_when_it_is_switched() -> None:
    result = _run()

    assert result["flipped"] == {"off": None, "on": "true"}
    assert result["added"] == {"later": "true", "svg": None}


def test_a_recreated_frame_replaces_the_old_observer() -> None:
    assert _run()["rerun"] == {"firstConnected": False, "count": 2, "handler": True}


def test_the_toolbar_frame_carries_the_script() -> None:
    """`app.py` 가 테마 버튼 iframe 에 싣는다 — 빠지면 꺼진 링크가 다시 꺼졌다고 읽히지 않는다."""
    source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")

    assert "disabled_link_aria_script()," in source
