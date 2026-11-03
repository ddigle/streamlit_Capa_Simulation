# Purpose: Space 베이·요소 모양 값의 계약과 설비 0033 저장·가정 배치 차이를 검사한다.

"""2026-11-03 사용자 요청 — U자 베이 화살표(가운데 「B<번호>」)와 화살표 머리 크기(엑셀처럼).

- 베이(`bay`)는 층 도면 요소다(FAB 에는 없다). 이름표 칸에는 번호만 둔다 — 「80」·「B80」·「b 80」
  모두 「80」 이고 그릴 때 「B」 를 붙인다. 10자까지.
- 모양 값(`look` — 정규 JSON 글 한 칸)은 동선·베이만 갖는다. 처음 값인 키는 빼고 다 처음 값이면 빈
  글이다(옛 행과 같다). 받지 않는 키·틀린 값은 층 전체를 거부한다(층 단위 전체 교체라 버리지
  않는다).
- 저장은 설비 `0033` `look_json`(층·FAB 요소 표와 가정 배치 차이 표) — 빈 글 ↔ NULL. 옛 행은 NULL
  이라 지금 모습으로 읽힌다.
- 지문 안정: 모양 값이 빈 요소의 배치 차이 지문(`layout_hash`)·요소 지문은 0033 전 코드가 같은
  내용으로 낸 값과 같다(아래 고정 기대값은 `1700bc9` 코드로 잰 것이다).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import duckdb
import pytest
from test_equipment_availability import _baseline, _downtime, _equipment
from test_equipment_layout_overlay_repository import FLOOR, _floor_base, _hypothetical, _seeded
from test_equipment_scenario_repository import _request, _session

from capa_simulation.persistence.equipment_migration_runner import load_equipment_migrations
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.fab_layout import (
    FabLayoutMark,
    fab_marks_fingerprint,
    prepare_fab_layout_marks,
)
from capa_simulation.services.floor_layout_mark import (
    ARROW_HEADS,
    BLOCKING_MARK_KINDS,
    LINE_WIDTHS,
    LOOK_DEFAULTS,
    LOOK_KEYS,
    MARK_KINDS,
    MARK_NAMES,
    FloorLayoutMark,
    bay_label,
    mark_look,
    marks_fingerprint,
    prepare_floor_layout_marks,
)
from capa_simulation.services.layout_overlay import (
    LayoutOverlay,
    MarkChange,
    make_layout_overlay,
    mark_changes,
)

CANVAS = (100.0, 60.0)
FAB = (101.0, 62.0)


def _arrow(mark_id: str = "A1", **values: Any) -> dict[str, Any]:
    mark: dict[str, Any] = {"id": mark_id, "kind": "arrow", "x": 1, "y": 1, "w": 16, "h": 3}
    mark.update(values)
    return mark


def _bay(mark_id: str = "B1", **values: Any) -> dict[str, Any]:
    mark: dict[str, Any] = {"id": mark_id, "kind": "bay", "x": 30, "y": 1, "w": 10, "h": 4}
    mark.update(values)
    return mark


# ------------------------------------------------------------------------------- 계약


def test_the_bay_is_a_floor_mark_that_does_not_block_units() -> None:
    assert "bay" in MARK_KINDS and MARK_NAMES["bay"] == "베이"
    assert "bay" not in BLOCKING_MARK_KINDS
    (bay,) = prepare_floor_layout_marks([_bay()], CANVAS)
    assert not bay.blocks and bay.name == "베이"
    with pytest.raises(ValueError, match="종류를 알 수 없습니다"):
        prepare_fab_layout_marks([_bay()], FAB)


@pytest.mark.parametrize(
    ("raw", "number"),
    [
        ("80", "80"),
        ("B80", "80"),
        ("b 80", "80"),
        (" B  12A ", "12A"),
        ("B", ""),
        ("", ""),
        (None, ""),
        ("BB1", "1"),
        ("bB 80", "80"),
        ("B B 80", "80"),
        ("0123456789", "0123456789"),
        ("B0123456789", "0123456789"),
        ("BBB0123456789", "0123456789"),
    ],
)
def test_a_bay_keeps_only_its_number(raw: Any, number: str) -> None:
    """앞의 B·b 와 그 뒤 빈칸만 뗀다 — 그릴 때 늘 「B」 를 붙이므로 「B80」 을 넣어도 「BB80」 이
    되지 않는다. 다른 요소의 이름표는 그대로다."""
    assert bay_label({"label": raw}, "B1") == number
    (bay, arrow) = prepare_floor_layout_marks([_bay(label=raw), _arrow(label=raw)], CANVAS)
    assert bay.label == number
    assert arrow.label == str(raw or "").strip()


@pytest.mark.parametrize("raw", ["BB80", "BBB80", "b B 80", "B80", "80"])
def test_the_bay_number_does_not_change_again_on_apply_or_save(raw: str) -> None:
    """번호 떼기는 다시 거쳐도 같다(리뷰 data-1) — 편집기 입력(`bayNumber`) · 적용(`bay_label`) ·
    저장 길의 대기분 재검증(`editor_payload` → `prepare_floor_layout_marks`)을 지날 때마다 B 가
    하나씩 떨어져 「BBB80」 이 BB80 → B80 → 80 으로 말없이 바뀌었다."""
    once = bay_label({"label": raw}, "B1")
    assert bay_label({"label": once}, "B1") == once == "80"
    (applied,) = prepare_floor_layout_marks([_bay(label=raw)], CANVAS)
    (saved,) = prepare_floor_layout_marks([applied.editor_payload()], CANVAS)
    assert applied.label == saved.label == "80"


def test_a_bay_number_over_ten_characters_rejects_the_floor() -> None:
    with pytest.raises(ValueError, match="번호는 10자까지"):
        prepare_floor_layout_marks([_bay(label="B01234567890")], CANVAS)


def test_the_look_lists_are_the_decided_ones() -> None:
    """머리 크기 3×3(너비·길이 S·M·L), 선 굵기 일곱(화면 px), 처음 값은 지금 모습 — 동선은
    MM·강조색·점선 (굵기는 처음 값 없이 상자 높이를 따름), 베이는 MM·진하게·2px·실선·안 뒤집음."""
    assert ARROW_HEADS == ("SS", "SM", "SL", "MS", "MM", "ML", "LS", "LM", "LL")
    assert LINE_WIDTHS == (0.75, 1, 1.5, 2, 3, 4.5, 6)
    assert {kind: LOOK_KEYS[kind] for kind in ("arrow", "bay")} == {
        "arrow": ("head", "line", "lineWidth", "lineStyle"),
        "bay": ("head", "line", "lineWidth", "lineStyle", "flip"),
    }
    assert {kind: LOOK_DEFAULTS[kind] for kind in ("arrow", "bay")} == {
        "arrow": {"head": "MM", "line": "accent", "lineStyle": "dashed"},
        "bay": {"head": "MM", "line": "ink", "lineWidth": 2, "lineStyle": "solid", "flip": False},
    }


@pytest.mark.parametrize(
    ("kind", "look", "expected"),
    [
        ("arrow", None, ""),
        ("arrow", {}, ""),
        ("arrow", "", ""),
        ("arrow", {"head": "MM", "line": "accent", "lineStyle": "dashed"}, ""),
        ("arrow", {"head": "LS"}, '{"head":"LS"}'),
        ("arrow", {"lineWidth": 2.0, "head": "SL"}, '{"head":"SL","lineWidth":2}'),
        ("arrow", {"lineWidth": "1.5", "line": "ink"}, '{"line":"ink","lineWidth":1.5}'),
        ("arrow", '{"lineStyle":"solid"}', '{"lineStyle":"solid"}'),
        ("arrow", {"head": None, "lineWidth": None}, ""),
        ("bay", {"lineWidth": 2, "flip": False, "line": "ink"}, ""),
        ("bay", {"flip": True, "head": "LL"}, '{"flip":true,"head":"LL"}'),
        (
            "bay",
            {"line": "accent", "lineStyle": "dotted"},
            '{"line":"accent","lineStyle":"dotted"}',
        ),
        ("bay", {"line": "blue", "lineWidth": 0.75}, '{"line":"blue","lineWidth":0.75}'),
    ],
)
def test_a_look_is_canonical_json_of_the_values_off_their_defaults(
    kind: str, look: Any, expected: str
) -> None:
    """정규 글은 키 차례·빈칸 없는 JSON 이고 숫자는 정수면 정수다(편집기 JS 의 정규 글과 같다)."""
    assert mark_look({"look": look}, kind, "M1") == expected
    raw = (_arrow if kind == "arrow" else _bay)(look=look)
    (mark,) = prepare_floor_layout_marks([raw], CANVAS)
    assert mark.look == expected
    payload = mark.editor_payload()
    if expected:
        assert payload["look"] == json.loads(expected)
    else:
        assert "look" not in payload


@pytest.mark.parametrize(
    ("kind", "look", "message"),
    [
        ("arrow", {"head": "XL"}, "머리 크기를 알 수 없습니다"),
        ("arrow", {"head": "mm"}, "머리 크기를 알 수 없습니다"),
        ("arrow", {"line": "red"}, "선 색을 알 수 없습니다"),
        ("arrow", {"lineWidth": 7}, "선 굵기를 알 수 없습니다"),
        ("arrow", {"lineWidth": True}, "선 굵기를 알 수 없습니다"),
        ("arrow", {"lineStyle": "double"}, "선 모양을 알 수 없습니다"),
        ("arrow", {"flip": True}, "없는 모양 값입니다"),
        ("arrow", {"shape": "rect"}, "없는 모양 값입니다"),
        ("bay", {"flip": "Y"}, "뒤집기 값은 참·거짓"),
        ("bay", ["head"], "모양 값을 읽지 못했습니다"),
        ("bay", "{not json", "모양 값을 읽지 못했습니다"),
    ],
)
def test_a_look_off_the_lists_rejects_the_whole_floor(kind: str, look: Any, message: str) -> None:
    raw = (_arrow if kind == "arrow" else _bay)(look=look)
    with pytest.raises(ValueError, match=message):
        prepare_floor_layout_marks([raw], CANVAS)


@pytest.mark.parametrize("kind", ["zone", "shutter", "door", "column", "text"])
def test_marks_without_a_look_ignore_whatever_is_sent(kind: str) -> None:
    raw = {"id": "M1", "kind": kind, "x": 1, "y": 1, "w": 4, "h": 4, "look": {"head": "LL"}}
    (mark,) = prepare_floor_layout_marks([raw], CANVAS)
    assert mark.look == "" and "look" not in mark.editor_payload()


def test_fab_arrows_carry_a_look_like_floor_arrows() -> None:
    (arrow, zone) = prepare_fab_layout_marks(
        [
            _arrow(look={"head": "LM", "line": "gray"}),
            {"id": "Z", "kind": "zone", "x": 40, "y": 10, "w": 10, "h": 5, "look": "junk"},
        ],
        FAB,
    )
    assert arrow.look == '{"head":"LM","line":"gray"}' and zone.look == ""
    assert arrow.editor_payload()["look"] == {"head": "LM", "line": "gray"}
    with pytest.raises(ValueError, match="없는 모양 값입니다"):
        prepare_fab_layout_marks([_arrow(look={"flip": True})], FAB)


def test_cached_payloads_without_a_look_rebuild_with_the_default_look() -> None:
    """캐시는 `**payload` 로 다시 만든다. 0033 전에 실린 모양(look 키 없음)도 열려야 한다."""
    (floor,) = prepare_floor_layout_marks([_arrow()], CANVAS)
    (fab,) = prepare_fab_layout_marks([_arrow()], FAB)
    old_floor = {key: value for key, value in asdict(floor).items() if key != "look"}
    old_fab = {key: value for key, value in asdict(fab).items() if key != "look"}
    assert FloorLayoutMark(**old_floor) == floor
    assert FabLayoutMark(**old_fab) == fab


def test_a_resent_payload_keeps_the_look_and_the_fingerprint() -> None:
    """편집기가 돌려보내는 모양(`editor_payload`) 그대로 다시 검사하면 같은 값·같은 지문이다."""
    marks = prepare_floor_layout_marks(
        [_arrow(look={"head": "SL"}), _bay(label="B7", look={"flip": True}), _bay("B2")], CANVAS
    )
    again = prepare_floor_layout_marks([mark.editor_payload() for mark in marks], CANVAS)
    assert again == marks
    assert marks_fingerprint(again) == marks_fingerprint(marks)


# ------------------------------------------------------------------------------- 지문 안정


_ARROW = FloorLayoutMark(
    mark_id="MK-A",
    kind="arrow",
    x=2.0,
    y=3.0,
    w=16.0,
    h=3.0,
    rotation=90,
    label="반입",
    color="",
    hatch=False,
    keep_out=False,
    font_size=13,
)
_ZONE = FloorLayoutMark(
    mark_id="Z1",
    kind="zone",
    x=10.0,
    y=10.0,
    w=20.0,
    h=12.0,
    rotation=0,
    label="창고",
    color="green",
    hatch=True,
    keep_out=True,
    border_style="solid",
    label_align="center",
)


def _overlay(*marks: FloorLayoutMark) -> LayoutOverlay:
    return make_layout_overlay(
        [("k-A", "G", ("C1", "1F", 1.0, 2.0, 3.0, 4.0, "Y"))],
        {
            ("C1", "1F"): (
                *(MarkChange(mark.mark_id, "set", mark) for mark in marks),
                MarkChange("D", "drop"),
            )
        },
        {("C1", "1F"): (("G", "top"),)},
    )


def test_a_difference_without_looks_keeps_its_pre_0033_digest() -> None:
    """모양 값이 빈 요소는 지문 재료(`_mark_payload`)에 `look` 키를 넣지 않는다 — 옛 리비전의 저장된
    `layout_hash` 와 새 코드가 같은 내용으로 낸 지문이 같다(배치 빨리 감기·되돌리기 미리 보기). 요소
    지문(`marks_fingerprint` — 편집 시작 대조)도 같다. 기대값은 `1700bc9` 코드로 잰 것이다."""
    assert (
        _overlay(_ARROW, _ZONE).digest()
        == "ab3438c19ddc512f35eb98889614d796f7a373900b95b56b18784e33eade066b"
    )
    assert (
        marks_fingerprint((_ARROW, _ZONE))
        == "94997211ad13aae0bc4ff67a5cc6da5f5dd868d1b86085765947a9bc3631abdb"
    )


def test_a_look_changes_the_digest_and_round_trips_through_the_payload() -> None:
    headed = FloorLayoutMark(**{**asdict(_ARROW), "look": '{"head":"LL"}'})
    overlay = _overlay(headed, _ZONE)
    assert overlay.digest() != _overlay(_ARROW, _ZONE).digest()
    back = LayoutOverlay.from_payload(json.loads(json.dumps(overlay.to_payload())))
    assert back == overlay and back.digest() == overlay.digest()
    assert back.marks_for(("C1", "1F"))[0].mark == headed


def test_a_look_only_change_is_a_set_difference() -> None:
    headed = FloorLayoutMark(**{**asdict(_ARROW), "look": '{"head":"SS"}'})
    assert mark_changes((headed, _ZONE), (_ARROW, _ZONE)) == (MarkChange("MK-A", "set", headed),)
    assert mark_changes((_ARROW, _ZONE), (_ARROW, _ZONE)) == ()


# ------------------------------------------------------------------------------- 저장


def _repository(path: Path) -> DuckDBEquipmentRepository:
    repository = DuckDBEquipmentRepository(path)
    repository.initialize()
    return repository


def test_floor_looks_and_bays_round_trip_and_defaults_store_null(tmp_path: Path) -> None:
    database = tmp_path / "equipment.duckdb"
    repository = _repository(database)
    repository.save_snapshot(_baseline(), _equipment(), _downtime())
    marks = [
        _arrow("PLAIN"),
        _arrow("HEAD", y=10, look={"head": "LS", "lineWidth": 3}),
        _bay("BAY", label="B80", look={"flip": True, "line": "rose"}),
        _bay("BARE", x=50),
    ]

    stored = repository.replace_floor_layout_marks("C1", "1F", marks)

    assert [(mark.kind, mark.label, mark.look) for mark in stored] == [
        ("arrow", "", ""),
        ("arrow", "", '{"head":"LS","lineWidth":3}'),
        ("bay", "80", '{"flip":true,"line":"rose"}'),
        ("bay", "", ""),
    ]
    assert repository.load_floor_layout_marks("C1", "1F") == stored
    with duckdb.connect(str(database)) as connection:
        raw = connection.execute(
            "SELECT mark_id, label, look_json FROM equipment_ops.floor_layout_mark "
            "ORDER BY source_row_no"
        ).fetchall()
    assert raw == [
        ("PLAIN", None, None),
        ("HEAD", None, '{"head":"LS","lineWidth":3}'),
        ("BAY", "80", '{"flip":true,"line":"rose"}'),
        ("BARE", None, None),
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


def test_fab_arrow_looks_round_trip(tmp_path: Path) -> None:
    database = tmp_path / "equipment.duckdb"
    repository = _repository(database)
    marks = [
        _arrow("A-HEAD", look={"head": "ML", "lineStyle": "solid"}),
        _arrow("A-PLAIN", y=10),
        {"id": "B1", "kind": "block", "x": 40, "y": 10, "w": 12, "h": 5, "link": "C1 1F"},
    ]

    repository.save_fab_layout(canvas=None, marks=marks, base=(None, fab_marks_fingerprint(())))

    assert [mark.look for mark in repository.load_fab_layout_marks()] == [
        '{"head":"ML","lineStyle":"solid"}',
        "",
        "",
    ]
    with duckdb.connect(str(database)) as connection:
        raw = connection.execute(
            "SELECT look_json FROM equipment_ops.fab_layout_mark ORDER BY source_row_no"
        ).fetchall()
    assert raw == [('{"head":"ML","lineStyle":"solid"}',), (None,), (None,)]


def test_migration_0033_reads_old_marks_with_the_default_look(tmp_path: Path) -> None:
    """0032 까지 적용된 DB 의 요소는 0033 뒤에 모양 값이 빈 글(지금 모습)로 읽힌다. 세 표 모두 NULL
    허용 `look_json` 을 얻는다."""
    database = tmp_path / "before-0033.duckdb"
    before = [migration for migration in load_equipment_migrations() if migration.version <= 32]
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
                x_coordinate, y_coordinate, x_size, y_size, rotation_deg, label
            ) VALUES ('C1', '1F', 'OLD', 1, 'arrow', 1, 1, 16, 3, 0, '반입')
            """
        )
        connection.execute(
            """
            INSERT INTO equipment_ops.fab_layout_mark (
                mark_id, source_row_no, mark_kind, x_coordinate, y_coordinate, x_size, y_size,
                rotation_deg
            ) VALUES ('A-OLD', 1, 'arrow', 10, 10, 12, 3, 0)
            """
        )

    repository = DuckDBEquipmentRepository(database)
    assert repository.initialize() == (33,)

    (floor,) = repository.load_floor_layout_marks("C1", "1F")
    (fab,) = repository.load_fab_layout_marks()
    assert (floor.label, floor.look) == ("반입", "")
    assert fab.look == ""
    with duckdb.connect(str(database)) as connection:
        nullable = {
            row[0]: (row[1], row[2])
            for row in connection.execute(
                """
                SELECT table_name, data_type, is_nullable FROM information_schema.columns
                WHERE table_schema = 'equipment_ops' AND column_name = 'look_json'
                """
            ).fetchall()
        }
    assert nullable == {
        table: ("VARCHAR", "YES")
        for table in (
            "floor_layout_mark",
            "fab_layout_mark",
            "equipment_schedule_layout_mark",
        )
    }


# ------------------------------------------------------------------------------- 가정 배치 차이


def test_a_look_only_change_in_a_hypothetical_scenario_is_one_mark_difference(
    tmp_path: Path,
) -> None:
    """가정 설비 시나리오에서 공식 동선의 머리 크기만 바꿔 저장하면 그 요소 하나가 차이(`set`)로
    들고 (머리 알림 「도면 요소 1개」), 차이 표의 `look_json` 에 실리며, 공식 요소는 그대로다."""
    repository = _seeded(tmp_path)
    official = _arrow("MK-A", label="동선")
    repository.replace_floor_layout_marks(*FLOOR, [official])
    (stored,) = repository.load_floor_layout_marks(*FLOOR)
    scenario_id = _hypothetical(repository)
    session = _session(repository, scenario_id)
    assert session.schedule is not None
    headed = {**stored.editor_payload(), "look": {"head": "LL"}}

    result = repository.save_equipment(
        _request(
            session,
            scenario_id,
            floor_marks={FLOOR: [headed]},
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
    assert (change.mark.mark_id, change.mark.look) == ("MK-A", '{"head":"LL"}')
    assert repository.load_floor_layout_marks(*FLOOR) == (stored,)
    with duckdb.connect(str(repository.database_path), read_only=True) as connection:
        rows = connection.execute(
            "SELECT mark_id, change_kind, look_json "
            "FROM equipment_ops.equipment_schedule_layout_mark"
        ).fetchall()
    assert rows == [("MK-A", "set", '{"head":"LL"}')]
