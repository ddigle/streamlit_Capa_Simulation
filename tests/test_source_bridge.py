# Purpose: 원천 CSV 다리(Q-C1 (나))를 본다 — 불변 검사 · 자동 갱신 · DB 목록의 「등록됨」 셈.

"""원천 CSV 는 DB 가 그 코드를 적재하기 전까지 건너는 다리다(`services/source_bridge.py`).

다음 날 같은 코드가 DB 에 오면 CSV 원천과 바이트가 달라도 DB 등록 · 자동 갱신이 평소처럼
선다. CSV 원천끼리, 그리고 DB 원천이 먼저 있을 때의 CSV 원천은 지금처럼 원천 코드 불변 검사를
받는다. 처음 이름 꼬리는 `tests/test_source_csv_view.py` · `tests/test_source_csv_registration.py`
가 본다. 값은 합성(저장소 시험 견본 · 내장 합성 시드 — 샘플 관측)이다."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest
from auto_update_fakes import DISPLAY_ORDER, FakeBigDataQuery, new_repository, source_frame
from auto_update_fakes import catalog_frame as _catalog
from auto_update_fakes import fixed_clock as _clock
from auto_update_fakes import official_w40 as _official_w40
from auto_update_fakes import publish_snapshot as _publish
from source_csv_samples import source_csv_bytes
from test_duckdb_repository import _core_data_source, _reference_tables, _repository
from test_source_csv_registration import (
    _app,
    _csv_route,
    _database,
    _db_route,
    _rows,
    _save,
    _scenarios,
    _upload,
)

from capa_simulation.auto_official_update_runner import run_auto_official_update
from capa_simulation.components import bigdataquery_registration as registration
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.io.core_data_source import CoreDataBatch
from capa_simulation.io.source_csv import SOURCE_CSV_SOURCE_TYPE
from capa_simulation.persistence.models import (
    AutoOfficialUpdateRun,
    ScenarioCreate,
    ScenarioPreset,
    ScenarioSnapshot,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_preset_state import full_data_scenario_preset
from capa_simulation.scenario_registration import save_bigdataquery_scenario
from capa_simulation.services.auto_official_update import (
    STATUS_ERROR,
    STATUS_PUBLISHED,
    STATUS_SKIPPED,
    TRIGGER_MANUAL,
)
from capa_simulation.services.bigdataquery_catalog_view import (
    REGISTERED_LABEL,
    UNREGISTERED_LABEL,
)
from capa_simulation.services.core_data_pipeline import prepare_core_data_dataset
from capa_simulation.services.reference_transformer import build_reference_tables
from capa_simulation.services.source_bridge import (
    BRIDGE_NAME_TAIL,
    compared_source_hashes,
    is_bridge_source,
    settled_source_codes,
)

DB_SOURCE = "BIGDATAQUERY"


@pytest.fixture(autouse=True)
def _no_process_labels_from_the_repository_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """저장 뒤 알림의 공정 표시명은 저장소 `data/` DB 를 읽는다 — 이 파일의 시험은 그 DB 를 열지
    않는다."""
    monkeypatch.setattr(registration, "get_process_labels", ProcessLabels)


@dataclass(frozen=True)
class _Record:
    source_simulation_code: str
    source_type: str


def test_only_the_csv_upload_source_type_is_a_bridge() -> None:
    """다리는 원천 CSV 올림 하나다 — 초기 이관 스크립트의 CSV 원천 · DB 조회 · 복제는 아니다."""
    assert is_bridge_source(SOURCE_CSV_SOURCE_TYPE)
    for other in (
        DB_SOURCE,
        "CSV_CORE_DATA_INITIAL_BOOTSTRAP",
        "CSV_CORE_DATA_INITIAL_REFRESH",
        "DUCKDB_SCENARIO_CLONE",
        "BUILTIN_SYNTHETIC_SEED",
    ):
        assert not is_bridge_source(other), other


def test_compared_hashes_leave_out_csv_hashes_only_for_a_non_csv_source() -> None:
    existing = [("h-csv", SOURCE_CSV_SOURCE_TYPE), ("h-db", DB_SOURCE)]

    assert compared_source_hashes(existing, DB_SOURCE) == {"h-db"}
    assert compared_source_hashes(existing, SOURCE_CSV_SOURCE_TYPE) == {"h-csv", "h-db"}
    assert compared_source_hashes([("h-csv", SOURCE_CSV_SOURCE_TYPE)], DB_SOURCE) == set()


def test_settled_codes_leave_out_scenarios_received_only_from_a_csv_file() -> None:
    records = [
        _Record("DEMO-CSV-ONLY", SOURCE_CSV_SOURCE_TYPE),
        _Record("DEMO-BOTH", SOURCE_CSV_SOURCE_TYPE),
        _Record("DEMO-BOTH", DB_SOURCE),
        _Record("DEMO-DB", DB_SOURCE),
        _Record("DEMO-CLONE", "DUCKDB_SCENARIO_CLONE"),
    ]

    assert settled_source_codes(records) == {"DEMO-BOTH", "DEMO-DB", "DEMO-CLONE"}


def _create(
    repository: DuckDBScenarioRepository, name: str, source_type: str, frame: pd.DataFrame
) -> None:
    """저장소 시험 견본(코드 `SIM-001`)을 그 원천 유형으로 저장한다."""
    repository.create_scenario(
        ScenarioCreate(
            scenario_name=name,
            source_simulation_code="SIM-001",
            source_simulation_name="Source simulation",
            source_type=source_type,
            pipeline_version="test-v1",
        ),
        build_reference_tables(frame, _reference_tables()["RQ_DISPLAY_ORDER"]),
        ScenarioPreset(202608, 202608, ("Process-A",)),
        source_data=frame,
    )


def test_a_db_source_is_saved_over_a_changed_csv_source_of_the_same_code(tmp_path: Path) -> None:
    """다음 날 같은 코드가 DB 에 오면 CSV 원천과 바이트가 달라도 DB 등록이 선다 — 한 코드에 원천
    두 벌(CSV · DB)이고 CSV 시나리오는 남는다."""
    repository = _repository(tmp_path / "bridge.duckdb")
    _create(repository, "CSV 로 먼저", SOURCE_CSV_SOURCE_TYPE, _core_data_source())

    _create(repository, "DB 로 다음 날", DB_SOURCE, _core_data_source(quantity=200.0))

    kinds = sorted(scenario.source_type for scenario in repository.list_scenarios())
    assert kinds == sorted([DB_SOURCE, SOURCE_CSV_SOURCE_TYPE])


@pytest.mark.parametrize("first", [SOURCE_CSV_SOURCE_TYPE, DB_SOURCE])
def test_a_changed_csv_source_is_still_refused_after_a_csv_or_db_source(
    tmp_path: Path, first: str
) -> None:
    """CSV 원천을 받을 때는 지금처럼 모든 원천과 견준다 — 같은 코드의 CSV 원천은 한 벌이고, DB
    원천이 먼저 있으면 바이트가 같은 파일만 받는다."""
    repository = _repository(tmp_path / "bridge.duckdb")
    _create(repository, "먼저", first, _core_data_source())

    with pytest.raises(ValueError, match="원천 코드는 불변"):
        _create(repository, "다시 받은 CSV", SOURCE_CSV_SOURCE_TYPE, _core_data_source(quantity=7))
    _create(repository, "같은 바이트의 CSV", SOURCE_CSV_SOURCE_TYPE, _core_data_source())

    assert len(repository.list_scenarios()) == 2


def test_a_changed_db_source_is_still_refused_after_a_db_source_beside_a_csv_one(
    tmp_path: Path,
) -> None:
    """DB 원천끼리는 지금 규칙 그대로다 — CSV 원천이 곁에 있어도 바이트가 다른 DB 원천은 막힌다."""
    repository = _repository(tmp_path / "bridge.duckdb")
    _create(repository, "CSV", SOURCE_CSV_SOURCE_TYPE, _core_data_source())
    _create(repository, "DB", DB_SOURCE, _core_data_source(quantity=200.0))

    with pytest.raises(ValueError, match="원천 코드는 불변"):
        _create(repository, "DB 다시", DB_SOURCE, _core_data_source(quantity=300.0))

    assert len(repository.list_scenarios()) == 2


@pytest.fixture
def repository(tmp_path: Path) -> DuckDBScenarioRepository:
    return new_repository(tmp_path / "bridge_runner.duckdb")


def _csv_frame() -> pd.DataFrame:
    """원천 웹 CSV 로 받은 원천 — 내장 합성 시드 사본의 첫 계획 행 생산수량만 달라 DB 원천과
    바이트가 다르다."""
    frame = source_frame()
    first = frame.index[frame["계획기초정보여부"].eq("Y")][0]
    frame.loc[first, "생산수량"] = float(frame.loc[first, "생산수량"]) + 7.0
    return frame


def _register_csv(
    repository: DuckDBScenarioRepository,
    *,
    code: str,
    scenario_name: str,
    registered_at: datetime | None = None,
) -> ScenarioSnapshot:
    """원천 CSV 등록과 같은 저장 길 — 원천 유형 `CSV_CORE_DATA_UPLOAD` · 대조 없음 · 등록시점은
    처음 값 빈칸(공식으로 지정할 시나리오는 적는다 — Guide)."""
    prepared = prepare_core_data_dataset(
        CoreDataBatch(
            simulation_code=code,
            simulation_name=code,
            source_type=SOURCE_CSV_SOURCE_TYPE,
            frame=_csv_frame(),
            source_registered_at=registered_at,
        ),
        DISPLAY_ORDER,
    )
    return save_bigdataquery_scenario(
        repository,
        prepared,
        full_data_scenario_preset(
            prepared.reference_tables, secure_threshold=1.095, warning_threshold=0.995
        ),
        scenario_name=scenario_name,
        revision_name="초기 리비전",
        note="",
    ).snapshot


def _run(repository: DuckDBScenarioRepository, fake: FakeBigDataQuery) -> AutoOfficialUpdateRun:
    result = run_auto_official_update(
        repository, trigger=TRIGGER_MANUAL, sources=fake.sources, clock=_clock
    )
    assert result.not_run_reason is None
    assert result.run is not None
    return result.run


def test_a_code_received_only_from_a_csv_file_is_taken_by_the_auto_update(
    repository: DuckDBScenarioRepository,
) -> None:
    """CSV 로만 받은 코드가 DB 목록에 오면 자동 갱신이 평소처럼 DB 원천으로 받아 공식으로 올린다
    — CSV 시나리오(처음 이름 꼬리 「 · CSV」)는 남는다."""
    _official_w40(repository)
    _register_csv(repository, code="SIM-W41", scenario_name=f"SIM-W41 (SIM-W41){BRIDGE_NAME_TAIL}")
    fake = FakeBigDataQuery(_catalog(("PSM W41", "SIM-W41", "2026-10-12 09:00:00")))

    run = _run(repository, fake)

    assert (run.status, run.simulation_code) == (STATUS_PUBLISHED, "SIM-W41")
    received = {
        scenario.scenario_name: scenario.source_type
        for scenario in repository.list_scenarios(include_archived=True)
        if scenario.source_simulation_code == "SIM-W41"
    }
    assert received == {
        "SIM-W41 (SIM-W41) · CSV": SOURCE_CSV_SOURCE_TYPE,
        "PSM W41 (SIM-W41)": DB_SOURCE,
    }


@pytest.mark.parametrize(
    ("registered_at", "taken"),
    [(datetime(2026, 10, 12, 18, 0), False), (datetime(2026, 10, 12, 8, 0), True)],
)
def test_an_official_csv_code_is_taken_from_the_db_only_when_it_is_first_listed_later(
    repository: DuckDBScenarioRepository, registered_at: datetime, taken: bool
) -> None:
    """CSV 시나리오를 손으로 공식 지정한 코드가 DB 목록에 오면 같은 주차 규칙 그대로다 — 목록에
    처음 보인 그 코드의 시각이 공식 기준 시각(원천 등록시점, 비우면 공식 지정 시각)보다 늦을 때만
    자동 갱신이 DB 원천으로 받아 공식으로 올리고, 이르면 받지 않는다(기준 시각이 그 이른 시각으로
    당겨진다). 처음 이름 꼬리가 든 시나리오명에서도 주차를 읽는다.

    등록시점은 늘 적어 둔다 — 비우면 기준이 공식 지정 시각(시험을 돈 날)이 되어 주차의 해가 도는
    날에 따라 갈린다."""
    csv = _register_csv(
        repository,
        code="SIM-W41",
        scenario_name=f"PSM W41 (SIM-W41){BRIDGE_NAME_TAIL}",
        registered_at=registered_at,
    )
    _publish(repository, csv)
    fake = FakeBigDataQuery(_catalog(("PSM W41", "SIM-W41", "2026-10-12 09:00:00")))

    run = _run(repository, fake)

    if taken:
        assert (run.status, run.simulation_code, run.baseline_week) == (
            STATUS_PUBLISHED,
            "SIM-W41",
            41,
        )
    else:
        assert (run.status, run.baseline_week, run.candidate_count) == (STATUS_SKIPPED, 41, 0)
        assert fake.requests == []


def test_a_csv_scenario_renamed_to_the_db_name_stops_each_round_at_register(
    repository: DuckDBScenarioRepository,
) -> None:
    """처음 이름 꼬리를 지워 CSV 시나리오 이름을 DB 로 받는 이름(「<원천명> (<코드>)」)과 같게
    고치면 그 코드의 자동 갱신 회차는 등록 단계에서 같은 이름으로 멈추고, 받은 코드로 세지 않아
    다음 회차가 다시 받는다 — Guide 가 꼬리를 남기라고 말하는 까닭이다."""
    _official_w40(repository)
    _register_csv(repository, code="SIM-W41", scenario_name="PSM W41 (SIM-W41)")
    fake = FakeBigDataQuery(_catalog(("PSM W41", "SIM-W41", "2026-10-12 09:00:00")))

    first = _run(repository, fake)
    second = _run(repository, fake)

    for run in (first, second):
        assert (run.status, run.stage, run.created_scenario_id) == (STATUS_ERROR, "register", None)
        assert run.reason is not None and "같은 이름의 시나리오" in run.reason
    assert [request.simulation_code for request in fake.requests] == ["SIM-W41", "SIM-W41"]


def test_the_db_list_counts_a_csv_only_code_as_unregistered_and_the_csv_list_as_registered(
    tmp_path: Path,
) -> None:
    """DB 목록은 원천 CSV 로만 받은 코드를 미등록으로 센다(다음 날 DB 로 받을 수 있음). CSV 목록은
    모든 시나리오로 세어 같은 코드가 등록됨이다."""
    database = _database(tmp_path)
    app = _save(_upload(_csv_route(_app(database)), source_csv_bytes(_rows("DEMO-A-001"))))
    assert [scenario.source_type for scenario in _scenarios(database)] == [SOURCE_CSV_SOURCE_TYPE]

    app = _upload(app, source_csv_bytes(_rows("DEMO-A-001")))
    [csv_list] = app.dataframe
    assert set(csv_list.value["등록여부"]) == {REGISTERED_LABEL}

    app.session_state["__catalog__"] = True
    app = _db_route(app)
    [db_list] = app.dataframe
    assert list(db_list.value["시뮬레이션 코드"]) == ["DEMO-A-001"]
    assert list(db_list.value["등록여부"]) == [UNREGISTERED_LABEL]
