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
import shutil
import sys
import types
from collections import Counter
from collections.abc import Sequence
from dataclasses import replace
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
from capa_simulation.persistence.equipment_repository import (
    EQUIPMENT_MASTER_DB_COLUMNS,
    DuckDBEquipmentRepository,
    EquipmentSaveRequest,
)
from capa_simulation.persistence.repository import REVISION_TABLES, DuckDBScenarioRepository
from capa_simulation.services.core_data_derivation import build_q_core_data
from capa_simulation.services.equipment_contract import (
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
from test_equipment_migration_0027_scenarios import _database_before  # noqa: E402

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
ST_DEFINITION_LINE = (
    "- ST 정의 대조(참고) — 리비전 1 `RQ_UPEH` 의 UPEH × ST ÷ 60(ST 는 분 단위라 기대 1)"
)
HOME_PLAN_MONTHS_LINE = (
    "- 계획 달(`RQ_PKG_PLAN` 에 생산수량이 0 보다 큰 행이 있는 달 · 리비전 1 전체 기간)"
)


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


# 옛 판이 쓴 계약 v3 리비전의 날짜 칸 — 넣을 때 날짜로 바꾼다.
_LEGACY_DATE_COLUMNS = tuple(
    column for column in EQUIPMENT_MASTER_DB_COLUMNS if "일정" in column or "실적" in column
)


def _legacy_equipment_database(
    path: Path, revisions: Sequence[tuple[int, str | None, list[dict[str, object]]]]
) -> None:
    """옛 판(설비 마이그레이션 25 까지)이 저장한 계약 v3 리비전을 넣은 뒤 지금 판으로 연다(0027
    이관).

    옛 Qual 자리표 2262-04-11 은 옛 판의 마스터 표에만 있을 수 있다 — 0027 뒤의 저장은 계약 v4 라
    마스터 표에 일정 칸을 쓰지 않는다. 그래서 그런 리비전은 0027 전에 옛 꼴로 넣는다. `revisions` 는
    (번호, 저장 시각 — None 이면 지금, 마스터 행)이다.
    """
    _database_before(path, 25)
    with duckdb.connect(str(path)) as connection:
        for number, created_at, rows in revisions:
            revision_id = f"legacy-r{number}"
            connection.execute(
                """
                INSERT INTO equipment_ops.revision (
                    revision_id, revision_no, note, baseline_hash, schedule_hash,
                    equipment_hash, downtime_hash, equipment_contract_version, created_at
                ) VALUES (?, ?, '옛 판', 'b', 's', 'e', 'd', 3,
                          COALESCE(CAST(? AS TIMESTAMP), current_timestamp))
                """,
                [revision_id, number, created_at],
            )
            frame = pd.DataFrame(rows, columns=list(EQUIPMENT_COLUMNS))
            frame = frame.loc[:, list(EQUIPMENT_MASTER_DB_COLUMNS)]
            for column in _LEGACY_DATE_COLUMNS:
                frame[column] = pd.to_datetime(frame[column])
            frame = frame.rename(columns=dict(EQUIPMENT_MASTER_DB_COLUMNS))
            frame.insert(0, "source_row_no", range(1, len(frame) + 1))
            frame.insert(0, "revision_id", revision_id)
            columns = ", ".join(frame.columns)
            connection.register("legacy_rows", frame)
            connection.execute(
                f"INSERT INTO equipment_ops.equipment_master_snapshot ({columns}) "
                f"SELECT {columns} FROM legacy_rows"
            )
            connection.unregister("legacy_rows")
    DuckDBEquipmentRepository(path).initialize()


@pytest.fixture(scope="module")
def equipment_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Main 설비 묶음 하나(모듈 넷, 환산비 0.2 로 잘림), 옛 자리표 Qual 한 대, 반입 미정 한 대.

    옛 판이 저장한 계약 v3 리비전 하나를 0027 로 옮긴 DB 다 — 공통 r1 · 「운영 일정」 r1 · 공식 v1.
    """
    path = tmp_path_factory.mktemp("equipment") / "equipment_availability.duckdb"
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
    _legacy_equipment_database(path, [(1, None, rows)])
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
    for heading in ("### 8-1.", "### 8-2.", "### 8-3.", "### 8-4.", "### 8-9."):
        assert heading in output
    assert "### 8-5." not in output  # BigDataQuery 는 따로 부를 때만
    # HOME 월 축 — 내장 시드는 달마다 양산이 있어 빠지는 달이 없다.
    assert f"{HOME_PLAN_MONTHS_LINE} 12 · 그 가운데 1~12월이 다 든 해 1" in output
    assert "| **계획 달 가운데 양산 Density 없는 달** | 0 | 0 |" in output
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
    # ST 정의 대조는 ≈60 무리와 무관하게 늘 찍힌다. 내장 시드는 Main 은 UPEH, MI 는 ST 만 적는다.
    assert f"{ST_DEFINITION_LINE} — UPEH·ST 가 둘 다 양수인 행 0" in output
    # Chip 부하량은 정식 대조 표의 한 줄이다. 답이 난 탐색 비율(GOOD_DIE 등)은 더 찍지 않는다.
    assert "| Chip `Plan_Chip(K개)` | 24 |" in output
    assert "GOOD_DIE` ÷" not in output
    assert "Plan_Chip(K개) · GOOD_DIE" not in output
    assert "계획 줄×WF 구분" in output  # PCB 절
    # 설비 — 잘린 환산비·옛 자리표·일정 미정.
    assert "| **모듈 행 환산비 0.2** — 다시 입력할 행 | 4 |" in output
    assert "| Main 설비 묶음 / 그 가운데 모듈 환산비 합이 1 이 아닌 묶음(±0.01) | 1 / 1 |" in output
    assert "| Qual일정 = 2262-04-11 (공식 일정 리비전의 원천, 이제 빈 Qual 로 읽음) | 1 |" in output
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
        "| 공식 일정 리비전의 정지일정·반출/이설일정 둘 다 있는 행 (개편 뒤 저장 가능 — 정보) | 0 |"
        in output
    )
    assert "| Qual상태(qual_confirmation_status) = 완료 | 8 |" in output
    assert "| Qual상태 빈 칸 | 1 |" in output
    # 설비 시나리오 이관 확인(0027) — 이관 직후: 시나리오 하나, 이관 리비전 = 이관 전 리비전.
    assert "| 공식 일정 리비전 | 공식 v1 → 이관 시나리오 r1 |" in output
    assert "| 공식 일정 리비전 비가동 일정 | 0 |" in output
    assert "| 설비 시나리오 | 1 |" in output
    assert "| 이관 시나리오(operations) 리비전 / 그 가운데 이관(legacy) | 1 / 1 |" in output
    assert "| 이관 전 설비 리비전(이관 경계 1행) — 이관 리비전 수와 같아야 함 | 1 |" in output
    assert "| **경계 뒤 계약 v3 공통(옛 배포로 저장한 흔적)** — 0 이어야 함 | 0 |" in output
    assert "| 공식 일정 리비전의 일정 없음 호기 / 고아 일정 행(이관 직후 0) | 0 / 0 |" in output


def test_the_both_dates_check_looks_at_the_last_revision_saved_before_0023(
    simulation_db: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """「0 이어야 함」은 개편 전 마지막 리비전만 잰다 — 개편 뒤에는 정지·반출/이설을 함께 저장할
    수 있어(2026-10-16 결정) 최신 리비전의 수는 정보 줄이다. 시각만 옮겨 r1 을 0023 전, r2 를
    뒤로 둔다."""
    path = tmp_path / "equipment_availability.duckdb"
    both = {"stop": "2026-03-01", "relocation": "2026-04-01"}
    _legacy_equipment_database(
        path,
        [
            (
                count,
                created_at,
                [
                    _equipment_row(f"{SENTINEL}EQ-{index}", None, 1.0, **both)
                    for index in range(count)
                ],
            )
            for count, created_at in ((1, "2026-01-01"), (2, "2026-03-01"))
        ],
    )
    with duckdb.connect(str(path)) as connection:
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
        "| 공식 일정 리비전의 정지일정·반출/이설일정 둘 다 있는 행 (개편 뒤 저장 가능 — 정보) | 2 |"
        in output
    )


def _summary_keys(
    capsys: pytest.CaptureFixture[str], simulation: Path, equipment: Path
) -> dict[str, str]:
    """`--only env,equipment` 요약의 키별 줄(확인 코드 포함)."""
    code, output = _run(
        capsys,
        "--only",
        "env,equipment",
        "--database",
        str(simulation),
        "--equipment-database",
        str(equipment),
    )
    assert code == 0
    _assert_no_leak(output)
    return {line.split(" ", 2)[1]: line for line in _summary(output)}


def test_a_common_only_v4_save_keeps_the_8_1_and_8_4_keys(
    simulation_db: Path,
    equipment_db: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """회귀(설계 5장) — 일정은 그대로 두고 공통만 계약 v4 로 저장한 직후에도 8-1·8-4 요약 키가 저장
    전과 같다. 공통 칸 수는 공통 최신(이제 v4 r2)에서, 일정 칸 수(Q 자리표·D·일정 미정·비가동)는
    공식 일정 리비전(아직 이관 리비전 「운영 일정」 r1 — 그 원천 옛 r1)에서 센다. 8-4 의 r 은 공식
    일정 리비전 번호라 공통 번호가 올라도 그대로다."""
    copied = tmp_path / "equipment_availability.duckdb"
    shutil.copyfile(equipment_db, copied)
    before = _summary_keys(capsys, simulation_db, copied)

    repository = DuckDBEquipmentRepository(copied)
    official = repository.load_official_snapshot()
    assert official is not None and official.schedule is not None
    equipment = official.equipment.copy()
    equipment.loc[0, "담당자"] = "담당 바뀜"
    result = repository.save_equipment(
        EquipmentSaveRequest(
            baseline=official.baseline,
            equipment=equipment,
            downtime=official.downtime,
            equipment_scenario_id="operations",
            base_common_revision_id=official.revision.revision_id,
            base_schedule_revision_id=official.schedule.schedule_revision_id,
        )
    )
    assert result.common is not None and result.common.revision_no == 2
    assert result.schedule is None and result.release_no is None
    after = _summary_keys(capsys, simulation_db, copied)

    assert after["8-1"] == before["8-1"]
    assert after["8-4"] == before["8-4"]
    assert after["8-4"].startswith("- 8-4 r1 · M 9 = ")
    assert after["8-4s"] == before["8-4s"]


def test_the_migration_check_line_is_carried_and_checked(
    simulation_db: Path, equipment_db: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """8-4s(설비 시나리오 이관 확인)도 확인 코드가 붙고 `--check-summary` 가 키로 알아본다 — 코드를
    떼면 「확인 코드가 없다」, 수 하나를 바꾸면 「맞지 않는다」."""
    line = _summary_keys(capsys, simulation_db, equipment_db)["8-4s"]
    assert checks.check_transcript([line]) == []
    body = line.rsplit(" #", 1)[0]
    assert "확인 코드(`#NN`)가 없다" in checks.check_transcript([body])[0]
    assert checks.check_transcript([line.replace("X0", "X8")]) != []


def test_an_error_message_carrying_names_is_reported_by_kind_only(
    simulation_db: Path,
    equipment_db: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """이 앱의 검증 오류 문구에는 설비명·공정명이 실린다. 스크립트는 예외 종류만 적는다."""

    def broken(*_args: object, **_kwargs: object) -> pd.DataFrame:
        raise ValueError(f"{SENTINEL}EQ-M0 의 일정이 틀렸습니다")

    monkeypatch.setattr(checks, "read_merged", broken)
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

    notes: list[str] = []
    lines = checks._left_out_lines(required, notes)
    text = "\n".join(lines)

    assert "경로에 닿지 않은 계획 부하 3" in lines[0]
    assert "키 어긋남 · CHIP · BUFFER 1" in text
    assert "REQB 에 없는 제품 · CHIP · 그 밖 1" in text
    assert "키 어긋남 · PKG · (PKG) 1" in text
    assert "규칙상 미사용 · PKG · (PKG) 1" in text
    assert SENTINEL not in text
    # 전송용 요약 — 세는 갈래만 짧은 이름으로 더한 줄 안 식(합 = 경로에 닿지 않음)과 규칙상 미사용.
    assert notes == [
        "- 8-2X 0 · 0 · 3 · 0",
        "- 8-2B 3 = K·CHIP·BUFFER 1 + K·PKG·(PKG) 1 + P·CHIP·? 1 · U 1",
    ]
    assert checks.check_transcript(checks.summary_lines(notes)) == []
    assert SENTINEL not in "\n".join(notes)


def test_many_unrouted_branches_keep_the_summary_line_short() -> None:
    """갈래가 많아도 요약 줄은 큰 갈래 셋과 「그 밖 n갈래 m」 뿐이고 줄 안 식의 합은 그대로 선다."""
    reasons = [UNROUTED_KEY_MISMATCH_REASON, UNROUTED_UNKNOWN_PRODUCT_REASON]
    divisions = ["BUFFER", "CORE", "TOP", "DUMMY", "MASTER"]
    rows = [
        (reason, division)
        for index, division in enumerate(divisions)
        for reason in reasons
        for _ in range(index + 1)
    ]
    required = pd.DataFrame()
    required.attrs["unrouted_required_loads"] = pd.DataFrame(
        {
            **{key: ["X"] * len(rows) for key in LOAD_KEYS},
            "소요기준": ["CHIP"] * len(rows),
            "WF 구분": [division for _, division in rows],
            "부하량": [1.0] * len(rows),
            "제외사유": [reason for reason, _ in rows],
        }
    )

    notes: list[str] = []
    checks._left_out_lines(required, notes)

    assert notes[1] == (
        "- 8-2B 30 = K·CHIP·MASTER 5 + P·CHIP·MASTER 5 + K·CHIP·DUMMY 4 + 그 밖 7갈래 16 · U 0"
    )
    assert checks.check_transcript(checks.summary_lines(notes)) == []


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


def _plant_home_months(path: Path) -> None:
    """HOME 월 축에서 빠지는 달을 셋 만든다. 내장 시드는 달마다 양산 한 행·ER 한 행이다.

    - 202603 — 양산 행을 ER 로 바꾼다(양산 없이 ER 만 있는 달).
    - 202605 — 양산 행의 제품을 Density 기준정보에 없는 것으로 바꾼다(양산은 있는데 Density 가
      붙지 않는 달). 바꾼 이름은 표지값이라 찍히면 누출이다.
    - 202607 — 양산 행의 제품타입을 EDP-TSV 로 바꾼다(EDP 를 뺀 HOME 에서만 빠지는 달).
    """
    with duckdb.connect(str(path)) as connection:
        for month, column, value in (
            (202603, "양산구분", "ER"),
            (202605, "제품정보", f"{SENTINEL}NEW"),
            (202607, "제품타입", "EDP-TSV"),
        ):
            connection.execute(
                f'UPDATE rev_data.rq_pkg_plan SET "{column}" = ? '
                'WHERE "생산계획년월" = ? AND "양산구분" = \'양산\'',
                [value, month],
            )


def test_the_home_block_counts_plan_months_missing_from_the_month_axis(
    simulation_db: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """HOME 월 축은 양산 Density 가 있는 달만 선다(2026-10-22 결정 A — 그대로 둔다). 실데이터에
    그런 달이 있는지 개수로만 잰다 — EDP 를 포함한 기본 화면과 EDP 를 뺀 화면 두 칸."""
    path = tmp_path / "capa_simulation.duckdb"
    path.write_bytes(simulation_db.read_bytes())
    _plant_home_months(path)
    before = _md5(path)

    code, output = _run(capsys, "--only", "home", "--database", str(path))

    assert code == 0
    _assert_no_leak(output)
    assert _md5(path) == before
    assert "### 8-9. HOME 월 축 — 양산 Density 없는 계획 달 (`home`)" in output
    assert f"{HOME_PLAN_MONTHS_LINE} 12 · 그 가운데 1~12월이 다 든 해 1" in output
    assert "| HOME 월 축에 서는 달 — 양산 Density 가 있는 달 | 10 | 9 |" in output
    assert "| **계획 달 가운데 양산 Density 없는 달** | 2 | 3 |" in output
    assert "| └ 양산 계획이 없는 달(ER 등만 있는 달) | 1 | 2 |" in output
    assert "| └ 양산 계획은 있는데 Density 가 붙지 않은 달 | 1 | 1 |" in output
    assert (
        "| └ 양산 Density 없는 달 가운데 Wafer 부하량이 있는 달(Wafer 계획·Wafer Capa 에서 빠짐) "
        "| 2 | 3 |"
    ) in output
    assert (
        "| 연간 Total 열이 빠지는 해(계획은 1~12월이 다 있는데 월 축은 아닌 해) | 1 | 1 |" in output
    )


def test_the_home_block_does_not_count_zero_quantity_rows_as_plan(
    simulation_db: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """수량 0 행은 계산이 걷어내므로 계획으로 세지 않는다(런북 8-9 「계획 달」). 세면 사내
    실데이터에서 없는 빠진 달을 지어낸다 — 편집 격자는 계획 없는 달에도 수량 0 행을 들고 있다.

    - 202609 — 양산 행만 수량 0. ER 이 남아 계획 달이고, 양산 계획이 없는 달로 센다(Density 미연결이
      아니다).
    - 202612 — 모든 행이 수량 0. 계획 달이 아니라 빠진 달로도 세지 않고, 2026 은 1~12월이 다 든 해가
      아니게 된다.
    """
    path = tmp_path / "capa_simulation.duckdb"
    path.write_bytes(simulation_db.read_bytes())
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            'UPDATE rev_data.rq_pkg_plan SET "생산수량" = 0 '
            'WHERE ("생산계획년월" = 202609 AND "양산구분" = \'양산\') OR "생산계획년월" = 202612'
        )

    code, output = _run(capsys, "--only", "home", "--database", str(path))

    assert code == 0
    _assert_no_leak(output)
    assert f"{HOME_PLAN_MONTHS_LINE} 11 · 그 가운데 1~12월이 다 든 해 0" in output
    assert "| HOME 월 축에 서는 달 — 양산 Density 가 있는 달 | 10 | 10 |" in output
    assert "| **계획 달 가운데 양산 Density 없는 달** | 1 | 1 |" in output
    assert "| └ 양산 계획이 없는 달(ER 등만 있는 달) | 1 | 1 |" in output
    assert "| └ 양산 계획은 있는데 Density 가 붙지 않은 달 | 0 | 0 |" in output
    assert (
        "| └ 양산 Density 없는 달 가운데 Wafer 부하량이 있는 달(Wafer 계획·Wafer Capa 에서 빠짐) "
        "| 1 | 1 |"
    ) in output
    assert (
        "| 연간 Total 열이 빠지는 해(계획은 1~12월이 다 있는데 월 축은 아닌 해) | 0 | 0 |" in output
    )


def test_a_home_column_that_stops_is_named_by_kind_only(
    simulation_db: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """제품타입이 빈 계획이면 EDP 를 뺀 HOME 은 멈춘다. 그 오류 문구에는 제품 이름이 실린다 — 칸에는
    종류만 적고, EDP 를 포함한 칸은 그대로 센다."""
    path = tmp_path / "capa_simulation.duckdb"
    path.write_bytes(simulation_db.read_bytes())
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            'UPDATE rev_data.rq_pkg_plan SET "제품타입" = NULL WHERE "생산계획년월" = 202601'
        )

    code, output = _run(capsys, "--only", "home", "--database", str(path))

    assert code == 0
    _assert_no_leak(output)
    assert "| **계획 달 가운데 양산 Density 없는 달** | 0 | 실패(ValueError) |" in output


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


def test_the_st_definition_line_reads_upeh_times_minutes_st_over_sixty(
    simulation_db: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """두 칸이 다 있는 행을 심는다 — MI 는 정의대로(UPEH = 60 ÷ ST → 1), Main 은 초로 적은 ST(→ 60).

    MI 와 Main 은 따로 찍힌다 — 계산에 쓰지 않는 Main 의 ST 가 MI 분포를 가리지 않는다. 분포·개수만
    찍고 판정하지 않는다. 값은 새지 않는다.
    """
    path = tmp_path / "capa_simulation.duckdb"
    path.write_bytes(simulation_db.read_bytes())
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            'UPDATE rev_data.rq_upeh SET "UPEH" = 60.0 / "ST" WHERE "Area_Name" = ? AND "ST" > 0',
            ["MI"],
        )
        connection.execute(
            'UPDATE rev_data.rq_upeh SET "ST" = 3600.0 / "UPEH" '
            'WHERE "Area_Name" = ? AND "UPEH" > 0',
            ["Main"],
        )
        mi, main = (
            int(
                connection.execute(
                    "SELECT count(*) FROM rev_data.rq_upeh AS u "
                    "JOIN app_meta.scenario_revision AS r USING (revision_id) "
                    'WHERE r.revision_no = 1 AND u."Area_Name" = ?',
                    [area],
                ).fetchone()[0]  # type: ignore[index]
            )
            for area in ("MI", "Main")
        )
    assert mi > 0 and main > mi

    code, output = _run(capsys, "--only", "legacy", "--database", str(path))

    assert code == 0
    _assert_no_leak(output)
    lines = [line for line in output.splitlines() if line.startswith(ST_DEFINITION_LINE)]
    assert lines == [
        f"{ST_DEFINITION_LINE} — MI {mi} · p5 · 중앙 · p95 1 · 1 · 1 · 1 ±5% 안 {mi} / "
        f"Main(계산에 쓰지 않음) {main} · p5 · 중앙 · p95 60 · 60 · 60 · 1 ±5% 안 0"
    ]


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
    # 전송용 요약 — Wafer 경로 줄은 갈리는 칸 · 맞대기 중앙 · 가장 잘 따라가는 칸과 그 ≈ 칸 / 칸 ≠1.
    assert re.search(
        rf"^- 8-2W {cells}/{cells} · [\d.]+% · Step수 (\d+)/\1 #\d\d$",
        output,
        flags=re.MULTILINE,
    )


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


def test_a_failing_ratio_grouping_stays_inside_the_requirement_section(
    simulation_db: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """≈60 무리를 세는 `ratio_groups` 가 멈춰도 그 실패는 소요대수 절 안에 머문다 — PCB 절과 8-2
    의 나머지는 그대로 찍히고, 요약 8-2R 줄에는 무리 칸만 「실패(종류)」 다."""

    def broken(*_args: object, **_kwargs: object) -> object:
        raise ValueError(f"{SENTINEL} 문구")

    monkeypatch.setattr(checks, "ratio_groups", broken)

    code, output = _run(capsys, "--only", "legacy", "--database", str(simulation_db))

    assert code == 0
    _assert_no_leak(output)
    assert "블록이 멈췄다" not in output
    assert "- ≈60 배 가르기 실패(ValueError)" in output
    assert "**PCB수(K매)**" in output
    bare = _uncoded(_summary(output))
    assert re.fullmatch(r"- 8-2R 100\.00% · [\d.]+% · 실패\(ValueError\)", bare[3]), bare


def test_a_failing_summary_line_keeps_the_block(
    simulation_db: Path,
    equipment_db: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """요약 줄을 짓다 멈춰도(칸이 비는 등) 블록 출력은 그대로 남고 요약에는 그 키와 종류만
    적는다."""
    shape = checks._column_shape_lines

    def without_facts(
        connection: duckdb.DuckDBPyConnection,
        revision_id: str,
        facts: dict[str, str] | None = None,
        *,
        official: object = None,
    ) -> list[str]:
        return shape(connection, revision_id)

    monkeypatch.setattr(checks, "_column_shape_lines", without_facts)

    code, output = _run(
        capsys,
        "--only",
        "equipment",
        "--database",
        str(simulation_db),
        "--equipment-database",
        str(equipment_db),
    )

    assert code == 0
    assert "블록이 멈췄다" not in output
    assert "| Area Code(classification_1) = Main | 4 |" in output
    # 이관 확인 줄(8-4s)은 따로 지어 8-4 줄이 멈춰도 남는다.
    assert _uncoded(_summary(output)) == [
        "- 8-4 요약 실패(KeyError)",
        "- 8-4s S1 · L1/1 · O v1→r1 · X0 · U0 · G0",
    ]


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
    # 전송용 요약 — 목록 · 전 코드 적재일(줄 안 식) · 표본 · 사본 코드마다 네 칸(과 기준 날에만)의
    # 합.
    summary = _uncoded(_summary(output))
    assert re.match(r"- 8-5L 31일 2행 [\d.]+초 · 366일 4행 [\d.]+초 · 위반 1/4$", summary[0])
    assert summary[1:] == [
        "- 8-5D 3 = 1 + 1 + 1",
        "- 8-5S 1/3 · 75.86%",
        "- 8-5C1 표본 32일 · 3 · 0 · 0 · 0 · 0 · 0",
        "- 8-5C2 표본 2일 · 1 · 80 · 0 · 20 · 0 · 0",
    ]
    assert checks.check_transcript(_summary(output)) == []
    assert not [line for line in output.splitlines() if _self_check_pattern().search(line)]
    bdq_keys = [line.split(" ", 2)[1] for line in summary]
    assert all(_matches_a_key(key, bdq_keys) for key in _carried_keys() if key.startswith("8-5"))


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
    # 멈춤 줄 뒤에 잰 데까지의 요약이 「(중단 — 여기까지)」 와 함께 붙는다.
    stop = written.index("블록이 멈췄다 — 중단(KeyboardInterrupt)")
    assert stop < written.index(checks.SUMMARY_HEADING)
    summary = _summary(written)
    assert summary[0] == "(중단 — 여기까지)"
    assert _uncoded(summary[1:])[-1] == "- 8-5 멈춤 중단"
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


# ------------------------------------------------------------------- 8-10 센서스 · 전송용 요약

# 센서스 줄 이름 → 요약 키. 표 줄은 `| 키 | 항목 | 근거 | 걸림 / 봄 | 수 |` 다.
CENSUS_KEYS = {
    "ratio": "C1",
    "negative": "C2",
    "run_day": "C3",
    "plan": "C4",
    "own": "C5",
    "lent": "C6",
    "division": "C7",
    "fold": "C8",
    "blank": "C9",
    "merge": "C10",
    "flag": "C11",
    "names": "C12",
}


def _census_row(output: str, key: str) -> str:
    """센서스 표에서 그 키 줄의 `걸림 / 봄 | 수 |` 부분."""
    rows = [line for line in output.splitlines() if line.startswith(f"| {CENSUS_KEYS[key]} | ")]
    assert len(rows) == 1, (key, rows)
    cells = rows[0].split(" | ")
    return " | ".join(cells[3:]).strip()


def _plant_census(simulation: Path, equipment: Path) -> None:
    """센서스 줄마다 하나씩(대여평가·계획기초정보여부는 둘) 꼴을 심는다. 달을 갈라 줄끼리 섞이지
    않게 하고, 머지 공백 달(202606)에는 아무것도 심지 않는다.

    결정 7 은 202601 의 Main 공정 하나 — 그 (월·공정·양산구분) 의 Main UPEH 를 0 으로(뒤에서
    빠질 경로) 두고 효율 칸을 비운다. 같은 공정의 202602 편중률도 비우지만 그 경로는 살아 있어
    세지 않는다.
    """
    with duckdb.connect(str(simulation)) as connection:
        month, process, kind = connection.execute(
            'SELECT "생산계획년월", "공정", "양산구분" FROM rev_data.rq_upeh '
            'WHERE "Area_Name" = \'Main\' AND "생산계획년월" = 202601 AND "공정" NOT IN '
            '(SELECT "공정" FROM rev_data.rq_upeh WHERE "Area_Name" = \'MI\') '
            'ORDER BY "공정" LIMIT 1'
        ).fetchone()  # type: ignore[misc]
        key = 'WHERE "생산계획년월" = ? AND "공정" = ? AND "양산구분" = ?'
        connection.execute(f'UPDATE rev_data.rq_upeh SET "UPEH" = 0 {key}', [month, process, kind])
        connection.execute(
            f'UPDATE rev_data.rq_run_rate SET "CAPA_RUN_RATE" = NULL {key}', [month, process, kind]
        )
        connection.execute(
            f'UPDATE rev_data.rq_vital SET "편중률" = NULL {key}', [202602, process, kind]
        )

        def one(table: str, assignment: str, month: int, *, rows: int = 1) -> None:
            connection.execute(
                f"UPDATE rev_data.{table} SET {assignment} WHERE source_row_no IN ("
                f'SELECT source_row_no FROM rev_data.{table} WHERE "생산계획년월" = ? '
                f"ORDER BY source_row_no LIMIT {rows})",
                [month],
            )

        one("rq_lot_ratio", '"Lot 측정률" = 1.5', 202603)
        one("rq_run_day", '"RUN_DAY" = 0', 202604)
        one("rq_pkg_plan", '"생산수량" = NULL', 202604)
        one("rq_eqp_avbl", '"가용대수" = -1', 202605)
        one("rq_eqp_own", '"설비보유" = NULL', 202607)
        one("rq_eqp_lent", '"설비대여평가" = NULL', 202608, rows=2)
        connection.execute(
            "INSERT INTO rev_data.rq_yld SELECT revision_id, source_row_no + 100000, "
            '"생산계획년월", "제품정보", "Stack", upper("WF 구분"), "EDS_수율", "BE_수율" '
            'FROM rev_data.rq_yld WHERE "WF 구분" = \'Core\' AND "생산계획년월" = 202609 '
            "ORDER BY source_row_no LIMIT 1"
        )
        quoted = [f'"{column}"' for column in REQB_COLUMNS]
        padded = ["' ' || \"공정\" || ' '" if column == '"공정"' else column for column in quoted]
        connection.execute(
            f"INSERT INTO rev_data.rq_reqb (revision_id, source_row_no, {', '.join(quoted)}) "
            f"SELECT revision_id, source_row_no + 100000, {', '.join(padded)} "
            'FROM rev_data.rq_reqb WHERE "생산계획년월" = 202610 ORDER BY source_row_no LIMIT 1'
        )
        for table in (
            "rq_eqp_avbl",
            "rq_eqp_lent",
            "rq_eqp_own",
            "rq_lot_ratio",
            "rq_pkg_plan",
            "rq_reqb",
            "rq_run_day",
            "rq_run_rate",
            "rq_upeh",
            "rq_vital",
            "rq_wf_ratio",
            "rq_yld",
        ):
            connection.execute(f'DELETE FROM rev_data.{table} WHERE "생산계획년월" = 202606')
        connection.execute("UPDATE app_meta.dataset SET source_type = 'SCENARIO_MONTH_MERGE'")
        flags = connection.execute(
            "SELECT source_row_no FROM raw_data.core_data ORDER BY source_row_no LIMIT 3"
        ).fetchall()
        for (row,), value in zip(flags, ["x", None, " y "], strict=True):
            connection.execute(
                'UPDATE raw_data.core_data SET "계획기초정보여부" = ? WHERE source_row_no = ?',
                [value, row],
            )
    with duckdb.connect(str(equipment)) as connection:
        columns = [
            str(row[0])
            for row in connection.execute(
                "SELECT column_name FROM duckdb_columns() WHERE schema_name = 'equipment_ops' "
                "AND table_name = 'equipment_master_snapshot' ORDER BY column_index"
            ).fetchall()
        ]
        picked = ", ".join(
            {
                "source_row_no": "source_row_no + 100000",
                "equipment_id": "lower(equipment_id) || ' '",
            }.get(column, column)
            for column in columns
        )
        connection.execute(
            f"INSERT INTO equipment_ops.equipment_master_snapshot SELECT {picked} "
            "FROM equipment_ops.equipment_master_snapshot ORDER BY source_row_no LIMIT 1"
        )


def test_the_census_counts_each_planted_shape_without_names(
    simulation_db: Path, equipment_db: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """「지금대로」 결정마다 심은 꼴을 개수로만 센다 — 리비전·이름·값은 찍지 않는다."""
    simulation = tmp_path / "capa_simulation.duckdb"
    equipment = tmp_path / "equipment_availability.duckdb"
    simulation.write_bytes(simulation_db.read_bytes())
    equipment.write_bytes(equipment_db.read_bytes())
    _plant_census(simulation, equipment)
    before = (_md5(simulation), _md5(equipment))

    code, output = _run(
        capsys,
        "--only",
        "census",
        "--database",
        str(simulation),
        "--equipment-database",
        str(equipment),
    )

    assert code == 0
    _assert_no_leak(output)
    assert (_md5(simulation), _md5(equipment)) == before
    assert "### 8-10. 센서스 — 「지금대로」 결정의 실데이터 유병률 (`census`)" in output
    assert "- 본 리비전 1 — 시나리오마다 활성 리비전과 공식버전 대상" in output
    expected = {
        "ratio": "1 / 1 리비전 | 칸 1 |",
        "negative": "1 / 1 리비전 | 칸 1 |",
        "run_day": "1 / 1 리비전 | 칸 1 |",
        "plan": "1 / 1 리비전 | 행 1 |",
        "own": "1 / 1 리비전 | 칸 1 |",
        "lent": "1 / 1 리비전 | 칸 2 |",
        "division": "1 / 1 리비전 | 키 1 |",
        "fold": "1 / 1 리비전 | 행 1 |",
        "blank": "1 / 1 리비전 | 칸 1 |",
        "merge": "1 / 1 머지 리비전 | 달 1 |",
        "flag": "1 / 1 원천 데이터셋 | 행 2 |",
        "names": "1 / 1 설비 리비전 | 묶음 1 |",
    }
    assert {key: _census_row(output, key) for key in expected} == expected
    # 근거 칸은 「근거 · 결정 n(잰 부분)」 이고, 옛 리비전이 대상인 결정 6 · 9 는 그것을 밝힌다.
    basis = {item.key: item.basis for item in checks.CENSUS_ITEMS}
    assert all(
        text.startswith(("근거 · 결정 ", "근거 · 사내 확인 요청", "참고 · 고침 "))
        for text in basis.values()
    )
    assert "--census-all-revisions" in basis["C7"] and "--census-all-revisions" in basis["C10"]
    assert "지금대로" not in "".join(basis.values())
    # 요약 — 0 이 아닌 줄만 키와 함께 한 줄씩, 머리는 그 줄 수와 합.
    summary = _uncoded(_summary(output))
    assert summary[0] == "- 8-10 활성 1 · 0 아님 12/12 · 합 14"
    assert summary[1:] == [
        f"- 8-10 C{index} {count}"
        for index, count in enumerate([1, 1, 1, 1, 1, 2, 1, 1, 1, 1, 2, 1], start=1)
    ]
    assert checks.check_transcript(_summary(output)) == []


def test_the_census_counts_every_revision_only_when_asked(
    simulation_db: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """기본은 활성·공식 리비전만 센다(6-3 a `--active-only` 와 같은 묶음). 옛 리비전의 꼴은
    `--census-all-revisions` 에서만 잡힌다."""
    path = tmp_path / "capa_simulation.duckdb"
    path.write_bytes(simulation_db.read_bytes())
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            "INSERT INTO app_meta.scenario_revision (revision_id, scenario_id, revision_no, "
            "revision_name, parent_revision_id, note, reference_hash, created_at) "
            "SELECT 'old-revision', scenario_id, 2, revision_name, NULL, note, reference_hash, "
            "created_at FROM app_meta.scenario_revision"
        )
        connection.execute(
            "INSERT INTO rev_data.rq_run_day SELECT 'old-revision', source_row_no, "
            '"생산계획년월", "공정", 0 FROM rev_data.rq_run_day ORDER BY source_row_no LIMIT 2'
        )
    argv = (
        "--only",
        "census",
        "--database",
        str(path),
        "--equipment-database",
        str(tmp_path / "none.duckdb"),
    )

    code, active = _run(capsys, *argv)
    assert code == 0
    assert "- 본 리비전 1 — " in active
    assert _census_row(active, "run_day") == "0 / 1 리비전 | 칸 0 |"

    code, every = _run(capsys, *argv, "--census-all-revisions")
    assert code == 0
    assert "- 본 리비전 2 — 저장된 모든 리비전(`--census-all-revisions`)" in every
    assert _census_row(every, "run_day") == "1 / 2 리비전 | 칸 2 |"
    # 설비 DB 가 없으면 그 줄만 이 스크립트의 문구로 멈춘다.
    assert _census_row(every, "names") == "- | 설비 DB 를 열지 못함 |"
    # 요약 머리는 범위(전부 · 본 리비전 수)를 밝히고, 멈춘 줄은 수 줄과 따로 센다.
    assert _uncoded(_summary(every)) == [
        "- 8-10 전부 2 · 0 아님 1/12 · 실패 1 · 합 2",
        "- 8-10 C3 2",
        "- 8-10 C12 설비 DB 를 열지 못함",
    ]
    assert checks.check_transcript(_summary(every)) == []


def test_the_census_value_ranges_follow_the_reference_editor() -> None:
    """상한 1·하한 0 은 기준 정보 편집 격자(`app_pages/reference_data.EDITOR_FORMATS`)의 범위다.
    화면 모듈이라 불러오지 않고 글자로 읽어 맞댄다 — 격자에 표가 늘면 센서스도 늘린다."""
    source = (PROJECT_ROOT / "app_pages" / "reference_data.py").read_text(encoding="utf-8")
    formats = next(
        node.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "EDITOR_FORMATS"
    )
    assert formats is not None
    editors: dict[str, tuple[str, float | None, float | None]] = ast.literal_eval(formats)

    assert {table for table, *_ in checks.CENSUS_VALUE_COLUMNS} == set(editors)
    assert {table for table, *_ in checks.CENSUS_RATIO_COLUMNS} == {
        table for table, (_, _, top) in editors.items() if top == 1.0
    }


def test_the_census_division_tables_are_every_revision_table_with_a_wf_division(
    simulation_db: Path,
) -> None:
    with duckdb.connect(str(simulation_db), read_only=True) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT table_name FROM duckdb_columns() WHERE schema_name = 'rev_data' "
                "AND column_name = 'WF 구분'"
            ).fetchall()
        }
    assert {REVISION_TABLES[name] for name in checks.CENSUS_DIVISION_TABLES} == tables


RUNBOOK = PROJECT_ROOT / "docs" / "internal_update_runbook.md"
DUAL_ENV = PROJECT_ROOT / "docs" / "dual_env_workflow.md"


def _self_check_pattern() -> re.Pattern[str]:
    """런북 5장 자가 점검(`Select-String … -Pattern '…'`)의 그물. PowerShell 은 대소문자를 가리지
    않는다. 점검은 이번 리뷰의 두 파일만 본다 — `review\\*.md` 는 지난 전문마다 남은 8-4 사용기준
    줄까지 잡아 「예외 말고는 없음」 이 늘 거짓이 된다."""
    runbook = RUNBOOK.read_text(encoding="utf-8")
    found = re.search(
        r"Select-String -Path review\\<ZIP 파일명>\.md, review\\<ZIP 파일명>\.full\.md "
        r"-Pattern '([^']+)'",
        runbook,
    )
    assert found is not None
    assert "Select-String -Path review\\*.md" not in runbook
    return re.compile(found.group(1), re.IGNORECASE)


def _carried_keys() -> list[str]:
    """런북 8-6 「늘 옮기는 줄」 이 적은 요약 키(`8-5C<i>` 꼴 포함) — 결정 대기의 근거라 압축본에서
    `=` 로 접지 않는 줄."""
    runbook = RUNBOOK.read_text(encoding="utf-8")
    section = runbook[runbook.index("### 8-6.") :]
    found = re.search(r"\*\*늘 옮기는 줄 — [^\n]*\n(?:  [^\n]*\n)*", section)
    assert found is not None
    return re.findall(r"`(8-[^`\s]+)`", found.group(0))


def _matches_a_key(carried: str, keys: Sequence[str]) -> bool:
    pattern = re.escape(carried).replace(re.escape("<i>"), r"\d+")
    return any(re.fullmatch(pattern, key) for key in keys)


def _summary(output: str) -> list[str]:
    """요약 머리 아래의 줄(빈 줄 뺌)."""
    assert output.count(checks.SUMMARY_HEADING) == 1
    return [
        line for line in output.split(checks.SUMMARY_HEADING, 1)[1].splitlines() if line.strip()
    ]


def _uncoded(lines: Sequence[str]) -> list[str]:
    """줄 끝 확인 코드(` #NN`)를 뗀 줄 — 코드가 줄의 수로 셈한 값인지도 함께 본다."""
    bare = []
    for line in lines:
        body, code = line.rsplit(" #", 1)
        assert code == checks.summary_code(body[2:]), line
        bare.append(body)
    return bare


def test_the_report_and_its_summary_stay_clear_of_the_review_self_check(
    simulation_db: Path, equipment_db: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """사내는 블록을 고치지 못한다(런북 8-6 · 8-7). 그래서 출력이 5장 자가 점검에 걸리는 줄은 런북이
    적은 예외 하나(8-4 사용기준 줄 — 계약 상수)뿐이어야 하고, 전송용 요약에는 하나도 없어야 한다."""
    pattern = _self_check_pattern()

    code, output = _run(
        capsys, "--database", str(simulation_db), "--equipment-database", str(equipment_db)
    )

    assert code == 0
    caught = [line for line in output.splitlines() if pattern.search(line)]
    assert caught and all(
        line.startswith("- 사용기준(`equipment_contract.counts_for_capacity`") for line in caught
    ), caught
    assert not [line for line in _summary(output) if pattern.search(line)]


def test_the_summary_is_short_ordered_by_block_and_its_check_lines_add_up(
    simulation_db: Path, equipment_db: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """전송용 요약 — 사람이 손으로 옮겨 적을 몫이라 블록마다 짧은 키와 수만 실은 한 줄이 블록
    차례로 서고(8-10 은 0 이 아닌 줄만 더한다), 줄마다 확인 코드가 붙으며 줄 안 식은 스스로 선다.
    블록 출력은 요약 앞에 그대로 있고, 요약 머리 아래에는 옮겨 적을 줄만 있다(안내문 없음)."""
    code, output = _run(
        capsys, "--database", str(simulation_db), "--equipment-database", str(equipment_db)
    )

    assert code == 0
    _assert_no_leak(output)
    assert output.index("### 8-10.") < output.index(checks.SUMMARY_HEADING)
    lines = _summary(output)
    keys = [line.split(" ", 2)[1] for line in lines]
    assert keys == [
        "8-1",
        "8-2L",
        "8-2W",
        "8-2T",
        "8-2R",
        "8-2X",
        "8-2B",
        "8-3",
        "8-4",
        "8-4s",
        "8-9",
        "8-10",
    ]
    # 런북 8-6 「늘 옮기는 줄」 의 키는 스크립트가 실제로 찍는 키다(8-5 는 BigDataQuery
    # 시험이 본다).
    carried = _carried_keys()
    assert carried and all(
        _matches_a_key(key, keys) for key in carried if not key.startswith("8-5")
    ), carried
    assert all(line.startswith("- ") and re.search(r" #\d\d$", line) for line in lines)
    # 손으로 옮겨 적는 줄이라 짧다 — 범례(런북 8-6)가 키의 뜻을 맡는다.
    assert max(len(line) for line in lines) <= 90, lines
    bare = _uncoded(lines)
    assert re.fullmatch(r"- 8-1 S (\d+)/\1 · E (\d+)/\2 · R 1 · O 1", bare[0]), bare[0]
    assert bare[4].startswith("- 8-2R 100.00% · ")
    assert bare[6] == "- 8-2B 0"
    assert bare[9] == "- 8-4s S1 · L1/1 · O v1→r1 · X0 · U0 · G0"
    assert bare[10] == "- 8-9 12 · 포함 0 = 0 + 0 · 뺌 0"
    assert bare[11] == "- 8-10 활성 1 · 모두 0 (12/12)"
    assert checks.check_transcript(lines) == []
    assert (
        sum(1 for line in lines if " = " in line) == 3
    )  # 8-3 · 8-4 · 8-9 (경로 갈래 0 이라 8-2B 는 식 없음)


def test_a_check_code_catches_a_one_digit_slip_and_a_swap() -> None:
    """확인 코드는 줄의 숫자 한 자리를 바꾸거나 한 수 안의 이웃한 두 자리를 바꾸면 늘 달라진다 —
    「(기대 0)」 칸의 0 을 8 로 잘못 쳐도, 마이그레이션 번호를 바꿔 써도 잡힌다. 수 하나를
    빼먹거나 쪼갠 것은 97 가운데 96 꼴로 잡힌다(빼먹기는 이 표본 줄에서 모두 — 쪼개기는 보장이
    아니라 고정하지 않는다). 글자·쉼표·목록 표지·칸 가름은 코드에 들지 않는다."""
    lines = [
        "8-1 S 35/35 · E 23/23 · R 12 · O 3",
        "8-2R 100.00% · 0.01% · 0",
        "8-4 r6 · M 1,020 = 계획 700 + 확정 300 + 완료 0 + 지연 0 + 빈 20 + ? 0 · T 0 · Q 0 · D 0",
        "8-5C1 표본 32일 · 3 · 0 · 0 · 0 · 0 · 0",
    ]
    for line in lines:
        code = checks.summary_code(line)
        for index, char in enumerate(line):
            if not char.isdigit():
                continue
            for other in "0123456789":
                if other != char:
                    slipped = line[:index] + other + line[index + 1 :]
                    assert checks.summary_code(slipped) != code, (line, slipped)
        for index in range(len(line) - 1):
            pair = line[index : index + 2]
            # 한 수 안의 이웃한 두 자리(소수점 포함) 자리바꿈.
            if pair[0] != pair[1] and all(char.isdigit() or char == "." for char in pair):
                swapped = line[:index] + pair[::-1] + line[index + 2 :]
                assert checks.summary_code(swapped) != code, (line, swapped)
        # 수 하나를 빼먹은(` 0 ·` 하나) 전사.
        for found in re.finditer(r"\d+", line):
            dropped = line[: found.start()] + line[found.end() :]
            assert checks.summary_code(dropped) != code, (line, dropped)
    # 손으로 옮길 때 바뀌는 것 — 쉼표 빠짐·칸 가름(` · ` → `;`)·글자 바뀜은 코드를 바꾸지 않는다.
    assert checks.summary_code("8-4 r6 · M 1020 = 계획 700") == checks.summary_code(
        "8-4 r6 · M 1,020 = 계획 700"
    )
    coded = checks.summary_lines(["- 8-2R 100.00% · 0.01% · 0"])[2]
    assert checks.check_transcript([coded[2:]]) == []
    assert checks.check_transcript([coded[2:].replace(" · ", "; ")]) == []
    assert checks.check_transcript([coded.replace("0.01%", "0.10%")]) != []


def test_a_dropped_or_shifted_census_line_is_caught() -> None:
    """8-10 은 0 이 아닌 줄만 키와 함께 옮긴다. 줄 하나를 빼거나 겹쳐 적으면 머리의
    `0 아님 k` · `합` 과 어긋나고, 수를 다른 키 줄로 옮겨 적으면 확인 코드가 어긋난다."""
    scope = checks.CensusScope(picked="", revisions=5, label="")
    rows = [
        checks.CensusRow(key=item.key, label=item.label, basis=item.basis, unit=item.unit)
        for item in checks.CENSUS_ITEMS
    ]
    rows[0] = replace(rows[0], count=3)
    rows[7] = replace(rows[7], count=4)
    summary = checks.summary_lines(checks._census_notes(scope, rows, all_revisions=False))
    lines = [line for line in summary if line.startswith("- ")]
    assert _uncoded(lines) == [
        "- 8-10 활성 5 · 0 아님 2/12 · 합 7",
        "- 8-10 C1 3",
        "- 8-10 C8 4",
    ]
    assert checks.check_transcript(lines) == []

    dropped = checks.check_transcript([lines[0], lines[2]])
    assert len(dropped) == 1 and "줄이 빠졌거나 겹쳤다" in dropped[0]
    doubled = checks.check_transcript([*lines, lines[2]])
    assert len(doubled) == 1 and "줄이 빠졌거나 겹쳤다" in doubled[0]
    shifted = lines[1].replace("C1 3", "C2 3")
    assert checks.check_transcript([lines[0], shifted, lines[2]]) != []

    # 요약이 둘 이상 든 파일(다시 돌린 블록을 함께 붙인 리뷰 전문 같은 것)도 8-10 은 머리마다
    # 따로 센다.
    assert checks.check_transcript([*lines, "판정 — 손으로 쓴 줄", *lines]) == []
    orphan = checks.check_transcript([lines[1]])
    assert orphan == ["줄 1 — 8-10 수 줄인데 위에 8-10 머리 줄이 없다"]

    zeros = [replace(row, count=0) for row in rows]
    all_zero = checks._census_notes(scope, zeros, all_revisions=True)
    assert all_zero == ["- 8-10 전부 5 · 모두 0 (12/12)"]
    assert checks.check_transcript(checks.summary_lines(all_zero)) == []


def test_check_summary_reads_a_transcript_without_opening_a_database(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--check-summary` 는 사외가 받은 리뷰 압축본에 돌린다 — DB 를 열지 않고 맞지 않는 줄 번호만
    찍는다."""

    def must_not_open(*_args: object, **_kwargs: object) -> duckdb.DuckDBPyConnection:
        raise AssertionError("압축본 확인은 DB 를 열지 않는다")

    monkeypatch.setattr(duckdb, "connect", must_not_open)
    good = checks.summary_lines(
        ["- 8-1 S 35/35 · E 23/23 · R 12 · O 3", "- 8-9 12 · 포함 1 = 1 + 0 · 뺌 0"]
    )
    transcript = tmp_path / "transcript.txt"
    transcript.write_text(
        "202610300900 (가); 적용 ok; 관문 ok; 권한 ok; 발견 0; 사외요청 0; 식별값 없음 확인\n"
        + "\n".join(line[2:] for line in good if line.startswith("- ")),
        encoding="utf-8",
    )
    assert checks.main(["--check-summary", str(transcript)]) == 0
    assert capsys.readouterr().out.splitlines() == ["확인 코드가 있는 줄 2 · 맞지 않는 것 0"]

    transcript.write_text(
        transcript.read_text(encoding="utf-8").replace("S 35/35", "S 35/36"), encoding="utf-8"
    )
    assert checks.main(["--check-summary", str(transcript)]) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "확인 코드가 있는 줄 2 · 맞지 않는 것 1"
    assert out[1].startswith("- 줄 2 — 확인 코드가 맞지 않는다")


def _sample_compressed_review() -> list[str]:
    """런북 5장 차례 · `docs/dual_env_workflow.md` 4장 양식대로 쓴 압축본 표본. 8장 줄은 스크립트가
    찍은 그대로(확인 코드째)이고, 늘 옮기는 줄은 판정 · B · A 바로 아래, 나머지는 끝이다."""
    eighth = [
        line[2:]
        for line in checks.summary_lines(
            [
                "- 8-1 S 35/35 · E 23/23 · R 12 · O 3",
                "- 8-2W 0/12 · 0.00% · -",
                "- 8-2B 3 = K·CHIP·BUFFER 1 + K·PKG·(PKG) 1 + P·CHIP·? 1 · U 1",
                "- 8-5C1 표본 32일 · 3 · 0 · 0 · 0 · 0 · 0",
                "- 8-10 활성 5 · 0 아님 2/12 · 합 7",
                "- 8-10 C1 3",
                "- 8-10 C8 4",
                "- 8-4 r6 · M 1,020 = 계획 700 + 확정 300 + 완료 0 + 지연 0 + 빈 20 + ? 0"
                " · T 0 · Q 0 · D 0",
            ]
        )
        if line.startswith("- ")
    ]
    return [
        "202610300900 (가); 적용 ok; 관문 ok; 권한 ng 복사함; 발견 1; 사외요청 1; 식별값 없음 확인",
        "권한 템플릿 복사함; 모드 기본",
        "적용먼저 확인 1030",
        "wf TOP 0",
        "B 6 = 기록 4 + 미기록 2; u3 a3; na칸 4; 빈칸 0",
        "B 1)ok@u 2)ok,a3,b0@ua 3)na 시간 없음 4)ng 칸2 다름@u 5)12초@a 6)na 인쇄 못 함@a",
        "A 15 = 기록 14 + 미기록 1 + 안함 0; ng a7 TimeoutError(PageUp)",
        *eighth[1:7],
        "6-3a 사본 1030 0910; 리비전 54 = 됨 52 + 멈춤 2 + 확보율멈춤 0 + 막힘 0 + 읽지못함 0;"
        " 겹친키 0; 최신공식Density ok",
        "탐색 1; 1) Buffer 표기 2종",
        "발견 1) 멈춘 리비전 둘; 증상 계산 멈춤; 재현 DEMO_ 두 행, 표기만 다름; 관측 꼴 2종, 5행;"
        " 제안 모름",
        "사외요청 1) 6-3 b 시간 상한",
        "7-8 ok",
        "7장요청 9 = 했음 8 + 안함 1; 안함 4) 시간",
        "데이터변화 리비전 +1; 호기 0; 사내커밋 0; 임시수정 0; 남은사본 0",
        "6-3 b cold 12.3초; c 17/17; 8501 ok",
        "8장 =202610200720 8-3 8-9",
        eighth[0],
        eighth[7],
    ]


def _recount_b(items: str) -> tuple[int, int, int, int]:
    """B 항목 줄에서 N · n · u · a 를 다시 센다(런북 5장 「B 세는 법」) — 사외가 하는 셈."""
    entries = re.findall(r"(\d+)\)(\S.*?)(?=\s\d+\)|$)", items.removeprefix("B "))
    values = [value for _, value in entries]
    marks = [value.rsplit("@", 1)[1] if "@" in value else "" for value in values]
    recorded = sum(not value.startswith("na") for value in values)
    return (
        len(values),
        recorded,
        sum("u" in mark for mark in marks),
        sum("a" in mark for mark in marks),
    )


def test_a_compressed_review_in_the_template_form_checks_clean() -> None:
    """양식대로 쓴 압축본은 `--check-summary` 에 맞지 않는 것이 없다 — 8장 줄의 확인 코드와 8-10 줄
    수, 손으로 쓴 줄(B · A · 6-3a · 7장요청)의 합계 식을 다시 센다. 손으로 쓴 식이 틀리거나 8장
    줄의 확인 코드가 빠지면 그 줄 번호가 나온다. B 셈 줄의 수는 항목 줄의 표지로 다시 셀 수 있다."""
    review = _sample_compressed_review()
    assert checks.check_transcript(review) == []

    count_line = review.index("B 6 = 기록 4 + 미기록 2; u3 a3; na칸 4; 빈칸 0")
    assert _recount_b(review[count_line + 1]) == (6, 4, 3, 3)

    slipped = [*review]
    slipped[count_line] = slipped[count_line].replace("미기록 2", "미기록 1")
    assert checks.check_transcript(slipped) == [
        f"줄 {count_line + 1} — 줄 안 검산 식이 서지 않는다"
    ]
    revisions = next(n for n, line in enumerate(review) if line.startswith("6-3a "))
    slipped = [*review]
    slipped[revisions] = slipped[revisions].replace("멈춤 2", "멈춤 1")
    assert checks.check_transcript(slipped) == [f"줄 {revisions + 1} — 줄 안 검산 식이 서지 않는다"]

    census = next(n for n, line in enumerate(review) if line.startswith("8-10 C1 "))
    uncoded = [*review]
    uncoded[census] = uncoded[census].rsplit(" #", 1)[0]
    assert checks.check_transcript(uncoded) == [
        f"줄 {census + 1} — 8장 요약 줄인데 확인 코드(`#NN`)가 없다"
    ]


def test_summary_lines_copied_with_keyboard_separators_still_check() -> None:
    """손으로 옮기며 칸 가름 ` · ` 을 `;` 나 `, ` 로, 갈래 이름 안의 `·` 을 `.` 으로 바꿔 써도 확인
    코드 · 줄 안 식 · 8-10 머리와 수 줄이 그대로 맞는다(런북 5장 · 8-6). 바꿔 쓴 줄에서도 숫자 한
    자리는 잡힌다."""
    review = _sample_compressed_review()
    for separator in ("; ", ";", ", "):
        typed = [
            line.replace(" · ", separator).replace("·", ".") if re.match(r"8-\d", line) else line
            for line in review
        ]
        assert typed != review
        assert checks.check_transcript(typed) == [], separator
        head = next(n for n, line in enumerate(typed) if line.startswith("8-10 활성"))
        slipped = [*typed]
        slipped[head] = slipped[head].replace("합 7", "합 8")
        assert checks.check_transcript(slipped), separator


def _compressed_template() -> list[str]:
    """`docs/dual_env_workflow.md` 4장 압축본 양식 코드블록의 줄."""
    text = DUAL_ENV.read_text(encoding="utf-8")
    section = text[text.index("### 양식") :]
    block = section[section.index("```text\n") + len("```text\n") :]
    return [line for line in block[: block.index("```")].splitlines() if line.strip()]


def _runbook_line_keys() -> list[list[str]]:
    """런북 5장 「압축본 줄 — 이 차례로」 의 번호마다 줄 앞 백틱 키."""
    text = RUNBOOK.read_text(encoding="utf-8")
    section = text[text.index("**압축본 줄 — 이 차례로**") : text.index("**B 세는 법**")]
    items = re.findall(r"^(\d+)\. ((?:`[^`]+`(?: · )?)+)", section, re.MULTILINE)
    assert [int(number) for number, _ in items] == list(range(1, len(items) + 1))
    return [re.findall(r"`([^`]+)`", keys) for _, keys in items]


def test_the_compressed_review_template_follows_the_runbook_order() -> None:
    """적는 꼴의 정본은 런북 5장이고 dual_env 4장은 양식만 둔다 — 양식의 줄은 런북 번호의 키로
    시작하고 그 차례를 지키며 번호를 모두 덮는다. 결정 근거 줄의 키는 런북 8-6 「늘 옮기는 줄」 과
    같다."""
    keys = _runbook_line_keys()
    positions = []
    for line in _compressed_template():
        found = [
            index
            for index, item in enumerate(keys)
            if any(line == key or line.startswith(f"{key} ") for key in item)
        ]
        assert len(found) == 1, line
        positions.append(found[0])
    assert positions == sorted(positions), positions
    assert set(positions) == set(range(len(keys)))
    assert next(item for item in keys if "8-2W" in item) == _carried_keys()


def test_a_block_that_stops_is_named_in_the_summary(
    simulation_db: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_args: object, **_kwargs: object) -> list[str]:
        raise RuntimeError(f"{SENTINEL} 문구")

    monkeypatch.setattr(checks, "check_reqb", broken)

    code, output = _run(capsys, "--only", "env,reqb", "--database", str(simulation_db))

    assert code == 0
    _assert_no_leak(output)
    assert "- 8-3 멈춤 실패(RuntimeError)" in _uncoded(_summary(output))


def test_an_interrupted_run_still_prints_the_summary_so_far(
    simulation_db: Path,
    equipment_db: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`Ctrl+C` 로 멈춰도 멈춤 줄 뒤에 잰 데까지의 요약이 「(중단 — 여기까지)」 와 함께
    남는다 — 사외로 가는 것은 이 요약뿐이다. 센서스는 그 줄까지 센 수를 남긴다."""
    calls = {"n": 0}
    measure = checks.CensusItem.measure

    def stop_after_three(
        self: checks.CensusItem, session: checks.Session, scope: checks.CensusScope
    ) -> checks.CensusRow:
        calls["n"] += 1
        if calls["n"] > 3:
            raise KeyboardInterrupt
        return measure(self, session, scope)

    monkeypatch.setattr(checks.CensusItem, "measure", stop_after_three)
    target = tmp_path / "out.md"
    argv = ["--database", str(simulation_db), "--equipment-database", str(equipment_db)]

    with pytest.raises(KeyboardInterrupt):
        checks.main(["--only", "env,census", *argv, "--output", str(target)])

    written = target.read_text(encoding="utf-8")
    stop = written.index("- `8-10` 블록이 멈췄다 — 중단(KeyboardInterrupt)")
    assert stop < written.index(checks.SUMMARY_HEADING)
    summary = _summary(written)
    assert summary[0] == "(중단 — 여기까지)"
    bare = _uncoded(summary[1:])
    assert bare[0].startswith("- 8-1 S ")
    assert bare[1:] == ["- 8-10 활성 1 · 0 아님 0/3 · 중단 잰 3/12 · 합 0", "- 8-10 멈춤 중단"]
    assert written.strip() in capsys.readouterr().out


def test_a_copy_before_equipment_0031_is_named_as_such_and_skips_the_official_read(
    tmp_path: Path,
) -> None:
    """검토 F19 — 0027 뒤 0031 전 사본은 「0027 전」 이 아니라 「설비 0031 전」 으로 적고 리비전
    투영(배치 차이 셈 칸)을 부르지 않는다."""
    path = tmp_path / "equipment_availability.duckdb"
    _database_before(path, 29)
    with duckdb.connect(str(path), read_only=True) as connection:
        found = checks._read_official_equipment(connection)
    assert isinstance(found, str) and found.startswith("설비 0031 전")
    assert "0027 전" not in found
