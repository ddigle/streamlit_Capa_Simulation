# Purpose: 계산 · 시나리오 · HOME 화면의 등급 넷마다 단추 · 탭 · 값만과 화면을 거친 거절 · 앱 자신의
# 쓰기를 잰다.

"""등급 넷마다 calc 화면(2026-11-18 접속 등급 — 시나리오 관리 · 사이드바 시나리오 팝업 · HOME 설정 ·
VOC · 표준 목표 · 필요 단축 기본값 · 고침 꼬리).

모든 등급 시험은 「운영 + 통합인증 켜짐」 판정을 거친다(`grade_support.as_grade` — 가짜 버킷의
명단 · 등급 파일로 넷 계정의 등급을 단언한다). 화면은 `grade_page_script` 로 돌려 실제 받는 자리
(`run_core_page` · `grade_ui.emit`)를 지난다. 운영 서버에서는 내장 시드를 세우지 않으므로 DB 는
시험 밖(판정기 없음)에서 미리 심은 견본을 베껴 쓴다. 값은 모두 합성(`demo.*` · 내장 시드)이다.

화면을 거친 거절 시험은 「단추를 그린 뒤 등급이 내려간 누름」 이다 — 쿠키는 낮은 등급으로 바꾸고
화면 판정(`sso_identity.screen_grade`)만 그린 회차의 등급으로 붙들어, 누른 회차에도 단추가 선 채
쓰는 순간의 벽(실제 등급)에 닿게 한다(실제 앱에서는 그 회차의 화면 판정이 단추를 걷어 누름이
버려지는 것이 먼저이고, 벽은 그 사이를 지나온 누름의 마지막 그물이다).
설계 규칙: UI-INP-07(예외 — 등급 밖 기능은 숨김) · UI-NTF-03 · UI-NTF-05 · UI-NTF-09 · UI-STA-04 ·
UI-STA-05 · UI-CON-03.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from alert_marks import flashed
from grade_support import (
    GRADE_PARAMS,
    as_grade,
    assert_refusals_caught,
    grade_page_script,
    judge_spy,
    operational_sso_off,
    unrestricted,
    visible_labels,
)
from streamlit.testing.v1 import AppTest

from capa_simulation import page_failures
from capa_simulation.application_bootstrap import ensure_initial_scenario
from capa_simulation.audit.recorder import as_system
from capa_simulation.auth import grades
from capa_simulation.components import page_failure_card, sso_identity
from capa_simulation.components.edit_file_tail import with_unsaved_tail
from capa_simulation.components.scenario_edit_bar import (
    REVISION_SAVE_TAIL,
    with_revision_save_tail,
)
from capa_simulation.components.scenario_management import (
    ARCHIVE_EFFECT_HELP,
    CARD_OFFICIAL_KEY,
    CLONE_MODE,
    DELETE_BUTTON_LABEL,
    MODE_KEY,
    OFFICIAL_DIALOG_KEY,
    SIDE_ARCHIVE,
    SIDE_CHANGES,
    SIDE_KEY,
)
from capa_simulation.components.scenario_management_tabs import (
    AUTO_UPDATE_TAB,
    CAPA_SCENARIO_TAB,
    EQUIPMENT_SCENARIO_TAB,
    QUERY_TAB,
    SCENARIO_MANAGEMENT_TABS_KEY,
)
from capa_simulation.components.scenario_status import SAVE_MODE, SCENARIO_DIALOG_MODE_KEY
from capa_simulation.components.tab_state import remembered_tab_key
from capa_simulation.persistence import repository as repository_module
from capa_simulation.persistence.cache import get_scenario_repository
from capa_simulation.persistence.models import ScenarioCreate
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.voc_board import VOC_CATEGORIES

ROOT = Path(__file__).resolve().parents[1]
COVERED_ACTIONS = frozenset(
    {
        "voc.post",
        "voc.manage",
        "scenario.revision_save",
        "scenario.create",
        "scenario.db_register",
        "scenario.list_edit",
        "scenario.archive",
        "revision.rename",
        "scenario.delete",
        "official.publish",
        "home.settings",
        "shortening.baseline",
        "shortening.filter_default",
        "target.availability",
        "auto_update.view",
        "auto_update.edit",
    }
)
# 이 갈래가 받는 자리를 다는 뿌리 파일(장부 쓰기에 이르는 콜백 · 팝업 · 프래그먼트).
ROOT_FILES = (
    "app_pages/voc.py",
    "app_pages/standard_target_capa.py",
    "app_pages/scenario_management.py",
    "app_pages/home.py",
    "app_pages/required_shortening.py",
    "src/capa_simulation/components/home_main_cases.py",
    "src/capa_simulation/components/home_preference.py",
    "src/capa_simulation/components/home_settings.py",
    "src/capa_simulation/components/past_data_management.py",
    "src/capa_simulation/components/scenario_management.py",
    "src/capa_simulation/components/scenario_status.py",
    "src/capa_simulation/components/scenario_transform.py",
    "src/capa_simulation/components/shortening_progress_panel.py",
    "src/capa_simulation/components/required_shortening_panel.py",
    "src/capa_simulation/components/auto_official_update_tab.py",
    "src/capa_simulation/components/bigdataquery_registration.py",
)
SCENARIO_PAGE = "app_pages/scenario_management.py"


# ------------------------------------------------------------------ 견본 · 화면 원문
@pytest.fixture(scope="module")
def seed_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """내장 시드 공식버전 하나를 심은 시뮬레이션 DB(판정기 없이 — 운영 서버는 시드를 세우지
    않는다)."""
    path = tmp_path_factory.mktemp("grade_calc_seed") / "scenario.duckdb"
    repository = DuckDBScenarioRepository(path)
    repository.initialize()
    assert ensure_initial_scenario(repository).release is not None
    return path


@pytest.fixture
def databases(seed_template: Path, tmp_path: Path) -> tuple[Path, Path]:
    """견본을 베낀 시험 한 벌의 (시뮬레이션 DB, 설비 DB)."""
    database = tmp_path / "scenario.duckdb"
    shutil.copy(seed_template, database)
    wal = seed_template.with_name(seed_template.name + ".wal")
    if wal.exists():
        shutil.copy(wal, database.with_name(database.name + ".wal"))
    return database, tmp_path / "equipment.duckdb"


def _page(page_path: str, database: Path, equipment: Path, *, tail: str = "") -> str:
    """화면 하나 — 첫 공식버전 올리기는 앱 자신의 쓰기(`as_system` — `app.py` 와 같다)."""
    source = (ROOT / page_path).resolve()
    return f"""
from pathlib import Path

import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
import capa_simulation.components.month_range_picker as month_range_picker
import capa_simulation.settings as settings
from capa_simulation.audit.recorder import as_system

original_database_path = settings.DUCKDB_PATH
original_equipment_path = settings.EQUIPMENT_DUCKDB_PATH
original_scrollbar = horizontal_scrollbar.render_horizontal_scrollbar
original_month_picker = month_range_picker.render_month_range_apply
settings.DUCKDB_PATH = Path({str(database)!r})
settings.EQUIPMENT_DUCKDB_PATH = Path({str(equipment)!r})
horizontal_scrollbar.render_horizontal_scrollbar = lambda *args, **kwargs: None
month_range_picker.render_month_range_apply = (
    lambda *, start, end, min_month, max_month, key, this_month=None: None
)
try:
    from capa_simulation.scenario_activation import bootstrap_latest_official_scenario
    from capa_simulation.scenario_preset_state import apply_pending_scenario_preset

    with as_system():
        bootstrap_latest_official_scenario(str(settings.DUCKDB_PATH))
    apply_pending_scenario_preset()
    source = Path({str(source)!r})
    exec(
        compile(source.read_text(encoding="utf-8"), str(source), "exec"),
        {{"__name__": "__main__"}},
    )
{tail}
finally:
    settings.DUCKDB_PATH = original_database_path
    settings.EQUIPMENT_DUCKDB_PATH = original_equipment_path
    horizontal_scrollbar.render_horizontal_scrollbar = original_scrollbar
    month_range_picker.render_month_range_apply = original_month_picker
"""


def _graded(script: str) -> AppTest:
    return AppTest.from_string(grade_page_script(script), default_timeout=180)


def _clean(app: AppTest) -> None:
    """예외 · 오류 카드 · 등급 거절 · 거절 표지가 없다(감싸기는 오류를 카드로 바꾸므로 셋 다
    본다)."""
    assert not list(app.exception), [element.message for element in app.exception]
    assert not page_failures.recent_failures(), page_failures.recent_failures()
    assert not flashed(app, "error"), [item.value for item in flashed(app, "error")]
    assert page_failure_card.REFUSAL_MARK_KEY not in app.session_state


def _buttons(app: AppTest) -> set[str]:
    """단추 라벨(팝업 안 포함 — `visible_labels` 는 본문 · 사이드바 뿌리만 본다)."""
    return {str(button.label) for button in app.button}


def _hold_screen(monkeypatch: pytest.MonkeyPatch, grade: str) -> None:
    """화면 판정만 `grade` 로 붙든다 — 쿠키(실제 등급)는 그대로(모듈 설명)."""
    monkeypatch.setattr(sso_identity, "screen_grade", lambda: grade)


def _clone_official(database: Path, name: str) -> str:
    """내장 시드 공식 리비전을 복제한 시나리오 하나(앱 자신의 쓰기로 — 판정 없이)."""
    repository = DuckDBScenarioRepository(database)
    release = repository.latest_official_release()
    assert release is not None
    official = repository.load_revision(release.revision_id)
    with as_system():
        created = repository.create_scenario(
            ScenarioCreate(
                scenario_name=name,
                source_simulation_code=f"DEMO-{name}",
                source_simulation_name=name,
                source_type="DUCKDB_SCENARIO_CLONE",
                pipeline_version="test-v1",
            ),
            official.tables,
            official.preset,
        )
    return str(created.scenario.scenario_id)


# ------------------------------------------------------------------ 시나리오 관리 · 사이드바 팝업
SIDEBAR_DIALOG_TAIL = """
    from capa_simulation.components.scenario_status import render_scenario_dialog_body

    render_scenario_dialog_body(Path(settings.DUCKDB_PATH), page_file=None)
"""


@GRADE_PARAMS
def test_scenario_management_shows_each_grade_its_buttons_and_tabs(
    databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, grade: str
) -> None:
    database, equipment = databases
    archived_id = _clone_official(database, "DEMO 보관본")
    with as_system():
        DuckDBScenarioRepository(database).archive_scenario(archived_id)
    as_grade(monkeypatch, grade)
    app = _graded(_page(SCENARIO_PAGE, database, equipment, tail=SIDEBAR_DIALOG_TAIL))
    app.run()

    _clean(app)
    at_least = {need: grades.at_least(grade, need) for need in grades.GRADES}
    tabs = [tab.label for tab in app.main.tabs]
    assert tabs[:2] == [CAPA_SCENARIO_TAB, EQUIPMENT_SCENARIO_TAB]
    assert (QUERY_TAB in tabs) is at_least[grades.EDITOR], "DB 등록 탭 — 실무자부터"
    assert (AUTO_UPDATE_TAB in tabs) is at_least[grades.MANAGER], "자동 갱신 탭 — 관리자부터"
    labels = visible_labels(app)
    assert ("공식으로 지정…" in labels) is at_least[grades.MANAGER]
    assert ("보관…" in labels) is at_least[grades.EDITOR]
    assert "선택한 리비전 불러오기" in labels, "불러오기는 모두"
    assert ("시뮬레이션 코드 조회" in labels) is at_least[grades.EDITOR]
    assert ("설정 저장" in labels) is (grade == grades.DEVELOPER), "자동 갱신 설정 — 개발자만"
    assert ("지금 실행" in labels) is (grade == grades.DEVELOPER)
    if grade == grades.MANAGER:
        assert "시뮬레이션명 키워드" in {widget.label for widget in app.text_input}, "값만"
    assert (CLONE_MODE in app.segmented_control(key=MODE_KEY).options) is at_least[grades.EDITOR]
    sides = list(app.segmented_control(key=SIDE_KEY).options)
    assert (SIDE_CHANGES in sides) is at_least[grades.EDITOR], "저장 전 변경 — 실무자부터"
    dialog_modes = [
        control for control in app.segmented_control if control.key == SCENARIO_DIALOG_MODE_KEY
    ]
    if at_least[grades.EDITOR]:
        assert SAVE_MODE in dialog_modes[0].options
    else:
        assert not dialog_modes, "열람은 「불러오기」 만 — 구획 고르기도 없다"

    app.session_state[SIDE_KEY] = SIDE_ARCHIVE
    app.run()
    _clean(app)
    labels = visible_labels(app)
    assert "보관본" in {box.label for box in app.selectbox}, "보관본 목록은 모두"
    assert ("되돌리기" in labels) is at_least[grades.EDITOR]
    assert any(DELETE_BUTTON_LABEL in label for label in labels) is at_least[grades.MANAGER]


def test_the_sidebar_dialog_save_section_stands_for_an_editor(
    databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    database, equipment = databases
    as_grade(monkeypatch, grades.EDITOR)
    app = _graded(_page(SCENARIO_PAGE, database, equipment, tail=SIDEBAR_DIALOG_TAIL))
    app.session_state[SCENARIO_DIALOG_MODE_KEY] = SAVE_MODE
    app.run()

    _clean(app)
    assert "신규 리비전 저장" in visible_labels(app)


def test_a_viewer_left_on_the_save_section_is_moved_to_load(
    databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    database, equipment = databases
    as_grade(monkeypatch, grades.VIEWER)
    app = _graded(_page(SCENARIO_PAGE, database, equipment, tail=SIDEBAR_DIALOG_TAIL))
    app.session_state[SCENARIO_DIALOG_MODE_KEY] = SAVE_MODE
    app.run()

    _clean(app)
    assert "신규 리비전 저장" not in visible_labels(app)


def test_the_archive_tooltip_says_the_home_picks_are_cleared() -> None:
    """보관하면 HOME 「비교 · 주요 Case」 지정이 함께 비워지고 되돌려도 돌아오지 않는다
    (UI-NTF-09)."""
    assert "비교 · 주요 Case" in ARCHIVE_EFFECT_HELP
    assert "돌아오지 않습니다" in ARCHIVE_EFFECT_HELP


@pytest.mark.parametrize(
    ("hidden", "grade", "message"),
    [
        (QUERY_TAB, grades.VIEWER, "실무자부터 여는 탭입니다"),
        (AUTO_UPDATE_TAB, grades.EDITOR, "관리자부터 여는 탭입니다"),
    ],
)
def test_a_remembered_hidden_tab_stops_once_then_opens_the_first_tab(
    databases: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    hidden: str,
    grade: str,
    message: str,
) -> None:
    """「그 화면으로」 · 기억된 탭(`open_scenario_management_tab` — 기억 칸만 적는다)이 숨은 탭을
    가리킨 회차는 한 번 멈추고 두 칸을 첫 탭으로 새로 적는다 — 다음 회차는 첫 탭이다."""
    database, equipment = databases
    as_grade(monkeypatch, grade)
    app = _graded(_page(SCENARIO_PAGE, database, equipment))
    app.session_state[remembered_tab_key(SCENARIO_MANAGEMENT_TABS_KEY)] = hidden
    app.run()

    assert not list(app.exception)
    assert [item.value for item in app.warning] == [message]
    assert not list(app.main.tabs)
    assert app.session_state[remembered_tab_key(SCENARIO_MANAGEMENT_TABS_KEY)] == (
        CAPA_SCENARIO_TAB
    )

    app.run()
    _clean(app)
    assert not list(app.warning)
    assert app.main.tabs[0].label == CAPA_SCENARIO_TAB
    assert hidden not in [tab.label for tab in app.main.tabs]


def test_a_viewers_list_is_read_only_and_drops_rename_ops(
    databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from scenario_list_fake import ListBrowser, install_fake_list_grid, last

    from capa_simulation.components import scenario_list_grid as grid
    from capa_simulation.components.scenario_list_state import DRAFT_KEY
    from capa_simulation.services.scenario_list_edits import has_edits

    database, equipment = databases
    as_grade(monkeypatch, grades.VIEWER)
    calls = install_fake_list_grid(monkeypatch)
    app = _graded(_page(SCENARIO_PAGE, database, equipment))
    app.run()
    _clean(app)
    assert last(calls, grid.TABLE_KEY).get("readonly") is True
    assert last(calls, grid.REVISIONS_KEY).get("readonly") is True, "리비전 이름도 값만"
    row_id = last(calls, grid.TABLE_KEY)["rows"][0]["id"]

    ListBrowser(app, calls).rename_scenario(row_id, "DEMO 바꾼 이름")

    _clean(app)
    assert not has_edits(app.session_state[DRAFT_KEY])
    with as_system():
        names = [item.scenario_name for item in DuckDBScenarioRepository(database).list_scenarios()]
    assert "DEMO 바꾼 이름" not in names


def test_an_editors_list_takes_rename_ops(
    databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from scenario_list_fake import ListBrowser, install_fake_list_grid, last

    from capa_simulation.components import scenario_list_grid as grid
    from capa_simulation.components.scenario_list_state import DRAFT_KEY
    from capa_simulation.services.scenario_list_edits import has_edits

    database, equipment = databases
    as_grade(monkeypatch, grades.EDITOR)
    calls = install_fake_list_grid(monkeypatch)
    app = _graded(_page(SCENARIO_PAGE, database, equipment))
    app.run()
    assert "readonly" not in last(calls, grid.TABLE_KEY)
    row_id = last(calls, grid.TABLE_KEY)["rows"][0]["id"]

    ListBrowser(app, calls).rename_scenario(row_id, "DEMO 바꾼 이름")

    _clean(app)
    assert has_edits(app.session_state[DRAFT_KEY])


# ------------------------------------------------------------------ 화면을 거친 거절
@pytest.mark.page_failure_card
def test_the_official_popup_refuses_a_press_after_the_grade_drops(
    databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    database, equipment = databases
    as_grade(monkeypatch, grades.MANAGER)
    app = _graded(_page(SCENARIO_PAGE, database, equipment))
    app.run()
    _clean(app)
    repository = DuckDBScenarioRepository(database)
    releases_before = len(repository.list_official_releases())
    scenario_id = repository.list_scenarios()[0].scenario_id
    app.button(key=f"{CARD_OFFICIAL_KEY}_{scenario_id}").click().run()
    assert app.session_state[OFFICIAL_DIALOG_KEY][0] == scenario_id

    as_grade(monkeypatch, grades.EDITOR)
    _hold_screen(monkeypatch, grades.MANAGER)
    with judge_spy() as seen:
        next(
            button for button in app.button if button.label == "선택 리비전을 공식버전으로 지정"
        ).click()
        app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert not page_failures.recent_failures()
    assert [item.value for item in flashed(app, "error")] == [
        grades.refusal_text("official.publish")
    ]
    assert ("official.publish", grades.EDITOR) in seen
    assert len(repository.list_official_releases()) == releases_before


SIDEBAR_SAVE_POPUP = """
    from capa_simulation.components.scenario_status import show_scenario_dialog

    show_scenario_dialog(None)
"""


@pytest.mark.page_failure_card
def test_the_sidebar_save_popup_refuses_a_press_after_the_grade_drops(
    databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    database, equipment = databases
    as_grade(monkeypatch, grades.EDITOR)
    app = _graded(_page(SCENARIO_PAGE, database, equipment, tail=SIDEBAR_SAVE_POPUP))
    app.session_state[SCENARIO_DIALOG_MODE_KEY] = SAVE_MODE
    app.run()
    _clean(app)
    repository = DuckDBScenarioRepository(database)
    scenario_id = repository.list_scenarios()[0].scenario_id
    revisions_before = len(repository.list_revisions(scenario_id))
    next(widget for widget in app.text_input if widget.label == "새 리비전명").set_value(
        "DEMO 거절될 리비전"
    )

    as_grade(monkeypatch, grades.VIEWER)
    _hold_screen(monkeypatch, grades.EDITOR)
    with judge_spy() as seen:
        next(button for button in app.button if button.label == "신규 리비전 저장").click()
        app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert not page_failures.recent_failures()
    assert [item.value for item in flashed(app, "error")] == [
        grades.refusal_text("scenario.revision_save")
    ]
    assert ("scenario.revision_save", grades.VIEWER) in seen
    assert len(repository.list_revisions(scenario_id)) == revisions_before


HOME_SETTINGS_SCRIPT = """
from pathlib import Path

import pandas as pd

import capa_simulation.settings as settings

from capa_simulation.components import home_settings
from capa_simulation.components.home_preference import render_home_preference
from capa_simulation.components.past_data_management import render_past_data_management
from capa_simulation.components.process_labels import get_process_labels
from capa_simulation.persistence.cache import (
    load_global_advance_load,
    load_global_advance_shipment,
    load_global_execution_capacity,
    load_global_past_data,
    load_global_securement_threshold,
    load_global_summary_note,
    load_global_top5_band,
)
from capa_simulation.services.month_columns import month_label

database = {database!r}
months = [202601, 202602, 202603]


def preference(tabs):
    render_home_preference(
        tabs=tabs,
        months=months,
        month_labels=[month_label(month) for month in months],
        threshold_profile=load_global_securement_threshold(database),
        advance_profile=load_global_advance_load(database),
        advance_shipment_profile=load_global_advance_shipment(database),
        execution_profile=load_global_execution_capacity(database),
        top5_band_profile=load_global_top5_band(database),
        summary_profile=load_global_summary_note(database),
        process_options=["DEMO-P1", "DEMO-P2"],
        process_labels=get_process_labels(),
        unmatched_execution=pd.DataFrame(),
        clamped_execution=pd.DataFrame(),
        database_path=database,
    )


def past():
    render_past_data_management(database, load_global_past_data(database))


original_database_path = settings.DUCKDB_PATH
settings.DUCKDB_PATH = Path(database)
try:
    home_settings._settings_dialog(preference, past)
finally:
    settings.DUCKDB_PATH = original_database_path
"""
# 「HOME 설정」 창의 저장 단추 — 아래 등급(관리자 미만)에게는 하나도 서지 않는다.
HOME_SAVE_LABELS = frozenset(
    {
        "판정 기준 저장",
        "선행 B/O 저장",
        "선행 입고 저장",
        "확보율 보정 저장",
        "Capa 요약 저장",
        "확보율 구간 저장",
        "프리셋 저장",
        "과거 구간 저장",
    }
)


def _seed_key_process(database: Path) -> None:
    with as_system():
        DuckDBScenarioRepository(database).replace_global_key_process_presets(
            [("DEMO 핵심", ["DEMO-P1", "DEMO-P2"])], source="DEMO"
        )


def _home_settings(database: Path) -> AppTest:
    return _graded(HOME_SETTINGS_SCRIPT.format(database=str(database)))


@GRADE_PARAMS
def test_home_settings_are_values_only_below_the_manager(
    databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, grade: str
) -> None:
    database, _ = databases
    _seed_key_process(database)
    as_grade(monkeypatch, grade)
    with judge_spy() as seen:
        app = _home_settings(database).run()

    _clean(app)
    editable = grades.at_least(grade, grades.MANAGER)
    assert not [entry for entry in seen if entry[1] == grade and not editable], seen
    labels = _buttons(app)
    assert (HOME_SAVE_LABELS <= labels) is editable, HOME_SAVE_LABELS - labels
    assert not (HOME_SAVE_LABELS & labels) or editable, HOME_SAVE_LABELS & labels
    assert ("기본으로" in labels) is editable, "주요공정 프리셋 기본으로 · 삭제"
    assert all(area.disabled is not editable for area in app.text_area), "Capa 요약 칸"
    assert any("DEMO 핵심" in str(item.value) for item in app.markdown) or editable
    assert ("변경 메모" in {widget.label for widget in app.text_input}) is editable
    assert all(widget.disabled is not editable for widget in app.number_input), "값만은 잠긴 칸"
    pickers = {"비교 시나리오", "시나리오"}
    assert bool(pickers & {box.label for box in app.selectbox}) is editable, "고르기 없음"


def test_home_settings_redrawn_from_manager_to_viewer_in_one_session_stay_whole(
    databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """같은 창이 관리자 화면에서 열람 화면으로 다시 그려진다(「이 등급으로 보기」 꼴) — 같은 key 의
    편집표 · 칸이 잠기고(줄 더하기 없음) 저장 단추가 걷혀도 오류 없이 선다. 다시 관리자로 돌아와도
    그렇다."""
    database, _ = databases
    _seed_key_process(database)
    as_grade(monkeypatch, grades.MANAGER)
    app = _home_settings(database).run()
    _clean(app)
    assert HOME_SAVE_LABELS <= _buttons(app)

    _hold_screen(monkeypatch, grades.VIEWER)
    app.run()
    _clean(app)
    assert not (HOME_SAVE_LABELS & _buttons(app))
    assert all(widget.disabled for widget in app.number_input)

    monkeypatch.setattr(sso_identity, "screen_grade", lambda: grades.MANAGER)
    app.run()
    _clean(app)
    assert HOME_SAVE_LABELS <= _buttons(app)


@pytest.mark.page_failure_card
def test_the_home_settings_window_refuses_a_save_after_the_grade_drops(
    databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    database, _ = databases
    as_grade(monkeypatch, grades.MANAGER)
    app = _home_settings(database).run()
    _clean(app)
    repository = DuckDBScenarioRepository(database)
    version_before = repository.load_global_securement_threshold().version

    as_grade(monkeypatch, grades.EDITOR)
    _hold_screen(monkeypatch, grades.MANAGER)
    with judge_spy() as seen:
        next(button for button in app.button if button.label == "판정 기준 저장").click()
        app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert not page_failures.recent_failures()
    assert [item.value for item in flashed(app, "error")] == [grades.refusal_text("home.settings")]
    assert ("home.settings", grades.EDITOR) in seen
    assert repository.load_global_securement_threshold().version == version_before


# ------------------------------------------------------------------ VOC · 표준 목표
@GRADE_PARAMS
def test_voc_manage_buttons_are_the_developers_and_posting_is_everyones(
    databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, grade: str
) -> None:
    database, equipment = databases
    with as_system():
        DuckDBScenarioRepository(database).create_voc_post(
            category=VOC_CATEGORIES[0], title="DEMO 글", body="DEMO 내용", author="DEMO 작성자"
        )
    as_grade(monkeypatch, grade)
    app = _graded(_page("app_pages/voc.py", database, equipment)).run()

    _clean(app)
    labels = visible_labels(app)
    assert {"글 올리기", "답변 남기기"} <= labels
    manages = grade == grades.DEVELOPER
    assert ("답변 완료로 표시" in labels) is manages
    assert any("삭제 확인" in widget.label for widget in app.checkbox) is manages


@GRADE_PARAMS
def test_standard_target_paste_and_clear_are_the_managers(
    databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, grade: str
) -> None:
    database, equipment = databases
    as_grade(monkeypatch, grade)
    app = _graded(_page("app_pages/standard_target_capa.py", database, equipment)).run()

    _clean(app)
    labels = visible_labels(app)
    allowed = grades.at_least(grade, grades.MANAGER)
    assert ("가용설비 붙여넣기" in labels) is allowed
    assert ("입력 초기화" in labels) is allowed


BASELINE_SCRIPT = """
from datetime import date

from capa_simulation.components.shortening_progress_panel import (
    BaselineSaveContext,
    render_baseline_controls,
)

render_baseline_controls(
    BaselineSaveContext(
        database_path={database!r}, plan=None, today=date(2026, 11, 18), provenance=None
    ),
    None,
)
"""


@GRADE_PARAMS
def test_the_baseline_save_popover_is_from_the_editor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, grade: str
) -> None:
    as_grade(monkeypatch, grade)
    app = _graded(BASELINE_SCRIPT.format(database=str(tmp_path / "equipment.duckdb"))).run()

    _clean(app)
    assert ("기준선 저장" in visible_labels(app)) is grades.at_least(grade, grades.EDITOR)


# ---------------------------------------------------------- 열람의 모든 화면 · 앱 자신의 쓰기
@pytest.mark.parametrize(
    "page",
    [
        "app_pages/home.py",
        "app_pages/calculation_result.py",
        SCENARIO_PAGE,
        "app_pages/required_shortening.py",
        "app_pages/standard_target_capa.py",
        "app_pages/voc.py",
    ],
)
def test_a_viewer_draws_every_calc_page_without_a_refusal(
    databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, page: str
) -> None:
    """배포 날 모두가 열람이다 — 첫 회차의 자동 쓰기(비교 · 주요 Case 메우기 · 사라진 지정 비우기 ·
    표시순서 첫 판)가 벽에 걸려 서는 화면이 없다."""
    database, equipment = databases
    as_grade(monkeypatch, grades.VIEWER)
    with judge_spy() as seen:
        app = _graded(_page(page, database, equipment)).run()

    _clean(app)
    assert sum(1 for _ in app.main) > 5, "화면이 실제로 섰다"
    assert not [entry for entry in seen if entry[1] == grades.VIEWER], seen


@pytest.mark.parametrize(
    ("page", "expected"),
    [
        ("app_pages/reference_data.py", {"변경사항 적용"}),
        ("app_pages/load_conversion.py", {"변경사항 적용", "Excel 붙여넣기", "가상 제품 등록"}),
    ],
)
def test_a_viewer_still_edits_and_calculates_on_their_own_screen(
    databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, page: str, expected: set[str]
) -> None:
    """「그대로」 — 기준 정보 · 생산 계획을 고쳐 내 화면에서 계산해 보는 단추는 열람에게도 선다(저장
    안 함 — 「신규 리비전 저장」 을 누르기 전에는 남에게 가지 않는다)."""
    database, equipment = databases
    as_grade(monkeypatch, grades.VIEWER)
    with judge_spy() as seen:
        app = _graded(_page(page, database, equipment)).run()

    _clean(app)
    assert expected <= _buttons(app), expected - _buttons(app)
    assert not [entry for entry in seen if entry[1] == grades.VIEWER], seen


BDQ_SAVE_SCRIPT = """
import streamlit as st

from capa_simulation.components import bigdataquery_registration as registration

for key, value in (
    (registration.FORM_CODE_KEY, "SIM-DEMO"),
    (registration.FORM_SOURCE_NAME_KEY, "DEMO 원천"),
    (registration.FORM_SCENARIO_NAME_KEY, "DEMO 등록"),
    (registration.FORM_REGISTERED_AT_KEY, "2026-11-01 09:00:00"),
):
    st.session_state[registration.form_field_key(key)] = value
# 저장 제출은 첫 회차 한 번이다 — 거절 알림을 내는 다음 회차에는 다시 누르지 않는다.
if not st.session_state.get("__submitted__"):
    st.session_state["__submitted__"] = True
    registration._save_scenario(None, "demo.duckdb", existing_names=frozenset())
"""


def test_a_viewers_db_register_save_never_reaches_the_shared_account_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DB 등록 「저장」 은 공용 BigDataQuery 계정으로 사내 DB 를 여는 상세 조회를 저장소 벽보다
    먼저 돌린다 — 목록 조회처럼 누른 순간 실제 등급으로 본다. 열람의 저장 제출은 조회 함수에 닿지
    않고 거절 알림 한 번이다(화면 본문의 받는 자리)."""
    from capa_simulation.components import bigdataquery_registration as registration

    fetched: list[object] = []

    def _fetch(*args: object, **kwargs: object) -> None:
        fetched.append(args)
        raise RuntimeError("시험 — 사내 DB 상세 조회에 닿았다")

    monkeypatch.setattr(registration, "fetch_core_data_dataset", _fetch)
    monkeypatch.setattr(
        registration, "load_global_display_order", lambda _path: SimpleNamespace(rules=())
    )
    as_grade(monkeypatch, grades.VIEWER)
    with judge_spy() as seen:
        app = _graded(BDQ_SAVE_SCRIPT).run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert fetched == []
    assert seen == [("scenario.db_register", grades.VIEWER)]
    assert [item.value for item in flashed(app, "error")] == [
        grades.refusal_text("scenario.db_register")
    ]


YIELD_GRID_HOST = "yield_grid"
YIELD_TAB_LABEL = ":material/percent: 수율"


@pytest.mark.parametrize("grade", [grades.VIEWER, grades.EDITOR])
def test_the_apply_notice_points_to_the_revision_save_only_where_that_button_stands(
    databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, grade: str
) -> None:
    """열람은 「변경사항 적용」 을 하지만 사이드바 시나리오 팝업에 「신규 리비전 저장」 단추가
    없다 — 적용 알림이 없는 단추를 가리키지 않는다(실무자부터만 그 안내 꼬리, 설계 규칙 UI-INP-07
    예외).
    생산 계획 수율 탭에서 칸 하나를 고쳐 적용한다(기준 정보 · PKG PLAN 도 같은 꼬리 함수)."""
    from alert_marks import successes
    from edit_grid_fake import install_fake_edit_grid, last, send_ops, shell_frame, shell_key

    calls = install_fake_edit_grid(monkeypatch)
    database, equipment = databases
    as_grade(monkeypatch, grade)
    app = _graded(_page("app_pages/load_conversion.py", database, equipment))
    app.session_state["load_conversion_active_tab"] = YIELD_TAB_LABEL
    app.run()
    _clean(app)
    shell = last(calls, YIELD_GRID_HOST)
    month = next(str(column) for column in shell_frame(shell).columns if str(column).isdigit())
    op = {"op": "write", "rows": [shell_key(shell, 0)], "cols": [month], "values": [["0.5"]]}
    send_ops(app, calls, op, host=YIELD_GRID_HOST)
    with judge_spy() as seen:
        app.button(key="apply_yield_changes").click().run()

    _clean(app)
    assert not seen, "적용은 저장이 아니다 — 벽에 닿지 않는다"
    applied = [
        str(item.value)
        for item in successes(app)
        if "활성 시나리오에 적용했습니다" in str(item.value)
    ]
    assert len(applied) == 1, applied
    assert (REVISION_SAVE_TAIL in applied[0]) is (grade == grades.EDITOR), applied[0]


@GRADE_PARAMS
def test_the_revision_save_tail_follows_the_save_button(
    monkeypatch: pytest.MonkeyPatch, grade: str
) -> None:
    """꼬리 함수는 「신규 리비전 저장」 단추와 같은 판정(`scenario.revision_save` — 실무자부터)을
    본다. 운영 서버가 아닌 곳은 지금 글 그대로다."""
    as_grade(monkeypatch, grade)
    tailed = with_revision_save_tail("DEMO 적용했습니다. ")
    expected = grades.at_least(grade, grades.EDITOR)
    assert tailed == (
        f"DEMO 적용했습니다. {REVISION_SAVE_TAIL}" if expected else "DEMO 적용했습니다."
    )

    unrestricted(monkeypatch)
    assert with_revision_save_tail("DEMO 적용했습니다.").endswith(REVISION_SAVE_TAIL)


def test_the_display_order_first_cut_is_the_apps_own_write_on_a_viewers_first_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """새 프로세스의 첫 회차가 열람이어도 표시순서 첫 판 · 보강(Admin 몫 표지)이 선다 — 저장소
    캐시를 비우고 새 DB 로 연다. 보강 갈래를 늘 타게 견주기를 바꿔 끼워 벽이 실제로 불렸는지(앱
    자신의 쓰기 — 판정 없음)를 본다."""
    as_grade(monkeypatch, grades.VIEWER)
    monkeypatch.setattr(repository_module, "display_order_frames_equal", lambda *_: False)
    get_scenario_repository.clear()
    with judge_spy() as seen:
        repository = get_scenario_repository(str(tmp_path / "fresh.duckdb"))

    assert ("admin.area", "unrestricted") in seen
    profile = repository.load_global_display_order()
    with pytest.raises(grades.GradeDenied):
        repository.replace_global_display_order(profile.rules, source="DEMO 열람의 손 저장")
    get_scenario_repository.clear()


MAIN_CASES_SCRIPT = """
from capa_simulation.components.home_main_cases import render_main_case_picker

render_main_case_picker({database!r})
"""


def test_a_vanished_main_case_is_cleared_on_a_viewers_run_as_the_app(
    databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    database, _ = databases
    gone_id = _clone_official(database, "DEMO 사라질 시나리오")
    repository = DuckDBScenarioRepository(database)
    with as_system():
        repository.replace_global_main_case(1, gone_id, None, source="DEMO")
    _drop_scenario_quietly(repository, gone_id)
    as_grade(monkeypatch, grades.VIEWER)
    with judge_spy() as seen:
        app = _graded(MAIN_CASES_SCRIPT.format(database=str(database))).run()

    _clean(app)
    assert ("home.settings", "unrestricted") in seen, "사라진 지정 비우기는 앱 자신의 쓰기"
    assert repository.load_global_main_cases().case(1) == (None, None)


def _drop_scenario_quietly(repository: DuckDBScenarioRepository, scenario_id: str) -> None:
    """「그 밖의 길로 남은 값」 — 저장소의 보관 · 삭제(같은 트랜잭션에서 지정을 비운다)를 거치지
    않고 목록에서만 빠진 시나리오를 흉내 낸다."""
    with repository._write_transaction() as connection:
        connection.execute(
            "UPDATE app_meta.scenario SET status = 'ARCHIVED' WHERE scenario_id = ?", [scenario_id]
        )


@pytest.mark.parametrize(("grade", "writes"), [(grades.EDITOR, False), (grades.MANAGER, True)])
def test_the_main_case_revision_fill_is_written_only_by_a_manager(
    databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, grade: str, writes: bool
) -> None:
    database, _ = databases
    repository = DuckDBScenarioRepository(database)
    scenario_id = repository.list_scenarios()[0].scenario_id
    with as_system():
        repository.replace_global_main_case(1, scenario_id, None, source="DEMO 빈 리비전 칸")
    version_before = repository.load_global_main_cases().version
    as_grade(monkeypatch, grade)
    with judge_spy() as seen:
        app = _graded(MAIN_CASES_SCRIPT.format(database=str(database))).run()

    _clean(app)
    filled = repository.load_global_main_cases()
    assert (filled.version > version_before) is writes
    assert (filled.case(1)[1] is not None) is writes
    assert bool([entry for entry in seen if entry[0] == "home.settings"]) is writes, seen


FILTER_SCRIPT = """
import streamlit as st

from capa_simulation.components import required_shortening_panel as panel
from capa_simulation.persistence.equipment_cache import get_equipment_repository

database = {equipment!r}
get_equipment_repository(database)
st.session_state[panel.SHORTENING_START_KEY] = 202602
st.session_state[panel.SHORTENING_END_KEY] = 202603
panel._save_month_range(database, (202601, 202602, 202603))
st.write(repr(get_equipment_repository(database).load_shortening_filter_profile().start_month))
"""


@pytest.mark.parametrize(("grade", "writes"), [(grades.EDITOR, False), (grades.MANAGER, True)])
def test_the_shortening_default_is_kept_only_by_a_manager(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, grade: str, writes: bool
) -> None:
    """아래 등급의 시작 · 끝 월은 세션에만 남는다 — 공용 기본값을 쓰지도 벽에 닿지도 않는다."""
    as_grade(monkeypatch, grade)
    with judge_spy() as seen:
        app = _graded(FILTER_SCRIPT.format(equipment=str(tmp_path / "equipment.duckdb"))).run()

    _clean(app)
    written = [str(item.value) for item in app.markdown]
    assert (written[-1] == "202602") is writes, written
    if not writes:
        assert not seen, "아래 등급의 고름은 벽에 닿기 전에 걸러진다"


# ------------------------------------------------------------------ 운영 아님 · 운영 + 꺼짐
def test_off_the_operational_server_the_calc_screens_are_as_before(
    databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    database, equipment = databases
    unrestricted(monkeypatch)
    app = _graded(_page(SCENARIO_PAGE, database, equipment, tail=SIDEBAR_DIALOG_TAIL)).run()

    _clean(app)
    labels = visible_labels(app)
    assert {"공식으로 지정…", "보관…", "설정 저장", "지금 실행", "시뮬레이션 코드 조회"} <= labels
    assert len(app.main.tabs) == 4


def test_with_sign_in_off_the_operational_server_stops_only_the_developers_part(
    databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    database, equipment = databases
    with as_system():
        DuckDBScenarioRepository(database).create_voc_post(
            category=VOC_CATEGORIES[0], title="DEMO 글", body="DEMO 내용", author="DEMO 작성자"
        )
    operational_sso_off(monkeypatch)
    app = _graded(_page(SCENARIO_PAGE, database, equipment)).run()

    _clean(app)
    labels = visible_labels(app)
    assert {"공식으로 지정…", "보관…", "시뮬레이션 코드 조회"} <= labels
    assert AUTO_UPDATE_TAB in [tab.label for tab in app.main.tabs]
    assert "설정 저장" not in labels and "지금 실행" not in labels

    voc = _graded(_page("app_pages/voc.py", database, equipment)).run()
    _clean(voc)
    assert "답변 완료로 표시" not in visible_labels(voc)
    assert "글 올리기" in visible_labels(voc)


# ------------------------------------------------------------------ 고침 꼬리
TAIL_SCRIPT = """
import streamlit as st

from capa_simulation.components.edit_file_tail import edited_file_name
from capa_simulation.scenario_state import ACTIVE_SCENARIO_KEY
from capa_simulation.scenario_activation import ACTIVE_PERSISTED_SESSION_REVISION_KEY

st.session_state[ACTIVE_PERSISTED_SESSION_REVISION_KEY] = 3
st.session_state[ACTIVE_SCENARIO_KEY] = {{"revision": {revision}}}
st.write(edited_file_name("Capa_Securement_Rate_202601_202603.csv"))
"""


@pytest.mark.parametrize(
    ("revision", "expected"),
    [
        (4, "Capa_Securement_Rate_202601_202603_unsaved.csv"),
        (3, "Capa_Securement_Rate_202601_202603.csv"),
    ],
)
def test_an_unsaved_edit_tails_the_download_name(revision: int, expected: str) -> None:
    app = AppTest.from_string(TAIL_SCRIPT.format(revision=revision), default_timeout=60).run()
    assert not list(app.exception)
    assert [str(item.value) for item in app.markdown] == [expected]


def test_the_tail_keeps_the_extension_and_is_not_doubled() -> None:
    assert with_unsaved_tail("a.xlsx") == "a_unsaved.xlsx"
    assert with_unsaved_tail("a_unsaved.xlsx") == "a_unsaved.xlsx"
    assert with_unsaved_tail("noext") == "noext_unsaved"
    assert with_unsaved_tail("a.b.csv") == "a.b_unsaved.csv"


# ------------------------------------------------------------------ 그물
def test_this_lane_roots_catch_refusals() -> None:
    """장부 쓰기에 이르는 calc 파일의 콜백 · 팝업 · 프래그먼트가 받는 자리를 달았다."""
    assert_refusals_caught(ROOT_FILES)


def test_the_covered_actions_are_known() -> None:
    assert COVERED_ACTIONS <= set(grades.ACTIONS)


def test_the_auto_update_writes_and_admin_profiles_carry_their_walls() -> None:
    """표지를 다는 쓰기 넷 — Admin 몫 공용 프로필 둘은 `admin.area`, 자동 갱신 둘은
    `auto_update.edit`(감사는 손으로)."""
    from grade_support import action_of

    owner = DuckDBScenarioRepository
    assert action_of(owner.replace_global_display_order) == "admin.area"
    assert action_of(owner.replace_global_process_rename) == "admin.area"
    assert action_of(owner.replace_auto_official_update_settings) == "auto_update.edit"
    assert action_of(owner.claim_auto_official_update_run) == "auto_update.edit"
