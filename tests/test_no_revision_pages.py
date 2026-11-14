# Purpose: 공식버전 없는 저장소로 연 화면이 회색 한 줄 · 공식버전 없음 알림 하나를 세우나 시험한다.

"""불러온 리비전이 없는 화면(카드 p1-no-revision — 2026-11-14 「앱 대신 뜨는 화면」 보드 「좋음」).

공식버전이 없는 DB 를 받았거나 보관본만 남은 드문 때, 계산 화면 본문은 오류 마크가 아니라 값 한 줄
(「공식버전 없음」)이고 알림은 화면마다 따로 뜨지 않고 상태 알림 `SC-01` 하나다 — 시나리오 관리
「Capa 시나리오」 탭과 같은 표지라 어느 화면을 돌아도 Alarm 줄 하나 · 알림창 한 번이다(2026-11-14
물음 보드 decided 5, 설계 규칙 UI-NTF-02 · UI-NTF-08 범위 · UI-TXT-04). 사이드바의 잠긴 공정 줄도
「계산 멈춤」 이 아니라 본문과 같은 「공식버전 없음」 이다(UI-DAT-11). 화면마다 붙인
머리(「기준정보를 불러오지 못했습니다: …」)가 있어도 같다.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alert_marks import alert_notes, data_error_marks, events, states
from streamlit.testing.v1 import AppTest
from test_all_pages_render import _page_script
from test_page_bootstrap import _store_with_scenarios

from capa_simulation import page_bootstrap
from capa_simulation.components.data_error_mark import EMPTY_CLASS
from capa_simulation.components.home_preference import KEY_PROCESS_FIELD_KEY
from capa_simulation.components.process_field import FIELD_KEY as SHARED_PROCESS_FIELD_KEY
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
# 멈춘 회차에 사이드바 공정 줄을 잠근 채 세우는 화면과 그 값 칸 key(HOME 공정 필터는
# `app_pages/home.py` 의 `PROCESS_FIELD_KEY` — 페이지 파일이라 글로 둔다).
HOME_PROCESS_FILTER_KEY = "dashboard_bottleneck_process_dialog_open"
STOPPED_FIELD_PAGES = {
    "app_pages/home.py": (HOME_PROCESS_FILTER_KEY, KEY_PROCESS_FIELD_KEY),
    "app_pages/calculation_result.py": (SHARED_PROCESS_FIELD_KEY,),
    "app_pages/process_capa_detail.py": (SHARED_PROCESS_FIELD_KEY,),
    "app_pages/constraint_simulation.py": (SHARED_PROCESS_FIELD_KEY,),
}


@pytest.fixture(scope="module")
def unpublished_databases(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """시나리오 하나 · 공식버전 없음 — 첫 접속이 불러올 것이 없다(내장 시드도 서지 않는다)."""
    root = tmp_path_factory.mktemp("no_revision")
    database = root / "scenario.duckdb"
    _store_with_scenarios(database, archived=0, active=1)
    return database, root / "equipment.duckdb"


def _empty_lines(app: AppTest) -> int:
    return sum(EMPTY_CLASS in str(element.proto.body) for element in app._tree.get("html"))


def _active_missing(app: AppTest) -> list[dict[str, object]]:
    return [note for note in states(app, "SC-01") if note["active"]]


def test_the_scenario_tab_name_matches_the_screen() -> None:
    """빈 상태 알림의 탭 이름은 시나리오 관리 탭 이름과 같다(그 모듈을 부를 수 없어 글로 둔다)."""
    assert page_bootstrap.SCENARIO_TAB_NAME == CAPA_SCENARIO_TAB_NAME


def test_one_missing_official_alert_is_the_same_mark_wherever_it_comes_from() -> None:
    """공식버전 없음은 한 표지다 — 범위가 없고 내용 값이 갈래라 어느 화면이 내도 Alarm 줄 하나 ·
    알림창 한 번이고, 해소 표지는 같은 줄(범위)을 닫는다. 보관본만 남은 갈래는 내용이 달라 새로
    뜬다."""
    none = page_bootstrap.missing_official_note("none")
    archived = page_bootstrap.missing_official_note("archived_only")
    resolved = page_bootstrap.missing_official_note(None)

    assert none["code"] == archived["code"] == resolved["code"] == "SC-01"
    assert none["kind"] == "state" and none["level"] == "check"
    assert none["active"] and archived["active"] and not resolved["active"]
    assert none["scope"] == archived["scope"] == resolved["scope"]
    assert none["fp"] and archived["fp"] and none["fp"] != archived["fp"]
    assert resolved["fp"] == ""
    for note in (none, archived):
        assert (note["page"], note["href"], note["tab"]) == (
            tab_label(SCENARIO_MANAGEMENT),
            SCENARIO_MANAGEMENT.href,
            CAPA_SCENARIO_TAB_NAME,
        )
    assert "보관함" in archived["short"] and "보관함" not in none["short"]


@pytest.mark.parametrize("page_path", [spec.path for spec in ALL_SPECS])
def test_no_screen_shows_the_error_mark_for_a_missing_official(
    page_path: str, unpublished_databases: tuple[Path, Path]
) -> None:
    """공식버전이 없어 멈춘 화면은 어디서나 마크가 아니라 회색 한 줄이고, 알림은 그 화면 코드의 사건
    알림이 아니라 공식버전 없음 상태 알림 `SC-01` 하나다(시나리오 관리 탭과 같은 표지 — 범위 ·
    지문이 같다). 리비전으로 본문을 그리는 화면은 반드시 그 알림을 내고, 그 알림을 낸 화면은
    시나리오 관리(목록 탭이 회색 줄 없이 알림을 낸다)만 빼고 모두 그 한 줄이 선다 — 필요 단축
    일정 · 재공 현황도 그렇다. 멈춘 사이드바 공정 줄도 본문과 같은 「공식버전 없음」 이다."""
    database, equipment = unpublished_databases
    app = AppTest.from_string(
        _page_script(page_path, database, equipment), default_timeout=300
    ).run()
    assert not list(app.exception), [element.message for element in app.exception]

    # 화면마다 따로 뜨던 사건 알림(그 화면 코드 + 빈 상태 글)은 없다.
    assert not [
        note
        for note in alert_notes(app)
        if note.get("kind") == "event"
        and page_bootstrap.NO_OFFICIAL_MESSAGE in str(note.get("full", ""))
    ], page_path
    expected = page_bootstrap.missing_official_note("none")
    missing = _active_missing(app)
    if page_path in REVISION_PAGES:
        assert missing, page_path
    if not missing:
        return
    assert data_error_marks(app) == 0, page_path
    if page_path != SCENARIO_MANAGEMENT.path:
        assert _empty_lines(app) >= 1, page_path
    for note in missing:
        assert (note["scope"], note["fp"]) == (expected["scope"], expected["fp"]), page_path
        assert note["level"] == "check"
        assert note["short"] == expected["short"]
        assert (note["page"], note["href"], note["tab"]) == (
            tab_label(SCENARIO_MANAGEMENT),
            SCENARIO_MANAGEMENT.href,
            CAPA_SCENARIO_TAB_NAME,
        )
        assert "DuckDB" not in str(note["full"])
    for key in STOPPED_FIELD_PAGES.get(page_path, ()):
        field = app.button(key=key)
        assert (field.label, field.disabled) == ("공식버전 없음", True), (page_path, key)


def test_an_archive_only_store_raises_the_archive_alert_once_and_says_so_in_the_sidebar(
    tmp_path: Path,
) -> None:
    """보관본만 남은 저장소 — 알림은 `SC-01` 의 보관본 갈래 하나(HOME 코드 사건 알림 없음), 사이드바
    잠긴 줄은 본문 회색 줄과 같은 글이다."""
    database = tmp_path / "archived.duckdb"
    _store_with_scenarios(database, archived=2, active=0)
    app = AppTest.from_string(
        _page_script("app_pages/home.py", database, tmp_path / "equipment.duckdb"),
        default_timeout=300,
    ).run()
    assert not list(app.exception), [element.message for element in app.exception]

    expected = page_bootstrap.missing_official_note("archived_only")
    (note,) = _active_missing(app)
    assert (note["scope"], note["fp"], note["short"]) == (
        expected["scope"],
        expected["fp"],
        expected["short"],
    )
    assert not events(app, "HM-01")
    for key in STOPPED_FIELD_PAGES["app_pages/home.py"]:
        assert app.button(key=key).label == "불러올 시나리오 없음 · 보관본만"


def test_the_scenario_tab_and_a_stopped_screen_raise_the_same_row(
    unpublished_databases: tuple[Path, Path],
) -> None:
    """시나리오 관리 「Capa 시나리오」 탭이 내는 `SC-01` 과 멈춘 계산 화면이 내는 `SC-01` 은 같은
    줄(범위) · 같은 지문 · 같은 글이다 — 두 화면을 오가도 알림창이 다시 뜨지 않는다."""
    database, equipment = unpublished_databases
    tab = AppTest.from_string(
        _page_script("app_pages/scenario_management.py", database, equipment),
        default_timeout=300,
    ).run()
    home = AppTest.from_string(
        _page_script("app_pages/home.py", database, equipment), default_timeout=300
    ).run()
    assert not list(tab.exception) and not list(home.exception)

    (from_tab,) = _active_missing(tab)
    (from_home,) = _active_missing(home)
    keys = ("code", "scope", "fp", "level", "short", "full", "page", "href", "tab")
    assert {key: from_tab[key] for key in keys} == {key: from_home[key] for key in keys}
