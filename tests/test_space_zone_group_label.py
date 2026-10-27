# Purpose: Space 영역 테두리·이름표 정렬과 Main 설비명 위치의 계약·0025 저장·적용을 검사한다.

"""2026-10-23 사용자 요청 둘(모양·저장).

- 영역 요소: 테두리 실선/점선·이름표 왼쪽/가운데/오른쪽. 처음 값은 지금 모습(점선·왼쪽)이고 옛 행(칸
  없음)도 처음 값이다. 영역만 갖고 다른 요소는 늘 처음 값이다. 층·FAB 요소 표 둘(0025).
- Main 설비명 위치: 모듈 묶음마다 가운데·위·아래. 고른 적이 없는 묶음(행 없음)은 모양의 처음 위치 —
  한 줄 묶음(모듈 2·3)은 위, 그 밖은 가운데(2026-10-24 결정 (e), `default_group_label`)다. 설비
  마스터 칸이 아니라 층 현행값(`floor_layout_group_label`, 0025)이고, 층 저장의 동시성 대조(요소와
  함께 본 지문)·적용(`parse_editor_apply` → `next_group_labels`)·Main 설비 이름 바꾸기 따라가기에
  든다.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import duckdb
import pytest
from test_equipment_availability import _baseline, _downtime, _equipment
from test_space_layout_edit import _master, _parse

from capa_simulation.persistence.equipment_migration_runner import load_equipment_migrations
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.fab_layout import (
    FabLayoutMark,
    fab_marks_fingerprint,
    prepare_fab_layout_marks,
)
from capa_simulation.services.floor_layout_mark import (
    GROUP_LABEL_POSITIONS,
    ZONE_BORDER_STYLES,
    ZONE_LABEL_ALIGNS,
    FloorLayoutMark,
    floor_layout_fingerprint,
    marks_fingerprint,
    prepare_floor_layout_marks,
    prepare_group_labels,
)
from capa_simulation.services.space_layout_edit import (
    EditorApply,
    default_group_label,
    module_group_sizes,
    next_group_labels,
)

CANVAS = (100.0, 60.0)
FAB = (101.0, 62.0)
KEY = ("C1", "1F")


def _zone(mark_id: str = "Z1", **values: Any) -> dict[str, Any]:
    mark: dict[str, Any] = {"id": mark_id, "kind": "zone", "x": 10, "y": 10, "w": 20, "h": 10}
    mark.update(values)
    return mark


def _repository(path: Path) -> DuckDBEquipmentRepository:
    repository = DuckDBEquipmentRepository(path)
    repository.initialize()
    return repository


# ------------------------------------------------------------------------------- 영역 계약


def test_zone_looks_are_the_decided_lists_with_the_current_look_first() -> None:
    assert ZONE_BORDER_STYLES == ("dashed", "solid")
    assert ZONE_LABEL_ALIGNS == ("left", "center", "right")
    assert GROUP_LABEL_POSITIONS == ("center", "top", "bottom")


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({}, ("dashed", "left")),
        ({"borderStyle": None, "labelAlign": ""}, ("dashed", "left")),
        ({"borderStyle": "solid", "labelAlign": "center"}, ("solid", "center")),
        ({"borderStyle": " dashed ", "labelAlign": "right"}, ("dashed", "right")),
    ],
)
def test_a_zone_takes_its_border_and_label_alignment(
    values: dict[str, Any], expected: tuple[str, str]
) -> None:
    (floor,) = prepare_floor_layout_marks([_zone(**values)], CANVAS)
    (fab,) = prepare_fab_layout_marks([_zone(**values)], FAB)

    assert (floor.border_style, floor.label_align) == expected
    assert (fab.border_style, fab.label_align) == expected
    assert floor.editor_payload()["borderStyle"] == expected[0]
    assert fab.editor_payload()["labelAlign"] == expected[1]


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"borderStyle": "dotted"}, "테두리 모양을 알 수 없습니다"),
        ({"borderStyle": True}, "테두리 모양을 알 수 없습니다"),
        ({"labelAlign": "middle"}, "이름표 정렬을 알 수 없습니다"),
        ({"labelAlign": 1}, "이름표 정렬을 알 수 없습니다"),
    ],
)
def test_a_zone_look_outside_the_lists_rejects_the_whole_floor(
    values: dict[str, Any], message: str
) -> None:
    """층 단위 전체 교체라 조용히 처음 값으로 내리지 않는다 — 통째로 거부한다."""
    with pytest.raises(ValueError, match=message):
        prepare_floor_layout_marks([_zone(**values)], CANVAS)
    with pytest.raises(ValueError, match=message):
        prepare_fab_layout_marks([_zone(**values)], FAB)


@pytest.mark.parametrize("kind", ["shutter", "door", "column", "text", "arrow"])
def test_other_marks_keep_the_first_look_whatever_is_sent(kind: str) -> None:
    raw = _zone(kind=kind, w=4, h=4, borderStyle="weird", labelAlign="right")
    (mark,) = prepare_floor_layout_marks([raw], CANVAS)

    assert (mark.border_style, mark.label_align) == ("dashed", "left")


def test_cached_payloads_without_zone_looks_rebuild_with_the_first_look() -> None:
    """캐시는 `**payload` 로 다시 만든다. 새 필드가 생기기 전에 실린 모양도 열려야 한다."""
    (floor,) = prepare_floor_layout_marks([_zone()], CANVAS)
    (fab,) = prepare_fab_layout_marks([_zone()], FAB)
    new = ("border_style", "label_align")
    old_floor = {key: value for key, value in asdict(floor).items() if key not in new}
    old_fab = {key: value for key, value in asdict(fab).items() if key not in new}

    assert FloorLayoutMark(**old_floor) == floor
    assert FabLayoutMark(**old_fab) == fab


# ------------------------------------------------------------------------------- 영역 저장


def test_zone_looks_round_trip_and_other_marks_store_null(tmp_path: Path) -> None:
    database = tmp_path / "equipment.duckdb"
    repository = _repository(database)
    repository.save_snapshot(_baseline(), _equipment(), _downtime())
    marks = [
        _zone("PLAIN"),
        _zone("SOLID", y=30, borderStyle="solid", labelAlign="right"),
        {"id": "DOOR", "kind": "door", "x": 50, "y": 0, "w": 4, "h": 4},
    ]

    stored = repository.replace_floor_layout_marks(*KEY, marks)

    assert [(mark.border_style, mark.label_align) for mark in stored] == [
        ("dashed", "left"),
        ("solid", "right"),
        ("dashed", "left"),
    ]
    with duckdb.connect(str(database)) as connection:
        raw = connection.execute(
            "SELECT mark_id, border_style, label_align FROM equipment_ops.floor_layout_mark "
            "ORDER BY source_row_no"
        ).fetchall()
    assert raw == [("PLAIN", "dashed", "left"), ("SOLID", "solid", "right"), ("DOOR", None, None)]
    # 편집기가 돌려보내는 모양 그대로 다시 저장하면 바뀐 것이 없고 리비전도 만들지 않는다.
    resent = prepare_floor_layout_marks([mark.editor_payload() for mark in stored], CANVAS)
    assert marks_fingerprint(resent) == marks_fingerprint(stored)
    before = len(repository.list_revisions())
    assert (
        repository.save_space_layout(
            _baseline(),
            _equipment(),
            _downtime(),
            floor_marks={KEY: [mark.editor_payload() for mark in stored]},
        )
        is None
    )
    assert len(repository.list_revisions()) == before


def test_fab_zone_looks_round_trip(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")
    marks = [
        _zone("Z-A", borderStyle="solid", labelAlign="center"),
        {"id": "B1", "kind": "block", "x": 40, "y": 10, "w": 12, "h": 5, "link": "C1 1F"},
    ]

    repository.save_fab_layout(canvas=None, marks=marks, base=(None, fab_marks_fingerprint(())))
    stored = repository.load_fab_layout_marks()

    assert [(mark.border_style, mark.label_align) for mark in stored] == [
        ("solid", "center"),
        ("dashed", "left"),
    ]


def test_migration_0025_reads_old_zones_as_dashed_left_and_starts_with_no_labels(
    tmp_path: Path,
) -> None:
    """0023 까지 적용된 DB 의 영역은 0025 뒤에 점선·왼쪽으로 읽힌다. 위치 표는 비어 있다."""
    database = tmp_path / "before-0025.duckdb"
    before = [migration for migration in load_equipment_migrations() if migration.version <= 23]
    with duckdb.connect(str(database)) as connection:
        for migration in before:
            connection.execute(migration.sql)
            connection.execute(
                "INSERT INTO equipment_meta.schema_migration (version, name, checksum) "
                "VALUES (?, ?, ?)",
                [migration.version, migration.name, migration.checksum],
            )
        connection.execute(
            """
            INSERT INTO equipment_ops.floor_layout_mark (
                building, floor_name, mark_id, source_row_no, mark_kind,
                x_coordinate, y_coordinate, x_size, y_size, rotation_deg, label, color_key
            ) VALUES ('C1', '1F', 'OLD', 1, 'zone', 1, 1, 20, 10, 0, '창고', 'green')
            """
        )
        connection.execute(
            """
            INSERT INTO equipment_ops.fab_layout_mark (
                mark_id, source_row_no, mark_kind, x_coordinate, y_coordinate, x_size, y_size,
                rotation_deg, label, color_key
            ) VALUES ('Z-OLD', 1, 'zone', 10, 10, 12, 5, 0, '독립동', 'gray')
            """
        )

    repository = DuckDBEquipmentRepository(database)
    assert repository.initialize() == (25, 27, 29, 31, 32)

    (floor,) = repository.load_floor_layout_marks(*KEY)
    (fab,) = repository.load_fab_layout_marks()
    assert (floor.label, floor.border_style, floor.label_align) == ("창고", "dashed", "left")
    assert (fab.border_style, fab.label_align) == ("dashed", "left")
    assert repository.load_floor_group_labels(*KEY) == {}
    with duckdb.connect(str(database)) as connection:
        nullable = {
            (row[0], row[1]): row[2]
            for row in connection.execute(
                """
                SELECT table_name, column_name, is_nullable FROM information_schema.columns
                WHERE table_schema = 'equipment_ops'
                  AND table_name IN ('floor_layout_mark', 'fab_layout_mark')
                  AND column_name IN ('border_style', 'label_align')
                """
            ).fetchall()
        }
    assert nullable == {
        (table, column): "YES"
        for table in ("floor_layout_mark", "fab_layout_mark")
        for column in ("border_style", "label_align")
    }


# ------------------------------------------------------------------------------- 위치 계약


def test_group_labels_keep_every_position_and_sort_by_name() -> None:
    """가운데도 행으로 남는다 — 한 줄 묶음(모듈 2·3)은 처음 위치가 위라 가운데를 고른 것을 지켜야
    한다. 처음 위치인 묶음을 빼는 것은 적용(`next_group_labels`)의 몫이다."""
    assert prepare_group_labels({"G-2": "bottom", " G-1 ": "top", "G-3": "center"}) == {
        "G-1": "top",
        "G-2": "bottom",
        "G-3": "center",
    }
    assert prepare_group_labels({}) == {}


def test_a_one_row_group_starts_above_its_range_and_a_grid_group_in_the_middle() -> None:
    """한 줄 묶음(모듈 2·3 — `module_grid` 의 행이 1)은 범위 바깥 위, 두 줄 이상(넷부터)은
    가운데."""
    assert [default_group_label(count) for count in (2, 3, 4, 5, 9)] == [
        "top",
        "top",
        "center",
        "center",
        "center",
    ]


@pytest.mark.parametrize(
    ("labels", "message"),
    [
        ({"G-1": "left"}, "이름 위치를 알 수 없습니다"),
        ({"G-1": None}, "이름 위치를 알 수 없습니다"),
        ({"": "top"}, "Main 설비 이름이 맞지 않습니다"),
        ({"   ": "top"}, "Main 설비 이름이 맞지 않습니다"),
        ({7: "top"}, "Main 설비 이름이 맞지 않습니다"),
        ({"G-1": "top", " G-1": "bottom"}, "두 번 왔습니다"),
    ],
)
def test_a_bad_group_label_rejects_the_floor(labels: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        prepare_group_labels(labels)


def test_group_label_names_follow_the_master_rule() -> None:
    """Main 설비 이름은 설비 마스터의 Main 설비 칸처럼 길이·글자를 묶지 않는다 — 편집기 적용
    (`_parse_group_labels`)이 받은 이름을 저장이 거부하지 않게(앞뒤 공백만 걷는다)."""
    long_name = "SMP-" + "G" * 40
    assert prepare_group_labels({f" {long_name} ": "top", "G\x1f-1": "bottom"}) == {
        "G\x1f-1": "bottom",
        long_name: "top",
    }


def test_a_long_group_name_applies_and_saves(tmp_path: Path) -> None:
    """설비 마스터가 받은 44자 Main 설비 — 적용(`parse_editor_apply` → `next_group_labels`)이
    받은 위치를 층 저장도 받는다(저장이 거부되면 그 대기분이 다른 「배치 저장」 까지 막는다)."""
    long_name = "SMP-" + "G" * 40
    module = {"Main 설비": long_name, "Xsize": 10, "Ysize": 7}
    master = _master(
        {**module, "설비명": "G1-A", "X좌표": 50.0, "Y좌표": 37.0},
        {**module, "설비명": "G1-B", "X좌표": 60.0, "Y좌표": 37.0},
    )
    items = _items(master)
    applied = _parse(
        {"changes": [], "groupLabels": [{"group": long_name, "position": "top"}]},
        master,
        editor_items=items,
        editor_groups={long_name},
    )
    # 모듈 둘이라 처음 위치가 위다 — 위를 보내면 행이 없고, 아래를 보내야 행이 선다.
    assert next_group_labels({}, applied, module_group_sizes(items)) == {}
    applied = _parse(
        {"changes": [], "groupLabels": [{"group": long_name, "position": "bottom"}]},
        master,
        editor_items=items,
        editor_groups={long_name},
    )
    labels = next_group_labels({}, applied, module_group_sizes(items))
    assert labels == {long_name: "bottom"}

    repository = _repository(tmp_path / "equipment.duckdb")
    repository.save_snapshot(_baseline(), _equipment(), _downtime())
    repository.save_space_layout(
        _baseline(),
        _equipment(),
        _downtime(),
        floor_group_labels={KEY: labels},
        floor_layout_bases={KEY: (None, floor_layout_fingerprint((), {}))},
    )
    assert repository.load_floor_group_labels(*KEY) == {long_name: "bottom"}


def test_the_floor_fingerprint_is_the_marks_fingerprint_until_a_label_is_chosen() -> None:
    """위치를 한 번도 고르지 않은 층은 지문이 요소 지문 그대로다(그 층의 편집 대조가 바뀌지
    않는다)."""
    marks = prepare_floor_layout_marks([_zone()], CANVAS)

    assert floor_layout_fingerprint(marks, {}) == marks_fingerprint(marks)
    top = floor_layout_fingerprint(marks, {"G-1": "top"})
    assert top != marks_fingerprint(marks)
    assert top != floor_layout_fingerprint(marks, {"G-1": "bottom"})
    assert top == floor_layout_fingerprint(marks, {"G-1": "top"})


# ------------------------------------------------------------------------------- 위치 저장


def test_group_labels_save_without_a_revision_and_reload(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")
    repository.save_snapshot(_baseline(), _equipment(), _downtime())
    before = len(repository.list_revisions())

    saved = repository.save_space_layout(
        _baseline(),
        _equipment(),
        _downtime(),
        floor_group_labels={KEY: {"G-1": "top", "G-2": "center", "G-3": "bottom"}},
        floor_layout_bases={KEY: (None, floor_layout_fingerprint((), {}))},
    )

    assert saved is None and len(repository.list_revisions()) == before
    assert repository.load_floor_group_labels(*KEY) == {
        "G-1": "top",
        "G-2": "center",
        "G-3": "bottom",
    }
    assert repository.load_floor_group_labels("C1", "2F") == {}
    # 층 전체 교체 — 빈 목록이면 그 층 위치가 모두 처음 위치로 돌아간다.
    repository.save_space_layout(
        _baseline(), _equipment(), _downtime(), floor_group_labels={KEY: {}}
    )
    assert repository.load_floor_group_labels(*KEY) == {}


def test_a_label_save_from_an_old_base_is_refused(tmp_path: Path) -> None:
    """두 세션이 같은 층을 고친다. 먼저 저장한 위치를 뒤 세션의 옛 목록이 덮지 않는다 — 요소와 함께
    본 지문이 달라 거부된다. 요소만 고친 저장도 남이 먼저 바꾼 위치 위에서는 거부된다."""
    repository = _repository(tmp_path / "equipment.duckdb")
    repository.save_snapshot(_baseline(), _equipment(), _downtime())
    seen = (None, floor_layout_fingerprint(repository.load_floor_layout_marks(*KEY), {}))

    repository.save_space_layout(
        _baseline(),
        _equipment(),
        _downtime(),
        floor_group_labels={KEY: {"G-1": "top"}},
        floor_layout_bases={KEY: seen},
    )

    with pytest.raises(ValueError, match="Main 설비명 위치를 다른 사용자가 먼저 바꿔"):
        repository.save_space_layout(
            _baseline(),
            _equipment(),
            _downtime(),
            floor_group_labels={KEY: {"G-1": "bottom"}},
            floor_layout_bases={KEY: seen},
        )
    with pytest.raises(ValueError, match="다른 사용자가 먼저 바꿔"):
        repository.save_space_layout(
            _baseline(),
            _equipment(),
            _downtime(),
            floor_marks={KEY: [_zone()]},
            floor_layout_bases={KEY: seen},
        )
    assert repository.load_floor_group_labels(*KEY) == {"G-1": "top"}
    fresh = (None, floor_layout_fingerprint((), {"G-1": "top"}))
    repository.save_space_layout(
        _baseline(),
        _equipment(),
        _downtime(),
        floor_group_labels={KEY: {"G-1": "bottom"}},
        floor_layout_bases={KEY: fresh},
    )
    assert repository.load_floor_group_labels(*KEY) == {"G-1": "bottom"}


# ------------------------------------------------------------------------------- 적용


def _group_master() -> Any:
    module = {"Main 설비": "GRP-1", "Xsize": 10, "Ysize": 7}
    other = {"Main 설비": "GRP-2", "Xsize": 10, "Ysize": 7}
    return _master(
        {**module, "설비명": "G1-A", "X좌표": 50.0, "Y좌표": 37.0},
        {**module, "설비명": "G1-B", "X좌표": 60.0, "Y좌표": 37.0},
        {**other, "설비명": "G2-A", "X좌표": 20.0, "Y좌표": 37.0},
        {**other, "설비명": "G2-B", "X좌표": 30.0, "Y좌표": 37.0},
    )


def _items(master: Any) -> list[dict[str, Any]]:
    return [
        {
            "id": str(row["설비명"]),
            "group": row["Main 설비"] if isinstance(row["Main 설비"], str) else None,
            "placed": True,
            "x": row["X좌표"],
            "y": row["Y좌표"],
            "w": row["Xsize"],
            "h": row["Ysize"],
        }
        for row in master.to_dict(orient="records")
    ]


def _parse_labels(payload: dict[str, Any]) -> EditorApply:
    master = _group_master()
    items = _items(master)
    return _parse(
        payload,
        master,
        editor_items=items,
        editor_groups={item["group"] for item in items if item["group"]},
    )


def test_an_apply_carries_the_positions_of_the_loaded_module_groups() -> None:
    applied = _parse_labels(
        {
            "changes": [],
            "groupLabels": [
                {"group": "GRP-1", "position": "top"},
                {"group": "GRP-2", "position": "center"},
            ],
        }
    )

    assert applied.group_labels == (("GRP-1", "top"), ("GRP-2", "center"))
    assert _parse_labels({"changes": []}).group_labels is None


@pytest.mark.parametrize(
    ("labels", "message"),
    [
        ([{"group": "GRP-9", "position": "top"}], "이 편집기에 없는 모듈 묶음"),
        ([{"group": "GRP-1", "position": "left"}], "이름 위치를 알 수 없습니다"),
        (
            [{"group": "GRP-1", "position": "top"}, {"group": "GRP-1", "position": "bottom"}],
            "두 번 왔습니다",
        ),
        ("GRP-1", "목록을 읽지 못했습니다"),
    ],
)
def test_a_bad_position_rejects_the_apply(labels: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _parse_labels({"changes": [], "groupLabels": labels})


def test_a_group_with_a_hidden_module_takes_its_position() -> None:
    """편집기에 모듈 하나만 실리고 형제는 숨은 모듈(레이아웃표시 N — 칸만 차지)인 묶음도 모듈
    묶음이다 — 위치 검증이 숨은 모듈을 함께 센다(`editor_ghosts`)."""
    master = _group_master()
    items = [item for item in _items(master) if item["id"] != "G1-B"]
    ghosts = [{"id": "G1-B", "group": "GRP-1", "x": 60.0, "y": 37.0, "w": 10.0, "h": 7.0}]
    applied = _parse(
        {"changes": [], "groupLabels": [{"group": "GRP-1", "position": "bottom"}]},
        master,
        editor_items=items,
        editor_ghosts=ghosts,
        editor_groups={"GRP-1", "GRP-2"},
    )

    assert applied.group_labels == (("GRP-1", "bottom"),)
    with pytest.raises(ValueError, match="이 편집기에 없는 모듈 묶음"):
        _parse(
            {"changes": [], "groupLabels": [{"group": "GRP-1", "position": "bottom"}]},
            master,
            editor_items=items,
            editor_groups={"GRP-1", "GRP-2"},
        )


def test_the_editor_groups_are_module_groups_only() -> None:
    """한 행짜리 묶음(자기 설비명을 Main 설비로 적은 행)은 이름표가 없다 — 모듈 둘 이상만."""
    items = [
        {"id": "A", "group": "G"},
        {"id": "B", "group": "G"},
        {"id": "S", "group": "S"},
        {"id": "C", "group": "H"},
    ]
    ghosts = [{"id": "D", "group": "H", "x": 1, "y": 1, "w": 1, "h": 1}]

    assert module_group_sizes(items, ghosts) == {"G": 2, "H": 2}


def test_next_labels_replace_loaded_groups_keep_others_and_follow_a_rename() -> None:
    current = {"GRP-1": "bottom", "GRP-2": "top", "GONE": "top"}
    applied = EditorApply(
        changes=(),
        created=(),
        canvas=None,
        marks=None,
        renames=(),
        group_labels=(("GRP-1", "center"), ("GRP-2", "bottom")),
    )

    # 모듈 넷인 GRP-1 은 가운데(처음 위치 — 행 없음)로, GRP-2 는 아래로, 편집기에 없는 GONE 은
    # 그대로.
    assert next_group_labels(current, applied, {"GRP-1": 4, "GRP-2": 4}) == {
        "GONE": "top",
        "GRP-2": "bottom",
    }
    # 다른 층으로 보낸 묶음(보내지 않은 실린 묶음)은 이 층에서 빠진다.
    sent_away = EditorApply(
        changes=(), created=(), canvas=None, marks=None, group_labels=(("GRP-2", "top"),)
    )
    assert next_group_labels(current, sent_away, {"GRP-1": 4, "GRP-2": 4}) == {
        "GONE": "top",
        "GRP-2": "top",
    }


def test_a_one_row_group_keeps_a_centre_row_and_drops_a_return_to_the_top() -> None:
    """한 줄 묶음(모듈 2·3)은 처음 위치가 위다 — 가운데를 고르면 가운데 행이 서고, 위로 되돌리면
    행이 빠진다. 이미 있는 행과 같은 위치를 보낸 묶음(손대지 않은 묶음)은 행을 그대로 둬 아무것도
    고르지 않은 적용이 층 위치 목록을 바꾸지 않는다."""

    def labels_of(*pairs: tuple[str, str]) -> EditorApply:
        return EditorApply(changes=(), created=(), canvas=None, marks=None, group_labels=pairs)

    sizes = {"ROW-2": 2, "ROW-3": 3, "GRID-4": 4}
    chosen = labels_of(("ROW-2", "center"), ("ROW-3", "top"), ("GRID-4", "center"))
    assert next_group_labels({}, chosen, sizes) == {"ROW-2": "center"}
    back = labels_of(("ROW-2", "top"), ("ROW-3", "top"), ("GRID-4", "center"))
    assert next_group_labels({"ROW-2": "center"}, back, sizes) == {}
    # 옛 저장값(가운데 행이 없던 때)의 위 행·가운데 행은 같은 위치가 오면 그대로 남는다.
    untouched = labels_of(("ROW-2", "top"), ("ROW-3", "top"), ("GRID-4", "center"))
    kept = {"ROW-3": "top", "GRID-4": "center"}
    assert next_group_labels(kept, untouched, sizes) == kept


def test_next_labels_follow_a_group_rename_with_or_without_positions() -> None:
    from capa_simulation.services.space_layout_edit import NameChange

    rename = (NameChange(kind="group", old="GRP-1", new="GRP-9"),)
    with_labels = EditorApply(
        changes=(),
        created=(),
        canvas=None,
        marks=None,
        renames=rename,
        group_labels=(("GRP-1", "top"),),
    )
    without = EditorApply(changes=(), created=(), canvas=None, marks=None, renames=rename)

    assert next_group_labels({"GRP-1": "bottom"}, with_labels, {"GRP-1": 4}) == {"GRP-9": "top"}
    assert next_group_labels({"GRP-1": "bottom"}, without, {"GRP-1": 4}) == {"GRP-9": "bottom"}
    # 편집기에 모듈 하나만 실려 묶음이 아닌 채(실린 묶음 밖) 이름을 바꿔도 위치가 따라간다 — 다른
    # 묶음의 위치를 보낸 적용이어도.
    other = EditorApply(
        changes=(),
        created=(),
        canvas=None,
        marks=None,
        renames=rename,
        group_labels=(("GRP-2", "top"),),
    )
    assert next_group_labels({"GRP-1": "bottom"}, other, {"GRP-2": 4}) == {
        "GRP-2": "top",
        "GRP-9": "bottom",
    }
