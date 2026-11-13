# Purpose: 공식버전 없는 저장소로 연 화면이 마크 대신 회색 한 줄 · 확인 알림을 세우는지 시험한다.

"""불러온 리비전이 없는 화면(카드 p1-no-revision — 2026-11-14 「앱 대신 뜨는 화면」 보드 「좋음」).

공식버전이 없는 DB 를 받았거나 보관본만 남은 드문 때, 계산 화면 본문은 오류 마크가 아니라 값 한 줄
(「공식버전 없음」)이고 Alarm 줄은 확인 단계 · 「그 화면으로」 시나리오 관리 › Capa 시나리오다(설계
규칙 UI-NTF-08 범위 · UI-TXT-04). 화면마다 붙인 머리(「기준정보를 불러오지 못했습니다: …」)가 있어도
같다.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alert_marks import alert_notes, data_error_marks
from streamlit.testing.v1 import AppTest
from test_all_pages_render import _page_script
from test_page_bootstrap import _store_with_scenarios

from capa_simulation import page_bootstrap
from capa_simulation.components.data_error_mark import EMPTY_CLASS
from capa_simulation.components.scenario_management_tabs import CAPA_SCENARIO_TAB_NAME
from capa_simulation.navigation import ALL_SPECS, SCENARIO_MANAGEMENT
from capa_simulation.page_tabs_state import tab_label

# 불러온 리비전으로 본문을 그리는 화면 — 빈 상태 한 줄이 서야 한다.
REVISION_PAGES = (
    "app_pages/home.py",
    "app_pages/static_capa.py",
    "app_pages/load_conversion.py",
    "app_pages/standard_target_capa.py",
    "app_pages/calculation_result.py",
    "app_pages/reference_data.py",
    "app_pages/process_capa_detail.py",
    "app_pages/constraint_simulation.py",
)


@pytest.fixture(scope="module")
def unpublished_databases(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """시나리오 하나 · 공식버전 없음 — 첫 접속이 불러올 것이 없다(내장 시드도 서지 않는다)."""
    root = tmp_path_factory.mktemp("no_revision")
    database = root / "scenario.duckdb"
    _store_with_scenarios(database, archived=0, active=1)
    return database, root / "equipment.duckdb"


def _empty_lines(app: AppTest) -> int:
    return sum(EMPTY_CLASS in str(element.proto.body) for element in app._tree.get("html"))


def test_the_scenario_tab_name_matches_the_screen() -> None:
    """빈 상태 알림의 탭 이름은 시나리오 관리 탭 이름과 같다(그 모듈을 부를 수 없어 글로 둔다)."""
    assert page_bootstrap.SCENARIO_TAB_NAME == CAPA_SCENARIO_TAB_NAME


@pytest.mark.parametrize("page_path", [spec.path for spec in ALL_SPECS])
def test_no_screen_shows_the_error_mark_for_a_missing_official(
    page_path: str, unpublished_databases: tuple[Path, Path]
) -> None:
    """공식버전이 없어 멈춘 화면은 어디서나 마크가 아니라 회색 한 줄이고, 알림은 확인 단계 ·
    시나리오 관리로 가는 줄이다. 리비전으로 본문을 그리는 화면은 반드시 그 한 줄이 선다."""
    database, equipment = unpublished_databases
    app = AppTest.from_string(
        _page_script(page_path, database, equipment), default_timeout=300
    ).run()
    assert not list(app.exception), [element.message for element in app.exception]

    empty_notes = [
        note
        for note in alert_notes(app)
        if page_bootstrap.NO_OFFICIAL_MESSAGE in str(note.get("full", ""))
    ]
    if page_path in REVISION_PAGES:
        assert empty_notes, page_path
    if not empty_notes:
        return
    assert data_error_marks(app) == 0, page_path
    assert _empty_lines(app) >= 1, page_path
    for note in empty_notes:
        assert note["level"] == "check"
        assert note["short"] == "공식버전 없음 — 시나리오 관리에서 발행"
        assert (note["page"], note["href"], note["tab"]) == (
            tab_label(SCENARIO_MANAGEMENT),
            SCENARIO_MANAGEMENT.href,
            CAPA_SCENARIO_TAB_NAME,
        )
        assert "DuckDB" not in str(note["full"])
