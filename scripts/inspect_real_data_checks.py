# Purpose: 실데이터로만 답이 나오는 항목을 두 DB·BigDataQuery 에서 읽기만 해 집계로 찍는다.

"""사내 실데이터 확인 도구 — 런북 8장(`docs/internal_update_runbook.md`)이 부른다.

사외에는 합성 표본밖에 없어 **실데이터로만 답이 나오는 질문**이 쌓인다(`docs/TODO.md`). 이
스크립트는 그 질문을 사내에서 한 번에 재고, 결과를 리뷰 문서에 **그대로 붙일 수 있는 Markdown
블록**으로 찍는다.

    uv run --no-sync python scripts/inspect_real_data_checks.py             # DB 확인 넷
    uv run --no-sync python scripts/inspect_real_data_checks.py --only bdq  # BigDataQuery

| 블록 | `--only` | 무엇을 |
|---|---|---|
| 8-1 | `env` | 두 DB 의 마이그레이션 번호·주요 표 행 수, 적용 배포, `ref_data` 사본 |
| 8-2 | `legacy` | 기존 결과와 신규 계산의 차이율·비율 분포, Wafer 경로 값·소요대수 ≈60 배 가르기 |
| 8-3 | `reqb` | 원천 `RQ_REQB` 의 소요기준별 행·공정 수 |
| 8-4 | `equipment` | 설비 DB 의 2262-04-11 Qual·환산비 0.2 모듈 행·일정 미정·사용기준 HBM·EDP |
| 8-5 | `bdq` | 목록 조회 시간·`reg_date` 꼴·코드 규칙 위반·전 코드 적재일·표본 적재일·사본 여부 |

**지키는 것 셋.**

- **앱을 끄고 돌린다.** DuckDB 는 프로세스 배타 잠금이다. 앱이 떠 있으면 DB 를 열지 못하고
  그렇게 알린 뒤 멈춘다(코드 1).
- **읽기만 한다.** 두 DB 를 `read_only=True` 로 열고 저장소(Repository)를 만들지 않는다 —
  저장소의 `initialize()` 는 마이그레이션을 건다(쓰기다).
- **값을 찍지 않는다.** 개수·비율·dtype·초만 찍는다. 제품·고객·공정·설비·시뮬레이션 이름과
  코드, 키별 값, 합계 물량, 파일 경로, **예외 문구**를 찍지 않는다 — 이 앱의 오류 문구에는
  설계상 식별값이 박혀 있다. 실패는 예외 종류(클래스 이름)만 적는다. 출력은 리뷰 문서를 거쳐
  사외로 나가는 유일한 것이다.

사외에서 돌린 수는 합성 표본의 `샘플 관측` 일 뿐 업무 사실이 아니다(AGENTS.md 10-1).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from collections import Counter
from collections.abc import Callable, Hashable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Final, Protocol, TextIO, TypeVar, cast

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from capa_simulation.io.bigdataquery_catalog import (  # noqa: E402
    fetch_simulation_catalog,
    is_bigdataquery_catalog_configured,
)
from capa_simulation.io.company_bigdataquery_adapter import (  # noqa: E402
    BDQ_USER_NAME_ENV,
    DETAIL_WINDOW_DAYS_AFTER,
    DETAIL_WINDOW_DAYS_BEFORE,
    QUERY_TEMPLATE,
    SOURCE_COLUMN_MAPPING,
    BigDataQueryModule,
    QueryWindow,
    build_query,
    call_get_data,
    is_bigdataquery_adapter_configured,
    is_bigdataquery_package_available,
    is_valid_simulation_code,
    load_bigdataquery_module,
    registration_detail_window,
    resolve_user_name,
)
from capa_simulation.io.core_data_source import (  # noqa: E402
    CoreDataContract,
    load_core_data_contract,
)
from capa_simulation.persistence._sql_helpers import load_frame  # noqa: E402
from capa_simulation.persistence.equipment_migration_runner import (  # noqa: E402
    load_equipment_migrations,
)
from capa_simulation.persistence.equipment_repository import (  # noqa: E402
    LEGACY_QUAL_PLACEHOLDER,
    _read_snapshot,
)
from capa_simulation.persistence.migration_runner import load_migrations  # noqa: E402
from capa_simulation.persistence.repository import (  # noqa: E402
    DATASET_TABLES,
    REVISION_TABLES,
)
from capa_simulation.services.bigdataquery_catalog_view import (  # noqa: E402
    code_registration_span,
    first_registration_dates,
    format_registered_at,
    normalize_catalog,
)
from capa_simulation.services.core_data_derivation import build_q_core_data  # noqa: E402
from capa_simulation.services.equipment_contract import (  # noqa: E402
    COUNTED_USAGE_BASIS,
    EQUIPMENT_ID_COLUMN,
    USAGE_BASIS_COLUMN,
    counts_for_capacity,
    usage_basis_key,
)
from capa_simulation.services.equipment_units import (  # noqa: E402
    format_unit_count,
    unit_keys,
)
from capa_simulation.services.frame_contracts import (  # noqa: E402
    AREA_NAMES,
    DEMAND_BASES,
    UNIMPLEMENTED_BASES,
    match_key,
    normalize_demand_basis,
)
from capa_simulation.services.legacy_comparison import (  # noqa: E402
    AGREE_GROUP,
    COMPARISONS,
    FORMULA_INPUTS,
    GROUP_COLUMN,
    NEAR_TARGETS,
    NEAR_TOLERANCE,
    OTHER_GROUP,
    RATIO_GROUPS,
    ROUTE_SPLIT_TOLERANCE,
    SUSPECT_GROUP,
    TIGHT_TOLERANCE,
    WAFER_ROUTE_FACTORS,
    WAFER_ROUTE_RESULTS,
    DifferenceDistribution,
    FormulaInput,
    LegacyMetric,
    Quantiles,
    RatioDistribution,
    RouteCells,
    RouteLink,
    ScalingCheck,
    attach_formula_inputs,
    compare_metric,
    describe_ratios,
    difference_distribution,
    factor_agreement,
    fold_route_cells,
    fold_route_result,
    folded_route_totals,
    group_spread,
    hourly_rate,
    input_applies,
    legacy_grain,
    measured_wafer_load,
    median_ratio,
    process_consistency,
    ratio_distribution,
    ratio_groups,
    route_cells,
    route_factor_by_key,
    route_factor_values,
    scaling_check,
    split_mixed_processes,
    split_route_cells,
    summarize_comparison,
    time_agreement,
)
from capa_simulation.services.load_calculator import (  # noqa: E402
    calculate_chip_load,
    calculate_density_load,
    calculate_wafer_load,
)
from capa_simulation.services.product_type import WF_DIVISIONS_BY_PRODUCT_TYPE  # noqa: E402
from capa_simulation.services.required_equipment import (  # noqa: E402
    REQB_COLUMNS,
    REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR,
    calculate_required_equipment,
)
from capa_simulation.services.undated_equipment import (  # noqa: E402
    UNDATED_KIND_COLUMN,
    UNDATED_KINDS,
    undated_counts,
    undated_equipment,
)
from capa_simulation.services.unit_capacity import calculate_unit_capacity  # noqa: E402
from capa_simulation.services.usage_basis import (  # noqa: E402
    usage_excluded_count,
    usage_excluded_equipment,
)
from capa_simulation.settings import DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH  # noqa: E402

CHECKS: Final[tuple[str, ...]] = ("env", "legacy", "reqb", "equipment", "bdq")
# BigDataQuery 는 사내 DB 를 길게 훑는다. 따로 부를 때만 돈다.
DEFAULT_CHECKS: Final[tuple[str, ...]] = ("env", "legacy", "reqb", "equipment")

# 기존 결과가 실려 오는 원천 컬럼. 채움 상태는 늘 찍는다.
LEGACY_CANDIDATES: Final[tuple[str, ...]] = (
    "WF수(매)",
    "EQ(억Gb)",
    "소요대수",
    "PCB수(K매)",
    "Plan_Chip(K개)",
    "GOOD_DIE",
)
# 소요기준 PKG 의 계수 단위. 이름을 찍어도 되는 것은 계약 어휘(코드에 적힌 분류명)뿐이다.
KNOWN_BASES: Final[tuple[str, ...]] = (*DEMAND_BASES, *sorted(UNIMPLEMENTED_BASES))
BUFFER_DIVISION: Final = "BUFFER"
# `WF 구분` 의 계약 어휘. 이 밖의 값은 이름을 찍지 않고 종류 수만 센다.
DECLARED_DIVISIONS: Final[tuple[str, ...]] = tuple(
    dict.fromkeys(name for names in WF_DIVISIONS_BY_PRODUCT_TYPE.values() for name in names)
)

# 정식 대조(`COMPARISONS`)마다 표의 이름과 신규 계산. 대조 목록에 지표를 더하면 여기도 더한다.
LoadBuilder = Callable[[dict[str, pd.DataFrame]], pd.DataFrame]
LOAD_BUILDERS: Final[dict[str, tuple[str, LoadBuilder]]] = {
    "WF수(매)": (
        "Wafer",
        lambda t: calculate_wafer_load(t["RQ_PKG_PLAN"], t["RQ_YLD"], t["RQ_CHIP_QTY"]),
    ),
    "EQ(억Gb)": ("Density", lambda t: calculate_density_load(t["RQ_PKG_PLAN"], t["RQ_CHIP_EQ"])),
    "Plan_Chip(K개)": (
        "Chip",
        lambda t: calculate_chip_load(t["RQ_PKG_PLAN"], t["RQ_YLD"], t["RQ_CHIP_QTY"]),
    ),
}

# 소요대수 ≈60 배 가르기. 섞인 공정을 가를 후보 — 경로 키 13 가운데 공정·소요기준을 뺀 것과,
# 원천에만 있는 설비 칸(키에 값이 여럿이면 한 묶음으로 센다).
SPLIT_ATTRIBUTES: Final[tuple[str, ...]] = (
    "Area_Name",
    "WF 구분",
    "생산계획년월",
    "양산구분",
    "제품정보",
    "Stack",
    "Capa Code",
    "Customer",
    "CS",
    "STEP_SEQ",
    "MCP_SEQ",
)
ROUTE_SPLITTERS: Final[tuple[str, ...]] = ("메이커", "모델명")
# 기존 시스템이 경로 행마다 실어 보내고 신규 산식에는 없는 칸. 값은 찍지 않고 종류 수만 센다.
ROUTE_CATEGORIES: Final[tuple[str, ...]] = (
    "메이커",
    "모델명",
    "Para",
    "Step수",
    "Shot Time",
    "Shot수",
    "Index Time",
)
ROUTE_NUMBERS: Final[tuple[str, ...]] = ("Side반영률", "MCP_Chip_Ratio")

# 설비 모듈 행 환산비 — 직접 편집 칸의 `step=0.1` 이 0.25 를 0.2 로 자르던 결함의 흔적.
TRUNCATED_RATIO: Final = 0.2
MODULE_RATIO: Final = 0.25

# BigDataQuery 등록 화면과 같은 값이어야 한다(`components/bigdataquery_registration.py` —
# 그 모듈은 streamlit 을 불러 여기서 import 하지 않는다. 테스트가 두 값을 대조한다).
CATALOG_DEFAULT_DAYS: Final = 30
CATALOG_BUSY_ROWS: Final = 3000
CATALOG_MAX_DAYS: Final = 366
DEFAULT_SAMPLE: Final = 5
DEFAULT_MARGIN_DAYS: Final = 30

# 표본 코드의 적재일을 세는 조회. 사외에서 돌려 볼 수 없는 유일한 새 SQL 이다 — 테이블·컬럼은
# 상세·목록 SQL 과 같고 함수는 Impala·Hive 공통(`substr`·`cast ... AS string`)만 쓴다. 사내 엔진이
# 받지 않으면 이 줄만 실패로 적고 나머지는 계속한다.
LOAD_DAYS_QUERY_TEMPLATE: Final = """
SELECT
    substr(cast(impala_insert_time AS string), 1, 10) AS load_day,
    count(*) AS row_count
FROM camp_tsp.campavp_catb_sim_rslt_report
WHERE impala_insert_time >= '{start_date}'
  AND impala_insert_time <  '{end_date}'
  AND catb_sim_info_id = '{simulation_code}'
GROUP BY substr(cast(impala_insert_time AS string), 1, 10)
"""

# 목록 창 안의 **모든 코드**의 적재일 수·첫·끝 적재일·행 수를 한 번에 센다(GROUP BY 한 번).
# 이것도 사외에서 돌려 보지 못한 SQL 이다 — 테이블·컬럼·함수는 위 적재일 조회와 같고,
# `count(DISTINCT …)` 는 쿼리에 하나뿐이다(Impala 는 한 쿼리에 여럿을 받지 않는다). 결과에
# 코드가 실리지만 분포로만 접고 찍지 않는다.
CODE_LOAD_DAYS_QUERY_TEMPLATE: Final = """
SELECT
    catb_sim_info_id AS simulation_code,
    count(DISTINCT substr(cast(impala_insert_time AS string), 1, 10)) AS load_days,
    min(substr(cast(impala_insert_time AS string), 1, 10)) AS first_day,
    max(substr(cast(impala_insert_time AS string), 1, 10)) AS last_day,
    count(*) AS row_count
FROM camp_tsp.campavp_catb_sim_rslt_report
WHERE impala_insert_time >= '{start_date}'
  AND impala_insert_time <  '{end_date}'
GROUP BY catb_sim_info_id
"""
# 사본 확인의 기본 — 여러 날 코드 둘(표본 것 먼저), 코드마다 적재일 넷(첫 적재일·가운데·
# 끝 앞날·끝 날)을 앱 SQL 로 하루씩 다시 받는다 → 하루치 상세 조회 최대 8번. 사내 상세 한
# 번이 3~26초라 그보다 많으면 8-5 가 수십 분으로 는다. 한 번에 받지 않는 것은 매일 다시
# 적재된 코드가 적재일 수만큼 부푼 프레임(사내 표본 하나가 32일)으로 메모리에 오르기 때문이다.
DEFAULT_COPY_CODES: Final = 2
DEFAULT_COPY_DAYS: Final = 4

# 다른 시나리오에서 만든 데이터셋의 원천 종류(`components/` 의 복제·월 병합·연도 이동이 적는 값).
DERIVED_SOURCE_TYPES: Final[tuple[str, ...]] = (
    "DUCKDB_SCENARIO_CLONE",
    "SCENARIO_MONTH_MERGE",
    "SCENARIO_YEAR_SHIFT",
)

_Picked = TypeVar("_Picked", bound=Hashable)

_CODE_RULE: Final = "^[A-Za-z0-9._-]+$"
_DEFAULT_WINDOW: Final = f"−{DETAIL_WINDOW_DAYS_BEFORE}~+{DETAIL_WINDOW_DAYS_AFTER}일"
_LOCK_MESSAGE: Final = (
    "DB 를 열지 못했습니다. 앱이 떠 있으면 먼저 끄세요 — DuckDB 는 프로세스 배타 잠금입니다. "
    "앱이 꺼져 있는데도 이 줄이 나오면 파일 손상일 수 있다 — 그대로 리뷰 문서에 적는다."
)


# ---------------------------------------------------------------------------------- 출력 도우미


def _count(value: int | float | None) -> str:
    return "-" if value is None else f"{int(value):,}"


def _percent(value: float | None, digits: int = 4) -> str:
    return "-" if value is None else f"{value:.{digits}%}"


def _ratio(value: float | None) -> str:
    return "-" if value is None else f"{value:.4g}"


def _seconds(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}"


def _failure(exc: BaseException) -> str:
    """예외 종류만. 문구는 식별값을 실을 수 있어 찍지 않는다."""
    return f"실패({type(exc).__name__})"


def _table(headers: Sequence[str], rows: Iterable[Sequence[str]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


def _ranges(versions: Sequence[int]) -> str:
    """[1, 4, 5, 6, 9] → `1, 4–6, 9`."""
    if not versions:
        return "(없음)"
    ordered = sorted(set(versions))
    parts: list[str] = []
    start = previous = ordered[0]
    for value in ordered[1:]:
        if value == previous + 1:
            previous = value
            continue
        parts.append(str(start) if start == previous else f"{start}–{previous}")
        start = previous = value
    parts.append(str(start) if start == previous else f"{start}–{previous}")
    return ", ".join(parts)


def _heading(number: str, title: str, check: str) -> list[str]:
    return [f"### {number}. {title} (`{check}`)", ""]


# ---------------------------------------------------------------------------------- DB 열기


@dataclass
class Session:
    """한 번 실행 동안 연 두 DB 와 읽어 둔 표. 블록끼리 나눠 쓴다."""

    simulation_path: Path
    equipment_path: Path
    dataset_id: str | None
    simulation: duckdb.DuckDBPyConnection | None = None
    equipment: duckdb.DuckDBPyConnection | None = None
    simulation_failure: str | None = None
    equipment_failure: str | None = None
    _source: SourceData | None = None
    _source_failure: str | None = None
    locked: bool = False

    def close(self) -> None:
        for connection in (self.simulation, self.equipment):
            if connection is not None:
                connection.close()


def _open_read_only(path: Path) -> tuple[duckdb.DuckDBPyConnection | None, str | None, bool]:
    """(연결, 실패 문구, 잠금 여부). 파일 경로는 문구에 넣지 않는다 — 이름만."""
    if not path.exists():
        return None, f"`{path.name}` 파일이 없다", False
    try:
        return duckdb.connect(str(path), read_only=True), None, False
    except duckdb.IOException:
        return None, _LOCK_MESSAGE, True
    except duckdb.Error as exc:
        return None, f"`{path.name}` 을 열지 못했다 — {_failure(exc)}", False


def _scalar(connection: duckdb.DuckDBPyConnection, sql: str, params: Sequence[object] = ()) -> int:
    row = connection.execute(sql, list(params)).fetchone()
    return 0 if row is None or row[0] is None else int(row[0])


def _safe_scalar(
    connection: duckdb.DuckDBPyConnection, sql: str, params: Sequence[object] = ()
) -> str:
    try:
        return _count(_scalar(connection, sql, params))
    except duckdb.Error as exc:
        return _failure(exc)


def _versions(connection: duckdb.DuckDBPyConnection, table: str) -> list[int] | None:
    try:
        rows = connection.execute(f"SELECT version FROM {table} ORDER BY version").fetchall()
    except duckdb.Error:
        return None
    return [int(row[0]) for row in rows]


def _migration_line(
    label: str, path: Path, versions: list[int] | None, code_versions: Sequence[int]
) -> str:
    code_max = max(code_versions, default=0)
    size = path.stat().st_size / 1_000_000 if path.exists() else 0.0
    if versions is None:
        return f"- {label} `{path.name}` {size:,.1f} MB — 마이그레이션 표를 읽지 못함"
    db_max = max(versions, default=0)
    if db_max < code_max:
        state = "**코드보다 낮다** — 앱을 띄워 그 DB 를 여는 화면을 연 뒤 다시(4-2)"
    elif db_max > code_max:
        state = "**코드보다 높다** — 옛 배포를 적용했을 수 있다"
    else:
        state = "코드와 같다"
    return (
        f"- {label} `{path.name}` {size:,.1f} MB — 마이그레이션 {_ranges(versions)} "
        f"(최고 {db_max} · 코드 {code_max}, {state})"
    )


# ---------------------------------------------------------------------------------- 8-1 env


def _applied_deploy(root: Path) -> str:
    path = root / ".deploy" / "applied.json"
    if not path.exists():
        return "기록 없음(`.deploy/applied.json` 없음 — 사외 작업 폴더이거나 적용기를 쓰지 않았다)"
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return f"기록을 읽지 못함 — {_failure(exc)}"
    stamp = str(state.get("stamp") or "?")
    commit = str(state.get("commit") or "")[:7] or "?"
    return f"`{stamp}` (사외 커밋 `{commit}`)"


def _ref_data_copies(connection: duckdb.DuckDBPyConnection) -> tuple[int, int]:
    """(리비전 표 사본이 `ref_data` 에 남은 데이터셋 수, 그 사본 행 수)."""
    unions = " UNION ".join(
        f"SELECT DISTINCT dataset_id FROM ref_data.{table}" for table in REVISION_TABLES.values()
    )
    datasets = _scalar(connection, f"SELECT count(*) FROM ({unions})")
    rows = sum(
        _scalar(connection, f"SELECT count(*) FROM ref_data.{table}")
        for table in REVISION_TABLES.values()
    )
    return datasets, rows


def check_env(session: Session, *, now: datetime, root: Path = PROJECT_ROOT) -> list[str]:
    lines = _heading("8-1", "환경 — 두 DB 와 적용 배포", "env")
    lines.append(f"- 실행 {now:%Y-%m-%d %H:%M} · 적용 배포 {_applied_deploy(root)}")
    code_simulation = [migration.version for migration in load_migrations()]
    code_equipment = [migration.version for migration in load_equipment_migrations()]

    simulation = session.simulation
    if simulation is None:
        lines.append(f"- 시뮬레이션 DB — {session.simulation_failure}")
    else:
        versions = _versions(simulation, "app_meta.schema_migration")
        lines.append(
            _migration_line("시뮬레이션 DB", session.simulation_path, versions, code_simulation)
        )
        rows: list[list[str]] = []
        for label, sql in (
            ("데이터셋", "SELECT count(*) FROM app_meta.dataset"),
            ("시나리오(보관 포함)", "SELECT count(*) FROM app_meta.scenario"),
            ("보관된 시나리오", "SELECT count(*) FROM app_meta.scenario WHERE status <> 'ACTIVE'"),
            ("리비전", "SELECT count(*) FROM app_meta.scenario_revision"),
            ("공식버전", "SELECT count(*) FROM app_meta.official_release"),
            ("원천 행 `raw_data.core_data`", "SELECT count(*) FROM raw_data.core_data"),
            ("리비전 행 `rev_data.rq_reqb`", "SELECT count(*) FROM rev_data.rq_reqb"),
            ("리비전 행 `rev_data.rq_pkg_plan`", "SELECT count(*) FROM rev_data.rq_pkg_plan"),
        ):
            rows.append([label, _safe_scalar(simulation, sql)])
        try:
            kinds = simulation.execute(
                "SELECT source_type, count(*) FROM app_meta.dataset GROUP BY 1 ORDER BY 1"
            ).fetchall()
            rows.append(
                [
                    "데이터셋 원천 종류",
                    " · ".join(f"`{kind}` {int(count):,}" for kind, count in kinds) or "-",
                ]
            )
        except duckdb.Error as exc:
            rows.append(["데이터셋 원천 종류", _failure(exc)])
        try:
            copied, copied_rows = _ref_data_copies(simulation)
            rows.append(
                [
                    "`ref_data` 에 리비전 표 사본이 남은 데이터셋",
                    f"{copied:,} (사본 {copied_rows:,}행 — 리비전 1 과 달라 `0033` 이 남긴 사본. "
                    "0 이 아니어도 결함 아님)",
                ]
            )
        except duckdb.Error as exc:
            rows.append(["`ref_data` 에 리비전 표 사본이 남은 데이터셋", _failure(exc)])
        lines.extend(["", *_table(["시뮬레이션 DB", "행"], rows), ""])

    equipment = session.equipment
    if equipment is None:
        lines.append(f"- 설비 DB — {session.equipment_failure}")
        lines.append("")
        return lines
    versions = _versions(equipment, "equipment_meta.schema_migration")
    lines.append(_migration_line("설비 DB", session.equipment_path, versions, code_equipment))
    rows = []
    latest = _latest_equipment_revision(equipment)
    rows.append(
        ["설비 리비전", _safe_scalar(equipment, "SELECT count(*) FROM equipment_ops.revision")]
    )
    if latest is None:
        rows.append(["최신 설비 리비전", "없음"])
    else:
        revision_id, revision_no, contract = latest
        rows.append(["최신 설비 리비전", f"r{revision_no} · 계약 v{contract}"])
        for label, table in (
            ("최신 리비전 설비 마스터", "equipment_master_snapshot"),
            ("최신 리비전 기존 보유대수", "baseline_snapshot"),
            ("최신 리비전 비가동 일정", "downtime_schedule_snapshot"),
        ):
            rows.append(
                [
                    label,
                    _safe_scalar(
                        equipment,
                        f"SELECT count(*) FROM equipment_ops.{table} WHERE revision_id = ?",
                        [revision_id],
                    ),
                ]
            )
    lines.extend(["", *_table(["설비 DB", "행"], rows), ""])
    return lines


def _latest_equipment_revision(
    connection: duckdb.DuckDBPyConnection,
) -> tuple[str, int, int] | None:
    try:
        row = connection.execute(
            "SELECT revision_id, revision_no, coalesce(equipment_contract_version, 2) "
            "FROM equipment_ops.revision ORDER BY revision_no DESC LIMIT 1"
        ).fetchone()
    except duckdb.Error:
        return None
    if row is None:
        return None
    return str(row[0]), int(row[1]), int(row[2])


# ---------------------------------------------------------------------------------- 원천 읽기


@dataclass
class SourceData:
    """대조 기준 — 데이터셋의 원천 행과 그 시나리오의 리비전 1 표."""

    dataset_label: str
    raw: pd.DataFrame
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)


_SOURCE_DATASET_FILTER: Final = (
    f"source_type NOT IN ({', '.join('?' for _ in DERIVED_SOURCE_TYPES)}) "
    "AND EXISTS (SELECT 1 FROM raw_data.core_data AS c WHERE c.dataset_id = d.dataset_id)"
)


def _dataset_row(
    connection: duckdb.DuckDBPyConnection, dataset_id: str | None
) -> tuple[str, str, str, object] | None:
    """`--dataset-id` 가 없으면 원천에서 온 데이터셋 가운데 가장 최근 것.

    복제·월 병합·연도 이동은 다른 시나리오에서 만든 데이터셋이라 리비전 1 이 원천 그대로가 아니다
    (복제는 원천 행도 없다). 가장 최근이 그런 것이면 대조가 조용히 원천이 아닌 것을 보게 된다.
    """
    if dataset_id:
        row = connection.execute(
            "SELECT dataset_id, scenario_id, source_type, imported_at FROM app_meta.dataset "
            "WHERE dataset_id = ?",
            [dataset_id],
        ).fetchone()
    else:
        row = connection.execute(
            "SELECT dataset_id, scenario_id, source_type, imported_at FROM app_meta.dataset AS d "
            f"WHERE {_SOURCE_DATASET_FILTER} ORDER BY imported_at DESC LIMIT 1",
            list(DERIVED_SOURCE_TYPES),
        ).fetchone()
    if row is None:
        return None
    return str(row[0]), str(row[1]), str(row[2]), row[3]


def load_source(session: Session) -> SourceData | None:
    """가장 최근(또는 `--dataset-id`) 데이터셋의 원천과 리비전 1 표. 한 번만 읽는다."""
    if session._source is not None or session._source_failure is not None:
        return session._source
    connection = session.simulation
    if connection is None:
        session._source_failure = str(session.simulation_failure)
        return None
    try:
        picked = _dataset_row(connection, session.dataset_id)
        if picked is None:
            session._source_failure = (
                "그 데이터셋이 없다"
                if session.dataset_id
                else "원천에서 온 데이터셋이 없다(복제·월 병합·연도 이동뿐이거나 등록한 적이 없다)"
            )
            return None
        dataset_id, scenario_id, source_type, imported_at = picked
        total = _scalar(connection, "SELECT count(*) FROM app_meta.dataset")
        sources = _scalar(
            connection,
            f"SELECT count(*) FROM app_meta.dataset AS d WHERE {_SOURCE_DATASET_FILTER}",
            DERIVED_SOURCE_TYPES,
        )
        revision = connection.execute(
            "SELECT revision_id FROM app_meta.scenario_revision "
            "WHERE scenario_id = ? AND revision_no = 1",
            [scenario_id],
        ).fetchone()
        if revision is None:
            session._source_failure = "그 데이터셋 시나리오의 리비전 1 이 없다"
            return None
        revision_id = str(revision[0])
        raw = connection.execute(
            "SELECT * EXCLUDE (dataset_id, source_row_no, row_hash) "
            "FROM raw_data.core_data WHERE dataset_id = ? ORDER BY source_row_no",
            [dataset_id],
        ).fetch_df()
        tables: dict[str, pd.DataFrame] = {}
        for logical, physical in REVISION_TABLES.items():
            tables[logical] = load_frame(
                connection,
                schema="rev_data",
                table_name=physical,
                owner_column="revision_id",
                owner_id=revision_id,
            )
        for logical, physical in DATASET_TABLES.items():
            tables[logical] = load_frame(
                connection,
                schema="ref_data",
                table_name=physical,
                owner_column="dataset_id",
                owner_id=dataset_id,
            )
    except (duckdb.Error, RuntimeError) as exc:
        session._source_failure = _failure(exc)
        return None
    which = (
        "`--dataset-id` 로 고른"
        if session.dataset_id
        else "원천에서 온 것 가운데 가장 최근에 적재한"
    )
    stamp = str(imported_at)[:10] if imported_at is not None else "?"
    label = (
        f"{which} 데이터셋(전체 {total:,}개 · 원천에서 온 것 {sources:,}개) · 원천 종류 "
        f"`{source_type}` · 적재 {stamp} · 원천 {len(raw):,}행 · 계산은 그 시나리오의 리비전 1"
    )
    if source_type in DERIVED_SOURCE_TYPES or raw.empty:
        label += " · **⚠ 원천에서 온 데이터셋이 아니다 — 리비전 1 이 원천 그대로가 아닐 수 있다**"
    else:
        label += "(원천 그대로)"
    session._source = SourceData(dataset_label=label, raw=raw, tables=tables)
    return session._source


# ---------------------------------------------------------------------------------- 8-2 legacy


@dataclass(frozen=True)
class ComparisonResult:
    label: str
    comparison: pd.DataFrame | None = None
    failure: str | None = None


def _difference_row(result: ComparisonResult) -> list[str]:
    if result.comparison is None:
        return [result.label, result.failure or "-", *["-"] * 10]
    summary = summarize_comparison(result.comparison)
    spread: DifferenceDistribution = difference_distribution(result.comparison)
    over = dict(spread.over)
    return [
        result.label,
        _count(spread.keys),
        _percent(spread.median),
        _percent(spread.p95),
        _percent(spread.maximum),
        _count(over.get(0.001)),
        _count(over.get(0.01)),
        _ratio(spread.sum_ratio),
        _count(cast(int, summary["기존 0·신규 있음"])),
        _count(cast(int, summary["값 불일치"])),
        _count(cast(int, summary["신규에만 있음"])),
        _count(cast(int, summary["기존에만 있음"])),
    ]


_DIFFERENCE_HEADERS: Final = (
    "대조",
    "키",
    "차이율 중앙",
    "p95",
    "최대",
    ">0.1%",
    ">1%",
    "Σ신규÷Σ기존",
    "기존 0·신규 있음",
    "값 불일치",
    "신규에만",
    "기존에만",
)


def _decades(spread: RatioDistribution) -> str:
    return " · ".join(f"10^{power}: {count:,}" for power, count in spread.decades) or "-"


def _ratio_row(label: str, spread: RatioDistribution) -> list[str]:
    near = dict(spread.near)
    return [
        label,
        _count(spread.keys),
        _count(spread.undefined),
        _ratio(spread.p5),
        _ratio(spread.median),
        _ratio(spread.p95),
        _count(near.get(1.0)),
        _count(near.get(1_000.0)),
        _count(near.get(0.001)),
        _decades(spread),
    ]


_RATIO_HEADERS: Final = (
    "비율",
    "자리",
    "정의 안 됨",
    "p5",
    "중앙",
    "p95",
    "≈1",
    "≈1000",
    "≈0.001",
    "자릿수(10^k: 자리 수)",
)


def _fill_rows(raw: pd.DataFrame) -> list[list[str]]:
    rows: list[list[str]] = []
    for column in LEGACY_CANDIDATES:
        if column not in raw.columns:
            rows.append([f"`{column}`", "원천에 컬럼 없음", "-", "-", "-"])
            continue
        values = pd.to_numeric(raw[column], errors="coerce")
        filled = int(values.notna().sum())
        rows.append(
            [
                f"`{column}`",
                f"{filled:,} / {len(raw):,}",
                _count(int(values.eq(0).sum())),
                _count(int(values.lt(0).sum())),
                _count(int(values.nunique())),
            ]
        )
    return rows


def _filled(frame: pd.DataFrame, column: str) -> bool:
    return column in frame.columns and bool(
        pd.to_numeric(frame[column], errors="coerce").notna().any()
    )


def _compare_built(
    core: pd.DataFrame,
    build: Callable[[], pd.DataFrame],
    metric: LegacyMetric,
    contract: CoreDataContract,
) -> pd.DataFrame:
    return compare_metric(core, build(), metric, contract)


def _guarded(label: str, build: Callable[[], pd.DataFrame]) -> ComparisonResult:
    try:
        return ComparisonResult(label=label, comparison=build())
    except Exception as exc:  # 계산·대조 어디서 실패해도 다른 지표는 계속 잰다
        return ComparisonResult(label=label, failure=_failure(exc))


def _route_frame(core: pd.DataFrame) -> pd.DataFrame:
    """경로 행 — `RQ_REQB` 를 만드는 것과 같은 행(Area_Name 이 빈 행은 경로가 아니다)."""
    route = core.loc[core["Area_Name"].astype("string").str.strip().fillna("").ne("")].copy()
    route["소요기준"] = normalize_demand_basis(route["소요기준"])
    return route


def _key_set(frame: pd.DataFrame, keys: Sequence[str]) -> set[tuple[object, ...]]:
    prepared = frame.loc[:, list(keys)].copy()
    for key in keys:
        if key == "생산계획년월":
            prepared[key] = pd.to_numeric(prepared[key], errors="coerce").astype("Int64")
        else:
            prepared[key] = prepared[key].astype("string").str.strip()
    return {
        tuple(None if pd.isna(value) else value for value in row)
        for row in prepared.astype(object).to_numpy()
    }


def _required_equipment(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    unit_capacity = calculate_unit_capacity(
        upeh=tables["RQ_UPEH"],
        run_rate=tables["RQ_RUN_RATE"],
        vital=tables["RQ_VITAL"],
        module=tables["RQ_MODULE"],
        run_day=tables["RQ_RUN_DAY"],
        lot_ratio=tables["RQ_LOT_RATIO"],
        wf_ratio=tables["RQ_WF_RATIO"],
    )
    return calculate_required_equipment(
        reqb=tables["RQ_REQB"],
        plan=tables["RQ_PKG_PLAN"],
        yield_data=tables["RQ_YLD"],
        chip_qty=tables["RQ_CHIP_QTY"],
        unit_capacity=unit_capacity,
    )


def _requirement_section(
    core: pd.DataFrame, tables: dict[str, pd.DataFrame], calculated: Required
) -> list[str]:
    lines = ["**소요대수** — 신규는 리비전 1 로 다시 계산한 `RQ_REQB` 행별 소요대수다.", ""]
    contract = load_core_data_contract()
    required = calculated.frame
    if required is None:
        return [*lines, f"- 신규 소요대수 계산 {calculated.failure} — 대조하지 않았다", ""]
    route = _route_frame(core)
    exclusions = required.attrs.get(REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR)
    excluded_keys = (
        _key_set(exclusions, REQB_COLUMNS)
        if isinstance(exclusions, pd.DataFrame) and not exclusions.empty
        else set()
    )
    fresh_keys = _key_set(required, REQB_COLUMNS) | excluded_keys
    route_keys = _key_set(route, REQB_COLUMNS)
    linked = len(fresh_keys & route_keys)
    lines.append(
        f"- 키 연결(값과 무관) — 신규 경로 키 {len(fresh_keys):,} 중 원천 경로에 있는 키 "
        f"{linked:,} ({_percent(linked / len(fresh_keys) if fresh_keys else None, 2)}) · "
        "신규가 제외 목록에 둔 키 "
        f"{len(excluded_keys):,}"
    )
    if not _filled(route, "소요대수"):
        lines.extend(["- 원천 `소요대수` 가 비어 있어 대조 불가", ""])
        return lines
    unimplemented = route["소요기준"].isin(UNIMPLEMENTED_BASES).fillna(False)
    dropped = int((unimplemented & pd.to_numeric(route["소요대수"], errors="coerce").notna()).sum())
    lines.append(
        f"- 원천 소요기준 BOX·PCB 경로 행 가운데 값이 든 {dropped:,}행은 뺐다"
        "(신규가 아직 세지 않는다)"
    )
    compared = route.loc[~unimplemented].copy()
    compared["_원천행"] = np.arange(len(compared))
    metric = LegacyMetric(label="소요대수", legacy_column="소요대수", new_column="소요대수")
    finest = [*legacy_grain(contract), *REQB_COLUMNS]
    month_process = ["생산계획년월", "공정", "소요기준"]
    results = [
        _guarded(
            "경로 키 13 · 같은 경로 반복을 접음",
            lambda: compare_metric(
                compared, required, metric, contract, keys=REQB_COLUMNS, grain=finest
            ),
        ),
        _guarded(
            "월×공정×소요기준 · 접음",
            lambda: compare_metric(
                compared, required, metric, contract, keys=month_process, grain=finest
            ),
        ),
        _guarded(
            "월×공정×소요기준 · 접지 않고 행마다 더함",
            lambda: compare_metric(
                compared,
                required,
                metric,
                contract,
                keys=month_process,
                grain=[*month_process, "_원천행"],
            ),
        ),
    ]
    by_basis = results[1].comparison
    if by_basis is not None:
        for basis in DEMAND_BASES:
            part = by_basis.loc[by_basis["소요기준"].astype("string").eq(basis)]
            if not part.empty:
                results.append(
                    ComparisonResult(label=f"└ 접음 · 소요기준 {basis}", comparison=part)
                )
    lines.extend(["", *_table(_DIFFERENCE_HEADERS, [_difference_row(r) for r in results]), ""])
    ratio_rows = [
        _ratio_row(f"기존÷신규 · {r.label}", ratio_distribution(r.comparison))
        for r in results[:3]
        if r.comparison is not None
    ]
    if ratio_rows:
        lines.extend([*_table(_RATIO_HEADERS, ratio_rows), ""])
    path = results[0].comparison
    if path is not None:
        try:
            lines.extend(_ratio_breakdown(path, compared, required, tables, finest))
        except Exception as exc:  # 가르기가 실패해도 아래 절은 계속 잰다
            lines.extend([f"- ≈60 배 가르기 {_failure(exc)}", ""])
    return lines


# ------------------------------------------------------------------ 8-2 소요대수 ≈60 배 가르기


def _ratio_breakdown(
    path: pd.DataFrame,
    route: pd.DataFrame,
    required: pd.DataFrame,
    tables: dict[str, pd.DataFrame],
    grain: Sequence[str],
) -> list[str]:
    """경로 키 대조를 기존÷신규 ≈60·≈1·그 밖 세 무리로 나눠 어디서 60 배가 나는지 센다.

    사내 리뷰 202610071831·202610080745 에서 경로 키 절반이 기존 = 신규 × 60 이었다. 어느 쪽이
    틀렸는지 모르므로 판정하지 않고 가르기만 한다 — 속성·공정·산식 인자·원천 칸마다 개수와 분포.
    """
    groups = ratio_groups(path)
    frame = groups.frame
    if groups.size(SUSPECT_GROUP) == 0:
        return [
            f"- ≈60 배 가르기 — 비율이 정의된 경로 키 {len(frame):,} 가운데 ≈60 이 없어 건너뛴다",
            "",
        ]
    link = RouteLink.build(frame, route)
    sizes = {group: groups.size(group) for group in RATIO_GROUPS}
    lines = [
        "**소요대수 ≈60 배 가르기** — 위 `경로 키 13` 대조의 키를 기존÷신규 ≈60 · ≈1(각 ±"
        f"{NEAR_TOLERANCE:.0%}) · 그 밖 세 무리로 나눠 60 배가 어디서 나는지 개수로 본다. "
        "어느 쪽이 틀렸는지는 판정하지 않는다.",
        "",
        f"- 비율이 정의된 경로 키 {len(frame):,} — ≈60 {sizes[SUSPECT_GROUP]:,}"
        f"(그 가운데 60 ±0.1% 안 {groups.tight:,}) · ≈1 {sizes[AGREE_GROUP]:,} · 그 밖 "
        f"{sizes[OTHER_GROUP]:,} · 비율이 정의되지 않은 키 {groups.undefined:,}",
        "",
        "무리마다 속성별 키 수 — 한 줄에 몰리면 그 속성이 60 배를 가른다. WF 구분은 계약 어휘만 "
        "이름을 적고 나머지는 종류 수만 적는다.",
        "",
        *_table(["속성", *RATIO_GROUPS], _group_attribute_rows(frame)),
        "",
    ]
    lines.extend(_process_split_lines(frame, link))
    lines.extend(_formula_input_lines(frame, required, tables, link, route, grain))
    lines.extend(_route_category_lines(link, route))
    return lines


def _group_attribute_rows(frame: pd.DataFrame) -> list[list[str]]:
    group = frame[GROUP_COLUMN]

    def row(label: str, mask: pd.Series) -> list[str]:
        return [label, *(_count(int((mask & group.eq(name)).sum())) for name in RATIO_GROUPS)]

    rows = [row("키", pd.Series(True, index=frame.index))]
    basis = match_key(normalize_demand_basis(frame["소요기준"]))
    for name in DEMAND_BASES:
        mask = basis.eq(name.casefold())
        if mask.any():
            rows.append(row(f"소요기준 {name}", mask))
    area = match_key(frame["Area_Name"])
    for name in AREA_NAMES:
        mask = area.eq(name.casefold())
        if mask.any():
            rows.append(row(f"{name} 경로", mask))
    division = match_key(frame["WF 구분"])
    declared = {name.casefold(): name for name in DECLARED_DIVISIONS}
    for key, name in declared.items():
        mask = division.eq(key)
        if mask.any():
            rows.append(row(f"WF 구분 {name.upper()}", mask))
    others = ~division.isin(set(declared))
    if others.any():
        rows.append(row(f"WF 구분 그 밖({division.loc[others].nunique():,}종)", others))
    return rows


def _process_split_lines(frame: pd.DataFrame, link: RouteLink) -> list[str]:
    consistency = process_consistency(frame)
    lines = [
        f"- 공정 {consistency.processes:,}개 — 키가 전부 ≈60 {consistency.all_suspect:,} · 전부 ≈1 "
        f"{consistency.all_agree:,} · 전부 그 밖 {consistency.all_other:,} · **≈60 과 ≈1 이 섞임 "
        f"{consistency.mixed:,}** · ≈60·≈1 하나와 그 밖이 섞임 {consistency.partly_other:,}",
        "",
    ]
    if consistency.mixed == 0:
        return lines
    candidates = frame.copy()
    splitters = list(SPLIT_ATTRIBUTES)
    for column in ROUTE_SPLITTERS:
        if not link.texts(column).empty:
            candidates[column] = link.labels(column)
            splitters.append(column)
    rows = [
        [f"`{count.attribute}`", _count(count.splits), _count(count.fails), _count(count.trivial)]
        for count in split_mixed_processes(candidates, splitters)
    ]
    lines.extend(
        [
            f"≈60 과 ≈1 이 섞인 공정 {consistency.mixed:,}개를 무엇이 가르나 — 공정 안에서 "
            "그 칸 값마다 무리가 하나뿐이면 「가름」, 값이 키마다 달라 저절로 갈린 것은 "
            "「자명」(증거가 못 된다).",
            "",
            *_table(["칸", "가름", "못 가름", "자명"], rows),
            "",
        ]
    )
    return lines


def _reach_label(item: FormulaInput) -> str:
    if item.area is not None:
        return item.area
    if item.bases:
        return "·".join(item.bases)
    return "전부"


def _spread_cell(quantiles: Quantiles, *, volume: bool) -> str:
    if quantiles.keys == 0:
        return "-"
    if volume:
        return "(물량)"
    return f"{_ratio(quantiles.p5)} · {_ratio(quantiles.median)} · {_ratio(quantiles.p95)}"


def _input_row(
    label: str,
    reach: str,
    spread: dict[str, Quantiles],
    *,
    volume: bool = False,
    check: ScalingCheck | None = None,
) -> list[str]:
    other = spread[OTHER_GROUP]
    return [
        label,
        reach,
        f"{spread[SUSPECT_GROUP].keys:,} / {spread[AGREE_GROUP].keys:,}",
        _spread_cell(spread[SUSPECT_GROUP], volume=volume),
        _spread_cell(spread[AGREE_GROUP], volume=volume),
        "(물량)" if volume and other.keys else _ratio(other.median),
        _ratio(median_ratio(spread)),
        "-" if check is None else f"{check.fixed:,} / {check.applicable:,}",
        "-" if check is None else _count(check.collateral),
    ]


_INPUT_HEADERS: Final = (
    "인자",
    "걸리는 곳",
    "값 있는 키 ≈60 / ≈1",
    "≈60 p5 · 중앙 · p95",
    "≈1 p5 · 중앙 · p95",
    "그 밖 중앙",
    "중앙 ≈60÷≈1",
    "60 배로 고침",
    "같이 어긋남",
)


def _formula_input_lines(
    frame: pd.DataFrame,
    required: pd.DataFrame,
    tables: dict[str, pd.DataFrame],
    link: RouteLink,
    route: pd.DataFrame,
    grain: Sequence[str],
) -> list[str]:
    inputs = attach_formula_inputs(frame, required, tables)
    rows: list[list[str]] = []
    for item in FORMULA_INPUTS:
        reach = input_applies(inputs, item)
        rows.append(
            _input_row(
                item.label,
                _reach_label(item),
                group_spread(inputs, inputs[item.label].where(reach)),
                volume=item.volume,
                check=scaling_check(inputs, item.keys, reach),
            )
        )
    load = pd.to_numeric(inputs["부하량"], errors="coerce").astype("float64")
    run_day = pd.to_numeric(inputs["RUN_DAY"], errors="coerce").astype("float64")
    daily_load = (load / run_day).where(run_day.gt(0) & load.gt(0))
    daily_need = folded_route_totals(inputs, route, "일 필요", grain)
    derived: list[tuple[str, pd.Series]] = [
        ("환산_UPEH (CHIP·PKG ÷1000)", hourly_rate(inputs)),
        ("UPEH × ST ÷ 3600 (둘 다 있는 키)", time_agreement(inputs)),
        ("원천 `일 필요` ÷ (부하량 ÷ RUN_DAY)", daily_need / daily_load),
        *[(f"원천 `{column}`", link.numbers(column)) for column in ROUTE_NUMBERS],
    ]
    rows.extend(_input_row(label, "-", group_spread(inputs, values)) for label, values in derived)
    return [
        "산식 인자 — 무리별 p5 · 중앙 · p95 와 중앙의 비(≈60 ÷ ≈1 이 60 이나 0.0167 근처면 "
        "그 인자가 단위째 다르다). 「60 배로 고침」은 ≈1 키가 쓰지 않는 인자 값만 신규가 60 배가 "
        "되는 쪽으로 고쳐 다시 계산했을 때 ≈1 이 되는 ≈60 키 / 그 인자가 걸리는 ≈60 키(분모가 "
        "첫 줄의 ≈60 전체보다 작으면 그 인자는 ≈60 무리 일부에만 걸린다), 「같이 어긋남」은 ≈60 "
        "키가 쓰는 인자 값을 모두 고치면 함께 ≈1 을 벗어나는 ≈1 키다. 고침이 ≈60 전체이고 "
        "어긋남이 0 인 인자만 혼자서 60 배를 설명한다(산식이 곱이라 키 하나로는 어느 인자든 "
        "맞춰진다). 공정마다 무리가 하나뿐이면 공정 단위보다 잘게 정해지는 인자는 모두 그렇게 "
        "보인다 — 그때 가르는 것은 공정을 넘어 값을 나눠 쓰는 부하량·제품 단위 인자와 위 표들이다.",
        "",
        *_table(_INPUT_HEADERS, rows),
        "",
        "- 상수(하루 24시간 · MI 의 3600 ÷ ST · CHIP·PKG 의 ÷1000)는 인자 값처럼 가를 수 없다 — "
        "3600 은 MI, ÷1000 은 CHIP·PKG 에만 걸리므로 위 속성 표의 Main/MI·소요기준 줄이 그 "
        "답이다. `원천 …` 줄은 기존 시스템이 실어 보낸 값이라 신규 산식에 없다 — `일 필요` 가 "
        "하루 부하라면 그 줄이 ≈60 무리에서도 1 근처일 때 60 배는 부하가 아니라 능력(대당 Capa) "
        "쪽에 있다.",
        "",
    ]


def _route_category_lines(link: RouteLink, route: pd.DataFrame) -> list[str]:
    rows: list[list[str]] = []
    for column in ROUTE_CATEGORIES:
        label = f"`{column}`"
        if column not in route.columns:
            rows.append([label, "원천에 컬럼 없음", *["-"] * 4])
            continue
        contrast = link.contrast(column)
        if contrast is None:
            rows.append([label, "값 없음", *["-"] * 4])
            continue
        distinct = contrast.distinct
        rows.append(
            [
                label,
                " / ".join(f"{distinct[group]:,}" for group in RATIO_GROUPS),
                _count(contrast.shared),
                f"{contrast.suspect_only:,} ({contrast.suspect_only_keys:,}키)",
                _count(contrast.agree_only),
                _ratio(contrast.numeric_ratio),
            ]
        )
    return [
        "원천 범주 칸 — 무리별 값 종류 수만 센다(값은 적지 않는다). ≈60 에만 있는 값이 ≈60 키 "
        "대부분을 덮으면 그 칸(설비 모델·시간 표기 등)이 60 배를 가른다. 숫자로 읽히는 값은 무리 "
        "중앙의 비도 본다.",
        "",
        *_table(
            [
                "원천 칸",
                "값 종류 ≈60 / ≈1 / 그 밖",
                "≈60·≈1 둘 다",
                "≈60 에만(그 값을 가진 ≈60 키)",
                "≈1 에만",
                "숫자 중앙 ≈60÷≈1",
            ],
            rows,
        ),
        "",
    ]


# ------------------------------------------------------------------ 8-2 Wafer 경로 값 가르기


@dataclass(frozen=True)
class Required:
    """리비전 1 로 다시 계산한 `RQ_REQB` 행별 결과. 실패하면 예외 종류만 남는다."""

    frame: pd.DataFrame | None
    failure: str | None = None


def _calculate_required(tables: dict[str, pd.DataFrame]) -> Required:
    try:
        return Required(frame=_required_equipment(tables))
    except Exception as exc:  # 기준정보 오류면 계산이 멈춘다. 종류만 적는다
        return Required(frame=None, failure=_failure(exc))


def _wafer_route_tables(cells: RouteCells) -> list[str]:
    split_rows = [
        [f"`{count.attribute}`", _count(count.splits), _count(count.fails), _count(count.trivial)]
        for count in split_route_cells(cells)
    ]
    fold_rows: list[list[str]] = []
    for factor in WAFER_ROUTE_FACTORS:
        fold = fold_route_cells(cells, route_factor_values(cells.frame, factor), label=factor.label)
        fold_rows.append(
            [
                f"`{fold.label}`",
                _count(fold.testable),
                _count(fold.constant),
                _count(fold.divided),
                _count(fold.multiplied),
            ]
        )
    result_rows: list[list[str]] = []
    for factor in WAFER_ROUTE_RESULTS:
        result = fold_route_result(cells, factor)
        inverse, forward = _count(result.inverse), _count(result.forward)
        result_rows.append(
            [
                f"`{result.label}`",
                _count(result.testable),
                _count(result.constant),
                _count(result.equal),
                "-" if result.additive else inverse,
                "-" if result.additive else forward,
                inverse if result.additive else "-",
                forward if result.additive else "-",
            ]
        )
    return [
        "갈리는 칸을 무엇이 가르나 — 칸 안에서 그 칸 값마다 `WF수(매)` 가 한 값이면 "
        "「가름」, 칸 값이 행마다 달라 저절로 그렇게 된 것은 「자명」(증거가 못 된다).",
        "",
        *_table(["칸", "가름", "못 가름", "자명"], split_rows),
        "",
        "경로 칸으로 나누거나 곱하면 한 값이 되나 — 갈리는 칸 가운데 모든 행에 그 칸 "
        "값(양수)이 있는 칸만 본다. 「÷ 로 한 값」이 `값이 다 있는 칸` − `칸 안에서 한 값` 에 "
        "가까우면 원천 경로 값 = 계획 줄 값 × 그 칸이다(칸 안의 비만 보므로 그 칸의 "
        "단위·배율과 무관하다). 같이 움직인다는 뜻이지 원인이라는 뜻은 아니다.",
        "",
        *_table(
            [
                "경로 칸",
                "값이 다 있는 칸",
                "칸 안에서 한 값(가를 수 없음)",
                "÷ 로 한 값",
                "× 로 한 값",
            ],
            fold_rows,
        ),
        "",
        "결과 칸 — 기존 시스템이 경로마다 실어 보낸 결과라 원천 경로 값에서 만들어졌을 수 "
        "있다(인과 "
        "방향을 모른다). 한 값이 되어도 설명이 아니라 같이 움직인다는 뜻이다. `값과 같은 칸` 은 "
        "그 칸이 곧 "
        "경로 값인 칸이라 나머지 칸에서 뺐다. `TEST WF수(매)` 는 같은 단위라 빼기·더하기로 본다.",
        "",
        *_table(
            [
                "결과 칸",
                "값이 다 있는 칸",
                "칸 안에서 한 값",
                "값과 같은 칸",
                "÷ 로 한 값",
                "× 로 한 값",
                "− 로 한 값",
                "+ 로 한 값",
            ],
            result_rows,
        ),
        "",
    ]


def _wafer_route_comparison(
    core: pd.DataFrame,
    tables: dict[str, pd.DataFrame],
    required: Required,
    grain: Sequence[str],
    contract: CoreDataContract,
) -> list[str]:
    column = "WF수(매)"
    if required.frame is None:
        return [f"- 신규 계산 {required.failure} — 경로 키로 맞대지 않았다", ""]
    route = _route_frame(core)
    wf_route = route.loc[route["소요기준"].eq("WF").fillna(False).astype(bool)]
    fresh = required.frame
    wf_fresh = fresh.loc[
        normalize_demand_basis(fresh["소요기준"]).eq("WF").fillna(False).astype(bool)
    ].copy()
    finest = [*grain, *REQB_COLUMNS]

    def compared(new_column: str) -> pd.DataFrame:
        if new_column not in wf_fresh.columns:
            wf_fresh[new_column] = measured_wafer_load(wf_fresh, tables)
        metric = LegacyMetric(label="Wafer 경로", legacy_column=column, new_column=new_column)
        return compare_metric(wf_route, wf_fresh, metric, contract, keys=REQB_COLUMNS, grain=finest)

    results = [
        _guarded("WF 경로 키 13 · 신규 `부하량`", lambda: compared("부하량")),
        _guarded(
            "WF 경로 키 13 · 신규 `부하량 × Lot 측정률 × WF측정률`",
            lambda: compared("측정 반영 부하량"),
        ),
    ]
    lines = [
        "신규와 경로 키 13 으로 맞대기 — 소요기준 WF 경로만(CHIP·PKG 경로의 `부하량` 은 "
        "Wafer 가 아니다). 같은 경로 반복은 접고 Pack Code 는 더한다(소요대수와 같은 접기). "
        "둘째 줄은 측정률을 부하 쪽으로 옮긴 값이다(소요대수가 실제로 나누는 부하).",
        "",
        *_table(_DIFFERENCE_HEADERS, [_difference_row(result) for result in results]),
        "",
    ]
    ratio_rows = [
        _ratio_row(f"기존÷신규 · {result.label}", ratio_distribution(result.comparison))
        for result in results
        if result.comparison is not None
    ]
    if ratio_rows:
        lines.extend([*_table(_RATIO_HEADERS, ratio_rows), ""])
    path = results[0].comparison
    if path is None:
        return lines
    frame = ratio_groups(path).frame
    link = RouteLink.build(frame, wf_route)
    rows: list[list[str]] = []
    for factor in WAFER_ROUTE_FACTORS:
        agreement = factor_agreement(frame, route_factor_by_key(link, factor), label=factor.label)
        rows.append(
            [
                f"`{agreement.label}`",
                _count(agreement.keys),
                _count(agreement.off_one),
                _count(agreement.near_factor),
                _count(agreement.near_inverse),
                _count(agreement.near_one),
            ]
        )
    lines.extend(
        [
            "기존÷신규(`부하량`)가 경로 칸을 따라가나 — 경로 키마다 그 키 원천 경로 행의 칸 "
            f"값(중앙)과 견준다. **이 표의 ≈ 는 ±{TIGHT_TOLERANCE:.1%}** 다(위 표들의 "
            f"±{NEAR_TOLERANCE:.0%} 가 아니다). `≈ 칸` 이 `칸 ≠1 인 키` 에 가까우면 원천 경로 "
            "값 = 신규 계획 줄 Wafer × 그 칸이다.",
            "",
            *_table(
                ["경로 칸", "키", "칸 ≠1 인 키", "그 가운데 기존÷신규 ≈ 칸", "≈ 1÷칸", "≈1"],
                rows,
            ),
            "",
        ]
    )
    return lines


def _wafer_route_section(
    core: pd.DataFrame,
    tables: dict[str, pd.DataFrame],
    required: Required,
    grain: Sequence[str],
    contract: CoreDataContract,
) -> list[str]:
    """Wafer `WF수(매)` 를 경로 단위로 본다(2026-10-10 사용자 결정).

    원천 안에서 경로 값이 무엇으로 갈리는지 가르고, 신규 계산과 경로 키 13 으로 맞댄다.
    """
    column = "WF수(매)"
    lines = [
        "**Wafer `WF수(매)` 경로 값** — 위 표의 Wafer `값 불일치` 는 계획 줄 × WF 구분 안에서 "
        "경로 행마다 `WF수(매)` 가 갈려서다(계획 줄 값이 아니라 경로 값). 신규 계산에는 경로마다 "
        "갈리는 Wafer 값이 없다 — 소요기준 WF 경로의 `부하량` 은 계획 줄(Pack Code 합산) × "
        "WF 구분의 Wafer 부하량을 그 계획 줄의 모든 WF 경로에 같은 값으로 붙인 것이고, 측정률은 "
        "대당 Capa 의 분모로만 든다. 그래서 원천 경로 값이 무엇으로 갈리는지를 개수로 가른다.",
        "",
    ]
    if not _filled(core, column):
        return [*lines, "- 원천 `WF수(매)` 가 비어 있다", ""]
    spread, cells = route_cells(core, column, grain)
    lines.extend(
        [
            f"- 계획 줄 × WF 구분 칸 {spread.cells:,} 가운데 값이 갈리는 칸 {spread.split:,}(위 "
            f"`값 불일치` 가 여기서 난다) · 경로 행(Area_Name 있음)·양수만 남기면 칸 "
            f"{spread.route_cells:,} 가운데 ±{ROUTE_SPLIT_TOLERANCE:.1%} 를 넘게 갈리는 칸 "
            f"**{spread.route_split:,}** — 아래 두 표는 이 칸만 본다",
            "",
        ]
    )
    if spread.route_split:
        lines.extend(_wafer_route_tables(cells))
    lines.extend(_wafer_route_comparison(core, tables, required, grain, contract))
    return lines


def _with_raw_columns(
    core: pd.DataFrame, raw: pd.DataFrame, columns: Sequence[str]
) -> pd.DataFrame:
    """파생 프레임이 떨어뜨린 원천 칸(`메이커`·`모델명` 등)을 행 순서 그대로 되붙인다."""
    missing = [column for column in columns if column not in core and column in raw]
    if not missing or not core.index.equals(raw.index):
        return core
    return core.assign(**{column: raw[column] for column in missing})


def _pcb_section(raw: pd.DataFrame, core: pd.DataFrame, grain: Sequence[str]) -> list[str]:
    column = "PCB수(K매)"
    lines = [
        "**PCB수(K매)** — 신규 계산이 없다(PCB 산식 미구현, 소요기준 PCB 는 계산에서 뺀다).",
        "",
    ]
    if not _filled(raw, column):
        return [*lines, "- 원천 `PCB수(K매)` 가 비어 있다", ""]
    if not core.index.equals(raw.index):
        return [*lines, "- 원천과 파생 프레임의 행이 맞지 않아 건너뜀", ""]
    frame = core.loc[:, list(grain)].copy()
    frame[column] = pd.to_numeric(raw[column], errors="coerce")
    frame["생산수량"] = pd.to_numeric(core["생산수량"], errors="coerce")
    filled = frame.dropna(subset=[column])
    keys = list(grain)
    distinct = filled.groupby(keys, dropna=False)[column].nunique()
    lines.append(
        f"- 계획 줄×WF 구분 {len(distinct):,}칸 가운데 경로마다 값이 갈리는 칸 "
        f"{int(distinct.gt(1).sum()):,} (0 이면 계획 줄 단위 값이다)"
    )
    cells = filled.drop_duplicates(subset=keys)
    spread = describe_ratios(cells["생산수량"], cells[column])
    lines.extend(
        [
            "",
            *_table(
                _RATIO_HEADERS, [_ratio_row("생산수량 ÷ PCB수(K매) — PCB 한 매당 Unit", spread)]
            ),
            "",
        ]
    )
    return lines


def check_legacy(session: Session) -> list[str]:
    lines = _heading("8-2", "기존 결과 대조 — 분포만", "legacy")
    source = load_source(session)
    if source is None:
        return [*lines, f"- 원천을 읽지 못함 — {session._source_failure}", ""]
    raw, tables = source.raw, source.tables
    lines.extend([f"- {source.dataset_label}", ""])
    lines.extend(
        [
            *_table(["원천 컬럼", "값 있음", "0", "음수", "고유값 수"], _fill_rows(raw)),
            "",
        ]
    )
    if raw.empty:
        return [*lines, "- 원천 행이 없다", ""]
    contract = load_core_data_contract()
    try:
        core = build_q_core_data(raw, contract)
    except Exception as exc:  # 원천이 계약을 어기면 여기서 멈춘다
        return [*lines, f"- 파생 프레임을 만들지 못함 — {_failure(exc)}", ""]
    grain = legacy_grain(contract)

    lines.extend(
        [
            "**부하량** — 대조 키 `생산계획년월 × 제품정보 × Stack × WF 구분`, Chip 은 계획 줄"
            "(Pack Code 합산) × WF 구분(값은 계획 줄 × WF 구분에서 접은 뒤 더함).",
            "",
        ]
    )
    load_results: list[ComparisonResult] = []
    for metric in COMPARISONS:
        name, build = LOAD_BUILDERS.get(metric.legacy_column, (metric.label, None))
        label = f"{name} `{metric.legacy_column}`"
        if build is None:
            load_results.append(ComparisonResult(label=label, failure="신규 계산 연결 없음"))
            continue
        if not _filled(core, metric.legacy_column):
            load_results.append(ComparisonResult(label=label, failure="원천이 비어 대조 불가"))
            continue
        load_results.append(
            _guarded(label, partial(_compare_built, core, partial(build, tables), metric, contract))
        )
    lines.extend([*_table(_DIFFERENCE_HEADERS, [_difference_row(r) for r in load_results]), ""])

    required = _calculate_required(tables)
    try:
        lines.extend(_wafer_route_section(core, tables, required, grain, contract))
    except Exception as exc:  # 이 절이 멈춰도 소요대수·PCB 절과 다음 블록은 잰다
        lines.extend([f"- Wafer `WF수(매)` 경로 값 — {_failure(exc)}", ""])
    lines.extend(
        _requirement_section(_with_raw_columns(core, raw, ROUTE_CATEGORIES), tables, required)
    )
    lines.extend(_pcb_section(raw, core, grain))
    lines.extend(
        [
            f"- ≈ 는 기준의 ±{NEAR_TOLERANCE:.0%} 안. 기준 "
            + " · ".join(f"{target:g}" for target in NEAR_TARGETS)
            + ". 차이율은 |신규 − 기존| ÷ |기존|, 비율은 기존 ÷ 신규(두 값이 모두 양수인 자리만).",
            "",
        ]
    )
    return lines


# ---------------------------------------------------------------------------------- 8-3 reqb


def check_reqb(session: Session) -> list[str]:
    lines = _heading("8-3", "원천 RQ_REQB 소요기준 분포", "reqb")
    source = load_source(session)
    if source is None:
        return [*lines, f"- 원천을 읽지 못함 — {session._source_failure}", ""]
    reqb = source.tables.get("RQ_REQB", pd.DataFrame()).copy()
    lines.extend([f"- {source.dataset_label}", ""])
    if reqb.empty:
        return [*lines, "- 리비전 1 의 `RQ_REQB` 가 비어 있다", ""]
    reqb["소요기준"] = normalize_demand_basis(reqb["소요기준"]).fillna("")
    reqb["공정"] = reqb["공정"].astype("string").str.strip()
    reqb["Area_Name"] = reqb["Area_Name"].astype("string").str.strip()
    reqb["WF 구분"] = reqb["WF 구분"].astype("string").str.strip().str.upper()

    rows: list[list[str]] = []
    for basis in KNOWN_BASES:
        part = reqb.loc[reqb["소요기준"].eq(basis)]
        divisions = part.dropna(subset=["WF 구분"]).groupby("공정")["WF 구분"]
        single = divisions.nunique().eq(1)
        buffer_only = single & divisions.first().eq(BUFFER_DIVISION)
        area_counts = [
            int(part.loc[part["Area_Name"].str.casefold().eq(area.casefold()), "공정"].nunique())
            for area in AREA_NAMES
        ]
        rows.append(
            [
                basis,
                _count(len(part)),
                _count(part["공정"].nunique()),
                *[_count(count) for count in area_counts],
                _count(int(single.sum())),
                _count(int(buffer_only.sum())),
            ]
        )
    others = reqb.loc[~reqb["소요기준"].isin(KNOWN_BASES)]
    lines.extend(
        [
            *_table(
                [
                    "소요기준",
                    "행",
                    "공정",
                    *[f"{area} 공정" for area in AREA_NAMES],
                    "WF 구분이 하나뿐인 공정",
                    "그 하나가 BUFFER",
                ],
                rows,
            ),
            "",
        ]
    )
    bases_per_process = reqb.groupby("공정")["소요기준"].nunique()
    lines.append(
        f"- 그 밖의 소요기준 {others['소요기준'].nunique():,}종 {len(others):,}행 "
        f"{others['공정'].nunique():,}공정(값은 적지 않는다)"
    )
    lines.append(
        f"- 공정 {reqb['공정'].nunique():,}개 가운데 소요기준이 둘 이상인 공정 "
        f"{int(bases_per_process.gt(1).sum()):,} (업무 규칙상 0 이어야 한다)"
    )
    lines.append("")
    return lines


# ---------------------------------------------------------------------------------- 8-4 equipment


def check_equipment(session: Session) -> list[str]:
    lines = _heading("8-4", "설비 DB — 옛 Qual 자리표·환산비 0.2·일정 미정·사용기준", "equipment")
    connection = session.equipment
    if connection is None:
        return [*lines, f"- 설비 DB — {session.equipment_failure}", ""]
    latest = _latest_equipment_revision(connection)
    if latest is None:
        return [*lines, "- 설비 리비전이 없다(저장한 적이 없다)", ""]
    revision_id, revision_no, contract = latest
    lines.append(f"- 최신 설비 리비전 r{revision_no} · 계약 v{contract}")
    if contract < 3:
        lines.extend(
            [
                "- 최신 리비전이 옛 계약(v2)이라 설비 마스터 표가 없다 — "
                "이 절의 수는 모두 0 이 정상",
                "",
            ]
        )
    rows: list[list[str]] = []
    placeholder = f"DATE '{LEGACY_QUAL_PLACEHOLDER}'"
    master = "equipment_ops.equipment_master_snapshot"
    for label, sql, params in (
        (
            "최신 리비전 설비 마스터 행",
            f"SELECT count(*) FROM {master} WHERE revision_id = ?",
            [revision_id],
        ),
        (
            f"Qual일정 = {LEGACY_QUAL_PLACEHOLDER} (최신 리비전, 이제 빈 Qual 로 읽음)",
            f"SELECT count(*) FROM {master} WHERE revision_id = ? AND qual_date = {placeholder}",
            [revision_id],
        ),
        (
            f"Qual일정 = {LEGACY_QUAL_PLACEHOLDER} (모든 리비전 합)",
            f"SELECT count(*) FROM {master} WHERE qual_date = {placeholder}",
            [],
        ),
        (
            f"Qual일정 = {LEGACY_QUAL_PLACEHOLDER} 이 든 리비전",
            f"SELECT count(DISTINCT revision_id) FROM {master} WHERE qual_date = {placeholder}",
            [],
        ),
    ):
        rows.append([label, _safe_scalar(connection, sql, params)])

    module = "nullif(trim(parent_equipment_id), '') IS NOT NULL"
    ratio_is = "abs(conversion_ratio - {value}) < 1e-9"
    for label, condition in (
        ("모듈 행(Main 설비 있음)", module),
        (f"모듈 행 환산비 {MODULE_RATIO}", f"{module} AND {ratio_is.format(value=MODULE_RATIO)}"),
        (
            f"**모듈 행 환산비 {TRUNCATED_RATIO}** — 다시 입력할 행",
            f"{module} AND {ratio_is.format(value=TRUNCATED_RATIO)}",
        ),
        (
            f"Main 설비 없이 환산비 {TRUNCATED_RATIO} 인 행 (Main 설비 도입 전 모듈일 수 있음)",
            f"NOT ({module}) AND {ratio_is.format(value=TRUNCATED_RATIO)}",
        ),
    ):
        rows.append(
            [
                label,
                _safe_scalar(
                    connection,
                    f"SELECT count(*) FROM {master} WHERE revision_id = ? AND {condition}",
                    [revision_id],
                ),
            ]
        )
    rows.append(
        [
            "Main 설비 묶음 / 그 가운데 모듈 환산비 합이 1 이 아닌 묶음(±0.01)",
            _module_groups(connection, revision_id),
        ]
    )
    lines.extend(["", *_table(["항목", "수"], rows), ""])
    lines.extend(_undated_lines(session, connection, revision_id, contract))
    lines.append("")
    return lines


def _module_groups(connection: duckdb.DuckDBPyConnection, revision_id: str) -> str:
    try:
        groups, off = connection.execute(
            """
            SELECT count(*), count(*) FILTER (WHERE abs(total - 1.0) > 0.01)
            FROM (
                SELECT trim(parent_equipment_id) AS parent,
                       sum(coalesce(conversion_ratio, 1.0)) AS total
                FROM equipment_ops.equipment_master_snapshot
                WHERE revision_id = ? AND nullif(trim(parent_equipment_id), '') IS NOT NULL
                GROUP BY 1
            )
            """,
            [revision_id],
        ).fetchone() or (0, 0)
    except duckdb.Error as exc:
        return _failure(exc)
    return f"{int(groups or 0):,} / {int(off or 0):,}"


def _undated_lines(
    session: Session, connection: duckdb.DuckDBPyConnection, revision_id: str, contract: int
) -> list[str]:
    code_max = max((migration.version for migration in load_equipment_migrations()), default=0)
    db_max = max(_versions(connection, "equipment_meta.schema_migration") or [0])
    if db_max < code_max:
        return [
            f"- 일정 미정 — 건너뜀: 설비 DB 마이그레이션이 코드보다 낮다({db_max} < {code_max}). "
            "앱을 띄워 `가용설비 현황` 을 연 뒤 앱을 끄고 다시 돌린다(4-2)."
        ]
    try:
        snapshot = _read_snapshot(connection, revision_id)
        undated = undated_equipment(snapshot.equipment)
    except Exception as exc:  # 검증 오류 문구는 설비명을 싣는다. 종류만 적는다
        return [f"- 일정 미정 — {_failure(exc)}"]
    usage_line = _usage_basis_line(snapshot.equipment)
    counts = undated_counts(undated)
    rows_by_kind = {
        kind: int(undated[UNDATED_KIND_COLUMN].eq(kind).sum()) for kind in UNDATED_KINDS
    }
    parts = " · ".join(
        f"{kind} {format_unit_count(counts[kind])}대({rows_by_kind[kind]:,}행)"
        for kind in UNDATED_KINDS
    )
    placeholder_units = 0
    if contract >= 3:
        try:
            placeholder_ids = {
                str(row[0])
                for row in connection.execute(
                    "SELECT equipment_id FROM equipment_ops.equipment_master_snapshot "
                    f"WHERE revision_id = ? AND qual_date = DATE '{LEGACY_QUAL_PLACEHOLDER}'",
                    [revision_id],
                ).fetchall()
            }
        except duckdb.Error:
            placeholder_ids = set()
        qual_rows = undated.loc[undated[UNDATED_KIND_COLUMN].eq(UNDATED_KINDS[1])]
        placeholder_units = int(
            qual_rows[EQUIPMENT_ID_COLUMN].astype("string").isin(placeholder_ids).sum()
        )
    return [
        f"- 일정 미정(`services/undated_equipment.py`, 화면 알림과 같은 셈) — {parts}",
        f"- 그 가운데 Qual 미정 행이 옛 자리표 {LEGACY_QUAL_PLACEHOLDER} 에서 온 것 "
        f"{placeholder_units:,}행",
        usage_line,
    ]


def _usage_basis_line(equipment: pd.DataFrame) -> str:
    """세는 사용기준(HBM·EDP)마다의 행 수와 가용대수에서 빠지는 설비 대수.

    Dynamic 가용대수는 사용기준이 HBM·EDP 인 호기만 센다(2026-10-08 사용자 결정). 사용기준을 비워 둔
    옛 리비전은 그 결정으로 Dynamic 에서 빠지므로 배포마다 이 수를 받아 본다. 세는 값은 계약 상수라
    이름을 적고, 그 밖의 값(사용기준 글자)은 찍지 않고 `다른 값` 으로 접는다.
    """
    try:
        keys = usage_basis_key(equipment[USAGE_BASIS_COLUMN])
        by_basis = {
            basis: int(keys.eq(basis.strip().casefold()).fillna(False).astype(bool).sum())
            for basis in COUNTED_USAGE_BASIS
        }
        counted_rows = int(counts_for_capacity(equipment).sum())
        blank_rows = int(keys.isna().sum())
        excluded_units = usage_excluded_count(usage_excluded_equipment(equipment))
        total_units = int(unit_keys(equipment).nunique())
    except Exception as exc:  # 검증 오류 문구는 설비명을 싣는다. 종류만 적는다
        return f"- 사용기준 — {_failure(exc)}"
    other_rows = len(equipment) - counted_rows - blank_rows
    counted_parts = " · ".join(f"{basis} {rows:,}행" for basis, rows in by_basis.items())
    return (
        "- 사용기준(`equipment_contract.counts_for_capacity`, Dynamic 가용대수는 "
        f"{'·'.join(COUNTED_USAGE_BASIS)} 만 센다) — {counted_parts} · 다른 값 {other_rows:,}행 · "
        f"빈 칸 {blank_rows:,}행 / 가용대수에서 빠지는 설비 {format_unit_count(excluded_units)}대"
        f"(설비 {total_units:,}대 중)"
    )


# ---------------------------------------------------------------------------------- 8-5 bdq


class BigDataQueryProbe(Protocol):
    """이 스크립트가 BigDataQuery 에 묻는 다섯 가지. 테스트는 가짜를 넘긴다."""

    def catalog(self, window: QueryWindow) -> pd.DataFrame: ...

    def detail_rows(self, code: str, window: QueryWindow) -> int: ...

    def detail_frame(self, code: str, window: QueryWindow) -> pd.DataFrame: ...

    def load_days(self, code: str, window: QueryWindow) -> pd.DataFrame: ...

    def code_load_days(self, window: QueryWindow) -> pd.DataFrame: ...


class CompanyProbe:
    """사내 `bigdataquery` 패키지로 묻는다. 상세는 앱과 같은 SQL(`QUERY_TEMPLATE`)이다."""

    def __init__(self) -> None:
        self._module = cast(BigDataQueryModule, load_bigdataquery_module())

    def _frame(self, sql: str) -> pd.DataFrame:
        frame = call_get_data(self._module, sql)
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("getData 반환값이 DataFrame 이 아니다")
        return frame

    def catalog(self, window: QueryWindow) -> pd.DataFrame:
        return fetch_simulation_catalog(window)

    def detail_rows(self, code: str, window: QueryWindow) -> int:
        return int(len(self.detail_frame(code, window)))

    def detail_frame(self, code: str, window: QueryWindow) -> pd.DataFrame:
        return self._frame(build_query(QUERY_TEMPLATE, code, window=window))

    def load_days(self, code: str, window: QueryWindow) -> pd.DataFrame:
        if not is_valid_simulation_code(code):
            raise ValueError("시뮬레이션 코드 규칙 위반")
        start, end = window.sql_bounds()
        sql = LOAD_DAYS_QUERY_TEMPLATE.format(simulation_code=code, start_date=start, end_date=end)
        return self._frame(sql)

    def code_load_days(self, window: QueryWindow) -> pd.DataFrame:
        start, end = window.sql_bounds()
        return self._frame(CODE_LOAD_DAYS_QUERY_TEMPLATE.format(start_date=start, end_date=end))


def _bdq_failure(exc: BaseException) -> str:
    """우리 어댑터가 낸 안내만 뜻으로 옮긴다. 원문은 찍지 않는다."""
    text = str(exc)
    if isinstance(exc, RuntimeError) and BDQ_USER_NAME_ENV in text:
        return f"요청자 계정 필요 — `{BDQ_USER_NAME_ENV}` 를 넣고 새 셸에서 다시(런북 8-0)"
    if isinstance(exc, RuntimeError) and "패키지가 없습니다" in text:
        return "`bigdataquery` 패키지 없음"
    if isinstance(exc, RuntimeError) and "설정되지 않았습니다" in text:
        return "SQL 미설정"
    if isinstance(exc, ValueError) and "계약 별칭" in text:
        return "목록 결과에 계약 별칭 5개가 없다"
    return f"조회 실패({type(exc).__name__})"


@dataclass
class CatalogRun:
    label: str
    window: QueryWindow
    frame: pd.DataFrame | None = None
    seconds: float | None = None
    failure: str | None = None


def _run_catalog(probe: BigDataQueryProbe, label: str, window: QueryWindow) -> CatalogRun:
    started = time.perf_counter()
    try:
        frame = probe.catalog(window)
    except Exception as exc:  # 사내 패키지 예외 종류를 모른다
        return CatalogRun(label=label, window=window, failure=_bdq_failure(exc))
    return CatalogRun(
        label=label, window=window, frame=frame, seconds=time.perf_counter() - started
    )


def _catalog_row(run: CatalogRun) -> list[str]:
    if run.frame is None:
        return [run.label, f"{run.window.days}일", run.failure or "-", "-", "-", "-", "-", "-"]
    frame = run.frame
    try:
        normalized = normalize_catalog(frame)
        codes = frame["simulation_code"].astype("string").str.strip().nunique()
    except Exception as exc:  # 계약 별칭이 빠진 결과
        return [run.label, f"{run.window.days}일", _failure(exc), "-", "-", "-", "-", "-"]
    return [
        run.label,
        f"{run.window.days}일",
        "성공",
        _seconds(run.seconds),
        _count(len(frame)),
        _count(len(normalized)),
        _count(int(codes)),
        "넘음" if len(normalized) > CATALOG_BUSY_ROWS else "아니오",
    ]


def _value_shape(value: object) -> str:
    """값의 꼴만 — 숫자는 9, 영문은 A, 그 밖의 글자는 ? 로 바꾸고 기호·공백은 남긴다."""
    text = str(value)[:40]
    return "".join(
        "9"
        if char.isdigit()
        else "A"
        if char.isascii() and char.isalpha()
        else char
        if char.isascii()
        else "?"
        for char in text
    )


def describe_registered_at(values: pd.Series) -> list[str]:
    """`reg_date`(목록의 `regist_data`) 의 dtype·종류·꼴. 값은 찍지 않는다."""
    lines = [
        f"- `reg_date` dtype `{values.dtype}` · 빈 값 {int(values.isna().sum()):,} / "
        f"{len(values):,}"
    ]
    kinds: dict[str, int] = {}
    digits: dict[int, int] = {}
    shapes: dict[str, int] = {}
    with_time = 0
    with_zone = 0
    for value in values.dropna():
        if isinstance(value, bool):
            kind = "bool"
        elif isinstance(value, (int, float, np.integer, np.floating)):
            kind = "숫자"
            number = float(value)
            if math.isfinite(number):
                width = len(str(int(abs(number))))
                digits[width] = digits.get(width, 0) + 1
        elif isinstance(value, datetime):
            kind = "날짜시각"
            stamp = pd.Timestamp(value)
            with_time += int(stamp != stamp.normalize())
            with_zone += int(stamp.tzinfo is not None)
        elif isinstance(value, date):
            kind = "날짜"
        elif isinstance(value, str):
            kind = "문자열"
            shape = _value_shape(value.strip())
            shapes[shape] = shapes.get(shape, 0) + 1
        else:
            kind = type(value).__name__
        kinds[kind] = kinds.get(kind, 0) + 1
    lines.append(
        "- 값의 종류 — " + (" · ".join(f"{kind} {count:,}" for kind, count in kinds.items()) or "-")
    )
    if digits:
        lines.append(
            "- 숫자 자릿수 — "
            + " · ".join(f"{width}자리 {count:,}" for width, count in sorted(digits.items()))
            + " (8 = YYYYMMDD · 14 = YYYYMMDDHHMMSS · 10/13 = 에폭 초/밀리초 · 19 = 나노초)"
        )
    if kinds.get("날짜시각"):
        lines.append(
            f"- 날짜시각 가운데 시각이 0 시가 아닌 값 {with_time:,} · "
            f"시간대가 붙은 값 {with_zone:,}"
        )
    if shapes:
        top = sorted(shapes.items(), key=lambda item: (-item[1], item[0]))[:5]
        lines.append(
            "- 문자열 꼴(상위 5) — " + " · ".join(f"`{shape}` {count:,}" for shape, count in top)
        )
    unreadable = sum(1 for value in values.dropna() if not format_registered_at(value))
    lines.append(
        f"- 원천 등록시각으로 읽지 못하는 값 {unreadable:,} "
        "(저장 시 빈 원천 등록시점이 된다 — 숫자는 "
        "1970 년으로 읽히는 것을 막으려고 일부러 버린다)"
    )
    return lines


def describe_codes(codes: pd.Series) -> str:
    """`catb_sim_info_id` 규칙 위반 수와 까닭의 종류. 코드는 찍지 않는다.

    세는 일은 파이썬으로 한다 — pandas 2.2 는 문자열 Series 에 `.map` 을 걸면 참/거짓도
    문자열로 돌려줘 `.sum()` 이 `Cannot perform reduction 'sum' with string dtype` 으로 죽었다
    (사내 리뷰 202610070927·202610071831 의 8-5). 판올림마다 갈리는 dtype 추론에 기대지 않는다.
    """
    distinct = [str(code) for code in codes.astype("string").fillna("").unique()]
    invalid = [code for code in distinct if not is_valid_simulation_code(code)]
    empty = sum(1 for code in invalid if not code.strip())
    spaced = sum(1 for code in invalid if re.search(r"\s", code.strip()))
    non_ascii = sum(1 for code in invalid if not code.isascii())
    others = len(invalid) - empty - spaced - non_ascii
    return (
        f"- `catb_sim_info_id` 규칙(`{_CODE_RULE}`) 위반 — 코드 {len(distinct):,}개 중 "
        f"{len(invalid):,}개 (빈 값 {empty:,} · 가운데 공백 {spaced:,} · 비ASCII {non_ascii:,} · "
        f"그 밖 {max(others, 0):,}, 겹쳐 셀 수 있다)"
    )


@dataclass
class SampleResult:
    default_rows: int | None = None
    wide_rows: int | None = None
    default_seconds: float | None = None
    wide_seconds: float | None = None
    failure: str | None = None
    load_days: pd.DataFrame | None = None
    load_failure: str | None = None
    first_registered: date | None = None
    last_registered: date | None = None
    default_window: QueryWindow | None = None
    wide_window: QueryWindow | None = None


def _pick_evenly(items: Sequence[_Picked], count: int) -> list[_Picked]:
    if count <= 0 or not items:
        return []
    if count >= len(items):
        return list(items)
    if count == 1:
        return [items[len(items) // 2]]
    picks = [items[round(index * (len(items) - 1) / (count - 1))] for index in range(count)]
    return list(dict.fromkeys(picks))


def _timed(
    call: Callable[[str, QueryWindow], int], code: str, window: QueryWindow
) -> tuple[int, float]:
    started = time.perf_counter()
    value = call(code, window)
    return value, time.perf_counter() - started


def _sample_codes(
    probe: BigDataQueryProbe,
    frame: pd.DataFrame,
    *,
    sample: int,
    margin_days: int,
    today: date,
) -> tuple[list[str], dict[str, SampleResult], int, int]:
    """(표본 코드, 결과, 규칙을 지키는 코드 수, 등록일을 읽은 코드 수)."""
    normalized = normalize_catalog(frame)
    first = first_registration_dates(frame)
    spans: dict[str, tuple[date, date]] = {}
    valid = [
        code
        for code in normalized["simulation_code"].drop_duplicates()
        if is_valid_simulation_code(str(code))
    ]
    for code in valid:
        span = code_registration_span(normalized, first, str(code))
        if span is not None:
            spans[str(code)] = span
    ordered = sorted(spans, key=lambda code: (spans[code][0], spans[code][1], code))
    picked = _pick_evenly(ordered, sample)
    margin = max(margin_days, DETAIL_WINDOW_DAYS_BEFORE, DETAIL_WINDOW_DAYS_AFTER)
    results: dict[str, SampleResult] = {}
    probe_days = True
    for code in picked:
        earliest, latest = spans[code]
        default = registration_detail_window(earliest, latest, today=today)
        wide_end = max(default.end_date, min(latest + timedelta(days=margin), today))
        wide = QueryWindow(start_date=earliest - timedelta(days=margin), end_date=wide_end)
        result = SampleResult(
            first_registered=earliest,
            last_registered=latest,
            default_window=default,
            wide_window=wide,
        )
        try:
            result.default_rows, result.default_seconds = _timed(probe.detail_rows, code, default)
            result.wide_rows, result.wide_seconds = _timed(probe.detail_rows, code, wide)
        except Exception as exc:  # 사내 패키지 예외 종류를 모른다
            result.failure = _bdq_failure(exc)
        if probe_days:
            try:
                result.load_days = probe.load_days(code, wide)
            except Exception as exc:  # 새 SQL 이 사내 엔진에서 돌지 않을 수 있다
                result.load_failure = _bdq_failure(exc)
                probe_days = False
        results[code] = result
    return picked, results, len(valid), len(spans)


def _load_day_stats(results: Sequence[SampleResult]) -> list[list[str]]:
    probed = [result for result in results if result.load_days is not None]
    failures = [result.load_failure for result in results if result.load_failure]
    rows: list[list[str]] = [
        [
            "적재일 조회(`impala_insert_time` 날짜별 행 수, 사외에서 돌려 보지 못한 SQL)",
            f"{len(probed):,} / {len(results):,} 성공" + (f" · {failures[0]}" if failures else ""),
        ]
    ]
    if not probed:
        return rows
    spans: list[int] = []
    multi = 0
    outside = 0
    edge = 0
    unreadable = 0
    first_offsets: list[int] = []
    last_offsets: list[int] = []
    for result in probed:
        frame = cast(pd.DataFrame, result.load_days)
        if frame.empty or "load_day" not in frame.columns:
            continue
        days = pd.to_datetime(frame["load_day"].astype("string"), errors="coerce")
        unreadable += int(days.isna().sum())
        stamps = sorted({stamp.date() for stamp in days.dropna()})
        if not stamps:
            continue
        multi += int(len(stamps) > 1)
        spans.append((stamps[-1] - stamps[0]).days + 1)
        assert result.first_registered is not None and result.last_registered is not None
        first_offsets.append((stamps[0] - result.first_registered).days)
        last_offsets.append((stamps[-1] - result.last_registered).days)
        default = cast(QueryWindow, result.default_window)
        wide = cast(QueryWindow, result.wide_window)
        outside += int(any(day < default.start_date or day > default.end_date for day in stamps))
        edge += int(stamps[0] <= wide.start_date or stamps[-1] >= wide.end_date)
    median_span = float(np.median(spans)) if spans else None
    rows.extend(
        [
            ["여러 날에 나눠 적재된 코드", f"{multi:,} / {len(probed):,}"],
            [
                "적재일 폭(첫 적재일 ~ 끝 적재일, 일)",
                f"중앙 {_ratio(median_span)} · 최대 {_count(max(spans) if spans else None)}",
            ],
            [
                "첫 적재일 − 첫 원천 등록일(일)",
                f"최소 {_count(min(first_offsets)) if first_offsets else '-'} · 최대 "
                f"{_count(max(first_offsets)) if first_offsets else '-'}",
            ],
            [
                "끝 적재일 − 끝 원천 등록일(일)",
                f"최소 {_count(min(last_offsets)) if last_offsets else '-'} · 최대 "
                f"{_count(max(last_offsets)) if last_offsets else '-'}",
            ],
            [
                f"기본 창({_DEFAULT_WINDOW}) 밖 적재일이 있는 코드",
                f"{outside:,} / {len(probed):,}",
            ],
            ["넓은 창 첫날·끝날에 적재가 닿은 코드(창 밖에도 있을 수 있다)", f"{edge:,}"],
            ["날짜로 읽지 못한 적재일 값", f"{unreadable:,}"],
        ]
    )
    return rows


# -------------------------------------------------------- 8-5 전 코드 적재일 · 여러 날 사본


def _as_day(value: object) -> date | None:
    """적재일 문자열(`YYYY-MM-DD…`)을 날짜로. 읽지 못하면 `None`."""
    if value is None:
        return None
    try:
        stamp = pd.Timestamp(str(value)[:10])
    except (TypeError, ValueError):
        return None
    if pd.isna(stamp):
        return None
    return stamp.date()


@dataclass(frozen=True)
class LoadSpan:
    """코드 하나의 적재 — 목록 창 안에서 서로 다른 적재일 수, 첫·끝 적재일, 행 수."""

    days: int
    first: date
    last: date
    rows: int

    @property
    def width(self) -> int:
        return (self.last - self.first).days + 1


@dataclass
class CodeLoadDays:
    """전 코드 적재일 조회. `spans` 는 규칙을 지키고 적재일을 읽은 코드뿐이며 코드는 찍지 않는다."""

    window: QueryWindow
    spans: dict[str, LoadSpan] = field(default_factory=dict)
    codes: int = 0
    invalid: int = 0
    unreadable: int = 0
    seconds: float | None = None
    failure: str | None = None


def parse_code_load_days(frame: pd.DataFrame, window: QueryWindow) -> CodeLoadDays:
    """`CODE_LOAD_DAYS_QUERY_TEMPLATE` 결과를 코드별 `LoadSpan` 으로. 나머지는 수만 센다."""
    result = CodeLoadDays(window=window)
    codes = frame["simulation_code"].astype("string").str.strip().fillna("")
    days = pd.to_numeric(frame["load_days"], errors="coerce")
    rows = pd.to_numeric(frame["row_count"], errors="coerce")
    result.codes = int(codes.nunique())
    for code, count, first, last, size in zip(
        codes, days, frame["first_day"], frame["last_day"], rows, strict=True
    ):
        text = str(code)
        if not is_valid_simulation_code(text):
            result.invalid += 1
            continue
        first_day, last_day = _as_day(first), _as_day(last)
        if first_day is None or last_day is None or pd.isna(count) or pd.isna(size):
            result.unreadable += 1
            continue
        result.spans.setdefault(
            text, LoadSpan(days=int(count), first=first_day, last=last_day, rows=int(size))
        )
    return result


def _run_code_load_days(probe: BigDataQueryProbe, window: QueryWindow) -> CodeLoadDays:
    started = time.perf_counter()
    try:
        frame = probe.code_load_days(window)
        result = parse_code_load_days(frame, window)
    except Exception as exc:  # 새 SQL 이 사내 엔진에서 돌지 않을 수 있다
        return CodeLoadDays(window=window, failure=_bdq_failure(exc))
    result.seconds = time.perf_counter() - started
    return result


def _spread(values: Sequence[float]) -> str:
    if not values:
        return "-"
    ordered = np.asarray(values, dtype="float64")
    return (
        f"중앙 {_ratio(float(np.median(ordered)))} · p95 "
        f"{_ratio(float(np.quantile(ordered, 0.95)))} · 최대 {_ratio(float(ordered.max()))}"
    )


def _code_load_day_rows(loads: CodeLoadDays) -> list[list[str]]:
    label = (
        f"조회(목록 창 {loads.window.days}일 전체를 GROUP BY 한 번, 사외에서 돌려 보지 못한 SQL)"
    )
    if loads.failure is not None:
        return [[label, loads.failure]]
    spans = list(loads.spans.values())
    multi = [span for span in spans if span.days > 1]
    total_rows = sum(span.rows for span in spans)
    multi_rows = sum(span.rows for span in multi)
    coverage = [span.days / span.width for span in multi]
    at_end = sum(1 for span in multi if span.last >= loads.window.end_date)
    one = sum(1 for span in spans if span.days == 1)
    few = sum(1 for span in spans if 2 <= span.days <= 5)
    many = sum(1 for span in spans if span.days >= 6)
    return [
        [label, f"성공 · {_seconds(loads.seconds)}초"],
        [
            "코드",
            f"규칙을 지키고 적재일을 읽은 코드 {len(spans):,} (결과 코드 {loads.codes:,} · "
            f"규칙 위반 {loads.invalid:,} · 적재일을 읽지 못함 {loads.unreadable:,})",
        ],
        ["적재일 1일 · 2–5일 · 6일 이상", f"{one:,} · {few:,} · {many:,}"],
        ["적재일 폭(첫 ~ 끝 적재일, 일) — 전체", _spread([span.width for span in spans])],
        ["적재일 폭 — 여러 날 코드", _spread([span.width for span in multi])],
        [
            "여러 날 코드의 적재일 수 ÷ 폭(1 이면 하루도 빠짐없이 적재)",
            "-"
            if not coverage
            else f"중앙 {_ratio(float(np.median(coverage)))} · 최소 {_ratio(min(coverage))}",
        ],
        [
            "여러 날 코드가 차지하는 행",
            f"전체의 {_percent(multi_rows / total_rows if total_rows else None, 2)}",
        ],
        [
            "여러 날 코드 가운데 끝 적재일이 목록 창 끝날(오늘)인 코드",
            f"{at_end:,} / {len(multi):,}",
        ],
    ]


def _day_rows(frame: pd.DataFrame | None) -> dict[date, int]:
    """적재일 조회 결과 → 날마다 행 수. 날짜로 읽지 못한 값은 뺀다."""
    if frame is None or frame.empty or "load_day" not in frame.columns:
        return {}
    counts = (
        pd.to_numeric(frame["row_count"], errors="coerce")
        if "row_count" in frame.columns
        else pd.Series(np.nan, index=frame.index)
    )
    result: dict[date, int] = {}
    for value, count in zip(frame["load_day"], counts, strict=True):
        day = _as_day(value)
        if day is not None:
            result[day] = result.get(day, 0) + (0 if pd.isna(count) else int(count))
    return result


_EMPTY: Final = "\x00"


def canonical_values(values: pd.Series) -> pd.Series:
    """한 칸의 값을 견주기 꼴로 — 숫자로 읽히면 실수 글자로, 아니면 앞뒤 공백을 뗀 글자로.

    날마다 같은 칸이 정수·실수·숫자 글자·빈 글자 섞인 `object`·참거짓으로 갈려 와도 같은
    값이 같은 꼴이 되게 한다(빈 글자는 빈 값, 참·거짓은 1·0). 값마다 따로 읽으므로 같은 칸의
    다른 값에 기대지 않는다.
    """
    if pd.api.types.is_bool_dtype(values):
        return values.astype("Float64").astype("string").fillna(_EMPTY)
    text = values.astype("string").str.strip()
    text = text.mask(text.eq("").fillna(False).astype(bool)).replace({"True": "1", "False": "0"})
    numeric = pd.to_numeric(text, errors="coerce")
    canonical = numeric.astype("Float64").astype("string")
    return canonical.where(numeric.notna(), text).fillna(_EMPTY)


def row_signatures(frame: pd.DataFrame) -> pd.Series:
    """행마다 내용 해시 — 모든 칸이 같아야 같은 행이다(적재 시각은 상세 SQL 에 없다).

    칸마다 `canonical_values` 를 거친 뒤 해시한다. 날마다 갈리는 dtype 추론으로 같은 행이
    「값이 바뀐 행」으로 헛보이지 않게 한다. 해시만 남기고 값은 버린다.
    """
    names = sorted(dict.fromkeys(str(name) for name in frame.columns))
    if not names:
        return pd.Series(np.zeros(len(frame), dtype="uint64"), index=frame.index)
    unique = frame.loc[:, ~frame.columns.duplicated()]
    unique.columns = [str(name) for name in unique.columns]
    columns = {name: canonical_values(unique[name]) for name in names}
    return pd.util.hash_pandas_object(pd.DataFrame(columns, index=frame.index), index=False)


KeySet = frozenset[tuple[str, ...]]
# 경로 키 13 — `RQ_REQB` 업무 키. `양산구분` 은 `CS` 에서 나오는 파생 칸이라 원천에 없고 빼도
# 수가 같다.
ROUTE_KEY_COLUMNS: Final[tuple[str, ...]] = tuple(key for key in REQB_COLUMNS if key != "양산구분")


def _key_tuples(frame: pd.DataFrame, keys: Sequence[str]) -> KeySet:
    canonical = pd.DataFrame({key: canonical_values(frame[key]) for key in keys}, index=frame.index)
    return frozenset(tuple(str(value) for value in row) for row in canonical.to_numpy().tolist())


def _renamed(frame: pd.DataFrame) -> pd.DataFrame:
    """칸 이름을 앱처럼 `SOURCE_COLUMN_MAPPING` 으로 맞춘다(엔진이 별칭을 소문자로 돌려줄 때)."""
    renamed = frame.rename(columns=dict(SOURCE_COLUMN_MAPPING))
    return renamed.loc[:, ~renamed.columns.duplicated()]


def plan_line_key_set(frame: pd.DataFrame) -> KeySet | None:
    """상세 조회 결과의 계획 줄 업무 키(`RQ_PKG_PLAN` 업무 키). 칸이 모자라면 `None`.

    `양산구분` 은 `CS` 에서 나오는 파생 칸이라 원천에 없고 빼도 키 수가 같다.
    """
    renamed = _renamed(frame)
    keys = [
        key for key in load_core_data_contract().derived_keys["RQ_PKG_PLAN"] if key != "양산구분"
    ]
    if any(key not in renamed.columns for key in keys):
        return None
    return _key_tuples(renamed, keys)


def route_key_set(frame: pd.DataFrame) -> KeySet | None:
    """상세 조회 결과의 경로 키 13(`ROUTE_KEY_COLUMNS`). `공정` 이 없으면 `None`.

    상세 SQL 은 열셋을 모두 돌려준다. 일부가 빠진 결과면 있는 칸만으로 센다(`공정` 은 꼭
    있어야 한다).
    """
    renamed = _renamed(frame)
    if "공정" not in renamed.columns:
        return None
    return _key_tuples(renamed, [key for key in ROUTE_KEY_COLUMNS if key in renamed.columns])


@dataclass(frozen=True)
class DayLoad:
    """적재일 하루치 — 행 수, 행 서명의 중복 수, 계획 줄 키, 경로 키. 값은 담지 않는다."""

    day: date
    rows: int
    counts: Counter[int]
    plan_keys: KeySet | None
    route_keys: KeySet | None

    @property
    def row_set(self) -> set[int]:
        return set(self.counts)


def day_load(day: date, frame: pd.DataFrame) -> DayLoad:
    renamed = _renamed(frame)
    counts = Counter(int(value) for value in row_signatures(renamed).tolist())
    return DayLoad(
        day=day,
        rows=len(renamed),
        counts=counts,
        plan_keys=plan_line_key_set(renamed) if len(renamed) else None,
        route_keys=route_key_set(renamed) if len(renamed) else None,
    )


# 앞 날이 기준 날(마지막 적재일)과 어떤 사이인가. 판정 칸과 런북 8-5 판정표가 이 이름을 쓴다.
SAME_DAY: Final = "같음"
SUBSET_DAY: Final = "⊆"
SUPERSET_DAY: Final = "⊇"
CHANGED_DAY: Final = "값 바뀜"
ROUTE_SPLIT_DAY: Final = "경로 나눠"
PLAN_SPLIT_DAY: Final = "계획 줄 나눠"
UNDECIDED_DAY: Final = "가를 수 없음"


def _nested(left: KeySet, right: KeySet) -> bool:
    return left <= right or left >= right


def day_relation(day: DayLoad, reference: DayLoad) -> str:
    """하루치를 기준 날과 견준다 — 행 집합이 같다·안에 든다·감싼다, 아니면 키로 가른다.

    행 집합이 서로 안에 들지 않으면 키로 가른다 — 계획 줄 키 집합도 서로 안에 들지 않으면
    「계획 줄 나눠」(날마다 다른 계획 줄을 실었다), 경로 키 집합이 서로 안에 들면 「값 바뀜」
    (같은 경로의 값이 바뀌었다), 그 밖은 「경로 나눠」(같은 계획 줄의 다른 경로를 실었다).
    경로 키를 셀 수 없으면 「가를 수 없음」.
    """
    rows, base = day.row_set, reference.row_set
    if rows == base:
        return SAME_DAY
    if rows < base:
        return SUBSET_DAY
    if rows > base:
        return SUPERSET_DAY
    if (
        day.plan_keys is not None
        and reference.plan_keys is not None
        and not _nested(day.plan_keys, reference.plan_keys)
    ):
        return PLAN_SPLIT_DAY
    if day.route_keys is None or reference.route_keys is None:
        return UNDECIDED_DAY
    if _nested(day.route_keys, reference.route_keys):
        return CHANGED_DAY
    return ROUTE_SPLIT_DAY


# 판정 칸의 이름 — 런북 8-5 판정표의 줄과 같다.
COPY_VERDICTS: Final[tuple[tuple[str, str], ...]] = (
    (SUBSET_DAY, "누적 적재"),
    (SUPERSET_DAY, "뒤 적재에서 지워짐"),
    (CHANGED_DAY, "같은 키 값 바뀜"),
    (ROUTE_SPLIT_DAY, "경로 나눠 적재"),
    (PLAN_SPLIT_DAY, "계획 줄 나눠 적재"),
    (UNDECIDED_DAY, "가를 수 없음"),
)


@dataclass
class CopyCheck:
    """여러 날 적재된 코드 하나 — 앞 날들이 기준 날(마지막 적재일)과 어떤 사이인가. 코드는 없다."""

    extra: bool
    load_days: int = 0
    day_rows: tuple[int, ...] = ()
    examined: int = 0
    empty_days: int = 0
    reference: str = ""
    relations: Counter[str] = field(default_factory=Counter)
    same_counts: int = 0
    rows: int = 0
    distinct_rows: int = 0
    plan_keys: int | None = None
    reference_plan_keys: int | None = None
    route_keys: int | None = None
    reference_route_keys: int | None = None
    missing_from_reference: int = 0
    failure: str | None = None

    @property
    def compared(self) -> int:
        return sum(self.relations.values())

    def verdict(self) -> str:
        if self.compared == 0:
            return "견줄 날 없음"
        kinds = [name for relation, name in COPY_VERDICTS if self.relations[relation]]
        if not kinds:
            return "통째 사본"
        return kinds[0] if len(kinds) == 1 else "섞임: " + " · ".join(kinds)


def _union_size(sets: Sequence[KeySet | None]) -> int | None:
    if any(keys is None for keys in sets):
        return None
    return len(frozenset[tuple[str, ...]]().union(*cast(Sequence[KeySet], sets)))


def _reference_label(
    picked_last: date,
    reference: DayLoad,
    in_progress: DayLoad | None,
    window: QueryWindow,
    *,
    bounded: bool,
) -> str:
    if in_progress is not None:
        states = {
            SAME_DAY: "기준 날과 같음",
            SUBSET_DAY: "기준 날의 일부(⊆)",
            SUPERSET_DAY: "기준 날을 감쌈(⊇)",
        }
        relation = day_relation(in_progress, reference) if in_progress.rows else ""
        state = "0행" if not in_progress.rows else states.get(relation, relation)
        return f"끝 앞날 — 끝 날은 오늘이라 적재 중일 수 있어 뺐다(오늘은 {state})"
    if reference.day != picked_last:
        return "끝 앞날 — 끝 날이 0행"
    if not bounded and reference.day >= window.end_date:
        return "끝 적재일 — 창 끝날에 닿음(창 밖에도 있을 수 있다)"
    return "끝 적재일"


def check_copies(
    probe: BigDataQueryProbe,
    code: str,
    window: QueryWindow,
    *,
    extra: bool,
    today: date | None = None,
    bounded: bool = True,
    max_days: int = DEFAULT_COPY_DAYS,
) -> CopyCheck:
    """`window` 안의 적재일을 세고 첫 적재일·가운데·끝 앞날·끝 날을 하루씩 받아 견준다.

    하루치는 앱과 같은 상세 SQL 을 그날 하루 창으로 부른 것이다 — 상세 SQL 이 적재 시각으로만
    거르므로 그 창이 곧 그날 적재분이다. 기준 날은 끝 적재일이다. 끝 날이 `today` 면 아직 적재
    중일 수 있어 그 앞날을 기준으로 삼고, 0행인 날은 따로 세고 견주지 않는다. `bounded` 가
    아니면(전 코드 조회가 없어 등록일 창으로 셌으면) 끝 적재일이 창 끝날에 닿을 때 그렇게 적는다.
    """
    result = CopyCheck(extra=extra)
    try:
        by_day = _day_rows(probe.load_days(code, window))
    except Exception as exc:  # 사내 패키지 예외 종류를 모른다
        result.failure = _bdq_failure(exc)
        return result
    days = sorted(by_day)
    result.load_days = len(days)
    result.day_rows = tuple(by_day[day] for day in days)
    if len(days) < 2:
        return result
    picked = [*_pick_evenly(days[:-1], max(max_days, 2) - 1), days[-1]]
    loads: list[DayLoad] = []
    try:
        for day in picked:
            frame = probe.detail_frame(code, QueryWindow(start_date=day, end_date=day))
            loads.append(day_load(day, frame))
    except Exception as exc:  # 사내 패키지 예외 종류를 모른다
        result.failure = _bdq_failure(exc)
        return result
    result.examined = len(loads)
    result.empty_days = sum(1 for load in loads if load.rows == 0)
    in_progress = loads[-1] if today is not None and picked[-1] >= today else None
    candidates = [load for load in loads if load.rows > 0 and load is not in_progress]
    if not candidates:
        result.reference = "0행뿐"
        return result
    reference = candidates[-1]
    compared = candidates[:-1]
    result.reference = _reference_label(picked[-1], reference, in_progress, window, bounded=bounded)
    result.relations = Counter(day_relation(load, reference) for load in compared)
    result.same_counts = sum(1 for load in compared if load.counts == reference.counts)
    seen = set[int]().union(*(load.row_set for load in candidates))
    result.rows = sum(load.rows for load in candidates)
    result.distinct_rows = len(seen)
    result.missing_from_reference = len(seen - reference.row_set)
    result.plan_keys = _union_size([load.plan_keys for load in candidates])
    result.route_keys = _union_size([load.route_keys for load in candidates])
    result.reference_plan_keys = _union_size([reference.plan_keys])
    result.reference_route_keys = _union_size([reference.route_keys])
    return result


@dataclass(frozen=True)
class CopyTarget:
    code: str
    extra: bool
    window: QueryWindow
    bounded: bool


def _copy_targets(
    picked: Sequence[str],
    results: dict[str, SampleResult],
    loads: CodeLoadDays | None,
    *,
    max_codes: int = DEFAULT_COPY_CODES,
) -> list[CopyTarget]:
    """사본을 볼 코드 — 표본의 여러 날 코드(적재일이 많은 순)를 먼저, 모자라면 전 코드 조회의
    여러 날 코드에서 고르게 채워 모두 `max_codes` 개까지.

    창은 표본의 넓은 창에 전 코드 조회가 준 첫·끝 적재일을 더한 것이다 — 매일 다시 적재되는
    코드는 등록일 ±30 일 창 밖에서도 적재가 이어져, 그 창의 끝날을 「끝 적재일」로 잘못 보게
    된다. 전 코드 조회가 없으면 넓은 창만 쓰고 `bounded` 를 끈다.
    """
    if max_codes <= 0:
        return []
    spans = loads.spans if loads is not None else {}
    sampled: list[tuple[int, CopyTarget]] = []
    for code in picked:
        result = results[code]
        span = spans.get(code)
        days = span.days if span is not None else len(_day_rows(result.load_days))
        if days < 2 or result.wide_window is None:
            continue
        window = result.wide_window
        if span is not None:
            window = QueryWindow(
                start_date=min(window.start_date, span.first),
                end_date=max(window.end_date, span.last),
            )
        sampled.append((days, CopyTarget(code, False, window, span is not None)))
    sampled.sort(key=lambda item: -item[0])
    targets = [target for _, target in sampled[:max_codes]]
    chosen = set(picked)
    candidates = sorted(
        (code for code, span in spans.items() if span.days > 1 and code not in chosen),
        key=lambda code: (spans[code].days, spans[code].last, code),
    )
    for code in _pick_evenly(candidates, max_codes - len(targets)):
        span = spans[code]
        targets.append(
            CopyTarget(code, True, QueryWindow(start_date=span.first, end_date=span.last), True)
        )
    return targets


_COPY_HEADERS: Final = (
    "코드",
    "고른 길",
    "적재일",
    "날별 행 최소 · 중앙 · 최대",
    "기준 날",
    "견준 날(0행 날)",
    "본 날 행 → 고유 행",
    "계획 줄 키 전체 / 기준 날",
    "경로 키 전체 / 기준 날",
    "기준 날과 같은 날(중복 수까지 같은 날)",
    "⊆ 기준 · ⊇ 기준",
    "그 밖 — 값 바뀜 · 경로 나눠 · 계획 줄 나눠",
    "기준 날에 없는 고유 행",
    "판정",
)


def _copy_row(index: int, check: CopyCheck) -> list[str]:
    head = [str(index), "여러 날 코드 더함" if check.extra else "표본"]
    if check.failure is not None:
        return [*head, check.failure, *["-"] * (len(_COPY_HEADERS) - 3)]
    day_rows = (
        "-"
        if not check.day_rows
        else f"{min(check.day_rows):,} · {float(np.median(check.day_rows)):,.0f} · "
        f"{max(check.day_rows):,}"
    )
    if check.examined == 0:
        return [
            *head,
            _count(check.load_days),
            day_rows,
            *["-"] * (len(_COPY_HEADERS) - 5),
            "여러 날이 아님",
        ]
    relations = check.relations
    undecided = relations[UNDECIDED_DAY]
    return [
        *head,
        _count(check.load_days),
        day_rows,
        check.reference or "-",
        f"{check.compared:,} ({check.empty_days:,})",
        f"{check.rows:,} → {check.distinct_rows:,}",
        f"{_count(check.plan_keys)} / {_count(check.reference_plan_keys)}",
        f"{_count(check.route_keys)} / {_count(check.reference_route_keys)}",
        f"{relations[SAME_DAY]:,} ({check.same_counts:,})",
        f"{relations[SUBSET_DAY]:,} · {relations[SUPERSET_DAY]:,}",
        f"{relations[CHANGED_DAY]:,} · {relations[ROUTE_SPLIT_DAY]:,} · "
        f"{relations[PLAN_SPLIT_DAY]:,}" + (f" (가를 수 없음 {undecided:,})" if undecided else ""),
        _count(check.missing_from_reference),
        check.verdict(),
    ]


def _copy_parts(
    probe: BigDataQueryProbe,
    picked: Sequence[str],
    results: dict[str, SampleResult],
    loads: CodeLoadDays | None,
    *,
    today: date,
    max_codes: int,
    max_days: int,
) -> Iterator[list[str]]:
    """사본 표를 머리·코드마다 한 줄·꼬리로 나눠 내준다 — 끝난 줄은 바로 찍힌다."""
    days = max(max_days, 2)
    title = (
        "**여러 날 적재 — 날마다 사본인가** — 표본의 여러 날 코드(적재일이 많은 순)를 먼저, "
        "모자라면 "
        f"전 코드 조회의 여러 날 코드에서 고르게 채워 최대 {max_codes}개(코드는 찍지 않는다)를, 첫 "
        f"적재일·가운데·끝 앞날·끝 날 가운데 최대 {days}일을 앱과 같은 상세 SQL 로 하루씩 다시 "
        "받아 "
        "기준 날(끝 적재일)과 견준다. 모든 칸이 같아야 같은 행이다 — 적재 시각은 그 SQL 에 "
        "없고, 숫자로 "
        "읽히는 값은 숫자로 맞춘 뒤 견준다."
    )
    if max_codes <= 0 or max_days <= 0:
        yield [
            title,
            "",
            "- 사본 확인은 `--bdq-copy-codes 0` 또는 `--bdq-copy-days 0` 이라 껐다.",
            "",
        ]
        return
    if any(results[code].load_failure for code in picked):
        yield [title, "", "- 적재일 조회가 실패해 건너뛴다.", ""]
        return
    targets = _copy_targets(picked, results, loads, max_codes=max_codes)
    if not targets:
        yield [title, "", "- 여러 날 적재된 코드가 표본에도 전 코드 조회에도 없다.", ""]
        return
    yield [title, "", *_table(_COPY_HEADERS, [])]
    for index, target in enumerate(targets, start=1):
        check = check_copies(
            probe,
            target.code,
            target.window,
            extra=target.extra,
            today=today,
            bounded=target.bounded,
            max_days=days,
        )
        yield _table(_COPY_HEADERS, [_copy_row(index, check)])[2:]
    yield [
        "",
        "- 판정 칸은 런북 8-5 판정표의 이름이다. `기준 날과 같은 날` 이 `견준 날` 전부면 「통째 "
        "사본」 — "
        "기본 창이 놓친 행은 사본이다.",
        "",
    ]


def iter_bigdataquery(
    *,
    today: date,
    sample: int = DEFAULT_SAMPLE,
    margin_days: int = DEFAULT_MARGIN_DAYS,
    max_window: bool = True,
    code_days: bool = True,
    copy_codes: int = DEFAULT_COPY_CODES,
    copy_days: int = DEFAULT_COPY_DAYS,
    probe: BigDataQueryProbe | None = None,
) -> Iterator[list[str]]:
    """8-5 를 조각마다 내준다 — 부르는 쪽이 조각이 끝나는 대로 찍는다."""
    lines = _heading("8-5", "BigDataQuery — 목록·등록일·코드·적재일·사본", "bdq")
    account = (
        "있음" if resolve_user_name() else "없음(Windows 는 없어도 된다 — 로그인 이름으로 묻는다)"
    )
    if probe is None:
        if not is_bigdataquery_package_available():
            yield [
                *lines,
                "- `bigdataquery` 패키지가 없다 — 사외 PC 이거나 맨 `uv sync` 가 지웠다"
                "(4-1 의 되돌리기). "
                "이 절은 건너뛴다.",
                "",
            ]
            return
        if not (is_bigdataquery_catalog_configured() and is_bigdataquery_adapter_configured()):
            yield [*lines, "- 목록 또는 상세 SQL 이 설정되지 않았다 — 이 절은 건너뛴다.", ""]
            return
        try:
            probe = CompanyProbe()
        except Exception as exc:  # 패키지를 불러오다 실패
            yield [*lines, f"- 패키지를 불러오지 못함 — {_bdq_failure(exc)}", ""]
            return
    lines.extend(
        [f"- 준비 — 패키지 있음 · SQL 설정됨 · 요청자 계정(`{BDQ_USER_NAME_ENV}`) {account}", ""]
    )

    runs = [
        _run_catalog(
            probe,
            f"기본(오늘−{CATALOG_DEFAULT_DAYS}일 ~ 오늘)",
            QueryWindow(start_date=today - timedelta(days=CATALOG_DEFAULT_DAYS), end_date=today),
        )
    ]
    if max_window:
        runs.append(
            _run_catalog(
                probe,
                f"상한 {CATALOG_MAX_DAYS}일",
                QueryWindow(
                    start_date=today - timedelta(days=CATALOG_MAX_DAYS - 1), end_date=today
                ),
            )
        )
    lines.extend(
        [
            *_table(
                [
                    "목록 조회",
                    "기간",
                    "결과",
                    "초",
                    "목록 행(DISTINCT)",
                    "코드·PLAN",
                    "코드",
                    f"코드·PLAN {CATALOG_BUSY_ROWS:,} 넘음",
                ],
                [_catalog_row(run) for run in runs],
            ),
            "",
        ]
    )
    widest = next((run for run in reversed(runs) if run.frame is not None), None)
    if widest is None or widest.frame is None:
        yield [*lines, "- 목록 조회가 모두 실패해 나머지는 건너뛴다.", ""]
        return
    frame = widest.frame
    lines.append(f"- 아래는 `{widest.label}` 목록 기준")
    lines.extend(describe_registered_at(frame["regist_data"]))
    per_pair = (
        frame.assign(
            _code=frame["simulation_code"].astype("string").str.strip(),
            _plan=frame["plan_code"].astype("string").str.strip(),
            _at=[format_registered_at(value) for value in frame["regist_data"]],
        )
        .groupby(["_code", "_plan"], dropna=False)["_at"]
        .nunique()
    )
    if not per_pair.empty:
        lines.append(
            "- 코드·PLAN 하나의 서로 다른 등록시각 수 — "
            f"중앙 {_ratio(float(per_pair.median()))} · 최대 "
            f"{int(per_pair.max()):,} (1 보다 크면 `reg_date` 가 적재 단위 시각이다)"
        )
    lines.append(describe_codes(frame["simulation_code"]))
    lines.append("")
    yield lines

    loads: CodeLoadDays | None = None
    if code_days:
        loads = _run_code_load_days(probe, widest.window)
        yield [*_table(["전 코드 적재일", "값"], _code_load_day_rows(loads)), ""]
    else:
        yield ["- 전 코드 적재일 조회는 `--bdq-no-code-days` 라 건너뛰었다.", ""]

    if sample <= 0:
        yield ["- 표본 적재일 확인은 `--bdq-sample 0` 이라 건너뛰었다.", ""]
        return
    picked, results, valid, readable = _sample_codes(
        probe, frame, sample=sample, margin_days=margin_days, today=today
    )
    sampled = [results[code] for code in picked]
    measured = [r for r in sampled if r.default_rows is not None and r.wide_rows is not None]
    pairs = [
        (r.default_rows, r.wide_rows)
        for r in measured
        if r.default_rows is not None and r.wide_rows is not None
    ]
    same = sum(1 for narrow, wide in pairs if narrow == wide)
    missing = [(wide - narrow) / wide for narrow, wide in pairs if wide]
    total_wide = sum(wide for _, wide in pairs)
    total_missing = sum(wide - narrow for narrow, wide in pairs)
    detail_failures = [r.failure for r in sampled if r.failure]
    margin = max(margin_days, DETAIL_WINDOW_DAYS_BEFORE, DETAIL_WINDOW_DAYS_AFTER)

    def _seconds_spread(values: list[float]) -> str:
        if not values:
            return "-"
        return f"중앙 {_seconds(float(np.median(values)))} · 최대 {_seconds(max(values))}"

    rows: list[list[str]] = [
        [
            "표본",
            f"{len(picked):,} 코드 (규칙을 지키는 코드 {valid:,} · "
            f"등록일을 읽은 코드 {readable:,} 가운데 "
            "첫 등록일 순으로 고르게)",
        ],
        [
            "상세 조회(앱과 같은 SQL)",
            f"{len(measured):,} / {len(picked):,} 성공"
            + (f" · {detail_failures[0]}" if detail_failures else ""),
        ],
        [
            f"기본 창({_DEFAULT_WINDOW}) 행 = 넓은 창(±{margin}일) 행",
            f"{same:,} / {len(measured):,}",
        ],
        [
            "기본 창이 놓친 행",
            f"전체의 {_percent(total_missing / total_wide if total_wide else None, 2)} · "
            "코드별 최대 "
            f"{_percent(max(missing) if missing else None, 2)}",
        ],
        [
            "상세 조회 초 — 기본 창",
            _seconds_spread([cast(float, r.default_seconds) for r in measured]),
        ],
        [
            "상세 조회 초 — 넓은 창",
            _seconds_spread([cast(float, r.wide_seconds) for r in measured]),
        ],
        *_load_day_stats(sampled),
    ]
    yield [*_table(["표본 적재일", "값"], rows), ""]
    yield from _copy_parts(
        probe,
        picked,
        results,
        loads,
        today=today,
        max_codes=copy_codes,
        max_days=copy_days,
    )


# ---------------------------------------------------------------------------------- 실행


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="사내 실데이터 확인(읽기 전용). 앱을 끈 뒤 돌린다 — 런북 8장."
    )
    parser.add_argument(
        "--only",
        default=",".join(DEFAULT_CHECKS),
        help=f"돌릴 블록을 쉼표로({', '.join(CHECKS)}). 기본은 BigDataQuery 를 뺀 넷",
    )
    parser.add_argument("--database", type=Path, default=DUCKDB_PATH, help="시뮬레이션 DuckDB")
    parser.add_argument(
        "--equipment-database", type=Path, default=EQUIPMENT_DUCKDB_PATH, help="설비 DuckDB"
    )
    parser.add_argument("--dataset-id", default=None, help="비우면 가장 최근에 적재한 데이터셋")
    parser.add_argument(
        "--bdq-sample",
        type=int,
        default=DEFAULT_SAMPLE,
        help="적재일을 볼 표본 코드 수(0 이면 건너뜀)",
    )
    parser.add_argument(
        "--bdq-margin-days",
        type=int,
        default=DEFAULT_MARGIN_DAYS,
        help="표본의 넓은 창 — 원천 등록일 앞뒤 며칠",
    )
    parser.add_argument(
        "--bdq-no-max-window",
        action="store_true",
        help=f"{CATALOG_MAX_DAYS}일 목록 조회를 건너뛴다(너무 오래 걸릴 때)",
    )
    parser.add_argument(
        "--bdq-no-code-days",
        action="store_true",
        help="전 코드 적재일 조회(GROUP BY 한 번)를 건너뛴다",
    )
    parser.add_argument(
        "--bdq-copy-codes",
        type=int,
        default=DEFAULT_COPY_CODES,
        help="사본을 볼 여러 날 코드 수(0 이면 사본 확인을 끈다)",
    )
    parser.add_argument(
        "--bdq-copy-days",
        type=int,
        default=DEFAULT_COPY_DAYS,
        help="코드마다 다시 받을 적재일 수(끝 날 포함, 0 이면 끈다, 2 보다 작으면 2)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="같은 출력을 이 파일에도 블록마다 덧붙인다(UTF-8). 저장소 밖 경로를 준다 — 런북 8-0",
    )
    parser.add_argument("--today", type=date.fromisoformat, default=None, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def _use_utf8_stdout() -> None:
    # Windows 콘솔 기본 코드페이지(cp949)는 이 출력의 기호를 못 쓴다.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass


class _Sink:
    """조각이 끝나는 대로 화면과 `--output` 파일에 쓴다 — 중간에 멈춰도 앞 조각은 남는다."""

    def __init__(self, path: Path | None) -> None:
        self._file: TextIO | None = (
            None if path is None else path.open("w", encoding="utf-8", newline="\n")
        )

    def emit(self, text: str) -> None:
        print(text, flush=True)
        if self._file is not None:
            self._file.write(text + "\n")
            self._file.flush()

    def close(self) -> None:
        if self._file is not None:
            self._file.close()


_BLOCK_TITLES: Final[dict[str, str]] = {
    "env": "8-1",
    "legacy": "8-2",
    "reqb": "8-3",
    "equipment": "8-4",
    "bdq": "8-5",
}


def _block_parts(
    name: str,
    session: Session,
    args: argparse.Namespace,
    *,
    now: datetime,
    today: date,
    probe: BigDataQueryProbe | None,
) -> Iterator[list[str]]:
    if name == "env":
        yield check_env(session, now=now)
    elif name == "legacy":
        yield check_legacy(session)
    elif name == "reqb":
        yield check_reqb(session)
    elif name == "equipment":
        yield check_equipment(session)
    else:
        yield from iter_bigdataquery(
            today=today,
            sample=args.bdq_sample,
            margin_days=args.bdq_margin_days,
            max_window=not args.bdq_no_max_window,
            code_days=not args.bdq_no_code_days,
            copy_codes=args.bdq_copy_codes,
            copy_days=args.bdq_copy_days,
            probe=probe,
        )


def main(argv: Sequence[str] | None = None, *, probe: BigDataQueryProbe | None = None) -> int:
    _use_utf8_stdout()
    args = parse_args(argv)
    selected = [name.strip() for name in str(args.only).split(",") if name.strip()]
    unknown = [name for name in selected if name not in CHECKS]
    if unknown or not selected:
        print(f"모르는 블록: {unknown or '(없음)'} — 고를 수 있는 것: {', '.join(CHECKS)}")
        return 2
    now = datetime.now()
    today = args.today or now.date()
    session = Session(
        simulation_path=Path(args.database),
        equipment_path=Path(args.equipment_database),
        dataset_id=args.dataset_id,
    )
    needs_simulation = any(name in selected for name in ("env", "legacy", "reqb"))
    needs_equipment = any(name in selected for name in ("env", "equipment"))
    if needs_simulation:
        session.simulation, session.simulation_failure, locked = _open_read_only(
            session.simulation_path
        )
        session.locked |= locked
    if needs_equipment:
        session.equipment, session.equipment_failure, locked = _open_read_only(
            session.equipment_path
        )
        session.locked |= locked
    if session.locked:
        session.close()
        print(_LOCK_MESSAGE)
        return 1

    sink = _Sink(None if args.output is None else Path(args.output))
    try:
        sink.emit(
            "<!-- inspect_real_data_checks.py — 아래 블록을 리뷰 문서 "
            "「실데이터 확인」 절에 그대로 붙인다 -->\n"
        )
        for name in CHECKS:
            if name not in selected:
                continue
            try:
                for part in _block_parts(name, session, args, now=now, today=today, probe=probe):
                    sink.emit("\n".join(part))
            except Exception as exc:  # 한 블록이 멈춰도 다음 블록은 잰다. 문구는 찍지 않는다
                sink.emit(f"- `{_BLOCK_TITLES[name]}` 블록이 멈췄다 — {_failure(exc)}\n")
    finally:
        session.close()
        sink.close()
    return 0
