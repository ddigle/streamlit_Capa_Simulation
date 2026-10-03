# Purpose: FAB 도면 요소 검증(층 블록 연결 필수·색 키)과 FAB 저장(대조·용량 합계·캐시)을 검사한다.

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from test_equipment_availability import _baseline, _downtime, _equipment
from test_floor_layout_profile import _png

from capa_simulation.persistence import sync_state
from capa_simulation.persistence.equipment_cache import (
    clear_equipment_repository,
    clear_floor_layout_cache,
    load_fab_layout,
)
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services import floor_layout_profile
from capa_simulation.services.fab_layout import (
    FAB_CANVAS,
    FLOOR_KEYS,
    default_fab_layout,
    duplicate_block_links,
    effective_fab_layout,
    fab_marks_fingerprint,
    parse_fab_editor_apply,
    prepare_fab_layout_marks,
)
from capa_simulation.services.floor_layout_mark import MARKS_PER_FLOOR_MAX, marks_extent

CANVAS = (100.0, 60.0)


def _block(mark_id: str = "B1", **values: Any) -> dict[str, Any]:
    mark: dict[str, Any] = {
        "id": mark_id,
        "kind": "block",
        "x": 10,
        "y": 10,
        "w": 12,
        "h": 5,
        "link": "C1 1F",
    }
    mark.update(values)
    return mark


def _repository(path: Path) -> DuckDBEquipmentRepository:
    repository = DuckDBEquipmentRepository(path)
    repository.initialize()
    return repository


def test_a_floor_block_must_point_at_one_of_the_fab_floors() -> None:
    """층 블록은 연결이 필수다 — S.PKG 가 아닌 자리는 블록이 아니라 영역·글자로 그린다."""
    (block,) = prepare_fab_layout_marks([_block(link="C2 3F")], CANVAS)
    assert block.link == ("C2", "3F")
    assert block.editor_payload()["link"] == "C2 3F"

    for link in ("", None, "C9 1F", "C1-1F", "FAB"):
        with pytest.raises(ValueError, match="연결 층"):
            prepare_fab_layout_marks([_block(link=link)], CANVAS)


def test_block_colour_is_default_or_one_of_the_zone_colours() -> None:
    """블록 색은 상태(단계) 색이 아니라 자리 구분 색이다 — 기본(빈 값) 또는 영역과 같은 여섯 색."""
    default, tinted = prepare_fab_layout_marks(
        [_block("B1", color=""), _block("B2", color="green", x=40)], CANVAS
    )
    assert (default.color, tinted.color) == ("", "green")
    for color in ("가용", "red", "입고"):
        with pytest.raises(ValueError, match="색을 알 수 없습니다"):
            prepare_fab_layout_marks([_block(color=color)], CANVAS)


def test_fab_kinds_are_zone_text_arrow_and_block() -> None:
    """반입구·문·기둥은 층 도면 요소라 FAB 에 없다. 영역 색은 층 도면과 같고(비면 회색), 블록이
    아닌 요소에 실린 연결은 버린다."""
    marks = prepare_fab_layout_marks(
        [
            {"id": "Z", "kind": "zone", "x": 0, "y": 0, "w": 30, "h": 20, "link": "C1 1F"},
            {"id": "T", "kind": "text", "x": 0, "y": 30, "w": 10, "h": 3, "rot": 90},
            {"id": "A", "kind": "arrow", "x": 40, "y": 0, "w": 10, "h": 3},
        ],
        CANVAS,
    )
    assert [(mark.kind, mark.color, mark.link) for mark in marks] == [
        ("zone", "gray", None),
        ("text", "", None),
        ("arrow", "", None),
    ]
    # 돌린 글자는 저장·다시 읽기에서 회전을 잃지 않는다.
    assert marks[1].editor_payload()["rot"] == 90
    for kind in ("shutter", "door", "column", "unit"):
        with pytest.raises(ValueError, match="종류를 알 수 없습니다"):
            prepare_fab_layout_marks([_block(kind=kind)], CANVAS)


def test_fab_marks_must_stay_inside_the_canvas_and_under_the_cap() -> None:
    with pytest.raises(ValueError, match="벗어났습니다"):
        prepare_fab_layout_marks([_block(x=95)], CANVAS)
    too_many = [_block(f"B{index}") for index in range(MARKS_PER_FLOOR_MAX + 1)]
    with pytest.raises(ValueError, match="까지입니다"):
        prepare_fab_layout_marks(too_many, CANVAS)


def test_two_blocks_on_one_floor_are_only_a_warning() -> None:
    marks = prepare_fab_layout_marks(
        [_block("B1"), _block("B2", x=40), _block("B3", x=60, link="C2 1F")], CANVAS
    )
    assert duplicate_block_links(marks) == ["C1 1F"]


def test_the_fab_apply_refuses_units_and_checks_the_new_canvas() -> None:
    with pytest.raises(ValueError, match="호기가 없습니다"):
        parse_fab_editor_apply({"changes": [{"id": "EQ-01"}]}, CANVAS)
    applied = parse_fab_editor_apply(
        {"changes": [], "canvas": {"width": 120, "height": 60}, "marks": [_block(x=105)]},
        CANVAS,
    )
    assert applied.canvas == (120.0, 60.0)
    assert applied.marks is not None and applied.marks[0].x == 105.0
    assert parse_fab_editor_apply({"changes": [], "canvas": None, "marks": None}, CANVAS) == (
        parse_fab_editor_apply({}, CANVAS)
    )


def test_without_stored_marks_the_fab_draws_the_default_layout() -> None:
    """요소 행이 없으면 기본 배치를 그린다 — 배경 도면만 먼저 올려도 블록이 사라지지 않는다."""
    canvas, marks = effective_fab_layout(None, ())
    assert (canvas, marks) == default_fab_layout()
    stored = prepare_fab_layout_marks([_block()], CANVAS)
    assert effective_fab_layout(None, stored) == (FAB_CANVAS, stored)


def test_a_fab_save_round_trips_without_a_revision(tmp_path: Path) -> None:
    """FAB 는 설비 리비전과 무관한 현행값이다. 설비 저장본이 없어도 저장하고, 처음 저장은 캔버스
    행도 함께 쓴다."""
    repository = _repository(tmp_path / "equipment.duckdb")
    assert repository.load_fab_layout_profile() is None
    assert repository.load_fab_layout_marks() == ()

    wrote = repository.save_fab_layout(
        canvas=None,
        marks=[
            _block("B1", color="rose"),
            {"id": "Z", "kind": "zone", "x": 0, "y": 30, "w": 40, "h": 20, "hatch": True},
        ],
        base=(None, fab_marks_fingerprint(())),
    )

    assert wrote is True
    assert repository.list_revisions() == []
    profile = repository.load_fab_layout_profile()
    assert profile is not None and profile.canvas_size == FAB_CANVAS
    assert profile.image_data_uri is None
    marks = repository.load_fab_layout_marks()
    assert [(mark.mark_id, mark.link, mark.color) for mark in marks] == [
        ("B1", ("C1", "1F"), "rose"),
        ("Z", None, "gray"),
    ]
    assert marks[1].hatch is True
    # 아무것도 바꾸지 않은 저장은 쓰지 않는다.
    assert repository.save_fab_layout(canvas=None, marks=None, base=None) is False


def test_a_fab_save_refuses_when_someone_else_saved_first(tmp_path: Path) -> None:
    """쓰기 잠금 안에서 처음 본 값과 견준다 — 남이 먼저 저장한 FAB 를 옛 목록으로 덮지 않는다."""
    repository = _repository(tmp_path / "equipment.duckdb")
    start = (None, fab_marks_fingerprint(()))
    repository.save_fab_layout(canvas=None, marks=[_block("THEIRS")], base=start)

    with pytest.raises(ValueError, match="다른 사용자가 먼저"):
        repository.save_fab_layout(canvas=None, marks=[_block("MINE")], base=start)
    with pytest.raises(ValueError, match="다른 사용자가 먼저"):
        repository.save_fab_layout(canvas=(120.0, 70.0), marks=None, base=start)

    assert [mark.mark_id for mark in repository.load_fab_layout_marks()] == ["THEIRS"]
    seen = (FAB_CANVAS, fab_marks_fingerprint(repository.load_fab_layout_marks()))
    repository.save_fab_layout(canvas=(120.0, 70.0), marks=None, base=seen)
    profile = repository.load_fab_layout_profile()
    assert profile is not None and profile.canvas_size == (120.0, 70.0)


def test_the_fab_canvas_cannot_shrink_under_the_drawn_marks(tmp_path: Path) -> None:
    """요소가 없으면 기본 배치가 그려지므로, 그 기본 배치보다 작게 줄이지 못한다."""
    repository = _repository(tmp_path / "equipment.duckdb")
    right, top = marks_extent(default_fab_layout()[1])

    with pytest.raises(ValueError, match="밖에 도면 요소"):
        repository.save_fab_layout_canvas(right - 1, top)
    with pytest.raises(ValueError, match="밖에 도면 요소"):
        repository.save_fab_layout(canvas=(right, top - 1), marks=None, base=None)

    assert repository.save_fab_layout_canvas(right, top).canvas_size == (right, top)
    repository.delete_fab_layout_profile()
    assert repository.load_fab_layout_profile() is None


def test_emptying_the_fab_marks_checks_the_default_layout_against_the_canvas(
    tmp_path: Path,
) -> None:
    """요소를 빈 목록으로 쓰면 기본 배치를 그린다 — 작은 캔버스에서는 그 저장도 거부한다."""
    repository = _repository(tmp_path / "equipment.duckdb")
    repository.save_fab_layout(canvas=None, marks=[_block("SMALL", w=5, h=3)], base=None)
    assert repository.save_fab_layout_canvas(20, 20).canvas_size == (20.0, 20.0)

    with pytest.raises(ValueError, match="기본 배치"):
        repository.save_fab_layout(canvas=None, marks=[], base=None)
    with pytest.raises(ValueError, match="기본 배치"):
        repository.save_fab_layout(canvas=(20.0, 20.0), marks=[], base=None)
    assert [mark.mark_id for mark in repository.load_fab_layout_marks()] == ["SMALL"]

    right, top = marks_extent(default_fab_layout()[1])
    assert repository.save_fab_layout(canvas=(right, top), marks=[], base=None) is True
    assert repository.load_fab_layout_marks() == ()


def test_fab_writes_mark_the_database_dirty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dirty: list[Path] = []
    repository = _repository(tmp_path / "equipment.duckdb")
    monkeypatch.setattr(sync_state, "mark_dirty", dirty.append)

    repository.save_fab_layout(canvas=None, marks=[_block()], base=None)

    assert dirty == [repository.database_path]


def test_the_30mb_budget_counts_floor_and_fab_drawings_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(floor_layout_profile, "MAX_TOTAL_LAYOUT_BYTES", 3_000)
    repository = _repository(tmp_path / "equipment.duckdb")
    payload = _png(101, 62) + bytes(1_500)

    repository.save_floor_layout_image("C1", "1F", "c1_1f.png", payload)
    with pytest.raises(ValueError, match="전체 합계"):
        repository.save_fab_layout_image("fab.png", payload)
    assert repository.load_fab_layout_profile() is None

    repository.delete_floor_layout_profile("C1", "1F")
    saved = repository.save_fab_layout_image(
        "fab.png", payload, canvas_width=FAB_CANVAS[0], canvas_height=FAB_CANVAS[1]
    )
    assert saved.image_name == "fab.png" and str(saved.image_data_uri).startswith("data:image/png")
    # FAB 도면을 다시 올리는 것은 합계가 늘지 않는다. 층 도면은 FAB 와 함께 센다.
    repository.save_fab_layout_image(
        "fab.png", payload, canvas_width=FAB_CANVAS[0], canvas_height=FAB_CANVAS[1]
    )
    with pytest.raises(ValueError, match="전체 합계"):
        repository.save_floor_layout_image("C1", "2F", "c1_2f.png", payload)


def test_a_fab_drawing_keeps_the_default_blocks(tmp_path: Path) -> None:
    """배경 도면만 올려도 요소 행이 없으니 기본 배치가 그대로 그려진다."""
    repository = _repository(tmp_path / "equipment.duckdb")
    repository.save_fab_layout_image("fab.png", _png(1010, 620))

    profile = repository.load_fab_layout_profile()
    assert profile is not None
    canvas, marks = effective_fab_layout(profile, repository.load_fab_layout_marks())
    assert {mark.link for mark in marks if mark.kind == "block"} == set(FLOOR_KEYS)
    assert canvas == profile.canvas_size


def test_clearing_the_floor_layout_cache_also_clears_the_fab(tmp_path: Path) -> None:
    database = tmp_path / "equipment.duckdb"
    repository = _repository(database)
    repository.save_snapshot(_baseline(), _equipment(), _downtime(), note="r1")
    clear_equipment_repository()
    assert load_fab_layout(str(database)) == (None, ())

    repository.save_fab_layout(canvas=None, marks=[_block()], base=None)
    assert load_fab_layout(str(database)) == (None, ())
    clear_floor_layout_cache()

    profile, marks = load_fab_layout(str(database))
    assert profile is not None and [mark.mark_id for mark in marks] == ["B1"]
    clear_equipment_repository()
