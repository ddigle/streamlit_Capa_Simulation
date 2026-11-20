# Purpose: 설비 마스터 표 자산의 출납·트리거·색 변수·데이터 글·키·팝오버 계약을 글자·node 로 본다.

"""AppTest 는 표 JS 를 돌리지 못한다. 자산 글자로 드러나는 약속(개편 명세 11장 「자산 글」)은 글자로
붙잡고, DOM 을 모르는 순수 구획(`// <grid-…>`)은 node(없으면 bun)로 떼어 돌린다 — 없으면 건너뛰고 CI
에서는 실패다. 불러오기 팝오버의 초점·Esc 는 파일 전체를 작은 가짜 DOM 에 마운트해 본다. 그 밖의
화면 동작은 사본 앱 브라우저로 본다."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from edit_grid_node import FAKE_DOM
from js_runner import run_js_json
from test_design_tokens import SMALL_TEXT_MINIMUM, contrast_ratio

from capa_simulation.components import equipment_master_grid as emg
from capa_simulation.components.app_header import PAGE_TABS_SELECTOR
from capa_simulation.design import tokens
from capa_simulation.services import equipment_grid as eg
from capa_simulation.services.space_layout_edit import natural_name_key

ASSETS = emg._ASSETS
HTML = (ASSETS / "grid.html").read_text(encoding="utf-8")
CSS = emg.registered_css()
OWN_CSS = (ASSETS / "grid.css").read_text(encoding="utf-8")
JS = emg.registered_js()
SOURCE = Path(emg.__file__).read_text(encoding="utf-8")


def test_the_editing_channel_is_one_state_value_and_triggers_are_the_declared_set() -> None:
    """편집본을 바꾸는 조작은 상태 값 `outbox` 하나로만 — 트리거는 다음 트리거에 덮여 잃을 수
    있다. 상태 값은 그 밖에 「새 호기」 초안 `draft` 하나다(편집본을 바꾸지 않는다)."""
    assert set(re.findall(r"setState\('([a-z]+)'", JS)) == set(emg.STATE_NAMES)
    assert set(emg.STATE_NAMES) == {"outbox", "draft"}
    assert "setStateValue(" not in JS.replace("setStateValue, setTriggerValue", "")
    sent = set(re.findall(r"setTrigger\('([a-z]+)'", JS)) | {"load"}
    assert sent == set(emg.TRIGGER_NAMES)
    registered = set(re.findall(r"on_([a-z]+)_change=", SOURCE))
    assert registered == set(emg.STATE_NAMES) | set(emg.TRIGGER_NAMES)


def test_ops_the_browser_sends_are_the_ops_python_applies() -> None:
    sent = set(re.findall(r"\{ op: '([a-z]+)'", JS))
    assert (
        sent <= eg.OP_NAMES
        and {"cell", "paste", "set", "shift", "delete", "restore", "revert"} <= sent
    )
    assert "undo" not in sent, "되돌리기는 「한 단계 되돌리기」 단추(파이썬) 하나다"


def test_the_clipboard_is_read_only_from_the_paste_event() -> None:
    """사내 주소가 보안 문맥이 아닐 수 있어 비동기 Clipboard API 를 쓰지 않는다."""
    assert "navigator.clipboard" not in JS
    assert JS.count("clipboardData") >= 2


def test_local_storage_is_touched_only_inside_try() -> None:
    for match in re.finditer(r"localStorage", JS):
        before = JS[max(match.start() - 80, 0) : match.start()]
        assert "try {" in before, JS[match.start() - 80 : match.end() + 20]


def test_every_css_variable_comes_from_the_palette_and_no_colour_is_written() -> None:
    used = set(re.findall(r"var\(--emg-([a-z-]+)", CSS))
    assert used <= set(emg._palette()), used - set(emg._palette())
    for text in (CSS, JS, HTML):
        assert not re.search(r"#[0-9A-Fa-f]{3,8}\b", text)
        assert "rgb(" not in text and "rgba(" not in text


def test_placeholders_use_the_muted_ink_of_the_theme() -> None:
    """자리표시 글(「설비명으로 불러오기」 등)이 브라우저 기본 #757575 라 어두운 테마 바탕
    #1C1C21 에서 3.68:1 이었다(2026-10-26 E2E). 앱 토큰 TEXT_MUTED(`--emg-muted` — 두 테마 모든
    칸 바탕에서 4.5:1 이상)로 그리고 흐리게 하지 않는다."""
    rule = re.search(r"\.emg input::placeholder\s*\{(?P<body>[^}]*)\}", CSS)
    assert rule, "grid.css 에 자리표시 규칙이 없다"
    assert "color: var(--emg-muted)" in rule.group("body") and "opacity: 1" in rule.group("body")


def test_the_shift_days_stay_with_their_unit_and_blank_dates_show_the_pattern() -> None:
    """고른 줄 띠(지금은 「일정 밀기」 팝업)가 좁으면(1500px) 「반입·Qual 일정 [7]」 다음의
    단위 「일」 만 다음 줄로 넘어가 칸과 떨어졌다 — 이름·날 수 칸·「일」·밀기 단추를 한
    덩이(`emg-shift`, 안에서 줄을 바꾸지 않음)로 둔다. 빈 날짜 칸 자리표시는 실제
    날짜(「2026-11-09」)라 값처럼 읽혔다 — 꼴(YYYY-MM-DD)을 적는다(2026-10-25 E2E
    #26·#28)."""
    selection = _function("bulkShiftPanel")
    group = selection[
        selection.index("el('span', 'emg-shift')") : selection.index(
            "panel.appendChild(shiftGroup)"
        )
    ]
    for part in (
        "shiftGroup.appendChild(el('span', null, '반입·Qual 일정'))",
        "shiftGroup.appendChild(days)",
        "shiftGroup.appendChild(el('span', null, '일'))",
        "shiftGroup.appendChild(shiftTip.host)",
    ):
        assert part in group, part
    rule = re.search(r"\n\.emg-shift\s*\{(?P<body>[^}]*)\}", CSS)
    assert rule and "flex-wrap: nowrap" in rule.group("body")
    assert "const DATE_PLACEHOLDER = 'YYYY-MM-DD'" in JS
    dated = [line for line in JS.splitlines() if "placeholder = " in line and "'date'" in line]
    assert len(dated) == 4 and all("DATE_PLACEHOLDER" in line for line in dated), dated
    assert not re.search(r"placeholder = [^\n]*'\d{4}-\d{2}-\d{2}", JS)


def test_the_registered_css_carries_no_comments() -> None:
    """등록 CSS 는 data 가 바뀐 회차마다 요소와 함께 다시 간다 — 주석을 싣지 않는다."""
    assert "/*" not in CSS


def test_data_text_goes_in_with_text_content_only() -> None:
    """설비명·메모·문구 같은 데이터 글은 textContent 로만 — innerHTML 은 고정 아이콘에만 쓴다."""
    assignments = re.findall(r"\.innerHTML\s*=\s*([^\n]+)", JS)
    assert assignments and all(
        re.fullmatch(r"ICONS(\.[a-z]+|\[name\])", item.strip()) for item in assignments
    )
    assert "insertAdjacentHTML" not in JS and "outerHTML" not in JS


def test_handled_keys_stop_at_the_component() -> None:
    """칸·찾기 칸의 키가 문서로 올라가면 Streamlit 단축키(r 다시 실행·c 캐시)가 글자를 먹는다."""
    assert "event.stopPropagation()" in JS
    for name in ("onBodyKey", "searchBox", "detailField", "popover", "newField", "copyRow"):
        body = JS[JS.index(f"function {name}(") :]
        body = body[: body.index("\nfunction ")]
        assert "stopKeys(event)" in body, name


def test_the_cleanup_releases_listeners_and_timers() -> None:
    cleanup = JS[JS.rindex("return () => {") :]
    for piece in (
        "removeEventListener",
        "clearTimeout(S.timer)",
        "clearTimeout(S.noteTimer)",
        "cancelAnimationFrame",
    ):
        assert piece in cleanup, piece
    assert "listen(S, document, 'visibilitychange'" in JS


def test_the_outbox_flushes_after_quiet_and_at_once_when_focus_leaves() -> None:
    assert "const SEND_MS = 300" in JS
    assert "listen(S, host, 'focusout'" in JS and "send(S)" in JS


def test_the_shadow_root_is_kept_and_widths_follow_the_spec() -> None:
    """팝업 안에 마운트하지 않는다(그림자 DOM 기본값). 칸 폭은 시안 2차의 폭이다."""
    assert "isolate_styles" not in SOURCE.split('"""', 2)[2].split("_GRID =")[1].split(")")[0]
    wide, narrow = OWN_CSS.split("@media (max-width: 640px)")
    widths = {
        name: int(value)
        for name, value in re.findall(r"\.emg-w-([a-z]+)\s*\{\s*width:\s*(\d+)px", wide)
    }
    assert widths == {
        "chk": 40,
        "name": 150,
        "status": 84,
        "date": 108,
        "num": 76,
        "text": 118,
        "memo": 180,
        "rm": 36,
    }
    assert re.search(r"\.emg-w-name\s*\{\s*width:\s*120px", narrow), "좁은 화면 설비명 120"
    assert re.search(r"\.emg-w-short,\s*\.emg-w-status\s*\{\s*width:\s*84px", CSS)
    assert {column.width for column in eg.GRID_COLUMNS} <= set(widths) | {"short", "status"}


def test_the_hidden_attribute_wins_over_display_rules() -> None:
    assert re.search(r"\.emg \[hidden\]\s*\{\s*display:\s*none !important", CSS)


def test_the_code_alphabet_matches_python() -> None:
    assert f"const CODE_ALPHABET = '{eg.CODE_ALPHABET}'" in JS


def _function(name: str) -> str:
    body = JS[JS.index(f"function {name}(") :]
    return body[: body.index("\nfunction ")]


def test_results_leave_the_grid_and_only_the_refusals_stay_in_place() -> None:
    """표 안 · 오른쪽 칸 띠의 결과 토스트와 그 「되돌리기」 는 없다 — 결과는 알림창, 되돌리기는 「한
    단계 되돌리기」 하나다(설계 규칙 UI-NTF-03 · UI-LAY-11). 표 띠는 브라우저 한 줄만, 오른쪽 칸은
    그 칸에서 고칠 파이썬 거부도 그린다."""
    for gone in ("fillToast", "paintToast", "revealToast", "emg-toast", "toast.undo", "op: 'undo'"):
        assert gone not in JS, gone
    assert "emg-toast" not in CSS
    assert "fillNote(S, S.noteBar, null)" in JS
    assert "fillNote(S, note, S.data && S.data.toast)" in _function("drawSide")
    assert "'되돌리기'" not in _function("fillNote")


_NOTE_RUNNER = """
const S = { box: createBox(), pending: new Map(), note: '', noteSeq: 0, noteTimer: 0, repaints: 0 }
S.repaintNote = () => { S.repaints += 1 }
const data = (seq) => ({ base: 'b', ack: { mount: 'm', seq } })
S.mount = 'm'
receive(S, { base: 'b' })
const out = {}
showNote(S, '붙여넣는 중 — 2줄', 3)
receive(S, data(2))
out.before = S.note
receive(S, data(3))
out.after = [S.note, S.noteSeq, S.noteTimer]
showNote(S, '한 번에 5,000칸까지 붙입니다')
receive(S, data(4))
out.refusal = S.note
clearTimeout(S.noteTimer)
process.stdout.write(JSON.stringify(out))
"""


def test_the_paste_progress_line_leaves_when_its_op_comes_back() -> None:
    """결과가 띠로 오지 않아 「붙여넣는 중」 은 그 op 의 ack 에 거둔다 — 안 거두면 결과 알림이 뜬 뒤
    6초 남는다. 거부 한 줄은 다른 op 의 ack 로 사라지지 않는다."""
    assert _node({}, _NOTE_RUNNER, source=_fake_dom_source()) == {
        "before": "붙여넣는 중 — 2줄",
        "after": ["", 0, 0],
        "refusal": "한 번에 5,000칸까지 붙입니다",
    }


def test_the_grid_body_has_one_tab_stop_and_space_picks_a_row() -> None:
    row = _function("rowElement")
    for name in ("box", "back", "unload"):
        assert f"{name}.tabIndex = -1" in row, name
    key = _function("onBodyKey")
    assert "event.key === ' '" in key and "toggleRow(S, id, event.shiftKey)" in key
    assert key.index("event.key === ' '") < key.index("event.key.length === 1")


def test_a_deleted_row_stays_on_the_keyboard_path() -> None:
    """지운 줄에 남은 초점에서 ↓ 가 맨 첫 줄로 뛰고(산 줄 목록에서 −1 → 0) 지운 줄의 「되살리기」 에
    키보드로 닿지 못했다(2026-10-26 E2E). 화살표는 화면 차례의 모든 줄(`model.ordered`)을 걷고, 지운
    줄의 Space 는 그 줄의 체크 칸 자리 「되살리기」 다. 고른 줄 띠를 닫는 단추(지우기·선택 풀기)는
    초점을 표로 돌린다."""
    key = _function("onBodyKey")
    assert "moveFocus(model.ordered.map((row) => row.id)" in key
    assert "live.findIndex" not in key.split("event.key === ' '")[0]
    space = key[key.index("event.key === ' '") : key.index("if (col === model.nameCol) return")]
    assert "toggleRow(S, id, event.shiftKey)" in space and "{ op: 'restore', ids: [id] }" in space
    selection = _function("buildSelection") + _function("buildBulkTools")
    assert selection.count("refocusTable(S, ") == 2
    refocus = _function("refocusTable")
    assert "S.wantFocus = true" in refocus and "ensureVisible(S, S.focus.id)" in refocus
    runner = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
process.stdout.write(JSON.stringify({
  moves: input.cases.map((c) => moveFocus(c.ids, c.cols, c.at, c.dir)),
}))
"""
    ids = ["s:A", "s:B", "s:C"]  # s:B 가 지운 줄이다 — 화면 차례 그대로 든다.
    cols = [0, 2, 3]
    cases = [
        {"at": {"id": "s:B", "col": 0}, "dir": "down"},
        {"at": {"id": "s:B", "col": 0}, "dir": "up"},
        {"at": {"id": "s:A", "col": 0}, "dir": "down"},
        {"at": {"id": "s:C", "col": 3}, "dir": "down"},
        {"at": {"id": "s:B", "col": 2}, "dir": "right"},
        {"at": {"id": "s:Z", "col": 0}, "dir": "down"},
    ]
    result = _node({"cases": [{"ids": ids, "cols": cols, **case} for case in cases]}, runner=runner)

    assert result["moves"] == [
        {"id": "s:C", "col": 0},
        {"id": "s:A", "col": 0},
        {"id": "s:B", "col": 0},
        None,
        {"id": "s:B", "col": 3},
        None,
    ]


def test_a_returning_load_does_not_steal_focus_from_the_table() -> None:
    assert "focusIsFree(host)" in _function("drawLoader")
    assert "S.refocus = null" in JS[JS.index("listen(S, host, 'focusout'") :]
    load = _function("loadQuery")
    assert "clearSearch(S)" in load and "S.searchInput.value = ''" in _function("clearSearch")


def test_moved_ids_are_applied_before_the_list_fingerprint_resets_the_view() -> None:
    draw = _function("drawGrid")
    assert draw.index("data.moved") < draw.index("S.view !== view")
    assert draw.index("const before = S.model") < draw.index("S.model = gridModel(S, data)")
    assert "keptView(before, after, moved," in draw
    assert "S.openId = typeof data.open === 'string'" in draw
    click = _function("onBodyClick")
    assert "classList.add('is-open')" in click


def test_the_condition_popover_keeps_values_by_text_and_focus_across_repaints() -> None:
    conditions = _function("conditionPopover")
    assert "resolvePicks(S.conds, values)" in conditions and "pick.value = " not in conditions
    assert "line.addEventListener('keydown', stopKeys)" not in conditions, "Esc 가 패널에 닿는다"
    assert "cond-col-" in conditions and "cond-val-" in conditions
    paint = _function("popover")
    assert "captureFocus(panel)" in paint and "restoreFocus(panel, saved)" in paint
    assert "popoverShift(" in paint
    assert re.search(r"\.emg-pop\.is-wide\s*\{\s*width:\s*min\(420px, calc\(100vw - 16px\)\)", CSS)


def test_pasting_on_the_name_column_spreads_from_the_next_column_or_says_why() -> None:
    paste = _function("onPaste")
    assert "NAME_PASTE_NOTE" in paste and "[model.nameCol].concat(model.visible)" in paste
    assert "pasteRowsByName(cells, live.map(" in paste and "namePasteRefusal(matched)" in paste


# ---------------------------------------------------------------- JS 순수 구획(node)

_SECTIONS = (
    "grid-paste",
    "grid-nav",
    "grid-outbox",
    "grid-match",
    "grid-plan",
    "grid-sort",
    "grid-view",
    "grid-codes",
    "grid-place",
    "grid-new",
    "grid-choice",
)
_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const results = {}
results.paste = (input.paste || []).map((c) => {
  const cells = parseClipboard(c.text)
  if (!cells) return null
  const locked = new Set(c.locked || [])
  return planPaste(cells, c.row, c.col, c.ids, c.cols, (id, col) => !locked.has(id + '|' + col),
  c.limit)
})
results.nav = (input.nav || []).map((c) => {
  const locked = new Set(c.locked || [])
  return nextCell(c.rows, c.cols, c.from, c.dir, (r, k) => !locked.has(r + ',' + k), c.limit)
})
results.outbox = (() => {
  const box = createBox()
  const out = []
  out.push(rebaseBox(box, 'b1'))
  const a = queueOp(box, { op: 'cell' }, 3, 1)
  const b = queueOp(box, { op: 'paste', rows: [['x', null], ['y', 'z']] }, 4, 2)
  const c = queueOp(box, { op: 'set', ids: ['a', 'b'] }, 4, 3)
  out.push([a.seq, a.base, b.seq, c, boxCells(box)])
  out.push(ackBox(box, 1), box.ops.map((op) => op.seq))
  out.push(rebaseBox(box, 'b1'), rebaseBox(box, 'b2'), box.ops.length, box.base)
  out.push(opCells({ op: 'shift', ids: ['a', 'b', 'c'] }))
  return out
})()
results.match = (input.match || []).map((c) => matchNames(c.text, c.names))
results.plan = {
  days: (input.days || []).map(parseDays),
  shift: (input.shiftIso || []).map((c) => shiftIso(c[0], c[1])),
  set: planSet(input.rows, 1, ' x ', (row, col) => row.locked === true),
  shiftCount: planShift(input.rows, [0, 2], -3, (row, col) => row.locked === true),
}
results.sort = (input.sort || []).map((c) => sortOrder(c.values, c.dir, c.kind))
results.codes = (input.codes || []).map((c) => decodeCodes(c.text, c.width))
results.conditions = matchConditions(input.columns, input.picks, input.count)
results.resolved = resolvePicks(input.pickTexts, input.pickValues)
results.shifts = (input.shifts || []).map((c) => popoverShift(c[0], c[1], c[2], c[3]))
process.stdout.write(JSON.stringify(results))
"""


def _sections() -> str:
    parts = []
    for name in _SECTIONS:
        match = re.search(rf"// <{name}>\n(?P<body>.*?)\n// </{name}>", JS, re.S)
        assert match, f"grid.js 에 // <{name}> 구획이 없습니다"
        parts.append(match.group("body"))
    return "\n".join(parts)


def _node(
    payload: dict[str, Any], runner: str = _RUNNER, source: str | None = None
) -> dict[str, Any]:
    """`source`(기본은 순수 구획들) 뒤에 `runner` 를 붙여 돌리고 그 출력 JSON 을 돌려준다."""
    result: dict[str, Any] = run_js_json(
        (_sections() if source is None else source) + runner,
        what="설비 마스터 표 JS 대조",
        stdin=json.dumps(payload),
    )
    return result


def _python_codes(values: list[int], width: int) -> str:
    return eg.encode_codes(values, width)


def test_the_pure_sections_behave_as_specified() -> None:
    names = ["WBA-01", "WBA-02", "wba-10", "DAA-05", "MLD-01"]
    rows = [
        {"values": ["2026-11-01", " x ", "2026-11-03"], "locked": False},
        {"values": ["", "y", "bad"], "locked": False},
        {"values": ["2026-11-01", "x", ""], "locked": True},
    ]
    result = _node(
        {
            "paste": [
                {
                    "text": "a\tb\tc\r\nd\te\n\n",
                    "row": 1,
                    "col": 0,
                    "ids": ["r0", "r1", "r2"],
                    "cols": ["A", "B"],
                    "locked": ["r1|B"],
                    "limit": 5000,
                },
                {"text": "한 칸\n", "row": 0, "col": 0, "ids": ["r0"], "cols": ["A"], "limit": 5},
                {
                    "text": "1\t2\n3\t4\n",
                    "row": 0,
                    "col": 0,
                    "ids": ["r0", "r1"],
                    "cols": ["A", "B"],
                    "limit": 3,
                },
                {
                    "text": "X\t담당Z\nY\t담당Z",
                    "row": 0,
                    "col": 0,
                    "ids": ["r0", "r1"],
                    "cols": ["설비명", "담당자"],
                    "locked": ["r0|설비명", "r1|설비명"],
                    "limit": 5000,
                },
            ],
            "nav": [
                {
                    "rows": 3,
                    "cols": 3,
                    "from": {"row": 0, "col": 0},
                    "dir": "right",
                    "locked": ["0,1"],
                },
                {"rows": 3, "cols": 3, "from": {"row": 0, "col": 2}, "dir": "right"},
                {
                    "rows": 200,
                    "cols": 1,
                    "from": {"row": 0, "col": 0},
                    "dir": "down",
                    "locked": [f"{r},0" for r in range(1, 150)],
                    "limit": 80,
                },
                {
                    "rows": 3,
                    "cols": 3,
                    "from": {"row": 2, "col": 1},
                    "dir": "up",
                    "locked": ["1,1"],
                },
            ],
            "match": [
                {"text": "wba", "names": names},
                {"text": "WBA-0, DAA-05; ABC-99", "names": names},
                {"text": "zzz", "names": names},
                {"text": "WBA-01\nMLD", "names": names},
            ],
            "days": ["7", "−3", "+2", "0", "x", " -10 "],
            "shiftIso": [["2026-02-27", 3], ["2026-03-01", -1], ["bad", 1]],
            "rows": rows,
            "sort": [
                {"values": ["10", "", "9", "100"], "dir": "asc", "kind": "number"},
                {"values": ["10", "", "9", "100"], "dir": "desc", "kind": "number"},
                {"values": ["나", "", "가", "다"], "dir": "asc", "kind": "text"},
                {"values": ["b", "a"], "dir": None, "kind": "text"},
            ],
            "codes": [
                {"text": _python_codes([0, 5, 63], 1), "width": 1},
                {"text": _python_codes([0, 64, 4095], 2), "width": 2},
            ],
            "columns": [[0, 1, 0, 1], [2, 2, 3, 2]],
            "picks": [{"col": 0, "value": 1}, {"col": 1, "value": 2}, {"col": 1, "value": None}],
            "count": 4,
            "pickTexts": [
                {"col": 0, "text": "Die Attach"},
                {"col": 1, "text": "사라진 값"},
                {"col": 0, "text": None},
            ],
            "pickValues": [["Burn-In", "Die Attach"], ["a"]],
            "shifts": [
                [169, 374, 390, 8],
                [100, 300, 1500, 8],
                [1300, 400, 1500, 8],
                [5, 400, 300, 8],
            ],
        }
    )
    first, single, too_many, from_name = result["paste"]
    assert first["ids"] == ["r1", "r2"] and first["cols"] == ["A", "B"]
    assert first["rows"] == [["a", None], ["d", "e"]]
    assert first["cut"] == 1, "표 끝을 넘은 줄"
    assert first["skipped"] == 2, "칸 끝을 넘은 c 하나 + 잠긴 r1|B"
    assert first["count"] == 3 and not first["tooMany"]
    assert single is None, "한 칸이면 보통 붙여넣기"
    assert too_many["tooMany"] is True
    assert from_name["rows"] == [[None, "담당Z"], [None, "담당Z"]] and from_name["skipped"] == 2
    assert result["resolved"] == [
        {"col": 0, "value": 1},
        {"col": 1, "value": None},
        {"col": 0, "value": None},
    ], "값은 글로 기억하고, 목록에서 사라지면 비운다"
    assert result["shifts"] == [-161, 0, -208, 0], "화면 오른쪽 밖이면 왼쪽으로(왼쪽 끝 8px)"
    assert result["nav"] == [{"row": 0, "col": 2}, None, None, {"row": 0, "col": 1}]
    assert result["match"][0] == {"found": [0, 1, 2], "missing": [], "list": False}
    assert result["match"][1] == {"found": [0, 1, 3], "missing": ["ABC-99"], "list": True}
    assert result["match"][2] == {"found": [], "missing": ["zzz"], "list": False}
    assert result["match"][3]["found"] == [0, 4] and result["match"][3]["list"]
    plan = result["plan"]
    assert plan["days"] == [7, -3, 2, None, None, -10]
    assert plan["shift"] == ["2026-03-02", "2026-02-28", None]
    assert plan["set"] == 1, "같은 값(x)·잠긴 줄은 뺀다"
    assert plan["shiftCount"] == 2, "날짜가 있는 칸만, 잠긴 줄 빼고"
    assert result["sort"] == [[2, 0, 3, 1], [3, 0, 2, 1], [2, 0, 3, 1], [0, 1]]
    assert result["codes"] == [[0, 5, 63], [0, 64, 4095]]
    assert result["conditions"] == [1, 3]
    box = result["outbox"]
    assert box[0] is False, "처음 base 를 받는 것은 버림이 아니다"
    assert box[1] == [1, "b1", 2, None, 4], "칸 상한을 넘는 op 는 넣지 않는다"
    assert box[2] == 1 and box[3] == [2]
    assert box[4:8] == [False, True, 1, "b2"], "base 가 바뀌어도 든 op 는 서버까지 간다"
    assert box[8] == 6


_NAME_ORDER_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const pick = (order, names) => order.map((k) => names[k])
const R = {}
R.parity = pick(sortOrder(input.parity, null, 'name', input.parity), input.parity)
R.cases = input.cases.map((c) => sortOrder(c.values, c.dir, c.kind, c.names))
R.cycle = input.cycle.map((c) => nextSort(c[0], c[1], c[2]))
process.stdout.write(JSON.stringify(R))
"""


def test_rows_stand_in_natural_name_order_and_equal_values_follow_the_name() -> None:
    """설비 마스터 표 처음 차례는 설비명 오름차순 — 파이썬 `natural_name_key`(「전체 불러오기」 가
    상한을 자르는 차례)와 같은 자연 차례다(숫자는 수로 — 호기 2 가 호기 10 앞, 한글은 가나다, 영문이
    한글 앞). 머리로 정렬하면 값이 같은 줄은 설비명 오름차순이고 내림차순이어도 둘째 열쇠는
    오름이다. 빈 값 · 빈 이름은 늘 아래. 머리 누름은 다른 칸이 오름 → 내림 → 처음 차례, 설비명
    칸이 처음 차례 ↔ 내림이다(2026-11-20 사용자 요청 — Qual 일정 오름차순에서 같은 날 호기가
    가나다 차례로)."""
    parity = [
        "EQ10", "EQ2", "eq3", "EQ02", "EQ2", "호기 10", "호기 2", "가나-1", "나-2", "다-1",
        "A-1", "a-1", "_X", "-X", "Zeta", "가", "12B", "12A", "12", "12a", "007", "7",
        "EQ-12D", "EQ-12C", "x😀", "x＀", "DEMO 1", "DEMO-1", "demo1", "Demo1",
    ]  # fmt: skip
    dates = ["2026-12-01", "2026-11-01", "2026-12-01", "", "2026-11-01", ""]
    names = ["호기 10", "B-2", "호기 2", "A-1", "B-10", ""]
    cases = [
        {"values": names, "dir": None, "kind": "name", "names": names},
        {"values": dates, "dir": "asc", "kind": "date", "names": names},
        {"values": dates, "dir": "desc", "kind": "date", "names": names},
        {"values": names, "dir": "desc", "kind": "name", "names": names},
        {"values": ["", "x", ""], "dir": "desc", "kind": "text", "names": ["B", "A", "A2"]},
        {"values": ["2", "10", "2", "2"], "dir": "asc", "kind": "number", "names": list("QPPP")},
        {"values": ["b", "a"], "dir": None, "kind": "text"},
    ]
    cycle = [
        [None, 3, 0],
        [{"col": 3, "dir": "asc"}, 3, 0],
        [{"col": 3, "dir": "desc"}, 3, 0],
        [None, 0, 0],
        [{"col": 0, "dir": "desc"}, 0, 0],
        [{"col": 3, "dir": "desc"}, 0, 0],
        [None, 2, -1],
    ]
    result = _node({"parity": parity, "cases": cases, "cycle": cycle}, _NAME_ORDER_RUNNER)
    order = result["parity"]
    assert order == sorted(parity, key=natural_name_key)
    assert order.index("호기 2") < order.index("호기 10")
    assert order.index("EQ2") < order.index("EQ10")
    assert order.index("Zeta") < order.index("가") < order.index("나-2") < order.index("다-1")
    default, asc, desc, name_desc, blank_ties, numbers, plain = result["cases"]
    assert default == [3, 1, 4, 2, 0, 5], "A-1 · B-2 · B-10 · 호기 2 · 호기 10 · 빈 이름"
    assert asc == [1, 4, 2, 0, 3, 5], "같은 날은 설비명 오름 — B-2 · B-10, 호기 2 · 호기 10"
    assert desc == [2, 0, 1, 4, 3, 5], "내림이어도 같은 날은 설비명 오름, 빈 값은 아래"
    assert name_desc == [0, 2, 4, 1, 3, 5], "설비명 내림 — 빈 이름은 늘 아래"
    assert blank_ties == [1, 2, 0], "빈 값끼리도 설비명 오름"
    assert numbers == [2, 3, 0, 1], "수 칸 동점은 설비명, 같은 이름이면 원래 차례"
    assert plain == [0, 1], "설비명을 주지 않으면 원래 차례 그대로"
    assert result["cycle"] == [
        {"col": 3, "dir": "asc"},
        {"col": 3, "dir": "desc"},
        None,
        {"col": 0, "dir": "desc"},
        None,
        None,
        {"col": 2, "dir": "asc"},
    ]


_TEXT_ORDER_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const pick = (order, values) => order.map((k) => values[k])
const R = {}
R.asc = input.kinds.map((kind) => pick(sortOrder(input.mixed, 'asc', kind), input.mixed))
R.desc = input.kinds.map((kind) => pick(sortOrder(input.mixed, 'desc', kind), input.mixed))
R.ties = input.ties.map((c) => sortOrder(c.values, c.dir, c.kind, c.names))
R.cells = input.cells.map((c) => Math.sign(compareCells(c[0], c[1], c[2])))
process.stdout.write(JSON.stringify(R))
"""

# 글 칸에 실제로 섞여 드는 꼴 — 숫자로 시작 · 기호(영문 앞 · 영문 뒤 · ASCII 밖) · 영문(대소문자) ·
# 한글 · 이름 안 숫자 · 전각 숫자 · 전각 기호 · 줄바꿈 · 탭 · BMP 밖 글자 · 빈 값 · 겹친 값.
_MIXED_TEXT = [
    "물류", "FDY", "MI", "Main", "부대", "HBM", "EDP", "범용", "PKG",
    "11월 1주 — 셋업 지연", "D 모듈 도면 숨김", "Qual 지연 — 부품 수급",
    "도면 미표시", "자리 미정",
    "모델-10", "모델-2", "Model-10", "Model-2", "model-2", "12A", "7", "007",
    "-X", "_X", "Zeta", "가", "１２", "줄\n바꿈", "탭\t칸", "x😀", "", "물류", "",
    "~임시", "※ 확인 필요", "·메모", "(주)A", "（주）B",
]  # fmt: skip


def test_text_columns_sort_in_the_same_order_as_the_name_column_and_the_condition_values() -> None:
    """설비 마스터 표 글 칸(글 · 메모 · 고르기)의 머리 정렬은 설비명 칸과 같은 비교 하나다 —
    이름 안 숫자(0-9)는 수로(「Model-2」 가 「Model-10」 앞), 나머지는 소문자로 바꾼 글자의
    코드 포인트 차례다. 그래서 숫자로 시작하는 값 → 기호 대부분 → 영문 → 한글이고, 「~」 같은
    ASCII 끝 기호와 ※ · 가운뎃점 같은 ASCII 밖 기호는 영문 뒤 · 한글 앞, 전각 숫자 · 기호
    (「１２」 · 「（주）」)는 한글 뒤다. 대소문자는 가리지 않는다. 그 차례는 파이썬
    `natural_name_key` 와 같고, 조건 값 목록 차례(`_sorted_values`)와도 같다. 내림차순은 그
    거꾸로이고 빈 값은 늘 아래, 값이 같은 줄은 설비명 오름차순이다. 수 · 날짜 칸은 그대로 — 수
    칸은 수로(「1e3」 이 「200」 뒤), 날짜 칸은 글자 그대로다(2026-11-20 결과 보드 여쭘-2 a)."""
    kinds = ["text", "memo", "choice", "name"]
    ties = [
        {
            "values": ["물류", "FDY", "물류", "FDY", "", "Main"],
            "names": ["호기 10", "B-2", "호기 2", "A-1", "C", "Z"],
            "kind": kind,
            "dir": direction,
        }
        for kind in ("text", "choice")
        for direction in ("asc", "desc")
    ]
    cells = [
        ["1e3", "200", "number"],
        ["1e3", "200", "text"],
        ["2026-1-5", "2026-01-10", "date"],
        ["2026-1-5", "2026-01-10", "text"],
        ["가", "A", "memo"],
        ["가", "A", "choice"],
    ]
    result = _node(
        {"kinds": kinds, "mixed": _MIXED_TEXT, "ties": ties, "cells": cells}, _TEXT_ORDER_RUNNER
    )
    filled = [value for value in _MIXED_TEXT if value]
    blanks = [value for value in _MIXED_TEXT if not value]
    ascending = sorted(filled, key=natural_name_key) + blanks
    descending = sorted(filled, key=natural_name_key, reverse=True) + blanks
    for kind, asc, desc in zip(kinds, result["asc"], result["desc"], strict=True):
        assert asc == ascending, kind
        assert desc == descending, kind
    text = result["asc"][0]
    assert list(dict.fromkeys(text)) == eg._sorted_values(_MIXED_TEXT), "조건 값 목록 차례와 같다"
    assert text.index("7") < text.index("-X") < text.index("FDY") < text.index("물류")
    assert text.index("Zeta") < text.index("가")
    assert text.index("(주)A") < text.index("Zeta") < text.index("~임시") < text.index("·메모")
    assert text.index("·메모") < text.index("※ 확인 필요") < text.index("가")
    assert text.index("가") < text.index("（주）B") and text.index("가") < text.index("１２")
    assert text.index("Model-2") < text.index("Model-10")
    assert text.index("모델-2") < text.index("모델-10")
    assert text.index("Qual 지연 — 부품 수급") < text.index("도면 미표시")
    assert result["ties"] == [[3, 1, 5, 2, 0, 4], [2, 0, 5, 3, 1, 4]] * 2, "같은 값은 설비명 오름"
    assert result["cells"] == [1, -1, 1, -1, 1, 1], "수 · 날짜 칸은 제 비교, 글 칸은 영문이 앞"


_VIEW_FOLLOW_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
process.stdout.write(JSON.stringify({
  fresh: input.fresh.map((c) => freshOpen(c[0], c[1], c[2], c[3], c[4])),
  slot: input.slot.map((c) => openSlot(c[0], c[1], c[2], c[3])),
}))
"""


def test_the_grid_scrolls_to_an_open_row_only_when_it_is_newly_added_or_moved_in_view() -> None:
    """설비명 차례 표의 스크롤 따라가기 두 판정(UI-PRF-03). `freshOpen` — 처음으로 돌린 회차에
    표를 연 줄까지 굴리는 것은 「호기 추가」 · 「저장 전 변경」 에서 목록 밖 호기 열기뿐이다: 앞
    목록 줄이 모두 남은 채 늘기만 했고(옮김을 얹어), 연 줄이 앞 회차에 연 줄이 아닐 때. 「목록
    비우기」 뒤 연 상세를 둔 채 다시 불러오기 · 저장(새 호기 id 가 n: → s:)은 맨 위다. `openSlot` —
    앞 그리기에서 창 안에 보이던 연 줄만 지킨 회차에 따라간다(창 밖이면 null)."""
    fresh = [
        [["a", "b"], ["n", "a", "b"], [], "n", "a"],
        [["a", "b"], ["n", "a", "b"], [], "n", None],
        [["a", "b"], ["n", "a", "b"], [], "a", None],
        [["x", "b"], ["y", "b"], [["x", "y"]], "y", None],
        [["a"], ["a", "n"], [], "q", None],
        [["a"], ["a", "n"], [], None, None],
        [None, ["n"], [], "n", None],
        # 「목록 비우기」(연 상세 s40 은 그대로) 뒤 다시 불러오기 — 앞 회차에도 연 줄.
        [[], ["s1", "s40"], [], "s40", "s40"],
        # 저장 — 새 호기 n:A 가 s:A 로(옮김이 실리지 않는다), 앞 목록 줄이 빠졌다.
        [["n:A", "s1"], ["s:A", "s1"], [], "s:A", "n:A"],
        # 다른 줄이 빠진 같은 회차.
        [["a", "b"], ["n", "a"], [], "n", "a"],
        # 옮김으로 들어온 연 줄(새 호기 이름 바꿈 되돌리기)은 새로 든 줄이 아니다.
        [["x", "b"], ["y", "b", "n"], [["x", "y"]], "y", "x"],
    ]
    rows = ["r0", "r1", "r2", "r3", "r4", "r5"]
    slot = [
        [rows, "r3", 2, 3],
        [rows, "r2", 2, 3],
        [rows, "r4", 2, 3],
        [rows, "r5", 2, 3],
        [rows, "r1", 2, 3],
        [rows, "q", 0, 6],
        [rows, None, 0, 6],
    ]
    result = _node({"fresh": fresh, "slot": slot}, _VIEW_FOLLOW_RUNNER)
    assert result["fresh"] == ["n", "n", None, None, None, None, None, None, None, None, None]
    assert result["slot"] == [3, 2, 4, None, None, None, None]


_NAME_PASTE_PURE_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
process.stdout.write(JSON.stringify({ cases: input.cases.map((c) => {
  const matched = pasteRowsByName(c.cells, c.rows)
  return { ...matched, note: namePasteRefusal(matched) }
}) }))
"""


def test_a_block_pasted_from_the_name_column_finds_its_rows_by_name() -> None:
    """설비명 칸에서 붙인 덩이(엑셀에서 설비명 열부터 잡은 흔한 꼴)는 보이는 차례가 아니라 붙인
    첫 열의 설비명으로 줄을 맞댄다(`pasteRowsByName`) — 표는 설비명 자연 차례(호기 2 가 호기 10
    앞)라 엑셀 차례(글 오름차순 · 찾기 칸에 붙인 차례)와 다를 수 있다. 앞뒤 공백만 떼고 글자 그대로
    견준다. 빈 설비명 · 표에 없는 이름 · 표에 같은 이름이 둘 · 붙인 글에 두 번이면 붙이지 않고 한 줄
    (앞 셋만 적는다)."""
    rows = [
        ["s:2", "호기 2"],
        ["s:7", "호기 7"],
        ["s:10", "호기 10"],
        ["d1", "겹침"],
        ["d2", "겹침"],
    ]
    cases = [
        {"cells": [["호기 10", "a"], [" 호기 2 ", "b"], ["호기 7", "c"]], "rows": rows},
        {"cells": [["호기 10", "a"], ["호기 99", "b"], ["", "c"]], "rows": rows},
        {"cells": [["겹침", "a"]], "rows": rows},
        {"cells": [["호기 7", "a"], ["호기 7", "b"]], "rows": rows},
        {"cells": [["호기 2"]], "rows": rows},
        {"cells": [["x1"], ["x2"], ["x3"], ["x4"], ["x5"]], "rows": rows},
        {"cells": [["호기 2", "a"]], "rows": [["s:2", "호기 2"], ["n:호기 2", "호기 2x"]]},
    ]
    result = _node({"cases": cases}, _NAME_PASTE_PURE_RUNNER)["cases"]
    assert result[0] == {"ids": ["s:10", "s:2", "s:7"], "missing": [], "twice": [], "note": ""}
    assert result[1]["missing"] == ["호기 99", ""]
    assert result[1]["note"] == (
        "붙인 설비명 2개를 표에서 찾지 못해 붙이지 않았습니다 — 호기 99, 빈 설비명"
        " · 찾기 칸으로 불러온 뒤 다시 붙입니다"
    )
    assert result[2]["missing"] == ["겹침"], "표에 같은 이름이 둘이면 어느 줄인지 모른다"
    assert result[3]["twice"] == ["호기 7"] and result[3]["ids"] == ["s:7"]
    assert result[3]["note"] == "붙인 글에 같은 설비명이 두 번 있어 붙이지 않았습니다 — 호기 7"
    assert result[4] == {"ids": ["s:2"], "missing": [], "twice": [], "note": ""}
    assert result[5]["note"].endswith("x1, x2, x3 외 2개 · 찾기 칸으로 불러온 뒤 다시 붙입니다")
    assert result[6]["ids"] == ["s:2"], "앞부분 일치로 맞대지 않는다"


_CLIPBOARD_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
process.stdout.write(JSON.stringify({ parsed: input.texts.map(parseClipboard) }))
"""


def test_pasting_excel_quoted_cells_keeps_line_breaks_inside_one_cell() -> None:
    """엑셀은 줄바꿈(Alt+Enter)·탭이 든 칸을 따옴표로 감싸고 안의 따옴표를 겹쳐 복사한다 — 그
    칸이 아래 호기 칸으로 쪼개져 들어가지 않고, 「엑셀·CSV로 한꺼번에」 처럼 한 칸으로 읽힌다.
    닫히지 않거나 닫는 따옴표 뒤에 글이 더 있는 칸은 따옴표 칸이 아니라 글자 그대로다."""
    texts = [
        '"줄1\n줄2"\t"따옴표 ""안"""\r\n일반\t값\r\n',
        '"첫줄\n둘째줄"\r\n',
        '"A" 형\t나\n다\t"라',
        'a\t""\n"탭\t안"\tb',
        'plain "quote"\tx\n',
        '"한 칸"',
    ]
    result = _node({"texts": texts}, _CLIPBOARD_RUNNER)["parsed"]
    assert result[0] == [["줄1\n줄2", '따옴표 "안"'], ["일반", "값"]]
    assert result[1] == [["첫줄\n둘째줄"]], "줄바꿈이 든 한 칸은 아래 줄로 넘치지 않는다"
    assert result[2] == [['"A" 형', "나"], ["다", '"라']], "따옴표 칸이 아니면 글자 그대로"
    assert result[3] == [["a", ""], ["탭\t안", "b"]]
    assert result[4] == [['plain "quote"', "x"]]
    assert result[5] is None, "탭·줄바꿈이 없는 글은 보통 붙여넣기"


_NEW_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const local = { seq: 4, values: ['a', 'b'] }
const results = {
  first: adoptDraft(null, { seq: 0, values: ['', 'N'] }),
  keep: adoptDraft(local, { seq: 4, values: ['x', 'y'] }) === local,
  older: adoptDraft(local, { seq: 3, values: ['x', 'y'] }) === local,
  newer: adoptDraft(local, { seq: 6, values: ['c', 'd'] }),
  oldShape: bumpDraft({ seq: 4, values: ['a', 'b'], propagate: false }, 2),
  bump: [bumpDraft(local, 2).seq, bumpDraft(local, 9).seq],
  tier: [
    tierDone(true, '', true),
    tierDone(false, 'x', true),
    tierDone(false, 'x', false),
    tierDone(true, ' ', false),
  ],
  tip: [
    addTip('아직 추가할 수 없습니다', true, false, []),
    addTip('아직 추가할 수 없습니다', false, false, []),
    addTip('', true, false, []),
    addTip(null, true, false, []),
    addTip('옛 판정', false, true, []),
    addTip('옛 판정', false, true, ['설비명', '공정소분류']),
  ],
  add: [
    canAdd(['A', 'B'], [0, 1], false, true, null),
    canAdd(['A', ''], [0, 1], false, true, null),
    canAdd(['A', 'B'], [0, 1], true, true, null),
    canAdd(['A', 'B'], [0, 1], true, false, null),
    canAdd(['A', 'B'], [0, 1], false, true, '잠김'),
  ],
  error: [
    showsError(true, true, '', false, true),
    showsError(true, true, 'x', false, true),
    showsError(true, true, '', true, true),
    showsError(true, true, '', false, false),
    showsError(true, false, 'x', true, false),
    showsError(false, true, 'x', true, false),
  ],
  reveal: [needsReveal(-1104, 72), needsReveal(40, 72), needsReveal(300, 72)],
  box: [
    boxScrollFor(1474, -1172, 302),
    boxScrollFor(120, 182, 302),
    boxScrollFor(300, 250, 302),
    boxScrollFor(0, 302, 302),
    boxScrollFor(500, 400, 302),
  ],
}
process.stdout.write(JSON.stringify(results))
"""


def test_the_new_unit_draft_section_adopts_newer_drafts_and_gates_the_add_button() -> None:
    """「새 호기」 초안(`// <grid-new>`) — 파이썬 초안은 번호가 클 때만 받고(가져오기·「호기
    추가」 뒤), 확정마다 번호를 올리며, 체크 상자 칸은 판정 전이면 칸이 찼는지만 보고, 「호기 추가」
    는 필수 칸이 찼고 지금 초안의 판정이 막지 않을 때 켠다(판정 전이면 켜 두고 파이썬이 다시
    본다)."""
    result = _node({}, _NEW_RUNNER)

    assert result["first"] == {"seq": 0, "values": ["", "N"]}
    assert result["keep"] is True and result["older"] is True
    assert result["newer"] == {"seq": 6, "values": ["c", "d"]}
    assert result["oldShape"] == {"seq": 5, "values": ["a", "b"]}
    assert result["bump"] == [5, 10]
    assert result["tier"] == [True, False, True, False]
    assert result["add"] == [True, False, False, True, False]
    pending = "고친 칸을 확인하는 중입니다"
    assert result["tip"] == [
        "아직 추가할 수 없습니다",
        pending,
        "",
        "",
        "칸을 벗어나면 확인합니다",
        "아직 추가할 수 없습니다 — 설비명 · 공정소분류 칸을 확인합니다",
    ]


def test_new_unit_errors_on_cells_other_values_require_show_before_touching() -> None:
    """칸 오류는 판정이 지금 초안의 것일 때만, 값이 있거나 만졌을 때 — 다만 늘 필수인
    칸(설비명·공정소분류·Y/N 셋)이 아니면(Qual일정이 있는 신규 호기의 Qual상태, 좌표가 있는데
    빈 크기) 만지지 않아도 보인다(막는 오류가 빈 칸에 숨어 꺼진 「호기 추가」 의 까닭을 못 찾던
    길). 화면 위로 나간 토스트는 칸 머리를 보인다(`needsReveal` — 머리 띠 높이 아래면 그대로)."""
    result = _node({}, _NEW_RUNNER)

    assert result["error"] == [False, True, True, True, False, False]
    assert result["reveal"] == [True, True, False]


_CHOICE_RUNNER = """
const columns = [{ name: '동' }, { name: '층' }]
const floor = {
  name: '층',
  options: ['1F', '2F', '3F'],
  blank: true,
  optionsBy: { '동': { C1: ['1F', '2F'], C2: ['1F', '2F', '3F'], C5: [] } },
}
const at = (building) => (k) => (k === 0 ? building : '')
const results = {
  c1: choiceOptions(columns, floor, at('C1'), ''),
  c2: choiceOptions(columns, floor, at(' C2 '), ''),
  keep: choiceOptions(columns, floor, at('C1'), '3F'),
  none: choiceOptions(columns, floor, at('C5'), ''),
  blank: choiceOptions(columns, floor, at(''), ''),
  unknown: choiceOptions(columns, floor, at('C9'), ''),
  plain: choiceOptions(columns, { name: '동', options: ['C1', 'C2'], blank: false }, at('C1'), ''),
}
process.stdout.write(JSON.stringify(results))
"""


def test_the_floor_choice_narrows_by_the_rows_building_and_keeps_the_current_value() -> None:
    """고르는 칸 선택지(`// <grid-choice>`) — 층 칸은 그 줄의 동으로 좁히고(짝만 꺼진 「C1 3F」),
    지금 값은 비활성 층이어도 남긴다. 동이 비었거나 모르는 값이면 칸 단위 그대로, `optionsBy` 가
    없는 칸도 그대로다. 표 칸·호기 상세 「위치」·새 호기 초안이 같은 함수를 지난다."""
    result = _node({}, _CHOICE_RUNNER)

    assert result["c1"] == ["1F", "2F", ""]
    assert result["c2"] == ["1F", "2F", "3F", ""]
    assert result["keep"] == ["1F", "2F", "3F", ""]
    assert result["none"] == [""]
    assert result["blank"] == ["1F", "2F", "3F", ""]
    assert result["unknown"] == ["1F", "2F", "3F", ""]
    assert result["plain"] == ["C1", "C2"]
    # 정의 하나 + 표 칸 셋(그리기·편집 시작·키) + 새 호기 + 상세. 여러 줄 넣기만 칸 단위 그대로다.
    assert JS.count("choiceOptions(") == 6
    assert "choiceOptions(columns, column, (j) => S.nd.values[j], value)" in JS
    assert "choiceOptions(columns, column, rowValueAt(S, unit), shown)" in JS


_HEAD_BOX_RUNNER = """
let calls = []
const main = { matches: (selector) => selector === '[data-testid="stMain"]', parentElement: null }
const box = {
  overflowY: 'auto', scrollTop: 0, scrollHeight: 2200, clientHeight: 653, top: 302,
  parentElement: main, matches: () => false,
  getBoundingClientRect() { return { top: this.top } },
}
// 그림자 DOM 밖 마운트 자리 → 본문 칸. 그림자 안의 맨 위 요소는 parentElement 가 없어 뿌리의
// host 로 건넌다.
const outer = { parentElement: box, matches: () => false }
const side = { parentElement: null, getRootNode: () => ({ host: outer }) }
const head = {
  isConnected: true, parentElement: side,
  getBoundingClientRect() { return { top: box.top - box.scrollTop } },
  scrollIntoView(options) { calls.push(options) },
}
globalThis.window = {
  requestAnimationFrame(fn) { fn(); return 1 },
  getComputedStyle: (node) => ({ overflowY: node.overflowY || 'visible' }),
}
const run = (setup) => {
  calls = []
  setup()
  revealHead(head)
  return { box: box.scrollTop, page: calls.length ? calls : null }
}
const out = {}
// 붙은 오른쪽 칸, 본문 칸 맨 아래(사본 앱 1500×950 — 본문 칸 위 끝 302, 스크롤 1474).
out.bottom = run(() => { box.scrollTop = 1474 })
// 본문 칸이 조금만 내려가 칸 머리가 머리 띠 아래이지만 칸 위로 가려 있다.
out.little = run(() => { box.scrollTop = 120 })
// 칸 안에서 보인다.
out.visible = run(() => { box.scrollTop = 0 })
// 좁은 창에서 쌓인 칸이 화면 위로 나가 있다 — 칸을 올린 뒤에도 가려 있어 페이지를 옮긴다.
out.stacked = run(() => { box.top = -500; box.scrollTop = 300 })
// 넘치지 않는 칸은 스크롤 칸이 아니다 — 페이지 길(전과 같음).
out.short = run(() => { box.top = -200; box.scrollTop = 0; box.scrollHeight = 653 })
// 스크롤 칸 없이 페이지 본문(stMain) 바로 안.
out.page = run(() => { box.scrollHeight = 2200; box.overflowY = 'visible'; box.top = -300 })
// 떨어진 칸은 건드리지 않는다.
out.detached = run(() => {
  box.overflowY = 'auto'; box.top = 302; box.scrollTop = 1474; head.isConnected = false
})
process.stdout.write(JSON.stringify(out))
"""


def test_a_fresh_side_head_in_the_side_scroll_box_scrolls_only_that_box() -> None:
    """설비 마스터 오른쪽 칸 본문 칸(넘치면 스크롤하는 칸, 오른쪽 칸은 sticky) 안에 새로 연 칸 —
    바로 `scrollIntoView` 하면 Chrome 이 붙은 자리가 아니라 원래 흐름 자리로 셈해 바깥 페이지
    (stMain)까지 밀어 왼쪽 표가 튀었다(사본 앱 1500×950 — stMain 0 → 223px, 250 → 310px). 그림자
    DOM 밖으로 건너 올라가 가장 가까운 넘치는 스크롤 칸을 찾아 그 칸만 칸 머리까지
    올리고(`scrollBoxOf`·`boxScrollFor`), 그래도 머리 띠 아래로 가려 있을 때만(쌓인 좁은 창·스크롤
    칸이 없는 페이지 흐름) 전처럼 `scrollIntoView` 한다."""
    pure = _node({}, _NEW_RUNNER)
    assert pure["box"] == [0, 0, 248, 0, 500]

    out = _node({}, _HEAD_BOX_RUNNER, source=_fake_dom_source())

    start = [{"block": "start"}]
    assert out == {
        "bottom": {"box": 0, "page": None},
        "little": {"box": 0, "page": None},
        "visible": {"box": 0, "page": None},
        "stacked": {"box": 0, "page": start},
        "short": {"box": 0, "page": start},
        "page": {"box": 0, "page": start},
        "detached": {"box": 1474, "page": None},
    }
    assert "const PAGE_SCROLLER = '[data-testid=\"stMain\"]'" in JS


def test_the_new_unit_panel_has_no_spread_choice() -> None:
    """「새 호기」 칸에 호기별 함께 넣기 체크 · 경고가 없고 초안 · op 도 그 값을 싣지 않는다(늘 넣고
    결과 알림이 대수를 적는다)."""
    assert "propagate" not in JS
    assert "emg-checkline" not in JS and "emg-checkline" not in CSS


_ADD_TIP_RUNNER = """
const panel = (fields) => ({
  mode: 'side', panel: 'new', base: 'b1', columns: [{ name: '설비명', kind: 'name' }],
  groups: [[0, '호기 정보', 'common', '', [0]]], blank: [''], required: [0],
  tiers: { required: [[0, false]] },
  draft: { seq: 3, values: [''] }, checked: 3, errors: {}, warns: {}, locks: {},
  ...fields,
})
const look = () => {
  const add = buttonOf('호기 추가')
  const tip = host.querySelector('.emg-tip')
  const wrap = add.parentNode
  return {
    disabled: add.disabled,
    tip: tip.textContent,
    role: tip.getAttribute('role'),
    sibling: wrap.children[1] === tip,
    wrapped: wrap.className,
    described: [add.getAttribute('aria-describedby'), wrap.getAttribute('aria-describedby')].every(
      (id) => id === tip.id && Boolean(id)),
    tab: wrap.tabIndex,
    focusKeys: [wrap.dataset.fk, add.dataset.fk],
    line: host.querySelectorAll('p').map((node) => node.textContent),
    title: add.title || '',
  }
}
mount(panel({ blocked: true, hint: '아직 추가할 수 없습니다 — 설비명 칸을 확인합니다' }))
results.blocked = look()
const field = host.querySelector('[data-fk="n0"]')
field.value = 'EQ-09'
fire(field, 'input')
results.typed = look()
fire(field, 'blur')
results.sent = look()
mount(panel({
  blocked: false, hint: '추가할 수 있습니다 — 반입일정 칸이 비거나',
  draft: { seq: 5, values: ['EQ-09'] }, checked: 5,
}))
results.waiting = look()
mount(panel({ blocked: false, hint: '', draft: { seq: 6, values: ['EQ-09'] }, checked: 6 }))
results.ready = look()
const filled = host.querySelector('[data-fk="n0"]')
filled.value = ''
fire(filled, 'input')
results.emptied = look()
process.stdout.write(JSON.stringify(results))
"""


def test_the_add_button_says_why_in_a_tip_and_the_panel_keeps_no_line() -> None:
    """「아직 추가할 수 없습니다 …」 는 칸에 늘 서지 않고 「호기 추가」 풍선이다(2026-11-05 사용자
    답). 꺼진 단추는 마우스 · 초점을 받지 않으므로 감싼 칸이 받는다 — 꺼진 동안은 그 칸이 탭
    자리이고(켜지면 단추가 탭 자리) 다시 그릴 때의 초점 표지도 탭 자리를 따라간다. 판정 전이면 옛
    판정 글을 풍선에 보이지 않고, 더 말할 것이 없으면 풍선을 세우지 않는다. 「확인 중」 은 보낸
    초안의 판정을 기다릴 때만이다 — 아직 보내지 않은 글에는 아무 확인도 돌지 않아, 빈 필수 칸이
    있으면 그 칸 이름을, 없으면 칸을 벗어나면 확인한다고 말한다."""
    runner = _FAKE_DOM + _MOUNT_LOADER + _ADD_TIP_RUNNER
    result = _node({}, runner, source=_fake_dom_source())

    shape = {
        "role": "tooltip",
        "sibling": True,
        "wrapped": "emg-tip-host",
        "described": True,
        "line": [],
        "title": "",
    }
    off = {**shape, "disabled": True, "tab": 0, "focusKeys": ["add", ""]}
    on = {**shape, "disabled": False, "tab": -1, "focusKeys": ["", "add"]}
    assert result["blocked"] == {
        **off,
        "tip": "아직 추가할 수 없습니다 — 설비명 칸을 확인합니다",
    }
    assert result["typed"] == {**on, "tip": "칸을 벗어나면 확인합니다"}
    assert result["sent"] == {**on, "tip": "고친 칸을 확인하는 중입니다"}
    assert result["waiting"] == {**on, "tip": "추가할 수 있습니다 — 반입일정 칸이 비거나"}
    assert result["ready"] == {**on, "tip": ""}
    assert result["emptied"] == {
        **off,
        "tip": "아직 추가할 수 없습니다 — 설비명 칸을 확인합니다",
    }


_LEAVING_RUNNER = """
const sent = []
const data = {
  mode: 'side', panel: 'new', base: 'b1', columns: [{ name: '설비명', kind: 'name' }],
  groups: [[0, '호기 정보', 'common', '', [0]]], blank: [''], required: [0],
  tiers: { required: [[0, false]] }, blocked: false, hint: '',
  draft: { seq: 6, values: ['EQ-09'] }, checked: 6, errors: {}, warns: {}, locks: {},
}
const cleanup = globalThis.__mount({
  data, parentElement, setTriggerValue() {},
  setStateValue(name, value) {
    if (name === 'outbox') sent.push(value.ops.map((op) => op.op))
  },
})
const S = host.__emg
fire(buttonOf('호기 추가'), 'click')
results.pressed = sent.length
for (const handler of host.listeners.focusout) handler({ relatedTarget: null })
results.focusLeft = sent.length
cleanup()
results.left = sent.length
enqueue(S, { op: 'cell', id: 'a', col: '설비명', text: 'EQ-10' }, [])
cleanup()
results.unsentLeft = sent
process.stdout.write(JSON.stringify(results))
"""


def test_a_mount_leaving_does_not_resend_what_it_already_sent() -> None:
    """「호기 추가」 는 그 회차가 「새 호기」 마운트를 내리고 칸 고르기를 「호기 상세」 로 적는다.
    보낸 `add` 의 ack 를 받지 못한 채 내려가는 마운트가 다시 보내면 그 둘째 회차가 고르기 값을
    브라우저에 적용하기 전의 옛 「새 호기」 를 실어, 눌림은 「호기 상세」 인데 본문은 빈 「새 호기
    추가」 폼으로 어긋났다(g5-01 — 같은 세션 이어 추가 10번에 6번, 샘플 관측). 초점이 나갈 때도
    마찬가지다. 아직 보내지 않은 op 는 내려갈 때도 보낸다."""
    runner = _FAKE_DOM + _MOUNT_LOADER + _LEAVING_RUNNER
    result = _node({}, runner, source=_fake_dom_source())

    assert result["pressed"] == 1
    assert result["focusLeft"] == 1
    assert result["left"] == 1
    assert result["unsentLeft"] == [["add"], ["add", "cell"]]


_LOCK_TEXT_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
process.stdout.write(JSON.stringify({
  search: [searchLockText(''), searchLockText('  '), searchLockText('WBA')],
  condition: [conditionLockText(0, 0), conditionLockText(2, 0), conditionLockText(2, 5)],
  loadAll: [loadAllLockText(641, 641), loadAllLockText(640, 641), loadAllLockText(1000, 1200)],
  apply: [applyLockText(3, true, ''), applyLockText(0, false, ''), applyLockText(0, true, ''),
    applyLockText(0, true, '잠긴 칸')],
  shift: [shiftLockText(4, 7), shiftLockText(0, null), shiftLockText(0, 7),
    shiftLockText(0, 7, '잠긴 칸'), shiftLockText(0, null, '잠긴 칸'),
    shiftLockText(4, 7, '잠긴 칸')],
  held: (() => {
    const row = (id, ...values) => ({ id, values })
    const lockedIds = (ids) => (line) => ids.includes(line.id)
    const pick = (rows, locked) => {
      const cell = lockedShiftCell(rows, [0, 1], locked)
      return cell ? [cell[0].id, cell[1]] : null
    }
    const dated = row('a', '2026-11-01', '')
    const empty = row('b', '', '')
    const other = row('c', '', '2026-11-02')
    return [
      pick([dated], lockedIds(['a'])),
      pick([empty, other], lockedIds(['b', 'c'])),
      pick([dated, other], lockedIds(['a'])),
      pick([empty], lockedIds(['b'])),
      pick([dated], lockedIds([])),
    ]
  })(),
}))
"""


def test_each_locked_button_can_say_why_and_an_unlocked_one_says_nothing() -> None:
    """잠긴 「불러오기」 · 「맞는 0대 불러오기」 · 「넣기 (0칸)」 · 「밀기 (0칸)」 와 다 불러온 뒤의
    「전체 n대 불러오기」 는 까닭이 있고(설계 규칙 UI-INP-07, g5-08 · g5-09), 켜진 단추는 빈 글이라
    풍선이 서지 않는다. 호기를 다 불러오지 못한 상한 초과(1,000 / 1,200)는 켠 채로 둔다. 「밀기」 는
    낡은 세션처럼 일정이 잠겨 0칸이면 값을 고치라는 말 대신 그 잠금 까닭을 말한다."""
    result = _node({}, _LOCK_TEXT_RUNNER)

    assert result["search"] == [
        "설비명을 치면 누를 수 있습니다",
        "설비명을 치면 누를 수 있습니다",
        "",
    ]
    assert result["condition"] == [
        "조건을 고르면 누를 수 있습니다",
        "조건에 맞는 호기가 없습니다",
        "",
    ]
    assert result["loadAll"] == ["전체를 불러왔습니다", "", ""]
    assert result["apply"] == [
        "",
        "넣을 값을 고르면 누를 수 있습니다",
        "바뀔 칸이 없습니다",
        "잠긴 칸",
    ]
    assert result["shift"] == [
        "",
        "밀 날 수를 적으면 누를 수 있습니다",
        "밀 일정이 있는 칸이 없습니다",
        "잠긴 칸",
        "잠긴 칸",
        "",
    ]
    # 일정이 있는 칸이 모두 잠겼을 때만 잠금이 까닭이다 — 풀린 일정이 있거나 일정이 없으면 아니다.
    assert result["held"] == [["a", 0], ["c", 1], None, None, None]


_LOADER_LOCK_RUNNER = """
const data = {
  mode: 'loader', names: ['EQ-01', 'EQ-02'], ids: {}, loaded: ['s:EQ-01', 's:EQ-02'],
  loadedCount: 2, total: 2, alertIds: [],
  conditions: { columns: [], values: [], codes: [], widths: [] },
}
const look = (name) => {
  const target = buttonOf(name)
  const wrap = target.parentNode
  const tip = wrap.querySelector('.emg-tip')
  return {
    disabled: target.disabled, wrapped: wrap.className, tip: tip.textContent,
    tab: wrap.tabIndex, keys: [wrap.dataset.fk, target.dataset.fk],
  }
}
mount(data)
results.goEmpty = look('불러오기')
results.allLoaded = look('전체 2대 불러오기')
const input2 = host.querySelector('[data-fk="search"]')
input2.value = 'EQ'
fire(input2, 'input')
results.goTyped = look('불러오기')
mount({ ...data, loaded: ['s:EQ-01'], loadedCount: 1 })
results.allOpen = look('전체 2대 불러오기')
process.stdout.write(JSON.stringify(results))
"""


def test_the_locked_loader_buttons_keep_a_tip_host_that_follows_the_lock() -> None:
    """꺼진 단추는 마우스 · 초점을 받지 않아 감싼 칸이 풍선과 탭 자리를 받고, 켜지면 단추에 돌려준다
    (설계 규칙 UI-INP-07). 다 불러온 「전체 n대 불러오기」 는 눌러도 0대라 잠근다(g5-08)."""
    runner = _FAKE_DOM + _MOUNT_LOADER + _LOADER_LOCK_RUNNER
    result = _node({}, runner, source=_fake_dom_source())

    off = {"disabled": True, "wrapped": "emg-tip-host", "tab": 0}
    on = {"disabled": False, "wrapped": "emg-tip-host", "tab": -1, "tip": ""}
    assert result["goEmpty"] == {
        **off,
        "tip": "설비명을 치면 누를 수 있습니다",
        "keys": ["search-go", ""],
    }
    assert result["goTyped"] == {**on, "keys": ["", "search-go"]}
    assert result["allLoaded"] == {
        **off,
        "tip": "전체를 불러왔습니다",
        "keys": ["load-all", ""],
    }
    assert result["allOpen"] == {**on, "keys": ["", "load-all"]}


def test_the_selection_bar_takes_the_loader_line_place_while_rows_are_picked() -> None:
    """고른 동안 고른 줄 띠가 표 위 작업 줄(불러오기 줄 · 메뉴 「엑셀·CSV」) 자리에 같은 높이로 대신
    선다(2026-11-08 사용자 결정 g01 (가)). 띠는 흐름 밖(표 틀 기준 절대 자리 — `placeBand` 가
    불러오기 칸에서 잰다)이라 줄을 골라도 표가 밀리지 않고(설계 규칙 UI-PRF-03), 창 아래 끝에
    붙던 띠와 그 띠가 덮은 줄을 올리던 길 · 닫을 때 자리를 남기던 길은 걷었다. 고른 동안 페이지
    서식이 불러오기 줄(그림자 DOM — 상속 변수)과 메뉴를 숨겨 자리는 지키고, 칸 차례는 표 앞이다."""
    assert "[sel, bar, note, box, foot]" in _function("buildGridSkeleton")
    for gone in ("clearOfBar", "holdPlace", "pageMain"):
        assert gone not in JS, gone
    bar = re.search(r"\n\.emg-sel \{(?P<body>[^}]*)\}", CSS)
    assert bar is not None
    assert "position: absolute" in bar["body"] and "sticky" not in bar["body"]
    frame = re.search(r"\n\.emg-grid \{(?P<body>[^}]*)\}", CSS)
    assert frame is not None and "position: relative" in frame["body"]
    assert "overflow" not in frame["body"]
    loader = re.search(r"\n\.emg-lb \{(?P<body>[^}]*)\}", CSS)
    assert loader is not None and "visibility: var(--emd-sel-hide, visible)" in loader["body"]
    style = emg.tools_menu_style()
    assert f"html[data-emg-sel] .st-key-{emg.LOADER_KEY} {{ --emd-sel-hide: hidden; }}" in style
    item = f'[data-testid="stLayoutWrapper"]:has(> .st-key-{emg.TOOLS_KEY})'
    assert f"html[data-emg-sel] {item} {{ visibility: hidden; }}" in style
    assert '"loaderKey": LOADER_KEY' in SOURCE
    assert "root.dataset.emgSel = '1'" in _function("markSelecting")


_BAND_RUNNER = """
document.documentElement.dataset = {}
const R = {}
const toggleOf = (label) => S.selBar.querySelectorAll('button').find(
  (node) => node.getAttribute('aria-haspopup') === 'dialog' && node.textContent.startsWith(label))
const panelOf = (toggle) => toggle.parentNode.children[1]
const label = () => {
  const active = document.activeElement
  return active ? active.getAttribute('aria-label') || active.textContent.trim() : null
}
;(async () => {
  R.idle = { hidden: S.selBar.hidden, mark: document.documentElement.dataset.emgSel || null }
  toggleRow(S, 'a', false)
  R.picked = {
    hidden: S.selBar.hidden,
    mark: document.documentElement.dataset.emgSel || null,
    count: S.selBar.querySelector('.emg-sel-count').textContent,
    buttons: S.selBar.children.map((node) => node.textContent.trim()),
    selects: S.selBar.querySelectorAll('select').length,
  }
  let toggle = toggleOf('값 넣기')
  toggle.focus()
  fire(toggle, 'click')
  let panel = panelOf(toggle)
  R.setOpen = {
    open: !panel.hidden,
    focus: label(),
    inside: panel.querySelectorAll('button').map((node) => node.textContent.trim()),
  }
  fire(document.activeElement, 'keydown', { key: 'Escape' })
  R.setClosed = { open: !panel.hidden, back: document.activeElement === toggle }
  toggle = toggleOf('일정 밀기')
  toggle.focus()
  fire(toggle, 'click')
  panel = panelOf(toggle)
  R.shiftOpen = {
    open: !panel.hidden,
    focus: label(),
    text: panel.textContent.replace(/\\s+/g, ' ').trim(),
  }
  fire(document.activeElement, 'keydown', { key: 'Escape' })
  R.shiftClosed = { open: !panel.hidden, back: document.activeElement === toggle }
  const buttons = S.selBar.querySelectorAll('button')
  const release = buttons.find((node) => node.textContent === '선택 풀기')
  fire(release, 'click')
  R.released = { hidden: S.selBar.hidden, mark: document.documentElement.dataset.emgSel || null }
  toggleRow(S, 'b', false)
  cleanup()
  R.unmounted = document.documentElement.dataset.emgSel || null
  process.stdout.write(JSON.stringify(R))
})()
"""


def test_the_selection_bar_is_one_line_and_its_edits_open_in_popups() -> None:
    """띠는 한 줄 — 「선택 n대 · 값 넣기 ▾ · 일정 밀기 ▾ · 선택 n대 지우기 · 선택 풀기」 이고, 칸
    고르기 · 값 · 넣기와 날 수 · 밀기는 팝업 안이다. 팝업을 열면 초점이 패널 첫 칸으로 가고 Esc 로
    닫히며 초점은 여는 단추로 돌아온다. 고른 동안만 `<html data-emg-sel>` 이 서고 선택을 풀거나
    표가 내려가면 걷힌다."""
    runner = _BURST_RUNNER[: _BURST_RUNNER.index("const R = {}")] + _BAND_RUNNER
    result = _node({}, runner, source=FAKE_DOM + _fake_dom_source())
    assert result["idle"] == {"hidden": True, "mark": None}
    assert result["picked"] == {
        "hidden": False,
        "mark": "1",
        "count": "선택 1대",
        "buttons": ["선택 1대", "값 넣기", "일정 밀기", "선택 1대 지우기", "선택 풀기"],
        "selects": 0,
    }
    assert result["setOpen"]["open"] is True
    assert result["setOpen"]["focus"] == "값을 넣을 칸"
    assert result["setOpen"]["inside"][-1].startswith("넣기 (")
    assert result["setClosed"] == {"open": False, "back": True}
    assert result["shiftOpen"]["open"] is True
    assert result["shiftOpen"]["focus"] == "밀 날 수"
    assert result["shiftOpen"]["text"].startswith("반입·Qual 일정")
    assert result["shiftClosed"] == {"open": False, "back": True}
    assert result["released"] == {"hidden": True, "mark": None}
    assert result["unmounted"] is None


_READ_ONLY_BAND_RUNNER = """
document.documentElement.dataset = {}
const R = {}
toggleRow(S, 'a', false)
R.picked = S.selBar.children.map((node) => node.textContent.trim())
cleanup()
process.stdout.write(JSON.stringify(R))
"""


def test_a_read_only_grid_keeps_the_selection_band_without_its_edit_tools() -> None:
    """화면 등급으로 표를 고칠 수 없으면(`readOnly` — `read_only_data`) 고른 줄 띠는 「선택 n대 ·
    선택 풀기」 만 — 값 넣기 · 일정 밀기 · 선택 n대 지우기는 세우지 않는다(설계 규칙 UI-INP-07
    등급 예외 · 2026-11-18 구현 확인 보드 「고칠 것」 — 모든 등급이 같은 표, 권한 없는 칸만
    잠금). 호기 상세의 이 호기 지우기 · 이 호기로 새 호기 만들기도 같은 판정이다."""
    head = _BURST_RUNNER[: _BURST_RUNNER.index("const R = {}")]
    head = head.replace("const component = {", "data.readOnly = true\nconst component = {", 1)
    result = _node({}, head + _READ_ONLY_BAND_RUNNER, source=FAKE_DOM + _fake_dom_source())
    assert result["picked"] == ["선택 1대", "선택 풀기"]
    assert "if (!S.data.readOnly) buildBulkTools(S, bar, rows)" in _function("buildSelection")
    assert "} else if (!data.readOnly) {" in _function("drawDetail")
    locked = emg.read_only_data({"columns": [{"name": "설비명"}], "rows": []}, "까닭")
    assert locked["readOnly"] is True
    assert "readOnly" not in emg.read_only_data({"columns": [], "rows": []}, None)


# 칸 고치기 길을 모두 눌러 본다 — 표(Enter · F2 · 글자 치기 · 한 칸 · 여러 칸 붙여넣기)와
# 호기 상세(입력 칸 · 고르기 칩). 받은 data 를 그대로 올린다(등급 시험이 대역이 받은 data 를
# 넣는다 — AppTest 는 JS 를 못 돌린다).
_TRY_EDITS_RUNNER = r"""
FakeNode.prototype.select = function () {}
FakeNode.prototype.scrollIntoView = function () {}
Object.defineProperty(FakeNode.prototype, 'innerHTML', { set() { this.textContent = '' } })
document.querySelector = () => null
document.documentElement = { clientWidth: 1200 }
// 표가 칸을 찾는 겹친 선택자(「.칸[속성]」 한 덩이).
const oneMatch = FakeNode.prototype.matches
FakeNode.prototype.matches = function (selector) {
  return selector.split(',').some((part) => {
    const text = part.trim()
    const bits = text.match(/\.[\w-]+|\[[^\]]+\]/g)
    if (!bits || bits.join('') !== text) return oneMatch.call(this, text)
    return bits.every((bit) => oneMatch.call(this, bit))
  })
}
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const mountOn = (data) => {
  const parentElement = new FakeNode('div')
  const host = parentElement.appendChild(new FakeNode('div'))
  host.className = 'emg'
  const sent = []
  const cleanup = globalThis.__mount({
    data, parentElement, setTriggerValue() {}, setStateValue: (name) => sent.push(name),
  })
  return { host, S: host.__emg, cleanup, sent }
}
const head = (node) => String(node.title || '').split('\n')[0]
const R = {}
;(async () => {
  if (input.grid) {
    const { S, cleanup, sent } = mountOn(input.grid)
    const body = S.body
    const values = () => body.querySelectorAll('.emg-c').filter(
      (node) => node.dataset.id !== undefined && Number(node.dataset.col) !== S.model.nameCol)
    const id = values()[0].dataset.id
    const kinds = S.model.columns.map((column) => column.kind)
    const textCol = values().map((node) => Number(node.dataset.col))
      .find((k) => kinds[k] !== 'choice')
    const press = () => values().find(
      (node) => node.dataset.id === id && Number(node.dataset.col) === textCol).children[0]
    const opened = (act) => {
      S.edit = null
      paintWindow(S)
      act()
      const got = Boolean(S.edit) || body.querySelectorAll('.emg-ed').length > 0
      S.edit = null
      paintWindow(S)
      return got
    }
    const paste = (text) => fire(press(), 'paste', { clipboardData: { getData: () => text } })
    R.grid = {
      cells: values().length,
      locked: values().filter((node) => node.classList.contains('is-locked')).length,
      tips: Array.from(new Set(values().map(head))),
      enter: opened(() => fire(press(), 'keydown', { key: 'Enter' })),
      f2: opened(() => fire(press(), 'keydown', { key: 'F2' })),
      typed: opened(() => fire(press(), 'keydown', { key: 'X' })),
      direct: opened(() => startEdit(S, id, textCol)),
    }
    paste('P1')
    R.grid.pasteOne = { ops: S.box.ops.length, note: S.note }
    paste('P1\tP2\nP3\tP4')
    R.grid.pasteMany = { ops: S.box.ops.length, note: S.note }
    await tick(400)
    R.grid.sent = sent.length
    cleanup()
  }
  if (input.detail) {
    const { host, S, cleanup, sent } = mountOn(input.detail)
    const inputs = host.querySelectorAll('.emg-input')
    for (const node of inputs) {
      if (node.disabled) continue
      node.value = 'Y'
      fire(node, 'input')
      fire(node, 'keydown', { key: 'Enter' })
    }
    const chips = host.querySelectorAll('.emg-chip')
    for (const chip of chips) fire(chip, 'click')
    await tick(400)
    R.detail = {
      inputs: inputs.length,
      open: inputs.filter((node) => !node.disabled).length,
      chips: chips.length,
      tips: Array.from(new Set(host.querySelectorAll('.emg-field').map(head))),
      ops: S.box.ops.length,
      sent: sent.length,
    }
    cleanup()
  }
  process.stdout.write(JSON.stringify(R))
})()
"""


def tried_master_edits(
    grid: dict[str, Any] | None = None, detail: dict[str, Any] | None = None
) -> dict[str, Any]:
    """표 · 호기 상세 data 를 가짜 DOM 에 올려 칸 고치기 길을 모두 눌러 본 결과 — 표는 칸 수 · 잠긴
    칸 수 · 풍선 첫 줄 · 편집기가 열렸나(Enter · F2 · 글자 · 바로 열기) · 붙여넣기 뒤 op 수와 한 줄
    · 보낸 수, 호기 상세는 입력 칸 수 · 열린 칸 수 · 칩 수 · 풍선 첫 줄 · op 수 · 보낸 수. 등급
    시험이 대역이 받은 data 를 그대로 넣는다(AppTest 는 JS 를 못 돌린다)."""
    return _node(
        {"grid": grid, "detail": detail}, _TRY_EDITS_RUNNER, source=FAKE_DOM + _fake_dom_source()
    )


GRADE_REASON = "DEMO 등급 까닭"


def _try_grid() -> dict[str, Any]:
    return {
        "mode": "grid",
        "base": "b1",
        "view": "v1",
        "limits": {"outboxCells": 10000, "pasteCells": 5000},
        "columns": [
            {"name": "설비명", "kind": "name", "width": "name"},
            {"name": "Model", "kind": "text", "width": "m"},
            {"name": "동", "kind": "choice", "width": "s", "options": ["C1", "C2"], "blank": True},
            {"name": "Area", "kind": "text", "width": "m"},
        ],
        "colSets": [["all", "전체", "", [1, 2, 3]]],
        "lockSets": {"module": [1, 2, 3]},
        "lockReasons": {"module": "DEMO 묶음 까닭"},
        "rows": [
            {"id": "a", "values": ["EQ-1", "x", "C1", "p"]},
            {"id": "b", "values": ["EQ-2", "y", "C2", "q"], "locks": ["module"]},
        ],
    }


def _try_detail() -> dict[str, Any]:
    return {
        "mode": "side",
        "panel": "detail",
        "base": "b1",
        "columns": _try_grid()["columns"],
        "groups": [["main", "기본", "", "", [1, 2, 3]]],
        "lockSets": {},
        "lockReasons": {},
        "unit": {"id": "a", "values": ["EQ-1", "x", "C1", "p"], "downtime": [], "deletable": True},
    }


def test_a_read_only_grid_and_detail_open_no_editor_and_send_nothing() -> None:
    """화면 등급으로 설비 마스터를 고칠 수 없으면(`read_only_data`) 표의 모든 칸이 잠긴 칸 길을
    탄다 — Enter · F2 · 글자 치기로 편집기가 열리지 않고, 한 칸 · 여러 칸 붙여넣기는 op 를 보내지
    않고 까닭 한 줄을 남기며, 칸 풍선 첫 줄이 까닭이다. 호기 상세도 입력 칸이 모두 꺼지고 고르기
    칩이 서지 않는다. 전에는 잠금 갈래에 칸 이름을 실어(브라우저는 칸 번호로 대조) 한 칸도 잠기지
    않았고 칸마다 서버 거절 알림이 섰다(2026-11-18 E2E). 같은 data 를 등급 없이 올리면 모두
    열린다(대조)."""
    locked = tried_master_edits(
        emg.read_only_data(_try_grid(), GRADE_REASON),
        emg.read_only_data(_try_detail(), GRADE_REASON),
    )
    grid = locked["grid"]
    assert grid["cells"] == grid["locked"] == 6
    assert grid["tips"] == [GRADE_REASON], "등급 까닭이 다른 잠금보다 앞이다"
    assert [grid[name] for name in ("enter", "f2", "typed", "direct")] == [False] * 4
    assert grid["pasteOne"] == {"ops": 0, "note": GRADE_REASON}
    assert grid["pasteMany"] == {"ops": 0, "note": GRADE_REASON}
    assert grid["sent"] == 0
    detail = locked["detail"]
    assert detail["inputs"] == 3 and detail["open"] == 0 and detail["chips"] == 0
    assert detail["tips"] == [GRADE_REASON]
    assert detail["ops"] == detail["sent"] == 0

    plain = tried_master_edits(
        emg.read_only_data(_try_grid(), None), emg.read_only_data(_try_detail(), None)
    )
    grid = plain["grid"]
    assert grid["locked"] == 3, "묶음 잠금 줄만"
    assert [grid[name] for name in ("enter", "f2", "typed", "direct")] == [True] * 4
    assert grid["pasteOne"]["ops"] == 1 and grid["pasteMany"]["ops"] == 2
    assert grid["sent"] == 1
    detail = plain["detail"]
    assert detail["open"] == 2 and detail["chips"] == 3
    assert detail["ops"] == 4 and detail["sent"] > 0, "입력 칸 둘 · 지금 값이 아닌 칩 둘"


_PLACE_TIP_RUNNER = """
const box = (left) => ({ getBoundingClientRect: () => ({ left }) })
const place = (frameLeft, tipLeft) => {
  const tip = { ...box(tipLeft), style: { transform: 'translateX(9px)' } }
  placeTip({ closest: () => box(frameLeft) }, tip)
  return tip.style.transform
}
const orphan = { style: { transform: '' } }
placeTip({ closest: () => null }, orphan)
process.stdout.write(JSON.stringify({
  left: place(332, 232),
  inside: place(332, 340),
  edge: place(332, 332),
  rounded: place(332, 331.5),
  orphan: orphan.style.transform,
  over: [overPx(911, 781), overPx(700, 781), overPx(100.2, 100)],
}))
"""


def test_a_tip_that_would_go_under_the_sidebar_moves_back_into_the_frame() -> None:
    """풍선은 단추 오른쪽 끝에 맞춰 왼쪽으로 자라, 띠가 접혀 「넣기」 가 둘째 줄 맨 앞에 오면 x
    232 ~ 419 로 떠서 오른쪽 끝 300 인 사이드바 밑에 앞 글자가 잘렸다(샘플 관측 · UI-INP-07 ·
    UI-ACC-02).
    뜰 때 칸 왼쪽 끝 밖으로 나간 만큼만 민다 — 칸 안이면 그대로다. 줄 접힘이 창 폭을 따라 달라
    서식으로 정하지 않는다. 꺼진 단추는 감싼 칸이 마우스 · 초점을 받는다."""
    result = _node({}, _PLACE_TIP_RUNNER, source=_sections() + _function("placeTip"))

    assert result == {
        "left": "translateX(100px)",
        "inside": "",
        "edge": "",
        "rounded": "translateX(1px)",
        "orphan": "",
        "over": [130, 0, 1],
    }
    wrap = _function("tipWrap")
    assert "host.addEventListener('pointerenter', place)" in wrap
    assert "host.addEventListener('focusin', place)" in wrap


def test_the_add_tip_shows_on_hover_and_keyboard_focus_and_has_the_app_tip_look() -> None:
    """풍선은 마우스(꺼진 단추 위에서도 감싼 칸이 받는다)와 키보드 초점으로 뜨고, 눌렀을 때 초점이
    남아 있어도 떠 있지 않도록 `:focus-within` 은 쓰지 않는다. 꼴은 편집 표 풍선(`.eg-tip`)과 같다
    — 칸 글자색 바탕에 칸 면 색 글자, 12px. 빈 풍선은 서지 않는다."""
    assert ".emg-hint" not in CSS and "emg-hint" not in JS
    assert ".emg-tip-host:hover > .emg-tip" in CSS
    assert ".emg-tip-host:focus-visible > .emg-tip" in CSS
    assert ".emg-btn:focus-visible + .emg-tip" in CSS
    assert "focus-within" not in CSS
    assert ".emg-tip:empty" in CSS
    tip = re.search(r"\.emg-tip \{(?P<body>.*?)\}", CSS, re.S)
    assert tip is not None
    for rule in (
        "background: var(--emg-text)",
        "color: var(--emg-surface)",
        "font-size: 12px",
        "pointer-events: none",
    ):
        assert rule in tip["body"]


def test_the_delete_buttons_carry_the_tip_and_a_lock_or_a_new_unit_takes_it_away() -> None:
    """저장본 호기를 지우면 어떻게 되나는 지우기 단추 두 곳의 풍선이다(토스트는 값 한 줄 —
    UI-NTF-09). 잠긴 까닭이 먼저이고, 바로 빠지는 새 호기에는 달지 않는다."""
    assert "const DELETE_TIP = '리비전을 저장하면 모든 설비 시나리오에서 지워집니다" in JS
    assert "remove.title = unit.deleteLock || (unit.tag === 'new' ? '' : DELETE_TIP)" in JS
    assert "remove.title = lock || (rows.some((row) => row.tag !== 'new') ? DELETE_TIP : '')" in JS


def test_redrawn_side_controls_keep_focus_and_a_panel_an_action_opened_shows_its_head() -> None:
    """칩·「양식 비우기」 는 칸을 다시 그려도 초점이 돌아온다(data-fk — 키보드로
    채우다 칸 처음으로 가지 않게). 상세 칩도 회차가 돌아와 다시 그려도 같다. 조작이 연 다른 칸은
    칸 머리를 보인다(「호기 추가」 뒤 상세·가져오기 뒤 새 호기 칸)."""
    assert "chip.dataset.fk = 'n' + k + '=' + option" in JS
    assert "chip.dataset.fk = 'f' + k + '=' + value" in JS
    assert "reset.dataset.fk = 'reset'" in JS
    assert "if (first && data.revealHead) revealHead(root)" in JS
    assert re.search(r"\.emg-side\s*\{[^}]*scroll-margin-top:\s*80px", CSS)


def test_the_scope_legend_keeps_three_words_and_puts_the_saving_words_in_tips() -> None:
    """범례는 표지 낱말 셋이다 — 저장 말은 표지 풍선이다(설계 규칙 UI-TXT-01). 긴 가정 시나리오
    이름이 범례를 제 줄로 내려 표가 26px 밀렸다(g5-13, 샘플 관측)."""
    bar = _function("paintBar")
    for word, tip in (
        ("'시나리오'", "scenario + '에만 저장'"),
        ("'배치'", "'공식 배치에 저장'"),
        ("'공통'", "'모든 설비 시나리오에 함께 저장'"),
    ):
        assert word in bar and tip in bar
    assert "scenario + '에만 저장(공식과 다른 것만)'" in bar
    assert "mark.title = tip" in bar and "el('span', null, ' '" not in bar


def test_the_process_count_and_the_none_value_keep_their_shape() -> None:
    """공정별 판의 대수는 한 덩이로 서고(g5-17 — 「20 / 대」 로 접혔다), 호기 상세의 「없음」 은
    곁 링크와 떨어진다(g5-23 — 「없음비가동 일정 표에서 고치기」 로 읽혔다)."""
    tail = re.search(r"\.emg-option \.emg-tail \{(?P<body>[^}]*)\}", CSS)
    assert tail is not None
    for rule in ("flex: none", "white-space: nowrap"):
        assert rule in tail["body"]
    assert "el('span', 'emg-muted emg-none', '없음')" in _function("drawDetail")
    assert re.search(r"\.emg-none \{[^}]*margin-right: 10px", CSS)


_PENDING_RUNNER = """
const box = createBox()
rebaseBox(box, 'b1')
const shift = { op: 'shift', ids: ['a', 'b'], days: 7 }
const out = { before: hasPendingOp(box, shift) }
queueOp(box, shift, 100, 1)
out.same = hasPendingOp(box, { op: 'shift', ids: ['a', 'b'], days: 7 })
out.otherDays = hasPendingOp(box, { op: 'shift', ids: ['a', 'b'], days: 3 })
out.otherIds = hasPendingOp(box, { op: 'shift', ids: ['b', 'a'], days: 7 })
out.otherOp = hasPendingOp(box, { op: 'set', ids: ['a', 'b'] })
ackBox(box, 1)
out.acked = hasPendingOp(box, shift)
process.stdout.write(JSON.stringify(out))
"""


def test_a_double_press_on_an_op_button_sends_the_op_once() -> None:
    """선택 띠 「밀기」 를 더블클릭하면 둘째 누름이 첫 op 의 회차가 돌아오기 전에 같은 띠의 단추에
    닿아 shift op 를 하나 더 보냈다 — 날짜가 두 번 밀리고 되돌리기는 한 번만 되돌렸다. 「넣기」·상세
    「되살리기」 는 둘째 op 의 헛결과(「0칸 바뀜」·「0대를 되살렸습니다」)가 첫 결과를 덮었다
    (2026-10-27 E2E). 단추 op 는 같은 op 가 아직 ack 되지 않았으면
    보내지 않는다(`sendOnce` — `hasPendingOp`). 다른 인자(밀 날 수·줄)나 ack 뒤의 누름은 보낸다."""
    assert _node({}, _PENDING_RUNNER) == {
        "before": False,
        "same": True,
        "otherDays": False,
        "otherIds": False,
        "otherOp": False,
        "acked": False,
    }
    once = {
        "bulkSetPanel": ["{ op: 'set', ids: targets"],
        "bulkShiftPanel": ["{ op: 'shift', ids: targets"],
        "rowElement": ["{ op: 'restore', ids: [row.id] }"],
        "onBodyKey": ["{ op: 'restore', ids: [id] }"],
        "drawDetail": [
            "{ op: 'official', id: unit.id }",
            "{ op: 'restore', ids: [unit.id] }",
            "{ op: 'delete', ids: [unit.id] }",
        ],
        "drawChanges": [
            "{ op: 'revert', id: unit.id, col: null }",
            "{ op: 'revert', id: unit.id, col }",
        ],
    }
    for name, ops in once.items():
        body = JS[JS.index(f"function {name}(") :]
        body = body[: body.index("\n}\n")]
        for op in ops:
            assert f"sendOnce(S, {op}" in body, (name, op)
            assert f"enqueue(S, {op}" not in body, (name, op)


_EDITOR_RUNNER = """
const editors = {}
const values = [
  ['multi', '첫째\\n둘째'], ['single', '한 줄'], ['empty', ''],
  ['tall', 'a\\nb\\nc\\nd\\ne\\nf\\ng\\nh'],
]
for (const [name, value] of values) {
  const node = textEditor('emg-ed', value)
  const rows = node.rows === undefined ? null : node.rows
  editors[name] = { tag: node.tagName, value: node.value, rows }
}
process.stdout.write(JSON.stringify(editors))
"""


def test_a_multi_line_value_opens_a_multi_line_editor_that_keeps_its_line_breaks() -> None:
    """엑셀 Alt+Enter 칸(줄바꿈 든 값)을 표 칸·호기 상세 칸에서 고치면 한 줄 칸(input)이 줄바꿈을
    지워, 끝에 「!」 만 붙여도(상세는 Enter 만 눌러도) 「첫째 둘째 → 첫째둘째!」 가 바뀐 칸으로
    남았다(2026-10-27 E2E). 줄바꿈이 든 값은 여러 줄 칸(textarea)으로 열어 값을 그대로 둔다 — 한
    줄 값은 전처럼 input 이다. 두 편집기와 「새 호기」 칸(가져오기로 든 값)이 모두 이 길로만 칸을
    짓는다."""
    parts = []
    for name in ("el", "textEditor"):
        body = JS[JS.index(f"function {name}(") :]
        parts.append(body[: body.index("\n}\n") + 2])
    source = _FAKE_DOM + "\n".join(parts) + _EDITOR_RUNNER
    result = _node({}, "", source=source)

    assert result == {
        "multi": {"tag": "TEXTAREA", "value": "첫째\n둘째", "rows": 2},
        "single": {"tag": "INPUT", "value": "한 줄", "rows": None},
        "empty": {"tag": "INPUT", "value": "", "rows": None},
        "tall": {"tag": "TEXTAREA", "value": "a\nb\nc\nd\ne\nf\ng\nh", "rows": 6},
    }
    assert "textEditor('emg-ed', S.edit.draft)" in _function("cellElement")
    assert "textEditor('emg-input', S.drafts.has(k) ? S.drafts.get(k) : shown)" in _function(
        "detailField"
    )
    assert "textEditor('emg-input', value)\n    input.id = id\n    input.dataset.fk = 'n' + k" in JS
    assert "el('input', 'emg-ed')" not in JS
    assert "el('input', 'emg-input')\n    input.id = id" not in JS
    assert re.search(r"\.emg textarea\s*\{[^}]*resize:\s*none", CSS)


def test_the_narrow_check_head_rule_outranks_the_wide_one() -> None:
    """좁은 화면 체크 줄 머리(한 줄 차지)는 넓은 규칙(116px)보다 특정도가 높아야 한다 — 미디어
    규칙이 파일 앞에 있어 같은 선택자면 뒤의 넓은 규칙이 이긴다."""
    narrow = OWN_CSS.split("@media (max-width: 640px)", 1)[1].split("\n}\n", 1)[0]
    assert re.search(r"\.emg-check-row \.emg-check-head\s*\{\s*flex:\s*0 0 100%", narrow)
    assert re.search(r"\n\.emg-check-head\s*\{\s*flex:\s*0 0 116px", OWN_CSS)


# ---------------------------------------------------------------- 불러오기 팝오버(node·가짜 DOM)

_MOUNT_HEAD = "export default function (component) {"
_FAKE_DOM_RUNNER = """
class FakeNode {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase()
    this.children = []
    this.parentNode = null
    this.attributes = {}
    this.dataset = {}
    this.listeners = {}
    this.style = { setProperty() {} }
    this.className = ''
    this.hidden = false
    this.ownText = ''
  }
  appendChild(child) {
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
  set innerHTML(value) {
    this.textContent = ''
  }
  setAttribute(name, value) {
    this.attributes[name] = String(value)
  }
  getAttribute(name) {
    return name in this.attributes ? this.attributes[name] : null
  }
  addEventListener(type, handler) {
    ;(this.listeners[type] = this.listeners[type] || []).push(handler)
  }
  removeEventListener() {}
  get classList() {
    return {
      add: (name) => {
        this.className = (this.className + ' ' + name).trim()
      },
    }
  }
  contains(node) {
    for (let at = node; at; at = at.parentNode) if (at === this) return true
    return false
  }
  getRootNode() {
    return document
  }
  getBoundingClientRect() {
    return { left: 0, width: 300 }
  }
  focus() {
    document.activeElement = this
  }
  click() {
    return fire(this, 'click')
  }
  matches(selector) {
    return selector.split(',').some((part) => {
      const text = part.trim()
      const data = text.match(/^\\[data-([a-z]+)="(.*)"\\]$/)
      if (data) return this.dataset[data[1]] === data[2].replace(/\\\\(.)/g, '$1')
      if (text.startsWith('.')) return this.className.split(/\\s+/).includes(text.slice(1))
      return this.tagName === text.toUpperCase()
    })
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

function fire(target, type, extra) {
  const event = Object.assign({
    type, target, stopped: false,
    stopPropagation() { this.stopped = true },
    preventDefault() {},
  }, extra || {})
  for (let at = target; at && !event.stopped; at = at.parentNode) {
    for (const handler of (at.listeners[type] || []).slice()) handler.call(at, event)
  }
  return event
}

globalThis.document = {
  activeElement: null,
  documentElement: { clientWidth: 1200 },
  body: null,
  createElement: (tag) => new FakeNode(tag),
  addEventListener() {},
  removeEventListener() {},
}

const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const parentElement = new FakeNode('div')
const host = parentElement.appendChild(new FakeNode('div'))
host.className = 'emg'
globalThis.__mount({
  data: input.data, parentElement, setStateValue() {}, setTriggerValue() {},
})
const toggleOf = (label) => host.querySelectorAll('button').find(
  (node) => node.getAttribute('aria-haspopup') === 'dialog' && node.textContent.startsWith(label))
const panelOf = (toggle) => toggle.parentNode.children[1]
const focusLabel = () => {
  const active = document.activeElement
  return active ? active.getAttribute('aria-label') || active.textContent.trim() : null
}
const wait = () => new Promise((resolve) => setTimeout(resolve, 5))
const open = (label) => {
  const toggle = toggleOf(label)
  toggle.focus()
  // 앞 단계에서 열린 채 남았으면(Esc 가 닫지 못함) 한 번 눌러 닫고 다시 연다.
  if (!panelOf(toggle).hidden) toggle.click()
  toggle.click()
  return toggle
}
const results = {}
;(async () => {
  // 공정 — 열고 잠시 뒤 Esc(비교 기준).
  let toggle = open('공정별')
  await wait()
  results.process = { focus: focusLabel(), open: !panelOf(toggle).hidden }
  fire(document.activeElement, 'keydown', { key: 'Escape' })
  results.process.closed = panelOf(toggle).hidden
  results.process.back = document.activeElement === toggle
  // 조건 — 열자마자 Esc.
  toggle = open('조건별')
  results.conditions = { focus: focusLabel(), open: !panelOf(toggle).hidden }
  fire(document.activeElement, 'keydown', { key: 'Escape' })
  results.conditions.closed = panelOf(toggle).hidden
  results.conditions.back = document.activeElement === toggle
  // 조건 — 값을 고르면 패널을 다시 지어도 고른 칸에 초점이 남는다.
  toggle = open('조건별')
  const value = panelOf(toggle).querySelector('[data-fk="cond-val-0"]')
  value.focus()
  value.value = '0'
  fire(value, 'change')
  results.repaint = { focus: focusLabel(), open: !panelOf(toggle).hidden }
  // 열린 채 단추로 돌아와(Shift+Tab) Esc — 닫고 Esc 는 문서로 올리지 않는다.
  toggle.focus()
  const onToggle = fire(toggle, 'keydown', { key: 'Escape' })
  results.toggle = { closed: panelOf(toggle).hidden, stopped: onToggle.stopped }
  // 닫힌 단추의 Esc 는 막지 않는다.
  results.closedToggle = { stopped: fire(toggle, 'keydown', { key: 'Escape' }).stopped }
  process.stdout.write(JSON.stringify(results))
})()
"""


def _loader_payload() -> dict[str, Any]:
    """불러오기 마운트 data 의 최소 꼴 — 설비 둘, 조건 칸 둘(공정소분류·동)."""
    return {
        "mode": "loader",
        "base": "b1",
        "names": ["DEMO-01", "DEMO-02"],
        "ids": {},
        "processes": [["DEMO-P1", 1], ["DEMO-P2", 1]],
        "conditions": {
            "columns": ["공정소분류", "동"],
            "values": [["DEMO-P1", "DEMO-P2"], ["D1", "D2"]],
            "codes": [_python_codes([0, 1], 1), _python_codes([0, 1], 1)],
            "widths": [1, 1],
        },
        "loaded": [],
        "alertIds": [],
        "total": 2,
        "limit": 1000,
        "missing": [],
        "firstData": False,
        "newEnabled": False,
        "newRowsLocked": False,
    }


_LOADER_INFO_RUNNER = (
    _FAKE_DOM_RUNNER.split("const toggleOf")[0]
    + "const info = host.querySelector('.emg-info').textContent\n"
    + "process.stdout.write(JSON.stringify({ text: info }))\n"
)


def test_the_loader_counts_loaded_units_like_the_total() -> None:
    """정보 줄 「불러온 호기 n대 / 전체 N대」 의 n 은 `loadedCount`(살아 있는 호기)다 — 지울 목록에
    든 호기 줄이 `loaded` 에 남아도 전체 N 을 넘지 않는다(E2E 「21대 / 전체 20대」)."""
    assert JS.count(_MOUNT_HEAD) == 1
    source = JS.replace(_MOUNT_HEAD, "globalThis.__mount = function (component) {")
    data = {**_loader_payload(), "loaded": ["s:DEMO-01", "s:DEMO-02", "s:GONE"], "loadedCount": 2}

    text = str(_node({"data": data}, _LOADER_INFO_RUNNER, source=source)["text"])

    assert text.startswith("불러온 호기 2대 / 전체 2대"), text


def test_both_loader_popovers_close_on_escape_right_after_opening() -> None:
    """「조건별 ▾」 를 열자마자 누른 Esc 로도 닫힌다 — 「공정별 ▾」 처럼 열면
    초점이 패널 안 첫 칸으로 가고(Esc 는 패널이 받는다), 열린 채 여는 단추로 돌아와도 Esc 로 닫는다.
    닫히면 초점은 여는 단추로 돌아온다. 값을 골라 패널을 다시 지어도 고른 칸의 초점은 그대로다."""
    assert JS.count(_MOUNT_HEAD) == 1
    source = JS.replace(_MOUNT_HEAD, "globalThis.__mount = function (component) {")
    result = _node({"data": _loader_payload()}, _FAKE_DOM_RUNNER, source=source)

    assert result["process"] == {
        "focus": "공정 이름 찾기",
        "open": True,
        "closed": True,
        "back": True,
    }
    assert result["conditions"] == {
        "focus": "조건 칸 1",
        "open": True,
        "closed": True,
        "back": True,
    }
    assert result["repaint"] == {"focus": "조건 값 1", "open": True}
    assert result["toggle"] == {"closed": True, "stopped": True}
    assert result["closedToggle"] == {"stopped": False}


# 가짜 DOM(위 러너의 앞부분 — FakeNode·fire·document)만 떼어 다른 단계를 붙인다.
_FAKE_DOM = _FAKE_DOM_RUNNER[: _FAKE_DOM_RUNNER.index("const input = JSON.parse")]
_MOUNT_LOADER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const parentElement = new FakeNode('div')
const host = parentElement.appendChild(new FakeNode('div'))
host.className = 'emg'
const mount = (data) => globalThis.__mount({
  data, parentElement, setStateValue() {}, setTriggerValue() {},
})
const buttonOf = (label) => host.querySelectorAll('button').find(
  (node) => node.textContent.startsWith(label))
const results = {}
"""


def _fake_dom_source() -> str:
    assert JS.count(_MOUNT_HEAD) == 1
    return JS.replace(_MOUNT_HEAD, "globalThis.__mount = function (component) {")


def test_the_loader_line_picks_its_shape_from_the_left_column_width() -> None:
    """메뉴 자리를 늘 비워 두면 왼쪽 칸이 좁을 때 입력 칸이 4 ~ 58px 로 사라지고 「불러오기」 가
    메뉴 밑에 깔렸다(2026-11-07 — 오른쪽 칸을 넓힌 뒤 창을 줄이면). 찾기 칸 한 줄 + 메뉴 자리가
    못 들면 `stack`(메뉴가 제 줄), 찾기 칸 혼자도 못 들면 `tight`(「불러오기」 가 아래로)다. 폭이
    바뀌어도 파이썬을 부르지 않고(UI-PRF-04), 숨은 탭(폭 0)은 앞 꼴을 두며, 내릴 때 관찰을 푼다."""
    runner = (
        _FAKE_DOM
        + """
const observers = []
globalThis.ResizeObserver = class {
  constructor(callback) {
    this.callback = callback
    this.disconnected = false
    observers.push(this)
  }
  observe(node) {
    this.target = node
  }
  disconnect() {
    this.disconnected = true
  }
}
let reserve = '109px'
globalThis.window = { getComputedStyle: () => ({ getPropertyValue: () => reserve }) }
"""
        + _MOUNT_LOADER
        + """
const sent = []
const data = input.data
const run = () => globalThis.__mount({
  data, parentElement,
  setStateValue: (...a) => sent.push(a),
  setTriggerValue: (...a) => sent.push(a),
})
const seen = {}
host.clientWidth = 862
const cleanup = run()
seen.first = [host.dataset.lb, observers.length, observers[0].target === host]
const resize = (width) => {
  host.clientWidth = width
  observers[0].callback([])
  return host.dataset.lb
}
seen.widths = [862, 409, 408, 300, 299, 224].map(resize)
reserve = '221px'
seen.folded = [resize(521), resize(520)]
reserve = '109px'
resize(862)
seen.hidden = [resize(0), host.dataset.lb]
resize(408)
run()
seen.again = [observers.length, host.dataset.lb]
seen.sent = sent.length
seen.picks = host.querySelector('.emg-lb-picks').querySelectorAll('button')
  .map((node) => node.textContent.trim()).filter((text) => !text.startsWith('DEMO'))
cleanup()
seen.gone = observers[0].disconnected
process.stdout.write(JSON.stringify(seen))
"""
    )
    result = _node({"data": _loader_payload()}, runner, source=_fake_dom_source())

    assert result["first"] == ["", 1, True]
    assert result["widths"] == ["", "", "stack", "stack", "tight", "tight"]
    assert result["folded"] == ["", "stack"]
    assert result["hidden"] == ["", ""]
    assert result["again"] == [1, "stack"]
    assert result["sent"] == 0
    assert result["picks"][:2] == ["공정별", "조건별"]
    assert result["picks"][-1].startswith("일정 확인")
    assert result["gone"] is True

    # 꼴은 그림자 안 서식만 받는다 — 메뉴는 같은 자리에 머문다.
    assert re.search(
        r'\.emg\[data-lb="stack"\] \.emg-lb,\n\.emg\[data-lb="tight"\] \.emg-lb \{\n'
        r"  padding-top: var\(--emd-tools-drop, 0px\);\n  padding-right: 0;",
        CSS,
    )
    tight = re.search(r'\.emg\[data-lb="tight"\] \.emg-search \{(?P<body>[^}]*)\}', CSS)
    assert tight and "flex-wrap: wrap" in tight.group("body")
    assert "height: auto" in tight.group("body")
    assert re.search(r"\.emg-search-wrap \{[^}]*flex: 1 1 220px;", CSS)


def test_the_guide_calls_the_loader_buttons_by_their_screen_names() -> None:
    """안 A 로 이름이 바뀐 뒤 줄바꿈에 걸려 옛 이름이 남았다 — 줄을 이어 붙여 본다. 「엑셀·CSV로
    한꺼번에」 는 팝업 제목 · 첫 화면 단추 이름으로만 남는다."""
    guide = (
        Path(__file__).resolve().parents[1]
        / "src/capa_simulation/guides/available_equipment_status.md"
    ).read_text(encoding="utf-8")
    joined = re.sub(r"\s*\n\s*", " ", guide)
    assert "조건으로 불러오기" not in joined
    assert "공정으로 불러오기" not in joined
    assert "더 많으면 메뉴 **엑셀·CSV** 의 **엑셀·CSV로 한꺼번에** 를 씁니다" in joined
    assert "새 호기 칸 머리·**조건별** 단추의 하는 법" in joined
    left = [m.start() for m in re.finditer(r"엑셀·CSV로 한꺼번에", joined)]
    assert all(joined[at + len("엑셀·CSV로 한꺼번에") :].startswith("**") for at in left)
    assert "**엑셀·CSV로 한꺼번에**(팝업 — 불러오기 줄 끝 메뉴 **엑셀·CSV** 안" in joined


def test_a_loader_popover_closes_when_the_keyboard_leaves_it() -> None:
    """「조건별 ▾」 를 연 채 Tab 으로 패널 밖(「일정 확인」 단추)에 가면 패널이
    열린 채 남아 초점 받은 오른쪽 호기 상세 칸을 덮었고, 그 칸의 Esc 로도 닫히지 않았다(2026-10-26
    E2E). 초점이 패널·여는 단추 밖으로 나가면 닫는다 — 패널 안 칸끼리 옮김과 다시 지으며 지운
    칸(받을 칸 없음)은 닫지 않는다."""
    runner = (
        _FAKE_DOM
        + _MOUNT_LOADER
        + """
mount(input.data)
const toggle = buttonOf('조건별')
const panel = toggle.parentNode.children[1]
toggle.focus()
toggle.click()
const inside = document.activeElement
const other = panel.querySelectorAll('select, input, button').find((node) => node !== inside)
fire(inside, 'focusout', { relatedTarget: other })
results.withinPanel = !panel.hidden
fire(inside, 'focusout', { relatedTarget: null })
results.repaint = !panel.hidden
fire(inside, 'focusout', { relatedTarget: toggle })
results.backToToggle = !panel.hidden
const outside = buttonOf('일정 확인')
fire(inside, 'focusout', { relatedTarget: outside })
results.left = { open: !panel.hidden, expanded: toggle.getAttribute('aria-expanded') }
process.stdout.write(JSON.stringify(results))
"""
    )
    result = _node({"data": _loader_payload()}, runner, source=_fake_dom_source())

    assert result == {
        "withinPanel": True,
        "repaint": True,
        "backToToggle": True,
        "left": {"open": False, "expanded": "false"},
    }


def test_a_press_on_the_text_or_margin_of_a_loader_popover_keeps_it_open() -> None:
    """팝오버 안 글 줄·여백을 누르면 초점이 초점 받는 가장 가까운 조상(본문 stMain)으로 가
    relatedTarget 이 감싸개 밖이 되고, 위의 「나감 닫기」 가 패널을 닫았다(2026-10-26 E2E r5 회귀 —
    f03490a 에서는 열린 채였다). 패널 안 누름에서 온 나감은 닫지 않는다(공정·조건 두 팝오버).
    누름이 지나간 뒤의 Tab 나감과 패널 밖 누름은 그대로 닫는다."""
    runner = (
        _FAKE_DOM
        + _MOUNT_LOADER
        + """
const main = new FakeNode('section')
main.appendChild(parentElement)
const tick = () => new Promise((resolve) => setTimeout(resolve, 5))
const openPanel = (label) => {
  const toggle = buttonOf(label)
  toggle.focus()
  toggle.click()
  return { toggle, panel: toggle.parentNode.children[1] }
}
const leaveTo = (target) => fire(document.activeElement, 'focusout', { relatedTarget: target })
;(async () => {
  mount(input.data)
  const outside = buttonOf('일정 확인')
  const spots = [['조건별', '.emg-cond'], ['공정별', '.emg-pop-list']]
  for (const [label, spot] of spots) {
    let { toggle, panel } = openPanel(label)
    const row = {}
    fire(panel.querySelector(spot), 'mousedown')
    leaveTo(main)
    row.text = !panel.hidden
    fire(panel, 'mousedown')
    leaveTo(main)
    row.margin = !panel.hidden
    await tick()
    leaveTo(outside)
    row.tabOut = { open: !panel.hidden, expanded: toggle.getAttribute('aria-expanded') }
    ;({ toggle, panel } = openPanel(label))
    fire(outside, 'mousedown')
    leaveTo(main)
    row.pressOutside = !panel.hidden
    await tick()
    results[label] = row
  }
  process.stdout.write(JSON.stringify(results))
})()
"""
    )
    result = _node({"data": _loader_payload()}, runner, source=_fake_dom_source())

    expected = {
        "text": True,
        "margin": True,
        "tabOut": {"open": False, "expanded": "false"},
        "pressOutside": False,
    }
    assert result == {"조건별": expected, "공정별": expected}


def test_escape_closes_a_loader_popover_after_a_press_on_its_text_or_margin() -> None:
    """팝오버 안 안내 글·여백을 누르면 패널은 열린 채 남지만(위 시험) 초점이 본문 stMain 으로
    빠져, Esc 가 패널의 keydown 에 닿지 않고 두 번 눌러도 열린 채였다(2026-10-27 E2E — 여는
    단추로만 닫혔다). 패널이 초점을 받아(`tabIndex -1`) 누름 뒤 초점이 패널에 머물고 Esc 가 닫는다 —
    초점은 여는 단추로 돌아온다. 가짜 DOM 의 누름은 브라우저처럼 초점 받는 가장 가까운 조상(없으면
    stMain)에 초점을 준다."""
    runner = (
        _FAKE_DOM
        + _MOUNT_LOADER
        + """
const main = new FakeNode('section')
main.appendChild(parentElement)
const tags = ['BUTTON', 'INPUT', 'SELECT', 'TEXTAREA']
const focusable = (node) => tags.includes(node.tagName) || typeof node.tabIndex === 'number'
const press = (node) => {
  fire(node, 'mousedown')
  let at = node
  while (at && !focusable(at)) at = at.parentNode
  const target = at || main
  const before = document.activeElement
  if (before && before !== target) fire(before, 'focusout', { relatedTarget: target })
  target.focus()
}
const tick = () => new Promise((resolve) => setTimeout(resolve, 5))
;(async () => {
  mount(input.data)
  const spots = [['조건별', '.emg-cond'], ['공정별', '.emg-pop-list']]
  for (const [label, spot] of spots) {
    const toggle = buttonOf(label)
    const panel = toggle.parentNode.children[1]
    const row = {}
    const targets = [['text', () => panel.querySelector(spot)], ['margin', () => panel]]
    for (const [name, target] of targets) {
      toggle.focus()
      toggle.click()
      await tick()
      press(target())
      await tick()
      const open = !panel.hidden
      fire(document.activeElement, 'keydown', { key: 'Escape' })
      row[name] = { open, closed: panel.hidden, back: document.activeElement === toggle }
    }
    results[label] = row
  }
  process.stdout.write(JSON.stringify(results))
})()
"""
    )
    result = _node({"data": _loader_payload()}, runner, source=_fake_dom_source())

    expected = {"open": True, "closed": True, "back": True}
    row = {"text": expected, "margin": expected}
    assert result == {"조건별": row, "공정별": row}
    assert re.search(r"\.emg-pop:focus\s*\{\s*outline:\s*none", CSS)


def test_closing_the_import_dialog_returns_focus_to_where_it_was_opened() -> None:
    """첫 화면 단추나 메뉴 「엑셀·CSV」 로 연 팝업을 Esc·닫기로 닫으면 초점이 BODY 로 빠지고 다음
    Tab 이 사이드바 머리로 갔다(2026-10-26 E2E — Streamlit 이 그림자 DOM 안 여는 단추로도, 팝업을
    열며 닫힌 메뉴 안으로도 돌려주지 못한다). 팝업이 닫힌 수(`dialogClosed`)가 바뀐 회차에 초점이
    아무 데도 없으면 연 자리로 돌린다 — 첫 화면 단추(넣어서 사라졌으면 메뉴 단추), 메뉴로 열었으면
    (`dialogFromMenu`) 메뉴 단추다. 다른 칸에 초점이 있거나 다른 길로 연 팝업이면 그대로 둔다."""
    runner = (
        _FAKE_DOM
        + _MOUNT_LOADER
        + """
const menu = new FakeNode('button')
menu.textContent = 'menu'
document.querySelector = (selector) => (selector === '.st-key-tools button' ? menu : null)
const first = { firstData: true }
const at = (closed, extra) => Object.assign(
  {}, input.data, { menuKey: 'tools', dialogClosed: closed }, extra)
const label = () => (document.activeElement ? document.activeElement.textContent : null)
const pressed = (extra) => {
  document.activeElement = null
  return extra
}
const FIRST = '엑셀·CSV로 한꺼번에'
mount(at(0, first))
buttonOf(FIRST).focus()
buttonOf(FIRST).click()
mount(at(1, pressed(first)))
results.firstScreen = label()
results.marked = buttonOf(FIRST).dataset.fk
buttonOf(FIRST).click()
mount(at(2, pressed({ loaded: ['s:DEMO-01'] })))
results.firstGone = label()
mount(at(3, pressed({ loaded: ['s:DEMO-01'], dialogFromMenu: true })))
results.fromMenu = label()
mount(at(3, pressed({ loaded: ['s:DEMO-01'], dialogFromMenu: true })))
results.sameCount = label()
mount(at(4, pressed({ loaded: ['s:DEMO-01'] })))
results.notOpenedHere = label()
const elsewhere = new FakeNode('input')
elsewhere.focus()
mount(at(5, { loaded: ['s:DEMO-01'], dialogFromMenu: true }))
results.busy = document.activeElement === elsewhere
process.stdout.write(JSON.stringify(results))
"""
    )
    result = _node({"data": _loader_payload()}, runner, source=_fake_dom_source())

    assert result == {
        "firstScreen": "엑셀·CSV로 한꺼번에",
        "marked": "import-first",
        "firstGone": "menu",
        "fromMenu": "menu",
        "sameCount": None,
        "notOpenedHere": None,
        "busy": True,
    }


def test_the_loader_line_holds_short_names_and_only_the_first_screen_keeps_its_buttons() -> None:
    """표 위 작업 줄은 한 줄이다(2026-11-07 사용자 답 안 A) — 찾기 칸 · 「공정별」 · 「조건별」 ·
    「일정 확인 n대」 뒤에 메뉴 「엑셀·CSV」(표 컴포넌트 밖)가 선다. 줄인 말의 원래 뜻은 풍선 · 패널
    접근성 이름에 남는다. 「+ 새 호기」(오른쪽 칸 고르기와 같은 일)와 팝업 단추는 저장된 데이터가
    없는 첫 화면에만 남는다."""
    runner = (
        _FAKE_DOM
        + _MOUNT_LOADER
        + """
const labels = (root) => root.querySelectorAll('button').map((node) => node.textContent.trim())
const line = () => labels(host.querySelector('.emg-lb')).filter(
  (text) => !text.startsWith('DEMO') && !text.startsWith('맞는'))
const on = { newEnabled: true, alertIds: ['s:DEMO-01'] }
mount(Object.assign({}, input.data, on))
results.line = line()
results.tips = ['공정별', '조건별', '일정 확인'].map((name) => buttonOf(name).title)
results.panels = host.querySelectorAll('.emg-pop').map((node) => node.getAttribute('aria-label'))
results.empty = labels(host.querySelector('.emg-empty'))
results.emptyTip = host.querySelector('.emg-empty').title
mount(Object.assign({}, input.data, on, { firstData: true }))
results.firstLine = line()
results.first = labels(host.querySelector('.emg-empty'))
process.stdout.write(JSON.stringify(results))
"""
    )
    result = _node({"data": _loader_payload()}, runner, source=_fake_dom_source())

    line = ["불러오기", "공정별", "조건별", "일정 확인 1대"]
    assert result["line"] == line
    assert result["firstLine"] == line
    assert result["tips"][0] == "공정으로 불러오기"
    assert result["tips"][1].startswith("조건으로 불러오기")
    assert result["tips"][2].startswith("일정 확인 필요")
    assert result["panels"] == ["맞는 설비명", "공정으로 불러오기", "조건으로 불러오기"]
    assert result["empty"] == ["일정 확인 1대 불러오기", "전체 2대 불러오기"]
    assert "「공정별」" in result["emptyTip"]
    assert result["first"] == ["엑셀·CSV로 한꺼번에", "+ 새 호기"]


def test_the_changes_panel_does_not_say_nothing_was_fixed_when_cells_need_fixing() -> None:
    """「저장 전 변경」 칸에 못 읽은 칸 초안 같은 고칠 것만 있으면 위의 「저장하기 전에 고칠 것」
    과 어긋나지 않게 「고친 값은 없고 고칠 칸이 있습니다」 라고 한다(E2E — 「1 오류 · 저장하기 전에
    고칠 것」 바로 아래 「아직 고친 것이 없습니다」). 고칠 것도 없으면 지금 글 그대로다."""
    runner = (
        _FAKE_DOM
        + _MOUNT_LOADER
        + """
const empty = () => host.querySelector('.emg-side-empty').textContent
const changes = (errors) => ({
  mode: 'side', panel: 'changes', base: 'b1', counts: { errors: errors.length },
  errors, units: [], others: 0,
})
mount(changes([['s:DEMO-01', 'DEMO-01', '반입일정', '반입일정은 날짜 형식이어야 합니다']]))
results.withErrors = empty()
mount(changes([]))
results.clean = empty()
process.stdout.write(JSON.stringify(results))
"""
    )
    result = _node({}, runner, source=_fake_dom_source())

    assert result == {
        "withErrors": "고친 값은 없고 고칠 칸이 있습니다.",
        "clean": "아직 고친 것이 없습니다.",
    }


def test_the_downtime_goto_brings_the_two_columns_head_back_into_view() -> None:
    """긴 호기 상세 맨 아래의 「비가동 일정 표에서 고치기」 를 누르면 화면이 내려간 채라 왼쪽에 선
    비가동 일정 표가 위로 나가 빈 칸처럼 보였다(2026-10-25 E2E #67). 누를 때 두 칸 줄(Streamlit
    가로 줄)의 머리가 가린 높이 위로 나가 있으면 머리 띠·화면 탭 줄 아래(+8px)로 올린다 — 보이면
    그대로 둔다. 화면 탭 줄이 없으면 머리 띠 높이(72px)를 쓴다."""
    runner = (
        _FAKE_DOM
        + """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const parentElement = new FakeNode('div')
const host = parentElement.appendChild(new FakeNode('div'))
host.className = 'emg'
const row = {
  top: 0, style: {}, scrolled: null,
  getBoundingClientRect() { return { top: this.top } },
  scrollIntoView(options) { this.scrolled = options },
}
host.closest = (selector) => (selector === '[data-testid="stHorizontalBlock"]' ? row : null)
const triggers = []
let strip = null
document.querySelector = (selector) => (selector === input.strip ? strip : null)
globalThis.__mount({
  data: input.data, parentElement, setStateValue() {},
  setTriggerValue(name, value) { triggers.push([name, value]) },
})
const link = host.querySelectorAll('button').find(
  (node) => node.textContent === '비가동 일정 표에서 고치기')
const results = {}
row.top = 300
link.click()
results.visible = { scrolled: row.scrolled, trigger: triggers[0] }
row.top = -900
link.click()
results.hidden = {
  scrolled: row.scrolled, margin: row.style.scrollMarginTop, sent: triggers.length,
}
strip = { getBoundingClientRect() { return { bottom: 94 } } }
row.scrolled = null
row.top = 90
link.click()
results.underStrip = { scrolled: row.scrolled, margin: row.style.scrollMarginTop }
process.stdout.write(JSON.stringify(results))
"""
    )
    data = {
        "mode": "side",
        "panel": "detail",
        "base": "b1",
        "columns": [{"name": "설비명", "kind": "name"}],
        "groups": [],
        "unit": {"id": "s:DEMO-01", "values": ["DEMO-01"], "downtime": [], "deletable": True},
    }

    result = _node({"data": data, "strip": PAGE_TABS_SELECTOR}, runner, source=_fake_dom_source())

    assert result == {
        "visible": {
            "scrolled": None,
            "trigger": ["goto", {"table": "비가동 일정", "unit": "DEMO-01"}],
        },
        "hidden": {"scrolled": {"block": "start"}, "margin": "80px", "sent": 2},
        "underStrip": {"scrolled": {"block": "start"}, "margin": "102px"},
    }
    assert f"const PAGE_TABS_STRIP = '{PAGE_TABS_SELECTOR}'" in JS


def test_a_loader_popover_closes_after_its_load_and_on_another_loader_button() -> None:
    """「조건별」 로 불러온 뒤나 불러오기 줄의 다른 단추를 누른 뒤에도 팝오버가 열린 채
    오른쪽 칸을 덮었다(2026-10-25 E2E #29). 패널 안에서 불러오면 바로 닫고 초점은 여는 단추로,
    불러오기 줄의 다른 단추(다른 팝오버의 여는 단추도)를 누르면 그 단추를 지우지 않고 패널만
    닫는다. 패널 안 누름은 닫지 않는다."""
    runner = (
        _FAKE_DOM
        + """
const docListeners = {}
document.addEventListener = (type, handler) => {
  ;(docListeners[type] = docListeners[type] || []).push(handler)
}
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const parentElement = new FakeNode('div')
const host = parentElement.appendChild(new FakeNode('div'))
host.className = 'emg'
const triggers = []
globalThis.__mount({
  data: input.data, parentElement, setStateValue() {},
  setTriggerValue(name, value) { triggers.push([name, value.kind]) },
})
const buttonOf = (label) => host.querySelectorAll('button').find(
  (node) => node.textContent.startsWith(label))
const press = (node) => {
  const path = []
  for (let at = node; at; at = at.parentNode) path.push(at)
  for (const handler of docListeners.mousedown || []) {
    handler({ target: node, composedPath: () => path })
  }
}
const isOpen = (toggle) => !toggle.parentNode.children[1].hidden
const results = {}
// 조건 팝오버 — 패널 안 누름은 닫지 않고, 다른 단추 누름은 그 단추를 남긴 채 닫는다.
let toggle = buttonOf('조건별')
toggle.click()
const inside = toggle.parentNode.children[1].querySelector('[data-fk="cond-val-0"]')
press(inside)
results.insidePress = isOpen(toggle)
const alerts = buttonOf('일정 확인')
press(alerts)
results.otherButton = {
  open: isOpen(toggle),
  expanded: toggle.getAttribute('aria-expanded'),
  kept: host.contains(alerts),
}
// 공정 팝오버를 연 채 조건 여는 단추를 누르면 공정 쪽이 닫힌다.
const byProcess = buttonOf('공정별')
byProcess.click()
press(toggle)
toggle.click()
results.otherToggle = { process: isOpen(byProcess), conditions: isOpen(toggle) }
// 조건별 — 값을 고르고 「맞는 n대 불러오기」 를 누르면 바로 닫고 여는 단추로 초점.
const value = toggle.parentNode.children[1].querySelector('[data-fk="cond-val-0"]')
value.value = '0'
fire(value, 'change')
buttonOf('맞는 ').click()
results.conditionsLoad = {
  open: isOpen(toggle),
  focus: document.activeElement === toggle,
  trigger: triggers[triggers.length - 1],
}
// 공정별 — 공정 하나를 누르면 바로 닫는다.
byProcess.click()
buttonOf('DEMO-P2').click()
results.processLoad = { open: isOpen(byProcess), trigger: triggers[triggers.length - 1] }
process.stdout.write(JSON.stringify(results))
"""
    )

    result = _node({"data": _loader_payload()}, runner, source=_fake_dom_source())

    assert result == {
        "insidePress": True,
        "otherButton": {"open": False, "expanded": "false", "kept": True},
        "otherToggle": {"process": False, "conditions": True},
        "conditionsLoad": {"open": False, "focus": True, "trigger": ["load", "conditions"]},
        "processLoad": {"open": False, "trigger": ["load", "process"]},
    }


def _brightened(color: str, factor: float) -> str:
    """CSS `filter: brightness(factor)` 를 입힌 `#RRGGBB` — 채널마다 곱하고 255 에서 자른다."""
    channels = (int(color[start : start + 2], 16) for start in (1, 3, 5))
    return "#" + "".join(f"{min(round(channel * factor), 255):02X}" for channel in channels)


def _button_hover_rules() -> list[tuple[str, str]]:
    """`.emg-btn` 호버 선택자마다 (선택자, 규칙 몸) — 묶인 선택자는 하나씩 가른다."""
    return [
        (selector.strip(), match["body"])
        for match in re.finditer(r"(?P<selectors>[^{}]*)\{(?P<body>[^{}]*)\}", CSS)
        for selector in match["selectors"].split(",")
        if ".emg-btn" in selector and ":hover" in selector
    ]


def test_a_filled_button_keeps_its_fill_on_hover_and_stays_readable() -> None:
    """켜진 「호기 추가」 에 마우스를 올리면 글이 거의 안 보였다 — `.emg-btn:hover:not(:disabled)`
    (0,3,0)가 `.emg-btn.is-primary`(0,2,0)를 이겨 옅은 바탕에 칠한 단추의 글자색만 남았다(2026-11-06
    사용자 답). 옅은 바탕 호버는 칠하지 않은 단추에만 걸고, 칠한 단추는 제 바탕 위에서 밝기만 바꾼다
    (`capa-month-apply` 와 같은 꼴 — 색을 새로 쓰지 않는다)."""
    rules = dict(_button_hover_rules())
    assert ".emg-btn:hover:not(:disabled)" not in rules
    for selector, body in rules.items():
        if "background" in body:
            assert ":not(.is-primary)" in selector, selector

    primary = rules[".emg-btn.is-primary:hover:not(:disabled)"]
    assert "background" not in primary and "color" not in primary
    found = re.search(r"filter:\s*brightness\((?P<factor>[0-9.]+)\)", primary)
    assert found, primary
    factor = float(found["factor"])

    for mode, palette in tokens._PALETTES.items():
        hovered = _brightened(palette["ACCENT"], factor)
        ratio = contrast_ratio(_brightened(palette["ACCENT_TEXT"], factor), hovered)
        assert ratio >= SMALL_TEXT_MINIMUM, f"{mode} 칠한 단추 호버 {ratio:.2f}:1"


def test_an_outlined_button_stays_readable_on_its_hover_fill() -> None:
    """옅은 바탕 호버가 걸리는 단추의 글자(보통·지우기)는 그 바탕에서 읽힌다."""
    for mode, palette in tokens._PALETTES.items():
        for name, ink in (("보통", palette["TEXT"]), ("지우기", palette["GRID_ERROR_LINE"])):
            ratio = contrast_ratio(ink, palette["SURFACE_SUBTLE"])
            assert ratio >= SMALL_TEXT_MINIMUM, f"{mode} {name} 단추 호버 {ratio:.2f}:1"


def test_the_shared_css_fragments_come_first_and_keep_the_cell_state_order() -> None:
    """칸 상태 규칙은 특이도가 같아 차례로 이긴다(잠긴 칸 + 오류 칸의 바탕이 뒤 규칙을 따른다). 표
    공용 조각을 떼어도 그 차례가 그대로이고, 이 표의 파일보다 앞에 선다."""
    order = (
        ".emg-c.is-changed {",
        ".emg-c.is-error {",
        ".emg-c.is-warn .emg-cb {",
        ".emg-c.is-locked {",
        ".emg-c.is-pending .emg-cb {",
        ".emg-c.is-editing {",
        ".emg-ed {",
        "textarea.emg-ed {",
    )
    places = [CSS.index(f"\n{rule}") for rule in order]
    assert places == sorted(places)
    assert CSS.endswith(OWN_CSS)
    assert not any(rule in OWN_CSS for rule in order)


_BURST_RUNNER = """
FakeNode.prototype.select = function () {}
FakeNode.prototype.scrollIntoView = function () {}
Object.defineProperty(FakeNode.prototype, 'innerHTML', {
  set() {
    this.textContent = ''
  },
})
// 브라우저처럼 — 초점 든 칸이 그리기로 사라지면 그 자리에서 대상 없는 focusout 이 난다.
const leaveIfGone = (node) => {
  const active = document.activeElement
  if (active && node.contains(active)) {
    fire(active, 'focusout', { relatedTarget: null })
    document.activeElement = null
  }
}
FakeNode.prototype.replaceWith = function (node) {
  leaveIfGone(this)
  this.parentNode.children[this.parentNode.children.indexOf(this)] = node
  node.parentNode = this.parentNode
  this.parentNode = null
}
const docListeners = {}
document.addEventListener = (type, fn) => {
  ;(docListeners[type] = docListeners[type] || []).push(fn)
}
document.removeEventListener = () => {}
document.querySelector = () => null
document.documentElement = { clientWidth: 1200 }
const parentElement = new FakeNode('div')
const host = parentElement.appendChild(new FakeNode('div'))
host.className = 'emg'
const sent = []
const outgoing = []
const data = {
  mode: 'grid', base: 'b1', view: 'v1', limits: { outboxCells: 10000, pasteCells: 5000 },
  columns: [
    { name: '설비명', kind: 'name', width: 'name' },
    { name: 'Model', kind: 'text', width: 'm' },
    { name: 'Area', kind: 'text', width: 'm' },
  ],
  colSets: [['all', '전체', '', [1, 2]]],
  rows: [
    { id: 'a', values: ['EQ-1', 'x', 'p'] },
    { id: 'b', values: ['EQ-2', 'y', 'q'] },
    { id: 'c', values: ['EQ-3', 'z', 'r'] },
  ],
}
const component = {
  parentElement, setTriggerValue() {},
  setStateValue: (name, value) => {
    sent.push(value.ops.length)
    outgoing.push(value.ops.map((op) => [op.seq, op.base, op.text]))
  },
}
const cleanup = globalThis.__mount({ data, ...component })
const S = host.__emg
const body = S.body
const clear = Object.getOwnPropertyDescriptor(FakeNode.prototype, 'textContent')
Object.defineProperty(body, 'textContent', {
  get: () => clear.get.call(body),
  set(value) {
    leaveIfGone(body)
    clear.set.call(body, value)
  },
})
const typed = (id, col, text, leave) => {
  if (!S.edit) startEdit(S, id, col)
  const input = body.querySelector('.emg-ed')
  input.value = text
  fire(input, 'input')
  leave(input)
}
const press = (name) => (input) => fire(input, 'keydown', { key: name })
const R = {}
;(async () => {
  typed('a', 1, 'T0', press('Tab'))
  typed('a', 2, 'T1', press('ArrowDown'))
  typed('b', 2, 'T2', press('ArrowDown'))
  typed('c', 2, 'T3', press('Enter'))
  R.moved = { sent: sent.length, box: S.box.ops.length }
  await tick(360)
  R.movedQuiet = { sent: sent.slice() }
  for (const text of ['E0', 'E1', 'E2']) typed('a', 1, text, press('Enter'))
  R.enter = { sent: sent.length }
  await tick(360)
  R.enterQuiet = { sent: sent.length }
  // 진짜로 표 밖을 누르면 — 그리기 밖의 focusout 이다 — 기다리지 않고 보낸다.
  typed('b', 1, 'OUT', (input) => {
    document.activeElement = null
    fire(input, 'focusout', { relatedTarget: null })
  })
  R.outside = { sent: sent.length, edit: S.edit }
  // 창이 숨어도 기다리지 않고 보낸다.
  typed('c', 1, 'VIS', press('Enter'))
  const queued = sent.length
  for (const run of docListeners.visibilitychange) run()
  R.hidden = { queued, sent: sent.length }
  cleanup()
  process.stdout.write(JSON.stringify(R))
})()
"""


def test_a_burst_of_cell_edits_goes_out_once_after_the_quiet_time() -> None:
    """칸을 잇달아 고치면 보냄은 300ms 묶음 한 번이다(UI-PRF-02 「연속 N회 → 보냄 1회」). 확정 ·
    다음 칸 열기가 표 본문을 다시 그리면 초점 든 칸이 사라져 대상 없는 focusout 이 나고, 그것을 표
    밖으로 나간 것으로 읽어 칸마다 회차가 돌았다(u4-02 — 6칸 6회차, 샘플 관측). 진짜로 표 밖을 누른
    때와 창이 숨을 때는 지금처럼 곧바로 보낸다."""
    result = _node({}, _BURST_RUNNER, source=FAKE_DOM + _fake_dom_source())
    assert result["moved"] == {"sent": 0, "box": 4}
    assert result["movedQuiet"] == {"sent": [4]}, "Tab · 아래 · Enter 4칸 → 보냄 1회"
    assert result["enter"] == {"sent": 1}
    assert result["enterQuiet"] == {"sent": 2}, "Enter 연속 3칸 → 보냄 1회"
    assert result["outside"] == {"sent": 3, "edit": None}, "표 밖 누름은 곧바로 보낸다"
    assert result["hidden"] == {"queued": 3, "sent": 4}, "창이 숨으면 곧바로 보낸다"


_REBASE_RUNNER = (
    _BURST_RUNNER[: _BURST_RUNNER.index("const R = {}")]
    + """
const R = {}
;(async () => {
  typed('a', 1, 'T0', press('Enter'))
  await tick(360)
  R.sentOne = { sent: outgoing.length, box: S.box.ops.length }
  // 저장이 도는 사이 친 칸 — 묶음이 든 op 하나와 연 칸의 글이 남은 채 새 base 가 온다.
  typed('b', 1, 'T1', press('Enter'))
  typed('c', 1, 'OPEN', () => {})
  globalThis.__mount({ data: { ...data, base: 'b2', view: 'v2' }, ...component })
  R.rebased = {
    sent: outgoing.length, box: S.box.ops.length, edit: S.edit, pending: S.pending.size,
  }
  await tick(360)
  R.quiet = outgoing[outgoing.length - 1]
  globalThis.__mount({
    data: { ...data, base: 'b2', view: 'v3', ack: { mount: S.mount, seq: 3 } }, ...component,
  })
  R.acked = { box: S.box.ops.length }
  // 글을 바꾸지 않은 연 칸은 op 가 아니다.
  startEdit(S, 'a', 1)
  globalThis.__mount({ data: { ...data, base: 'b3', view: 'v4' }, ...component })
  R.untouched = { box: S.box.ops.length, edit: S.edit }
  cleanup()
  process.stdout.write(JSON.stringify(R))
})()
"""
)


def test_ops_held_by_the_batch_when_the_base_changes_are_sent_and_counted() -> None:
    """base 가 바뀌어도 보낼 목록에서 빼지 않는다. 묶음이 든 op 와 연 칸의 글이 옛 base 로 나가
    서버가 세어 알리고 ack 가 지운다. 전에는 받은 자리에서 비워 「리비전 저장」 이 도는 사이 친
    칸이 토스트 없이 사라졌다(샘플 관측)."""
    result = _node({}, _REBASE_RUNNER, source=FAKE_DOM + _fake_dom_source())
    assert result["sentOne"] == {"sent": 1, "box": 1}
    assert result["rebased"] == {"sent": 1, "box": 3, "edit": None, "pending": 0}
    assert result["quiet"] == [[1, "b1", "T0"], [2, "b1", "T1"], [3, "b1", "OPEN"]]
    assert result["acked"] == {"box": 0}
    assert result["untouched"] == {"box": 0, "edit": None}


_CARET_RUNNER = (
    _BURST_RUNNER[: _BURST_RUNNER.index("const R = {}")]
    + """
FakeNode.prototype.select = function () {
  this.selection = 'all'
}
FakeNode.prototype.focus = function () {
  document.activeElement = this
  FAKE_ROOT.activeElement = this
}
const editor = () => body.querySelector('.emg-ed')
const R = {}
;(async () => {
  startEdit(S, 'a', 1)
  let input = editor()
  R.opened = input.selection
  // 칸에 「MI」 를 쳐 글자 자리가 끝(2)에 있다 — Tab 으로 다음 칸을 연다.
  input.value = 'MI'
  input.selectionStart = 2
  input.selectionEnd = 2
  fire(input, 'input')
  fire(input, 'keydown', { key: 'Tab' })
  input = editor()
  R.tab = { cell: [S.edit.id, S.edit.col], value: input.value, selection: input.selection }
  input.selectionStart = 1
  input.selectionEnd = 1
  fire(input, 'keydown', { key: 'ArrowDown' })
  input = editor()
  R.down = { cell: [S.edit.id, S.edit.col], value: input.value, selection: input.selection }
  // 같은 칸이 다시 그려지면(굴림 · 회차) 쓰던 글자 자리를 지킨다.
  input.selection = null
  input.selectionStart = 1
  input.selectionEnd = 1
  paintWindow(S)
  R.same = editor().selection
  cleanup()
  process.stdout.write(JSON.stringify(R))
})()
"""
)


def test_tab_or_down_into_the_next_cell_selects_its_old_value_to_be_typed_over() -> None:
    """Tab · ↓ 로 연 다음 칸은 옛 값을 통째로 고른 채 열려 친 글이 옛 값을 덮는다. 나가는 칸의 글자
    자리를 새 칸에 넘겨 「MI」 칸 뒤 Tab 하고 「D1」 을 치면 「MID1」 이 됐다(바탕부터 — X1). 같은
    칸이 다시 그려질 때는 쓰던 자리를 지킨다."""
    result = _node({}, _CARET_RUNNER, source=FAKE_DOM + _fake_dom_source())
    assert result["opened"] == "all"
    assert result["tab"] == {"cell": ["a", 2], "value": "p", "selection": "all"}
    assert result["down"] == {"cell": ["b", 2], "value": "q", "selection": "all"}
    assert result["same"] == [1, 1]


_SCROLL_RUNNER = (
    _BURST_RUNNER[: _BURST_RUNNER.index("const parentElement = new FakeNode('div')")]
    + r"""
// 그림자 뿌리의 초점은 문서 초점을 그대로 따른다(빠지면 둘 다 빈다).
Object.defineProperty(FAKE_ROOT, 'activeElement', { get: () => document.activeElement, set() {} })
// 표가 쓰는 겹친 선택자 — 「태그.칸[속성]」 한 덩이와 띄어 쓴 자손
// (`[data-id="a"][data-col="1"] button`).
const oneMatch = FakeNode.prototype.matches
const compound = (node, text) => {
  const m = text.match(/^([a-zA-Z]*)((?:\.[\w-]+|\[[^\]]+\])*)$/)
  if (!m || (!m[1] && !m[2])) return oneMatch.call(node, text)
  if (m[1] && node.tagName !== m[1].toUpperCase()) return false
  return (m[2].match(/\.[\w-]+|\[[^\]]+\]/g) || []).every((bit) => oneMatch.call(node, bit))
}
FakeNode.prototype.matches = function (selector) {
  return selector.split(',').some((part) => compound(this, part.trim()))
}
const oneAll = FakeNode.prototype.querySelectorAll
FakeNode.prototype.querySelectorAll = function (selector) {
  const parts = selector.trim().split(/\s+/)
  if (parts.length < 2 || selector.includes(',')) return oneAll.call(this, selector)
  let scope = [this]
  for (const part of parts) {
    const next = []
    for (const node of scope) {
      for (const found of oneAll.call(node, part)) if (!next.includes(found)) next.push(found)
    }
    scope = next
  }
  return scope
}
const focusCalls = []
FakeNode.prototype.focus = function (options) {
  document.activeElement = this
  focusCalls.push(options === undefined ? 'follow' : options)
}
FakeNode.prototype.select = function () {}
FakeNode.prototype.setSelectionRange = function () {}
let pageShift = 0
const rectOf = FakeNode.prototype.getBoundingClientRect
const parentElement = new FakeNode('div')
const host = parentElement.appendChild(new FakeNode('div'))
host.className = 'emg'
// 표 상자 · 페이지가 구르면 칸의 화면 자리도 그만큼 움직인다.
FakeNode.prototype.getBoundingClientRect = function () {
  const r = rectOf.call(this)
  const box = host.__emg && host.__emg.scroller
  const dy = (this.classList.contains('emg-c') && box ? box.scrollTop : 0) + pageShift
  return { ...r, top: r.top - dy, bottom: r.bottom - dy }
}
const rows = []
for (let k = 0; k < 60; k += 1) rows.push({ id: 'r' + k, values: ['EQ-' + k, 'm' + k, 'C1'] })
const data = {
  mode: 'grid', base: 'b1', view: 'v1', limits: { outboxCells: 10000, pasteCells: 5000 },
  columns: [
    { name: '설비명', kind: 'name', width: 'name' },
    { name: 'Model', kind: 'text', width: 'm' },
    { name: '동', kind: 'choice', width: 's', options: ['C1', 'C2', 'C3'], blank: true },
  ],
  colSets: [['all', '전체', '', [1, 2]]],
  rows,
}
const component = { parentElement, setTriggerValue() {}, setStateValue() {} }
const cleanup = globalThis.__mount({ data, ...component })
const S = host.__emg
const body = S.body
const clear = Object.getOwnPropertyDescriptor(FakeNode.prototype, 'textContent')
Object.defineProperty(body, 'textContent', {
  get: () => clear.get.call(body),
  set(value) {
    leaveIfGone(body)
    clear.set.call(body, value)
  },
})
const cellOf = (id, col) => body.querySelector('[data-id="' + id + '"][data-col="' + col + '"]')
const press = (id, col) => cellOf(id, col).querySelector('.emg-cb')
const wheel = async (top) => {
  S.scroller.scrollTop = top
  for (const run of S.scroller.listeners.scroll) run()
  await tick(5)
}
const last = () => focusCalls[focusCalls.length - 1]
const label = () => {
  const active = document.activeElement
  return active ? active.getAttribute('aria-label') : null
}
const R = {}
;(async () => {
  // 칸을 눌러 연 글 칸 — 휠로 다시 그려도 스크롤을 끌지 않는다(preventScroll).
  fire(press('r2', 1), 'click')
  R.clickOpen = { edit: [S.edit.id, S.edit.col], focus: last() }
  await wheel(240)
  R.wheelEditing = { edit: Boolean(S.edit), focus: last(), top: S.scroller.scrollTop }
  // Esc 로 닫은 뒤 초점만 남은 칸도 휠에 끌지 않는다. 화살표는 그 칸을 따라간다.
  fire(body.querySelector('.emg-ed'), 'keydown', { key: 'Escape' })
  R.escape = last()
  await wheel(272)
  R.wheelFocused = last()
  fire(document.activeElement, 'keydown', { key: 'ArrowDown' })
  R.arrow = { focus: last(), cell: [S.focus.id, S.focus.col] }
  // 친 글이 든 칸이 그린 창 밖으로 나가면 그 자리에서 확정하고, 초점은 돌아오면 되돌려 준다.
  await wheel(0)
  startEdit(S, 'r2', 1)
  const input = body.querySelector('.emg-ed')
  input.value = 'Q'
  fire(input, 'input')
  await wheel(34 * 40)
  R.leftWindow = {
    edit: S.edit,
    queued: S.box.ops.map((op) => [op.op, op.id, op.col, op.text]),
    held: S.heldFocus,
    active: document.activeElement,
  }
  await wheel(0)
  R.back = { held: S.heldFocus, focus: label(), call: last() }
  // 고르기 창 — 칸 안 자식이고 화면 자리(fixed)에 놓인다.
  // 늦게 온 scroll(자리 그대로)은 닫지 않는다.
  fire(press('r1', 2), 'click')
  const list = () => body.querySelector('.emg-dd')
  // 가짜 칸은 0 ~ 600px 이라(`getBoundingClientRect`) 창은 칸 아래 끝 599px 에 선다.
  R.choice = {
    open: Boolean(list()),
    inCell: list() ? list().parentNode === cellOf('r1', 2) : null,
    placed: list() ? [list().style.left, list().style.top, list().style.minWidth] : null,
    focus: last(),
    raised: cellOf('r1', 2).classList.contains('is-choosing'),
  }
  await wheel(0)
  R.lateScroll = Boolean(list())
  // 표가 구르면 닫고 초점은 그 칸으로(끌지 않음).
  await wheel(34)
  R.boxScroll = { open: Boolean(list()), edit: S.edit, focus: label(), call: last() }
  // 페이지가 구르면 닫는다(문서 scroll — 그림자 DOM 밖).
  fire(press('r3', 2), 'click')
  R.reopened = Boolean(list())
  pageShift = 20
  for (const run of docListeners.scroll) run()
  R.pageScroll = { open: Boolean(list()), edit: S.edit }
  pageShift = 0
  // 창 크기가 바뀌어도 칸이 움직였으면 닫는다.
  fire(press('r3', 2), 'click')
  pageShift = 12
  window.dispatchEvent(new Event('resize'))
  R.resized = { open: Boolean(list()), edit: S.edit }
  pageShift = 0
  // 키보드(Enter)로 연 창은 칸 단추를 먼저 보이게 하고(기본 focus) 창 단추는 끌지 않는다.
  press('r3', 2).focus()
  focusCalls.length = 0
  fire(press('r3', 2), 'keydown', { key: 'Enter' })
  R.keyOpen = { open: Boolean(list()), calls: focusCalls.slice() }
  // 머리 밑에 걸친 줄을 누르면 그 줄을 통째로 꺼낸 뒤 연다(`startEdit` 의 `ensureVisible`).
  fire(document.activeElement, 'keydown', { key: 'Escape' })
  S.scroller.scrollTop = 34 * 5 + 17
  fire(press('r5', 1), 'click')
  R.reveal = { edit: S.edit ? [S.edit.id, S.edit.col] : null, top: S.scroller.scrollTop }
  cleanup()
  process.stdout.write(JSON.stringify(R))
})()
"""
)


def test_a_redraw_from_the_wheel_or_a_click_does_not_drag_the_scroll_to_the_focused_cell() -> None:
    """칸을 누른 뒤 휠을 굴리면 표가 제자리에서 헛돌았다(2026-11-12 사용자 요청 2 · 표 첫 판부터) —
    스크롤마다 그린 창을 다시 그리며 초점을 되돌리는 focus() 가 스크롤을 초점 칸으로 끌고 갔다.
    키 손짓이 부른 그리기만 그 칸을 따라가고(가로 — 세로는 `ensureVisible`), 휠 · 누르기는
    `preventScroll` 이다. 친 글이 든 칸이 그린 창 밖으로 나가면 그 자리에서 확정하고(칸이
    사라지면 focusout 이 오지 않아 다른 칸 누르기가 친 글을 덮었다), 초점 칸이 돌아오면 초점을
    되돌려 준다. 고르기 창은 칸 안 자식 그대로 화면 자리에 떠, 표 · 페이지가 굴러 칸이 움직이면
    고르지 않은 채 닫는다. 머리 밑에 걸친 줄의 칸을 누르면 그 줄을 꺼낸 뒤 연다."""
    result = _node({}, _SCROLL_RUNNER, source=FAKE_DOM + _fake_dom_source())
    quiet = {"preventScroll": True}
    assert result["clickOpen"] == {"edit": ["r2", 1], "focus": quiet}
    assert result["wheelEditing"] == {"edit": True, "focus": quiet, "top": 240}
    assert result["escape"] == "follow"
    assert result["wheelFocused"] == quiet
    assert result["arrow"] == {"focus": "follow", "cell": ["r3", 1]}
    assert result["leftWindow"] == {
        "edit": None,
        "queued": [["cell", "r2", "Model", "Q"]],
        "held": True,
        "active": None,
    }
    assert result["back"] == {"held": False, "focus": "EQ-2 Model Q", "call": quiet}
    assert result["choice"] == {
        "open": True,
        "inCell": True,
        "placed": ["-1px", "599px", "1002px"],
        "focus": quiet,
        "raised": True,
    }
    assert result["lateScroll"] is True
    assert result["boxScroll"] == {
        "open": False,
        "edit": None,
        "focus": "EQ-1 동 C1",
        "call": quiet,
    }
    assert result["reopened"] is True
    assert result["pageScroll"] == {"open": False, "edit": None}
    assert result["resized"] == {"open": False, "edit": None}
    assert result["keyOpen"] == {"open": True, "calls": ["follow", quiet]}
    assert result["reveal"] == {"edit": ["r5", 1], "top": 170}


_CHOICE_PLACE_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const places = input.cases.map((c) => choicePlace(c.cell, c.size, c.view, 8))
const scrolls = input.scrolls.map((c) => listScroll(...c))
process.stdout.write(JSON.stringify({ places, scrolls }))
"""


def test_the_choice_list_opens_below_the_cell_or_flips_up_and_stays_on_screen() -> None:
    """고르기 창 자리(`choicePlace`) — 칸 바로 아래(아래 테와 1px 겹침), 아래가 모자라고 위가 더
    넓으면 위로, 편 쪽도 모자라면 그 높이만큼 펴고 창 안에서 굴린다. 오른쪽 화면 끝을 넘으면
    왼쪽으로 당긴다. 위로 펼 때 머리 띠 · 탭 줄(view.top) 밑으로 들어가지 않는다. 줄여 편 창 안
    스크롤(`listScroll`)은 고른 값이 보이는 칸에 들면 그대로, 밖이면 가장 적게 옮긴다."""
    view = {"width": 1600, "height": 1000, "top": 120}
    cases = [
        {"cell": {"left": 400, "top": 300, "bottom": 334}, "size": {"width": 90, "height": 270}},
        {"cell": {"left": 400, "top": 850, "bottom": 884}, "size": {"width": 90, "height": 270}},
        {"cell": {"left": 400, "top": 300, "bottom": 334}, "size": {"width": 90, "height": 900}},
        {"cell": {"left": 1550, "top": 300, "bottom": 334}, "size": {"width": 90, "height": 100}},
    ]
    # [지금 스크롤, 값 위, 값 높이, 보이는 높이, 창 안 여백]
    scrolls = [
        [0, 4, 24, 171, 4],
        [0, 186, 24, 171, 4],
        [58, 108, 24, 171, 4],
        [58, 30, 24, 171, 4],
    ]
    result = _node(
        {"cases": [{**case, "view": view} for case in cases], "scrolls": scrolls},
        runner=_CHOICE_PLACE_RUNNER,
    )
    places = result["places"]
    assert places[0] == {"left": 399, "top": 333, "maxHeight": None, "up": False}
    assert places[1] == {"left": 399, "top": 581, "maxHeight": None, "up": True}
    # 아래 659 · 위 181 — 넓은 아래쪽에 659 만큼 펴고 창 안에서 굴린다.
    assert places[2] == {"left": 399, "top": 333, "maxHeight": 659, "up": False}
    assert places[3] == {"left": 1502, "top": 333, "maxHeight": None, "up": False}
    # 첫 값은 0, 아래로 벗어난 값은 그 끝 + 여백까지, 보이는 값은 그대로,
    # 위로 벗어난 값은 그 위 - 여백.
    assert result["scrolls"] == [0, 43, 58, 26]


_LIST_SCROLL_RUNNER = (
    _SCROLL_RUNNER[: _SCROLL_RUNNER.index("const rows = []")]
    + """
// 창 안 자리 — 값 단추는 창 여백 4px 아래에 26px 간격으로 선다. 창은 제 높이(여백 둘 + 단추들)이고,
// maxHeight 를 받으면 테 둘(2px)을 뺀 만큼만 보인다.
Object.defineProperty(FakeNode.prototype, 'offsetTop', {
  get() {
    const up = this.parentNode
    return up && up.classList.contains('emg-dd') ? 4 + up.children.indexOf(this) * 26 : 0
  },
})
const make = document.createElement
document.createElement = (tag) => {
  const node = make(tag)
  Object.defineProperty(node, 'clientHeight', {
    get() {
      if (!this.classList.contains('emg-dd')) return 600
      const full = 8 + this.children.length * 26
      const cap = parseFloat(this.style.maxHeight)
      return cap > 0 ? Math.min(cap - 2, full) : full
    },
    set() {},
  })
  return node
}
const options = []
for (let k = 0; k < 20; k += 1) options.push('O' + k)
const rows = []
for (let k = 0; k < 6; k += 1) {
  rows.push({ id: 'r' + k, values: ['EQ-' + k, 'm' + k, k === 3 ? 'O12' : 'O0'] })
}
const data = {
  mode: 'grid', base: 'b1', view: 'v1', limits: { outboxCells: 10000, pasteCells: 5000 },
  columns: [
    { name: '설비명', kind: 'name', width: 'name' },
    { name: 'Model', kind: 'text', width: 'm' },
    { name: '층', kind: 'choice', width: 's', options, blank: true },
  ],
  colSets: [['all', '전체', '', [1, 2]]],
  rows,
}
const component = { parentElement, setTriggerValue() {}, setStateValue() {} }
const cleanup = globalThis.__mount({ data, ...component })
const S = host.__emg
const body = S.body
const list = () => body.querySelector('.emg-dd')
const press = (id, col) =>
  body.querySelector('[data-id="' + id + '"][data-col="' + col + '"]').querySelector('.emg-cb')
const key = (name, times) => {
  for (let k = 0; k < times; k += 1) fire(document.activeElement, 'keydown', { key: name })
}
// 고른 값이 창 안 보이는 칸에 드나.
const seen = () => {
  const box = list()
  const active = box.querySelector('button.is-active')
  return {
    active: active.textContent,
    focus: document.activeElement === active,
    top: box.scrollTop,
    inside: active.offsetTop >= box.scrollTop
      && active.offsetTop + active.offsetHeight <= box.scrollTop + box.clientHeight,
  }
}
const R = {}
// 가짜 칸은 0 ~ 600px · 화면 높이 950 이라 창(580px)은 아래 343px 로 줄어 창 안에서 구른다.
fire(press('r1', 2), 'click')
R.open = { maxHeight: list().style.maxHeight, ...seen() }
key('ArrowDown', 15)
R.down = seen()
// 휠로 창 안을 굴린 자리는 고른 값이 보이는 동안 화살표로 다시 지어도 이어 받는다.
list().scrollTop = 200
key('ArrowUp', 1)
R.kept = seen()
key('ArrowUp', 9)
R.up = seen()
// 처음 값에서 ↑ 는 끝 값(비움)으로 돈다.
key('ArrowUp', 6)
R.wrap = seen()
// 다른 칸의 창은 앞 창의 스크롤을 이어 받지 않는다 — r3 의 값 O12(창 안 316 ~ 340px)는
// 앞 창 211 이면 그대로 보인다.
fire(press('r3', 2), 'click')
R.other = { cell: S.edit ? S.edit.id : null, ...seen() }
cleanup()
process.stdout.write(JSON.stringify(R))
"""
)


def test_a_shortened_choice_list_keeps_the_active_value_inside_it() -> None:
    """화면이 낮아 줄여 편 고르기 창에서 ↓ 로 접힌 아래 값에 가면 고른 값이 창 밖에 남았다
    (2026-11-12 검토) — 창은 화살표마다 새로 지어 창 안 스크롤이 0 으로 돌아갔다. 창 안 스크롤은
    같은 칸의 앞 창을 이어 받고 고른 값이 보이게 가장 적게 옮긴다(`placeChoice` → `listScroll`).
    다른 칸의 창은 이어 받지 않는다."""
    result = _node({}, _LIST_SCROLL_RUNNER, source=FAKE_DOM + _fake_dom_source())
    assert result["open"] == {
        "maxHeight": "343px",
        "active": "O0",
        "focus": True,
        "top": 0,
        "inside": True,
    }
    # O15 는 창 안 394 ~ 418px — 보이는 341px 에 여백 4 를 더해 81 까지 굴린다.
    assert result["down"] == {"active": "O15", "focus": True, "top": 81, "inside": True}
    assert result["kept"] == {"active": "O14", "focus": True, "top": 200, "inside": True}
    assert result["up"] == {"active": "O5", "focus": True, "top": 130, "inside": True}
    assert result["wrap"] == {"active": "(비움)", "focus": True, "top": 211, "inside": True}
    assert result["other"] == {
        "cell": "r3",
        "active": "O12",
        "focus": True,
        "top": 3,
        "inside": True,
    }


def test_the_choice_list_floats_on_screen_and_the_text_editor_stays_under_the_head() -> None:
    """두 줄만 불러온 표에서 고르기 창을 열면 머리가 위로 밀려 사라지고 값이 잘렸다(2026-11-12
    사용자 요청 2) — 창이 표 상자 안 절대 자리라 상자를 넘치게 했다. 창은 화면 자리(fixed)에
    떠 상자에 잘리지 않고 창 안에서 구르며, 고르는 칸만 머리 위로 올린다(위로 편 창이 머리에
    깔리지 않게). 글 칸은 머리 밑이다 — 머리 밑에 걸친 편집 칸이 머리를 덮었다."""
    dropdown = re.search(r"\n\.emg-dd \{(?P<body>[^}]*)\}", CSS)
    assert dropdown is not None
    for part in ("position: fixed", "overflow-y: auto", "overscroll-behavior: contain"):
        assert part in dropdown["body"], part
    for gone in ("top: 33px", "min-width: calc(100% + 2px)", "position: absolute"):
        assert gone not in dropdown["body"], gone
    head = re.search(r"\n\.emg-head \{(?P<body>[^}]*)\}", CSS)
    editing = re.search(r"\n\.emg-c\.is-editing \{(?P<body>[^}]*)\}", CSS)
    choosing = re.search(r"\n\.emg-c\.is-editing\.is-choosing \{(?P<body>[^}]*)\}", CSS)
    name = re.search(r"\n\.emg-c-name \{(?P<body>[^}]*)\}", CSS)
    assert head and editing and choosing and name

    def z(match: re.Match[str]) -> int:
        found = re.search(r"z-index: (\d+)", match["body"])
        assert found
        return int(found.group(1))

    assert z(name) < z(editing) < z(head) < z(choosing)
    start = _function("startEdit")
    assert start.index("ensureVisible(S, id)") < start.index("paintWindow(S)")
    assert "listen(S, document, 'scroll', onPageMove, true)" in _function("buildGridSkeleton")


def test_the_table_note_floats_over_the_column_bar_without_pushing_the_table() -> None:
    """브라우저 한 줄(「붙여넣는 중」 · 이름 붙여넣기 거부 · 칸 수 상한)이 볼 칸 줄과 표 사이 흐름에
    끼어 표를 43 ~ 53px 밀었다(c5, 샘플 관측). 표 틀 맨 위 볼 칸 줄 위에 떠서 표는 그 자리다 —
    오른쪽 칸의 같은 줄은 칸 머리 흐름 그대로다."""
    assert "el('div', 'emg-note is-float')" in _function("buildGridSkeleton")
    assert "el('div', 'emg-note')" in _function("drawSide")
    rule = re.search(r"\n\.emg-note\.is-float \{(?P<body>[^}]*)\}", CSS)
    assert rule is not None
    for part in ("position: absolute", "top: 0", "left: 0", "right: 0"):
        assert part in rule["body"], part


_DETAIL_DRAFT_RUNNER = """
FakeNode.prototype.select = function () {}
FakeNode.prototype.scrollIntoView = function () {}
Object.defineProperty(FakeNode.prototype, 'innerHTML', { set() { this.textContent = '' } })
document.querySelector = () => null
document.documentElement = { clientWidth: 1200 }
const parentElement = new FakeNode('div')
const host = parentElement.appendChild(new FakeNode('div'))
host.className = 'emg'
const outgoing = []
const data = (base, memo) => ({
  mode: 'side', panel: 'detail', base,
  columns: [
    { name: '설비명', kind: 'name' },
    { name: '메모1', kind: 'memo' },
    { name: '메모2', kind: 'memo' },
  ],
  groups: [['memo', '메모', '', '', [1, 2]]],
  unit: { id: 's:D-1', values: ['D-1', memo, 'same'], downtime: [], deletable: true },
})
const component = {
  parentElement, setTriggerValue() {},
  setStateValue: (name, value) => {
    outgoing.push(value.ops.map((op) => [op.op, op.base, op.col, op.text]))
  },
}
globalThis.__mount({ data: data('b1', 'old'), ...component })
const S = host.__emg
const fields = () => host.querySelectorAll('.emg-input')
const R = {}
;(async () => {
  const [memo1, memo2] = fields()
  memo1.value = 'typed'
  fire(memo1, 'input')
  memo2.value = 'same'
  fire(memo2, 'input')
  // 남의 저장으로 편집본이 다시 섰다 — 바탕 값도 바뀌어 왔다.
  globalThis.__mount({ data: data('b2', 'theirs'), ...component })
  R.drafts = S.drafts.size
  R.shown = fields()[0].value
  await tick(360)
  R.sent = outgoing[outgoing.length - 1] || null
  process.stdout.write(JSON.stringify(R))
})()
"""


def test_text_typed_in_the_detail_panel_goes_out_like_an_open_cell_when_the_base_changes() -> None:
    """호기 상세 칸에 친 채 확정하지 않은 글은 남의 저장으로 편집본이 다시 서면 말없이 비워졌다
    (c4). 표의 연 칸과 같이 옛 base op 로 보내 서버가 세어 알린다 — 보이던 값 그대로인 글은
    보내지 않는다."""
    result = _node({}, _DETAIL_DRAFT_RUNNER, source=FAKE_DOM + _fake_dom_source())
    assert result["drafts"] == 0
    assert result["shown"] == "theirs"
    assert result["sent"] == [["cell", "b1", "메모1", "typed"]]


# ---------------------------------------------------------------- 모듈 묶음 같이 쓰기(Space 요청 3)

_KEPT_VIEW_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
process.stdout.write(JSON.stringify(input.cases.map((c) => keptView(c[0], c[1], c[2], c[3]))))
"""


def test_the_view_is_kept_only_when_moves_and_inserted_rows_explain_the_new_list() -> None:
    """목록 지문이 바뀐 회차 — 앞 목록에 옮김을 얹고 끼운 줄만 빼면 새 목록과 같을 때만 고름 ·
    스크롤을 지킨다. 같은 회차에 불러오기 · 빼기가 목록을 바꿨으면(옮김 · 끼움이 함께 실려도)
    처음으로 돌린다. 옮김도 끼움도 없으면 늘 처음으로다."""
    cases = [
        [["a", "b", "c"], ["a", "x", "y", "b", "c"], [], ["x", "y"]],
        [["a", "b", "c"], ["a", "b2", "c"], [["b", "b2"]], []],
        [["a", "b", "c"], ["a", "b2", "x", "c"], [["b", "b2"]], ["x"]],
        [["a", "b", "c"], ["a", "x", "c"], [], ["x"]],
        [["a", "b", "c"], ["c", "x", "a", "b"], [], ["x"]],
        [["a", "b"], ["q", "r"], [], []],
        [["a", "b"], ["a", "b", "c"], [], []],
    ]
    result: object = _node({"cases": cases}, _KEPT_VIEW_RUNNER)
    assert result == [True, True, True, False, False, False, False]


_ROW_SHIFT_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
process.stdout.write(JSON.stringify(input.cases.map((c) => keptRowShift(c[0], c[1], c[2]))))
"""


def test_the_kept_view_scrolls_by_how_far_the_first_seen_row_moved() -> None:
    """지킨 보기(끼운 형제 줄 · 이름 바꿈만 목록을 바꾼 회차)에서 보던 첫 줄이 새 보이는 차례에서
    옮겨 간 줄 수만큼 스크롤을 옮겨 보던 줄을 그 자리에 둔다(UI-PRF-03). 고친 줄이 위로 굴러간 채
    「호기 상세」 에서 고치면 형제가 보던 줄 위에 끼워지고, 정렬한 표에서 정렬 칸을 고치면 고친 줄 ·
    형제 줄이 보던 줄 앞뒤로 옮겨 간다 — 끼운 줄 수만 세면 정렬로 옮긴 몫이 남았다. 보던 줄이 고친
    줄 자신이면 옮겨 간 그 줄을 따라간다(음수 — 위로). 늘어난 높이를 먼저 세워 옮긴 스크롤이 옛 끝에
    잘리지 않는다."""
    cases = [
        # 정렬 없음 — 보던 줄(b, 앞 차례 2번째) 앞에 형제 셋이 끼워짐.
        [["a", "t", "x", "y", "z", "b", "c"], "b", 2],
        # 끼운 줄이 보던 줄 뒤.
        [["a", "t", "x", "y", "b", "c"], "a", 0],
        [["a", "t", "x", "b"], "t", 1],
        [["x", "a", "b"], "b", 1],
        # 보던 줄이 새 차례에 없음.
        [["a", "b"], "q", 0],
        # Model 오름차순 정렬 — g1 의 Model 을 Z → A 로 고쳐 g1 · 형제 g2 · g3 가 맨 앞으로(앞 차례
        # a c d e f g1, 보던 줄 e 는 3번째).
        [["g1", "g2", "g3", "a", "c", "d", "e", "f"], "e", 3],
        # 같은 고침에서 보던 줄이 g1 자신(앞 차례 5번째)이면 그 줄을 따라 위로.
        [["g1", "g2", "g3", "a", "c", "d", "e", "f"], "g1", 5],
        # 보던 줄(c, 2번째) 앞의 a 가 정렬로 뒤로 가고 형제 a2 가 그 뒤에 끼워짐.
        [["b", "c", "d", "a", "a2"], "c", 2],
    ]
    result: object = _node({"cases": cases}, _ROW_SHIFT_RUNNER)
    assert result == [3, 0, 0, 1, 0, 3, -5, -1]
    draw = _function("drawGrid")
    kept = draw[draw.index("if (!keptView(before, after, moved, inserted)) {") :]
    assert kept.index("S.resetScroll = true") < kept.index(
        "const top = Math.floor(S.scroller.scrollTop / ROW_H)"
    )
    assert "renamed.has(id) ? renamed.get(id) : id" in kept
    assert "keptRowShift(S.model.ordered.map((row) => row.id), keepTop.id, keepTop.top)" in draw
    assert "insertedAbove" not in JS
    shift = draw[draw.index("  if (shift) {") :]
    assert shift.index("S.body.style.height = S.model.ordered.length * ROW_H + 'px'") < shift.index(
        "S.scroller.scrollTop += shift * ROW_H"
    )
    assert shift.index("S.scroller.scrollTop += shift * ROW_H") < shift.index("paintWindow(S)")


_GROUP_VIEW_RUNNER = (
    _BURST_RUNNER[: _BURST_RUNNER.index("const parentElement = new FakeNode('div')")]
    + r"""
FakeNode.prototype.focus = function () { document.activeElement = this }
FakeNode.prototype.setSelectionRange = function () {}
const parentElement = new FakeNode('div')
const host = parentElement.appendChild(new FakeNode('div'))
host.className = 'emg'
const columns = [
  { name: '설비명', kind: 'name', width: 'name' },
  { name: 'Model', kind: 'text', width: 'm' },
  { name: '동', kind: 'choice', width: 's', options: ['C1', 'C2'], blank: true },
]
const red = {
  1: '같은 Main 설비의 모듈 행은 Model 칸이 같아야 합니다',
  2: '같은 Main 설비의 모듈 행은 동이 같아야 합니다',
}
const make = (ids, top, errors) => ({
  mode: 'grid', base: 'b1', view: ids.join(','), limits: { outboxCells: 10000, pasteCells: 5000 },
  columns, colSets: [['all', '전체', '', [1, 2]]],
  rows: ids.map((id) => ({
    id, values: [id, 'm', 'C1'], ...(errors && errors[id] ? { errors: errors[id] } : {}),
  })),
  ...(top || {}),
})
const component = { parentElement, setTriggerValue() {}, setStateValue() {} }
const mount = (data) => globalThis.__mount({ data, ...component })
const ids = []
for (let k = 0; k < 60; k += 1) ids.push('r' + k)
const cleanup = mount(make(ids))
const S = host.__emg
const state = () => ({
  top: S.scroller.scrollTop, selected: Array.from(S.selected).sort(), anchor: S.anchor,
})
const queued = () => S.box.ops.map((op) => [op.op, op.id, op.col, op.text])
const R = {}
// 줄을 골라 둔 채 표 가운데까지 굴린 뒤 — 형제 둘이 고친 줄(r12) 바로 아래에 끼어 온다.
S.scroller.scrollTop = 340
S.selected = new Set(['r12', 'r13'])
S.anchor = 'r12'
const withSiblings = [...ids.slice(0, 13), 'x1', 'x2', ...ids.slice(13)]
mount(make(withSiblings, { inserted: ['x1', 'x2'] }))
R.inserted = state()
// 새 호기 이름 바꿈(행 id 옮김) — 고름 · 기준 줄이 새 id 로 따라가고 스크롤은 그대로다.
const renamed = withSiblings.map((id) => (id === 'r12' ? 'r12b' : id))
mount(make(renamed, { moved: { r12: 'r12b' } }))
R.moved = state()
// 다음 회차(실린 것 없음 · 같은 목록)는 그대로다.
mount(make(renamed))
R.again = state()
// 같은 회차에 다른 줄이 빠졌으면(불러오기 · 빼기) 끼움이 실려도 처음으로 돌린다.
mount(make([...renamed.filter((id) => id !== 'r40'), 'x3'], { inserted: ['x3'] }))
R.otherChange = state()
// 막는 오류 표지가 선 칸은 같은 글도 확정(Enter · 고르기)하면 보낸다 — 칸을 열고 떠나기만
// 하면, 빨갛지 않은 칸은 보내지 않는다.
mount(make(ids, null, { r2: red }))
startEdit(S, 'r3', 1)
fire(body().querySelector('.emg-ed'), 'keydown', { key: 'Enter' })
R.plainEnter = queued()
startEdit(S, 'r2', 1)
fire(body().querySelector('.emg-ed'), 'focusout', { relatedTarget: null })
R.redLeave = queued()
startEdit(S, 'r2', 1)
fire(body().querySelector('.emg-ed'), 'keydown', { key: 'Enter' })
R.redEnter = queued()
startEdit(S, 'r2', 2)
pickChoice(S, 'C1')
R.redPick = queued()
cleanup()
process.stdout.write(JSON.stringify(R))
"""
).replace("body()", "S.body")


def test_rows_coming_in_with_a_group_write_keep_the_selection_and_the_scroll() -> None:
    """모듈 묶음 한 줄을 고치면 불러오지 않은 형제가 고친 줄 바로 아래에 끼어 와 목록 지문이
    바뀐다 — 그 회차에도 고른 줄 · 기준 줄 · 스크롤이 그대로다(설계 규칙 UI-PRF-03, 2026-11-12
    사용자 답 3-4). 새 호기 이름 바꿈의 id 옮김도 같다(전에는 옮김이 표 data 에 실리지 않아 맨
    위로 튀었다). 같은 회차에 다른 길로 목록이 바뀌었으면 처음으로 돌린다. 빨간 칸(묶음 갈림)은 같은
    글도 Enter · 고르기로 확정하면 보내 갈린 묶음을 푼다 — 열고 떠나기만 해서는 보내지 않는다."""
    result = _node({}, _GROUP_VIEW_RUNNER, source=FAKE_DOM + _fake_dom_source())
    assert result["inserted"] == {"top": 340, "selected": ["r12", "r13"], "anchor": "r12"}
    assert result["moved"] == {"top": 340, "selected": ["r12b", "r13"], "anchor": "r12b"}
    assert result["again"] == result["moved"]
    assert result["otherChange"] == {"top": 0, "selected": [], "anchor": None}
    assert result["plainEnter"] == []
    assert result["redLeave"] == []
    assert result["redEnter"] == [["cell", "r2", "Model", "m"]]
    assert result["redPick"] == [["cell", "r2", "Model", "m"], ["cell", "r2", "동", "C1"]]


_NAME_SORT_VIEW_RUNNER = (
    _BURST_RUNNER[: _BURST_RUNNER.index("const parentElement = new FakeNode('div')")]
    + r"""
FakeNode.prototype.focus = function () { document.activeElement = this }
const columns = [
  { name: '설비명', kind: 'name', width: 'name' },
  { name: 'Qual일정', kind: 'date', width: 'm' },
]
const qual = (k) => (k % 3 === 0 ? '' : k % 2 ? '2026-11-01' : '2026-12-01')
const make = (rows, top) => ({
  mode: 'grid', base: 'b1', view: rows.map((row) => row[0]).join(','),
  limits: { outboxCells: 10000, pasteCells: 5000 },
  columns, colSets: [['all', '전체', '', [1]]],
  rows: rows.map(([id, name, date]) => ({ id, values: [name, date] })),
  ...(top || {}),
})
const mountOn = (data) => {
  const parentElement = new FakeNode('div')
  const host = parentElement.appendChild(new FakeNode('div'))
  host.className = 'emg'
  const component = { parentElement, setTriggerValue() {}, setStateValue() {} }
  const again = (next) => globalThis.__mount({ data: next, ...component })
  again(data)
  return { S: host.__emg, again }
}
// 불러온 차례는 이름 차례가 아니다(새로 든 호기가 위로).
const rows = []
for (let k = 0; k < 60; k += 1) rows.push(['s:' + k, '호기 ' + ((k * 37) % 60 + 1), qual(k)])
const { S, again } = mountOn(make(rows))
const names = () => S.model.ordered.map((row) => row.values[0])
const pairs = () => S.model.ordered.map((row) => [row.values[1], row.values[0]])
const head = () => S.head.querySelectorAll('[role="columnheader"]')
  .map((cell) => [cell.textContent, cell.getAttribute('aria-sort')])
const R = {}
R.first = { names: names(), head: head() }
toggleSort(S, 1)
R.asc = { pairs: pairs(), head: head() }
toggleSort(S, 1)
R.desc = { pairs: pairs(), head: head() }
toggleSort(S, 1)
R.cleared = { names: names(), head: head() }
toggleSort(S, 0)
R.nameDesc = { names: names(), head: head() }
toggleSort(S, 0)
R.nameBack = { names: names(), head: head() }
// 「호기 추가」 — 새 호기가 불러온 목록 맨 위에 들고 오른쪽 칸에 열린다. 보이는 차례는 설비명
// 차례라 그 줄까지 굴린다.
S.scroller.scrollTop = 340
const fresh = ['n:호기 45B', '호기 45B', '']
again(make([fresh, ...rows], { open: 'n:호기 45B' }))
const at = (id) => S.model.ordered.findIndex((row) => row.id === id)
R.added = { top: S.scroller.scrollTop, at: at('n:호기 45B') }
// 연 줄이 새로 든 줄이 아닌 불러오기는 지금처럼 맨 위로.
S.scroller.scrollTop = 340
again(make([['s:x', '호기 7A', ''], fresh, ...rows], { open: 'n:호기 45B' }))
R.loaded = { top: S.scroller.scrollTop }
// 처음 그리기는 연 줄이 있어도 맨 위.
const other = mountOn(make(rows, { open: 's:5' }))
R.firstOpen = { top: other.S.scroller.scrollTop }
process.stdout.write(JSON.stringify(R))
"""
)


def test_the_grid_starts_in_name_order_and_a_sort_breaks_ties_by_name() -> None:
    """설비 마스터 표 — 불러온 차례(새로 든 호기가 위)와 상관없이 처음 차례는 설비명 오름차순이고
    (호기 2 가 호기 10 앞), Qual일정 오름 · 내림에서 같은 날 호기는 설비명 오름차순, 빈 날은
    아래다. 세 번째 누름은 설비명 차례로 돌아가고, 설비명 머리는 처음 차례 ↔ 내림이다. 처음 차례의
    설비명 머리는 ▲ 없이 읽기 도구에만 오름차순(설계 규칙 UI-TXT-05). 「호기 추가」 로 새로 든 줄을
    오른쪽 칸에 연 회차는 설비명 차례에 선 그 줄을 표 머리 바로 아래로 굴리고, 다른 불러오기 ·
    처음 그리기는 지금처럼 맨 위다(UI-PRF-03 · 2026-11-20 사용자 요청)."""
    result = _node({}, _NAME_SORT_VIEW_RUNNER, source=FAKE_DOM + _fake_dom_source())
    natural = [f"호기 {k}" for k in range(1, 61)]
    assert result["first"]["names"] == natural
    assert result["first"]["head"] == [["설비명", "ascending"], ["Qual일정", None]]

    def grouped(pairs: list[list[str]], dates: list[str]) -> None:
        assert [date for date, _ in pairs] == sorted(
            (date for date, _ in pairs), key=lambda date: (date == "", dates.index(date))
        )
        for date in dates:
            same = [name for when, name in pairs if when == date]
            assert same == sorted(same, key=natural_name_key), date or "빈 날"

    grouped(result["asc"]["pairs"], ["2026-11-01", "2026-12-01", ""])
    assert result["asc"]["head"] == [["설비명", None], ["Qual일정 ▲", "ascending"]]
    grouped(result["desc"]["pairs"], ["2026-12-01", "2026-11-01", ""])
    assert result["desc"]["head"] == [["설비명", None], ["Qual일정 ▼", "descending"]]
    assert result["cleared"]["names"] == natural
    assert result["cleared"]["head"] == result["first"]["head"]
    assert result["nameDesc"]["names"] == natural[::-1]
    assert result["nameDesc"]["head"] == [["설비명 ▼", "descending"], ["Qual일정", None]]
    assert result["nameBack"] == result["first"]
    added = result["added"]
    assert added["at"] == 45, "호기 45 와 46 사이"
    assert added["top"] == 45 * 34, "그 줄이 표 머리 바로 아래"
    assert result["loaded"]["top"] == 0
    assert result["firstOpen"]["top"] == 0


_TEXT_SORT_VIEW_RUNNER = (
    _BURST_RUNNER[: _BURST_RUNNER.index("const parentElement = new FakeNode('div')")]
    + r"""
FakeNode.prototype.focus = function () { document.activeElement = this }
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const columns = [
  { name: '설비명', kind: 'name', width: 'name' },
  { name: 'Model', kind: 'text', width: 'text' },
  { name: '동', kind: 'choice', width: 'short', options: input.options, blank: true },
  { name: '메모2', kind: 'memo', width: 'memo' },
]
const parentElement = new FakeNode('div')
const host = parentElement.appendChild(new FakeNode('div'))
host.className = 'emg'
globalThis.__mount({
  data: {
    mode: 'grid', base: 'b1', view: input.rows.map((row) => row[0]).join(','),
    limits: { outboxCells: 10000, pasteCells: 5000 },
    columns, colSets: [['all', '전체', '', [1, 2, 3]]],
    rows: input.rows.map(([id, ...values]) => ({ id, values })),
  },
  parentElement, setTriggerValue() {}, setStateValue() {},
})
const S = host.__emg
const shown = () => S.model.live.map((row) => row.id)
const R = {}
for (const col of [1, 2, 3]) {
  toggleSort(S, col)
  R['asc' + col] = shown()
  toggleSort(S, col)
  R['desc' + col] = shown()
  toggleSort(S, col)
}
process.stdout.write(JSON.stringify(R))
"""
)


def test_a_text_header_sorts_its_rows_like_the_name_column() -> None:
    """설비 마스터 표에서 글 칸(Model) · 고르기 칸(동) · 메모 칸(메모2) 머리를 누르면 보이는
    줄이 설비명 칸과 같은 차례로 선다 — 영문이 한글 앞, 이름 안 숫자는 수로, 같은 값은 설비명
    오름차순, 빈 값은 오름 · 내림 모두 아래(2026-11-20 결과 보드 여쭘-2 a)."""
    rows = [
        ["s:1", "호기 1", "가람-2", "본관", "도면 미표시"],
        ["s:2", "호기 2", "DEMO-MDL-10", "C10", "Qual 지연 — 부품 수급"],
        ["s:3", "호기 3", "DEMO-MDL-9", "C2", "11월 1주 — 셋업 지연"],
        ["s:4", "호기 4", "가람-10", "본관", ""],
        ["s:5", "호기 5", "", "C1", "자리 미정"],
        ["s:6", "호기 6", "나래-1", "", "D 모듈 도면 숨김"],
        ["s:7", "호기 7", "DEMO-MDL-9", "C10", ""],
        ["s:8", "호기 8", "7A", "C2", "도면 미표시"],
    ]
    options = ["본관", "C10", "C2", "C1"]
    result = _node(
        {"rows": rows, "options": options},
        _TEXT_SORT_VIEW_RUNNER,
        source=FAKE_DOM + _fake_dom_source(),
    )

    def expected(col: int, descending: bool) -> list[str]:
        filled = [row for row in rows if row[col]]
        by_name = sorted(filled, key=lambda row: natural_name_key(row[1]))
        ordered = sorted(by_name, key=lambda row: natural_name_key(row[col]), reverse=descending)
        return [row[0] for row in ordered] + [row[0] for row in rows if not row[col]]

    for col in (1, 2, 3):
        assert result[f"asc{col}"] == expected(col + 1, False), col
        assert result[f"desc{col}"] == expected(col + 1, True), col
    assert result["asc1"] == ["s:8", "s:3", "s:7", "s:2", "s:1", "s:4", "s:6", "s:5"]
    shown = ["s:5", "s:3", "s:8", "s:2", "s:7", "s:1", "s:4", "s:6"]
    assert result["asc2"] == shown, "C1 · C2 · C10 · 본관 · 빈 값"


_NAME_VIEW_PREFIX = _NAME_SORT_VIEW_RUNNER[
    : _NAME_SORT_VIEW_RUNNER.index("// 불러온 차례는 이름 차례가 아니다")
]

_NAME_PASTE_RUNNER = (
    _NAME_VIEW_PREFIX
    + r"""
// 찾기 칸에 엑셀 설비명 열(호기 10 · 호기 2 · 호기 7)을 붙여 불러온 목록 — 받은 차례 그대로다.
const { S } = mountOn(make([['s:10', '호기 10', ''], ['s:2', '호기 2', ''], ['s:7', '호기 7', '']]))
const paste = (text, id, col) => {
  const cell = { dataset: { id, col: String(col) } }
  const target = {
    closest: (sel) => (sel.startsWith('.emg-c') ? cell : null),
    classList: { contains: () => false },
  }
  S.note = ''
  const count = S.box.ops.length
  onPaste(S, { target, clipboardData: { getData: () => text }, preventDefault() {} })
  const op = S.box.ops.length > count ? S.box.ops[S.box.ops.length - 1] : null
  return {
    op: op
      ? { op: op.op, ids: op.ids, cols: op.cols, rows: op.rows, cut: op.cut, skipped: op.skipped }
      : null,
    note: S.note,
  }
}
const R = { visible: S.model.live.map((row) => row.id) }
const first = S.model.live[0].id
// 엑셀에서 설비명 열부터 세 줄을 잡아 첫 줄 설비명 칸에 붙인다.
R.byName = paste('호기 10\t2026-11-01\n호기 2\t2026-12-01\n호기 7\t2027-01-01\n', first, 0)
R.missing = paste('호기 10\t2026-11-01\n호기 99\t2026-12-01\n', first, 0)
R.namesOnly = paste('호기 10\n호기 2\n', first, 0)
R.onDate = paste('2026-11-01\n2026-12-01\n', first, 1)
process.stdout.write(JSON.stringify(R))
"""
)


def test_pasting_a_block_from_the_name_column_lands_on_the_named_units() -> None:
    """찾기 칸에 엑셀 설비명 열을 붙여 불러온 목록(호기 10 · 호기 2 · 호기 7 — 받은 차례)은 표에서
    설비명 차례(호기 2 · 호기 7 · 호기 10)로 선다. 엑셀에서 설비명 열부터 잡은 덩이를 설비명 칸에
    붙이면 보이는 차례가 아니라 붙인 설비명으로 줄을 맞대 값이 그 호기에 들고, 설비명 열은 열쇠라
    「넣지 못한 칸」 으로 세지 않는다. 못 맞대면 op 를 보내지 않고 한 줄, 설비명만 붙이면 지금처럼
    「설비명은 붙여 넣지 않습니다」. 설비명 밖 칸에서 시작한 붙여넣기는 보이는 차례
    그대로다(2026-11-20 검토 ems-paste-order)."""
    result = _node({}, _NAME_PASTE_RUNNER, source=FAKE_DOM + _fake_dom_source())
    assert result["visible"] == ["s:2", "s:7", "s:10"]
    assert result["byName"]["op"] == {
        "op": "paste",
        "ids": ["s:10", "s:2", "s:7"],
        "cols": ["Qual일정"],
        "rows": [["2026-11-01"], ["2026-12-01"], ["2027-01-01"]],
        "cut": 0,
        "skipped": 0,
    }
    assert result["missing"] == {
        "op": None,
        "note": "붙인 설비명 1개를 표에서 찾지 못해 붙이지 않았습니다 — 호기 99"
        " · 찾기 칸으로 불러온 뒤 다시 붙입니다",
    }
    name_note = re.search(r"const NAME_PASTE_NOTE = '([^']+)'", JS)
    assert name_note is not None
    assert result["namesOnly"] == {"op": None, "note": name_note.group(1)}
    assert result["onDate"]["op"]["ids"] == ["s:2", "s:7"], "설비명 밖 칸은 보이는 차례"


_OPEN_FOLLOW_RUNNER = (
    _NAME_VIEW_PREFIX
    + r"""
const rows = []
for (let k = 0; k < 60; k += 1) rows.push(['s:' + k, '호기 ' + (k + 1), ''])
const R = {}
const renameOpen = (open, top, name) => {
  const { S, again } = mountOn(make(rows, { open }))
  S.scroller.scrollTop = top * 34
  const at = (id) => S.model.ordered.findIndex((row) => row.id === id)
  const before = at(open) - top
  const renamed = rows.map((r) => (r[0] === open ? [open, name, ''] : r))
  again({ ...make(renamed, { open }), view: make(rows).view })
  return { slot: [before, at(open) - S.scroller.scrollTop / 34], top: S.scroller.scrollTop }
}
// 저장본 호기 이름 바꿈(행 id · 목록 지문 그대로) — 창 맨 위에 둔 연 줄, 창 가운데 연 줄
// (아래로 · 위로).
R.topRow = renameOpen('s:40', 40, '가-1')
R.down = renameOpen('s:25', 20, '호기 50A')
R.up = renameOpen('s:45', 40, '호기 10A')
// 창 밖에 둔 연 줄은 따라가지 않는다.
R.outside = renameOpen('s:5', 40, '호기 50A')
// 새 호기 이름 바꿈 — 행 id 가 옮겨 간다(moved).
{
  const withNew = [['n:호기 45B', '호기 45B', ''], ...rows]
  const { S, again } = mountOn(make(withNew, { open: 'n:호기 45B' }))
  S.scroller.scrollTop = 45 * 34
  const moved = { 'n:호기 45B': 'n:가-9' }
  again(make([['n:가-9', '가-9', ''], ...rows], { open: 'n:가-9', moved }))
  R.moved = { top: S.scroller.scrollTop, open: S.openId }
}
// 「목록 비우기」(연 상세는 그대로) 뒤 다시 불러오기 · 「호기 추가」 뒤 저장(n: → s:)은 맨 위다.
{
  const { S, again } = mountOn(make(rows, { open: 's:40' }))
  again(make([], { open: 's:40' }))
  S.scroller.scrollTop = 0
  again(make(rows, { open: 's:40' }))
  R.reload = S.scroller.scrollTop
  again(make([['n:호기 30A', '호기 30A', ''], ...rows], { open: 'n:호기 30A' }))
  R.added = S.scroller.scrollTop
  S.scroller.scrollTop = 340
  again(make([['s:호기 30A', '호기 30A', ''], ...rows], { open: 's:호기 30A' }))
  R.saved = S.scroller.scrollTop
}
process.stdout.write(JSON.stringify(R))
"""
)


def test_the_open_row_keeps_its_place_and_only_an_added_row_is_scrolled_to() -> None:
    """설비명 차례 표에서 호기 상세로 연 호기의 설비명을 바꾸면 그 줄이 새 차례 자리로 옮겨 간다 —
    앞 그리기에서 창 안에 보이던 연 줄이면 표가 그 줄을 따라가 창 안 같은 높이에 둔다(위로든
    아래로든, 저장본 · 새 호기 모두). 창 밖에 둔 연 줄은 따라가지 않는다(스크롤 그대로).
    처음으로 돌린 회차에 연 줄까지 굴리는 것은 「호기 추가」 뿐이고, 「목록 비우기」 뒤 다시
    불러오기와 저장은 맨 위다(설계 규칙 UI-PRF-03 — 2026-11-20 검토 ems-rename-jump ·
    ems-freshopen-extra)."""
    result = _node({}, _OPEN_FOLLOW_RUNNER, source=FAKE_DOM + _fake_dom_source())
    assert result["topRow"] == {"slot": [0, 0], "top": 0}
    assert result["down"] == {"slot": [5, 5], "top": 44 * 34}
    assert result["up"] == {"slot": [5, 5], "top": 5 * 34}
    assert result["outside"]["top"] == 40 * 34
    assert result["moved"] == {"top": 0, "open": "n:가-9"}
    assert result["reload"] == 0
    assert result["added"] == 30 * 34, "호기 30 다음 자리를 표 머리 바로 아래로"
    assert result["saved"] == 0


_GROUP_DETAIL_RUNNER = """
FakeNode.prototype.select = function () {}
FakeNode.prototype.scrollIntoView = function () {}
Object.defineProperty(FakeNode.prototype, 'innerHTML', { set() { this.textContent = '' } })
document.querySelector = () => null
document.documentElement = { clientWidth: 1200 }
const parentElement = new FakeNode('div')
const host = parentElement.appendChild(new FakeNode('div'))
host.className = 'emg'
const data = (group, errors, shared) => ({
  mode: 'side', panel: 'detail', base: 'b1',
  columns: [
    { name: '설비명', kind: 'name' },
    { name: '담당자', kind: 'text' },
    { name: '동', kind: 'choice', options: ['C1', 'C2'], blank: true },
    { name: '메모1', kind: 'memo' },
  ],
  groups: [['main', '기본', '', '', [1, 2, 3]]],
  sharedCols: shared,
  unit: {
    id: 's:D-1', values: ['D-1', '가', 'C1', ''], downtime: [], deletable: true, errors,
    ...(group ? { group } : {}),
  },
})
const component = { parentElement, setTriggerValue() {}, setStateValue() {} }
const mount = (d) => globalThis.__mount({ data: d, ...component })
const tags = () => host.querySelectorAll('.emg-group-tag')
  .map((node) => [node.parentNode.textContent, node.title])
const R = {}
mount(data({ name: 'GRP-1', count: 4 }, {}, [1, 2]))
const S = host.__emg
const queued = () => S.box.ops.map((op) => [op.op, op.col, op.text])
R.tags = tags()
const chip = (value) => host.querySelectorAll('.emg-chip')
  .find((node) => node.textContent === value)
const input = () => host.querySelectorAll('.emg-input')[0]
fire(chip('C1'), 'click')
fire(input(), 'keydown', { key: 'Enter' })
R.plain = queued()
mount(data({ name: 'GRP-1', count: 4 }, { 1: '갈림', 2: '갈림' }, [1, 2]))
fire(input(), 'blur')
R.leave = queued()
fire(input(), 'keydown', { key: 'Enter' })
fire(chip('C1'), 'click')
R.red = queued()
mount(data(null, {}, [1, 2]))
R.alone = tags()
process.stdout.write(JSON.stringify(R))
"""


def test_the_detail_marks_shared_columns_of_a_module_group_and_resends_a_red_value() -> None:
    """호기 상세 — 모듈 묶음(둘 이상) 줄이면 같이 바뀌는 칸(`sharedCols`) 이름 곁에만 「묶음」 글
    표지 + 풍선이 선다(2026-11-12 사용자 답 3-5). 묶음 밖 줄은 없다. 빨간 칸은 같은 글도 Enter ·
    칩으로 확정하면 보낸다 — 떠나기(blur)만 해서는 · 빨갛지 않은 칸은 보내지 않는다."""
    result = _node({}, _GROUP_DETAIL_RUNNER, source=FAKE_DOM + _fake_dom_source())
    tip = "같은 Main 설비(GRP-1) 모듈 4줄에 함께"
    assert result["tags"] == [["담당자묶음", tip], ["동묶음", tip]]
    assert result["plain"] == []
    assert result["leave"] == []
    assert result["red"] == [["cell", "담당자", "가"], ["cell", "동", "C1"]]
    assert result["alone"] == []
    rule = re.search(r"\n\.emg-group-tag \{(?P<body>[^}]*)\}", CSS)
    assert rule is not None and "var(--emg-accent)" in rule["body"]


# ---------------------------------------------------------------- 표 data 가르기(껍데기 · feed)

FEED_JS = (ASSETS / "feed.js").read_text(encoding="utf-8")


def test_the_feed_registration_is_small_and_the_table_waits_for_its_own_shell() -> None:
    """feed 등록은 작은 JS 하나(주석 줄을 걷는다)이고 칸 · 이벤트 이름이 표 JS 와 같다. 표 key ·
    feed key 는 고정이고 feed 요소를 숨기는 서식이 메뉴 서식 덩이에 든다(이벤트 칸 자리 수를 늘리지
    않는다)."""
    registered = emg.feed_js()
    assert len(registered.encode("utf-8")) < 1_000
    assert not any(line.lstrip().startswith("//") for line in registered.splitlines())
    assert "__capaEquipmentGrid" in registered and "__capaEquipmentGrid" in JS
    assert "'capa-equipment-grid'" in registered and "'capa-equipment-grid'" in JS
    assert emg.feed_key() == f"{emg.GRID_KEY}-feed" and "__" not in emg.feed_key()
    assert f".st-key-{emg.feed_key()} {{ display: none; }}" in emg.tools_menu_style()
    assert "_FEED(key=feed_key(key)" in SOURCE
    assert SOURCE.index("_FEED(key=feed_key(key)") < SOURCE.index(
        "_GRID(\n        key=key,\n        data=sent"
    )


def test_the_browser_joins_shell_and_feed_the_way_python_does() -> None:
    """브라우저가 잇는 표 data(`joinGridData`) = 파이썬 `join_grid_data` = 가르기 전 data. 다른
    껍데기의 feed 는 잇지 않는다(null — 그 껍데기를 기다린다)."""
    from test_equipment_grid_model import _copy, _saved, _view

    saved = _saved()
    view = _view(_copy(saved), saved)
    loaded = list(view.index.ids[:3])
    shell, _ = eg.split_grid_data(eg.grid_data(view, loaded))
    edited = _copy(saved)
    edited[1].loc[2, "Model"] = "MODEL-Z"
    data = eg.grid_data(_view(edited, saved), loaded, ack={"mount": "m-x", "seq": 4})
    kept, feed = eg.split_grid_data(data, shell)
    assert kept == shell and feed["rows"]
    runner = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
process.stdout.write(JSON.stringify({
  joined: joinGridData(input.shell, input.feed),
  other: joinGridData(input.shell, Object.assign({}, input.feed, { shell: 'other' })),
}))
"""
    match = re.search(r"// <grid-feed>\n(?P<body>.*?)\n// </grid-feed>", JS, re.S)
    assert match, "grid.js 에 // <grid-feed> 구획이 없습니다"
    result = _node({"shell": kept, "feed": feed}, runner, source=match.group("body"))
    assert result["joined"] == eg.join_grid_data(kept, feed) == data
    assert result["other"] is None


_SHELL_FEED_RUNNER = (
    _BURST_RUNNER[: _BURST_RUNNER.index("const data = {")]
    + FEED_JS.replace("export default function", "globalThis.__feed = function", 1)
    + """
const HOST = 'equipment_grid_table'
const columns = [
  { name: '설비명', kind: 'name', width: 'name' },
  { name: 'Model', kind: 'text', width: 'm' },
]
const rowOf = (id, name, model) => ({ id, values: [name, model] })
const shellOf = (token, rows) => ({
  mode: 'grid', host: HOST, shell: token, base: 'b1', view: 'v-' + token,
  limits: { outboxCells: 10000, pasteCells: 5000 }, columns, colSets: [['all', '전체', '', [1]]],
  rows,
})
const first = shellOf('s1', [rowOf('a', 'EQ-1', 'x'), rowOf('b', 'EQ-2', 'y')])
const feed = (token, extra) => globalThis.__feed({
  data: Object.assign({ host: HOST, shell: token, rows: {} }, extra),
})
let builds = 0
const build = buildGridSkeleton
buildGridSkeleton = (...args) => {
  builds += 1
  return build(...args)
}
const component = {
  parentElement, setTriggerValue() {},
  setStateValue: (name, value) => sent.push(value.ops.map((op) => op.seq)),
}
const R = {}
;(async () => {
  // 껍데기가 feed 보다 먼저 왔다 — 그 feed 가 올 때까지 그리지 않는다.
  const cleanup = globalThis.__mount({ data: first, ...component })
  const S = host.__emg
  R.waiting = { model: Boolean(S.model), builds }
  feed('s1', { ack: {}, counts: { loaded: 2, total: 2, limit: 1000 } })
  const models = () => S.model.rows.map((row) => row.values[1])
  R.drawn = { builds, models: models(), count: S.data.counts.loaded }
  // 칸 하나를 고쳐 보냈다 — 그 줄만 든 feed 가 오면 그 줄이 바뀌고 출납이 걷힌다(껍데기 그대로).
  enqueue(S, { op: 'cell', id: 'a', col: 'Model', text: 'X' }, [['a', 1, 'X']])
  send(S)
  const model = S.model
  feed('s1', { ack: { mount: S.mount, seq: 1 }, rows: { a: rowOf('a', 'EQ-1', 'X') } })
  R.patched = {
    builds, sent: sent.slice(), box: S.box.ops.length, pending: S.pending.size,
    models: models(), rebuilt: S.model !== model,
  }
  // 같은 껍데기 · 같은 바뀐 줄에 연 줄만 바뀐 feed — 표 모양을 다시 짓지 않는다.
  const kept = S.model
  feed('s1', { ack: { mount: S.mount, seq: 1 }, rows: { a: rowOf('a', 'EQ-1', 'X') }, open: 'b' })
  R.openOnly = { builds, same: S.model === kept, open: S.openId }
  // 다른 껍데기의 feed 는 잇지 않는다.
  feed('s9', { rows: { a: rowOf('a', 'EQ-1', 'Q') } })
  R.otherShell = { same: S.model === kept, models: models() }
  // 새 껍데기가 오면 그 껍데기의 feed 를 기다렸다 잇는다(칸에 남은 다른 껍데기 feed 로
  // 그리지 않는다).
  const third = [rowOf('a', 'EQ-1', 'X'), rowOf('b', 'EQ-2', 'y'), rowOf('c', 'EQ-3', 'z')]
  globalThis.__mount({ data: shellOf('s2', third), ...component })
  R.newShellWaits = { same: S.model === kept }
  feed('s2', { ack: { mount: S.mount, seq: 1 } })
  R.newShell = { builds, models: models() }
  cleanup()
  R.cleared = window.__capaEquipmentGrid[HOST].feed
  process.stdout.write(JSON.stringify(R))
})()
"""
)


def test_the_table_takes_feed_patches_and_does_not_rebuild_for_an_unchanged_shell() -> None:
    """표 JS 는 껍데기와 그 껍데기의 feed 를 이어 그린다(B4 data 가르기). feed 의 바뀐 줄이 그 줄을
    바꾸고 ack 가 출납을 걷는다. 껍데기가 그대로인 회차에는 표 뼈대를 다시 짓지 않고, 바뀐 줄도
    그대로인 feed(연 줄만 바뀜)에는 정렬한 표 모양도 다시 짓지 않는다. 다른 껍데기의 feed 는 그
    껍데기가 올 때까지 둔다. 내릴 때 칸의 feed 를 비운다(다음 마운트가 옛 feed 로 먼저 그리지
    않게)."""
    result = _node({}, _SHELL_FEED_RUNNER, source=FAKE_DOM + _fake_dom_source())
    assert result["waiting"] == {"model": False, "builds": 0}
    assert result["drawn"] == {"builds": 1, "models": ["x", "y"], "count": 2}
    assert result["patched"] == {
        "builds": 1,
        "sent": [[1]],
        "box": 0,
        "pending": 0,
        "models": ["X", "y"],
        "rebuilt": True,
    }
    assert result["openOnly"] == {"builds": 1, "same": True, "open": "b"}
    assert result["otherShell"] == {"same": True, "models": ["X", "y"]}
    assert result["newShellWaits"] == {"same": True}
    assert result["newShell"] == {"builds": 1, "models": ["X", "y", "z"]}
    assert result["cleared"] is None


# ---------------------------------------------------------------- 묶어 보내기 쉼(파이썬 값)

_SEND_MS_RUNNER = (
    _BURST_RUNNER[: _BURST_RUNNER.index("const R = {}")]
    + """
const remount = (extra) => globalThis.__mount({
  data: Object.assign({}, data, extra), ...component,
})
const paste = (text, id, col) => {
  const cell = { dataset: { id, col: String(col) } }
  const target = {
    closest: (sel) => (sel.startsWith('.emg-c') ? cell : null),
    classList: { contains: () => false },
  }
  onPaste(S, { target, clipboardData: { getData: () => text }, preventDefault() {} })
}
const R = {}
;(async () => {
  // 파이썬이 쉼을 1초로 주고 편집본이 깨끗하다 — 첫 칸은 곧바로, 그 답이 오기 전 칸은 1초를 모은다.
  remount({ sendMs: 1000, clean: true })
  R.sendMs = S.sendMs
  typed('a', 1, 'C1', press('Enter'))
  R.first = sent.length
  typed('a', 2, 'C2', press('Enter'))
  typed('b', 2, 'C3', press('Enter'))
  await tick(400)
  R.held = sent.length
  await tick(800)
  R.quiet = sent.slice()
  // 답이 왔다(깨끗하지 않음) — 첫 칸도 쉼을 기다린다.
  remount({ sendMs: 1000, clean: false, ack: { mount: S.mount, seq: 3 } })
  typed('c', 1, 'D1', press('Enter'))
  R.dirtyFirst = sent.length
  // 붙여넣기 · 단추 op · 표 밖 누름 · 창 숨김은 쉼 없이 곧바로 보낸다(앞에 모인 칸도 함께).
  paste('P1\\nP2', 'b', 2)
  R.paste = sent.length
  sendOnce(S, { op: 'restore', ids: ['a'] }, [])
  R.button = sent.length
  typed('b', 1, 'OUT', (input) => {
    document.activeElement = null
    fire(input, 'focusout', { relatedTarget: null })
  })
  R.outside = sent.length
  typed('c', 1, 'VIS', press('Enter'))
  for (const run of docListeners.visibilitychange) run()
  R.hidden = sent.length
  // 쉼을 주지 않으면 300ms 다.
  remount({ sendMs: undefined, clean: false })
  R.fallback = S.sendMs
  cleanup()
  process.stdout.write(JSON.stringify(R))
})()
"""
)


def test_the_send_interval_comes_from_python_and_the_immediate_paths_stay_immediate() -> None:
    """묶어 보내기 쉼은 파이썬 값(data `sendMs` — `equipment_master_grid.send_ms`)이다. 깨끗한
    편집본의 첫 op 는 곧바로 가고 그 답이 오기 전 칸은 쉼만큼 모은다. 붙여넣기 · 단추 op · 표 밖
    누름(focusout) · 창 숨김(visibilitychange)은 쉼이 길어도 곧바로 보낸다."""
    result = _node({}, _SEND_MS_RUNNER, source=FAKE_DOM + _fake_dom_source())
    assert result["sendMs"] == 1000
    assert result["first"] == 1, "깨끗한 편집본의 첫 칸은 곧바로"
    assert result["held"] == 1, "답이 오기 전 칸은 쉼(1초)만큼 모은다"
    assert result["quiet"] == [1, 3], "모은 두 칸은 쉼 뒤 한 번에"
    assert result["dirtyFirst"] == 2, "깨끗하지 않으면 첫 칸도 모은다"
    assert (result["paste"], result["button"]) == (3, 4)
    assert (result["outside"], result["hidden"]) == (5, 6)
    assert result["fallback"] == 300


def test_the_send_interval_reads_the_dev_override_only_in_range() -> None:
    """측정 사본 실행 줄 `CAPA_RR_GRID_SEND_MS` 만 쉼을 덮어쓴다 — 50 ~ 5000 정수가 아니면
    기본값."""
    assert emg.send_ms({}) == emg.SEND_MS == 300
    assert emg.send_ms({emg.SEND_MS_ENV: "800"}) == 800
    for text in ("", "abc", "10", "60000", "0.8"):
        assert emg.send_ms({emg.SEND_MS_ENV: text}) == emg.SEND_MS
