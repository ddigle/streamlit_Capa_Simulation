# Purpose: equipment pages 관련 정상·예외·회귀 동작을 검증한다.

from pathlib import Path

from streamlit.testing.v1 import AppTest
from test_floor_layout_profile import _png

from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.equipment_contract import (
    empty_downtime_schedule,
    empty_equipment_master,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _page_script(page_path: Path, database_path: Path) -> str:
    return f"""
from pathlib import Path
import capa_simulation.settings as settings

settings.EQUIPMENT_DUCKDB_PATH = Path({str(database_path)!r})
page_source = Path({str(page_path)!r}).read_text(encoding="utf-8")
exec(compile(page_source, {str(page_path)!r}, "exec"), {{"__name__": "__main__"}})
"""


def test_available_equipment_page_opens_with_empty_database(tmp_path: Path) -> None:
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    app = AppTest.from_string(
        _page_script(page_path, tmp_path / "availability.duckdb"),
        default_timeout=60,
    ).run()

    assert not app.exception
    # 공통 헤더가 상태 접미를 제목에서 떼어 배지로 보여준다.
    assert app.title[0].value == "가용설비 현황"
    assert any("Data확보중" in element.value for element in app.markdown)
    assert [tab.label for tab in app.tabs] == ["대시보드", "설비 데이터·이력 관리"]
    assert [widget.label for widget in app.multiselect[:4]] == [
        "라인구분",
        "활용구분",
        "공정대분류",
        "공정소분류",
    ]
    assert "운영 지침" in [expandable.label for expandable in app.status]
    assert any(markdown.value == "#### Qual 확정상태 실행관리" for markdown in app.markdown)

    app.multiselect[0].set_value(["Line-A"])
    app.multiselect[1].set_value(["양산"])
    app.run()

    assert not app.exception


def test_baseline_paste_import_needs_a_preview_before_it_applies(tmp_path: Path) -> None:
    """기존 보유대수도 호기 마스터·비가동 일정과 같은 미리보기 → 확정 순서를 탄다."""
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    app = AppTest.from_string(
        _page_script(page_path, tmp_path / "baseline_import.duckdb"),
        default_timeout=60,
    ).run()

    assert [widget.label for widget in app.text_area] == [
        "기존 보유대수 표 붙여넣기",
        "호기 마스터 표 붙여넣기",
        "비가동 일정 표 붙여넣기",
    ]

    app.text_area[0].set_value("공정\t분류\t기존보유대수\t비고\nProcess-X\t전체\t7\t증설")
    app.run()
    app.button("equipment_baseline_clipboard_preview_v4").click().run()

    assert not app.exception
    assert any(element.value == "**기존 보유대수 Import 확인**" for element in app.markdown)

    app.button("confirm_baseline_import_v3").click().run()

    assert not app.exception
    assert any("기존 보유대수 붙여넣기 데이터 1행" in element.value for element in app.success)
    assert "Process-X" in app.session_state["equipment_baseline_draft_v3"]["공정"].tolist()


def test_page_reseeds_drafts_for_a_session_opened_before_the_baseline_table(
    tmp_path: Path,
) -> None:
    """배포 직전부터 열려 있던 브라우저 세션에서도 첫 렌더가 죽으면 안 된다.

    씨뿌리기는 `DRAFT_REVISION_KEY` 가 활성 리비전과 다를 때만 돈다. 표를 새로 더하면서
    그 키 이름을 올리지 않으면, 옛 세션은 세 draft 중 새 표만 없는 상태로 블록을 건너뛰고
    바로 아래 첨자 접근에서 `KeyError` 가 난다. 옛 세션 상태를 흉내내 그 자리를 고정한다.
    """
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    app = AppTest.from_string(
        _page_script(page_path, tmp_path / "stale_session.duckdb"),
        default_timeout=60,
    )
    # 기존 보유대수 표가 생기기 전 배포본이 남긴 세션이다.
    app.session_state["equipment_master_draft_v3"] = empty_equipment_master()
    app.session_state["equipment_downtime_draft_v3"] = empty_downtime_schedule()
    app.session_state["equipment_draft_revision_v3"] = "empty"
    app.run()

    assert not app.exception
    assert "equipment_baseline_draft_v3" in app.session_state
    assert not app.session_state["equipment_baseline_draft_v3"].empty


def test_space_page_opens_with_empty_database(tmp_path: Path) -> None:
    page_path = PROJECT_ROOT / "app_pages" / "space_status.py"
    app = AppTest.from_string(
        _page_script(page_path, tmp_path / "space.duckdb"),
        default_timeout=60,
    ).run()

    assert not app.exception
    assert app.title[0].value == "Space 현황"
    assert any("Data확보중" in element.value for element in app.markdown)


def test_space_floor_detail_offers_the_layout_upload_and_follows_the_drawing_canvas(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "space_layout.duckdb"
    repository = DuckDBEquipmentRepository(database_path)
    repository.initialize()
    repository.save_floor_layout_image("C1", "1F", "c1_1f.png", _png(4000, 1500))
    clear_equipment_repository()

    page_path = PROJECT_ROOT / "app_pages" / "space_status.py"
    app = AppTest.from_string(_page_script(page_path, database_path), default_timeout=60)
    app.session_state["space_status_selected_building"] = "C1"
    app.session_state["space_status_selected_floor"] = "1F"
    app.run()

    assert not app.exception
    assert len(app.get("file_uploader")) == 1
    assert any("적용될 캔버스: 100 × 37.5" == element.value for element in app.caption)
    assert any("c1_1f.png" in element.value for element in app.success)
    clear_equipment_repository()
