# Purpose: 설비·Space 페이지의 초기 진입과 입력·보기 설정·저장 동작을 검증한다.

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Expander, Multiselect, Status
from test_equipment_availability import _baseline, _downtime, _equipment
from test_floor_layout_profile import _png

from capa_simulation.components import space_layout_editor
from capa_simulation.components.equipment_settings_dialog import (
    EQUIPMENT_DIALOG_KEY,
    SETTINGS_BUTTON_KEY,
)
from capa_simulation.components.sample_data import SAMPLE_TOGGLE_KEY
from capa_simulation.navigation import (
    EQUIPMENT_SUMMARY_TAB,
    EQUIPMENT_SUMMARY_TAB_KEY,
    EQUIPMENT_SUMMARY_TABS,
    EQUIPMENT_TAB_KEY,
)
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.equipment_contract import (
    empty_downtime_schedule,
    empty_equipment_master,
)
from capa_simulation.services.fab_layout import FLOOR_KEYS, floor_label
from capa_simulation.sidebar_status import CONDITION_CARD_PREFIX

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _open_tab(app: AppTest, name: str) -> AppTest:
    """가용설비 현황의 탭 하나를 연다. Summary 의 안쪽 탭(Main·Static 대비 일정)은 바깥 Summary 와
    함께 연다 — 안쪽만 고르면 바깥이 숨은 채라 그 본문이 돌지 않는다."""
    label = next(tab.label for tab in app.tabs if tab.label.endswith(f" {name}"))
    if label in EQUIPMENT_SUMMARY_TABS:
        app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_SUMMARY_TAB
        app.session_state[EQUIPMENT_SUMMARY_TAB_KEY] = label
    else:
        app.session_state[EQUIPMENT_TAB_KEY] = label
    return app.run()


def _open_settings(app: AppTest) -> AppTest:
    """머리 「설정」 단추로 공정별 Cut-off 팝업을 연다(개편 전 `Preference` 탭)."""
    return app.button(key=SETTINGS_BUTTON_KEY).click().run()


def _page_script(page_path: Path, database_path: Path) -> str:
    """두 DB 경로를 테스트 전용 폴더로 묶고 실제 페이지를 실행한다.

    Static 대비 일정 비교가 시뮬레이션 경계를 사용하므로 설비 DB만 바꾸면 충분하지 않다.
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
    # 운영 화면이라 상태 접미도 본문 배지도 없다(2026-10-19 사용자 요청).
    assert app.title[0].value == "가용설비 현황"
    assert not any("Data확보중" in element.value for element in app.markdown)
    # 탭 둘(2026-10-24): ① 설비 마스터(처음 여는 탭) ② Summary(안쪽 Main·Static 대비 일정). Cut-off
    # 는 머리 「설정」 팝업, Qual 마감 계산기는 필요 단축 일정 팝업, 설비 시나리오는 시나리오
    # 관리다. 설비 마스터 안의 입력표 탭은 최상위 목록과 별개다.
    labels = [tab.label for tab in app.tabs]
    assert [label for label in labels if label.startswith(":material/")] == [
        ":material/table_rows: 설비 마스터",
        ":material/insights: Summary",
        ":material/dashboard: Main",
        ":material/compare_arrows: Static 대비 일정",
    ]
    assert any(button.key == SETTINGS_BUTTON_KEY for button in app.button)
    _open_tab(app, "Main")
    filter_labels = {
        widget.label
        for widget in app.multiselect
        if widget.label in {"공정구분", "투자구분", "공정대분류", "공정소분류"}
    }
    assert filter_labels == {"공정구분", "투자구분", "공정대분류", "공정소분류"}
    # 거르는 조건은 사이드바 카드, 무엇을 볼지(볼 내용·보기·표현)는 본문이다(2026-09-29 결정).
    assert {widget.label for widget in app.sidebar.multiselect} >= filter_labels
    assert "볼 내용" in {widget.label for widget in app.main.segmented_control}
    assert "보기" in {widget.label for widget in app.main.selectbox}
    assert not app.sidebar.segmented_control
    assert any(button.label == "설비 데이터 입력" for button in app.button)
    assert app.session_state["equipment_baseline_draft_v3"].empty
    assert app.session_state["equipment_master_draft_v3"].empty
    assert not any(item.value.startswith("#### Qual 일정 · ") for item in app.markdown)

    def _filter(label: str) -> Multiselect[Any]:
        return next(widget for widget in app.multiselect if widget.label == label)

    _filter("공정구분").set_value(["Line-A"])
    _filter("투자구분").set_value(["양산"])
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
    _open_tab(app, "설비 마스터")
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
    # 본문 머리에는 상태 배지도 적용 이력 줄도 없다 — 배치도가 쓸 자리다(2026-10-01 사용자 결정).
    assert not any("Data확보중" in element.value for element in app.markdown)
    assert not any("적용 이력" in element.value for element in app.caption)


def test_space_page_with_the_sample_switch_off_keeps_a_card_under_the_sidebar_title(
    tmp_path: Path,
) -> None:
    """호기가 없고 샘플을 끄면 카드 안에 까닭 한 줄을 둔다.

    카드 없이 멈추면 사이드바에 「조회 조건 · 이 화면에 적용」 제목만 덩그러니 남았다
    (2026-10-01 브라우저 실측). 가용설비 현황의 같은 자리와 같은 모양이다.
    """
    page_path = PROJECT_ROOT / "app_pages" / "space_status.py"
    app = AppTest.from_string(
        _page_script(page_path, tmp_path / "space_off.duckdb"), default_timeout=60
    )
    app.session_state[SAMPLE_TOGGLE_KEY] = False
    app.run()

    assert not app.exception
    card = app.sidebar.get_by_key(f"{CONDITION_CARD_PREFIX}space")
    assert isinstance(card, (Status, Expander))
    assert card.label.endswith("Space 조건")
    assert any("조회할 호기가 없습니다" in item.value for item in app.sidebar.caption)
    # 조건 위젯은 서지 않는다 — 고를 호기가 없다.
    assert not app.sidebar.date_input
    assert not app.sidebar.multiselect


def test_space_page_counts_placement_and_leaves_stage_transitions_to_availability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Space 는 배치·공간만 본다. 기간별 단계 전환은 가용설비 현황 Main 의 「단계 전환」이다.

    2단이다: FAB 전체(층 도면과 같은 편집기의 보기 전용, `scope="fab"`) → 층 상세. 동 단계는 없다.
    """
    viewer: list[dict[str, object]] = []
    monkeypatch.setattr(
        space_layout_editor, "_EDITOR", lambda **kwargs: viewer.append(kwargs["data"])
    )
    page_path = PROJECT_ROOT / "app_pages" / "space_status.py"
    app = AppTest.from_string(
        _page_script(page_path, tmp_path / "space_place.duckdb"), default_timeout=60
    ).run()

    assert not app.exception
    # FAB 에는 카드가 없다. 배치·미배치·레이아웃 제외는 뷰어 도구 줄 오른쪽 한 줄 요약이다.
    assert not app.metric
    fab = viewer[-1]
    assert fab["mode"] == "view" and fab["scope"] == "fab"
    assert str(fab["summary"]).startswith("배치 ") and "레이아웃 제외" in str(fab["summary"])
    labels = {floor_label(key) for key in FLOOR_KEYS}
    marks = fab["marks"]
    assert isinstance(marks, list)
    assert {mark["link"] for mark in marks if mark["kind"] == "block"} == labels
    # 블록 대수는 배치·미배치만 센다(상태 대수가 아니다).
    stats = fab["linkStats"]
    assert isinstance(stats, dict) and set(stats) == labels
    assert not any("가용" in str(value) for floor in stats.values() for value in floor.values())
    # 사이드바 카드의 고르기는 공정소분류뿐이다 — 전환 조회기간·전환단계 폼이 없고, 기준일 칸과
    # 「단계」 필터도 없다(기준일은 층 상세 도면 위 페이더, 2026-10-16 사용자 결정).
    assert not app.sidebar.date_input
    assert [widget.label for widget in app.sidebar.multiselect] == ["공정소분류"]
    assert not any("단계 전환" in element.value for element in app.markdown)
    # FAB 아래는 30개 층 목록 표다(행을 고르면 그 층이 열린다).
    floor_table = app.dataframe[0].value
    assert list(floor_table.columns) == [
        "동",
        "층",
        "사용",
        "배치대수",
        "미배치대수",
        "점유율",
        "배치 도면",
        "캔버스",
    ]
    assert len(floor_table) == len(FLOOR_KEYS)

    # 동만 고른 세션은 FAB 그대로다(동 단계는 없다).
    app.session_state["space_status_selected_building"] = "C1"
    app.run()
    assert not app.exception
    assert viewer[-1]["scope"] == "fab"

    app.session_state["space_status_selected_building"] = "C1"
    app.session_state["space_status_selected_floor"] = "1F"
    app.run()
    assert not app.exception
    # 층 화면은 카드 없이 배치도가 화면을 쓴다. 배치·미배치·점유율은 뷰어 도구 줄의 한 줄 요약이다.
    assert not app.metric
    data = viewer[-1]
    assert data["mode"] == "view" and data["scope"] == "floor" and data["floor"] == "C1 1F"
    assert "배치 " in str(data["summary"]) and str(data["summary"]).count("%") == 1
    assert not any("Space 배치도" in element.value for element in app.markdown)


def test_space_floor_detail_offers_the_layout_upload_and_follows_the_drawing_canvas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "space_layout.duckdb"
    repository = DuckDBEquipmentRepository(database_path)
    repository.initialize()
    repository.save_floor_layout_image("C1", "1F", "c1_1f.png", _png(4000, 1500))
    clear_equipment_repository()

    viewer: list[dict[str, object]] = []
    monkeypatch.setattr(
        space_layout_editor, "_EDITOR", lambda **kwargs: viewer.append(kwargs["data"])
    )
    page_path = PROJECT_ROOT / "app_pages" / "space_status.py"
    app = AppTest.from_string(_page_script(page_path, database_path), default_timeout=60)
    app.session_state["space_status_selected_building"] = "C1"
    app.session_state["space_status_selected_floor"] = "1F"
    app.run()

    assert not app.exception
    # 뷰어는 도면의 캔버스와 배경 도면을 받는다.
    assert viewer[-1]["canvas"] == {"width": 100.0, "height": 37.5}
    assert str(viewer[-1]["backgroundImage"]).startswith("data:image/png")
    # 도면·캔버스 편집은 레이아웃 위 작업 줄의 팝업이다 — 닫혀 있는 동안 본문을 차지하지 않는다.
    assert len(app.get("file_uploader")) == 0
    app.button(key="space_floor_layout_open_C1_1F").click().run()
    assert not app.exception
    assert len(app.get("file_uploader")) == 1
    assert any("적용될 캔버스: 100 × 37.5" == element.value for element in app.caption)
    assert any("c1_1f.png" in element.value for element in app.success)
    clear_equipment_repository()


def _wide_floor_with_hidden_units(database_path: Path) -> None:
    """C1 1F 캔버스 200 × 100 과, 기본 캔버스(100 × 60) 밖에 서 있지만 층 화면에는 안 그려지는
    호기 둘 — 레이아웃표시 N(DEMO-EQ01)·공정 필터로 걸러질 Process-B(DEMO-EQ02)."""
    repository = DuckDBEquipmentRepository(database_path)
    repository.initialize()
    repository.save_floor_layout_canvas("C1", "1F", 200.0, 100.0)
    equipment = _equipment()
    hidden = pd.DataFrame(
        [
            {
                **equipment.iloc[0].to_dict(),
                "설비명": "DEMO-EQ01",
                "X좌표": 150,
                "레이아웃표시": "N",
            },
            {
                **equipment.iloc[0].to_dict(),
                "설비명": "DEMO-EQ02",
                "X좌표": 140,
                "공정소분류": "Process-B",
            },
        ]
    )
    repository.save_snapshot(
        _baseline(), pd.concat([equipment, hidden], ignore_index=True), _downtime()
    )
    clear_equipment_repository()


def _open_wide_floor_dialog(database_path: Path) -> AppTest:
    """C1 1F 를 열고 공정 필터를 Process-A 로 둔 뒤 도면·캔버스 팝업을 연다."""
    page_path = PROJECT_ROOT / "app_pages" / "space_status.py"
    app = AppTest.from_string(_page_script(page_path, database_path), default_timeout=60)
    app.session_state["space_status_selected_building"] = "C1"
    app.session_state["space_status_selected_floor"] = "1F"
    app.run()
    app.multiselect(key="space_status_process_filter").set_value(["Process-A"]).run()
    app.button(key="space_floor_layout_open_C1_1F").click().run()
    assert not app.exception
    return app


def test_the_drawing_dialog_checks_hidden_units_before_shrinking_the_canvas(
    tmp_path: Path,
) -> None:
    """캔버스 줄이기 검사는 층 화면에 그린 호기가 아니라 그 층의 저장된 호기 전부를 본다.

    레이아웃표시 N·공정 필터로 화면에 없는 호기도 저장 검증은 본다. 팝업이 그 호기를 빼고 재면
    경고 없이 줄인 뒤 그 다음 설비 저장(어느 칸을 고치든)이 전부 「캔버스 밖」으로 막힌다.
    """
    database_path = tmp_path / "space_hidden.duckdb"
    _wide_floor_with_hidden_units(database_path)
    app = _open_wide_floor_dialog(database_path)

    app.checkbox(key="space_floor_layout_auto_C1_1F").uncheck().run()
    app.number_input(key="space_floor_layout_width_C1_1F_manual_200x100").set_value(100.0)
    app.number_input(key="space_floor_layout_height_C1_1F_manual_200x100").set_value(60.0).run()

    assert not app.exception
    warnings = [str(item.value) for item in app.warning]
    assert any("DEMO-EQ01" in text and "DEMO-EQ02" in text for text in warnings), warnings
    assert app.button(key="space_floor_layout_save_C1_1F").disabled
    clear_equipment_repository()


def test_the_drawing_dialog_checks_hidden_units_before_deleting_the_canvas(
    tmp_path: Path,
) -> None:
    """지우면 캔버스가 기본 100 × 60 으로 돌아간다 — 그 밖에 남는 호기가 있으면 줄이기와 같은
    확인을 거쳐야 지운다."""
    database_path = tmp_path / "space_hidden_delete.duckdb"
    _wide_floor_with_hidden_units(database_path)
    app = _open_wide_floor_dialog(database_path)

    texts = [str(item.value) for item in app.caption]
    assert any("DEMO-EQ01" in text and "100 × 60" in text for text in texts), texts
    assert app.button(key="space_floor_layout_delete_C1_1F").disabled
    app.checkbox(key="space_floor_layout_delete_confirm_C1_1F").check().run()
    assert not app.button(key="space_floor_layout_delete_C1_1F").disabled
    clear_equipment_repository()


def _seeded_equipment(database_path: Path) -> None:
    """세 표에 모두 값이 있는 DuckDB. 보기 설정은 값이 있는 표에만 붙는다."""
    repository = DuckDBEquipmentRepository(database_path)
    repository.initialize()
    equipment = empty_equipment_master()
    equipment.loc[0] = {column: None for column in equipment.columns}
    equipment.loc[0, "설비명"] = "EQ-1"
    equipment.loc[0, "공정소분류"] = "DEMO_PROC"
    equipment.loc[0, "보관유무"] = "N"
    equipment.loc[0, "기존설비여부"] = "Y"
    equipment.loc[0, "레이아웃표시"] = "N"
    equipment.loc[0, "담당자"] = "숨김 컬럼 보존"
    downtime = empty_downtime_schedule()
    downtime.loc[0] = {column: None for column in downtime.columns}
    downtime.loc[0, "설비명"] = "EQ-1"
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
    for table in ("기존 보유대수", "설비 마스터", "운영 비가동 일정"):
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
    _open_tab(app, "설비 마스터")
    picker = app.multiselect("equipment_baseline_view_columns")
    remaining = [column for column in picker.value if column != "비고"]
    picker.set_value(remaining)
    app.button("equipment_view_apply_v1").click().run()
    _open_tab(app, "Main")
    _open_tab(app, "설비 마스터")
    assert app.multiselect("equipment_baseline_view_columns").value == remaining
    app.button("equipment_edit_save_v1").click().run()

    assert not app.exception
    assert not app.error
    repository = DuckDBEquipmentRepository(database_path)
    revisions = repository.list_revisions()
    # 감춘 칸 값이 빠져 나갔다면 「바뀐 것」 으로 보여 새 리비전이 생긴다 — 값이 그대로라 저장할
    # 것이 없다(빈 리비전을 만들지 않는다).
    assert len(revisions) == 1
    saved = repository.load_snapshot(revisions[0].revision_id)
    assert saved.baseline["비고"].tolist() == ["숨겨도 유지할 값"]
    assert saved.equipment["담당자"].tolist() == ["숨김 컬럼 보존"]
    assert saved.downtime["설비명"].tolist() == ["EQ-1"]


def test_the_empty_page_lists_the_three_inputs_with_counts_and_links(tmp_path: Path) -> None:
    """저장본이 없으면 첫 화면이 세 데이터를 건수와 함께 짚고 각각 갈 곳을 준다.

    한 줄 + 버튼 하나로는 **무엇이 없어서 비어 있는지**를 알 수 없다. 데모 fleet 이 가득
    차 보이는 화면이라 더 그렇다. 대수는 적지 않는다 — Main 총대수는 다른 산식이다.
    """
    database_path = tmp_path / "first_data.duckdb"
    repository = DuckDBEquipmentRepository(database_path)
    repository.initialize()
    repository.save_process_cutoff(pd.DataFrame({"공정": ["DEMO_PROC"], "Cutoff일수": [3]}))
    clear_equipment_repository()
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    app = AppTest.from_string(_page_script(page_path, database_path), default_timeout=60).run()
    # 첫 데이터 안내는 Summary › Main 에 선다(처음 여는 탭은 설비 마스터).
    assert not any("**설비 마스터** 0건" in element.value for element in app.markdown)
    _open_tab(app, "Main")

    assert not app.exception
    rendered = [element.value for element in app.markdown]
    assert "✗ **설비 마스터** 0건" in rendered
    assert "✗ **운영 비가동 일정** 0건" in rendered
    # 저장된 것은 ✓ 로 구분한다. 세 줄 중 이 줄만 tmp DB 에 따라 값이 달라진다.
    assert "✓ **공정별 Cut-off** 1건" in rendered
    app.button("equipment_first_data_cut_v1").click().run()

    assert not app.exception
    # 「설정에서 보기」 는 「설정」 팝업(공정별 Cut-off)을 연다.
    assert app.session_state[EQUIPMENT_DIALOG_KEY] == "settings"
    assert any(button.label == "Cut-off 저장" for button in app.button)
    # 「설비 마스터 탭에서 붙여넣기」 는 탭 ① 을 연다.
    del app.session_state[EQUIPMENT_DIALOG_KEY]
    _open_tab(app, "Main")
    app.button("equipment_first_data_master_v1").click().run()
    assert not app.exception
    assert app.session_state[EQUIPMENT_TAB_KEY] == ":material/table_rows: 설비 마스터"
    clear_equipment_repository()


def test_the_first_data_checklist_disappears_once_a_revision_exists(tmp_path: Path) -> None:
    """저장본이 생기면 목록을 그리지 않는다. 첫 행동 안내와 같은 조건이다."""
    database_path = tmp_path / "availability.duckdb"
    _seeded_equipment(database_path)
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    app = AppTest.from_string(_page_script(page_path, database_path), default_timeout=60).run()
    _open_tab(app, "Main")

    assert not app.exception
    labels = [button.label for button in app.button]
    assert "설비 데이터 입력" not in labels
    assert "설비 마스터 탭에서 붙여넣기" not in labels
    assert "설정에서 보기" not in labels
    clear_equipment_repository()
