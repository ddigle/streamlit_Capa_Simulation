# Purpose: 사내 실데이터 확인 스크립트가 읽기만 하고 집계만 찍어 식별값을 내보내지 않는지 본다.

"""`scripts/inspect_real_data_checks.py` 의 약속은 셋이다 — 읽기만 한다, 집계만 찍는다, 실패도
종류만 적는다. 출력은 리뷰 문서를 거쳐 사외로 나가는 유일한 것이라 **새면 그대로 밖으로 나간다.**

그래서 합성 DB 에 눈에 띄는 표지값(`ZZSENTINEL…`)을 심고 — 제품·고객·공정·시나리오·원천 코드·설비명·
Main 설비·메모, 그리고 자릿수가 많은 기존 결과 값 — 출력 어디에도 그것이 없는지 본다. 일부러 오류를
내 그 문구에 표지값이 실려도 나가지 않는지도 본다.

BigDataQuery 는 사내 전용 패키지라 가짜 `bigdataquery` 모듈을 `sys.modules` 에 넣는다. 스크립트는
앱과 같은 어댑터 경로(`load_bigdataquery_module` → `call_get_data`)로 그것을 부른다.
"""

from __future__ import annotations

import hashlib
import importlib.machinery
import re
import sys
import types
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from capa_simulation.application_bootstrap import ensure_initial_scenario
from capa_simulation.io.bigdataquery_catalog import CATALOG_COLUMNS
from capa_simulation.io.company_bigdataquery_adapter import BDQ_USER_NAME_ENV
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.equipment_contract import (
    BASELINE_COLUMNS,
    DOWNTIME_COLUMNS,
    EQUIPMENT_COLUMNS,
    PARENT_EQUIPMENT_COLUMN,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import inspect_real_data_checks as checks  # noqa: E402

SENTINEL = "ZZSENTINEL"
# 기존 결과 컬럼에 심는 값. 출력은 비율을 4자리 유효숫자로만 찍으므로 이 자릿수가 보이면 샌 것이다.
LEGACY_VALUES = {
    "소요대수": 98765.4321,
    "PCB수(K매)": 87654.3219,
    "GOOD_DIE": 76543.2198,
}
RENAMED_COLUMNS = {
    "제품정보": f"{SENTINEL}X ",
    "공정": f"{SENTINEL}P-",
    "Customer": f"{SENTINEL}C-",
    "Capa Code": f"{SENTINEL}K-",
    "Pack Code": f"{SENTINEL}PK-",
}
TODAY = date(2026, 10, 7)


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _plant_sentinels(path: Path) -> None:
    """내장 시드의 이름을 표지값으로 바꾼다. 모든 표를 같이 바꿔 계산의 조인은 그대로 선다."""
    with duckdb.connect(str(path)) as connection:
        columns = connection.execute(
            "SELECT table_schema, table_name, column_name FROM information_schema.columns "
            "WHERE table_schema IN ('raw_data', 'rev_data', 'ref_data')"
        ).fetchall()
        for schema, table, column in columns:
            prefix = RENAMED_COLUMNS.get(str(column))
            if prefix is None:
                continue
            connection.execute(
                f'UPDATE {schema}.{table} SET "{column}" = ? || "{column}" '
                f'WHERE "{column}" IS NOT NULL',
                [prefix],
            )
        for column, value in LEGACY_VALUES.items():
            connection.execute(f'UPDATE raw_data.core_data SET "{column}" = ?', [value])
        connection.execute(
            "UPDATE app_meta.scenario SET scenario_name = ?, source_simulation_code = ?, "
            "source_simulation_name = ?",
            [f"{SENTINEL}SCEN", f"{SENTINEL}CODE", f"{SENTINEL}SNAME"],
        )
        connection.execute(
            "UPDATE app_meta.scenario_revision SET revision_name = ?, note = ?",
            [f"{SENTINEL}REV", f"{SENTINEL}NOTE"],
        )


@pytest.fixture(scope="module")
def simulation_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("simulation") / "capa_simulation.duckdb"
    repository = DuckDBScenarioRepository(path)
    repository.initialize()
    ensure_initial_scenario(repository)
    _plant_sentinels(path)
    return path


def _equipment_row(
    unit: str,
    parent: str | None,
    ratio: float,
    *,
    arrival: str | None = "2026-01-05",
    qual: str | None = "2026-01-20",
    status: str | None = "완료",
) -> dict[str, object]:
    row: dict[str, object] = {column: None for column in EQUIPMENT_COLUMNS}
    row.update(
        {
            "설비명": unit,
            "공정소분류": f"{SENTINEL}PROC",
            "공정대분류": "B/N",
            "공정구분": "L1",
            "투자구분": "양산",
            "동": "C1",
            "층": "1F",
            "반입일정": arrival,
            "Qual일정": qual,
            "확정상태": status,
            "보관유무": "N",
            "기존설비여부": "N",
            "레이아웃표시": "N",
            "환산비": ratio,
            "메모1": f"{SENTINEL}MEMO",
            "설비이력": f"{SENTINEL}HISTORY",
            PARENT_EQUIPMENT_COLUMN: parent,
        }
    )
    return row


@pytest.fixture(scope="module")
def equipment_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Main 설비 묶음 하나(모듈 넷, 환산비 0.2 로 잘림), 옛 자리표 Qual 한 대, 반입 미정 한 대."""
    path = tmp_path_factory.mktemp("equipment") / "equipment_availability.duckdb"
    repository = DuckDBEquipmentRepository(path)
    repository.initialize()
    rows = [_equipment_row(f"{SENTINEL}EQ-M{index}", f"{SENTINEL}MAIN", 0.2) for index in range(4)]
    rows.append(
        _equipment_row(f"{SENTINEL}EQ-Q", None, 1.0, arrival="2026-02-01", qual="2262-04-11")
    )
    rows.append(_equipment_row(f"{SENTINEL}EQ-A", None, 1.0, arrival=None, qual=None, status=None))
    repository.save_snapshot(
        pd.DataFrame(columns=list(BASELINE_COLUMNS)),
        pd.DataFrame(rows, columns=list(EQUIPMENT_COLUMNS)),
        pd.DataFrame(columns=list(DOWNTIME_COLUMNS)),
    )
    return path


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    code = checks.main([*argv, "--today", TODAY.isoformat()])
    return code, capsys.readouterr().out


def _assert_no_leak(output: str) -> None:
    assert SENTINEL not in output
    for value in LEGACY_VALUES.values():
        assert f"{value}" not in output
        assert f"{value:,}" not in output
        assert f"{value:.2f}" not in output


def test_db_checks_print_aggregates_and_never_the_planted_names(
    simulation_db: Path, equipment_db: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = (_md5(simulation_db), _md5(equipment_db))

    code, output = _run(
        capsys,
        "--database",
        str(simulation_db),
        "--equipment-database",
        str(equipment_db),
    )

    assert code == 0
    _assert_no_leak(output)
    # 읽기만 했다 — 파일이 한 바이트도 바뀌지 않는다.
    assert (_md5(simulation_db), _md5(equipment_db)) == before
    for heading in ("### 8-1.", "### 8-2.", "### 8-3.", "### 8-4."):
        assert heading in output
    assert "### 8-5." not in output  # BigDataQuery 는 따로 부를 때만
    # 경로는 찍지 않고 파일 이름만.
    assert str(simulation_db.parent) not in output
    assert "`capa_simulation.duckdb`" in output
    # 소요대수는 원천에 값이 차면 대조까지 간다.
    assert "신규 경로 키 72 중 원천 경로에 있는 키 72 (100.00%)" in output
    assert "| 경로 키 13 · 같은 경로 반복을 접음 | 72 |" in output
    assert "계획 줄×WF 구분" in output  # PCB 절
    # 설비 — 잘린 환산비·옛 자리표·일정 미정.
    assert "| **모듈 행 환산비 0.2** — 다시 입력할 행 | 4 |" in output
    assert "| Main 설비 묶음 / 그 가운데 모듈 환산비 합이 1 이 아닌 묶음(±0.01) | 1 / 1 |" in output
    assert "| Qual일정 = 2262-04-11 (최신 리비전, 이제 빈 Qual 로 읽음) | 1 |" in output
    assert "반입 미정 1대(1행) · Qual 미정 1대(1행)" in output
    assert "옛 자리표 2262-04-11 에서 온 것 1행" in output


def test_an_error_message_carrying_names_is_reported_by_kind_only(
    simulation_db: Path,
    equipment_db: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """이 앱의 검증 오류 문구에는 설비명·공정명이 실린다. 스크립트는 예외 종류만 적는다."""

    def broken(*_args: object, **_kwargs: object) -> pd.DataFrame:
        raise ValueError(f"{SENTINEL}EQ-M0 의 일정이 틀렸습니다")

    monkeypatch.setattr(checks, "_read_snapshot", broken)
    monkeypatch.setattr(checks, "calculate_unit_capacity", broken)

    code, output = _run(
        capsys,
        "--only",
        "legacy,equipment",
        "--database",
        str(simulation_db),
        "--equipment-database",
        str(equipment_db),
    )

    assert code == 0
    _assert_no_leak(output)
    assert "- 신규 소요대수 계산 실패(ValueError) — 대조하지 않았다" in output
    assert "- 일정 미정 — 실패(ValueError)" in output


def test_an_unknown_demand_basis_is_counted_not_named(
    simulation_db: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "capa_simulation.duckdb"
    path.write_bytes(simulation_db.read_bytes())
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            'UPDATE rev_data.rq_reqb SET "소요기준" = ? WHERE source_row_no = 1',
            [f"{SENTINEL}BASIS"],
        )

    code, output = _run(capsys, "--only", "reqb", "--database", str(path))

    assert code == 0
    _assert_no_leak(output)
    assert "- 그 밖의 소요기준 1종 1행 1공정(값은 적지 않는다)" in output


def test_a_newer_clone_dataset_is_not_taken_for_the_source(
    simulation_db: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """복제·월 병합·연도 이동은 리비전 1 이 원천 그대로가 아니다. 더 최근이어도 고르지 않는다."""
    path = tmp_path / "capa_simulation.duckdb"
    path.write_bytes(simulation_db.read_bytes())
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            "INSERT INTO app_meta.dataset (dataset_id, scenario_id, source_type, imported_at, "
            "pipeline_version, status) "
            "SELECT 'clone-dataset', 'clone-scenario', 'DUCKDB_SCENARIO_CLONE', "
            "imported_at + INTERVAL 1 DAY, pipeline_version, status FROM app_meta.dataset"
        )

    code, output = _run(capsys, "--only", "legacy", "--database", str(path))

    assert code == 0
    _assert_no_leak(output)
    assert "데이터셋(전체 2개 · 원천에서 온 것 1개) · 원천 종류 `BUILTIN_SYNTHETIC_SEED`" in output
    assert "⚠" not in output


def test_derived_source_types_are_the_ones_the_app_writes() -> None:
    """이름이 바뀌면 복제가 원천으로 잘못 골린다. 앱 코드에 같은 글자가 있어야 한다."""
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (PROJECT_ROOT / "src" / "capa_simulation").rglob("*.py")
    )
    for source_type in checks.DERIVED_SOURCE_TYPES:
        assert f'"{source_type}"' in sources


def test_output_file_holds_the_same_markdown(
    simulation_db: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "real_data_check.md"

    code, output = _run(
        capsys, "--only", "env,reqb", "--database", str(simulation_db), "--output", str(target)
    )

    assert code == 0
    written = target.read_bytes().decode("utf-8")
    assert b"\r" not in target.read_bytes()
    assert written.strip() == output.strip()
    assert SENTINEL not in written


def test_a_locked_database_stops_with_the_app_running_message(
    simulation_db: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def locked(*_args: object, **_kwargs: object) -> duckdb.DuckDBPyConnection:
        raise duckdb.IOException(f"Could not set lock on file {SENTINEL}")

    monkeypatch.setattr(duckdb, "connect", locked)

    code, output = _run(capsys, "--only", "env", "--database", str(simulation_db))

    assert code == 1
    assert "앱이 떠 있으면 먼저 끄세요" in output
    assert SENTINEL not in output


def test_unknown_block_names_are_refused(capsys: pytest.CaptureFixture[str]) -> None:
    code, output = _run(capsys, "--only", "env,nope")

    assert code == 2
    assert "nope" in output


def test_catalog_defaults_match_the_registration_screen() -> None:
    from capa_simulation.components import bigdataquery_registration
    from capa_simulation.io.bigdataquery_catalog import MAX_CATALOG_WINDOW_DAYS

    assert checks.CATALOG_DEFAULT_DAYS == bigdataquery_registration.DEFAULT_CATALOG_DAYS
    assert checks.CATALOG_BUSY_ROWS == bigdataquery_registration.CATALOG_BUSY_ROWS
    assert checks.CATALOG_MAX_DAYS == MAX_CATALOG_WINDOW_DAYS


def test_value_shapes_keep_the_form_and_drop_the_letters() -> None:
    assert checks._value_shape("2026-09-02 03:04:05") == "9999-99-99 99:99:99"
    assert checks._value_shape("Sim_한글 7") == "AAA_?? 9"
    assert checks._ranges([1, 4, 5, 6, 9, 10]) == "1, 4–6, 9–10"


# ------------------------------------------------------------------------------- BigDataQuery

# 가짜 원천 — 코드마다 원천 등록일과, 그 코드의 행이 적재된 날(등록일 기준 며칠 뒤)·행 수.
VALID_A = f"{SENTINEL}OK-A"
VALID_B = f"{SENTINEL}OK-B"
INVALID = f"{SENTINEL} BAD CODE"
REGISTERED = {VALID_A: date(2026, 9, 1), VALID_B: date(2026, 9, 20), INVALID: date(2026, 9, 25)}
LOADS = {
    VALID_A: {0: 100, 5: 20},  # +5 일 적재분 20행은 기본 창(−7~+3) 밖이다
    VALID_B: {0: 50},
    INVALID: {0: 10},
}


def _window_of(sql: str) -> tuple[date, date]:
    start, end = re.findall(r"impala_insert_time\s*[<>]=?\s*'(\d{4}-\d{2}-\d{2})'", sql)
    return date.fromisoformat(start), date.fromisoformat(end)


def _loaded(code: str, sql: str) -> dict[date, int]:
    start, end = _window_of(sql)
    days = {REGISTERED[code] + timedelta(days=offset): rows for offset, rows in LOADS[code].items()}
    return {day: rows for day, rows in days.items() if start <= day < end}


def _fake_bigdataquery(
    *, fail_load_days: bool = False, need_user: bool = False
) -> types.ModuleType:
    module = types.ModuleType("bigdataquery")
    module.__spec__ = importlib.machinery.ModuleSpec("bigdataquery", None)

    def getData(  # noqa: N802 — 사내 패키지의 이름 그대로
        *, param: str, convert_type: bool, verbose: bool, user_name: str = ""
    ) -> pd.DataFrame:
        if need_user and not user_name:
            raise Exception("parameter user_name is necessary.")
        if "SELECT DISTINCT" in param:
            start, end = _window_of(param)
            rows = [
                {
                    "simulation_name": f"{SENTINEL}NAME {index}",
                    "simulation_code": code,
                    "plan_name": f"{SENTINEL}PLAN",
                    "plan_code": f"{SENTINEL}PLANCODE",
                    "regist_data": f"{registered:%Y-%m-%d} 09:00:00",
                }
                for index, (code, registered) in enumerate(REGISTERED.items())
                if start <= registered < end
            ]
            return pd.DataFrame(rows, columns=list(CATALOG_COLUMNS))
        code = re.search(r"catb_sim_info_id = '([^']+)'", param)
        assert code is not None
        loaded = _loaded(code.group(1), param)
        if "load_day" in param:
            if fail_load_days:
                raise RuntimeError(f"AnalysisException near {SENTINEL}")
            return pd.DataFrame(
                {
                    "load_day": [f"{day:%Y-%m-%d}" for day in loaded],
                    "row_count": list(loaded.values()),
                }
            )
        return pd.DataFrame({"시뮬레이션 ID": [code.group(1)] * sum(loaded.values())})

    module.getData = getData  # type: ignore[attr-defined]
    return module


def test_bigdataquery_absent_is_skipped_with_a_clear_line(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "bigdataquery", None)

    code, output = _run(capsys, "--only", "bdq")

    assert code == 0
    assert "`bigdataquery` 패키지가 없다" in output
    assert "이 절은 건너뛴다" in output


def test_bigdataquery_block_measures_windows_without_naming_codes(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "bigdataquery", _fake_bigdataquery())
    monkeypatch.setenv(BDQ_USER_NAME_ENV, f"{SENTINEL}USER")

    code, output = _run(capsys, "--only", "bdq", "--bdq-sample", "5")

    assert code == 0
    _assert_no_leak(output)
    assert "요청자 계정(`CAPA_BDQ_USER_NAME`) 있음" in output
    # 기본 목록(오늘−30일 ~ 오늘, 화면과 같다)은 9-20·9-25 두 코드, 366일 목록은 셋.
    assert re.search(
        r"\| 기본\(오늘−30일 ~ 오늘\) \| 31일 \| 성공 \| [\d.]+ \| 2 \| 2 \| 2 \| 아니오 \|",
        output,
    )
    assert re.search(
        r"\| 상한 366일 \| 366일 \| 성공 \| [\d.]+ \| 3 \| 3 \| 3 \| 아니오 \|", output
    )
    assert "- `reg_date` dtype `object` · 빈 값 0 / 3" in output
    assert "`9999-99-99 99:99:99` 3" in output
    assert "코드 3개 중 1개 (빈 값 0 · 가운데 공백 1" in output
    # 규칙을 지키는 두 코드가 표본이고, A 는 +5 일 적재분 20행을 기본 창이 놓친다.
    assert "| 기본 창(−7~+3일) 행 = 넓은 창(±30일) 행 | 1 / 2 |" in output
    assert "| 기본 창이 놓친 행 | 전체의 11.76% · 코드별 최대 16.67% |" in output
    assert "| 여러 날에 나눠 적재된 코드 | 1 / 2 |" in output
    assert "| 기본 창(−7~+3일) 밖 적재일이 있는 코드 | 1 / 2 |" in output
    assert "| 끝 적재일 − 끝 원천 등록일(일) | 최소 0 · 최대 5 |" in output


def test_bigdataquery_failures_are_named_by_kind_only(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """새 적재일 SQL 이 사내 엔진에서 돌지 않아도 나머지는 계속하고, 엔진 문구는 내보내지 않는다."""
    monkeypatch.setitem(sys.modules, "bigdataquery", _fake_bigdataquery(fail_load_days=True))

    code, output = _run(capsys, "--only", "bdq", "--bdq-no-max-window")

    assert code == 0
    _assert_no_leak(output)
    assert "상한 366일" not in output
    assert "0 / 1 성공 · 조회 실패(RuntimeError)" in output
    assert "| 상세 조회(앱과 같은 SQL) | 1 / 1 성공 |" in output


def test_bigdataquery_without_an_account_says_what_to_set(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "bigdataquery", _fake_bigdataquery(need_user=True))
    monkeypatch.delenv(BDQ_USER_NAME_ENV, raising=False)

    code, output = _run(capsys, "--only", "bdq")

    assert code == 0
    assert "요청자 계정 필요 — `CAPA_BDQ_USER_NAME` 를 넣고" in output
    assert "목록 조회가 모두 실패해 나머지는 건너뛴다" in output
