# Purpose: 시나리오 관리 페이지의 폼·목록 작업·보관함·복제 저장·캐시 무효화를 AppTest 로 고정한다.

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Button, Expander, Status
from streamlit.testing.v1.errors import AppTestError
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
    REVISION_SELECT_KEY,
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
    next(widget for widget in app.text_area if widget.label == "변경 메모").set_value(
        "남지 않을 메모"
    )
    next(button for button in app.button if button.label == "새 리비전 저장").click()
    app.run()
    assert not app.exception
    # 저장에 성공하면 두 칸이 새 key 의 빈 위젯으로 선다 — 남아 있으면 한 번 더 눌러 같은 이름의
    # 리비전이 또 선다. key 가 바뀌어야 브라우저도 옛 글을 들고 있지 않는다.
    name_box = next(widget for widget in app.text_input if widget.label == "새 리비전명")
    note_box = next(widget for widget in app.text_area if widget.label == "변경 메모")
    assert (name_box.key, name_box.value) == ("scenario_revision_name_g1", "")
    assert (note_box.key, note_box.value) == ("scenario_revision_note_g1", "")

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


def test_a_refused_revision_save_keeps_the_typed_name_and_memo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """계산 검사에 막힌 「새 리비전 저장」은 적은 리비전명·메모를 남긴다(key 세대 그대로)."""
    import capa_simulation.components.scenario_management as scenario_management
    from capa_simulation.components.capacity_gate import GateVerdict

    monkeypatch.setattr(
        scenario_management,
        "revision_save_verdict",
        lambda *args: GateVerdict(False, "이번 편집이 깨뜨린 것입니다"),
    )
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    app = AppTest.from_string(script, default_timeout=120).run()
    app.segmented_control(key=MODE_KEY).set_value("리비전 저장").run()
    app.text_input(key="scenario_revision_name_g0").set_value("막힐 리비전")
    app.text_area(key="scenario_revision_note_g0").set_value("고친 까닭")
    next(button for button in app.button if button.label == "새 리비전 저장").click()
    app.run()

    assert not app.exception
    assert any("이번 편집이 깨뜨린" in item.value for item in app.error)
    assert app.text_input(key="scenario_revision_name_g0").value == "막힐 리비전"
    assert app.text_area(key="scenario_revision_note_g0").value == "고친 까닭"


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


def _save_revision(app: AppTest, name: str) -> None:
    next(widget for widget in app.text_input if widget.label == "새 리비전명").set_value(name)
    next(button for button in app.button if button.label == "새 리비전 저장").click()
    app.run()
    assert not app.exception


def _history_products(repository: DuckDBScenarioRepository, revision_id: str) -> list[str]:
    return repository.list_virtual_products(revision_id)["제품정보"].tolist()


def _notice(count: int) -> str:
    return (
        f"가상 제품 {count}건이 포함되어 있습니다. "
        "실적과 대조할 수 없으므로 공식버전으로 발행하기 전에 확인하세요."
    )


def test_new_revision_inherits_the_loaded_revisions_virtual_products(tmp_path: Path) -> None:
    """r2 에 등록한 가상 제품이 r2 를 이어 저장한 r3 에도 남는다(2026-10-05 사용자 결정 N6 = A).

    리비전을 불러오면 세션 목록이 비어서, 물려받지 않으면 r3 부터 출처가 사라졌다. r3 의 세션
    목록에는 B 만 있으므로 A 는 부모 이력에서만 올 수 있고, 알림은 합친 건수를 센다.
    """
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    app = AppTest.from_string(script, default_timeout=120).run()
    assert not app.exception
    app.segmented_control(key=MODE_KEY).set_value("리비전 저장").run()
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
    assert f"새 리비전 r3을 저장했습니다. {_notice(2)}" in [item.value for item in app.success]


def test_clone_inherits_the_active_revisions_virtual_products_still_in_the_tables(
    tmp_path: Path,
) -> None:
    """「현재 활성 RQ 복제」의 초기 리비전도 활성 리비전의 이력을 물려받는다.

    물려받은 제품이 복제하는 표 어디에도 남아 있지 않으면 그 이력은 따라가지 않는다.
    """
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    app = AppTest.from_string(script, default_timeout=120).run()
    assert not app.exception
    app.segmented_control(key=MODE_KEY).set_value("리비전 저장").run()
    _register_virtual(app, "DEMO_VIRTUAL_A")
    _register_virtual(app, "DEMO_VIRTUAL_B")
    _save_revision(app, "가상 제품 둘")

    _drop_from_active_tables(app, "DEMO_VIRTUAL_A")
    app.segmented_control(key=MODE_KEY).set_value("현재 활성 RQ 복제").run()
    assert not app.exception
    _fill_clone(app, "가상 제품 상속 복제", "CLONE-INHERIT")

    assert f"가상 제품 상속 복제를 저장했습니다. {_notice(1)}" in [
        item.value for item in app.success
    ]
    repository = DuckDBScenarioRepository(database_path)
    clone = next(
        item for item in repository.list_scenarios() if item.scenario_name == "가상 제품 상속 복제"
    )
    assert _history_products(repository, clone.active_revision_id) == ["DEMO_VIRTUAL_B"]


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

    assert any("이름 바꾼 시나리오로 변경했습니다" in item.value for item in app.success)
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


OFFICIAL_BUTTON = "선택 리비전을 공식버전으로 지정"
VIRTUAL_CONFIRM_LABEL = "가상 제품이 포함된 것을 확인했습니다"


def _open_official(app: AppTest, database_path: Path, scenario_id: str, revision_id: str) -> None:
    """목록에서 그 시나리오를 고르고 리비전을 정한 뒤 「공식버전 지정」 칸을 연다."""
    _check_row(app, database_path, scenario_id)
    app.run()
    app.session_state[REVISION_SELECT_KEY] = revision_id
    app.session_state[ACTION_KEY] = "official"
    app.run()
    assert not app.exception


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
    _open_official(app, database_path, saved.scenario.scenario_id, revision_id)
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
    # 열어 주면, 확인하지 않은 리비전이 공식버전이 된다.
    app.selectbox(key=REVISION_SELECT_KEY).set_value(other_revision_id)
    app.run()
    assert not app.exception
    assert _official_button(app).disabled

    app.selectbox(key=REVISION_SELECT_KEY).set_value(revision_id)
    app.run()
    assert not app.exception
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


def test_official_release_without_virtual_products_asks_nothing(tmp_path: Path) -> None:
    """가상 제품이 없는 리비전은 전과 같다 — 경고·확인 체크 없이 버튼이 바로 열린다."""
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    repository = DuckDBScenarioRepository(database_path)
    release = repository.latest_official_release()
    assert release is not None

    app = AppTest.from_string(script, default_timeout=120)
    _open_official(app, database_path, release.scenario_id, release.revision_id)
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
