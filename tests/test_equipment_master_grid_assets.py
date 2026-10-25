# Purpose: 설비 마스터 표 자산의 출납·트리거·색 변수·데이터 글·키·팝오버 계약을 글자·node 로 본다.

"""AppTest 는 표 JS 를 돌리지 못한다. 자산 글자로 드러나는 약속(개편 명세 11장 「자산 글」)은 글자로
붙잡고, DOM 을 모르는 순수 구획(`// <grid-…>`)은 node(없으면 bun)로 떼어 돌린다 — 없으면 건너뛰고 CI
에서는 실패다. 불러오기 팝오버의 초점·Esc 는 파일 전체를 작은 가짜 DOM 에 마운트해 본다. 그 밖의
화면 동작은 사본 앱 브라우저로 본다."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from capa_simulation.components import equipment_master_grid as emg
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


def _runtime() -> str | None:
    return shutil.which("node") or shutil.which("bun")


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
    runtime = _runtime()
    if runtime is None:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            pytest.fail("CI 러너에 node 가 없다 — 설비 마스터 표 JS 대조를 건너뛸 수 없다")
        pytest.skip("node·bun 이 없다 — CI 에서 돈다")
    completed = subprocess.run(
        [runtime, "-e", (_sections() if source is None else source) + runner],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result: dict[str, Any] = json.loads(completed.stdout)
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


_NEW_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const local = { seq: 4, values: ['a', 'b'], propagate: true }
const results = {
  first: adoptDraft(null, { seq: 0, values: ['', 'N'], propagate: true }),
  keep: adoptDraft(local, { seq: 4, values: ['x', 'y'], propagate: false }) === local,
  older: adoptDraft(local, { seq: 3, values: ['x', 'y'], propagate: false }) === local,
  newer: adoptDraft(local, { seq: 6, values: ['c', 'd'], propagate: false }),
  bump: [bumpDraft(local, 2).seq, bumpDraft(local, 9).seq],
  tier: [
    tierDone(true, '', true),
    tierDone(false, 'x', true),
    tierDone(false, 'x', false),
    tierDone(true, ' ', false),
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
}
process.stdout.write(JSON.stringify(results))
"""


def test_the_new_unit_draft_section_adopts_newer_drafts_and_gates_the_add_button() -> None:
    """「새 호기」 초안(`// <grid-new>`) — 파이썬 초안은 번호가 클 때만 받고(가져오기·「호기
    추가」 뒤), 확정마다 번호를 올리며, 체크 상자 칸은 판정 전이면 칸이 찼는지만 보고, 「호기 추가」
    는 필수 칸이 찼고 지금 초안의 판정이 막지 않을 때 켠다(판정 전이면 켜 두고 파이썬이 다시
    본다)."""
    result = _node({}, _NEW_RUNNER)

    assert result["first"] == {"seq": 0, "values": ["", "N"], "propagate": True}
    assert result["keep"] is True and result["older"] is True
    assert result["newer"] == {"seq": 6, "values": ["c", "d"], "propagate": False}
    assert result["bump"] == [5, 10]
    assert result["tier"] == [True, False, True, False]
    assert result["add"] == [True, False, False, True, False]


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


def test_redrawn_side_controls_keep_keyboard_focus_and_fresh_toasts_are_revealed() -> None:
    """칩·함께 넣기 체크·「양식 비우기」 는 칸을 다시 그려도 초점이 돌아온다(data-fk — 키보드로
    채우다 칸 처음으로 가지 않게). 상세 칩도 회차가 돌아와 다시 그려도 같다. 오른쪽 칸 새 토스트가
    화면 위로 나갔으면 칸 머리를 보인다(「호기 추가」 뒤 상세·가져오기 뒤 새 호기 칸)."""
    assert "chip.dataset.fk = 'n' + k + '=' + option" in JS
    assert "chip.dataset.fk = 'f' + k + '=' + value" in JS
    assert "box.dataset.fk = 'propagate'" in JS
    assert "reset.dataset.fk = 'reset'" in JS
    assert "if (fresh) revealToast(toast)" in JS
    assert "(first || Boolean(data.toast.undo))" in JS
    assert re.search(r"\.emg-toast\s*\{[^}]*scroll-margin-top:\s*80px", CSS)


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
