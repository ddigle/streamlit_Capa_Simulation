# Purpose: 설비·Space 페이지의 초기 진입과 입력·보기 설정·저장 동작을 검증한다.

from datetime import date
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest
from test_floor_layout_profile import _png

from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.equipment_contract import (
    empty_downtime_schedule,
    empty_equipment_master,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _open_tab(app: AppTest, name: str) -> AppTest:
    label = next(tab.label for tab in app.tabs if tab.label.endswith(f" {name}"))
    app.session_state["equipment_active_tab"] = label
    return app.run()


def _page_script(page_path: Path, database_path: Path) -> str:
    """두 DB 경로를 테스트 전용 폴더로 묶고 실제 페이지를 실행한다.

    Static/Dynamic 비교가 시뮬레이션 경계를 사용하므로 설비 DB만 바꾸면 충분하지 않다.
    설정은 tests/conftest.py의 autouse fixture가 테스트 종료 후 복원한다.
    """
    simulation_database_path = database_path.with_name(f"{database_path.stem}_simulation.duckdb")
    return f"""
from pathlib import Path
import capa_simulation.settings as settings

settings.EQUIPMENT_DUCKDB_PATH = Path({str(database_path)!r})
settings.DUCKDB_PATH = Path({str(simulation_database_path)!r})
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
    # Cut-off는 Preference에서 입력한다. RawData 안의 입력표 탭은 최상위 목록과 별개다.
    assert [tab.label for tab in app.tabs[:4]] == [
        ":material/dashboard: Main",
        ":material/compare_arrows: Static/Dynamic",
        ":material/tune: Preference",
        ":material/table_rows: RawData",
    ]
    filter_labels = {
        widget.label
        for widget in app.multiselect
        if widget.label in {"라인구분", "활용구분", "공정대분류", "공정소분류"}
    }
    assert filter_labels == {"라인구분", "활용구분", "공정대분류", "공정소분류"}
    assert any(button.label == "설비 데이터 입력" for button in app.button)
    assert app.session_state["equipment_baseline_draft_v3"].empty
    assert app.session_state["equipment_master_draft_v3"].empty
    assert not any("Qual 확정상태 실행관리" in item.value for item in app.markdown)

    def _filter(label: str) -> object:
        return next(widget for widget in app.multiselect if widget.label == label)

    _filter("라인구분").set_value(["Line-A"])
    _filter("활용구분").set_value(["양산"])
    app.run()

    assert not app.exception


def test_baseline_paste_import_needs_a_preview_before_it_saves(tmp_path: Path) -> None:
    """붙여넣기·미리보기는 저장하지 않고, 확인하면 불변 리비전에 한 번에 저장한다."""
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    database_path = tmp_path / "baseline_import.duckdb"
    app = AppTest.from_string(
        _page_script(page_path, database_path),
        default_timeout=60,
    ).run()
    _open_tab(app, "RawData")
    app.selectbox("equipment_import_target_v1").set_value("기존 보유대수").run()
    app.text_area("equipment_import_clipboard_v1").set_value(
        "공정\t분류\t기존보유대수\t비고\nProcess-X\t전체\t7\t증설"
    )
    app.run()
    repository = DuckDBEquipmentRepository(database_path)
    assert not repository.list_revisions()
    assert app.session_state["equipment_baseline_draft_v3"].empty
    app.button("equipment_import_preview_v1").click().run()
    assert not app.exception
    assert not repository.list_revisions()
    assert app.session_state["equipment_baseline_draft_v3"].empty
    app.button("equipment_import_save_v1").click().run()

    assert not app.exception
    assert not app.error
    revisions = repository.list_revisions()
    assert len(revisions) == 1
    saved = repository.load_snapshot(revisions[0].revision_id)
    assert saved.baseline["공정"].tolist() == ["Process-X"]
    assert saved.baseline["기존보유대수"].tolist() == [7.0]
    assert saved.equipment.empty
    assert saved.downtime.empty


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
    # 빈 DB의 편집본은 비어 있어야 한다. 조회용 샘플은 초안에 섞지 않는다.
    assert app.session_state["equipment_baseline_draft_v3"].empty


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


def _seeded_equipment(database_path: Path) -> None:
    """세 표에 모두 값이 있는 DuckDB. 보기 설정은 값이 있는 표에만 붙는다."""
    repository = DuckDBEquipmentRepository(database_path)
    repository.initialize()
    equipment = empty_equipment_master()
    equipment.loc[0] = {column: None for column in equipment.columns}
    equipment.loc[0, "호기"] = "EQ-1"
    equipment.loc[0, "공정소분류"] = "DEMO_PROC"
    equipment.loc[0, "장기보관여부"] = "N"
    equipment.loc[0, "기존설비여부"] = "Y"
    equipment.loc[0, "레이아웃표시"] = "N"
    equipment.loc[0, "담당자"] = "숨김 컬럼 보존"
    downtime = empty_downtime_schedule()
    downtime.loc[0] = {column: None for column in downtime.columns}
    downtime.loc[0, "호기"] = "EQ-1"
    downtime.loc[0, "비가동유형"] = "고장"
    downtime.loc[0, "시작일"] = date(2026, 1, 1)
    repository.save_snapshot(
        pd.DataFrame(
            {
                "공정": ["DEMO_PROC"],
                "분류": ["기존"],
                "기존보유대수": [1.0],
                "비고": ["숨겨도 유지할 값"],
            }
        ),
        equipment,
        downtime,
        note="검사용",
    )
    clear_equipment_repository()


def test_the_view_controls_render_for_each_editable_table(tmp_path: Path) -> None:
    """값이 있는 세 표에 각각 컬럼 선택과 행 필터가 붙는다.

    보기 적용과 리비전 저장은 별개다. 필터 변경만으로 불변 리비전을 만들지 않는다.
    """
    database_path = tmp_path / "availability.duckdb"
    _seeded_equipment(database_path)
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    app = AppTest.from_string(_page_script(page_path, database_path), default_timeout=60).run()

    assert not app.exception
    labels = [expandable.label for expandable in app.status]
    for table in ("기존 보유대수", "호기 마스터", "운영 비가동 일정"):
        assert f"{table} · 표 보기 설정" in labels, table
    # 다른 탭이 붙어도 각 입력표의 키로 찾는다.
    for prefix in ("equipment_baseline_view", "equipment_master_view", "equipment_downtime_view"):
        assert app.multiselect(f"{prefix}_columns").value
    clear_equipment_repository()


def test_hiding_a_column_keeps_its_values_in_the_saved_frame(tmp_path: Path) -> None:
    """감춘 컬럼도 저장에는 그대로 들어간다.

    `st.data_editor` 는 `column_config={컬럼: None}` 으로 감춘 컬럼의 값을 반환 프레임에
    그대로 돌려준다. 값이 빠져 나가면 저장이 그 컬럼을 통째로 비운다.
    """
    database_path = tmp_path / "availability.duckdb"
    _seeded_equipment(database_path)
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    app = AppTest.from_string(
        _page_script(page_path, database_path),
        default_timeout=60,
    ).run()
    _open_tab(app, "RawData")
    picker = app.multiselect("equipment_baseline_view_columns")
    remaining = [column for column in picker.value if column != "비고"]
    picker.set_value(remaining)
    app.button("equipment_view_apply_v1").click().run()
    _open_tab(app, "Main")
    _open_tab(app, "RawData")
    assert app.multiselect("equipment_baseline_view_columns").value == remaining
    app.button("equipment_edit_save_v1").click().run()

    assert not app.exception
    assert not app.error
    repository = DuckDBEquipmentRepository(database_path)
    revisions = repository.list_revisions()
    assert len(revisions) == 2
    saved = repository.load_snapshot(revisions[0].revision_id)
    assert saved.baseline["비고"].tolist() == ["숨겨도 유지할 값"]
    assert saved.equipment["담당자"].tolist() == ["숨김 컬럼 보존"]
    assert saved.downtime["호기"].tolist() == ["EQ-1"]
