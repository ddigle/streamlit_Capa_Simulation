# Purpose: Space 도형(프리셋·모양 조절·채우기·선)의 계약·검증과 층·FAB·가정 배치 차이 저장 왕복을
# 검사한다.

"""2026-11-03 사용자 요청 — 도면 요소에 도형(원·사각형·ㄴ자 박스·프리셋 몇 가지)과 엑셀처럼 모양
바꾸기.

- 도형은 한 종류 `shape` 에 프리셋 키 `look.shape` 를 둔다(아홉 — 없으면 사각형). 층·FAB 둘 다이고
  꾸밈이라 막는 요소가 아니다(겹침 경고·「설비 금지」 없음).
- 모양 조절 값 `look.adj` 는 프리셋마다 0~2개의 0.01 단위 상자 비율이고 범위·개수가 어긋나면 층
  전체를 거부한다. 처음 값과 모두 같으면 넣지 않는다.
- 채우기 색은 요소의 `color`(영역 색 여섯 + `ink`·`surface`, 처음 파랑), 투명도는
  `look.fillAlpha`(불투명 0~100 의 5 단위, 처음 20), 선은 `look.line`(auto·none·ink·영역 색)·
  `lineWidth`·`lineStyle`, 빗금은 영역처럼 `hatch` 다.
- 저장은 설비 `0033` 의 `look_json`(마이그레이션 없음)과 기존 `color_key`·`hatch` 칸이다. 옛
  행(도형이 없던 DB)은 그대로 읽힌다 — `test_space_mark_look` 의 0033 시험이 본다.
"""

from __future__ import annotations

import json
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
    fab_marks_fingerprint,
    prepare_fab_layout_marks,
)
from capa_simulation.services.floor_layout_mark import (
    BLOCKING_MARK_KINDS,
    HATCH_MARK_KINDS,
    LINE_WIDTHS,
    LOOK_DEFAULTS,
    LOOK_KEYS,
    MARK_COLOR_KEYS,
    MARK_KINDS,
    MARK_NAMES,
    SHAPE_ADJUST,
    SHAPE_FILL_KEYS,
    SHAPE_LINE_KEYS,
    SHAPE_NAMES,
    SHAPE_PRESETS,
    mark_look,
    marks_fingerprint,
    prepare_floor_layout_marks,
    shape_fill,
)
from capa_simulation.services.layout_overlay import effective_floor_marks, mark_changes

CANVAS = (100.0, 60.0)
FAB = (101.0, 62.0)


def _shape(mark_id: str = "S1", **values: Any) -> dict[str, Any]:
    mark: dict[str, Any] = {"id": mark_id, "kind": "shape", "x": 10, "y": 10, "w": 8, "h": 6}
    mark.update(values)
    return mark


def _look(look: Any) -> str:
    return mark_look({"look": look}, "shape", "S1")


# ------------------------------------------------------------------------------- 계약


def test_the_shape_is_a_decorative_floor_and_fab_mark() -> None:
    assert MARK_KINDS[-1] == "shape" and MARK_NAMES["shape"] == "도형"
    assert "shape" in FAB_MARK_KINDS and FAB_MARK_NAMES["shape"] == "도형"
    assert "shape" not in BLOCKING_MARK_KINDS
    assert HATCH_MARK_KINDS == ("zone", "shape")
    (shape,) = prepare_floor_layout_marks([_shape(keepOut=True)], CANVAS)
    # 「설비 금지」는 영역만 — 도형에 와도 버린다. 테두리 모양·이름표 정렬도 영역만이다.
    assert not shape.blocks and not shape.keep_out
    assert (shape.border_style, shape.label_align) == ("dashed", "left")


def test_the_presets_and_their_adjust_ranges_are_the_decided_ones() -> None:
    """사양 4b-1 의 아홉 — (하한, 상한, 처음 값). 원·마름모는 모양 조절 값이 없다."""
    assert SHAPE_PRESETS == (
        "rect",
        "ellipse",
        "lbox",
        "cbox",
        "frame",
        "triangle",
        "diamond",
        "cross",
        "arrowblock",
    )
    assert SHAPE_NAMES["lbox"] == "ㄴ자 박스" and SHAPE_NAMES["ellipse"] == "원"
    assert SHAPE_ADJUST == {
        "rect": ((0, 1, 0),),
        "ellipse": (),
        "lbox": ((0.05, 0.95, 0.35), (0.05, 0.95, 0.35)),
        "cbox": ((0.05, 0.95, 0.3), (0.05, 0.49, 0.3)),
        "frame": ((0.02, 0.49, 0.12),),
        "triangle": ((0, 1, 0.5),),
        "diamond": (),
        "cross": ((0.05, 0.95, 0.34),),
        "arrowblock": ((0.05, 1, 0.5), (0.05, 0.95, 0.35)),
    }
    assert SHAPE_FILL_KEYS == (*MARK_COLOR_KEYS, "ink", "surface")
    assert SHAPE_LINE_KEYS == ("auto", "none", "ink", *MARK_COLOR_KEYS)
    assert LOOK_KEYS["shape"] == (
        "shape",
        "adj",
        "fillAlpha",
        "line",
        "lineWidth",
        "lineStyle",
        "flip",
    )
    assert LOOK_DEFAULTS["shape"] == {
        "shape": "rect",
        "fillAlpha": 20,
        "line": "auto",
        "lineWidth": 1.5,
        "lineStyle": "solid",
        "flip": False,
    }


# ------------------------------------------------------------------------------- 모양 값


@pytest.mark.parametrize(
    ("look", "expected"),
    [
        (None, ""),
        ({}, ""),
        # 처음 값은 모두 빠진다 — 사각형 · 둥글기 0 · 불투명 20 · 자동 선 1.5px 실선 · 안 뒤집음.
        (
            {
                "shape": "rect",
                "adj": [0],
                "fillAlpha": 20,
                "line": "auto",
                "lineWidth": 1.5,
                "lineStyle": "solid",
                "flip": False,
            },
            "",
        ),
        ({"shape": "ellipse"}, '{"shape":"ellipse"}'),
        ({"shape": "ellipse", "adj": []}, '{"shape":"ellipse"}'),
        # 프리셋의 처음 모양 조절 값과 같으면 뺀다 — 하나라도 다르면 둘 다 남긴다.
        ({"shape": "lbox", "adj": [0.35, 0.35]}, '{"shape":"lbox"}'),
        ({"shape": "lbox", "adj": [0.35, 0.6]}, '{"adj":[0.35,0.6],"shape":"lbox"}'),
        # 정수면 정수, 소수 둘째 자리까지(부동소수 꼬리를 걷는다).
        ({"adj": [1.0]}, '{"adj":[1]}'),
        ({"adj": [0.30000000000000004]}, '{"adj":[0.3]}'),
        ({"shape": "arrowblock", "adj": [1, 0.05]}, '{"adj":[1,0.05],"shape":"arrowblock"}'),
        ({"fillAlpha": 0, "line": "none"}, '{"fillAlpha":0,"line":"none"}'),
        ({"fillAlpha": 100.0, "lineWidth": 3.0}, '{"fillAlpha":100,"lineWidth":3}'),
        (
            {"line": "ink", "lineStyle": "dotted", "flip": True},
            '{"flip":true,"line":"ink","lineStyle":"dotted"}',
        ),
        ({"shape": None, "adj": None}, ""),
        ('{"shape": "cross", "adj": [0.5]}', '{"adj":[0.5],"shape":"cross"}'),
    ],
)
def test_a_shape_look_is_canonical_json_off_its_preset_defaults(look: Any, expected: str) -> None:
    assert _look(look) == expected


@pytest.mark.parametrize(
    ("look", "message"),
    [
        ({"shape": "hexagon"}, "도형 모양을 알 수 없습니다"),
        ({"adj": [0.5, 0.5]}, r"모양 조절 값은 1개여야"),
        ({"shape": "ellipse", "adj": [0.5]}, r"모양 조절 값은 0개여야"),
        ({"shape": "lbox", "adj": 0.5}, r"모양 조절 값은 2개여야"),
        ({"shape": "lbox", "adj": [0.04, 0.5]}, r"0\.05~0\.95 사이여야"),
        ({"shape": "cbox", "adj": [0.3, 0.5]}, r"0\.05~0\.49 사이여야"),
        ({"adj": [0.333]}, "0.01 단위 숫자여야"),
        ({"adj": [True]}, "0.01 단위 숫자여야"),
        ({"adj": ["가"]}, "0.01 단위 숫자여야"),
        ({"fillAlpha": 7}, "5 단위여야"),
        ({"fillAlpha": 105}, "5 단위여야"),
        ({"fillAlpha": 22.5}, "5 단위여야"),
        ({"line": "accent"}, "선 색을 알 수 없습니다"),
        ({"lineWidth": 7}, "선 굵기를 알 수 없습니다"),
        ({"flip": "Y"}, "뒤집기 값은 참·거짓"),
        ({"head": "MM"}, "없는 모양 값입니다"),
    ],
)
def test_a_shape_look_off_the_lists_rejects_the_whole_floor(look: Any, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        prepare_floor_layout_marks([_shape(look=look)], CANVAS)


def test_the_fill_colour_is_the_mark_colour_and_defaults_to_blue() -> None:
    marks = prepare_floor_layout_marks(
        [
            _shape("S-BLUE"),
            _shape("S-INK", x=30, color="ink"),
            _shape("S-SURF", x=50, color="surface", hatch=True),
            {**_shape("Z1", y=30), "kind": "zone", "color": "green", "hatch": True},
        ],
        CANVAS,
    )
    assert [(mark.kind, mark.color, mark.hatch) for mark in marks] == [
        ("shape", "blue", False),
        ("shape", "ink", False),
        ("shape", "surface", True),
        ("zone", "green", True),
    ]
    assert shape_fill({"color": " rose "}, "S") == "rose"
    with pytest.raises(ValueError, match="채우기 색을 알 수 없습니다"):
        prepare_floor_layout_marks([_shape(color="accent")], CANVAS)
    # 영역은 진하게·바탕을 받지 않는다(도형 채우기만의 색).
    with pytest.raises(ValueError, match="영역 Z1 의 색을 알 수 없습니다"):
        prepare_floor_layout_marks([{**_shape("Z1"), "kind": "zone", "color": "ink"}], CANVAS)


def test_other_kinds_ignore_shape_values() -> None:
    """도형 아닌 요소는 채우기 색·도형 모양 값을 보지 않는다(동선은 동선 모양 값만)."""
    (text, arrow) = prepare_floor_layout_marks(
        [
            {
                "id": "T1",
                "kind": "text",
                "x": 1,
                "y": 1,
                "w": 6,
                "h": 2,
                "color": "ink",
                "hatch": True,
                "look": {"shape": "lbox"},
            },
            {"id": "A1", "kind": "arrow", "x": 1, "y": 20, "w": 16, "h": 3, "color": "rose"},
        ],
        CANVAS,
    )
    assert (text.color, text.hatch, text.look) == ("", False, "")
    assert arrow.color == ""
    with pytest.raises(ValueError, match="동선 A1 의 선 색을 알 수 없습니다"):
        prepare_floor_layout_marks(
            [
                {
                    "id": "A1",
                    "kind": "arrow",
                    "x": 1,
                    "y": 1,
                    "w": 16,
                    "h": 3,
                    "look": {"line": "auto"},
                }
            ],
            CANVAS,
        )


def test_a_resent_shape_payload_keeps_its_values_and_fingerprint() -> None:
    raw = [
        _shape(
            "S1",
            label="창고",
            color="violet",
            hatch=True,
            rot=90,
            w=6,
            h=8,
            look={
                "shape": "lbox",
                "adj": [0.2, 0.7],
                "fillAlpha": 55,
                "line": "gray",
                "lineWidth": 3,
                "lineStyle": "dashed",
                "flip": True,
            },
        ),
        _shape("S2", x=40, look={"shape": "ellipse"}),
    ]
    marks = prepare_floor_layout_marks(raw, CANVAS)
    payload = marks[0].editor_payload()
    assert payload["look"] == {
        "adj": [0.2, 0.7],
        "fillAlpha": 55,
        "flip": True,
        "line": "gray",
        "lineStyle": "dashed",
        "lineWidth": 3,
        "shape": "lbox",
    }
    assert (payload["color"], payload["hatch"], payload["rot"]) == ("violet", True, 90)
    again = prepare_floor_layout_marks([mark.editor_payload() for mark in marks], CANVAS)
    assert again == marks
    assert marks_fingerprint(again) == marks_fingerprint(marks)
    # 사각형 처음 값 도형은 모양 값이 비어 `look` 키가 실리지 않는다(동선·베이와 같다).
    (plain,) = prepare_floor_layout_marks([_shape()], CANVAS)
    assert plain.look == "" and "look" not in plain.editor_payload()


def test_fab_shapes_follow_the_floor_contract() -> None:
    (shape, zone) = prepare_fab_layout_marks(
        [
            _shape(color="surface", hatch=True, look={"shape": "frame", "adj": [0.3]}),
            {"id": "Z", "kind": "zone", "x": 40, "y": 10, "w": 10, "h": 5},
        ],
        FAB,
    )
    assert (shape.kind, shape.color, shape.hatch) == ("shape", "surface", True)
    assert shape.look == '{"adj":[0.3],"shape":"frame"}'
    assert shape.editor_payload()["keepOut"] is False
    assert zone.hatch is False
    with pytest.raises(ValueError, match="모양 조절 값은 0.02~0.49 사이여야"):
        prepare_fab_layout_marks([_shape(look={"shape": "frame", "adj": [0.5]})], FAB)


def test_the_line_widths_offered_to_shapes_are_the_arrow_ones() -> None:
    for width in LINE_WIDTHS:
        expected = "" if width == 1.5 else json.dumps({"lineWidth": width}, separators=(",", ":"))
        assert _look({"lineWidth": width}) == expected


# ------------------------------------------------------------------------------- 저장


def _repository(path: Path) -> DuckDBEquipmentRepository:
    repository = DuckDBEquipmentRepository(path)
    repository.initialize()
    return repository


def test_floor_shapes_round_trip_through_look_json_and_colour(tmp_path: Path) -> None:
    database = tmp_path / "equipment.duckdb"
    repository = _repository(database)
    repository.save_snapshot(_baseline(), _equipment(), _downtime())
    marks = [
        _shape("PLAIN"),
        _shape(
            "LBOX",
            x=30,
            color="ink",
            hatch=True,
            label="자재",
            look={"shape": "lbox", "adj": [0.5, 0.25], "fillAlpha": 0, "line": "rose"},
        ),
        _shape("OVAL", x=50, rot=180, look={"shape": "ellipse", "lineStyle": "dotted"}),
    ]

    stored = repository.replace_floor_layout_marks("C1", "1F", marks)

    assert [(mark.mark_id, mark.color, mark.hatch, mark.look) for mark in stored] == [
        ("PLAIN", "blue", False, ""),
        ("LBOX", "ink", True, '{"adj":[0.5,0.25],"fillAlpha":0,"line":"rose","shape":"lbox"}'),
        ("OVAL", "blue", False, '{"lineStyle":"dotted","shape":"ellipse"}'),
    ]
    assert repository.load_floor_layout_marks("C1", "1F") == stored
    with duckdb.connect(str(database)) as connection:
        raw = connection.execute(
            "SELECT mark_id, mark_kind, color_key, hatch, keep_out, border_style, look_json "
            "FROM equipment_ops.floor_layout_mark ORDER BY source_row_no"
        ).fetchall()
    assert raw == [
        ("PLAIN", "shape", "blue", False, False, None, None),
        (
            "LBOX",
            "shape",
            "ink",
            True,
            False,
            None,
            '{"adj":[0.5,0.25],"fillAlpha":0,"line":"rose","shape":"lbox"}',
        ),
        ("OVAL", "shape", "blue", False, False, None, '{"lineStyle":"dotted","shape":"ellipse"}'),
    ]
    # 편집기가 돌려보내는 모양 그대로 다시 저장하면 바뀐 것이 없다.
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


def test_fab_shapes_round_trip(tmp_path: Path) -> None:
    database = tmp_path / "equipment.duckdb"
    repository = _repository(database)
    marks = [
        _shape("S-TRI", color="green", look={"shape": "triangle", "adj": [0.2], "flip": True}),
        {"id": "B1", "kind": "block", "x": 40, "y": 10, "w": 12, "h": 5, "link": "C1 1F"},
    ]

    repository.save_fab_layout(canvas=None, marks=marks, base=(None, fab_marks_fingerprint(())))

    (shape, block) = repository.load_fab_layout_marks()
    assert (shape.kind, shape.color, shape.look) == (
        "shape",
        "green",
        '{"adj":[0.2],"flip":true,"shape":"triangle"}',
    )
    assert block.look == ""
    with duckdb.connect(str(database)) as connection:
        raw = connection.execute(
            "SELECT mark_kind, color_key, look_json FROM equipment_ops.fab_layout_mark "
            "ORDER BY source_row_no"
        ).fetchall()
    assert raw == [
        ("shape", "green", '{"adj":[0.2],"flip":true,"shape":"triangle"}'),
        ("block", None, None),
    ]


# ------------------------------------------------------------------------------- 가정 배치 차이


def test_shapes_in_a_hypothetical_scenario_are_mark_differences(tmp_path: Path) -> None:
    """가정 설비 시나리오에서 공식 도형의 모양 조절 값만 바꾸고 새 도형을 하나 넣어 저장하면 둘이
    차이 (`set`)로 들고(머리 알림 「도면 요소 2개」), 차이 표에 프리셋·모양 조절·채우기 색이 실린다.
    공식 요소는 그대로이고, 합친 목록(`effective_floor_marks`)이 가정 쪽 모습을 그린다."""
    repository = _seeded(tmp_path)
    repository.replace_floor_layout_marks(*FLOOR, [_shape("MK-S", look={"shape": "cross"})])
    (official,) = repository.load_floor_layout_marks(*FLOOR)
    scenario_id = _hypothetical(repository)
    session = _session(repository, scenario_id)
    assert session.schedule is not None
    thicker = {**official.editor_payload(), "look": {"shape": "cross", "adj": [0.6]}}
    added = _shape("MK-NEW", x=40, color="surface", look={"shape": "diamond", "fillAlpha": 80})

    result = repository.save_equipment(
        _request(
            session,
            scenario_id,
            floor_marks={FLOOR: [thicker, added]},
            floor_layout_bases={
                FLOOR: _floor_base(repository, session.schedule.schedule_revision_id)
            },
        )
    )

    assert result.schedule is not None and result.layout_overlay_written
    assert (result.layout_overlay_units, result.layout_overlay_marks) == (0, 2)
    overlay = repository.load_layout_overlay(result.schedule.schedule_revision_id)
    changes = overlay.marks_for(FLOOR)
    assert [(change.mark_id, change.kind) for change in changes] == [
        ("MK-S", "set"),
        ("MK-NEW", "set"),
    ]
    assert repository.load_floor_layout_marks(*FLOOR) == (official,)
    effective = effective_floor_marks((official,), changes)
    assert [(mark.mark_id, mark.color, mark.look) for mark in effective] == [
        ("MK-S", "blue", '{"adj":[0.6],"shape":"cross"}'),
        ("MK-NEW", "surface", '{"fillAlpha":80,"shape":"diamond"}'),
    ]
    assert len(mark_changes(effective, (official,))) == 2
    with duckdb.connect(str(repository.database_path), read_only=True) as connection:
        rows = connection.execute(
            "SELECT mark_id, mark_kind, color_key, look_json "
            "FROM equipment_ops.equipment_schedule_layout_mark ORDER BY mark_id"
        ).fetchall()
    assert rows == [
        ("MK-NEW", "shape", "surface", '{"fillAlpha":80,"shape":"diamond"}'),
        ("MK-S", "shape", "blue", '{"adj":[0.6],"shape":"cross"}'),
    ]
