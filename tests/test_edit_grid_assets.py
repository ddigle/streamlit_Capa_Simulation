# Purpose: 범용 편집 그리드 자산의 글 약속(출납·색·글 넣기·조립·예산)과 CORE 순수 구획을 본다.

"""AppTest 는 그리드 JS 를 돌리지 못한다. 자산 글자로 드러나는 약속(편집 표 횡전개 명세 13-2)은
글자로 붙잡고, DOM 을 모르는 순수 구획(`// <eg-…>`)은 node 로 떼어 돌린다
(`tests/edit_grid_node.py`). 값 다듬기·표시 형식·코드 풀기는 Python 이 지은 같은 사례를 JS 가 같은
답으로 내는지 본다(쌍둥이 시험).
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from edit_grid_node import RUNNER_HEAD, asset, check_module, run_node, section, sections

from capa_simulation.components import edit_grid
from capa_simulation.services import edit_grid as eg
from capa_simulation.services import edit_grid_payload as payload

PURE = asset("eg_pure.js")
CORE = asset("eg_core.js")
FEED = asset("feed.js")
JS_FILES = {name: asset(name) for name in edit_grid.JS_PARTS}
CSS_FILES = {name: asset(name) for name in edit_grid.CSS_PARTS}
REGISTERED_JS = edit_grid.registered_js()
REGISTERED_CSS = edit_grid.registered_css()
SOURCE = Path(edit_grid.__file__).read_text(encoding="utf-8")
CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "edit_grid_cases.json").read_text(encoding="utf-8")
)
CORE_SECTIONS = (
    "eg-codes",
    "eg-format",
    "eg-outbox",
    "eg-nav",
    "eg-view",
    "eg-layout",
    "eg-changes",
)


# ------------------------------------------------------------------ 자산 글


def test_the_parts_are_the_files_in_the_folder() -> None:
    """등록 차례 상수와 폴더의 파일이 같다 — 새 기능 파일을 만들면 차례에도 넣는다."""
    folder = edit_grid._ASSETS
    scripts = {path.name for path in folder.glob("*.js")} - {edit_grid.FEED_JS}
    assert scripts == set(edit_grid.JS_PARTS)
    assert {path.name for path in folder.glob("*.css")} == set(edit_grid.CSS_PARTS)
    assert edit_grid.JS_PARTS[0] == "eg_pure.js" and edit_grid.JS_PARTS[-1] == "eg_core.js"


def test_the_registered_script_drops_comment_lines_and_keeps_the_rest() -> None:
    assert not any(re.match(r"^\s*//", line) for line in REGISTERED_JS.splitlines())
    for name, text in JS_FILES.items():
        for line in text.splitlines():
            if line.strip() and not re.match(r"^\s*//", line):
                assert line in REGISTERED_JS, (name, line)
    assert REGISTERED_JS.count("export default function") == 1


def test_the_registered_script_parses_as_a_module() -> None:
    completed = check_module(REGISTERED_JS)
    assert completed.returncode == 0, completed.stderr
    completed = check_module(edit_grid.feed_js())
    assert completed.returncode == 0, completed.stderr


def test_top_level_names_do_not_collide_between_files() -> None:
    """파일을 이어 붙여 한 모듈로 등록한다 — 최상위 이름이 겹치면 문법 오류이거나 앞 것을 덮는다."""
    seen: dict[str, str] = {}
    pattern = r"^(?:function|const|let|class)\s+([A-Za-z_$][\w$]*)"
    for name, text in JS_FILES.items():
        for found in re.findall(pattern, text, re.M):
            assert found not in seen, f"{found}: {seen.get(found)} 와 {name}"
            seen[found] = name


def test_every_feature_file_registers_its_hook_and_carries_its_sections() -> None:
    expected = {
        "eg_select.js": ("select", ("eg-rect", "eg-clip")),
        "eg_fill.js": ("fill", ("eg-paste", "eg-fill")),
        "eg_toolbar.js": ("toolbar", ("eg-search", "eg-summary", "eg-width")),
    }
    for name, (hook, names) in expected.items():
        text = JS_FILES[name]
        assert f"feature({{ name: '{hook}'" in text, name
        for part in names:
            section(text, part)
    for part in CORE_SECTIONS:
        section(PURE, part)


def test_the_core_offers_the_fixed_internal_api() -> None:
    """기능 가지(select·fill·toolbar)가 부르는 함수 이름 — 바꾸지 않는다(명세 4-2)."""
    names = (
        "paint scrollToCell setRange displayText rawText valueAt isLocked rowKeys colNames "
        "queueOp sendNow sendOnce startEdit commitEdit cancelEdit setStatus announce toast "
        "focusGrid cellAtPoint visibleRowCount setWidths"
    ).split()
    for name in names:
        assert re.search(rf"^function {name}\(S\b", CORE, re.M), name
    hooks = re.findall(r"item\.([a-zA-Z]+) && item\.\1\(", CORE) + re.findall(
        r"if \(item\.([a-zA-Z]+)\) item\.\1\(", CORE
    )
    assert set(hooks) == {
        "init",
        "keydown",
        "pointerdown",
        "paintCell",
        "paintOverlay",
        "onFeed",
        "onSelect",
        "onLayout",
        "cleanup",
    }


def test_the_editing_channel_is_one_state_value_without_triggers() -> None:
    """편집은 상태 값 `outbox` 하나 — 트리거는 다음 트리거에 덮여 잃을 수 있다(AGENTS 9장)."""
    assert set(re.findall(r"setState\('([a-z]+)'", REGISTERED_JS)) == set(edit_grid.STATE_NAMES)
    assert "setTrigger" not in REGISTERED_JS and "setTriggerValue" not in REGISTERED_JS
    assert edit_grid.TRIGGER_NAMES == ()
    registered = set(re.findall(r"on_([a-z]+)_change=", SOURCE))
    assert registered == set(edit_grid.STATE_NAMES)


def test_ops_the_browser_sends_are_the_ops_python_applies() -> None:
    sent = set(re.findall(r"\bop: '([a-z]+)'", REGISTERED_JS))
    assert sent and sent <= eg.OP_NAMES, sent - eg.OP_NAMES
    assert {"write", "clear"} <= sent


def test_the_clipboard_is_never_read_through_the_async_api() -> None:
    """사내 주소가 보안 문맥이 아닐 수 있어 비동기 Clipboard API 를 쓰지 않는다 — copy·paste
    이벤트만."""
    assert "navigator.clipboard" not in REGISTERED_JS
    assert "clipboardData" in CORE


def test_local_storage_is_touched_only_inside_try() -> None:
    for match in re.finditer(r"localStorage", REGISTERED_JS):
        before = REGISTERED_JS[max(match.start() - 120, 0) : match.start()]
        assert "try {" in before, REGISTERED_JS[match.start() - 120 : match.end() + 20]


def test_colours_come_only_from_the_palette() -> None:
    """등록 CSS 는 테마를 따라오지 않는다 — 색은 팔레트 data 의 `var(--eg-*)` 로만."""
    used = set(re.findall(r"var\(--eg-([a-z-]+)", REGISTERED_CSS + REGISTERED_JS))
    layout_vars = {"row-h", "head-h"}
    assert used - layout_vars <= set(edit_grid.palette()), used - set(edit_grid.palette())
    for text in (REGISTERED_CSS, REGISTERED_JS, asset("grid.html"), FEED):
        assert not re.search(r"#[0-9A-Fa-f]{3,8}\b", text)
        assert "rgb(" not in text and "rgba(" not in text and "hsl(" not in text


def test_the_palette_names_every_token_the_grid_needs() -> None:
    expected = (
        "font text muted surface subtle header border border-strong accent on-accent changed-fill "
        "changed-mark error-fill error-line warn-line lock-fill selected-fill match-fill pending"
    )
    assert list(edit_grid.palette()) == expected.split()
    assert all(isinstance(value, str) and value for value in edit_grid.palette().values())


def test_user_text_goes_in_with_text_content_only() -> None:
    """분류 표시명·적은 글·토스트는 데이터다 — innerHTML·insertAdjacentHTML 로 넣지 않는다."""
    for pattern in (
        r"\.innerHTML\s*=",
        r"insertAdjacentHTML",
        r"outerHTML\s*=",
        r"document\.write",
    ):
        assert not re.search(pattern, REGISTERED_JS), pattern


def test_nothing_is_fixed_on_screen() -> None:
    """전체 화면은 그림자 DOM 안 `<dialog>.showModal()` 이다 — `position: fixed` 덮개는 긴 회차에
    Streamlit 이 opacity 0.33 을 걸어 머리 띠·사이드바 밑으로 묻힌다(D2 시제품)."""
    for text in (REGISTERED_CSS, REGISTERED_JS):
        assert not re.search(r"position:\s*fixed", text)
        assert "position = 'fixed'" not in text


def _z_index(css: str, selector: str) -> int:
    """`selector {…}` 덩어리 하나의 z-index(정확히 그 선택자만)."""
    match = re.search(rf"(?:^|\n){re.escape(selector)} \{{(?P<body>[^}}]*)\}}", css)
    assert match, selector
    value = re.search(r"z-index:\s*(\d+)", match.group("body"))
    assert value, selector
    return int(value.group(1))


def test_the_cell_editor_scrolls_under_the_header_and_the_frozen_columns() -> None:
    """칸 편집기는 캔버스 좌표에 놓여 표와 함께 구른다 — 머리 줄(sticky)·고정 분류 칸 **아래**로
    숨어야 그 글을 가리지 않는다(엑셀 틀 고정, 2026-11-03 리뷰: z 6 이 머리 4·고정 2 위에 떴다).
    지금 칸 테(1)보다 낮지는 않다 — 같은 z 면 DOM 차례가 뒤인 편집기가 위다."""
    core = CSS_FILES["eg_core.css"]
    editor = _z_index(core, ".eg-ed")
    assert editor < _z_index(core, ".eg-head")
    assert editor < _z_index(core, ".eg-fz")
    assert editor < _z_index(core, ".eg-fz.is-active")
    assert editor >= _z_index(core, ".eg-c.is-active")
    assert core.index(".eg-ed {") > core.index(".eg-c.is-active {")
    assert "canvas.appendChild(editor)" in CORE
    assert CORE.index("canvas.appendChild(editor)") > CORE.index("canvas.appendChild(body)")


def test_css_files_carry_no_comments() -> None:
    """등록 CSS 는 data 가 바뀐 회차마다 요소와 함께 다시 간다 — 주석을 싣지 않는다."""
    for name, text in CSS_FILES.items():
        assert "/*" not in text, name


def test_the_registered_bytes_stay_within_budget() -> None:
    """명세 12장 예산 — 등록 JS(주석 줄 걷은 뒤) ≤ 120 KB, CSS ≤ 24 KB, feed JS ≤ 3 KB."""
    assert len(REGISTERED_JS.encode("utf-8")) <= 120_000
    assert len(REGISTERED_CSS.encode("utf-8")) <= 24_000
    assert len(edit_grid.feed_js().encode("utf-8")) <= 3_000


def test_the_feed_script_hands_its_data_over_through_the_window_slot() -> None:
    """두 등록은 같은 문서의 칸과 이벤트로 잇는다 — 호스트 key 는 [\\w-]+ 만(그 밖이면 버림)."""
    feed = edit_grid.feed_js()
    assert "window.__capaEditGrid" in feed and "slot.feed = data" in feed
    assert "new CustomEvent('capa-edit-grid', { detail: data.host })" in feed
    assert r"/^[\w-]+$/.test(data.host)" in feed
    assert "EG_FEED_EVENT = 'capa-edit-grid'" in CORE and "window.__capaEditGrid" in CORE
    assert "feed.baseKey !== S.shell.baseKey" in CORE


def test_handled_keys_stay_inside_the_grid() -> None:
    """그리드가 처리한 키는 문서로 올려 보내지 않는다 — Streamlit 문서 단축키(r·c)가 글자를
    먹는다."""
    assert "egListen(S, root, 'keydown', (event) => event.stopPropagation())" in CORE
    core_key = CORE[CORE.index("function egOnKey(") : CORE.index("function egCoreKey(")]
    assert "event.preventDefault()" in core_key and "event.stopPropagation()" in core_key
    editor = CORE[CORE.index("function egOnEditorKey(") :]
    assert "event.stopPropagation()" in editor[: editor.index("\n}\n")]


def test_the_outbox_flushes_after_quiet_at_once_on_leave_and_never_inside_render() -> None:
    assert "const EG_SEND_MS = 300" in CORE
    assert "egListen(S, root, 'focusout'" in CORE and "'visibilitychange'" in CORE
    send = CORE[CORE.index("function sendNow(") : CORE.index("function sendOnce(")]
    assert "if (S.inRender)" in send and "queueMicrotask" in send
    queue = CORE[CORE.index("function queueOp(") : CORE.index("function egPreviewOf(")]
    assert "!Number(counts.cells)" in queue


def test_the_cleanup_releases_listeners_timers_and_frames() -> None:
    cleanup = CORE[CORE.rindex("return () => {") :]
    for piece in ("removeEventListener", "clearTimeout", "cancelAnimationFrame", "disconnect()"):
        assert piece in cleanup, piece
    assert "item.cleanup" in cleanup


def test_the_component_is_registered_once_with_a_shadow_root() -> None:
    """그림자 DOM(기본값) — 팝업 안에 마운트하지 않는다. 두 등록 이름이 정해져 있다."""
    assert "isolate_styles" not in SOURCE.split("_GRID = st.components.v2.component(")[1][:200]
    assert SOURCE.count("st.components.v2.component(") == 2
    assert edit_grid.GRID_COMPONENT == "capa_edit_grid"
    assert edit_grid.FEED_COMPONENT == "capa_edit_grid_feed"


# ------------------------------------------------------------------ node — 순수 구획


def _pure(*names: str) -> str:
    return sections(PURE, names)


def _template(rows: int = 7, months: int = 70) -> tuple[pd.DataFrame, eg.GridSpec]:
    month_names = [f"M{k:03d}" for k in range(months)]
    frame = pd.DataFrame(
        {
            "공정": ["DEMO_A", "DEMO_B", "DEMO_A", "DEMO_C", "DEMO_A", "DEMO_B", "DEMO_D"][:rows],
            "구분": ["양산", "양산", "양산", "ER", "양산", "ER", "양산"][:rows],
        }
    )
    values = np.full((rows, months), 0.85)
    values[1, :] = np.nan
    values[2, 10:] = 0.9875
    values[3, ::2] = 1.0
    values[4, 5] = np.nan
    values[6, :] = np.arange(months) / 7
    for column, name in enumerate(month_names):
        frame[name] = values[:, column]
    spec = eg.GridSpec(
        "RQ_DEMO", "데모", ("공정", "구분"), tuple(month_names), eg.ValueFormat("percent", 2)
    )
    return frame, spec


def test_the_browser_decodes_the_shell_and_feed_python_built() -> None:
    """쌍둥이 — Python `encode_table`·`encode_feed` 가 지은 꼴을 JS `decodeBase`·`decodeDraft` 가
    같은 값으로 푼다(같은 키의 둘째 꼬리표 · 63 넘는 런 · 표시명 · 초안 코드 셋)."""
    frame, spec = _template()
    base = payload.build_base(frame, spec, {"공정": {"DEMO_A": "에이", "DEMO_B": "비"}})
    index = base.index
    draft: eg.DraftState = {
        "cells": {index.keys[0]: {"M000": 0.5, "M069": None}, index.keys[6]: {"M001": 0.25}},
        "bad": {index.keys[3]: {"M004": ("85", "max")}},
    }
    history = eg.new_history()
    feed = payload.encode_feed(
        index, draft, history, host="demo", base_key="k", acks={"m": 3}, toast=None
    )
    runner = (
        RUNNER_HEAD
        + """
const model = decodeBase(input.shell)
const decoded = decodeDraft(input.feed, model.valueCount)
done({
  keys: model.keys, values: model.values, labels: model.labels,
  draft: Array.from(decoded.draft.entries()), bad: Array.from(decoded.bad.entries()),
})
"""
    )
    result = run_node(_pure("eg-codes"), runner, {"shell": base.body, "feed": feed})
    assert result["keys"] == list(index.keys)
    assert "DEMO_A\x1f양산\x1e1" in result["keys"]
    expected = [None if math.isnan(value) else value for value in index.values.ravel().tolist()]
    assert result["values"] == expected
    assert result["labels"][0] == ["에이", "비", "DEMO_C", "DEMO_D"] and result["labels"][1] is None
    columns = len(spec.value_columns)
    assert sorted(result["draft"], key=lambda item: item[0]) == [
        [0, 0.5],
        [69, None],
        [3 * columns + 4, "bad"],
        [6 * columns + 1, 0.25],
    ]
    assert result["bad"] == [[3 * columns + 4, {"text": "85", "code": "max"}]]


@pytest.mark.parametrize("width", [1, 2])
def test_codes_round_trip_at_both_widths(width: int) -> None:
    count = 64 if width == 1 else 300
    codes = list(range(count))[::-1]
    text = payload.encode_codes(codes, payload.code_width(count))
    assert payload.code_width(count) == width
    runner = RUNNER_HEAD + "done(decodeCodes(input.text, input.width))"
    assert run_node(_pure("eg-codes"), runner, {"text": text, "width": width}) == codes


def test_value_parsing_and_display_match_python_for_every_case() -> None:
    """쌍둥이 — 사례 표의 값 다듬기·표시 형식을 JS 가 Python 과 같은 답으로 낸다."""
    runner = (
        RUNNER_HEAD
        + """
const formats = input.formats
done({
  coerce: input.coerce.map((c) => parseInput(c.raw, formats[c.fmt], c.template)),
  format: input.format.map((c) => formatValue(c.value, formats[c.fmt])),
})
"""
    )
    result = run_node(_pure("eg-format"), runner, CASES)
    for case, got in zip(CASES["coerce"], result["coerce"], strict=True):
        assert [got["value"], got["error"], got["text"]] == [
            case["value"],
            case["error"],
            case["text"],
        ], case
    assert result["format"] == [case["text"] for case in CASES["format"]]


def test_the_edit_text_shows_percent_as_a_percent() -> None:
    runner = (
        RUNNER_HEAD
        + """
const fmt = { kind: 'percent', digits: 2 }
done([editText(0.9875, fmt), editText(0.85, fmt), editText(null, fmt), editText(0.1 + 0.2, fmt),
  editText(30, { kind: 'fixed', digits: 0 }), editText(1234.5, { kind: 'sig', digits: 6 })])
"""
    )
    assert run_node(_pure("eg-format"), runner, {}) == ["98.75%", "85%", "", "30%", "30", "1234.5"]


def test_the_outbox_queues_acks_drops_stale_and_spots_repeats() -> None:
    runner = (
        RUNNER_HEAD
        + """
const box = createBox()
const write = (n) => ({ op: 'write', table: 'T', gen: 'g1', rows: ['a'], cols: ['m'],
  values: [Array(n).fill('1')] })
const first = boxQueue(box, write(3), 10, 100)
const second = boxQueue(box, write(5), 10, 101)
const tooMany = boxQueue(box, write(3), 10, 102)
const clear = boxQueue(box, { op: 'clear', table: 'T', gen: 'g1', rows: ['a'], cols: [] }, 10, 103)
const other = boxQueue(box, { op: 'undo', table: 'U', gen: 'x' }, 20, 104)
const repeat = boxHasOp(box, { op: 'undo', table: 'U', gen: 'x' })
const fresh = boxHasOp(box, { op: 'redo', table: 'U', gen: 'x' })
const acked = boxAck(box, 1)
const stale = boxDropStale(box, 'T', 'g2').map((op) => op.seq)
done({ first: [first.seq, first.at], second: second.seq, tooMany, clear: clear && clear.seq,
  cells: [opCells(write(4)), opCells({ op: 'fill', rows: ['a', 'b'], cols: ['m'] }),
    opCells({ op: 'undo' })],
  repeat, fresh, acked, stale, left: box.ops.map((op) => op.seq), other: other.seq })
"""
    )
    result = run_node(_pure("eg-outbox"), runner, {})
    assert result == {
        "first": [1, 100],
        "second": 2,
        "tooMany": None,
        "clear": 3,
        "cells": [4, 3, 1],
        "repeat": True,
        "fresh": False,
        "acked": 1,
        "stale": [2, 3],
        "left": [4],
        "other": 4,
    }


def test_navigation_keys_move_within_the_table() -> None:
    runner = (
        RUNNER_HEAD
        + """
const blank = new Set(['0,3', '0,4', '0,7'])
const isBlank = (r, c) => blank.has(r + ',' + c)
const go = (pos, key, mods) => moveCell(pos, key, mods || {}, 50, 10, 12, 4, isBlank)
const at = { r: 20, c: 2 }
const ctrl = { ctrl: true }
const alt = { alt: true }
done({
  arrows: [go(at, 'ArrowUp'), go(at, 'ArrowDown'), go(at, 'ArrowLeft'), go(at, 'ArrowRight')],
  edges: [go({ r: 0, c: 0 }, 'ArrowUp'), go({ r: 49, c: 9 }, 'ArrowRight')],
  page: [go(at, 'PageDown'), go(at, 'PageUp'), go({ r: 45, c: 2 }, 'PageDown'),
    go(at, 'PageDown', alt), go(at, 'PageUp', alt)],
  home: [go(at, 'Home'), go(at, 'End'), go(at, 'Home', ctrl), go(at, 'End', ctrl)],
  block: [go({ r: 0, c: 0 }, 'ArrowRight', ctrl), go({ r: 0, c: 2 }, 'ArrowRight', ctrl),
    go({ r: 0, c: 5 }, 'ArrowRight', ctrl), go({ r: 0, c: 8 }, 'ArrowRight', ctrl),
    go({ r: 0, c: 3 }, 'ArrowRight', ctrl), go({ r: 5, c: 5 }, 'ArrowDown', ctrl)],
  unknown: go(at, 'q'),
  tab: [tabMove({ r: 3, c: 8 }, false, 10), tabMove({ r: 3, c: 9 }, false, 10),
    tabMove({ r: 3, c: 0 }, true, 10)],
})
"""
    )
    result = run_node(_pure("eg-nav"), runner, {})

    def cell(r: int, c: int) -> dict[str, int]:
        return {"r": r, "c": c}

    assert result["arrows"] == [cell(19, 2), cell(21, 2), cell(20, 1), cell(20, 3)]
    assert result["edges"] == [cell(0, 0), cell(49, 9)]
    assert result["page"] == [cell(32, 2), cell(8, 2), cell(49, 2), cell(20, 6), cell(20, 0)]
    assert result["home"] == [cell(20, 0), cell(20, 9), cell(0, 0), cell(49, 9)]
    # 0..2 찬 칸 · 3,4 빈칸 · 5,6 찬 칸 · 7 빈칸 · 8,9 찬 칸(엑셀 Ctrl+→).
    assert result["block"] == [
        cell(0, 2),
        cell(0, 5),
        cell(0, 6),
        cell(0, 9),
        cell(0, 5),
        cell(49, 5),
    ]
    assert result["unknown"] is None
    assert result["tab"] == [cell(3, 9), None, None]


def test_shortcut_letters_read_the_key_position_under_a_hangul_layout() -> None:
    """단축키 글자는 라틴 key 를 먼저, 아니면 자판 자리(code)로 — 한글 자판의 Ctrl 조합은 key 가
    「ㅋ」 로 온다(2026-11-03 리뷰: Ctrl+ㅋ·ㅁ·ㄹ 가 먹지 않고 Ctrl+ㅁ→ㅊ 이 페이지 글을 복사했다).
    그리드의 Ctrl 단축키는 모두 이 한 길이다."""
    runner = (
        RUNNER_HEAD
        + """
done([
  shortcutLetter('z', 'KeyZ'), shortcutLetter('Z', 'KeyZ'), shortcutLetter('ㅋ', 'KeyZ'),
  shortcutLetter('ㅁ', 'KeyA'), shortcutLetter('Process', 'KeyC'), shortcutLetter('z', 'KeyW'),
  shortcutLetter('ArrowLeft', 'ArrowLeft'), shortcutLetter('ㄹ', ''),
  shortcutLetter(undefined, undefined), shortcutLetter('5', 'Digit5'),
])
"""
    )
    result = run_node(_pure("eg-nav"), runner, {})
    assert result == ["z", "z", "z", "a", "c", "z", "", "", "", ""]
    for name in ("eg_core.js", "eg_select.js", "eg_fill.js", "eg_toolbar.js"):
        body = JS_FILES[name]
        assert "shortcutLetter(" in body, name
        assert "key.toLowerCase() === 'f'" not in body and "lower === '" not in body, name


def test_the_view_filters_by_codes_and_sorts_stably_with_blanks_last() -> None:
    runner = (
        RUNNER_HEAD
        + """
const codes = [Int32Array.from([0, 1, 0, 2, 1, 0]), Int32Array.from([0, 0, 1, 1, 0, 0])]
const nums = [3, NaN, 1, 3, 2, NaN]
const names = ['공정10', '공정2', '', '공정1', '공정2', 'B']
const order = (filters, sort, numeric) => Array.from(viewOrder(6, codes, filters, sort,
  numeric ? (r) => nums[r] : (r) => names[r], numeric))
done({
  all: order(null, null, true),
  filtered: order({ 0: [0, 1] }, null, true),
  both: order({ '0': [0, 1], '1': [0] }, null, true),
  asc: order(null, { col: 3, dir: 'asc' }, true),
  desc: order(null, { col: 3, dir: 'desc' }, true),
  text: order(null, { col: 0, dir: 'asc' }, false),
  rank: Array.from(viewRank(Int32Array.from([4, 2, 0]), 6)),
  cycle: [nextSort(null, 3), nextSort({ col: 3, dir: 'asc' }, 3),
    nextSort({ col: 3, dir: 'desc' }, 3), nextSort({ col: 3, dir: 'asc' }, 1)],
})
"""
    )
    result = run_node(_pure("eg-nav", "eg-view"), runner, {})
    assert result["all"] == [0, 1, 2, 3, 4, 5]
    assert result["filtered"] == [0, 1, 2, 4, 5]
    assert result["both"] == [0, 1, 4, 5]
    assert result["asc"] == [2, 4, 0, 3, 1, 5]
    assert result["desc"] == [0, 3, 4, 2, 1, 5]
    # 한국어 차례 — 자연 수 차례(공정1 < 공정2 < 공정10), 한글이 라틴보다 앞, 빈 글은 끝.
    assert result["text"] == [3, 1, 4, 0, 5, 2]
    assert result["rank"] == [2, -1, 1, -1, 0, -1]
    assert result["cycle"] == [
        {"col": 3, "dir": "asc"},
        {"col": 3, "dir": "desc"},
        None,
        {"col": 1, "dir": "asc"},
    ]


def test_frozen_key_columns_stop_at_the_share_of_the_grid() -> None:
    """UPEH 열쇠 칸 9개를 104px 로 다 고정하면 936px 라 1,163px 표에서 월 칸이 셋만 보였다(D2)
    — 누적 폭이 표 폭의 45% 를 넘는 칸부터 풀고, 첫 열쇠 칸은 늘 고정한다."""
    runner = (
        RUNNER_HEAD
        + """
const nine = Array(9).fill(104).concat(Array(39).fill(80))
const placed = columnLefts([104, 104, 80, 80])
done({
  upeh: frozenCount(nine, 9, 1163, 0.45),
  narrow: frozenCount(nine, 9, 150, 0.45),
  wide: frozenCount(nine, 9, 4000, 0.45),
  first: frozenCount([600, 104].concat(Array(5).fill(80)), 2, 1000, 0.45),
  none: frozenCount([80, 80], 0, 1000, 0.45),
  lefts: placed,
  at: [colAtX(placed.lefts, 0), colAtX(placed.lefts, 103), colAtX(placed.lefts, 104),
    colAtX(placed.lefts, 300), colAtX(placed.lefts, 9999)],
  widths: defaultWidths([{ name: 'a' }, { name: 'b', width: 140 }], 3, 104, 80),
})
"""
    )
    result = run_node(_pure("eg-nav", "eg-layout"), runner, {})
    assert result["upeh"] == 5
    assert result["narrow"] == 1
    assert result["wide"] == 9
    assert result["first"] == 1
    assert result["none"] == 0
    assert result["lefts"] == {"lefts": [0, 104, 208, 288], "total": 368}
    assert result["at"] == [0, 0, 1, 3, 3]
    assert result["widths"] == [104, 140, 80, 80, 80]


def test_the_change_list_follows_the_view_and_puts_hidden_rows_last() -> None:
    runner = (
        RUNNER_HEAD
        + """
const values = Float64Array.from([1, 2, NaN, 4, 5, 6, 7, 8, 9])
const draft = new Map([[4, 50], [0, null], [8, 'bad'], [2, 3]])
const bad = new Map([[8, { text: 'x', code: 'num' }], [6, { text: 'y', code: 'max' }]])
const rank = Int32Array.from([1, 0, -1])
const all = changeEntries(draft, bad, values, 3, rank, 10)
const cut = changeEntries(draft, bad, values, 3, rank, 2)
done({ all, cut: cut.entries.map((e) => [e.row, e.col]), total: cut.total })
"""
    )
    result = run_node(_pure("eg-codes", "eg-changes"), runner, {})
    assert result["all"]["total"] == 5
    assert result["all"]["entries"] == [
        {"row": 1, "col": 1, "before": 5, "after": 50, "bad": None},
        {"row": 0, "col": 0, "before": 1, "after": None, "bad": None},
        {"row": 0, "col": 2, "before": None, "after": 3, "bad": None},
        {"row": 2, "col": 0, "before": 7, "after": None, "bad": {"text": "y", "code": "max"}},
        {"row": 2, "col": 2, "before": 9, "after": None, "bad": {"text": "x", "code": "num"}},
    ]
    assert result["cut"] == [[1, 1], [0, 0]] and result["total"] == 5


def test_features_register_once_and_run_in_the_fixed_order() -> None:
    source = PURE[PURE.index("const FEATURES = []") :]
    runner = """
feature({ name: 'toolbar', marker: 1 })
feature({ name: 'select' })
feature({ name: 'fill' })
feature({ name: 'toolbar', marker: 2 })
feature({ name: 3 })
process.stdout.write(JSON.stringify(FEATURES.map((item) => [item.name, item.marker || 0])))
"""
    result: Any = run_node(source, runner, {})
    assert result == [["select", 0], ["fill", 0], ["toolbar", 2]]
