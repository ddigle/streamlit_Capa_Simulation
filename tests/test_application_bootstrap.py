# Purpose: application bootstrap 관련 정상·예외·회귀 동작을 검증한다.

from pathlib import Path
from types import SimpleNamespace

import pytest
from alert_marks import alert_notes, data_error_marks, states
from streamlit.testing.v1 import AppTest
from test_all_pages_render import _page_script

from capa_simulation import page_bootstrap
from capa_simulation.application_bootstrap import ensure_initial_scenario
from capa_simulation.auth import names, runtime
from capa_simulation.components.data_error_mark import EMPTY_CLASS
from capa_simulation.io.core_data_source import load_core_data_contract
from capa_simulation.navigation import ALL_SPECS
from capa_simulation.persistence.models import ScenarioCreate, ScenarioPreset
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_activation import builtin_seed_allowed
from capa_simulation.services.builtin_seed import (
    BUILTIN_SEED_MONTHS,
    BUILTIN_SEED_SOURCE_CODE,
    build_builtin_seed_dataset,
    builtin_seed_processes,
)
from capa_simulation.services.required_equipment import calculate_required_equipment
from capa_simulation.services.securement_rate import calculate_securement_rate
from capa_simulation.services.unit_capacity import calculate_unit_capacity


def test_builtin_seed_uses_exact_contract_and_builds_all_reference_tables() -> None:
    prepared = build_builtin_seed_dataset()
    expected_columns = [column.name for column in load_core_data_contract().columns]

    assert list(prepared.source_data.columns) == expected_columns
    assert len(expected_columns) == 78
    assert set(prepared.reference_tables) == {
        "RQ_PKG_PLAN",
        "RQ_YLD",
        "RQ_CHIP_QTY",
        "RQ_CHIP_EQ",
        "RQ_DISPLAY_ORDER",
        "RQ_EQP_OWN",
        "RQ_EQP_LENT",
        "RQ_EQP_AVBL",
        "RQ_UPEH",
        "RQ_RUN_RATE",
        "RQ_VITAL",
        "RQ_MODULE",
        "RQ_RUN_DAY",
        "RQ_LOT_RATIO",
        "RQ_WF_RATIO",
        "RQ_REQB",
    }
    assert all(not table.empty for table in prepared.reference_tables.values())
    assert set(prepared.reference_tables["RQ_PKG_PLAN"]["생산계획년월"]) == set(BUILTIN_SEED_MONTHS)
    assert prepared.source_data["제품정보"].dropna().str.startswith("DEMO_").all()


def test_builtin_seed_runs_the_capacity_calculation_chain() -> None:
    tables = build_builtin_seed_dataset().reference_tables

    unit_capacity = calculate_unit_capacity(
        upeh=tables["RQ_UPEH"],
        run_rate=tables["RQ_RUN_RATE"],
        vital=tables["RQ_VITAL"],
        module=tables["RQ_MODULE"],
        run_day=tables["RQ_RUN_DAY"],
        lot_ratio=tables["RQ_LOT_RATIO"],
        wf_ratio=tables["RQ_WF_RATIO"],
    )
    required_equipment = calculate_required_equipment(
        reqb=tables["RQ_REQB"],
        plan=tables["RQ_PKG_PLAN"],
        yield_data=tables["RQ_YLD"],
        chip_qty=tables["RQ_CHIP_QTY"],
        unit_capacity=unit_capacity,
    )
    securement = calculate_securement_rate(tables["RQ_EQP_AVBL"], required_equipment)

    assert not unit_capacity.empty
    assert not required_equipment.empty
    assert not securement.empty
    assert set(securement["공정"]) == set(builtin_seed_processes())


def test_empty_store_is_seeded_published_and_idempotent(tmp_path: Path) -> None:
    repository = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    repository.initialize()

    created = ensure_initial_scenario(repository)
    repeated = ensure_initial_scenario(repository)

    assert created.status == "created_builtin_seed"
    assert created.release is not None
    assert repeated.status == "existing_official"
    assert repeated.release == created.release
    scenarios = repository.list_scenarios()
    assert len(scenarios) == 1
    assert scenarios[0].source_simulation_code == BUILTIN_SEED_SOURCE_CODE
    assert len(repository.load_source_data(scenarios[0].scenario_id).columns) == 78


def test_streamlit_session_activates_seed_on_first_start(tmp_path: Path) -> None:
    database_path = tmp_path / "streamlit-bootstrap.duckdb"
    script = f"""
import streamlit as st

from capa_simulation.scenario_activation import (
    ACTIVE_PERSISTED_REVISION_ID_KEY,
    bootstrap_latest_official_scenario,
)

st.write(bootstrap_latest_official_scenario({str(database_path)!r}))
st.write(st.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY])
"""

    app = AppTest.from_string(script).run(timeout=30)

    assert not app.exception
    assert app.markdown[0].value == "`True`"
    assert app.session_state["active_persisted_revision_id"]
    repository = DuckDBScenarioRepository(database_path)
    assert repository.latest_official_release() is not None


def _create_user_scenario(repository: DuckDBScenarioRepository) -> str:
    prepared = build_builtin_seed_dataset()
    snapshot = repository.create_scenario(
        ScenarioCreate(
            scenario_name="사용자 시나리오",
            source_simulation_code="USER-SCENARIO-001",
            source_simulation_name="사용자 원천",
            source_type="TEST",
            pipeline_version="test-v1",
        ),
        prepared.reference_tables,
        ScenarioPreset(
            min(BUILTIN_SEED_MONTHS),
            max(BUILTIN_SEED_MONTHS),
            builtin_seed_processes(),
        ),
        source_data=prepared.source_data,
    )
    return snapshot.scenario.scenario_id


def test_existing_unpublished_store_is_not_overwritten(tmp_path: Path) -> None:
    repository = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    repository.initialize()
    scenario_id = _create_user_scenario(repository)

    result = ensure_initial_scenario(repository)

    assert result.status == "existing_without_official"
    assert result.release is None
    scenarios = repository.list_scenarios()
    assert [scenario.scenario_id for scenario in scenarios] == [scenario_id]


def test_store_with_only_archived_scenarios_is_not_seeded(tmp_path: Path) -> None:
    repository = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    repository.initialize()
    scenario_id = _create_user_scenario(repository)
    repository.archive_scenario(scenario_id)

    result = ensure_initial_scenario(repository)

    assert result.status == "existing_without_official"
    assert result.release is None
    assert repository.latest_official_release() is None
    assert repository.list_scenarios() == []
    every = repository.list_scenarios(include_archived=True)
    assert [(item.scenario_id, item.status) for item in every] == [(scenario_id, "ARCHIVED")]


def _seed_without_official(repository: DuckDBScenarioRepository) -> str:
    seeded = ensure_initial_scenario(repository).release
    assert seeded is not None
    with repository._write_transaction() as connection:
        connection.execute("DELETE FROM app_meta.official_release")
    return seeded.scenario_id


def test_interrupted_builtin_seed_is_published_once(tmp_path: Path) -> None:
    repository = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    repository.initialize()
    seed_id = _seed_without_official(repository)

    repaired = ensure_initial_scenario(repository)
    repeated = ensure_initial_scenario(repository)

    assert repaired.status == "repaired_builtin_seed"
    assert repaired.release is not None
    assert repaired.release.scenario_id == seed_id
    assert repeated.status == "existing_official"
    assert repeated.release == repaired.release


def test_archived_builtin_seed_is_not_republished(tmp_path: Path) -> None:
    repository = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    repository.initialize()
    scenario_id = _seed_without_official(repository)
    repository.archive_scenario(scenario_id)

    result = ensure_initial_scenario(repository)

    assert result.status == "existing_without_official"
    assert result.release is None
    assert repository.latest_official_release() is None
    every = repository.list_scenarios(include_archived=True)
    assert [(item.scenario_id, item.status) for item in every] == [(scenario_id, "ARCHIVED")]


@pytest.mark.parametrize("user_archived", [True, False], ids=["user_archived", "user_active"])
def test_restored_builtin_seed_beside_another_scenario_is_not_published(
    tmp_path: Path, *, user_archived: bool
) -> None:
    repository = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    repository.initialize()
    seed_id = _seed_without_official(repository)
    user_id = _create_user_scenario(repository)
    repository.archive_scenario(seed_id)
    if user_archived:
        repository.archive_scenario(user_id)
    repository.restore_scenario(seed_id)

    result = ensure_initial_scenario(repository)

    assert result.status == "existing_without_official"
    assert result.release is None
    assert repository.latest_official_release() is None
    every = repository.list_scenarios(include_archived=True)
    assert {item.scenario_id: item.status for item in every} == {
        seed_id: "ACTIVE",
        user_id: "ARCHIVED" if user_archived else "ACTIVE",
    }


def _operational(app_env: str = "prod") -> None:
    """운영 서버(`SsoConfig.operational` — `APP_ENV` 운영, 통합인증 꺼짐)로 기동한 것처럼 세운다."""
    runtime.reset()
    runtime.start({names.ENV_APP_ENV: app_env})


def test_an_operational_server_leaves_an_empty_store_without_a_seed(tmp_path: Path) -> None:
    """운영 서버는 빈 저장소에 내장 합성 시드를 만들지도 「공식 v1」 로 올리지도 않는다 — 공식버전
    없이 남고 화면은 「공식버전 없음」 이다(2026-11-14 물음 보드 seed (nopub))."""
    repository = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    repository.initialize()

    result = ensure_initial_scenario(repository, seed=False)
    repeated = ensure_initial_scenario(repository, seed=False)

    assert (result.status, result.release) == ("empty_without_seed", None)
    assert (repeated.status, repeated.release) == ("empty_without_seed", None)
    assert repository.latest_official_release() is None
    assert repository.list_scenarios(include_archived=True) == []


def test_an_operational_server_does_not_publish_an_interrupted_seed(tmp_path: Path) -> None:
    """발행 전에 멈춘 시드가 저장소에 하나뿐이어도 운영 서버는 발행을 잇지 않는다 — 시드가 공식
    v1 이 되는 길은 만들기와 복구 둘 다 닫는다."""
    repository = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    repository.initialize()
    seed_id = _seed_without_official(repository)

    result = ensure_initial_scenario(repository, seed=False)

    assert (result.status, result.release) == ("existing_without_official", None)
    assert repository.latest_official_release() is None
    assert [item.scenario_id for item in repository.list_scenarios()] == [seed_id]


@pytest.mark.parametrize(
    ("app_env", "seeded"), [("prod", False), ("", True)], ids=["operational", "development"]
)
def test_the_session_bootstrap_seeds_only_off_the_operational_server(
    tmp_path: Path, app_env: str, *, seeded: bool
) -> None:
    """첫 세션의 부트스트랩이 시드를 올리는가는 운영 서버 판정(Admin Area 잠금과 같은 뿌리) 하나로
    갈린다 — 개발 `app.py` · 사내 PC 는 지금처럼 시드로 시작한다."""
    _operational(app_env)
    assert builtin_seed_allowed() is seeded
    database_path = tmp_path / "bootstrap.duckdb"
    script = f"""
import streamlit as st

from capa_simulation.scenario_activation import bootstrap_latest_official_scenario

st.write(bootstrap_latest_official_scenario({str(database_path)!r}))
"""

    app = AppTest.from_string(script).run(timeout=60)

    assert not app.exception
    assert app.markdown[0].value == ("`True`" if seeded else "`False`")
    repository = DuckDBScenarioRepository(database_path)
    assert (repository.latest_official_release() is not None) is seeded
    assert bool(repository.list_scenarios(include_archived=True)) is seeded


# 불러온 리비전으로 본문을 그리는 화면 — 빈 운영 저장소에서 회색 「공식버전 없음」 한 줄이
# 서야 한다.
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
def empty_operational_store(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """아무것도 없는 디스크 — 시뮬레이션 DB 파일도 없다(화면이 처음 열 때 빈 저장소가 선다)."""
    root = tmp_path_factory.mktemp("empty_operational")
    return root / "scenario.duckdb", root / "equipment.duckdb"


@pytest.mark.parametrize("page_path", [spec.path for spec in ALL_SPECS])
def test_every_screen_of_an_empty_operational_server_stands_without_a_seed(
    page_path: str, empty_operational_store: tuple[Path, Path]
) -> None:
    """빈 디스크로 뜬 운영 서버 — 어느 화면도 예외 · 「데이터 Error」 마크 없이 서고, 리비전으로
    본문을 그리는 화면은 회색 「공식버전 없음」 한 줄이다. 어느 화면을 열어도 시드 시나리오 · 공식이
    생기지 않는다. 알림은 어느 화면이 내도 공식버전 없음 `SC-01` 의 「시나리오 없음」 갈래 한 줄이고
    (목록 관리에서 고를 시나리오가 없다) 「그 화면으로」 는 시나리오 관리 › DB 등록이다 — 시나리오
    관리 탭이 내는 것과 같은 줄이다(2026-11-14 물음 보드 seed (nopub))."""
    _operational()
    database, equipment = empty_operational_store
    app = AppTest.from_string(
        _page_script(page_path, database, equipment), default_timeout=300
    ).run()

    assert not list(app.exception), [element.message for element in app.exception]
    if page_path in REVISION_PAGES:
        bodies = [str(element.proto.body) for element in app._tree.get("html")]
        assert any(EMPTY_CLASS in body and "공식버전 없음" in body for body in bodies), page_path
        assert data_error_marks(app) == 0, page_path
        assert [note for note in states(app, "SC-01") if note["active"]], page_path
    expected = page_bootstrap.missing_official_note("empty")
    for note in states(app, "SC-01"):
        assert note == expected, page_path
    assert not [
        note
        for note in alert_notes(app)
        if note.get("kind") == "event" and "공식버전" in str(note.get("short", ""))
    ], page_path
    if database.exists():
        repository = DuckDBScenarioRepository(database)
        assert repository.latest_official_release() is None, page_path
        assert repository.list_scenarios(include_archived=True) == [], page_path


def test_the_app_on_an_empty_operational_server_names_no_seed_in_the_header(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`app.py` 를 운영 꼴(통합인증 꺼짐 · `APP_ENV` 운영)로 빈 디스크에 띄운 HOME — 머리 띠에 내장
    시드 이름 · 「공식 v1」 이 없고 본문은 회색 「공식버전 없음」 한 줄이다. 같은 디스크를 개발 꼴로
    띄우면 지금처럼 시드가 공식 v1 로 선다."""
    import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
    import capa_simulation.components.intro_overlay as intro_overlay
    import capa_simulation.components.intro_summary as intro_summary
    import capa_simulation.components.month_range_picker as month_range_picker
    import capa_simulation.settings as settings
    from capa_simulation.services.builtin_seed import BUILTIN_SEED_SCENARIO_NAME

    database = tmp_path / "scenario.duckdb"
    monkeypatch.setattr(settings, "DUCKDB_PATH", database)
    monkeypatch.setattr(settings, "EQUIPMENT_DUCKDB_PATH", tmp_path / "equipment.duckdb")
    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda *a, **k: None)
    monkeypatch.setattr(intro_overlay, "render_intro_overlay", lambda: None)
    monkeypatch.setattr(intro_summary, "_SUMMARY", lambda **kwargs: None)
    monkeypatch.setattr(
        month_range_picker, "_MONTH_RANGE_APPLY", lambda **kwargs: SimpleNamespace(apply=None)
    )
    app_path = Path(__file__).resolve().parents[1] / "app.py"

    _operational()
    app = AppTest.from_file(str(app_path), default_timeout=300).run()

    assert not list(app.exception), [element.message for element in app.exception]
    bodies = [str(element.proto.body) for element in app._tree.get("html")]
    assert any(EMPTY_CLASS in body and "공식버전 없음" in body for body in bodies)
    assert not any(BUILTIN_SEED_SCENARIO_NAME in body for body in bodies)
    repository = DuckDBScenarioRepository(database)
    assert repository.latest_official_release() is None
    assert repository.list_scenarios(include_archived=True) == []

    _operational("")
    app = AppTest.from_file(str(app_path), default_timeout=300).run()

    assert not list(app.exception), [element.message for element in app.exception]
    bodies = [str(element.proto.body) for element in app._tree.get("html")]
    assert any(BUILTIN_SEED_SCENARIO_NAME in body for body in bodies)
    assert repository.latest_official_release() is not None
