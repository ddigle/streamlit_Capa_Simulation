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

import ast
import hashlib
import importlib.machinery
import re
import runpy
import sys
import types
from collections import Counter
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
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
from capa_simulation.services.required_equipment import (
    LOAD_KEYS,
    REQB_COLUMNS,
    UNROUTED_KEY_MISMATCH_REASON,
    UNROUTED_UNKNOWN_PRODUCT_REASON,
    UNROUTED_UNUSED_REASON,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import check_deploy_screens  # noqa: E402
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


@pytest.fixture(autouse=True)
def _no_user_app(monkeypatch: pytest.MonkeyPatch) -> None:
    """사용자 앱 프로세스 훑기는 이 기계에 무엇이 떠 있는지에 달렸다 — 기본은 「없음」으로
    막고, 그 갈래를 보는 시험만 바꾼다. `--only env` 처럼 설비 DB 를 기본 경로로 두는 시험도
    훑기를 탄다."""
    monkeypatch.setattr(check_deploy_screens, "running_app_count", lambda *_a, **_k: 0)


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
    area: str | None = "main",
    line: str = "L1",
    stop: str | None = None,
    relocation: str | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {column: None for column in EQUIPMENT_COLUMNS}
    row.update(
        {
            "설비명": unit,
            "Area Code": area,
            "공정소분류": f"{SENTINEL}PROC",
            "공정대분류": "B/N",
            "공정구분": line,
            "투자구분": "양산",
            # 일정 미정 알림은 일정 기준 가용이 세는 호기(사용기준 HBM·EDP)만 센다(2026-10-08 결정).
            "사용기준": usage,
            "동": "C1",
            "층": "1F",
            "반입일정": arrival,
            "Qual일정": qual,
            "Qual상태": status,
            "정지일정": stop,
            "반출/이설일정": relocation,
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
    # 38열 개편 분포(Area Code·공정구분·정지/반출이설) — 목록 밖 값은 표지값이라 찍히면 누출이다.
    rows.append(
        _equipment_row(
            f"{SENTINEL}EQ-Q",
            None,
            1.0,
            arrival="2026-02-01",
            qual="2262-04-11",
            area="MI",
        )
    )
    rows.append(
        _equipment_row(
            f"{SENTINEL}EQ-A", None, 1.0, arrival=None, qual=None, status=None, area="부대"
        )
    )
    # 사용기준이 EDP 인 호기는 HBM 과 함께 센다(2026-10-08 사용자 결정) — 줄에 따로 센다.
    rows.append(
        _equipment_row(
            f"{SENTINEL}EQ-E",
            None,
            1.0,
            usage="EDP",
            area=f"{SENTINEL}AREA",
            line=" pkg ",
            relocation="2099-01-01",
        )
    )
    # 사용기준이 HBM·EDP 가 아닌 호기 — 값은 표지값이라 찍히면 누출이다.
    rows.append(
        _equipment_row(
            f"{SENTINEL}EQ-U", None, 1.0, usage=f"{SENTINEL}USAGE", area=None, line=f"{SENTINEL}LT"
        )
    )
    # 일정 미정 셈에 들지 않는(사용기준 빈 칸) 호기에 정지일정을 둔다 — 그 셈을 흔들지 않는다.
    rows.append(
        _equipment_row(f"{SENTINEL}EQ-B", None, 1.0, usage=None, area=None, stop="2026-03-01")
    )
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
    # 알림 모음·발행 검사가 알리는 「소요대수에 들지 않은 수요」를 같은 셈으로 센다.
    assert "- 소요대수에 들지 않은 수요(리비전 1 전체 기간) — " in output
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
    # 38열 개편 분포 — 계약 이름만 적고 목록 밖 값은 종류 수로 접는다(대소문자·공백은 무시).
    assert "| Area Code(classification_1) = Main | 4 |" in output
    assert "| Area Code(classification_1) = MI | 1 |" in output
    assert "| Area Code(classification_1) = 부대 | 1 |" in output
    assert "| Area Code(classification_1) 빈 칸 | 2 |" in output
    assert "| Area Code(classification_1) 그 밖 — 행 / 종류 | 1 / 1 |" in output
    assert "| 공정구분(line_type) = PKG | 1 |" in output
    assert "| 공정구분(line_type) 그 밖 — 행 / 종류 | 8 / 2 |" in output
    assert "| 설비가동현황(classification_3, 계약에서 빠짐) 값 있는 행 | 0 |" in output
    assert "| 정지일정(removal_date) 값 있는 행 / 오늘 전 | 1 / 1 |" in output
    assert "| 반출/이설일정(relocation_date) 값 있는 행 / 오늘 전 | 1 / 0 |" in output
    # 픽스처는 마이그레이션 23 까지 올린 뒤 저장했다 — 개편 전 리비전이 없다.
    assert "| 개편 전 마지막 리비전(설비 마이그레이션 23 적용 전 저장) 번호 | 없음 |" in output
    assert (
        "| **개편 전 마지막 리비전의 정지일정·반출/이설일정 둘 다 있는 행** — 0 이어야 함 | - |"
        in output
    )
    assert (
        "| 최신 리비전의 정지일정·반출/이설일정 둘 다 있는 행 (개편 뒤 저장 가능 — 정보) | 0 |"
        in output
    )
    assert "| Qual상태(qual_confirmation_status) = 완료 | 8 |" in output
    assert "| Qual상태 빈 칸 | 1 |" in output


def test_the_both_dates_check_looks_at_the_last_revision_saved_before_0023(
    simulation_db: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """「0 이어야 함」은 개편 전 마지막 리비전만 잰다 — 개편 뒤에는 정지·반출/이설을 함께 저장할
    수 있어(2026-10-16 결정) 최신 리비전의 수는 정보 줄이다. 시각만 옮겨 r1 을 0023 전, r2 를
    뒤로 둔다."""
    path = tmp_path / "equipment_availability.duckdb"
    repository = DuckDBEquipmentRepository(path)
    repository.initialize()
    both = {"stop": "2026-03-01", "relocation": "2026-04-01"}
    for count in (1, 2):
        rows = [
            _equipment_row(f"{SENTINEL}EQ-{index}", None, 1.0, **both) for index in range(count)
        ]
        repository.save_snapshot(
            pd.DataFrame(columns=list(BASELINE_COLUMNS)),
            pd.DataFrame(rows, columns=list(EQUIPMENT_COLUMNS)),
            pd.DataFrame(columns=list(DOWNTIME_COLUMNS)),
        )
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            "UPDATE equipment_ops.revision SET created_at = CASE revision_no "
            "WHEN 1 THEN TIMESTAMP '2026-01-01' ELSE TIMESTAMP '2026-03-01' END"
        )
        connection.execute(
            "UPDATE equipment_meta.schema_migration SET applied_at = TIMESTAMP '2026-02-01' "
            "WHERE version = 23"
        )

    code, output = _run(
        capsys,
        "--only",
        "equipment",
        "--database",
        str(simulation_db),
        "--equipment-database",
        str(path),
    )

    assert code == 0
    _assert_no_leak(output)
    assert "| 개편 전 마지막 리비전(설비 마이그레이션 23 적용 전 저장) 번호 | 1 |" in output
    assert (
        "| **개편 전 마지막 리비전의 정지일정·반출/이설일정 둘 다 있는 행** — 0 이어야 함 | 1 |"
        in output
    )
    assert (
        "| 최신 리비전의 정지일정·반출/이설일정 둘 다 있는 행 (개편 뒤 저장 가능 — 정보) | 2 |"
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


def test_unrouted_load_branches_name_only_the_contract_vocabulary() -> None:
    """경로 없는 부하의 갈래는 사유와 계약 어휘만 이름으로 찍는다. 그 밖의 WF 구분은 「그 밖」으로
    묶고, 규칙상 미사용(EDP-TSV 의 PKG 같은 것)은 갈래에는 찍되 건수에는 넣지 않는다."""
    required = pd.DataFrame()
    required.attrs["unrouted_required_loads"] = pd.DataFrame(
        {
            **{key: ["X"] * 4 for key in LOAD_KEYS},
            "소요기준": ["CHIP", "CHIP", "PKG", "PKG"],
            "WF 구분": ["BUFFER", SENTINEL, "", ""],
            "부하량": [1.0, 2.0, 3.0, 4.0],
            "제외사유": [
                UNROUTED_KEY_MISMATCH_REASON,
                UNROUTED_UNKNOWN_PRODUCT_REASON,
                UNROUTED_KEY_MISMATCH_REASON,
                UNROUTED_UNUSED_REASON,
            ],
        }
    )

    lines = checks._left_out_lines(required)
    text = "\n".join(lines)

    assert "경로에 닿지 않은 계획 부하 3" in lines[0]
    assert "키 어긋남 · CHIP · BUFFER 1" in text
    assert "REQB 에 없는 제품 · CHIP · 그 밖 1" in text
    assert "키 어긋남 · PKG · (PKG) 1" in text
    assert "규칙상 미사용 · PKG · (PKG) 1" in text
    assert SENTINEL not in text


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


def test_a_block_that_stops_does_not_take_the_others_with_it(
    simulation_db: Path,
    equipment_db: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """한 블록이 예상 밖으로 멈춰도 종류만 적고 다음 블록을 잰다. 멈춘 실행도 앞 블록은 파일에
    남는다."""

    def broken(*_args: object, **_kwargs: object) -> list[str]:
        raise RuntimeError(f"{SENTINEL} 문구")

    def interrupted(*_args: object, **_kwargs: object) -> list[str]:
        raise KeyboardInterrupt

    monkeypatch.setattr(checks, "check_reqb", broken)
    target = tmp_path / "real_data_check.md"
    argv = ["--database", str(simulation_db), "--equipment-database", str(equipment_db)]

    code, output = _run(capsys, "--only", "env,reqb,equipment", *argv, "--output", str(target))

    assert code == 0
    _assert_no_leak(output)
    assert "- `8-3` 블록이 멈췄다 — 실패(RuntimeError)" in output
    assert "### 8-1." in output and "### 8-4." in output
    assert target.read_text(encoding="utf-8").strip() == output.strip()

    monkeypatch.setattr(checks, "check_equipment", interrupted)
    with pytest.raises(KeyboardInterrupt):
        checks.main(["--only", "env,equipment", *argv, "--output", str(target)])
    written = target.read_text(encoding="utf-8")
    assert "### 8-1." in written
    assert "### 8-4." not in written


def test_a_failing_wafer_route_section_leaves_the_rest_of_the_legacy_block(
    simulation_db: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_args: object, **_kwargs: object) -> object:
        raise ValueError(f"{SENTINEL} cannot reindex on an axis with duplicate labels")

    monkeypatch.setattr(checks, "route_cells", broken)

    code, output = _run(capsys, "--only", "legacy", "--database", str(simulation_db))

    assert code == 0
    _assert_no_leak(output)
    assert "- Wafer `WF수(매)` 경로 값 — 실패(ValueError)" in output
    assert "reindex" not in output and "Traceback" not in output
    assert "**소요대수**" in output
    assert "**PCB수(K매)**" in output


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


def _record_opens(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """`duckdb.connect` 가 연 파일 이름. 여는 것은 그대로 연다."""
    opened: list[str] = []
    connect = duckdb.connect

    def recording(database: str, *args: object, **kwargs: object) -> duckdb.DuckDBPyConnection:
        opened.append(Path(database).name)
        return connect(database, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(duckdb, "connect", recording)
    return opened


def _point_defaults_at(monkeypatch: pytest.MonkeyPatch, simulation: Path, equipment: Path) -> None:
    """앱의 운영 DB 경로(인자 기본값)를 바꿔 끼운다 — 그 경로를 열 때만 앱 프로세스를 훑는다."""
    monkeypatch.setattr(checks, "DUCKDB_PATH", simulation)
    monkeypatch.setattr(checks, "EQUIPMENT_DUCKDB_PATH", equipment)


@pytest.mark.parametrize(
    "argv",
    [(), ("--only", "equipment"), ("--only", "env", "--database", "copy.duckdb")],
    ids=["both-defaults", "equipment-default", "simulation-copy-equipment-default"],
)
def test_a_resting_user_app_stops_the_run_before_any_database_opens(
    argv: tuple[str, ...],
    simulation_db: Path,
    equipment_db: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """앱은 rerun 동안만 DB 를 쥔다 — 쉬는 앱은 잠금 확인을 지나쳐, 그대로 돌면 그동안
    사용자 화면이 「데이터베이스를 열지 못했습니다」가 된다. 운영 DB 를 열 때는 프로세스를 먼저
    보고 멈춘다."""
    _point_defaults_at(monkeypatch, simulation_db, equipment_db)
    monkeypatch.setattr(check_deploy_screens, "running_app_count", lambda *_a, **_k: 1)
    opened = _record_opens(monkeypatch)

    code, output = _run(capsys, *argv)

    assert code == 1
    assert "사용자 앱이 떠 있습니다" in output
    assert "### 8-" not in output
    assert opened == []


@pytest.mark.parametrize("scan", [0, None], ids=["no-app", "scan-failed"])
def test_with_no_app_seen_the_run_goes_on_and_says_when_it_could_not_look(
    scan: int | None,
    simulation_db: Path,
    equipment_db: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """프로세스를 살피지 못하면 지금처럼 잠금 확인으로 넘어가되, 잠금만 봤다는 것을 한 줄 남긴다."""
    _point_defaults_at(monkeypatch, simulation_db, equipment_db)
    monkeypatch.setattr(check_deploy_screens, "running_app_count", lambda *_a, **_k: scan)

    code, output = _run(capsys, "--only", "env")

    assert code == 0
    assert "### 8-1." in output
    assert ("DB 잠금만 봤다" in output) is (scan is None)


@pytest.mark.parametrize(
    "argv",
    [
        ("--only", "env", "--database", "{sim}", "--equipment-database", "{eq}"),
        ("--only", "legacy", "--database", "{sim}"),
        ("--only", "bdq"),
    ],
    ids=["both-copies", "simulation-copy-only", "bigdataquery-only"],
)
def test_copies_and_the_bigdataquery_block_do_not_look_for_the_app(
    argv: tuple[str, ...],
    simulation_db: Path,
    equipment_db: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """사본만 열거나 DB 를 열지 않는 블록은 사용자 앱과 겹치지 않는다 — 앱이 떠 있어도 돈다."""
    _point_defaults_at(monkeypatch, tmp_path / "app.duckdb", tmp_path / "app_equipment.duckdb")
    monkeypatch.setitem(sys.modules, "bigdataquery", None)

    def must_not_look(*_args: object, **_kwargs: object) -> int:
        raise AssertionError("사본·BigDataQuery 만 볼 때는 앱 프로세스를 훑지 않는다")

    monkeypatch.setattr(check_deploy_screens, "running_app_count", must_not_look)
    filled = [part.format(sim=simulation_db, eq=equipment_db) for part in argv]

    code, output = _run(capsys, *filled)

    assert code == 0
    assert "사용자 앱이 떠 있습니다" not in output


def test_the_ref_data_copy_line_says_whether_0033_has_run(
    simulation_db: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`0033` 이 걸렸으면 남은 사본은 「리비전 1 과 달라 남긴 것」, 아직이면 「적용 전」이다.

    적용 전 DB 에서 「0033 이 남긴 사본」이라고 찍으면 지울 사본을 결함 아닌 것으로 읽게 된다."""
    code, applied = _run(capsys, "--only", "env", "--database", str(simulation_db))
    assert code == 0
    assert "리비전 1 과 달라 `0033` 이 남긴 사본" in applied

    before = tmp_path / "capa_simulation.duckdb"
    before.write_bytes(simulation_db.read_bytes())
    with duckdb.connect(str(before)) as connection:
        connection.execute("DELETE FROM app_meta.schema_migration WHERE version = 33")

    code, pending = _run(capsys, "--only", "env", "--database", str(before))
    assert code == 0
    assert "`0033` 적용 전 — 앱을 띄우면 리비전 1 과 같은 사본은 지워진다" in pending
    assert "이 남긴 사본" not in pending


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
Loads = dict[str, dict[int, tuple[int, int]]]
REGISTERED = {
    VALID_A: date(2026, 9, 1),
    VALID_B: date(2026, 9, 20),
    VALID_C: date(2026, 8, 20),
    INVALID: date(2026, 9, 25),
}
LOADS: Loads = {
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


def _loaded(
    code: str, sql: str, registered: dict[str, date], loads: Loads
) -> dict[date, tuple[int, int]]:
    start, end = _window_of(sql)
    days = {registered[code] + timedelta(days=offset): load for offset, load in loads[code].items()}
    return {day: load for day, load in days.items() if start <= day < end}


def _detail_rows(
    code: str, rows: int, version: int, *, first: int = 0, lines: int = 4
) -> list[dict[str, object]]:
    """상세 SQL 이 돌려줄 행 — 경로 `first` 부터 `rows` 개. 계획 줄 키는 `제품정보` 로 `lines` 개로
    갈리고 경로 키 13 은 행마다 다르다. 이름은 표지값이다."""
    return [
        {
            "시뮬레이션 ID": code,
            "생산계획년월": 202610,
            "CS": "MP",
            "제품정보": f"{SENTINEL}P{index % lines}",
            "Stack": "8H",
            "Capa Code": f"{SENTINEL}CAPA",
            "Customer": f"{SENTINEL}CUST",
            "Pack Code": f"{SENTINEL}PK",
            "WF 구분": "Core",
            "Area_Name": "Main",
            "공정": f"{SENTINEL}S{index}",
            "STEP_SEQ": f"{SENTINEL}T{index}",
            "MCP_SEQ": "1A",
            "소요기준": "WF",
            "UPEH": float(index + version),
            "WF수(매)": float(index * 10 + version),
        }
        for index in range(first, first + rows)
    ]


def _fake_bigdataquery(
    *,
    fail_load_days: bool = False,
    fail_code_days: bool = False,
    need_user: bool = False,
    registered: dict[str, date] | None = None,
    loads: Loads | None = None,
    calls: Counter[str] | None = None,
    interrupt_day_detail: bool = False,
) -> types.ModuleType:
    module = types.ModuleType("bigdataquery")
    module.__spec__ = importlib.machinery.ModuleSpec("bigdataquery", None)
    codes = REGISTERED if registered is None else registered
    source = LOADS if loads is None else loads
    counted: Counter[str] = Counter() if calls is None else calls

    def getData(  # noqa: N802 — 사내 패키지의 이름 그대로
        *, param: str, convert_type: bool, verbose: bool, user_name: str = ""
    ) -> pd.DataFrame:
        if need_user and not user_name:
            raise Exception("parameter user_name is necessary.")
        if "SELECT DISTINCT" in param:
            counted["catalog"] += 1
            start, end = _window_of(param)
            rows = [
                {
                    "simulation_name": f"{SENTINEL}NAME {index}",
                    "simulation_code": code,
                    "plan_name": f"{SENTINEL}PLAN",
                    "plan_code": f"{SENTINEL}PLANCODE",
                    "regist_data": f"{day:%Y-%m-%d} 09:00:00",
                }
                for index, (code, day) in enumerate(codes.items())
                if start <= day < end
            ]
            return pd.DataFrame(rows, columns=list(CATALOG_COLUMNS))
        if "GROUP BY catb_sim_info_id" in param:
            counted["group_by"] += 1
            if fail_code_days:
                raise RuntimeError(f"AnalysisException near {SENTINEL}")
            spans: list[dict[str, object]] = []
            for code in codes:
                loaded = _loaded(code, param, codes, source)
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
        loaded = _loaded(found.group(1), param, codes, source)
        if "load_day" in param:
            counted["load_days"] += 1
            if fail_load_days:
                raise RuntimeError(f"AnalysisException near {SENTINEL}")
            return pd.DataFrame(
                {
                    "load_day": [f"{day:%Y-%m-%d}" for day in loaded],
                    "row_count": [rows for rows, _ in loaded.values()],
                }
            )
        start, end = _window_of(param)
        if (end - start).days == 1:
            counted["day_detail"] += 1
            if interrupt_day_detail:
                raise KeyboardInterrupt
        else:
            counted["detail"] += 1
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
    # 사본 확인 — 표본의 여러 날 코드 둘(적재일이 많은 C 먼저). 판정 없이 날마다 사실만 찍는다.
    # C 는 고른 넷이 모두 기준 날과 같고, A 의 앞 날은 경로 80개를 더 갖고 겹치는 20개의 값이
    # 다르다.
    assert "**여러 날 적재 — 날마다 무엇이 같고 다른가**" in output
    assert (
        "- 코드 1 · 표본 — 적재일 32일 · 날별 행 최소 · 중앙 · 최대 40 · 40 · 40 · "
        "기준 날 = 끝 적재일"
    ) in output
    assert "| 첫 적재일 (1/32) | 40 | 40 | 4 | 40 | 0 · 0 | 0 · 0 | 0 | 0 | 0 |" in output
    assert "| 가운데 (16/32) | 40 |" in output and "| 끝 앞날 (31/32) | 40 |" in output
    assert "| 기준 날 (32/32) | 40 | 40 | 4 | 40 | - | - | - | - | 0 |" in output
    assert "- 코드 2 · 표본 — 적재일 2일 · 날별 행 최소 · 중앙 · 최대 20 · 60 · 100" in output
    assert "| 첫 적재일 (1/2) | 100 | 100 | 4 | 100 | 0 · 80 | 0 · 0 | 20 | 0 | 0 |" in output
    assert "여러 날 코드 더함" not in output
    assert "| 판정 |" not in output and "통째 사본" not in output


def test_multi_day_codes_outside_the_sample_fill_the_copy_check(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """표본 하나(A)만 골라도 전 코드 조회가 찾은 여러 날 코드(C)로 둘을 채운다."""
    monkeypatch.setitem(sys.modules, "bigdataquery", _fake_bigdataquery())

    code, output = _run(capsys, "--only", "bdq", "--bdq-sample", "1")

    assert code == 0
    _assert_no_leak(output)
    assert "| 표본 | 1 코드 (" in output
    assert "- 코드 1 · 표본 — 적재일 2일" in output
    # 더한 코드의 창은 등록일 ±30 이 아니라 전 코드 조회의 첫·끝 적재일이다 — 32일을 다 센다.
    assert "- 코드 2 · 여러 날 코드 더함 — 적재일 32일" in output


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
        "조회 실패(RuntimeError · SQL) |"
    ) in output
    assert "0 / 1 성공 · 조회 실패(RuntimeError · SQL)" in output
    assert "| 상세 조회(앱과 같은 SQL) | 1 / 1 성공 |" in output
    assert "- 적재일 조회가 실패해 건너뛴다." in output


def test_without_the_all_code_query_a_last_load_on_the_window_edge_is_flagged(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """전 코드 조회가 없으면 넓은 창(등록일 ±30)으로만 센다 — 끝 적재일이 창 끝날이면 그렇다고
    적는다."""
    monkeypatch.setitem(sys.modules, "bigdataquery", _fake_bigdataquery(fail_code_days=True))

    code, output = _run(capsys, "--only", "bdq", "--bdq-sample", "5")

    assert code == 0
    _assert_no_leak(output)
    assert "기준 날 = 끝 적재일 · 기준 날이 창 끝날에 닿음(창 밖에도 적재가 있을 수 있다)" in output


def _many_daily_codes(count: int) -> tuple[dict[str, date], Loads]:
    registered = {
        f"{SENTINEL}D{index:02d}": date(2026, 8, 1) + timedelta(days=index)
        for index in range(count)
    }
    loads: Loads = {code: {offset: (12, 0) for offset in range(-1, 31)} for code in registered}
    return registered, loads


@pytest.mark.parametrize(
    ("flags", "day_details", "group_by", "codes"),
    [
        ((), 8, 1, 2),
        (("--bdq-sample", "2"), 8, 1, 2),
        (("--bdq-copy-codes", "1", "--bdq-copy-days", "2"), 2, 1, 1),
        (("--bdq-copy-codes", "0"), 0, 1, 0),
        (("--bdq-copy-days", "0", "--bdq-no-code-days"), 0, 0, 0),
    ],
)
def test_the_copy_check_has_a_small_fixed_query_budget(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    flags: tuple[str, ...],
    day_details: int,
    group_by: int,
    codes: int,
) -> None:
    """열 코드가 매일 다시 적재돼도 하루치 상세 조회는 기본 8번(코드 둘 × 날 넷)이다."""
    registered, loads = _many_daily_codes(10)
    calls: Counter[str] = Counter()
    monkeypatch.setitem(
        sys.modules,
        "bigdataquery",
        _fake_bigdataquery(registered=registered, loads=loads, calls=calls),
    )

    code, output = _run(capsys, "--only", "bdq", *flags)

    assert code == 0
    _assert_no_leak(output)
    assert (calls["day_detail"], calls["group_by"]) == (day_details, group_by)
    assert len(re.findall(r"^- 코드 \d+ · ", output, flags=re.MULTILINE)) == codes


def test_a_stopped_run_keeps_the_parts_already_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """사본 확인 도중 멈춰도(시간 제한·Ctrl+C) 앞 조각은 화면과 `--output` 파일에 남는다."""
    monkeypatch.setitem(sys.modules, "bigdataquery", _fake_bigdataquery(interrupt_day_detail=True))
    target = tmp_path / "bdq.md"

    with pytest.raises(KeyboardInterrupt):
        checks.main(["--only", "bdq", "--today", TODAY.isoformat(), "--output", str(target)])

    written = target.read_text(encoding="utf-8")
    assert "| 상한 366일 |" in written
    assert "| 적재일 1일 · 2–5일 · 6일 이상 |" in written
    assert "| 표본 적재일 | 값 |" in written
    assert "**여러 날 적재 — 날마다 무엇이 같고 다른가**" in written
    assert written.rstrip().endswith("블록이 멈췄다 — 중단(KeyboardInterrupt)")
    assert SENTINEL not in written
    assert written.strip() in capsys.readouterr().out


def test_the_script_runs_as_a_program_and_empties_a_stale_output_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """사내는 `python scripts/inspect_real_data_checks.py` 로 부른다 — 파일 끝의 `__main__` 이
    있어야
    돈다. `--output` 은 시작할 때 비운다(지난 배포의 파일이 새것처럼 붙여지지 않게)."""
    script = PROJECT_ROOT / "scripts" / "inspect_real_data_checks.py"
    monkeypatch.setattr(sys, "argv", [str(script), "--help"])
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(script), run_name="__main__")
    assert stopped.value.code == 0
    assert "--bdq-copy-codes" in capsys.readouterr().out

    target = tmp_path / "bdq.md"
    target.write_text("STALE 지난 배포의 출력", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "bigdataquery", _fake_bigdataquery())
    monkeypatch.setattr(
        sys,
        "argv",
        [str(script), "--only", "bdq", "--bdq-sample", "0", "--today", TODAY.isoformat()]
        + ["--output", str(target)],
    )
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(script), run_name="__main__")
    assert stopped.value.code == 0
    written = target.read_text(encoding="utf-8")
    assert "STALE" not in written
    assert written.startswith("<!-- inspect_real_data_checks.py")
    assert "| 상한 366일 | 366일 | 성공 |" in written
    assert "사본 확인(전 코드 조회로 더하는 코드 포함)은 `--bdq-sample 0`" in written
    assert "**여러 날 적재" not in written


def test_an_early_stop_still_empties_the_output_file(
    simulation_db: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def locked(*_args: object, **_kwargs: object) -> duckdb.DuckDBPyConnection:
        raise duckdb.IOException("Could not set lock")

    monkeypatch.setattr(duckdb, "connect", locked)
    target = tmp_path / "real_data_check.md"
    target.write_text("STALE 지난 배포의 출력", encoding="utf-8")

    code, _ = _run(
        capsys, "--only", "env", "--database", str(simulation_db), "--output", str(target)
    )

    assert code == 1
    written = target.read_text(encoding="utf-8")
    assert "STALE" not in written
    assert "앱이 떠 있으면 먼저 끄세요" in written


class _StopAtSecondCatalog:
    """두 번째 목록 조회에서 멈춘다(시간 제한·Ctrl+C 를 흉내 낸다)."""

    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.calls = 0

    def catalog(self, window: QueryWindow) -> pd.DataFrame:
        self.calls += 1
        if self.calls == 2:
            raise self.error
        return pd.DataFrame(columns=list(CATALOG_COLUMNS))

    def detail_rows(self, code: str, window: QueryWindow) -> int:
        raise AssertionError("부르지 않는다")

    def detail_frame(self, code: str, window: QueryWindow) -> pd.DataFrame:
        raise AssertionError("부르지 않는다")

    def load_days(self, code: str, window: QueryWindow) -> pd.DataFrame:
        raise AssertionError("부르지 않는다")

    def code_load_days(self, window: QueryWindow) -> pd.DataFrame:
        raise AssertionError("부르지 않는다")


def test_a_stop_inside_the_catalog_keeps_the_heading_and_closes_the_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """머리말·준비 줄과 끝난 목록 행은 조회 전·직후에 찍힌다. 멈춤 줄은 열린 표에 붙지 않는다."""
    target = tmp_path / "bdq.md"
    argv = ["--only", "bdq", "--today", TODAY.isoformat(), "--output", str(target)]

    with pytest.raises(KeyboardInterrupt):
        checks.main(argv, probe=_StopAtSecondCatalog(KeyboardInterrupt()))

    written = target.read_text(encoding="utf-8")
    assert "### 8-5." in written
    assert "- 준비 — 패키지 있음" in written
    assert "| 기본(오늘−30일 ~ 오늘) | 31일 | 성공 |" in written
    assert "아니오 |\n\n- `8-5` 블록이 멈췄다 — 중단(KeyboardInterrupt)" in written

    def broken(*_args: object, **_kwargs: object) -> list[str]:
        raise ValueError(f"{SENTINEL} 문구")

    monkeypatch.setattr(checks, "describe_registered_at", broken)
    assert checks.main(argv, probe=_StopAtSecondCatalog(RuntimeError())) == 0
    written = target.read_text(encoding="utf-8")
    assert "| 상한 366일 | 366일 | 조회 실패(RuntimeError · 그 밖) | 0.0 |" in written
    assert (
        "조회 실패(RuntimeError · 그 밖) | 0.0 | - | - | - | - |\n\n- `8-5` 블록이 멈췄다 — "
        "실패(ValueError)"
    ) in written
    assert SENTINEL not in written


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
        days = [day for day in sorted(self.frames) if window.start_date <= day <= window.end_date]
        return pd.DataFrame(
            {
                "load_day": [f"{day:%Y-%m-%d}" for day in days],
                "row_count": [max(len(self.frames[day]), 1) for day in days],
            }
        )

    def detail_frame(self, code: str, window: QueryWindow) -> pd.DataFrame:
        assert window.start_date == window.end_date  # 하루씩 받는다
        self.asked.append(window.start_date)
        return self.frames[window.start_date].copy()


def _day(
    lines: Sequence[int] = (0, 1, 2, 3),
    routes: Sequence[int] = (0, 1, 2),
    *,
    bump: float = 0.0,
    bumped: Sequence[int] | None = None,
    legacy: float = 0.0,
    pack: str = "PK",
    copies: int = 1,
    **extra: object,
) -> pd.DataFrame:
    """계획 줄 `lines` × 경로 `routes` 하루치. `bump` 는 업무 칸(`UPEH`)을, `legacy` 는 계산에 들지
    않는 기존 결과 칸(`WF수(매)`)을 바꾼다. `bumped` 를 주면 그 계획 줄만 바꾼다. 이름은
    표지값이다."""
    rows = [
        {
            "시뮬레이션 ID": f"{SENTINEL}SIM",
            "기준정보년월": 202609,
            "계획기초정보여부": "N",
            "생산계획년월": 202610,
            "CS": "MP",
            "제품정보": f"{SENTINEL}P{line}",
            "Stack": "8H",
            "Capa Code": f"{SENTINEL}CAPA",
            "Customer": f"{SENTINEL}CUST",
            "Pack Code": f"{SENTINEL}{pack}",
            "WF 구분": "Core",
            "Area_Name": "Main",
            "공정": f"{SENTINEL}S{route}",
            "STEP_SEQ": f"T{route}",
            "MCP_SEQ": "1A",
            "소요기준": "WF",
            "생산수량": 100.0 + line,
            "UPEH": 10.0 + route + (bump if bumped is None or line in bumped else 0.0),
            "WF수(매)": float(line * 100 + route) + legacy,
            **extra,
        }
        for line in lines
        for route in routes
    ]
    return pd.DataFrame(rows * copies)


DAYS = [date(2026, 9, 1) + timedelta(days=offset) for offset in range(32)]


def _facts(
    frames: Sequence[pd.DataFrame], *, today: date | None = None, max_days: int = 4
) -> list[checks.DayFacts]:
    probe = _DayProbe(dict(zip(DAYS, frames, strict=False)))
    window = QueryWindow(start_date=DAYS[0], end_date=DAYS[len(frames) - 1])
    result = checks.check_copies(
        probe, VALID_A, window, extra=False, today=today, max_days=max_days
    )
    assert result.failure is None
    return result.days


def _compared(facts: checks.DayFacts) -> tuple[object, ...]:
    """(그날에만 계획 줄·잘게, 기준 날에만 계획 줄·잘게, 행이 다른 키, 그 밖 칸만 다른 행)."""
    return (
        facts.only_day_plan,
        facts.only_day_finest,
        facts.only_reference_plan,
        facts.only_reference_finest,
        facts.changed,
        facts.other_only,
    )


@pytest.mark.parametrize(
    ("frames", "first", "reference_conflicts"),
    [
        # 날마다 같은 내용을 통째로 다시 적재했다 — 모든 칸이 0 이다.
        ([_day(), _day(), _day(), _day()], (0, 0, 0, 0, 0, 0), 0),
        # 기준 날이 경로 S1·S2 를 잃었고 S0 의 값도 바뀌었다(재검증 VL-1) — 키 손실이 가려지지
        # 않는다.
        ([_day(), _day(routes=(0,), bump=5)], (0, 8, 0, 0, 4, 0), 0),
        # 기준 날이 계획 줄 2·3 을 잃었고 남은 줄의 값도 바뀌었다(VL-3).
        ([_day(), _day(lines=(0, 1), bump=5)], (2, 6, 0, 0, 6, 0), 0),
        # 겹치는 계획 줄의 값이 바뀐 나눠 적재(7a) — 나눠진 줄과 바뀐 값이 둘 다 보인다.
        (
            [_day(lines=(0, 1, 2)), _day(lines=(1, 2, 3), bump=7, bumped=(1, 2))],
            (1, 3, 1, 3, 6, 0),
            0,
        ),
        # 날마다 다른 경로를 실었다 — 그날에만·기준 날에만 있는 키가 같이 나온다.
        ([_day(routes=(0,)), _day(routes=(1,)), _day(routes=(2,))], (0, 4, 0, 4, 0, 0), 0),
        # 앞 날은 기준 날의 일부다(누적).
        ([_day(lines=(0, 1)), _day()], (0, 0, 2, 6, 0, 0), 0),
        # 뒤 적재에서 계획 줄이 빠졌다.
        ([_day(), _day(lines=(0, 1))], (2, 6, 0, 0, 0, 0), 0),
        # 기준 날에 같은 키를 다른 값으로 두 번 적재했다(15b) — 하루 안 충돌로 보인다.
        ([_day(), pd.concat([_day(), _day(bump=9)], ignore_index=True)], (0, 0, 0, 0, 12, 0), 12),
        # 계산에 들지 않는 칸만 흔들렸다(기준정보년월·기존 결과 WF수) — 값 바뀜이 아니다.
        ([_day(), _day(기준정보년월=202610)], (0, 0, 0, 0, 0, 12), 0),
        ([_day(), _day(legacy=5)], (0, 0, 0, 0, 0, 12), 0),
    ],
)
def test_copy_facts_count_each_direction_without_a_verdict(
    frames: list[pd.DataFrame], first: tuple[int, ...], reference_conflicts: int
) -> None:
    facts = _facts(frames)

    assert _compared(facts[0]) == first
    assert facts[-1].label.startswith("기준 날")
    assert not facts[-1].compared
    assert facts[-1].conflicts == reference_conflicts


def test_the_reference_row_carries_its_own_counts() -> None:
    reference = _facts([_day(), _day(lines=(0, 1))])[-1]

    assert (reference.rows, reference.distinct, reference.plan_keys, reference.finest_keys) == (
        6,
        6,
        2,
        6,
    )
    assert checks.day_fact_row(reference) == [
        "기준 날 (2/2)",
        "6",
        "6",
        "2",
        "6",
        "-",
        "-",
        "-",
        "-",
        "0",
    ]


def test_long_numeric_looking_codes_stay_apart() -> None:
    """글자 칸은 숫자로 읽지 않는다 — 끝자리만 다른 긴 코드가 한 계획 줄로 합쳐지지 않는다."""
    facts = _facts(
        [
            _day().assign(**{"Capa Code": "12345678901234567"}),
            _day().assign(**{"Capa Code": "12345678901234568"}),
        ]
    )

    assert _compared(facts[0])[:4] == (4, 12, 4, 12)


def test_numeric_business_columns_compare_as_numbers() -> None:
    """숫자 칸은 숫자 글자·Decimal·정수·빈 글자·소문자 칸 이름이 날마다 갈려 와도 같은 값이다."""
    base = _day()
    drifted = base.assign(
        생산수량=[str(int(value)) for value in base["생산수량"]],
        UPEH=pd.Series([Decimal(str(value)) for value in base["UPEH"]], dtype=object),
        ST="",
    ).rename(columns={"CS": "cs", "Stack": "stack", "Customer": "customer"})
    steady = base.assign(ST=None)

    facts = _facts([drifted, steady.astype({"UPEH": "float64"}), steady])

    assert [_compared(day) for day in facts[:-1]] == [(0, 0, 0, 0, 0, 0)] * 2


def test_a_missing_key_column_is_reported_not_replaced() -> None:
    """키 칸이 하나라도 없으면 그 키로 세지 않는다 — 있는 칸만으로 대신 세지 않는다."""
    facts = _facts([_day().drop(columns=["MCP_SEQ"]), _day()])

    assert facts[0].finest_keys is None
    assert _compared(facts[0]) == (0, None, 0, None, None, 0)
    row = checks.day_fact_row(facts[0])
    assert row[4] == "칸 없음" and row[5] == "0 · 칸 없음" and row[7] == "칸 없음"


def test_a_day_without_rows_is_shown_as_it_is() -> None:
    facts = _facts([_day().iloc[:0], pd.DataFrame(), _day()])

    assert (facts[0].rows, facts[0].plan_keys, _compared(facts[0])) == (0, 0, (0, 0, 4, 12, 0, 0))
    assert (facts[1].rows, facts[1].plan_keys) == (0, None)


@pytest.mark.parametrize(
    ("count", "today", "max_days", "picked", "reference", "labels"),
    [
        # 기본 넷 — 첫 적재일·가운데·끝 앞날·기준 날.
        (
            32,
            None,
            4,
            [0, 15, 30, 31],
            31,
            ["첫 적재일 (1/32)", "가운데 (16/32)", "끝 앞날 (31/32)", "기준 날 (32/32)"],
        ),
        # 둘이면 끝 앞날과 기준 날 — 가운데를 고르지 않는다.
        (32, None, 2, [30, 31], 31, ["끝 앞날 (31/32)", "기준 날 (32/32)"]),
        # 끝 날이 오늘이면 오늘을 먼저 빼고 기준 날은 오늘 전 마지막 적재일이다.
        (32, 31, 2, [29, 30], 30, ["끝 앞날 (30/32)", "기준 날 (31/32)"]),
        # 셋 이상이면 오늘도 견주되 적재 중일 수 있다고 적는다.
        (
            32,
            31,
            3,
            [29, 30, 31],
            30,
            ["끝 앞날 (30/32)", "기준 날 (31/32)", "오늘 — 적재 중일 수 있음 (32/32)"],
        ),
        (
            32,
            31,
            4,
            [0, 29, 30, 31],
            30,
            [
                "첫 적재일 (1/32)",
                "끝 앞날 (30/32)",
                "기준 날 (31/32)",
                "오늘 — 적재 중일 수 있음 (32/32)",
            ],
        ),
        # 적재일 둘에 끝 날이 오늘 — 기준 날은 그 앞 하루다.
        (2, 1, 4, [0, 1], 0, ["기준 날 (1/2)", "오늘 — 적재 중일 수 있음 (2/2)"]),
    ],
)
def test_day_picks_keep_the_reference_and_name_real_positions(
    count: int,
    today: int | None,
    max_days: int,
    picked: list[int],
    reference: int,
    labels: list[str],
) -> None:
    probe = _DayProbe({day: _day() for day in DAYS[:count]})
    window = QueryWindow(start_date=DAYS[0], end_date=DAYS[count - 1])

    result = checks.check_copies(
        probe,
        VALID_A,
        window,
        extra=False,
        today=None if today is None else DAYS[today],
        max_days=max_days,
    )

    assert sorted(probe.asked) == [DAYS[index] for index in picked]
    assert [facts.label for facts in result.days] == labels
    assert sum(1 for facts in result.days if not facts.compared) == 1
    assert (
        checks.pick_copy_days(
            DAYS[:count], today=None if today is None else DAYS[today], max_days=max_days
        ).reference
        == DAYS[reference]
    )


def test_copy_lines_render_one_head_and_a_day_table_per_code() -> None:
    check = checks.CopyCheck(
        extra=True, load_days=3, day_rows=(29_460, 29_461, 29_470), note="기준 날 = 끝 적재일"
    )
    check.days = _facts([_day(), _day()])

    lines = checks.copy_lines(2, check)

    assert lines[0] == (
        "- 코드 2 · 여러 날 코드 더함 — 적재일 3일 · 날별 행 최소 · 중앙 · 최대 "
        "29,460 · 29,461 · 29,470 · 기준 날 = 끝 적재일"
    )
    assert lines[2].startswith("| 자리(적재일 차례) | 행 |")
    assert lines[4] == "| 첫 적재일 (1/2) | 12 | 12 | 4 | 12 | 0 · 0 | 0 · 0 | 0 | 0 | 0 |"
    assert checks.copy_lines(1, checks.CopyCheck(extra=False, failure="조회 실패(X)"))[0] == (
        "- 코드 1 · 표본 — 조회 실패(X)"
    )


def test_rq_source_columns_are_the_columns_the_rq_tables_read() -> None:
    """사본 확인의 업무 칸은 `reference_transformer` 가 읽는 칸과 같아야 한다(파생 둘은
    원천으로)."""
    source = (
        PROJECT_ROOT / "src" / "capa_simulation" / "services" / "reference_transformer.py"
    ).read_text(encoding="utf-8")
    literals = {
        node.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    columns = {column.name for column in load_core_data_contract().columns}
    expected = literals & columns
    if "양산구분" in literals:
        expected.add("CS")
    if "가용대수" in literals:
        expected |= {"설비보유", "설비대여평가"}

    assert set(checks.RQ_SOURCE_COLUMNS) == expected


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
