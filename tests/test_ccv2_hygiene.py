# Purpose: Components v2 부품의 누수 위생(등록은 모듈 머리 · 마운트마다 key · 바뀌는 key 없음 · 다시
# 불러도 처리기 한 번)을 정적으로, default export 50번 다시 부르기를 node 로 검사한다.

"""Components v2 위생(AGENTS 9장 「구역 회차 규칙」 R7 — 누수 기제).

- **등록은 모듈 머리에서 한 번** — `st.components.v2.component(…)` 는 모듈을 읽을 때 한 번만 부른다.
  등록 글(`js=` · `css=` · `html=`)이 프로세스 동안 같아야 한다 — 글이 바뀌면 브라우저가 글 해시마다
  blob URL 을 만들고 걷지 않는다. 함수 안에서 등록하면 회차마다 글이 달라질 수 있다.
- **마운트마다 `key=`** — key 없는 부품은 data 가 위젯 id 에 들어 편집마다 위젯 메타가
  늘고(`widget_metadata` 는 줄지 않는다) 콜백 클로저를 쥔다.
- **바뀌는 key 없음** — 부품 · 편집표 key 에 회차마다 바뀌는 값(seq · 시각 · 난수)을 넣지 않는다 —
  key 수만큼 `_key_id_mapper` 가 쌓인다.
- **다시 불러도 처리기 한 번(bind-once)** — CCv2 는 data 가 바뀔 때마다 default export 를 다시
  부르고 앞 호출의 정리 함수는 부르지 않는다. 문서 · 창 · 칸 처리기와 관찰자는 처음 한 번만
  단다(`S.bound` 꼴). node 로 등록 글을 그대로 50번 부르며 살아 있는 처리기 · 관찰자 수와, 스스로
  다시 거는 확인 고리 · 되풀이 타이머 수를 센다(부를 때마다 걸린 한 번짜리 타이머를 한 번씩 돌려
  끝난 것은 걷는다) — DOM 은 느슨한 대역(모르는 속성은 아무 일도 하지 않는 함수)이다. 새 부품은
  `BIND_ONCE` 에 한 줄을 더한다.
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from js_runner import run_js_json

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ("st", "components", "v2", "component")
# 회차마다 바뀌는 값의 이름 — 부품 · 편집표 key 식에 이 이름이 들면 거절한다.
VOLATILE = re.compile(r"(^|_)(seq|now|time|timestamp|stamp|uuid|random|counter|nonce)($|_)", re.I)


def _source_files() -> list[Path]:
    return sorted(
        [*(ROOT / "src").rglob("*.py"), *(ROOT / "app_pages").glob("*.py"), ROOT / "app.py"]
    )


def _dotted(node: ast.AST) -> tuple[str, ...]:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return tuple(reversed(parts))


def _is_register(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and _dotted(node.func)[-4:] == REGISTER


def _registrations() -> dict[str, tuple[ast.Module, set[str], list[ast.Call]]]:
    """파일 → (구문 나무, 등록을 받은 이름, 모든 등록 호출)."""
    found: dict[str, tuple[ast.Module, set[str], list[ast.Call]]] = {}
    for path in _source_files():
        text = path.read_text(encoding="utf-8")
        if "components.v2.component(" not in text:
            continue
        tree = ast.parse(text)
        names: set[str] = set()
        calls = [
            node for node in ast.walk(tree) if isinstance(node, ast.Call) and _is_register(node)
        ]
        for statement in tree.body:
            if isinstance(statement, ast.Assign) and _is_register(statement.value):
                names.update(t.id for t in statement.targets if isinstance(t, ast.Name))
        found[path.relative_to(ROOT).as_posix()] = (tree, names, calls)
    return found


def test_components_are_registered_once_at_module_level() -> None:
    """등록은 모듈 머리의 대입 한 줄이다 — 함수 안 등록이 없어 등록 글(`js=` 등)이 프로세스 동안
    같다."""
    offenders: list[str] = []
    for rel, (tree, names, calls) in _registrations().items():
        top = {
            id(statement.value)
            for statement in tree.body
            if isinstance(statement, ast.Assign) and _is_register(statement.value)
        }
        offenders.extend(f"{rel}:{call.lineno}" for call in calls if id(call) not in top)
        assert names, rel
    assert not offenders, offenders


def _mount_calls(tree: ast.Module, names: set[str]) -> list[ast.Call]:
    """등록 이름(또는 그 이름을 고른 지역 이름 — `grid = _GRID_ROWS if … else _GRID`)을 부르는
    마운트."""
    aliases = set(names)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.IfExp):
            picked = {_dotted(node.value.body), _dotted(node.value.orelse)}
            if all(len(item) == 1 and item[0] in names for item in picked):
                aliases.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in aliases
        and not _is_register(node)
    ]


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next((kw.value for kw in call.keywords if kw.arg == name), None)


def _volatile_names(expression: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(expression):
        if isinstance(node, ast.Name) and VOLATILE.search(node.id):
            names.append(node.id)
        elif isinstance(node, ast.Attribute) and VOLATILE.search(node.attr):
            names.append(node.attr)
        elif isinstance(node, ast.Call) and _dotted(node.func)[-1:] in {("time",), ("uuid4",)}:
            names.append(".".join(_dotted(node.func)))
    return names


def test_every_component_mount_carries_a_key() -> None:
    """모든 Components v2 마운트는 `key=` 를 준다 — key 없는 부품은 data 가 위젯 id 에 들어 편집마다
    위젯 메타가 늘고 콜백 클로저를 쥔다."""
    missing: list[str] = []
    counted = 0
    for rel, (tree, names, _calls) in _registrations().items():
        for call in _mount_calls(tree, names):
            counted += 1
            if _keyword(call, "key") is None:
                missing.append(f"{rel}:{call.lineno}")
    assert counted >= len(_registrations()), "마운트를 하나도 못 찾은 등록이 있다"
    assert not missing, missing


def _editor_keys() -> list[tuple[str, int, ast.expr]]:
    """부품 마운트와 편집표(`st.data_editor`)의 key 식."""
    found: list[tuple[str, int, ast.expr]] = []
    for rel, (tree, names, _calls) in _registrations().items():
        for call in _mount_calls(tree, names):
            key = _keyword(call, "key")
            if key is not None:
                found.append((rel, call.lineno, key))
    for path in _source_files():
        text = path.read_text(encoding="utf-8")
        if "data_editor(" not in text:
            continue
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Call) and _dotted(node.func)[-1:] == ("data_editor",):
                key = _keyword(node, "key")
                if key is not None:
                    found.append((path.relative_to(ROOT).as_posix(), node.lineno, key))
    return found


def test_component_and_editor_keys_hold_no_changing_values() -> None:
    """부품 · 편집표 key 에 회차마다 바뀌는 값(seq · 시각 · 난수)을 넣지 않는다 — 서로 다른 key 마다
    `_key_id_mapper` 가 쌓인다."""
    keys = _editor_keys()
    offenders = [(rel, line, names) for rel, line, key in keys if (names := _volatile_names(key))]
    assert keys
    assert not offenders, offenders


# ------------------------------------------------------------------ bind-once(node)

# 느슨한 DOM 대역 — 모르는 속성은 아무 일도 하지 않는 함수(부르면 또 대역)이고, 이어 걷는 속성(부모
# · 이웃 · closest)은 null, 수 · 참거짓 · 글은 0 · false · '' 이다. 자식은 단 차례로 남는다. 칸에 단
# 값(`host.__state` 꼴)은 그대로 남아 다시 부른 default export 가 같은 상태를 읽고, 달기 전의 `__`
# 이름은 없다. `querySelector` 는 선택자마다 같은 칸을 돌려준다. 처리기(`addEventListener`)와
# 관찰자(`observe`)는 살아 있는 것만 센다.
_HARNESS = r"""
const live = new Map()
let observing = 0
const ids = new WeakMap()
let nextId = 0
const registry = (fn) => {
  if (!ids.has(fn)) ids.set(fn, ++nextId)
  return ids.get(fn)
}
const captured = (options) =>
  typeof options === 'boolean' ? options : Boolean(options && options.capture)
const listen = (target) => ({
  addEventListener(type, fn, options) {
    if (typeof fn !== 'function') return
    let byTarget = live.get(target)
    if (!byTarget) live.set(target, (byTarget = new Set()))
    byTarget.add(type + '|' + captured(options) + '|' + registry(fn))
  },
  removeEventListener(type, fn, options) {
    const byTarget = live.get(target)
    if (byTarget) byTarget.delete(type + '|' + captured(options) + '|' + registry(fn))
  },
})
const listeners = () => [...live.values()].reduce((sum, set) => sum + set.size, 0)
const NULLISH = new Set([
  'parentNode', 'parentElement', 'nextSibling', 'nextElementSibling', 'previousSibling',
  'previousElementSibling', 'offsetParent', 'host', 'activeElement', 'ownerSVGElement',
  'shadowRoot',
])
const ZERO = new Set([
  'offsetLeft', 'offsetTop', 'offsetWidth', 'offsetHeight', 'scrollLeft', 'scrollTop',
  'scrollWidth', 'scrollHeight', 'clientWidth', 'clientHeight', 'length', 'size',
  'childElementCount', 'selectionStart', 'selectionEnd', 'devicePixelRatio', 'innerWidth',
  'innerHeight', 'nodeType',
])
const FALSE = new Set(['hidden', 'disabled', 'checked', 'open', 'defaultPrevented'])
const EMPTY = new Set([
  'textContent', 'innerHTML', 'innerText', 'className', 'id', 'tagName', 'value', 'nodeName',
  'href', 'search', 'hash',
])
const RECT = { left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0, x: 0, y: 0 }
const element = (label) => {
  const store = new Map()
  const cache = new Map()
  const kids = []
  let self = null
  const add = (...nodes) => {
    for (const node of nodes) {
      if (node !== null && (typeof node === 'object' || typeof node === 'function')) kids.push(node)
    }
  }
  const dynamic = {
    firstChild: () => kids[0] || null,
    firstElementChild: () => kids[0] || null,
    lastChild: () => kids[kids.length - 1] || null,
    lastElementChild: () => kids[kids.length - 1] || null,
    children: () => kids,
    childNodes: () => kids,
  }
  const fixed = {
    append: add,
    appendChild: (node) => {
      add(node)
      return node
    },
    prepend: add,
    insertBefore: (node) => {
      add(node)
      return node
    },
    replaceChildren: (...nodes) => {
      kids.length = 0
      add(...nodes)
    },
    addEventListener: (...args) => listen(self).addEventListener(...args),
    removeEventListener: (...args) => listen(self).removeEventListener(...args),
    querySelector: (selector) => {
      const name = 'q:' + selector
      if (!cache.has(name)) cache.set(name, element(selector))
      return cache.get(name)
    },
    querySelectorAll: () => [],
    closest: () => null,
    contains: () => false,
    matches: () => false,
    getAttribute: () => null,
    hasAttribute: () => false,
    getAttributeNames: () => [],
    getBoundingClientRect: () => ({ ...RECT }),
    getRootNode: () => self,
    attachShadow: () => element(label + ':shadow'),
    cloneNode: () => element(label + ':clone'),
    isConnected: true,
    dataset: {},
  }
  self = new Proxy(function () {}, {
    get(target, prop) {
      if (store.has(prop)) return store.get(prop)
      if (Object.prototype.hasOwnProperty.call(fixed, prop)) return fixed[prop]
      if (Object.prototype.hasOwnProperty.call(dynamic, prop)) return dynamic[prop]()
      if (typeof prop === 'symbol') {
        if (prop === Symbol.iterator) return function* () {}
        if (prop === Symbol.toPrimitive) return () => 0
        return undefined
      }
      // 칸에 다는 상태(`host.__state` 꼴)는 달기 전에는 없다 — 새 상태를 세운다.
      if (prop === 'then' || prop === 'toJSON' || prop.startsWith('__')) return undefined
      if (NULLISH.has(prop)) return null
      if (ZERO.has(prop)) return 0
      if (FALSE.has(prop)) return false
      if (EMPTY.has(prop)) return ''
      if (!cache.has(prop)) cache.set(prop, element(label + '.' + String(prop)))
      return cache.get(prop)
    },
    set(target, prop, value) {
      store.set(prop, value)
      return true
    },
    apply() {
      return element(label + '()')
    },
    construct() {
      return element('new ' + label)
    },
  })
  return self
}
class Observer {
  constructor(callback) {
    this.callback = callback
    this.on = false
  }
  observe() {
    if (!this.on) {
      this.on = true
      observing += 1
    }
  }
  unobserve() {}
  disconnect() {
    if (this.on) {
      this.on = false
      observing -= 1
    }
  }
  takeRecords() {
    return []
  }
}
const listened = (target) => ({
  addEventListener: (...a) => listen(target).addEventListener(...a),
  removeEventListener: (...a) => listen(target).removeEventListener(...a),
})
const doc = element('document')
const win = element('window')
const storage = { getItem: () => null, setItem() {}, removeItem() {} }
Object.assign(win, {
  document: doc,
  MutationObserver: Observer,
  ResizeObserver: Observer,
  IntersectionObserver: Observer,
  location: { pathname: '/page', href: 'http://app.test/page', search: '', hash: '' },
  history: { state: {}, pushState() {}, replaceState() {} },
  sessionStorage: storage,
  localStorage: storage,
  getComputedStyle: () => ({ getPropertyValue: () => '' }),
  matchMedia: () => ({ matches: false, ...listened('media') }),
  CustomEvent: class {
    constructor(type, init) {
      this.type = type
      this.detail = init && init.detail
    }
  },
  dispatchEvent: () => true,
  requestAnimationFrame: () => 1,
  cancelAnimationFrame: () => {},
  confirm: () => true,
})
doc.fonts = { ...listened('fonts'), check: () => true }
Object.assign(globalThis, {
  window: win,
  document: doc,
  MutationObserver: Observer,
  ResizeObserver: Observer,
  IntersectionObserver: Observer,
  requestAnimationFrame: () => 1,
  cancelAnimationFrame: () => {},
  getComputedStyle: win.getComputedStyle,
  CustomEvent: win.CustomEvent,
})
// 타이머 — 되풀이(`setInterval`)는 지울 때까지 남는다. 한 번짜리(`setTimeout`)는 부를 때마다
// 한 번씩 돌려(`tick`) 끝난 것은 걷고, 스스로 다시 거는 것(살아 있는 확인 고리)만 남긴다. 돌다
// 던지면 끝난 것으로 본다.
const timers = new Map()
let timerId = 0
const arm = (kind) => (fn) => {
  timerId += 1
  timers.set(timerId, { kind, fn })
  return timerId
}
const disarm = (id) => {
  timers.delete(id)
}
const tick = () => {
  for (const [id, timer] of [...timers]) {
    if (timer.kind !== 'timeout') continue
    timers.delete(id)
    try {
      if (typeof timer.fn === 'function') timer.fn()
    } catch (error) {
      // 느슨한 대역에서 던진 확인은 끝난 것으로 본다.
    }
  }
}
const pending = (kind) => [...timers.values()].filter((timer) => timer.kind === kind).length
globalThis.setTimeout = arm('timeout')
globalThis.clearTimeout = disarm
globalThis.setInterval = arm('interval')
globalThis.clearInterval = disarm
Object.assign(win, {
  setTimeout: globalThis.setTimeout,
  clearTimeout: disarm,
  setInterval: globalThis.setInterval,
  clearInterval: disarm,
})
"""

_DRIVE = r"""
const parent = element('parent')
const datas = %(datas)s
const sent = []
const component = (data) => ({
  name: 'probe', key: 'probe', data, parentElement: parent,
  setStateValue: (name, value) => sent.push(['state', name]),
  setTriggerValue: (name, value) => sent.push(['trigger', name]),
})
const counts = []
let cleanup = null
for (let i = 0; i < %(calls)d; i += 1) {
  const data = JSON.parse(JSON.stringify(datas[i %% datas.length]))
  data.__call = i
  cleanup = __default(component(data))
  tick()
  if (i === 0 || i === %(calls)d - 1) {
    counts.push([listeners(), observing, pending('timeout'), pending('interval')])
  }
}
process.stdout.write(JSON.stringify({ counts, cleanup: typeof cleanup }))
"""


def _tab_strip_js() -> str:
    from capa_simulation.components import page_tabs

    return page_tabs.registered_js()


def _tab_strip_data() -> list[dict[str, Any]]:
    from capa_simulation.components import page_tabs
    from capa_simulation.page_tabs_state import INITIAL_STRIP

    first = page_tabs.tabs_data(
        INITIAL_STRIP,
        active=INITIAL_STRIP.paths[0],
        hrefs={},
        marks={},
        leave="",
        epoch=1,
        notice=None,
    )
    second = page_tabs.tabs_data(
        INITIAL_STRIP,
        active=INITIAL_STRIP.paths[0],
        hrefs={},
        marks={},
        leave="편집",
        epoch=2,
        notice=None,
    )
    return [first, second]


def _edit_grid_js() -> str:
    from capa_simulation.components import edit_grid

    return edit_grid.registered_js()


def _edit_grid_rows_js() -> str:
    from capa_simulation.components import edit_grid

    return edit_grid.registered_js(edit_grid.ROWS_JS_PARTS)


def _two_palettes(shell: dict[str, Any]) -> list[dict[str, Any]]:
    """같은 표 껍데기 둘 — 색만 다르다(테마를 바꾼 회차처럼 data 가 바뀐다)."""
    palette = {**shell["palette"], "text": "#000001"}
    return [shell, {**shell, "palette": palette}]


def _edit_grid_data() -> list[dict[str, Any]]:
    """범용 편집 그리드 껍데기(합성 표 — 분류 둘 · 달 둘)."""
    import pandas as pd

    from capa_simulation.components import edit_grid
    from capa_simulation.services import edit_grid as eg
    from capa_simulation.services.edit_grid_payload import build_base

    months = ("202701", "202702")
    frame = pd.DataFrame({"공정": ["DEMO_A", "DEMO_B"], "구분": ["양산", "ER"]})
    for month in months:
        frame[month] = [0.9, 0.8]
    spec = eg.GridSpec("RQ_DEMO", "효율", ("공정", "구분"), months, eg.ValueFormat("percent", 2))
    base = build_base(frame, spec, None)
    shell = edit_grid.shell_data("demo_grid", base, spec, base_key="k1", changes_label="적용 전")
    return _two_palettes(shell)


def _edit_grid_rows_data() -> list[dict[str, Any]]:
    """줄 규칙 표 껍데기(접속 명단 꼴 합성 표 — `tests/test_edit_grid_rows.py`)."""
    from test_edit_grid_rows import RULES, SPEC, _frame

    from capa_simulation.components import edit_grid
    from capa_simulation.services.edit_grid_payload import build_base

    base = build_base(_frame(), SPEC, None, RULES)
    shell = edit_grid.shell_data("demo_rows", base, SPEC, base_key="k1", changes_label="저장 전")
    return _two_palettes(shell)


# 부품 이름 → (등록 JS, data 들). 편집기 갈래가 제 부품을 더한다 — 느슨한 대역으로 돌지 않는 부품은
# 그 부품의 node 시험에 bind-once 를 둔다.
BIND_ONCE: dict[str, tuple[Callable[[], str], Callable[[], list[dict[str, Any]]]]] = {
    "page_tabs": (_tab_strip_js, _tab_strip_data),
    "capa_edit_grid": (_edit_grid_js, _edit_grid_data),
    "capa_edit_grid_rows": (_edit_grid_rows_js, _edit_grid_rows_data),
}


def _as_script(source: str) -> str:
    """등록 글(ES 모듈)을 node 대본으로 — `export default function` 을 전역 이름에 단다."""
    assert source.count("export default function") == 1
    return source.replace("export default function", "globalThis.__default = function", 1)


@pytest.mark.parametrize("name", sorted(BIND_ONCE))
def test_calling_the_default_export_fifty_times_keeps_one_set_of_listeners(name: str) -> None:
    """data 가 바뀔 때마다 다시 불리는 default export 를 50번 불러도 살아 있는 처리기 · 관찰자 ·
    확인 고리 · 되풀이 타이머 수가 첫 호출 뒤와 같다 — 앞 호출의 정리 함수는 불리지 않으므로
    처리기와 타이머는 처음 한 번만 걸거나 지우고 다시 건다."""
    source, datas = BIND_ONCE[name]
    drive = _DRIVE % {"datas": json.dumps(datas()), "calls": 50}
    out = run_js_json(_HARNESS + _as_script(source()) + drive, what=f"{name} bind-once")

    first, last = out["counts"]
    assert first[0] > 0, "대역이 처리기를 하나도 세지 못했다"
    assert last == first
    assert out["cleanup"] == "function"


_BINDS_EVERY_CALL = """
export default function (component) {
  const host = component.parentElement.querySelector('.probe')
  const S = host.__probe || (host.__probe = { bound: false })
  window.addEventListener('resize', () => {})
  if (!S.bound) {
    S.bound = true
    document.addEventListener('keydown', () => {})
  }
  return () => {}
}
"""


def test_the_bind_once_harness_catches_a_component_that_binds_every_call() -> None:
    """대조 — 부를 때마다 창 처리기를 다는 부품은 50번 뒤 처리기가 49개 늘어난 것으로 잡힌다(대역이
    칸 상태를 남기고 살아 있는 처리기를 센다)."""
    drive = _DRIVE % {"datas": json.dumps([{}]), "calls": 50}
    out = run_js_json(_HARNESS + _as_script(_BINDS_EVERY_CALL) + drive, what="bind-once 대조")

    first, last = out["counts"]
    assert first == [2, 0, 0, 0]
    assert last == [51, 0, 0, 0]


_ARMS_EVERY_CALL = """
export default function (component) {
  const host = component.parentElement.querySelector('.probe')
  const S = host.__probe || (host.__probe = { bound: false, rearm: 0 })
  // 끝나는 한 번짜리 · 지우고 다시 거는 한 번짜리는 쌓이지 않는다.
  setTimeout(() => {}, 10)
  clearTimeout(S.rearm)
  S.rearm = setTimeout(() => {}, 10)
  // 부를 때마다 새 확인 고리 · 되풀이를 건다 — 쌓인다.
  const poll = () => { setTimeout(poll, 100) }
  poll()
  setInterval(() => {}, 1000)
  return () => {}
}
"""


def test_the_bind_once_harness_catches_timers_armed_on_every_call() -> None:
    """대조 — 부를 때마다 스스로 다시 거는 확인 고리 · 되풀이 타이머를 거는 부품은 50번 뒤 그
    수만큼 늘어난 것으로 잡힌다. 끝나는 한 번짜리와 지우고 다시 거는 한 번짜리는 세지 않는다(대역이
    부를 때마다 걸린 한 번짜리를 한 번씩 돌린다)."""
    drive = _DRIVE % {"datas": json.dumps([{}]), "calls": 50}
    out = run_js_json(_HARNESS + _as_script(_ARMS_EVERY_CALL) + drive, what="타이머 대조")

    first, last = out["counts"]
    assert first[2:] == [1, 1]
    assert last[2:] == [50, 50]
