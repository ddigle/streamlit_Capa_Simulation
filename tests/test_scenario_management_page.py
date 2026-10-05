# Purpose: 시나리오 관리 페이지의 폼·목록 작업·보관함·복제 저장·캐시 무효화를 AppTest 로 고정한다.

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from test_all_pages_render import _page_script

from capa_simulation.components.scenario_management import (
    ACTION_KEY,
    ARCHIVE_CONFIRM_KEY,
    ARCHIVED_EXPANDER_KEY,
    ARCHIVED_SELECT_KEY,
    DELETE_CONFIRM_KEY,
    FLASH_KEY,
    LIST_EDITOR_KEY,
    MODE_KEY,
)
from capa_simulation.persistence.cache import (
    clear_global_comparison_scenario_cache,
    load_global_comparison_scenario,
    load_scenario_snapshot,
)
from capa_simulation.persistence.models import ScenarioCreate, ScenarioSnapshot
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_state import VIRTUAL_PRODUCTS_KEY
from capa_simulation.services.virtual_product import VirtualProductRecord

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
    assert [tab.label for tab in app.main.tabs] == [
        ":material/database: 시나리오 관리",
        ":material/cloud_download: BigDataQuery 등록",
    ]
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
    app.session_state[LIST_EDITOR_KEY] = {
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


def test_archived_box_keeps_its_identity_when_the_flash_disappears(tmp_path: Path) -> None:
    """보관 알림이 사라지는 회차에도 「보관된 시나리오」 칸이 같은 블록 id 를 가진다.

    key 없는 칸은 알림이 빠져 자리가 밀리는 회차에 새로 마운트되어 접혔고, 이름을 적던 영구
    삭제 버튼이 가려졌다(2026-10-01 브라우저 실측). 브라우저는 펼침을 블록 id 로 기억하므로
    알림이 있든 없든 id 가 같고 비어 있지 않아야 한다.
    """
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    archived = _clone_official(database_path, "보관 대상", "ARCHIVE-1")
    DuckDBScenarioRepository(database_path).archive_scenario(archived.scenario.scenario_id)

    app = AppTest.from_string(script, default_timeout=120)
    app.session_state[FLASH_KEY] = "보관 대상을 보관했습니다."
    app.run()
    assert not app.exception
    assert any("보관했습니다" in item.value for item in app.success)
    box = app.main.get_by_key(ARCHIVED_EXPANDER_KEY)
    assert box.label == "보관된 시나리오 1건"
    flashed = box._block_id
    assert flashed

    app.run()
    assert not app.exception
    assert not any("보관했습니다" in item.value for item in app.success)
    assert app.main.get_by_key(ARCHIVED_EXPANDER_KEY)._block_id == flashed


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
    app.segmented_control(key=MODE_KEY).set_value("현재 활성 RQ 복제").run()
    assert not app.exception

    _fill_clone(app, "복제 A", "CLONE-A")
    assert any("복제 A을(를) 저장했습니다" in item.value for item in app.success)
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
    """빈 필수 칸은 **한 번에** 모두 알린다. 한 칸씩 알리면 세 번 눌러야 했다(2026-10-05 E2E)."""
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    app = AppTest.from_string(script, default_timeout=120).run()
    app.segmented_control(key=MODE_KEY).set_value("현재 활성 RQ 복제").run()
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
    """「신규 시나리오 저장」(현재 활성 RQ 복제)도 가상 제품 이력을 초기 리비전에 남긴다.

    복제는 가상 제품의 복제 행이 든 활성 RQ 를 그대로 옮기면서 그 출처만 버렸다. 리비전 저장과
    같은 확인 문장을 저장 알림에 붙인다.
    """
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    app = AppTest.from_string(script, default_timeout=120).run()
    assert not app.exception
    app.segmented_control(key=MODE_KEY).set_value("현재 활성 RQ 복제").run()
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
        for item in app.success
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


def test_revision_save_keeps_the_session_virtual_products(tmp_path: Path) -> None:
    """이 페이지의 「새 리비전 저장」은 처음부터 이력을 넘겼다. 공용 도우미로 옮긴 뒤에도 같다."""
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    app = AppTest.from_string(script, default_timeout=120).run()
    assert not app.exception
    app.segmented_control(key=MODE_KEY).set_value("리비전 저장").run()
    assert not app.exception
    app.session_state[VIRTUAL_PRODUCTS_KEY] = (
        VirtualProductRecord(
            product="DEMO_VIRTUAL",
            stack="8H",
            source_product="DEMO_SOURCE",
            source_stack="8H",
        ),
    )

    next(widget for widget in app.text_input if widget.label == "새 리비전명").set_value(
        "가상 제품 포함"
    )
    next(button for button in app.button if button.label == "새 리비전 저장").click()
    app.run()
    assert not app.exception

    repository = DuckDBScenarioRepository(database_path)
    (saved,) = [
        scenario for scenario in repository.list_scenarios() if scenario.active_revision_no == 2
    ]
    assert any(
        item.value
        == (
            "새 리비전 r2를 저장했습니다. 가상 제품 1건이 포함되어 있습니다. "
            "실적과 대조할 수 없으므로 공식버전으로 발행하기 전에 확인하세요."
        )
        for item in app.success
    )
    assert repository.list_virtual_products(saved.active_revision_id).to_dict("records") == [
        {
            "제품정보": "DEMO_VIRTUAL",
            "Stack": "8H",
            "원본 제품정보": "DEMO_SOURCE",
            "원본 Stack": "8H",
        }
    ]


def _check_row(app: AppTest, database_path: Path, scenario_id: str) -> None:
    """목록 표에서 그 시나리오 한 건만 체크한다. 표의 행 차례는 `list_scenarios()` 차례다."""
    order = [
        scenario.scenario_id
        for scenario in DuckDBScenarioRepository(database_path).list_scenarios()
    ]
    app.session_state[LIST_EDITOR_KEY] = {
        "edited_rows": {order.index(scenario_id): {"선택": True}},
        "added_rows": [],
        "deleted_rows": [],
    }


def test_rename_refreshes_the_cached_snapshot_name(tmp_path: Path) -> None:
    """이름을 바꾸면 캐시된 리비전 스냅샷도 새 이름을 돌려준다.

    스냅샷 payload 는 시나리오 메타데이터를 함께 담는다. 비우지 않으면 그 리비전에서 파생한
    시나리오의 `source_simulation_name` 과 출처 메모에 옛 이름이 남는다.
    """
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    (summary,) = DuckDBScenarioRepository(database_path).list_scenarios()
    revision_id = summary.active_revision_id
    cached = load_scenario_snapshot(str(database_path), revision_id)
    assert cached.scenario.scenario_name == summary.scenario_name

    app = AppTest.from_string(script, default_timeout=120)
    _check_row(app, database_path, summary.scenario_id)
    app.run()
    app.session_state[ACTION_KEY] = "rename"
    app.run()
    assert not app.exception
    next(widget for widget in app.text_input if widget.label == "새 시나리오명").set_value(
        "이름 바꾼 시나리오"
    )
    next(button for button in app.button if button.label == "이름 저장").click()
    app.run()
    assert not app.exception

    assert any("이름 바꾼 시나리오 으로 변경했습니다" in item.value for item in app.success)
    refreshed = load_scenario_snapshot(str(database_path), revision_id)
    assert refreshed.scenario.scenario_name == "이름 바꾼 시나리오"


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
    _check_row(app, database_path, target_id)
    app.run()
    app.session_state[ACTION_KEY] = "archive"
    app.run()
    assert not app.exception
    next(widget for widget in app.checkbox if widget.key == ARCHIVE_CONFIRM_KEY).check()
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
    app.session_state[ARCHIVED_SELECT_KEY] = target_id
    app.run()
    assert not app.exception
    app.text_input(key=DELETE_CONFIRM_KEY).set_value("비교 대상")
    app.run()
    next(button for button in app.button if button.label == "영구 삭제 실행").click()
    app.run()
    assert not app.exception

    assert target_id not in {
        scenario.scenario_id for scenario in repository.list_scenarios(include_archived=True)
    }
    assert load_global_comparison_scenario(database).scenario_id is None
