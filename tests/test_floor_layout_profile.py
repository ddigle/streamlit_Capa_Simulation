# Purpose: 층 캔버스 프로필의 정상·예외·회귀 동작을 검증한다.

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from test_equipment_availability import _baseline, _downtime, _equipment

from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.equipment_validation import (
    floor_equipment_outside_canvas,
    prepare_equipment_master,
)
from capa_simulation.services.floor_layout_profile import (
    DEFAULT_CANVAS_HEIGHT,
    DEFAULT_CANVAS_WIDTH,
    FloorLayoutCanvas,
    FloorLayoutProfile,
    max_canvas_extent,
    normalize_canvas_size,
)


def _repository(path: Path) -> DuckDBEquipmentRepository:
    repository = DuckDBEquipmentRepository(path)
    repository.initialize()
    return repository


def test_floor_without_a_drawing_keeps_the_default_canvas() -> None:
    assert max_canvas_extent(None) == (DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT)
    assert max_canvas_extent({("C2", "3F"): (120.0, 37.5)}) == (120.0, 60.0)


def test_canvas_size_rejects_values_outside_the_allowed_range() -> None:
    assert normalize_canvas_size(100, 37.46) == (100.0, 37.5)
    with pytest.raises(ValueError, match="캔버스 높이"):
        normalize_canvas_size(100, 0)
    with pytest.raises(ValueError, match="캔버스 폭"):
        normalize_canvas_size(10_000, 60)


def test_floor_layout_profile_round_trip(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")

    saved = repository.save_floor_layout_canvas("C1", "1F", 100.0, 37.5)

    assert saved.canvas_size == (100.0, 37.5)
    loaded = repository.load_floor_layout_profile("C1", "1F")
    assert loaded is not None and loaded.canvas_size == (100.0, 37.5)
    assert repository.load_floor_layout_canvases() == {("C1", "1F"): (100.0, 37.5)}

    widened = repository.save_floor_layout_canvas("C1", "1F", 120.0, 45.0)
    assert widened.canvas_size == (120.0, 45.0)
    assert [item.canvas_size for item in repository.load_floor_layout_summaries()] == [
        (120.0, 45.0)
    ]
    assert repository.load_floor_layout_profile("C2", "1F") is None


def test_floor_layout_profile_rejects_unknown_building_or_floor(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")

    with pytest.raises(ValueError, match="C1~C5"):
        repository.save_floor_layout_canvas("C9", "1F", 100.0, 60.0)


def test_an_old_drawing_row_stays_in_the_table_and_is_never_read(tmp_path: Path) -> None:
    """도면 올리기를 걷어도(검수 equip-60) 옛 판이 올린 행 · 칸은 그대로다 — 캔버스 저장은 숫자 두
    개만 고치고 그림은 지우지 않으며, 읽는 값에는 그림이 들지 않는다."""
    repository = _repository(tmp_path / "equipment.duckdb")
    repository.save_floor_layout_canvas("C1", "1F", 100.0, 60.0)
    with repository._connect() as connection:
        connection.execute(
            """
            UPDATE equipment_ops.floor_layout_profile
            SET image_mime = 'image/png', image_name = 'old.png', image_payload = ?
            WHERE building = 'C1' AND floor_name = '1F'
            """,
            [b"old-drawing"],
        )

    widened = repository.save_floor_layout_canvas("C1", "1F", 130.0, 60.0)

    assert widened.canvas_size == (130.0, 60.0)
    with repository._connect() as connection:
        stored = connection.execute(
            "SELECT image_name, image_payload FROM equipment_ops.floor_layout_profile"
        ).fetchall()
    assert stored == [("old.png", b"old-drawing")]
    for kind in (FloorLayoutCanvas, FloorLayoutProfile):
        assert not [name for name in kind.__dataclass_fields__ if name.startswith("image")]


def test_equipment_revisions_do_not_duplicate_the_floor_canvas(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")
    repository.save_floor_layout_canvas("C1", "1F", 100.0, 60.0)

    repository.save_snapshot(_baseline(), _equipment(), _downtime(), note="1차")
    repository.save_snapshot(_baseline(), _equipment(), _downtime(), note="2차")

    summaries = repository.load_floor_layout_summaries()
    assert len(repository.list_revisions()) == 2
    assert len(summaries) == 1
    assert summaries[0].canvas_size == (100.0, 60.0)


def test_saving_equipment_uses_the_floor_canvas_and_loading_stays_readable(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")
    saved = repository.save_snapshot(_baseline(), _equipment(), _downtime())

    # C1 1F 를 좁히면 EQ-02(30+12=42)가 캔버스를 벗어난다.
    repository.save_floor_layout_canvas("C1", "1F", 40.0, 60.0)
    with pytest.raises(ValueError, match="층 캔버스"):
        repository.save_snapshot(_baseline(), _equipment(), _downtime())

    reloaded = repository.load_snapshot(saved.revision.revision_id)
    assert reloaded.equipment["설비명"].tolist() == ["EQ-01", "EQ-02"]


def test_shrunk_canvas_error_on_an_unrelated_save_names_the_floor_canvas_and_the_fix(
    tmp_path: Path,
) -> None:
    """캔버스를 줄인 뒤 무관한 칸만 고친 저장이 막히면, 원인과 고칠 곳이 문구에 있어야 한다.

    예전 문구는 `Space 블럭이 층 캔버스 범위를 벗어났습니다: ['EQ-02']` 뿐이라, 기존보유대수
    한 칸만 고친 사람은 원인이 남이 줄인 캔버스라는 것을 알 수 없었다(2026-09-29 버그 보고).
    검사는 그대로 마스터 전체에 건다 — 바뀐 행만 보면 검증이 약해진다.
    """
    repository = _repository(tmp_path / "equipment.duckdb")
    first = repository.save_snapshot(_baseline(), _equipment(), _downtime())
    repository.save_floor_layout_canvas("C1", "1F", 40.0, 60.0)
    baseline = first.baseline.copy()
    baseline.loc[0, "기존보유대수"] = 3.0

    with pytest.raises(ValueError) as caught:
        repository.save_snapshot(baseline, first.equipment, first.downtime)

    message = str(caught.value)
    assert message.startswith("Space 블럭이 층 캔버스 범위를 벗어났습니다")
    # 층 이름·지금 캔버스·이 층 호기를 담는 데 필요한 크기(EQ-02 는 30+12=42)·이탈 호기
    assert "C1 1F 캔버스 40 × 60" in message
    assert "42 × 60 이상" in message
    assert "['EQ-02']" in message
    assert "무관한 칸만 고쳐도" in message
    assert "Space 현황" in message
    assert "「캔버스 편집」" in message
    assert "X좌표·Y좌표·Xsize·Ysize" in message
    assert len(repository.list_revisions()) == 1


def test_canvas_error_says_when_the_floor_has_no_saved_canvas() -> None:
    """저장된 캔버스가 없는 층은 기본 캔버스로 잰다. 그 사실을 문구가 말해야 한다."""
    equipment = _equipment()
    equipment.loc[1, "X좌표"] = 95

    with pytest.raises(ValueError) as caught:
        prepare_equipment_master(equipment, floor_canvases={})

    message = str(caught.value)
    assert (
        f"C1 1F 캔버스 {DEFAULT_CANVAS_WIDTH:g} × {DEFAULT_CANVAS_HEIGHT:g}"
        "(저장된 캔버스 없음 · 기본값)"
    ) in message
    assert f"107 × {DEFAULT_CANVAS_HEIGHT:g} 이상" in message


def test_wide_canvas_allows_coordinates_beyond_the_default_range(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")
    repository.save_floor_layout_canvas("C1", "1F", 160.0, 60.0)
    equipment = _equipment()
    equipment.loc[1, "X좌표"] = 140

    saved = repository.save_snapshot(_baseline(), equipment, _downtime())

    assert saved.equipment.loc[1, "X좌표"] == pytest.approx(140.0)
    pd.testing.assert_series_equal(
        saved.equipment["층"].reset_index(drop=True),
        pd.Series(["1F", "1F"], name="층", dtype=saved.equipment["층"].dtype),
    )


def test_canvas_shrink_check_sees_every_saved_unit_of_the_floor() -> None:
    """캔버스 팝업의 줄이기 검사는 저장 검증과 같은 행을 본다 — 레이아웃표시 N·화면 필터와
    무관하게 그 동·층에서 좌표·크기가 다 있는 호기 전부다. 다른 층·좌표 없는 행은 보지 않는다."""
    equipment = _equipment()
    rows = [
        {**equipment.iloc[0].to_dict(), "설비명": "DEMO-EQ01", "X좌표": 150, "레이아웃표시": "N"},
        {**equipment.iloc[0].to_dict(), "설비명": "DEMO-EQ02", "X좌표": 88.7, "Xsize": 11.3},
        {**equipment.iloc[0].to_dict(), "설비명": "DEMO-EQ03", "X좌표": 150, "층": "2F"},
        {
            **equipment.iloc[0].to_dict(),
            "설비명": "DEMO-EQ04",
            "X좌표": None,
            "Y좌표": None,
            "Xsize": 300,
            "Ysize": 300,
            "레이아웃표시": "N",
        },
    ]
    saved = prepare_equipment_master(pd.concat([equipment, pd.DataFrame(rows)], ignore_index=True))

    assert floor_equipment_outside_canvas(saved, ("C1", "1F"), (100.0, 60.0)) == ["DEMO-EQ01"]
    assert floor_equipment_outside_canvas(saved, ("C1", "1F"), (162.0, 60.0)) == []
    assert floor_equipment_outside_canvas(saved, ("C1", "2F"), (100.0, 60.0)) == ["DEMO-EQ03"]
    assert floor_equipment_outside_canvas(saved.iloc[0:0], ("C1", "1F"), (10.0, 10.0)) == []
