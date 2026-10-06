# Purpose: Space 도면 요소 이름표 글자 크기·색의 계약·0017 저장 왕복·무변경 재저장을 검사한다.

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import duckdb
import pytest
from test_equipment_availability import _baseline, _downtime, _equipment

from capa_simulation.persistence.equipment_migration_runner import load_equipment_migrations
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.fab_layout import (
    FabLayoutMark,
    fab_marks_fingerprint,
    prepare_fab_layout_marks,
)
from capa_simulation.services.floor_layout_mark import (
    MARK_COLOR_KEYS,
    MARK_FONT_SIZES,
    FloorLayoutMark,
    marks_fingerprint,
    prepare_floor_layout_marks,
)

CANVAS = (100.0, 60.0)
FAB = (101.0, 62.0)


def _mark(mark_id: str = "MK-1", **values: Any) -> dict[str, Any]:
    mark: dict[str, Any] = {"id": mark_id, "kind": "door", "x": 10, "y": 0, "w": 4, "h": 4}
    mark.update(values)
    return mark


def _repository(path: Path) -> DuckDBEquipmentRepository:
    repository = DuckDBEquipmentRepository(path)
    repository.initialize()
    return repository


# ------------------------------------------------------------------------------- 계약


def test_font_sizes_and_colours_are_the_decided_lists() -> None:
    assert MARK_FONT_SIZES == (9, 11, 13, 16, 20, 24)
    assert MARK_COLOR_KEYS == ("blue", "rose", "green", "violet", "sky", "gray")


@pytest.mark.parametrize("kind", ["zone", "shutter", "door", "column", "text", "arrow"])
def test_every_floor_mark_kind_takes_a_font_size_and_colour(kind: str) -> None:
    (mark,) = prepare_floor_layout_marks(
        [_mark(kind=kind, fontSize=16, fontColor="violet", label="이름")], CANVAS
    )

    assert (mark.font_size, mark.font_color) == (16, "violet")
    assert mark.editor_payload()["fontSize"] == 16
    assert mark.editor_payload()["fontColor"] == "violet"


@pytest.mark.parametrize("kind", ["zone", "text", "arrow", "block"])
def test_every_fab_mark_kind_takes_a_font_size_and_colour(kind: str) -> None:
    raw = _mark(kind=kind, fontSize=24.0, fontColor="sky")
    if kind == "block":
        raw["link"] = "C1 1F"
    (mark,) = prepare_fab_layout_marks([raw], FAB)

    assert (mark.font_size, mark.font_color) == (24, "sky")


@pytest.mark.parametrize(("size", "color"), [(None, None), ("", ""), ("자동", "")])
def test_missing_font_values_mean_auto_and_default(size: object, color: object) -> None:
    (mark,) = prepare_floor_layout_marks([_mark(fontSize=size, fontColor=color)], CANVAS)
    (old,) = prepare_floor_layout_marks([_mark()], CANVAS)

    assert (mark.font_size, mark.font_color) == (None, "")
    assert (old.font_size, old.font_color) == (None, "")


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"fontSize": 12}, "글자 크기는 자동 또는 9·11·13·16·20·24"),
        ({"fontSize": 11.5}, "글자 크기는"),
        ({"fontSize": True}, "글자 크기는"),
        ({"fontSize": "큼"}, "글자 크기는"),
        ({"fontColor": "red"}, "글자 색을 알 수 없습니다"),
    ],
)
def test_a_font_value_outside_the_lists_rejects_the_floor(
    values: dict[str, Any], message: str
) -> None:
    """층 단위 전체 교체라 조용히 자동으로 내리지 않는다 — 통째로 거부한다."""
    with pytest.raises(ValueError, match=message):
        prepare_floor_layout_marks([_mark(**values)], CANVAS)
    with pytest.raises(ValueError, match=message):
        prepare_fab_layout_marks([_mark(kind="text", **values)], FAB)


def test_cached_payloads_without_font_fields_rebuild_with_defaults() -> None:
    """캐시는 `**payload` 로 다시 만든다. 새 필드가 생기기 전에 실린 모양도 열려야 한다."""
    (floor,) = prepare_floor_layout_marks([_mark()], CANVAS)
    (fab,) = prepare_fab_layout_marks([_mark(kind="zone")], FAB)
    old_floor = {key: value for key, value in asdict(floor).items() if not key.startswith("font")}
    old_fab = {key: value for key, value in asdict(fab).items() if not key.startswith("font")}

    assert FloorLayoutMark(**old_floor) == floor
    assert FabLayoutMark(**old_fab) == fab


# ------------------------------------------------------------------------------- 저장


def test_floor_font_values_round_trip_and_an_untouched_resave_changes_nothing(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")
    repository.save_snapshot(_baseline(), _equipment(), _downtime())
    marks = [
        _mark("AUTO", label="문"),
        _mark("BIG", kind="column", w=1.5, h=1.5, label="C-1", fontSize=13),
        _mark("INK", kind="text", w=14, h=3, label="메모", fontSize=20, fontColor="rose"),
        _mark("ONLY-INK", kind="zone", w=20, h=10, fontColor="green"),
    ]

    stored = repository.replace_floor_layout_marks("C1", "1F", marks)

    assert [(mark.font_size, mark.font_color) for mark in stored] == [
        (None, ""),
        (13, ""),
        (20, "rose"),
        (None, "green"),
    ]
    with duckdb.connect(str(tmp_path / "equipment.duckdb")) as connection:
        raw = connection.execute(
            "SELECT mark_id, font_size, font_color FROM equipment_ops.floor_layout_mark "
            "ORDER BY source_row_no"
        ).fetchall()
    assert raw[0] == ("AUTO", None, None)
    assert raw[2] == ("INK", 20, "rose")

    # 편집기가 돌려보내는 모양 그대로 다시 검증하면 같은 요소·같은 지문이다(손대지 않은 적용).
    resent = prepare_floor_layout_marks([mark.editor_payload() for mark in stored], CANVAS)
    assert resent == stored
    assert marks_fingerprint(resent) == marks_fingerprint(stored)
    # 리비전도 만들지 않는다.
    before = len(repository.list_revisions())
    assert (
        repository.save_space_layout(
            _baseline(),
            _equipment(),
            _downtime(),
            floor_marks={("C1", "1F"): [mark.editor_payload() for mark in stored]},
        )
        is None
    )
    assert len(repository.list_revisions()) == before
    assert repository.load_floor_layout_marks("C1", "1F") == stored


def test_fab_font_values_round_trip(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")
    marks = [
        {"id": "B1", "kind": "block", "x": 10, "y": 10, "w": 12, "h": 5, "link": "C1 1F"},
        {
            "id": "B2",
            "kind": "block",
            "x": 30,
            "y": 10,
            "w": 12,
            "h": 5,
            "link": "C1 2F",
            "fontSize": 9,
            "fontColor": "blue",
        },
    ]

    repository.save_fab_layout(canvas=None, marks=marks, base=(None, fab_marks_fingerprint(())))
    stored = repository.load_fab_layout_marks()

    assert [(mark.font_size, mark.font_color) for mark in stored] == [(None, ""), (9, "blue")]
    resent = prepare_fab_layout_marks([mark.editor_payload() for mark in stored], FAB)
    assert fab_marks_fingerprint(resent) == fab_marks_fingerprint(stored)


def test_migration_0017_keeps_existing_marks_as_auto_and_default(tmp_path: Path) -> None:
    """0015 까지 적용된 DB 의 요소가 0017 뒤에 자동·기본으로 읽힌다. 열은 NULL 허용이다."""
    database_path = tmp_path / "before-0017.duckdb"
    before = [migration for migration in load_equipment_migrations() if migration.version <= 15]
    with duckdb.connect(str(database_path)) as connection:
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
                x_coordinate, y_coordinate, x_size, y_size, rotation_deg, label
            ) VALUES ('C1', '1F', 'OLD', 1, 'column', 1, 1, 1.5, 1.5, 0, '기둥 A')
            """
        )
        connection.execute(
            """
            INSERT INTO equipment_ops.fab_layout_mark (
                mark_id, source_row_no, mark_kind, x_coordinate, y_coordinate, x_size, y_size,
                rotation_deg, label, link_building, link_floor
            ) VALUES ('B-OLD', 1, 'block', 10, 10, 12, 5, 0, NULL, 'C1', '1F')
            """
        )

    repository = DuckDBEquipmentRepository(database_path)
    assert repository.initialize() == (17,)

    (floor,) = repository.load_floor_layout_marks("C1", "1F")
    (block,) = repository.load_fab_layout_marks()
    assert (floor.label, floor.font_size, floor.font_color) == ("기둥 A", None, "")
    assert (block.font_size, block.font_color) == (None, "")
    with duckdb.connect(str(database_path)) as connection:
        nullable = {
            (row[0], row[1]): row[2]
            for row in connection.execute(
                """
                SELECT table_name, column_name, is_nullable FROM information_schema.columns
                WHERE table_schema = 'equipment_ops'
                  AND column_name IN ('font_size', 'font_color')
                """
            ).fetchall()
        }
    assert nullable == {
        (table, column): "YES"
        for table in ("floor_layout_mark", "fab_layout_mark")
        for column in ("font_size", "font_color")
    }
