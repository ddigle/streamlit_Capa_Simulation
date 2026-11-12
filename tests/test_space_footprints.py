# Purpose: Space 발자국 도면 요소(층·FAB)의 저장 계약과 설비 DB 왕복·지문을 검사한다.

"""2026-11-12 Space 시안 보드 6-1 ~ 6-6 — 발자국(`footprints`, 이름 「발자국」).

- 층·FAB 둘 다의 도면 요소다. 저장은 지금 칸 그대로다(상자 · 돌림 · `look_json`) —
  마이그레이션이 없다.
- 선 꼴 요소라 상자의 한 축이 길이, 다른 축이 띠(3칸 고정)다. 0·180° 는 높이가 띠,
  90·270° 는 폭이 띠다. 띠가 3이 아니거나 길이가 3 아래면 저장을 거부한다(조용히 고치지
  않는다).
- 모양 값은 넷 — 발 모양 `foot`(밑창 · 발가락 · 점 · 고양이 · 새 · 구두, 처음 밑창),
  간격 `gap`(좁게 · 보통 · 넓게, 처음 보통), 선 색 `line`(동선과 같은 여덟, 처음 강조색),
  뒤집기 `flip`. 처음 값인 키는 빼고, 다 처음 값이면 빈 글(NULL)이다.
- 발자국이 없는 층·FAB 의 지문은 그대로다(아래 고정 기대값은 바탕 `67086f7` 코드로 잰
  것이다).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pytest
from test_equipment_availability import _baseline, _downtime, _equipment
from test_equipment_layout_overlay_repository import FLOOR, _floor_base, _hypothetical, _seeded
from test_equipment_scenario_repository import _request, _session

from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.fab_layout import (
    FAB_MARK_KINDS,
    FAB_MARK_NAMES,
    fab_layout_fingerprint,
    fab_marks_fingerprint,
    parse_fab_editor_apply,
    prepare_fab_layout_marks,
)
from capa_simulation.services.floor_layout_mark import (
    BLOCKING_MARK_KINDS,
    FOOT_BAND,
    FOOT_GAP_NAMES,
    FOOT_GAPS,
    FOOT_MIN_LENGTH,
    FOOT_SHAPE_NAMES,
    FOOT_SHAPES,
    HATCH_MARK_KINDS,
    LINE_COLOR_KEYS,
    LOOK_DEFAULTS,
    LOOK_KEYS,
    MARK_KINDS,
    MARK_NAMES,
    floor_layout_fingerprint,
    mark_look,
    marks_fingerprint,
    prepare_floor_layout_marks,
)

CANVAS = (100.0, 60.0)
FAB = (101.0, 62.0)


def _foot(mark_id: str = "F1", **values: Any) -> dict[str, Any]:
    mark: dict[str, Any] = {"id": mark_id, "kind": "footprints", "x": 10, "y": 10, "w": 16, "h": 3}
    mark.update(values)
    return mark


# ------------------------------------------------------------------------------- 계약


def test_footprints_are_a_floor_and_fab_mark_named_footprints() -> None:
    """종류 값 `footprints` 는 저장 계약이다(`mark_kind`). 층·FAB 둘 다이고 동선 바로
    뒤다. 막는 요소가 아니고 빗금이 없다."""
    assert MARK_KINDS.index("footprints") == MARK_KINDS.index("arrow") + 1
    assert MARK_NAMES["footprints"] == "발자국"
    assert FAB_MARK_KINDS.index("footprints") == FAB_MARK_KINDS.index("arrow") + 1
    assert FAB_MARK_NAMES["footprints"] == "발자국"
    assert "footprints" not in BLOCKING_MARK_KINDS
    assert "footprints" not in HATCH_MARK_KINDS
    (mark,) = prepare_floor_layout_marks([_foot(keepOut=True, hatch=True, color="blue")], CANVAS)
    assert not mark.blocks and not mark.hatch and mark.color == ""
    assert (mark.border_style, mark.label_align) == ("dashed", "left")


def test_the_band_shapes_gaps_and_look_keys_are_the_decided_ones() -> None:
    """띠 3칸 · 가장 짧은 길이 3칸, 모양 여섯(처음 밑창), 간격 셋(처음 보통), 모양 키 넷 —
    2026-11-12 계획 「정한 것」 그대로(저장 계약)."""
    assert (FOOT_BAND, FOOT_MIN_LENGTH) == (3.0, 3.0)
    assert FOOT_SHAPES == ("sole", "toes", "dots", "cat", "bird", "heel")
    assert [FOOT_SHAPE_NAMES[key] for key in FOOT_SHAPES] == [
        "밑창",
        "발가락",
        "점",
        "고양이",
        "새",
        "구두",
    ]
    assert FOOT_GAPS == ("narrow", "normal", "wide")
    assert [FOOT_GAP_NAMES[key] for key in FOOT_GAPS] == ["좁게", "보통", "넓게"]
    assert LOOK_KEYS["footprints"] == ("foot", "gap", "line", "flip")
    assert LOOK_DEFAULTS["footprints"] == {
        "foot": "sole",
        "gap": "normal",
        "line": "accent",
        "flip": False,
    }


@pytest.mark.parametrize(
    ("rot", "w", "h"),
    [(0, 16, 3), (180, 3, 3), (90, 3, 16), (270, 3, 40.5), (0, 89.9, 3)],
)
def test_the_band_is_three_across_the_walking_axis(rot: int, w: float, h: float) -> None:
    (mark,) = prepare_floor_layout_marks([_foot(rot=rot, w=w, h=h)], CANVAS)
    assert (mark.rotation, mark.w, mark.h) == (rot, w, h)
    (fab,) = prepare_fab_layout_marks([_foot(rot=rot, w=w, h=h)], FAB)
    assert (fab.rotation, fab.w, fab.h) == (rot, w, h)


@pytest.mark.parametrize(
    ("rot", "w", "h", "message"),
    [
        (0, 16, 4, "띠는 3칸이어야 합니다"),
        (0, 16, 2.9, "띠는 3칸이어야 합니다"),
        (90, 16, 3, "띠는 3칸이어야 합니다"),
        (270, 4, 16, "띠는 3칸이어야 합니다"),
        (0, 2.9, 3, "길이는 3칸 이상이어야 합니다"),
        (90, 3, 2, "길이는 3칸 이상이어야 합니다"),
    ],
)
def test_a_band_or_length_off_the_contract_rejects_floor_and_fab(
    rot: int, w: float, h: float, message: str
) -> None:
    """조용히 고치지 않는다 — 층·FAB 단위 전체 교체라 하나라도 어긋나면 저장 전체를 거부한다."""
    with pytest.raises(ValueError, match=message):
        prepare_floor_layout_marks([_foot("OK", y=30), _foot(rot=rot, w=w, h=h)], CANVAS)
    with pytest.raises(ValueError, match=message):
        prepare_fab_layout_marks([_foot(rot=rot, w=w, h=h)], FAB)
    with pytest.raises(ValueError, match=message):
        parse_fab_editor_apply({"marks": [_foot(rot=rot, w=w, h=h)]}, FAB)


@pytest.mark.parametrize(
    ("look", "expected"),
    [
        (None, ""),
        ({}, ""),
        ({"foot": "sole", "gap": "normal", "line": "accent", "flip": False}, ""),
        ({"foot": "cat"}, '{"foot":"cat"}'),
        ({"gap": "wide", "line": "rose"}, '{"gap":"wide","line":"rose"}'),
        ({"flip": True, "foot": "heel"}, '{"flip":true,"foot":"heel"}'),
        ('{"gap":"narrow"}', '{"gap":"narrow"}'),
        ({"foot": None, "gap": None}, ""),
    ],
)
def test_a_footprints_look_is_canonical_json_off_the_defaults(look: Any, expected: str) -> None:
    assert mark_look({"look": look}, "footprints", "F1") == expected


def test_every_shape_gap_and_line_colour_is_accepted() -> None:
    for foot in FOOT_SHAPES:
        for gap in FOOT_GAPS:
            for line in LINE_COLOR_KEYS:
                mark_look({"look": {"foot": foot, "gap": gap, "line": line}}, "footprints", "F1")


@pytest.mark.parametrize(
    ("look", "message"),
    [
        ({"foot": "dog"}, "발 모양을 알 수 없습니다"),
        ({"gap": "huge"}, "간격을 알 수 없습니다"),
        ({"line": "auto"}, "선 색을 알 수 없습니다"),
        ({"flip": "Y"}, "뒤집기 값은 참·거짓이어야 합니다"),
        ({"lineWidth": 2}, "없는 모양 값입니다"),
        ({"head": "MM"}, "없는 모양 값입니다"),
        ({"shape": "rect"}, "없는 모양 값입니다"),
        ("{not json", "모양 값을 읽지 못했습니다"),
    ],
)
def test_a_look_off_the_lists_rejects_the_floor_and_the_fab(look: Any, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        prepare_floor_layout_marks([_foot(look=look)], CANVAS)
    with pytest.raises(ValueError, match=message):
        prepare_fab_layout_marks([_foot(look=look)], FAB)


def test_the_payload_carries_the_look_and_resends_to_the_same_marks() -> None:
    marks = prepare_floor_layout_marks(
        [
            _foot("F1", look={"foot": "bird", "gap": "narrow"}, label="입구 동선", fontSize=13),
            _foot("F2", x=50, y=20, w=3, h=20, rot=90, look={"flip": True, "line": "ink"}),
            _foot("F3", y=40),
        ],
        CANVAS,
    )
    assert marks[0].editor_payload()["look"] == {"foot": "bird", "gap": "narrow"}
    assert marks[0].label == "입구 동선" and marks[0].font_size == 13
    assert "look" not in marks[2].editor_payload()
    again = prepare_floor_layout_marks([mark.editor_payload() for mark in marks], CANVAS)
    assert again == marks
    assert marks_fingerprint(again) == marks_fingerprint(marks)


# ------------------------------------------------------------------------------- 지문 안정


def test_floors_and_the_fab_without_footprints_keep_their_fingerprints() -> None:
    """발자국을 더해도 발자국이 없는 층·FAB 의 지문(편집 시작 대조 · 뷰어 epoch)은
    그대로다. 기대값은 바탕 `67086f7` 코드로 같은 요소를 넣어 잰 것이다."""
    floor = prepare_floor_layout_marks(
        [
            {
                "id": "Z1",
                "kind": "zone",
                "x": 1,
                "y": 1,
                "w": 20,
                "h": 12,
                "label": "창고",
                "color": "green",
            },
            {"id": "A1", "kind": "arrow", "x": 30, "y": 5, "w": 16, "h": 3, "look": {"head": "LS"}},
            {"id": "B1", "kind": "bay", "x": 50, "y": 5, "w": 10, "h": 4, "label": "80"},
            {
                "id": "S1",
                "kind": "shape",
                "x": 70,
                "y": 5,
                "w": 8,
                "h": 6,
                "look": {"shape": "lbox"},
            },  # noqa: E501
        ],
        CANVAS,
    )
    fab = prepare_fab_layout_marks(
        [
            {"id": "A1", "kind": "arrow", "x": 30, "y": 5, "w": 16, "h": 3},
            {"id": "K1", "kind": "block", "x": 40, "y": 20, "w": 12, "h": 5, "link": "C1 1F"},
        ],
        FAB,
    )
    assert (
        marks_fingerprint(floor)
        == "1a03118fd71487d26557c21f96278d1b65f2ac6d9afa8a4e7f2bb2b00fbbe146"
    )
    assert (
        floor_layout_fingerprint(floor, {"G": "top"})
        == "ee6d5f5ea49d013012c89660bf2739d411a37208d67d77786241f1238fd900e6"
    )
    assert (
        fab_marks_fingerprint(fab)
        == "54c34333c727e5d6fc2195109cf12cc086a4055ff0d5daa491e8b1fe8c701e48"
    )
    assert (
        fab_layout_fingerprint(FAB, fab)
        == "1014cdc47ba3de34d009b139cb41ed15a86915aca73f5b7f1dfad7b4e8919b53"
    )


# ------------------------------------------------------------------------------- 저장


def _repository(path: Path) -> DuckDBEquipmentRepository:
    repository = DuckDBEquipmentRepository(path)
    repository.initialize()
    return repository


def test_floor_footprints_round_trip_and_default_looks_store_null(tmp_path: Path) -> None:
    database = tmp_path / "equipment.duckdb"
    repository = _repository(database)
    repository.save_snapshot(_baseline(), _equipment(), _downtime())
    marks = [
        _foot("PLAIN"),
        _foot("CAT", y=20, look={"foot": "cat", "gap": "wide", "line": "violet"}),
        _foot("TURNED", x=60, y=5, w=3, h=30, rot=270, look={"flip": True}),
    ]

    stored = repository.replace_floor_layout_marks("C1", "1F", marks)

    assert [(mark.kind, mark.rotation, mark.w, mark.h, mark.look) for mark in stored] == [
        ("footprints", 0, 16.0, 3.0, ""),
        ("footprints", 0, 16.0, 3.0, '{"foot":"cat","gap":"wide","line":"violet"}'),
        ("footprints", 270, 3.0, 30.0, '{"flip":true}'),
    ]
    assert repository.load_floor_layout_marks("C1", "1F") == stored
    with duckdb.connect(str(database)) as connection:
        raw = connection.execute(
            "SELECT mark_id, mark_kind, look_json FROM equipment_ops.floor_layout_mark "
            "ORDER BY source_row_no"
        ).fetchall()
    assert raw == [
        ("PLAIN", "footprints", None),
        ("CAT", "footprints", '{"foot":"cat","gap":"wide","line":"violet"}'),
        ("TURNED", "footprints", '{"flip":true}'),
    ]
    # 편집기가 돌려보내는 모양 그대로 다시 저장하면 바뀐 것이 없고 리비전도 만들지 않는다.
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


def test_a_floor_save_with_a_bad_band_writes_nothing(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")
    repository.save_snapshot(_baseline(), _equipment(), _downtime())
    repository.replace_floor_layout_marks("C1", "1F", [_foot("KEEP")])

    with pytest.raises(ValueError, match="띠는 3칸이어야 합니다"):
        repository.replace_floor_layout_marks("C1", "1F", [_foot("BAD", h=5)])

    assert [mark.mark_id for mark in repository.load_floor_layout_marks("C1", "1F")] == ["KEEP"]


def test_fab_footprints_round_trip(tmp_path: Path) -> None:
    database = tmp_path / "equipment.duckdb"
    repository = _repository(database)
    marks = [
        _foot("F-DOTS", look={"foot": "dots", "line": "sky"}),
        _foot("F-PLAIN", y=30, x=5, w=3, h=20, rot=90),
        {"id": "B1", "kind": "block", "x": 40, "y": 10, "w": 12, "h": 5, "link": "C1 1F"},
    ]

    repository.save_fab_layout(canvas=None, marks=marks, base=(None, fab_marks_fingerprint(())))

    loaded = repository.load_fab_layout_marks()
    assert [(mark.kind, mark.rotation, mark.look) for mark in loaded] == [
        ("footprints", 0, '{"foot":"dots","line":"sky"}'),
        ("footprints", 90, ""),
        ("block", 0, ""),
    ]
    with duckdb.connect(str(database)) as connection:
        raw = connection.execute(
            "SELECT mark_kind, look_json FROM equipment_ops.fab_layout_mark ORDER BY source_row_no"
        ).fetchall()
    assert raw == [
        ("footprints", '{"foot":"dots","line":"sky"}'),
        ("footprints", None),
        ("block", None),
    ]
    with pytest.raises(ValueError, match="띠는 3칸이어야 합니다"):
        repository.save_fab_layout(
            canvas=None,
            marks=[_foot("F-BAD", h=6)],
            base=None,
        )
    assert repository.load_fab_layout_marks() == loaded


def test_footprints_added_in_a_hypothetical_scenario_are_one_mark_difference(
    tmp_path: Path,
) -> None:
    """가정 설비 시나리오에서 발자국을 더해 저장하면 그 요소 하나가 차이(`set`)로 들고 차이 표의
    `look_json` 에 실린다. 공식 요소는 그대로다."""
    repository = _seeded(tmp_path)
    scenario_id = _hypothetical(repository)
    session = _session(repository, scenario_id)
    assert session.schedule is not None
    added = _foot("MK-F", look={"foot": "toes", "gap": "narrow"})

    result = repository.save_equipment(
        _request(
            session,
            scenario_id,
            floor_marks={FLOOR: [added]},
            floor_layout_bases={
                FLOOR: _floor_base(repository, session.schedule.schedule_revision_id)
            },
        )
    )

    assert result.schedule is not None and result.layout_overlay_written
    assert (result.layout_overlay_units, result.layout_overlay_marks) == (0, 1)
    overlay = repository.load_layout_overlay(result.schedule.schedule_revision_id)
    (change,) = overlay.marks_for(FLOOR)
    assert change.kind == "set" and change.mark is not None
    assert (change.mark.mark_id, change.mark.kind, change.mark.look) == (
        "MK-F",
        "footprints",
        '{"foot":"toes","gap":"narrow"}',
    )
    assert repository.load_floor_layout_marks(*FLOOR) == ()
    with duckdb.connect(str(repository.database_path), read_only=True) as connection:
        rows = connection.execute(
            "SELECT mark_id, change_kind, mark_kind, look_json "
            "FROM equipment_ops.equipment_schedule_layout_mark"
        ).fetchall()
    assert rows == [("MK-F", "set", "footprints", '{"foot":"toes","gap":"narrow"}')]
