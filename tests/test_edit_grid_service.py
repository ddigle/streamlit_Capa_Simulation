# Purpose: 범용 편집 그리드 서비스(업무 키·값 다듬기·op 반영·되돌리기·출납·되머지)를 본다.

from __future__ import annotations

import json
import pickle
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from capa_simulation.services import edit_grid as eg

CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "edit_grid_cases.json").read_text(encoding="utf-8")
)
FORMATS = {
    name: eg.ValueFormat(
        value["kind"],
        value["digits"],
        integer=value["int"],
        min_value=value["min"],
        max_value=value["max"],
        blank_zero=value["blankZero"],
    )
    for name, value in CASES["formats"].items()
}
MONTHS = ("202701", "202702", "202703", "202704")
RATE = eg.ValueFormat("percent", 2, max_value=1.0)


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "공정": ["DEMO_A", "DEMO_B", "DEMO_C", "DEMO_A"],
            "구분": ["양산", "양산", "ER", "양산"],
            "202701": [0.9, 0.8, np.nan, 0.5],
            "202702": [0.9, 0.8, 0.7, 0.5],
            "202703": [0.9, np.nan, 0.7, 0.5],
            "202704": [0.9, 0.8, 0.7, 0.5],
        }
    )


SPEC = eg.GridSpec("RQ_DEMO", "효율", ("공정", "구분"), MONTHS, RATE)


def _index() -> eg.GridIndex:
    return eg.build_index(_frame(), SPEC)


def _plain(draft: eg.DraftState | None) -> object:
    """초안을 dict 와 견주는 꼴로(TypedDict 와 dict 글자 비교를 mypy 가 막는다)."""
    return draft


def _op(kind: str, gen: str, seq: int = 1, **parts: Any) -> eg.Op:
    return eg.Op(mount="m", seq=seq, at=float(seq), table="RQ_DEMO", gen=gen, kind=kind, **parts)


def _apply(
    ops: list[eg.Op], draft: eg.DraftState | None = None, history: eg.HistoryState | None = None
) -> eg.ApplyResult:
    return eg.apply_ops(_index(), SPEC, draft, history or {"gen": "g", "undo": [], "redo": []}, ops)


KEY_A, KEY_B, KEY_C, KEY_A2 = (
    "DEMO_A\x1f양산",
    "DEMO_B\x1f양산",
    "DEMO_C\x1fER",
    "DEMO_A\x1f양산\x1e1",
)


# ------------------------------------------------------------------ 값 다듬기·표시


@pytest.mark.parametrize("case", CASES["coerce"], ids=lambda c: f"{c['fmt']}:{c['raw']!r}")
def test_coerce_gives_the_case_table_answer(case: dict[str, Any]) -> None:
    got = eg.coerce(case["raw"], FORMATS[case["fmt"]], template_value=case["template"])
    assert [got.value, got.error, got.text] == [case["value"], case["error"], case["text"]]


@pytest.mark.parametrize("case", CASES["format"], ids=lambda c: f"{c['fmt']}:{c['value']}")
def test_format_value_gives_the_case_table_answer(case: dict[str, Any]) -> None:
    value = None if case["value"] is None else float(case["value"])
    assert eg.format_value(value, FORMATS[case["fmt"]]) == case["text"]


def test_the_case_table_covers_the_decided_rules() -> None:
    """명세 1-2 의 12 — 사례 표가 결정한 규칙을 빠짐없이 짚는다(40개 이상)."""
    raws = {(case["raw"], case["fmt"]) for case in CASES["coerce"]}
    for needed in (
        ("85%", "rate"),
        (" 0.85 ", "rate"),
        ("85", "rate"),
        ("1,234.5", "upeh"),
        ("1,5", "upeh"),
        ("1e3", "upeh"),
        ("-0", "upeh"),
        ("inf", "upeh"),
        ("NaN", "upeh"),
        ("30.5", "days"),
        ("#N/A", "upeh"),
        ("", "upeh"),
        ("", "count"),
    ):
        assert needed in raws, needed
    assert len(CASES["coerce"]) >= 40
    by_raw = {(c["raw"], c["fmt"], c["template"]): c for c in CASES["coerce"]}
    assert by_raw[("85", "rate", 85.0)]["error"] is None, "양식과 같은 값은 범위 검사를 하지 않는다"
    assert by_raw[("99.99%", "rate", None)]["value"] == 0.9999


# ------------------------------------------------------------------ 업무 키


def test_row_keys_join_raw_values_and_tag_repeats() -> None:
    frame = _frame()
    assert eg.row_keys(frame, ("공정", "구분")) == (KEY_A, KEY_B, KEY_C, KEY_A2)
    assert eg.key_duplicates(frame, ("공정", "구분")) == ((3, 1),)
    numbers = pd.DataFrame({"a": [1, 1, 1], "b": [2.0, None, 2.0]})
    assert eg.row_keys(numbers, ("a", "b")) == ("1\x1f2.0", "1\x1fnan", "1\x1f2.0\x1e1")


def test_the_index_maps_keys_rows_and_months() -> None:
    index = _index()
    assert index.rows[KEY_C] == 2 and index.cols["202703"] == 2
    assert index.template_value(2, 0) is None and index.template_value(0, 0) == 0.9
    with pytest.raises(KeyError):
        eg.build_index(_frame().drop(columns=["202704"]), SPEC)


# ------------------------------------------------------------------ op 반영


def test_a_write_repeats_its_block_over_the_rectangle_and_drops_template_equal_cells() -> None:
    result = _apply(
        [
            _op(
                "write",
                "g",
                rows=(KEY_A, KEY_B, KEY_C),
                cols=MONTHS,
                values=(("50%", "0.6"), ("0.8", None)),
            )
        ]
    )
    assert result.draft is not None and result.changed
    cells = result.draft["cells"]
    assert cells[KEY_A] == {"202701": 0.5, "202702": 0.6, "202703": 0.5, "202704": 0.6}
    # 둘째 줄 덩어리 「0.8, 빈 자리」 — 양식과 같은 0.8 은 초안이 아니고 빈 자리는 그대로 둔다.
    assert cells[KEY_B] == {"202703": 0.8}
    assert cells[KEY_C] == {"202701": 0.5, "202702": 0.6, "202703": 0.5, "202704": 0.6}
    assert eg.change_counts(result.draft) == (9, 3, 0)
    assert len(result.history["undo"]) == 1 and result.acks == {"m": 1}


def test_errors_stay_in_the_cell_and_a_later_good_value_replaces_them() -> None:
    first = _apply([_op("write", "g", rows=(KEY_A,), cols=("202701",), values=(("85",),))])
    assert _plain(first.draft) == {"cells": {}, "bad": {KEY_A: {"202701": ("85", "max")}}}
    assert eg.change_counts(first.draft) == (1, 1, 1)
    second = _apply(
        [_op("write", "g", seq=2, rows=(KEY_A,), cols=("202701",), values=(("85%",),))],
        first.draft,
        first.history,
    )
    assert _plain(second.draft) == {"cells": {KEY_A: {"202701": 0.85}}, "bad": {}}
    back = _apply(
        [_op("write", "g", seq=3, rows=(KEY_A,), cols=("202701",), values=(("90%",),))],
        second.draft,
        second.history,
    )
    assert back.draft is None, "양식과 같은 값이 되면 초안이 사라진다"


def test_clear_and_revert_cover_their_rectangle() -> None:
    cleared = _apply([_op("clear", "g", rows=(KEY_A, KEY_B), cols=("202701", "202703"))])
    assert _plain(cleared.draft) == {
        "cells": {KEY_A: {"202701": None, "202703": None}, KEY_B: {"202701": None}},
        "bad": {},
    }
    reverted = _apply(
        [_op("revert", "g", seq=2, rows=(KEY_A,), cols=("202703",))],
        cleared.draft,
        cleared.history,
    )
    assert _plain(reverted.draft) == {
        "cells": {KEY_A: {"202701": None}, KEY_B: {"202701": None}},
        "bad": {},
    }


def test_blank_cells_turn_into_zero_where_blank_means_zero() -> None:
    spec = eg.GridSpec(
        "RQ_DEMO", "설비대수", ("공정", "구분"), MONTHS, eg.ValueFormat("fixed", 2, blank_zero=True)
    )
    frame = _frame()
    frame[list(MONTHS)] = [[1.0, 2.0, 0.0, 3.0]] * 4
    index = eg.build_index(frame, spec)
    result = eg.apply_ops(
        index,
        spec,
        None,
        {"gen": "g", "undo": [], "redo": []},
        [_op("clear", "g", rows=(KEY_A,), cols=MONTHS)],
    )
    assert _plain(result.draft) == {
        "cells": {KEY_A: {"202701": 0.0, "202702": 0.0, "202704": 0.0}},
        "bad": {},
    }


@pytest.mark.parametrize(
    ("direction", "rows", "cols", "src_rows", "src_cols", "expected"),
    [
        (
            "down",
            (KEY_B, KEY_C, KEY_A2),
            ("202702",),
            (KEY_A,),
            ("202702",),
            {KEY_B: {"202702": 0.9}, KEY_C: {"202702": 0.9}, KEY_A2: {"202702": 0.9}},
        ),
        (
            "up",
            (KEY_B, KEY_A),
            ("202701",),
            (KEY_C, KEY_A2),
            ("202701",),
            # 원본 [C 빈칸, A2 0.5] 를 위로 — 바로 위(B)가 원본 끝(A2), 그 위(A)가 원본 첫(C).
            {KEY_B: {"202701": 0.5}, KEY_A: {"202701": None}},
        ),
        (
            "right",
            (KEY_A, KEY_C),
            ("202702", "202703", "202704"),
            (KEY_A, KEY_C),
            ("202701",),
            {
                KEY_A: {},
                KEY_C: {},
            },
        ),
        (
            "left",
            (KEY_B,),
            ("202702", "202701"),
            (KEY_B,),
            ("202703", "202704"),
            # 원본 [빈칸, 0.8] 을 왼쪽으로 — 바로 왼쪽(202702)이 원본 끝(0.8 — 양식 그대로),
            # 그다음(202701)이 첫(빈칸).
            {KEY_B: {"202701": None}},
        ),
    ],
)
def test_fill_repeats_the_source_away_from_it_in_four_directions(
    direction: str,
    rows: tuple[str, ...],
    cols: tuple[str, ...],
    src_rows: tuple[str, ...],
    src_cols: tuple[str, ...],
    expected: dict[str, dict[str, float | None]],
) -> None:
    result = _apply(
        [
            _op(
                "fill",
                "g",
                rows=rows,
                cols=cols,
                src_rows=src_rows,
                src_cols=src_cols,
                direction=direction,
            )
        ]
    )
    cells = result.draft["cells"] if result.draft else {}
    if direction == "right":
        # A 의 202701 = 0.9 (양식과 같은 칸 — 초안 없음), C 의 202701 = 빈칸 → 오른쪽 셋이 빈칸.
        assert cells == {KEY_C: {"202702": None, "202703": None, "202704": None}}
    else:
        assert cells == {key: row for key, row in expected.items() if row}


def test_fill_reads_the_current_draft_of_its_source() -> None:
    first = _apply([_op("write", "g", rows=(KEY_A,), cols=("202701",), values=(("12%",),))])
    filled = _apply(
        [
            _op(
                "fill",
                "g",
                seq=2,
                rows=(KEY_B,),
                cols=("202701",),
                src_rows=(KEY_A,),
                src_cols=("202701",),
                direction="down",
            )
        ],
        first.draft,
        first.history,
    )
    assert filled.draft is not None
    assert filled.draft["cells"][KEY_B] == {"202701": 0.12}


def test_undo_and_redo_walk_the_steps_and_a_new_edit_clears_redo() -> None:
    write = _op("write", "g", rows=(KEY_A,), cols=("202701",), values=(("10%",),))
    clear = _op("clear", "g", seq=2, rows=(KEY_B,), cols=("202702",))
    done = _apply([write, clear])
    assert eg.change_counts(done.draft) == (2, 2, 0)
    undone = _apply([_op("undo", "g", seq=3)], done.draft, done.history)
    assert _plain(undone.draft) == {"cells": {KEY_A: {"202701": 0.1}}, "bad": {}}
    assert len(undone.history["undo"]) == 1 and len(undone.history["redo"]) == 1
    redone = _apply([_op("redo", "g", seq=4)], undone.draft, undone.history)
    assert redone.draft == done.draft
    again = _apply([_op("undo", "g", seq=5), _op("undo", "g", seq=6)], redone.draft, redone.history)
    assert again.draft is None
    fresh = _apply(
        [_op("write", "g", seq=7, rows=(KEY_C,), cols=("202704",), values=(("1%",),))],
        again.draft,
        again.history,
    )
    assert fresh.history["redo"] == [] and len(fresh.history["undo"]) == 1
    empty = _apply([_op("undo", "g", seq=8), _op("undo", "g", seq=9)], None, None)
    assert empty.toasts == [eg.UNDO_EMPTY_TOAST]


def test_the_history_keeps_forty_steps() -> None:
    ops = [
        _op("write", "g", seq=k + 1, rows=(KEY_A,), cols=("202701",), values=((f"{k}%",),))
        for k in range(45)
    ]
    result = _apply(ops)
    assert len(result.history["undo"]) == eg.UNDO_LIMIT
    steps = result
    for k in range(eg.UNDO_LIMIT):
        steps = _apply([_op("undo", "g", seq=100 + k)], steps.draft, steps.history)
    assert _plain(steps.draft) == {"cells": {KEY_A: {"202701": 0.04}}, "bad": {}}


def test_the_history_drops_old_steps_over_its_cell_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(eg, "HISTORY_CELL_LIMIT", 10)
    ops = [
        _op("clear", "g", seq=1, rows=(KEY_A, KEY_B), cols=MONTHS),
        _op("clear", "g", seq=2, rows=(KEY_C,), cols=MONTHS),
        _op("clear", "g", seq=3, rows=(KEY_A2,), cols=MONTHS),
    ]
    result = _apply(ops)
    assert [step["rows"] for step in result.history["undo"]] == [(KEY_C,), (KEY_A2,)]


def test_ops_from_another_generation_or_table_or_shape_are_dropped_but_acknowledged() -> None:
    ops = [
        _op("write", "old", seq=1, rows=(KEY_A,), cols=("202701",), values=(("1%",),)),
        eg.Op("m", 2, 2.0, "RQ_OTHER", "g", "clear", rows=(KEY_A,), cols=MONTHS),
        eg.Op("m", 3, 3.0, "RQ_DEMO", "g", "bad"),
        _op("write", "g", seq=4, rows=(KEY_A,), cols=("202701",), values=(("2%",),)),
    ]
    result = _apply(ops)
    assert result.acks == {"m": 4}
    assert _plain(result.draft) == {"cells": {KEY_A: {"202701": 0.02}}, "bad": {}}
    assert result.toasts == [eg.DROPPED_TOAST.format(n="3")]


def test_missing_rows_and_unknown_columns_are_skipped_and_counted() -> None:
    result = _apply(
        [
            _op(
                "write",
                "g",
                rows=("없는\x1f키", KEY_A),
                cols=("209912", "202701"),
                values=(("1%", "2%"),),
            )
        ]
    )
    # 덩어리 자리는 op 의 자리 그대로다 — A(둘째 줄)·202701(둘째 칸)에는 「2%」.
    assert _plain(result.draft) == {"cells": {KEY_A: {"202701": 0.02}}, "bad": {}}
    assert result.toasts == [eg.MISSING_ROWS_TOAST.format(n="1")]


def test_a_paste_over_the_cell_limit_is_refused() -> None:
    values = tuple(("1%",) * 100 for _ in range(eg.PASTE_CELL_LIMIT // 100 + 1))
    result = _apply([_op("write", "g", rows=(KEY_A,), cols=("202701",), values=values)])
    assert result.draft is None and not result.changed
    assert result.toasts == [eg.PASTE_LIMIT_TOAST.format(limit=f"{eg.PASTE_CELL_LIMIT:,}")]


def test_apply_does_not_mutate_its_inputs() -> None:
    first = _apply([_op("write", "g", rows=(KEY_A,), cols=("202701",), values=(("1%",),))])
    draft = first.draft
    history = first.history
    snapshot = (pickle.dumps(draft), pickle.dumps(history))
    _apply([_op("clear", "g", seq=2, rows=(KEY_B,), cols=MONTHS)], draft, history)
    assert (pickle.dumps(draft), pickle.dumps(history)) == snapshot


# ------------------------------------------------------------------ 출납 고르기


def _outbox(mount: str, *ops: dict[str, Any]) -> dict[str, Any]:
    return {"mount": mount, "ops": list(ops)}


def _raw(seq: int, at: float, op: str = "undo", **parts: Any) -> dict[str, Any]:
    return {"seq": seq, "at": at, "table": "RQ_DEMO", "gen": "g", "op": op, **parts}


def test_new_ops_pick_unapplied_ops_in_time_order_and_remember_seq() -> None:
    boxes = {
        "grid": _outbox("m2", _raw(1, 30.0), _raw(2, 10.0)),
        "other": _outbox("m1", _raw(4, 20.0), _raw(5, 20.0)),
    }
    ops, memory = eg.new_ops(boxes, {"m1": 4})
    assert [(op.mount, op.seq) for op in ops] == [("m2", 2), ("m1", 5), ("m2", 1)]
    assert memory == {"m2": 2, "m1": 5}
    again, same = eg.new_ops(boxes, memory)
    assert again == [] and same == memory


def test_new_ops_forget_old_mounts_beyond_the_limit() -> None:
    applied = {f"old{k}": 1 for k in range(eg.MOUNT_LIMIT)}
    _, memory = eg.new_ops({"grid": _outbox("new", _raw(1, 1.0))}, applied)
    assert len(memory) == eg.MOUNT_LIMIT and "new" in memory and "old0" not in memory


def test_parse_outbox_keeps_malformed_ops_for_acknowledgement() -> None:
    parsed = eg.parse_outbox(
        _outbox(
            "m",
            _raw(1, 1.0, "write", rows=["a"], cols=["b"], values=[["1", None, 2]]),
            _raw(2, 1.0, "write", rows=["a"], cols=["b"], values="x"),
            _raw(3, 1.0, "nuke"),
            {"seq": "4"},
            _raw(5, 1.0, "fill", rows=["a"], cols=["b"], src={"rows": ["a"], "cols": ["b"]}),
            _raw(
                6, 1.0, "fill", rows=["a"], cols=["b"], src={"rows": ["a"], "cols": ["c"]}, dir="up"
            ),
        )
    )
    assert parsed is not None
    mount, ops = parsed
    assert mount == "m"
    assert [(op.seq, op.kind) for op in ops] == [
        (1, "write"),
        (2, "bad"),
        (3, "bad"),
        (5, "bad"),
        (6, "fill"),
    ]
    assert ops[0].values == (("1", None, 2),)
    assert ops[4].direction == "up" and ops[4].src_cols == ("c",)
    assert eg.parse_outbox({"mount": "", "ops": []}) is None
    assert eg.parse_outbox(None) is None


# ------------------------------------------------------------------ 변경 목록·되머지


def test_the_change_list_runs_in_template_order_with_before_and_after() -> None:
    draft: eg.DraftState = {
        "cells": {KEY_C: {"202701": 0.3}, KEY_A: {"202704": None}, "없음": {"202701": 1.0}},
        "bad": {KEY_A: {"202701": ("x", "num")}},
    }
    entries = eg.change_list(_index(), draft)
    assert [(entry.key, entry.month) for entry in entries] == [
        (KEY_A, "202701"),
        (KEY_A, "202704"),
        (KEY_C, "202701"),
    ]
    assert entries[0].bad == ("x", "num") and entries[0].before == 0.9
    assert entries[2].before is None and entries[2].after == 0.3
    assert eg.change_list(_index(), draft, limit=1) == entries[:1]
    assert eg.change_list(_index(), None) == []


def test_merge_follows_business_keys_even_when_rows_move() -> None:
    draft: eg.DraftState = {
        "cells": {KEY_C: {"202701": 0.3}, KEY_A2: {"202704": None}},
        "bad": {},
    }
    moved = _frame().iloc[[3, 2, 1, 0]].reset_index(drop=True)
    merged = eg.merge_into_template(moved, SPEC, draft)
    # 줄 차례가 바뀐 양식 — 같은 업무 키의 칸에 붙는다. 같은 키가 둘이면 꼬리표는 나온 차례라 두
    # 번째 A 는 바뀐 양식의 셋째 줄 뒤(4번째 줄)다.
    assert merged.loc[1, "202701"] == 0.3
    assert pd.isna(merged.loc[3, "202704"]) and merged.loc[0, "202704"] == 0.5
    assert list(merged.columns) == list(moved.columns)
    with pytest.raises(ValueError):
        eg.merge_into_template(moved, SPEC, {"cells": {}, "bad": {KEY_A: {"202701": ("x", "num")}}})
    assert eg.merge_into_template(moved, SPEC, None).equals(moved)


# ------------------------------------------------------------------ 잰 값(합성 표본 — 샘플 관측)


def _big(rows: int = 2660, months: int = 30) -> tuple[pd.DataFrame, eg.GridSpec]:
    month_names = tuple(f"M{k:02d}" for k in range(months))
    frame = pd.DataFrame(
        {f"K{j}": [f"DEMO_{j}_{i % (5 + j)}" for i in range(rows)] for j in range(8)}
    )
    frame["K8"] = [f"DEMO_ROW_{i}" for i in range(rows)]
    values = np.round(np.random.default_rng(7).uniform(1, 500, size=(rows, 1)), 2)
    for name in month_names:
        frame[name] = values[:, 0]
    spec = eg.GridSpec(
        "RQ_UPEH", "UPEH", tuple(f"K{j}" for j in range(9)), month_names, eg.ValueFormat("sig", 6)
    )
    return frame, spec


def test_clearing_a_whole_large_table_stays_fast_and_small() -> None:
    """명세 12장 — 표 전체 비우기(79,800칸) 반영 목표 ≤ 300 ms, 그 뒤 세션(초안 + 이력) 목표 ≤ 8 MB.
    잰
    값(합성 2,660×30): 반영 약 90 ms · 세션 pickle 약 1.0 MB(시험은 부하가 걸린 관문에서도 돌므로
    상한을 넉넉히 둔다)."""
    frame, spec = _big()
    index = eg.build_index(frame, spec)
    history = eg.new_history()
    clear = eg.Op(
        "m", 1, 1.0, spec.table, history["gen"], "clear", rows=index.keys, cols=spec.value_columns
    )
    began = time.perf_counter()
    result = eg.apply_ops(index, spec, None, history, [clear])
    elapsed = time.perf_counter() - began
    assert eg.change_counts(result.draft)[0] == 2660 * 30
    assert elapsed < 1.5, elapsed
    assert len(pickle.dumps((result.draft, result.history))) < 8_000_000
    undone = eg.apply_ops(
        index,
        spec,
        result.draft,
        result.history,
        [eg.Op("m", 2, 2.0, spec.table, history["gen"], "undo")],
    )
    assert undone.draft is None


def _code_texts() -> dict[str, str]:
    """코어 코드·스크립트·시험의 `.py` 글(파일 → 글)."""
    project = Path(__file__).resolve().parents[1]
    paths = [project / "app.py"]
    for folder in ("app_pages", "src", "scripts", "tests"):
        paths.extend((project / folder).rglob("*.py"))
    return {str(path.relative_to(project)): path.read_text(encoding="utf-8") for path in paths}


def test_every_module_constant_is_used_and_no_comment_points_to_the_old_formats() -> None:
    """이 모듈의 공개 상수는 모두 어딘가에서 쓴다(정의만 남은 죽은 상수가 없다). 옛 편집표의 값
    형식 `reference_data.EDITOR_FORMATS` 는 `reference_grid.GRID_FORMATS` 로 옮겼다 — 주석·설명이
    지운 이름을 가리키지 않는다(옮겼다는 「옛 `EDITOR_FORMATS`」 한 마디만 남는다)(2026-11-03 마지막
    검토 C5)."""
    import ast
    import re

    texts = _code_texts()
    module = ast.parse(Path(eg.__file__).read_text(encoding="utf-8"))
    names = [
        node.target.id
        for node in module.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and not node.target.id.startswith("_")
    ]
    assert names
    dead = [
        name
        for name in names
        if sum(len(re.findall(rf"\b{name}\b", text)) for text in texts.values()) < 2
    ]
    assert dead == []
    pointers = [
        path
        for path, text in texts.items()
        if not path.endswith("test_edit_grid_service.py")
        for line in text.splitlines()
        if "EDITOR_FORMATS" in line and "옛 `EDITOR_FORMATS`" not in line
    ]
    assert pointers == []
