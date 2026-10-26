# Purpose: 열릴 때 테마 새로고침이 첫 세션이 지운 링크 인자를 되살리는지 node 로 고정한다.

"""필요 단축 일정 「도면에서 보기」 주소(`/space_status?layer=short&floor=…&target=…&proc=…`)를
테마 인자 없이(또는 저장 테마와 다른 인자로) 새로 열면 테마 스크립트가 한 번 새로고침한다.
버려지는 첫 세션도 페이지 본문까지 돌아 링크 인자를 받고 주소에서 지운다 — 그 지우기가 테마
스크립트보다 먼저 브라우저에 닿으면, 지금 주소(`?floor=…`)에 테마만 붙여 새로고침한 새 세션은
링크를 받지 못해 두 번에 한 번꼴로 필요 단축 보기·목표·공정 칩 없이 층만 열렸다(E2E 결함).
공정 Capa 상세 `?process=…`·제약 시뮬레이션 `?process=` 도 같은 길이다.

툴바 iframe 의 스크립트 셋(키 규칙·차례 규칙·테마 단추)을 글자 그대로 node 에서 가짜 부모 창으로
돌린다. 부모 창의 탐색 항목(`performance.getEntriesByType("navigation")`)이 문서를 연 주소다 —
Chrome 은 `history.replaceState` 로 주소를 고쳐도 그 이름을 바꾸지 않는다(브라우저 확인). node 가
없으면 건너뛰고 CI 에서는 실패한다(`test_space_module_group._node`).
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
import streamlit as st
from test_space_module_group import _node

from capa_simulation.components import theme_toggle
from capa_simulation.design.theme import THEME_QUERY_PARAM

ORIGIN = "http://127.0.0.1:8565"
LINK = f"{ORIGIN}/space_status?layer=short&floor=C1-2F&target=1.1&proc=Die+Attach"
STRIPPED = f"{ORIGIN}/space_status?floor=C1-2F"

_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
function store(init) {
  const m = new Map(Object.entries(init || {}))
  return {
    get length() { return m.size },
    key(i) { const keys = [...m.keys()]; return i < keys.length ? keys[i] : null },
    getItem(k) { return m.has(k) ? m.get(k) : null },
    setItem(k, v) { m.set(k, String(v)) },
    removeItem(k) { m.delete(k) },
  }
}
const run = new Function('window', input.script)
const out = input.cases.map((c) => {
  const log = { replaced: [], reloads: 0, button: null }
  let current = new URL(c.href)
  const doc = {
    querySelector() { return slot },
    getElementById() { return null },
    createElement() { return { style: {}, setAttribute() {} } },
    documentElement: {},
    body: {},
  }
  const slot = {
    ownerDocument: doc,
    appendChild(node) { log.button = node },
    insertBefore(node) { log.button = node },
  }
  const parent = {
    URL,
    document: doc,
    location: {
      get href() { return current.href },
      get pathname() { return current.pathname },
      reload() { log.reloads += 1 },
    },
    history: {
      replaceState(_state, _title, url) {
        current = new URL(url, current.href)
        log.replaced.push(current.href)
      },
    },
    performance: {
      getEntriesByType(type) {
        return type === 'navigation' && c.opened ? [{ name: c.opened }] : []
      },
    },
    localStorage: store(c.local),
    sessionStorage: store({}),
    MutationObserver: class { observe() {} disconnect() {} },
    setTimeout() {},
    getComputedStyle() { return { getPropertyValue() { return '' } } },
    confirm() { return true },
  }
  run({ parent })
  const opened = current.href
  if (c.click && log.button) log.button.onclick()
  return {
    opened, href: current.href, replaced: log.replaced, reloads: log.reloads,
    button: Boolean(log.button),
  }
})
process.stdout.write(JSON.stringify(out))
"""


def _frame_script(monkeypatch: pytest.MonkeyPatch) -> str:
    """`render_theme_toggle` 이 보내는 iframe 의 `<script>` 본문을 차례대로 잇는다."""
    frames: list[str] = []
    monkeypatch.setattr(st, "iframe", lambda src, **_kwargs: frames.append(src))
    monkeypatch.setattr(st, "html", lambda _body, **_kwargs: None)
    theme_toggle.render_theme_toggle()
    assert len(frames) == 1
    return "\n".join(re.findall(r"<script>(.*?)</script>", frames[0], re.S))


def _run(monkeypatch: pytest.MonkeyPatch, cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: Any = _node(_RUNNER, {"script": _frame_script(monkeypatch), "cases": cases})
    return list(result)


def _query(href: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(href).query)


def _synced(choice: str, path: str = "/space_status") -> dict[str, str]:
    """앱 키·지금 경로의 Streamlit 키·우리 표지가 모두 `choice` 인 저장소.

    키 때문에는 새로고침하지 않는다.
    """
    streamlit_key = f"{theme_toggle.THEME_STORAGE_PREFIX}{path}{theme_toggle.THEME_STORAGE_SUFFIX}"
    return {
        theme_toggle.THEME_APP_KEY: choice,
        streamlit_key: f'"{choice}"',
        f"{theme_toggle.THEME_SYNC_PREFIX}{path}": choice,
    }


def test_the_reload_reopens_the_link_the_first_session_already_stripped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E2E 재현 셋 — 저장 테마 없음·Dark 저장(테마 인자 없음)·Light 저장(`&theme=dark`).

    첫 세션이 링크 인자를 지운 뒤(`?floor=C1-2F`) 스크립트가 돌아도 새로고침 주소는 링크 인자를
    모두 싣는다. 예전에는 `?floor=C1-2F&theme=…` 였다.
    """
    no_saved, dark_saved, light_saved = _run(
        monkeypatch,
        [
            {"href": STRIPPED, "opened": LINK, "local": {}},
            {"href": STRIPPED, "opened": LINK, "local": {theme_toggle.THEME_APP_KEY: "Dark"}},
            {
                "href": f"{STRIPPED}&theme=dark",
                "opened": f"{LINK}&theme=dark",
                "local": _synced("Light"),
            },
        ],
    )

    for result, mode in ((no_saved, "light"), (dark_saved, "dark"), (light_saved, "light")):
        assert result["reloads"] == 1
        assert len(result["replaced"]) == 1
        assert urlsplit(result["href"]).path == "/space_status"
        assert _query(result["href"]) == {
            "floor": ["C1-2F"],
            "layer": ["short"],
            "target": ["1.1"],
            "proc": ["Die Attach"],
            THEME_QUERY_PARAM: [mode],
        }


def test_the_reload_keeps_the_link_once_when_the_script_wins_the_race(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """스크립트가 첫 세션의 지우기보다 먼저 돌면 지금 주소가 연 주소다 — 인자를 겹쳐 싣지 않는다."""
    (result,) = _run(monkeypatch, [{"href": LINK, "opened": LINK, "local": {}}])

    assert result["reloads"] == 1
    assert _query(result["href"]) == {
        "layer": ["short"],
        "floor": ["C1-2F"],
        "target": ["1.1"],
        "proc": ["Die Attach"],
        THEME_QUERY_PARAM: ["light"],
    }


def test_only_missing_names_of_the_same_page_come_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """되살리는 것은 같은 출처·경로에서 **빠진 이름**뿐이다.

    지금 주소의 값(세션이 고친 층)은 그대로, 같은 이름 여러 값은 모두, 다른 화면을 연 문서(앱
    안에서 옮겨 온 경로)의 인자는 싣지 않는다. 탐색 항목이 없으면 예전처럼 지금 주소에 테마만
    붙인다.
    """
    changed, repeated, other_page, other_origin, unknown = _run(
        monkeypatch,
        [
            {
                "href": f"{ORIGIN}/space_status?floor=C2-6F",
                "opened": f"{ORIGIN}/space_status?floor=C1-2F&layer=short",
                "local": {},
            },
            {
                "href": f"{ORIGIN}/space_status",
                "opened": f"{ORIGIN}/space_status?k=a&k=b",
                "local": {},
            },
            {"href": STRIPPED, "opened": f"{ORIGIN}/?process=Die+Attach", "local": {}},
            {
                "href": STRIPPED,
                "opened": "http://other.example/space_status?layer=short",
                "local": {},
            },
            {"href": STRIPPED, "opened": None, "local": {}},
        ],
    )

    assert _query(changed["href"]) == {
        "floor": ["C2-6F"],
        "layer": ["short"],
        THEME_QUERY_PARAM: ["light"],
    }
    assert _query(repeated["href"]) == {"k": ["a", "b"], THEME_QUERY_PARAM: ["light"]}
    for result in (other_page, other_origin, unknown):
        assert result["reloads"] == 1
        assert _query(result["href"]) == {"floor": ["C1-2F"], THEME_QUERY_PARAM: ["light"]}


def test_no_reload_when_the_theme_already_matches_and_the_button_uses_the_current_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """테마 인자·키가 맞으면(앱 안 링크를 같은 브라우저 새 탭으로 연 때) 새로고침하지 않는다.

    단추를 세우고, 단추를 눌러 바꿀 때는 세션 안에서 바뀐 **지금 주소** 그대로다 — 연 주소의
    지운 링크 인자를 되살리면 링크를 다시 받는다.
    """
    (result,) = _run(
        monkeypatch,
        [
            {
                "href": f"{STRIPPED}&theme=light",
                "opened": f"{LINK}&theme=light",
                "local": _synced("Light"),
                "click": True,
            }
        ],
    )

    assert result["button"] is True
    assert result["opened"] == f"{STRIPPED}&theme=light"
    assert result["reloads"] == 1  # 단추 누름의 새로고침 하나뿐이다
    assert _query(result["href"]) == {"floor": ["C1-2F"], THEME_QUERY_PARAM: ["dark"]}


def test_the_open_time_reload_goes_through_the_reopen_rule() -> None:
    """열릴 때의 새로고침은 `reloadOnOpen` 한 곳이고 연 주소를 탐색 항목에서 읽는다.

    단추는 `syncParam`(지금 주소)이다.
    """
    script = theme_toggle._SCRIPT
    place = script[script.index("function place(") :]
    assert "reloadOnOpen(dark ? " in place
    assert "syncParam(dark ? " not in place
    assert "syncParam(next.toLowerCase());" in place
    assert 'getEntriesByType("navigation")' in script
    assert re.search(
        r"// <theme-reopen>\n.*function reopenHref\(.*// </theme-reopen>", script, re.S
    )
