# Purpose: Space 「호기 정보」 창의 필터 판정·고른 호기 줄·강조 대상(편집기 JS)을 node 로 검사한다.

"""2026-11-03 사용자 요청 — 고른 호기의 칸을 도면 위 창으로, 거꾸로 칸 필터 → 맞는 호기 목록 → 도면
강조.

판정은 `editor.js` 의 `// <unit-sheet>` 구획이고(자연 정렬은 `// <module-tiling>` 의
`naturalCompare`) node 로 떼어 돌린다(node·bun 이 없으면 건너뛰고 CI 에서는 실패 —
`test_space_module_group._node`). 고른 호기 줄 차례는 파이썬 `space_layout.picked_unit_rows` 와 같은
입력으로 대조하고, 표 재료는 파이썬 `unit_sheet` 가 만든 것을 그대로 넣는다. 창 그리기·끌기·강조
칠하기의 둘레는 자산 글자로 붙잡고 실제 동작은 브라우저로 본다.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any

import pandas as pd
from test_space_layout_edit import _master
from test_space_module_group import _node

from capa_simulation.components import space_layout_editor
from capa_simulation.components.space_layout import FLOOR_TABLE_COLUMNS, picked_unit_rows
from capa_simulation.services.space_unit_sheet import unit_sheet

ASSETS = space_layout_editor._ASSETS
JS = (ASSETS / "editor.js").read_text(encoding="utf-8")
CSS = (ASSETS / "editor.css").read_text(encoding="utf-8")
HTML = (ASSETS / "editor.html").read_text(encoding="utf-8")
_SHEET = re.compile(r"// <unit-sheet>\n(?P<body>.*?)\n\s*// </unit-sheet>", re.S)
_TILING = re.compile(r"// <module-tiling>\n(?P<body>.*?)\n\s*// </module-tiling>", re.S)

_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const ids = (rows) => rows.map((row) => row.id)
const hits = (set) => (set === null ? null : [...set].sort())
process.stdout.write(JSON.stringify({
  matches: (input.matches || []).map((c) => ids(sheetMatch(c.rows, c.columns, c.filters, c.skip))),
  values: (input.values || []).map((c) => distinctValues(c.rows, c.index, c.type)),
  picked: (input.picked || []).map((c) => ids(pickedRows(c.rows, c.id))),
  many: (input.many || []).map((c) => ids(pickedRowsMany(c.rows, c.ids))),
  hits: (input.hits || []).map((c) => hits(sheetHits(c.rows, c.columns, c.filters))),
  active: (input.active || []).map((c) => sheetActive(c.columns, c.filters)),
  ranges: (input.ranges || []).map((c) => inRange(c.value, c.rule, c.type)),
  keys: (input.keys || []).map((value) => [sheetKey(value), sheetText(value)]),
  clamps: (input.clamps || []).map((c) => clampSheet(c.win, c.def, c.w, c.h, 360, 200, 34)),
  wins: (input.wins || []).map((raw) => storedSheetWin(raw)),
  states: (input.states || []).map((raw) => storedSheetState(raw)),
  clears: (input.clears || []).map((c) => clearOfSheet(c.stage, c.win, c.rect)),
  csvs: (input.csvs || []).map((c) => sheetCsv(c.columns, c.rows)),
}))
"""


def _run(payload: dict[str, Any]) -> dict[str, Any]:
    sheet = _SHEET.search(JS)
    tiling = _TILING.search(JS)
    assert sheet, "editor.js 에 // <unit-sheet> 구획이 없습니다"
    assert tiling, "editor.js 에 // <module-tiling> 구획이 없습니다"
    return _node(tiling.group("body") + "\n" + sheet.group("body") + _RUNNER, payload)


COLUMNS = [
    {"name": "공정소분류", "type": "text"},
    {"name": "설비명", "type": "text"},
    {"name": "투자Capa", "type": "number"},
    {"name": "반입일정", "type": "date"},
    {"name": "도면", "type": "text"},
]


def _row(unit: str, process: Any, capa: Any, arrival: Any, place: str = "배치") -> dict[str, Any]:
    return {"id": unit, "group": None, "cells": [process, unit, capa, arrival, place]}


ROWS = [
    _row("EQ-01", "DAF Attach", 120.0, "2026-10-01"),
    _row("EQ-02", "daf attach ", 80.0, "2026-12-15"),
    _row("EQ-03", "Saw", None, None, "미배치"),
    _row("EQ-04", None, "TBD", "2027-02-01"),
    _row("EQ-05", "Saw", 200.0, "2026-11-30", "레이아웃 제외"),
]


def test_columns_and_and_values_or_with_blanks_case_and_ranges() -> None:
    """칸 안은 OR(고른 값 가운데 하나), 칸끼리는 AND. 글은 대소문자·앞뒤 공백을 가리지 않고, 빈 값은
    열쇠 ''(「(빈칸)」). 숫자·날짜 범위는 양 끝 포함이고 빈 끝은 열림 — 범위가 걸리면 빈 값·수가
    아닌 글은 맞지 않는다. `skip` 칸의 필터는 보지 않는다(그 칸 값 목록을 셀 때)."""
    cases: list[dict[str, Any]] = [
        {"filters": {}},
        {"filters": {"공정소분류": {"values": ["daf attach"]}}},
        {"filters": {"공정소분류": {"values": ["daf attach", ""]}}},
        {"filters": {"공정소분류": {"values": ["saw"]}, "도면": {"values": ["배치"]}}},
        {"filters": {"투자Capa": {"from": "100"}}},
        {"filters": {"투자Capa": {"from": "80", "to": "120"}}},
        {"filters": {"반입일정": {"from": "2026-11-01", "to": "2026-12-31"}}},
        {"filters": {"반입일정": {"to": "2026-11-30"}}},
        {"filters": {"투자Capa": {"values": ["tbd"]}}},
        {"filters": {"공정소분류": {"values": []}}},
        {"filters": {"공정소분류": {"values": ["saw"]}, "반입일정": {"from": "2026-12-01"}}},
        {"filters": {"공정소분류": {"values": ["saw"]}}, "skip": "공정소분류"},
        {"filters": {"없는 칸": {"values": ["x"]}}},
    ]
    result = _run(
        {"matches": [{"rows": ROWS, "columns": COLUMNS, "skip": None, **case} for case in cases]}
    )
    assert result["matches"] == [
        ["EQ-01", "EQ-02", "EQ-03", "EQ-04", "EQ-05"],
        ["EQ-01", "EQ-02"],
        ["EQ-01", "EQ-02", "EQ-04"],
        [],
        ["EQ-01", "EQ-05"],
        ["EQ-01", "EQ-02"],
        ["EQ-02", "EQ-05"],
        ["EQ-01", "EQ-05"],
        ["EQ-04"],
        [],
        [],
        ["EQ-01", "EQ-02", "EQ-03", "EQ-04", "EQ-05"],
        ["EQ-01", "EQ-02", "EQ-03", "EQ-04", "EQ-05"],
    ]


def test_saw_on_the_drawing_matches_only_the_placed_one() -> None:
    """「Saw」 이면서 도면 「배치」 — 둘 다 맞는 줄은 없다(EQ-03 은 미배치, EQ-05 는 레이아웃
    제외)."""
    rows = [*ROWS, _row("EQ-06", "SAW", 10.0, "2026-09-01")]
    result = _run(
        {
            "matches": [
                {
                    "rows": rows,
                    "columns": COLUMNS,
                    "filters": {"공정소분류": {"values": ["saw"]}, "도면": {"values": ["배치"]}},
                    "skip": None,
                }
            ]
        }
    )
    assert result["matches"] == [["EQ-06"]]


def test_value_lists_group_case_count_and_put_blanks_last() -> None:
    """값 목록 — 대소문자만 다른 글은 한 항목(처음 만난 꼴), 개수, 빈 값은 「(빈칸)」 맨 뒤. 숫자
    칸은 수 차례이고 수가 아닌 글은 수 뒤다."""
    result = _run(
        {
            "values": [
                {"rows": ROWS, "index": 0, "type": "text"},
                {"rows": ROWS, "index": 2, "type": "number"},
                {"rows": ROWS, "index": 3, "type": "date"},
            ]
        }
    )
    process, capa, arrival = result["values"]
    assert process == [
        {"key": "daf attach", "text": "DAF Attach", "count": 2},
        {"key": "saw", "text": "Saw", "count": 2},
        {"key": "", "text": "(빈칸)", "count": 1},
    ]
    assert [value["text"] for value in capa] == ["80", "120", "200", "TBD", "(빈칸)"]
    assert [value["key"] for value in arrival] == [
        "2026-10-01",
        "2026-11-30",
        "2026-12-15",
        "2027-02-01",
        "",
    ]


def test_ranges_keys_and_shown_text() -> None:
    result = _run(
        {
            "ranges": [
                {"value": 5.0, "rule": {}, "type": "number"},
                {"value": None, "rule": {"from": "1"}, "type": "number"},
                {"value": "TBD", "rule": {"to": "9"}, "type": "number"},
                {"value": 9.0, "rule": {"to": "9"}, "type": "number"},
                {"value": 9.0, "rule": {"from": "x"}, "type": "number"},
                {"value": "2026-01-01", "rule": {"from": "2026-01-01"}, "type": "date"},
                {"value": "언젠가", "rule": {"from": "2026-01-01"}, "type": "date"},
                {"value": None, "rule": {"from": " ", "to": ""}, "type": "date"},
            ],
            "keys": [None, "", "  Ab ", 3.0, 2.346, "2026-01-02"],
        }
    )
    assert result["ranges"] == [True, False, False, True, False, True, False, True]
    assert result["keys"] == [
        ["", ""],
        ["", ""],
        ["ab", "Ab"],
        ["3", "3"],
        ["2.346", "2.35"],
        ["2026-01-02", "2026-01-02"],
    ]


def test_picked_rows_follow_the_python_rule_for_modules_and_names() -> None:
    """고른 호기의 줄 — 파이썬 `picked_unit_rows` 와 같은 입력·같은 차례(모듈이면 같은 Main 설비
    줄 전부, 누른 것이 첫 줄, 나머지 자연 정렬 · 설비명 앞뒤 공백을 걷는다 · 없는 설비는 빈 목록).
    표 재료는 파이썬 `unit_sheet` 가 만든 그대로다."""
    module = {"Main 설비": "MOD-1"}
    rows = _master(
        {**module, "설비명": "MOD-1C"},
        {**module, "설비명": "MOD-10"},
        {**module, "설비명": "MOD-1A"},
        {**module, "설비명": "MOD-1D", "X좌표": None},
        {**module, "설비명": "MOD-2"},
        {**module, "설비명": "MOD-1B"},
        {"설비명": " LONE "},
        {"Main 설비": " OTHER ", "설비명": "OT-1"},
        {"Main 설비": "OTHER", "설비명": "OT-2"},
    )
    sheet = unit_sheet(rows, columns=FLOOR_TABLE_COLUMNS, place_of={})
    asked = ["MOD-1B", "MOD-10", "EQ-01", "LONE", "OT-2", "GONE"]
    result = _run({"picked": [{"rows": sheet["rows"], "id": unit} for unit in asked]})
    expected = [
        [str(name).strip() for name in picked_unit_rows(rows, unit)["설비명"]] for unit in asked
    ]
    assert result["picked"] == expected
    assert expected[0] == [
        "MOD-1B",
        "MOD-1A",
        "MOD-1C",
        "MOD-1D",
        "MOD-2",
        "MOD-10",
    ]
    assert expected[-1] == []


def test_many_picked_units_join_in_order_without_repeats() -> None:
    rows = [
        {"id": "A-1", "group": "A", "cells": []},
        {"id": "A-2", "group": "A", "cells": []},
        {"id": "B", "group": None, "cells": []},
        {"id": "C", "group": None, "cells": []},
    ]
    result = _run(
        {
            "many": [
                {"rows": rows, "ids": ["C", "A-2", "A-1", "B"]},
                {"rows": rows, "ids": []},
                {"rows": rows, "ids": ["GONE", "B"]},
            ]
        }
    )
    assert result["many"] == [["C", "A-2", "A-1", "B"], [], ["B"]]


def test_the_drawing_highlights_only_while_a_filter_is_on() -> None:
    """강조 대상 — 필터가 하나도 없으면 null(강조 없음), 있으면 맞는 줄의 id(빈 묶음이면 모두
    흐림). 걸린 칸은 이 표에 있는 칸만 센다."""
    result = _run(
        {
            "hits": [
                {"rows": ROWS, "columns": COLUMNS, "filters": {}},
                {"rows": ROWS, "columns": COLUMNS, "filters": {"공정소분류": {"values": ["saw"]}}},
                {"rows": ROWS, "columns": COLUMNS, "filters": {"공정소분류": {"values": []}}},
                {"rows": ROWS, "columns": COLUMNS, "filters": {"없는 칸": {"values": []}}},
            ],
            "active": [
                {"columns": COLUMNS, "filters": {"도면": {"values": []}, "투자Capa": {"to": "9"}}},
                {"columns": COLUMNS, "filters": {"반입일정": {"from": ""}, "없는 칸": {"to": "1"}}},
            ],
        }
    )
    assert result["hits"] == [None, ["EQ-03", "EQ-05"], [], None]
    assert result["active"] == [["투자Capa", "도면"], []]


def test_the_window_stays_inside_the_editor_body() -> None:
    """창 자리·크기 — 최소 360×200(몸이 더 작으면 몸), 몸보다 크지 않고, 창 전체가 몸 안이다(접힌
    창은 제목 줄 높이만). 값이 없으면 처음 자리(무대 왼쪽 아래)."""
    default = {"x": 228, "y": 400, "w": 720, "h": 320}
    result = _run(
        {
            "clamps": [
                {"win": {}, "def": default, "w": 1200, "h": 728},
                {
                    "win": {"x": 900, "y": 600, "w": 500, "h": 300},
                    "def": default,
                    "w": 1200,
                    "h": 728,
                },
                {
                    "win": {"x": -40, "y": -9, "w": 100, "h": 50},
                    "def": default,
                    "w": 1200,
                    "h": 728,
                },
                {"win": {"x": 10, "y": 10, "w": 900, "h": 900}, "def": default, "w": 600, "h": 300},
                {"win": {"x": 0, "y": 700, "min": True}, "def": default, "w": 1200, "h": 728},
                {"win": {}, "def": default, "w": 300, "h": 150},
            ]
        }
    )
    assert result["clamps"] == [
        {"x": 228, "y": 400, "w": 720, "h": 320},
        {"x": 700, "y": 428, "w": 500, "h": 300},
        {"x": 0, "y": 0, "w": 360, "h": 200},
        {"x": 0, "y": 0, "w": 600, "h": 300},
        {"x": 0, "y": 694, "w": 720, "h": 320},
        {"x": 0, "y": 0, "w": 300, "h": 150},
    ]


def test_stored_window_and_state_are_read_defensively() -> None:
    """저장값 — 꼴이 다르면 기본(창 자리는 None → 처음 자리, 상태는 닫힘·「고른 호기」·강조 켬·필터
    없음). 필터는 칸마다 글 열쇠 목록·범위 글만 남기고 걸린 것이 없는 칸은 뺀다."""
    result = _run(
        {
            "wins": ["", "[1]", "nope", '{"x": 10, "y": "a", "w": 400, "h": null, "min": true}'],
            "states": [
                None,
                '{"open": true, "tab": "filter", "hl": false, "filters": {"공정소분류": '
                '{"values": ["saw", 3, ""]}, "반입일정": {"from": " 2026-01-01 ", "to": 5}, '
                '"빈": {"from": "  "}, "틀림": 7}}',
                '{"tab": "other", "filters": []}',
            ],
        }
    )
    empty = {"x": None, "y": None, "w": None, "h": None, "min": False}
    assert result["wins"] == [
        empty,
        empty,
        empty,
        {"x": 10, "y": None, "w": 400, "h": None, "min": True},
    ]
    assert result["states"] == [
        {"open": False, "tab": "picked", "hl": True, "filters": {}},
        {
            "open": True,
            "tab": "filter",
            "hl": False,
            "filters": {
                "공정소분류": {"values": ["saw", ""]},
                "반입일정": {"from": "2026-01-01"},
            },
        },
        {"open": False, "tab": "picked", "hl": True, "filters": {}},
    ]


# ---------------------------------------------------------------- 둘레(자산 글자)


def test_units_carry_a_filter_ring_and_the_dim_multiplies_with_the_shortening_dim() -> None:
    """호기마다 테 부품(`.sle-filter-ring`, 보기·편집 모두)을 만들고 선택 후광보다 바깥에 둔다.
    강조는 class 둘이고 흐림은 필요 단축 흐림과 곱해진다. 색은 팔레트 변수다."""
    build = JS[
        JS.index("  function buildGroup(item) {") : JS.index("  function paintUnit(group, item) {")
    ]
    assert "el('rect', { class: 'sle-filter-ring', rx: 0.8 })" in build
    assert build.index("group.append(el('rect', { class: 'sle-filter-ring'") > build.index(
        "} else {"
    )
    assert "paintFilter(group, item.id)" in build
    assert "const FILTER_GAP_PX = 5" in JS and "const HALO_GAP_PX = 3" in JS
    assert "const gap = FILTER_GAP_PX * upp" in JS
    assert ".sle-unit.is-filter-hit .sle-filter-ring {" in CSS
    assert "stroke: var(--sle-filter-ring); stroke-width: 2.5;" in CSS
    assert ".sle-unit.is-filter-out { opacity: var(--sle-filter-dim-opacity); }" in CSS
    assert (
        ".sle.is-view .sle-unit.is-dim.is-filter-out { opacity: calc(var(--sle-short-dim-opacity) "
        "* var(--sle-filter-dim-opacity)); }"
    ) in CSS
    palette = space_layout_editor._palette()
    assert {"filter-ring", "filter-dim-opacity"} <= set(palette)


def test_the_window_lives_in_the_editor_and_never_reaches_python() -> None:
    """창은 편집기 몸 안 겹친 창이고(FAB 에는 없음 — `sle-floor-only`), 자리·크기·접힘은
    localStorage, 열림·탭·필터·강조는 sessionStorage 다(읽기·쓰기 모두 try). 필터를 고쳐도
    `setStateValue`·`setTriggerValue` 를 부르지 않는다. 창 안 키는 도면 단축키로 새지 않는다."""
    body = HTML[HTML.index('<div class="sle-body">') : HTML.index('<div class="sle-resize"')]
    assert '<section class="sle-sheet sle-floor-only" id="sle-sheet" role="region"' in body
    assert 'aria-label="호기 정보" hidden>' in body
    toolbar = HTML[HTML.index('<div class="sle-toolbar">') : HTML.index('<div class="sle-body">')]
    assert toolbar.index("sle-sheet-toggle sle-floor-only") < toolbar.index('class="sle-lock"')
    assert "const SHEET_WIN_KEY = 'capa.space.sheet.win.v1'" in JS
    assert "const SHEET_STATE_KEY = 'capa.space.sheet.state.v1'" in JS
    state = JS[JS.index("  function sheetLoad() {") : JS.index("  adoptSheet()\n  renderSheet()")]
    assert "window.sessionStorage.getItem(SHEET_STATE_KEY)" in state
    assert "window.localStorage.getItem(SHEET_WIN_KEY)" in state
    assert state.count("try {") >= 4
    assert "setStateValue" not in state and "setTriggerValue" not in state
    assert "event.stopPropagation()" in state[state.index("sheetBox.onkeydown") :]
    # 상태 줄을 고칠 때마다 창도 맞춘다(보기·편집 둘 다).
    status = JS[JS.index("  function updateStatus() {") : JS.index("  // 이름 칸(호기 `이름`")]
    assert status.count("renderSheet()") == 2
    # 호기를 두 번 누르면 「고른 호기」 를 연다 — 빈 곳은 보기에서 확대/전체 보기 그대로.
    dbl = JS[JS.index("  svg.ondblclick = (event) => {") : JS.index("  host.onkeyup = ")]
    assert dbl.index("openSheet('picked')") < dbl.index("if (!VIEW) return")
    assert "zoomAt(2.5, toUser(event))" in dbl


def test_the_editor_place_column_follows_the_unapplied_edit() -> None:
    """배치 편집의 「도면」 칸은 브라우저가 쥔 편집이다 — 트레이로 뺀 호기는 미배치, 다른 층으로
    보낸 호기는 「→ 그 층」. 보기는 받은 그대로다."""
    rows = JS[JS.index("  function sheetRows() {") : JS.index("  function pickedUnitIds() {")]
    assert "if (VIEW || sheet.placeIdx < 0) return sheet.rows" in rows
    assert "item.moveTo ? `→ ${item.moveTo}` : onCanvas(item) ? '배치' : '미배치'" in rows


def test_python_sheet_cells_line_up_with_the_js_columns() -> None:
    """파이썬 표 재료는 칸 수와 줄의 값 수가 같고 「도면」 이 끝 칸이다 — JS `placeIdx` 가 이름으로
    찾는다."""
    rows = _master({"설비명": "EQ-09", "레이아웃표시": "N"})
    sheet = unit_sheet(pd.concat([rows]), columns=FLOOR_TABLE_COLUMNS, place_of={"EQ-01": "배치"})
    assert all(len(row["cells"]) == len(sheet["columns"]) for row in sheet["rows"])
    assert sheet["columns"][-1] == {"name": "도면", "type": "text"}
    assert "SHEET_PLACE = '도면'" in JS


def test_a_unit_under_the_window_moves_to_the_widest_free_band() -> None:
    """목록 줄로 간 호기가 창 밑에 들면 무대에서 창이 덮지 않은 가장 넓은 띠의 가운데로 민다 — 창이
    무대 아래쪽이면 위 띠, 오른쪽 위면 왼쪽 띠. 창이 무대와 겹치지 않거나 호기가 창 밖이면
    그대로."""

    def box(left: float, top: float, right: float, bottom: float) -> dict[str, float]:
        return {"left": left, "top": top, "right": right, "bottom": bottom}

    stage = box(0, 0, 1000, 600)
    result = _run(
        {
            "clears": [
                {"stage": stage, "win": box(8, 280, 728, 592), "rect": box(480, 280, 520, 320)},
                {"stage": stage, "win": box(600, 0, 1000, 600), "rect": box(700, 100, 740, 140)},
                {"stage": stage, "win": box(8, 280, 728, 592), "rect": box(480, 100, 520, 140)},
                {"stage": stage, "win": box(1100, 0, 1400, 600), "rect": box(480, 280, 520, 320)},
            ]
        }
    )
    assert result["clears"] == [
        {"dx": 0, "dy": 160},
        {"dx": 420, "dy": -180},
        None,
        None,
    ]


def test_the_shown_rows_csv_quotes_like_python_and_keeps_the_window_values() -> None:
    """「CSV」 의 「보이는 줄」(`sheetCsv` — 2026-11-04 Space 결정 보드 답) — 창의 칸 이름이 머리,
    값은 창이 받은 그대로(날짜 글 · 수 글 · 빈 값은 빈칸)이고 쉼표 · 큰따옴표 · 줄바꿈이 든 칸만
    큰따옴표로 싼다(파이썬 `csv` QUOTE_MINIMAL · LF 와 같은 글). 엑셀이 다시 읽으면 같은 칸이다."""
    rows = [
        *ROWS,
        _row("EQ-06", 'Saw, "B"', 12.5, "2026-01-02", "줄\n바꿈"),
    ]
    (got,) = _run({"csvs": [{"columns": COLUMNS, "rows": rows}]})["csvs"]
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow([column["name"] for column in COLUMNS])
    for row in rows:
        writer.writerow(
            [
                "" if cell is None else (f"{cell:g}" if isinstance(cell, float) else cell)
                for cell in row["cells"]
            ]
        )
    assert got == buffer.getvalue()
    back = list(csv.reader(io.StringIO(got)))
    assert back[-1] == ['Saw, "B"', "EQ-06", "12.5", "2026-01-02", "줄\n바꿈"]
    assert back[4][0] == "" and back[3][2] == ""


def test_the_csv_button_lives_in_the_window_and_downloads_in_the_browser() -> None:
    """「CSV」 는 창 제목 줄 단추와 두 줄 펼침(도면에 선 호기 · 보이는 줄)이다 — 옛 도면 아래
    내려받기 줄을 걷었다(같은 일을 두 자리에 두지 않는다). 도면에 선 호기는 파이썬이 지은 글(data
    `sheet.csv` — 옛 내려받기와 같은 줄 · 칸이라 창의 미배치 · 레이아웃 제외 줄은 없다 — 재검 c-5
    로 이름을 맞춤)을, 보이는 줄은 지금 탭의 줄(`S.sheetShown`)을 창의 칸으로 지어 BOM + UTF-8 Blob
    으로 내려받는다. 파이썬으로 아무것도 보내지 않는다. 접힌 창에서 누르면 창을 편다. Esc 는 펼침을
    먼저 닫는다. 제목 줄 빈 칸은 도구 줄 빈 칸(보기에서 숨음)과 따로라 보기에서도 CSV · 접기 ·
    닫기가 오른쪽 끝이고, 펼침은 단추 오른쪽 끝에 맞춰 선다(재검 b-2 — 보기에서 펼침이 단추와 300px
    떨어졌다)."""
    head = HTML[
        HTML.index('<div class="sle-sheet-head"') : HTML.index('<div class="sle-sheet-main">')
    ]
    assert head.index('class="sle-sheet-gap"') < head.index('class="sle-sheet-csv"')
    assert head.index('class="sle-sheet-csv"') < head.index('class="sle-sheet-min"')
    assert 'class="sle-spacer"' not in head
    assert ".sle-sheet-gap { flex: 1 1 auto; min-width: 0; }" in CSS
    assert 'aria-haspopup="menu"' in head and 'aria-controls="sle-sheet-csvmenu"' in head
    menu = HTML[HTML.index('class="sle-sheet-csvmenu"') : HTML.index('<div class="sle-sheet-menu"')]
    assert 'data-csv="all"' in menu and 'data-csv="shown"' in menu and 'role="menu"' in menu
    assert ">도면에 선 호기 · 모든 칸</button>" in menu and "층 전체" not in menu
    adopt = JS[JS.index("  function adoptSheet() {") : JS.index("  function sheetRows() {")]
    assert "typeof SHEET.csv.text === 'string' && typeof SHEET.csv.file === 'string'" in adopt
    render = JS[JS.index("  function renderSheet() {") : JS.index("  function drawSheetTable(")]
    assert "S.sheetShown = shown" in render
    # 잘린 줄 수는 값 「n줄 더 있음」 이고 모든 줄을 받는 자리는 풍선이다 — 빈 결과 · 잘림 줄에
    # 하는 법 꼬리를 달지 않는다(설계 규칙 UI-TXT-03 · UI-TXT-04).
    assert "`${S.sheet.cut}줄 더 있음`" in render and "아래 층 CSV" not in JS
    assert "「CSV」 → 「도면에 선 호기 · 모든 칸」" in render
    for tail in ("로 보세요", "필터를 바꾸세요", "호기를 누르세요"):
        assert tail not in render, tail
    assert "'맞는 호기가 없습니다.'" in render and "'고른 호기가 없습니다.'" in render
    csv_part = JS[JS.index("  function closeCsvMenu(") : JS.index("  if (sheetBox) {")]
    assert (
        "sheetCsvMenu.style.right = `${Math.max(0, Math.round(inner - anchor.right))}px`"
        in csv_part
    )
    assert "new Blob([`\\ufeff${text}`], { type: 'text/csv;charset=utf-8' })" in csv_part
    assert "saveCsv(sheet.csv.text, sheet.csv.file)" in csv_part
    assert "saveCsv(sheetCsv(sheet.columns, S.sheetShown), `${base}_보이는줄.csv`)" in csv_part
    assert "if (S.sheetWin.min) {" in csv_part
    assert "setStateValue" not in csv_part and "setTriggerValue" not in csv_part
    keys = JS[
        JS.index("    sheetBox.onkeydown = (event) => {") : JS.index("    // 펼침 밖을 누르면")
    ]
    assert keys.index("if (!sheetCsvMenu.hidden) closeCsvMenu(true)") < keys.index(
        "else if (S.sheetMenu) closeMenu(true)"
    )
    assert ".sle-sheet.is-min .sle-sheet-csvmenu { display: none; }" in CSS.replace(
        ".sle-sheet.is-min .sle-sheet-menu,\n", ""
    )


def test_a_list_row_zooms_to_three_hundred_percent_and_the_pick_view_stays_at_most() -> None:
    """목록 줄 누르기(`goToUnit`)는 그 호기로 옮기며 300% 까지만 확대한다(2026-11-04 Space 결정
    보드 답 — 800% 는 둘레 호기가 거의 안 보였다). 「고른 곳 보기」 는 그대로 최대(800%)다."""
    assert "  const MAX_ZOOM = 8\n" in JS and "  const LIST_ROW_ZOOM = 3\n" in JS
    fit = JS[JS.index("  function zoomToBox(") : JS.index("  function panBy(")]
    assert "function zoomToBox(box, cap = MAX_ZOOM) {" in fit
    assert "1, Math.min(cap, MAX_ZOOM))" in fit
    go = JS[
        JS.index("  function goToUnit(id) {") : JS.index("    if (item && isUnit(item) && !VIEW")
    ]
    assert "zoomToBox(bbox(VIEW ? [item] : expanded([item])), LIST_ROW_ZOOM)" in go
    assert JS.count("zoomToBox(") == 3
    assert "if (list.length) zoomToBox(bbox(list))\n" in JS
