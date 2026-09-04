# Purpose: duckdb repository 관련 정상·예외·회귀 동작을 검증한다.

import pickle
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
)
from capa_simulation.persistence.cache import (
    clear_scenario_repository,
    load_scenario_snapshot,
)
from capa_simulation.persistence.repository import REFERENCE_TABLES
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
    # 되돌아가면 이 지점에서 ConnectionException이 난다.
    with duckdb.connect(str(database_path)):
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
        def load_revision(self, _revision_id: str) -> StaleSnapshot:
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


def test_archive_hides_scenario_without_deleting_it(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "scenario.duckdb")
    snapshot = repository.create_scenario(
        _metadata(),
        _reference_tables(),
        ScenarioPreset(202608, 202608, ("Process-A",)),
    )

    repository.archive_scenario(snapshot.scenario.scenario_id)

    assert repository.list_scenarios() == []
    archived = repository.list_scenarios(include_archived=True)
    assert len(archived) == 1
    assert archived[0].status == "ARCHIVED"


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


def test_official_release_rejects_foreign_revision_and_latest_cannot_be_archived(
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
        repository.archive_scenario(first.scenario.scenario_id)


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

    with pytest.raises(ValueError, match="원천 코드는 불변"):
        repository.create_scenario(
            _metadata("Changed"),
            build_reference_tables(changed, display_order),
            preset,
            source_data=changed,
        )

    assert len(repository.list_scenarios()) == 1


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
