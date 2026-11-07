# Purpose: 시나리오 관리 화면의 목록 표 · 오른쪽 칸 · 공식 지정 · 보관함 · 복제를 AppTest 로 잰다.

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, NoReturn
from uuid import uuid4

import duckdb
import pandas as pd
import pytest
from alert_marks import flashed, infos, place_errors, successes
from scenario_list_fake import (
    Calls,
    ListBrowser,
    drawn,
    install_fake_list_grid,
    last,
    table_ids,
    table_names,
    table_row,
)
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Button
from streamlit.testing.v1.errors import AppTestError
from test_all_pages_render import _page_script

import capa_simulation.components.write_guard as write_guard
from capa_simulation.components.bigdataquery_registration import CATALOG_START_DATE_KEY
from capa_simulation.components.date_panel import panel_key
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.scenario_list_grid import (
    CHANGES_KEY,
    LIST_SIDE,
    REVISIONS_KEY,
    TABLE_KEY,
)
from capa_simulation.components.scenario_list_state import DRAFT_KEY, SIDE_NEXT_KEY
from capa_simulation.components.scenario_management import (
    ACTION_KEY,
    ARCHIVE_EFFECT_HELP,
    ARCHIVE_LOCK_HELP,
    ARCHIVED_SELECT_KEY,
    CARD_LOAD_KEY,
    CARD_NOTICE_KEY,
    CARD_OFFICIAL_KEY,
    CLONE_MODE,
    CLONE_SOURCE_NOTE,
    DELETE_BUTTON_KEY,
    DELETE_BUTTON_LABEL,
    DELETE_CONFIRM_KEY,
    DELETE_LOCK_HELP,
    DISCARD_CONFIRM_KEY,
    DISCARD_LOCK_HELP,
    DISCARD_POPOVER_KEY,
    DISCARD_UNSAVED_KEY,
    FLASH_KEY,
    FLASH_WARNING_KEY,
    LIST_NOTICE_KEY,
    MODE_KEY,
    OFFICIAL_CONFIRM_HELP,
    OFFICIAL_DIALOG_KEY,
    OPENED_MOVED_MESSAGE,
    SAME_AS_OFFICIAL_HELP,
    SAME_AS_OFFICIAL_LINE,
    SIDE_ARCHIVE,
    SIDE_CHANGES,
    SIDE_DETAIL,
    SIDE_HISTORY,
    SIDE_KEY,
    SIDES,
    archive_confirm_key,
    official_confirm_key,
    official_virtual_product_warning,
)
from capa_simulation.components.tab_state import remembered_tab_key
from capa_simulation.persistence.cache import (
    clear_global_comparison_scenario_cache,
    clear_global_main_cases_cache,
    load_global_comparison_scenario,
    load_global_main_cases,
    load_scenario_snapshot,
)
from capa_simulation.persistence.models import ScenarioCreate, ScenarioSnapshot
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_state import ACTIVE_SCENARIO_KEY, VIRTUAL_PRODUCTS_KEY
from capa_simulation.services.builtin_seed import BUILTIN_SEED_SCENARIO_NAME
from capa_simulation.services.scenario_list_edits import ListDraft, NameEdit, draft_base
from capa_simulation.services.virtual_product import (
    VirtualProductRecord,
    VirtualProductRequest,
    available_source_products,
    clone_product,
    clone_table_names,
)

PAGE_PATH = "app_pages/scenario_management.py"


@pytest.fixture(scope="module")
def seeded_databases(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    root = tmp_path_factory.mktemp("scenario_management")
    return root / "scenario.duckdb", root / "equipment.duckdb"


def test_every_tab_form_is_rendered_in_one_run(
    seeded_databases: tuple[Path, Path], date_panels: dict[str, dict[str, Any]]
) -> None:
    """열린 탭만 그리면 다른 탭을 잠깐 여는 순간 그 탭의 form 입력값이 사라진다.

    설비 시나리오 탭을 뺀 세 탭의 폼이 한 rerun 에 모두 있어야 탭을 오가도 입력 중이던 값이 남는다.
    """
    database_path, equipment_path = seeded_databases
    app = AppTest.from_string(
        _page_script(PAGE_PATH, database_path, equipment_path), default_timeout=120
    ).run()

    assert not app.exception
    labels = {widget.label for widget in app.text_input}
    # DB 등록 폼. Capa 시나리오 탭의 폼(복제 저장과 공식 지정 팝업)은 탭 안의 작업 선택(segmented
    # control)과 고른 시나리오에 따라 그려지므로 여기 없다. 표시순서 관리는 Admin Area 로 옮겼다.
    assert {"조회할 시뮬레이션 코드"} <= labels
    assert [tab.label for tab in app.main.tabs] == [
        ":material/database: Capa 시나리오",
        ":material/account_tree: 설비 시나리오",
        ":material/cloud_download: DB 등록",
        ":material/autorenew: 자동 갱신",
    ]
    # 자동 갱신 설정 폼도 같은 rerun 에 선다.
    assert "시뮬레이션명 키워드" in labels
    assert "설정 저장" in {button.label for button in app.button}
    # 1단계 조회 폼과 2단계 등록 폼이 한 rerun 에 함께 있어야 탭을 오갈 때 값이 남는다.
    assert date_panels[panel_key(CATALOG_START_DATE_KEY)]["label"] == "조회일"
    assert "시뮬레이션 코드 조회" in {button.label for button in app.button}


def test_list_management_opens_a_scenario_in_the_side_panel(
    seeded_databases: tuple[Path, Path],
) -> None:
    """왼쪽 표 + 오른쪽 칸 넷이다. 첫 진입에 올라와 있는 시나리오가 열려 오른쪽 칸이 빈 채 서지
    않는다. 고친 수는 「저장 전 변경」 칸의 수 넷이 말한다 — 표 위에 값 줄을 세우지
    않는다(UI-TXT-07)."""
    database_path, equipment_path = seeded_databases
    script = _page_script(PAGE_PATH, database_path, equipment_path)

    app = AppTest.from_string(script, default_timeout=120).run()
    assert not app.exception
    assert list(app.segmented_control(key=SIDE_KEY).options) == list(SIDES)
    assert app.segmented_control(key=SIDE_KEY).value == SIDE_DETAIL
    assert not any("고친 것" in str(item.value) for item in app.caption)
    labels = {button.label for button in app.button}
    assert {"선택한 리비전 불러오기", "공식으로 지정…", "보관…"} <= labels
    # 저장 단추는 「저장 전 변경」 칸 한 곳이다.
    assert "변경 저장" not in labels

    app.session_state["scenario_list_action"] = "archive"
    app.run()

    assert not app.exception
    # 첫 행은 내장 시드 — 지금 최신 공식버전의 시나리오다. 자리에는 표지 한 마디와 꺼진 단추만
    # 두고 까닭은 그 풍선이다(검수표 11/02 equip-44 와 같은 꼴).
    assert not any("보관할 수 없습니다" in item.value for item in infos(app))
    assert "보관합니다" not in "".join(widget.label for widget in app.checkbox)
    blocked = next(button for button in app.button if button.label == "보관 실행")
    assert blocked.disabled and "보관할 수 없습니다" in str(blocked.help)

    # 공식이 아닌 시나리오는 보관할 수 있다. 되돌릴 수 있으므로 확인이 체크박스 한 번이다.
    other = _clone_official(database_path, "보관해 볼 시나리오", "ARCHIVE-TRY")
    app = AppTest.from_string(script, default_timeout=120)
    _check_row(app, other.scenario.scenario_id)
    app.run()
    app.button(key=f"{ACTION_KEY}_archive").click().run()

    assert not app.exception
    assert "보관합니다" in "".join(widget.label for widget in app.checkbox)
    execute = next(button for button in app.button if button.label == "보관 실행")
    assert execute.disabled
    # 보관의 뜻은 파란 안내 상자가 아니라 단추 풍선이다(검수표 11/02 equip-41 같은 기준). 잠긴
    # 동안은 그 풍선이 푸는 길도 말한다(설계 규칙 UI-INP-07).
    assert execute.help == ARCHIVE_LOCK_HELP
    assert "새 리비전 저장·공식버전 지정이 막힙니다" in str(execute.help)
    assert not any("보관하면" in item.value for item in infos(app))
    app.checkbox(key=archive_confirm_key(other.scenario.scenario_id)).check().run()
    execute = next(button for button in app.button if button.label == "보관 실행")
    assert not execute.disabled and execute.help == ARCHIVE_EFFECT_HELP


def test_a_database_held_by_another_program_shows_the_notice_instead_of_a_traceback(
    seeded_databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """따뜻한 프로세스에서는 저장소 생성자가 캐시라 페이지의 준비 단계가 DB 를 열지 않는다.

    그 회차의 첫 DB 열기는 시나리오 목록 읽기다. 다른 프로그램이 파일을 쥐어 그 읽기가 막혀도
    원문 트레이스백 대신 다른 화면과 같은 잠금 안내를 보이고, 이웃 두 탭도 그대로 선다.
    """
    database_path, equipment_path = seeded_databases
    app = AppTest.from_string(
        _page_script(PAGE_PATH, database_path, equipment_path), default_timeout=120
    ).run()
    assert not app.exception

    def held_by_another_program(*args: object, **kwargs: object) -> NoReturn:
        raise duckdb.IOException(
            'IO Error: Could not set lock on file "scenario.duckdb": '
            "Conflicting lock is held in python (PID 4242)"
        )

    monkeypatch.setattr(DuckDBScenarioRepository, "list_scenarios", held_by_another_program)
    app.run()

    assert not app.exception
    assert any("다른 프로그램이 파일을 열어 두었습니다" in text for text in place_errors(app))
    # Capa 시나리오 탭은 목록을 못 읽으면 작업 선택 앞에서 멈춘다.
    assert "시나리오 작업" not in {widget.label for widget in app.segmented_control}
    assert [tab.label for tab in app.main.tabs] == [
        ":material/database: Capa 시나리오",
        ":material/account_tree: 설비 시나리오",
        ":material/cloud_download: DB 등록",
        ":material/autorenew: 자동 갱신",
    ]


def _clone_official(database_path: Path, name: str, code: str) -> ScenarioSnapshot:
    """내장 시드 공식 리비전을 그대로 복제한 시나리오 하나. 페이지를 한 번 돌린 뒤에 부른다."""
    repository = DuckDBScenarioRepository(database_path)
    release = repository.latest_official_release()
    assert release is not None
    official = repository.load_revision(release.revision_id)
    return repository.create_scenario(
        ScenarioCreate(
            scenario_name=name,
            source_simulation_code=code,
            source_simulation_name=name,
            source_type="DUCKDB_SCENARIO_CLONE",
            pipeline_version="test-v1",
        ),
        official.tables,
        official.preset,
    )


def _place_of(app: AppTest, key: str) -> tuple[int, ...]:
    """그 key 의 화면 자리(블록 차례 경로) — 알림이 생기고 사라져도 같은지 본다."""

    def walk(node: Any, path: tuple[int, ...]) -> tuple[int, ...] | None:
        if getattr(node, "key", None) == key:
            return path
        children = getattr(node, "children", None)
        if isinstance(children, dict):
            for index, child in sorted(children.items()):
                found = walk(child, (*path, index))
                if found is not None:
                    return found
        return None

    found = walk(app._tree, ())
    assert found is not None, key
    return found


def test_the_archive_panel_keeps_its_place_when_the_flash_disappears(tmp_path: Path) -> None:
    """보관 알림이 사라지는 회차에도 「보관함」 칸 입력의 자리가 같다 — 자리가 밀리면 다시
    마운트되어 이름을 적던 영구 삭제 칸이 비었다(2026-10-01 브라우저 실측 — 옛 접힘 칸). 알림은 늘
    서 있는 칸 안이다."""
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    archived = _clone_official(database_path, "보관 대상", "ARCHIVE-1")
    DuckDBScenarioRepository(database_path).archive_scenario(archived.scenario.scenario_id)

    app = AppTest.from_string(script, default_timeout=120)
    app.session_state[SIDE_KEY] = SIDE_ARCHIVE
    app.session_state[FLASH_KEY] = "보관 대상을 보관했습니다."
    app.run()
    assert not app.exception
    assert any("보관했습니다" in item.value for item in successes(app))
    flashed_place = _place_of(app, DELETE_CONFIRM_KEY)
    assert app.selectbox(key=ARCHIVED_SELECT_KEY).options == ["보관 대상"]

    app.run()
    assert not app.exception
    assert not any("보관했습니다" in item.value for item in successes(app))
    assert _place_of(app, DELETE_CONFIRM_KEY) == flashed_place


def _clone_inputs(app: AppTest) -> dict[str, str]:
    """복제 폼 칸의 (라벨 → 값). BigDataQuery 탭에도 같은 라벨이 있어 키로 가린다."""
    return {
        widget.label: str(widget.value)
        for widget in [*app.text_input, *app.text_area]
        if str(widget.key or "").startswith("scenario_create_")
    }


def _fill_clone(app: AppTest, name: str, code: str) -> None:
    for widget in app.text_input:
        if not str(widget.key or "").startswith("scenario_create_"):
            continue
        if widget.label == "시나리오명":
            widget.set_value(name)
        elif widget.label == "원천 시뮬레이션 코드":
            widget.set_value(code)
        elif widget.label == "원천 시뮬레이션명":
            widget.set_value("복제 원천")
    next(button for button in app.button if button.label == "신규 시나리오 저장").click()
    app.run()
    assert not app.exception


def test_clone_form_clears_after_saving_and_refuses_a_taken_name(tmp_path: Path) -> None:
    """저장한 값이 폼에 남으면 한 번 더 눌러 같은 시나리오가 또 생겼다(2026-10-01 재현).

    성공하면 폼이 비고, 같은 이름을 다시 적으면 저장소가 막는다. 막힌 입력은 고쳐 쓰도록
    남는다.
    """
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    app = AppTest.from_string(script, default_timeout=120).run()
    assert not app.exception
    app.segmented_control(key=MODE_KEY).set_value(CLONE_MODE).run()
    assert not app.exception

    _fill_clone(app, "복제 A", "CLONE-A")
    assert any("복제 A를 저장했습니다" in item.value for item in successes(app))
    assert _clone_inputs(app) == {
        "시나리오명": "",
        "원천 시뮬레이션 코드": "",
        "원천 시뮬레이션명": "",
        "초기 리비전명": "초기 리비전",
        "메모": "",
    }

    _fill_clone(app, "복제 A", "CLONE-B")
    assert any("같은 이름의 시나리오가 이미 있습니다" in item.value for item in app.error)
    assert _clone_inputs(app)["시나리오명"] == "복제 A"
    names = [
        scenario.scenario_name
        for scenario in DuckDBScenarioRepository(database_path).list_scenarios(
            include_archived=True
        )
    ]
    assert names.count("복제 A") == 1


def test_clone_names_every_missing_required_field_at_once(tmp_path: Path) -> None:
    """빈 필수 칸은 **한 번에** 모두 알린다. 한 칸씩 알리면 세 번 눌러야 했다(2026-10-05 E2E).

    원천 코드·원천명 칸은 원본 값을 물려받지 않고 빈 채로 선다(2026-10-22 결정) — 그 두 칸의 풍선이
    새로 적어야 한다고 말한다(E2E r3 static — 채워질 줄 알고 눌러 한 번 막혔다). 늘 띄워 두는 설명
    글은 두지 않는다(설계 규칙 UI-TXT-01 · AMB-01 (가))."""
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    app = AppTest.from_string(script, default_timeout=120).run()
    app.segmented_control(key=MODE_KEY).set_value(CLONE_MODE).run()
    assert CLONE_SOURCE_NOTE not in [str(item.value) for item in app.caption]
    assert "새로 적는 필수 칸" in CLONE_SOURCE_NOTE
    helps = {
        widget.label: str(widget.help)
        for widget in app.text_input
        if str(widget.key or "").startswith("scenario_create_")
    }
    assert helps["원천 시뮬레이션 코드"] == CLONE_SOURCE_NOTE
    assert helps["원천 시뮬레이션명"] == CLONE_SOURCE_NOTE
    # 폼 위 한 줄은 값(복제 대상)과 표지만이다.
    (target,) = [str(item.value) for item in app.caption if str(item.value).startswith("복제 대상")]
    assert "복제합니다" not in target, target
    assert _clone_inputs(app)["원천 시뮬레이션 코드"] == ""
    assert _clone_inputs(app)["원천 시뮬레이션명"] == ""
    for widget in app.text_input:
        if str(widget.key or "").startswith("scenario_create_") and widget.label == "시나리오명":
            widget.set_value("이름만 적은 복제")
    next(button for button in app.button if button.label == "신규 시나리오 저장").click().run()

    assert not app.exception
    assert [item.value for item in app.error] == [
        "필수 칸이 비어 있습니다: 원천 시뮬레이션 코드, 원천 시뮬레이션명"
    ]
    assert _clone_inputs(app)["시나리오명"] == "이름만 적은 복제"


def test_clone_keeps_the_session_virtual_products(tmp_path: Path) -> None:
    """「신규 시나리오 저장」(복제)도 가상 제품 이력을 초기 리비전에 남긴다.

    복제는 가상 제품의 복제 행이 든 지금 편집본을 그대로 옮기면서 그 출처만 버렸다. 리비전 저장과
    같은 확인 문장을 저장 알림에 붙인다.
    """
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    app = AppTest.from_string(script, default_timeout=120).run()
    assert not app.exception
    app.segmented_control(key=MODE_KEY).set_value(CLONE_MODE).run()
    assert not app.exception
    # 첫 회차의 공식버전 활성화가 목록을 비우므로 그 뒤에 넣는다.
    app.session_state[VIRTUAL_PRODUCTS_KEY] = (
        VirtualProductRecord(
            product="DEMO_VIRTUAL",
            stack="8H",
            source_product="DEMO_SOURCE",
            source_stack="8H",
        ),
    )

    _fill_clone(app, "가상 제품 복제", "CLONE-VIRTUAL")

    assert any(
        item.value
        == (
            "가상 제품 복제를 저장했습니다. 가상 제품 1건이 포함되어 있습니다. "
            "실적과 대조할 수 없으므로 공식버전으로 발행하기 전에 확인하세요."
        )
        for item in successes(app)
    )
    repository = DuckDBScenarioRepository(database_path)
    clone = next(
        scenario
        for scenario in repository.list_scenarios()
        if scenario.scenario_name == "가상 제품 복제"
    )
    history = repository.list_virtual_products(clone.active_revision_id)
    assert history.to_dict("records") == [
        {
            "제품정보": "DEMO_VIRTUAL",
            "Stack": "8H",
            "원본 제품정보": "DEMO_SOURCE",
            "원본 Stack": "8H",
        }
    ]


def test_the_page_has_no_revision_save_mode_and_points_to_the_sidebar(tmp_path: Path) -> None:
    """새 리비전 저장은 사이드바 팝업 한 곳이다(2026-10-22 사용자 결정 S8).

    작업 선택에 「리비전 저장」이 없다. 그리로 가는 길 안내 글은 늘 띄워 두지 않는다(설계 규칙
    UI-TXT-03 · AMB-06 (나) — Guide 가 말한다). 예전 세션에 남은 옛 모드 값은 위젯 앞에서 버려 첫
    모드로 선다.
    """
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    app = AppTest.from_string(script, default_timeout=120)
    app.session_state[MODE_KEY] = "리비전 저장"
    app.run()

    assert not app.exception
    mode = app.segmented_control(key=MODE_KEY)
    assert list(mode.options) == ["목록 관리", "복제", "월 머지", "연도 Shift"]
    assert mode.value == "목록 관리"
    assert not any("새 리비전 저장은" in item.value for item in app.caption)
    # 하는 법 글을 두지 않는다(설계 규칙 UI-TXT-01).
    assert not any("한 건을 고르면" in item.value for item in app.caption)
    assert not app.success
    assert not any("DEMO 데이터" in item.value for item in app.info)


def test_the_tab_opens_straight_on_the_work_switch_without_a_store_status_box(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """옛 「저장소 상태」 칸(제목 · 올라와 있음 줄 · 식별자 펼침 · 공식버전 줄)은 없다 — 지금 올라와
    있는 리비전과 공식 표지는 사이드바 · 머리 띠, 최신 공식은 목록 표 칸이 말한다(설계 규칙
    UI-TXT-07). 작업 전환은 보이는 글 없이 서고 라벨은 보조 기술이 읽는 이름으로 남는다."""
    calls = install_fake_list_grid(monkeypatch)
    script = _page_script(PAGE_PATH, tmp_path / "scenario.duckdb", tmp_path / "equipment.duckdb")
    app = AppTest.from_string(script, default_timeout=120).run()

    assert not app.exception
    words = [str(item.value) for item in (*app.markdown, *app.caption)]
    for gone in ("저장소 상태", "**공식버전**", "올라와 있음 ·", "시나리오 ID", "리비전 ID"):
        assert not any(gone in word for word in words), gone
    assert not [item for item in app.main.expander if item.label == "식별자"]
    mode = app.segmented_control(key=MODE_KEY)
    assert mode.label == "시나리오 작업"
    assert mode.proto.label_visibility.value == mode.proto.label_visibility.COLLAPSED
    assert "관리할 시나리오" not in {item.label for item in app.segmented_control}
    # 내장 합성 시드의 표지는 그 이름이다 — 목록 표(와 사이드바 · 머리 띠)가 그대로 말한다.
    assert BUILTIN_SEED_SCENARIO_NAME in table_names(calls)
    # 시나리오 표는 머리를 맞출 오른쪽 칸 머리 두 자리를 안다.
    assert last(calls, TABLE_KEY)["side"] == {
        "choice": LIST_SIDE.choice_key,
        "body": LIST_SIDE.body_key,
    }


def test_an_old_session_clone_mode_name_falls_back_to_the_first_mode(tmp_path: Path) -> None:
    """옛 작업 이름 「지금 편집본 복제」 는 목록 밖이라 위젯 앞에서 버린다 — 첫 작업으로 선다."""
    script = _page_script(PAGE_PATH, tmp_path / "scenario.duckdb", tmp_path / "equipment.duckdb")
    app = AppTest.from_string(script, default_timeout=120)
    app.session_state[MODE_KEY] = "지금 편집본 복제"
    app.run()

    assert not app.exception
    assert app.segmented_control(key=MODE_KEY).value == "목록 관리"
    app.segmented_control(key=MODE_KEY).set_value(CLONE_MODE).run()
    assert not app.exception
    assert app.segmented_control(key=MODE_KEY).value == "복제"


@pytest.mark.parametrize(
    ("widget", "remembered"),
    [
        (":material/database: 시나리오 관리", None),
        (":material/cloud_download: BigDataQuery 등록", None),
        (None, ":material/database: 시나리오 관리"),
        (None, ":material/cloud_download: BigDataQuery 등록"),
    ],
)
def test_an_old_session_tab_value_outside_the_list_opens_the_first_tab(
    tmp_path: Path, widget: str | None, remembered: str | None
) -> None:
    """옛 세션의 탭 값(위젯 칸 · 기억 칸)이 지금 탭 넷 밖이어도 멈추지 않고 첫 탭이 열린다 — 그
    회차의 알림은 첫 탭 이름으로 나고, 기억 칸은 첫 탭으로 고쳐 적힌다."""
    script = _page_script(PAGE_PATH, tmp_path / "scenario.duckdb", tmp_path / "equipment.duckdb")
    app = AppTest.from_string(script, default_timeout=120)
    key = "scenario_management_tabs"
    if widget is not None:
        app.session_state[key] = widget
    if remembered is not None:
        app.session_state[remembered_tab_key(key)] = remembered
    app.run()

    assert not app.exception
    assert len(app.main.tabs) == 4
    assert app.session_state[remembered_tab_key(key)] == ":material/database: Capa 시나리오"
    assert app.segmented_control(key=MODE_KEY).value == "목록 관리"


def test_clone_refuses_an_edit_that_breaks_the_calculation(tmp_path: Path) -> None:
    """감사 D3: 리비전 저장에서 막히는 편집은 「복제」로도 저장되지 않는다.

    복제도 지금 편집본을 새 시나리오의 초기 리비전으로 적으므로 리비전 저장과 같은 검사를 거친다.
    """
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    app = AppTest.from_string(script, default_timeout=120).run()
    assert not app.exception
    active = dict(app.session_state[ACTIVE_SCENARIO_KEY])
    upeh = active["tables"]["RQ_UPEH"]
    # 모듈수(RQ_MODULE)가 없는 공정의 UPEH 한 줄 — 편집 전 리비전은 계산된다.
    active["tables"] = {
        **active["tables"],
        "RQ_UPEH": pd.concat(
            [upeh, upeh.iloc[:1].assign(공정="DEMO_NO_MODULE")], ignore_index=True
        ),
    }
    active["revision"] = int(active["revision"]) + 1
    active["content_token"] = uuid4().hex
    app.session_state[ACTIVE_SCENARIO_KEY] = active
    repository = DuckDBScenarioRepository(database_path)
    before = len(repository.list_scenarios())

    app.segmented_control(key=MODE_KEY).set_value(CLONE_MODE).run()
    _fill_clone(app, "깨진 편집 복제", "CLONE-BROKEN")

    assert any("이번 편집이 깨뜨린" in item.value for item in app.error)
    assert len(repository.list_scenarios()) == before
    assert _clone_inputs(app)["시나리오명"] == "깨진 편집 복제"


def test_clone_that_leaves_demand_out_warns_only_through_the_alert_popup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """복제 저장 뒤 소요대수에 들지 않은 수요(`GateVerdict.exclusion`)는 버튼 곁 경고 상자 없이
    알림창 · Alarm 에만 낸다 — 사이드바 리비전 저장 · 공식 지정과 한 꼴(2026-11-04 검수 의견
    home-18). 남은 계산 오류 경고(`exclusion` 거짓)도 같은 길이다(아래 물결표 시험 — 설계 규칙
    AMB-05 (나))."""
    import capa_simulation.components.scenario_management as scenario_management
    from capa_simulation.components.capacity_gate import GateVerdict

    message = (
        "소요대수에 들지 않은 수요가 있습니다(시나리오 전체 기간) — "
        "대당 Capa 가 없어 뺀 부하 경로 2건"
    )
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    monkeypatch.setattr(
        scenario_management,
        "revision_save_verdict",
        lambda *args: GateVerdict(True, message, exclusion=True),
    )
    app = AppTest.from_string(script, default_timeout=120).run()
    app.segmented_control(key=MODE_KEY).set_value(CLONE_MODE).run()
    _fill_clone(app, "빠진 수요 복제", "CLONE-EXCLUSION")

    assert any("빠진 수요 복제를 저장했습니다" in item.value for item in successes(app))
    assert not any("소요대수에 들지 않은 수요" in item.value for item in app.warning)
    (warned,) = flashed(app, "warning")
    assert warned.value == message
    assert warned.note is not None
    assert (warned.note["code"], warned.note["level"]) == ("FL-03", "check")


def test_gate_refusals_and_warnings_keep_tildes_in_example_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """계산 검사 거절·경고 글은 알림 상자(마크다운)다 — 오류 예시 키(편집한 칸 값)의 물결표 둘이
    지움선(「P<del>Q</del>R」)이 되지 않는다. 복제 거절·복제 뒤 경고·공식 지정 거절 세 자리."""
    import capa_simulation.components.scenario_management as scenario_management
    from capa_simulation.components.capacity_gate import GateVerdict

    message = "오류: RQ_UPEH 에 없는 공정이 있습니다: 1건, 예시 ['P~Q~R']"
    shown = message.replace("~", "\\~")
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    repository = DuckDBScenarioRepository(database_path)
    release = repository.latest_official_release()
    assert release is not None

    monkeypatch.setattr(
        scenario_management, "revision_save_verdict", lambda *args: GateVerdict(False, message)
    )
    app = AppTest.from_string(script, default_timeout=120).run()
    app.segmented_control(key=MODE_KEY).set_value(CLONE_MODE).run()
    _fill_clone(app, "물결표 거절 복제", "CLONE-TILDE-REFUSED")
    assert [item.value for item in app.error] == [shown]

    monkeypatch.setattr(
        scenario_management, "revision_save_verdict", lambda *args: GateVerdict(True, message)
    )
    _fill_clone(app, "물결표 경고 복제", "CLONE-TILDE-WARNED")
    # 복제 뒤 남은 계산 오류 경고는 알림창 표지로만 간다(설계 규칙 AMB-05 (나)). 단계는 확인
    # 필요(`FL-03`)다.
    (warned,) = [item for item in flashed(app, "warning") if item.value == shown]
    assert warned.note is not None
    assert (warned.note["code"], warned.note["level"]) == ("FL-03", "check")
    assert not app.warning

    monkeypatch.setattr(
        scenario_management, "official_publish_verdict", lambda *args: GateVerdict(False, message)
    )
    app = AppTest.from_string(script, default_timeout=120)
    _open_official(app, release.scenario_id, release.revision_id)
    _official_button(app).click()
    app.run()
    assert not app.exception
    assert [item.value for item in app.error] == [shown]
    latest = repository.latest_official_release()
    assert latest is not None and latest.release_no == release.release_no


def _register_virtual(app: AppTest, product: str) -> VirtualProductRecord:
    """등록 팝업이 하는 일을 세션에 그대로 한다 — 복제 행을 활성 표에 넣고 세션 목록에 더한다."""
    active = dict(app.session_state[ACTIVE_SCENARIO_KEY])
    tables = active["tables"]
    source = available_source_products(tables).iloc[0]
    request = VirtualProductRequest(
        source_product=str(source["제품정보"]),
        source_stack=str(source["Stack"]),
        product=product,
        stack=str(source["Stack"]),
    )
    active["tables"] = {**tables, **clone_product(tables, request)}
    app.session_state[ACTIVE_SCENARIO_KEY] = active
    record = VirtualProductRecord.from_request(request)
    registered = (
        app.session_state[VIRTUAL_PRODUCTS_KEY] if VIRTUAL_PRODUCTS_KEY in app.session_state else ()
    )
    app.session_state[VIRTUAL_PRODUCTS_KEY] = (*registered, record)
    return record


def _drop_from_active_tables(app: AppTest, product: str) -> None:
    """그 제품의 행을 제품 키를 가진 모든 표에서 지운다."""
    active = dict(app.session_state[ACTIVE_SCENARIO_KEY])
    tables = dict(active["tables"])
    for name in clone_table_names(tables):
        tables[name] = tables[name].loc[~tables[name]["제품정보"].eq(product)]
    active["tables"] = tables
    app.session_state[ACTIVE_SCENARIO_KEY] = active


def _page_with_sidebar_save(database_path: Path, equipment_path: Path) -> str:
    """이 페이지와 사이드바 시나리오 팝업 본문을 한 회차에 그리는 스크립트 — 새 리비전 저장은 팝업
    한 곳이라(S8) 실제 DB 로 저장 경로를 잴 때 이것을 쓴다. 팝업은 저장 구획으로 연다."""
    return _page_script(PAGE_PATH, database_path, equipment_path) + (
        "\nfrom capa_simulation.components.scenario_status import render_scenario_dialog_body\n"
        f"render_scenario_dialog_body(Path({str(database_path)!r}), page_file=None)\n"
    )


def _save_revision(app: AppTest, name: str) -> None:
    """사이드바 팝업 저장 구획에서 새 리비전을 저장한다(성공하면 칸의 key 세대가 오른다)."""
    from capa_simulation.components.scenario_status import SAVE_MODE, SCENARIO_DIALOG_MODE_KEY

    app.session_state[SCENARIO_DIALOG_MODE_KEY] = SAVE_MODE
    app.run()
    next(widget for widget in app.text_input if widget.label == "새 리비전명").set_value(name)
    next(button for button in app.button if button.label == "신규 리비전 저장").click()
    app.run()
    assert not app.exception


def _history_products(repository: DuckDBScenarioRepository, revision_id: str) -> list[str]:
    return repository.list_virtual_products(revision_id)["제품정보"].tolist()


def test_a_sidebar_save_with_nothing_changed_makes_no_revision(tmp_path: Path) -> None:
    """실제 DB — 리비전을 편집 없이 올린 세션의 「신규 리비전 저장」 은 새 리비전을 만들지 않고
    팝업에 「바뀐 것이 없습니다」 를 적는다(2026-11-01 개선 I5). 올린 세션의 표는 DB 를 오간 형이라
    등록 때 지은 지문과 갈려도 같은 내용으로 본다(저장소가 저장된 표로 지문을 다시 짓는다). 가상
    제품을 등록하면(이력이 바뀜) 평소대로 저장한다."""
    from capa_simulation.components.scenario_status import revision_unchanged_notice

    database_path = tmp_path / "scenario.duckdb"
    script = _page_with_sidebar_save(database_path, tmp_path / "equipment.duckdb")
    app = AppTest.from_string(script, default_timeout=120).run()
    assert not app.exception
    repository = DuckDBScenarioRepository(database_path)
    (scenario,) = repository.list_scenarios()
    latest_no = scenario.active_revision_no

    _save_revision(app, "그대로 저장")

    notices = [str(item.value) for item in infos(app) if "바뀐 것이 없습니다" in str(item.value)]
    assert notices == [revision_unchanged_notice(latest_no)]
    assert [item.active_revision_no for item in repository.list_scenarios()] == [latest_no]

    _register_virtual(app, "DEMO_VIRTUAL_A")
    _save_revision(app, "가상 제품 A")
    assert [item.active_revision_no for item in repository.list_scenarios()] == [latest_no + 1]


def test_new_revision_inherits_the_loaded_revisions_virtual_products(tmp_path: Path) -> None:
    """r2 에 등록한 가상 제품이 r2 를 이어 저장한 r3 에도 남는다(2026-10-05 사용자 결정 N6 = A).

    리비전을 불러오면 세션 목록이 비어서, 물려받지 않으면 r3 부터 출처가 사라졌다. r3 의 세션
    목록에는 B 만 있으므로 A 는 부모 이력에서만 올 수 있다. 저장은 사이드바 팝업 한 곳이다.
    """
    database_path = tmp_path / "scenario.duckdb"
    script = _page_with_sidebar_save(database_path, tmp_path / "equipment.duckdb")
    app = AppTest.from_string(script, default_timeout=120).run()
    assert not app.exception
    _register_virtual(app, "DEMO_VIRTUAL_A")
    _save_revision(app, "가상 제품 A")
    repository = DuckDBScenarioRepository(database_path)
    (scenario,) = [item for item in repository.list_scenarios() if item.active_revision_no == 2]
    assert _history_products(repository, scenario.active_revision_id) == ["DEMO_VIRTUAL_A"]
    # 활성화가 세션 목록을 비웠다 — r2 의 이력은 이제 DB 에만 있다.
    assert VIRTUAL_PRODUCTS_KEY not in app.session_state

    _register_virtual(app, "DEMO_VIRTUAL_B")
    assert [record.product for record in app.session_state[VIRTUAL_PRODUCTS_KEY]] == [
        "DEMO_VIRTUAL_B"
    ]
    _save_revision(app, "가상 제품 B")

    summary = next(
        item for item in repository.list_scenarios() if item.scenario_id == scenario.scenario_id
    )
    assert summary.active_revision_no == 3
    assert _history_products(repository, summary.active_revision_id) == [
        "DEMO_VIRTUAL_A",
        "DEMO_VIRTUAL_B",
    ]


def test_clone_inherits_the_active_revisions_virtual_products_still_in_the_tables(
    tmp_path: Path,
) -> None:
    """「복제」의 초기 리비전도 올라와 있는 리비전의 이력을 물려받는다.

    물려받은 제품이 복제하는 표 어디에도 남아 있지 않으면 그 이력은 따라가지 않는다.
    """
    database_path = tmp_path / "scenario.duckdb"
    script = _page_with_sidebar_save(database_path, tmp_path / "equipment.duckdb")
    app = AppTest.from_string(script, default_timeout=120).run()
    assert not app.exception
    _register_virtual(app, "DEMO_VIRTUAL_A")
    _register_virtual(app, "DEMO_VIRTUAL_B")
    _save_revision(app, "가상 제품 둘")

    _drop_from_active_tables(app, "DEMO_VIRTUAL_A")
    app.segmented_control(key=MODE_KEY).set_value(CLONE_MODE).run()
    assert not app.exception
    _fill_clone(app, "가상 제품 상속 복제", "CLONE-INHERIT")

    notice = (
        "가상 제품 1건이 포함되어 있습니다. "
        "실적과 대조할 수 없으므로 공식버전으로 발행하기 전에 확인하세요."
    )
    assert f"가상 제품 상속 복제를 저장했습니다. {notice}" in [
        item.value for item in successes(app)
    ]
    repository = DuckDBScenarioRepository(database_path)
    clone = next(
        item for item in repository.list_scenarios() if item.scenario_name == "가상 제품 상속 복제"
    )
    assert _history_products(repository, clone.active_revision_id) == ["DEMO_VIRTUAL_B"]


def _check_row(app: AppTest, scenario_id: str) -> None:
    """목록 표에서 그 시나리오를 연 상태로 둔다 — 연 시나리오는 초안의 `opened` 다(행 id)."""
    held = app.session_state[DRAFT_KEY] if DRAFT_KEY in app.session_state else ListDraft()
    app.session_state[DRAFT_KEY] = replace(held, opened=scenario_id)


def _check_archive(app: AppTest) -> None:
    """연 시나리오의 보관 확인 체크를 켠다 — 칸 key 는 시나리오마다 다르다."""
    app.checkbox(key=archive_confirm_key(str(_draft(app).opened))).check()


def _draft(app: AppTest) -> ListDraft:
    draft = app.session_state[DRAFT_KEY]
    assert isinstance(draft, ListDraft)
    return draft


def _list_app(
    script: str, monkeypatch: pytest.MonkeyPatch, *, side: str = SIDE_CHANGES
) -> tuple[AppTest, ListBrowser, Calls]:
    """목록 표 대역을 깐 화면 한 벌. 「변경 저장」 은 「저장 전 변경」 칸에 있다."""
    calls = install_fake_list_grid(monkeypatch)
    app = AppTest.from_string(script, default_timeout=120)
    app.session_state[SIDE_KEY] = side
    browser = ListBrowser(app, calls)
    browser.run()
    return app, browser, calls


def _side(app: AppTest, side: str) -> None:
    """오른쪽 칸 고르기를 누른 것과 같다."""
    app.session_state[SIDE_KEY] = side
    app.run()
    assert not app.exception


def _save(app: AppTest) -> None:
    """「변경 저장」 을 눌러 그 회차를 돌린다."""
    app.button(key="scenario_list_save").click().run()
    assert not app.exception


def _revision_rows(calls: Calls) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = last(calls, REVISIONS_KEY)["rows"]
    return rows


def _counts(calls: Calls) -> dict[str, int]:
    counts: dict[str, int] = last(calls, CHANGES_KEY)["counts"]
    return counts


def test_rename_refreshes_the_cached_snapshot_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """목록 표에서 시나리오명을 고쳐 「변경 저장」하면 캐시된 리비전 스냅샷도 새 이름을 돌려준다.

    스냅샷 payload 는 시나리오 메타데이터를 함께 담는다. 비우지 않으면 그 리비전에서 파생한
    시나리오의 `source_simulation_name` 과 출처 메모에 옛 이름이 남는다. 올라와 있는 시나리오면
    머리 띠 이름표도 같이 바뀐다.
    """
    from capa_simulation.scenario_activation import ACTIVE_SCENARIO_LABEL_KEY

    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    (summary,) = DuckDBScenarioRepository(database_path).list_scenarios()
    revision_id = summary.active_revision_id
    cached = load_scenario_snapshot(str(database_path), revision_id)
    assert cached.scenario.scenario_name == summary.scenario_name

    app, browser, calls = _list_app(script, monkeypatch)
    browser.rename_scenario(summary.scenario_id, "  이름 바꾼 시나리오 ")
    # 고친 수는 칸 안 수 넷이 말한다 — 표 위에 값 줄을 세우지 않는다.
    assert _counts(calls) == {"scenario": 1, "order": 0, "revision": 0, "blocked": 0}
    assert not any("고친 것" in str(item.value) for item in app.caption)
    _save(app)

    assert "시나리오명 1건을 저장했습니다." in [item.value for item in successes(app)]
    refreshed = load_scenario_snapshot(str(database_path), revision_id)
    assert refreshed.scenario.scenario_name == "이름 바꾼 시나리오"
    assert table_names(calls) == ["이름 바꾼 시나리오"]
    assert "saved" not in table_row(calls, summary.scenario_id)
    assert _counts(calls)["scenario"] == 0
    assert app.session_state[ACTIVE_SCENARIO_LABEL_KEY]["scenario_name"] == "이름 바꾼 시나리오"


def test_archive_and_delete_drop_the_cached_comparison_target(tmp_path: Path) -> None:
    """보관·영구 삭제는 DB 의 공용 비교 대상을 비운다. 캐시된 비교 대상도 함께 비어야 한다.

    캐시는 DB 경로 키라 저장소가 `version` 을 올려도 무효화되지 않는다. 남아 있으면 새 세션의
    HOME 이 보관·삭제된 시나리오를 비교 대상으로 다시 심는다.
    """
    database_path = tmp_path / "scenario.duckdb"
    database = str(database_path)
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    repository = DuckDBScenarioRepository(database_path)
    target = _clone_official(database_path, "비교 대상", "COMPARE-1")
    target_id = target.scenario.scenario_id
    repository.replace_global_comparison_scenario(
        target_id, target.revision.revision_id, source="테스트"
    )
    clear_global_comparison_scenario_cache()
    assert load_global_comparison_scenario(database).scenario_id == target_id

    app = AppTest.from_string(script, default_timeout=120)
    _check_row(app, target_id)
    app.run()
    app.button(key=f"{ACTION_KEY}_archive").click().run()
    assert not app.exception
    _check_archive(app)
    app.run()
    next(button for button in app.button if button.label == "보관 실행").click()
    app.run()
    assert not app.exception

    assert repository.load_global_comparison_scenario().scenario_id is None
    assert load_global_comparison_scenario(database).scenario_id is None

    # 영구 삭제 칸만 따로 본다. 보관이 DB 를 이미 비웠으므로 보관본을 다시 가리키게 한다.
    repository.replace_global_comparison_scenario(
        target_id, target.revision.revision_id, source="테스트"
    )
    clear_global_comparison_scenario_cache()
    assert load_global_comparison_scenario(database).scenario_id == target_id

    app = AppTest.from_string(script, default_timeout=120)
    app.session_state[SIDE_KEY] = SIDE_ARCHIVE
    app.session_state[ARCHIVED_SELECT_KEY] = target_id
    app.run()
    assert not app.exception
    app.text_input(key=DELETE_CONFIRM_KEY).set_value("비교 대상")
    app.run()
    app.button(key=DELETE_BUTTON_KEY).click()
    app.run()
    assert not app.exception

    assert target_id not in {
        scenario.scenario_id for scenario in repository.list_scenarios(include_archived=True)
    }
    assert load_global_comparison_scenario(database).scenario_id is None


def test_rename_archive_and_delete_refresh_the_cached_main_cases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """목록 이름 바꾸기·보관·영구 삭제는 DB 의 주요 Case 프로필을 바꾼다. 캐시도 새로 읽혀야 한다.

    캐시는 DB 경로 키라 저장소가 `version` 을 올리거나 Case 를 비워도 무효화되지 않는다. 남아 있으면
    HOME 슬롯(캐시만 읽는다)이 옛 이름이나 보관·삭제된 시나리오를 그대로 가리킨다.
    """
    database_path = tmp_path / "scenario.duckdb"
    database = str(database_path)
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    repository = DuckDBScenarioRepository(database_path)
    target = _clone_official(database_path, "주요 대상", "MAIN-CASE-1")
    target_id = target.scenario.scenario_id
    target_revision = target.revision.revision_id
    repository.replace_global_main_case(2, target_id, target_revision, source="테스트")
    clear_global_main_cases_cache()
    seen = load_global_main_cases(database)
    assert seen.case(2) == (target_id, target_revision)

    # 목록 표에서 이름 바꾸기 — 저장소가 version 을 올렸다.
    app, browser, _ = _list_app(script, monkeypatch)
    browser.rename_scenario(target_id, "주요 대상 새 이름")
    _save(app)
    assert "시나리오명 1건을 저장했습니다." in [item.value for item in successes(app)]
    assert load_global_main_cases(database).version == seen.version + 1

    app = AppTest.from_string(script, default_timeout=120)
    _check_row(app, target_id)
    app.run()
    app.button(key=f"{ACTION_KEY}_archive").click().run()
    assert not app.exception
    _check_archive(app)
    app.run()
    next(button for button in app.button if button.label == "보관 실행").click()
    app.run()
    assert not app.exception
    assert repository.load_global_main_cases().case(2) == (None, None)
    assert load_global_main_cases(database).case(2) == (None, None)

    # 영구 삭제 칸만 따로 본다. 보관이 DB 를 이미 비웠으므로 보관본을 다시 가리키게 한다.
    repository.replace_global_main_case(2, target_id, target_revision, source="테스트")
    clear_global_main_cases_cache()
    assert load_global_main_cases(database).case(2) == (target_id, target_revision)

    app = AppTest.from_string(script, default_timeout=120)
    app.session_state[SIDE_KEY] = SIDE_ARCHIVE
    app.session_state[ARCHIVED_SELECT_KEY] = target_id
    app.run()
    assert not app.exception
    app.text_input(key=DELETE_CONFIRM_KEY).set_value("주요 대상 새 이름")
    app.run()
    app.button(key=DELETE_BUTTON_KEY).click()
    app.run()
    assert not app.exception
    assert target_id not in {
        scenario.scenario_id for scenario in repository.list_scenarios(include_archived=True)
    }
    assert load_global_main_cases(database).case(2) == (None, None)


def test_the_archived_box_shows_what_the_next_restore_and_delete_act_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """되돌리기·영구 삭제 뒤 보관본 상자의 **브라우저 글자**가 서버의 선택과 같다.

    처리한 시나리오의 선택을 지우기(`pop`)만 하면 서버는 첫 보관본을 쓰는데 브라우저는 처리한
    이름을 계속 보였고, 다음 「되돌리기」가 보이지 않는 다른 시나리오를 되돌렸다. 영구 삭제의 확인
    칸에도 지운 이름이 남았다. 브라우저가 글자를 들고 다니므로 `BrowserChoice` 로 잰다.
    """
    from widget_browser import BrowserChoice

    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    repository = DuckDBScenarioRepository(database_path)
    for index, name in enumerate(("보관 가", "보관 나", "보관 다"), start=1):
        archived = _clone_official(database_path, name, f"ARCHIVE-{index}")
        repository.archive_scenario(archived.scenario.scenario_id)

    def name_of(scenario_id: object) -> str:
        return next(
            scenario.scenario_name
            for scenario in repository.list_scenarios(include_archived=True)
            if scenario.scenario_id == scenario_id
        )

    def status_of(name: str) -> str:
        return next(
            scenario.status
            for scenario in repository.list_scenarios(include_archived=True)
            if scenario.scenario_name == name
        )

    def click(key_or_label: str) -> None:
        next(button for button in app.button if key_or_label in {button.key, button.label}).click()
        browser.run()
        assert not app.exception

    app = AppTest.from_string(script, default_timeout=120)
    app.session_state[SIDE_KEY] = SIDE_ARCHIVE
    browser = BrowserChoice(app, "selectbox", ARCHIVED_SELECT_KEY)
    browser.start()
    assert not app.exception
    shown = browser.options()
    assert sorted(shown) == ["보관 가", "보관 나", "보관 다"]

    # 가운데 것을 골라 되돌린다 — 상자는 남은 것 가운데 서버가 고른 것을 보인다.
    middle = shown[1]
    browser.pick(middle)
    browser.run()
    assert name_of(app.session_state[ARCHIVED_SELECT_KEY]) == middle
    click("scenario_archived_restore")
    assert status_of(middle) == "ACTIVE"
    assert middle not in browser.options()
    assert browser.last_set_value
    assert browser.wire == name_of(app.session_state[ARCHIVED_SELECT_KEY])

    # 보이는 것을 영구 삭제한다 — 상자는 남은 하나를 보이고 확인 칸은 빈 칸으로 돌아간다.
    doomed = str(browser.wire)
    app.text_input(key=DELETE_CONFIRM_KEY).set_value(doomed)
    browser.run()
    click(DELETE_BUTTON_KEY)
    remaining = browser.options()
    assert doomed not in remaining
    assert len(remaining) == 1
    assert browser.last_set_value
    assert browser.wire == remaining[0] == name_of(app.session_state[ARCHIVED_SELECT_KEY])
    confirm = app.text_input(key=DELETE_CONFIRM_KEY)
    assert confirm.proto.set_value
    assert confirm.value == ""

    # 다음 「되돌리기」 는 보이던 것을 되돌린다. 고름이 바뀐 직후의 누름은 사람이 바뀐 고름을 보고
    # 누른 것이 아니라 걸지 않는다(`prune_named_choice`) — 창이 지난 누름으로 본다.
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    click("scenario_archived_restore")
    assert status_of(remaining[0]) == "ACTIVE"


OFFICIAL_BUTTON = "선택 리비전을 공식버전으로 지정"
VIRTUAL_CONFIRM_LABEL = "가상 제품이 포함된 것을 확인했습니다"


def _open_official(app: AppTest, scenario_id: str, revision_id: str) -> None:
    """목록에서 그 시나리오를, 리비전 표에서 리비전을 고른 뒤 「공식으로 지정…」 팝업을 연다."""
    _check_row(app, scenario_id)
    app.run()
    app.session_state[DRAFT_KEY] = replace(_draft(app), picked=revision_id)
    app.run()
    app.button(key=f"{CARD_OFFICIAL_KEY}_{scenario_id}").click().run()
    assert not app.exception
    assert app.session_state[OFFICIAL_DIALOG_KEY] == (scenario_id, revision_id)


def _close_official(app: AppTest) -> None:
    """팝업의 X·바깥 클릭(`on_dismiss`)과 같다 — 열림 칸을 비운다."""
    del app.session_state[OFFICIAL_DIALOG_KEY]
    app.run()


def _official_button(app: AppTest) -> Button:
    return next(button for button in app.button if button.label == OFFICIAL_BUTTON)


def test_official_release_of_a_revision_with_virtual_products_needs_a_confirmation(
    tmp_path: Path,
) -> None:
    """가상 제품이 든 리비전은 확인 체크 전에 공식버전으로 지정되지 않는다(2026-10-06 사용자 결정).

    가상 제품은 실적과 대조할 수 없는 값이다. 그런 리비전이 모두의 첫 화면이 되기 전에 지정하는
    사람이 제품 · Stack 목록을 보고 확인해야 한다. 계산 검사(`official_publish_verdict`)는 그대로
    함께 돈다.
    """
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    repository = DuckDBScenarioRepository(database_path)
    release = repository.latest_official_release()
    assert release is not None
    official = repository.load_revision(release.revision_id)
    virtual_products = [
        {
            "product": "DEMO_VIRTUAL",
            "stack": "8H",
            "source_product": "DEMO_SOURCE",
            "source_stack": "8H",
        }
    ]
    saved = repository.save_revision(
        official.scenario.scenario_id,
        official.tables,
        official.preset,
        revision_name="가상 제품 포함",
        parent_revision_id=release.revision_id,
        virtual_products=virtual_products,
    )
    revision_id = saved.revision.revision_id
    other = repository.save_revision(
        official.scenario.scenario_id,
        official.tables,
        official.preset,
        revision_name="가상 제품 포함 2",
        parent_revision_id=revision_id,
        virtual_products=virtual_products,
    )
    other_revision_id = other.revision.revision_id

    app = AppTest.from_string(script, default_timeout=120)
    _open_official(app, saved.scenario.scenario_id, revision_id)
    assert (
        "이 리비전에는 가상 제품 1건이 포함되어 있습니다(DEMO\\_VIRTUAL · 8H). "
        "실적과 대조할 수 없는 값입니다. 그대로 공식버전으로 지정할까요?"
    ) in [item.value for item in app.warning]
    assert _official_button(app).disabled
    assert _official_button(app).help == OFFICIAL_CONFIRM_HELP

    # 잠긴 버튼은 누를 수 없다(AppTest 도 브라우저처럼 거절한다). 발행 이력은 그대로다.
    with pytest.raises(AppTestError):
        _official_button(app).click()
    assert repository.count_official_releases(saved.scenario.scenario_id) == 1

    app.checkbox(key=official_confirm_key(revision_id)).check()
    app.run()
    assert not app.exception
    assert not _official_button(app).disabled
    assert not _official_button(app).help

    # 확인은 리비전마다 따로다. 한 리비전에 남긴 체크가 가상 제품이 든 다른 리비전의 지정을
    # 열어 주면, 확인하지 않은 리비전이 공식버전이 된다. 팝업을 닫고 다른 리비전으로 다시 연다.
    _close_official(app)
    _open_official(app, saved.scenario.scenario_id, other_revision_id)
    assert _official_button(app).disabled

    _close_official(app)
    _open_official(app, saved.scenario.scenario_id, revision_id)
    # 다른 리비전을 보는 동안 그리지 않은 체크는 지워진다. 돌아오면 다시 확인해야 한다.
    assert _official_button(app).disabled
    app.checkbox(key=official_confirm_key(revision_id)).check()
    app.run()
    assert not app.exception
    assert not _official_button(app).disabled
    _official_button(app).click()
    app.run()
    assert not app.exception

    latest = repository.latest_official_release()
    assert latest is not None and latest.revision_id == revision_id
    assert latest.release_no == 2
    assert any(item.value.startswith("공식 v2 · ") for item in successes(app))
    # 지정하면 팝업이 닫힌다.
    assert OFFICIAL_DIALOG_KEY not in app.session_state


def test_the_official_virtual_product_warning_draws_the_typed_names_literally() -> None:
    """공식 지정 확인의 가상 제품 목록은 `st.warning`(마크다운)으로 그린다 — 사람이 적은
    제품정보·Stack 의 물결표·별표가 지움선·기울임이 되지 않게 막아 싣는다(2026-10-26 E2E 같은 꼴 —
    가상 제품 등록 알림)."""
    record = VirtualProductRecord(
        product="HBM4~시제~",
        stack="E2E~가상~*1*",
        source_product="DEMO PRODUCT A",
        source_stack="8H",
    )
    warning = official_virtual_product_warning([record])
    assert (
        f"가상 제품 1건이 포함되어 있습니다({literal_markdown('HBM4~시제~')} · "
        f"{literal_markdown('E2E~가상~*1*')})."
    ) in warning, warning


def test_official_release_without_virtual_products_asks_nothing(tmp_path: Path) -> None:
    """가상 제품이 없는 리비전은 전과 같다 — 경고·확인 체크 없이 버튼이 바로 열린다.

    팝업은 「지금 공식 → 새 공식」을 나란히 보인다(2026-10-22 사용자 결정 S9).
    """
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    repository = DuckDBScenarioRepository(database_path)
    release = repository.latest_official_release()
    assert release is not None

    app = AppTest.from_string(script, default_timeout=120)
    _open_official(app, release.scenario_id, release.revision_id)
    shown = [item.value for item in app.markdown]
    assert any(value.startswith(f"**v{release.release_no}** · ") for value in shown), shown
    assert any(value.startswith(f"**v{release.release_no + 1}** · ") for value in shown), shown
    # 값 표지 한 마디와 지정 단추 풍선 — 파란 안내 상자는 서지 않는다(검수표 11/02 equip-41 같은
    # 기준).
    assert any(item.value == SAME_AS_OFFICIAL_LINE for item in app.caption)
    assert not any("지금 공식과 같은 리비전" in item.value for item in infos(app))
    assert _official_button(app).help == SAME_AS_OFFICIAL_HELP
    assert not any("가상 제품" in item.value for item in app.warning)
    assert VIRTUAL_CONFIRM_LABEL not in {widget.label for widget in app.checkbox}
    assert not _official_button(app).disabled

    _official_button(app).click()
    app.run()
    assert not app.exception

    latest = repository.latest_official_release()
    assert latest is not None and latest.release_no == 2
    assert latest.revision_id == release.revision_id
    assert any(item.value.startswith("공식 v2 · ") for item in successes(app))


def test_the_official_popup_does_not_publish_over_a_release_made_while_it_was_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """팝업을 연 사이 다른 사람이 먼저 공식버전을 지정하면 지정하지 않는다(S9 — 「지금 공식」 대조).

    팝업이 보인 「지금 공식」 번호를 저장소에 넘긴다. 그 사이 번호가 올랐으면 저장소가 쓰지 않고,
    팝업은 배경 회차 말투가 아니라 할 일(닫고 다시 열기)을 적는다. 브라우저에서 팝업 안 제출은
    프래그먼트 회차라 「지금 공식」이 마지막 전체 회차의 값이지만, `AppTest` 는 전체 회차로 다시
    읽으므로 남의 지정을 지정 단추를 누른 회차의 쓰기 바로 앞에 끼운다.
    """
    from capa_simulation.components.scenario_management import official_moved_message

    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    repository = DuckDBScenarioRepository(database_path)
    release = repository.latest_official_release()
    assert release is not None
    publish = DuckDBScenarioRepository.publish_official_revision

    def racing(
        self: DuckDBScenarioRepository, scenario_id: str, revision_id: str, **kwargs: Any
    ) -> object:
        publish(self, scenario_id, revision_id, release_name="남이 먼저 지정")
        return publish(self, scenario_id, revision_id, **kwargs)

    app = AppTest.from_string(script, default_timeout=120)
    _open_official(app, release.scenario_id, release.revision_id)
    monkeypatch.setattr(DuckDBScenarioRepository, "publish_official_revision", racing)
    _official_button(app).click()
    app.run()
    monkeypatch.undo()

    assert not app.exception
    assert official_moved_message(release.release_no + 1) in [item.value for item in app.error]
    latest = repository.latest_official_release()
    assert latest is not None
    assert (latest.release_no, latest.release_name) == (release.release_no + 1, "남이 먼저 지정")
    assert app.session_state[OFFICIAL_DIALOG_KEY] == (release.scenario_id, release.revision_id)


def test_official_release_with_demand_left_out_of_the_requirement_warns_after_publishing(
    tmp_path: Path,
) -> None:
    """P1·P3 — 소요대수에 들지 않은 수요가 있는 리비전도 지정은 되지만, 지정한 사람이 건수를 본다.

    발행 검사가 경고를 돌려줘도 화면이 성공 문구만 띄우면 지정한 사람은 확보율이 높게 나온
    리비전을 모두의 첫 화면으로 올린 줄 모른다. 지정은 끝났고 고칠 입력이 그 자리에 없어 버튼 곁
    경고 상자 없이 알림창 · Alarm 에만 낸다(사이드바 리비전 저장과 한 꼴 — 2026-11-04 검수 의견
    home-18). 단계는 확인 필요(`FL-03`)다.
    """
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    repository = DuckDBScenarioRepository(database_path)
    release = repository.latest_official_release()
    assert release is not None
    official = repository.load_revision(release.revision_id)
    tables = dict(official.tables)
    chip = tables["RQ_CHIP_QTY"]
    tables["RQ_CHIP_QTY"] = chip.loc[chip["제품정보"].ne(chip["제품정보"].iloc[-1])]
    saved = repository.save_revision(
        official.scenario.scenario_id,
        tables,
        official.preset,
        revision_name="Chip 구성 한 제품 누락",
        parent_revision_id=release.revision_id,
    )

    app = AppTest.from_string(script, default_timeout=120)
    _open_official(app, saved.scenario.scenario_id, saved.revision.revision_id)
    _official_button(app).click()
    app.run()
    assert not app.exception

    latest = repository.latest_official_release()
    assert latest is not None and latest.revision_id == saved.revision.revision_id
    assert any(item.value.startswith("공식 v2 · ") for item in successes(app))
    assert not any("부하량에서 빠진 계획" in item.value for item in app.warning), [
        item.value for item in app.warning
    ]
    (warned,) = flashed(app, "warning")
    assert "부하량에서 빠진 계획" in warned.value
    assert warned.note is not None
    assert (warned.note["code"], warned.note["level"]) == ("FL-03", "check")


def test_the_card_follows_a_revision_loaded_from_the_sidebar_popup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """리비전 표의 고름은 올라와 있는 리비전이 바뀌면 그 리비전으로 옮긴다(2026-10-11 리뷰).

    사이드바 시나리오 팝업의 불러오기는 프래그먼트 실행이라 이 페이지의 값이 버려지지 않는다.
    처음에만 넣던 씨앗이 옛 리비전을 고른 채 남아 「불러오기」·「공식버전 지정」이 엉뚱한 리비전에
    걸렸다. 올라와 있는 리비전이 그대로인 동안 사용자가 일부러 고른 리비전은 남는다.
    """
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    app = AppTest.from_string(script, default_timeout=120).run()
    assert not app.exception
    repository = DuckDBScenarioRepository(database_path)
    release = repository.latest_official_release()
    assert release is not None
    official = repository.load_revision(release.revision_id)
    scenario_id = official.scenario.scenario_id
    second = repository.save_revision(
        scenario_id,
        official.tables,
        official.preset,
        revision_name="두 번째",
    )
    app, browser, _ = _list_app(script, monkeypatch, side=SIDE_DETAIL)
    assert _draft(app).picked == release.revision_id

    # 사이드바 팝업에서 두 번째 리비전을 불러온 것과 같다 — 이 페이지의 값은 남아 있다.
    app.session_state["active_persisted_revision_id"] = second.revision.revision_id
    browser.run()
    assert _draft(app).picked == second.revision.revision_id

    # 올라와 있는 리비전이 그대로인 동안 사용자가 고른 리비전은 다음 회차에도 남는다.
    browser.pick(scenario_id, release.revision_id)
    browser.run()
    assert _draft(app).picked == release.revision_id

    # 올라와 있는 것이 다른 시나리오로 갔다가 마지막으로 씨앗을 넣은 리비전으로 돌아와도 표가
    # 따라온다 — 씨앗 기록이 남아 있으면 「같은 씨앗」으로 읽혀 사용자가 고른 옛 리비전에
    # 머물렀다(2026-10-11 재검증).
    app.session_state["active_persisted_scenario_id"] = "elsewhere-scenario"
    app.session_state["active_persisted_revision_id"] = "elsewhere-revision"
    browser.run()
    app.session_state["active_persisted_scenario_id"] = scenario_id
    app.session_state["active_persisted_revision_id"] = second.revision.revision_id
    browser.run()
    assert _draft(app).picked == second.revision.revision_id


def test_a_picked_bigdataquery_row_keeps_its_form_after_the_list_order_is_saved(
    tmp_path: Path,
) -> None:
    """첫 탭의 「변경 저장」이 DB 등록 폼 글자를 버리지 않는다.

    옛 「순서 저장」은 `st.rerun()` 으로 등록 폼보다 먼저 끊어, 그 회차에 그려지지 않은 폼 글자 칸을
    Streamlit 이 버렸다 — 목록 행은 선택된 채 코드·시나리오명이 비어 저장이 막혔다. 「변경 저장」은
    콜백이라 본문을 끊지 않는다.
    """
    from datetime import date, datetime

    from capa_simulation.components.bigdataquery_registration import (
        CATALOG_RESULT_KEY,
        FORM_CODE_KEY,
        FORM_SCENARIO_NAME_KEY,
        CatalogResult,
        catalog_list_key,
    )
    from capa_simulation.io.company_bigdataquery_adapter import QueryWindow
    from capa_simulation.services.bigdataquery_catalog_view import SCOPE_ALL, normalize_catalog

    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    _clone_official(database_path, "순서 바꿀 시나리오", "ORDER-1")
    stored = [
        scenario.scenario_id
        for scenario in DuckDBScenarioRepository(database_path).list_scenarios()
    ]
    app = AppTest.from_string(script, default_timeout=120)
    app.session_state[CATALOG_RESULT_KEY] = CatalogResult(
        frame=normalize_catalog(
            pd.DataFrame(
                {
                    "simulation_name": ["알파 시뮬"],
                    "simulation_code": ["DEMO-A-001"],
                    "plan_name": ["PLAN 알파"],
                    "plan_code": ["DEMO-PLAN-1"],
                    "regist_data": ["2026-09-02 03:04:05"],
                }
            )
        ),
        window=QueryWindow(start_date=date(2026, 9, 1), end_date=date(2026, 9, 8)),
        queried_at=datetime(2026, 9, 8, 10, 0, 0),
        token="demo-token",
    )
    # 목록 표에서 첫 행을 누른 것과 같다 — 선택 이벤트를 위젯 상태 모양 그대로 넣는다.
    app.session_state[catalog_list_key("demo-token", 0, "", SCOPE_ALL)] = {
        "selection": {"rows": [0], "columns": []}
    }
    app.session_state[DRAFT_KEY] = ListDraft(
        order=tuple(reversed(stored)), order_base=tuple(stored)
    )
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    app.run()
    assert not app.exception
    assert app.text_input(key=FORM_CODE_KEY).value == "DEMO-A-001"

    app.button(key="scenario_list_save").click().run()

    assert not app.exception
    assert "누적 순서를 저장했습니다." in [item.value for item in successes(app)]
    assert app.text_input(key=FORM_CODE_KEY).value == "DEMO-A-001"
    assert app.text_input(key=FORM_SCENARIO_NAME_KEY).value == "알파 시뮬 (DEMO-A-001)"


def test_the_list_names_the_latest_revision_and_which_revision_is_official(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """「최신」은 마지막으로 저장한 리비전이고, 공식 칸은 공식 리비전 번호를 함께 적는다.

    「활성 리비전」이라 부르던 열은 세션에 올라와 있는 리비전처럼 읽혀, 「r5 | v5 · 최신」이 r5 를
    공식으로 오독하게 했다(2026-10-22 화면 점검).
    """
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    repository = DuckDBScenarioRepository(database_path)
    seed_release = repository.latest_official_release()
    assert seed_release is not None
    seed = repository.load_revision(seed_release.revision_id)
    newer = repository.save_revision(
        seed.scenario.scenario_id, seed.tables, seed.preset, revision_name="공식 뒤 저장"
    )
    clone = _clone_official(database_path, "공식 복제", "OFFICIAL-CLONE")
    repository.publish_official_revision(
        clone.scenario.scenario_id, clone.revision.revision_id, release_name="복제 공식안"
    )

    _, _, calls = _list_app(script, monkeypatch, side=SIDE_DETAIL)
    seed_row = table_row(calls, seed.scenario.scenario_id)
    assert seed_row["latest"] == f"r{newer.revision.revision_no}"
    assert seed_row["official"] == f"v{seed_release.release_no} · r{seed_release.revision_no}"
    assert table_row(calls, clone.scenario.scenario_id)["official"] == (
        f"v{seed_release.release_no + 1} · r{clone.revision.revision_no} · 최신"
    )


def test_a_revision_renamed_elsewhere_is_still_the_one_loaded_and_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """다른 세션이 고른 리비전의 이름을 바꿔도 「불러오기」·「공식으로 지정…」은 고른 리비전에
    걸린다.

    옛 카드 리비전 상자는 리비전명이 든 글자로 값을 주고받아, 이름이 바뀐 뒤 브라우저가 되보낸 옛
    글자를 Streamlit 1.63 이 **예외 없이** 첫 항목(최신 리비전)으로 되돌렸다 — r2 를 고르고 누른
    「불러오기」가 r3 을 올렸다(2026-10-22 AppTest 실측). 리비전 표의 고름은 행 id 로 초안에 남아
    이름과 상관없다. 그래서 예외 없음이 아니라 누른 회차에 실제로 걸린 리비전 id 를 잰다.
    """
    from capa_simulation.scenario_activation import ACTIVE_PERSISTED_REVISION_ID_KEY
    from capa_simulation.services.korean_particle import object_particle

    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    repository = DuckDBScenarioRepository(database_path)
    target = _clone_official(database_path, "이름 바꿀 시나리오", "RENAME-1")
    scenario_id = target.scenario.scenario_id
    picked = repository.save_revision(
        scenario_id,
        target.tables,
        target.preset,
        revision_name="고를 리비전",
        parent_revision_id=target.revision.revision_id,
    ).revision
    repository.save_revision(
        scenario_id,
        target.tables,
        target.preset,
        revision_name="최신 리비전",
        parent_revision_id=picked.revision_id,
    )

    def pick_then_rename(new_name: str) -> tuple[AppTest, ListBrowser]:
        calls = install_fake_list_grid(monkeypatch)
        app = AppTest.from_string(script, default_timeout=120)
        browser = ListBrowser(app, calls)
        _check_row(app, scenario_id)
        browser.run()
        # 올라와 있지 않은 시나리오는 처음 볼 때 최신 리비전을 고른다. 표는 최신이 먼저다.
        assert last(calls, REVISIONS_KEY)["picked"] == _revision_rows(calls)[0]["id"]
        browser.pick(scenario_id, picked.revision_id)
        assert _draft(app).picked == picked.revision_id
        current = next(
            revision.revision_name
            for revision in repository.list_revisions(scenario_id)
            if revision.revision_id == picked.revision_id
        )
        # 다른 세션이 고른 리비전의 이름을 바꾼다. 이 세션은 그 사이 다른 조작을 한 번 한다.
        repository.rename_revision(picked.revision_id, new_name, expected_name=current)
        browser.run()
        assert _draft(app).picked == picked.revision_id
        assert _revision_rows(calls)[1]["name"] == new_name, "표가 옛 이름을 보입니다."
        return app, browser

    app, browser = pick_then_rename("고른 뒤 바뀐 이름")
    app.button(key=f"{CARD_LOAD_KEY}_{scenario_id}").click()
    browser.run()
    assert app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY] == picked.revision_id
    assert any(
        item.value
        == f"이름 바꿀 시나리오 r{picked.revision_no}{object_particle(str(picked.revision_no))} "
        "불러왔습니다."
        for item in successes(app)
    ), [item.value for item in successes(app)]

    app, browser = pick_then_rename("두 번째로 바뀐 이름")
    app.button(key=f"{CARD_OFFICIAL_KEY}_{scenario_id}").click()
    browser.run()
    # 팝업은 대상 리비전을 이름으로도 적는다 — 사람 눈으로도 확인한다.
    assert any(
        f"r{picked.revision_no} · 두 번째로 바뀐 이름" in item.value for item in app.markdown
    ), [item.value for item in app.markdown]
    _official_button(app).click()
    browser.run()
    latest = repository.latest_official_release()
    assert latest is not None
    assert latest.revision_id == picked.revision_id


def test_a_pick_sent_with_the_press_is_the_revision_loaded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """리비전 줄을 누르고 바로 단추를 눌러도 그 리비전에 걸린다 — 단추 콜백이 출납을 먼저 접는다.
    고름이 트리거였으면 다음 누름에 덮여 옛 리비전을 올렸다."""
    from capa_simulation.scenario_activation import ACTIVE_PERSISTED_REVISION_ID_KEY

    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    repository = DuckDBScenarioRepository(database_path)
    target = _clone_official(database_path, "고를 시나리오", "PICK-A")
    scenario_id = target.scenario.scenario_id
    newest = repository.save_revision(
        scenario_id, target.tables, target.preset, revision_name="최신"
    ).revision
    assert newest.revision_id != target.revision.revision_id

    calls = install_fake_list_grid(monkeypatch)
    app = AppTest.from_string(script, default_timeout=120)
    browser = ListBrowser(app, calls)
    _check_row(app, scenario_id)
    browser.run()
    assert _draft(app).picked == newest.revision_id
    browser.prepared(
        REVISIONS_KEY, {"op": "pick", "owner": scenario_id, "id": target.revision.revision_id}
    )
    app.button(key=f"{CARD_LOAD_KEY}_{scenario_id}").click()
    browser.run()
    assert app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY] == target.revision.revision_id


def test_an_old_card_button_does_not_act_on_the_row_opened_since(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """왼쪽 줄을 누르고 바로 옛 카드 단추를 누르면 아무것도 하지 않고 알린다 — 불러오기에는 확인
    팝업이 없다. 단추 key 에 시나리오 id 를 실어 옛 단추의 콜백은 옛 시나리오를 인자로 받는다."""
    from capa_simulation.scenario_activation import ACTIVE_PERSISTED_REVISION_ID_KEY

    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    first = _clone_official(database_path, "먼저 연 시나리오", "OPEN-A").scenario.scenario_id
    second = _clone_official(database_path, "뒤에 연 시나리오", "OPEN-B").scenario.scenario_id

    calls = install_fake_list_grid(monkeypatch)
    app = AppTest.from_string(script, default_timeout=120)
    browser = ListBrowser(app, calls)
    _check_row(app, first)
    browser.run()
    active = app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY]
    browser.prepared(TABLE_KEY, {"op": "open", "id": second})
    app.button(key=f"{CARD_LOAD_KEY}_{first}").click()
    browser.run()
    assert _draft(app).opened == second
    assert app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY] == active
    assert OPENED_MOVED_MESSAGE in [str(item.value) for item in flashed(app, "error")]


def test_loading_over_unsaved_edits_needs_the_discard_check(tmp_path: Path) -> None:
    """미저장 편집이 있으면 「변경을 버리고 불러오기」를 체크해야 카드의 불러오기가 열린다.

    사이드바 팝업과 같은 확인 절차다. 단추 잠금은 화면의 약속이라 누른 회차의 콜백도 체크를
    다시 본다.
    """
    from capa_simulation.scenario_activation import (
        ACTIVE_PERSISTED_REVISION_ID_KEY,
        ACTIVE_PERSISTED_SESSION_REVISION_KEY,
    )

    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    other = _clone_official(database_path, "불러올 시나리오", "LOAD-1")

    app = AppTest.from_string(script, default_timeout=120)
    app.run()
    before = app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY]
    # 세션 편집 번호가 저장 리비전과 다르면 미저장 편집이 있는 것이다.
    app.session_state[ACTIVE_PERSISTED_SESSION_REVISION_KEY] = -1
    _check_row(app, other.scenario.scenario_id)
    app.run()
    assert not app.exception
    load_key = f"{CARD_LOAD_KEY}_{other.scenario.scenario_id}"
    assert app.button(key=load_key).disabled
    assert app.button(key=load_key).help == DISCARD_LOCK_HELP
    assert any("저장하지 않은 편집" in item.value for item in app.warning)

    app.checkbox(key=DISCARD_UNSAVED_KEY).check().run()
    assert not app.button(key=load_key).disabled
    assert not app.button(key=load_key).help
    app.button(key=load_key).click().run()
    assert not app.exception
    assert app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY] == other.revision.revision_id
    assert app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY] != before


def test_permanent_delete_says_what_goes_with_it_right_above_an_empty_box(
    tmp_path: Path,
) -> None:
    """영구 삭제 입력 바로 위에 함께 지워질 리비전 수·공식 발행 이력 수와 되돌릴 수 없다는 말이
    선다.

    입력 칸은 빈 칸으로 선다 — 시나리오명을 placeholder 로 깔면 이미 채워진 칸처럼 보였다.
    단추는 눈에 띄는 primary 다.
    """
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    repository = DuckDBScenarioRepository(database_path)
    doomed = _clone_official(database_path, "지울 시나리오", "DELETE-1")
    repository.save_revision(
        doomed.scenario.scenario_id, doomed.tables, doomed.preset, revision_name="둘째"
    )
    repository.publish_official_revision(
        doomed.scenario.scenario_id, doomed.revision.revision_id, release_name="잠깐 공식"
    )
    seed = repository.list_official_releases()[-1]
    repository.publish_official_revision(
        seed.scenario_id, seed.revision_id, release_name="다시 시드"
    )
    repository.archive_scenario(doomed.scenario.scenario_id)

    app = AppTest.from_string(script, default_timeout=120)
    app.session_state[SIDE_KEY] = SIDE_ARCHIVE
    app.run()
    assert not app.exception
    assert any(
        item.value
        == "영구 삭제하면 리비전 2개와 공식 발행 이력 1건이 함께 지워지고 되돌릴 수 없습니다."
        for item in app.warning
    ), [item.value for item in app.warning]
    assert not any("영구 삭제는 되돌릴 수 없습니다" in item.value for item in app.caption)
    confirm = app.text_input(key=DELETE_CONFIRM_KEY)
    assert confirm.label == "확인: 「지울 시나리오」를 그대로 입력하세요"
    assert confirm.placeholder == ""
    # 되돌릴 수 없는 단추는 주 동작(청록 primary)이 아니다 — 보조 단추이고, 이름을 맞게 적어
    # 누를 수 있을 때만 빨간 글자다(잠긴 단추가 빨가면 누를 수 있는 것처럼 보인다).
    execute = app.button(key=DELETE_BUTTON_KEY)
    assert execute.proto.type == "secondary"
    assert execute.disabled
    assert execute.help == DELETE_LOCK_HELP
    assert execute.label == DELETE_BUTTON_LABEL
    confirm.set_value("지울 시나리오")
    app.run()
    execute = app.button(key=DELETE_BUTTON_KEY)
    assert execute.proto.type == "secondary"
    assert not execute.disabled
    assert not execute.help
    assert execute.label == f":red[{DELETE_BUTTON_LABEL}]"
    assert execute.proto.icon == ":material/delete_forever:"


def test_the_clone_form_names_what_it_copies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """복제 폼 위 값 줄이 지금 올라와 있는 시나리오·리비전을 적고, 저장하지 않은 편집이 함께
    들어가면 그 표지 배지를 붙인다(설계 규칙 UI-TXT-04 — 값 · 표지만, 문장으로 풀지 않는다)."""
    import capa_simulation.components.scenario_management as scenario_management

    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    app = AppTest.from_string(script, default_timeout=120).run()
    assert not app.exception
    release = DuckDBScenarioRepository(database_path).latest_official_release()
    assert release is not None
    app.segmented_control(key=MODE_KEY).set_value(CLONE_MODE).run()
    assert not app.exception

    shown = f"복제 대상 · 「{literal_markdown(release.scenario_name)}」 r{release.revision_no}"
    assert shown in [item.value for item in app.caption], [item.value for item in app.caption]
    label = SimpleNamespace(scenario_name=release.scenario_name, revision_no=release.revision_no)
    monkeypatch.setattr(scenario_management, "active_scenario_label", lambda: label)
    monkeypatch.setattr(scenario_management, "has_unsaved_scenario_changes", lambda: True)
    assert scenario_management.clone_target_caption() == (
        f"{shown} · :orange-badge[미저장 편집 포함]"
    )
    # 원천 코드·원천명은 비워 둔다 — 원천명은 자동 갱신 주차 판정의 근거다.
    assert _clone_inputs(app)["원천 시뮬레이션 코드"] == ""
    assert _clone_inputs(app)["원천 시뮬레이션명"] == ""


def test_names_in_markdown_places_are_shown_as_typed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """보관 확인처럼 마크다운으로 그려지는 자리에 시나리오명을 글자 그대로 싣는다. 표 · 제목은
    부품이 textContent 로 넣어 그대로 싣는다.

    그대로면 「A~B~C」의 물결표는 취소선으로, 「$x$」는 수식으로 사라진다(AGENTS 9장).
    """

    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    name = "A~B~C $x$ *y*"
    target = _clone_official(database_path, name, "MARKDOWN-1")

    calls = install_fake_list_grid(monkeypatch)
    app = AppTest.from_string(script, default_timeout=120)
    _check_row(app, target.scenario.scenario_id)
    app.run()
    app.button(key=f"{ACTION_KEY}_archive").click().run()
    assert not app.exception
    escaped = literal_markdown(name)
    assert any(widget.label.startswith(escaped) for widget in app.checkbox)
    assert last(calls, REVISIONS_KEY)["title"] == name
    assert name in table_names(calls)


def test_the_right_panel_keeps_its_place_with_or_without_notices(tmp_path: Path) -> None:
    """맨 위 알림 · 결과 칸이 생기고 사라져도 오른쪽 칸 본문의 자리가 같다.

    보관함의 「되돌리기」·「영구 삭제」는 본문에서 `st.rerun()` 으로 회차를 끊는다. 다음 회차에
    알림이 생겨 key 있는 상자가 한 칸 밀리면 옛 자리에 흐린 사본이 남아 모드를 바꿔도 새로고침
    전까지 따라왔다(2026-10-22 사본 앱 이분 탐색 — 알림 · 상자 key · 본문 rerun 셋이 모두 있을
    때만). 알림은 늘 서 있는 칸 안에 그려 자리를 고정한다(AGENTS 9장).
    """
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    repository = DuckDBScenarioRepository(database_path)
    _clone_official(database_path, "보관 자리 하나", "PLACE-1")
    archived = _clone_official(database_path, "보관 자리 둘", "PLACE-2")
    repository.archive_scenario(archived.scenario.scenario_id)

    app = AppTest.from_string(script, default_timeout=120)
    app.session_state[SIDE_KEY] = SIDE_ARCHIVE
    app.run()
    assert not app.exception
    quiet = _place_of(app, LIST_SIDE.body_key)

    app.session_state[FLASH_KEY] = "보관 자리 둘을 목록으로 되돌렸습니다."
    app.session_state[FLASH_WARNING_KEY] = ("error", "맨 위 경고")
    app.run()
    assert not app.exception
    assert any("되돌렸습니다" in item.value for item in successes(app))
    assert any("맨 위 경고" in item.value for item in app.error)
    assert _place_of(app, LIST_SIDE.body_key) == quiet

    _side(app, SIDE_CHANGES)
    assert _place_of(app, LIST_SIDE.body_key) == quiet
    app.session_state[LIST_NOTICE_KEY] = ("error", "결과 칸")
    app.run()
    assert any("결과 칸" in item.value for item in app.error)
    assert _place_of(app, LIST_SIDE.body_key) == quiet


def test_a_result_notice_goes_to_the_alert_popup_when_its_panel_is_closed(tmp_path: Path) -> None:
    """결과 칸은 그 칸이 선 회차에만 그린다. 칸이 안 서면 맨 위 칸이 알림창 · Alarm 으로 꺼낸다 —
    사라진 위젯의 콜백도 돌아 「변경 저장」 을 누른 사이 칸이 옮겨도 저장은 된다. 알림이 그 칸을
    다시 열 때까지 잠자면 거부를 저장된 줄로 믿는다."""
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception

    app = AppTest.from_string(script, default_timeout=120)
    app.session_state[SIDE_KEY] = SIDE_DETAIL
    app.session_state[LIST_NOTICE_KEY] = ("error", "저장 거부 글")
    app.run()
    assert not app.exception
    assert not any("저장 거부 글" in item.value for item in app.error)
    assert [str(item.value) for item in flashed(app, "error")] == ["저장 거부 글"]
    assert LIST_NOTICE_KEY not in app.session_state

    app.session_state[SIDE_KEY] = SIDE_CHANGES
    app.session_state[CARD_NOTICE_KEY] = ("error", "카드 거부 글")
    app.run()
    assert not any("카드 거부 글" in item.value for item in app.error)
    assert [str(item.value) for item in flashed(app, "error")] == ["카드 거부 글"]


def test_the_history_and_archive_panels_stand_with_a_line_when_empty(tmp_path: Path) -> None:
    """보관본이 없으면 한 줄이 서고, 공식 발행 이력은 r 번호 · 공식버전명만이다.

    공식 발행 이력에 리비전명을 실으면 이름을 바꾸는 순간 과거 발행 행이 발행 당시와 다른 이름을
    보인다(2026-10-22 결정 — 이력 표는 지금처럼).
    """
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    app = AppTest.from_string(script, default_timeout=120)
    app.session_state[SIDE_KEY] = SIDE_ARCHIVE
    app.run()
    assert not app.exception
    assert "보관된 시나리오가 없습니다." in [str(item.value) for item in app.caption]
    _side(app, SIDE_HISTORY)
    frame = next(
        element.value for element in app.dataframe if "공식버전명" in element.value.columns
    )
    assert frame.columns.tolist() == ["공식버전", "시나리오", "리비전", "공식버전명", "지정시각"]
    assert len(frame) == 1


def test_the_tab_mounts_are_edit_tables_for_the_leave_hold() -> None:
    """떠나기 붙들기가 세 마운트를 편집 칸으로 본다 — 쓰는 중의 고침이 그 회차에 실린다. 표 모듈과
    세션 칸 이름이 같은지도 본다(탭 줄은 표 모듈을 부르지 않는다)."""
    from capa_simulation.components.page_tabs import EDIT_HOST_KEYS

    assert {TABLE_KEY, REVISIONS_KEY, CHANGES_KEY} <= set(EDIT_HOST_KEYS)
    assert LIST_SIDE.choice_key == SIDE_KEY and LIST_SIDE.next_key == SIDE_NEXT_KEY
    assert LIST_SIDE.reveal_key not in EDIT_HOST_KEYS


def _three_scenarios(tmp_path: Path) -> tuple[str, Path, list[str], list[str]]:
    """내장 시드 + 복제 둘. (스크립트, DB, 목록 차례의 id, 그 이름)."""
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    _clone_official(database_path, "고를 하나", "PICK-1")
    _clone_official(database_path, "고를 둘", "PICK-2")
    scenarios = DuckDBScenarioRepository(database_path).list_scenarios()
    return (
        script,
        database_path,
        [scenario.scenario_id for scenario in scenarios],
        [scenario.scenario_name for scenario in scenarios],
    )


def test_opening_another_row_keeps_the_unsaved_name_order_and_revision_edits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """다른 줄을 열어도 고침은 줄 id 로 남는다 — 리비전명 고침도(옛 카드는 시나리오를 바꾸면
    버렸다). 다시 그 시나리오를 열면 칸이 노랑으로 돌아오고, 「저장 전 변경」 은 시나리오별로 묶어
    다 보인다."""
    script, _, ids, names = _three_scenarios(tmp_path)
    app, browser, calls = _list_app(script, monkeypatch, side=SIDE_DETAIL)
    browser.open(ids[0])
    revision = _revision_rows(calls)[0]["id"]
    browser.rename_scenario(ids[2], "고친 이름")
    browser.rename_revision(revision, "고친 리비전명")
    assert _draft(app).opened == ids[0]

    browser.open(ids[1])
    assert _draft(app).opened == ids[1]
    assert table_names(calls) == [names[0], names[1], "고친 이름"]
    assert revision in _draft(app).revisions

    browser.move(ids[2], ids[0], order=tuple(ids))
    browser.open(ids[0])
    assert table_names(calls) == ["고친 이름", names[0], names[1]]
    (row,) = [row for row in _revision_rows(calls) if row["id"] == revision]
    assert (row["name"], row["saved"]) == ("고친 리비전명", row["saved"])
    assert row["saved"] != "고친 리비전명"

    _side(app, SIDE_CHANGES)
    data = last(calls, CHANGES_KEY)
    assert data["counts"]["scenario"] == 1 and data["counts"]["revision"] == 1
    assert [group["id"] for group in data["groups"]] == [ids[2], ids[0]]
    assert data["order"]["moved"] == 3
    # 칸 머리 알약 — 이름 둘 + 차례 묶음 하나.
    assert any("저장 전 변경 3건" in str(item.proto.body) for item in app.get("badge")) or any(
        "저장 전 변경 3건" in str(item.value) for item in app.markdown
    )


def test_opening_a_row_keeps_the_changes_panel_and_a_name_in_it_goes_to_the_detail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """「저장 전 변경」 을 보며 다른 줄을 눌러도 칸이 돌지 않는다(이름 여러 개를 고칠 때 칸 왕복이
    없다). 그 칸 안 이름 누름은 「상세」 로 간다. 보관함 · 발행 이력에서 줄을 누르면 「상세」 로
    간다."""
    script, _, ids, _ = _three_scenarios(tmp_path)
    app, browser, _ = _list_app(script, monkeypatch, side=SIDE_CHANGES)
    start = (
        app.session_state[LIST_SIDE.reveal_key] if LIST_SIDE.reveal_key in app.session_state else 0
    )
    browser.open(ids[1])
    assert app.segmented_control(key=SIDE_KEY).value == SIDE_CHANGES
    assert _draft(app).opened == ids[1]
    # 접혀 있으면 편다(`reveal`).
    assert app.session_state[LIST_SIDE.reveal_key] == start + 1

    browser.send(CHANGES_KEY, {"op": "open", "id": ids[2], "detail": True})
    assert app.segmented_control(key=SIDE_KEY).value == SIDE_DETAIL
    assert _draft(app).opened == ids[2]

    _side(app, SIDE_HISTORY)
    browser.open(ids[0])
    assert app.segmented_control(key=SIDE_KEY).value == SIDE_DETAIL


def test_opening_again_keeps_the_pick_and_a_gone_pick_is_seeded_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """같은 줄을 다시 열어도 고름이 남고, A → B → A 가 한 회차로 접혀 고름이 비어도 씨앗이 다시
    고른다 — 불러오기가 잠긴 채 서지 않는다. 고름이 그 시나리오의 리비전이 아니어도 다시 고른다."""
    script, _, ids, _ = _three_scenarios(tmp_path)
    app, browser, calls = _list_app(script, monkeypatch, side=SIDE_DETAIL)
    browser.open(ids[1])
    picked = _draft(app).picked
    assert picked is not None
    browser.open(ids[1])
    assert _draft(app).picked == picked

    browser.send(TABLE_KEY, {"op": "open", "id": ids[2]}, {"op": "open", "id": ids[1]})
    assert _draft(app).opened == ids[1]
    assert _draft(app).picked == _revision_rows(calls)[0]["id"]
    assert not app.button(key=f"{CARD_LOAD_KEY}_{ids[1]}").disabled

    app.session_state[DRAFT_KEY] = replace(_draft(app), picked="다른 시나리오의 리비전")
    browser.run()
    assert _draft(app).picked == _revision_rows(calls)[0]["id"]


def test_a_scenario_without_a_revision_stands_with_a_line_and_no_load_button(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """리비전이 없는 시나리오 — 표는 빈 채 서고 불러오기 · 공식 지정 없이 보관만 남는다."""
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    target = _clone_official(database_path, "리비전 없음", "NO-REV").scenario.scenario_id
    listing = DuckDBScenarioRepository.list_revisions

    def without(self: DuckDBScenarioRepository, scenario_id: str) -> Any:
        return [] if scenario_id == target else listing(self, scenario_id)

    monkeypatch.setattr(DuckDBScenarioRepository, "list_revisions", without)
    calls = install_fake_list_grid(monkeypatch)
    app = AppTest.from_string(script, default_timeout=120)
    _check_row(app, target)
    app.run()
    assert not app.exception
    assert last(calls, REVISIONS_KEY)["rows"] == []
    assert "이 시나리오에 저장된 리비전이 없습니다." in [str(item.value) for item in app.caption]
    labels = {button.label for button in app.button}
    assert "선택한 리비전 불러오기" not in labels and "보관…" in labels


def test_a_place_number_and_the_buttons_arrive_as_moves_and_one_save_writes_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """순서 칸 번호 · 끌기 · 위로 · 아래로 · 맨 위로는 브라우저에서 모두 `move` 다(`before` — 뒤에
    올 줄). 미저장 순서 고침으로 쌓이고 「변경 저장」 한 번으로 쓴다. 저장 차례로 돌아오면 고침이
    없다."""
    script, database_path, ids, names = _three_scenarios(tmp_path)
    app, browser, calls = _list_app(script, monkeypatch)
    order = tuple(ids)

    browser.move(ids[2], ids[0], order=order)
    assert table_names(calls) == [names[2], names[0], names[1]]
    assert table_row(calls, ids[2])["place"] == 3
    assert _counts(calls)["order"] == 3

    # 끝 — before 없음. 저장 차례로 돌아왔다.
    browser.move(ids[2], None, order=order)
    assert table_names(calls) == names
    assert _draft(app).order is None and "place" not in table_row(calls, ids[2])

    browser.move(ids[2], ids[1], order=order)
    assert table_ids(calls) == [ids[0], ids[2], ids[1]]
    _save(app)
    assert "누적 순서를 저장했습니다." in [item.value for item in successes(app)]
    stored = DuckDBScenarioRepository(database_path).list_scenarios()
    assert [scenario.scenario_id for scenario in stored] == [ids[0], ids[2], ids[1]]
    # 저장하면 고침이 비고 연 시나리오는 남는다.
    done = _draft(app)
    assert done.order is None and done.opened is not None and done.generation == 1


def test_a_stale_move_is_refused_alone_and_an_old_generation_edit_is_told(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """옮기기는 그린 저장 차례의 지문을 들고 온다 — 다르면 그 op 만 거절하고 알린다. 저장 사이에
    고친 것은 반영하지 않고 수를 세어 알린다(사라지는 고침을 말없이 버리지 않는다)."""
    script, database_path, ids, names = _three_scenarios(tmp_path)
    app, browser, calls = _list_app(script, monkeypatch)
    browser.send(
        TABLE_KEY,
        {"op": "move", "id": ids[2], "before": ids[0], "token": "다른 지문"},
        {"op": "name", "kind": "scenario", "id": ids[1], "text": "새 이름", "seen": names[1]},
    )
    assert table_ids(calls) == list(ids)
    assert _draft(app).scenarios == {ids[1]: NameEdit(names[1], "새 이름")}
    assert any("목록 차례가 바뀌어" in str(item.value) for item in flashed(app, "warning"))

    _save(app)
    old_base = "옛 세션:0"
    app.session_state["test_fake_scenario_list_event"] = (
        TABLE_KEY,
        {
            "mount": "m-old",
            "ops": [
                {
                    "seq": 1,
                    "at": 1,
                    "base": old_base,
                    "op": "name",
                    "kind": "scenario",
                    "id": ids[0],
                    "text": "버려질 이름",
                    "seen": names[0],
                }
            ],
        },
    )
    browser.run()
    browser.run()
    assert _draft(app).scenarios == {}
    assert any("저장 사이에 고친 1건" in str(item.value) for item in flashed(app, "warning"))
    stored = DuckDBScenarioRepository(database_path).list_scenarios()
    assert ids[0] in {item.scenario_id for item in stored}
    assert "버려질 이름" not in {item.scenario_name for item in stored}


def test_a_gone_rows_edit_is_dropped_and_told_on_that_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """고친 시나리오를 남이 보관 · 삭제하면 그 고침을 빼고 그 회차 알림창에 알린다(맨 위 알림 앞에서
    맞춘다 — 뒤에서 맞추면 다음 조작까지 숨는다). 이 세션이 한 보관은 알리지 않는다."""
    script, database_path, ids, _ = _three_scenarios(tmp_path)
    repository = DuckDBScenarioRepository(database_path)
    release = repository.latest_official_release()
    assert release is not None
    victim = next(item for item in ids if item != release.scenario_id)
    app, browser, _ = _list_app(script, monkeypatch)
    browser.rename_scenario(victim, "남이 보관할 줄")

    repository.archive_scenario(victim)
    browser.run()
    assert _draft(app).scenarios == {}
    assert any("고침 1건을 버렸습니다" in str(item.value) for item in flashed(app, "warning"))


def test_archiving_here_drops_its_edits_silently_and_keeps_the_order_edit_valid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """이 세션의 보관은 그 시나리오의 고침(리비전명 포함)을 말없이 빼고, 순서 고침의 본 차례를
    옮긴다 — 안 옮기면 「다른 곳에서 바뀌었습니다」 로 막히는데 거짓이다."""
    script, database_path, ids, names = _three_scenarios(tmp_path)
    repository = DuckDBScenarioRepository(database_path)
    release = repository.latest_official_release()
    assert release is not None
    victim = next(item for item in ids if item != release.scenario_id)
    rest = [item for item in ids if item != victim]
    app, browser, calls = _list_app(script, monkeypatch, side=SIDE_DETAIL)
    browser.open(victim)
    revision = _revision_rows(calls)[0]["id"]
    browser.rename_revision(revision, "보관될 리비전 이름")
    browser.rename_scenario(victim, "보관될 이름")
    browser.move(rest[1], rest[0], order=tuple(ids))

    app.button(key=f"{ACTION_KEY}_archive").click().run()
    assert not app.exception
    _check_archive(app)
    app.run()
    next(button for button in app.button if button.label == "보관 실행").click()
    browser.run()
    draft = _draft(app)
    assert draft.scenarios == {} and draft.revisions == {}
    assert draft.opened != victim
    assert not any("고침" in str(item.value) for item in flashed(app, "warning"))

    _side(app, SIDE_CHANGES)
    assert last(calls, CHANGES_KEY)["order"].get("problem") is None
    _save(app)
    stored = [item.scenario_id for item in repository.list_scenarios()]
    assert stored == [rest[1], rest[0]]
    assert names  # 합성 이름은 쓰지 않았다.


def test_a_list_save_with_one_refused_name_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """하나라도 거부되면 아무것도 쓰지 않고 행마다 까닭을 적는다. 이름 맞바꾸기는 된다. 막힘은 저장
    전에도 그 칸과 수 넷에 보인다."""
    script, database_path, ids, names = _three_scenarios(tmp_path)
    repository = DuckDBScenarioRepository(database_path)
    app, browser, calls = _list_app(script, monkeypatch)
    browser.rename_scenario(ids[0], names[1])
    browser.rename_scenario(ids[2], "새 이름")
    assert _counts(calls)["blocked"] == 1
    assert (
        table_row(calls, ids[0])["problem"]
        == "같은 이름의 시나리오가 이미 있습니다. 이름을 바꿔 저장하세요."
    )
    _save(app)

    (error,) = [item.value for item in app.error]
    assert error.startswith("저장하지 않았습니다 — 하나라도 막히면 아무것도 쓰지 않습니다.")
    assert f"1행 「{literal_markdown(names[1])}」" in error
    assert literal_markdown("같은 이름의 시나리오가 이미 있습니다") in error
    assert [scenario.scenario_name for scenario in repository.list_scenarios()] == names
    assert _counts(calls)["scenario"] == 2

    # 두 이름을 맞바꾸면 저장 뒤 이름이 겹치지 않아 된다.
    browser.rename_scenario(ids[1], names[0])
    assert _counts(calls)["blocked"] == 0
    _save(app)
    assert "시나리오명 3건을 저장했습니다." in [item.value for item in successes(app)]
    renamed = {
        scenario.scenario_id: scenario.scenario_name for scenario in repository.list_scenarios()
    }
    assert renamed == {ids[0]: names[1], ids[1]: names[0], ids[2]: "새 이름"}


def test_a_name_only_save_keeps_the_row_where_the_table_showed_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """순서를 한 번도 저장하지 않은 목록에서 아래 행의 이름만 고쳐 「변경 저장」 해도 그 행이
    맨 위로 가지 않는다 — 순서를 저장한 적 없는 행은 만든 시각 차례라(`list_order NULLS LAST,
    created_at DESC`) 이름 변경이 올리는 「최근 수정」을 따르지 않는다. 「최근 수정」 칸은 그대로
    오른다."""
    script, database_path, ids, names = _three_scenarios(tmp_path)
    repository = DuckDBScenarioRepository(database_path)
    before = {item.scenario_id: item.updated_at for item in repository.list_scenarios()}
    app, browser, calls = _list_app(script, monkeypatch)
    browser.rename_scenario(ids[2], "아래 새 이름")
    _save(app)

    assert "시나리오명 1건을 저장했습니다." in [item.value for item in successes(app)]
    assert [scenario.scenario_id for scenario in repository.list_scenarios()] == ids
    assert table_names(calls) == [names[0], names[1], "아래 새 이름"]
    after = {item.scenario_id: item.updated_at for item in repository.list_scenarios()}
    assert after[ids[0]] == before[ids[0]] and after[ids[1]] == before[ids[1]]
    assert after[ids[2]] > before[ids[2]]


def test_an_order_changed_elsewhere_refuses_the_order_and_keeps_the_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """순서를 고치는 사이 다른 곳에서 목록 차례가 바뀌면 순서는 쓰지 않는다(남의 차례를 덮지 않음).

    아무것도 쓰지 않고, 순서 고침만 버려 지금 차례로 표를 다시 세운다. 이름 고침은 행 id 로 남아
    다시 누르면 저장된다.
    """
    from capa_simulation.persistence.repository import SCENARIO_LIST_MOVED_MESSAGE

    script, database_path, ids, names = _three_scenarios(tmp_path)
    repository = DuckDBScenarioRepository(database_path)
    app, browser, calls = _list_app(script, monkeypatch)
    browser.rename_scenario(ids[0], "새 첫째")
    browser.move(ids[2], ids[0], order=tuple(ids))

    repository.reorder_scenarios([ids[1], ids[0], ids[2]])
    browser.run()
    # 화면은 이 세션이 고친 차례를 그대로 보이고, 막힘을 미리 보인다.
    assert table_names(calls) == [names[2], "새 첫째", names[1]]
    assert last(calls, CHANGES_KEY)["order"]["problem"] == SCENARIO_LIST_MOVED_MESSAGE
    _save(app)

    (error,) = [item.value for item in app.error]
    assert literal_markdown(SCENARIO_LIST_MOVED_MESSAGE) in error
    stored = repository.list_scenarios()
    assert [scenario.scenario_id for scenario in stored] == [ids[1], ids[0], ids[2]]
    assert [scenario.scenario_name for scenario in stored] == [names[1], names[0], names[2]]
    assert table_names(calls) == [names[1], "새 첫째", names[2]]
    assert _counts(calls) == {"scenario": 1, "order": 0, "revision": 0, "blocked": 0}

    _save(app)
    assert "시나리오명 1건을 저장했습니다." in [item.value for item in successes(app)]
    assert (
        next(
            scenario.scenario_name
            for scenario in repository.list_scenarios()
            if scenario.scenario_id == ids[0]
        )
        == "새 첫째"
    )


def test_an_unsaved_name_stays_on_its_scenario_when_another_session_reorders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """고침은 행 id 로 초안에 든다 — 다른 세션이 차례를 바꿔도 고친 이름은 그 시나리오에 붙는다."""
    script, database_path, ids, names = _three_scenarios(tmp_path)
    app, browser, calls = _list_app(script, monkeypatch)
    browser.rename_scenario(ids[0], "첫째 새 이름")

    DuckDBScenarioRepository(database_path).reorder_scenarios([ids[2], ids[1], ids[0]])
    browser.run()
    assert table_names(calls) == [names[2], names[1], "첫째 새 이름"]
    assert _draft(app).scenarios == {ids[0]: NameEdit(names[0], "첫째 새 이름")}


def test_revision_names_are_saved_with_the_list_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """리비전 표의 리비전명을 고쳐 「변경 저장」 한 곳에서 쓴다.

    공식으로 지정된 리비전도 고칠 수 있고 공식버전명은 그대로다(S4) — 고치는 동안 그 줄 곁 표지와
    풍선이 그 사실을 말한다. 올라와 있는 리비전이면 머리 띠 이름표도 바뀐다. 시나리오 「최근
    수정」은 오르지 않는다. 메모 · 저장일 · 부모는 값 줄이고(append-only — 이름표만 고친다) 표에는
    번호 · 이름 · 상태다.
    """
    from capa_simulation.scenario_activation import ACTIVE_SCENARIO_LABEL_KEY

    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    repository = DuckDBScenarioRepository(database_path)
    release = repository.latest_official_release()
    assert release is not None
    seed = repository.load_revision(release.revision_id)
    probe = repository.save_revision(
        seed.scenario.scenario_id,
        seed.tables,
        seed.preset,
        revision_name="probe save",
        parent_revision_id=release.revision_id,
        note="첫 줄\n둘째 줄",
    ).revision
    (before,) = repository.list_scenarios()

    app, browser, calls = _list_app(script, monkeypatch, side=SIDE_DETAIL)
    rows = _revision_rows(calls)
    assert [row["no"] for row in rows] == ["r2", "r1"]
    assert [row["parent"] for row in rows] == ["r1", ""]
    assert rows[0]["memo"] == "첫 줄 둘째 줄"
    assert [row["status"] for row in rows] == ["", f"공식 v{release.release_no} · 올라와 있음"]
    # 저장 단추는 「저장 전 변경」 칸에만 있다.
    assert "변경 저장" not in {button.label for button in app.button}

    browser.rename_revision(release.revision_id, "공식 리비전 새 이름")
    browser.rename_revision(probe.revision_id, "필터 저장")
    _side(app, SIDE_CHANGES)
    (group,) = last(calls, CHANGES_KEY)["groups"]
    lines = {line["id"]: line for line in group["lines"]}
    assert lines[release.revision_id]["mark"] == f"공식 v{release.release_no}"
    assert "공식버전명은 바뀌지 않습니다" in lines[release.revision_id]["note"]
    assert "mark" not in lines[probe.revision_id]
    _save(app)

    assert "리비전명 2건을 저장했습니다." in [item.value for item in successes(app)]
    names = {
        revision.revision_id: revision.revision_name
        for revision in repository.list_revisions(seed.scenario.scenario_id)
    }
    assert names == {release.revision_id: "공식 리비전 새 이름", probe.revision_id: "필터 저장"}
    latest = repository.latest_official_release()
    assert latest is not None and latest.release_name == release.release_name
    (after,) = repository.list_scenarios()
    assert after.updated_at == before.updated_at
    assert app.session_state[ACTIVE_SCENARIO_LABEL_KEY]["revision_name"] == "공식 리비전 새 이름"
    assert _counts(calls)["revision"] == 0


def test_a_revision_name_changed_elsewhere_refuses_the_whole_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """다른 사용자가 먼저 바꾼 리비전이 하나라도 있으면 아무 이름도 쓰지 않고 그 리비전을 적는다."""
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    repository = DuckDBScenarioRepository(database_path)
    release = repository.latest_official_release()
    assert release is not None
    seed = repository.load_revision(release.revision_id)
    probe = repository.save_revision(
        seed.scenario.scenario_id, seed.tables, seed.preset, revision_name="probe save"
    ).revision

    app, browser, _ = _list_app(script, monkeypatch, side=SIDE_DETAIL)
    browser.rename_revision(probe.revision_id, "내가 고친 이름")
    browser.rename_revision(release.revision_id, "같이 고친 이름")
    repository.rename_revision(probe.revision_id, "남이 고친 이름", expected_name="probe save")
    _side(app, SIDE_CHANGES)
    _save(app)

    (error,) = [item.value for item in app.error]
    assert f"r2 「{literal_markdown('내가 고친 이름')}」" in error
    assert literal_markdown("다른 사용자가 먼저 이름을 바꿨습니다(지금: 남이 고친 이름).") in error
    names = [
        revision.revision_name for revision in repository.list_revisions(seed.scenario.scenario_id)
    ]
    assert names == ["남이 고친 이름", seed.revision.revision_name]


def test_a_scenario_name_changed_elsewhere_is_not_overwritten_after_more_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """이름은 사용자가 그 칸을 고칠 때 **본** 이름과 대조한다(S6 비교 후 쓰기).

    다른 사용자가 먼저 바꾼 뒤 이 세션에서 회차가 더 돌아도(다른 줄 열기 등) 대조 기준은 처음
    본 이름이다. 마지막 회차에 다시 읽은 이름을 기준으로 삼으면 남의 변경을 알림 없이 덮는다
    (2026-10-22 리뷰 — 클릭 직전에만 끼운 시험은 이 길을 못 봤다). 그 칸에 미리 막힘을 보이고,
    거부되면 그 행만 지금 이름으로 다시 세워 보고 다시 고치게 한다.
    """
    script, database_path, ids, names = _three_scenarios(tmp_path)
    repository = DuckDBScenarioRepository(database_path)
    app, browser, calls = _list_app(script, monkeypatch)
    browser.rename_scenario(ids[1], "내가 바꾼 이름")
    repository.rename_scenario(ids[1], "남이 바꾼 이름")
    browser.run()
    browser.open(ids[0])
    assert _draft(app).opened == ids[0]
    row = table_row(calls, ids[1])
    assert row["name"] == "내가 바꾼 이름"
    assert row["problem"] == "다른 사용자가 먼저 이름을 바꿨습니다(지금: 남이 바꾼 이름)."
    assert _counts(calls)["blocked"] == 1
    # 표 아래 경고 상자는 없다 — 그 칸 · 풍선 · 막힘 수가 말한다.
    assert not any("먼저 이름을 바꿨습니다" in item.value for item in app.warning)

    _save(app)
    (error,) = [item.value for item in app.error]
    assert literal_markdown("다른 사용자가 먼저 이름을 바꿨습니다(지금: 남이 바꾼 이름).") in error
    stored = {
        scenario.scenario_id: scenario.scenario_name for scenario in repository.list_scenarios()
    }
    assert stored == {ids[0]: names[0], ids[1]: "남이 바꾼 이름", ids[2]: names[2]}
    # 그 행만 지금 이름으로 다시 선다. 연 시나리오는 남는다.
    assert "남이 바꾼 이름" in table_names(calls) and "내가 바꾼 이름" not in table_names(calls)
    assert _draft(app).opened == ids[0]
    assert _counts(calls) == {"scenario": 0, "order": 0, "revision": 0, "blocked": 0}

    # 지금 이름을 보고 다시 고치면 저장된다.
    browser.rename_scenario(ids[1], "내가 바꾼 이름")
    _save(app)
    assert "시나리오명 1건을 저장했습니다." in [item.value for item in successes(app)]
    stored = {
        scenario.scenario_id: scenario.scenario_name for scenario in repository.list_scenarios()
    }
    assert stored[ids[1]] == "내가 바꾼 이름"


def test_a_revision_name_changed_elsewhere_is_not_overwritten_after_more_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """리비전 표도 그 칸을 고칠 때 본 이름과 대조한다 — 남의 변경 뒤 다른 줄을 골라 회차가 더
    돌아도 남의 이름을 덮지 않는다(2026-10-22 리뷰). 리비전 고침은 다른 시나리오를 열어도 남아 그
    이름도 그대로 막힌다."""
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    repository = DuckDBScenarioRepository(database_path)
    release = repository.latest_official_release()
    assert release is not None
    seed = repository.load_revision(release.revision_id)
    scenario_id = seed.scenario.scenario_id
    probe = repository.save_revision(
        scenario_id, seed.tables, seed.preset, revision_name="probe save"
    ).revision

    app, browser, calls = _list_app(script, monkeypatch, side=SIDE_DETAIL)
    browser.rename_revision(probe.revision_id, "내가 고친 이름")
    repository.rename_revision(probe.revision_id, "남이 고친 이름", expected_name="probe save")
    browser.run()
    browser.pick(scenario_id, probe.revision_id)
    assert _draft(app).picked == probe.revision_id
    row = next(row for row in _revision_rows(calls) if row["id"] == probe.revision_id)
    assert row["problem"] == "다른 사용자가 먼저 이름을 바꿨습니다(지금: 남이 고친 이름)."
    assert not any("먼저 이름을 바꿨습니다" in item.value for item in app.warning)

    _side(app, SIDE_CHANGES)
    _save(app)
    (error,) = [item.value for item in app.error]
    assert f"r2 「{literal_markdown('내가 고친 이름')}」" in error
    assert literal_markdown("다른 사용자가 먼저 이름을 바꿨습니다(지금: 남이 고친 이름).") in error
    names = [revision.revision_name for revision in repository.list_revisions(scenario_id)]
    assert names == ["남이 고친 이름", seed.revision.revision_name]
    assert _draft(app).revisions == {}
    _side(app, SIDE_DETAIL)
    assert [row["name"] for row in _revision_rows(calls)] == names
    assert _draft(app).picked == probe.revision_id


def test_discard_all_clears_the_edits_keeps_the_open_row_and_raises_the_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """「모두 버리기」 는 확인 팝오버를 지나 고침 · 순서를 비우고 세대를 올린다 — 연 시나리오는
    남는다. 옛 화면에 닿은 둘째 누름은 세대가 달라 아무 일도 없다. 그 뒤 온 옛 세대 고침은 세어
    알린다."""
    script, _, ids, names = _three_scenarios(tmp_path)
    app, browser, calls = _list_app(script, monkeypatch)
    browser.rename_scenario(ids[1], "버릴 이름")
    browser.move(ids[2], ids[0], order=tuple(ids))
    base = draft_base(_draft(app))
    assert app.button(key=DISCARD_CONFIRM_KEY).label == "모두 버리기 확인"
    assert _place_of(app, DISCARD_POPOVER_KEY)

    app.button(key=DISCARD_CONFIRM_KEY).click().run()
    assert not app.exception
    done = _draft(app)
    assert done.scenarios == {} and done.order is None and done.opened is not None
    assert draft_base(done) != base
    assert table_names(calls) == names
    assert "저장하지 않은 이름 · 순서 고침을 모두 버렸습니다." in [
        str(item.value) for item in infos(app)
    ]
    assert last(calls, TABLE_KEY)["base"] == draft_base(done)


def test_the_panels_draw_one_mount_at_a_time_and_the_save_button_stays_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """오른쪽 칸은 고른 칸의 마운트만 그린다. 「변경 저장」 은 잠그지 않는다 — 출납이 묶음이라
    마지막 회차의 판정은 브라우저보다 늦다. 고친 것이 없을 때 누르면 그 곁에 「고친 것이 없습니다」
    를 알린다. 풍선은 없다 — 풍선이 떠 있는 채 남는 문제는 이동 단추가 부품 안으로 들어가며 함께
    사라졌다."""
    script, _, _, _ = _three_scenarios(tmp_path)
    calls = install_fake_list_grid(monkeypatch)
    app = AppTest.from_string(script, default_timeout=120).run()
    assert not app.exception
    assert drawn(calls, TABLE_KEY) and drawn(calls, REVISIONS_KEY)
    assert not drawn(calls, CHANGES_KEY)

    _side(app, SIDE_CHANGES)
    assert drawn(calls, CHANGES_KEY)
    save = app.button(key="scenario_list_save")
    assert not save.disabled and not save.help
    save.click().run()
    assert not app.exception
    assert "고친 것이 없습니다." in [str(item.value) for item in infos(app)]
    # 표 안 단추가 된 이동 단추는 위젯으로 서지 않는다.
    keys = {button.key for button in app.button}
    assert not keys & {"scenario_list_up", "scenario_list_down", "scenario_list_top"}
