# Purpose: 시나리오 관리 페이지의 목록·리비전 편집표·공식 지정 팝업·보관함·복제를 AppTest 로 잰다.

from pathlib import Path
from typing import Any, NoReturn
from uuid import uuid4

import duckdb
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Button, Expander, Status
from streamlit.testing.v1.errors import AppTestError
from test_all_pages_render import _page_script
from widget_browser import BrowserTables

from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.pick_edit_table import (
    ShownTable,
    TableDraft,
    draft_session_key,
    shown_session_key,
)
from capa_simulation.components.scenario_management import (
    ACTION_KEY,
    ARCHIVE_CONFIRM_KEY,
    ARCHIVED_EXPANDER_KEY,
    ARCHIVED_SELECT_KEY,
    CLONE_MODE,
    DELETE_CONFIRM_KEY,
    DISCARD_UNSAVED_KEY,
    FLASH_KEY,
    HISTORY_EXPANDER_KEY,
    LIST_EDITOR_KEY,
    MODE_KEY,
    OFFICIAL_DIALOG_KEY,
    REVISION_EDITOR_KEY,
    REVISION_SAVE_GUIDE,
    official_confirm_key,
)
from capa_simulation.persistence.cache import (
    clear_global_comparison_scenario_cache,
    load_global_comparison_scenario,
    load_scenario_snapshot,
)
from capa_simulation.persistence.models import ScenarioCreate, ScenarioSnapshot
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_state import ACTIVE_SCENARIO_KEY, VIRTUAL_PRODUCTS_KEY
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
    # BigDataQuery 등록 폼. 시나리오 관리 탭의 폼(복제 저장과 공식 지정 팝업)은 탭 안의 작업
    # 선택(segmented control)과 고른 시나리오에 따라 그려지므로 여기 없다. 표시순서 관리는
    # Admin Area 로 옮겼다.
    assert {"조회할 시뮬레이션 코드"} <= labels
    assert [tab.label for tab in app.main.tabs] == [
        ":material/database: 시나리오 관리",
        ":material/cloud_download: BigDataQuery 등록",
        ":material/autorenew: 자동 갱신",
    ]
    # 자동 갱신 설정 폼도 같은 rerun 에 선다.
    assert "시뮬레이션명 키워드" in labels
    assert "설정 저장" in {button.label for button in app.button}
    # 1단계 조회 폼과 2단계 등록 폼이 한 rerun 에 함께 있어야 탭을 오갈 때 값이 남는다.
    assert {"시작일", "종료일"} <= {widget.label for widget in app.date_input}
    assert "시뮬레이션 코드 조회" in {button.label for button in app.button}


def test_list_management_acts_on_the_checked_scenario(
    seeded_databases: tuple[Path, Path],
) -> None:
    """체크한 한 건에 대해서만 카드가 열린다. 표 위 작업 줄은 고친 것이 있을 때만 저장이 열린다."""
    database_path, equipment_path = seeded_databases
    script = _page_script(PAGE_PATH, database_path, equipment_path)

    app = AppTest.from_string(script, default_timeout=120).run()
    assert not app.exception
    save = app.button(key="scenario_list_save")
    assert save.label == "변경 저장" and save.disabled
    # 고른 것이 없으면 카드가 없다.
    assert "보관…" not in {button.label for button in app.button}

    # 표의 체크 한 번 — 브라우저가 보내는 편집표 상태를 그대로 보낸다.
    app = AppTest.from_string(script, default_timeout=120)
    tables = BrowserTables(app)
    tables.run()
    tables.edit(_shown_key(app, LIST_EDITOR_KEY), 0, "선택", True)
    tables.run()

    assert not app.exception
    labels = {button.label for button in app.button}
    assert {"선택한 리비전 불러오기", "공식으로 지정…", "이름 저장", "보관…"} <= labels

    app.session_state["scenario_list_action"] = "archive"
    app.run()

    assert not app.exception
    # 첫 행은 내장 시드 — 지금 최신 공식버전의 시나리오다. 체크·단추 대신 보관할 수 없다는
    # 안내만 선다.
    assert any("보관할 수 없습니다" in item.value for item in app.info)
    assert "보관합니다" not in "".join(widget.label for widget in app.checkbox)
    assert "보관 실행" not in {button.label for button in app.button}

    # 공식이 아닌 시나리오는 보관할 수 있다. 되돌릴 수 있으므로 확인이 체크박스 한 번이다.
    other = _clone_official(database_path, "보관해 볼 시나리오", "ARCHIVE-TRY")
    app = AppTest.from_string(script, default_timeout=120)
    _check_row(app, other.scenario.scenario_id)
    app.run()
    app.button(key=f"{ACTION_KEY}_archive").click().run()

    assert not app.exception
    assert not any("보관할 수 없습니다" in item.value for item in app.info)
    assert "보관합니다" in "".join(widget.label for widget in app.checkbox)
    execute = next(button for button in app.button if button.label == "보관 실행")
    assert execute.disabled


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
    assert any("다른 프로그램이 파일을 열어 두었습니다" in error.value for error in app.error)
    # 시나리오 관리 탭은 목록을 못 읽으면 작업 선택 앞에서 멈춘다.
    assert "시나리오 작업" not in {widget.label for widget in app.segmented_control}
    assert [tab.label for tab in app.main.tabs] == [
        ":material/database: 시나리오 관리",
        ":material/cloud_download: BigDataQuery 등록",
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
    assert isinstance(box, (Expander, Status))
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
    app.segmented_control(key=MODE_KEY).set_value(CLONE_MODE).run()
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
    app.segmented_control(key=MODE_KEY).set_value(CLONE_MODE).run()
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
    """「신규 시나리오 저장」(지금 편집본 복제)도 가상 제품 이력을 초기 리비전에 남긴다.

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


def test_the_page_has_no_revision_save_mode_and_points_to_the_sidebar(tmp_path: Path) -> None:
    """새 리비전 저장은 사이드바 팝업 한 곳이다(2026-10-22 사용자 결정 S8).

    작업 선택에 「리비전 저장」이 없고, 그 자리 바로 아래 한 줄이 사이드바 팝업으로 안내한다. 예전
    세션에 남은 옛 모드 값은 위젯 앞에서 버려 첫 모드로 선다.
    """
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    app = AppTest.from_string(script, default_timeout=120)
    app.session_state[MODE_KEY] = "리비전 저장"
    app.run()

    assert not app.exception
    mode = app.segmented_control(key=MODE_KEY)
    assert list(mode.options) == ["목록 관리", "지금 편집본 복제", "월 머지", "연도 Shift"]
    assert mode.value == "목록 관리"
    assert REVISION_SAVE_GUIDE in [item.value for item in app.caption]


def test_clone_refuses_an_edit_that_breaks_the_calculation(tmp_path: Path) -> None:
    """감사 D3: 리비전 저장에서 막히는 편집은 「지금 편집본 복제」로도 저장되지 않는다.

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
    """「지금 편집본 복제」의 초기 리비전도 올라와 있는 리비전의 이력을 물려받는다.

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
    assert f"가상 제품 상속 복제를 저장했습니다. {notice}" in [item.value for item in app.success]
    repository = DuckDBScenarioRepository(database_path)
    clone = next(
        item for item in repository.list_scenarios() if item.scenario_name == "가상 제품 상속 복제"
    )
    assert _history_products(repository, clone.active_revision_id) == ["DEMO_VIRTUAL_B"]


def _check_row(app: AppTest, scenario_id: str) -> None:
    """목록 표에서 그 시나리오 한 건을 고른 상태로 둔다 — 고름은 표 초안의 `picked` 다(행 id)."""
    app.session_state[draft_session_key(LIST_EDITOR_KEY)] = TableDraft(picked=scenario_id)


def _shown_key(app: AppTest, key: str) -> str:
    """지난 회차에 그린 편집표의 위젯 key — 칸 편집을 보낼 곳."""
    return str(app.session_state[shown_session_key(key)].widget_key)


def _draft(app: AppTest, key: str) -> TableDraft:
    draft = app.session_state[draft_session_key(key)]
    assert isinstance(draft, TableDraft)
    return draft


def _caption_with(app: AppTest, text: str) -> str:
    return next(item.value for item in app.caption if text in item.value)


def test_rename_refreshes_the_cached_snapshot_name(tmp_path: Path) -> None:
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

    app = AppTest.from_string(script, default_timeout=120)
    tables = BrowserTables(app)
    tables.run()
    tables.edit(_shown_key(app, LIST_EDITOR_KEY), 0, "시나리오명", "  이름 바꾼 시나리오 ")
    tables.run()
    assert not app.exception
    assert _caption_with(app, "고친 것").endswith("고친 것: 이름 1 · 순서 0")
    assert not app.button(key="scenario_list_save").disabled
    app.button(key="scenario_list_save").click()
    tables.run()
    assert not app.exception

    assert "시나리오명 1건을 저장했습니다." in [item.value for item in app.success]
    refreshed = load_scenario_snapshot(str(database_path), revision_id)
    assert refreshed.scenario.scenario_name == "이름 바꾼 시나리오"
    assert _list_frame(app).index.tolist() == ["이름 바꾼 시나리오"]
    assert _caption_with(app, "고친 것").endswith("고친 것: 이름 0 · 순서 0")
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


def test_the_archived_box_shows_what_the_next_restore_and_delete_act_on(tmp_path: Path) -> None:
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
    click("영구 삭제 실행")
    remaining = browser.options()
    assert doomed not in remaining
    assert len(remaining) == 1
    assert browser.last_set_value
    assert browser.wire == remaining[0] == name_of(app.session_state[ARCHIVED_SELECT_KEY])
    confirm = app.text_input(key=DELETE_CONFIRM_KEY)
    assert confirm.proto.set_value
    assert confirm.value == ""

    # 다음 「되돌리기」 는 보이던 것을 되돌린다.
    click("scenario_archived_restore")
    assert status_of(remaining[0]) == "ACTIVE"


OFFICIAL_BUTTON = "선택 리비전을 공식버전으로 지정"
VIRTUAL_CONFIRM_LABEL = "가상 제품이 포함된 것을 확인했습니다"


def _open_official(app: AppTest, scenario_id: str, revision_id: str) -> None:
    """목록에서 그 시나리오를, 리비전 표에서 리비전을 고른 뒤 「공식으로 지정…」 팝업을 연다."""
    _check_row(app, scenario_id)
    app.run()
    app.session_state[draft_session_key(REVISION_EDITOR_KEY)] = TableDraft(picked=revision_id)
    app.run()
    app.button(key=f"{ACTION_KEY}_official").click().run()
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
        "이 리비전에는 가상 제품 1건이 포함되어 있습니다(DEMO_VIRTUAL · 8H). "
        "실적과 대조할 수 없는 값입니다. 그대로 공식버전으로 지정할까요?"
    ) in [item.value for item in app.warning]
    assert _official_button(app).disabled

    # 잠긴 버튼은 누를 수 없다(AppTest 도 브라우저처럼 거절한다). 발행 이력은 그대로다.
    with pytest.raises(AppTestError):
        _official_button(app).click()
    assert repository.count_official_releases(saved.scenario.scenario_id) == 1

    app.checkbox(key=official_confirm_key(revision_id)).check()
    app.run()
    assert not app.exception
    assert not _official_button(app).disabled

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
    assert any(item.value.startswith("공식 v2 · ") for item in app.success)
    # 지정하면 팝업이 닫힌다.
    assert OFFICIAL_DIALOG_KEY not in app.session_state


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
    assert any("지금 공식과 같은 리비전입니다" in item.value for item in app.info)
    assert not any("가상 제품" in item.value for item in app.warning)
    assert VIRTUAL_CONFIRM_LABEL not in {widget.label for widget in app.checkbox}
    assert not _official_button(app).disabled

    _official_button(app).click()
    app.run()
    assert not app.exception

    latest = repository.latest_official_release()
    assert latest is not None and latest.release_no == 2
    assert latest.revision_id == release.revision_id
    assert any(item.value.startswith("공식 v2 · ") for item in app.success)


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
    """P1·P3 — 소요대수에 들지 않은 수요가 있는 리비전도 지정은 되지만, 지정한 자리에서 건수를 본다.

    발행 검사가 경고를 돌려줘도 화면이 성공 문구만 띄우면 지정한 사람은 확보율이 높게 나온
    리비전을 모두의 첫 화면으로 올린 줄 모른다.
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
    assert any(item.value.startswith("공식 v2 · ") for item in app.success)
    assert any("부하량에서 빠진 계획" in item.value for item in app.warning), [
        item.value for item in app.warning
    ]


def test_the_card_follows_a_revision_loaded_from_the_sidebar_popup(tmp_path: Path) -> None:
    """카드 리비전 표의 고름은 올라와 있는 리비전이 바뀌면 그 리비전으로 옮긴다(2026-10-11 리뷰).

    사이드바 시나리오 팝업의 불러오기는 프래그먼트 실행이라 이 페이지의 위젯 값이 버려지지 않는다.
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
    second = repository.save_revision(
        official.scenario.scenario_id,
        official.tables,
        official.preset,
        revision_name="두 번째",
    )
    app = AppTest.from_string(script, default_timeout=120)
    tables = BrowserTables(app)
    _check_row(app, official.scenario.scenario_id)
    tables.run()
    assert not app.exception
    assert _draft(app, REVISION_EDITOR_KEY).picked == release.revision_id

    # 사이드바 팝업에서 두 번째 리비전을 불러온 것과 같다 — 이 페이지의 위젯 값은 남아 있다.
    app.session_state["active_persisted_revision_id"] = second.revision.revision_id
    tables.run()
    assert not app.exception
    assert _draft(app, REVISION_EDITOR_KEY).picked == second.revision.revision_id

    # 올라와 있는 리비전이 그대로인 동안 사용자가 고른 리비전은 다음 회차에도 남는다. 표는 최신이
    # 먼저라 공식 리비전(r1)은 둘째 줄이다.
    tables.edit(_shown_key(app, REVISION_EDITOR_KEY), 1, "고름", True)
    tables.run()
    tables.run()
    assert _draft(app, REVISION_EDITOR_KEY).picked == release.revision_id

    # 올라와 있는 것이 다른 시나리오로 갔다가 마지막으로 씨앗을 넣은 리비전으로 돌아와도 표가
    # 따라온다 — 씨앗 기록이 남아 있으면 「같은 씨앗」으로 읽혀 사용자가 고른 옛 리비전에
    # 머물렀다(2026-10-11 재검증).
    app.session_state["active_persisted_scenario_id"] = "elsewhere-scenario"
    app.session_state["active_persisted_revision_id"] = "elsewhere-revision"
    tables.run()
    assert not app.exception
    app.session_state["active_persisted_scenario_id"] = official.scenario.scenario_id
    app.session_state["active_persisted_revision_id"] = second.revision.revision_id
    tables.run()
    assert not app.exception
    assert _draft(app, REVISION_EDITOR_KEY).picked == second.revision.revision_id


def test_a_picked_bigdataquery_row_keeps_its_form_after_the_list_order_is_saved(
    tmp_path: Path,
) -> None:
    """첫 탭의 「변경 저장」이 BigDataQuery 등록 폼 글자를 버리지 않는다.

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
    app.session_state[draft_session_key(LIST_EDITOR_KEY)] = TableDraft(
        order=tuple(reversed(stored)), order_base=tuple(stored)
    )
    app.run()
    assert not app.exception
    assert app.text_input(key=FORM_CODE_KEY).value == "DEMO-A-001"

    app.button(key="scenario_list_save").click().run()

    assert not app.exception
    assert "누적 순서를 저장했습니다." in [item.value for item in app.success]
    assert app.text_input(key=FORM_CODE_KEY).value == "DEMO-A-001"
    assert app.text_input(key=FORM_SCENARIO_NAME_KEY).value == "알파 시뮬 (DEMO-A-001)"


def _list_frame(app: AppTest) -> pd.DataFrame:
    """목록 편집표(첫 탭의 시나리오 표)를 시나리오명 → 행으로 읽는다."""
    for element in app.dataframe:
        frame: pd.DataFrame = element.value
        if "시나리오명" in frame.columns and "최신 리비전" in frame.columns:
            return frame.set_index("시나리오명")
    raise AssertionError("시나리오 목록 표가 없습니다.")


def test_the_list_names_the_latest_revision_and_which_revision_is_official(
    tmp_path: Path,
) -> None:
    """「최신 리비전」은 마지막으로 저장한 리비전이고, 공식 칸은 공식 리비전 번호를 함께 적는다.

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

    app = AppTest.from_string(script, default_timeout=120).run()
    assert not app.exception
    table = _list_frame(app)
    assert "활성 리비전" not in table.columns
    seed_row = table.loc[seed.scenario.scenario_name]
    assert seed_row["최신 리비전"] == f"r{newer.revision.revision_no}"
    assert seed_row["공식버전"] == f"v{seed_release.release_no} · r{seed_release.revision_no}"
    assert table.loc["공식 복제"]["공식버전"] == (
        f"v{seed_release.release_no + 1} · r{clone.revision.revision_no} · 최신"
    )


def test_a_revision_renamed_elsewhere_is_still_the_one_loaded_and_published(
    tmp_path: Path,
) -> None:
    """다른 세션이 고른 리비전의 이름을 바꿔도 「불러오기」·「공식으로 지정…」은 고른 리비전에
    걸린다.

    옛 카드 리비전 상자는 리비전명이 든 글자로 값을 주고받아, 이름이 바뀐 뒤 브라우저가 되보낸 옛
    글자를 Streamlit 1.63 이 **예외 없이** 첫 항목(최신 리비전)으로 되돌렸다 — r2 를 고르고 누른
    「불러오기」가 r3 을 올렸다(2026-10-22 AppTest 실측). 리비전 표의 고름은 행 id 로 초안에 남아
    이름과 상관없다. 그래서 예외 없음이 아니라 누른 회차에 실제로 걸린 리비전 id 를 잰다. 브라우저의
    칸 편집은 `BrowserTables` 가 들고 다닌다.
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

    def pick_then_rename(new_name: str) -> tuple[AppTest, BrowserTables]:
        app = AppTest.from_string(script, default_timeout=120)
        tables = BrowserTables(app)
        _check_row(app, scenario_id)
        tables.run()
        assert not app.exception
        # 올라와 있지 않은 시나리오는 처음 볼 때 최신 리비전을 고른다. 표는 최신이 먼저다.
        frame = _revision_frame(app)
        assert frame["고름"].tolist() == [True, False, False]
        tables.edit(_shown_key(app, REVISION_EDITOR_KEY), 1, "고름", True)
        tables.run()
        assert _draft(app, REVISION_EDITOR_KEY).picked == picked.revision_id
        current = next(
            revision.revision_name
            for revision in repository.list_revisions(scenario_id)
            if revision.revision_id == picked.revision_id
        )
        # 다른 세션이 고른 리비전의 이름을 바꾼다. 이 세션은 그 사이 다른 조작을 한 번 한다.
        repository.rename_revision(picked.revision_id, new_name, expected_name=current)
        tables.run()
        assert not app.exception
        assert _draft(app, REVISION_EDITOR_KEY).picked == picked.revision_id
        assert _revision_frame(app)["리비전명"].tolist()[1] == new_name, "표가 옛 이름을 보입니다."
        return app, tables

    app, tables = pick_then_rename("고른 뒤 바뀐 이름")
    app.button(key="scenario_card_load").click()
    tables.run()
    assert not app.exception
    assert app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY] == picked.revision_id
    assert any(
        item.value
        == f"이름 바꿀 시나리오 r{picked.revision_no}{object_particle(str(picked.revision_no))} "
        "불러왔습니다."
        for item in app.success
    ), [item.value for item in app.success]

    app, tables = pick_then_rename("두 번째로 바뀐 이름")
    app.button(key=f"{ACTION_KEY}_official").click()
    tables.run()
    assert not app.exception
    # 팝업은 대상 리비전을 이름으로도 적는다 — 사람 눈으로도 확인한다.
    assert any(
        f"r{picked.revision_no} · 두 번째로 바뀐 이름" in item.value for item in app.markdown
    ), [item.value for item in app.markdown]
    _official_button(app).click()
    tables.run()
    assert not app.exception
    latest = repository.latest_official_release()
    assert latest is not None
    assert latest.revision_id == picked.revision_id


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
    assert app.button(key="scenario_card_load").disabled
    assert any("저장하지 않은 편집" in item.value for item in app.warning)

    app.checkbox(key=DISCARD_UNSAVED_KEY).check().run()
    assert not app.button(key="scenario_card_load").disabled
    app.button(key="scenario_card_load").click().run()
    assert not app.exception
    assert app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY] == other.revision.revision_id
    assert app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY] != before


def _revision_frame(app: AppTest) -> pd.DataFrame:
    """고른 시나리오 카드의 리비전 편집표."""
    for element in app.dataframe:
        frame: pd.DataFrame = element.value
        if "고름" in frame.columns:
            return frame
    raise AssertionError("리비전 표가 없습니다.")


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

    app = AppTest.from_string(script, default_timeout=120).run()
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
    execute = next(button for button in app.button if button.label == "영구 삭제 실행")
    assert execute.proto.type == "primary"
    assert execute.disabled


def test_the_clone_form_names_what_it_copies(tmp_path: Path) -> None:
    """복제 폼 위에 지금 올라와 있는 시나리오·리비전과 저장하지 않은 편집이 들어가는지를 적는다."""
    from capa_simulation.services.korean_particle import object_particle

    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    app = AppTest.from_string(script, default_timeout=120).run()
    assert not app.exception
    release = DuckDBScenarioRepository(database_path).latest_official_release()
    assert release is not None
    app.segmented_control(key=MODE_KEY).set_value(CLONE_MODE).run()
    assert not app.exception

    expected = (
        f"지금 올라와 있는 「{release.scenario_name}」 r{release.revision_no}"
        f"{object_particle(str(release.revision_no))} 새 시나리오로 복제합니다 — "
        "저장하지 않은 편집은 없습니다."
    )
    shown = expected.replace(release.scenario_name, literal_markdown(release.scenario_name))
    assert shown in [item.value for item in app.caption], [item.value for item in app.caption]
    # 원천 코드·원천명은 비워 둔다 — 원천명은 자동 갱신 주차 판정의 근거다.
    assert _clone_inputs(app)["원천 시뮬레이션 코드"] == ""
    assert _clone_inputs(app)["원천 시뮬레이션명"] == ""


def test_names_in_markdown_places_are_shown_as_typed(tmp_path: Path) -> None:
    """카드 제목·보관 확인처럼 마크다운으로 그려지는 자리에 시나리오명을 글자 그대로 싣는다.

    그대로면 「A~B~C」의 물결표는 취소선으로, 「$x$」는 수식으로 사라진다(AGENTS 9장).
    """

    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    name = "A~B~C $x$ *y*"
    target = _clone_official(database_path, name, "MARKDOWN-1")

    app = AppTest.from_string(script, default_timeout=120)
    _check_row(app, target.scenario.scenario_id)
    app.run()
    app.button(key=f"{ACTION_KEY}_archive").click().run()
    assert not app.exception
    escaped = literal_markdown(name)
    assert any(item.value == f"#### :material/check_box: {escaped}" for item in app.markdown)
    assert any(widget.label.startswith(escaped) for widget in app.checkbox)


def _archived_box_place(app: AppTest) -> int:
    """첫 탭 안에서 보관함 상자가 몇 번째 자식인가(브라우저가 블록을 가리키는 순번)."""
    tab = app.main.tabs[0]
    box = app.main.get_by_key(ARCHIVED_EXPANDER_KEY)
    return next(index for index, child in tab.children.items() if child is box)


def test_the_archived_box_keeps_its_place_with_or_without_notices(tmp_path: Path) -> None:
    """맨 위 알림·목록 결과 칸·고른 시나리오 카드가 생기고 사라져도 보관함 상자의 순번이 같다.

    보관함의 「되돌리기」·「영구 삭제」는 본문에서 `st.rerun()` 으로 회차를 끊는다. 다음 회차에
    알림이 생겨 key 있는 보관함 상자가 한 칸 밀리면 옛 자리에 흐린 사본이 남아 모드를 바꿔도
    새로고침 전까지 따라왔다(2026-10-22 사본 앱 이분 탐색 — 알림·상자 key·본문 rerun 셋이 모두
    있을 때만). 알림·카드는 늘 서 있는 칸 안에 그려 자리를 고정한다(AGENTS 9장). 공식 발행 이력
    상자도 같은 까닭으로 늘 선다.
    """
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    repository = DuckDBScenarioRepository(database_path)
    first = _clone_official(database_path, "보관 자리 하나", "PLACE-1")
    _clone_official(database_path, "보관 자리 둘", "PLACE-2")
    archived = _clone_official(database_path, "보관 자리 셋", "PLACE-3")
    repository.archive_scenario(archived.scenario.scenario_id)

    app = AppTest.from_string(script, default_timeout=120).run()
    assert not app.exception
    quiet = _archived_box_place(app)
    history = app.main.get_by_key(HISTORY_EXPANDER_KEY)
    assert isinstance(history, (Expander, Status))

    app.session_state[FLASH_KEY] = "보관 자리 셋을 목록으로 되돌렸습니다."
    app.session_state["scenario_management_flash_warning"] = "남은 계산 경고"
    app.session_state["scenario_list_notice"] = ("error", "목록 결과 칸")
    app.run()
    assert not app.exception
    assert any("되돌렸습니다" in item.value for item in app.success)
    assert any("목록 결과 칸" in item.value for item in app.error)
    assert _archived_box_place(app) == quiet

    _check_row(app, first.scenario.scenario_id)
    app.session_state["scenario_card_notice"] = ("success", "카드 결과 칸")
    app.run()
    assert not app.exception
    assert "보관…" in {button.label for button in app.button}
    assert _archived_box_place(app) == quiet


def test_the_two_boxes_under_the_card_always_stand(tmp_path: Path) -> None:
    """보관본이 없어도 「보관된 시나리오 0건」 상자가 서고, 공식 발행 이력은 r 번호·공식버전명만.

    공식 발행 이력에 리비전명을 실으면 이름을 바꾸는 순간 과거 발행 행이 발행 당시와 다른 이름을
    보인다(2026-10-22 결정 — 이력 표는 지금처럼).
    """
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    app = AppTest.from_string(script, default_timeout=120).run()
    assert not app.exception
    box = app.main.get_by_key(ARCHIVED_EXPANDER_KEY)
    assert isinstance(box, (Expander, Status))
    assert box.label == "보관된 시나리오 0건"
    history = app.main.get_by_key(HISTORY_EXPANDER_KEY)
    assert isinstance(history, (Expander, Status))
    assert history.label == "공식 발행 이력 1건"
    frame = next(
        element.value for element in app.dataframe if "공식버전명" in element.value.columns
    )
    assert frame.columns.tolist() == ["공식버전", "시나리오", "리비전", "공식버전명", "지정시각"]


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


def test_picking_another_row_keeps_the_unsaved_name_and_order_edits(tmp_path: Path) -> None:
    """다른 행을 고르면 앞 고름만 풀리고 같은 표의 미저장 이름·순서 편집은 남는다(C안).

    편집표를 다시 세우는 길(`discard_editor` — key 세대)은 편집을 모두 버린다. 그래서 고른 줄이
    둘이 되면 초안에 이름·순서를 행 id 로 먼저 적고 새 위젯으로 세운다 — 초안이 값을 다시 싣는다.
    """
    script, _, ids, names = _three_scenarios(tmp_path)
    app = AppTest.from_string(script, default_timeout=120)
    tables = BrowserTables(app)
    tables.run()
    tables.edit(_shown_key(app, LIST_EDITOR_KEY), 2, "시나리오명", "고친 이름")
    tables.edit(_shown_key(app, LIST_EDITOR_KEY), 0, "선택", True)
    tables.run()
    assert not app.exception
    assert _draft(app, LIST_EDITOR_KEY).picked == ids[0]

    tables.edit(_shown_key(app, LIST_EDITOR_KEY), 1, "선택", True)
    tables.run()
    assert not app.exception
    assert _draft(app, LIST_EDITOR_KEY).picked == ids[1]
    frame = _list_frame(app)
    assert frame["선택"].tolist() == [False, True, False]
    assert frame.index.tolist() == [names[0], names[1], "고친 이름"]
    assert _caption_with(app, "고친 것").endswith("고친 것: 이름 1 · 순서 0")

    # 순서를 고친 뒤 다른 행을 골라도 순서·이름이 남는다.
    tables.edit(_shown_key(app, LIST_EDITOR_KEY), 2, "순서", 1)
    tables.run()
    tables.edit(_shown_key(app, LIST_EDITOR_KEY), 1, "선택", True)
    tables.run()
    assert not app.exception
    frame = _list_frame(app)
    assert frame.index.tolist() == ["고친 이름", names[0], names[1]]
    assert frame["순서"].tolist() == [1, 2, 3]
    assert _draft(app, LIST_EDITOR_KEY).picked == ids[0]
    assert _caption_with(app, "고친 것").endswith("고친 것: 이름 1 · 순서 3")
    # 카드는 하나다 — 두 건 경고 없이 새로 고른 시나리오의 카드가 선다.
    assert not any("한 건만" in item.value for item in app.warning)
    assert any(item.value.endswith(names[0]) for item in app.markdown if "####" in item.value)


def test_a_place_number_inserts_the_row_and_the_buttons_move_the_picked_one(tmp_path: Path) -> None:
    """순서 칸에 자리 번호를 넣으면 그 자리로 끼워 넣고(나머지는 밀림) 칸은 늘 1..n 이다.

    고른 시나리오는 위로·아래로·맨 위로 단추로도 옮긴다. 둘 다 미저장 순서 편집으로 쌓이고 「변경
    저장」 한 번으로 쓴다(순서 바꾸기 개선안 (a)+(b)).
    """
    script, database_path, ids, names = _three_scenarios(tmp_path)
    app = AppTest.from_string(script, default_timeout=120)
    tables = BrowserTables(app)
    tables.run()
    for key in ("scenario_list_up", "scenario_list_down", "scenario_list_top"):
        assert app.button(key=key).disabled, key

    tables.edit(_shown_key(app, LIST_EDITOR_KEY), 2, "순서", 1)
    tables.run()
    frame = _list_frame(app)
    assert frame.index.tolist() == [names[2], names[0], names[1]]
    assert frame["순서"].tolist() == [1, 2, 3]

    # 끝 밖의 번호는 끝에 붙는다.
    tables.edit(_shown_key(app, LIST_EDITOR_KEY), 0, "순서", 9)
    tables.run()
    assert _list_frame(app).index.tolist() == [names[0], names[1], names[2]]
    assert app.button(key="scenario_list_save").disabled  # 저장 차례와 같아졌다

    tables.edit(_shown_key(app, LIST_EDITOR_KEY), 2, "선택", True)
    tables.run()
    assert app.button(key="scenario_list_down").disabled
    app.button(key="scenario_list_top").click()
    tables.run()
    assert _list_frame(app).index.tolist() == [names[2], names[0], names[1]]
    assert app.button(key="scenario_list_up").disabled
    app.button(key="scenario_list_down").click()
    tables.run()
    assert _list_frame(app).index.tolist() == [names[0], names[2], names[1]]
    assert _list_frame(app)["선택"].tolist() == [False, True, False]

    app.button(key="scenario_list_save").click()
    tables.run()
    assert not app.exception
    assert "누적 순서를 저장했습니다." in [item.value for item in app.success]
    stored = DuckDBScenarioRepository(database_path).list_scenarios()
    assert [scenario.scenario_id for scenario in stored] == [ids[0], ids[2], ids[1]]
    # 저장하면 편집이 비고 고름은 남는다.
    assert _draft(app, LIST_EDITOR_KEY) == TableDraft(picked=ids[2])


def test_a_list_save_with_one_refused_name_writes_nothing(tmp_path: Path) -> None:
    """하나라도 거부되면 아무것도 쓰지 않고 행마다 까닭을 적는다. 이름 맞바꾸기는 된다."""
    script, database_path, ids, names = _three_scenarios(tmp_path)
    repository = DuckDBScenarioRepository(database_path)
    app = AppTest.from_string(script, default_timeout=120)
    tables = BrowserTables(app)
    tables.run()
    tables.edit(_shown_key(app, LIST_EDITOR_KEY), 0, "시나리오명", names[1])
    tables.edit(_shown_key(app, LIST_EDITOR_KEY), 2, "시나리오명", "새 이름")
    tables.run()
    app.button(key="scenario_list_save").click()
    tables.run()

    assert not app.exception
    (error,) = [item.value for item in app.error]
    assert error.startswith("저장하지 않았습니다 — 하나라도 막히면 아무것도 쓰지 않습니다.")
    assert f"1행 「{literal_markdown(names[1])}」" in error
    assert literal_markdown("같은 이름의 시나리오가 이미 있습니다") in error
    assert [scenario.scenario_name for scenario in repository.list_scenarios()] == names
    assert _caption_with(app, "고친 것").endswith("고친 것: 이름 2 · 순서 0")

    # 두 이름을 맞바꾸면 저장 뒤 이름이 겹치지 않아 된다.
    tables.edit(_shown_key(app, LIST_EDITOR_KEY), 1, "시나리오명", names[0])
    tables.run()
    app.button(key="scenario_list_save").click()
    tables.run()
    assert not app.exception
    assert "시나리오명 3건을 저장했습니다." in [item.value for item in app.success]
    renamed = {
        scenario.scenario_id: scenario.scenario_name for scenario in repository.list_scenarios()
    }
    assert renamed == {ids[0]: names[1], ids[1]: names[0], ids[2]: "새 이름"}


def test_an_order_changed_elsewhere_refuses_the_order_and_keeps_the_names(tmp_path: Path) -> None:
    """순서를 고치는 사이 다른 곳에서 목록 차례가 바뀌면 순서는 쓰지 않는다(남의 차례를 덮지 않음).

    아무것도 쓰지 않고, 순서 편집만 버려 지금 차례로 표를 다시 세운다. 이름 편집은 행 id 로 남아
    다시 누르면 저장된다.
    """
    from capa_simulation.persistence.repository import SCENARIO_LIST_MOVED_MESSAGE

    script, database_path, ids, names = _three_scenarios(tmp_path)
    repository = DuckDBScenarioRepository(database_path)
    app = AppTest.from_string(script, default_timeout=120)
    tables = BrowserTables(app)
    tables.run()
    tables.edit(_shown_key(app, LIST_EDITOR_KEY), 0, "시나리오명", "새 첫째")
    tables.run()
    tables.edit(_shown_key(app, LIST_EDITOR_KEY), 2, "순서", 1)
    tables.run()

    repository.reorder_scenarios([ids[1], ids[0], ids[2]])
    tables.run()
    # 화면은 이 세션이 고친 차례를 그대로 보인다.
    assert _list_frame(app).index.tolist() == [names[2], "새 첫째", names[1]]
    app.button(key="scenario_list_save").click()
    tables.run()

    assert not app.exception
    (error,) = [item.value for item in app.error]
    assert literal_markdown(SCENARIO_LIST_MOVED_MESSAGE) in error
    stored = repository.list_scenarios()
    assert [scenario.scenario_id for scenario in stored] == [ids[1], ids[0], ids[2]]
    assert [scenario.scenario_name for scenario in stored] == [names[1], names[0], names[2]]
    assert _list_frame(app).index.tolist() == [names[1], "새 첫째", names[2]]
    assert _caption_with(app, "고친 것").endswith("고친 것: 이름 1 · 순서 0")

    app.button(key="scenario_list_save").click()
    tables.run()
    assert "시나리오명 1건을 저장했습니다." in [item.value for item in app.success]
    assert (
        next(
            scenario.scenario_name
            for scenario in repository.list_scenarios()
            if scenario.scenario_id == ids[0]
        )
        == "새 첫째"
    )


def test_an_unsaved_name_stays_on_its_scenario_when_another_session_reorders(
    tmp_path: Path,
) -> None:
    """편집표 편집은 행 위치로 남는다. 다른 세션이 차례를 바꿔도 고친 이름은 그 시나리오에 붙는다.

    위젯 key 에 행 차례 지문이 있어 차례가 바뀌면 새 위젯으로 서고, 지난 회차에 그린 차례로 접은
    초안이 id 로 값을 다시 싣는다(2026-10-22 critique — 같은 key 면 옛 위치의 편집이 다른 행에
    붙었다).
    """
    script, database_path, ids, names = _three_scenarios(tmp_path)
    app = AppTest.from_string(script, default_timeout=120)
    tables = BrowserTables(app)
    tables.run()
    tables.edit(_shown_key(app, LIST_EDITOR_KEY), 0, "시나리오명", "첫째 새 이름")
    tables.run()

    DuckDBScenarioRepository(database_path).reorder_scenarios([ids[2], ids[1], ids[0]])
    tables.run()
    assert not app.exception
    frame = _list_frame(app)
    assert frame.index.tolist() == [names[2], names[1], "첫째 새 이름"]
    assert _draft(app, LIST_EDITOR_KEY).names == {ids[0]: "첫째 새 이름"}


def test_revision_names_are_saved_from_the_card_table(tmp_path: Path) -> None:
    """카드 리비전 표의 리비전명(✎)을 고쳐 「이름 저장 (n)」으로 한 번에 쓴다.

    공식으로 지정된 리비전도 고칠 수 있고 공식버전명은 그대로다(S4) — 고치는 동안 그 사실을 한 줄로
    적는다. 올라와 있는 리비전이면 머리 띠 이름표도 바뀐다. 시나리오 「최근 수정」은 오르지 않는다.
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

    app = AppTest.from_string(script, default_timeout=120)
    tables = BrowserTables(app)
    _check_row(app, seed.scenario.scenario_id)
    tables.run()
    frame = _revision_frame(app)
    assert frame["r"].tolist() == ["r2", "r1"]
    assert frame["부모"].tolist() == ["r1", ""]
    assert frame["메모"].tolist()[0] == "첫 줄 둘째 줄"
    assert frame["상태"].tolist() == ["", f"공식 v{release.release_no} · 올라와 있음"]
    assert app.button(key="scenario_card_save_names").disabled

    tables.edit(_shown_key(app, REVISION_EDITOR_KEY), 1, "리비전명", "공식 리비전 새 이름")
    tables.edit(_shown_key(app, REVISION_EDITOR_KEY), 0, "리비전명", "필터 저장")
    tables.run()
    assert app.button(key="scenario_card_save_names").label == "이름 저장 (2)"
    assert any(
        f"r1: 공식 v{release.release_no} 으로 지정된 리비전입니다 — 공식버전명은 바뀌지 않습니다."
        in item.value
        for item in app.caption
    )
    app.button(key="scenario_card_save_names").click()
    tables.run()

    assert not app.exception
    assert any(item.value.startswith("리비전명을 저장했습니다: ") for item in app.success), [
        item.value for item in app.success
    ]
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
    assert app.button(key="scenario_card_save_names").label == "이름 저장"


def test_a_revision_name_changed_elsewhere_refuses_the_whole_name_save(tmp_path: Path) -> None:
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

    app = AppTest.from_string(script, default_timeout=120)
    tables = BrowserTables(app)
    _check_row(app, seed.scenario.scenario_id)
    tables.run()
    tables.edit(_shown_key(app, REVISION_EDITOR_KEY), 0, "리비전명", "내가 고친 이름")
    tables.edit(_shown_key(app, REVISION_EDITOR_KEY), 1, "리비전명", "같이 고친 이름")
    tables.run()
    repository.rename_revision(probe.revision_id, "남이 고친 이름", expected_name="probe save")
    app.button(key="scenario_card_save_names").click()
    tables.run()

    assert not app.exception
    (error,) = [item.value for item in app.error]
    assert f"r2 「{literal_markdown('내가 고친 이름')}」" in error
    assert literal_markdown("다른 사용자가 먼저 이름을 바꿨습니다(지금: 남이 고친 이름).") in error
    names = [
        revision.revision_name for revision in repository.list_revisions(seed.scenario.scenario_id)
    ]
    assert names == ["남이 고친 이름", seed.revision.revision_name]


def _row_position(app: AppTest, key: str, row_id: str) -> int:
    """지난 회차에 그린 편집표에서 그 행 id 가 선 자리 — 칸 편집을 보낼 행 위치."""
    shown = app.session_state[shown_session_key(key)]
    assert isinstance(shown, ShownTable)
    return shown.rows.index(row_id)


def test_a_scenario_name_changed_elsewhere_is_not_overwritten_after_more_runs(
    tmp_path: Path,
) -> None:
    """이름은 사용자가 그 칸을 고칠 때 **본** 이름과 대조한다(S6 비교 후 쓰기).

    다른 사용자가 먼저 바꾼 뒤 이 세션에서 회차가 더 돌아도(다른 행 고르기 등) 대조 기준은 처음
    본 이름이다. 마지막 회차에 다시 읽은 이름을 기준으로 삼으면 남의 변경을 알림 없이 덮는다
    (2026-10-22 리뷰 — 클릭 직전에만 끼운 시험은 이 길을 못 봤다). 표 위에 미리 경고하고, 거부되면
    그 행만 지금 이름으로 다시 세워 보고 다시 고치게 한다.
    """
    script, database_path, ids, names = _three_scenarios(tmp_path)
    repository = DuckDBScenarioRepository(database_path)
    app = AppTest.from_string(script, default_timeout=120)
    tables = BrowserTables(app)
    tables.run()
    tables.edit(
        _shown_key(app, LIST_EDITOR_KEY),
        _row_position(app, LIST_EDITOR_KEY, ids[1]),
        "시나리오명",
        "내가 바꾼 이름",
    )
    tables.run()
    repository.rename_scenario(ids[1], "남이 바꾼 이름")
    tables.run()
    tables.edit(
        _shown_key(app, LIST_EDITOR_KEY), _row_position(app, LIST_EDITOR_KEY, ids[0]), "선택", True
    )
    tables.run()
    assert not app.exception
    assert _draft(app, LIST_EDITOR_KEY).picked == ids[0]
    (warning,) = [item.value for item in app.warning if "먼저 이름을 바꿨습니다" in item.value]
    assert literal_markdown("「내가 바꾼 이름」(지금: 남이 바꾼 이름)") in warning

    app.button(key="scenario_list_save").click()
    tables.run()
    assert not app.exception
    (error,) = [item.value for item in app.error]
    assert literal_markdown("다른 사용자가 먼저 이름을 바꿨습니다(지금: 남이 바꾼 이름).") in error
    stored = {
        scenario.scenario_id: scenario.scenario_name for scenario in repository.list_scenarios()
    }
    assert stored == {ids[0]: names[0], ids[1]: "남이 바꾼 이름", ids[2]: names[2]}
    # 그 행만 지금 이름으로 다시 선다. 고름은 남는다.
    frame = _list_frame(app)
    assert "남이 바꾼 이름" in frame.index and "내가 바꾼 이름" not in frame.index
    assert _draft(app, LIST_EDITOR_KEY).picked == ids[0]
    assert _caption_with(app, "고친 것").endswith("고친 것: 이름 0 · 순서 0")
    assert not any("먼저 이름을 바꿨습니다" in item.value for item in app.warning)

    # 지금 이름을 보고 다시 고치면 저장된다.
    tables.edit(
        _shown_key(app, LIST_EDITOR_KEY),
        _row_position(app, LIST_EDITOR_KEY, ids[1]),
        "시나리오명",
        "내가 바꾼 이름",
    )
    tables.run()
    app.button(key="scenario_list_save").click()
    tables.run()
    assert not app.exception
    assert "시나리오명 1건을 저장했습니다." in [item.value for item in app.success]
    stored = {
        scenario.scenario_id: scenario.scenario_name for scenario in repository.list_scenarios()
    }
    assert stored[ids[1]] == "내가 바꾼 이름"


def test_a_revision_name_changed_elsewhere_is_not_overwritten_after_more_runs(
    tmp_path: Path,
) -> None:
    """리비전 표도 그 칸을 고칠 때 본 이름과 대조한다 — 남의 변경 뒤 다른 줄을 골라(표를 다시
    세우는 회차) 회차가 더 돌아도 남의 이름을 덮지 않는다(2026-10-22 리뷰)."""
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

    app = AppTest.from_string(script, default_timeout=120)
    tables = BrowserTables(app)
    _check_row(app, seed.scenario.scenario_id)
    tables.run()
    tables.edit(_shown_key(app, REVISION_EDITOR_KEY), 0, "리비전명", "내가 고친 이름")
    tables.run()
    repository.rename_revision(probe.revision_id, "남이 고친 이름", expected_name="probe save")
    tables.run()
    # 이미 고른 줄(r1, 올라와 있는 리비전)이 있는 채 r2 를 고르면 두 줄이 골라져 표를 다시 세운다.
    tables.edit(_shown_key(app, REVISION_EDITOR_KEY), 0, "고름", True)
    tables.run()
    assert not app.exception
    assert _draft(app, REVISION_EDITOR_KEY).picked == probe.revision_id
    (warning,) = [item.value for item in app.warning if "먼저 이름을 바꿨습니다" in item.value]
    assert literal_markdown("r2 「내가 고친 이름」(지금: 남이 고친 이름)") in warning

    app.button(key="scenario_card_save_names").click()
    tables.run()
    assert not app.exception
    (error,) = [item.value for item in app.error]
    assert f"r2 「{literal_markdown('내가 고친 이름')}」" in error
    assert literal_markdown("다른 사용자가 먼저 이름을 바꿨습니다(지금: 남이 고친 이름).") in error
    names = [
        revision.revision_name for revision in repository.list_revisions(seed.scenario.scenario_id)
    ]
    assert names == ["남이 고친 이름", seed.revision.revision_name]
    assert _revision_frame(app)["리비전명"].tolist() == names
    assert _draft(app, REVISION_EDITOR_KEY).picked == probe.revision_id
    assert app.button(key="scenario_card_save_names").disabled
