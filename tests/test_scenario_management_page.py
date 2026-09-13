# Purpose: 시나리오 관리 페이지가 세 탭의 폼을 한 rerun 에 모두 그리는지 고정한다.

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from test_all_pages_render import _page_script

PAGE_PATH = "app_pages/scenario_management.py"


@pytest.fixture(scope="module")
def seeded_databases(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    root = tmp_path_factory.mktemp("scenario_management")
    return root / "scenario.duckdb", root / "equipment.duckdb"


def test_every_tab_form_is_rendered_in_one_run(seeded_databases: tuple[Path, Path]) -> None:
    """열린 탭만 그리면 다른 탭을 잠깐 여는 순간 그 탭의 form 입력값이 사라진다.

    세 탭의 폼이 한 rerun 에 모두 있어야 탭을 오가도 입력 중이던 값이 남는다.
    """
    database_path, equipment_path = seeded_databases
    app = AppTest.from_string(
        _page_script(PAGE_PATH, database_path, equipment_path), default_timeout=120
    ).run()

    assert not app.exception
    labels = {widget.label for widget in app.text_input}
    # BigDataQuery 등록 폼. 시나리오 관리 탭의 폼(복제 저장·리비전 저장과 목록 관리의 이름
    # 수정·공식 지정)은 탭 안의 작업 선택(segmented control)과 고른 시나리오에 따라
    # 그려지므로 여기 없다. 표시순서 관리는 Admin Area 로 옮겼다.
    assert {"조회할 시뮬레이션 코드"} <= labels
    assert [tab.label for tab in app.main.tabs] == ["시나리오 관리", "BigDataQuery 등록"]
    # 1단계 조회 폼과 2단계 등록 폼이 한 rerun 에 함께 있어야 탭을 오갈 때 값이 남는다.
    assert {"시작일", "종료일"} <= {widget.label for widget in app.date_input}
    assert "시뮬레이션 코드 조회" in {button.label for button in app.button}


def test_list_management_acts_on_the_checked_scenario(
    seeded_databases: tuple[Path, Path],
) -> None:
    """체크한 한 건에 대해서만 작업 칸이 열린다. 두 건을 체크하면 아무것도 열리지 않는다."""
    database_path, equipment_path = seeded_databases
    script = _page_script(PAGE_PATH, database_path, equipment_path)

    app = AppTest.from_string(script, default_timeout=120).run()
    assert not app.exception
    assert "순서 저장" in {button.label for button in app.button}
    # 고른 것이 없으면 작업 버튼이 없다.
    assert "시나리오 보관" not in {button.label for button in app.button}

    # data_editor 위젯 상태는 편집한 셀만 담는다. 체크 한 번을 그 모양 그대로 넣는다.
    app = AppTest.from_string(script, default_timeout=120)
    app.session_state["scenario_list_editor"] = {
        "edited_rows": {0: {"선택": True}},
        "added_rows": [],
        "deleted_rows": [],
    }
    app.run()

    assert not app.exception
    labels = {button.label for button in app.button}
    assert {"시나리오 불러오기", "시나리오명 수정", "공식버전 지정", "시나리오 보관"} <= labels

    app.session_state["scenario_list_action"] = "archive"
    app.run()

    assert not app.exception
    # 보관은 되돌릴 수 있으므로 확인이 체크박스 한 번이다. 영구 삭제만 이름을 받는다.
    assert "보관합니다" in "".join(widget.label for widget in app.checkbox)
    execute = next(button for button in app.button if button.label == "보관 실행")
    assert execute.disabled
