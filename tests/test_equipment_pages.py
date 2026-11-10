# Purpose: 설비·Space 페이지의 초기 진입과 입력·보기 설정·저장 동작을 검증한다.


from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from alert_marks import active_state, data_error_texts, events, place_errors, states
from streamlit.proto.Block_pb2 import Block as BlockProto
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Expander, Multiselect, Status
from test_equipment_availability import _baseline, _downtime, _equipment
from test_process_field import share

from capa_simulation.components import space_layout_editor
from capa_simulation.components.equipment_settings_dialog import (
    EQUIPMENT_DIALOG_KEY,
    SETTINGS_BOX_KEY,
    SETTINGS_BUTTON_KEY,
    SETTINGS_DIALOG_TITLE,
)
from capa_simulation.components.process_field import FIELD_KEY as PROCESS_FIELD_KEY
from capa_simulation.components.sample_data import NO_UNITS_MARK, SAMPLE_TOGGLE_KEY
from capa_simulation.components.table_toolbar import toolbar_room_css
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
    """사이드바 「가용설비 설정」 상자로 공정별 Cut-off 팝업을 연다(개편 전 `Preference` 탭)."""
    return app.button(key=SETTINGS_BUTTON_KEY).click().run()


def _sidebar_keys(app: AppTest) -> list[str]:
    """사이드바 **최상위** 칸의 key 를 화면 차례대로(key 를 준 컨테이너·확장 패널은 id 끝이 그
    key 다). key 가 없는 칸은 빈 문자열이다."""
    keys: list[str] = []
    for node in app.sidebar.children.values():
        identifier = str(getattr(getattr(node, "proto", None), "id", "") or "")
        keys.append(identifier.rsplit("-", 1)[-1] if identifier else "")
    return keys


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
    # 탭 셋(2026-10-24 두 탭 개편, 2026-10-27 Preference): ① 설비 마스터(처음 여는 탭) ②
    # Summary(안쪽 Main·Static 대비 일정) ③ Preference(입력 비가동 대수). Cut-off 는 사이드바
    # 「가용설비 설정」 팝업, Qual 마감 계산기는 필요 단축 일정 팝업, 설비 시나리오는 시나리오
    # 관리다. 설비 마스터 안의 입력표 탭은 최상위 목록과 별개다.
    labels = [tab.label for tab in app.tabs]
    assert [label for label in labels if label.startswith(":material/")] == [
        ":material/table_rows: 설비 마스터",
        ":material/insights: Summary",
        ":material/dashboard: Main",
        ":material/compare_arrows: Static 대비 일정",
        ":material/tune: Preference",
    ]
    assert any(button.key == SETTINGS_BUTTON_KEY for button in app.button)
    _open_tab(app, "Main")
    filter_labels = {
        widget.label
        for widget in app.multiselect
        if widget.label in {"공정구분", "투자구분", "공정대분류", "공정소분류"}
    }
    assert filter_labels == {"공정구분", "투자구분", "공정대분류"}
    # 거르는 조건은 사이드바 카드, 무엇을 볼지(볼 내용·보기·표현)는 본문이다(2026-09-29 결정).
    # 공정소분류는 조회 조건 패널의 공용 공정 칸이다(2026-11-08 사용자 답 P1).
    assert {widget.label for widget in app.sidebar.multiselect} >= filter_labels
    assert PROCESS_FIELD_KEY in {button.key for button in app.sidebar.button}
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


def test_the_settings_box_stands_in_the_sidebar_above_the_card_on_every_tab(
    tmp_path: Path,
) -> None:
    """「가용설비 설정」 은 사이드바 상자다(2026-11-03 사용자 지시 — 설정 단추는 사이드바 상자로).

    본문(제목 줄 끝)에는 설정 단추가 없고 제목 줄은 큰 제목 하나다. 상자는 탭에 매이지 않아 세 탭
    모두 같은 자리에 서고, 카드가 서는 Summary 탭에서는 `설비 조회 조건` 카드 **위**다(사이드바는
    부른 차례로 선다). 누르면 같은 제목의 팝업이 공정별 Cut-off 표로 열린다.
    """
    database_path = tmp_path / "settings_box.duckdb"
    _seeded_equipment(database_path)
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    app = AppTest.from_string(_page_script(page_path, database_path), default_timeout=60).run()
    assert not app.exception
    assert SETTINGS_DIALOG_TITLE == "가용설비 설정"

    for tab in ("Main", "Preference", "설비 마스터"):
        app = _open_tab(app, tab)
        assert not app.exception, tab
        assert SETTINGS_BOX_KEY in _sidebar_keys(app), tab
        assert [button.key for button in app.sidebar.button if button.key == SETTINGS_BUTTON_KEY]
        assert SETTINGS_BUTTON_KEY not in {button.key for button in app.main.button}, tab

    app = _open_tab(app, "Main")
    keys = _sidebar_keys(app)
    card = f"{CONDITION_CARD_PREFIX}equipment"
    assert keys.index(SETTINGS_BOX_KEY) < keys.index(card)
    box = next(button for button in app.sidebar.button if button.key == SETTINGS_BUTTON_KEY)
    assert box.label == SETTINGS_DIALOG_TITLE and not box.disabled
    assert "공정별 Cut-off" in str(box.help)

    app = _open_settings(app)
    assert not app.exception
    assert app.session_state[EQUIPMENT_DIALOG_KEY] == "settings"
    assert any(button.label == "Cut-off 저장" for button in app.button)
    clear_equipment_repository()


def test_the_settings_box_is_locked_in_place_when_the_equipment_db_cannot_open(
    tmp_path: Path,
) -> None:
    """설비 DB 를 읽지 못한 회차 — 페이지는 오류를 알리고 멈추고, 「가용설비 설정」 상자는 잠긴 채
    같은 자리에 선다(팝업 본문의 저장소가 없다 — HOME 계산 멈춤의 「HOME 설정」 과 같은 꼴)."""
    database_path = tmp_path / "broken.duckdb"
    database_path.write_bytes(b"not a database file")
    clear_equipment_repository()
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    app = AppTest.from_string(_page_script(page_path, database_path), default_timeout=60).run()

    assert not app.exception
    assert any("설비 현황을 준비하지 못했습니다" in text for text in data_error_texts(app))
    assert _sidebar_keys(app) == [SETTINGS_BOX_KEY]
    box = app.button(key=SETTINGS_BUTTON_KEY)
    assert box.disabled
    assert "설비 DB 를 읽지 못해" in str(box.help)
    clear_equipment_repository()


def test_baseline_paste_import_needs_a_preview_before_it_saves(tmp_path: Path) -> None:
    """「엑셀·CSV로 한꺼번에」 팝업의 붙여넣기·미리보기·「편집본에 넣기」 는 저장하지 않고,
    「저장 전 변경」 의 「리비전 저장」 이 불변 리비전에 한 번에 저장한다(개편 B1 — 첫 리비전도 한
    길)."""
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    database_path = tmp_path / "baseline_import.duckdb"
    app = AppTest.from_string(
        _page_script(page_path, database_path),
        default_timeout=60,
    ).run()
    _open_tab(app, "설비 마스터")
    app.session_state[EQUIPMENT_DIALOG_KEY] = "import"
    app.run()
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
    app.button("equipment_import_apply_v1").click().run()
    assert not app.exception
    # 넣기는 편집본만 바꾼다 — 저장본 사본·리비전은 그대로다.
    assert not repository.list_revisions()
    assert app.session_state["equipment_baseline_draft_v3"].empty
    assert app.session_state["equipment_workspace_buffers_v1"][0]["공정"].tolist() == ["Process-X"]
    app.session_state["equipment_master_side_v1"] = "저장 전 변경"
    app.run()
    app.button("equipment_master_save_v1").click().run()

    assert not app.exception
    assert not place_errors(app)
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
    tmp_path: Path, date_panels: dict[str, dict[str, Any]]
) -> None:
    """호기가 없고 샘플을 끄면 카드 안에 값 한 마디(「조회할 호기 없음」)와 풍선을 둔다.

    카드 없이 멈추면 사이드바에 「조회 조건 · 이 화면에 적용」 제목만 덩그러니 남았다
    (2026-10-01 브라우저 실측). 가용설비 현황의 같은 자리와 같은 모양이다. 하는 법 · 호기 없이도
    FAB 배치를 고친다는 말은 풍선이다(설계 규칙 UI-TXT-03 · UI-TXT-04) — 카드 · 본문 어디에도 그
    문장이 서지 않는다.
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
    (mark,) = [item for item in app.sidebar.caption if str(item.value) == NO_UNITS_MARK]
    assert "샘플 데이터" in mark.proto.help and "FAB 전체 배치" in mark.proto.help
    captions = [str(item.value) for item in (*app.sidebar.caption, *app.main.caption)]
    assert not any(
        "켜세요" in text or "고치고 저장할 수 있습니다" in text or "데모 fleet" in text
        for text in captions
    )
    # 조건 위젯은 서지 않는다 — 고를 호기가 없다.
    assert not date_panels
    assert not app.sidebar.multiselect


def test_space_page_counts_placement_and_leaves_stage_transitions_to_availability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    date_panels: dict[str, dict[str, Any]],
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
    # 사이드바 카드에는 고르는 칸이 없다 — 전환 조회기간·전환단계 폼이 없고, 기준일 칸과 「단계」
    # 필터도 없다(기준일은 층 상세 도면 위 페이더, 2026-10-16 사용자 결정). 공정소분류는 조회 조건
    # 패널의 공용 공정 칸(값 칸 하나)이다(2026-11-08 사용자 답 P1).
    assert not date_panels
    assert not app.sidebar.multiselect
    assert PROCESS_FIELD_KEY in {button.key for button in app.sidebar.button}
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


def _canvas_checkboxes(app: AppTest) -> list[object]:
    """캔버스 팝업의 체크 칸(이 화면 사이드바의 색 기준 체크는 뺀다)."""
    return [box for box in app.checkbox if str(box.key).startswith("space_floor_layout")]


def test_space_floor_detail_offers_the_canvas_dialog_and_ignores_an_old_drawing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """캔버스 편집 팝업은 폭 · 높이 · 저장 단추뿐이다(검수 equip-60 — 도면 올리기 · 자동 계산 ·
    지우기 · 설명 글을 걷었다). 옛 판이 올린 도면 그림은 표에 남아도 뷰어에 싣지 않는다."""
    database_path = tmp_path / "space_layout.duckdb"
    repository = DuckDBEquipmentRepository(database_path)
    repository.initialize()
    repository.save_floor_layout_canvas("C1", "1F", 100.0, 37.5)
    with repository._connect() as connection:
        connection.execute(
            "UPDATE equipment_ops.floor_layout_profile "
            "SET image_mime = 'image/png', image_name = 'old.png', image_payload = ?",
            [b"old-drawing"],
        )
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
    assert viewer[-1]["canvas"] == {"width": 100.0, "height": 37.5}
    assert "backgroundImage" not in viewer[-1]
    # 캔버스 편집은 사이드바 「Space 도면」 상자 단추의 팝업이다 — 닫혀 있는 동안 본문을 차지하지
    # 않는다.
    assert not app.number_input
    opener = app.button(key="space_floor_layout_open_C1_1F")
    assert opener.label == "캔버스 편집"
    opener.click().run()
    assert not app.exception
    assert len(app.get("file_uploader")) == 0
    assert [widget.label for widget in app.number_input] == ["캔버스 폭", "캔버스 높이"]
    assert not _canvas_checkboxes(app) and not app.success
    for element in (*app.caption, *app.warning):
        for word in ("배경 도면", "종횡비", "적용될 캔버스", "이탈 호기"):
            assert word not in str(element.value)
    assert [element.value for element in app.markdown if "37.5" in str(element.value)]
    assert "저장된 도면" not in "".join(str(element.value) for element in app.markdown)
    save = app.button(key="space_floor_layout_save_C1_1F")
    assert save.label == "캔버스 저장" and not save.disabled
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
    """C1 1F 를 열고 공정 필터를 Process-A 로 둔 뒤 캔버스 팝업을 연다."""
    page_path = PROJECT_ROOT / "app_pages" / "space_status.py"
    app = AppTest.from_string(_page_script(page_path, database_path), default_timeout=60)
    app.session_state["space_status_selected_building"] = "C1"
    app.session_state["space_status_selected_floor"] = "1F"
    app.run()
    share(app, ["Process-A"])
    app.run()
    app.button(key="space_floor_layout_open_C1_1F").click().run()
    assert not app.exception
    return app


def test_the_canvas_dialog_checks_hidden_units_before_shrinking_the_canvas(
    tmp_path: Path,
) -> None:
    """캔버스 줄이기 검사는 층 화면에 그린 호기가 아니라 그 층의 저장된 호기 전부를 본다.

    레이아웃표시 N·공정 필터로 화면에 없는 호기도 저장 검증은 본다. 팝업이 그 호기를 빼고 재면
    알림 없이 줄인 뒤 그 다음 설비 저장(어느 칸을 고치든)이 전부 「캔버스 밖」으로 막힌다. 호기
    목록은 알림창으로만 가고(`EQ-16`) 자리에는 확인 칸 하나 · 잠긴 저장 단추 + 짧은 풍선이 남는다.
    되돌리면 「해소」 다."""
    database_path = tmp_path / "space_hidden.duckdb"
    _wide_floor_with_hidden_units(database_path)
    app = _open_wide_floor_dialog(database_path)
    assert active_state(app, "EQ-16") is None

    app.number_input(key="space_floor_layout_width_C1_1F").set_value(100.0)
    app.number_input(key="space_floor_layout_height_C1_1F").set_value(60.0).run()

    assert not app.exception
    assert not app.warning
    note = active_state(app, "EQ-16")
    assert note is not None
    assert note["short"] == "C1 1F 캔버스 100 × 60 밖 — 호기 2대"
    assert "DEMO-EQ01" in note["full"] and "DEMO-EQ02" in note["full"]
    assert "\\-" not in note["full"]
    save = app.button(key="space_floor_layout_save_C1_1F")
    assert save.disabled and "확인" in str(save.help)
    confirm = app.checkbox(key="space_floor_layout_shrink_C1_1F")
    assert confirm.label == "이탈 호기 2대 알고 저장"
    confirm.check().run()
    assert not app.button(key="space_floor_layout_save_C1_1F").disabled

    app.number_input(key="space_floor_layout_width_C1_1F").set_value(200.0)
    app.number_input(key="space_floor_layout_height_C1_1F").set_value(100.0).run()
    assert active_state(app, "EQ-16") is None
    assert not _canvas_checkboxes(app)
    clear_equipment_repository()


def test_a_canvas_saved_over_outside_units_says_what_it_blocks(tmp_path: Path) -> None:
    """저장 결과는 알림창이다 — 호기를 밖에 둔 채 저장했으면 설비 저장이 막힌다는 말까지. 저장하면
    팝업이 닫히고 밖 알림은 해소된다."""
    database_path = tmp_path / "space_hidden_saved.duckdb"
    _wide_floor_with_hidden_units(database_path)
    app = _open_wide_floor_dialog(database_path)
    app.number_input(key="space_floor_layout_width_C1_1F").set_value(100.0).run()
    app.checkbox(key="space_floor_layout_shrink_C1_1F").check().run()
    app.button(key="space_floor_layout_save_C1_1F").click().run()

    assert not app.exception
    assert not app.number_input
    assert DuckDBEquipmentRepository(database_path).load_floor_layout_canvases()[("C1", "1F")] == (
        100.0,
        100.0,
    )
    assert active_state(app, "EQ-16") is None
    assert [str(note["short"]) for note in events(app, "FL-03")] == [
        "C1 1F 캔버스 100 × 100 저장 — 호기 2대가 밖이라 설비 저장이 막힙니다"
    ]
    clear_equipment_repository()


def test_units_outside_a_saved_canvas_are_one_alert_for_the_whole_fab(tmp_path: Path) -> None:
    """저장된 캔버스 밖 호기는 층 화면 맨 위 상자가 아니라 상태 알림 `EQ-18` 이다 — 전 층을 훑어
    FAB · 고른 층 · 공정 필터 어디서나 지문이 같고(고를 때마다 다시 뜨지 않는다), 층별 수 · 설비명은
    전문에 있다(마크다운이 아니라 막지 않는다). 캔버스를 넓히면 해소다."""
    database_path = tmp_path / "space_outside.duckdb"
    _wide_floor_with_hidden_units(database_path)
    DuckDBEquipmentRepository(database_path).save_floor_layout_canvas("C1", "1F", 100.0, 100.0)
    clear_equipment_repository()
    page_path = PROJECT_ROOT / "app_pages" / "space_status.py"
    app = AppTest.from_string(_page_script(page_path, database_path), default_timeout=60)
    app.run()

    assert not app.exception
    assert not app.warning
    fab = active_state(app, "EQ-18")
    assert fab is not None
    assert fab["level"] == "action"
    assert fab["short"] == "캔버스 밖 호기 2대(C1 1F)"
    assert fab["full"].startswith("C1 1F 캔버스 100 × 100 밖 2대: DEMO-EQ01, DEMO-EQ02\n")
    assert "공식 설비 시나리오에서 그 층의 「캔버스 편집」" in fab["full"]

    app.session_state["space_status_selected_building"] = "C1"
    app.session_state["space_status_selected_floor"] = "1F"
    app.run()
    assert not app.warning
    floor = active_state(app, "EQ-18")
    assert floor is not None and floor["fp"] == fab["fp"] and floor["scope"] == fab["scope"]

    share(app, ["Process-A"])
    app.run()
    filtered = active_state(app, "EQ-18")
    assert filtered is not None and filtered["fp"] == fab["fp"]

    # 밖 호기가 그대로여도 크기가 바뀌면 지문이 바뀐다 — 지문이 같으면 브라우저가 옛 전문을 둔다.
    DuckDBEquipmentRepository(database_path).save_floor_layout_canvas("C1", "1F", 120.0, 100.0)
    clear_equipment_repository()
    app.run()
    resized = active_state(app, "EQ-18")
    assert resized is not None and resized["short"] == fab["short"]
    assert resized["scope"] == fab["scope"] and resized["fp"] != fab["fp"]
    assert resized["full"].startswith("C1 1F 캔버스 120 × 100 밖 2대: DEMO-EQ01, DEMO-EQ02\n")

    DuckDBEquipmentRepository(database_path).save_floor_layout_canvas("C1", "1F", 200.0, 100.0)
    clear_equipment_repository()
    app.run()
    assert not app.exception
    assert active_state(app, "EQ-18") is None
    assert [note["active"] for note in states(app, "EQ-18")] == [False]
    clear_equipment_repository()


def test_the_outside_alert_counts_units_without_a_schedule(tmp_path: Path) -> None:
    """저장 검증은 일정 없는 호기까지 보므로 `EQ-18` 도 센다 — 계산 표(`calculation_frames`)는 그
    호기를 빼 저장이 막히는데도 알림이 안 설 수 있다."""
    database_path = tmp_path / "space_unscheduled.duckdb"
    _wide_floor_with_hidden_units(database_path)
    repository = DuckDBEquipmentRepository(database_path)
    repository.save_floor_layout_canvas("C1", "1F", 100.0, 100.0)
    scenario = next(
        item
        for item in repository.list_equipment_scenarios()
        if item.equipment_scenario_id == "operations"
    )
    schedule = scenario.latest_schedule_revision_id
    assert schedule is not None
    unit_key = repository.load_saved_pair(schedule).unit_keys["DEMO-EQ02"]
    with repository._connect() as connection:
        connection.execute(
            "DELETE FROM equipment_ops.equipment_schedule_snapshot "
            "WHERE schedule_revision_id = ? AND unit_key = ?",
            [schedule, unit_key],
        )
    clear_equipment_repository()
    assert repository.load_saved_pair(schedule).unscheduled_units == frozenset({"DEMO-EQ02"})

    page_path = PROJECT_ROOT / "app_pages" / "space_status.py"
    app = AppTest.from_string(_page_script(page_path, database_path), default_timeout=60)
    app.run()

    assert not app.exception
    note = active_state(app, "EQ-18")
    assert note is not None
    assert note["full"].startswith("C1 1F 캔버스 100 × 100 밖 2대: DEMO-EQ01, DEMO-EQ02\n")
    assert active_state(app, "EQ-04") is not None
    clear_equipment_repository()


def test_the_outside_alert_stays_quiet_when_nothing_is_outside(tmp_path: Path) -> None:
    """조건이 없어도 표지 자리는 한 번 쓴다(`active` 거짓 — 표지 자리 수가 회차마다 같다)."""
    database_path = tmp_path / "space_inside.duckdb"
    _wide_floor_with_hidden_units(database_path)
    page_path = PROJECT_ROOT / "app_pages" / "space_status.py"
    app = AppTest.from_string(_page_script(page_path, database_path), default_timeout=60)
    app.run()

    assert not app.exception
    assert [note["active"] for note in states(app, "EQ-18")] == [False]
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


def test_the_preference_tab_lists_the_saved_processes_by_the_period_months(
    tmp_path: Path,
) -> None:
    """③ Preference — 행은 저장본의 공정, 열은 사이드바 조회기간의 달이다(설비 0032 공용 프로필).

    다른 탭을 보는 회차에도 폼은 서 있다(적은 칸을 지킨다) — 저장 이력만 열린 회차에 선다.
    """
    from capa_simulation.components.manual_downtime_tab import MANUAL_EDITOR_KEY
    from capa_simulation.scenario_preset_state import MONTH_RANGE_KEY

    database_path = tmp_path / "availability.duckdb"
    _seeded_equipment(database_path)
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    app = AppTest.from_string(_page_script(page_path, database_path), default_timeout=60)
    app.session_state[MONTH_RANGE_KEY] = ("2026-07", "2026-09")
    app.run()
    assert not app.exception
    hidden = next(frame for frame in app.dataframe if MANUAL_EDITOR_KEY in frame.proto.id)
    assert hidden.value["공정"].tolist() == ["DEMO_PROC"]
    assert not any(item.label.startswith(":material/history:") for item in app.expander)

    app = _open_tab(app, "Preference")
    assert not app.exception
    editor = next(frame for frame in app.dataframe if MANUAL_EDITOR_KEY in frame.proto.id)
    assert list(editor.value.columns) == ["공정", "202607", "202608", "202609"]
    assert any(item.label.startswith(":material/history:") for item in app.expander)
    clear_equipment_repository()


def _blocks(node: Any) -> list[Any]:
    from streamlit.testing.v1.element_tree import Block

    out: list[Any] = []
    for child in getattr(node, "children", {}).values():
        if isinstance(child, Block):
            out.append(child)
            out.extend(_blocks(child))
    return out


def _view_popovers(app: AppTest) -> list[Any]:
    return [
        block
        for block in _blocks(app.main)
        if getattr(block, "type", None) == "popover" and "_view_popover" in str(block.proto.id)
    ]


def test_the_view_controls_render_for_each_small_editor(tmp_path: Path) -> None:
    """작은 편집표 둘(기존 보유대수·비가동 일정)에 각각 컬럼 선택과 행 필터가 붙는다 — 설비
    마스터는 표 컴포넌트(칸 묶음·정렬·불러오기)라 보기 설정이 없다(개편 B1).

    보기 적용과 리비전 저장은 별개다. 필터 변경만으로 불변 리비전을 만들지 않는다.
    """
    database_path = tmp_path / "availability.duckdb"
    _seeded_equipment(database_path)
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    app = AppTest.from_string(_page_script(page_path, database_path), default_timeout=60).run()

    assert not app.exception
    assert not _view_popovers(app)
    for table, slug, prefix in (
        ("기존 보유대수", "baseline", "equipment_baseline_view"),
        ("비가동 일정", "downtime", "equipment_downtime_view"),
    ):
        app.session_state["equipment_master_table_v1"] = table
        app.run()
        assert not app.exception
        # 보기 설정은 접힘 줄이 아니라 표 작업 줄 끝 「표 보기 ▾」 팝오버다(2026-11-09 사용자 보드
        # T5) — 「편집본에 적용」 과 한 가로 칸이다.
        assert not [item for item in app.status if "표 보기" in item.label], table
        (row,) = [
            block
            for block in _blocks(app.main)
            if any(
                getattr(child, "key", None) == f"equipment_{slug}_apply_v1"
                for child in block.children.values()
            )
        ]
        assert row.proto.flex_container.direction == BlockProto.FlexContainer.Direction.HORIZONTAL
        menu, view = [
            child for child in row.children.values() if getattr(child, "type", None) == "popover"
        ]
        assert str(view.proto.id).endswith(f"-{prefix}_view_popover")
        # 「선택 해제」 · 「선택 행 삭제」 는 「모두 선택」 곁 「선택 ▾」 메뉴 하나다(2026-11-10
        # 사용자 답 Q-14 「한 줄로」) — 단추 key 는 그대로다.
        assert menu.proto.popover.label == "선택"
        assert str(menu.proto.id).endswith(f"-equipment_{slug}_selection_menu_v1__g0")
        assert [(button.label, button.key) for button in menu.button] == [
            ("선택 해제", f"equipment_{slug}_select_clear_v1"),
            ("선택 행 삭제", f"equipment_{slug}_delete_selected_v1"),
        ]
        assert [
            child.label
            for child in row.children.values()
            if getattr(child, "type", None) == "button"
        ] == ["편집본에 적용", "모두 선택"]
        assert view.proto.popover.label == "표 보기"
        # 작업 줄 오른쪽 끝은 표 도구 막대 자리로 비운다 — 표가 줄 바로 아래 붙어 단추가 그 자리에
        # 닿으면 막대가 덮는다(AGENTS 9장 「표 도구 막대」).
        action_row = f"equipment_small_{slug}_action_row_v1"
        assert getattr(row, "key", None) == action_row
        assert f"<style>{toolbar_room_css(action_row)}</style>" in [
            str(element.proto.body) for element in app.get("html")
        ]
        assert app.multiselect(f"{prefix}_columns").value
        # 「보기 적용」 은 고르는 칸이 든 팝오버 안이다(설계 규칙 UI-LAY-03).
        assert [button.label for button in view.button] == ["보기 적용"]
    assert len(DuckDBEquipmentRepository(database_path).list_revisions()) == 1
    clear_equipment_repository()


def test_the_filter_mark_follows_the_applied_view_not_the_picked_one(tmp_path: Path) -> None:
    """「표 보기 · 필터」 표지 · 잠김 풍선은 편집표에 **건** 보기를 따른다(설계 규칙 UI-DAT-11).
    작은 편집표는 폼 밖이라 필터 값을 고르는 즉시 회차가 돈다 — 고르기만 하고 「보기 적용」 을
    누르지 않으면 표는 아직 거르지 않고 행 추가 · 삭제도 열려 있으니 표지가 없다. 적용한 뒤 칸을
    비우기만 하면 표는 아직 걸러져 잠겨 있으니 표지가 남는다."""
    from capa_simulation.components.table_view_controls import FILTERED_NOTICE

    database_path = tmp_path / "availability.duckdb"
    _seeded_equipment(database_path)
    repository = DuckDBEquipmentRepository(database_path)
    snapshot = repository.load_snapshot(repository.list_revisions()[0].revision_id)
    baseline = pd.concat(
        [
            snapshot.baseline,
            pd.DataFrame(
                {"공정": ["DEMO_OTHER"], "분류": ["기존"], "기존보유대수": [2.0], "비고": ["둘째"]}
            ),
        ],
        ignore_index=True,
    )
    repository.save_snapshot(baseline, snapshot.equipment, snapshot.downtime, note="둘째 공정")
    clear_equipment_repository()
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    app = AppTest.from_string(_page_script(page_path, database_path), default_timeout=60).run()
    app.session_state["equipment_master_table_v1"] = "기존 보유대수"
    app.run()

    def mark() -> tuple[str, str]:
        (view,) = _view_popovers(app)
        return str(view.proto.popover.label), str(view.proto.popover.help)

    picker = "equipment_baseline_view_filter_공정"
    apply = "equipment_baseline_view_apply_v1"
    assert mark() == ("표 보기", "")
    app.multiselect(picker).set_value(["DEMO_PROC"]).run()
    assert not app.exception
    assert mark() == ("표 보기", "")
    app.button(apply).click().run()
    assert not app.exception
    assert mark() == ("표 보기 · 필터", FILTERED_NOTICE)
    app.multiselect(picker).set_value([]).run()
    assert mark() == ("표 보기 · 필터", FILTERED_NOTICE)
    app.button(apply).click().run()
    assert mark() == ("표 보기", "")
    clear_equipment_repository()


def test_hiding_a_column_keeps_its_values_in_the_saved_frame(tmp_path: Path) -> None:
    """감춘 컬럼도 편집본에는 그대로 들어간다.

    `st.data_editor` 는 `column_config={컬럼: None}` 으로 감춘 컬럼의 값을 반환 프레임에
    그대로 돌려준다. 값이 빠져 나가면 적용·저장이 그 컬럼을 통째로 비운다. 보기 설정은 탭을
    옮겨도 남는다(`persist_state` — 탭 ① 은 숨은 회차에 그리지 않는다).
    """
    database_path = tmp_path / "availability.duckdb"
    _seeded_equipment(database_path)
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    app = AppTest.from_string(
        _page_script(page_path, database_path),
        default_timeout=60,
    ).run()
    _open_tab(app, "설비 마스터")
    app.session_state["equipment_master_table_v1"] = "기존 보유대수"
    app.run()
    picker = app.multiselect("equipment_baseline_view_columns")
    remaining = [column for column in picker.value if column != "비고"]
    picker.set_value(remaining)
    app.button("equipment_baseline_view_apply_v1").click().run()
    _open_tab(app, "Main")
    _open_tab(app, "설비 마스터")
    assert app.multiselect("equipment_baseline_view_columns").value == remaining
    app.button("equipment_baseline_apply_v1").click().run()
    app.session_state["equipment_master_side_v1"] = "저장 전 변경"
    app.run()
    app.button("equipment_master_save_v1").click().run()

    assert not app.exception
    assert not place_errors(app)
    buffer = app.session_state["equipment_workspace_buffers_v1"]
    assert buffer[0]["비고"].tolist() == ["숨겨도 유지할 값"]
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
    """저장본이 없으면 첫 화면이 세 데이터를 건수와 함께 짚는다 — 설비 마스터 · 운영 비가동 줄은
    넣는 팝업으로 가는 단추를 달고, Cut-off 줄은 건수만이다(공용 설정이라 사이드바 「가용설비
    설정」 상자가 연다 — 설계 규칙 UI-LAY-01 · AMB-07 (가)).

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
    assert "✗ **비가동 일정** 0건" in rendered
    # 저장된 것은 ✓ 로 구분한다. 세 줄 중 이 줄만 tmp DB 에 따라 값이 달라진다.
    assert "✓ **공정별 Cut-off** 1건" in rendered
    # Cut-off 줄에는 본문 설정 단추가 없다 — 「가용설비 설정」 팝업은 사이드바 상자만 연다.
    keys = {button.key for button in app.button}
    assert "equipment_first_data_cut_v1" not in keys
    assert "설정에서 보기" not in [button.label for button in app.button]
    # 「설비 마스터 탭에서 붙여넣기」 는 탭 ① 을 연다.
    app.button("equipment_first_data_master_v1").click().run()
    assert not app.exception
    assert app.session_state[EQUIPMENT_TAB_KEY] == ":material/table_rows: 설비 마스터"
    clear_equipment_repository()


def _recording_page_script(page_path: Path, database_path: Path) -> str:
    """`_page_script` 에 Summary 의 두 본문(Main 탐색·Static 대비 일정 구간 계산)을 부른 기록을
    단다."""
    simulation_database_path = database_path.with_name(f"{database_path.stem}_simulation.duckdb")
    return f"""
from pathlib import Path
import streamlit as st
import capa_simulation.settings as settings
import capa_simulation.components.equipment_explorer as explorer
import capa_simulation.services.simulation_cache as simulation_cache

settings.EQUIPMENT_DUCKDB_PATH = Path({str(database_path)!r})
settings.DUCKDB_PATH = Path({str(simulation_database_path)!r})
calls = st.session_state.setdefault("summary_calls", [])
original_explorer = explorer.render_equipment_explorer
original_spans = simulation_cache.get_equipment_lifecycle_spans


def recording_explorer(*args, **kwargs):
    calls.append("explorer")
    return original_explorer(*args, **kwargs)


def recording_spans(*args, **kwargs):
    calls.append("spans")
    return original_spans(*args, **kwargs)


explorer.render_equipment_explorer = recording_explorer
simulation_cache.get_equipment_lifecycle_spans = recording_spans
try:
    page_source = Path({str(page_path)!r}).read_text(encoding="utf-8")
    exec(compile(page_source, {str(page_path)!r}, "exec"), {{"__name__": "__main__"}})
finally:
    explorer.render_equipment_explorer = original_explorer
    simulation_cache.get_equipment_lifecycle_spans = original_spans
"""


def test_the_master_tab_run_skips_the_summary_work(tmp_path: Path) -> None:
    """Summary 의 안쪽 탭은 바깥 Summary 안에서 늘 부르므로 바깥이 숨어도 안쪽 고른 탭의 `open` 은
    참이다 — 본문 갈래는 둘을 합친 판정(`NestedTab`)이라 ① 을 보는 회차에 Main 탐색·Static 대비 일정
    구간 계산을 부르지 않는다(사양 R23)."""
    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    app = AppTest.from_string(
        _recording_page_script(page_path, tmp_path / "skip.duckdb"), default_timeout=60
    ).run()
    assert not app.exception
    assert app.session_state["summary_calls"] == []

    _open_tab(app, "Static 대비 일정")
    assert "spans" in app.session_state["summary_calls"]
    _open_tab(app, "Main")
    assert "explorer" in app.session_state["summary_calls"]

    # ① 로 돌아오면(안쪽은 Main 을 고른 채) 다시 부르지 않는다.
    app.session_state["summary_calls"] = []
    _open_tab(app, "설비 마스터")
    assert not app.exception
    assert app.session_state["summary_calls"] == []
    clear_equipment_repository()


def test_unsaved_equipment_edits_put_a_dot_on_the_master_tab(tmp_path: Path) -> None:
    """저장하지 않은 설비 편집이 있으면 ① 탭 이름 옆에 점 — 라벨 글자는 그대로(탭 위젯 id), CSS 로
    찍는다(`tab_marks`). 판정은 화면 탭 줄의 점과 같다(편집본 세대가 씨앗보다 앞섬)."""
    from capa_simulation.components.equipment_data_workspace import BUFFER_GENERATION_KEY
    from capa_simulation.components.tab_marks import pending_tabs_style
    from capa_simulation.navigation import EQUIPMENT_MASTER_TAB, EQUIPMENT_TABS

    page_path = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    app = AppTest.from_string(
        _page_script(page_path, tmp_path / "dot.duckdb"), default_timeout=60
    ).run()
    dot = pending_tabs_style(EQUIPMENT_TAB_KEY, EQUIPMENT_TABS, {EQUIPMENT_MASTER_TAB}).strip()
    bodies = [str(element.proto.body).strip() for element in app.get("html")]
    assert dot not in bodies

    app.session_state[BUFFER_GENERATION_KEY] = int(app.session_state[BUFFER_GENERATION_KEY]) + 1
    app.run()
    assert not app.exception
    assert dot in [str(element.proto.body).strip() for element in app.get("html")]
    assert app.tabs[0].label == EQUIPMENT_MASTER_TAB
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
