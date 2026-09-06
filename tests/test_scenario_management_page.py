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
    # 시나리오 관리 탭의 이름 수정 폼 · BigDataQuery 등록 폼 · 표시순서 직접 편집 폼. 신규
    # 생성·리비전 저장 폼은 탭 안의 작업 선택(segmented control)에 따라 그려지므로 여기 없다.
    assert {"새 시나리오명", "조회할 시뮬레이션 코드", "변경 메모"} <= labels
