# Purpose: 범용 편집 그리드 JS 의 순수 구획을 떼어 node(없으면 bun)로 돌리는 시험 도우미다.

"""AppTest 는 그리드 JS 를 돌리지 못한다. DOM 을 모르는 순수 구획(`// <eg-…>` ~ `// </eg-…>`)을 자산
파일에서 떼어 이어 붙이고 러너 글을 뒤에 붙여 `js_runner` 로 돌린다(설비 마스터 표 자산 시험 꼴).
입력은 표준 입력 JSON 이다.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from js_runner import need_js_runtime, run_js_json

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


def run_node(source: str, runner: str, payload: object) -> Any:
    """`source` 뒤에 `runner` 를 붙여 돌리고 표준 출력 JSON 을 돌려준다(`.cjs` — CommonJS)."""
    return run_js_json(
        source + "\n" + runner,
        what="편집 그리드 JS 대조",
        stdin=json.dumps(payload),
        timeout=120,
    )


def check_module(source: str) -> subprocess.CompletedProcess[str]:
    """ES 모듈 글을 node `--check` 로 읽힌다(문법만)."""
    node = need_js_runtime("편집 그리드 JS 대조")
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


# 작은 가짜 DOM — 그리드 core 를 통째로 마운트해 키·붙여넣기·feed 받기·출납 보내기를 돌린다(기능
# 가지도 쓴다). window 는 node 의 EventTarget 이라 `CustomEvent` 가 그대로 간다. 좌표는 표 칸 왼쪽
# 위가 (0, 0)·스크롤 칸 1000×600 이다.
FAKE_DOM = r"""
class FakeStyle {
  constructor() {
    this.vars = {}
  }
  setProperty(name, value) {
    this.vars[name] = String(value)
  }
  getPropertyValue(name) {
    return this.vars[name] || ''
  }
}
class FakeClassList {
  constructor(node) {
    this.node = node
  }
  list() {
    return this.node.className.split(/\s+/).filter(Boolean)
  }
  add(...names) {
    const set = new Set(this.list())
    names.forEach((name) => set.add(name))
    this.node.className = Array.from(set).join(' ')
  }
  remove(...names) {
    this.node.className = this.list().filter((name) => !names.includes(name)).join(' ')
  }
  contains(name) {
    return this.list().includes(name)
  }
  toggle(name, on) {
    const want = on === undefined ? !this.contains(name) : on
    if (want) this.add(name)
    else this.remove(name)
    return want
  }
}
const camel = (text) => text.replace(/-([a-z])/g, (match, letter) => letter.toUpperCase())
class FakeNode {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase()
    this.children = []
    this.parentNode = null
    this.attributes = {}
    this.dataset = {}
    this.listeners = {}
    this.style = new FakeStyle()
    this.className = ''
    this.classList = new FakeClassList(this)
    this.hidden = false
    this.ownText = ''
    this.id = ''
    this.value = ''
    this.scrollTop = 0
    this.scrollLeft = 0
    this.clientWidth = 1000
    this.clientHeight = 600
    this.clientLeft = 0
    this.clientTop = 0
    this.offsetHeight = 24
  }
  appendChild(child) {
    if (child.tagName === '#FRAGMENT') {
      for (const item of child.children.slice()) this.appendChild(item)
      child.children = []
      return child
    }
    const old = child.parentNode
    if (old) old.children = old.children.filter((item) => item !== child)
    child.parentNode = this
    this.children.push(child)
    return child
  }
  get textContent() {
    return this.ownText + this.children.map((child) => child.textContent).join('')
  }
  set textContent(value) {
    for (const child of this.children) child.parentNode = null
    this.children = []
    this.ownText = String(value)
  }
  setAttribute(name, value) {
    this.attributes[name] = String(value)
  }
  getAttribute(name) {
    return name in this.attributes ? this.attributes[name] : null
  }
  removeAttribute(name) {
    delete this.attributes[name]
  }
  addEventListener(type, handler) {
    ;(this.listeners[type] = this.listeners[type] || []).push(handler)
  }
  removeEventListener(type, handler) {
    this.listeners[type] = (this.listeners[type] || []).filter((item) => item !== handler)
  }
  contains(node) {
    for (let at = node; at; at = at.parentNode) if (at === this) return true
    return false
  }
  getRootNode() {
    return FAKE_ROOT
  }
  getBoundingClientRect() {
    const width = this.clientWidth
    const height = this.clientHeight
    return { left: 0, top: 0, right: width, bottom: height, width, height }
  }
  focus() {
    document.activeElement = this
  }
  setSelectionRange(start, end) {
    this.selection = [start, end]
  }
  matches(selector) {
    return selector.split(',').some((part) => {
      const text = part.trim()
      const attr = text.match(/^\[([a-z-]+)(?:="([^"]*)")?\]$/)
      if (attr) {
        const name = attr[1]
        const want = attr[2]
        const data = name.startsWith('data-') ? this.dataset[camel(name.slice(5))] : undefined
        const value = name in this.attributes ? this.attributes[name] : data
        if (value === undefined) return false
        return want === undefined || String(value) === want
      }
      const names = text.startsWith('.') ? text.slice(1).split('.') : null
      if (names) return names.every((name) => this.classList.contains(name))
      return this.tagName === text.toUpperCase()
    })
  }
  closest(selector) {
    for (let at = this; at; at = at.parentNode) if (at.matches && at.matches(selector)) return at
    return null
  }
  querySelectorAll(selector) {
    const found = []
    const walk = (node) => {
      for (const child of node.children) {
        if (child.matches(selector)) found.push(child)
        walk(child)
      }
    }
    walk(this)
    return found
  }
  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null
  }
}
const FAKE_ROOT = { host: null, activeElement: null }
function fire(target, type, extra) {
  const event = Object.assign({
    type, target, stopped: false, defaultPrevented: false, key: '', ctrlKey: false,
    metaKey: false, shiftKey: false, altKey: false, isComposing: false, button: 0,
    clientX: 0, clientY: 0,
    stopPropagation() {
      this.stopped = true
    },
    preventDefault() {
      this.defaultPrevented = true
    },
  }, extra || {})
  for (let at = target; at && !event.stopped; at = at.parentNode) {
    for (const handler of (at.listeners[type] || []).slice()) handler.call(at, event)
  }
  return event
}
const fakeWindow = new EventTarget()
fakeWindow.innerHeight = 950
fakeWindow.scrollY = 0
globalThis.window = fakeWindow
globalThis.document = {
  activeElement: null,
  createElement: (tag) => new FakeNode(tag),
  createDocumentFragment: () => new FakeNode('#fragment'),
  getSelection: () => ({ rangeCount: 0, removeAllRanges() {} }),
  addEventListener() {},
  removeEventListener() {},
}
globalThis.requestAnimationFrame = (run) => setTimeout(run, 0)
globalThis.cancelAnimationFrame = (handle) => clearTimeout(handle)
const tick = (ms) => new Promise((resolve) => setTimeout(resolve, ms || 0))
"""


def mountable(registered_js: str) -> str:
    """등록 JS 의 `export default function` 을 전역 `__mount` 로 바꾼 글(CommonJS 로 돌린다)."""
    head = "export default function (component) {"
    assert registered_js.count(head) == 1
    return registered_js.replace(head, "globalThis.__mount = function (component) {")
