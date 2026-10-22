# Purpose: 전 리비전 계산 집계 스크립트가 읽기만 하고 상태·개수만 찍어 이름을 내보내지 않는지 본다.

"""`scripts/inspect_revision_calculations.py` 의 약속 — 읽기만 한다, 리비전마다 상태와
개수만 찍는다, 멈춘 리비전은 단계·예외 종류·계약 표 이름만 적는다. 출력은 리뷰 문서를
거쳐 사외로 나가므로 **새면 그대로 밖으로 나간다.**

합성 DB 에 갈래마다 리비전을 하나씩 둔다 — 계산되는 것(내장 시드·보관한 복제), 부하량에서
빠지는 계획 줄이 있는 것, `RQ_MODULE` 이 모자라 대당 Capa 에서 멈추는 머지(정적 감사
D1·D2 의 꼴), 가용대수가 모자라 확보율에서 멈추는 연도 이동, 경로 키가 없어 앱이 불러오지
않는 옛 등록, 계산은 서는데 저장·발행 검사의 Density 환산에서 멈추는 공식 v2(`구분_EQ` 0).
그리고 공정·제품·시나리오·리비전 이름에 표지값(`ZZSENTINEL…`)을 심어, 멈춘 리비전의 오류
문구(공정 이름이 실린다)까지 출력에 없는지 본다.
"""

from __future__ import annotations

import hashlib
import logging
import os
import runpy
import subprocess
import sys
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from capa_simulation.application_bootstrap import ensure_initial_scenario
from capa_simulation.persistence.models import ScenarioCreate, ScenarioSnapshot
from capa_simulation.persistence.repository import (
    REVISION_TABLES,
    DuckDBScenarioRepository,
)
from capa_simulation.services.required_equipment import (
    REQB_COLUMNS,
    calculate_required_equipment,
)

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


def _density_broken(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """계획이 있는 제품 하나의 `구분_EQ` 를 0 으로 — `tests/test_capacity_gate.py` 와 같은 꼴."""
    plan = tables["RQ_PKG_PLAN"]
    planned = plan.loc[pd.to_numeric(plan["생산수량"]).gt(0)].iloc[0]
    chip_eq = tables["RQ_CHIP_EQ"].copy()
    target = chip_eq["제품정보"].eq(planned["제품정보"]) & chip_eq["Stack"].eq(planned["Stack"])
    assert target.any()
    chip_eq.loc[target, "구분_EQ"] = 0.0
    return {**tables, "RQ_CHIP_EQ": chip_eq}


def _create(
    repository: DuckDBScenarioRepository,
    name: str,
    source_type: str,
    tables: dict[str, pd.DataFrame],
    preset: object,
) -> ScenarioSnapshot:
    return repository.create_scenario(
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
    repository.archive_scenario(clone.scenario.scenario_id)

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

    # S6 — 계획이 있는 제품의 `구분_EQ` 가 0 인 원천 등록을 공식 v2 로 지정했다(저장소는 검사하지
    # 않는다). 대당 Capa·소요대수·확보율은 서고 저장·발행 검사의 Density 환산만 멈춘다.
    density = _create(
        repository, "density", "CSV_CORE_DATA", _density_broken(tables), snapshot.preset
    )
    repository.publish_official_revision(
        density.scenario.scenario_id, density.revision.revision_id, release_name="v2"
    )

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
    assert "DB `capa_simulation.duckdb` · 시나리오 6(보관 1) · 리비전 8" in output

    rows = [line for line in output.splitlines() if line.startswith("| S")]
    by_revision = {tuple(line.split(" | ")[:2]): line for line in rows}
    assert len(rows) == len(by_revision) == 8
    assert by_revision[("| S1", "r1")].startswith(
        "| S1 | r1 | 내장 시드 | - | v1 | 됨 | 됨 | 0 / 24 | 0 | "
    )
    assert " | 됨 | 됨 | 1 / 25 | 0 | " in by_revision[("| S1", "r3")]
    assert " | 복제 | 보관 | - | 됨 | 됨 | 0 / 24 | " in by_revision[("| S2", "r1")]
    # Capa 계산이 서지 않으면 Density 는 재지 않는다(`-`) — 저장·발행 검사와 같은 차례다.
    assert (
        " | 월 병합 | - | - | 멈춤 — 대당 Capa(ValueError · RQ_MODULE) | - | - | - | - | "
        in (by_revision[("| S3", "r1")])
    )
    # 확보율에서 멈춰도 Density 는 잰다 — 둘은 서로 기대지 않는다.
    assert (
        " | 연도 이동 | - | - | 확보율 멈춤 — 확보율(ValueError) | 됨 | 0 / 24 | "
        in (by_revision[("| S4", "r1")])
    )
    assert " | 불러오기 막힘 — 경로 키 없음(RQ_UPEH) | - | - | " in by_revision[("| S5", "r1")]
    # `계산` 은 서는데 Density 만 멈춘다 — 대당 Capa·소요대수는 `구분_EQ` 를 쓰지 않는다.
    assert (
        " | 원천 등록(CSV) | - | v2 | 됨 | 멈춤(ValueError · RQ_CHIP_EQ) | 0 / 24 | 0 | "
        in (by_revision[("| S6", "r1")])
    )

    assert "| **합계** | 6 | 8 | 5 | 1 | 1 | 1 | 0 | 1 | 2 | 0 |" in output
    assert "| 내장 시드 | 1 | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 2 | 0 |" in output
    assert "| 원천 등록(CSV) | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 |" in output
    assert (
        "- 공식버전 — 최신 공식 v2(S6 r1) 됨 · Density 멈춤(ValueError · RQ_CHIP_EQ) · "
        "이력이 가리키는 리비전 2개: 됨 2 · 지난 공식버전 포함 Density 멈춤 1"
    ) in output
    assert "| Density 멈춤 | Density | ValueError | RQ_CHIP_EQ | 1 |" in output
    assert "| 멈춤 | 대당 Capa | ValueError | RQ_MODULE | 1 |" in output
    assert "| 확보율 멈춤 | 확보율 | ValueError | - | 1 |" in output
    assert "**최신 공식의 `Density` 칸이 `됨` 이어야 한다**" in output


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
        ("| S6", "r1"),
    ]
    assert "`--active-only`" in output


def test_density_and_securement_are_judged_apart(simulation_db: Path) -> None:
    """확보율에서 멈춘 리비전도 Density 를 잰다.

    한쪽 멈춤이 다른 쪽을 가리지 않고, 갈래 표에는 두 줄로 든다.
    """
    with duckdb.connect(str(simulation_db), read_only=True) as connection:
        shift = next(
            revision
            for revision in script.list_revisions(connection, active_only=False)
            if revision.source_group == "연도 이동"
        )
        tables = script.load_tables(connection, shift)

    outcome = script.calculate(_density_broken(tables))

    assert (outcome.status, outcome.density) == (script.SECUREMENT_STOPPED, script.STOPPED)
    assert script.describe_density(outcome) == "멈춤(ValueError · RQ_CHIP_EQ)"
    lines = script.summary_lines([shift], [outcome], active_only=False)
    assert "| Density 멈춤 | Density | ValueError | RQ_CHIP_EQ | 1 |" in lines
    assert "| 확보율 멈춤 | 확보율 | ValueError | - | 1 |" in lines


def _official_revision(scenario_no: int, *official: int) -> script.RevisionRow:
    return script.RevisionRow(
        scenario_no=scenario_no,
        revision_no=1,
        revision_id=f"r{scenario_no}",
        dataset_id=f"d{scenario_no}",
        source_group="내장 시드",
        archived=False,
        official=official,
    )


def test_the_official_line_states_a_zero_density_stop() -> None:
    """이력 전체의 `지난 공식버전 포함 Density 멈춤` 은 없다는 것도 확인한 값이라 0 이어도 적는다.

    판정값인 최신 공식의 `Density` 칸이 앞에 온다(사내 런북 6-3 a).
    """
    outcome = script.Outcome(script.CALCULATED, density=script.CALCULATED)

    lines = script.summary_lines([_official_revision(1, 1)], [outcome], active_only=False)

    assert (
        "- 공식버전 — 최신 공식 v1(S1 r1) 됨 · Density 됨 · "
        "이력이 가리키는 리비전 1개: 됨 1 · 지난 공식버전 포함 Density 멈춤 0"
    ) in lines
    # 멈춘 리비전이 없으면 갈래 표를 찍지 않는다.
    assert not [line for line in lines if line.startswith("- 멈춘 리비전의 갈래")]


def test_only_the_latest_official_decides_and_an_older_stop_is_counted_apart() -> None:
    """지난 공식버전(v1)만 Density 에서 멈추고 최신 공식(v2)은 선다.

    판정값은 최신 공식의 `Density` 칸(됨)이고, 이력 전체의 멈춤은 이름을 따로 단 수로만 남는다
    — 지난 공식버전의 멈춤은 그 시나리오를 다시 열어 저장할 때만 경고가 붙는다(사내 런북 6-3 a).
    """
    older = script.Outcome(
        script.CALCULATED,
        density=script.STOPPED,
        density_kind="ValueError",
        density_tables=("RQ_CHIP_EQ",),
    )
    latest = script.Outcome(script.CALCULATED, density=script.CALCULATED)

    lines = script.summary_lines(
        [_official_revision(1, 1), _official_revision(2, 2)], [older, latest], active_only=False
    )

    assert (
        "- 공식버전 — 최신 공식 v2(S2 r1) 됨 · Density 됨 · "
        "이력이 가리키는 리비전 2개: 됨 2 · 지난 공식버전 포함 Density 멈춤 1"
    ) in lines
    # 갈래 표에는 그대로 든다 — 지난 공식의 멈춤도 「발견」에 수로 옮길 거리다.
    assert "| Density 멈춤 | Density | ValueError | RQ_CHIP_EQ | 1 |" in lines
    guide = "\n".join(script.READING_GUIDE)
    assert (
        "**최신 공식의 `Density` 칸이 `됨` 이어야 한다** — 지난 공식버전의 Density 멈춤은 그 "
        "시나리오를 다시 열어 저장할 때만 경고가 붙는다(「발견」에 수만 옮긴다)."
    ) in guide
    assert "공식버전 줄의 `Density 멈춤` 은 0 이어야 한다" not in guide


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


def test_duplicate_route_keys_ignore_only_the_case_of_wf_division() -> None:
    """`WF 구분` 의 대소문자만 다른 행은 같은 경로다. 다른 컬럼의 대소문자는 그대로 견준다.

    계산(`_prepare_reqb`)이 다른 표기 차이를 이미 접어 결과에는 글자 그대로 같은 행이 없다 — 남는
    겹침은 `WF 구분` 의 대소문자뿐이라 그것만 무시한다.
    """
    row = {column: f"v-{column}" for column in REQB_COLUMNS}
    required = pd.DataFrame(
        [
            {**row, "WF 구분": "Buffer"},
            {**row, "WF 구분": "BUFFER"},
            {**row, "WF 구분": "buffer"},
            {**row, "WF 구분": "Core"},
            {**row, "WF 구분": "Buffer", "공정": "V-공정"},
        ]
    ).assign(소요대수=1.0)

    assert script.duplicate_route_keys(required) == 2


def _pkg_inputs(*divisions: str) -> dict[str, pd.DataFrame]:
    """PKG 경로 하나를 `WF 구분` 표기마다 한 행씩 둔 소요대수 입력(생산수량 100, 대당 Capa 50)."""
    route = {
        "생산계획년월": 202608,
        "Area_Name": "Main",
        "공정": "Process-A",
        "양산구분": "양산",
        "제품정보": "Product-A",
        "Stack": "12H",
        "Capa Code": "CAPA-A",
        "Customer": "Customer-A",
        "CS": "MP",
        "STEP_SEQ": "10",
        "MCP_SEQ": "1",
        "소요기준": "PKG",
    }
    plan_keys = ("생산계획년월", "양산구분", "제품정보", "Stack", "Capa Code", "Customer", "CS")
    capacity_keys = (
        "생산계획년월",
        "Area_Name",
        "공정",
        "STEP_SEQ",
        "MCP_SEQ",
        "소요기준",
        "양산구분",
        "제품정보",
        "Stack",
    )
    return {
        "reqb": pd.DataFrame([{**route, "WF 구분": division} for division in divisions]),
        "plan": pd.DataFrame([{**{key: route[key] for key in plan_keys}, "생산수량": 100.0}]),
        "yield_data": pd.DataFrame(),
        "chip_qty": pd.DataFrame(),
        "unit_capacity": pd.DataFrame(
            [
                {**{key: route[key] for key in capacity_keys}, "WF 구분": division}
                for division in divisions
            ]
        ).assign(**{"대당 Capa": 50.0}),
    }


def test_a_pkg_buffer_route_saved_in_two_spellings_is_counted_after_the_calculation() -> None:
    """한 경로에 `Buffer`·`BUFFER` 두 행이 저장된 옛 리비전 — 계산은 둘을 다 세고 집계가 센다.

    PKG 부하량은 `WF 구분` 없이 붙고 Buffer 판정은 대소문자를 무시하므로 두 행이 같은 부하를 받아
    그 경로의 소요대수가 두 배다(계산은 이 행을 접지 않는다 — 런북 6-3 a 가 옛 리비전의 수를
    잰다). 글자 그대로 세면 0 이라 이 자리를 놓친다. 계산이 접게 되면 앞 두 단언도 같이 고친다.
    """
    doubled = calculate_required_equipment(**_pkg_inputs("Buffer", "BUFFER"))
    single = calculate_required_equipment(**_pkg_inputs("BUFFER"))

    assert doubled["소요대수"].tolist() == pytest.approx([2.0, 2.0])
    assert int(doubled.duplicated(subset=REQB_COLUMNS).sum()) == 0
    assert script.duplicate_route_keys(doubled) == 1
    assert single["소요대수"].tolist() == pytest.approx([2.0])
    assert script.duplicate_route_keys(single) == 0


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


@pytest.mark.parametrize(
    "target",
    [
        PROJECT_ROOT / "data" / "capa_simulation.duckdb",
        PROJECT_ROOT / "data" / "temp" / "copy" / "capa_simulation.duckdb",
        PROJECT_ROOT / "data" / ".." / "data" / "other.duckdb",
    ],
    ids=["operational-db", "under-data", "dotted-path"],
)
def test_the_operational_database_place_is_refused_before_it_opens(
    target: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """사본 강제 — 운영 DB 자리(`settings.DUCKDB_PATH` · 저장소 `data/` 아래)는 열기 전에 거절한다.
    이 거절이 권한 템플릿에 이 스크립트를 허용할 전제다(런북 6-3 a · `docs/TODO.md` 결정 12)."""

    def must_not_open(*_args: object, **_kwargs: object) -> duckdb.DuckDBPyConnection:
        raise AssertionError("운영 DB 자리는 열지 않는다")

    monkeypatch.setattr(duckdb, "connect", must_not_open)

    code, output = _run(capsys, "--database", str(target))

    assert code == 2
    assert "운영 DB 자리" in output and "DB 를 열지 않았다" in output
    assert str(PROJECT_ROOT) not in output


def test_a_moved_operational_database_is_refused_wherever_settings_point(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """운영 DB 를 `settings.DUCKDB_PATH` 로 옮겨 두어도 그 파일과 그 폴더는 거절하고, 다른 폴더의
    사본은 그대로 받는다."""
    operational = tmp_path / "live" / "capa_simulation.duckdb"
    monkeypatch.setattr(script, "DUCKDB_PATH", operational)

    assert script.operational_path(operational)
    assert script.operational_path(operational.parent / "sibling.duckdb")
    assert not script.operational_path(tmp_path / "copy" / "capa_simulation.duckdb")

    code, output = _run(capsys, "--database", str(operational))
    assert code == 2
    assert str(tmp_path) not in output


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


# 새 파이썬에서 로그 끄기 단계를 정해 두고 이 스크립트를 불러온 뒤 그 단계를 찍는다.
_IMPORT_UNDER_DISABLED_LOGGING = """
import logging
import sys

logging.disable(int(sys.argv[2]))
sys.path.insert(0, sys.argv[1])
import inspect_revision_calculations

print(logging.root.manager.disable)
"""


@pytest.mark.parametrize("level", [logging.NOTSET, logging.CRITICAL])
def test_importing_keeps_stderr_quiet_and_the_logging_level(level: int) -> None:
    """`capacity_gate` 가 딸려 오는 Streamlit 캐시 래퍼의 「No runtime found」 경고를 찍지 않고,
    불러오기 전 로그 끄기 단계를 그대로 돌려놓는다 — `benchmark_home.py` 는 로그를 끈 채 이 모듈을
    불러온다(되살리면 HOME 이 멈춘 문구를 Streamlit 로그가 찍는다). 이 pytest 프로세스는 이미
    불러왔으므로 새 프로세스에서 본다."""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(PROJECT_ROOT / "src"), *filter(None, [environment.get("PYTHONPATH")])]
    )
    finished = subprocess.run(
        [
            sys.executable,
            "-c",
            _IMPORT_UNDER_DISABLED_LOGGING,
            str(PROJECT_ROOT / "scripts"),
            str(level),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=PROJECT_ROOT,
        env=environment,
        timeout=120,
        check=False,
    )

    assert finished.returncode == 0, finished.stderr[-2000:]
    assert finished.stdout.strip() == str(level)
    assert finished.stderr == ""
