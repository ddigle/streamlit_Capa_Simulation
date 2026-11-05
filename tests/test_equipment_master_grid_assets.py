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

from js_runner import run_js_json
from test_design_tokens import SMALL_TEXT_MINIMUM, contrast_ratio

from capa_simulation.components import equipment_master_grid as emg
from capa_simulation.components.app_header import PAGE_TABS_SELECTOR
from capa_simulation.design import tokens
from capa_simulation.services import equipment_grid as eg

ASSETS = emg._ASSETS
HTML = (ASSETS / "grid.html").read_text(encoding="utf-8")
CSS = (ASSETS / "grid.css").read_text(encoding="utf-8")
JS = (ASSETS / "grid.js").read_text(encoding="utf-8")
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
        and {"cell", "paste", "set", "shift", "delete", "restore", "revert", "undo"} <= sent
    )


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
    """고른 줄 띠가 좁으면(1500px) 「반입·Qual 일정 [7]」 다음의 단위 「일」 만 다음 줄로
    넘어가 칸과 떨어졌다 — 이름·날 수 칸·「일」·밀기 단추를 한 덩이(`emg-shift`, 안에서 줄을
    바꾸지 않음)로 둔다. 빈 날짜 칸 자리표시는 실제 날짜(「2026-11-09」)라 값처럼 읽혔다 —
    꼴(YYYY-MM-DD)을 적는다(2026-10-25 E2E #26·#28)."""
    selection = _function("buildSelection")
    group = selection[
        selection.index("el('span', 'emg-shift')") : selection.index("bar.appendChild(shiftGroup)")
    ]
    for part in (
        "shiftGroup.appendChild(el('span', null, '반입·Qual 일정'))",
        "shiftGroup.appendChild(days)",
        "shiftGroup.appendChild(el('span', null, '일'))",
        "shiftGroup.appendChild(shift)",
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
    wide, narrow = CSS.split("@media (max-width: 640px)")
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


def test_a_toast_undo_names_its_step_and_side_mounts_draw_their_toast() -> None:
    """토스트 「되돌리기」 는 그 토스트가 가리킨 단계를 싣는다 — 대상 없는 undo 는 맨 위 단계(그
    뒤 칸 고침)를 되돌린다. 오른쪽 칸도 제 토스트(상세 「이 호기 지우기」)를 그린다."""
    toast = _function("fillToast")
    assert "{ op: 'undo', step: toast.undo }" in toast and "typeof toast.undo === 'string'" in toast
    assert "{ op: 'undo' }" not in JS
    assert "fillToast(S, toast, S.data && S.data.toast)" in _function("drawSide")
    assert "fillToast(S, S.toastBar" in _function("paintToast")


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
    selection = _function("buildSelection")
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
    assert "if (!moved.length)" in draw and "S.openId = typeof data.open === 'string'" in draw
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


# ---------------------------------------------------------------- JS 순수 구획(node)

_SECTIONS = (
    "grid-paste",
    "grid-nav",
    "grid-outbox",
    "grid-match",
    "grid-plan",
    "grid-sort",
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
    assert box[4:8] == [False, True, 0, "b2"]
    assert box[8] == 6


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


_TOAST_BOX_RUNNER = """
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
const toast = {
  isConnected: true, hidden: false, parentElement: side,
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
  revealToast(toast)
  return { box: box.scrollTop, page: calls.length ? calls : null }
}
const out = {}
// 붙은 오른쪽 칸, 본문 칸 맨 아래(사본 앱 1500×950 — 본문 칸 위 끝 302, 스크롤 1474).
out.bottom = run(() => { box.scrollTop = 1474 })
// 본문 칸이 조금만 내려가 토스트가 머리 띠 아래이지만 칸 위로 가려 있다.
out.little = run(() => { box.scrollTop = 120 })
// 칸 안에서 보인다.
out.visible = run(() => { box.scrollTop = 0 })
// 좁은 창에서 쌓인 칸이 화면 위로 나가 있다 — 칸을 올린 뒤에도 가려 있어 페이지를 옮긴다.
out.stacked = run(() => { box.top = -500; box.scrollTop = 300 })
// 넘치지 않는 칸은 스크롤 칸이 아니다 — 페이지 길(전과 같음).
out.short = run(() => { box.top = -200; box.scrollTop = 0; box.scrollHeight = 653 })
// 스크롤 칸 없이 페이지 본문(stMain) 바로 안.
out.page = run(() => { box.scrollHeight = 2200; box.overflowY = 'visible'; box.top = -300 })
// 내려간 토스트·떨어진 토스트는 건드리지 않는다.
out.hidden = run(() => {
  box.overflowY = 'auto'; box.top = 302; box.scrollTop = 1474; toast.hidden = true
})
toast.hidden = false
out.detached = run(() => { toast.isConnected = false })
process.stdout.write(JSON.stringify(out))
"""


def test_a_fresh_toast_in_the_side_scroll_box_scrolls_only_that_box() -> None:
    """설비 마스터 오른쪽 칸 본문 칸(넘치면 스크롤하는 칸, 오른쪽 칸은 sticky) 안의 새 토스트 —
    바로 `scrollIntoView` 하면 Chrome 이 붙은 자리가 아니라 원래 흐름 자리로 셈해 바깥 페이지
    (stMain)까지 밀어 왼쪽 표가 튀었다(사본 앱 1500×950, 본문 칸 맨 아래에서 「이 호기 지우기」 —
    stMain 0 → 223px, 250 → 310px). 그림자 DOM 밖으로 건너 올라가 가장 가까운 넘치는 스크롤 칸을
    찾아 그 칸만 토스트 머리까지 올리고(`scrollBoxOf`·`boxScrollFor`), 그래도 머리 띠 아래로 가려
    있을 때만(쌓인 좁은 창·스크롤 칸이 없는 페이지 흐름) 전처럼 `scrollIntoView` 한다. 칸이 조금만
    내려가 칸 위 끝에 가려 있던 토스트(머리 띠 아래라 전에는 그대로 두던 것)도 보인다."""
    pure = _node({}, _NEW_RUNNER)
    assert pure["box"] == [0, 0, 248, 0, 500]

    out = _node({}, _TOAST_BOX_RUNNER, source=_fake_dom_source())

    start = [{"block": "start"}]
    assert out == {
        "bottom": {"box": 0, "page": None},
        "little": {"box": 0, "page": None},
        "visible": {"box": 0, "page": None},
        "stacked": {"box": 0, "page": start},
        "short": {"box": 0, "page": start},
        "page": {"box": 0, "page": start},
        "hidden": {"box": 1474, "page": None},
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


def test_redrawn_side_controls_keep_keyboard_focus_and_fresh_toasts_are_revealed() -> None:
    """칩·「양식 비우기」 는 칸을 다시 그려도 초점이 돌아온다(data-fk — 키보드로
    채우다 칸 처음으로 가지 않게). 상세 칩도 회차가 돌아와 다시 그려도 같다. 오른쪽 칸 새 토스트가
    화면 위로 나갔으면 칸 머리를 보인다(「호기 추가」 뒤 상세·가져오기 뒤 새 호기 칸)."""
    assert "chip.dataset.fk = 'n' + k + '=' + option" in JS
    assert "chip.dataset.fk = 'f' + k + '=' + value" in JS
    assert "reset.dataset.fk = 'reset'" in JS
    assert "if (fresh) revealToast(toast)" in JS
    assert "(first || Boolean(data.toast.undo))" in JS
    assert re.search(r"\.emg-toast\s*\{[^}]*scroll-margin-top:\s*80px", CSS)


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
    닿아 shift op 를 하나 더 보냈다 — 날짜가 두 번 밀리고 토스트 「되돌리기」 는 한 번만 되돌렸다.
    「넣기」·상세 「되살리기」 는 둘째 op 의 헛결과 토스트(「0칸 바뀜」·「0대를 되살렸습니다」)가 첫
    결과와 그 「되돌리기」 를 덮었다(2026-10-27 E2E). 단추 op 는 같은 op 가 아직 ack 되지 않았으면
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
        "buildSelection": ["{ op: 'set', ids: targets", "{ op: 'shift', ids: targets"],
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
    narrow = CSS.split("@media (max-width: 640px)", 1)[1].split("\n}\n", 1)[0]
    assert re.search(r"\.emg-check-row \.emg-check-head\s*\{\s*flex:\s*0 0 100%", narrow)
    assert re.search(r"\n\.emg-check-head\s*\{\s*flex:\s*0 0 116px", CSS)


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
  let toggle = open('공정으로 불러오기')
  await wait()
  results.process = { focus: focusLabel(), open: !panelOf(toggle).hidden }
  fire(document.activeElement, 'keydown', { key: 'Escape' })
  results.process.closed = panelOf(toggle).hidden
  results.process.back = document.activeElement === toggle
  // 조건 — 열자마자 Esc.
  toggle = open('조건으로 불러오기')
  results.conditions = { focus: focusLabel(), open: !panelOf(toggle).hidden }
  fire(document.activeElement, 'keydown', { key: 'Escape' })
  results.conditions.closed = panelOf(toggle).hidden
  results.conditions.back = document.activeElement === toggle
  // 조건 — 값을 고르면 패널을 다시 지어도 고른 칸에 초점이 남는다.
  toggle = open('조건으로 불러오기')
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
    """「조건으로 불러오기 ▾」 를 열자마자 누른 Esc 로도 닫힌다 — 「공정으로 불러오기 ▾」 처럼 열면
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


def test_a_loader_popover_closes_when_the_keyboard_leaves_it() -> None:
    """「조건으로 불러오기 ▾」 를 연 채 Tab 으로 패널 밖(「일정 확인 필요」 단추)에 가면 패널이
    열린 채 남아 초점 받은 오른쪽 호기 상세 칸을 덮었고, 그 칸의 Esc 로도 닫히지 않았다(2026-10-26
    E2E). 초점이 패널·여는 단추 밖으로 나가면 닫는다 — 패널 안 칸끼리 옮김과 다시 지으며 지운
    칸(받을 칸 없음)은 닫지 않는다."""
    runner = (
        _FAKE_DOM
        + _MOUNT_LOADER
        + """
mount(input.data)
const toggle = buttonOf('조건으로 불러오기')
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
const outside = buttonOf('일정 확인 필요')
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
  const outside = buttonOf('일정 확인 필요')
  const spots = [['조건으로 불러오기', '.emg-cond'], ['공정으로 불러오기', '.emg-pop-list']]
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
    assert result == {"조건으로 불러오기": expected, "공정으로 불러오기": expected}


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
  const spots = [['조건으로 불러오기', '.emg-cond'], ['공정으로 불러오기', '.emg-pop-list']]
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
    assert result == {"조건으로 불러오기": row, "공정으로 불러오기": row}
    assert re.search(r"\.emg-pop:focus\s*\{\s*outline:\s*none", CSS)


def test_closing_the_import_dialog_returns_focus_to_the_button_that_opened_it() -> None:
    """불러오기 줄 「엑셀·CSV로 한꺼번에」 로 연 팝업을 Esc·닫기로 닫으면 초점이 BODY 로 빠지고 다음
    Tab 이 사이드바 머리로 갔다(2026-10-26 E2E — Streamlit 이 그림자 DOM 안 여는 단추로 돌려주지
    못한다). 팝업이 닫힌 수(`dialogClosed`)가 바뀐 회차에 이 불러오기가 연 팝업이고 초점이 아무
    데도 없으면 여는 단추로 돌린다 — 다른 칸에 초점이 있거나 다른 길로 연 팝업이면 그대로 둔다."""
    runner = (
        _FAKE_DOM
        + _MOUNT_LOADER
        + """
const at = (closed) => Object.assign({}, input.data, { dialogClosed: closed })
const label = () => (document.activeElement ? document.activeElement.textContent : null)
mount(at(0))
let opener = buttonOf('엑셀·CSV로 한꺼번에')
opener.focus()
opener.click()
document.activeElement = null
mount(at(1))
results.returned = label()
results.marked = buttonOf('엑셀·CSV로 한꺼번에').dataset.fk
document.activeElement = null
mount(at(2))
results.notOpenedHere = label()
buttonOf('엑셀·CSV로 한꺼번에').click()
const elsewhere = new FakeNode('input')
elsewhere.focus()
mount(at(3))
results.busy = document.activeElement === elsewhere
process.stdout.write(JSON.stringify(results))
"""
    )
    result = _node({"data": _loader_payload()}, runner, source=_fake_dom_source())

    assert result == {
        "returned": "엑셀·CSV로 한꺼번에",
        "marked": "import-bar",
        "notOpenedHere": None,
        "busy": True,
    }


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
    """「조건으로 불러오기」 로 불러온 뒤나 불러오기 줄의 다른 단추를 누른 뒤에도 팝오버가 열린 채
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
let toggle = buttonOf('조건으로 불러오기')
toggle.click()
const inside = toggle.parentNode.children[1].querySelector('[data-fk="cond-val-0"]')
press(inside)
results.insidePress = isOpen(toggle)
const alerts = buttonOf('일정 확인 필요')
press(alerts)
results.otherButton = {
  open: isOpen(toggle),
  expanded: toggle.getAttribute('aria-expanded'),
  kept: host.contains(alerts),
}
// 공정 팝오버를 연 채 조건 여는 단추를 누르면 공정 쪽이 닫힌다.
const byProcess = buttonOf('공정으로 불러오기')
byProcess.click()
press(toggle)
toggle.click()
results.otherToggle = { process: isOpen(byProcess), conditions: isOpen(toggle) }
// 조건으로 불러오기 — 값을 고르고 「맞는 n대 불러오기」 를 누르면 바로 닫고 여는 단추로 초점.
const value = toggle.parentNode.children[1].querySelector('[data-fk="cond-val-0"]')
value.value = '0'
fire(value, 'change')
buttonOf('맞는 ').click()
results.conditionsLoad = {
  open: isOpen(toggle),
  focus: document.activeElement === toggle,
  trigger: triggers[triggers.length - 1],
}
// 공정으로 불러오기 — 공정 하나를 누르면 바로 닫는다.
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
