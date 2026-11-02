# Purpose: 범용 편집 그리드 붙여넣기·채우기(eg_fill)의 순수 구획·사례 표·가짜 DOM 동작을 본다.

"""붙여넣기·채우기(FILL) 가지 몫(편집 표 횡전개 명세 1-2 의 14·15, 9-3, 9-4, 13-1).

순수 구획 `// <eg-paste>`·`// <eg-fill>` 은 node 로 떼어 돌린다(`tests/edit_grid_node.py` —
`<eg-paste>` 는 eg_select 의 `<eg-clip>`(`pasteAtAnchor`)을 함께 싣는다). 사례 표
(`tests/fixtures/edit_grid_cases.json` 의 `grid`·`fill`·`paste`)는 쌍둥이로 본다 — node 가 고름·끈
칸·키에서 짓는 판이 사례 표의 판과 같고, Python 서버(`apply_ops`)가 그 판의 op 를 반영한 표가 사례
표의 결과와 같다. 동작은 등록 JS 전체를 가짜 DOM 에 마운트해 손잡이 끌기·Ctrl+D/R·Ctrl+Enter·paste
이벤트를 쏘아 보고, 브라우저가 보낸 출납을 그대로 Python 에 넣어 미리보기와 서버 반영이 같은지
본다. 실제 Chrome 의 Ctrl+D·Ctrl+R 가로채기는 사본 앱 브라우저로 잰다(명세 13-5 FILL)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from edit_grid_node import FAKE_DOM, RUNNER_HEAD, asset, mountable, run_node, section

from capa_simulation.components import edit_grid
from capa_simulation.services import edit_grid as eg
from capa_simulation.services.edit_grid_payload import build_base, encode_base, encode_feed

FILL = asset("eg_fill.js")
FILL_CSS = asset("eg_fill.css")
SELECT = asset("eg_select.js")
REGISTERED_JS = edit_grid.registered_js()
CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "edit_grid_cases.json").read_text(encoding="utf-8")
)
GRID = CASES["grid"]
GRID_MONTHS = ("202701", "202702", "202703", "202704")
GRID_FORMAT = CASES["formats"][GRID["fmt"]]
GRID_SPEC = eg.GridSpec(
    "RQ_DEMO",
    "UPEH",
    ("공정", "구분"),
    GRID_MONTHS,
    eg.ValueFormat(
        GRID_FORMAT["kind"],
        GRID_FORMAT["digits"],
        integer=GRID_FORMAT["int"],
        min_value=GRID_FORMAT["min"],
        max_value=GRID_FORMAT["max"],
        blank_zero=GRID_FORMAT["blankZero"],
    ),
)


def _pure() -> str:
    """`<eg-paste>` 는 eg_select 의 `pasteAtAnchor`(`<eg-clip>`)를 부른다 — 함께 싣는다."""
    return "\n".join(
        (section(SELECT, "eg-clip"), section(FILL, "eg-paste"), section(FILL, "eg-fill"))
    )


# ------------------------------------------------------------------ 자산 글


def test_the_fill_feature_registers_its_hooks() -> None:
    hook = FILL[FILL.rindex("feature({ name: 'fill'") :]
    for name in ("init", "keydown", "pointerdown", "paintOverlay", "paste", "cleanup"):
        assert re.search(rf"\b{name}: fill[A-Z]", hook), name


def test_fill_sends_the_server_fill_op_without_values() -> None:
    """채우기는 값을 싣지 않는다 — 채울 줄·칸 + 원본 줄·칸 + 방향을 보내고 서버가 지금 원본 칸
    값(초안 ∪ 양식)에서 되풀이한다(`services/edit_grid` 의 `FILL_DIRECTIONS`)."""
    send = FILL[FILL.index("function fillSend(") : FILL.index("function fillEnterAll(")]
    assert "op: 'fill', dir: plan.dir" in send and "src: { rows:" in send
    assert "values" not in send
    assert set(re.findall(r"'(down|up|right|left)'", FILL)) == set(eg.FILL_DIRECTIONS)


def test_ctrl_d_and_ctrl_r_stop_the_browser_defaults_and_read_the_key_position_under_hangul() -> (
    None
):
    key = FILL[FILL.index("function fillKey(") : FILL.index("function fillInit(")]
    assert "event.preventDefault()" in key
    assert "event.code === 'KeyD'" in key and "event.code === 'KeyR'" in key
    assert "/^[a-z]$/.test(key)" in key


def test_the_fill_css_draws_with_palette_colours_only() -> None:
    used = set(re.findall(r"var\(--eg-([a-z-]+)", FILL_CSS))
    assert used and used <= set(edit_grid.palette())
    assert "/*" not in FILL_CSS
    assert not re.search(r"#[0-9A-Fa-f]{3,8}\b", FILL_CSS)
    handle = FILL_CSS[FILL_CSS.index(".eg-handle {") :]
    handle = handle[: handle.index("}")]
    assert "width: 7px" in handle and "height: 7px" in handle
    assert "const FILL_HANDLE_PX = 7" in FILL


def test_the_fill_texts_are_shipped_in_korean() -> None:
    spec = eg.GridSpec("RQ_DEMO", "효율", ("공정",), ("202701",), eg.ValueFormat("percent", 2))
    texts = edit_grid.texts(spec, changes_label="적용 전 변경")
    for name in ("filled", "filledAll"):
        assert "{n}" in texts[name], name
    for name in ("filled", "filledAll", "pasteTiled", "fillNoSource", "fillHandle"):
        assert re.search(r"[가-힣]", texts[name]), name
        assert f"'{name}'" in FILL, name


# ------------------------------------------------------------------ 사례 표 — Python 쪽(node 없이)


def _grid_frame() -> pd.DataFrame:
    values = GRID["values"]
    frame = pd.DataFrame(
        {
            "공정": [f"DEMO_P{k}" for k in range(len(values))],
            "구분": ["양산" if k % 2 == 0 else "ER" for k in range(len(values))],
        }
    )
    for column, month in enumerate(GRID_MONTHS):
        frame[month] = [np.nan if line[column] is None else float(line[column]) for line in values]
    return frame


def _after(op: eg.Op) -> list[list[float | None]]:
    """사례 표의 판 하나를 서버에 반영한 뒤 보이는 값(초안 ∪ 양식) — 보기 차례 = 양식 차례."""
    frame = _grid_frame()
    index = eg.build_index(frame, GRID_SPEC)
    result = eg.apply_ops(index, GRID_SPEC, None, {"gen": "g", "undo": [], "redo": []}, [op])
    assert result.acks == {"m": 1} and not result.toasts, result.toasts
    merged = eg.merge_into_template(frame, GRID_SPEC, result.draft)
    matrix = merged[list(GRID_MONTHS)].to_numpy(dtype=float)
    return [[None if np.isnan(value) else float(value) for value in line] for line in matrix]


def _keys(rows: list[int]) -> tuple[str, ...]:
    keys = eg.row_keys(_grid_frame(), GRID_SPEC.key_columns)
    return tuple(keys[row] for row in rows)


def _months(cols: list[int]) -> tuple[str, ...]:
    return tuple(GRID_MONTHS[col - GRID["keyCount"]] for col in cols)


def _fill_op(plan: dict[str, Any]) -> eg.Op:
    return eg.Op(
        mount="m",
        seq=1,
        at=1.0,
        table="RQ_DEMO",
        gen="g",
        kind="fill",
        rows=_keys(plan["rows"]),
        cols=_months(plan["cols"]),
        src_rows=_keys(plan["srcRows"]),
        src_cols=_months(plan["srcCols"]),
        direction=plan["dir"],
    )


def _paste_op(plan: dict[str, Any]) -> eg.Op:
    rows = list(range(plan["r0"], plan["r1"] + 1))
    cols = list(range(plan["c0"], plan["c1"] + 1))
    values = tuple(tuple(line) for line in plan["values"])
    return eg.Op(
        mount="m",
        seq=1,
        at=1.0,
        table="RQ_DEMO",
        gen="g",
        kind="write",
        rows=_keys(rows),
        cols=_months(cols),
        values=values,
    )


def _plain(grid: list[list[Any]]) -> list[list[float | None]]:
    return [[None if value is None else float(value) for value in line] for line in grid]


@pytest.mark.parametrize("case", CASES["fill"], ids=lambda case: case["name"])
def test_the_server_fills_the_case_table_plans_into_the_case_table_results(
    case: dict[str, Any],
) -> None:
    """네 방향 되풀이 — 아래·오른쪽은 원본 첫 줄·칸부터, 위·왼쪽은 원본 끝부터(엑셀). 빈칸도 원본
    값으로 옮긴다."""
    plan = case["plan"]
    if plan is None or "error" in plan:
        assert "result" not in case
        return
    assert _after(_fill_op(plan)) == _plain(case["result"])


@pytest.mark.parametrize("case", CASES["paste"], ids=lambda case: case["name"])
def test_the_server_writes_the_case_table_paste_plans_into_the_case_table_results(
    case: dict[str, Any],
) -> None:
    """덩어리 한 벌을 싣고 서버가 (i mod h, j mod w) 로 되풀이한다 — 분류 칸에서 시작한 되풀이는
    덩어리 칸을 돌려 실어 엑셀과 같은 자리 차례가 된다."""
    plan = case["plan"]
    if not plan["cells"]:
        assert "result" not in case and plan["values"] == []
        return
    assert plan["valueCells"] == sum(len(line) for line in plan["values"])
    assert _after(_paste_op(plan)) == _plain(case["result"])


def test_the_case_table_covers_every_decided_fill_rule() -> None:
    """명세 1-2 의 14·15 — 네 방향·더 먼 축·같으면 세로·분류 칸 건너뜀·한 줄/한 칸 단축키·원본
    없음·잠김·값 하나·정수 배 되풀이·기준 칸·표 끝 자름·들쭉날쭉 덩어리."""
    fills = {case["name"]: case for case in CASES["fill"]}
    plans = [case["plan"] for case in fills.values() if case["plan"]]
    assert {plan["dir"] for plan in plans if "dir" in plan} == set(eg.FILL_DIRECTIONS)
    errors = {plan["error"] for plan in plans if "error" in plan}
    assert errors == {"noSource", "locked"}
    assert any(case["plan"] and case["plan"].get("skipped") for case in fills.values())
    assert any(case["plan"] is None for case in fills.values()), "범위 안 되끌기"
    assert {"down", "right"} == {case["key"] for case in fills.values() if "key" in case}
    pastes = CASES["paste"]
    assert any(case["plan"]["tiled"] and case["matrix"] == [["7"]] for case in pastes)
    assert any(not case["plan"]["tiled"] for case in pastes)
    assert any(case["plan"]["clipped"] for case in pastes)
    assert any(case["plan"]["skipped"] and case["plan"]["cells"] for case in pastes)


# ------------------------------------------------------------------ node — 순수 구획 + 쌍둥이


def test_node_plans_the_same_fills_and_pastes_as_the_case_table() -> None:
    runner = (
        RUNNER_HEAD
        + """
const rect = (s) => ({ r0: s[0], r1: s[1], c0: s[2], c1: s[3] })
const k = input.keyCount
done({
  fill: input.fill.map((c) => c.key
    ? fillByKey(rect(c.select), c.key, k)
    : fillByHandle(rect(c.select), { r: c.drag[0], c: c.drag[1] }, k)),
  paste: input.paste.map((c) => planPaste(rect(c.select), c.matrix, input.rows, input.cols, k)),
})
"""
    )
    payload = {
        "keyCount": GRID["keyCount"],
        "rows": len(GRID["values"]),
        "cols": GRID["keyCount"] + len(GRID_MONTHS),
        "fill": CASES["fill"],
        "paste": CASES["paste"],
    }
    result = run_node(_pure(), runner, payload)
    for case, got in zip(CASES["fill"], result["fill"], strict=True):
        assert got == case["plan"], case["name"]
    for case, got in zip(CASES["paste"], result["paste"], strict=True):
        assert {key: got[key] for key in case["plan"]} == case["plan"], case["name"]


def test_the_handle_extends_along_the_farther_axis_only() -> None:
    """손잡이를 비스듬히 끌면 범위 밖으로 더 멀리 나간 쪽(칸 수) 하나로만 늘린다 — 같으면 세로."""
    runner = (
        RUNNER_HEAD
        + """
const rect = { r0: 4, r1: 5, c0: 4, c1: 5 }
const dir = (r, c) => {
  const plan = fillByHandle(rect, { r, c }, 2)
  return plan && (plan.dir || plan.error)
}
done({
  downRight: dir(9, 7), rightDown: dir(6, 9), tie: dir(7, 7), upLeft: dir(0, 3), leftUp: dir(3, 0),
  inside: dir(4, 5), corner: dir(5, 5), upRight: dir(1, 6),
})
"""
    )
    result = run_node(_pure(), runner, {})
    assert result == {
        "downRight": "down",
        "rightDown": "right",
        "tie": "down",
        "upLeft": "up",
        "leftUp": "left",
        "inside": None,
        "corner": None,
        "upRight": "up",
    }


def test_a_paste_plan_counts_the_cells_it_ships_against_the_limit() -> None:
    """값 하나를 큰 범위에 붙여도 싣는 값 칸은 하나다(서버가 되풀이) — 상한은 싣는 칸 수로
    견준다. 덩어리를 그대로 펴면 실은 칸 수가 상한과 견줄 수다."""
    runner = (
        RUNNER_HEAD
        + """
const block = Array.from({ length: 500 }, () => Array.from({ length: 30 }, () => '1'))
const one = planPaste({ r0: 0, r1: 2659, c0: 0, c1: 38 }, [['5']], 2660, 39, 9)
const big = planPaste({ r0: 0, r1: 0, c0: 9, c1: 9 }, block, 2660, 39, 9)
const over = planPaste({ r0: 0, r1: 0, c0: 9, c1: 9 }, block.concat([['1']]), 2660, 39, 9)
done({
  one: [one.tiled, one.cells, one.valueCells, one.skipped, one.c0],
  big: [big.tiled, big.cells, big.valueCells],
  over: [over.cells, over.valueCells],
})
"""
    )
    result = run_node(_pure(), runner, {})
    assert result["one"] == [True, 2660 * 30, 1, 2660 * 9, 9]
    assert result["big"] == [False, 15_000, 15_000]
    # 들쭉날쭉한 마지막 줄은 null 로 채워 싣는다 — 서버도 그 칸을 센다(501 × 30).
    assert result["over"] == [15_001, 15_030]


# ------------------------------------------------------------------ 가짜 DOM — 등록 JS 전체

MONTHS = ("202701", "202702", "202703", "202704")
ROWS = 12
SPEC = eg.GridSpec(
    "RQ_DEMO",
    "효율",
    ("공정", "구분"),
    MONTHS,
    eg.ValueFormat("percent", 2, max_value=1.0),
)


def _key(row: int) -> str:
    """가짜 DOM 표 줄의 업무 키(공정 + 구분)."""
    return f"DEMO_P{row:02d}\x1f{'양산' if row % 2 == 0 else 'ER'}"


def _frame() -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "공정": [f"DEMO_P{k:02d}" for k in range(ROWS)],
            "구분": ["양산" if k % 2 == 0 else "ER" for k in range(ROWS)],
        }
    )
    for column, month in enumerate(MONTHS):
        frame[month] = [round(0.5 + (k * 4 + column) / 100, 4) for k in range(ROWS)]
    return frame


def _payloads() -> dict[str, Any]:
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
const store = (window.__capaEditGrid = window.__capaEditGrid || {})
;(store[input.feed.host] = store[input.feed.host] || {}).feed = input.feed
window.dispatchEvent(new CustomEvent('capa-edit-grid', { detail: input.feed.host }))
const cleanup = globalThis.__mount({
  data: input.shell, parentElement,
  setStateValue: (name, value) => sent.push([name, JSON.parse(JSON.stringify(value))]),
})
const S = host.__eg
const q = (selector) => host.querySelector(selector)
const scroller = q('.eg-scroll')
const lineOf = (r) => S.dom.body.children.find((line) => Number(line.dataset.r) === r)
const text = (r, c) => lineOf(r).children[c].textContent
const key = (name, extra) => fire(scroller, 'keydown', Object.assign({ key: name }, extra))
const range = () => S.range()
const lastOp = () => S.box.ops[S.box.ops.length - 1] || null
const note = () => q('.eg-note').textContent
const toastText = () => (q('.eg-toast').hidden ? '' : q('.eg-toast').textContent)
const xOf = (c) => S.lefts[c] + S.widths[c] / 2 - (c < S.frozen ? 0 : scroller.scrollLeft)
const yOf = (r) => S.headH + r * S.rowH + S.rowH / 2 - scroller.scrollTop
const handle = () => q('.eg-handle')
const box = () => q('.eg-fill-box')
const drag = (to, extra) => {
  fire(handle(), 'pointerdown', { clientX: 0, clientY: 0, pointerId: 1 })
  fire(scroller, 'pointermove', { clientX: xOf(to[1]), clientY: yOf(to[0]), pointerId: 1 })
  return Object.assign({ box: { hidden: box().hidden, left: box().style.left, top: box().style.top,
    width: box().style.width, height: box().style.height } }, extra || {})
}
const pick = (r0, c0, r1, c1) => S && setRange(S, { r: r0, c: c0 }, { r: r1, c: c1 })
const R = {}
"""


def _run(body: str) -> Any:
    source = FAKE_DOM + mountable(REGISTERED_JS)
    return run_node(source, MOUNT + "\n;(async () => {\n" + body + "\n})()\n", _payloads())


def _server(outboxes: list[Any]) -> eg.DraftState | None:
    """브라우저가 보낸 마지막 출납을 Python 서버에 그대로 넣어 반영한 초안."""
    frame = _frame()
    index = eg.build_index(frame, SPEC)
    ops, _ = eg.new_ops({"demo_grid": outboxes[-1][1]}, {})
    result = eg.apply_ops(index, SPEC, None, {"gen": "g1", "undo": [], "redo": []}, ops)
    assert not result.toasts, result.toasts
    return result.draft


def test_the_handle_sits_on_the_range_corner_and_hides_while_editing() -> None:
    body = r"""
  pick(1, 2, 2, 3)
  R.shown = { hidden: handle().hidden, left: handle().style.left, top: handle().style.top,
    title: handle().title }
  key('Enter')
  R.editing = handle().hidden
  fire(q('.eg-ed'), 'keydown', { key: 'Escape' })
  R.after = handle().hidden
  pick(1, 0, 1, 1)
  R.keysOnly = handle().hidden
  pick(4, 1, 4, 2)
  R.overKeys = handle().hidden
  // 가로로 굴린 뒤 — 손잡이(값 칸)는 캔버스와 함께 구르고, 점선 테 왼쪽 끝이 고정(분류) 칸이면 굴린
  // 만큼 따라간다(sticky).
  scroller.scrollLeft = 30
  fire(scroller, 'scroll')
  pick(0, 0, 0, 3)
  R.scrolledHandle = handle().style.left
  drag([2, 3])
  R.scrolledBox = { left: box().style.left, width: box().style.width }
  key('Escape')
  process.stdout.write(JSON.stringify(R))
"""
    result = _run(body)
    shown = result["shown"]
    # 오른쪽 끝 = 104 + 104 + 80 + 80 = 368 → 368 − 4, 아래 끝 = 32 + 3 × 30 = 122 → 122 − 4.
    assert shown["hidden"] is False and shown["left"] == "364px" and shown["top"] == "118px"
    assert shown["title"].startswith("끌어서 채우기")
    assert result["editing"] is True and result["after"] is False
    assert result["keysOnly"] is True, "분류 칸만 고르면 채울 값 칸이 없다"
    assert result["overKeys"] is False
    assert result["scrolledHandle"] == "364px", "캔버스 좌표 — 굴려도 같은 자리"
    # 분류 칸 0(고정)에서 202702(c=3) 끝까지 — 왼쪽 0 + 30(굴림), 폭 368 − 30.
    assert result["scrolledBox"] == {"left": "30px", "width": "338px"}


def test_dragging_the_handle_down_fills_from_the_source_rows_and_selects_the_span() -> None:
    body = r"""
  pick(0, 2, 1, 3)
  R.during = drag([5, 3])
  R.filling = scroller.classList.contains('is-filling')
  fire(scroller, 'pointerup', { clientX: xOf(3), clientY: yOf(5), pointerId: 1 })
  R.op = lastOp()
  R.after = { range: range(), anchor: Object.assign({}, S.anchor), note: note(),
    box: box().hidden, filling: scroller.classList.contains('is-filling'),
    preview: [text(2, 2), text(3, 3), text(4, 2), text(5, 3), text(6, 2)],
    source: [text(0, 2), text(1, 3)] }
  await tick(360)
  process.stdout.write(JSON.stringify(Object.assign(R, { sent })))
"""
    result = _run(body)
    during = result["during"]["box"]
    # 원본 ∪ 채울 범위 = 줄 0~5, 칸 2~3 → 왼쪽 208, 위 32, 폭 160, 높이 180.
    assert during == {
        "hidden": False,
        "left": "208px",
        "top": "32px",
        "width": "160px",
        "height": "180px",
    }
    assert result["filling"]
    op = result["op"]
    assert op["op"] == "fill" and op["dir"] == "down" and op["gen"] == "g1"
    assert op["rows"] == [_key(k) for k in (2, 3, 4, 5)]
    assert op["cols"] == ["202701", "202702"]
    assert op["src"] == {"rows": [_key(0), _key(1)], "cols": ["202701", "202702"]}
    after = result["after"]
    assert after["range"] == {"r0": 0, "r1": 5, "c0": 2, "c1": 3}
    assert after["anchor"] == {"r": 0, "c": 2}
    assert after["note"] == "8칸 채움" and after["box"] and not after["filling"]
    # 곧바로 미리보기 — 원본 두 줄이 되풀이된다(0 → 2·4, 1 → 3·5).
    assert after["source"] == ["50%", "55%"]
    assert after["preview"] == ["50%", "55%", "50%", "55%", "74%"]
    draft = _server(result["sent"])
    assert draft is not None
    expected = {
        _key(k): {
            "202701": 0.5 if k % 2 == 0 else 0.54,
            "202702": 0.51 if k % 2 == 0 else 0.55,
        }
        for k in (2, 3, 4, 5)
    }
    assert draft["cells"] == expected, "브라우저 미리보기와 서버 반영이 같은 칸·같은 값"


def test_dragging_up_or_left_fills_away_from_the_source_and_escape_cancels() -> None:
    body = r"""
  pick(6, 4, 7, 5)
  drag([3, 5])
  fire(scroller, 'pointerup', { clientX: xOf(5), clientY: yOf(3), pointerId: 1 })
  R.up = lastOp()
  pick(8, 4, 8, 5)
  drag([8, 1])
  fire(scroller, 'pointerup', { clientX: xOf(1), clientY: yOf(8), pointerId: 1 })
  R.left = { op: lastOp(), note: note(), toast: toastText(), range: range() }
  const count = S.box.ops.length
  pick(9, 2, 9, 2)
  drag([11, 2])
  const esc = key('Escape')
  R.escape = { prevented: esc.defaultPrevented, ops: S.box.ops.length === count,
    box: box().hidden, drag: S.fill.drag, selDrag: S.sel.drag }
  pick(9, 2, 10, 3)
  drag([10, 3])
  fire(scroller, 'pointerup', { clientX: xOf(3), clientY: yOf(10), pointerId: 1 })
  R.inside = S.box.ops.length === count
  await tick(360)
  process.stdout.write(JSON.stringify(Object.assign(R, { sent })))
"""
    result = _run(body)
    up = result["up"]
    assert up["dir"] == "up" and up["cols"] == ["202703", "202704"]
    assert up["rows"] == [_key(k) for k in (5, 4, 3)]
    left = result["left"]
    assert left["op"]["dir"] == "left" and left["op"]["cols"] == ["202702", "202701"]
    assert left["op"]["src"]["cols"] == ["202703", "202704"]
    assert left["note"] == "2칸 채움 · 분류 칸 1칸은 건너뛰었습니다"
    assert left["toast"] == left["note"], "건너뛴 칸 수는 토스트로도"
    assert left["range"] == {"r0": 8, "r1": 8, "c0": 1, "c1": 5}
    assert result["escape"] == {
        "prevented": True,
        "ops": True,
        "box": True,
        "drag": None,
        "selDrag": None,
    }
    assert result["inside"], "범위 안으로 되끌면 아무것도 하지 않는다"
    draft = _server(result["sent"])
    assert draft is not None
    frame = _frame()
    # 위로: 원본 [6, 7] — 바로 위(5)가 원본 끝(7), 그 위(4)가 원본 첫(6), 3 이 다시 7.
    assert draft["cells"]["DEMO_P05\x1fER"] == {
        "202703": frame.loc[7, "202703"],
        "202704": frame.loc[7, "202704"],
    }
    assert draft["cells"]["DEMO_P04\x1f양산"] == {
        "202703": frame.loc[6, "202703"],
        "202704": frame.loc[6, "202704"],
    }
    # 왼쪽: 원본 [202703, 202704] — 202702 ← 202704, 202701 ← 202703.
    assert draft["cells"]["DEMO_P08\x1f양산"] == {
        "202702": frame.loc[8, "202704"],
        "202701": frame.loc[8, "202703"],
    }


def test_ctrl_d_and_ctrl_r_fill_down_and_right_and_explain_when_they_cannot() -> None:
    body = r"""
  pick(2, 2, 4, 3)
  const d = key('d', { ctrlKey: true })
  R.down = { prevented: d.defaultPrevented, stopped: d.stopped, op: lastOp(), note: note(),
    range: range(), preview: [text(3, 2), text(4, 3)] }
  pick(6, 3, 6, 4)
  const hangul = key('ㅇ', { ctrlKey: true, code: 'KeyD' })
  R.oneRow = { prevented: hangul.defaultPrevented, op: lastOp() }
  pick(0, 2, 0, 3)
  const count = S.box.ops.length
  key('d', { ctrlKey: true })
  R.top = { ops: S.box.ops.length === count, note: note() }
  pick(8, 0, 9, 5)
  const r = key('r', { ctrlKey: true })
  R.right = { prevented: r.defaultPrevented, op: lastOp(), note: note(), toast: toastText(),
    range: range() }
  pick(10, 2, 10, 2)
  const before = S.box.ops.length
  key('r', { ctrlKey: true })
  R.firstValue = { ops: S.box.ops.length === before, note: note() }
  pick(10, 0, 10, 1)
  key('r', { ctrlKey: true })
  R.keys = note()
  const shift = key('d', { ctrlKey: true, shiftKey: true })
  const dvorak = key('e', { ctrlKey: true, code: 'KeyD' })
  R.ignored = [shift.defaultPrevented, dvorak.defaultPrevented, S.box.ops.length === before]
  await tick(360)
  process.stdout.write(JSON.stringify(Object.assign(R, { sent })))
"""
    result = _run(body)
    down = result["down"]
    assert down["prevented"] and down["stopped"], "Ctrl+D 책갈피를 막는다"
    assert down["op"]["dir"] == "down" and len(down["op"]["rows"]) == 2
    assert down["op"]["src"]["rows"] == ["DEMO_P02\x1f양산"]
    assert down["note"] == "4칸 채움"
    assert down["range"] == {"r0": 2, "r1": 4, "c0": 2, "c1": 3}, "단축키는 고름을 그대로 둔다"
    assert down["preview"] == ["58%", "59%"]
    one = result["oneRow"]
    assert one["prevented"], "한글 입력 상태(key 「ㅇ」)도 자판 자리 KeyD 로 본다"
    assert one["op"]["rows"] == ["DEMO_P06\x1f양산"]
    assert one["op"]["src"]["rows"] == ["DEMO_P05\x1fER"]
    assert result["top"]["ops"] and result["top"]["note"].startswith("채울 원본이 없습니다")
    right = result["right"]
    assert right["prevented"] and right["op"]["dir"] == "right"
    assert right["op"]["src"]["cols"] == ["202701"]
    assert right["op"]["cols"] == ["202702", "202703", "202704"]
    assert right["note"] == "6칸 채움 · 분류 칸 4칸은 건너뛰었습니다"
    assert right["toast"] == right["note"]
    assert right["range"] == {"r0": 8, "r1": 9, "c0": 0, "c1": 5}
    assert result["firstValue"]["ops"]
    assert result["firstValue"]["note"].startswith("채울 원본이 없습니다")
    assert result["keys"] == "분류 칸은 고칠 수 없습니다"
    assert result["ignored"] == [False, False, True]
    draft = _server(result["sent"])
    assert draft is not None
    frame = _frame()
    assert draft["cells"]["DEMO_P09\x1fER"] == {
        month: frame.loc[9, "202701"] for month in ("202702", "202703", "202704")
    }


def test_ctrl_enter_writes_the_typed_value_into_the_whole_range() -> None:
    body = r"""
  pick(1, 3, 3, 0)
  key('4')
  q('.eg-ed').value = '42%'
  const enter = fire(q('.eg-ed'), 'keydown', { key: 'Enter', ctrlKey: true })
  R.all = { prevented: enter.defaultPrevented, op: lastOp(), edit: S.edit,
    hidden: q('.eg-ed').hidden, range: range(), note: note(),
    preview: [text(1, 2), text(3, 3), text(4, 2)] }
  pick(5, 2, 5, 2)
  key('Enter')
  const count = S.box.ops.length
  fire(q('.eg-ed'), 'keydown', { key: 'Enter', ctrlKey: true })
  R.same = [S.box.ops.length === count, S.edit, range()]
  await tick(360)
  process.stdout.write(JSON.stringify(Object.assign(R, { sent })))
"""
    result = _run(body)
    every = result["all"]
    assert every["prevented"] and every["edit"] is None and every["hidden"]
    op = every["op"]
    assert op["op"] == "write" and op["values"] == [["42%"]]
    assert len(op["rows"]) == 3 and op["cols"] == ["202701", "202702"]
    assert every["range"] == {"r0": 1, "r1": 3, "c0": 0, "c1": 3}, "고름을 그대로 둔다(엑셀)"
    assert every["note"] == "6칸에 같은 값을 넣음 · 분류 칸 6칸은 건너뛰었습니다"
    assert every["preview"] == ["42%", "42%", "66%"]
    assert result["same"] == [True, None, {"r0": 5, "r1": 5, "c0": 2, "c1": 2}]
    draft = _server(result["sent"])
    assert draft is not None
    assert {key: set(row.values()) for key, row in draft["cells"].items()} == {
        _key(k): {0.42} for k in (1, 2, 3)
    }


def test_paste_repeats_a_value_or_a_block_over_an_exact_multiple_selection() -> None:
    body = r"""
  const paste = (value) => fire(scroller, 'paste', { clipboardData: { getData: () => value } })
  pick(0, 2, 4, 4)
  paste('90%\r\n')
  R.one = { op: lastOp(), note: note(), range: range(),
    preview: [text(0, 2), text(4, 4), text(5, 2)] }
  pick(6, 2, 9, 2)
  paste('10%\r\n20%\r\n')
  R.column = { op: lastOp(), preview: [6, 7, 8, 9].map((r) => text(r, 2)) }
  pick(10, 1, 11, 4)
  paste('31%\t32%')
  R.phase = { op: lastOp(), note: note(), toast: toastText(),
    preview: [text(10, 2), text(10, 3), text(11, 4)] }
  pick(0, 5, 2, 5)
  paste('1%\t2%\r\n3%\t4%')
  R.anchor = { op: lastOp(), range: range(), note: note() }
  await tick(360)
  process.stdout.write(JSON.stringify(Object.assign(R, { sent })))
"""
    result = _run(body)
    one = result["one"]
    assert one["op"]["values"] == [["90%"]], "값 하나는 한 벌만 싣고 서버가 되풀이한다"
    assert len(one["op"]["rows"]) == 5 and one["op"]["cols"] == ["202701", "202702", "202703"]
    assert one["note"] == "15칸 붙여넣음 · 고른 범위에 되풀이"
    assert one["range"] == {"r0": 0, "r1": 4, "c0": 2, "c1": 4}
    assert one["preview"] == ["90%", "90%", "70%"]
    column = result["column"]
    assert column["op"]["values"] == [["10%"], ["20%"]] and len(column["op"]["rows"]) == 4
    assert column["preview"] == ["10%", "20%", "10%", "20%"]
    phase = result["phase"]
    # 고른 범위가 분류 칸(c=1)에서 시작 — 엑셀 자리 차례(1 → 31, 2 → 32, 3 → 31, 4 → 32)대로
    # 돌려 싣는다.
    assert phase["op"]["values"] == [["32%", "31%"]]
    assert phase["op"]["cols"] == ["202701", "202702", "202703"]
    assert phase["preview"] == ["32%", "31%", "32%"]
    assert phase["note"] == "6칸 붙여넣음 · 고른 범위에 되풀이 · 분류 칸 2칸은 건너뛰었습니다"
    assert phase["toast"] == phase["note"]
    anchor = result["anchor"]
    assert anchor["op"]["values"] == [["1%"], ["3%"]]
    assert anchor["range"] == {"r0": 0, "r1": 1, "c0": 5, "c1": 5}
    assert anchor["note"] == "2칸 붙여넣음 · 표 끝을 넘은 2칸은 버렸습니다"
    draft = _server(result["sent"])
    assert draft is not None
    cells = draft["cells"]
    assert cells["DEMO_P04\x1f양산"]["202703"] == 0.9
    assert [cells[_key(k)]["202701"] for k in (6, 7, 8, 9)] == [0.1, 0.2, 0.1, 0.2]
    assert cells["DEMO_P11\x1fER"] == {"202701": 0.32, "202702": 0.31, "202703": 0.32}


def test_cleanup_drops_a_fill_drag() -> None:
    body = r"""
  pick(1, 2, 1, 2)
  drag([4, 2])
  const during = S.fill.drag !== null
  cleanup()
  R.after = { during, drag: S.fill.drag, filling: scroller.classList.contains('is-filling'),
    ops: S.box.ops.length }
  process.stdout.write(JSON.stringify(R))
"""
    result = _run(body)
    assert result["after"] == {"during": True, "drag": None, "filling": False, "ops": 0}
