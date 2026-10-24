# Purpose: 가정 계획 시간 스크립트가 사본으로 재고 실패는 단계·예외 종류만 찍는지 본다.

"""`scripts/benchmark_upeh_assumption.py` — 사내 런북 6-3 b 의 「가정 계획 1회 시간」.

내장 시드로 부트스트랩한 시뮬레이션 DB 와, 시드 공정에 신규 호기 둘·Cut-off 를 넣은 설비 DB 를 사본
폴더로 삼는다. 오늘은 시드 첫 달로 박는다(시드 달은 2026년이라 날짜가 지나도 시험이 같게 돈다). 합성
표본이라 초는 보지 않고 칸·개수만 본다.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from test_required_shortening import _cutoff, _downtime, _master, _unit

from capa_simulation.application_bootstrap import ensure_initial_scenario
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.persistence.repository import DuckDBScenarioRepository

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import benchmark_upeh_assumption as benchmark  # noqa: E402

SEED_PROCESS = "DEMO_Chip_Attach"


@pytest.fixture(scope="module")
def copy_folder(tmp_path_factory: pytest.TempPathFactory) -> Path:
    folder = tmp_path_factory.mktemp("upeh_bench")
    scenario = DuckDBScenarioRepository(folder / benchmark.SCENARIO_DATABASE)
    scenario.initialize()
    ensure_initial_scenario(scenario)
    equipment = DuckDBEquipmentRepository(folder / benchmark.EQUIPMENT_DATABASE)
    equipment.initialize()
    master = _master(
        [
            _unit("DA-01", date(2026, 3, 10), process=SEED_PROCESS, arrival=date(2026, 2, 1)),
            _unit("DA-02", date(2026, 5, 20), process=SEED_PROCESS, arrival=date(2026, 4, 1)),
        ]
    )
    baseline = pd.DataFrame(columns=["공정", "분류", "기존보유대수", "비고"])
    equipment.save_snapshot(baseline, master, _downtime())
    equipment.save_process_cutoff(_cutoff(10, SEED_PROCESS))
    return folder


def test_it_times_the_official_and_the_assumed_plan(copy_folder: Path) -> None:
    result = benchmark.measure(copy_folder, percent=120, today=date(2026, 1, 1))
    assert result["percent"] == 120
    assert result["months"] == 12
    assert result["processes"] == 1
    assert result["levels"] == 5
    for key in ("official_seconds", "scale_seconds", "assumed_seconds"):
        seconds = result[key]
        assert isinstance(seconds, float) and seconds >= 0
    assert str(result["verdict"]).startswith("1초")
    # 값(공정·호기 이름)은 싣지 않는다 — 개수와 초뿐이다.
    assert SEED_PROCESS not in json.dumps(result, ensure_ascii=False)


def test_the_cli_writes_json_and_refuses_a_bad_folder_or_percent(
    copy_folder: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "bench.json"
    assert benchmark.main(["--data-dir", str(copy_folder), "--output", str(output)]) == 0
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["percent"] == 110
    assert benchmark.main(["--data-dir", str(tmp_path)]) == 2
    assert "사본 폴더에 없는 파일" in capsys.readouterr().err
    assert benchmark.main(["--data-dir", str(copy_folder), "--percent", "200"]) == 2
    assert "--percent 는" in capsys.readouterr().err
    # 저장소 안(운영 data/ 와 그 아래 포함)은 받지 않는다 — 저장소 밖 사본 폴더만
    # (`settings.is_operational_database_place`, `benchmark_home.py` 와 같은 판정).
    refused = "저장소 안(data/ 포함)은 쓰지 않는다 — 저장소 밖 사본 폴더를 준다(런북 6-3)"
    for inside in (PROJECT_ROOT / "data", PROJECT_ROOT / "data" / "temp" / "copy", PROJECT_ROOT):
        assert benchmark.main(["--data-dir", str(inside)]) == 2
        assert capsys.readouterr().err.strip() == refused


def test_a_failure_names_only_the_stage_and_the_exception_kind(tmp_path: Path) -> None:
    """설비 저장본이 없는 사본 — 「설비 읽기 실패 — LookupError」 한 줄이다(이름·경로를 싣지
    않는다)."""
    scenario = DuckDBScenarioRepository(tmp_path / benchmark.SCENARIO_DATABASE)
    scenario.initialize()
    ensure_initial_scenario(scenario)
    DuckDBEquipmentRepository(tmp_path / benchmark.EQUIPMENT_DATABASE).initialize()
    with pytest.raises(RuntimeError) as caught:
        benchmark.measure(tmp_path, percent=110, today=date(2026, 1, 1))
    assert str(caught.value) == "설비 읽기 실패 — LookupError"


def test_it_reads_the_official_equipment_scenario_not_the_wrapper(
    copy_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """설비는 공식 설비 시나리오(공통 최신 + 최신 공식 발행)로 읽는다 — 앱 새 세션과 같은 한 벌이다.
    공통 id 하나로 짝을 찾는 호환 래퍼(`load_snapshot`)는 부르지 않는다."""

    def wrapper(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("호환 래퍼 load_snapshot 을 불렀다")

    monkeypatch.setattr(DuckDBEquipmentRepository, "load_snapshot", wrapper)
    result = benchmark.measure(copy_folder, percent=120, today=date(2026, 1, 1))
    assert result["processes"] == 1


def test_a_copy_from_before_0027_is_read_through_a_migrated_temporary_copy(
    tmp_path: Path,
) -> None:
    """사용자 앱이 새 배포로 설비 화면을 아직 열지 않은 사본(설비 마이그레이션 0025 까지) — 받은
    사본은 그대로 두고 임시 사본에만 마이그레이션을 걸어 잰다(전에는 「설비 읽기 실패 —
    CatalogException」)."""
    import duckdb
    from test_equipment_migration_0027_scenarios import build_legacy_database

    scenario = DuckDBScenarioRepository(tmp_path / benchmark.SCENARIO_DATABASE)
    scenario.initialize()
    ensure_initial_scenario(scenario)
    equipment = tmp_path / benchmark.EQUIPMENT_DATABASE
    build_legacy_database(equipment)
    before = equipment.read_bytes()

    result = benchmark.measure(tmp_path, percent=110, today=date(2026, 1, 1))

    assert result["equipment_migrated_copy"] is True
    assert equipment.read_bytes() == before
    with duckdb.connect(str(equipment), read_only=True) as connection:
        row = connection.execute(
            "SELECT MAX(version) FROM equipment_meta.schema_migration"
        ).fetchone()
    assert row is not None and row[0] == 25
    assert sorted(path.name for path in tmp_path.iterdir()) == sorted(
        [benchmark.SCENARIO_DATABASE, benchmark.EQUIPMENT_DATABASE]
    )


def test_a_migrated_copy_says_so_only_when_it_was_needed(copy_folder: Path) -> None:
    result = benchmark.measure(copy_folder, percent=110, today=date(2026, 1, 1))
    assert result["equipment_migrated_copy"] is False
