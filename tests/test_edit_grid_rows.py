# Purpose: 범용 편집 그리드의 줄 규칙 표(글 · 고르기 칸 · 업무 키 칸 · 줄 잠금 · 줄 지우기)를 본다.

"""줄 규칙 표 — 2026-11-18 접속 명단 편집 표가 범용 편집 그리드에 더한 몫(`services/edit_grid` 모듈
설명 「글 · 고르기 칸 · 줄 규칙은 고른 표만」). 주지 않은 표의 껍데기 · feed 꼴은 그대로인지도 본다.
값은 모두 합성(`demo.*`)이다."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from capa_simulation.components import edit_grid
from capa_simulation.services import edit_grid as eg
from capa_simulation.services import edit_grid_payload as payload

KINDS = json.loads(
    (Path(__file__).parent / "fixtures" / "edit_grid_cases.json").read_text(encoding="utf-8")
)["kinds"]
OPTIONS = ("열람", "실무자", "관리자", "개발자")
CHOICE = eg.ValueFormat("choice", 0, options=OPTIONS)
ACCOUNT = eg.ValueFormat("text", 0, pattern=r"[a-z.]+", max_length=12)
TEXT = eg.ValueFormat("text", 0)
COLUMNS = ("계정", "이름", "등급")
SPEC = eg.GridSpec(
    "DEMO_ROWS",
    "데모 명단",
    ("No.",),
    COLUMNS,
    TEXT,
    column_formats=(("계정", ACCOUNT), ("이름", TEXT), ("등급", CHOICE)),
    id_column="_id",
    label_column="_label",
    row_ops=True,
)
LISTED = eg.LockKind(cols=("계정",), reason="명단 칸은 잠김")
SELF = eg.LockKind(cols=COLUMNS, reason="나 자신", remove="나 자신은 못 지움")
FRESH = eg.LockKind(cols=(), reason="", fresh=True)
RULES = eg.RowRules((LISTED, SELF, FRESH), (0, 1, 2, 2))


def _formats() -> dict[str, eg.ValueFormat]:
    found: dict[str, eg.ValueFormat] = {}
    for name, value in KINDS["formats"].items():
        found[name] = eg.ValueFormat(
            value["kind"],
            0,
            options=tuple(value.get("options") or ()),
            pattern=value.get("pattern"),
            max_length=value.get("maxLength") or 0,
        )
    return found


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "No.": ["1", "2", "새 1", "새 2"],
            "_id": ["demo.a", "demo.me", "+1", "+2"],
            "_label": ["demo.a", "demo.me", "새 줄 1", "새 줄 2"],
            "계정": ["demo.a", "demo.me", None, None],
            "이름": ["데모 가", None, None, None],
            "등급": [0.0, 3.0, None, None],
        }
    )


def _index() -> eg.GridIndex:
    return eg.build_index(_frame(), SPEC, RULES)


def _plain(draft: eg.DraftState | None) -> object:
    """초안을 dict 와 견주는 꼴로(TypedDict 와 dict 글자 비교를 mypy 가 막는다)."""
    return draft


def _op(kind: str, seq: int = 1, **parts: Any) -> eg.Op:
    return eg.Op(mount="m", seq=seq, at=float(seq), table="DEMO_ROWS", gen="g", kind=kind, **parts)


def _apply(
    ops: list[eg.Op], draft: eg.DraftState | None = None, history: eg.HistoryState | None = None
) -> eg.ApplyResult:
    return eg.apply_ops(_index(), SPEC, draft, history or {"gen": "g", "undo": [], "redo": []}, ops)


# ------------------------------------------------------------------ 글 · 고르기 칸


def test_text_and_choice_values_follow_the_twin_cases() -> None:
    """글 · 고르기 칸 다듬기 · 표시는 사례 표(`tests/fixtures/edit_grid_cases.json` 의 `kinds`) —
    JS(`eg_rows.js` 의 `// <eg-kinds>`)가 같은 사례를 같은 답으로 낸다."""
    formats = _formats()
    for case in KINDS["coerce"]:
        got = eg.coerce(case["raw"], formats[case["fmt"]], template_value=case["template"])
        assert [got.value, got.error, got.text] == [case["value"], case["error"], case["text"]], (
            case
        )
    for case in KINDS["format"]:
        assert eg.format_value(case["value"], formats[case["fmt"]]) == case["text"], case


def test_only_text_and_choice_formats_carry_their_own_fields() -> None:
    """글 · 고르기 형식만 제 칸을 더 싣는다 — 수 형식 껍데기 꼴은 그대로다."""
    assert set(eg.format_payload(eg.ValueFormat("percent", 2))) == {
        "kind",
        "digits",
        "int",
        "min",
        "max",
        "blankZero",
    }
    assert eg.format_payload(CHOICE)["options"] == list(OPTIONS)
    assert eg.format_payload(ACCOUNT)["pattern"] == "[a-z.]+"
    assert eg.format_payload(ACCOUNT)["maxLength"] == 12


# ------------------------------------------------------------------ 색인 · 껍데기 · feed


def test_the_id_column_is_the_business_key_and_text_cells_keep_their_text() -> None:
    index = _index()
    assert index.keys == ("demo.a", "demo.me", "+1", "+2")
    assert index.template_value(0, 0) == "demo.a"
    assert index.template_value(0, 1) == "데모 가"
    assert index.template_value(2, 0) is None
    assert index.template_value(1, 2) == 3.0
    assert index.lock_reason(0, 0) == "명단 칸은 잠김" and index.lock_reason(0, 2) is None
    assert index.remove_lock(1) == "나 자신은 못 지움" and index.is_fresh(3)
    with pytest.raises(ValueError, match="겹칩니다"):
        eg.build_index(_frame().assign(_id=["a", "a", "+1", "+2"]), SPEC)
    with pytest.raises(ValueError, match="줄 수"):
        eg.build_index(_frame(), SPEC, eg.RowRules(RULES.kinds, (0,)))


def test_the_shell_of_a_row_table_carries_its_extra_fields_only_there() -> None:
    base = payload.build_base(_frame(), SPEC, None, RULES)
    body = base.body
    assert body["ids"] == ["demo.a", "demo.me", "+1", "+2"]
    assert body["rowLabels"] == ["demo.a", "demo.me", "새 줄 1", "새 줄 2"]
    assert [fmt["kind"] for fmt in body["fmts"]] == ["text", "text", "choice"]
    assert body["rowOps"] is True and body["dupes"] == []
    assert body["locks"]["rows"] == [0, 1, 2, 2]
    assert body["locks"]["kinds"][1] == {
        "cols": [0, 1, 2],
        "reason": "나 자신",
        "remove": "나 자신은 못 지움",
        "fresh": False,
    }
    assert "demo.a" in body["vals"] and "데모 가" in body["vals"] and 3 in body["vals"]

    plain = eg.GridSpec("RQ_DEMO", "데모", ("공정",), ("202701",), eg.ValueFormat("fixed", 0))
    frame = pd.DataFrame({"공정": ["DEMO_A"], "202701": [3.0]})
    plain_body = payload.build_base(frame, plain, None).body
    for name in ("ids", "rowLabels", "fmts", "locks", "rowOps"):
        assert name not in plain_body, name
    assert not edit_grid.uses_rows(plain_body) and edit_grid.uses_rows(body)


def test_the_feed_names_removed_rows_and_carries_text_values() -> None:
    index = _index()
    draft: eg.DraftState = {
        "cells": {"demo.a": {eg.ROW_REMOVED: 1.0}, "+1": {"계정": "demo.new", "등급": 1.0}},
        "bad": {},
    }
    feed = payload.encode_feed(
        index, draft, eg.new_history(), host="h", base_key="k", acks={}, toast=None
    )
    assert feed["removed"] == [0]
    assert "demo.new" in feed["dvals"] and 1 in feed["dvals"]
    assert feed["counts"] == {"cells": 3, "rows": 2, "errors": 0}
    quiet = payload.encode_feed(
        index, None, eg.new_history(), host="h", base_key="k", acks={}, toast=None
    )
    assert "removed" not in quiet


# ------------------------------------------------------------------ op 반영


def test_locked_cells_are_skipped_and_counted() -> None:
    write = _op(
        "write", rows=("demo.a", "demo.me"), cols=("계정", "등급"), values=(("x", "관리자"),)
    )
    result = _apply([write])
    assert _plain(result.draft) == {"cells": {"demo.a": {"등급": 2.0}}, "bad": {}}
    assert result.toasts == ["잠긴 칸 3칸은 건너뛰었습니다"]


# 계정이 그 줄을 가리키는 명단 줄 둘 · 새 줄 하나(접속 명단 편집 표의 꼴).
ANCHORED = eg.LockKind(cols=("계정", "이름"), reason="명단 칸은 잠김", anchor=("계정",))
ANCHORED_RULES = eg.RowRules((ANCHORED, FRESH), (0, 0, 1))


def _anchored_apply(ops: list[eg.Op]) -> eg.ApplyResult:
    frame = pd.DataFrame(
        {
            "No.": ["1", "2", "새 1"],
            "_id": ["demo.a", "demo.b", "+1"],
            "_label": ["demo.a", "demo.b", "새 줄 1"],
            "계정": ["demo.a", "demo.b", None],
            "이름": ["데모 가", "데모 나", None],
            "등급": [0.0, 0.0, None],
        }
    )
    index = eg.build_index(frame, SPEC, ANCHORED_RULES)
    return eg.apply_ops(index, SPEC, None, {"gen": "g", "undo": [], "redo": []}, ops)


def test_a_paste_whose_account_points_to_another_row_skips_that_row() -> None:
    """차례가 다른 목록(계정 · 등급)을 첫 줄에 붙이면 계정이 다른 줄은 등급까지 건너뛴다 — 그 줄
    사람에게 다른 사람의 등급이 들어가지 않는다."""
    result = _anchored_apply(
        [
            _op(
                "write",
                rows=("demo.a", "demo.b"),
                cols=("계정", "등급"),
                values=(("demo.b", "개발자"), ("demo.a", "열람")),
            )
        ]
    )
    assert result.draft is None and not result.changed
    assert result.history["undo"] == []
    assert result.toasts == ["계정 칸이 다른 줄 2개는 건너뛰었습니다"]


def test_a_paste_in_the_same_order_or_case_still_writes_the_grade() -> None:
    """같은 차례 — 계정이 그 줄과 같으면(앞뒤 공백 · 대소문자만 다름 포함) 잠긴 계정 칸만 건너뛰고
    등급은 쓴다. 한 줄만 어긋나면 그 줄만 건너뛴다."""
    result = _anchored_apply(
        [
            _op(
                "write",
                rows=("demo.a", "demo.b"),
                cols=("계정", "등급"),
                values=((" DEMO.A ", "관리자"), ("demo.x", "개발자")),
            )
        ]
    )
    assert _plain(result.draft) == {"cells": {"demo.a": {"등급": 2.0}}, "bad": {}}
    assert result.toasts == [
        "잠긴 칸 1칸은 건너뛰었습니다",
        "계정 칸이 다른 줄 1개는 건너뛰었습니다",
    ]


def test_grade_only_paste_fill_and_fresh_rows_are_not_anchored() -> None:
    """계정 칸을 싣지 않은 쓰기 · 채우기 · 빈 새 줄의 쓰기는 계정 견줌과 상관없다."""
    result = _anchored_apply(
        [
            _op("write", rows=("demo.a", "demo.b"), cols=("등급",), values=(("실무자",),)),
            _op(
                "fill",
                seq=2,
                rows=("demo.b",),
                cols=("계정", "등급"),
                src_rows=("demo.a",),
                src_cols=("계정", "등급"),
                direction="down",
            ),
            _op(
                "write",
                seq=3,
                rows=("+1",),
                cols=("계정", "이름", "등급"),
                values=(("demo.new", "데모 다", "열람"),),
            ),
        ]
    )
    assert _plain(result.draft) == {
        "cells": {
            "demo.a": {"등급": 1.0},
            "demo.b": {"등급": 1.0},
            "+1": {"계정": "demo.new", "이름": "데모 다", "등급": 0.0},
        },
        "bad": {},
    }
    assert result.toasts == ["잠긴 칸 1칸은 건너뛰었습니다"]


def test_fresh_rows_take_text_and_choice_with_errors_in_place() -> None:
    result = _apply(
        [
            _op(
                "write",
                rows=("+1", "+2"),
                cols=("계정", "이름", "등급"),
                values=(("demo.new", "데모 나", "실무자"), ("Bad Name", "", "모름")),
            )
        ]
    )
    assert _plain(result.draft) == {
        "cells": {"+1": {"계정": "demo.new", "이름": "데모 나", "등급": 1.0}},
        "bad": {"+2": {"계정": ("Bad Name", "pattern"), "등급": ("모름", "choice")}},
    }


def test_filling_a_choice_repeats_its_option() -> None:
    draft: eg.DraftState = {"cells": {"+1": {"등급": 2.0}}, "bad": {}}
    result = _apply(
        [
            _op(
                "fill",
                rows=("+2",),
                cols=("등급",),
                src_rows=("+1",),
                src_cols=("등급",),
                direction="down",
            )
        ],
        draft,
    )
    assert result.draft is not None and result.draft["cells"]["+2"] == {"등급": 2.0}


def test_removing_and_restoring_rows_is_one_undo_step_each() -> None:
    first = _apply([_op("remove", rows=("demo.a", "demo.me", "+1"))])
    assert _plain(first.draft) == {"cells": {"demo.a": {eg.ROW_REMOVED: 1.0}}, "bad": {}}
    assert first.toasts == ["지울 수 없는 줄 1개는 건너뛰었습니다"]
    assert eg.removed_keys(first.draft) == ("demo.a",)
    assert len(first.history["undo"]) == 1

    undone = _apply([_op("undo", seq=2)], first.draft, first.history)
    assert undone.draft is None
    redone = _apply([_op("redo", seq=3)], undone.draft, undone.history)
    assert eg.removed_keys(redone.draft) == ("demo.a",)
    restored = _apply([_op("restore", seq=4, rows=("demo.a",))], redone.draft, redone.history)
    assert restored.draft is None and len(restored.history["undo"]) == 2


def test_removing_a_fresh_row_clears_its_cells() -> None:
    draft: eg.DraftState = {"cells": {"+1": {"계정": "demo.new", "등급": 1.0}}, "bad": {}}
    result = _apply([_op("remove", rows=("+1",))], draft)
    assert result.draft is None
    assert eg.removed_keys(result.draft) == ()
    undone = _apply([_op("undo", seq=2)], result.draft, result.history)
    assert undone.draft == draft


def test_row_ops_on_a_table_without_them_are_dropped() -> None:
    plain = eg.GridSpec("DEMO_ROWS", "데모", ("No.",), COLUMNS, TEXT, id_column="_id")
    index = eg.build_index(_frame(), plain)
    result = eg.apply_ops(
        index, plain, None, {"gen": "g", "undo": [], "redo": []}, [_op("remove", rows=("demo.a",))]
    )
    assert result.draft is None and result.toasts[0].startswith("표가 바뀌기 전에 보낸 편집 1개")


def test_a_bad_row_op_is_dropped_with_its_ack() -> None:
    parsed = eg.parse_outbox(
        {"mount": "m", "ops": [{"seq": 1, "table": "DEMO_ROWS", "gen": "g", "op": "remove"}]}
    )
    assert parsed is not None and parsed[1][0].kind == "bad"


def test_merging_keeps_text_columns_as_text() -> None:
    draft: eg.DraftState = {
        "cells": {"+1": {"계정": "demo.new", "등급": 1.0}, "demo.a": {eg.ROW_REMOVED: 1.0}},
        "bad": {},
    }
    merged = eg.merge_into_template(_frame(), SPEC, draft)
    assert merged["계정"].tolist() == ["demo.a", "demo.me", "demo.new", None]
    assert merged["등급"].tolist()[2] == 1.0
