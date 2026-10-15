# Purpose: 전 리비전 계산 집계 스크립트가 읽기만 하고 상태·개수만 찍어 이름을 내보내지 않는지 본다.

"""`scripts/inspect_revision_calculations.py` 의 약속 — 읽기만 한다, 리비전마다 상태와
개수만 찍는다, 멈춘 리비전은 단계·예외 종류·계약 표 이름만 적는다. 출력은 리뷰 문서를
거쳐 사외로 나가므로 **새면 그대로 밖으로 나간다.**

합성 DB 에 갈래마다 리비전을 하나씩 둔다 — 계산되는 것(내장 시드·보관한 복제), 부하량에서
빠지는 계획 줄이 있는 것, `RQ_MODULE` 이 모자라 대당 Capa 에서 멈추는 머지(정적 감사
D1·D2 의 꼴), 가용대수가 모자라 확보율에서 멈추는 연도 이동, 경로 키가 없어 앱이 불러오지
않는 옛 등록. 그리고 공정·제품·시나리오·리비전 이름에 표지값(`ZZSENTINEL…`)을 심어, 멈춘
리비전의 오류 문구(공정 이름이 실린다)까지 출력에 없는지 본다.
"""

from __future__ import annotations

import hashlib
import runpy
import sys
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from capa_simulation.application_bootstrap import ensure_initial_scenario
from capa_simulation.persistence.models import ScenarioCreate
from capa_simulation.persistence.repository import (
    REVISION_TABLES,
    DuckDBScenarioRepository,
)
from capa_simulation.services.required_equipment import REQB_COLUMNS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import inspect_revision_calculations as script  # noqa: E402

SENTINEL = "ZZSENTINEL"
# 표지값을 앞에 붙이는 컬럼 — 모든 표에 같이 붙여 계산의 조인은 그대로 선다.
RENAMED_COLUMNS = ("공정", "제품정보", "Customer")


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _plant_sentinels(path: Path) -> None:
    with duckdb.connect(str(path)) as connection:
        columns = connection.execute(
            "SELECT table_schema, table_name, column_name FROM information_schema.columns "
            "WHERE table_schema IN ('rev_data', 'ref_data')"
        ).fetchall()
        for schema, table, column in columns:
            if column in RENAMED_COLUMNS:
                connection.execute(
                    f'UPDATE {schema}.{table} SET "{column}" = ? || "{column}" '
                    f'WHERE "{column}" IS NOT NULL',
                    [f"{SENTINEL}-"],
                )
        connection.execute(
            "UPDATE app_meta.scenario SET scenario_name = ? || scenario_name, "
            "source_simulation_code = ? || source_simulation_code",
            [SENTINEL, SENTINEL],
        )
        connection.execute(
            "UPDATE app_meta.scenario_revision SET revision_name = ? || revision_name",
            [SENTINEL],
        )


def _create(
    repository: DuckDBScenarioRepository,
    name: str,
    source_type: str,
    tables: dict[str, pd.DataFrame],
    preset: object,
) -> str:
    snapshot = repository.create_scenario(
        ScenarioCreate(
            scenario_name=name,
            source_simulation_code=f"CODE-{name}",
            source_simulation_name=name,
            source_type=source_type,
            pipeline_version="test",
        ),
        tables,
        preset,  # type: ignore[arg-type]
    )
    return snapshot.scenario.scenario_id


@pytest.fixture(scope="module")
def simulation_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("revisions") / "capa_simulation.duckdb"
    repository = DuckDBScenarioRepository(path)
    repository.initialize()
    release = ensure_initial_scenario(repository).release
    assert release is not None
    snapshot = repository.load_revision(release.revision_id)
    tables = {name: frame.copy() for name, frame in snapshot.tables.items()}

    # S1 r2·r3 — 원천에 없는 제품의 계획 한 줄. Chip·수율 기준도 경로도 없어 소요대수에 닿지 않는다.
    plan = tables["RQ_PKG_PLAN"]
    unplanned = plan.iloc[[0]].assign(제품정보="NEW-PRODUCT")
    edited = {name: tables[name] for name in REVISION_TABLES}
    edited["RQ_PKG_PLAN"] = pd.concat([plan, unplanned], ignore_index=True)
    for name in ("r2", "r3"):
        repository.save_revision(
            snapshot.scenario.scenario_id, edited, snapshot.preset, revision_name=name
        )

    # S2 — 보관한 복제. 원천 그대로라 계산된다.
    clone = _create(repository, "clone", "DUCKDB_SCENARIO_CLONE", tables, snapshot.preset)
    repository.archive_scenario(clone)

    # S3 — 덧붙인 쪽 공정의 `RQ_MODULE` 이 빠진 머지. 대당 Capa 에서 멈춘다.
    merged = dict(tables)
    merged["RQ_MODULE"] = tables["RQ_MODULE"].iloc[1:].copy()
    _create(repository, "merge", "SCENARIO_MONTH_MERGE", merged, snapshot.preset)

    # S4 — 한 공정의 가용대수가 없는 연도 이동. 소요대수까지 서고 확보율에서 멈춘다.
    shifted = dict(tables)
    available = tables["RQ_EQP_AVBL"]
    shifted["RQ_EQP_AVBL"] = available.loc[available["공정"].ne(available["공정"].iloc[0])]
    _create(repository, "shift", "SCENARIO_YEAR_SHIFT", shifted, snapshot.preset)

    # S5 — 경로 키 계약 전의 옛 등록. 앱이 불러오기를 막는다.
    old = dict(tables)
    old["RQ_UPEH"] = tables["RQ_UPEH"].assign(STEP_SEQ=None)
    _create(repository, "old", "BIGDATAQUERY", old, snapshot.preset)

    _plant_sentinels(path)
    return path


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    code = script.main(list(argv))
    return code, capsys.readouterr().out


def test_every_revision_is_counted_by_source_and_status_without_names(
    simulation_db: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = _md5(simulation_db)

    code, output = _run(capsys, "--database", str(simulation_db))

    assert code == 0
    # 읽기만 했다 — 파일이 한 바이트도 바뀌지 않고 WAL 도 생기지 않는다.
    assert _md5(simulation_db) == before
    assert not simulation_db.with_name(simulation_db.name + ".wal").exists()
    # 이름·코드·오류 문구(머지가 멈춘 문구에는 공정 이름이 실린다)가 나가지 않는다. 경로도 이름만.
    assert SENTINEL not in output
    assert str(simulation_db.parent) not in output
    assert "DB `capa_simulation.duckdb` · 시나리오 5(보관 1) · 리비전 7" in output

    rows = [line for line in output.splitlines() if line.startswith("| S")]
    by_revision = {tuple(line.split(" | ")[:2]): line for line in rows}
    assert len(rows) == len(by_revision) == 7
    assert by_revision[("| S1", "r1")].startswith(
        "| S1 | r1 | 내장 시드 | - | v1 | 됨 | 0 / 24 | 0 | "
    )
    assert " | 됨 | 1 / 25 | 0 | " in by_revision[("| S1", "r3")]
    assert " | 복제 | 보관 | - | 됨 | 0 / 24 | " in by_revision[("| S2", "r1")]
    assert (
        " | 월 병합 | - | - | 멈춤 — 대당 Capa(ValueError · RQ_MODULE) | - | - | - | "
        in (by_revision[("| S3", "r1")])
    )
    assert (
        " | 연도 이동 | - | - | 확보율 멈춤 — 확보율(ValueError) | 0 / 24 | "
        in (by_revision[("| S4", "r1")])
    )
    assert " | 불러오기 막힘 — 경로 키 없음(RQ_UPEH) | - | " in by_revision[("| S5", "r1")]

    assert "| **합계** | 5 | 7 | 4 | 1 | 1 | 1 | 0 | 2 | 0 |" in output
    assert "| 내장 시드 | 1 | 3 | 3 | 0 | 0 | 0 | 0 | 2 | 0 |" in output
    assert "- 공식버전 — 이력이 가리키는 리비전 1개: 됨 1 · 최신 공식 v1(S1 r1) 됨" in output
    assert "| 멈춤 | 대당 Capa | ValueError | RQ_MODULE | 1 |" in output
    assert "| 확보율 멈춤 | 확보율 | ValueError | - | 1 |" in output


def test_active_only_keeps_the_active_and_the_official_revisions(
    simulation_db: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """S1 은 r1(공식)·r2·r3(활성) — r2 만 빠진다."""
    code, output = _run(capsys, "--database", str(simulation_db), "--active-only")

    assert code == 0
    revisions = [
        tuple(line.split(" | ")[:2]) for line in output.splitlines() if line.startswith("| S")
    ]
    assert revisions == [
        ("| S1", "r1"),
        ("| S1", "r3"),
        ("| S2", "r1"),
        ("| S3", "r1"),
        ("| S4", "r1"),
        ("| S5", "r1"),
    ]
    assert "`--active-only`" in output


def test_plan_lines_match_the_calculation_keys_not_the_raw_text() -> None:
    """계산처럼 월은 정수, 글자는 앞뒤 공백을 떼고 맞댄다. 부하량 0 인 행은 닿은 것이 아니다."""
    keys = {
        "양산구분": "양산",
        "Stack": "8H",
        "Capa Code": "C",
        "Customer": "K",
        "CS": "S",
    }
    plan = pd.DataFrame(
        [
            {"생산계획년월": "202601", "제품정보": " A ", **keys, "생산수량": 100.0},
            {"생산계획년월": 202601, "제품정보": "B", **keys, "생산수량": 100.0},
            {"생산계획년월": 202601, "제품정보": "C", **keys, "생산수량": 0.0},
            {"생산계획년월": 202602, "제품정보": "A", **keys, "생산수량": 50.0},
        ]
    )
    required = pd.DataFrame(
        [
            {"생산계획년월": 202601, "제품정보": "A", **keys, "부하량": 12.5},
            {"생산계획년월": 202601, "제품정보": "B", **keys, "부하량": 0.0},
            {"생산계획년월": 202602, "제품정보": "A", **keys, "부하량": 3.0},
        ]
    )

    assert script.unreached_plan_lines(plan, required) == (3, 1)


def test_duplicate_route_keys_count_the_second_and_later_rows() -> None:
    row = {column: f"v-{column}" for column in REQB_COLUMNS}
    other = {**row, "STEP_SEQ": "other"}
    required = pd.DataFrame([row, row, row, other]).assign(소요대수=1.0)

    assert script.duplicate_route_keys(required) == 2
    assert script.duplicate_route_keys(required.iloc[0:0]) == 0


def test_only_contract_table_names_are_taken_from_a_message() -> None:
    message = f"RQ_MODULE 에 없는 공정이 있습니다: ['{SENTINEL}-P'] (RQ_UPEH 기준)"

    assert script.contract_tables_in(message) == ("RQ_UPEH", "RQ_MODULE")
    assert script.contract_tables_in(f"{SENTINEL} 값이 숫자가 아닙니다") == ()


def test_unknown_source_types_are_named_as_the_app_wrote_them() -> None:
    assert script.source_group("CSV_CORE_DATA_INITIAL_BOOTSTRAP") == "원천 등록(CSV)"
    assert script.source_group("SOMETHING_NEW") == "그 밖(`SOMETHING_NEW`)"
    assert script.source_group(None) == "그 밖(빈 값)"


def test_a_locked_database_says_to_use_a_copy(
    simulation_db: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def locked(*_args: object, **_kwargs: object) -> duckdb.DuckDBPyConnection:
        raise duckdb.IOException(f"Could not set lock on file {SENTINEL}")

    monkeypatch.setattr(duckdb, "connect", locked)

    code, output = _run(capsys, "--database", str(simulation_db))

    assert code == 1
    assert "그동안 사용자 앱의 연결이 막힌다" in output
    assert "런북 6-3 대로 사본을 떠" in output
    assert SENTINEL not in output


def test_the_database_has_no_default(capsys: pytest.CaptureFixture[str]) -> None:
    """기본값이 운영 DB 면 저장소에서 부를 때 그것을 연다. 이 앱은 연산마다 연결을 열고 닫아 쉬는
    동안에는 잠금이 없으니 열리기는 하지만, 수 분 동안 쥐는 사이 사용자 앱의 연결이 다른 프로세스
    잠금으로 곧바로 실패한다(`_sql_helpers.connect` 는 그 잠금을 다시 시도하지 않는다)."""
    with pytest.raises(SystemExit) as stopped:
        script.parse_args([])

    assert stopped.value.code == 2
    assert "--database" in capsys.readouterr().err


def test_a_missing_file_stops_without_its_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, output = _run(capsys, "--database", str(tmp_path / "none.duckdb"))

    assert code == 2
    assert "`none.duckdb` 파일이 없다" in output
    assert str(tmp_path) not in output


def test_the_output_file_is_emptied_and_holds_the_same_markdown(
    simulation_db: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "revisions.md"
    target.write_text("STALE 지난 배포의 출력", encoding="utf-8")

    code, output = _run(capsys, "--database", str(simulation_db), "--output", str(target))

    assert code == 0
    written = target.read_text(encoding="utf-8")
    assert "STALE" not in written
    assert written.startswith("<!-- inspect_revision_calculations.py")
    assert written.strip() == output.strip()


def test_the_script_runs_as_a_program(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    path = PROJECT_ROOT / "scripts" / "inspect_revision_calculations.py"
    monkeypatch.setattr(sys, "argv", [str(path), "--help"])
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(path), run_name="__main__")
    assert stopped.value.code == 0
    assert "--active-only" in capsys.readouterr().out
