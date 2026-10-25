# Purpose: 설비 마스터 표 자산의 출납·트리거 이름·색 변수·데이터 글·키 계약을 글자·node 로 본다.

"""AppTest 는 표 JS 를 돌리지 못한다. 자산 글자로 드러나는 약속(개편 명세 11장 「자산 글」)은 글자로
붙잡고, DOM 을 모르는 순수 구획(`// <grid-…>`)은 node(없으면 bun)로 떼어 돌린다 — 없으면 건너뛰고 CI
에서는 실패다. 화면 동작은 사본 앱 브라우저로 본다."""

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
    있다."""
    assert set(re.findall(r"setState\('([a-z]+)'", JS)) == set(emg.STATE_NAMES) == {"outbox"}
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
    for name in ("onBodyKey", "searchBox", "detailField", "popover"):
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


# ---------------------------------------------------------------- JS 순수 구획(node)

_SECTIONS = (
    "grid-paste",
    "grid-nav",
    "grid-outbox",
    "grid-match",
    "grid-plan",
    "grid-sort",
    "grid-codes",
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


def _node(payload: dict[str, Any]) -> dict[str, Any]:
    runtime = _runtime()
    if runtime is None:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            pytest.fail("CI 러너에 node 가 없다 — 설비 마스터 표 JS 대조를 건너뛸 수 없다")
        pytest.skip("node·bun 이 없다 — CI 에서 돈다")
    completed = subprocess.run(
        [runtime, "-e", _sections() + _RUNNER],
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
        }
    )
    first, single, too_many = result["paste"]
    assert first["ids"] == ["r1", "r2"] and first["cols"] == ["A", "B"]
    assert first["rows"] == [["a", None], ["d", "e"]]
    assert first["cut"] == 1, "표 끝을 넘은 줄"
    assert first["skipped"] == 2, "칸 끝을 넘은 c 하나 + 잠긴 r1|B"
    assert first["count"] == 3 and not first["tooMany"]
    assert single is None, "한 칸이면 보통 붙여넣기"
    assert too_many["tooMany"] is True
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
