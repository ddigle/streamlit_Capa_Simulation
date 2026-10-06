# Purpose: 층 배치 도면 프로필의 정상·예외·회귀 동작을 검증한다.

from __future__ import annotations

import random
import struct
from pathlib import Path

import pandas as pd
import pytest
from test_equipment_availability import _baseline, _downtime, _equipment

from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services import floor_layout_profile
from capa_simulation.services.equipment_validation import prepare_equipment_master
from capa_simulation.services.floor_layout_profile import (
    DEFAULT_CANVAS_HEIGHT,
    DEFAULT_CANVAS_WIDTH,
    MAX_FLOOR_LAYOUT_BYTES,
    MAX_TOTAL_LAYOUT_BYTES,
    canvas_from_pixel_size,
    image_pixel_size,
    max_canvas_extent,
    normalize_canvas_size,
    normalize_image_upload,
    require_total_layout_budget,
)


def _png(width: int, height: int) -> bytes:
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + header + b"\x00" * 4


def _jpeg(width: int, height: int) -> bytes:
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sof = (
        b"\xff\xc0"
        + struct.pack(">H", 11)
        + b"\x08"
        + struct.pack(">HH", height, width)
        + b"\x01\x01\x11\x00"
    )
    return b"\xff\xd8" + app0 + sof + b"\xff\xd9"


def _repository(path: Path) -> DuckDBEquipmentRepository:
    repository = DuckDBEquipmentRepository(path)
    repository.initialize()
    return repository


def test_floor_without_a_drawing_keeps_the_default_canvas() -> None:
    assert max_canvas_extent(None) == (DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT)
    assert max_canvas_extent({("C2", "3F"): (120.0, 37.5)}) == (120.0, 60.0)


def test_canvas_follows_the_drawing_aspect_ratio() -> None:
    assert canvas_from_pixel_size(3000, 1800) == (100.0, 60.0)
    assert canvas_from_pixel_size(4000, 1500) == (100.0, 37.5)
    assert canvas_from_pixel_size(0, 0) == (DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT)


def test_pixel_size_reads_png_and_jpeg_headers_without_extra_dependencies() -> None:
    assert image_pixel_size(_png(4000, 1500)) == (4000, 1500)
    assert image_pixel_size(_jpeg(1200, 900)) == (1200, 900)
    assert image_pixel_size(b"not-an-image") is None


def test_upload_rejects_unsupported_extension_and_oversized_payload() -> None:
    with pytest.raises(ValueError, match="png, jpeg, jpg|jpeg, jpg, png"):
        normalize_image_upload("layout.gif", _png(100, 100))
    with pytest.raises(ValueError, match="이하만 저장"):
        normalize_image_upload("layout.png", _png(100, 100) + b"\x00" * MAX_FLOOR_LAYOUT_BYTES)
    with pytest.raises(ValueError, match="형식을 읽지"):
        normalize_image_upload("layout.png", b"broken")
    assert normalize_image_upload("layout.PNG", _png(100, 100)) == ("layout.PNG", "image/png")


def test_canvas_size_rejects_values_outside_the_allowed_range() -> None:
    assert normalize_canvas_size(100, 37.46) == (100.0, 37.5)
    with pytest.raises(ValueError, match="캔버스 높이"):
        normalize_canvas_size(100, 0)
    with pytest.raises(ValueError, match="캔버스 폭"):
        normalize_canvas_size(10_000, 60)


def test_floor_layout_profile_round_trip_and_delete(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")

    saved = repository.save_floor_layout_image("C1", "1F", "c1_1f.png", _png(4000, 1500))

    assert saved.canvas_size == (100.0, 37.5)
    assert saved.image_data_uri is not None
    assert saved.image_data_uri.startswith("data:image/png;base64,")
    loaded = repository.load_floor_layout_profile("C1", "1F")
    assert loaded is not None
    assert loaded.image_data_uri == saved.image_data_uri
    assert loaded.image_name == "c1_1f.png"
    assert repository.load_floor_layout_canvases() == {("C1", "1F"): (100.0, 37.5)}

    widened = repository.save_floor_layout_canvas("C1", "1F", 120.0, 45.0)
    assert widened.canvas_size == (120.0, 45.0)
    assert widened.image_data_uri == saved.image_data_uri

    repository.delete_floor_layout_profile("C1", "1F")
    assert repository.load_floor_layout_profile("C1", "1F") is None
    assert repository.load_floor_layout_summaries() == ()


def test_floor_layout_profile_rejects_unknown_building_or_floor(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")

    with pytest.raises(ValueError, match="C1~C5"):
        repository.save_floor_layout_image("C9", "1F", "layout.png", _png(100, 60))


def test_equipment_revisions_do_not_duplicate_the_floor_drawing(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")
    repository.save_floor_layout_image("C1", "1F", "c1_1f.png", _png(3000, 1800))

    repository.save_snapshot(_baseline(), _equipment(), _downtime(), note="1차")
    repository.save_snapshot(_baseline(), _equipment(), _downtime(), note="2차")

    summaries = repository.load_floor_layout_summaries()
    assert len(repository.list_revisions()) == 2
    assert len(summaries) == 1
    assert summaries[0].has_image
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
    assert "「도면·캔버스 편집」" in message
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


def test_jpeg_parsing_stops_when_the_marker_chain_breaks() -> None:
    """SOI 뒤를 건너뛰며 훑으면 난수에서도 우연히 SOF 를 만나 통과한다.

    수정 전 표본 통과율이 1.5MB 난수 20회 중 4회였다. 체인이 끊기면 즉시 포기한다.
    """
    random.seed(7)
    passed = 0
    for _ in range(200):
        noise = bytes([0xFF, 0xD8]) + bytes(random.getrandbits(8) for _ in range(2000))
        if image_pixel_size(noise) is not None:
            passed += 1

    assert passed == 0


def test_upload_rejects_a_file_whose_content_disagrees_with_its_extension() -> None:
    """확장자만 바꾼 파일을 저장하면 data URI 의 MIME 이 내용과 달라 배경이 안 그려진다."""
    png = _png(3000, 1800)

    assert normalize_image_upload("plan.png", png) == ("plan.png", "image/png")
    with pytest.raises(ValueError, match="확장자와 다릅니다"):
        normalize_image_upload("plan.jpg", png)


def test_pixel_size_rejects_dimensions_outside_the_sane_range() -> None:
    """난수 바이트가 가짜 SOF 마커를 만나 돌려주는 말도 안 되는 치수를 막는다."""
    assert image_pixel_size(_jpeg(42808, 47750)) is None
    assert image_pixel_size(_png(40_000, 100)) is None
    with pytest.raises(ValueError, match="형식을 읽지"):
        normalize_image_upload("layout.jpg", _jpeg(42808, 47750))


def test_oversized_message_reports_the_actual_byte_count() -> None:
    payload = _png(100, 100) + bytes(MAX_FLOOR_LAYOUT_BYTES)

    with pytest.raises(ValueError) as error:
        normalize_image_upload("layout.png", payload)

    assert f"{len(payload):,}B" in str(error.value)


def test_total_layout_budget_counts_every_floor() -> None:
    require_total_layout_budget(MAX_TOTAL_LAYOUT_BYTES - 10, 10)
    with pytest.raises(ValueError, match="전체 합계"):
        require_total_layout_budget(MAX_TOTAL_LAYOUT_BYTES - 10, 11)


def test_saving_stops_when_all_floors_exceed_the_total_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(floor_layout_profile, "MAX_TOTAL_LAYOUT_BYTES", 3_000)
    repository = _repository(tmp_path / "equipment.duckdb")
    payload = _png(100, 60) + bytes(1_500)

    repository.save_floor_layout_image("C1", "1F", "c1_1f.png", payload)
    # 같은 층을 다시 저장하는 것은 합계가 늘지 않으므로 막히지 않는다.
    repository.save_floor_layout_image("C1", "1F", "c1_1f.png", payload)
    with pytest.raises(ValueError, match="전체 합계"):
        repository.save_floor_layout_image("C1", "2F", "c1_2f.png", payload)

    assert repository.load_floor_layout_profile("C1", "2F") is None


def test_canvas_only_save_keeps_a_floor_without_a_drawing(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")

    saved = repository.save_floor_layout_canvas("C2", "3F", 120.0, 80.0)

    assert saved.canvas_size == (120.0, 80.0)
    assert saved.image_data_uri is None
    assert repository.load_floor_layout_canvases() == {("C2", "3F"): (120.0, 80.0)}
    repository.delete_floor_layout_profile("C2", "3F")
    assert repository.load_floor_layout_profile("C2", "3F") is None


def test_canvas_edits_and_identical_reuploads_never_copy_the_drawing(tmp_path: Path) -> None:
    """DuckDB 는 지운 페이지를 회수하지 않는다. 저장 경로가 BLOB 을 다시 쓰면 안 된다."""
    database_path = tmp_path / "equipment.duckdb"
    repository = _repository(database_path)
    payload = _png(3000, 1800) + bytes(1_500_000)

    repository.save_floor_layout_image("C1", "1F", "c1_1f.png", payload)
    after_first_save = database_path.stat().st_size
    for step in range(6):
        repository.save_floor_layout_canvas("C1", "1F", 100.0, 60.0 + step)
    after_canvas_edits = database_path.stat().st_size
    for _ in range(8):
        repository.save_floor_layout_image("C1", "1F", "c1_1f.png", payload)
    after_reuploads = database_path.stat().st_size

    assert after_canvas_edits < after_first_save + len(payload)
    assert after_reuploads < after_first_save + len(payload)
    profile = repository.load_floor_layout_profile("C1", "1F")
    assert profile is not None
    assert profile.image_byte_count == len(payload)
    # 마지막 저장이 도면 종횡비로 캔버스를 다시 계산한다.
    assert profile.canvas_size == (100.0, 60.0)
