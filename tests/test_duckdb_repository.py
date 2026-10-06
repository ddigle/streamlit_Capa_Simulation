# Purpose: duckdb repository 관련 정상·예외·회귀 동작을 검증한다.

import pickle
from dataclasses import replace
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import pytest

import capa_simulation.persistence.cache as scenario_cache
from capa_simulation.io.core_data_source import load_core_data_contract
from capa_simulation.persistence import (
    DuckDBScenarioRepository,
    ScenarioCreate,
    ScenarioPreset,
    display_order_store,
    sync_state,
)
from capa_simulation.persistence._sql_helpers import connect, transaction
from capa_simulation.persistence.cache import (
    clear_scenario_repository,
    load_scenario_snapshot,
)
from capa_simulation.persistence.repository import (
    DATASET_TABLES,
    REFERENCE_TABLES,
    REVISION_TABLES,
)
from capa_simulation.services.display_order_editor import (
    ROUTE_SEQUENCE_COLUMNS,
    ROUTE_SEQUENCE_SCOPES,
    DisplayOrderValueClashError,
)
from capa_simulation.services.reference_transformer import build_reference_tables


def _reference_tables() -> dict[str, pd.DataFrame]:
    return {
        "RQ_PKG_PLAN": pd.DataFrame(
            {
                "생산계획년월": [202608],
                "양산구분": ["양산"],
                "CS": ["MP"],
                "제품정보": ["Product-A"],
                "Stack": ["8H"],
                "Capa Code": ["C1"],
                "Customer": ["Customer-A"],
                "생산수량": [100.0],
                "제품타입": ["HBM"],
                "Pack Code": ["PK-1"],
            }
        ),
        "RQ_YLD": pd.DataFrame(
            {
                "생산계획년월": [202608],
                "제품정보": ["Product-A"],
                "Stack": ["8H"],
                "WF 구분": ["Core"],
                "EDS_수율": [0.95],
                "BE_수율": [0.96],
            }
        ),
        "RQ_CHIP_QTY": pd.DataFrame(
            {
                "제품정보": ["Product-A"],
                "Stack": ["8H"],
                "WF 구분": ["Core"],
                "구분_Chip": [8.0],
                "Net Die": [1000.0],
            }
        ),
        "RQ_CHIP_EQ": pd.DataFrame(
            {
                "제품정보": ["Product-A"],
                "Stack": ["8H"],
                "WF 구분": ["Core"],
                "구분_Chip": [8.0],
                "구분_EQ": [24.0],
            }
        ),
        "RQ_DISPLAY_ORDER": pd.DataFrame(
            {
                "페이지 구분": ["HOME"],
                "탭 구분": ["계획"],
                "정렬우선순위": [1],
                "분류컬럼": ["제품정보"],
                "정렬방식": ["사용자지정"],
                "분류값": ["Product-A"],
                "값표시순서": [1],
                "활성여부": ["Y"],
            }
        ),
        "RQ_EQP_OWN": pd.DataFrame(
            {"생산계획년월": [202608], "공정": ["Process-A"], "설비보유": [10.0]}
        ),
        "RQ_EQP_LENT": pd.DataFrame(
            {
                "생산계획년월": [202608],
                "공정": ["Process-A"],
                "설비대여평가": [1.0],
            }
        ),
        "RQ_EQP_AVBL": pd.DataFrame(
            {"생산계획년월": [202608], "공정": ["Process-A"], "가용대수": [9.0]}
        ),
        "RQ_UPEH": pd.DataFrame(
            {
                "생산계획년월": [202608],
                "Area_Name": ["Main"],
                "공정": ["Process-A"],
                "STEP_SEQ": ["P100"],
                "MCP_SEQ": ["1A"],
                "양산구분": ["양산"],
                "제품정보": ["Product-A"],
                "Stack": ["8H"],
                "WF 구분": ["Core"],
                "소요기준": ["CHIP"],
                "UPEH": [1000.0],
                "ST": [None],
            }
        ),
        "RQ_RUN_RATE": pd.DataFrame(
            {
                "생산계획년월": [202608],
                "공정": ["Process-A"],
                "양산구분": ["양산"],
                "CAPA_RUN_RATE": [0.9],
            }
        ),
        "RQ_VITAL": pd.DataFrame(
            {
                "생산계획년월": [202608],
                "공정": ["Process-A"],
                "양산구분": ["양산"],
                "편중률": [1.05],
            }
        ),
        "RQ_MODULE": pd.DataFrame({"공정": ["Process-A"], "모듈수": [2.0]}),
        "RQ_RUN_DAY": pd.DataFrame(
            {"생산계획년월": [202608], "공정": ["Process-A"], "RUN_DAY": [31.0]}
        ),
        "RQ_LOT_RATIO": pd.DataFrame(
            {
                "생산계획년월": [202608],
                "Area_Name": ["Main"],
                "공정": ["Process-A"],
                "STEP_SEQ": ["P100"],
                "MCP_SEQ": ["1A"],
                "양산구분": ["양산"],
                "제품정보": ["Product-A"],
                "Stack": ["8H"],
                "WF 구분": ["Core"],
                "Lot 측정률": [1.0],
            }
        ),
        "RQ_WF_RATIO": pd.DataFrame(
            {
                "생산계획년월": [202608],
                "Area_Name": ["Main"],
                "공정": ["Process-A"],
                "STEP_SEQ": ["P100"],
                "MCP_SEQ": ["1A"],
                "양산구분": ["양산"],
                "제품정보": ["Product-A"],
                "Stack": ["8H"],
                "WF 구분": ["Core"],
                "WF측정률": [1.0],
            }
        ),
        "RQ_REQB": pd.DataFrame(
            {
                "생산계획년월": [202608],
                "Area_Name": ["Main"],
                "공정": ["Process-A"],
                "양산구분": ["양산"],
                "제품정보": ["Product-A"],
                "Stack": ["8H"],
                "Capa Code": ["C1"],
                "Customer": ["Customer-A"],
                "CS": ["MP"],
                "WF 구분": ["Core"],
                "STEP_SEQ": ["P100"],
                "MCP_SEQ": ["1A"],
                "소요기준": ["CHIP"],
            }
        ),
    }


def _metadata(name: str = "Scenario A") -> ScenarioCreate:
    return ScenarioCreate(
        scenario_name=name,
        source_simulation_code="SIM-001",
        source_simulation_name="Source simulation",
        source_type="TEST",
        pipeline_version="test-v1",
    )


def _core_data_source(*, quantity: float = 100.0) -> pd.DataFrame:
    contract = load_core_data_contract()
    values: dict[str, object] = {
        column.name: (
            "기준값" if column.dtype == "string" else 1 if column.dtype == "integer" else 1.0
        )
        for column in contract.columns
    }
    values.update(
        {
            "시뮬레이션 ID": "SIM-001",
            "PLAN ID": "PLAN-001",
            "생산계획년월": 202608,
            "제품정보": "Product-A",
            "생산수량": quantity,
            "Stack": "8H",
            "Customer": "Customer-A",
            "CS": "MP",
            "WF 구분": "Core",
            "Capa Code": "C1",
            "계획기초정보여부": "Y",
            "Area_Name": "Main",
            "공정": "Process-A",
            "소요기준": "CHIP",
            "STEP_SEQ": "P100",
            "MCP_SEQ": "1A",
        }
    )
    return pd.DataFrame([values], columns=[column.name for column in contract.columns])


def _repository(path: Path) -> DuckDBScenarioRepository:
    repository = DuckDBScenarioRepository(path)
    applied = repository.initialize()
    assert applied
    assert applied[0] == 1
    assert repository.initialize() == ()
    return repository


def test_reads_succeed_while_another_connection_is_open(tmp_path: Path) -> None:
    """읽기와 쓰기가 서로 다른 configuration으로 열리면 DuckDB가 연결을 거부한다."""
    database_path = tmp_path / "scenario.duckdb"
    repository = _repository(database_path)

    # 다른 브라우저 세션이 저장 중인 상황을 흉내낸다. 읽기 경로가 read_only=True로
    # 되돌아가거나 공용 connect() 를 우회해 직접 열면 이 지점에서 ConnectionException이 난다.
    with connect(database_path):
        assert repository.list_scenarios() == []
        assert repository.latest_official_release() is None


def test_create_and_load_scenario_snapshot(tmp_path: Path) -> None:
    database_path = tmp_path / "scenario.duckdb"
    repository = _repository(database_path)
    source = _reference_tables()
    preset = ScenarioPreset(
        start_month=202608,
        end_month=202608,
        included_processes=("Process-A",),
        standard_target_processes=("Process-A",),
    )

    snapshot = repository.create_scenario(_metadata(), source, preset)

    assert snapshot.scenario.active_revision_no == 1
    assert snapshot.preset == preset
    assert snapshot.preset.standard_target_processes == ("Process-A",)
    assert set(snapshot.tables) == set(REFERENCE_TABLES)
    pd.testing.assert_frame_equal(
        snapshot.tables["RQ_PKG_PLAN"],
        source["RQ_PKG_PLAN"],
        check_dtype=False,
    )
    assert repository.list_scenarios() == [snapshot.scenario]
    assert repository.list_revisions(snapshot.scenario.scenario_id) == [snapshot.revision]
    with duckdb.connect(str(database_path), read_only=True) as connection:
        schemas = {
            str(row[0])
            for row in connection.execute(
                "SELECT schema_name FROM information_schema.schemata"
            ).fetchall()
        }
    assert "equipment_ops" not in schemas
    assert "equipment_meta" not in schemas


def test_revision_tables_are_written_only_to_the_revision(tmp_path: Path) -> None:
    """리비전 표 14개는 리비전(`rev_data`)에만, 나머지 둘은 데이터셋(`ref_data`)에만 적는다.

    스냅샷은 리비전 표를 `rev_data` 에서만 읽고 리비전은 불변이라 데이터셋 사본은 읽는 곳 없이
    행만 늘었다(2026-10-06 사용자 결정 B3). 스냅샷 왕복은 그대로다.
    """
    database_path = tmp_path / "scenario.duckdb"
    repository = _repository(database_path)
    source = _reference_tables()
    snapshot = repository.create_scenario(
        _metadata(), source, ScenarioPreset(202608, 202608, ("Process-A",))
    )

    assert set(DATASET_TABLES) == {"RQ_DISPLAY_ORDER", "RQ_MODULE"}
    assert set(DATASET_TABLES) | set(REVISION_TABLES) == set(REFERENCE_TABLES)
    with duckdb.connect(str(database_path), read_only=True) as connection:
        for logical_name, table_name in REFERENCE_TABLES.items():
            dataset_rows = connection.execute(
                f"SELECT count(*) FROM ref_data.{table_name} WHERE dataset_id = ?",
                [snapshot.scenario.dataset_id],
            ).fetchone()
            in_dataset = int(dataset_rows[0]) if dataset_rows else 0
            if logical_name in REVISION_TABLES:
                assert in_dataset == 0, logical_name
                revision_rows = connection.execute(
                    f"SELECT count(*) FROM rev_data.{table_name} WHERE revision_id = ?",
                    [snapshot.revision.revision_id],
                ).fetchone()
                assert revision_rows is not None
                assert int(revision_rows[0]) == len(source[logical_name]), logical_name
            else:
                assert in_dataset == len(source[logical_name]), logical_name
    reloaded = repository.load_revision(
        snapshot.revision.revision_id, apply_global_display_order=False
    )
    for logical_name in REFERENCE_TABLES:
        assert len(reloaded.tables[logical_name]) == len(source[logical_name]), logical_name


def test_global_display_order_migrates_and_replaces_independently(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "scenario.duckdb")
    source = _reference_tables()
    snapshot = repository.create_scenario(
        _metadata(),
        source,
        ScenarioPreset(202608, 202608, ("Process-A",)),
    )
    fallback = source["RQ_DISPLAY_ORDER"].assign(분류값="Fallback")

    initial = repository.initialize_global_display_order(fallback)

    assert initial.version == 1
    assert initial.source == "기존 시나리오 표시순서 이관"
    assert initial.rules["분류값"].tolist() == ["Product-A"]

    revised_rules = initial.rules.assign(분류값="Product-B")
    revised = repository.replace_global_display_order(
        revised_rules,
        source="테스트 직접 편집",
    )

    assert revised.version == 2
    assert revised.source == "테스트 직접 편집"
    assert revised.rules["분류값"].tolist() == ["Product-B"]
    assert repository.load_revision(snapshot.revision.revision_id).tables["RQ_DISPLAY_ORDER"][
        "분류값"
    ].tolist() == ["Product-B"]


def test_global_display_order_init_marks_sync_dirty_only_when_it_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """프로필이 이미 있으면 기동마다 도는 초기화가 동기화 dirty 를 세우지 않는다."""
    database_path = tmp_path / "scenario.duckdb"
    repository = _repository(database_path)
    marked: list[Path] = []
    monkeypatch.setattr(sync_state, "mark_dirty", marked.append)
    fallback = _reference_tables()["RQ_DISPLAY_ORDER"]

    created = repository.initialize_global_display_order(fallback)

    assert created.version == 1
    assert created.source == "초기 표시순서 시드"
    assert marked == [database_path.resolve()]

    marked.clear()
    reopened = DuckDBScenarioRepository(database_path)
    again = reopened.initialize_global_display_order(fallback.assign(분류값="Ignored"))

    assert marked == []
    assert again.version == 1
    assert again.rules["분류값"].tolist() == ["Product-A"]


def test_global_display_order_init_still_augments_an_existing_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """프로필이 있어도 경로 식별 컬럼 보강은 매번 확인하고 필요할 때만 쓴다."""
    database_path = tmp_path / "scenario.duckdb"
    repository = _repository(database_path)
    page, tab = ROUTE_SEQUENCE_SCOPES[0]
    raw = _reference_tables()["RQ_DISPLAY_ORDER"].assign(**{"페이지 구분": page, "탭 구분": tab})
    with connect(database_path) as connection:
        display_order_store.insert_global_display_order(
            connection, raw, version=1, source="보강 전 저장본"
        )
    marked: list[Path] = []
    monkeypatch.setattr(sync_state, "mark_dirty", marked.append)

    augmented = repository.initialize_global_display_order(raw)

    assert augmented.version == 2
    assert augmented.source == "경로 식별 컬럼 하위 배치 자동 보강"
    assert set(ROUTE_SEQUENCE_COLUMNS) <= set(augmented.rules["분류컬럼"])
    assert marked == [database_path.resolve()]

    marked.clear()
    assert repository.initialize_global_display_order(raw).version == 2
    assert marked == []


def _case_clash_rules(page: str, tab: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "페이지 구분": [page] * 2,
            "탭 구분": [tab] * 2,
            "정렬우선순위": [1] * 2,
            "분류컬럼": ["WF 구분"] * 2,
            "정렬방식": ["사용자지정"] * 2,
            "분류값": ["Top", "TOP"],
            "값표시순서": [1, 2],
            "활성여부": ["Y"] * 2,
        }
    )


def test_saving_a_case_clash_is_refused(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "scenario.duckdb")
    created = repository.initialize_global_display_order(_reference_tables()["RQ_DISPLAY_ORDER"])

    with pytest.raises(DisplayOrderValueClashError, match="`Top` · `TOP`"):
        repository.replace_global_display_order(
            _case_clash_rules("부하량", "환산"), source="대소문자만 다른 값"
        )
    assert repository.load_global_display_order().version == created.version


def test_a_stored_case_clash_does_not_stop_startup(tmp_path: Path) -> None:
    """저장 검사가 생기기 전에 저장된 프로필이 있어도 기동은 막히지 않는다.

    기동마다 도는 경로 식별 컬럼 보강이 그 프로필을 저장 검사로 다시 보면 앱 전체가 열리지
    않는다. 보강은 미루고 프로필을 그대로 돌려준다 — 겹친 값은 화면과 Admin 탭이 알린다.
    """
    database_path = tmp_path / "scenario.duckdb"
    repository = _repository(database_path)
    page, tab = ROUTE_SEQUENCE_SCOPES[0]
    stored = _case_clash_rules(page, tab)
    with connect(database_path) as connection:
        display_order_store.insert_global_display_order(
            connection, stored, version=1, source="검사 전 저장본"
        )

    profile = repository.initialize_global_display_order(_reference_tables()["RQ_DISPLAY_ORDER"])

    assert profile.version == 1
    assert profile.rules["분류값"].tolist() == ["Top", "TOP"]
    assert not set(ROUTE_SEQUENCE_COLUMNS) & set(profile.rules["분류컬럼"])


def test_a_seed_with_a_case_clash_does_not_stop_startup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """기동마다 읽는 로컬 시드(`data/input/RQ_DISPLAY_ORDER.csv`)에 겹친 값이 있어도 기동한다.

    시드는 저장된 프로필이 있으면 쓰이지도 않는데, 저장 검사로 읽으면 그 파일 한 줄 때문에
    앱 전체가 열리지 않는다. 프로필이 없으면 시드가 그대로 첫 프로필이 되고 화면이 알린다.
    """
    from capa_simulation.services import builtin_seed

    seed_csv = tmp_path / "RQ_DISPLAY_ORDER.csv"
    seed_csv.write_bytes(
        _case_clash_rules("부하량", "환산").to_csv(index=False).encode("utf-8-sig")
    )
    monkeypatch.setattr(builtin_seed, "LOCAL_DISPLAY_ORDER_CSV_PATH", seed_csv)
    fallback = builtin_seed.load_builtin_display_order()
    assert fallback["분류값"].tolist() == ["Top", "TOP"]

    fresh = _repository(tmp_path / "fresh.duckdb").initialize_global_display_order(fallback)
    assert fresh.rules["분류값"].tolist() == ["Top", "TOP"]

    existing = _repository(tmp_path / "existing.duckdb")
    created = existing.initialize_global_display_order(_reference_tables()["RQ_DISPLAY_ORDER"])
    again = existing.initialize_global_display_order(fallback)
    assert again.version == created.version
    assert again.rules["분류값"].tolist() == created.rules["분류값"].tolist()


def test_transaction_surfaces_the_commit_failure_cause(tmp_path: Path) -> None:
    """COMMIT 이 실패하면 뒤따르는 ROLLBACK 오류가 아니라 실패 원인이 올라온다."""
    database_path = tmp_path / "commit.duckdb"
    with connect(database_path) as connection:
        connection.execute("CREATE TABLE t (k INTEGER PRIMARY KEY, v INTEGER)")
    other = connect(database_path)
    writer = connect(database_path)
    try:
        with pytest.raises(duckdb.TransactionException, match="Failed to commit"):
            with transaction(writer):
                writer.execute("INSERT INTO t VALUES (1, 2)")
                other.execute("INSERT INTO t VALUES (1, 1)")

        assert other.execute("SELECT k, v FROM t").fetchall() == [(1, 1)]
        with transaction(writer):
            writer.execute("INSERT INTO t VALUES (2, 2)")
        assert other.execute("SELECT k, v FROM t ORDER BY k").fetchall() == [(1, 1), (2, 2)]
    finally:
        writer.close()
        other.close()


def test_transaction_body_failure_still_rolls_back_and_reraises(tmp_path: Path) -> None:
    database_path = tmp_path / "body.duckdb"
    with connect(database_path) as connection:
        connection.execute("CREATE TABLE t (k INTEGER PRIMARY KEY)")
        with pytest.raises(ValueError, match="본문 실패"):
            with transaction(connection):
                connection.execute("INSERT INTO t VALUES (1)")
                raise ValueError("본문 실패")
        assert connection.execute("SELECT count(*) FROM t").fetchone() == (0,)


def test_cached_scenario_load_always_overlays_global_display_order(tmp_path: Path) -> None:
    database_path = tmp_path / "scenario.duckdb"
    repository = _repository(database_path)
    source = _reference_tables()
    first = repository.create_scenario(
        _metadata("First"),
        source,
        ScenarioPreset(202608, 202608, ("Process-A",)),
    )
    second_source = dict(source)
    second_source["RQ_DISPLAY_ORDER"] = source["RQ_DISPLAY_ORDER"].assign(분류값="Scenario-B")
    second = repository.create_scenario(
        _metadata("Second"),
        second_source,
        ScenarioPreset(202608, 202608, ("Process-A",)),
    )
    repository.initialize_global_display_order(source["RQ_DISPLAY_ORDER"])
    repository.replace_global_display_order(
        source["RQ_DISPLAY_ORDER"].assign(분류값="Global"),
        source="테스트 공용값",
    )
    clear_scenario_repository()

    first_loaded = load_scenario_snapshot(str(database_path), first.revision.revision_id)
    second_loaded = load_scenario_snapshot(str(database_path), second.revision.revision_id)

    assert first_loaded.tables["RQ_DISPLAY_ORDER"]["분류값"].tolist() == ["Global"]
    assert second_loaded.tables["RQ_DISPLAY_ORDER"]["분류값"].tolist() == ["Global"]
    clear_scenario_repository()


def test_snapshot_cache_serializes_plain_payload_after_model_reload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path / "scenario.duckdb")
    source = _reference_tables()
    snapshot = repository.create_scenario(
        _metadata("Reload-safe"),
        source,
        ScenarioPreset(202608, 202608, ("Process-A",)),
    )
    display_order = repository.initialize_global_display_order(source["RQ_DISPLAY_ORDER"])

    class StaleSnapshot:
        def __init__(self) -> None:
            self.scenario = snapshot.scenario
            self.revision = snapshot.revision
            self.preset = snapshot.preset
            self.tables = snapshot.tables

        def __reduce__(self) -> object:
            raise pickle.PicklingError("stale ScenarioSnapshot class")

    class StaleDisplayOrder:
        def __init__(self) -> None:
            self.version = display_order.version
            self.source = display_order.source
            self.updated_at = display_order.updated_at
            self.rules = display_order.rules

        def __reduce__(self) -> object:
            raise pickle.PicklingError("stale GlobalDisplayOrder class")

    stale_snapshot = StaleSnapshot()
    stale_display_order = StaleDisplayOrder()

    class FakeRepository:
        def load_revision(
            self, _revision_id: str, *, apply_global_display_order: bool = True
        ) -> StaleSnapshot:
            return stale_snapshot

        def load_global_display_order(self) -> StaleDisplayOrder:
            return stale_display_order

    with pytest.raises(pickle.PicklingError, match="stale ScenarioSnapshot"):
        pickle.dumps(stale_snapshot)
    with pytest.raises(pickle.PicklingError, match="stale GlobalDisplayOrder"):
        pickle.dumps(stale_display_order)

    monkeypatch.setattr(
        scenario_cache,
        "get_scenario_repository",
        lambda _database_path: FakeRepository(),
    )
    scenario_cache._load_scenario_snapshot_payload.clear()
    scenario_cache._load_global_display_order_payload.clear()

    restored_snapshot = scenario_cache.load_scenario_snapshot(
        str(tmp_path / "reload-safe.duckdb"),
        snapshot.revision.revision_id,
    )
    restored_display_order = scenario_cache.load_global_display_order(
        str(tmp_path / "reload-safe.duckdb")
    )

    assert restored_snapshot.scenario == snapshot.scenario
    assert restored_snapshot.revision == snapshot.revision
    assert restored_snapshot.preset == snapshot.preset
    assert restored_snapshot.tables.keys() == snapshot.tables.keys()
    for table_name, expected in snapshot.tables.items():
        pd.testing.assert_frame_equal(restored_snapshot.tables[table_name], expected)
    assert restored_display_order.version == display_order.version
    pd.testing.assert_frame_equal(restored_display_order.rules, display_order.rules)
    scenario_cache._load_scenario_snapshot_payload.clear()
    scenario_cache._load_global_display_order_payload.clear()


def test_new_revision_replaces_only_revision_owned_tables(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "scenario.duckdb")
    source = _reference_tables()
    initial = repository.create_scenario(
        _metadata(),
        source,
        ScenarioPreset(202608, 202608, ("Process-A",)),
    )
    revised_tables = {name: frame.copy(deep=True) for name, frame in initial.tables.items()}
    revised_tables["RQ_PKG_PLAN"].loc[0, "생산수량"] = 250.0
    revised_tables["RQ_REQB"].loc[0, "STEP_SEQ"] = "P200"
    revised_tables["RQ_EQP_AVBL"].loc[0, "가용대수"] = 12.0
    revised_tables["RQ_CHIP_QTY"].loc[0, "Net Die"] = 9999.0
    revised_preset = ScenarioPreset(
        202608,
        202608,
        (),
        standard_target_processes=("Process-A",),
    )

    revised = repository.save_revision(
        initial.scenario.scenario_id,
        revised_tables,
        revised_preset,
        revision_name="Revision 2",
    )

    assert revised.revision.revision_no == 2
    assert revised.preset.included_processes == ()
    assert revised.preset.standard_target_processes == ("Process-A",)
    assert revised.tables["RQ_PKG_PLAN"].loc[0, "생산수량"] == pytest.approx(250.0)
    assert revised.tables["RQ_REQB"].loc[0, "STEP_SEQ"] == "P200"
    assert revised.tables["RQ_EQP_AVBL"].loc[0, "가용대수"] == pytest.approx(12.0)
    # RQ_CHIP_QTY 는 가상 제품 복제 등록을 위해 리비전 소유로 승격됐다. 예전에는
    # 데이터셋 소유라 저장해도 원본값이 돌아왔다.
    assert revised.tables["RQ_CHIP_QTY"].loc[0, "Net Die"] == pytest.approx(9999.0)
    loaded_initial = repository.load_revision(initial.revision.revision_id)
    assert loaded_initial.tables["RQ_PKG_PLAN"].loc[0, "생산수량"] == pytest.approx(100.0)
    assert loaded_initial.tables["RQ_REQB"].loc[0, "STEP_SEQ"] == "P100"
    assert loaded_initial.tables["RQ_EQP_AVBL"].loc[0, "가용대수"] == pytest.approx(9.0)
    # 이전 리비전은 승격 뒤에도 자기 스냅샷을 그대로 지킨다.
    assert loaded_initial.tables["RQ_CHIP_QTY"].loc[0, "Net Die"] == pytest.approx(1000.0)


def test_failed_registration_rolls_back_all_metadata(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "scenario.duckdb")
    source = _reference_tables()
    source["RQ_PKG_PLAN"] = source["RQ_PKG_PLAN"].drop(columns="생산수량")

    with pytest.raises(ValueError, match="컬럼 계약"):
        repository.create_scenario(
            _metadata(),
            source,
            ScenarioPreset(202608, 202608, ("Process-A",)),
        )

    assert repository.list_scenarios() == []


def test_revision_can_branch_from_an_older_revision(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "scenario.duckdb")
    initial = repository.create_scenario(
        _metadata(),
        _reference_tables(),
        ScenarioPreset(202608, 202608, ("Process-A",)),
    )
    revision_two = repository.save_revision(
        initial.scenario.scenario_id,
        initial.tables,
        initial.preset,
        revision_name="Revision 2",
    )

    branched = repository.save_revision(
        initial.scenario.scenario_id,
        initial.tables,
        initial.preset,
        revision_name="Branch from revision 1",
        parent_revision_id=initial.revision.revision_id,
    )

    assert revision_two.revision.revision_no == 2
    assert branched.revision.revision_no == 3
    assert branched.revision.parent_revision_id == initial.revision.revision_id


def test_revision_rejects_parent_from_another_scenario(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "scenario.duckdb")
    source = _reference_tables()
    preset = ScenarioPreset(202608, 202608, ("Process-A",))
    first = repository.create_scenario(_metadata("First"), source, preset)
    second = repository.create_scenario(_metadata("Second"), source, preset)

    with pytest.raises(ValueError, match="현재 시나리오에 속하지 않습니다"):
        repository.save_revision(
            first.scenario.scenario_id,
            first.tables,
            first.preset,
            revision_name="Invalid parent",
            parent_revision_id=second.revision.revision_id,
        )

    assert repository.list_revisions(first.scenario.scenario_id) == [first.revision]


def test_delete_removes_every_row_the_scenario_owned(tmp_path: Path) -> None:
    """삭제는 논리 상태 변경이 아니라 물리 삭제다. 주인 없는 행이 남으면 안 된다."""
    database_path = tmp_path / "scenario.duckdb"
    repository = _repository(database_path)
    doomed = repository.create_scenario(
        _metadata(),
        _reference_tables(),
        ScenarioPreset(202608, 202608, ("Process-A",)),
        source_data=_core_data_source(),
    )
    repository.save_revision(
        doomed.scenario.scenario_id,
        doomed.tables,
        doomed.preset,
        revision_name="두 번째",
    )
    kept = repository.create_scenario(
        _metadata("Kept"),
        _reference_tables(),
        ScenarioPreset(202608, 202608, ("Process-A",)),
    )

    repository.delete_scenario(doomed.scenario.scenario_id)

    assert [scenario.scenario_id for scenario in repository.list_scenarios()] == [
        kept.scenario.scenario_id
    ]
    with duckdb.connect(str(database_path), read_only=True) as connection:
        leftovers = _rows_owned_by(
            connection, doomed.scenario.scenario_id, doomed.scenario.dataset_id
        )
    assert leftovers == {}


def _rows_owned_by(
    connection: duckdb.DuckDBPyConnection,
    scenario_id: str,
    dataset_id: str,
) -> dict[str, int]:
    """시나리오·데이터셋·리비전 소유 컬럼으로 아직 남아 있는 행 수."""
    revision_ids = [
        str(row[0])
        for row in connection.execute(
            "SELECT revision_id FROM app_meta.scenario_revision WHERE scenario_id = ?",
            [scenario_id],
        ).fetchall()
    ]
    tables = connection.execute(
        """
        SELECT table_schema, table_name, list(column_name)
        FROM information_schema.columns
        WHERE table_schema IN ('app_meta', 'raw_data', 'ref_data', 'rev_data', 'result_data')
        GROUP BY table_schema, table_name
        """
    ).fetchall()
    remaining: dict[str, int] = {}
    for schema, table, columns in tables:
        present = set(columns)
        if "scenario_id" in present:
            clause, parameters = "scenario_id = ?", [scenario_id]
        elif "dataset_id" in present:
            clause, parameters = "dataset_id = ?", [dataset_id]
        elif "revision_id" in present and revision_ids:
            placeholders = ", ".join("?" for _ in revision_ids)
            clause, parameters = f"revision_id IN ({placeholders})", list(revision_ids)
        else:
            continue
        row = connection.execute(
            f"SELECT count(*) FROM {schema}.{table} WHERE {clause}", parameters
        ).fetchone()
        count = 0 if row is None else int(row[0])
        if count:
            remaining[f"{schema}.{table}"] = count
    return remaining


def test_removing_a_scenario_clears_the_shared_comparison_profile(tmp_path: Path) -> None:
    """공용 GAP 비교 프로필은 시나리오 소유가 아니라 참조다.

    소유로 보면 자동 발견이 단일 행 프로필을 통째로 지워 프로필 자체가 사라지고
    `version` 도 안 올라가, 다른 세션이 사라진 시나리오를 계속 비교 대상으로 쥔다.
    """
    repository = _repository(tmp_path / "capa.duckdb")
    kept = repository.create_scenario(
        _metadata("Kept"),
        _reference_tables(),
        ScenarioPreset(202608, 202608, ("Process-A",)),
        source_data=_core_data_source(),
    )
    doomed = repository.create_scenario(
        _metadata("Doomed"),
        _reference_tables(),
        ScenarioPreset(202608, 202608, ("Process-A",)),
    )
    repository.replace_global_comparison_scenario(
        doomed.scenario.scenario_id,
        doomed.revision.revision_id,
        source="test",
    )
    before = repository.load_global_comparison_scenario()

    repository.delete_scenario(doomed.scenario.scenario_id)

    after = repository.load_global_comparison_scenario()
    # 프로필 행 자체는 살아 있고 대상만 비워진다.
    assert after.scenario_id is None
    assert after.revision_id is None
    # `version` 이 올라가야 다른 세션 캐시가 낡은 대상을 버린다.
    assert after.version > before.version
    # 남은 시나리오를 가리키던 값이었다면 건드리지 않는다.
    repository.replace_global_comparison_scenario(
        kept.scenario.scenario_id,
        kept.revision.revision_id,
        source="test",
    )
    untouched = repository.load_global_comparison_scenario()
    assert untouched.scenario_id == kept.scenario.scenario_id


def test_removing_a_scenario_keeps_the_shared_summary_notice(tmp_path: Path) -> None:
    """공지는 시나리오에 딸린 값이 아니다.

    소유 컬럼을 두면 `_owned_tables` 자동 발견이 시나리오 소유로 보고 단일 행을 함께
    지운다. 시나리오 하나를 지웠다고 팀 공지가 사라지면 안 된다.
    """
    repository = _repository(tmp_path / "capa.duckdb")
    repository.replace_global_summary_note("남아 있어야 한다", source="test")
    doomed = repository.create_scenario(
        _metadata("Doomed"),
        _reference_tables(),
        ScenarioPreset(202608, 202608, ("Process-A",)),
        source_data=_core_data_source(),
    )
    before = repository.load_global_summary_note()

    repository.delete_scenario(doomed.scenario.scenario_id)

    after = repository.load_global_summary_note()
    assert after.note == "남아 있어야 한다"
    # 참조가 아니라 무관한 값이므로 `version` 도 그대로여야 한다.
    assert after.version == before.version


def test_archiving_clears_the_shared_comparison_profile(tmp_path: Path) -> None:
    """보관본은 목록에 없다. 비교 대상으로 남겨 두면 매 세션 되살렸다 버리는 왕복이 생긴다."""
    repository = _repository(tmp_path / "capa.duckdb")
    repository.create_scenario(
        _metadata("Kept"),
        _reference_tables(),
        ScenarioPreset(202608, 202608, ("Process-A",)),
        source_data=_core_data_source(),
    )
    hidden = repository.create_scenario(
        _metadata("Hidden"),
        _reference_tables(),
        ScenarioPreset(202608, 202608, ("Process-A",)),
    )
    repository.replace_global_comparison_scenario(
        hidden.scenario.scenario_id,
        hidden.revision.revision_id,
        source="test",
    )
    before = repository.load_global_comparison_scenario()

    repository.archive_scenario(hidden.scenario.scenario_id)

    after = repository.load_global_comparison_scenario()
    assert after.scenario_id is None
    assert after.version > before.version


def test_archiving_hides_the_scenario_but_keeps_every_row(tmp_path: Path) -> None:
    """보관은 목록에서 숨길 뿐이다. 행이 남아 있어야 되돌릴 수 있다."""
    repository = _repository(tmp_path / "capa.duckdb")
    kept = repository.create_scenario(
        _metadata("Kept"),
        _reference_tables(),
        ScenarioPreset(202608, 202608, ("Process-A",)),
        source_data=_core_data_source(),
    )
    hidden = repository.create_scenario(
        _metadata("Hidden"),
        _reference_tables(),
        ScenarioPreset(202608, 202608, ("Process-A",)),
    )

    repository.archive_scenario(hidden.scenario.scenario_id)

    assert [scenario.scenario_id for scenario in repository.list_scenarios()] == [
        kept.scenario.scenario_id
    ]
    assert {
        scenario.scenario_id for scenario in repository.list_scenarios(include_archived=True)
    } == {kept.scenario.scenario_id, hidden.scenario.scenario_id}
    # 행이 남아 있으므로 리비전을 그대로 읽을 수 있다. 이것이 삭제와의 차이다.
    assert repository.load_revision(hidden.revision.revision_id).scenario.scenario_id == (
        hidden.scenario.scenario_id
    )

    repository.restore_scenario(hidden.scenario.scenario_id)

    assert {scenario.scenario_id for scenario in repository.list_scenarios()} == {
        kept.scenario.scenario_id,
        hidden.scenario.scenario_id,
    }


def test_archived_scenarios_reject_new_revisions_and_official_release(
    tmp_path: Path,
) -> None:
    """보관본은 읽기 전용이다. 숨은 시나리오가 자라면 되돌릴 지점이 흐려진다."""
    repository = _repository(tmp_path / "capa.duckdb")
    snapshot = repository.create_scenario(
        _metadata("Frozen"),
        _reference_tables(),
        ScenarioPreset(202608, 202608, ("Process-A",)),
        source_data=_core_data_source(),
    )
    repository.archive_scenario(snapshot.scenario.scenario_id)

    with pytest.raises(ValueError, match="보관된 시나리오에는 새 리비전을"):
        repository.save_revision(
            snapshot.scenario.scenario_id,
            snapshot.tables,
            snapshot.preset,
            revision_name="두 번째",
        )
    with pytest.raises(ValueError, match="보관된 시나리오는 공식버전으로"):
        repository.publish_official_revision(
            snapshot.scenario.scenario_id,
            snapshot.revision.revision_id,
            release_name="v1",
        )


def test_reordering_compares_against_active_scenarios_only(tmp_path: Path) -> None:
    """목록이 보관본을 빼고 그리므로 순서 대조도 활성만 본다.

    전체와 대조하면 보관본이 하나만 생겨도 「순서 저장」이 항상 ValueError 로 죽는다.
    """
    repository = _repository(tmp_path / "capa.duckdb")
    first = repository.create_scenario(
        _metadata("First"),
        _reference_tables(),
        ScenarioPreset(202608, 202608, ("Process-A",)),
        source_data=_core_data_source(),
    )
    second = repository.create_scenario(
        _metadata("Second"),
        _reference_tables(),
        ScenarioPreset(202608, 202608, ("Process-A",)),
    )
    hidden = repository.create_scenario(
        _metadata("Hidden"),
        _reference_tables(),
        ScenarioPreset(202608, 202608, ("Process-A",)),
    )
    repository.archive_scenario(hidden.scenario.scenario_id)

    reordered = repository.reorder_scenarios(
        [second.scenario.scenario_id, first.scenario.scenario_id]
    )

    assert [scenario.scenario_id for scenario in reordered] == [
        second.scenario.scenario_id,
        first.scenario.scenario_id,
    ]


def test_list_order_is_saved_and_rejects_a_partial_list(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "scenario.duckdb")
    first = repository.create_scenario(
        _metadata("First"),
        _reference_tables(),
        ScenarioPreset(202608, 202608, ("Process-A",)),
    )
    second = repository.create_scenario(
        _metadata("Second"),
        _reference_tables(),
        ScenarioPreset(202608, 202608, ("Process-A",)),
    )
    ids = [first.scenario.scenario_id, second.scenario.scenario_id]

    reordered = repository.reorder_scenarios(ids)

    assert [scenario.scenario_id for scenario in reordered] == ids
    assert [scenario.scenario_id for scenario in repository.list_scenarios()] == ids
    # 최근 수정 순서였다면 나중에 만든 쪽이 앞에 온다. 지정한 순서가 그것을 이긴다.
    assert reordered[0].scenario_name == "First"
    with pytest.raises(ValueError, match="전체를 한 번에"):
        repository.reorder_scenarios([ids[0]])


def test_scenario_can_be_renamed_without_changing_revision(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "scenario.duckdb")
    snapshot = repository.create_scenario(
        _metadata(),
        _reference_tables(),
        ScenarioPreset(202608, 202608, ("Process-A",)),
    )

    renamed = repository.rename_scenario(snapshot.scenario.scenario_id, "Renamed scenario")

    assert renamed.scenario_name == "Renamed scenario"
    assert renamed.active_revision_id == snapshot.revision.revision_id


def test_a_second_scenario_with_the_same_name_is_refused(tmp_path: Path) -> None:
    """같은 이름이 둘이면 사이드바·보관함에서 가릴 수 없다(2026-10-01 사용자 결정).

    보관본도 센다 — 되돌리면 목록에 같은 이름이 둘이 된다. 앞뒤 공백은 떼고 대조한다.
    """
    repository = _repository(tmp_path / "scenario.duckdb")
    preset = ScenarioPreset(202608, 202608, ("Process-A",))
    first = repository.create_scenario(_metadata("같은 이름"), _reference_tables(), preset)

    with pytest.raises(ValueError, match="같은 이름의 시나리오가 이미 있습니다"):
        repository.create_scenario(_metadata(" 같은 이름 "), _reference_tables(), preset)

    repository.archive_scenario(first.scenario.scenario_id)
    with pytest.raises(ValueError, match="같은 이름의 시나리오가 이미 있습니다"):
        repository.create_scenario(_metadata("같은 이름"), _reference_tables(), preset)
    # 막힌 시도는 아무것도 남기지 않는다.
    assert len(repository.list_scenarios(include_archived=True)) == 1


def test_renaming_onto_another_scenario_name_is_refused_but_keeping_it_is_not(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path / "scenario.duckdb")
    preset = ScenarioPreset(202608, 202608, ("Process-A",))
    taken = repository.create_scenario(_metadata("먼저 쓴 이름"), _reference_tables(), preset)
    other = repository.create_scenario(_metadata("다른 이름"), _reference_tables(), preset)
    repository.archive_scenario(taken.scenario.scenario_id)

    with pytest.raises(ValueError, match="같은 이름의 시나리오가 이미 있습니다"):
        repository.rename_scenario(other.scenario.scenario_id, "먼저 쓴 이름")

    # 지금 이름 그대로 저장하는 것은 자기 자신과 겹칠 뿐이다.
    kept = repository.rename_scenario(other.scenario.scenario_id, "다른 이름")
    assert kept.scenario_name == "다른 이름"


def test_latest_official_release_is_append_only_and_loadable(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "scenario.duckdb")
    first = repository.create_scenario(
        _metadata("First"),
        _reference_tables(),
        ScenarioPreset(202608, 202608, ("Process-A",)),
    )
    second = repository.create_scenario(
        _metadata("Second"),
        _reference_tables(),
        ScenarioPreset(202608, 202608, ("Process-A",)),
    )

    release_one = repository.publish_official_revision(
        first.scenario.scenario_id,
        first.revision.revision_id,
        release_name="Official 1",
    )
    release_two = repository.publish_official_revision(
        second.scenario.scenario_id,
        second.revision.revision_id,
        release_name="Official 2",
        note="Approved",
    )

    assert release_one.release_no == 1
    assert release_two.release_no == 2
    assert repository.latest_official_release() == release_two
    assert repository.list_official_releases() == [release_two, release_one]
    assert repository.load_revision(release_two.revision_id).scenario.scenario_name == "Second"


def test_official_release_rejects_foreign_revision_and_latest_cannot_be_deleted(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path / "scenario.duckdb")
    first = repository.create_scenario(
        _metadata("First"),
        _reference_tables(),
        ScenarioPreset(202608, 202608, ("Process-A",)),
    )
    second = repository.create_scenario(
        _metadata("Second"),
        _reference_tables(),
        ScenarioPreset(202608, 202608, ("Process-A",)),
    )

    with pytest.raises(ValueError, match="선택한 시나리오"):
        repository.publish_official_revision(
            first.scenario.scenario_id,
            second.revision.revision_id,
            release_name="Invalid",
        )

    repository.publish_official_revision(
        first.scenario.scenario_id,
        first.revision.revision_id,
        release_name="Official",
    )
    with pytest.raises(ValueError, match="최신 공식버전"):
        repository.delete_scenario(first.scenario.scenario_id)


def test_typed_core_data_and_profile_round_trip(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "scenario.duckdb")
    raw = _core_data_source()
    display_order = _reference_tables()["RQ_DISPLAY_ORDER"]
    reference_tables = build_reference_tables(raw, display_order)

    snapshot = repository.create_scenario(
        _metadata(),
        reference_tables,
        ScenarioPreset(202608, 202608, ("Process-A",)),
        source_data=raw,
    )

    loaded = repository.load_source_data(snapshot.scenario.scenario_id)
    profile = repository.load_source_profile(snapshot.scenario.scenario_id)
    assert loaded.shape == (1, 78)
    assert loaded.loc[0, "생산수량"] == pytest.approx(100.0)
    assert len(profile) == 78
    assert profile["ordinal_position"].tolist() == list(range(1, 79))


def test_same_simulation_code_rejects_changed_raw_snapshot(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "scenario.duckdb")
    display_order = _reference_tables()["RQ_DISPLAY_ORDER"]
    original = _core_data_source()
    changed = _core_data_source(quantity=200.0)
    preset = ScenarioPreset(202608, 202608, ("Process-A",))
    repository.create_scenario(
        _metadata("Original"),
        build_reference_tables(original, display_order),
        preset,
        source_data=original,
    )

    with pytest.raises(ValueError, match="원천 코드는 불변") as caught:
        repository.create_scenario(
            _metadata("Changed"),
            build_reference_tables(changed, display_order),
            preset,
            source_data=changed,
        )

    assert len(repository.list_scenarios()) == 1
    # 상세 조회 기간을 바꿔 다시 받으려는 사람에게 「새 리비전」은 답이 아니다.
    # 다시 받는 길(보관 뒤 영구 삭제)을 함께 적는다.
    assert "보관한 뒤 영구 삭제" in str(caught.value)


def test_same_simulation_code_can_be_physically_copied_when_raw_is_identical(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path / "scenario.duckdb")
    raw = _core_data_source()
    reference_tables = build_reference_tables(raw, _reference_tables()["RQ_DISPLAY_ORDER"])
    preset = ScenarioPreset(202608, 202608, ("Process-A",))
    repository.create_scenario(
        _metadata("First"),
        reference_tables,
        preset,
        source_data=raw,
    )

    copied = repository.create_scenario(
        _metadata("Second"),
        reference_tables,
        preset,
        source_data=raw,
    )

    assert copied.scenario.scenario_name == "Second"
    assert len(repository.list_scenarios()) == 2


def test_revision_records_virtual_products(tmp_path: Path) -> None:
    """저장한 리비전이 가상 제품 목록을 그대로 돌려줘야 공식버전 발행 때 확인할 수 있다.

    가상 제품은 기존 제품을 복제해 만든 것이라 실적과 대조할 수 없다. 어떤 제품이
    어느 원본에서 나왔는지 리비전에 남겨야 발행 전에 걸러낼 수 있다.
    """
    repository = _repository(tmp_path / "scenario.duckdb")
    preset = ScenarioPreset(
        start_month=202608,
        end_month=202608,
        included_processes=("Process-A",),
        standard_target_processes=("Process-A",),
    )
    created = repository.create_scenario(_metadata(), _reference_tables(), preset)

    saved = repository.save_revision(
        created.scenario.scenario_id,
        {name: created.tables[name] for name in REVISION_TABLES},
        preset,
        revision_name="가상 제품 포함",
        virtual_products=[
            {
                "product": "DEMO_NEW",
                "stack": "8H",
                "source_product": "Product-A",
                "source_stack": "8H",
            }
        ],
    )

    recorded = repository.list_virtual_products(saved.revision.revision_id)
    assert recorded["제품정보"].tolist() == ["DEMO_NEW"]
    assert recorded["원본 제품정보"].tolist() == ["Product-A"]
    assert repository.list_virtual_products(created.revision.revision_id).empty


def test_standard_target_view_settings_survive_a_revision_round_trip(tmp_path: Path) -> None:
    """표준 목표 Capa 조회·집계 설정이 리비전과 함께 저장되고 그대로 돌아온다."""
    repository = _repository(tmp_path / "scenario.duckdb")
    preset = ScenarioPreset(
        start_month=202608,
        end_month=202608,
        included_processes=("Process-A",),
        standard_target_processes=("Process-A",),
        standard_target_start_date=date(2026, 8, 10),
        standard_target_end_date=date(2026, 8, 20),
        standard_target_show_detail=True,
        standard_target_detail_level="Stack",
        standard_target_output_metric="가용대수",
    )

    created = repository.create_scenario(_metadata(), _reference_tables(), preset)
    restored = repository.load_revision(created.revision.revision_id)

    assert restored.preset == preset
    assert restored.preset.standard_target_start_date == date(2026, 8, 10)
    assert restored.preset.standard_target_end_date == date(2026, 8, 20)
    assert restored.preset.standard_target_show_detail is True
    assert restored.preset.standard_target_detail_level == "Stack"
    assert restored.preset.standard_target_output_metric == "가용대수"


def test_revision_saved_before_view_settings_existed_opens_with_defaults(tmp_path: Path) -> None:
    """조회·집계 설정 컬럼이 NULL 인 과거 리비전도 예외 없이 기본값으로 열린다."""
    database_path = tmp_path / "scenario.duckdb"
    repository = _repository(database_path)
    created = repository.create_scenario(
        _metadata(),
        _reference_tables(),
        ScenarioPreset(
            202608,
            202608,
            ("Process-A",),
            standard_target_start_date=date(2026, 8, 10),
            standard_target_show_detail=True,
            standard_target_output_metric="가용대수",
        ),
    )
    with connect(database_path) as connection:
        connection.execute(
            """
            UPDATE app_meta.scenario_preset
            SET standard_target_start_date = NULL,
                standard_target_end_date = NULL,
                standard_target_show_detail = NULL,
                standard_target_detail_level = NULL,
                standard_target_output_metric = NULL
            WHERE revision_id = ?
            """,
            [created.revision.revision_id],
        )

    restored = repository.load_revision(created.revision.revision_id)

    assert restored.preset.standard_target_start_date is None
    assert restored.preset.standard_target_end_date is None
    assert restored.preset.standard_target_show_detail is False
    assert restored.preset.standard_target_detail_level == "제품정보"
    assert restored.preset.standard_target_output_metric == "일 표준 가능량"


def test_reversed_view_dates_are_corrected_instead_of_rejected() -> None:
    """저장값이 뒤집혀 있어도 리비전을 열 수 있어야 한다. 종료일을 시작일에 맞춘다."""
    preset = ScenarioPreset(
        202608,
        202608,
        ("Process-A",),
        standard_target_start_date=date(2026, 8, 25),
        standard_target_end_date=date(2026, 8, 5),
    )

    assert preset.standard_target_start_date == date(2026, 8, 25)
    assert preset.standard_target_end_date == date(2026, 8, 25)


def test_view_settings_change_the_preset_digest() -> None:
    base = ScenarioPreset(202608, 202608, ("Process-A",))

    assert base.digest() != replace(base, standard_target_detail_level="Stack").digest()
    assert base.digest() != replace(base, standard_target_start_date=date(2026, 8, 1)).digest()


def test_scenario_summary_carries_the_source_registration_time(tmp_path: Path) -> None:
    """머리 띠가 「{원천} {등록일} 등록」을 적는 원천 등록시점은 시나리오 요약과 스냅샷에 실린다.
    원천에 등록시점이 없으면 비어 있다(머리 띠는 시나리오를 만든 시각으로 물러난다)."""
    from datetime import datetime

    repository = _repository(tmp_path / "scenario.duckdb")
    preset = ScenarioPreset(start_month=202608, end_month=202608, included_processes=("Process-A",))
    registered = datetime(2026, 9, 28, 10, 30)

    with_time = repository.create_scenario(
        replace(_metadata("With time"), source_registered_at=registered),
        _reference_tables(),
        preset,
    )
    without = repository.create_scenario(_metadata("Without time"), _reference_tables(), preset)

    by_name = {summary.scenario_name: summary for summary in repository.list_scenarios()}
    assert by_name["With time"].source_registered_at == registered
    assert by_name["Without time"].source_registered_at is None
    assert with_time.scenario.source_registered_at == registered
    assert without.scenario.source_registered_at is None
    loaded = repository.load_revision(with_time.revision.revision_id)
    assert loaded.scenario.source_registered_at == registered
