# Purpose: 범용 편집 그리드 도구 막대(eg_toolbar)의 순수 구획과 가짜 DOM 동작을 본다.

"""도구 막대(TOOLBAR) 가지 몫(편집 표 횡전개 명세 9-1·9-5·9-7·13-1). 순수 구획 `// <eg-search>`·
`// <eg-summary>`·`// <eg-width>` 은 node 로 떼어 돌리고(`tests/edit_grid_node.py`), 동작은 등록 JS
전체를 가짜 DOM 에 마운트해 찾기·되돌리기 단추·요약·칸 폭(맞춤·끌기·저장)·적용 전 변경 서랍·전체
화면을 본다. 실제 top layer·글 폭·느린 회차는 사본 앱 브라우저로 잰다(명세 13-5 TOOLBAR)."""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd
from edit_grid_node import FAKE_DOM, RUNNER_HEAD, asset, mountable, run_node, sections

from capa_simulation.components import edit_grid
from capa_simulation.services import edit_grid as eg
from capa_simulation.services.edit_grid_payload import build_base, encode_base, encode_feed

TOOLBAR = asset("eg_toolbar.js")
TOOLBAR_CSS = asset("eg_toolbar.css")
# 색이 아니라 자리 · 크기 값 — 페이지가 내려보낸다(`reference_grid.ONE_LINE_STYLE`).
LAYOUT_VARS = {"toolbar-justify", "toolbar-reserve", "tb-height", "tb-radius", "tb-font"}
PURE = asset("eg_pure.js")
CORE = asset("eg_core.js")
REGISTERED_JS = edit_grid.registered_js()


def _pure(*names: str) -> str:
    return sections(PURE, ("eg-format", "eg-nav")) + "\n" + sections(TOOLBAR, names)


# ------------------------------------------------------------------ 자산 글


def test_the_toolbar_feature_registers_every_hook_it_needs() -> None:
    hook = TOOLBAR[TOOLBAR.rindex("feature({") :]
    assert "name: 'toolbar'" in hook
    for name in (
        "init",
        "keydown",
        "pointerdown",
        "paintCell",
        "paintOverlay",
        "onFeed",
        "onSelect",
        "onLayout",
        "cleanup",
    ):
        assert re.search(rf"\b{name}: tb[A-Z]", hook), name


def test_the_core_functions_the_toolbar_borrows_still_exist() -> None:
    """고정 API 밖에서 부르는 core 함수 둘 — 이름이 바뀌면 이 시험이 먼저 깨진다."""
    for name in ("egLayout(S)", "egHistory(S, kind)"):
        assert f"function {name}" in CORE, name
        assert name.split("(")[0] + "(S" in TOOLBAR, name


def test_every_toolbar_text_is_shipped_by_python() -> None:
    """도구 막대 글은 껍데기 texts 로 온다(JS 의 글은 texts 가 오기 전 기본값)."""
    spec = eg.GridSpec("RQ_DEMO", "효율", ("공정",), ("202701",), eg.ValueFormat("percent", 2))
    texts = edit_grid.texts(spec, changes_label="적용 전 변경")
    used = set(re.findall(r"tbText\(S, '([A-Za-z]+)'", TOOLBAR))
    assert used, "tbText 를 쓰지 않는다"
    missing = used - set(texts)
    assert not missing, missing
    for name in used:
        assert isinstance(texts[name], str) and texts[name], name
    assert texts["changesEmpty"] == "적용 전 변경이 없습니다"
    assert texts["fullLabel"] == "효율 전체 화면"
    assert "{count}" in texts["summaryCount"] and "{n}" in texts["fitDone"]


def test_the_toolbar_css_draws_with_palette_colours_only() -> None:
    used = set(re.findall(r"var\(--eg-([a-z-]+)", TOOLBAR_CSS)) - LAYOUT_VARS
    assert used and used <= set(edit_grid.palette()), used - set(edit_grid.palette())
    assert "/*" not in TOOLBAR_CSS
    assert not re.search(r"#[0-9A-Fa-f]{3,8}\b", TOOLBAR_CSS)
    assert "rgb(" not in TOOLBAR_CSS and "hsl(" not in TOOLBAR_CSS
    # 찾기 일치 칠은 고른 범위 칠에 진다(명세 10-1 — 고른 범위가 찾기 일치 위).
    assert ".eg-c.is-match:not(.is-sel)" in TOOLBAR_CSS


def test_the_page_can_stand_the_toolbar_beside_its_action_row_but_fullscreen_stays_as_it_was() -> (
    None
):
    """표 위 줄을 합치는 값은 페이지가 CSS 변수로 내려보낸다(변수가 없으면 옛 꼴 그대로). 전체 화면
    창에는 곁에 설 단추 줄이 없어 그 창이 값을 되돌린다."""
    bar = TOOLBAR_CSS[TOOLBAR_CSS.index(".eg-toolbar {") :]
    assert "justify-content: var(--eg-toolbar-justify, flex-start)" in bar
    assert "padding-left: var(--eg-toolbar-reserve, 0)" in bar
    assert "height: var(--eg-tb-height, 28px)" in TOOLBAR_CSS
    dialog = TOOLBAR_CSS[TOOLBAR_CSS.index(".eg-dialog {") :]
    dialog = dialog[: dialog.index("}")]
    for name in LAYOUT_VARS:
        assert f"--eg-{name}:" in dialog, name


def test_the_status_line_shows_the_edit_scope_the_feed_carries() -> None:
    """편집 범위 글은 표 아래 상태 줄이다 — 표 위 줄을 먹지 않고, 고른 칸 요약과 같은 줄에 선다.
    좁아 말줄임이 되면 풍선으로 다 읽는다."""
    body = r"""
  const scope = q('.eg-scope')
  R.home = scope.parentNode === S.dom.status
  R.first = [scope.textContent, scope.title]
  sendFeed({ ...input.feed, scope: input.feed.scope + ' · 필터로 1개 행 표시' })
  R.next = [scope.textContent, scope.title]
  sendFeed({ ...input.feed, scope: null })
  R.gone = [scope.textContent, scope.title]
"""
    payload = _payloads()
    payload["feed"] = {
        **payload["feed"],
        "scope": "편집 범위 202601 – 202602 · 2개월 · 전체 2개 행",
    }
    result = _run(body, payload)
    assert result["home"] is True
    assert result["first"] == [payload["feed"]["scope"]] * 2
    assert (
        result["next"][0].endswith("필터로 1개 행 표시") and result["next"][0] == result["next"][1]
    )
    assert result["gone"] == ["", ""]


def test_the_edit_scope_gives_way_before_the_cell_error_at_the_end_of_the_status_line() -> None:
    """칸 오류 문구는 상태 줄 왼쪽 글의 맨 끝에만 있다. 편집 범위 글이 칸을 버티면 좁은 창에서
    그 문구가 말줄임으로 사라진다 — 범위 글이 먼저 줄어야 하고, 그래도 잘리면 풍선으로 읽는다."""
    scope = TOOLBAR_CSS[TOOLBAR_CSS.index(".eg-scope {") :]
    scope = scope[: scope.index("}")]
    grow, shrink, basis = re.search(r"flex: (\S+) (\S+) (\S+);", scope).groups()  # type: ignore[union-attr]
    # 왼쪽 글(`flex: 1 1 auto`)이 0.1px 만 줄어도 말줄임이 서므로 비율이 커야 한다.
    assert (grow, basis) == ("0", "auto") and int(shrink) >= 10_000
    assert "min-width: 0" in scope
    # 빈 칸은 접는다 — 남으면 줄 사이 틈(12px)마다 왼쪽 글이 좁아진다.
    assert ".eg-scope:empty {\n  display: none;" in TOOLBAR_CSS
    core_css = asset("eg_core.css")
    assert ".eg-note:empty,\n.eg-summary:empty {\n  display: none;" in core_css

    body = r"""
  const where = q('.eg-where')
  sendFeed(input.feed2)
  await tick(5)
  scroller.focus()
  key(scroller, 'ArrowRight')
  key(scroller, 'ArrowRight')
  key(scroller, 'ArrowDown')
  key(scroller, 'ArrowDown')
  await tick(5)
  R.where = [where.textContent, where.title]
"""
    draft: eg.DraftState = {"cells": {}, "bad": {"DEMO_P02\x1f양산": {"202703": ("85", "max")}}}
    text, title = _run(body, _payloads(draft=draft))["where"]
    assert " — " in text and title == text


def test_fullscreen_is_a_dialog_in_the_shadow_root_not_a_fixed_overlay() -> None:
    """전체 화면은 그림자 DOM 안 `<dialog>.showModal()` — `position: fixed` 덮개는 긴 회차에
    opacity 0.33 으로 머리 띠·사이드바 밑에 묻힌다(D2). 브라우저 전체 화면 API 도 쓰지 않는다."""
    assert "tbEl('dialog', 'eg-dialog')" in TOOLBAR and "dialog.showModal()" in TOOLBAR
    assert "S.host.appendChild(dialog)" in TOOLBAR
    assert "requestFullscreen" not in TOOLBAR
    for text in (TOOLBAR, TOOLBAR_CSS):
        assert not re.search(r"position:\s*fixed", text)
    cancel = TOOLBAR[TOOLBAR.index("tbListen(S, dialog, 'cancel'") :]
    assert "event.preventDefault()" in cancel[: cancel.index("})")]


def test_the_toolbar_sends_only_ops_python_knows() -> None:
    sent = set(re.findall(r"\bop: '([a-z]+)'", TOOLBAR))
    assert sent == {"revert"} and sent <= eg.OP_NAMES
    assert "setState" not in TOOLBAR and "setTrigger" not in TOOLBAR


# ------------------------------------------------------------------ node — 순수 구획


def test_search_finds_cells_in_view_order_and_steps_around_the_ends() -> None:
    runner = (
        RUNNER_HEAD
        + """
const list = searchCells(3, 4, (r, c) => (r + c) % 3 === 0)
done({
  needle: [searchNeedle('  DeMo '), searchNeedle(null), searchNeedle(12)],
  has: [searchHas('DEMO_P01', 'p0'), searchHas('공정 영', '영'), searchHas('', ''),
    searchHas('abc', ''), searchHas(85, '8')],
  list,
  index: [searchIndex(list, 3), searchIndex(list, 4), searchIndex(list, 0), searchIndex(list, 11)],
  next: [searchStep(list, -1, 1, 0), searchStep(list, -1, 1, 1), searchStep(list, -1, 1, 11),
    searchStep(list, 3, 1, 0), searchStep(list, 0, 1, 99)],
  prev: [searchStep(list, -1, -1, 4), searchStep(list, -1, -1, 0), searchStep(list, 0, -1, 0),
    searchStep(list, 2, -1, 0)],
  none: [searchStep(new Int32Array(0), -1, 1, 0), searchStep(new Int32Array(0), 0, -1, 0)],
})
"""
    )
    result = run_node(_pure("eg-search"), runner, {})
    assert result["needle"] == ["demo", "", "12"]
    assert result["has"] == [True, True, False, False, True]
    # (r + c) % 3 === 0 — 줄 우선 차례 칸 번호: (0,0) (0,3) (1,2) (2,1).
    assert result["list"] == [0, 3, 6, 9]
    assert result["index"] == [1, -1, 0, -1]
    # 다음: from 이나 그 뒤의 첫 일치, 끝을 넘으면 처음 — 일치 자리에서는 한 걸음(끝에서 처음으로).
    assert result["next"] == [0, 1, 0, 0, 1]
    # 이전: from 앞의 마지막 일치, 처음 앞이면 끝.
    assert result["prev"] == [1, 3, 3, 1]
    assert result["none"] == [-1, -1]


def test_the_summary_counts_values_and_formats_sum_and_average_like_the_table() -> None:
    runner = (
        RUNNER_HEAD
        + """
const run = (values, cells, valueCells, fmt) => {
  const acc = summaryStart()
  for (const value of values) summaryAdd(acc, value)
  return [acc, summaryText(acc, cells, valueCells, fmt, input.texts)]
}
const percent = { kind: 'percent', digits: 2 }
const days = { kind: 'fixed', digits: 0, int: true }
const units = { kind: 'fixed', digits: 2 }
const upeh = { kind: 'sig', digits: 6 }
done({
  mixed: run([0.5, null, '85', NaN, 0.51, '', 0.52], 7, 7, percent),
  days: run([30, 31], 2, 2, days),
  daysWhole: run([30, 30], 2, 2, days),
  units: run([1, 2, 0.5], 3, 3, units),
  upeh: run([1234.5, 100], 2, 2, upeh),
  upehBig: run([123456.7, 900000], 2, 2, upeh),
  upehHuge: run(Array.from({ length: 79800 }, () => 293.346), 79800, 79800, upeh),
  big: run(Array.from({ length: 1200 }, () => 1000), 1200, 1200, days),
  textOnly: run(['abc', null], 2, 2, percent),
  keysOnly: run([], 6, 0, percent),
  single: run([0.5], 1, 1, percent),
  fallback: (() => {
    const acc = summaryStart()
    summaryAdd(acc, 2)
    summaryAdd(acc, 4)
    return summaryText(acc, 2, 2, days, null)
  })(),
})
"""
    )
    spec = eg.GridSpec("RQ_DEMO", "효율", ("공정",), ("202701",), eg.ValueFormat("percent", 2))
    texts = edit_grid.texts(spec, changes_label="적용 전 변경")
    result = run_node(_pure("eg-summary"), runner, {"texts": texts})
    acc, text = result["mixed"]
    # 비지 않은 칸 4개(수 3 + 못 읽은 글 1), 합계·평균은 수 칸만.
    assert (acc["count"], acc["nums"]) == (4, 3) and abs(acc["sum"] - 1.53) < 1e-12
    assert text == "개수 4 · 합계 153% · 평균 51%"
    assert result["days"][1] == "개수 2 · 합계 61 · 평균 30.5"
    assert result["daysWhole"][1] == "개수 2 · 합계 60 · 평균 30"
    assert result["units"][1] == "개수 3 · 합계 3.50 · 평균 1.17"
    assert result["upeh"][1] == "개수 2 · 합계 1,334.5 · 평균 667.25"
    # 유효숫자 6자리 형식은 1,000,000 이상에서 지수 꼴(1.02346e+06)이 된다 — 요약은 천 단위 +
    # 소수 둘째 자리.
    assert result["upehBig"][1] == "개수 2 · 합계 1,023,456.7 · 평균 511,728"
    assert result["upehHuge"][1].startswith("개수 79,800 · 합계 23,409,0")
    assert "e+" not in result["upehHuge"][1] and result["upehHuge"][1].endswith(" · 평균 293.346")
    assert result["big"][1] == "개수 1,200 · 합계 1,200,000 · 평균 1,000"
    assert result["textOnly"][1] == "개수 1"
    assert result["keysOnly"][1] == "칸 6개"
    assert result["single"][1] == ""
    assert result["fallback"] == "개수 2 · 합계 6 · 평균 3"


def test_widths_fit_text_clamp_drags_and_survive_storage_round_trips() -> None:
    runner = (
        RUNNER_HEAD
        + """
const measured = []
const measure = (text, head) => {
  measured.push(text)
  return text.length * (head ? 8 : 7)
}
const fit = (texts, head, numeric) => {
  measured.length = 0
  const width = fitWidth(texts, measure, head, 16, 30, 40, 160, numeric)
  return [width, measured.slice()]
}
const store = (() => {
  const data = {}
  return { data, getItem: (key) => (key in data ? data[key] : null),
    setItem: (key, value) => { data[key] = String(value) } }
})()
const names = widthNames([{ name: '공정' }, { name: '구분' }], ['202701', '202702'])
const key = widthStoreKey('reference_grid', 'RQ_RUN_DAY')
const wrote = writeWidths(store, key, names, [120.4, 60, 81, 90])
const back = readWidths(store, key, names, [104, 104, 80, 80], 40, 480)
// 월이 밀린 표 — 같은 이름 칸만 되찾고 나머지는 기본 폭.
const shifted = readWidths(store, key, widthNames([{ name: '공정' }], ['202702', '202703']),
  [104, 80, 80], 40, 480)
store.data['other'] = JSON.stringify({ 'k:공정': 9999, 'v:202701': -5, 'v:202702': 'x' })
const clamped = readWidths(store, 'other', names, [104, 104, 80, 80], 40, 480)
store.data['broken'] = '{not json'
const throwing = { getItem() { throw new Error('denied') }, setItem() { throw new Error('full') } }
done({
  head: fit(['A', 'BB'], '202701', true),
  long: fit(['DEMO_LONG_PROCESS_NAME_THAT_IS_VERY_LONG_INDEED'], '공정', false),
  narrow: fit([''], 'x', false),
  numeric: fit(['1', '12', '1,234', '1,234', '98.75%', '100%'], 'M', true),
  text: fit(['가', '1,234,567'], 'k', false),
  drag: [dragWidth(80, 100, 160, 40, 480), dragWidth(80, 100, 0, 40, 480),
    dragWidth(80, 100, 900, 40, 480), dragWidth(80, 100, 100.6, 40, 480)],
  key, names, wrote, back, shifted, clamped,
  missing: readWidths(store, 'none', names, [1, 2, 3, 4], 40, 480),
  broken: readWidths(store, 'broken', names, [1, 2, 3, 4], 40, 480),
  denied: [readWidths(throwing, key, names, [1, 2, 3, 4], 40, 480),
    writeWidths(throwing, key, names, [1, 2, 3, 4]), writeWidths(null, key, names, [1, 2, 3, 4]),
    readWidths(null, key, names, [1, 2, 3, 4], 40, 480)],
})
"""
    )
    result = run_node(_pure("eg-width"), runner, {})
    # 머리 6글자 × 8 + 30 = 78 이 칸 글보다 넓다 — 머리가 정한다.
    assert result["head"][0] == 78
    # 상한 160px(열쇠 칸 맞춤 상한).
    assert result["long"][0] == 160
    # 하한 40px — 빈 글은 재지 않는다.
    assert result["narrow"] == [40, ["x"]]
    width, measured = result["numeric"]
    # 수 칸은 가장 긴 글(6자)보다 두 글자 넘게 짧은 글은 재지 않고, 같은 글은 한 번만 잰다.
    assert width == 6 * 7 + 16 and measured == ["M", "1,234", "98.75%", "100%"]
    assert result["text"][0] == 9 * 7 + 16 and len(result["text"][1]) == 3
    assert result["drag"] == [140, 40, 480, 81]
    assert result["key"] == "capa-edit-grid-v1:reference_grid:RQ_RUN_DAY:widths"
    assert result["names"] == ["k:공정", "k:구분", "v:202701", "v:202702"]
    assert result["wrote"] is True
    assert result["back"] == [120, 60, 81, 90]
    assert result["shifted"] == [120, 90, 80]
    assert result["clamped"] == [480, 104, 80, 80]
    assert result["missing"] is None and result["broken"] is None
    assert result["denied"] == [None, False, False, None]


# ------------------------------------------------------------------ 가짜 DOM — 등록 JS 전체

MONTHS = ("202701", "202702", "202703", "202704")
SPEC = eg.GridSpec(
    "RQ_DEMO",
    "효율",
    ("공정", "구분"),
    MONTHS,
    eg.ValueFormat("percent", 2, max_value=1.0),
)


def _frame(rows: int = 60) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "공정": [f"DEMO_P{k:02d}" for k in range(rows)],
            "구분": ["양산" if k % 2 == 0 else "ER" for k in range(rows)],
        }
    )
    for column, month in enumerate(MONTHS):
        frame[month] = [round(0.5 + ((k + column) % 10) / 100, 4) for k in range(rows)]
    frame.loc[3, MONTHS[1]] = np.nan
    return frame


def _step() -> eg.Step:
    return {"rows": (), "cols": (), "before": (), "after": ()}


def _payloads(
    *,
    rows: int = 60,
    draft: eg.DraftState | None = None,
    undo: int = 0,
    redo: int = 0,
    filters: dict[int, list[int]] | None = None,
) -> dict[str, Any]:
    frame = _frame(rows)
    base = build_base(frame, SPEC, {"공정": {"DEMO_P00": "공정 영"}})
    shell = encode_base(
        base.body,
        host="demo_grid",
        base_key="k1",
        texts=edit_grid.texts(SPEC, changes_label="적용 전 변경"),
        palette={"text": "ink"},
        row_height=30,
    )
    history: eg.HistoryState = {"gen": "g1", "undo": [_step()] * undo, "redo": [_step()] * redo}
    feed = encode_feed(
        base.index,
        None,
        {"gen": "g1", "undo": [], "redo": []},
        host="demo_grid",
        base_key="k1",
        acks={},
        toast=None,
    )
    feed2 = encode_feed(
        base.index,
        draft,
        history,
        host="demo_grid",
        base_key="k1",
        acks={},
        toast=None,
        filters=filters,
    )
    return {"shell": shell, "feed": feed, "feed2": feed2}


# 가짜 DOM 에 없는 것 — 대화 상자(showModal·close)·insertBefore·input.select·글 폭 재는
# canvas·브라우저 저장소.
PRELUDE = r"""
FakeNode.prototype.insertBefore = function (child, ref) {
  const old = child.parentNode
  if (old) old.children = old.children.filter((item) => item !== child)
  child.parentNode = this
  const at = ref ? this.children.indexOf(ref) : -1
  if (at < 0) this.children.push(child)
  else this.children.splice(at, 0, child)
  return child
}
FakeNode.prototype.showModal = function () {
  this.open = true
  this.modals = (this.modals || 0) + 1
}
FakeNode.prototype.close = function () {
  this.open = false
  fire(this, 'close')
}
FakeNode.prototype.select = function () {
  this.selectedAll = true
}
const makeNode = document.createElement
let canvasOn = Boolean(input.canvas)
document.createElement = (tag) => {
  const node = makeNode(tag)
  if (tag === 'canvas' && canvasOn) {
    node.getContext = () => ({ font: '', measureText(text) {
      return { width: String(text).length * (this.font.startsWith('700') ? 8 : 7) } } })
  }
  return node
}
const storage = (() => {
  const data = {}
  return { data, getItem: (key) => (key in data ? data[key] : null),
    setItem: (key, value) => { data[key] = String(value) } }
})()
if (input.stored) Object.assign(storage.data, input.stored)
window.localStorage = storage
"""

MOUNT = r"""
const sent = []
const mountAt = (shell) => {
  const parentElement = new FakeNode('div')
  const host = parentElement.appendChild(new FakeNode('div'))
  host.setAttribute('data-eg-root', '')
  host.className = 'eg'
  const cleanup = globalThis.__mount({
    data: shell, parentElement,
    setStateValue: (name, value) => sent.push([name, JSON.parse(JSON.stringify(value))]),
  })
  return { host, cleanup, S: host.__eg }
}
const sendFeed = (feed) => {
  const store = (window.__capaEditGrid = window.__capaEditGrid || {})
  ;(store[feed.host] = store[feed.host] || {}).feed = feed
  window.dispatchEvent(new CustomEvent('capa-edit-grid', { detail: feed.host }))
}
sendFeed(input.feed)
const { host, cleanup, S } = mountAt(input.shell)
const q = (selector) => host.querySelector(selector)
const scroller = q('.eg-scroll')
const lineOf = (r) => S.dom.body.children.find((line) => Number(line.dataset.r) === r)
const cell = (r, c) => lineOf(r).children[c]
const has = (r, c, name) => cell(r, c).classList.contains(name)
const key = (target, name, extra) => fire(target, 'keydown', Object.assign({ key: name }, extra))
const click = (node) => fire(node, 'click')
const range = () => S.range()
const note = () => q('.eg-note').textContent
const lastSent = () => (sent.length ? sent[sent.length - 1][1].ops : [])
const tb = () => S.tb.dom
const R = {}
"""


def _run(body: str, payload: dict[str, Any]) -> Any:
    source = FAKE_DOM + mountable(REGISTERED_JS)
    runner = (
        "const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))\n"
        + PRELUDE
        + MOUNT
        + "\n;(async () => {\n"
        + body
        + "\nprocess.stdout.write(JSON.stringify(R))\n})()\n"
    )
    return run_node(source, runner, payload)


def test_the_toolbar_is_built_with_labels_from_the_shell() -> None:
    body = r"""
  const bar = q('.eg-toolbar')
  R.bar = { role: bar.getAttribute('role'), label: bar.getAttribute('aria-label'),
    kids: bar.children.map((node) => node.className) }
  const d = tb()
  R.find = { placeholder: d.input.placeholder, label: d.input.getAttribute('aria-label'),
    prev: d.prev.getAttribute('aria-label'), next: d.next.getAttribute('aria-label'),
    keys: d.input.getAttribute('aria-keyshortcuts') }
  R.buttons = [d.undo, d.redo, d.fit, d.changes, d.full].map((node) => [node.textContent,
    node.getAttribute('aria-disabled'), node.getAttribute('aria-pressed'), node.title,
    node.getAttribute('aria-label')])
  R.findShown = d.input.parentNode.classList.contains('has-q')
  d.input.value = 'p'
  fire(d.input, 'input')
  R.findTyped = d.input.parentNode.classList.contains('has-q')
  key(d.input, 'Escape')
  R.findCleared = d.input.parentNode.classList.contains('has-q')
  R.dialog = { inHost: d.dialog.parentNode === host, label: d.dialog.getAttribute('aria-label'),
    open: Boolean(d.dialog.open), registered: S.dom.dialog === d.dialog }
  R.drawer = { hidden: d.drawer.hidden, inFrame: d.drawer.parentNode === S.dom.frame }
  R.edge = q('.eg-head').children[2].children
    .find((node) => node.classList.contains('eg-edge')).title
  R.summary = q('.eg-summary').textContent
"""
    result = _run(body, _payloads())
    bar = result["bar"]
    assert bar["role"] == "toolbar" and bar["label"] == "효율 표 도구"
    assert bar["kids"] == [
        "eg-tb-find",
        "eg-tb-sep",
        "eg-tb-btn eg-tb-glyph eg-tb-undo is-off",
        "eg-tb-btn eg-tb-glyph eg-tb-redo is-off",
        "eg-tb-sep",
        "eg-tb-btn eg-tb-glyph eg-tb-fit",
        "eg-tb-btn eg-tb-changes",
        "eg-tb-btn eg-tb-glyph eg-tb-full",
    ]
    assert result["find"] == {
        "placeholder": "찾기",
        "label": "표에서 찾기 (Ctrl+F) — Enter 다음 · Shift+Enter 이전 · Esc 지움",
        "prev": "이전 일치 (Shift+Enter)",
        "next": "다음 일치 (Enter)",
        "keys": "Control+F",
    }
    undo, redo, fit, changes, full = result["buttons"]
    # 그림 단추(글은 Material Symbols 이름) — 이름은 aria-label, 풍선은 이름 · 단축키 · 하는 일.
    # feed 의 되돌리기·다시 실행 수가 0 — 꺼짐(초점은 남도록 aria-disabled).
    assert undo == ["undo", "true", None, "되돌리기 (Ctrl+Z)", "되돌리기"]
    assert redo == ["redo", "true", None, "다시 실행 (Ctrl+Y)", "다시 실행"]
    assert fit[0] == "fit_width" and fit[4] == "칸 폭 맞춤"
    assert fit[3].startswith("칸 폭 맞춤 — 모든 칸 폭을 글에 맞춥니다")
    assert changes[:3] == ["적용 전 변경 (0)", None, "false"]
    assert full == ["fullscreen", None, "false", "전체 화면", "전체 화면"]
    # 위아래 화살표 · 찾은 수는 찾는 글이 있을 때만(Esc 로 지우면 다시 숨는다).
    assert (result["findShown"], result["findTyped"], result["findCleared"]) == (
        False,
        True,
        False,
    )
    assert result["dialog"] == {
        "inHost": True,
        "label": "효율 전체 화면",
        "open": False,
        "registered": True,
    }
    assert result["drawer"] == {"hidden": True, "inFrame": True}
    assert result["edge"] == "끌어 칸 폭 바꾸기 · 두 번 눌러 맞춤"
    assert result["summary"] == ""


def test_find_highlights_matches_steps_with_enter_and_wraps() -> None:
    body = r"""
  const d = tb()
  // Ctrl+F 는 그리드 초점에서 찾기 칸으로(브라우저 찾기를 막는다).
  const ctrlF = key(scroller, 'f', { ctrlKey: true })
  R.ctrlF = [ctrlF.defaultPrevented, document.activeElement === d.input,
    Boolean(d.input.selectedAll)]
  d.input.value = 'p0'
  fire(d.input, 'input')
  R.before = d.count.textContent
  await tick(160)
  // DEMO_P01..P09 의 공정 칸(P00 은 표시명 「공정 영」) — 지금 칸(0, 2) 뒤의 첫 일치로 간다.
  R.typed = { count: d.count.textContent, anchor: Object.assign({}, S.anchor),
    list: Array.from(S.tb.find.list), focus: document.activeElement === d.input }
  R.marks = { now: [has(1, 0, 'is-match'), has(1, 0, 'is-match-now')],
    other: [has(2, 0, 'is-match'), has(2, 0, 'is-match-now')], none: has(0, 0, 'is-match'),
    value: has(1, 2, 'is-match') }
  const enter = key(d.input, 'Enter')
  R.enter = [enter.defaultPrevented, S.anchor.r, d.count.textContent,
    has(1, 0, 'is-match-now'), has(2, 0, 'is-match-now')]
  key(d.input, 'Enter', { shiftKey: true })
  R.back = [S.anchor.r, d.count.textContent]
  key(d.input, 'Enter', { shiftKey: true })
  R.wrapBack = [S.anchor.r, d.count.textContent]
  key(d.input, 'Enter')
  R.wrapNext = [S.anchor.r, d.count.textContent]
  click(d.next)
  R.button = [S.anchor.r, d.count.textContent]
  // F3 · Shift+F3 는 그리드 초점에서.
  const f3 = key(scroller, 'F3')
  R.f3 = [f3.defaultPrevented, S.anchor.r]
  key(scroller, 'F3', { shiftKey: true })
  R.shiftF3 = S.anchor.r
  // 지금 칸을 일치 밖으로 옮긴 뒤 「다음」 은 그 자리 뒤의 첫 일치.
  key(scroller, 'ArrowDown')
  key(scroller, 'ArrowDown')
  key(scroller, 'ArrowDown')
  key(scroller, 'ArrowRight')
  click(d.next)
  R.fromHere = [S.anchor.r, S.anchor.c]
  // 값 칸도 형식 적용 글로 찾는다(53% — 0.53).
  d.input.value = '53%'
  fire(d.input, 'input')
  key(d.input, 'Enter')
  R.value = { count: d.count.textContent, at: Object.assign({}, S.anchor),
    text: cell(S.anchor.r, S.anchor.c).textContent }
  d.input.value = 'zzz'
  fire(d.input, 'input')
  await tick(160)
  click(d.next)
  R.none = [d.count.textContent, note()]
  // Esc 는 찾기를 지우고 표로 초점 — 기본 동작을 막아 전체 화면으로 번지지 않는다.
  d.input.value = 'p0'
  fire(d.input, 'input')
  await tick(160)
  const esc = key(d.input, 'Escape')
  R.esc = { prevented: esc.defaultPrevented, value: d.input.value, count: d.count.textContent,
    focus: document.activeElement === scroller,
    marks: has(1, 0, 'is-match') || has(2, 0, 'is-match') }
  // 찾을 글 없이 「다음」 은 찾기 칸으로.
  click(d.next)
  R.empty = document.activeElement === d.input
  R.ms = S.tb.find.ms
"""
    result = _run(body, _payloads())
    assert result["ctrlF"] == [True, True, True]
    assert result["before"] == "", "입력 뒤 잠깐(120ms) 기다렸다 찾는다"
    typed = result["typed"]
    assert typed["count"] == "1/9" and typed["anchor"] == {"r": 1, "c": 0}
    assert typed["list"] == [k * 6 for k in range(1, 10)]
    assert typed["focus"], "찾는 동안 초점은 찾기 칸에 남는다"
    marks = result["marks"]
    assert marks == {"now": [True, True], "other": [True, False], "none": False, "value": False}
    assert result["enter"] == [True, 2, "2/9", False, True]
    assert result["back"] == [1, "1/9"]
    assert result["wrapBack"] == [9, "9/9"], "처음에서 이전은 끝으로 돈다"
    assert result["wrapNext"] == [1, "1/9"], "끝에서 다음은 처음으로 돈다"
    assert result["button"] == [2, "2/9"]
    assert result["f3"] == [True, 3] and result["shiftF3"] == 2
    assert result["fromHere"] == [6, 0]
    value = result["value"]
    assert value["text"] == "53%" and value["count"].endswith("/24")
    assert result["none"] == ["없음", "찾기 없음"]
    assert result["esc"] == {
        "prevented": True,
        "value": "",
        "count": "",
        "focus": True,
        "marks": False,
    }
    assert result["empty"]


def test_find_follows_edits_and_sorting_without_typing_again() -> None:
    body = r"""
  const d = tb()
  d.input.value = '77%'
  fire(d.input, 'input')
  await tick(160)
  R.before = d.count.textContent
  // 칸 고침(미리보기)으로 일치가 생긴다 — 다시 치지 않아도 목록이 따라온다.
  scroller.focus()
  key(scroller, 'ArrowDown')
  key(scroller, '7')
  q('.eg-ed').value = '77%'
  key(q('.eg-ed'), 'Enter')
  R.after = [d.count.textContent, has(1, 2, 'is-match')]
  // 머리 눌러 정렬(보기 차례가 바뀜) — 같은 칸이 새 자리에서 일치로 칠해진다.
  fire(q('.eg-head').children[0].children[0], 'click')
  fire(q('.eg-head').children[0].children[0], 'click')
  const r = S.view.rank[1]
  R.sorted = [r, d.count.textContent, has(r, 2, 'is-match')]
"""
    result = _run(body, _payloads())
    assert result["before"] == "없음"
    assert result["after"] == ["0/1", True]
    r, count, marked = result["sorted"]
    assert r != 1 and count == "0/1" and marked


def test_undo_and_redo_buttons_follow_the_feed_and_wait_for_the_ack() -> None:
    body = r"""
  const d = tb()
  click(d.undo)
  R.empty = [sent.length, note(), d.undo.getAttribute('aria-disabled')]
  sendFeed(input.feed2)
  R.enabled = [d.undo.getAttribute('aria-disabled'), d.redo.getAttribute('aria-disabled'),
    d.undo.classList.contains('is-off')]
  click(d.undo)
  R.sentUndo = { ops: lastSent().map((op) => op.op), busy: d.undo.getAttribute('aria-busy'),
    cls: d.undo.classList.contains('is-busy'), redoBusy: d.redo.getAttribute('aria-busy') }
  sendFeed(Object.assign({}, input.feed2, { acks: { [S.mount]: S.box.seq }, undo: 1, redo: 2 }))
  R.acked = { busy: d.undo.getAttribute('aria-busy'), box: S.box.ops.length,
    undo: d.undo.getAttribute('aria-disabled') }
  click(d.redo)
  R.sentRedo = [lastSent().map((op) => op.op), d.redo.classList.contains('is-busy')]
  // 고친 칸이 아직 가는 중이면(초안 0) 되돌리기가 켜진다 — Ctrl+Z 와 같은 셈.
  sendFeed(Object.assign({}, input.feed, { acks: { [S.mount]: S.box.seq } }))
  R.off = d.undo.getAttribute('aria-disabled')
  key(scroller, 'Delete')
  R.editing = d.undo.getAttribute('aria-disabled')
"""
    result = _run(body, _payloads(undo=2, redo=1))
    sends, text, disabled = result["empty"]
    assert sends == 0 and text == "되돌릴 편집이 없습니다" and disabled == "true"
    assert result["enabled"] == ["false", "false", False]
    assert result["sentUndo"] == {"ops": ["undo"], "busy": "true", "cls": True, "redoBusy": None}
    assert result["acked"] == {"busy": None, "box": 0, "undo": "false"}
    assert result["sentRedo"] == [["redo"], True]
    assert result["off"] == "true"
    assert result["editing"] == "false"


def test_a_mouse_click_on_a_grid_button_hands_the_keyboard_back_to_the_grid() -> None:
    """되돌리기·다시 실행·칸 폭 맞춤을 마우스로 누르면(detail ≥ 1) 초점이 표로 돌아가 이어 누르는
    Ctrl+Z 가 표에 간다. 자판으로 누르면(detail 0) 단추에 남는다."""
    body = r"""
  const d = tb()
  sendFeed(input.feed2)
  const focused = () => (document.activeElement === scroller ? 'grid'
    : document.activeElement === d.undo ? 'undo' : document.activeElement === d.redo ? 'redo'
      : document.activeElement === d.fit ? 'fit' : 'other')
  R.after = []
  for (const [name, detail] of [['undo', 1], ['redo', 2], ['fit', 1], ['undo', 0], ['fit', 0]]) {
    d[name].focus()
    fire(d[name], 'click', { detail })
    R.after.push([name, detail, focused()])
  }
  // 마우스로 되돌리기를 누른 뒤의 Ctrl+Z 는 표의 keydown 으로 간다(되돌리기 op 하나 더).
  sendFeed(Object.assign({}, input.feed2, { acks: { [S.mount]: S.box.seq } }))
  d.undo.focus()
  fire(d.undo, 'click', { detail: 1 })
  sendFeed(Object.assign({}, input.feed2, { acks: { [S.mount]: S.box.seq } }))
  const before = sent.length
  const down = fire(document.activeElement, 'keydown', { key: 'z', ctrlKey: true })
  R.chain = [focused(), sent.length - before, lastSent().map((op) => op.op), down.defaultPrevented]
"""
    result = _run(body, _payloads(undo=2, redo=1))
    assert result["after"] == [
        ["undo", 1, "grid"],
        ["redo", 2, "grid"],
        ["fit", 1, "grid"],
        ["undo", 0, "undo"],
        ["fit", 0, "fit"],
    ]
    assert result["chain"] == ["grid", 1, ["undo"], True]


def test_the_status_bar_sums_the_numeric_cells_of_the_selection() -> None:
    body = r"""
  const summary = () => q('.eg-summary').textContent
  await tick(5)
  R.single = summary()
  key(scroller, 'ArrowRight', { shiftKey: true })
  key(scroller, 'ArrowDown', { shiftKey: true })
  await tick(5)
  R.block = [summary(), S.tb.lastSummary.cells]
  // 빈칸(3행 202702)과 못 읽은 칸(2행 202703 — feed 의 오류)이 섞인 범위.
  sendFeed(input.feed2)
  key(scroller, 'ArrowDown')
  key(scroller, 'ArrowDown')
  key(scroller, 'ArrowRight')
  key(scroller, 'ArrowDown', { shiftKey: true })
  key(scroller, 'ArrowRight', { shiftKey: true })
  await tick(5)
  R.mixed = summary()
  key(scroller, 'Home')
  key(scroller, 'ArrowRight', { shiftKey: true })
  key(scroller, 'ArrowDown', { shiftKey: true })
  await tick(5)
  R.keys = summary()
  key(scroller, 'a', { ctrlKey: true })
  await tick(5)
  R.all = [summary(), S.tb.lastSummary.count, S.tb.lastSummary.valueCells]
  // 고른 칸 값을 고치면(미리보기) 요약이 따라온다.
  key(scroller, 'Home', { ctrlKey: true })
  key(scroller, 'ArrowRight')
  key(scroller, 'ArrowRight')
  key(scroller, 'ArrowDown', { shiftKey: true })
  key(scroller, 'Delete')
  await tick(5)
  R.cleared = summary()
"""
    draft: eg.DraftState = {"cells": {}, "bad": {"DEMO_P02\x1f양산": {"202703": ("85", "max")}}}
    result = _run(body, _payloads(draft=draft))
    assert result["single"] == "", "한 칸만 골랐으면 요약을 쓰지 않는다(엑셀)"
    # (0..1, 202701..202702) = 0.50 0.51 / 0.51 0.52.
    assert result["block"] == ["개수 4 · 합계 204% · 평균 51%", 4]
    # (2..3, 202702..202703) = 0.53 「85」(오류) / 빈칸 0.55 — 개수 3, 합계·평균은 수 둘만.
    assert result["mixed"] == "개수 3 · 합계 108% · 평균 54%"
    assert result["keys"] == "칸 4개"
    text, count, value_cells = result["all"]
    assert value_cells == 240 and count == 239
    assert text.startswith("개수 239 · 합계 ")
    assert result["cleared"] == "개수 0", "비운 칸(미리보기)을 따라온다"


def test_fit_measures_text_and_remembers_widths_per_table() -> None:
    body = r"""
  const storeKey = 'capa-edit-grid-v1:demo_grid:RQ_DEMO:widths'
  // 저장된 폭이 없는 첫 진입 — 맞춤을 한 번 돌리고 저장한다.
  R.first = { widths: S.widths.slice(), auto: S.tb.lastFit && S.tb.lastFit.auto,
    stored: JSON.parse(storage.data[storeKey] || 'null'), note: note() }
  // 칸 폭 맞춤 단추 — 글이 길어진 칸(편집 미리보기 포함)을 따라온다.
  scroller.focus()
  key(scroller, 'ArrowDown')
  key(scroller, '1')
  q('.eg-ed').value = '1234567890'
  key(q('.eg-ed'), 'Enter')
  click(tb().fit)
  R.fit = { widths: S.widths.slice(), note: note(), auto: S.tb.lastFit.auto,
    cols: S.tb.lastFit.cols,
    head: q('.eg-head').children[2].style.width }
  // 머리 경계 두 번 누름 — 그 칸만 맞춤.
  const widths = S.widths.slice()
  widths[1] = 200
  setWidths(S, widths)
  const edge = q('.eg-head').children[1].children.find((node) => node.classList.contains('eg-edge'))
  fire(edge, 'dblclick')
  R.one = [S.widths[1], S.tb.lastFit.cols, note()]
"""
    result = _run(body, {**_payloads(), "canvas": True})
    first = result["first"]
    # 공정: 「DEMO_P01」 8자 × 7 + 16 = 72 · 구분: 머리 「구분」 2자 × 8 + 30 = 46 ·
    # 월: 머리 6자 × 8 + 30 = 78.
    assert first["widths"] == [72, 46, 78, 78, 78, 78]
    assert first["auto"] is True and first["note"] == "", "첫 진입 맞춤은 상태 줄을 쓰지 않는다"
    assert first["stored"] == {
        "k:공정": 72,
        "k:구분": 46,
        "v:202701": 78,
        "v:202702": 78,
        "v:202703": 78,
        "v:202704": 78,
    }
    fit = result["fit"]
    # 못 읽은 글 「1234567890」 10자 × 7 + 16 = 86.
    assert fit["widths"] == [72, 46, 86, 78, 78, 78]
    assert fit["note"] == "칸 폭 맞춤 — 6칸" and fit["auto"] is False and fit["cols"] == 6
    assert fit["head"] == "86px"
    assert result["one"] == [46, 1, "칸 폭 맞춤 — 1칸"]


def test_header_edges_resize_columns_and_a_new_mount_restores_them() -> None:
    body = r"""
  const edgeOf = (c) => q('.eg-head').children[c].children
    .find((node) => node.classList.contains('eg-edge'))
  const startWidths = S.widths.slice()
  // 머리 경계 끌기 — 손이 움직여야 스크롤 칸이 손을 붙든다. 폭은 한 프레임에 한 번.
  let captured = 0
  scroller.setPointerCapture = () => { captured += 1 }
  scroller.releasePointerCapture = () => {}
  fire(edgeOf(2), 'pointerdown', { clientX: 300, pointerId: 7 })
  fire(scroller, 'pointermove', { clientX: 301, pointerId: 7 })
  R.slop = [captured, S.widths[2]]
  fire(scroller, 'pointermove', { clientX: 360, pointerId: 7 })
  R.beforeFrame = S.widths[2]
  await tick(5)
  R.dragging = [captured, S.widths[2], S.frozen]
  fire(scroller, 'pointermove', { clientX: 360, pointerId: 9 })
  fire(scroller, 'pointerup', { clientX: 380, pointerId: 7 })
  R.done = { width: S.widths[2], resize: S.tb.resize,
    stored: JSON.parse(storage.data['capa-edit-grid-v1:demo_grid:RQ_DEMO:widths'])['v:202701'],
    sort: q('.eg-head').children[2].getAttribute('aria-sort') }
  // 상한·하한.
  fire(edgeOf(3), 'pointerdown', { clientX: 0, pointerId: 1 })
  fire(scroller, 'pointermove', { clientX: 2000, pointerId: 1 })
  fire(scroller, 'pointerup', { clientX: 2000, pointerId: 1 })
  fire(edgeOf(4), 'pointerdown', { clientX: 500, pointerId: 1 })
  fire(scroller, 'pointermove', { clientX: 0, pointerId: 1 })
  fire(scroller, 'pointercancel', { pointerId: 1 })
  R.limits = [S.widths[3], S.widths[4]]
  // 끊긴 끌기(pointercancel)는 처음 폭으로 돌아간다.
  fire(edgeOf(5), 'pointerdown', { clientX: 500, pointerId: 1 })
  fire(scroller, 'pointermove', { clientX: 0, pointerId: 1 })
  await tick(5)
  const mid = S.widths[5]
  fire(scroller, 'pointercancel', { pointerId: 1 })
  R.cancel = [mid, S.widths[5]]
  // 같은 표의 새 마운트 — 저장된 폭을 되살리고(맞춤 없음) 고정 칸 수를 다시 센다.
  const other = mountAt(input.shell)
  R.restored = { widths: other.S.widths.slice(), fit: other.S.tb.lastFit, start: startWidths }
"""
    result = _run(body, {**_payloads(), "canvas": True})
    assert result["slop"] == [0, 78], "2px 안의 움직임은 끌기가 아니다"
    assert result["beforeFrame"] == 78
    captured, width, frozen = result["dragging"]
    assert captured == 1 and width == 138 and frozen == 2
    done = result["done"]
    assert done["width"] == 158 and done["resize"] is None and done["stored"] == 158
    assert done["sort"] is None, "경계 끌기는 정렬하지 않는다"
    assert result["limits"] == [480, 78], "pointercancel 은 처음 폭으로"
    assert result["cancel"] == [40, 78]
    restored = result["restored"]
    assert restored["widths"] == [72, 46, 158, 480, 78, 78]
    assert restored["fit"] is None


def test_changes_drawer_lists_old_and_new_values_goes_to_cells_and_reverts() -> None:
    body = r"""
  const d = tb()
  sendFeed(input.feed2)
  R.label = d.changes.textContent
  click(d.changes)
  const items = () => d.list.children
  R.open = { pressed: d.changes.getAttribute('aria-pressed'), hidden: d.drawer.hidden,
    frame: S.dom.frame.classList.contains('has-drawer'), title: d.title.textContent,
    rows: items().map((item) => [item.children[0].children[0].textContent,
      item.children[0].children[1].textContent, item.classList.contains('is-bad'),
      item.children[1].getAttribute('aria-label')]),
    badTitle: items()[2].children[0].children[1].children[2].title,
    more: d.more.hidden, empty: d.empty.hidden }
  // 줄을 누르면 그 칸으로 간다.
  click(items()[1].children[0])
  R.go = [Object.assign({}, S.anchor), document.activeElement === scroller]
  // ✕ 는 revert — 두 번 눌러도 ack 전에는 한 번만 보낸다.
  click(items()[0].children[1])
  click(items()[0].children[1])
  R.revert = [lastSent().filter((op) => op.op === 'revert').map((op) => [op.rows, op.cols]),
    items()[0].classList.contains('is-pending')]
  // 새 feed 가 오면 목록을 다시 짓는다.
  sendFeed(Object.assign({}, input.feed, { acks: { [S.mount]: S.box.seq } }))
  R.after = { rows: items().length, empty: d.empty.hidden, emptyText: d.empty.textContent,
    label: d.changes.textContent }
  click(d.close)
  R.closed = [d.drawer.hidden, S.dom.frame.classList.contains('has-drawer'),
    d.changes.getAttribute('aria-pressed'), document.activeElement === scroller]
"""
    draft: eg.DraftState = {
        "cells": {
            "DEMO_P00\x1f양산": {"202701": 0.9},
            "DEMO_P03\x1fER": {"202702": 0.6},
        },
        "bad": {"DEMO_P05\x1fER": {"202701": ("85", "max")}},
    }
    result = _run(body, _payloads(draft=draft))
    assert result["label"] == "적용 전 변경 (3)"
    opened = result["open"]
    assert opened["pressed"] == "true" and not opened["hidden"] and opened["frame"]
    assert opened["title"] == "적용 전 변경 3칸"
    assert opened["rows"] == [
        ["공정 영 · 양산 · 202701", "50% → 90%", False, "공정 영 · 양산 · 202701 되돌리기"],
        ["DEMO_P03 · ER · 202702", "빈칸 → 60%", False, "DEMO_P03 · ER · 202702 되돌리기"],
        ["DEMO_P05 · ER · 202701", "55% → 85", True, "DEMO_P05 · ER · 202701 되돌리기"],
    ]
    assert opened["badTitle"].startswith("100% 이하로 적습니다")
    assert opened["more"] and opened["empty"]
    assert result["go"] == [{"r": 3, "c": 3}, True]
    reverts, pending = result["revert"]
    assert reverts == [[["DEMO_P00\x1f양산"], ["202701"]]] and pending
    after = result["after"]
    assert after == {
        "rows": 0,
        "empty": False,
        "emptyText": "적용 전 변경이 없습니다",
        "label": "적용 전 변경 (0)",
    }
    assert result["closed"] == [True, False, "false", True]


def test_changes_drawer_caps_its_list_and_explains_filtered_rows() -> None:
    body = r"""
  const d = tb()
  sendFeed(input.feed2)
  click(d.changes)
  R.capped = [d.list.children.length, d.more.hidden, d.more.textContent, d.title.textContent]
  // 필터로 보기에 없는 줄은 보기 차례 뒤에 오고, 누르면 안내만.
  const last = d.list.children[d.list.children.length - 1]
  R.lastWhere = last.children[0].children[0].textContent
  const before = Object.assign({}, S.anchor)
  click(last.children[0])
  R.hidden = [note(), S.anchor.r === before.r && S.anchor.c === before.c]
"""
    rows = 140
    frame = _frame(rows)
    keys = [f"{frame.loc[k, '공정']}\x1f{frame.loc[k, '구분']}" for k in range(rows)]
    cells: dict[str, dict[str, float | None]] = {
        key: {month: 0.7 for month in MONTHS} for key in keys
    }
    draft: eg.DraftState = {"cells": cells, "bad": {}}
    probe = _payloads(rows=rows)
    mass = probe["shell"]["dims"][1].index("양산")
    result = _run(body, _payloads(rows=rows, draft=draft, filters={1: [mass]}))
    count, more_hidden, more, title = result["capped"]
    assert count == 500 and not more_hidden
    assert more == "외 60개 — 목록은 앞 500개만 보입니다"
    assert title == "적용 전 변경 560칸"
    assert " · ER · " in result["lastWhere"], "필터로 숨긴 ER 줄이 목록 뒤에 온다"
    assert result["hidden"] == ["지금 보기(필터)에 없는 줄입니다 — 표 조건을 풀면 보입니다", True]


def test_fullscreen_moves_the_grid_into_a_modal_dialog_and_esc_closes_it() -> None:
    body = r"""
  const d = tb()
  const root = S.dom.root
  scroller.scrollTop = 120
  scroller.scrollLeft = 30
  click(d.full)
  R.open = { full: S.full, open: d.dialog.open, modals: d.dialog.modals,
    inside: root.parentNode === d.dialog,
    pressed: d.full.getAttribute('aria-pressed'), text: d.full.textContent,
    label: d.full.getAttribute('aria-label'), title: d.full.title,
    scroll: [scroller.scrollTop, scroller.scrollLeft], focus: document.activeElement === scroller,
    live: q('.eg-live').textContent }
  // 칸 편집 중 Esc 는 편집만 끝낸다(편집기가 기본 동작을 막아 대화 상자 cancel 이 오지 않는다).
  key(scroller, 'Enter')
  const editEsc = key(q('.eg-ed'), 'Escape')
  R.editEsc = [editEsc.defaultPrevented, S.full, S.edit === null]
  // 복사 점선이 있으면 첫 Esc 는 점선만 지운다.
  fire(scroller, 'copy', { clipboardData: { setData() {} } })
  const first = key(scroller, 'Escape')
  R.copyEsc = [first.defaultPrevented, S.full, S.sel.copied === null]
  scroller.scrollTop = 150
  scroller.scrollLeft = 40
  const second = key(scroller, 'Escape')
  R.closed = { prevented: second.defaultPrevented, full: S.full, open: d.dialog.open,
    back: root.parentNode === host
      && host.children.indexOf(root) === host.children.indexOf(d.dialog) - 1,
    pressed: d.full.getAttribute('aria-pressed'), text: d.full.textContent,
    label: d.full.getAttribute('aria-label'),
    focus: document.activeElement === scroller, scroll: [scroller.scrollTop, scroller.scrollLeft] }
  // 바깥 초점의 Esc 는 브라우저가 대화 상자에 cancel 을 쏜다 — 막고 뿌리를 제자리로 옮겨 닫는다.
  click(d.full)
  const cancel = fire(d.dialog, 'cancel')
  R.cancel = [cancel.defaultPrevented, S.full, d.dialog.open, root.parentNode === host]
  // 브라우저가 다른 길로 닫아도(close) 뿌리를 되돌린다.
  click(d.full)
  d.dialog.close()
  R.close = [S.full, root.parentNode === host]
  // 정리 — 열린 대화 상자를 닫고 도구 막대 듣기를 걷는다.
  click(d.full)
  const listeners = S.tb.listeners.length
  cleanup()
  R.cleanup = [listeners > 10, S.tb.listeners.length, d.dialog.open, S.full,
    (scroller.listeners.pointermove || []).length]
"""
    result = _run(body, _payloads())
    opened = result["open"]
    assert opened["full"] and opened["open"] and opened["modals"] == 1 and opened["inside"]
    assert opened["pressed"] == "true" and opened["text"] == "fullscreen_exit"
    assert opened["label"] == opened["title"] == "전체 화면 닫기 (Esc)"
    assert opened["scroll"] == [120, 30], "옮겨 붙여도 스크롤 자리를 되돌린다"
    assert opened["focus"] and opened["live"] == "전체 화면"
    assert result["editEsc"] == [True, True, True]
    assert result["copyEsc"] == [True, True, True]
    closed = result["closed"]
    assert closed == {
        "prevented": True,
        "full": False,
        "open": False,
        "back": True,
        "pressed": "false",
        "text": "fullscreen",
        "label": "전체 화면",
        "focus": True,
        "scroll": [150, 40],
    }
    assert result["cancel"] == [True, False, False, True]
    assert result["close"] == [False, True]
    assert result["cleanup"] == [True, 0, False, False, 0]
