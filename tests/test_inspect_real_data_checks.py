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
from capa_simulation.io.company_bigdataquery_adapter import BDQ_USER_NAME_ENV, QueryWindow
from capa_simulation.io.core_data_source import load_core_data_contract
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.core_data_derivation import build_q_core_data
from capa_simulation.services.equipment_contract import (
    BASELINE_COLUMNS,
    DOWNTIME_COLUMNS,
    EQUIPMENT_COLUMNS,
    PARENT_EQUIPMENT_COLUMN,
)
from capa_simulation.services.legacy_comparison import COMPARISONS
from capa_simulation.services.required_equipment import LOAD_KEYS, REQB_COLUMNS

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
    usage: str | None = "HBM",
) -> dict[str, object]:
    row: dict[str, object] = {column: None for column in EQUIPMENT_COLUMNS}
    row.update(
        {
            "설비명": unit,
            "공정소분류": f"{SENTINEL}PROC",
            "공정대분류": "B/N",
            "공정구분": "L1",
            "투자구분": "양산",
            # 일정 미정 알림은 Dynamic 이 세는 호기(사용기준 HBM·EDP)만 센다(2026-10-08 결정).
            "사용기준": usage,
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
    # 사용기준이 EDP 인 호기는 HBM 과 함께 센다(2026-10-08 사용자 결정) — 줄에 따로 센다.
    rows.append(_equipment_row(f"{SENTINEL}EQ-E", None, 1.0, usage="EDP"))
    # 사용기준이 HBM·EDP 가 아닌 호기 — 값은 표지값이라 찍히면 누출이다.
    rows.append(_equipment_row(f"{SENTINEL}EQ-U", None, 1.0, usage=f"{SENTINEL}USAGE"))
    rows.append(_equipment_row(f"{SENTINEL}EQ-B", None, 1.0, usage=None))
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
    # 기존 값이 표지값 하나라 60 배 무리가 없다 — 가르기는 한 줄로 끝난다.
    assert "- ≈60 배 가르기 — 비율이 정의된 경로 키 72 가운데 ≈60 이 없어 건너뛴다" in output
    # Chip 부하량은 정식 대조 표의 한 줄이다. 답이 난 탐색 비율(GOOD_DIE 등)은 더 찍지 않는다.
    assert "| Chip `Plan_Chip(K개)` | 24 |" in output
    assert "GOOD_DIE` ÷" not in output
    assert "Plan_Chip(K개) · GOOD_DIE" not in output
    assert "계획 줄×WF 구분" in output  # PCB 절
    # 설비 — 잘린 환산비·옛 자리표·일정 미정.
    assert "| **모듈 행 환산비 0.2** — 다시 입력할 행 | 4 |" in output
    assert "| Main 설비 묶음 / 그 가운데 모듈 환산비 합이 1 이 아닌 묶음(±0.01) | 1 / 1 |" in output
    assert "| Qual일정 = 2262-04-11 (최신 리비전, 이제 빈 Qual 로 읽음) | 1 |" in output
    assert "반입 미정 1대(1행) · Qual 미정 1대(1행)" in output
    assert "옛 자리표 2262-04-11 에서 온 것 1행" in output
    assert (
        "HBM 6행 · EDP 1행 · 다른 값 1행 · 빈 칸 1행 / 가용대수에서 빠지는 설비 2대(설비 6대 중)"
        in output
    )


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


def _plant_sixty_fold(path: Path) -> tuple[int, int, int]:
    """원천 `소요대수` 를 신규 × 60(MI 공정 전부 · WF 공정의 202607 이후) 또는 × 1 로 다시 싣는다.

    표지값도 더 심는다 — 계약 밖 `WF 구분`(내장 시드의 `Base`)과 원천에만 있는 `메이커`·`모델명`.
    돌려주는 것은 (≈60 키, MI 키, WF 공정의 ≈1 키).
    """
    with duckdb.connect(str(path)) as connection:
        tables = connection.execute(
            "SELECT table_schema, table_name FROM information_schema.columns "
            "WHERE column_name = 'WF 구분' AND table_schema IN ('raw_data', 'rev_data', 'ref_data')"
        ).fetchall()
        for schema, table in tables:
            connection.execute(
                f'UPDATE {schema}.{table} SET "WF 구분" = ? WHERE "WF 구분" = ?',
                [f"{SENTINEL}WF", "Base"],
            )
        connection.execute(
            'UPDATE raw_data.core_data SET "메이커" = ?, "모델명" = ?',
            [f"{SENTINEL}MAKER", f"{SENTINEL}MODEL"],
        )
    session = checks.Session(simulation_path=path, equipment_path=path, dataset_id=None)
    session.simulation, _, _ = checks._open_read_only(path)
    source = checks.load_source(session)
    session.close()
    assert source is not None
    core = build_q_core_data(source.raw, load_core_data_contract())
    required = checks._required_equipment(source.tables)

    def keyed(frame: pd.DataFrame) -> pd.DataFrame:
        keys = pd.DataFrame(
            {key: frame[key].astype("string").str.strip() for key in REQB_COLUMNS},
            index=frame.index,
        )
        keys["생산계획년월"] = pd.to_numeric(frame["생산계획년월"]).astype("Int64").astype("string")
        return keys

    route = keyed(core.loc[core["Area_Name"].notna()])
    route["_행"] = route.index
    fresh = keyed(required).assign(신규=required["소요대수"].to_numpy())
    merged = route.merge(fresh, on=REQB_COLUMNS, how="inner")
    sixty = merged["Area_Name"].eq("MI") | (
        merged["소요기준"].eq("WF") & merged["생산계획년월"].ge("202607")
    )
    merged["기존"] = merged["신규"] * sixty.map({True: 60.0, False: 1.0})
    with duckdb.connect(str(path)) as connection:
        row_numbers = [
            int(row[0])
            for row in connection.execute(
                "SELECT source_row_no FROM raw_data.core_data ORDER BY source_row_no"
            ).fetchall()
        ]
        connection.execute('UPDATE raw_data.core_data SET "소요대수" = NULL')
        connection.executemany(
            'UPDATE raw_data.core_data SET "소요대수" = ? WHERE source_row_no = ?',
            [
                [float(value), row_numbers[int(index)]]
                for index, value in zip(merged["_행"], merged["기존"], strict=True)
            ],
        )
    wf_agree = int((merged["소요기준"].eq("WF") & ~sixty).sum())
    return int(sixty.sum()), int(merged["Area_Name"].eq("MI").sum()), wf_agree


def test_the_sixty_fold_group_is_localized_by_counts_only(
    simulation_db: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """일부러 만든 ×60 무리(MI 공정 전부 · WF 공정의 뒤 여섯 달)를 가르기가 찾는다. 값은 안 샌다."""
    path = tmp_path / "capa_simulation.duckdb"
    path.write_bytes(simulation_db.read_bytes())
    suspects, mi_keys, wf_agree = _plant_sixty_fold(path)
    total = 72
    assert 0 < wf_agree < suspects < total

    code, output = _run(capsys, "--only", "legacy", "--database", str(path))

    assert code == 0
    _assert_no_leak(output)
    assert "Base" not in output
    assert "**소요대수 ≈60 배 가르기**" in output
    assert (
        f"- 비율이 정의된 경로 키 {total} — ≈60 {suspects}(그 가운데 60 ±0.1% 안 {suspects}) · "
        f"≈1 {total - suspects} · 그 밖 0 · 비율이 정의되지 않은 키 0"
    ) in output
    # 속성 — MI 경로는 전부 ≈60 이다. 계약 밖 WF 구분은 이름 없이 종류 수만.
    assert f"| MI 경로 | {mi_keys} | 0 | 0 |" in output
    assert "| WF 구분 CORE |" in output
    assert "| WF 구분 그 밖(1종) |" in output
    # 공정 — WF 공정 하나가 섞였고, 달이 그것을 가른다. 설비 칸은 값이 하나라 못 가른다.
    assert "**≈60 과 ≈1 이 섞임 1**" in output
    assert "| `생산계획년월` | 1 | 0 | 0 |" in output
    assert "| `제품정보` | 0 | 1 | 0 |" in output
    assert "| `메이커` | 0 | 1 | 0 |" in output
    # 인자 — ST(MI)·RUN_DAY(달×공정)는 ≈1 을 건드리지 않고 고치고, 공정 단위 모듈수는 WF 공정의
    # ≈1 키를 같이 어긋나게 한다.
    assert re.search(rf"\| ST \| MI \| {mi_keys} / 0 \|.*\| {mi_keys} / {mi_keys} \| 0 \|", output)
    assert re.search(rf"\| RUN_DAY \| 전부 \|.*\| {suspects} / {suspects} \| 0 \|", output)
    assert re.search(rf"\| 모듈수 \| 전부 \|.*\| {mi_keys} / {suspects} \| {wf_agree} \|", output)
    # 원천 범주 칸 — 표지값 모델명 하나를 두 무리가 같이 쓴다(값은 적지 않는다).
    assert "| `모델명` | 1 / 1 / 0 | 1 | 0 (0키) | 0 | - |" in output


def _plant_route_wafers(path: Path) -> int:
    """경로 행의 `WF수(매)` 를 신규 계획 줄 Wafer 부하량 × `Step수` 로 다시 싣는다(STEP 마다 2·3·4).

    계획 행은 그대로 둔다 — 사내처럼 같은 계획 줄 × WF 구분 안에서 경로마다 값이 갈린다. 계획 줄
    값을 신규 계산으로 두므로 경로 키 맞대기의 기존÷신규가 그 경로의 Step수 가 된다. 돌려주는 것은
    갈리는 계획 줄 × WF 구분 칸 수.
    """
    session = checks.Session(simulation_path=path, equipment_path=path, dataset_id=None)
    session.simulation, _, _ = checks._open_read_only(path)
    source = checks.load_source(session)
    session.close()
    assert source is not None
    core = build_q_core_data(source.raw, load_core_data_contract())
    required = checks._required_equipment(source.tables)
    plan = [key for key in LOAD_KEYS if key != "소요기준"]
    wafer = required.loc[required["소요기준"].eq("WF")]
    loads = _keyed(wafer, plan).assign(부하량=wafer["부하량"].to_numpy()).drop_duplicates(plan)
    routes = core.loc[core["Area_Name"].notna()]
    merged = _keyed(routes, plan).assign(_행=routes.index).merge(loads, on=plan, how="inner")
    steps = {step: count for count, step in enumerate(sorted(routes["STEP_SEQ"].unique()), 2)}
    merged["Step수"] = routes.loc[merged["_행"], "STEP_SEQ"].map(steps).to_numpy()
    with duckdb.connect(str(path)) as connection:
        row_numbers = [
            int(row[0])
            for row in connection.execute(
                "SELECT source_row_no FROM raw_data.core_data ORDER BY source_row_no"
            ).fetchall()
        ]
        connection.executemany(
            'UPDATE raw_data.core_data SET "Step수" = ?, "WF수(매)" = ? WHERE source_row_no = ?',
            [
                [str(step), float(load) * step, row_numbers[int(index)]]
                for index, load, step in zip(
                    merged["_행"], merged["부하량"], merged["Step수"], strict=True
                )
            ],
        )
    return int(merged.loc[merged["부하량"].gt(0), plan].drop_duplicates().shape[0])


def _keyed(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """맞대기용 키 — 글자는 앞뒤 공백을 떼고 월은 정수 글자로."""
    keyed = pd.DataFrame(
        {key: frame[key].astype("string").str.strip() for key in keys}, index=frame.index
    )
    keyed["생산계획년월"] = pd.to_numeric(frame["생산계획년월"]).astype("Int64").astype("string")
    return keyed


def test_route_wafer_values_are_split_by_the_column_that_carries_them(
    simulation_db: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """원천 경로 `WF수(매)` 가 Step수 를 따라 갈리면 가르기 표와 신규 맞대기가 그 칸을 짚는다."""
    path = tmp_path / "capa_simulation.duckdb"
    path.write_bytes(simulation_db.read_bytes())
    cells = _plant_route_wafers(path)

    code, output = _run(capsys, "--only", "legacy", "--database", str(path))

    assert code == 0
    _assert_no_leak(output)
    assert "**Wafer `WF수(매)` 경로 값**" in output
    # 계획 줄 대조는 그대로 남고, 이제 값 불일치로 떨어진다.
    assert re.search(r"\| Wafer `WF수\(매\)` \| 0 \|.*\| \d+ \| 0 \| 0 \|", output)
    assert (
        f"- 계획 줄 × WF 구분 칸 {cells} 가운데 값이 갈리는 칸 {cells}(위 `값 불일치` 가 여기서 "
        f"난다) · 경로 행(Area_Name 있음)·양수만 남기면 칸 {cells} 가운데 ±0.1% 를 넘게 갈리는 칸 "
        f"**{cells}**"
    ) in output
    # Step수 는 경로마다 하나라 「자명」이고, 계획 줄 칸 안에서 한 값인 Para 는 가르지 못한다.
    assert f"| `Step수` | 0 | 0 | {cells} |" in output
    assert f"| `Para` | 0 | {cells} | 0 |" in output
    # Step수 로 나누면 모든 칸이 한 값이 된다. 칸 안에서 한 값인 Side반영률 은 가를 수 없다.
    assert f"| `Step수` | {cells} | 0 | {cells} | 0 |" in output
    assert f"| `Side반영률` | {cells} | {cells} | 0 | 0 |" in output
    assert "| `Lot 측정률` | " in output
    # 신규(계획 줄 Wafer)와 경로 키로 맞대면 기존÷신규가 WF 경로의 Step수 를 따라간다. 측정률은
    # 1 이 아니어도 따라가지 않는다.
    assert "| WF 경로 키 13 · 신규 `부하량` |" in output
    assert re.search(r"\| `Step수` \| (\d+) \| \1 \| \1 \| 0 \| 0 \|", output)
    assert re.search(r"\| `WF측정률` \| (\d+) \| \1 \| 0 \| 0 \| 0 \|", output)


def test_every_formal_comparison_has_a_new_calculation() -> None:
    assert {metric.legacy_column for metric in COMPARISONS} == set(checks.LOAD_BUILDERS)


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

# 가짜 원천 — 코드마다 원천 등록일과, 그 코드의 행이 적재된 날(등록일 기준 며칠 뒤)·행 수·내용 판.
# 같은 판이면 같은 행이다(날마다 통째로 다시 적재한 사본). 판이 바뀌면 값이 바뀐 재적재다.
VALID_A = f"{SENTINEL}OK-A"
VALID_B = f"{SENTINEL}OK-B"
VALID_C = f"{SENTINEL}OK-C"
INVALID = f"{SENTINEL} BAD CODE"
REGISTERED = {
    VALID_A: date(2026, 9, 1),
    VALID_B: date(2026, 9, 20),
    VALID_C: date(2026, 8, 20),
    INVALID: date(2026, 9, 25),
}
LOADS: dict[str, dict[int, tuple[int, int]]] = {
    # +5 일 적재분 20행은 기본 창(−7~+3) 밖이고 값도 바뀌었다(판 1).
    VALID_A: {0: (100, 0), 5: (20, 1)},
    VALID_B: {0: (50, 0)},
    # 사내 리뷰 202610081500 8-5 의 꼴 — 등록 하루 전부터 32일 동안 같은 내용을 매일 다시 적재했다.
    VALID_C: {offset: (40, 0) for offset in range(-1, 31)},
    INVALID: {0: (10, 0)},
}


def _window_of(sql: str) -> tuple[date, date]:
    start, end = re.findall(r"impala_insert_time\s*[<>]=?\s*'(\d{4}-\d{2}-\d{2})'", sql)
    return date.fromisoformat(start), date.fromisoformat(end)


def _loaded(code: str, sql: str) -> dict[date, tuple[int, int]]:
    start, end = _window_of(sql)
    days = {REGISTERED[code] + timedelta(days=offset): load for offset, load in LOADS[code].items()}
    return {day: load for day, load in days.items() if start <= day < end}


def _detail_rows(code: str, rows: int, version: int) -> list[dict[str, object]]:
    """상세 SQL 이 돌려줄 행. 계획 줄 업무 키 넷과 경로마다 다른 값 — 이름은 표지값이다."""
    return [
        {
            "시뮬레이션 ID": code,
            "생산계획년월": 202610,
            "CS": "MP",
            "제품정보": f"{SENTINEL}P{index % 4}",
            "Stack": "8H",
            "Capa Code": f"{SENTINEL}CAPA",
            "Customer": f"{SENTINEL}CUST",
            "Pack Code": f"{SENTINEL}PK",
            "공정": f"{SENTINEL}S{index}",
            "WF수(매)": float(index * 10 + version),
        }
        for index in range(rows)
    ]


def _fake_bigdataquery(
    *, fail_load_days: bool = False, fail_code_days: bool = False, need_user: bool = False
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
        if "GROUP BY catb_sim_info_id" in param:
            if fail_code_days:
                raise RuntimeError(f"AnalysisException near {SENTINEL}")
            spans: list[dict[str, object]] = []
            for code in REGISTERED:
                loaded = _loaded(code, param)
                if loaded:
                    spans.append(
                        {
                            "simulation_code": code,
                            "load_days": len(loaded),
                            "first_day": f"{min(loaded):%Y-%m-%d}",
                            "last_day": f"{max(loaded):%Y-%m-%d}",
                            "row_count": sum(rows for rows, _ in loaded.values()),
                        }
                    )
            return pd.DataFrame(spans)
        found = re.search(r"catb_sim_info_id = '([^']+)'", param)
        assert found is not None
        loaded = _loaded(found.group(1), param)
        if "load_day" in param:
            if fail_load_days:
                raise RuntimeError(f"AnalysisException near {SENTINEL}")
            return pd.DataFrame(
                {
                    "load_day": [f"{day:%Y-%m-%d}" for day in loaded],
                    "row_count": [rows for rows, _ in loaded.values()],
                }
            )
        return pd.DataFrame(
            [
                row
                for rows, version in loaded.values()
                for row in _detail_rows(found.group(1), rows, version)
            ]
        )

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
    # 기본 목록(오늘−30일 ~ 오늘, 화면과 같다)은 9-20·9-25 두 코드, 366일 목록은 넷.
    assert re.search(
        r"\| 기본\(오늘−30일 ~ 오늘\) \| 31일 \| 성공 \| [\d.]+ \| 2 \| 2 \| 2 \| 아니오 \|",
        output,
    )
    assert re.search(
        r"\| 상한 366일 \| 366일 \| 성공 \| [\d.]+ \| 4 \| 4 \| 4 \| 아니오 \|", output
    )
    assert "- `reg_date` dtype `object` · 빈 값 0 / 4" in output
    assert "`9999-99-99 99:99:99` 4" in output
    assert "코드 4개 중 1개 (빈 값 0 · 가운데 공백 1" in output
    # 전 코드 적재일 — 1일(B)·2일(A)·32일(C), 규칙 위반 코드는 수로만.
    assert re.search(
        r"\| 조회\(목록 창 366일 전체를 GROUP BY 한 번, 사외에서 돌려 보지 못한 SQL\) \| "
        r"성공 · [\d.]+초 \|",
        output,
    )
    assert (
        "| 코드 | 규칙을 지키고 적재일을 읽은 코드 3 (결과 코드 4 · 규칙 위반 1 · "
        "적재일을 읽지 못함 0) |"
    ) in output
    assert "| 적재일 1일 · 2–5일 · 6일 이상 | 1 · 1 · 1 |" in output
    assert "| 적재일 폭 — 여러 날 코드 | 중앙 19 · p95 30.7 · 최대 32 |" in output
    assert (
        "| 여러 날 코드의 적재일 수 ÷ 폭(1 이면 하루도 빠짐없이 적재) | 중앙 0.6667 · 최소 0.3333 |"
    ) in output
    assert "| 여러 날 코드가 차지하는 행 | 전체의 96.55% |" in output
    assert "| 여러 날 코드 가운데 끝 적재일이 목록 창 끝날(오늘)인 코드 | 0 / 2 |" in output
    # 규칙을 지키는 세 코드가 표본이다. A 는 +5 일 적재분 20행을, C 는 32일 가운데 27일을 기본 창이
    # 놓친다(84.38% = 1 − 5/32, 사내 리뷰 202610081500 8-5 와 같은 꼴).
    assert "| 기본 창(−7~+3일) 행 = 넓은 창(±30일) 행 | 1 / 3 |" in output
    assert "| 기본 창이 놓친 행 | 전체의 75.86% · 코드별 최대 84.38% |" in output
    assert "| 여러 날에 나눠 적재된 코드 | 2 / 3 |" in output
    assert "| 기본 창(−7~+3일) 밖 적재일이 있는 코드 | 2 / 3 |" in output
    assert "| 끝 적재일 − 끝 원천 등록일(일) | 최소 0 · 최대 30 |" in output
    # 사본 여부 — C 는 본 12일이 모두 마지막 날과 같고, A 는 앞 날의 값이 바뀌어 마지막 날에 없다.
    assert "**여러 날 적재 — 날마다 사본인가**" in output
    assert (
        "| 1 | 표본 | 32 | 40 · 40 · 40 | 12 | 480 → 40 | 40 | 4 / 4 | 11 / 0 (0) | 0 |" in output
    )
    assert (
        "| 2 | 표본 | 2 | 20 · 60 · 100 | 2 | 120 → 120 | 20 | 4 / 4 | 0 / 1 (0) | 100 |" in output
    )
    assert "여러 날 코드 더함" not in output


def test_multi_day_codes_outside_the_sample_are_added_for_the_copy_check(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """표본 하나(A)만 골라도 전 코드 조회가 찾은 여러 날 코드(C)를 더해 사본을 본다."""
    monkeypatch.setitem(sys.modules, "bigdataquery", _fake_bigdataquery())

    code, output = _run(capsys, "--only", "bdq", "--bdq-sample", "1")

    assert code == 0
    _assert_no_leak(output)
    assert "| 표본 | 1 코드 (" in output
    assert (
        "| 1 | 표본 | 2 | 20 · 60 · 100 | 2 | 120 → 120 | 20 | 4 / 4 | 0 / 1 (0) | 100 |" in output
    )
    # 더한 코드의 창은 등록일 ±30 이 아니라 전 코드 조회의 첫·끝 적재일이다 — 32일을 다 센다.
    assert (
        "| 2 | 여러 날 코드 더함 | 32 | 40 · 40 · 40 | 12 | 480 → 40 | 40 | 4 / 4 | "
        "11 / 0 (0) | 0 |"
    ) in output


def test_bigdataquery_failures_are_named_by_kind_only(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """새 적재일 SQL 이 사내 엔진에서 돌지 않아도 나머지는 계속하고, 엔진 문구는 내보내지 않는다."""
    monkeypatch.setitem(
        sys.modules,
        "bigdataquery",
        _fake_bigdataquery(fail_load_days=True, fail_code_days=True),
    )

    code, output = _run(capsys, "--only", "bdq", "--bdq-no-max-window")

    assert code == 0
    _assert_no_leak(output)
    assert "상한 366일" not in output
    assert (
        "| 조회(목록 창 31일 전체를 GROUP BY 한 번, 사외에서 돌려 보지 못한 SQL) | "
        "조회 실패(RuntimeError) |"
    ) in output
    assert "0 / 1 성공 · 조회 실패(RuntimeError)" in output
    assert "| 상세 조회(앱과 같은 SQL) | 1 / 1 성공 |" in output
    assert "- 적재일 조회가 실패해 건너뛴다." in output


class _DayProbe:
    """`check_copies` 만 부르는 가짜 — 날마다 정해 둔 프레임을 돌려준다."""

    def __init__(self, frames: dict[date, pd.DataFrame]) -> None:
        self.frames = frames
        self.asked: list[date] = []

    def catalog(self, window: QueryWindow) -> pd.DataFrame:
        raise AssertionError("부르지 않는다")

    def detail_rows(self, code: str, window: QueryWindow) -> int:
        raise AssertionError("부르지 않는다")

    def code_load_days(self, window: QueryWindow) -> pd.DataFrame:
        raise AssertionError("부르지 않는다")

    def load_days(self, code: str, window: QueryWindow) -> pd.DataFrame:
        days = [day for day in self.frames if window.start_date <= day <= window.end_date]
        return pd.DataFrame(
            {
                "load_day": [f"{day:%Y-%m-%d}" for day in days],
                "row_count": [len(self.frames[day]) for day in days],
            }
        )

    def detail_frame(self, code: str, window: QueryWindow) -> pd.DataFrame:
        assert window.start_date == window.end_date  # 하루씩 받는다
        self.asked.append(window.start_date)
        return self.frames[window.start_date]


def _plan_frame(rows: int, *, pack_codes: int = 1, as_float: bool = False) -> pd.DataFrame:
    frame = pd.DataFrame(_detail_rows(VALID_A, rows, 0))
    # 네 행(제품정보 넷)마다 Pack Code 가 바뀐다 — 다른 Pack Code 는 다른 계획 줄이다.
    frame["Pack Code"] = [f"PK{index // 4 % pack_codes}" for index in range(rows)]
    if as_float:
        # 빈 값이 낀 날에는 정수 칸이 실수로 읽힌다 — 같은 행이어야 한다.
        frame["생산계획년월"] = frame["생산계획년월"].astype("float64")
    return frame


def test_copy_check_tells_a_partial_load_from_a_copy_and_ignores_dtype_drift() -> None:
    day1, day2, day3 = date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)
    probe = _DayProbe(
        {
            day1: _plan_frame(10),  # 마지막 날의 일부 — 부분 적재
            day2: _plan_frame(30, as_float=True),  # 마지막 날과 같다(dtype 만 다름)
            day3: _plan_frame(30),
        }
    )

    result = checks.check_copies(
        probe, VALID_A, QueryWindow(start_date=day1, end_date=day3), extra=False
    )

    assert result.failure is None
    assert probe.asked == [day3, day1, day2]  # 마지막 날을 먼저 받는다
    assert (result.load_days, result.examined, result.rows, result.distinct_rows) == (3, 3, 70, 30)
    assert (result.same_days, result.differing_days, result.subset_days) == (1, 1, 1)
    assert result.missing_from_last == 0
    assert (result.plan_keys, result.last_plan_keys) == (4, 4)


def test_copy_check_counts_plan_lines_that_only_older_loads_have() -> None:
    """나눠 적재 — 앞 날에만 있는 계획 줄은 마지막 날만 받으면 빠진다. 키 수가 그것을 보인다."""
    day1, day2 = date(2026, 9, 1), date(2026, 9, 2)
    probe = _DayProbe({day1: _plan_frame(8, pack_codes=2), day2: _plan_frame(4)})

    result = checks.check_copies(
        probe, VALID_A, QueryWindow(start_date=day1, end_date=day2), extra=True
    )

    assert (result.plan_keys, result.last_plan_keys) == (8, 4)
    assert result.missing_from_last == 4
    assert (result.same_days, result.differing_days, result.subset_days) == (0, 1, 0)


def test_bigdataquery_without_an_account_says_what_to_set(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "bigdataquery", _fake_bigdataquery(need_user=True))
    monkeypatch.delenv(BDQ_USER_NAME_ENV, raising=False)

    code, output = _run(capsys, "--only", "bdq")

    assert code == 0
    assert "요청자 계정 필요 — `CAPA_BDQ_USER_NAME` 를 넣고" in output
    assert "목록 조회가 모두 실패해 나머지는 건너뛴다" in output


def test_code_rule_counts_do_not_rely_on_pandas_string_reductions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`describe_codes` 는 위반 수를 파이썬으로 센다. pandas 2.2 는 문자열 Series 의 `.map` 결과를
    문자열로 돌려줘 `.sum()` 이 `Cannot perform reduction 'sum' with string dtype` 으로 죽었다(사내
    리뷰 202610070927·202610071831 의 8-5). 그 판의 동작을 흉내 내도 같은 줄이 나와야 한다."""
    codes = pd.Series(["GOOD_CODE1", "가나다", "bad code", None, "  "], dtype="string")
    expected = checks.describe_codes(codes)

    def _string_map(self: pd.Series, *args: object, **kwargs: object) -> pd.Series:
        raise TypeError("Cannot perform reduction 'sum' with string dtype")

    monkeypatch.setattr(pd.Series, "map", _string_map)
    assert checks.describe_codes(codes) == expected
    assert "코드 5개 중 4개" in expected
    assert "빈 값 2" in expected and "비ASCII 1" in expected
