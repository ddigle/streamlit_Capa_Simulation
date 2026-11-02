# Purpose: 범용 편집 그리드 고르기(eg_select)의 순수 구획과 가짜 DOM 동작을 본다.

"""고르기(SELECT) 가지 몫(편집 표 횡전개 명세 9-2·9-3·13-1). 순수 구획 `// <eg-rect>`·
`// <eg-clip>` 은 node 로 떼어 돌리고(`tests/edit_grid_node.py`), 동작은 등록 JS 전체를 가짜 DOM에
마운트해 키·누름·끌기·copy/paste 이벤트를 쏘아 본다. 실제 클립보드·자동 스크롤 속도는 사본 앱
브라우저로 잰다(명세 13-5 SELECT)."""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd
from edit_grid_node import FAKE_DOM, RUNNER_HEAD, asset, mountable, run_node, sections

from capa_simulation.components import edit_grid
from capa_simulation.services import edit_grid as eg
from capa_simulation.services.edit_grid_payload import build_base, encode_base, encode_feed

SELECT = asset("eg_select.js")
SELECT_CSS = asset("eg_select.css")
REGISTERED_JS = edit_grid.registered_js()


def _pure(*names: str) -> str:
    return sections(SELECT, names)


# ------------------------------------------------------------------ 자산 글


def test_the_select_feature_registers_every_hook_it_needs() -> None:
    hook = SELECT[SELECT.rindex("feature({ name: 'select'") :]
    for name in ("init", "keydown", "pointerdown", "paintCell", "paintOverlay", "cleanup"):
        assert re.search(rf"\b{name}: sel[A-Z]", hook), name


def test_copy_goes_through_the_synchronous_copy_event_only() -> None:
    """복사는 동기 `copy` 이벤트의 `clipboardData` 로만 — Ctrl+C keydown 은 막지 않아 브라우저가
    초점 칸에 copy 를 쏘게 한다(비동기 `navigator.clipboard` 는 사내 주소가 보안 문맥이 아닐 수
    있어 쓰지 않는다)."""
    assert "navigator.clipboard" not in SELECT and "execCommand" not in SELECT
    assert "selListen(S, scroller, 'copy'" in SELECT
    assert "event.clipboardData.setData('text/plain', text)" in SELECT
    ctrl_c = SELECT[SELECT.index("if (plainCtrl && lower === 'c')") :]
    ctrl_c = ctrl_c[: ctrl_c.index("}")]
    assert "preventDefault" not in ctrl_c and "selClearPageSelection()" in ctrl_c


def test_the_other_features_can_take_over_paste_and_drag() -> None:
    """채우기(FILL)는 `paste` 갈고리로 붙여넣기 판을 먼저 가져가고 `selDrag` 로 손잡이를 끈다."""
    assert re.search(r"^function selDrag\(S, event, handlers\)", SELECT, re.M)
    assert "item.name !== 'select' && item.paste && item.paste(S, matrix, event) === true" in SELECT


def test_the_select_css_draws_with_palette_colours_only() -> None:
    used = set(re.findall(r"var\(--eg-([a-z-]+)", SELECT_CSS))
    assert used and used <= set(edit_grid.palette())
    assert "/*" not in SELECT_CSS
    assert not re.search(r"#[0-9A-Fa-f]{3,8}\b", SELECT_CSS)


def test_the_new_status_texts_are_shipped_in_korean() -> None:
    spec = eg.GridSpec("RQ_DEMO", "효율", ("공정",), ("202701",), eg.ValueFormat("percent", 2))
    texts = edit_grid.texts(spec, changes_label="적용 전 변경")
    for name in ("copied", "cleared", "pasted", "pasteSkipped", "cut", "locked", "clipped"):
        assert "{n}" in texts[name] or name in ("cut", "locked"), name
        assert f"'{name}'" in SELECT, name


# ------------------------------------------------------------------ node — 순수 구획


def test_ranges_normalise_measure_and_mark_their_edges() -> None:
    runner = (
        RUNNER_HEAD
        + """
const rect = rectNorm({ r: 5, c: 4 }, { r: 2, c: 1 })
done({
  rect, size: rectSize(rect), has: [rectHas(rect, 2, 1), rectHas(rect, 5, 4), rectHas(rect, 6, 4)],
  edges: [rectEdges(rect, 2, 1), rectEdges(rect, 5, 4), rectEdges(rect, 3, 2),
    rectEdges(rect, 2, 4), rectEdges(rect, 9, 9),
    rectEdges(rectNorm({ r: 1, c: 1 }, { r: 1, c: 1 }), 1, 1)],
  all: rectSpan('all', { r: 3, c: 3 }, { r: 4, c: 5 }, 10, 8),
  row: rectSpan('row', { r: 4, c: 3 }, { r: 2, c: 5 }, 10, 8),
  col: rectSpan('col', { r: 4, c: 3 }, { r: 2, c: 5 }, 10, 8),
  empty: rectSpan('all', { r: 0, c: 0 }, { r: 0, c: 0 }, 0, 8),
  unknown: rectSpan('x', { r: 0, c: 0 }, { r: 0, c: 0 }, 3, 3),
})
"""
    )
    result = run_node(_pure("eg-rect"), runner, {})
    assert result["rect"] == {"r0": 2, "r1": 5, "c0": 1, "c1": 4}
    assert result["size"] == {"h": 4, "w": 4, "cells": 16}
    assert result["has"] == [True, True, False]
    # 1 위 · 2 아래 · 4 왼쪽 · 8 오른쪽 — 왼쪽 위 모서리 5, 오른쪽 아래 10, 안 0, 오른쪽 위 9.
    assert result["edges"] == [5, 10, 0, 9, 0, 15]
    assert result["all"] == {"anchor": {"r": 0, "c": 0}, "focus": {"r": 9, "c": 7}}
    # 줄 고르기는 고른 줄들(4 → 2)을 끝까지, 칸 고르기는 고른 칸들(3 → 5)을 위에서 아래까지.
    assert result["row"] == {"anchor": {"r": 4, "c": 0}, "focus": {"r": 2, "c": 7}}
    assert result["col"] == {"anchor": {"r": 0, "c": 3}, "focus": {"r": 9, "c": 5}}
    assert result["empty"] is None and result["unknown"] is None


def test_drag_auto_scroll_speeds_up_with_distance_and_respects_frozen_columns() -> None:
    """창 밖으로 멀수록 빨리 — min(4 + 거리 × 0.5, 80)px/프레임(D2: 60px 밖 약 60줄/초).
    고정 칸 위에서는 끌기가 고정 칸 밖에서 시작했고 아직 왼쪽으로 굴릴 것이 있을 때만 왼쪽으로
    굴린다."""
    runner = (
        RUNNER_HEAD
        + """
const view = { left: 100, top: 50, width: 800, height: 500, headH: 32, frozenWidth: 200,
  scrollLeft: 300 }
const at = (x, y, over, scrollLeft) => dragScrollStep(x, y, Object.assign({}, view,
  scrollLeft === undefined ? {} : { scrollLeft }), over)
done({
  inside: at(500, 300, true),
  below: at(500, 610, true),
  far: at(500, 5000, true),
  header: at(500, 60, true),
  above: at(500, 10, true),
  right: at(960, 300, true),
  frozen: at(150, 300, true),
  frozenFromKey: at(150, 300, false),
  frozenAtStart: at(150, 300, true, 0),
  outsideLeft: at(40, 300, false),
  corner: at(960, 600, true),
})
"""
    )
    result = run_node(_pure("eg-rect"), runner, {})
    assert result["inside"] == {"dx": 0, "dy": 0}
    assert result["below"] == {"dx": 0, "dy": 34}
    assert result["far"] == {"dx": 0, "dy": 80}
    assert result["header"] == {"dx": 0, "dy": -15}
    assert result["above"] == {"dx": 0, "dy": -40}
    assert result["right"] == {"dx": 34, "dy": 0}
    assert result["frozen"] == {"dx": -79, "dy": 0}
    assert result["frozenFromKey"] == {"dx": 0, "dy": 0}
    assert result["frozenAtStart"] == {"dx": 0, "dy": 0}
    assert result["outsideLeft"] == {"dx": -34, "dy": 0}
    assert result["corner"] == {"dx": 34, "dy": 29}


def test_excel_tsv_round_trips_tabs_newlines_quotes_and_blank_last_lines() -> None:
    """엑셀 따옴표 TSV — 줄 사이 CRLF, 탭·줄바꿈·따옴표가 든 칸은 따옴표로 감싸고 `""` 로 겹친다.
    마지막 줄이 빈 글이면 끝 CRLF 를 하나 더 붙여 붙여넣기가 그 줄을 살려 둔다."""
    matrices: list[list[list[str]]] = [
        [["1", "2"], ["3", "4"]],
        [["a\tb", 'say "hi"', "line1\nline2"], ["", "", ""]],
        [["0.9875"]],
        [[""]],
        [["1"], [""]],
        [["", ""], ["", "x"]],
        [['"quoted"', "end\r\n"]],
        [["공정 에이", "양산", "0.85"]],
    ]
    runner = (
        RUNNER_HEAD
        + """
done(input.map((matrix) => {
  const text = toTsv(matrix)
  return { text, back: parseClipboard(text) }
}))
"""
    )
    result = run_node(_pure("eg-clip"), runner, matrices)
    texts = [item["text"] for item in result]
    assert texts[0] == "1\t2\r\n3\t4"
    assert texts[1] == '"a\tb"\t"say ""hi"""\t"line1\nline2"\r\n\t\t'
    assert texts[2] == "0.9875"
    assert texts[3] == "\r\n" and texts[4] == "1\r\n\r\n"
    for matrix, item in zip(matrices, result, strict=True):
        # 칸 안 CRLF 는 붙여넣기에서 LF 로 읽힌다(엑셀 칸 줄바꿈도 LF).
        expected = [[cell.replace("\r\n", "\n") for cell in line] for line in matrix]
        assert item["back"] == expected, (matrix, item)


def test_pasted_text_is_read_like_excel_writes_it() -> None:
    cases = {
        "excel": "1\t2\r\n3\t4\r\n",
        "lf": "1\t2\n3\t4",
        "cr": "1\t2\r3\t4\r",
        "single": "12%",
        "single_newline": "12%\r\n",
        "empty_cell": "\r\n",
        "ragged": "1\t2\t3\r\n4\r\n",
        "quoted": '"a\r\nb"\t"x""y"\r\n',
        "not_quoted": '"open\t5',
        "text_after_quote": '"ab"c\t5',
        "blank_middle": "1\t\t3",
        "keep_one_trailing": "1\r\n\r\n",
    }
    runner = (
        RUNNER_HEAD
        + "done(Object.fromEntries(Object.entries(input).map(([k, v]) => [k, parseClipboard(v)])))"
    )
    result = run_node(_pure("eg-clip"), runner, cases)
    assert result == {
        "excel": [["1", "2"], ["3", "4"]],
        "lf": [["1", "2"], ["3", "4"]],
        "cr": [["1", "2"], ["3", "4"]],
        "single": [["12%"]],
        "single_newline": [["12%"]],
        "empty_cell": [[""]],
        "ragged": [["1", "2", "3"], ["4"]],
        "quoted": [["a\nb", 'x"y']],
        "not_quoted": [['"open', "5"]],
        "text_after_quote": [['"ab"c', "5"]],
        "blank_middle": [["1", "", "3"]],
        "keep_one_trailing": [["1"], [""]],
    }


def test_a_block_is_spread_from_the_anchor_skipping_key_columns_and_clipping_at_the_end() -> None:
    """표 10줄 × 6칸(앞 2칸이 분류 칸). 덩어리는 기준 칸부터 그대로 — 분류 칸에 걸린 칸은
    건너뛰고, 표 끝을 넘은 칸은 버린다. values 는 값 칸 범위의 줄 × 칸(모자란 자리는 null — 그
    칸은 그대로)."""
    runner = (
        RUNNER_HEAD
        + """
const block = [['1', '2'], ['3', '4']]
done({
  inside: pasteAtAnchor(3, 2, block, 10, 6, 2),
  overKeys: pasteAtAnchor(0, 1, [['k', 'a', 'b'], ['k', 'c']], 10, 6, 2),
  onlyKeys: pasteAtAnchor(0, 0, [['k', 'j']], 10, 6, 2),
  pastEnd: pasteAtAnchor(9, 5, block, 10, 6, 2),
  ragged: pasteAtAnchor(0, 2, [['1', '2', '3'], ['4']], 10, 6, 2),
  emptyTable: pasteAtAnchor(0, 2, block, 0, 6, 2),
})
"""
    )
    result = run_node(_pure("eg-clip"), runner, {})
    inside = result["inside"]
    assert {key: inside[key] for key in ("r0", "r1", "c0", "c1", "values", "cells")} == {
        "r0": 3,
        "r1": 4,
        "c0": 2,
        "c1": 3,
        "values": [["1", "2"], ["3", "4"]],
        "cells": 4,
    }
    assert inside["clipped"] == 0 and inside["skipped"] == 0
    assert inside["span"] == {"r0": 3, "r1": 4, "c0": 2, "c1": 3}
    over = result["overKeys"]
    assert over["c0"] == 2 and over["c1"] == 3
    assert over["values"] == [["a", "b"], ["c", None]]
    assert over["skipped"] == 2 and over["cells"] == 3
    assert over["span"] == {"r0": 0, "r1": 1, "c0": 1, "c1": 3}
    only = result["onlyKeys"]
    assert only["cells"] == 0 and only["skipped"] == 2 and only["c0"] > only["c1"]
    end = result["pastEnd"]
    assert end["values"] == [["1"]] and end["cells"] == 1 and end["clipped"] == 3
    assert result["ragged"]["values"] == [["1", "2", "3"], ["4", None, None]]
    assert result["ragged"]["cells"] == 4
    empty = result["emptyTable"]
    assert empty["cells"] == 0 and empty["values"] == [] and empty["clipped"] == 4


# ------------------------------------------------------------------ 가짜 DOM — 등록 JS 전체

MONTHS = ("202701", "202702", "202703", "202704")
ROWS = 60
SPEC = eg.GridSpec(
    "RQ_DEMO",
    "효율",
    ("공정", "구분"),
    MONTHS,
    eg.ValueFormat("percent", 2, max_value=1.0),
)


def _frame() -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "공정": [f"DEMO_P{k:02d}" for k in range(ROWS)],
            "구분": ["양산" if k % 2 == 0 else "ER" for k in range(ROWS)],
        }
    )
    for column, month in enumerate(MONTHS):
        frame[month] = [round(0.5 + ((k + column) % 10) / 100, 4) for k in range(ROWS)]
    frame.loc[3, MONTHS[1]] = np.nan
    return frame


def _payloads(paste_limit: int | None = None) -> dict[str, Any]:
    frame = _frame()
    base = build_base(frame, SPEC, {"공정": {"DEMO_P00": "공정 영"}})
    shell = encode_base(
        base.body,
        host="demo_grid",
        base_key="k1",
        texts=edit_grid.texts(SPEC, changes_label="적용 전 변경"),
        palette={"text": "ink"},
        row_height=30,
    )
    if paste_limit is not None:
        shell["limits"] = {**shell["limits"], "paste": paste_limit}
    history: eg.HistoryState = {"gen": "g1", "undo": [], "redo": []}
    feed = encode_feed(
        base.index, None, history, host="demo_grid", base_key="k1", acks={}, toast=None
    )
    return {"shell": shell, "feed": feed}


# 좌표: 스크롤 칸 1000×600(가짜 DOM), 머리 32px, 줄 30px, 열쇠 칸 104px 둘(고정), 값 칸 80px.
MOUNT = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const sent = []
const parentElement = new FakeNode('div')
const host = parentElement.appendChild(new FakeNode('div'))
host.setAttribute('data-eg-root', '')
let removed = 0
document.getSelection = () => ({ rangeCount: 1, removeAllRanges() { removed += 1 } })
const sendFeed = (feed) => {
  const store = (window.__capaEditGrid = window.__capaEditGrid || {})
  ;(store[feed.host] = store[feed.host] || {}).feed = feed
  window.dispatchEvent(new CustomEvent('capa-edit-grid', { detail: feed.host }))
}
sendFeed(input.feed)
const cleanup = globalThis.__mount({
  data: input.shell, parentElement,
  setStateValue: (name, value) => sent.push([name, JSON.parse(JSON.stringify(value))]),
})
const S = host.__eg
const q = (selector) => host.querySelector(selector)
const scroller = q('.eg-scroll')
const lineOf = (r) => S.dom.body.children.find((line) => Number(line.dataset.r) === r)
const cell = (r, c) => lineOf(r).children[c]
const MARKS = ['in-rng', 'is-sel', 'sel-t', 'sel-b', 'sel-l', 'sel-r', 'is-cp', 'cp-t', 'cp-b',
  'cp-l', 'cp-r', 'is-active']
const classes = (r, c) => MARKS.filter((name) => cell(r, c).classList.contains(name))
const key = (name, extra) => fire(scroller, 'keydown', Object.assign({ key: name }, extra))
const range = () => S.range()
const lastOp = () => S.box.ops[S.box.ops.length - 1] || null
const note = () => q('.eg-note').textContent
const xOf = (c) => S.lefts[c] + S.widths[c] / 2 - (c < S.frozen ? 0 : scroller.scrollLeft)
const yOf = (r) => S.headH + r * S.rowH + S.rowH / 2 - scroller.scrollTop
const point = (type, r, c, extra) => fire(scroller, type,
  Object.assign({ clientX: xOf(c), clientY: yOf(r), pointerId: 1 }, extra))
const R = {}
"""


def _run(body: str, payload: dict[str, Any]) -> Any:
    source = FAKE_DOM + mountable(REGISTERED_JS)
    return run_node(source, MOUNT + "\n;(async () => {\n" + body + "\n})()\n", payload)


def test_shift_keys_grow_the_range_from_the_active_cell_and_mark_it() -> None:
    body = r"""
  key('ArrowRight', { shiftKey: true })
  key('ArrowDown', { shiftKey: true })
  key('ArrowDown', { shiftKey: true })
  R.grown = { range: range(), anchor: Object.assign({}, S.anchor) }
  R.marks = {
    anchor: classes(0, 2), right: classes(0, 3), middle: classes(1, 2), corner: classes(2, 3),
    outside: classes(3, 3),
    selected: [cell(1, 3).getAttribute('aria-selected'), cell(3, 3).getAttribute('aria-selected')],
    heads: q('.eg-head').children.map((head) => head.classList.contains('is-sel-col')),
  }
  key('End', { shiftKey: true, ctrlKey: true })
  R.ctrlEnd = range()
  key('Home', { shiftKey: true })
  R.home = range()
  key('PageDown', { shiftKey: true })
  R.page = range()
  key('ArrowDown')
  R.collapsed = [range(), classes(0, 3).includes('in-rng')]
  key('ArrowUp', { shiftKey: true, ctrlKey: true })
  R.blockUp = range()
  process.stdout.write(JSON.stringify(R))
"""
    result = _run(body, _payloads())
    assert result["grown"] == {
        "range": {"r0": 0, "r1": 2, "c0": 2, "c1": 3},
        "anchor": {"r": 0, "c": 2},
    }
    marks = result["marks"]
    # 지금 칸은 칠하지 않고(엑셀) 테만, 나머지 고른 칸은 바탕 + 둘레 변 표지.
    assert marks["anchor"] == ["in-rng", "sel-t", "sel-l", "is-active"]
    assert marks["right"] == ["in-rng", "is-sel", "sel-t", "sel-r"]
    assert marks["middle"] == ["in-rng", "is-sel", "sel-l"]
    assert marks["corner"] == ["in-rng", "is-sel", "sel-b", "sel-r"]
    assert marks["outside"] == [] and marks["selected"] == ["true", "false"]
    assert marks["heads"] == [False, False, True, True, False, False]
    assert result["ctrlEnd"] == {"r0": 0, "r1": ROWS - 1, "c0": 2, "c1": 5}
    assert result["home"] == {"r0": 0, "r1": ROWS - 1, "c0": 0, "c1": 2}
    # 맞은편 모서리가 이미 끝 줄이라 PageDown 은 더 가지 않는다.
    assert result["page"] == {"r0": 0, "r1": ROWS - 1, "c0": 0, "c1": 2}
    assert result["collapsed"] == [{"r0": 1, "r1": 1, "c0": 2, "c1": 2}, False]
    assert result["blockUp"] == {"r0": 0, "r1": 1, "c0": 2, "c1": 2}


def test_whole_table_row_and_column_selections() -> None:
    body = r"""
  key('ArrowDown')
  key('ArrowRight')
  key('ArrowDown', { shiftKey: true })
  key('a', { ctrlKey: true })
  R.all = [range(), Object.assign({}, S.anchor)]
  key('ArrowDown')
  key('ArrowRight')
  key('ArrowDown', { shiftKey: true })
  key(' ', { shiftKey: true })
  R.row = [range(), Object.assign({}, S.anchor)]
  key('ArrowRight')
  key(' ', { ctrlKey: true })
  R.col = range()
  key(' ', { ctrlKey: true, shiftKey: true })
  R.allAgain = range()
  R.noEdit = S.edit === null && q('.eg-ed').hidden
  process.stdout.write(JSON.stringify(R))
"""
    result = _run(body, _payloads())
    assert result["all"] == [{"r0": 0, "r1": ROWS - 1, "c0": 0, "c1": 5}, {"r": 0, "c": 0}]
    assert result["row"] == [{"r0": 1, "r1": 2, "c0": 0, "c1": 5}, {"r": 1, "c": 0}]
    assert result["col"] == {"r0": 0, "r1": ROWS - 1, "c0": 1, "c1": 1}
    assert result["allAgain"] == {"r0": 0, "r1": ROWS - 1, "c0": 0, "c1": 5}
    assert result["noEdit"], "Shift+Space 는 칸 편집을 열지 않는다"


def test_click_shift_click_and_drag_with_auto_scroll() -> None:
    body = r"""
  point('pointerdown', 1, 3)
  point('pointerup', 1, 3)
  R.click = [range(), removed > 0, document.activeElement === scroller]
  point('pointerdown', 4, 5, { shiftKey: true })
  point('pointerup', 4, 5)
  R.shiftClick = range()
  // 끌기 — 손 밑 칸이 바뀔 때마다 맞은편 모서리가 따라온다.
  point('pointerdown', 2, 2)
  point('pointermove', 3, 3)
  point('pointermove', 5, 4)
  R.dragging = [range(), S.sel.drag !== null]
  point('pointerup', 5, 4)
  R.dragged = [range(), S.sel.drag === null]
  // 아래로 창 밖 60px — 자동 스크롤로 끝 줄까지 고른다.
  point('pointerdown', 0, 2)
  fire(scroller, 'pointermove', { clientX: xOf(2), clientY: 660, pointerId: 1 })
  await tick(120)
  R.auto = { scrollTop: scroller.scrollTop, focus: Object.assign({}, S.focus),
    anchor: Object.assign({}, S.anchor) }
  fire(scroller, 'pointerup', { clientX: xOf(2), clientY: 660, pointerId: 1 })
  R.autoEnd = { scrolled: S.sel.lastDrag.scrolled > 3, drag: S.sel.drag }
  const stopped = scroller.scrollTop
  await tick(30)
  R.stopped = scroller.scrollTop === stopped
  process.stdout.write(JSON.stringify(R))
"""
    result = _run(body, _payloads())
    click, cleared, focused = result["click"]
    assert click == {"r0": 1, "r1": 1, "c0": 3, "c1": 3}
    assert cleared and focused, "누르면 페이지 글 고름을 지우고 표에 초점"
    assert result["shiftClick"] == {"r0": 1, "r1": 4, "c0": 3, "c1": 5}
    assert result["dragging"] == [{"r0": 2, "r1": 5, "c0": 2, "c1": 4}, True]
    assert result["dragged"] == [{"r0": 2, "r1": 5, "c0": 2, "c1": 4}, True]
    auto = result["auto"]
    assert auto["scrollTop"] > 0 and auto["anchor"] == {"r": 0, "c": 2}
    assert auto["focus"] == {"r": ROWS - 1, "c": 2}
    assert result["autoEnd"] == {"scrolled": True, "drag": None}
    assert result["stopped"], "놓으면 자동 스크롤이 멈춘다"


def test_dragging_left_over_frozen_columns_scrolls_before_it_selects_keys() -> None:
    """끌기가 값 칸에서 시작했으면 고정(분류) 칸 위에서는 먼저 왼쪽으로 굴리고, 다 굴린 뒤에야 분류
    칸을 고른다(엑셀 틀 고정과 같다)."""
    body = r"""
  const log = []
  const record = (state) => log.push([state.focus.c, state.dom.scroller.scrollLeft])
  feature({ name: 'toolbar', onSelect: record })
  scroller.scrollLeft = 200
  point('pointerdown', 1, 5)
  fire(scroller, 'pointermove', { clientX: 50, clientY: yOf(1), pointerId: 1 })
  await tick(120)
  fire(scroller, 'pointerup', { clientX: 50, clientY: yOf(1), pointerId: 1 })
  R.log = log
  R.end = { scrollLeft: scroller.scrollLeft, range: range() }
  process.stdout.write(JSON.stringify(R))
"""
    result = _run(body, _payloads())
    assert result["end"] == {"scrollLeft": 0, "range": {"r0": 1, "r1": 1, "c0": 0, "c1": 5}}
    scrolled = [entry for entry in result["log"] if entry[1] > 0]
    assert scrolled, result["log"]
    assert all(focus_col >= 2 for focus_col, _ in scrolled), result["log"]


def test_copy_puts_the_selection_on_the_clipboard_as_excel_tsv() -> None:
    body = r"""
  const store = {}
  const clip = { setData(type, text) { store[type] = text } }
  key('ArrowLeft')
  key('ArrowLeft')
  key('ArrowDown', { shiftKey: true })
  key('ArrowDown', { shiftKey: true })
  key('ArrowDown', { shiftKey: true })
  key('ArrowRight', { shiftKey: true })
  key('ArrowRight', { shiftKey: true })
  key('ArrowRight', { shiftKey: true })
  removed = 0
  const down = key('c', { ctrlKey: true })
  R.keydown = { prevented: down.defaultPrevented, cleared: removed }
  const copy = fire(scroller, 'copy', { clipboardData: clip })
  R.copy = { prevented: copy.defaultPrevented, text: store['text/plain'], note: note(),
    last: S.sel.lastCopy.cells }
  R.marquee = { corner: classes(0, 0), inner: classes(1, 1), edge: classes(3, 3),
    outside: classes(4, 0) }
  // 고름을 옮겨도 점선은 남고(붙여넣을 곳으로 간다), Esc 가 지운다. 둘째 Esc 는 쥐지 않는다.
  key('ArrowDown')
  key('ArrowDown')
  key('ArrowDown')
  key('ArrowDown')
  key('ArrowDown')
  R.kept = classes(0, 0).includes('is-cp')
  const esc = key('Escape')
  const esc2 = key('Escape')
  R.escape = [esc.defaultPrevented, classes(0, 0).includes('is-cp'), esc2.defaultPrevented]
  // 칸 편집을 시작하면 점선이 사라진다.
  key('ArrowRight')
  key('ArrowRight')
  fire(scroller, 'copy', { clipboardData: clip })
  R.copiedAgain = S.sel.copied !== null
  key('Enter')
  R.editDrops = [S.edit !== null, S.sel.copied === null, classes(5, 2).includes('is-cp')]
  fire(q('.eg-ed'), 'keydown', { key: 'Escape' })
  // 칸 편집기 안의 복사는 브라우저 기본(그리드 글을 싣지 않는다).
  key('Enter')
  store['text/plain'] = 'untouched'
  const inEditor = fire(q('.eg-ed'), 'copy', { clipboardData: clip })
  R.editor = [inEditor.defaultPrevented, store['text/plain']]
  fire(q('.eg-ed'), 'keydown', { key: 'Escape' })
  // Ctrl+X 는 잘라내지 않고 안내만.
  const cut = key('x', { ctrlKey: true })
  R.cut = [cut.defaultPrevented, note(), S.box.ops.length]
  process.stdout.write(JSON.stringify(R))
"""
    result = _run(body, _payloads())
    assert result["keydown"] == {"prevented": False, "cleared": 1}
    frame = _frame()
    lines = []
    for row in range(4):
        labels = [
            "공정 영" if row == 0 else str(frame.loc[row, "공정"]),
            str(frame.loc[row, "구분"]),
        ]
        values = ["" if pd.isna(frame.loc[row, m]) else str(frame.loc[row, m]) for m in MONTHS[:2]]
        lines.append("\t".join([*labels, *values]))
    copy = result["copy"]
    assert copy["prevented"] and copy["last"] == 16
    assert copy["text"] == "\r\n".join(lines)
    # percent 는 분수 원값, 빈칸은 빈 글.
    assert "\t0.51\r\n" in copy["text"] and copy["text"].endswith("\t0.53\t")
    assert copy["note"] == "16칸 복사함 — 붙여넣을 칸에서 Ctrl+V"
    marquee = result["marquee"]
    assert {"is-cp", "cp-t", "cp-l"} <= set(marquee["corner"])
    assert "cp-b" not in marquee["corner"] and "cp-r" not in marquee["corner"]
    assert marquee["inner"] == ["in-rng", "is-sel", "is-cp"]
    assert {"is-cp", "cp-b", "cp-r"} <= set(marquee["edge"]) and marquee["outside"] == []
    assert result["kept"]
    assert result["escape"] == [True, False, False]
    assert result["copiedAgain"] and result["editDrops"] == [True, True, False]
    assert result["editor"] == [False, "untouched"]
    assert result["cut"] == [True, "잘라내기는 없습니다 — 복사(Ctrl+C) 뒤 Delete 로 지우세요", 0]


def test_delete_clears_the_value_cells_of_the_selection() -> None:
    body = r"""
  key('Home')
  key('ArrowDown', { shiftKey: true })
  key('ArrowRight', { shiftKey: true })
  key('ArrowRight', { shiftKey: true })
  key('ArrowRight', { shiftKey: true })
  const del = key('Delete')
  R.clear = { prevented: del.defaultPrevented, op: lastOp(), note: note() }
  R.preview = [cell(0, 2).textContent, cell(1, 3).textContent,
    cell(0, 2).classList.contains('is-changed')]
  key('Home')
  key('ArrowDown', { shiftKey: true })
  const ops = S.box.ops.length
  key('Delete')
  R.keysOnly = [S.box.ops.length === ops, note()]
  process.stdout.write(JSON.stringify(R))
"""
    result = _run(body, _payloads())
    clear = result["clear"]
    assert clear["prevented"]
    op = clear["op"]
    assert op["op"] == "clear" and op["table"] == "RQ_DEMO" and op["gen"] == "g1"
    assert op["rows"] == ["DEMO_P00\x1f양산", "DEMO_P01\x1fER"]
    assert op["cols"] == ["202701", "202702"], "분류 칸은 비우지 않는다"
    assert clear["note"] == "4칸 비움"
    assert result["preview"] == ["", "", True]
    assert result["keysOnly"] == [True, "분류 칸은 고칠 수 없습니다"]


def test_paste_spreads_a_block_from_the_anchor_and_selects_it() -> None:
    body = r"""
  const paste = (text) => fire(scroller, 'paste', { clipboardData: { getData: () => text } })
  key('ArrowDown')
  key('ArrowRight')
  key('ArrowDown', { shiftKey: true })
  const first = paste('55%\t0.6\r\n"0.7"\tabc\r\n')
  R.block = { prevented: first.defaultPrevented, op: lastOp(), range: range(), note: note(),
    texts: [cell(1, 3).textContent, cell(2, 4).textContent,
      cell(2, 4).classList.contains('is-error')] }
  // 분류 칸에서 시작한 덩어리 — 분류 칸 몫은 건너뛴다.
  key('Home')
  paste('X\tY\t0.8\t0.9')
  R.keys = { op: lastOp(), note: note(), range: range() }
  // 표 끝을 넘은 칸은 버린다.
  key('End', { ctrlKey: true })
  paste('0.1\t0.2\r\n0.3\t0.4')
  R.end = { op: lastOp(), note: note() }
  // 분류 칸뿐이면 보내지 않는다.
  key('Home', { ctrlKey: true })
  const ops = S.box.ops.length
  paste('X')
  R.locked = [S.box.ops.length === ops, note()]
  // 빈 클립보드(그림 등)는 아무것도 하지 않는다.
  key('ArrowRight')
  key('ArrowRight')
  paste('')
  R.empty = S.box.ops.length === ops
  process.stdout.write(JSON.stringify(R))
"""
    result = _run(body, _payloads())
    block = result["block"]
    assert block["prevented"]
    op = block["op"]
    assert op["op"] == "write"
    assert op["rows"] == ["DEMO_P01\x1fER", "DEMO_P02\x1f양산"]
    assert op["cols"] == ["202702", "202703"]
    assert op["values"] == [["55%", "0.6"], ["0.7", "abc"]]
    assert block["range"] == {"r0": 1, "r1": 2, "c0": 3, "c1": 4}
    assert block["note"] == "4칸 붙여넣음"
    assert block["texts"] == ["55%", "abc", True], "곧바로 미리보기 — 못 읽은 칸은 빨강"
    keys = result["keys"]
    assert keys["op"]["cols"] == ["202701", "202702"] and keys["op"]["values"] == [["0.8", "0.9"]]
    assert keys["note"] == "2칸 붙여넣음 · 분류 칸 2칸은 건너뛰었습니다"
    assert keys["op"]["rows"] == ["DEMO_P01\x1fER"]
    assert keys["range"] == {"r0": 1, "r1": 1, "c0": 0, "c1": 3}
    end = result["end"]
    assert end["op"]["rows"] == [f"DEMO_P{ROWS - 1:02d}\x1fER"] and end["op"]["cols"] == ["202704"]
    assert end["op"]["values"] == [["0.1"]]
    assert end["note"] == "1칸 붙여넣음 · 표 끝을 넘은 3칸은 버렸습니다"
    assert result["locked"] == [True, "분류 칸은 고칠 수 없습니다"]
    assert result["empty"]


def test_paste_respects_the_cell_limit_and_yields_to_a_fill_paste_hook() -> None:
    body = r"""
  const paste = (text) => fire(scroller, 'paste', { clipboardData: { getData: () => text } })
  paste('1\t2\r\n3\t4')
  R.limit = [S.box.ops.length, note()]
  let taken = null
  feature({ name: 'fill', paste(state, matrix) { taken = matrix; return true } })
  const event = paste('5\t6')
  R.hook = [taken, S.box.ops.length, event.defaultPrevented]
  process.stdout.write(JSON.stringify(R))
"""
    result = _run(body, _payloads(paste_limit=3))
    count, text = result["limit"]
    assert count == 0 and text.startswith("한 번에 붙여넣을 수 있는 칸은")
    assert result["hook"] == [[["5", "6"]], 0, True]


def test_cleanup_ends_a_drag_and_releases_the_select_listeners() -> None:
    body = r"""
  point('pointerdown', 1, 3)
  const listeners = S.sel.listeners.length
  cleanup()
  R.after = { listeners, left: S.sel.listeners.length, drag: S.sel.drag,
    copyListeners: (scroller.listeners.copy || []).length,
    pasteListeners: (scroller.listeners.paste || []).length }
  process.stdout.write(JSON.stringify(R))
"""
    result = _run(body, _payloads())
    assert result["after"] == {
        "listeners": 7,
        "left": 0,
        "drag": None,
        "copyListeners": 0,
        "pasteListeners": 0,
    }
