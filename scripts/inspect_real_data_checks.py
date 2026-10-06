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
| 8-2 | `legacy` | 원천의 기존 결과 컬럼과 신규 계산의 차이율·비율 분포 |
| 8-3 | `reqb` | 원천 `RQ_REQB` 의 소요기준별 행·공정 수 |
| 8-4 | `equipment` | 설비 DB 의 2262-04-11 Qual·환산비 0.2 모듈 행·일정 미정 대수 |
| 8-5 | `bdq` | 목록 조회 시간·`reg_date` 꼴·코드 규칙 위반·기간별 행 수·표본 적재일 |

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
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Final, Protocol, cast

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
from capa_simulation.services.equipment_contract import EQUIPMENT_ID_COLUMN  # noqa: E402
from capa_simulation.services.equipment_units import format_unit_count  # noqa: E402
from capa_simulation.services.frame_contracts import (  # noqa: E402
    AREA_NAMES,
    DEMAND_BASES,
    UNIMPLEMENTED_BASES,
    normalize_demand_basis,
)
from capa_simulation.services.legacy_comparison import (  # noqa: E402
    NEAR_TARGETS,
    NEAR_TOLERANCE,
    DifferenceDistribution,
    LegacyMetric,
    RatioDistribution,
    compare_metric,
    describe_ratios,
    difference_distribution,
    legacy_grain,
    ratio_distribution,
    summarize_comparison,
)
from capa_simulation.services.load_calculator import (  # noqa: E402
    calculate_chip_load,
    calculate_density_load,
    calculate_wafer_load,
)
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

_CODE_RULE: Final = "^[A-Za-z0-9._-]+$"
_DEFAULT_WINDOW: Final = f"−{DETAIL_WINDOW_DAYS_BEFORE}~+{DETAIL_WINDOW_DAYS_AFTER}일"
_LOCK_MESSAGE: Final = (
    "DB 를 열지 못했습니다. 앱이 떠 있으면 먼저 끄세요 — DuckDB 는 프로세스 배타 잠금입니다."
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
                    f"{copied:,} (사본 {copied_rows:,}행 — 2026-10-06 결정 B3 전에 만든 것)",
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
            ("최신 리비전 호기 마스터", "equipment_master_snapshot"),
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


def _dataset_row(
    connection: duckdb.DuckDBPyConnection, dataset_id: str | None
) -> tuple[str, str, str, object] | None:
    if dataset_id:
        row = connection.execute(
            "SELECT dataset_id, scenario_id, source_type, imported_at FROM app_meta.dataset "
            "WHERE dataset_id = ?",
            [dataset_id],
        ).fetchone()
    else:
        row = connection.execute(
            "SELECT dataset_id, scenario_id, source_type, imported_at FROM app_meta.dataset "
            "ORDER BY imported_at DESC LIMIT 1"
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
            session._source_failure = "데이터셋이 없다(시나리오를 등록한 적이 없다)"
            return None
        dataset_id, scenario_id, source_type, imported_at = picked
        total = _scalar(connection, "SELECT count(*) FROM app_meta.dataset")
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
    which = "`--dataset-id` 로 고른" if session.dataset_id else "가장 최근에 적재한"
    stamp = str(imported_at)[:10] if imported_at is not None else "?"
    label = (
        f"{which} 데이터셋(전체 {total:,}개 중) · 원천 종류 `{source_type}` · 적재 {stamp} · "
        f"원천 {len(raw):,}행 · 계산은 그 시나리오의 리비전 1(원천 그대로)"
    )
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


def _requirement_section(core: pd.DataFrame, tables: dict[str, pd.DataFrame]) -> list[str]:
    lines = ["**소요대수** — 신규는 리비전 1 로 다시 계산한 `RQ_REQB` 행별 소요대수다.", ""]
    contract = load_core_data_contract()
    try:
        required = _required_equipment(tables)
    except Exception as exc:  # 기준정보 오류면 계산이 멈춘다. 종류만 적는다
        return [*lines, f"- 신규 소요대수 계산 {_failure(exc)} — 대조하지 않았다", ""]
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
    return lines


def _chip_keys(contract_grain: Sequence[str]) -> list[str]:
    """Chip 부하량 결과가 갖는 계획 키 — `Pack Code` 는 계산 계층이 합산해 없다."""
    return [key for key in contract_grain if key != "Pack Code"]


def _definition_rows(core: pd.DataFrame, grain: Sequence[str]) -> list[list[str]]:
    """행 단위 정의 후보. 계획 줄 × WF 구분 에 한 번씩만 센다(경로 반복은 같은 값이다)."""
    rows: list[list[str]] = []
    candidates: tuple[tuple[str, str, Callable[[pd.DataFrame], pd.Series]], ...] = (
        (
            "`Plan_Chip(K개)` ÷ (생산수량 × 구분_Chip)",
            "Plan_Chip(K개)",
            lambda f: f["생산수량"] * f["구분_Chip"],
        ),
        (
            "`Plan_Chip(K개)` ÷ (생산수량 × 구분_Chip ÷ BE_수율) — 신규 Chip 부하량 식",
            "Plan_Chip(K개)",
            lambda f: f["생산수량"] * f["구분_Chip"] / f["BE_수율"],
        ),
        ("`GOOD_DIE` ÷ Net Die", "GOOD_DIE", lambda f: f["Net Die"]),
        ("`GOOD_DIE` ÷ (Net Die × EDS_수율)", "GOOD_DIE", lambda f: f["Net Die"] * f["EDS_수율"]),
    )
    inputs = ["생산수량", "구분_Chip", "BE_수율", "EDS_수율", "Net Die"]
    for label, column, denominator in candidates:
        if not _filled(core, column):
            continue
        try:
            needed = list(dict.fromkeys([*grain, column, *inputs]))
            cells = core.loc[:, needed].drop_duplicates(subset=list(grain))
            numeric = cells.loc[:, [column, *inputs]].apply(pd.to_numeric, errors="coerce")
            rows.append(_ratio_row(label, describe_ratios(numeric[column], denominator(numeric))))
        except Exception as exc:  # 원천 형이 달라도 다른 후보는 계속 본다
            rows.append([label, _failure(exc), *["-"] * 8])
    return rows


def _good_die_constancy(core: pd.DataFrame) -> str | None:
    if not _filled(core, "GOOD_DIE"):
        return None
    keys = ["제품정보", "Stack", "WF 구분"]
    values = core.loc[:, [*keys, "GOOD_DIE"]].copy()
    values["GOOD_DIE"] = pd.to_numeric(values["GOOD_DIE"], errors="coerce")
    distinct = values.dropna(subset=["GOOD_DIE"]).groupby(keys, dropna=False)["GOOD_DIE"].nunique()
    constant = int(distinct.eq(1).sum())
    return (
        f"- `GOOD_DIE` 는 제품정보×Stack×WF 구분 키 {len(distinct):,}개 중 {constant:,}개에서 값이 "
        f"하나뿐이고 {len(distinct) - constant:,}개에서 달·계획 줄마다 갈린다"
        "(하나뿐이면 물량이 아니라 "
        "제품 속성일 가능성이 크다)"
    )


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
            "**부하량** — 대조 키 `생산계획년월 × 제품정보 × Stack × WF 구분`"
            "(값은 계획 줄 × WF 구분에서 "
            "접은 뒤 더함).",
            "",
        ]
    )

    def wafer() -> pd.DataFrame:
        return calculate_wafer_load(tables["RQ_PKG_PLAN"], tables["RQ_YLD"], tables["RQ_CHIP_QTY"])

    def density() -> pd.DataFrame:
        return calculate_density_load(tables["RQ_PKG_PLAN"], tables["RQ_CHIP_EQ"])

    load_results: list[ComparisonResult] = []
    for label, column, build in (
        ("Wafer `WF수(매)`", "WF수(매)", wafer),
        ("Density `EQ(억Gb)`", "EQ(억Gb)", density),
    ):
        if not _filled(core, column):
            load_results.append(ComparisonResult(label=label, failure="원천이 비어 대조 불가"))
            continue
        metric = LegacyMetric(label=label, legacy_column=column)
        load_results.append(_guarded(label, partial(_compare_built, core, build, metric, contract)))
    lines.extend([*_table(_DIFFERENCE_HEADERS, [_difference_row(r) for r in load_results]), ""])

    lines.extend(_requirement_section(core, tables))
    lines.extend(_pcb_section(raw, core, grain))

    lines.extend(
        [
            "**Plan_Chip(K개) · GOOD_DIE** — 신규 Chip 부하량(K개)과의 비율. "
            "대조 키는 계획 줄(Pack Code "
            "합산) × WF 구분.",
            "",
        ]
    )
    chip_rows: list[list[str]] = []
    try:
        chip = calculate_chip_load(tables["RQ_PKG_PLAN"], tables["RQ_YLD"], tables["RQ_CHIP_QTY"])
    except Exception as exc:  # 기준정보 오류면 계산이 멈춘다
        chip = None
        lines.append(f"- 신규 Chip 부하량 계산 {_failure(exc)}")
    if chip is not None:
        keys = _chip_keys(grain)
        for column in ("Plan_Chip(K개)", "GOOD_DIE"):
            label = f"`{column}` ÷ 신규 Chip 부하량"
            if not _filled(core, column):
                chip_rows.append([label, "원천이 비어 대조 불가", *["-"] * 8])
                continue
            metric = LegacyMetric(label=column, legacy_column=column)
            result = _guarded(
                label, partial(compare_metric, core, chip, metric, contract, keys=keys)
            )
            if result.comparison is None:
                chip_rows.append([label, result.failure or "-", *["-"] * 8])
            else:
                chip_rows.append(_ratio_row(label, ratio_distribution(result.comparison)))
    chip_rows.extend(_definition_rows(core, grain))
    if chip_rows:
        lines.extend([*_table(_RATIO_HEADERS, chip_rows), ""])
    constancy = _good_die_constancy(core)
    if constancy:
        lines.append(constancy)
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
    lines = _heading("8-4", "설비 DB — 옛 Qual 자리표·환산비 0.2·일정 미정", "equipment")
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
                "- 최신 리비전이 옛 계약(v2)이라 호기 마스터 표가 없다 — "
                "이 절의 수는 모두 0 이 정상",
                "",
            ]
        )
    rows: list[list[str]] = []
    placeholder = f"DATE '{LEGACY_QUAL_PLACEHOLDER}'"
    master = "equipment_ops.equipment_master_snapshot"
    for label, sql, params in (
        (
            "최신 리비전 호기 마스터 행",
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
    ]


# ---------------------------------------------------------------------------------- 8-5 bdq


class BigDataQueryProbe(Protocol):
    """이 스크립트가 BigDataQuery 에 묻는 세 가지. 테스트는 가짜를 넘긴다."""

    def catalog(self, window: QueryWindow) -> pd.DataFrame: ...

    def detail_rows(self, code: str, window: QueryWindow) -> int: ...

    def load_days(self, code: str, window: QueryWindow) -> pd.DataFrame: ...


class CompanyProbe:
    """사내 `bigdataquery` 패키지로 묻는다. 상세는 앱과 같은 SQL(`QUERY_TEMPLATE`)이다."""

    def __init__(self) -> None:
        self._module = cast(BigDataQueryModule, load_bigdataquery_module())

    def catalog(self, window: QueryWindow) -> pd.DataFrame:
        return fetch_simulation_catalog(window)

    def detail_rows(self, code: str, window: QueryWindow) -> int:
        frame = call_get_data(self._module, build_query(QUERY_TEMPLATE, code, window=window))
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("getData 반환값이 DataFrame 이 아니다")
        return int(len(frame))

    def load_days(self, code: str, window: QueryWindow) -> pd.DataFrame:
        if not is_valid_simulation_code(code):
            raise ValueError("시뮬레이션 코드 규칙 위반")
        start, end = window.sql_bounds()
        sql = LOAD_DAYS_QUERY_TEMPLATE.format(simulation_code=code, start_date=start, end_date=end)
        frame = call_get_data(self._module, sql)
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("getData 반환값이 DataFrame 이 아니다")
        return frame


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
    """`catb_sim_info_id` 규칙 위반 수와 까닭의 종류. 코드는 찍지 않는다."""
    distinct = pd.Series(codes.astype("string").fillna("").unique())
    invalid = distinct.loc[[not is_valid_simulation_code(str(code)) for code in distinct]]
    empty = int(invalid.str.strip().eq("").sum())
    spaced = int(invalid.str.strip().str.contains(r"\s", regex=True).sum())
    non_ascii = int(invalid.map(lambda code: not str(code).isascii()).sum())
    others = int(len(invalid)) - empty - spaced - non_ascii
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


def _pick_evenly(items: Sequence[str], count: int) -> list[str]:
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


def check_bigdataquery(
    *,
    today: date,
    sample: int = DEFAULT_SAMPLE,
    margin_days: int = DEFAULT_MARGIN_DAYS,
    max_window: bool = True,
    probe: BigDataQueryProbe | None = None,
) -> list[str]:
    lines = _heading("8-5", "BigDataQuery — 목록·등록일·코드·적재일", "bdq")
    account = (
        "있음" if resolve_user_name() else "없음(Windows 는 없어도 된다 — 로그인 이름으로 묻는다)"
    )
    if probe is None:
        if not is_bigdataquery_package_available():
            return [
                *lines,
                "- `bigdataquery` 패키지가 없다 — 사외 PC 이거나 맨 `uv sync` 가 지웠다"
                "(4-1 의 되돌리기). "
                "이 절은 건너뛴다.",
                "",
            ]
        if not (is_bigdataquery_catalog_configured() and is_bigdataquery_adapter_configured()):
            return [*lines, "- 목록 또는 상세 SQL 이 설정되지 않았다 — 이 절은 건너뛴다.", ""]
        try:
            probe = CompanyProbe()
        except Exception as exc:  # 패키지를 불러오다 실패
            return [*lines, f"- 패키지를 불러오지 못함 — {_bdq_failure(exc)}", ""]
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
        return [*lines, "- 목록 조회가 모두 실패해 나머지는 건너뛴다.", ""]
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

    if sample <= 0:
        return [*lines, "- 표본 적재일 확인은 `--bdq-sample 0` 이라 건너뛰었다.", ""]
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
    lines.extend([*_table(["표본 적재일", "값"], rows), ""])
    return lines


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

    print(
        "<!-- inspect_real_data_checks.py — 아래 블록을 리뷰 문서 "
        "「실데이터 확인」 절에 그대로 붙인다 -->"
    )
    print()
    try:
        for name in CHECKS:
            if name not in selected:
                continue
            if name == "env":
                block = check_env(session, now=now)
            elif name == "legacy":
                block = check_legacy(session)
            elif name == "reqb":
                block = check_reqb(session)
            elif name == "equipment":
                block = check_equipment(session)
            else:
                block = check_bigdataquery(
                    today=today,
                    sample=args.bdq_sample,
                    margin_days=args.bdq_margin_days,
                    max_window=not args.bdq_no_max_window,
                    probe=probe,
                )
            print("\n".join(block))
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
