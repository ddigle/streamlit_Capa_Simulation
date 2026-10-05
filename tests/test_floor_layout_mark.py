# Purpose: 층 도면 요소의 검증·층 단위 교체와 리비전·캔버스를 함께 쓰는 저장의 원자성을 검사한다.

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from test_equipment_availability import _baseline, _downtime, _equipment

from capa_simulation.persistence import sync_state
from capa_simulation.persistence.equipment_repository import (
    EMPTY_REVISION_TOKEN,
    DuckDBEquipmentRepository,
)
from capa_simulation.services.equipment_contract import (
    empty_downtime_schedule,
    empty_equipment_baseline,
    empty_equipment_master,
)
from capa_simulation.services.floor_layout_mark import (
    MARKS_PER_FLOOR_MAX,
    marks_extent,
    marks_fingerprint,
    prepare_floor_layout_marks,
)

CANVAS = (100.0, 60.0)


def _mark(mark_id: str = "MK-1", **values: Any) -> dict[str, Any]:
    mark: dict[str, Any] = {"id": mark_id, "kind": "shutter", "x": 10, "y": 0, "w": 12, "h": 5}
    mark.update(values)
    return mark


def _repository(path: Path) -> DuckDBEquipmentRepository:
    repository = DuckDBEquipmentRepository(path)
    repository.initialize()
    return repository


def test_marks_are_normalized_to_the_editor_contract() -> None:
    (zone, door) = prepare_floor_layout_marks(
        [
            _mark(
                "Z1", kind="zone", x=1.04, y=2.06, w=20, h=10, label="  정비 공간 ", keepOut=True
            ),
            _mark("D1", kind="door", rot=90, color="rose", hatch=True),
        ],
        CANVAS,
    )

    assert (zone.x, zone.y, zone.label, zone.color, zone.keep_out) == (
        1.0,
        2.1,
        "정비 공간",
        "gray",
        True,
    )
    assert zone.blocks
    # 영역이 아닌 요소는 색·빗금·설비 금지를 갖지 않는다.
    assert (door.rotation, door.color, door.hatch, door.keep_out) == (90, "", False, False)
    assert door.blocks and door.name == "문"
    assert zone.editor_payload()["keepOut"] is True
    assert marks_extent((zone, door)) == (22.0, 12.1)


@pytest.mark.parametrize(
    ("marks", "message"),
    [
        ([_mark(kind="window")], "종류를 알 수 없습니다"),
        ([_mark("bad id")], "id 는"),
        ([_mark("A"), _mark("A")], "겹칩니다"),
        ([_mark(x=95)], "캔버스 100 × 60 를 벗어났습니다"),
        ([_mark(w=0)], "0 보다 커야"),
        ([_mark(rot=45)], "회전은"),
        ([_mark(x=float("nan"))], "숫자여야"),
        ([_mark(kind="zone", color="purple")], "색을 알 수 없습니다"),
        ([_mark(label="가" * 41)], "40자까지"),
    ],
)
def test_one_bad_mark_rejects_the_whole_list(marks: list[dict[str, Any]], message: str) -> None:
    """층 단위 전체 교체라 하나를 조용히 버리면 그 요소가 지워진다. 그래서 통째로 거부한다."""
    with pytest.raises(ValueError, match=message):
        prepare_floor_layout_marks(marks, CANVAS)


def test_a_floor_holds_at_most_the_mark_limit() -> None:
    marks = [
        _mark(f"M{index}", kind="column", x=0, y=0, w=1, h=1)
        for index in range(MARKS_PER_FLOOR_MAX + 1)
    ]
    with pytest.raises(ValueError, match="까지입니다"):
        prepare_floor_layout_marks(marks, CANVAS)


def test_marks_replace_one_floor_and_keep_the_drawing_order(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")
    repository.replace_floor_layout_marks("C2", "2F", [_mark("OTHER")])

    stored = repository.replace_floor_layout_marks(
        "C1", "1F", [_mark("B", kind="column", w=1.5, h=1.5), _mark("A")]
    )
    assert [mark.mark_id for mark in stored] == ["B", "A"]
    repository.replace_floor_layout_marks("C1", "1F", [_mark("A")])

    assert [mark.mark_id for mark in repository.load_floor_layout_marks("C1", "1F")] == ["A"]
    # 다른 층은 건드리지 않는다.
    assert [mark.mark_id for mark in repository.load_floor_layout_marks("C2", "2F")] == ["OTHER"]
    repository.replace_floor_layout_marks("C1", "1F", [])
    assert repository.load_floor_layout_marks("C1", "1F") == ()
    with pytest.raises(ValueError, match="동은 C1~C5"):
        repository.replace_floor_layout_marks("C9", "1F", [])


def test_revisions_do_not_copy_the_marks(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")
    repository.save_snapshot(
        _baseline(), _equipment(), _downtime(), floor_marks={("C1", "1F"): [_mark()]}
    )
    repository.save_snapshot(_baseline(), _equipment(), _downtime(), note="2차")

    assert len(repository.list_revisions()) == 2
    assert [mark.mark_id for mark in repository.load_floor_layout_marks("C1", "1F")] == ["MK-1"]


def test_a_unit_placed_on_an_enlarged_canvas_saves_with_that_canvas(tmp_path: Path) -> None:
    """캔버스를 넓히고 그 자리에 놓은 호기는 **같은 저장**에서 통과해야 한다."""
    repository = _repository(tmp_path / "equipment.duckdb")
    equipment = _equipment()
    equipment.loc[0, "X좌표"] = 110.0

    with pytest.raises(ValueError, match="캔버스"):
        repository.save_snapshot(_baseline(), equipment, _downtime())
    saved = repository.save_snapshot(
        _baseline(), equipment, _downtime(), floor_canvases={("C1", "1F"): (130.0, 60.0)}
    )

    assert saved.equipment.loc[0, "X좌표"] == 110.0
    assert repository.load_floor_layout_canvases()[("C1", "1F")] == (130.0, 60.0)


def test_a_failed_master_check_writes_neither_canvas_nor_marks(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")
    repository.save_snapshot(_baseline(), _equipment(), _downtime())
    broken = _equipment()
    broken.loc[1, "호기"] = broken.loc[0, "호기"]

    with pytest.raises(ValueError, match="중복"):
        repository.save_snapshot(
            _baseline(),
            broken,
            _downtime(),
            floor_canvases={("C1", "1F"): (150.0, 80.0)},
            floor_marks={("C1", "1F"): [_mark()]},
        )

    assert len(repository.list_revisions()) == 1
    assert ("C1", "1F") not in repository.load_floor_layout_canvases()
    assert repository.load_floor_layout_marks("C1", "1F") == ()


def test_a_layout_only_space_save_makes_no_revision(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")
    repository.save_snapshot(_baseline(), _equipment(), _downtime())

    unchanged = repository.save_space_layout(
        _baseline(), _equipment(), _downtime(), floor_marks={("C1", "1F"): [_mark()]}
    )
    assert unchanged is None
    assert len(repository.list_revisions()) == 1
    assert len(repository.load_floor_layout_marks("C1", "1F")) == 1

    moved = _equipment()
    moved.loc[0, "X좌표"] = 50.0
    changed = repository.save_space_layout(_baseline(), moved, _downtime(), note="배치")
    assert changed is not None and changed.revision.revision_no == 2


def test_a_canvas_cannot_shrink_below_the_stored_marks(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")
    repository.save_snapshot(
        _baseline(), _equipment(), _downtime(), floor_marks={("C1", "1F"): [_mark(x=80, w=12)]}
    )

    with pytest.raises(ValueError, match="도면 요소가 있습니다"):
        repository.save_space_layout(
            _baseline(), _equipment(), _downtime(), floor_canvases={("C1", "1F"): (60.0, 60.0)}
        )
    # 요소를 같은 저장에서 옮기면 통과한다.
    repository.save_space_layout(
        _baseline(),
        _equipment(),
        _downtime(),
        floor_canvases={("C1", "1F"): (60.0, 60.0)},
        floor_marks={("C1", "1F"): [_mark(x=40, w=12)]},
    )
    assert repository.load_floor_layout_canvases()[("C1", "1F")] == (60.0, 60.0)


def test_the_drawing_popup_cannot_shrink_or_delete_the_canvas_below_the_marks(
    tmp_path: Path,
) -> None:
    """팝업 경로(캔버스 저장·도면 업로드·삭제)도 「요소는 캔버스 안」을 지킨다. 요소가 밖에 남으면
    그 층 요소를 다시 저장할 때 손대지 않은 요소 때문에 막힌다."""
    repository = _repository(tmp_path / "equipment.duckdb")
    repository.save_space_layout(
        _baseline(),
        _equipment(),
        _downtime(),
        floor_canvases={("C1", "1F"): (130.0, 60.0)},
        floor_marks={("C1", "1F"): [_mark(kind="column", x=120, w=2, h=2)]},
    )

    with pytest.raises(ValueError, match="밖에 도면 요소가 있습니다"):
        repository.save_floor_layout_canvas("C1", "1F", 100, 60)
    # 지우면 캔버스가 기본 100 × 60 으로 돌아간다 — 요소를 남기므로 거부한다.
    with pytest.raises(ValueError, match="밖에 도면 요소가 있습니다"):
        repository.delete_floor_layout_profile("C1", "1F")
    assert repository.load_floor_layout_canvases()[("C1", "1F")] == (130.0, 60.0)

    repository.replace_floor_layout_marks("C1", "1F", [_mark(kind="column", x=10, w=2, h=2)])
    repository.delete_floor_layout_profile("C1", "1F")
    assert ("C1", "1F") not in repository.load_floor_layout_canvases()
    assert [mark.mark_id for mark in repository.load_floor_layout_marks("C1", "1F")] == ["MK-1"]


def test_a_save_from_a_stale_revision_is_refused(tmp_path: Path) -> None:
    """편집본이 나온 리비전 뒤에 다른 사람이 저장했으면 거부한다 — 옛 편집본이 그 저장을 되돌리지
    않게. 견주기는 쓰기 잠금 안에서 한다."""
    repository = _repository(tmp_path / "equipment.duckdb")
    first = repository.save_snapshot(_baseline(), _equipment(), _downtime())
    other = _equipment()
    other.loc[0, "담당자"] = "담당B"
    repository.save_snapshot(_baseline(), other, _downtime(), note="다른 사람")

    for save in (repository.save_snapshot, repository.save_space_layout):
        with pytest.raises(ValueError, match="먼저 r2를 저장"):
            save(
                _baseline(),
                _equipment(),
                _downtime(),
                floor_marks={("C1", "1F"): [_mark()]},
                base_revision_id=first.revision.revision_id,
            )
    assert len(repository.list_revisions()) == 2
    assert repository.load_floor_layout_marks("C1", "1F") == ()


def test_a_floor_changed_by_someone_else_is_not_overwritten(tmp_path: Path) -> None:
    """요소는 층 전체 교체라 옛 목록으로 덮으면 남의 요소가 지워진다. 편집을 시작할 때 본 값과
    저장 직전 값이 다르면 거부한다."""
    repository = _repository(tmp_path / "equipment.duckdb")
    repository.save_snapshot(_baseline(), _equipment(), _downtime())
    start = repository.load_floor_layout_marks("C1", "1F")
    base = {("C1", "1F"): (None, marks_fingerprint(start))}
    repository.replace_floor_layout_marks("C1", "1F", [_mark("THEIRS")])

    with pytest.raises(ValueError, match="다른 사용자가 먼저 바꿔"):
        repository.save_space_layout(
            _baseline(),
            _equipment(),
            _downtime(),
            floor_marks={("C1", "1F"): [_mark("MINE")]},
            floor_layout_bases=base,
        )
    assert [mark.mark_id for mark in repository.load_floor_layout_marks("C1", "1F")] == ["THEIRS"]

    fresh = repository.load_floor_layout_marks("C1", "1F")
    repository.save_space_layout(
        _baseline(),
        _equipment(),
        _downtime(),
        floor_marks={("C1", "1F"): [*[m.editor_payload() for m in fresh], _mark("MINE", x=40)]},
        floor_layout_bases={("C1", "1F"): (None, marks_fingerprint(fresh))},
    )
    assert len(repository.load_floor_layout_marks("C1", "1F")) == 2


def test_a_space_save_with_nothing_to_write_marks_nothing_dirty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")
    repository.save_snapshot(_baseline(), _equipment(), _downtime())
    dirty: list[Path] = []
    monkeypatch.setattr(sync_state, "mark_dirty", dirty.append)

    assert repository.save_space_layout(_baseline(), _equipment(), _downtime()) is None
    assert dirty == []
    repository.save_space_layout(
        _baseline(), _equipment(), _downtime(), floor_marks={("C1", "1F"): [_mark()]}
    )
    assert len(dirty) == 1


def test_marks_on_an_empty_store_do_not_create_an_empty_revision(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")

    saved = repository.save_space_layout(
        empty_equipment_baseline(),
        empty_equipment_master(),
        empty_downtime_schedule(),
        floor_marks={("C1", "1F"): [_mark()]},
        base_revision_id=EMPTY_REVISION_TOKEN,
    )

    assert saved is None
    assert repository.list_revisions() == []
    assert len(repository.load_floor_layout_marks("C1", "1F")) == 1
