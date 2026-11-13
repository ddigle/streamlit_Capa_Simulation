# Purpose: Space 겹친 순서(설비 0034)의 계약 · 줄 세우기 · 지문 안정을 검증한다.

"""Space 겹친 순서 — 호기끼리 차례와 호기 위로 올린 영역 · 도형(`services/floor_layout_stack`).

순서가 비면 지금과 똑같이 그리고 지문도 순서를 넣기 전과 같아야 한다(배포 직후 편집기 epoch ·
저장 기준 지문이 흔들리지 않게). 저장 왕복 · 거부는 아래 저장소 절이 본다.
"""

from __future__ import annotations

import pytest

from capa_simulation.services.floor_layout_mark import (
    FloorLayoutMark,
    floor_layout_fingerprint,
    marks_fingerprint,
)
from capa_simulation.services.floor_layout_stack import (
    EMPTY_STACK,
    STACK_UNITS_MAX,
    FloorStack,
    ordered_ids,
    ordered_items,
    prepare_floor_stack,
    raised_ids,
    renamed_stack,
    same_stack,
    stack_fingerprint,
    stack_keys,
    stack_names,
    staged_stack,
)


def _mark(mark_id: str, kind: str) -> FloorLayoutMark:
    return FloorLayoutMark(
        mark_id=mark_id,
        kind=kind,
        x=1.0,
        y=1.0,
        w=4.0,
        h=4.0,
        rotation=0,
        label="",
        color="blue" if kind == "zone" else "",
        hatch=False,
        keep_out=False,
    )


MARKS = (_mark("Z1", "zone"), _mark("S1", "shape"), _mark("T1", "text"))


# ------------------------------------------------------------------ 줄 세우기


def test_an_empty_stack_keeps_the_received_order() -> None:
    ids = ["B", "A", "C"]
    assert ordered_ids(ids, {}, ()) == ids
    items = [{"id": "B"}, {"id": "A"}]
    assert ordered_items(items, EMPTY_STACK) == items


def test_listed_units_come_first_in_their_order_and_the_rest_go_on_top() -> None:
    # 적힌 것은 적힌 차례, 적히지 않은 것(새 호기 · 옮겨 온 호기)은 그 위에 받은 차례다
    # (옮겨 온 것 맨 위).
    ids = ["A", "B", "C", "NEW", "ARRIVED"]
    assert ordered_ids(ids, {}, ("C", "A", "B")) == ["C", "A", "B", "NEW", "ARRIVED"]


def test_listed_units_that_left_the_floor_are_skipped() -> None:
    assert ordered_ids(["A", "B"], {}, ("GONE", "B", "A")) == ["B", "A"]


def test_modules_move_as_a_bundle_and_an_unlisted_module_joins_its_sibling() -> None:
    ids = ["M-1", "X", "M-2", "Y", "M-3"]
    groups: dict[str, str | None] = {"M-1": "M", "M-2": "M", "M-3": "M"}
    # 묶음은 적힌 형제 가운데 가장 아래 자리에 한 덩이로 — 적히지 않은 모듈(M-3)도 형제 자리로 간다.
    assert ordered_ids(ids, groups, ("X", "M-2", "Y", "M-1")) == ["X", "M-2", "M-1", "M-3", "Y"]


def test_ordered_items_reorders_payload_rows_by_id_and_group() -> None:
    items: list[dict[str, str | None]] = [
        {"id": "A", "group": None},
        {"id": "M-1", "group": "M"},
        {"id": "B", "group": None},
        {"id": "M-2", "group": "M"},
    ]
    stack = FloorStack(units=("B", "M-1", "A"))
    assert [item["id"] for item in ordered_items(items, stack)] == ["B", "M-1", "M-2", "A"]


# ------------------------------------------------------------------ 검증


def test_prepare_takes_known_units_and_raised_zones_and_shapes() -> None:
    stack = prepare_floor_stack(
        {"units": ["B", "A"], "raised": ["Z1", "S1"]}, unit_ids={"A", "B"}, marks=MARKS
    )
    assert stack == FloorStack(units=("B", "A"), raised=frozenset({"Z1", "S1"}))


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"units": ["A", "Q"]}, "이 편집기에 없는 호기"),
        ({"units": ["A", "A"]}, "같은 호기가 두 번"),
        ({"raised": ["T1"]}, "영역 · 도형뿐"),
        ({"raised": ["NOPE"]}, "이 층에 없는 요소"),
        ({"raised": ["Z1", "Z1"]}, "같은 id 가 두 번"),
        ({"units": "A"}, "목록을 읽지 못했습니다"),
        ({"units": [3]}, "id 가 맞지 않습니다"),
        ("stack", "읽지 못했습니다"),
    ],
)
def test_prepare_refuses_unknown_repeated_or_wrong_kind_entries(raw: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        prepare_floor_stack(raw, unit_ids={"A", "B"}, marks=MARKS)


def test_prepare_refuses_a_list_over_the_limit() -> None:
    ids = [f"U{k}" for k in range(STACK_UNITS_MAX + 1)]
    with pytest.raises(ValueError, match="까지입니다"):
        prepare_floor_stack({"units": ids}, unit_ids=set(ids), marks=MARKS)


# ------------------------------------------------------------------ 이름 · 키 · 대기분 꼴


def test_names_and_keys_round_trip_and_skip_what_they_do_not_know() -> None:
    stored = FloorStack(units=("k-b", "k-gone", "k-a"), raised=frozenset({"Z1"}))
    named = stack_names(stored, {"k-a": "A", "k-b": "B"})
    assert named == FloorStack(units=("B", "A"), raised=frozenset({"Z1"}))
    assert stack_keys(named, {"A": "k-a", "B": "k-b"}) == FloorStack(
        units=("k-b", "k-a"), raised=frozenset({"Z1"})
    )
    # 지운 호기의 이름은 키가 없어 빠진다.
    assert stack_keys(FloorStack(units=("A", "DELETED")), {"A": "k-a"}).units == ("k-a",)
    assert renamed_stack(named, {"B": "B2"}).units == ("B2", "A")


def test_raised_ids_keep_only_zones_and_shapes_still_on_the_floor() -> None:
    stack = FloorStack(raised=frozenset({"Z1", "T1", "GONE"}))
    assert raised_ids(stack, MARKS) == frozenset({"Z1"})


def test_a_raise_only_apply_does_not_pin_the_unit_order() -> None:
    ids = ["A", "B", "C"]
    applied = FloorStack(units=("A", "B", "C"), raised=frozenset({"Z1"}))
    staged = staged_stack(applied, base=EMPTY_STACK, ids=ids, groups={}, marks=MARKS)
    assert staged == FloorStack(raised=frozenset({"Z1"}))


def test_an_unchanged_unit_order_keeps_the_base_rows_and_a_new_order_replaces_them() -> None:
    ids = ["A", "B", "C"]
    base = FloorStack(units=("C", "A", "B", "OLD"))
    same = staged_stack(
        FloorStack(units=("C", "A", "B")), base=base, ids=ids, groups={}, marks=MARKS
    )
    assert same.units == base.units
    moved = staged_stack(
        FloorStack(units=("A", "C", "B")), base=base, ids=ids, groups={}, marks=MARKS
    )
    assert moved.units == ("A", "C", "B")


def test_same_stack_compares_the_drawn_order_and_the_live_raise() -> None:
    ids = ["A", "B"]
    assert same_stack(FloorStack(units=("A", "B")), EMPTY_STACK, ids=ids, groups={}, marks=MARKS)
    assert same_stack(
        FloorStack(raised=frozenset({"GONE"})), EMPTY_STACK, ids=ids, groups={}, marks=MARKS
    )
    assert not same_stack(
        FloorStack(units=("B", "A")), EMPTY_STACK, ids=ids, groups={}, marks=MARKS
    )
    assert not same_stack(
        FloorStack(raised=frozenset({"S1"})), EMPTY_STACK, ids=ids, groups={}, marks=MARKS
    )


# ------------------------------------------------------------------ 지문


def test_an_empty_stack_leaves_the_floor_fingerprint_as_before() -> None:
    labels = {"MAIN": "top"}
    before_no_labels = floor_layout_fingerprint(MARKS, {})
    before_labels = floor_layout_fingerprint(MARKS, labels)
    assert before_no_labels == marks_fingerprint(MARKS)
    assert floor_layout_fingerprint(MARKS, {}, EMPTY_STACK) == before_no_labels
    assert floor_layout_fingerprint(MARKS, labels, EMPTY_STACK) == before_labels
    assert floor_layout_fingerprint(MARKS, labels, None) == before_labels
    assert stack_fingerprint(EMPTY_STACK) == ""


def test_a_stack_changes_the_floor_fingerprint_with_or_without_labels() -> None:
    stack = FloorStack(units=("k-a",))
    raised = FloorStack(raised=frozenset({"Z1"}))
    for labels in ({}, {"MAIN": "top"}):
        plain = floor_layout_fingerprint(MARKS, labels)
        assert floor_layout_fingerprint(MARKS, labels, stack) != plain
        assert floor_layout_fingerprint(MARKS, labels, raised) != plain
        assert floor_layout_fingerprint(MARKS, labels, stack) != floor_layout_fingerprint(
            MARKS, labels, raised
        )
    assert stack_fingerprint(stack) != stack_fingerprint(FloorStack(units=("k-b",)))
