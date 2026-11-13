# Purpose: Space 겹친 순서(설비 0034)의 계약 · 줄 세우기 · 지문 안정을 검증한다.

"""Space 겹친 순서 — 호기끼리 차례와 호기 위로 올린 영역 · 도형(`services/floor_layout_stack`).

순서가 비면 지금과 똑같이 그리고 지문도 순서를 넣기 전과 같아야 한다(배포 직후 편집기 epoch ·
저장 기준 지문이 흔들리지 않게). 저장 왕복 · 거부는 아래 저장소 절이 본다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import pytest
from test_equipment_availability import _baseline, _downtime, _equipment
from test_equipment_scenario_repository import (
    _clone,
    _request,
    _scenario,
    _session,
    _set,
    _with_unit,
)

from capa_simulation.persistence.equipment_repository import (
    DuckDBEquipmentRepository,
    EquipmentLayoutScopeError,
)
from capa_simulation.services.fab_layout import parse_fab_editor_apply
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


# ------------------------------------------------------------------ 저장소(설비 0034)

KEY = ("C1", "1F")
ZONE = {"id": "Z1", "kind": "zone", "x": 10, "y": 10, "w": 20, "h": 10}
SHAPE = {"id": "S1", "kind": "shape", "x": 40, "y": 10, "w": 10, "h": 10}


def _seeded(tmp_path: Path) -> DuckDBEquipmentRepository:
    repository = DuckDBEquipmentRepository(tmp_path / "equipment.duckdb")
    repository.initialize()
    repository.save_snapshot(_baseline(), _equipment(), _downtime())
    return repository


def _stack_rows(repository: DuckDBEquipmentRepository) -> list[tuple[str, str, int]]:
    with duckdb.connect(str(repository.database_path), read_only=True) as connection:
        return [
            (str(kind), str(ref), int(number))
            for kind, ref, number in connection.execute(
                "SELECT item_kind, item_ref, stack_no FROM equipment_ops.floor_layout_stack "
                "ORDER BY item_kind, stack_no, item_ref"
            ).fetchall()
        ]


def _base(repository: DuckDBEquipmentRepository) -> tuple[None, str]:
    return None, floor_layout_fingerprint(
        repository.load_floor_layout_marks(*KEY),
        repository.load_floor_group_labels(*KEY),
        repository.load_floor_layout_stack(*KEY),
    )


def _save_stack(
    repository: DuckDBEquipmentRepository,
    stack: FloorStack,
    *,
    equipment: pd.DataFrame | None = None,
    marks: list[dict[str, Any]] | None = None,
    base: tuple[None, str] | None = None,
) -> None:
    repository.save_space_layout(
        _baseline(),
        _equipment() if equipment is None else equipment,
        _downtime(),
        floor_stacks={KEY: stack},
        floor_marks={KEY: marks} if marks is not None else None,
        floor_layout_bases={KEY: base if base is not None else _base(repository)},
    )


def test_an_official_save_writes_unit_keys_and_raised_marks_and_reads_them_back(
    tmp_path: Path,
) -> None:
    repository = _seeded(tmp_path)
    repository.save_space_layout(
        _baseline(), _equipment(), _downtime(), floor_marks={KEY: [ZONE, SHAPE]}
    )
    revisions = len(repository.list_revisions())

    _save_stack(repository, FloorStack(units=("EQ-02", "EQ-01"), raised=frozenset({"Z1"})))

    keys = repository.load_official_snapshot()
    assert keys is not None
    names = {key: name for name, key in keys.unit_keys.items()}
    stored = repository.load_floor_layout_stack(*KEY)
    assert [names[key] for key in stored.units] == ["EQ-02", "EQ-01"]
    assert stored.raised == frozenset({"Z1"})
    # 층 현행값이라 리비전을 만들지 않는다. 호기 행은 아래 → 위 1 부터, 올림은 0.
    assert len(repository.list_revisions()) == revisions
    assert [(kind, number) for kind, _, number in _stack_rows(repository)] == [
        ("raised", 0),
        ("unit", 1),
        ("unit", 2),
    ]
    assert repository.load_floor_layout_stack("C1", "2F") == EMPTY_STACK


def test_a_renamed_unit_keeps_its_place_and_a_new_unit_gets_its_key_in_the_same_save(
    tmp_path: Path,
) -> None:
    repository = _seeded(tmp_path)
    equipment = _with_unit(_equipment(), "EQ-03", 50.0)
    _save_stack(repository, FloorStack(units=("EQ-03", "EQ-02", "EQ-01")), equipment=equipment)
    snapshot = repository.load_official_snapshot()
    assert snapshot is not None
    keys = snapshot.unit_keys
    assert repository.load_floor_layout_stack(*KEY).units == (
        keys["EQ-03"],
        keys["EQ-02"],
        keys["EQ-01"],
    )
    # 이름을 바꿔도 키가 같아 순서 행은 그대로 그 호기를 가리킨다.
    renamed = _set(snapshot.equipment, "EQ-01", "설비명", "EQ-01B")
    assert snapshot.schedule is not None
    downtime = _set(snapshot.downtime, "EQ-01", "설비명", "EQ-01B")
    repository.save_equipment(
        _request(
            snapshot,
            snapshot.schedule.equipment_scenario_id,
            equipment=renamed,
            downtime=downtime,
            renames={"EQ-01B": "EQ-01"},
        )
    )
    after = repository.load_official_snapshot()
    assert after is not None
    names = {key: name for name, key in after.unit_keys.items()}
    stored = repository.load_floor_layout_stack(*KEY).units
    assert [names[key] for key in stored] == ["EQ-03", "EQ-02", "EQ-01B"]


def test_a_unit_deleted_before_the_save_is_skipped_not_refused(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    _save_stack(repository, FloorStack(units=("EQ-02", "GONE", "EQ-01")))
    snapshot = repository.load_official_snapshot()
    assert snapshot is not None
    keys = snapshot.unit_keys
    assert repository.load_floor_layout_stack(*KEY).units == (keys["EQ-02"], keys["EQ-01"])


def test_marks_saved_without_a_stack_sweep_raised_rows_of_deleted_marks(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    repository.save_space_layout(
        _baseline(), _equipment(), _downtime(), floor_marks={KEY: [ZONE, SHAPE]}
    )
    _save_stack(repository, FloorStack(raised=frozenset({"Z1", "S1"})))
    assert repository.load_floor_layout_stack(*KEY).raised == frozenset({"Z1", "S1"})

    repository.save_space_layout(
        _baseline(),
        _equipment(),
        _downtime(),
        floor_marks={KEY: [SHAPE]},
        floor_layout_bases={KEY: _base(repository)},
    )
    assert repository.load_floor_layout_stack(*KEY).raised == frozenset({"S1"})
    # 같은 저장에서 지운 요소의 올림은 쓰지 않는다 — 텍스트 같은 다른 종류도.
    _save_stack(
        repository,
        FloorStack(raised=frozenset({"S1", "Z1"})),
        marks=[SHAPE, {"id": "T1", "kind": "text", "x": 1, "y": 1, "w": 4, "h": 2}],
    )
    assert repository.load_floor_layout_stack(*KEY).raised == frozenset({"S1"})


def test_a_stack_save_from_an_old_base_is_refused(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    seen = _base(repository)
    _save_stack(repository, FloorStack(units=("EQ-02", "EQ-01")), base=seen)

    with pytest.raises(ValueError, match="겹친 순서·Main 설비명 위치를 다른 사용자가 먼저"):
        _save_stack(repository, FloorStack(units=("EQ-01", "EQ-02")), base=seen)
    # 요소만 고친 저장도 남이 먼저 바꾼 순서 위에서는 거부된다.
    with pytest.raises(ValueError, match="다른 사용자가 먼저"):
        repository.save_space_layout(
            _baseline(),
            _equipment(),
            _downtime(),
            floor_marks={KEY: [ZONE]},
            floor_layout_bases={KEY: seen},
        )
    snapshot = repository.load_official_snapshot()
    assert snapshot is not None
    keys = snapshot.unit_keys
    assert repository.load_floor_layout_stack(*KEY).units == (keys["EQ-02"], keys["EQ-01"])


def test_a_hypothetical_role_refuses_a_stack_and_writes_nothing(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    scenario_id = _clone(repository).equipment_scenario_id
    session = _session(repository, scenario_id)
    revisions = len(repository.list_schedule_revisions(scenario_id))

    with pytest.raises(EquipmentLayoutScopeError, match="겹친 순서는 공식 설비 시나리오에서"):
        repository.save_equipment(
            _request(
                session,
                scenario_id,
                equipment=_set(session.equipment, "EQ-01", "X좌표", 50.0),
                floor_stacks={KEY: FloorStack(units=("EQ-02", "EQ-01"))},
            )
        )
    assert _stack_rows(repository) == []
    assert len(repository.list_schedule_revisions(scenario_id)) == revisions


def test_stack_rows_leave_hypothetical_layout_digests_alone(tmp_path: Path) -> None:
    """순서는 가정 배치 차이에 들지 않는다 — 행이 있어도 가정 리비전의 배치 지문이 그대로다."""
    repository = _seeded(tmp_path)
    scenario_id = _clone(repository).equipment_scenario_id
    session = _session(repository, scenario_id)
    moved = repository.save_equipment(
        _request(session, scenario_id, equipment=_set(session.equipment, "EQ-01", "X좌표", 50.0))
    )
    assert moved.schedule is not None
    digest = moved.schedule.layout_digest
    overlay = repository.load_layout_overlay(moved.schedule.schedule_revision_id).digest()

    _save_stack(repository, FloorStack(units=("EQ-02", "EQ-01"), raised=frozenset()))

    after = _scenario(repository, scenario_id)
    assert after.latest_schedule_revision_id == moved.schedule.schedule_revision_id
    assert repository.load_layout_overlay(moved.schedule.schedule_revision_id).digest() == overlay
    summary = repository.schedule_revision_summary(moved.schedule.schedule_revision_id)
    assert summary is not None and summary.layout_digest == digest


def test_the_fab_editor_refuses_an_order_across_tiers() -> None:
    """FAB 는 같은 겹 안 요소 차례만 바꾼다 — 호기 겹이 없어 순서 값이 오면 거부한다
    (설계 F (가))."""
    with pytest.raises(ValueError, match="FAB 전체 도면에는 호기 위로"):
        parse_fab_editor_apply({"stack": {"units": [], "raised": []}}, (101.0, 62.0))
