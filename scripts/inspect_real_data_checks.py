# Purpose: 실데이터로만 답이 나오는 항목을 두 DB·BigDataQuery 에서 읽기만 해 집계로 찍는다.

"""사내 실데이터 확인 도구 — 런북 8장(`docs/internal_update_runbook.md`)이 부른다.

사외에는 합성 표본밖에 없어 **실데이터로만 답이 나오는 질문**이 쌓인다(`docs/TODO.md`). 이
스크립트는 그 질문을 사내에서 한 번에 재고, 결과를 리뷰 문서에 **그대로 붙일 수 있는 Markdown
블록**으로 찍는다.

    uv run --no-sync python scripts/inspect_real_data_checks.py             # DB 확인 여섯
    uv run --no-sync python scripts/inspect_real_data_checks.py --only bdq  # BigDataQuery

| 블록 | `--only` | 무엇을 |
|---|---|---|
| 8-1 | `env` | 두 DB 의 마이그레이션 번호·주요 표 행 수, 적용 배포, `ref_data` 사본 |
| 8-2 | `legacy` | 기존 결과 대조 차이율·비율 분포, Wafer 경로 값, ST 정의 대조, ≈60 배 가르기 |
| 8-3 | `reqb` | 원천 `RQ_REQB` 의 소요기준별 행·공정 수 |
| 8-4 | `equipment` | 설비 DB 의 옛 Qual 자리표·모듈 환산비·일정 미정·사용기준·38열 개편 분포 |
| 8-5 | `bdq` | 목록 조회 시간·`reg_date` 꼴·코드 규칙 위반·전 코드 적재일·표본 적재일·사본 여부 |
| 8-9 | `home` | HOME 월 축(양산 Density 가 있는 달)에서 빠지는 계획 달 수 — EDP 포함·뺌 |
| 8-10 | `census` | 「지금대로」 로 정한 결정마다 그 꼴이 저장 리비전에 몇 개 있는지(센서스) |

8-6 ~ 8-8 은 런북의 다른 절(리뷰에 옮기는 법 등)이 쓰는 번호라 블록 번호로 쓰지 않는다.

**끝에 「전송용 요약」 을 찍는다.** 사내 리뷰는 사람이 손으로 옮겨 적는다(2026-10-22
사용자 답) — 블록은 리뷰 전문(`review/<stamp>.full.md`)에 남고, 사외로 가는 것은 압축본
(`review/<stamp>.md`)이다(런북 5장). 그래서 돌린 블록마다 판정에 쓰는 수를 **짧은 키와
수만으로** 한 줄에 싣는다(예: `8-2W 0/12 · 0.00% · -` — 키의 뜻은 런북 8-6 범례 한 곳). 합이
서는 수 묶음은 같은 줄 안에 `합 = 항 + 항` 식으로 두고, 줄 끝에 그 줄의 수로 만든 확인 코드
`#NN` 을 단다 — 사외가 받은 압축본에 `--check-summary <파일>` 을 돌려 한 자리 오타 · 자리바꿈 ·
빠진 8-10 줄을 잡는다(DB 를 열지 않는다. 압축본의 손으로 쓴 줄도 `합 = 항 + 항` 식은 다시 셈한다).
블록 출력은 그대로 두고 요약은 그 뒤에 따로
찍으며, 멈춘 실행(`Ctrl+C`)도 잰 데까지의 요약을 남긴다. 요약도 판정은 내리지 않는다 — 기대
꼴은 런북 8장이 적는다.

**지키는 것 셋.**

- **앱을 끄고 돌린다.** DuckDB 는 프로세스 배타 잠금인데 앱은 rerun 동안만 DB 를 쥐므로,
  쉬는 앱은 잠금에 안 잡힌다. 그래서 운영 DB 를 열 때는 이 저장소의 앱 프로세스
  (`streamlit run … app.py`)를 먼저 보고, 보이거나 DB 가 잠겨 있으면 그렇게 알린 뒤 멈춘다
  (코드 1). 프로세스를 살피지 못하면 잠금만 보고 그 사실을 한 줄 찍는다 — 런북 1-1 로 앱이
  꺼진 것을 먼저 본다. 사본만 열면 앱을 보지 않는다.
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
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from functools import lru_cache, partial
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
    BigDataQueryCallError,
    BigDataQueryModule,
    QueryWindow,
    build_query,
    call_get_data,
    classify_query_failure,
    failure_type_names,
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
from capa_simulation.persistence._sql_helpers import load_frame, quote  # noqa: E402
from capa_simulation.persistence.equipment_migration_runner import (  # noqa: E402
    load_equipment_migrations,
)
from capa_simulation.persistence.equipment_repository import (  # noqa: E402
    LEGACY_QUAL_PLACEHOLDER,
    EquipmentSnapshot,
    read_merged,
    read_official_pair,
)
from capa_simulation.persistence.equipment_scenario_store import (  # noqa: E402
    OPERATIONS_SCENARIO_ID,
    latest_release_row,
    legacy_trace_count,
    scenario_rows,
    schedule_revision_row,
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
from capa_simulation.services.dashboard import (  # noqa: E402
    build_monthly_wafer_load_from_load,
    build_production_dashboard,
)
from capa_simulation.services.equipment_contract import (  # noqa: E402
    AREA_CODES,
    COUNTED_USAGE_BASIS,
    EQUIPMENT_ID_COLUMN,
    LINE_TYPE_GROUPS,
    QUAL_CONFIRMATION_STATUSES,
    RELOCATION_DATE_COLUMN,
    STOP_DATE_COLUMN,
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
    duplicate_route_rows,
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
    FactorAgreement,
    FormulaInput,
    LegacyMetric,
    Quantiles,
    RatioDistribution,
    RatioGroups,
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
    drop_unplanned_rows,
    filter_edp_plan,
)
from capa_simulation.services.month_columns import complete_years  # noqa: E402
from capa_simulation.services.product_type import WF_DIVISIONS_BY_PRODUCT_TYPE  # noqa: E402
from capa_simulation.services.required_equipment import (  # noqa: E402
    REQB_COLUMNS,
    REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR,
    UNROUTED_KEY_MISMATCH_REASON,
    UNROUTED_LOADS_ATTR,
    UNROUTED_REASON_COLUMN,
    UNROUTED_UNKNOWN_PRODUCT_REASON,
    UNROUTED_UNUSED_REASON,
    calculate_required_equipment,
    required_exclusion_counts,
)
from capa_simulation.services.scenario_transform import (  # noqa: E402
    MONTHLY_TABLES,
    missing_calendar_months,
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
from capa_simulation.settings import (  # noqa: E402
    DUCKDB_PATH,
    EQUIPMENT_DUCKDB_PATH,
    is_operational_database_place,
)

CHECKS: Final[tuple[str, ...]] = (
    "env",
    "legacy",
    "reqb",
    "equipment",
    "bdq",
    "home",
    "census",
)
# BigDataQuery 는 사내 DB 를 길게 훑는다. 따로 부를 때만 돈다.
DEFAULT_CHECKS: Final[tuple[str, ...]] = (
    "env",
    "legacy",
    "reqb",
    "equipment",
    "home",
    "census",
)

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
MONTH_MERGE_SOURCE: Final = "SCENARIO_MONTH_MERGE"
DERIVED_SOURCE_TYPES: Final[tuple[str, ...]] = (
    "DUCKDB_SCENARIO_CLONE",
    MONTH_MERGE_SOURCE,
    "SCENARIO_YEAR_SHIFT",
)

_Picked = TypeVar("_Picked", bound=Hashable)

_CODE_RULE: Final = "^[A-Za-z0-9._-]+$"
_DEFAULT_WINDOW: Final = f"−{DETAIL_WINDOW_DAYS_BEFORE}~+{DETAIL_WINDOW_DAYS_AFTER}일"
_LOCK_MESSAGE: Final = (
    "DB 를 열지 못했습니다. 앱이 떠 있으면 먼저 끄세요 — DuckDB 는 프로세스 배타 잠금입니다. "
    "앱이 꺼져 있는데도 이 줄이 나오면 파일 손상일 수 있다 — 그대로 리뷰 문서에 적는다."
)
_APP_RUNNING_MESSAGE: Final = (
    "사용자 앱이 떠 있습니다 — DB 는 열지 않았습니다. 앱을 끈 뒤 다시 칩니다(런북 1-1)."
)
_SCAN_FAILED_NOTE: Final = (
    "- 앱 프로세스를 살피지 못해 DB 잠금만 봤다 — 쉬는 앱은 잠금에 안 잡힌다"
    "(런북 1-1 로 앱이 꺼진 것을 먼저 본다).\n"
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


# ---------------------------------------------------------------------------------- 전송용 요약
#
# 요약 줄은 사람이 손으로 옮겨 적는다(런북 5장). 그래서 줄은 짧은 키와 수만 싣고(키의 뜻은 런북 8-6
# 범례 한 곳), 줄 끝에 그 줄의 수로 만든 확인 코드 `#NN` 을 단다 — 사외가 `--check-summary` 로 다시
# 셈해 한 자리 오타·자리바꿈을 잡는다. 합이 서는 수 묶음은 같은 줄 안에 `합 = 항 + 항` 식으로 둔다.

_SUMMARY_NUMBER: Final = re.compile(r"\d+(?:\.\d+)?")
_SUMMARY_CODE: Final = re.compile(r"^(?P<body>.*?)\s*#(?P<code>\d{2})\s*$")
# 옮겨 적은 줄 앞의 목록 표지 — 코드에 넣지 않는다.
_SUMMARY_PREFIX: Final = re.compile(r"^\s*(?:[-*]\s+)?")
# 칸 가름 — 찍는 것은 ` · ` 이고, 손으로 옮기며 `;` 나 `, ` 로 바꿔 써도 같은 칸으로 본다. 붙여 쓴
# 가운뎃점(갈래 이름 `K·CHIP·WF`)과 띄지 않은 쉼표(천 단위 `1,020`)는 칸을 가르지 않는다.
_CELL_SPLIT: Final = re.compile(r"\s*;\s*|\s+·\s*|\s*·\s+|,\s+")
_CELL_SEP: Final = r"\s*(?:·|;|,)\s*"
# 요약 줄의 키(`8-1` · `8-2W` · `8-4s` · `8-5C1` · `8-10`) — 이 꼴로 시작하는 줄은 확인 코드가
# 있어야 한다.
_SUMMARY_KEY: Final = re.compile(r"^8-\d+[A-Za-z]?\d*(?:\s|$)")


def summary_code(text: str) -> str:
    """줄의 수만으로 만든 두 자리 확인 코드(0~96).

    쉼표를 떼고 수(소수점 포함)를 차례대로 읽어 숫자는 0~9, 소수점은 10, 수와 수 사이는 11 로 놓고
    12 진수로 이어 97 로 나눈 나머지다. 97 이 12 보다 큰 소수라 숫자 한 자리를 바꾸거나 한 수 안의
    이웃한 두 자리를 바꾸면 늘 코드가 달라진다. 수 하나를 빼먹거나 쪼개거나 붙인 것은 97 가운데 96
    꼴로 잡힌다(보장은 아니다 — 8-10 줄 수는 머리의 `0 아님 k` 가 따로 잡는다). 글자·기호는 셈에
    들지 않는다 — 손으로 옮기며 띄어쓰기를 바꾸거나 가운뎃점을 `;` · `, ` 로(갈래 이름 안의 것은
    `.` 으로) 바꿔 써도 같고, 키의 숫자(`8-2`)는 든다. 칸 가름을 그렇게 바꾼 줄은 `check_transcript`
    도 같은 칸으로 읽는다.
    """
    value = 0
    for token in _SUMMARY_NUMBER.findall(text.replace(",", "")):
        for char in token:
            value = (value * 12 + (10 if char == "." else int(char))) % 97
        value = (value * 12 + 11) % 97
    return f"{value:02d}"


def _summary_body(line: str) -> str:
    return _SUMMARY_PREFIX.sub("", line, count=1).strip()


def _note(key: str, *parts: str) -> str:
    """요약 한 줄 — `- <키> <칸> · <칸>`. 확인 코드는 찍을 때 붙인다(`summary_lines`)."""
    return f"- {key} " + " · ".join(part for part in parts if part)


def _short(text: str | None) -> str:
    """요약 칸의 실패·빈 값 — 예외 종류(`실패(X)`)는 그대로, 원천이 빈 것은 「빔」."""
    if not text:
        return "-"
    return "빔" if "비어" in text else text


def _noted(notes: list[str], key: str, build: Callable[[], Sequence[str]]) -> None:
    """요약 줄 조립이 멈춰도 블록 줄은 지킨다 — 요약에는 그 키와 실패 종류만 남긴다."""
    try:
        notes.extend(build())
    except Exception as exc:  # 요약은 덧붙이는 것이라 블록 출력을 잃지 않는다
        notes.append(_note(key, f"요약 {_failure(exc)}"))


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
    # 전송용 요약에 모을 줄 — 블록이 돈 차례대로 쌓는다(`summary_lines`).
    notes: list[str] = field(default_factory=list)
    # 공식 설비 시나리오 한 벌(8-1·8-4 가 나눈다 — 한 번만 읽는다). 못 읽었으면 그 까닭 글.
    _official: OfficialEquipment | str | None = None

    def official_equipment(self) -> OfficialEquipment | str:
        """공식 설비 시나리오(공통 최신 + 최신 공식 발행)를 한 번 읽어 둔다."""
        if self._official is None:
            assert self.equipment is not None
            self._official = _read_official_equipment(self.equipment)
        return self._official

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


# ---------------------------------------------------------------------------------- 공식 설비


@dataclass(frozen=True)
class OfficialEquipment:
    """공식 설비 시나리오 한 벌 — 앱이 새 세션에 여는 것과 같은 길(`read_official_pair` →
    `read_merged`)로 읽는다.

    공통 칸은 공통 대장 최신(`common_*`), 일정 칸(날짜 여섯·시나리오 메모·비가동)은 최신 공식 발행의
    일정 리비전(`schedule_*`)이다. 일정 리비전이 0027 이관 리비전이면 그 원천인 옛 리비전 id 가
    `legacy_revision_id` 다 — 옛 Qual 자리표는 그 원천 행에만 있다(새 표에는 없다 — 읽기 투영이
    빈칸으로 바꿔 넣는다). 합친 읽기가 막히면 `snapshot` 이 None 이고 `failure` 가 그 종류다.
    """

    common_id: str
    common_no: int
    contract: int
    schedule_id: str | None = None
    schedule_no: int | None = None
    legacy_revision_id: str | None = None
    migrated_scenario: bool = False
    release_no: int | None = None
    snapshot: EquipmentSnapshot | None = None
    failure: str | None = None


# 가정 배치 차이(설비 0031) — 앱의 리비전 읽기(투영의 배치 차이 셈·지문 칸)가 이 번호의 표·칸에
# 기댄다. 0027 뒤 이 번호 전의 사본은 「설비 0031 전」 으로 따로 적고 공식 설비 읽기를 건너뛴다(지금
# 까닭 「0027 전」 으로 잘못 찍히지 않게 — 설계 7-1).
_LAYOUT_OVERLAY_MIGRATION = 31
_SCENARIO_MIGRATION = 27


def _read_official_equipment(connection: duckdb.DuckDBPyConnection) -> OfficialEquipment | str:
    """공식 설비 시나리오를 읽는다. 리비전이 없거나 설비 시나리오 표가 없거나(0027 전) 가정 배치
    차이 표가 없으면(0031 전) 그 까닭 글."""
    versions = _versions(connection, "equipment_meta.schema_migration")
    if (
        versions is not None
        and _SCENARIO_MIGRATION in versions
        and _LAYOUT_OVERLAY_MIGRATION not in versions
    ):
        return "설비 0031 전(가정 배치 차이 표 없음) — 앱을 띄워 마이그레이션을 건 뒤 다시"
    try:
        pair = read_official_pair(connection)
        if pair is None:
            return "리비전 0"
        common_id, schedule_id = pair
        common = _latest_equipment_revision(connection)
        assert common is not None
        schedule = schedule_revision_row(connection, schedule_id) if schedule_id else None
        release = latest_release_row(connection)
    except duckdb.Error as exc:
        return f"설비 시나리오 표를 읽지 못함 {_failure(exc)} — 0027 전이면 앱을 띄운 뒤 다시"
    snapshot: EquipmentSnapshot | None = None
    failure: str | None = None
    try:
        snapshot = read_merged(connection, common_id, schedule_id)
    except Exception as exc:  # 검증 오류 문구는 설비명을 싣는다. 종류만 적는다
        failure = _failure(exc)
    return OfficialEquipment(
        common_id=common_id,
        common_no=common[1],
        contract=common[2],
        schedule_id=schedule_id,
        schedule_no=int(str(schedule["revision_no"])) if schedule is not None else None,
        legacy_revision_id=(
            str(schedule["legacy_revision_id"])
            if schedule is not None and schedule["legacy_revision_id"] is not None
            else None
        ),
        migrated_scenario=(
            schedule is not None and schedule["equipment_scenario_id"] == OPERATIONS_SCENARIO_ID
        ),
        release_no=int(str(release["release_no"])) if release is not None else None,
        snapshot=snapshot,
        failure=failure,
    )


def _official_downtime_rows(official: OfficialEquipment | str) -> str:
    """공식 일정 리비전의 비가동 행 수(합친 읽기 — 레거시 비가동 중복은 앱처럼 하나로 본다)."""
    if isinstance(official, str):
        return _short(official)
    if official.snapshot is None:
        return official.failure or "-"
    return f"{len(official.snapshot.downtime):,}"


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


def _migration_note(label: str, versions: list[int] | None, code_versions: Sequence[int]) -> str:
    """전송용 요약의 마이그레이션 칸 — 「S 35/35」(DB 최고 번호 / 코드 최고 번호).

    읽지 못하면 「S -」 다.
    """
    if versions is None:
        return f"{label} -"
    return f"{label} {max(versions, default=0)}/{max(code_versions, default=0)}"


def check_env(session: Session, *, now: datetime, root: Path = PROJECT_ROOT) -> list[str]:
    lines = _heading("8-1", "환경 — 두 DB 와 적용 배포", "env")
    lines.append(f"- 실행 {now:%Y-%m-%d %H:%M} · 적용 배포 {_applied_deploy(root)}")
    code_simulation = [migration.version for migration in load_migrations()]
    code_equipment = [migration.version for migration in load_equipment_migrations()]
    # 요약 — 「8-1 S 35/35 · E 23/23 · R 12 · O 3」(R 리비전 · O 공식버전).
    note = {"S": "S -", "E": "E -", "R": "R -", "O": "O -"}

    simulation = session.simulation
    if simulation is None:
        lines.append(f"- 시뮬레이션 DB — {session.simulation_failure}")
    else:
        versions = _versions(simulation, "app_meta.schema_migration")
        lines.append(
            _migration_line("시뮬레이션 DB", session.simulation_path, versions, code_simulation)
        )
        note["S"] = _migration_note("S", versions, code_simulation)
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
        counted = dict((label, value) for label, value in rows)
        note["R"] = f"R {counted.get('리비전', '-')}"
        note["O"] = f"O {counted.get('공식버전', '-')}"
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
            cleaned = simulation.execute(
                "SELECT count(*) FROM app_meta.schema_migration WHERE version = 33"
            ).fetchall()[0][0]
            meaning = (
                "리비전 1 과 달라 `0033` 이 남긴 사본. 0 이 아니어도 결함 아님"
                if cleaned
                else "`0033` 적용 전 — 앱을 띄우면 리비전 1 과 같은 사본은 지워진다"
            )
            rows.append(
                [
                    "`ref_data` 에 리비전 표 사본이 남은 데이터셋",
                    f"{copied:,} (사본 {copied_rows:,}행 — {meaning})",
                ]
            )
        except duckdb.Error as exc:
            rows.append(["`ref_data` 에 리비전 표 사본이 남은 데이터셋", _failure(exc)])
        lines.extend(["", *_table(["시뮬레이션 DB", "행"], rows), ""])

    equipment = session.equipment
    if equipment is None:
        lines.append(f"- 설비 DB — {session.equipment_failure}")
        lines.append("")
        session.notes.append(_note("8-1", *note.values()))
        return lines
    versions = _versions(equipment, "equipment_meta.schema_migration")
    lines.append(_migration_line("설비 DB", session.equipment_path, versions, code_equipment))
    note["E"] = _migration_note("E", versions, code_equipment)
    session.notes.append(_note("8-1", *note.values()))
    rows = []
    latest = _latest_equipment_revision(equipment)
    rows.append(
        ["설비 리비전", _safe_scalar(equipment, "SELECT count(*) FROM equipment_ops.revision")]
    )
    if latest is None:
        rows.append(["최신 설비 리비전", "없음"])
    else:
        revision_id, revision_no, contract = latest
        # 설비 리비전 = 공통 호기 대장 리비전(0027 뒤). 마스터·보유대수는 공통 최신, 비가동은 설비
        # 시나리오 일정에 있어 **공식 일정 리비전**(최신 공식 발행)으로 센다 — 공통만 저장해도
        # 비가동 수가 0 으로 보이지 않는다.
        rows.append(["최신 설비 리비전", f"r{revision_no} · 계약 v{contract}"])
        for label, table in (
            ("최신 리비전 설비 마스터", "equipment_master_snapshot"),
            ("최신 리비전 기존 보유대수", "baseline_snapshot"),
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
        official = session.official_equipment()
        rows.append(
            [
                "공식 일정 리비전",
                _short(official) if isinstance(official, str) else _official_place(official),
            ]
        )
        rows.append(["공식 일정 리비전 비가동 일정", _official_downtime_rows(official)])
    lines.extend(["", *_table(["설비 DB", "행"], rows), ""])
    return lines


def _official_place(official: OfficialEquipment) -> str:
    """「공식 v1 → 이관 시나리오 r3」 — 시나리오 이름은 사용자가 지은 값이라 찍지 않는다."""
    if official.release_no is None or official.schedule_no is None:
        return "발행 없음"
    scenario = "이관 시나리오" if official.migrated_scenario else "다른 시나리오"
    return f"공식 v{official.release_no} → {scenario} r{official.schedule_no}"


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
    revision_id: str = ""


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
    session._source = SourceData(
        dataset_label=label, raw=raw, tables=tables, revision_id=revision_id
    )
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
    core: pd.DataFrame,
    tables: dict[str, pd.DataFrame],
    calculated: Required,
    notes: list[str] | None = None,
    *,
    st_reference: Callable[[], StReference | str | None] | None = None,
) -> list[str]:
    notes = [] if notes is None else notes
    lines = [
        "**소요대수** — 신규는 리비전 1 로 다시 계산한 `RQ_REQB` 행별 소요대수다.",
        "",
        *_st_definition_lines(tables, notes, reference=st_reference),
    ]
    contract = load_core_data_contract()
    required = calculated.frame
    if required is None:
        notes.append(_note("8-2R", _short(calculated.failure)))
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
    link_share = _percent(linked / len(fresh_keys) if fresh_keys else None, 2)
    lines.append(
        f"- 키 연결(값과 무관) — 신규 경로 키 {len(fresh_keys):,} 중 원천 경로에 있는 키 "
        f"{linked:,} ({link_share}) · "
        "신규가 제외 목록에 둔 키 "
        f"{len(excluded_keys):,}"
    )
    # 요약 — 「8-2R 키 연결 % · 경로 키 접음 차이율 최대 % · ≈60 무리」.
    requirement_note = [link_share]
    left_out_notes: list[str] = []
    lines.extend(_left_out_lines(required, left_out_notes))
    if not _filled(route, "소요대수"):
        notes.extend([_note("8-2R", *requirement_note, "빔"), *left_out_notes])
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
    if path is None:
        requirement_note.append(_short(results[0].failure))
    else:
        requirement_note.append(_percent(difference_distribution(path).maximum, 2))
        try:
            # 무리 수도 가르기와 같은 `ratio_groups` 다 — 둘 다 이 안에서 재야 실패가 이 절에
            # 머문다.
            groups = ratio_groups(path)
            requirement_note.append(f"{groups.size(SUSPECT_GROUP):,}")
            lines.extend(_ratio_breakdown(path, compared, required, tables, finest, groups))
        except Exception as exc:  # 가르기가 실패해도 아래 절은 계속 잰다
            if len(requirement_note) < 3:
                requirement_note.append(_failure(exc))
            lines.extend([f"- ≈60 배 가르기 {_failure(exc)}", ""])
    notes.extend([_note("8-2R", *requirement_note), *left_out_notes])
    return lines


@dataclass(frozen=True)
class StReference:
    """ST 정의 대조를 대신 본 리비전 — 그 `RQ_UPEH` 와 저장 차례(만든 시각 차례, 1 이 처음 저장한
    리비전) `order` / 전체 리비전 수 `total`. 이름·번호 대신 차례만 찍는다."""

    upeh: pd.DataFrame
    order: int
    total: int


# 대신 볼 리비전 후보 — UPEH·ST 가 둘 다 양수이고 Area 가 MI 일 수 있는 행이 하나라도 있는 리비전.
# Area 맞춤의 끝 판정은 파이썬 `match_key`(앞뒤 공백 · 대소문자)가 한다 — SQL 은 그보다 넓게만
# 거른다(`mi` 를 품은 값). Main 행만 양수인 리비전마다 `RQ_UPEH` 전체를 읽지 않게 한다.
_ST_CANDIDATES_SQL: Final = (
    "SELECT DISTINCT revision_id FROM rev_data.{table} "
    'WHERE TRY_CAST("UPEH" AS DOUBLE) > 0 AND TRY_CAST("ST" AS DOUBLE) > 0 '
    """AND lower("Area_Name") LIKE '%mi%'"""
)


def _mi_agreement(upeh: pd.DataFrame) -> tuple[pd.Series, pd.Series] | None:
    """(UPEH × ST ÷ 60 이 선 행, 그 행의 Area 맞댐 값). 칸이 없으면 None."""
    if not {"Area_Name", "UPEH", "ST"} <= set(upeh.columns):
        return None
    agreement = time_agreement(upeh).dropna()
    return agreement, match_key(upeh["Area_Name"]).loc[agreement.index]


def _mi_rows(upeh: pd.DataFrame) -> int:
    found = _mi_agreement(upeh)
    return 0 if found is None else int(found[1].eq("mi").sum())


def load_st_reference(session: Session) -> StReference | str | None:
    """리비전 1 에 UPEH·ST 가 둘 다 양수인 MI 행이 없을 때 ST 정의 대조가 대신 볼 리비전.

    가장 최근에 저장한 리비전부터 거꾸로 보아 그런 MI 행이 있는 첫 리비전이다(리비전 1 은 뺀다).
    없으면 None, 읽다 멈추면 그 실패 종류 글. 원천에 ST 가 빈 리비전 1 만으로는 정의 대조가 판정
    불가였다(`202610231430` 리뷰 사외 요청 5).
    """
    connection = session.simulation
    source = session._source
    if connection is None or source is None:
        return None
    table = REVISION_TABLES["RQ_UPEH"]
    try:
        ordered = connection.execute(
            "SELECT revision_id FROM app_meta.scenario_revision ORDER BY created_at, revision_id"
        ).fetchall()
        candidates = {
            str(row[0])
            for row in connection.execute(_ST_CANDIDATES_SQL.format(table=quote(table))).fetchall()
        }
        revisions = [str(row[0]) for row in ordered]
        for position in range(len(revisions) - 1, -1, -1):
            revision_id = revisions[position]
            if revision_id == source.revision_id or revision_id not in candidates:
                continue
            upeh = load_frame(
                connection,
                schema="rev_data",
                table_name=table,
                owner_column="revision_id",
                owner_id=revision_id,
            )
            if _mi_rows(upeh):
                return StReference(upeh=upeh, order=position + 1, total=len(revisions))
    except (duckdb.Error, RuntimeError) as exc:
        return _failure(exc)
    return None


def _st_definition_lines(
    tables: dict[str, pd.DataFrame],
    notes: list[str] | None = None,
    *,
    reference: Callable[[], StReference | str | None] | None = None,
) -> list[str]:
    """ST 정의 대조(참고) — `RQ_UPEH` 에서 UPEH·ST 가 둘 다 양수인 행의 UPEH × ST ÷ 60 을 MI·Main
    으로 나눠 찍는다.

    `RQ_UPEH` 의 MI 행 ST 는 한 개당 분이다(정의). 두 칸이 같은 처리 속도를 적었으면 1 근처이고,
    MI 쪽이 벗어나면 원천 입력이 정의와 다르다는 신호다. 계산이 쓰는 ST 는 MI 행뿐이라 MI 를 앞에
    따로 두고, ST 가 계산에 들지 않는 Main 행은 뒤에 참고로만 둔다 — 한 분포로 섞으면 Main 에 다른
    뜻으로 실린 ST 가 MI 분포를 가린다. 판정하지 않고 행 수와 분포만 찍는다. ≈60 가르기와 달리
    소요대수 대조가 없어도 늘 찍는다.

    리비전 1 에 그런 MI 행이 없으면(원천에 ST 가 빈 리비전) `reference` 가 내는 리비전(가장 최근에
    저장한 리비전 가운데 그런 MI 행이 있는 것)으로 한 줄을 더 찍는다. 요약은 첫 칸이 늘 리비전 1 의
    MI 행 수이고, 대신 본 것이 있으면 `대신 k/N` 칸 뒤에 그 리비전의 MI 세 칸이 붙는다.
    """
    head = "- ST 정의 대조(참고) — 리비전 1 `RQ_UPEH` 의 UPEH × ST ÷ 60(ST 는 분 단위라 기대 1)"
    notes = [] if notes is None else notes
    upeh = tables.get("RQ_UPEH")
    found = None if upeh is None else _mi_agreement(upeh)
    if upeh is None or found is None:
        lines = [f"{head} — 칸 없음"]
        mi_count: int | None = None
    else:
        agreement, area = found
        mi_count = int(area.eq("mi").sum())
        if agreement.empty:
            lines = [f"{head} — UPEH·ST 가 둘 다 양수인 행 0"]
        else:
            lines = [f"{head} — {' / '.join(_agreement_parts(agreement, area))}"]
    if mi_count:
        mi = agreement.loc[area.eq("mi")]
        near = int(mi.sub(1.0).abs().le(NEAR_TOLERANCE).sum())
        # 요약 — 「8-2T MI 행 · 중앙 · 1 ±5% 안」.
        notes.append(_note("8-2T", f"{mi_count:,}", _ratio(float(mi.median())), f"{near:,}"))
        return lines
    first = "-" if mi_count is None else "0"
    picked = reference() if reference is not None else None
    other = (
        "- ST 정의 대조(대신) — 리비전 1 에 UPEH·ST 가 둘 다 양수인 MI 행이 없어 가장 최근에 "
        "저장한 리비전 가운데 그런 MI 행이 있는 것"
    )
    if reference is None:
        notes.append(_note("8-2T", first))
    elif isinstance(picked, StReference):
        agreement, area = cast(tuple[pd.Series, pd.Series], _mi_agreement(picked.upeh))
        mi = agreement.loc[area.eq("mi")]
        near = int(mi.sub(1.0).abs().le(NEAR_TOLERANCE).sum())
        lines.append(
            f"{other}(저장 차례 {picked.order:,}/{picked.total:,})의 `RQ_UPEH` — "
            + " / ".join(_agreement_parts(agreement, area))
        )
        # 요약 — 「8-2T 0 · 대신 k/N · MI 행 · 중앙 · 1 ±5% 안」.
        notes.append(
            _note(
                "8-2T",
                first,
                f"대신 {picked.order:,}/{picked.total:,}",
                f"{len(mi):,}",
                _ratio(float(mi.median())),
                f"{near:,}",
            )
        )
    elif picked is None:
        lines.append(f"{other} — 없음")
        notes.append(_note("8-2T", first, "대신 없음"))
    else:
        lines.append(f"{other} — 찾지 못함 {picked}")
        notes.append(_note("8-2T", first, f"대신 {picked}"))
    return lines


def _agreement_parts(agreement: pd.Series, area: pd.Series) -> list[str]:
    """MI · Main(계산에 쓰지 않음) · 그 밖 — 한 리비전의 UPEH × ST ÷ 60 분포 칸들."""
    parts = [
        _agreement_part("MI", agreement.loc[area.eq("mi")]),
        _agreement_part("Main(계산에 쓰지 않음)", agreement.loc[area.eq("main")]),
    ]
    others = int((~area.isin(["mi", "main"])).sum())
    if others:
        parts.append(f"그 밖 {others:,}")
    return parts


def _agreement_part(label: str, values: pd.Series) -> str:
    """한 Area 의 UPEH × ST ÷ 60 — 행 수, p5·중앙·p95, 1 ±5% 안 행 수."""
    if values.empty:
        return f"{label} 0"
    near = int(values.sub(1.0).abs().le(NEAR_TOLERANCE).sum())
    p5, median, p95 = (float(np.quantile(values.to_numpy(), q)) for q in (0.05, 0.5, 0.95))
    return (
        f"{label} {len(values):,} · p5 · 중앙 · p95 {_ratio(p5)} · {_ratio(median)} · "
        f"{_ratio(p95)} · 1 ±{NEAR_TOLERANCE:.0%} 안 {near:,}"
    )


# 경로 없는 부하의 사유 → 짧은 이름. 사유는 코드 상수라 찍어도 실데이터 값이 아니다.
_UNROUTED_REASON_LABELS = {
    UNROUTED_KEY_MISMATCH_REASON: "키 어긋남",
    UNROUTED_UNKNOWN_PRODUCT_REASON: "REQB 에 없는 제품",
    UNROUTED_UNUSED_REASON: "규칙상 미사용",
}


def _left_out_lines(required: pd.DataFrame, notes: list[str] | None = None) -> list[str]:
    """소요대수에 들지 않은 수요 건수(알림 모음·발행 검사가 알리는 것과 같은 셈)와 경로 없는 부하의
    갈래.

    경로 없는 부하는 사유·소요기준·WF 구분별 개수만 적는다. 세지 않는 「규칙상 미사용」(그 제품에 그
    소요기준·WF 구분 경로가 없음)도 따로 찍는다 — 세는 두 사유가 한 갈래에 몰려 있으면 아직 규칙으로
    가르지 못한 구조일 수 있어(경고가 늘 뜨는 잡음) 사외가 규칙을 정할 근거가 된다. 이름은 계약
    어휘(`KNOWN_BASES`·`DECLARED_DIVISIONS`)만 찍고 그 밖은 「그 밖」으로 묶는다.
    """
    counts = required_exclusion_counts(required)
    lines = [
        "- 소요대수에 들지 않은 수요(리비전 1 전체 기간) — 기준정보가 없어 부하량에서 빠진 계획 "
        f"{counts.excluded_plans:,} · 생산수량이 빈 계획 {counts.blank_plans:,} · 경로에 닿지 "
        f"않은 계획 부하 {counts.unrouted_loads:,} · 대당 Capa 없는 부하 경로 "
        f"{counts.excluded_routes:,}"
    ]
    notes = [] if notes is None else notes
    # 요약 — 「8-2X 기준정보 없음 · 생산수량 빈 · 경로에 닿지 않음 · 대당 Capa 없는 경로」.
    notes.append(
        _note(
            "8-2X",
            *(
                f"{value:,}"
                for value in (
                    counts.excluded_plans,
                    counts.blank_plans,
                    counts.unrouted_loads,
                    counts.excluded_routes,
                )
            ),
        )
    )
    unrouted = required.attrs.get(UNROUTED_LOADS_ATTR)
    if not isinstance(unrouted, pd.DataFrame) or unrouted.empty:
        notes.append(_note("8-2B", "0"))
        return lines
    bases = {name.casefold(): name for name in KNOWN_BASES}
    divisions = {name.casefold(): name.upper() for name in DECLARED_DIVISIONS}
    divisions[""] = "(PKG)"
    reasons = (
        unrouted[UNROUTED_REASON_COLUMN]
        if UNROUTED_REASON_COLUMN in unrouted.columns
        else pd.Series(UNROUTED_KEY_MISMATCH_REASON, index=unrouted.index)
    )
    labels = pd.DataFrame(
        {
            "reason": reasons.map(_UNROUTED_REASON_LABELS).fillna("그 밖"),
            "basis": match_key(unrouted["소요기준"]).map(bases).fillna("그 밖"),
            "division": match_key(unrouted["WF 구분"]).map(divisions).fillna("그 밖"),
        }
    )
    groups = labels.groupby(["reason", "basis", "division"]).size().reset_index(name="count")
    branches = " · ".join(
        f"{reason} · {basis} · {division} {int(count):,}"
        for reason, basis, division, count in groups.itertuples(index=False)
    )
    lines.append(
        "  - 경로에 닿지 않은 계획 부하의 갈래(사유 · 소요기준 · WF 구분 → 개수, 규칙상 미사용은 "
        "세지 않음) " + branches
    )
    notes.append(_branch_note(groups, counts.unrouted_loads))
    return lines


# 요약의 갈래 이름 — 사유는 한 글자로 접는다(범례 런북 8-6). 소요기준·WF 구분 칸의 「그 밖」 은 `?`.
_REASON_KEYS: Final = {
    "키 어긋남": "K",
    "REQB 에 없는 제품": "P",
    "규칙상 미사용": "U",
    "그 밖": "?",
}
SUMMARY_BRANCHES: Final = 3


def _branch_note(groups: pd.DataFrame, unrouted_loads: int) -> str:
    """요약의 경로 갈래 줄 — 「8-2B 닿지 않음 = 큰 갈래 셋 + 그 밖 n갈래 m · U 규칙상 미사용」.

    세는 갈래(규칙상 미사용 밖)를 개수가 큰 차례로 셋까지 이름과 함께, 나머지는 갈래 수와 합만
    적는다 — 갈래가 몇 개든 줄 길이가 정해진다. 식의 합은 `경로에 닿지 않음` 이라 줄 안에서 검산이
    선다.
    """
    unused = _UNROUTED_REASON_LABELS[UNROUTED_UNUSED_REASON]

    def label(reason: str, basis: str, division: str) -> str:
        names = [
            _REASON_KEYS.get(reason, "?"),
            *("?" if n == "그 밖" else n for n in (basis, division)),
        ]
        return "·".join(names)

    counted = sorted(
        (
            (int(count), label(reason, basis, division))
            for reason, basis, division, count in groups.itertuples(index=False)
            if reason != unused
        ),
        key=lambda item: (-item[0], item[1]),
    )
    terms = [f"{name} {count:,}" for count, name in counted[:SUMMARY_BRANCHES]]
    rest = counted[SUMMARY_BRANCHES:]
    if rest:
        terms.append(f"그 밖 {len(rest):,}갈래 {sum(count for count, _ in rest):,}")
    unused_count = sum(
        int(count) for reason, *_, count in groups.itertuples(index=False) if reason == unused
    )
    return _note(
        "8-2B", f"{unrouted_loads:,} = " + (" + ".join(terms) or "0"), f"U {unused_count:,}"
    )


# ------------------------------------------------------------------ 8-2 소요대수 ≈60 배 가르기


def _ratio_breakdown(
    path: pd.DataFrame,
    route: pd.DataFrame,
    required: pd.DataFrame,
    tables: dict[str, pd.DataFrame],
    grain: Sequence[str],
    groups: RatioGroups | None = None,
) -> list[str]:
    """경로 키 대조를 기존÷신규 ≈60·≈1·그 밖 세 무리로 나눠 어디서 60 배가 나는지 센다.

    사내 리뷰 202610071831~202610182227 의 ≈60 무리는 모두 MI 경로였고, `RQ_UPEH` 의 ST 를 분
    단위로 읽는 정의(2026-10-22)로 신규가 그 무리에 맞는다. 이 가르기는 ≈60 무리가 다시 나는지 보는
    감시다 — 나오면 다른 원인이라 판정하지 않고 속성·공정·산식 인자·원천 칸마다 개수와 분포를 낸다.
    """
    groups = ratio_groups(path) if groups is None else groups
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
        "ST 를 분 단위로 읽는 정의 뒤에도 남은 무리다 — 판정하지 않는다.",
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
        ("UPEH × ST ÷ 60 (둘 다 있는 키 — 정의대로면 1)", time_agreement(inputs)),
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
        "- 상수(하루 24시간 · MI 의 60 ÷ ST · CHIP·PKG 의 ÷1000)는 인자 값처럼 가를 수 없다 — "
        "60 은 MI, ÷1000 은 CHIP·PKG 에만 걸리므로 위 속성 표의 Main/MI·소요기준 줄이 그 "
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
    note: list[str] | None = None,
) -> list[str]:
    """`note` 에는 전송용 요약의 Wafer 경로 줄 조각(맞대기 차이율·가장 잘 따라가는 칸)을 더한다."""
    column = "WF수(매)"
    note = [] if note is None else note
    if required.frame is None:
        note.append(_short(required.failure))
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
        note.append(_short(results[0].failure))
        return lines
    note.append(_percent(difference_distribution(path).median, 2))
    frame = ratio_groups(path).frame
    link = RouteLink.build(frame, wf_route)
    rows: list[list[str]] = []
    best: FactorAgreement | None = None
    for factor in WAFER_ROUTE_FACTORS:
        agreement = factor_agreement(frame, route_factor_by_key(link, factor), label=factor.label)
        if agreement.off_one and (
            best is None
            or agreement.near_factor * best.off_one > best.near_factor * agreement.off_one
        ):
            best = agreement
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
    # 가장 잘 따라가는 칸 — 칸 ≠1 인 키가 없으면 「-」, 어느 칸도 따라가지 않으면 「0」.
    if best is None:
        note.append("-")
    elif best.near_factor == 0:
        note.append("0")
    else:
        note.append(f"{best.label} {best.near_factor:,}/{best.off_one:,}")
    return lines


def _wafer_route_section(
    core: pd.DataFrame,
    tables: dict[str, pd.DataFrame],
    required: Required,
    grain: Sequence[str],
    contract: CoreDataContract,
    notes: list[str] | None = None,
) -> list[str]:
    """Wafer `WF수(매)` 를 경로 단위로 본다(2026-10-10 사용자 결정).

    원천 안에서 경로 값이 무엇으로 갈리는지 가르고, 신규 계산과 경로 키 13 으로 맞댄다.
    """
    column = "WF수(매)"
    notes = [] if notes is None else notes
    lines = [
        "**Wafer `WF수(매)` 경로 값** — 위 표의 Wafer `값 불일치` 는 계획 줄 × WF 구분 안에서 "
        "경로 행마다 `WF수(매)` 가 갈려서다(계획 줄 값이 아니라 경로 값). 신규 계산에는 경로마다 "
        "갈리는 Wafer 값이 없다 — 소요기준 WF 경로의 `부하량` 은 계획 줄(Pack Code 합산) × "
        "WF 구분의 Wafer 부하량을 그 계획 줄의 모든 WF 경로에 같은 값으로 붙인 것이고, 측정률은 "
        "대당 Capa 의 분모로만 든다. 그래서 원천 경로 값이 무엇으로 갈리는지를 개수로 가른다.",
        "",
    ]
    if not _filled(core, column):
        notes.append(_note("8-2W", "빔"))
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
    # 요약 — 「8-2W 갈리는 칸/경로 칸 · 맞대기 차이율 중앙 % · 가장 잘 따라가는 칸 ≈칸/칸≠1」.
    note = [f"{spread.route_split:,}/{spread.route_cells:,}"]
    lines.extend(_wafer_route_comparison(core, tables, required, grain, contract, note))
    notes.append(_note("8-2W", *note))
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


# 요약의 부하량 이름 — 한 글자(범례 런북 8-6). 대조 목록에 지표를 더하면 여기도 더한다.
_LOAD_KEYS: Final = {"Wafer": "W", "Density": "D", "Chip": "C"}


def _load_note(names: Sequence[str], results: Sequence[ComparisonResult]) -> str:
    """요약의 부하량 줄 — 「8-2L W 차이율 최대 % · D … · C …」."""
    cells = [
        f"{_LOAD_KEYS.get(name, name)} "
        + (
            _short(result.failure)
            if result.comparison is None
            else _percent(difference_distribution(result.comparison).maximum, 2)
        )
        for name, result in zip(names, results, strict=True)
    ]
    return _note("8-2L", *cells)


def check_legacy(session: Session) -> list[str]:
    lines = _heading("8-2", "기존 결과 대조 — 분포만", "legacy")
    notes = session.notes
    source = load_source(session)
    if source is None:
        notes.append(_note("8-2", f"원천 못 읽음 {session._source_failure}"))
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
        notes.append(_note("8-2", "원천 행 0"))
        return [*lines, "- 원천 행이 없다", ""]
    contract = load_core_data_contract()
    try:
        core = build_q_core_data(raw, contract)
    except Exception as exc:  # 원천이 계약을 어기면 여기서 멈춘다
        notes.append(_note("8-2", f"파생 프레임 {_failure(exc)}"))
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
    load_names: list[str] = []
    for metric in COMPARISONS:
        name, build = LOAD_BUILDERS.get(metric.legacy_column, (metric.label, None))
        label = f"{name} `{metric.legacy_column}`"
        load_names.append(name)
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
    _noted(notes, "8-2L", lambda: [_load_note(load_names, load_results)])

    required = _calculate_required(tables)
    try:
        lines.extend(_wafer_route_section(core, tables, required, grain, contract, notes))
    except Exception as exc:  # 이 절이 멈춰도 소요대수·PCB 절과 다음 블록은 잰다
        notes.append(_note("8-2W", _failure(exc)))
        lines.extend([f"- Wafer `WF수(매)` 경로 값 — {_failure(exc)}", ""])
    lines.extend(
        _requirement_section(
            _with_raw_columns(core, raw, ROUTE_CATEGORIES),
            tables,
            required,
            notes,
            st_reference=partial(load_st_reference, session),
        )
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
        session.notes.append(_note("8-3", f"원천 못 읽음 {session._source_failure}"))
        return [*lines, f"- 원천을 읽지 못함 — {session._source_failure}", ""]
    reqb = source.tables.get("RQ_REQB", pd.DataFrame()).copy()
    lines.extend([f"- {source.dataset_label}", ""])
    if reqb.empty:
        session.notes.append(_note("8-3", "0"))
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
    mixed = int(bases_per_process.gt(1).sum())
    lines.append(
        f"- 그 밖의 소요기준 {others['소요기준'].nunique():,}종 {len(others):,}행 "
        f"{others['공정'].nunique():,}공정(값은 적지 않는다)"
    )
    lines.append(
        f"- 공정 {reqb['공정'].nunique():,}개 가운데 소요기준이 둘 이상인 공정 "
        f"{mixed:,} (업무 규칙상 0 이어야 한다)"
    )
    lines.append("")

    def note() -> list[str]:
        # 「8-3 행 = 소요기준마다 행 + ? 그 밖 · P 공정 · M 소요기준 둘 이상인 공정」.
        by_basis = [f"{basis} {int(reqb['소요기준'].eq(basis).sum()):,}" for basis in KNOWN_BASES]
        terms = " + ".join([*by_basis, f"? {len(others):,}"])
        return [
            _note(
                "8-3",
                f"{len(reqb):,} = {terms}",
                f"P {reqb['공정'].nunique():,}",
                f"M {mixed:,}",
            )
        ]

    _noted(session.notes, "8-3", note)
    return lines


# ---------------------------------------------------------------------------------- 8-9 home

# HOME 월 축을 세우는 `양산구분` 값 — `services/dashboard.build_production_dashboard` 가 이 값의
# 행만 Density 로 세운다. 월 축 자체는 그 함수를 그대로 불러 세우고, 이 값은 빠진 달을 가르는
# 데만 쓴다.
MASS_PRODUCTION: Final = "양산"
_HOME_MONTH_ROWS: Final[tuple[str, ...]] = (
    "HOME 월 축에 서는 달 — 양산 Density 가 있는 달",
    "**계획 달 가운데 양산 Density 없는 달**",
    "└ 양산 계획이 없는 달(ER 등만 있는 달)",
    "└ 양산 계획은 있는데 Density 가 붙지 않은 달",
    "└ 양산 Density 없는 달 가운데 Wafer 부하량이 있는 달(Wafer 계획·Wafer Capa 에서 빠짐)",
    "연간 Total 열이 빠지는 해(계획은 1~12월이 다 있는데 월 축은 아닌 해)",
)


def _months(frame: pd.DataFrame, mask: pd.Series | None = None) -> set[int]:
    months = pd.to_numeric(frame["생산계획년월"], errors="coerce")
    if mask is not None:
        months = months.loc[mask]
    return {int(month) for month in months.dropna()}


def _home_month_column(
    plan_of: Callable[[], pd.DataFrame], tables: dict[str, pd.DataFrame], plan_months: set[int]
) -> list[str]:
    """한 화면(EDP 포함·뺌)의 월 축을 HOME 과 같은 함수로 세우고 빠지는 계획 달을 센다.

    이 블록은 시나리오 전체 기간을, HOME 은 조회기간으로 자른 계획을 계산한다 — 여기서 멈추면
    멈추게 한 행이 조회기간에 들 때 HOME 도 그 화면에서 멈춘다. 칸마다 종류만 적는다(오류 문구에는
    제품 이름이 실린다).
    """
    try:
        plan = plan_of()
        monthly_density, _ = build_production_dashboard(plan, tables["RQ_CHIP_EQ"])
        monthly_wafer = build_monthly_wafer_load_from_load(
            calculate_wafer_load(plan, tables["RQ_YLD"], tables["RQ_CHIP_QTY"])
        )
    except Exception as exc:  # 원천이 계약을 어기면 계산이 멈춘다 — 종류만 적는다
        return [_failure(exc)] * len(_HOME_MONTH_ROWS)
    # 계산 입구와 같이 수량 0 행을 걷는다 — 양산 행이 수량 0 뿐인 달은 「양산 계획이 없는 달」이다.
    planned = drop_unplanned_rows(plan)
    mass = planned["양산구분"].astype("string").str.strip().eq(MASS_PRODUCTION).fillna(False)
    axis = _months(monthly_density)
    missing = plan_months - axis
    with_mass = missing & _months(planned, mass)
    with_wafer = missing & _months(
        monthly_wafer, pd.to_numeric(monthly_wafer["Wafer 부하량"], errors="coerce").gt(0)
    )
    lost_years = set(complete_years(sorted(plan_months))) - set(complete_years(sorted(axis)))
    counts = (len(axis), len(missing), len(missing - with_mass), len(with_mass), len(with_wafer))
    return [_count(value) for value in (*counts, len(lost_years))]


def check_home_months(session: Session) -> list[str]:
    """HOME 월 축은 양산 Density 가 있는 달만 선다(`services/dashboard.py`, 2026-10-22 결정 A —
    그대로 둔다). 그래서 양산 없이 ER 만 있는 달은 Wafer 계획·Wafer Capa·B/N·Top5 에서 빠지고 그 해
    연간 Total 열이 서지 않는다. 실데이터에 그런 달이 있는지 개수로만 잰다 — 달·제품 이름은 찍지
    않는다.

    계획 달은 시나리오 전체 기간에서 센다(HOME 조회기간은 그 일부다). EDP 를 뺀 칸은 HOME 토글을 끈
    화면이다 — 확보율·B/N 은 EDP 를 포함한 전체 계획 그대로라 계획 달도 전체 계획에서 센다.
    """
    lines = _heading("8-9", "HOME 월 축 — 양산 Density 없는 계획 달", "home")
    source = load_source(session)
    if source is None:
        session.notes.append(_note("8-9", f"원천 못 읽음 {session._source_failure}"))
        return [*lines, f"- 원천을 읽지 못함 — {session._source_failure}", ""]
    tables = source.tables
    plan = tables.get("RQ_PKG_PLAN", pd.DataFrame())
    lines.extend([f"- {source.dataset_label}", ""])
    if plan.empty:
        session.notes.append(_note("8-9", "0"))
        return [*lines, "- 리비전 1 의 `RQ_PKG_PLAN` 이 비어 있다", ""]
    plan_months = _months(drop_unplanned_rows(plan))
    full_years = complete_years(sorted(plan_months))
    lines.append(
        "- 계획 달(`RQ_PKG_PLAN` 에 생산수량이 0 보다 큰 행이 있는 달 · 리비전 1 전체 기간) "
        f"{len(plan_months):,} · 그 가운데 1~12월이 다 든 해 {len(full_years):,}"
    )
    columns = (
        _home_month_column(lambda: plan, tables, plan_months),
        _home_month_column(lambda: filter_edp_plan(plan, False), tables, plan_months),
    )
    rows = [[label, *cells] for label, *cells in zip(_HOME_MONTH_ROWS, *columns, strict=True)]
    lines.extend(["", *_table(["달 수", "EDP 포함(기본)", "EDP 뺌(HOME 토글)"], rows), ""])
    shown, hidden = columns
    # 요약 — 「8-9 계획 달 · 포함 없는 달 = 양산 계획 없는 달 + Density 안 붙은 달 · 뺌 없는 달」.
    session.notes.append(
        _note(
            "8-9",
            f"{len(plan_months):,}",
            f"포함 {shown[1]} = {shown[2]} + {shown[3]}",
            f"뺌 {hidden[1]}",
        )
    )
    return lines


# ---------------------------------------------------------------------------------- 8-4 equipment


_PLACEHOLDER_ROW: Final = (
    f"Qual일정 = {LEGACY_QUAL_PLACEHOLDER} (공식 일정 리비전의 원천, 이제 빈 Qual 로 읽음)"
)
_TRUNCATED_ROW: Final = f"**모듈 행 환산비 {TRUNCATED_RATIO}** — 다시 입력할 행"


def check_equipment(session: Session) -> list[str]:
    lines = _heading("8-4", "설비 DB — 옛 Qual 자리표·환산비 0.2·일정 미정·사용기준", "equipment")
    connection = session.equipment
    if connection is None:
        session.notes.append(_note("8-4", f"설비 DB {session.equipment_failure}"))
        return [*lines, f"- 설비 DB — {session.equipment_failure}", ""]
    latest = _latest_equipment_revision(connection)
    if latest is None:
        session.notes.append(_note("8-4", "리비전 0"))
        return [*lines, "- 설비 리비전이 없다(저장한 적이 없다)", ""]
    revision_id, revision_no, contract = latest
    official = session.official_equipment()
    lines.append(f"- 최신 설비 리비전(공통 대장) r{revision_no} · 계약 v{contract}")
    lines.append(
        "- 공식 일정 리비전(일정 칸·비가동은 여기서 센다) — "
        + (_short(official) if isinstance(official, str) else _official_place(official))
    )
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
    # 옛 Qual 자리표는 **레거시 원천 행**에만 있다 — 새 일정 표에는 없다(읽기 투영이 빈칸으로 바꿔
    # 넣는다). 공식 일정 리비전이 이관 리비전이면 그 원천 리비전의 행을 세고, 아니면 0 이다. 0027 전
    # DB(설비 시나리오 표 없음)는 최신 리비전이 곧 원천이다.
    placeholder_source = _placeholder_source(official, revision_id)
    rows.append(
        [
            "최신 리비전 설비 마스터 행",
            _safe_scalar(
                connection, f"SELECT count(*) FROM {master} WHERE revision_id = ?", [revision_id]
            ),
        ]
    )
    rows.append(
        [
            _PLACEHOLDER_ROW,
            _safe_scalar(
                connection,
                f"SELECT count(*) FROM {master} "
                f"WHERE revision_id = ? AND qual_date = {placeholder}",
                [placeholder_source],
            )
            if placeholder_source is not None
            else "0",
        ]
    )
    for label, sql in (
        (
            f"Qual일정 = {LEGACY_QUAL_PLACEHOLDER} (모든 리비전 합)",
            f"SELECT count(*) FROM {master} WHERE qual_date = {placeholder}",
        ),
        (
            f"Qual일정 = {LEGACY_QUAL_PLACEHOLDER} 이 든 리비전",
            f"SELECT count(DISTINCT revision_id) FROM {master} WHERE qual_date = {placeholder}",
        ),
    ):
        rows.append([label, _safe_scalar(connection, sql)])

    module = "nullif(trim(parent_equipment_id), '') IS NOT NULL"
    ratio_is = "abs(conversion_ratio - {value}) < 1e-9"
    for label, condition in (
        ("모듈 행(Main 설비 있음)", module),
        (f"모듈 행 환산비 {MODULE_RATIO}", f"{module} AND {ratio_is.format(value=MODULE_RATIO)}"),
        (
            _TRUNCATED_ROW,
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
    lines.extend(_undated_lines(connection, official, placeholder_source))
    lines.append("")
    facts: dict[str, str] = {}
    lines.extend(_column_shape_lines(connection, revision_id, facts, official=official))
    migration: dict[str, str] = {}
    lines.extend(_scenario_migration_lines(connection, official, migration))
    counted = dict((label, value) for label, value in rows)

    def note() -> list[str]:
        # 「8-4 r공식 · M 마스터 행 = Qual상태마다 + 빈 + ? · T 환산비 0.2 · Q 자리표 · D 개편 전 두
        # 날짜」. r 은 공식 일정 리비전 번호다 — 공통만 저장해도(공통 rN+1) 일정 쪽 수와 이 줄이
        # 그대로다(이관 직후 공식 「운영 일정」 rK 는 옛 rK 와 같은 번호다). 0027 전 DB 는 최신
        # 리비전 번호다.
        statuses = [
            f"{status} {facts[f'Qual상태 {status}']}" for status in QUAL_CONFIRMATION_STATUSES
        ]
        terms = " + ".join(
            [*statuses, f"빈 {facts['Qual상태 빈 칸']}", f"? {facts['Qual상태 그 밖']}"]
        )
        shown_no = (
            official.schedule_no
            if isinstance(official, OfficialEquipment) and official.schedule_no is not None
            else revision_no
        )
        return [
            _note(
                "8-4",
                f"r{shown_no}",
                f"M {counted['최신 리비전 설비 마스터 행']} = {terms}",
                f"T {counted[_TRUNCATED_ROW]}",
                f"Q {counted[_PLACEHOLDER_ROW]}",
                f"D {facts['개편 전 두 날짜']}",
            ),
        ]

    _noted(session.notes, "8-4", note)
    # 이관 확인 줄은 따로 짓는다 — 8-4 줄이 멈춰도 이 줄은 남는다.
    _noted(session.notes, "8-4s", lambda: [_scenario_migration_note(migration)])
    return lines


def _column_shape_lines(
    connection: duckdb.DuckDBPyConnection,
    revision_id: str,
    facts: dict[str, str] | None = None,
    *,
    official: OfficialEquipment | str | None = None,
) -> list[str]:
    """설비 마스터 38열 개편(2026-10-16)이 기대는 값의 꼴 — 공통 칸은 최신(공통 대장) 리비전의 DB
    컬럼을 직접 세고, 일정 칸(정지일정·반출/이설일정)은 **공식 일정 리비전**을 합쳐 읽은 마스터로
    센다(`official` — 0027 뒤 공통 리비전의 마스터 표에는 일정 칸이 비어 있다). `official` 을 주지
    않거나 0027 전 DB 면 최신 리비전의 DB 컬럼을 센다.

    Area Code(`classification_1`)·공정구분(`line_type`)은 계약이 정한 이름(Main·MI·부대, 공정구분
    여섯)만 이름을 적고, 그 밖의 값은 **종류 수와 행 수**로만 접는다(값을 찍지 않는다). 대조는
    앞뒤 공백을 떼고 대소문자를 가리지 않는다. 빠진 `설비가동현황`(`classification_3`)은 DB 에
    남아 있어 그대로 센다. 정지일정(`removal_date`)·반출/이설일정(`relocation_date`)이 둘 다 있는
    행은 개편 전에는 막혀 있었으므로 **개편 전 마지막 리비전**(설비 마이그레이션 23 을 적용하기 전에
    저장한 리비전 가운데 가장 늦은 것, 23 이 없으면 최신 리비전)에서 0 이어야 한다 — 그 수가 기존
    데이터의 숫자·도면이 바뀌지 않는다는 근거다. 개편 뒤에는 두 날짜를 함께 저장할 수 있으므로 최신
    리비전의 수는 정보 줄로 따로 적는다. 마이그레이션 0023 전에도 돈다(옛 컬럼만 본다).
    """
    master = "equipment_ops.equipment_master_snapshot"
    rows: list[list[str]] = []

    def count(condition: str) -> str:
        return _safe_scalar(
            connection,
            f"SELECT count(*) FROM {master} WHERE revision_id = ? AND ({condition})",
            [revision_id],
        )

    def kinds(condition: str, column: str) -> str:
        return _safe_scalar(
            connection,
            f"SELECT count(DISTINCT trim({column})) FROM {master} "
            f"WHERE revision_id = ? AND ({condition})",
            [revision_id],
        )

    def listed(column: str, names: Sequence[str]) -> str:
        quoted = ", ".join("'" + name.casefold().replace("'", "''") + "'" for name in names)
        return f"lower(trim({column})) IN ({quoted})"

    def blank(column: str) -> str:
        return f"nullif(trim({column}), '') IS NULL"

    for title, column, names in (
        ("Area Code(classification_1)", "classification_1", AREA_CODES),
        ("공정구분(line_type)", "line_type", LINE_TYPE_GROUPS),
    ):
        for name in names:
            rows.append(
                [f"{title} = {name}", count(f"lower(trim({column})) = '{name.casefold()}'")]
            )
        rows.append([f"{title} 빈 칸", count(blank(column))])
        other = f"NOT ({blank(column)}) AND NOT ({listed(column, names)})"
        rows.append([f"{title} 그 밖 — 행 / 종류", f"{count(other)} / {kinds(other, column)}"])
    capa_filled = f"NOT ({blank('investment_capa')})"
    rows.append(
        [
            "투자Capa(investment_capa) 값 있는 행 / 종류 / 빈 칸",
            f"{count(capa_filled)} / {kinds(capa_filled, 'investment_capa')} / "
            f"{count(blank('investment_capa'))}",
        ]
    )
    rows.append(
        [
            "설비가동현황(classification_3, 계약에서 빠짐) 값 있는 행",
            count(f"NOT ({blank('classification_3')})"),
        ]
    )
    schedule = _official_master(official)
    for title, column, contract_column in (
        ("정지일정(removal_date)", "removal_date", STOP_DATE_COLUMN),
        ("반출/이설일정(relocation_date)", "relocation_date", RELOCATION_DATE_COLUMN),
    ):
        if isinstance(schedule, pd.DataFrame):
            dates = pd.to_datetime(schedule[contract_column], errors="coerce")
            before_today = int(dates.lt(pd.Timestamp(date.today())).sum())
            value = f"{int(dates.notna().sum()):,} / {before_today:,}"
        elif isinstance(schedule, str):
            value = schedule
        else:
            value = f"{count(f'{column} IS NOT NULL')} / {count(f'{column} < current_date')}"
        rows.append([f"{title} 값 있는 행 / 오늘 전", value])
    both = "removal_date IS NOT NULL AND relocation_date IS NOT NULL"
    before = _pre_column_overhaul_revision(connection)
    rows.append(
        [
            "개편 전 마지막 리비전(설비 마이그레이션 23 적용 전 저장) 번호",
            before[1] if before else "없음",
        ]
    )
    facts = {} if facts is None else facts
    facts["개편 전 두 날짜"] = (
        _safe_scalar(
            connection,
            f"SELECT count(*) FROM {master} WHERE revision_id = ? AND ({both})",
            [before[0]],
        )
        if before
        else "-"
    )
    rows.append(
        [
            "**개편 전 마지막 리비전의 정지일정·반출/이설일정 둘 다 있는 행** — 0 이어야 함",
            facts["개편 전 두 날짜"],
        ]
    )
    if isinstance(schedule, pd.DataFrame):
        both_mask = schedule[STOP_DATE_COLUMN].notna() & schedule[RELOCATION_DATE_COLUMN].notna()
        both_rows = f"{int(both_mask.sum()):,}"
    elif isinstance(schedule, str):
        both_rows = schedule
    else:
        both_rows = count(both)
    rows.append(
        [
            "공식 일정 리비전의 정지일정·반출/이설일정 둘 다 있는 행 (개편 뒤 저장 가능 — 정보)",
            both_rows,
        ]
    )
    for status in QUAL_CONFIRMATION_STATUSES:
        facts[f"Qual상태 {status}"] = count(f"trim(qual_confirmation_status) = '{status}'")
        rows.append([f"Qual상태(qual_confirmation_status) = {status}", facts[f"Qual상태 {status}"]])
    status_listed = listed("qual_confirmation_status", QUAL_CONFIRMATION_STATUSES)
    facts["Qual상태 빈 칸"] = count(blank("qual_confirmation_status"))
    facts["Qual상태 그 밖"] = count(
        f"NOT ({blank('qual_confirmation_status')}) AND NOT ({status_listed})"
    )
    rows.append(["Qual상태 빈 칸", facts["Qual상태 빈 칸"]])
    rows.append(["Qual상태 그 밖", facts["Qual상태 그 밖"]])
    return [
        "- 38열 개편 컬럼 분포(공통 칸은 최신 리비전, 정지·반출/이설일정은 공식 일정 리비전 — 값은 "
        "찍지 않고 계약 이름만 적는다)",
        "",
        *_table(["항목", "수"], rows),
        "",
    ]


def _pre_column_overhaul_revision(
    connection: duckdb.DuckDBPyConnection,
) -> tuple[str, str] | None:
    """설비 마이그레이션 23(38열 개편)을 적용하기 전에 저장한 가장 늦은 리비전의 (id, 번호 글자).

    23 이 아직 없으면 모든 리비전이 개편 전이라 최신 리비전이다. 리비전이 없거나 읽지 못하면 `None`.
    두 시각은 모두 DuckDB 의 `current_timestamp` 기본값이라 같은 시계로 견준다.
    """
    try:
        row = connection.execute(
            """
            WITH cut AS (
                SELECT min(applied_at) AS applied_at
                FROM equipment_meta.schema_migration
                WHERE version = 23
            )
            SELECT revision_id, revision_no
            FROM equipment_ops.revision, cut
            WHERE cut.applied_at IS NULL OR created_at < cut.applied_at
            ORDER BY revision_no DESC
            LIMIT 1
            """
        ).fetchone()
    except duckdb.Error:
        return None
    if row is None:
        return None
    return str(row[0]), f"{int(row[1]):,}"


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
    connection: duckdb.DuckDBPyConnection,
    official: OfficialEquipment | str,
    placeholder_source: str | None,
) -> list[str]:
    """일정 미정·사용기준 — 공식 설비 시나리오의 **계산 프레임**(그 시나리오에 일정이 없는 호기를
    뺀 것)을 앱 화면과 같은 셈으로 센다. 옛 자리표에서 온 Qual 미정은 레거시 원천 행만 본다."""
    code_max = max((migration.version for migration in load_equipment_migrations()), default=0)
    db_max = max(_versions(connection, "equipment_meta.schema_migration") or [0])
    if db_max < code_max:
        return [
            f"- 일정 미정 — 건너뜀: 설비 DB 마이그레이션이 코드보다 낮다({db_max} < {code_max}). "
            "앱을 띄워 `가용설비 현황` 을 연 뒤 앱을 끄고 다시 돌린다(4-2)."
        ]
    if isinstance(official, str):
        return [f"- 일정 미정 — {_short(official)}"]
    if official.snapshot is None:
        return [f"- 일정 미정 — {official.failure or '-'}"]
    try:
        equipment = official.snapshot.calculation_frames()[1]
        undated = undated_equipment(equipment)
    except Exception as exc:  # 검증 오류 문구는 설비명을 싣는다. 종류만 적는다
        return [f"- 일정 미정 — {_failure(exc)}"]
    usage_line = _usage_basis_line(equipment)
    counts = undated_counts(undated)
    rows_by_kind = {
        kind: int(undated[UNDATED_KIND_COLUMN].eq(kind).sum()) for kind in UNDATED_KINDS
    }
    parts = " · ".join(
        f"{kind} {format_unit_count(counts[kind])}대({rows_by_kind[kind]:,}행)"
        for kind in UNDATED_KINDS
    )
    placeholder_units = 0
    if placeholder_source is not None:
        try:
            placeholder_ids = {
                str(row[0])
                for row in connection.execute(
                    "SELECT equipment_id FROM equipment_ops.equipment_master_snapshot "
                    f"WHERE revision_id = ? AND qual_date = DATE '{LEGACY_QUAL_PLACEHOLDER}'",
                    [placeholder_source],
                ).fetchall()
            }
        except duckdb.Error:
            placeholder_ids = set()
        qual_rows = undated.loc[undated[UNDATED_KIND_COLUMN].eq(UNDATED_KINDS[1])]
        placeholder_units = int(
            qual_rows[EQUIPMENT_ID_COLUMN].astype("string").isin(placeholder_ids).sum()
        )
    return [
        f"- 일정 미정(`services/undated_equipment.py`, 화면 알림과 같은 셈 — 공식 설비 시나리오) — "
        f"{parts}",
        f"- 그 가운데 Qual 미정 행이 옛 자리표 {LEGACY_QUAL_PLACEHOLDER} 에서 온 것 "
        f"{placeholder_units:,}행",
        usage_line,
    ]


def _official_master(official: OfficialEquipment | str | None) -> pd.DataFrame | str | None:
    """일정 칸을 셀 마스터 — 공식 합친 스냅샷(39칸). 0027 전이거나 주지 않았으면 None(옛 길), 합친
    읽기가 막혔으면 그 실패 글."""
    if not isinstance(official, OfficialEquipment):
        return None
    if official.snapshot is None:
        return official.failure or "-"
    return official.snapshot.equipment


def _placeholder_source(official: OfficialEquipment | str, latest_revision_id: str) -> str | None:
    """옛 Qual 자리표를 셀 레거시 원천 리비전 — 공식 일정 리비전이 이관 리비전이면 그 원천, 새
    리비전이면 None(새 표에는 자리표가 없다). 0027 전 DB(설비 시나리오 표 없음)는 최신
    리비전이다."""
    if isinstance(official, OfficialEquipment):
        return official.legacy_revision_id
    return latest_revision_id


def _scenario_migration_lines(
    connection: duckdb.DuckDBPyConnection,
    official: OfficialEquipment | str,
    facts: dict[str, str],
) -> list[str]:
    """설비 시나리오 이관(0027) 확인 줄 — 시나리오 수, 이관 시나리오 리비전 수와 그 가운데 이관 수,
    이관 전 설비 리비전 수(경계 1행), 공식, 옛 배포 흔적, 공식 리비전의 일정 없음·고아 일정 행.

    이관 직후에는 시나리오 1 · 이관 리비전 = 이관 전 리비전 · 공식 v1 → 마지막 이관 리비전 ·
    흔적 0 · 일정 없음 0 · 고아 0 이다. 시나리오 이름은 사용자가 지은 값이라 찍지 않는다.
    """
    if isinstance(official, str):
        facts["skip"] = _short(official)
        return [f"- 설비 시나리오 이관 확인 — {_short(official)}", ""]

    def scalar(sql: str) -> str:
        return _safe_scalar(connection, sql)

    facts["S"] = scalar("SELECT count(*) FROM equipment_ops.equipment_scenario")
    migrated = f"equipment_scenario_id = '{OPERATIONS_SCENARIO_ID}'"
    facts["L"] = scalar(
        "SELECT count(*) FROM equipment_ops.equipment_schedule_revision "
        f"WHERE {migrated} AND origin = 'legacy'"
    )
    facts["all"] = scalar(
        f"SELECT count(*) FROM equipment_ops.equipment_schedule_revision WHERE {migrated}"
    )
    facts["N"] = scalar(
        "SELECT coalesce((SELECT through_revision_no FROM equipment_ops.equipment_legacy_boundary "
        "ORDER BY boundary_no LIMIT 1), 0)"
    )
    try:
        facts["X"] = f"{legacy_trace_count(connection):,}"
    except duckdb.Error as exc:
        facts["X"] = _failure(exc)
    facts["O"] = (
        f"v{official.release_no}→r{official.schedule_no}"
        if official.release_no is not None and official.schedule_no is not None
        else "-"
    )
    snapshot = official.snapshot
    facts["U"] = f"{len(snapshot.unscheduled_units):,}" if snapshot is not None else "-"
    facts["G"] = f"{snapshot.orphan_rows:,}" if snapshot is not None else "-"
    layout = _layout_overlay_counts(connection)
    facts["Y"] = layout["units"]
    rows = [
        ["설비 시나리오", facts["S"]],
        [
            "이관 시나리오(operations) 리비전 / 그 가운데 이관(legacy)",
            f"{facts['all']} / {facts['L']}",
        ],
        ["이관 전 설비 리비전(이관 경계 1행) — 이관 리비전 수와 같아야 함", facts["N"]],
        ["공식", _official_place(official)],
        ["**경계 뒤 계약 v3 공통(옛 배포로 저장한 흔적)** — 0 이어야 함", facts["X"]],
        [
            "공식 일정 리비전의 일정 없음 호기 / 고아 일정 행(이관 직후 0)",
            f"{facts['U']} / {facts['G']}",
        ],
        [
            "가정 배치 차이(0031 — ACTIVE 시나리오 최신의 저장된 행): 시나리오 / 호기 / 요소 / "
            "이름표",
            f"{layout['scenarios']} / {layout['units']} / {layout['marks']} / {layout['labels']}",
        ],
        [
            "**배치 옛 코드 흔적(차이가 있는 리비전 뒤 지문 없이 저장된 리비전)** — 0 이어야 함",
            layout["traces"],
        ],
    ]
    return ["- 설비 시나리오 이관 확인(0027)", "", *_table(["항목", "수"], rows), ""]


def _layout_overlay_counts(connection: duckdb.DuckDBPyConnection) -> dict[str, str]:
    """가정 배치 차이(설비 0031) 셈 — ACTIVE 설비 시나리오 최신마다 저장된 호기·요소·이름표 차이 행
    수의 합과 그런 시나리오 수, 옛 코드 흔적(0031 을 모르는 옛 판이 차이 있는 리비전 뒤에 저장한
    리비전) 수. 앱의 목록 투영(`scenario_rows`)을 그대로 읽는다 — 값·이름은 찍지 않는다. 0031 직후는
    모두 0 이다."""
    try:
        listed = [row for row in scenario_rows(connection) if row["status"] == "ACTIVE"]
    except duckdb.Error as exc:
        failed = _failure(exc)
        return dict.fromkeys(("scenarios", "units", "marks", "labels", "traces"), failed)

    def total(column: str) -> int:
        return sum(int(str(row[column] or 0)) for row in listed)

    differing = sum(
        1
        for row in listed
        if int(str(row["latest_layout_unit_count"] or 0))
        + int(str(row["latest_layout_mark_count"] or 0))
        + int(str(row["latest_layout_label_count"] or 0))
    )
    return {
        "scenarios": f"{differing:,}",
        "units": f"{total('latest_layout_unit_count'):,}",
        "marks": f"{total('latest_layout_mark_count'):,}",
        "labels": f"{total('latest_layout_label_count'):,}",
        "traces": f"{total('layout_trace_count'):,}",
    }


def _scenario_migration_note(facts: dict[str, str]) -> str:
    """요약의 8-4s — 「8-4s S1 · L3/3 · O v1→r3 · X0 · U0 · G0 · Y0」(시나리오 · 이관 리비전/이관 전
    리비전 · 공식 · 흔적 · 일정 없음 · 고아 · 가정 배치 차이 호기 행). 끝 `Y` 는 설비 0031 뒤에
    더했다 — `--check-summary` 는 수만 셈하므로 `Y` 가 없는 옛 요약 줄도 그대로 받는다."""
    if "skip" in facts:
        return _note("8-4s", facts["skip"])
    return _note(
        "8-4s",
        f"S{facts['S']}",
        f"L{facts['L']}/{facts['N']}",
        f"O {facts['O']}",
        f"X{facts['X']}",
        f"U{facts['U']}",
        f"G{facts['G']}",
        f"Y{facts['Y']}",
    )


def _usage_basis_line(equipment: pd.DataFrame) -> str:
    """세는 사용기준(HBM·EDP)마다의 행 수와 가용대수에서 빠지는 설비 대수.

    설비 일정 기준 가용대수는 사용기준이 HBM·EDP 인 호기만 센다(2026-10-08 사용자 결정).
    사용기준을 비워 둔 옛 리비전은 그 결정으로 가용대수에서 빠지므로 배포마다 이 수를 받아 본다.
    세는 값은 계약 상수라 이름을 적고, 그 밖의 값(사용기준 글자)은 찍지 않고 `다른 값` 으로
    접는다.
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
        "- 사용기준(`equipment_contract.counts_for_capacity`, 설비 일정 기준 가용대수는 "
        f"{'·'.join(COUNTED_USAGE_BASIS)} 만 센다) — {counted_parts} · 다른 값 {other_rows:,}행 · "
        f"빈 칸 {blank_rows:,}행 / 가용대수에서 빠지는 설비 {format_unit_count(excluded_units)}대"
        f"(설비 {total_units:,}대 중)"
    )


# ---------------------------------------------------------------------------------- 8-10 census

# 센서스가 보는 리비전. 기본은 시나리오마다 활성 리비전과 공식버전 대상(런북 6-3 a
# `--active-only` 와 같은 묶음)이고, `--census-all-revisions` 면 저장된 모든 리비전이다.
_ACTIVE_REVISIONS: Final = (
    "picked AS (SELECT revision_id FROM app_meta.scenario_revision "
    "WHERE revision_id IN (SELECT active_revision_id FROM app_meta.scenario) "
    "OR revision_id IN (SELECT revision_id FROM app_meta.official_release))"
)
_ALL_REVISIONS: Final = "picked AS (SELECT revision_id FROM app_meta.scenario_revision)"

# 편집 격자가 상한 1 로 받는 값 칸과, 하한 0 으로 받는 값 칸 전부. 격자의 범위는
# `app_pages/reference_data.EDITOR_FORMATS` 다 — 화면 모듈이라 부르지 않고 시험이 맞대 본다.
# Excel 붙여넣기가 그 범위를 거치지 않던 때(사내 리뷰 202610120655 E5)의 값이 저장 리비전에
# 남았을 수 있다.
CENSUS_RATIO_COLUMNS: Final[tuple[tuple[str, str], ...]] = (
    ("RQ_RUN_RATE", "CAPA_RUN_RATE"),
    ("RQ_LOT_RATIO", "Lot 측정률"),
    ("RQ_WF_RATIO", "WF측정률"),
)
CENSUS_VALUE_COLUMNS: Final[tuple[tuple[str, str], ...]] = (
    ("RQ_UPEH", "UPEH"),
    ("RQ_UPEH", "ST"),
    ("RQ_RUN_RATE", "CAPA_RUN_RATE"),
    ("RQ_VITAL", "편중률"),
    ("RQ_LOT_RATIO", "Lot 측정률"),
    ("RQ_WF_RATIO", "WF측정률"),
    ("RQ_RUN_DAY", "RUN_DAY"),
    ("RQ_EQP_OWN", "설비보유"),
    ("RQ_EQP_LENT", "설비대여평가"),
    ("RQ_EQP_AVBL", "가용대수"),
)
# `WF 구분` 칸이 있는 리비전 표 — 계산은 이 칸의 대소문자를 접지 않는다(결정 6).
CENSUS_DIVISION_TABLES: Final[tuple[str, ...]] = (
    "RQ_CHIP_EQ",
    "RQ_CHIP_QTY",
    "RQ_LOT_RATIO",
    "RQ_REQB",
    "RQ_UPEH",
    "RQ_WF_RATIO",
    "RQ_YLD",
)

# 대당 Capa 계산(`unit_capacity.calculate_unit_capacity`)은 효율·편중률·모듈수·RUN_DAY 를 경로에
# 붙인 뒤 **제외를 정하기 전에** 빈 칸을 막는다(결정 7). 이 SQL 은 그 빈 칸 가운데 붙은 경로가 모두
# 뒤에서 빠질 경로(Main UPEH 0 이하 · 효율 0 이하 · 측정률 음수)인 칸을 리비전마다 센다 — 그 칸
# 때문에 그 리비전 계산이 멈춘다. 연결은 계산과 같은 키이고 글자 키는 앞뒤 공백을 떼어 견준다
# (`Area_Name` 은 대소문자도 무시). BOX·PCB 경로는 계산 대상이 아니라 처음부터 뺀다.
_PERFORMANCE_JOIN: Final = (
    '{alias}.revision_id = perf.revision_id AND {alias}."생산계획년월" = perf.m '
    'AND lower(trim({alias}."Area_Name")) = perf.a AND trim({alias}."공정") = perf.p '
    'AND trim({alias}."STEP_SEQ") = perf.s AND trim({alias}."MCP_SEQ") = perf.c '
    'AND trim({alias}."양산구분") = perf.q AND trim({alias}."제품정보") = perf.g '
    'AND trim({alias}."Stack") = perf.k AND trim({alias}."WF 구분") = perf.w'
)
_BLANK_ONLY_ON_DROPPED_ROUTES: Final = """
WITH {picked},
perf AS MATERIALIZED (
    SELECT u.revision_id, u."생산계획년월" AS m, trim(u."공정") AS p, trim(u."양산구분") AS q,
           lower(trim(u."Area_Name")) AS a, trim(u."STEP_SEQ") AS s, trim(u."MCP_SEQ") AS c,
           trim(u."제품정보") AS g, trim(u."Stack") AS k, trim(u."WF 구분") AS w,
           coalesce(lower(trim(u."Area_Name")) = 'main' AND u."UPEH" <= 0, false) AS upeh_out
    FROM rev_data.rq_upeh AS u JOIN picked USING (revision_id)
    WHERE upper(trim(u."소요기준")) NOT IN ('BOX', 'PCB')
),
routes AS MATERIALIZED (
    SELECT perf.revision_id, perf.m, perf.p, perf.q,
           perf.upeh_out
           OR coalesce(rr."CAPA_RUN_RATE" <= 0, false)
           OR coalesce(lr."Lot 측정률" < 0, false)
           OR coalesce(wr."WF측정률" < 0, false) AS dropped
    FROM perf
    LEFT JOIN rev_data.rq_run_rate AS rr
      ON rr.revision_id = perf.revision_id AND rr."생산계획년월" = perf.m
     AND trim(rr."공정") = perf.p AND trim(rr."양산구분") = perf.q
    LEFT JOIN rev_data.rq_lot_ratio AS lr ON {lot_join}
    LEFT JOIN rev_data.rq_wf_ratio AS wr ON {wf_join}
),
datasets AS (
    SELECT r.revision_id, d.dataset_id
    FROM app_meta.scenario_revision AS r JOIN picked USING (revision_id)
    JOIN app_meta.dataset AS d ON d.scenario_id = r.scenario_id
),
cells AS (
    SELECT b.revision_id, bool_and(routes.dropped) AS only_dropped
    FROM rev_data.rq_run_rate AS b JOIN picked USING (revision_id)
    JOIN routes ON routes.revision_id = b.revision_id AND routes.m = b."생산계획년월"
     AND routes.p = trim(b."공정") AND routes.q = trim(b."양산구분")
    WHERE b."CAPA_RUN_RATE" IS NULL
    GROUP BY b.revision_id, b.source_row_no
    UNION ALL
    SELECT b.revision_id, bool_and(routes.dropped)
    FROM rev_data.rq_vital AS b JOIN picked USING (revision_id)
    JOIN routes ON routes.revision_id = b.revision_id AND routes.m = b."생산계획년월"
     AND routes.p = trim(b."공정") AND routes.q = trim(b."양산구분")
    WHERE b."편중률" IS NULL
    GROUP BY b.revision_id, b.source_row_no
    UNION ALL
    SELECT b.revision_id, bool_and(routes.dropped)
    FROM rev_data.rq_run_day AS b JOIN picked USING (revision_id)
    JOIN routes ON routes.revision_id = b.revision_id AND routes.m = b."생산계획년월"
     AND routes.p = trim(b."공정")
    WHERE b."RUN_DAY" IS NULL
    GROUP BY b.revision_id, b.source_row_no
    UNION ALL
    SELECT datasets.revision_id, bool_and(routes.dropped)
    FROM ref_data.rq_module AS b JOIN datasets USING (dataset_id)
    JOIN routes ON routes.revision_id = datasets.revision_id AND routes.p = trim(b."공정")
    WHERE b."모듈수" IS NULL
    GROUP BY datasets.revision_id, b.source_row_no
)
SELECT revision_id, count(*) FROM cells WHERE only_dropped GROUP BY 1
"""


@dataclass(frozen=True)
class CensusScope:
    """센서스가 보는 리비전 묶음 — CTE 한 덩이와 그 리비전 수."""

    picked: str
    revisions: int
    label: str


@dataclass(frozen=True)
class CensusRow:
    """센서스 한 줄. `hit` 은 그 꼴이 하나라도 있는 리비전(또는 데이터셋·설비 리비전) 수다."""

    key: str
    label: str
    basis: str
    unit: str
    scope: str = "리비전"
    hit: int = 0
    seen: int = 0
    count: int = 0
    failure: str | None = None

    def cells(self) -> list[str]:
        if self.failure is not None:
            return [self.key, self.label, self.basis, "-", self.failure]
        return [
            self.key,
            self.label,
            self.basis,
            f"{self.hit:,} / {self.seen:,} {self.scope}",
            f"{self.unit} {self.count:,}",
        ]


def _by_owner(
    connection: duckdb.DuckDBPyConnection, sql: str, params: Sequence[object] = ()
) -> Counter[str]:
    """`SELECT 주인, 개수` 결과 → 주인마다 개수(0 은 뺀다)."""
    return Counter(
        {
            str(owner): int(count)
            for owner, count in connection.execute(sql, list(params)).fetchall()
            if count
        }
    )


def _cells_where(
    connection: duckdb.DuckDBPyConnection,
    scope: CensusScope,
    columns: Sequence[tuple[str, str]],
    condition: str,
) -> Counter[str]:
    """리비전 표의 값 칸이 `condition`(`{value}` 자리)에 걸리는 행 수를 리비전마다 더한다."""
    found: Counter[str] = Counter()
    for logical, column in columns:
        value = f't."{column}"'
        found.update(
            _by_owner(
                connection,
                f"WITH {scope.picked} SELECT t.revision_id, count(*) "
                f"FROM rev_data.{REVISION_TABLES[logical]} AS t JOIN picked USING (revision_id) "
                f"WHERE {condition.format(value=value)} GROUP BY 1",
            )
        )
    return found


def _census_key_columns(connection: duckdb.DuckDBPyConnection, table: str) -> list[str]:
    """리비전 표의 키 칸(값 칸 `DOUBLE`·주인·행 번호·`WF 구분` 을 뺀 것).

    글자 칸은 앞뒤 공백을 떼어 견준다 — 계산이 키를 붙이기 전에 하는 것과 같다.
    """
    columns = connection.execute(
        "SELECT column_name, data_type FROM duckdb_columns() "
        "WHERE schema_name = 'rev_data' AND table_name = ? ORDER BY column_index",
        [table],
    ).fetchall()
    keys: list[str] = []
    for name, kind in columns:
        if name in ("revision_id", "source_row_no", "WF 구분") or kind == "DOUBLE":
            continue
        keys.append(f'trim(t."{name}")' if kind == "VARCHAR" else f't."{name}"')
    return keys


def _census_division_case(
    connection: duckdb.DuckDBPyConnection, scope: CensusScope
) -> Counter[str]:
    """`WF 구분` 의 대소문자만 다른 행이 같은 키에 둘 이상 있는 키 수 — 표 일곱의 합."""
    found: Counter[str] = Counter()
    for logical in CENSUS_DIVISION_TABLES:
        table = REVISION_TABLES[logical]
        keys = ", ".join(_census_key_columns(connection, table))
        found.update(
            _by_owner(
                connection,
                f"""
                WITH {scope.picked}
                SELECT revision_id, count(*) FROM (
                    SELECT t.revision_id
                    FROM rev_data.{table} AS t JOIN picked USING (revision_id)
                    GROUP BY t.revision_id, {keys}, lower(trim(t."WF 구분"))
                    HAVING count(DISTINCT trim(t."WF 구분")) > 1
                ) GROUP BY 1
                """,
            )
        )
    return found


def _picked_revisions(connection: duckdb.DuckDBPyConnection, scope: CensusScope) -> list[str]:
    return [
        str(row[0])
        for row in connection.execute(
            f"WITH {scope.picked} SELECT revision_id FROM picked ORDER BY 1"
        ).fetchall()
    ]


def _census_route_folds(connection: duckdb.DuckDBPyConnection, scope: CensusScope) -> Counter[str]:
    """`RQ_REQB` 에서 계산이 앞 행과 같은 경로로 접는 행 가운데 글자 그대로는 다른 행.

    접는 규칙은 등록·계산과 같은 `frame_contracts.duplicate_route_rows` 다(앞뒤 공백 · 소요기준
    `WAFER` · `Area_Name` 대소문자). 리비전마다 따로 읽어 한 번에 한 리비전만 메모리에 둔다.
    """
    columns = ", ".join(f'"{column}"' for column in REQB_COLUMNS)
    found: Counter[str] = Counter()
    for revision_id in _picked_revisions(connection, scope):
        frame = connection.execute(
            f"SELECT {columns} FROM rev_data.rq_reqb WHERE revision_id = ?", [revision_id]
        ).fetch_df()
        folded = duplicate_route_rows(frame, REQB_COLUMNS) & ~frame.duplicated(subset=REQB_COLUMNS)
        if folded.any():
            found[revision_id] = int(folded.sum())
    return found


def _census_blank_capacity(
    connection: duckdb.DuckDBPyConnection, scope: CensusScope
) -> Counter[str]:
    return _by_owner(
        connection,
        _BLANK_ONLY_ON_DROPPED_ROUTES.format(
            picked=scope.picked,
            lot_join=_PERFORMANCE_JOIN.format(alias="lr"),
            wf_join=_PERFORMANCE_JOIN.format(alias="wr"),
        ),
    )


def _census_merge_gaps(connection: duckdb.DuckDBPyConnection, scope: CensusScope) -> CensusCount:
    """월 머지로 만든 시나리오의 리비전마다 첫 달 ~ 끝 달 사이 어느 월 표에도 없는 달."""
    merged = [
        str(row[0])
        for row in connection.execute(
            f"WITH {scope.picked} SELECT r.revision_id "
            "FROM app_meta.scenario_revision AS r JOIN picked USING (revision_id) "
            "JOIN app_meta.dataset AS d ON d.scenario_id = r.scenario_id "
            "WHERE d.source_type = ?",
            [MONTH_MERGE_SOURCE],
        ).fetchall()
    ]
    months_sql = " UNION ".join(
        f'SELECT "생산계획년월" FROM rev_data.{REVISION_TABLES[name]} WHERE revision_id = ?'
        for name in MONTHLY_TABLES
    )
    found: Counter[str] = Counter()
    for revision_id in merged:
        months = [
            int(row[0])
            for row in connection.execute(
                months_sql, [revision_id] * len(MONTHLY_TABLES)
            ).fetchall()
            if row[0] is not None
        ]
        gaps = len(missing_calendar_months(months))
        if gaps:
            found[revision_id] = gaps
    return len(found), len(merged), sum(found.values())


def _census_plan_flag(connection: duckdb.DuckDBPyConnection, scope: CensusScope) -> CensusCount:
    """원천 `계획기초정보여부` 가 앞뒤 공백·대소문자를 무시해도 `Y`·`N` 이 아닌 행(빈 칸 포함).

    본 리비전의 시나리오가 가진 데이터셋 가운데 원천 행이 있는 것(복제는 원천 행이 없다)만 센다.
    """
    rows = connection.execute(
        f"""
        WITH {scope.picked},
        sets AS (
            SELECT DISTINCT d.dataset_id
            FROM app_meta.scenario_revision AS r JOIN picked USING (revision_id)
            JOIN app_meta.dataset AS d ON d.scenario_id = r.scenario_id
        )
        SELECT c.dataset_id, count(*) FILTER (
            WHERE upper(trim(coalesce(c."계획기초정보여부", ''))) NOT IN ('Y', 'N')
        )
        FROM raw_data.core_data AS c JOIN sets USING (dataset_id)
        GROUP BY 1
        """
    ).fetchall()
    return sum(1 for _, count in rows if count), len(rows), sum(int(count) for _, count in rows)


def _census_equipment_names(connection: duckdb.DuckDBPyConnection) -> CensusCount:
    """설비 마스터에서 앞뒤 공백·대소문자만 다른 설비명 묶음 — 수는 최신 리비전의 묶음 수."""
    found = _by_owner(
        connection,
        """
        SELECT revision_id, count(*) FROM (
            SELECT revision_id FROM equipment_ops.equipment_master_snapshot
            GROUP BY revision_id, lower(trim(equipment_id))
            HAVING count(DISTINCT equipment_id) > 1
        ) GROUP BY 1
        """,
    )
    seen = _scalar(connection, "SELECT count(*) FROM equipment_ops.revision")
    latest = _latest_equipment_revision(connection)
    return len(found), seen, 0 if latest is None else found.get(latest[0], 0)


class _NotOpened(Exception):
    """센서스 줄이 볼 DB 를 열지 못했다 — 문구는 이 스크립트가 지은 것뿐이다."""


def _opened(connection: duckdb.DuckDBPyConnection | None, label: str) -> duckdb.DuckDBPyConnection:
    if connection is None:
        raise _NotOpened(f"{label} 를 열지 못함")
    return connection


CensusCount = tuple[int, int, int]
CensusRun = Callable[[Session, CensusScope], CensusCount]


@dataclass(frozen=True)
class CensusItem:
    """센서스 한 줄의 정의 — `run` 은 (걸린 수, 본 수, 꼴의 수) 를 돌려준다.

    `key`(C1 ~)는 전송용 요약이 이 줄을 가리키는 이름이다 — 줄을 더할 때는 끝에 새 번호로 더하고
    지운 번호를 다시 쓰지 않는다(옮겨 적은 지난 리뷰와 견준다). `basis` 는 이 수가 근거가 되는
    `docs/TODO.md` 결정과 그 가운데 잰 부분이다 — 수가 0 이어도 결정을 닫지는 않는다(사외가
    사용자에게 묻는다).
    """

    key: str
    label: str
    basis: str
    unit: str
    run: CensusRun
    scope: str = "리비전"

    def measure(self, session: Session, scope: CensusScope) -> CensusRow:
        row = CensusRow(
            key=self.key, label=self.label, basis=self.basis, unit=self.unit, scope=self.scope
        )
        try:
            hit, seen, count = self.run(session, scope)
        except _NotOpened as exc:
            return replace(row, failure=str(exc))
        except Exception as exc:  # 한 줄이 멈춰도 다음 줄은 센다. 문구는 찍지 않는다
            return replace(row, failure=_failure(exc))
        return replace(row, hit=hit, seen=seen, count=count)


def _per_revision(count: Callable[..., Counter[str]], *args: object) -> CensusRun:
    """리비전마다 센 수 → (걸린 리비전, 본 리비전, 합)."""

    def run(session: Session, scope: CensusScope) -> CensusCount:
        found = count(_opened(session.simulation, "시뮬레이션 DB"), scope, *args)
        return len(found), scope.revisions, sum(found.values())

    return run


def _on_simulation(
    count: Callable[[duckdb.DuckDBPyConnection, CensusScope], CensusCount],
) -> CensusRun:
    return lambda session, scope: count(_opened(session.simulation, "시뮬레이션 DB"), scope)


# 센서스 줄 차례. 근거는 `docs/TODO.md` 「사내 리뷰 `202610120655` 후속 — 사용자 결정 대기」 의
# 번호와 그 리뷰의 결함 ID, 괄호는 그 결정 가운데 이 줄이 재는 부분이다 — 결정 7·9·10 처럼 권장이
# 「지금대로」 가 아닌 결정도 있고, 센서스가 그 결정 전부를 재지도 않는다. 「참고 · 고침」 은 결정
# 없이 이미 고친 것의 남은 꼴이다. 결정 6·9 는 옛 리비전이 대상이라 기본(활성·공식) 범위의 0 은
# 근거가 되지 못한다.
_OLD_REVISIONS: Final = " — 옛 리비전은 `--census-all-revisions` 일 때만"
CENSUS_ITEMS: Final[tuple[CensusItem, ...]] = (
    CensusItem(
        "C1",
        "효율·측정률 1 초과(`CAPA_RUN_RATE`·`Lot 측정률`·`WF측정률`)",
        "근거 · 결정 8(E5 범위 밖 값)",
        "칸",
        _per_revision(_cells_where, CENSUS_RATIO_COLUMNS, "{value} > 1"),
    ),
    CensusItem(
        "C2",
        "편집 값 칸 음수(UPEH·ST·효율·편중률·측정률·RUN_DAY·보유·대여평가·가용)",
        "근거 · 결정 8(E5 범위 밖 값)",
        "칸",
        _per_revision(_cells_where, CENSUS_VALUE_COLUMNS, "{value} < 0"),
    ),
    CensusItem(
        "C3",
        "`RQ_RUN_DAY` 0 칸",
        "참고 · 고침 E2",
        "칸",
        _per_revision(_cells_where, (("RQ_RUN_DAY", "RUN_DAY"),), "{value} = 0"),
    ),
    CensusItem(
        "C4",
        "`RQ_PKG_PLAN` 빈 생산수량",
        "참고 · 고침 P5",
        "행",
        _per_revision(_cells_where, (("RQ_PKG_PLAN", "생산수량"),), "{value} IS NULL"),
    ),
    CensusItem(
        "C5",
        "빈 보유대수(`RQ_EQP_OWN`)",
        "근거 · 결정 8(P7 빈 보유대수)",
        "칸",
        _per_revision(_cells_where, (("RQ_EQP_OWN", "설비보유"),), "{value} IS NULL"),
    ),
    CensusItem(
        "C6",
        "빈 대여평가(`RQ_EQP_LENT`)",
        "근거 · 결정 8(P7 빈 대여평가)",
        "칸",
        _per_revision(_cells_where, (("RQ_EQP_LENT", "설비대여평가"),), "{value} IS NULL"),
    ),
    CensusItem(
        "C7",
        "같은 키에 `WF 구분` 대소문자만 다른 행이 둘 이상(표 일곱)",
        f"근거 · 결정 6(P8 대소문자 겹침{_OLD_REVISIONS})",
        "키",
        _per_revision(_census_division_case),
    ),
    CensusItem(
        "C8",
        "`RQ_REQB` 에서 계산이 앞 행과 같은 경로로 접는, 표기만 다른 행",
        "근거 · 결정 8(P4 표기만 다른 경로)",
        "행",
        _per_revision(_census_route_folds),
    ),
    CensusItem(
        "C9",
        "효율·편중률·모듈수·RUN_DAY 빈 칸 가운데 붙은 경로가 모두 뒤에서 빠질 칸",
        "근거 · 결정 7(P6 빈 칸 꼴의 규모)",
        "칸",
        _per_revision(_census_blank_capacity),
    ),
    CensusItem(
        "C10",
        "월 머지 리비전의 달력 공백 달(첫 달 ~ 끝 달 사이 어느 월 표에도 없는 달)",
        f"근거 · 결정 9(D6 빈 달{_OLD_REVISIONS})",
        "달",
        _on_simulation(_census_merge_gaps),
        scope="머지 리비전",
    ),
    CensusItem(
        "C11",
        "원천 `계획기초정보여부` 의 `Y`·`N` 밖 표기(빈 칸 포함)",
        "근거 · 사내 확인 요청(P8 표기)",
        "행",
        _on_simulation(_census_plan_flag),
        scope="원천 데이터셋",
    ),
    CensusItem(
        "C12",
        "앞뒤 공백·대소문자만 다른 설비명 묶음(설비 DB · 수는 최신 리비전)",
        "근거 · 결정 10(Q6·Q7 이름 대소문자)",
        "묶음",
        lambda session, _scope: _census_equipment_names(_opened(session.equipment, "설비 DB")),
        scope="설비 리비전",
    ),
)


def _census_scope(connection: duckdb.DuckDBPyConnection, all_revisions: bool) -> CensusScope:
    picked = _ALL_REVISIONS if all_revisions else _ACTIVE_REVISIONS
    count = _scalar(connection, f"WITH {picked} SELECT count(*) FROM picked")
    label = (
        "저장된 모든 리비전(`--census-all-revisions`)"
        if all_revisions
        else "시나리오마다 활성 리비전과 공식버전 대상(6-3 a `--active-only` 와 같은 묶음)"
    )
    return CensusScope(picked=picked, revisions=count, label=label)


_CENSUS_HEADERS: Final = ("키", "항목", "근거 — 결정(잰 부분)", "걸림 / 봄", "수")


def _census_notes(
    scope: CensusScope, rows: Sequence[CensusRow], *, all_revisions: bool
) -> list[str]:
    """요약의 8-10 — 머리 한 줄과 0 이 아닌 줄·멈춘 줄만 꼬리표(키)와 함께 한 줄씩.

    머리의 `0 아님 k` 는 아래 나열한 수 줄의 개수, `합` 은 그 수의 합이다 — 옮겨 적다 줄 하나를
    빼거나 겹쳐 적으면 둘 가운데 하나가 어긋난다(`check_transcript`). 다 세어 모두 0 이면 머리 한
    줄뿐이다.
    """
    head = f"{'전부' if all_revisions else '활성'} {scope.revisions:,}"
    total = len(CENSUS_ITEMS)
    counted = [row for row in rows if row.failure is None]
    nonzero = [row for row in counted if row.count]
    failed = [row for row in rows if row.failure is not None]
    if not nonzero and not failed and len(rows) == total:
        return [_note("8-10", head, f"모두 0 ({total}/{total})")]
    parts = [head, f"0 아님 {len(nonzero)}/{len(rows)}"]
    if failed:
        parts.append(f"실패 {len(failed)}")
    if len(rows) < total:
        parts.append(f"중단 잰 {len(rows)}/{total}")
    parts.append(f"합 {sum(row.count for row in nonzero):,}")
    return [
        _note("8-10", *parts),
        *(_note(f"8-10 {row.key}", f"{row.count:,}") for row in nonzero),
        *(_note(f"8-10 {row.key}", str(row.failure)) for row in failed),
    ]


def iter_census(session: Session, *, all_revisions: bool = False) -> Iterator[list[str]]:
    """8-10 을 줄마다 내준다 — 한 줄이 끝나는 대로 찍혀 중간에 멈춰도 앞 줄은 남는다.

    「지금대로」 로 정한 결정(`docs/TODO.md` 사내 리뷰 `202610120655` 후속 결정 대기)마다 그 꼴이
    저장 리비전에 몇 개 있는지 **개수만** 센다. 수는 결정의 근거일 뿐이다 — 0 이어도 결정을 닫는
    것은 사외가 사용자에게 「지금대로」 로 닫을지 물은 뒤다. BigDataQuery 조회가 있어야 하는 것(PSM
    코드의 주차 꼴 등)은 넣지 않는다. 요약 줄은 멈춰도(`Ctrl+C`·시간 제한) 잰 데까지 쌓는다.
    """
    started = time.perf_counter()
    lines = _heading("8-10", "센서스 — 「지금대로」 결정의 실데이터 유병률", "census")
    connection = session.simulation
    if connection is None:
        session.notes.append(_note("8-10", f"시뮬레이션 DB {session.simulation_failure}"))
        yield [*lines, f"- 시뮬레이션 DB — {session.simulation_failure}", ""]
        return
    try:
        scope = _census_scope(connection, all_revisions)
    except duckdb.Error as exc:
        session.notes.append(_note("8-10", f"리비전 목록 {_failure(exc)}"))
        yield [*lines, f"- 리비전 목록을 읽지 못함 — {_failure(exc)}", ""]
        return
    rows: list[CensusRow] = []
    try:
        yield [
            *lines,
            f"- 본 리비전 {scope.revisions:,} — {scope.label}",
            "- 개수만 센다(값·이름은 찍지 않는다). `키` 는 전송용 요약이 이 줄을 가리키는 "
            "이름, `근거` 는 `docs/TODO.md` 「사내 리뷰 `202610120655` 후속 — 사용자 결정 "
            "대기」 의 번호 · 그 리뷰의 결함 ID 와 그 결정 가운데 이 줄이 재는 부분이다"
            "(「참고 · 고침」 은 이미 고친 것의 남은 꼴).",
            "",
            *_table(_CENSUS_HEADERS, []),
        ]
        for item in CENSUS_ITEMS:
            row = item.measure(session, scope)
            rows.append(row)
            yield ["| " + " | ".join(row.cells()) + " |"]
        yield [
            "",
            "- 읽는 법 — `걸림 / 봄` 은 그 꼴이 하나라도 있는 리비전(또는 데이터셋 · 설비 "
            "리비전) 수 / 본 수, `수` 는 그 꼴의 칸 · 키 · 행 · 달 · 묶음 수다(설비명 묶음만 최신 "
            "리비전의 수). 수는 결정의 근거일 뿐이다 — **0 이어도 결정을 닫지 않는다.** 사외가 "
            "사용자에게 「지금대로」 로 닫을지 묻는다. 결정 6 · 9 는 옛 리비전이 대상이라 "
            "`--census-all-revisions` 로 센 0 만 근거가 된다. 에이전트는 판정하지 않고 수만 "
            "옮긴다.",
            f"- 걸린 시간 {time.perf_counter() - started:.1f}초",
            "",
        ]
    finally:
        session.notes.extend(_census_notes(scope, rows, all_revisions=all_revisions))


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
    # 패키지 예외는 어댑터가 감싸 올린다 — 감싸기 전 사슬의 종류 이름과 갈래(시간 초과·연결·
    # SQL, 문구 낱말로 가른 추정)를 적는다. 「Error」 하나로는 시간 초과인지 가를 수 없었다
    # (사내 리뷰 202610200720).
    if isinstance(exc, BigDataQueryCallError):
        names, kind = exc.type_names, exc.kind
    else:
        names, kind = failure_type_names(exc), classify_query_failure(exc)
    return f"조회 실패({' ← '.join(names)} · {kind})"


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
        # 실패까지 걸린 초도 적는다 — 패키지의 시간 제한에 닿았는지 가르는 실마리다.
        return CatalogRun(
            label=label,
            window=window,
            failure=_bdq_failure(exc),
            seconds=time.perf_counter() - started,
        )
    return CatalogRun(
        label=label, window=window, frame=frame, seconds=time.perf_counter() - started
    )


def _catalog_row(run: CatalogRun) -> list[str]:
    if run.frame is None:
        return [
            run.label,
            f"{run.window.days}일",
            run.failure or "-",
            _seconds(run.seconds),
            "-",
            "-",
            "-",
            "-",
        ]
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


def _catalog_note(run: CatalogRun) -> str:
    """전송용 요약의 목록 칸 — 「366일 4행 1.2초」.

    실패면 「366일 조회 실패(종류 · 갈래) 30.0초」 다.
    """
    if run.frame is None:
        return f"{run.window.days}일 {run.failure or '-'} {_seconds(run.seconds)}초"
    return f"{run.window.days}일 {len(run.frame):,}행 {_seconds(run.seconds)}초"


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


def _code_rule_split(codes: pd.Series) -> tuple[list[str], list[str]]:
    """(서로 다른 코드, 그 가운데 규칙을 어긴 코드). 코드는 부르는 쪽이 찍지 않는다."""
    distinct = [str(code) for code in codes.astype("string").fillna("").unique()]
    return distinct, [code for code in distinct if not is_valid_simulation_code(code)]


def describe_codes(codes: pd.Series) -> str:
    """`catb_sim_info_id` 규칙 위반 수와 까닭의 종류. 코드는 찍지 않는다.

    세는 일은 파이썬으로 한다 — pandas 2.2 는 문자열 Series 에 `.map` 을 걸면 참/거짓도
    문자열로 돌려줘 `.sum()` 이 `Cannot perform reduction 'sum' with string dtype` 으로 죽었다
    (사내 리뷰 202610070927·202610071831 의 8-5). 판올림마다 갈리는 dtype 추론에 기대지 않는다.
    """
    distinct, invalid = _code_rule_split(codes)
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


def _code_load_day_notes(loads: CodeLoadDays) -> list[str]:
    """전송용 요약의 전 코드 적재일 줄 — 「8-5D 코드 = 1일 + 2–5일 + 6일 이상」(줄 안 검산)."""
    if loads.failure is not None:
        return [_note("8-5D", loads.failure)]
    spans = list(loads.spans.values())
    one = sum(1 for span in spans if span.days == 1)
    few = sum(1 for span in spans if 2 <= span.days <= 5)
    many = sum(1 for span in spans if span.days >= 6)
    return [_note("8-5D", f"{len(spans):,} = {one:,} + {few:,} + {many:,}")]


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

# RQ 16 표가 원천에서 읽는 칸(`services/reference_transformer.py`). 사본 확인의 「행이 다른
# 키」는 이 칸만 견준다 — 계산에 들지 않는 스냅샷 칸(기준정보년월·설비대여평가DESC·기존 결과
# `WF수(매)` 등)이 적재마다 흔들려도 값 바뀜으로 잡히지 않게 한다. `양산구분` 은 `CS` 에서,
# `가용대수` 는 `설비보유 − 설비대여평가` 에서 나온다. 테스트가 그 모듈의 칸 이름과 대조한다.
RQ_SOURCE_COLUMNS: Final[tuple[str, ...]] = (
    "계획기초정보여부",
    "생산계획년월",
    "CS",
    "제품정보",
    "Stack",
    "Capa Code",
    "Customer",
    "생산수량",
    "제품타입",
    "Pack Code",
    "WF 구분",
    "EDS_수율",
    "BE_수율",
    "구분_Chip",
    "Net Die",
    "구분_EQ",
    "공정",
    "설비보유",
    "설비대여평가",
    "CAPA_RUN_RATE",
    "편중률",
    "모듈수",
    "RUN_DAY",
    "Lot 측정률",
    "WF측정률",
    "Area_Name",
    "STEP_SEQ",
    "MCP_SEQ",
    "소요기준",
    "UPEH",
    "ST",
)


@lru_cache(maxsize=1)
def _numeric_columns() -> frozenset[str]:
    """계약상 숫자 칸(`number`·`integer`). 숫자 정규화는 이 칸에만 한다."""
    return frozenset(
        column.name
        for column in load_core_data_contract().columns
        if column.dtype in {"number", "integer"}
    )


def canonical_values(values: pd.Series, *, numeric: bool) -> pd.Series:
    """한 칸의 값을 견주기 꼴로.

    숫자 칸은 값마다 숫자로 읽어 실수 글자로 맞춘다(정수·실수·숫자 글자·Decimal·참거짓이 날마다
    갈려 와도 같은 값, 빈 글자는 빈 값). 읽히지 않는 값은 글자 그대로 둔다. 글자 칸은 손대지
    않는다 — 숫자처럼 보이는 긴 코드가 실수로 합쳐지지 않게 한다.
    """
    text = values.astype("string")
    if not numeric:
        return text.fillna(_EMPTY)
    text = text.str.strip()
    text = text.mask(text.eq("").fillna(False).astype(bool)).replace({"True": "1", "False": "0"})
    number = pd.to_numeric(text, errors="coerce")
    canonical = number.astype("Float64").astype("string")
    return canonical.where(number.notna(), text).fillna(_EMPTY)


def _signatures(frame: pd.DataFrame, columns: Iterable[str]) -> pd.Series:
    """행마다 `columns` 의 해시(있는 칸만, 이름 순). 값은 남기지 않는다."""
    numeric = _numeric_columns()
    present = sorted({str(column) for column in columns} & {str(c) for c in frame.columns})
    if not present:
        return pd.Series(np.zeros(len(frame), dtype="uint64"), index=frame.index)
    unique = frame.loc[:, ~frame.columns.duplicated()]
    unique.columns = [str(column) for column in unique.columns]
    canonical = pd.DataFrame(
        {column: canonical_values(unique[column], numeric=column in numeric) for column in present},
        index=frame.index,
    )
    return pd.util.hash_pandas_object(canonical, index=False)


def row_signatures(frame: pd.DataFrame) -> pd.Series:
    """행마다 모든 칸의 해시(적재 시각은 상세 SQL 에 없다)."""
    return _signatures(frame, frame.columns)


def _renamed(frame: pd.DataFrame) -> pd.DataFrame:
    """칸 이름을 앱처럼 `SOURCE_COLUMN_MAPPING` 으로 맞춘다(엔진이 별칭을 소문자로 돌려줄 때)."""
    renamed = frame.rename(columns=dict(SOURCE_COLUMN_MAPPING))
    return renamed.loc[:, ~renamed.columns.duplicated()]


def plan_line_key_columns() -> list[str]:
    """계획 줄 키 — `RQ_PKG_PLAN` 업무 키. `양산구분` 은 `CS` 에서 나오는 파생 칸이라 뺀다."""
    keys = load_core_data_contract().derived_keys["RQ_PKG_PLAN"]
    return [key for key in keys if key != "양산구분"]


def finest_key_columns() -> list[str]:
    """가장 잘게 나눈 키 — 계획 줄 키 ∪ 경로 키 13(`Pack Code` 포함).

    원천이 Pack Code 마다 같은 경로를 되풀이하므로 경로 키만으로는 행을 가르지 못한다.
    """
    route = [key for key in REQB_COLUMNS if key != "양산구분"]
    return list(dict.fromkeys([*plan_line_key_columns(), *route]))


def _row_keys(frame: pd.DataFrame, keys: Sequence[str]) -> pd.Series | None:
    """행마다 키 해시. 키 칸이 하나라도 없으면 `None` — 있는 칸만으로 대신 세지 않는다."""
    if any(key not in frame.columns for key in keys):
        return None
    return _signatures(frame, keys)


@dataclass(frozen=True)
class DayLoad:
    """적재일 하루치 — 업무 칸 행 서명, 모든 칸 서명, 키. 값은 담지 않는다.

    `finest` 는 가장 잘게 나눈 키마다 그 키의 업무 칸 행 서명 집합이다(키 칸이 없으면 `None`).
    """

    day: date
    rows: int
    business: frozenset[int]
    full: frozenset[int]
    pairs: frozenset[tuple[int, int]]
    plan_keys: frozenset[int] | None
    finest: dict[int, frozenset[int]] | None


def day_load(day: date, frame: pd.DataFrame) -> DayLoad:
    renamed = _renamed(frame)
    business = _signatures(renamed, RQ_SOURCE_COLUMNS)
    full = row_signatures(renamed)
    plan = _row_keys(renamed, plan_line_key_columns())
    finest_ids = _row_keys(renamed, finest_key_columns())
    finest: dict[int, frozenset[int]] | None = None
    if finest_ids is not None:
        grouped: dict[int, set[int]] = {}
        for key, signature in zip(finest_ids.tolist(), business.tolist(), strict=True):
            grouped.setdefault(int(key), set()).add(int(signature))
        finest = {key: frozenset(values) for key, values in grouped.items()}
    return DayLoad(
        day=day,
        rows=len(renamed),
        business=frozenset(int(value) for value in business.tolist()),
        full=frozenset(int(value) for value in full.tolist()),
        pairs=frozenset(
            (int(b), int(f)) for b, f in zip(business.tolist(), full.tolist(), strict=True)
        ),
        plan_keys=None if plan is None else frozenset(int(value) for value in plan.tolist()),
        finest=finest,
    )


@dataclass(frozen=True)
class DayFacts:
    """고른 날 하나의 사실 — 기준 날과 견준 수. 기준 날 줄은 견준 칸이 `None` 이다.

    키 칸이 없어 셀 수 없는 칸도 `None` 이고 출력에서 「칸 없음」 이 된다(`compared` 로 가른다).
    """

    label: str
    rows: int
    distinct: int
    plan_keys: int | None
    finest_keys: int | None
    conflicts: int | None
    compared: bool = False
    only_day_plan: int | None = None
    only_day_finest: int | None = None
    only_reference_plan: int | None = None
    only_reference_finest: int | None = None
    changed: int | None = None
    other_only: int = 0


def day_facts(label: str, day: DayLoad, reference: DayLoad | None) -> DayFacts:
    """그날을 기준 날과 견준다. `reference` 가 `None` 이면 그날이 기준 날이다."""
    finest = day.finest
    base = DayFacts(
        label=label,
        rows=day.rows,
        distinct=len(day.business),
        plan_keys=None if day.plan_keys is None else len(day.plan_keys),
        finest_keys=None if finest is None else len(finest),
        conflicts=None if finest is None else sum(1 for rows in finest.values() if len(rows) > 1),
    )
    if reference is None:
        return base
    plan_pair = (
        (len(day.plan_keys - reference.plan_keys), len(reference.plan_keys - day.plan_keys))
        if day.plan_keys is not None and reference.plan_keys is not None
        else (None, None)
    )
    finest_pair: tuple[int | None, int | None] = (None, None)
    changed: int | None = None
    if finest is not None and reference.finest is not None:
        mine, theirs = set(finest), set(reference.finest)
        finest_pair = (len(mine - theirs), len(theirs - mine))
        changed = sum(1 for key in mine & theirs if finest[key] != reference.finest[key])
    other_only = sum(
        1
        for business, full in day.pairs
        if business in reference.business and full not in reference.full
    )
    return DayFacts(
        label=label,
        rows=base.rows,
        distinct=base.distinct,
        plan_keys=base.plan_keys,
        finest_keys=base.finest_keys,
        conflicts=base.conflicts,
        compared=True,
        only_day_plan=plan_pair[0],
        only_day_finest=finest_pair[0],
        only_reference_plan=plan_pair[1],
        only_reference_finest=finest_pair[1],
        changed=changed,
        other_only=other_only,
    )


@dataclass(frozen=True)
class CopyDays:
    """사본 확인에서 받을 날 — 날짜 차례로, 기준 날과 오늘(적재 중일 수 있는 날)."""

    picks: tuple[date, ...]
    reference: date
    in_progress: date | None


def pick_copy_days(days: Sequence[date], *, today: date | None, max_days: int) -> CopyDays:
    """받을 날을 고른다 — 기준 날은 늘 든다.

    끝 적재일이 오늘이면 먼저 오늘을 빼고 기준 날을 「오늘 전 마지막 적재일」로 정한다. 남은
    몫은 끝 앞날 → 첫 적재일 → 그 사이 고르게 차례로 채운다. 오늘은 `max_days` 가 3 이상일
    때만 견주는 날로 넣는다.
    """
    ordered = sorted(days)
    in_progress = ordered[-1] if today is not None and ordered[-1] >= today else None
    base = ordered[:-1] if in_progress is not None else ordered
    reference = base[-1]
    budget = max(max_days, 2) - 1
    picks = {reference}
    if in_progress is not None and max_days >= 3:
        picks.add(in_progress)
        budget -= 1
    pool = base[:-1]
    if budget >= 1 and pool:
        picks.add(pool[-1])
    if budget >= 2 and len(pool) >= 2:
        picks.add(pool[0])
    if budget >= 3 and len(pool) >= 3:
        picks.update(_pick_evenly(pool[1:-1], budget - 2))
    return CopyDays(picks=tuple(sorted(picks)), reference=reference, in_progress=in_progress)


def _position_label(day: date, days: Sequence[date], chosen: CopyDays) -> str:
    """실제 자리에서 이름을 만든다 — 그 자리가 아니면 「끝 앞날」 을 붙이지 않는다."""
    ordered = sorted(days)
    base = [value for value in ordered if value != chosen.in_progress]
    if day == chosen.in_progress:
        name = "오늘 — 적재 중일 수 있음"
    elif day == chosen.reference:
        name = "기준 날"
    elif day == base[0]:
        name = "첫 적재일"
    elif len(base) >= 2 and day == base[-2]:
        name = "끝 앞날"
    else:
        name = "가운데"
    return f"{name} ({ordered.index(day) + 1}/{len(ordered)})"


@dataclass
class CopyCheck:
    """여러 날 적재된 코드 하나 — 고른 날마다의 사실. 판정은 내리지 않는다(사외가 한다)."""

    extra: bool
    load_days: int = 0
    day_rows: tuple[int, ...] = ()
    note: str = ""
    days: list[DayFacts] = field(default_factory=list)
    failure: str | None = None


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
    """`window` 안의 적재일을 세고 고른 날(`pick_copy_days`)을 하루씩 받아 기준 날과 견준다.

    하루치는 앱과 같은 상세 SQL 을 그날 하루 창으로 부른 것이다 — 상세 SQL 이 적재 시각으로만
    거르므로 그 창이 곧 그날 적재분이다. `bounded` 가 아니면(전 코드 조회가 없어 등록일 창으로
    셌으면) 기준 날이 창 끝날일 때 그렇게 적는다.
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
    chosen = pick_copy_days(days, today=today, max_days=max_days)
    notes = ["기준 날 = 오늘 전 마지막 적재일" if chosen.in_progress else "기준 날 = 끝 적재일"]
    if chosen.in_progress is not None and chosen.in_progress not in chosen.picks:
        notes.append("오늘 적재는 `--bdq-copy-days` 3 이상에서 견준다")
    if not bounded and chosen.in_progress is None and chosen.reference >= window.end_date:
        notes.append("기준 날이 창 끝날에 닿음(창 밖에도 적재가 있을 수 있다)")
    result.note = " · ".join(notes)
    loads: dict[date, DayLoad] = {}
    try:
        for day in chosen.picks:
            frame = probe.detail_frame(code, QueryWindow(start_date=day, end_date=day))
            loads[day] = day_load(day, frame)
    except Exception as exc:  # 사내 패키지 예외 종류를 모른다
        result.failure = _bdq_failure(exc)
        return result
    reference = loads[chosen.reference]
    result.days = [
        day_facts(
            _position_label(day, days, chosen),
            loads[day],
            None if day == chosen.reference else reference,
        )
        for day in chosen.picks
    ]
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


DAY_FACT_HEADERS: Final = (
    "자리(적재일 차례)",
    "행",
    "고유 행(업무 칸)",
    "계획 줄 키",
    "가장 잘게 나눈 키",
    "그날에만 있는 키 — 계획 줄 · 잘게",
    "기준 날에만 있는 키 — 계획 줄 · 잘게",
    "두 날 모두 있는 키 가운데 행이 다른 키",
    "업무 칸은 같고 그 밖 칸만 다른 행",
    "하루 안 충돌 키",
)
_NO_COLUMNS: Final = "칸 없음"


def _known(value: int | None) -> str:
    return _NO_COLUMNS if value is None else f"{value:,}"


def day_fact_row(facts: DayFacts) -> list[str]:
    head = [
        facts.label,
        f"{facts.rows:,}",
        f"{facts.distinct:,}",
        _known(facts.plan_keys),
        _known(facts.finest_keys),
    ]
    if not facts.compared:
        return [*head, "-", "-", "-", "-", _known(facts.conflicts)]
    return [
        *head,
        f"{_known(facts.only_day_plan)} · {_known(facts.only_day_finest)}",
        f"{_known(facts.only_reference_plan)} · {_known(facts.only_reference_finest)}",
        _known(facts.changed),
        f"{facts.other_only:,}",
        _known(facts.conflicts),
    ]


def _day_rows_cell(values: Sequence[int]) -> str:
    if not values:
        return "-"
    return f"{min(values):,} · {float(np.median(values)):,.0f} · {max(values):,}"


def copy_lines(index: int, check: CopyCheck) -> list[str]:
    """코드 하나의 줄 — 머리 한 줄과 고른 날마다 한 줄의 표. 코드는 번호로만 적는다."""
    head = f"- 코드 {index} · {'여러 날 코드 더함' if check.extra else '표본'}"
    if check.failure is not None:
        return [f"{head} — {check.failure}", ""]
    summary = (
        f"{head} — 적재일 {check.load_days:,}일 · 날별 행 최소 · 중앙 · 최대 "
        + _day_rows_cell(check.day_rows)
    )
    if not check.days:
        return [f"{summary} · 여러 날이 아님", ""]
    return [
        f"{summary} · {check.note}",
        "",
        *_table(DAY_FACT_HEADERS, [day_fact_row(facts) for facts in check.days]),
        "",
    ]


def _summed(values: Iterable[int | None]) -> str:
    """견준 날들의 칸 합. 칸이 없는 날이 하나라도 있으면 「칸 없음」."""
    numbers = list(values)
    if any(value is None for value in numbers):
        return _NO_COLUMNS
    return f"{sum(value for value in numbers if value is not None):,}"


def copy_note(index: int, check: CopyCheck) -> str:
    """전송용 요약의 사본 줄 — 「8-5C1 표본 적재일 · 견준 날 · 그날에만 · 기준 날에만 ·
    행이 다른 키 · 그 밖 칸만 · 하루 안 충돌」.

    네 칸(과 기준 날에만)은 견준 날마다 더한 합이다. 판정은 없다.
    """
    key = f"8-5C{index}"
    kind = "더함" if check.extra else "표본"
    if check.failure is not None:
        return _note(key, f"{kind} {check.failure}")
    compared = [facts for facts in check.days if facts.compared]
    if not compared:
        return _note(key, f"{kind} {check.load_days:,}일", "여러 날 아님")
    return _note(
        key,
        f"{kind} {check.load_days:,}일",
        f"{len(compared):,}",
        _summed(facts.only_day_finest for facts in compared),
        _summed(facts.only_reference_finest for facts in compared),
        _summed(facts.changed for facts in compared),
        _summed(facts.other_only for facts in compared),
        _summed(facts.conflicts for facts in check.days),
    )


def _copy_parts(
    probe: BigDataQueryProbe,
    picked: Sequence[str],
    results: dict[str, SampleResult],
    loads: CodeLoadDays | None,
    *,
    today: date,
    max_codes: int,
    max_days: int,
    notes: list[str] | None = None,
) -> Iterator[list[str]]:
    """사본 확인을 머리와 코드마다 한 조각으로 내준다 — 끝난 코드는 바로 찍힌다."""
    notes = [] if notes is None else notes
    days = max(max_days, 2)
    title = (
        "**여러 날 적재 — 날마다 무엇이 같고 다른가** — 표본의 여러 날 코드(적재일이 많은 순)를 "
        "먼저, 모자라면 전 코드 조회의 여러 날 코드에서 고르게 채워 최대 "
        f"{max_codes}개(코드는 찍지 않는다)를, 기준 날·끝 앞날·첫 적재일·그 사이에서 최대 "
        f"{days}일을 "
        "앱과 같은 상세 SQL 로 하루씩 다시 받아 기준 날과 견준다. **판정은 내리지 않는다 — 수만 "
        "옮기고 사외가 정한다**(칸 뜻은 런북 8-5)."
    )
    if max_codes <= 0 or max_days <= 0:
        notes.append(_note("8-5C", "껐다"))
        yield [
            title,
            "",
            "- 사본 확인은 `--bdq-copy-codes 0` 또는 `--bdq-copy-days 0` 이라 껐다.",
            "",
        ]
        return
    if any(results[code].load_failure for code in picked):
        notes.append(_note("8-5C", "적재일 조회 실패"))
        yield [title, "", "- 적재일 조회가 실패해 건너뛴다.", ""]
        return
    targets = _copy_targets(picked, results, loads, max_codes=max_codes)
    if not targets:
        notes.append(_note("8-5C", "여러 날 코드 0"))
        yield [title, "", "- 여러 날 적재된 코드가 표본에도 전 코드 조회에도 없다.", ""]
        return
    yield [title, ""]
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
        notes.append(copy_note(index, check))
        yield copy_lines(index, check)


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
    notes: list[str] | None = None,
) -> Iterator[list[str]]:
    """8-5 를 조각마다 내준다 — 부르는 쪽이 조각이 끝나는 대로 찍는다.

    `notes` 에는 전송용 요약 줄(목록 · 전 코드 적재일과 그 검산 · 표본 · 사본 코드마다)을 더한다.
    """
    notes = [] if notes is None else notes
    lines = _heading("8-5", "BigDataQuery — 목록·등록일·코드·적재일·사본", "bdq")
    account = (
        "있음" if resolve_user_name() else "없음(Windows 는 없어도 된다 — 로그인 이름으로 묻는다)"
    )
    if probe is None:
        if not is_bigdataquery_package_available():
            notes.append(_note("8-5", "건너뜀 — 패키지 없음"))
            yield [
                *lines,
                "- `bigdataquery` 패키지가 없다 — 사외 PC 이거나 맨 `uv sync` 가 지웠다"
                "(4-1 의 되돌리기). "
                "이 절은 건너뛴다.",
                "",
            ]
            return
        if not (is_bigdataquery_catalog_configured() and is_bigdataquery_adapter_configured()):
            notes.append(_note("8-5", "건너뜀 — SQL 없음"))
            yield [*lines, "- 목록 또는 상세 SQL 이 설정되지 않았다 — 이 절은 건너뛴다.", ""]
            return
        try:
            probe = CompanyProbe()
        except Exception as exc:  # 패키지를 불러오다 실패
            notes.append(_note("8-5", f"패키지 {_bdq_failure(exc)}"))
            yield [*lines, f"- 패키지를 불러오지 못함 — {_bdq_failure(exc)}", ""]
            return
    # 머리말·준비 줄과 목록 표 머리는 조회 전에 내보낸다 — 첫 조회에서 멈춰도 블록 제목이 남는다.
    yield [
        *lines,
        f"- 준비 — 패키지 있음 · SQL 설정됨 · 요청자 계정(`{BDQ_USER_NAME_ENV}`) {account}",
        "",
    ]
    catalog_headers = [
        "목록 조회",
        "기간",
        "결과",
        "초",
        "목록 행(DISTINCT)",
        "코드·PLAN",
        "코드",
        f"코드·PLAN {CATALOG_BUSY_ROWS:,} 넘음",
    ]
    yield _table(catalog_headers, [])
    windows = [
        (
            f"기본(오늘−{CATALOG_DEFAULT_DAYS}일 ~ 오늘)",
            QueryWindow(start_date=today - timedelta(days=CATALOG_DEFAULT_DAYS), end_date=today),
        )
    ]
    if max_window:
        windows.append(
            (
                f"상한 {CATALOG_MAX_DAYS}일",
                QueryWindow(
                    start_date=today - timedelta(days=CATALOG_MAX_DAYS - 1), end_date=today
                ),
            )
        )
    runs: list[CatalogRun] = []
    for label, window in windows:
        runs.append(_run_catalog(probe, label, window))
        yield _table(catalog_headers, [_catalog_row(runs[-1])])[2:]
    widest = next((run for run in reversed(runs) if run.frame is not None), None)
    if widest is None or widest.frame is None:
        notes.append(_note("8-5L", *(_catalog_note(run) for run in runs)))
        yield ["", "- 목록 조회가 모두 실패해 나머지는 건너뛴다.", ""]
        return
    frame = widest.frame
    distinct, invalid = _code_rule_split(frame["simulation_code"])
    # 요약 — 「8-5L 창마다 일·행·초 · 위반 규칙 위반 코드/코드」.
    notes.append(
        _note(
            "8-5L",
            *(_catalog_note(run) for run in runs),
            f"위반 {len(invalid):,}/{len(distinct):,}",
        )
    )
    lines = ["", f"- 아래는 `{widest.label}` 목록 기준"]
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
        notes.extend(_code_load_day_notes(loads))
        yield [*_table(["전 코드 적재일", "값"], _code_load_day_rows(loads)), ""]
    else:
        notes.append(_note("8-5D", "건너뜀"))
        yield ["- 전 코드 적재일 조회는 `--bdq-no-code-days` 라 건너뛰었다.", ""]

    if sample <= 0:
        notes.append(_note("8-5S", "건너뜀"))
        yield [
            "- 표본 적재일 확인과 사본 확인(전 코드 조회로 더하는 코드 포함)은 `--bdq-sample 0` "
            "이라 건너뛰었다.",
            "",
        ]
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
    # 요약 — 「8-5S 기본 창 행 = 넓은 창 행인 코드/잰 코드 · 기본 창이 놓친 행 %」.
    notes.append(
        _note(
            "8-5S",
            f"{same:,}/{len(measured):,}",
            _percent(total_missing / total_wide if total_wide else None, 2),
        )
    )
    yield [*_table(["표본 적재일", "값"], rows), ""]
    yield from _copy_parts(
        probe,
        picked,
        results,
        loads,
        today=today,
        max_codes=copy_codes,
        max_days=copy_days,
        notes=notes,
    )


# ---------------------------------------------------------------------------------- 실행


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="사내 실데이터 확인(읽기 전용). 앱을 끈 뒤 돌린다 — 런북 8장."
    )
    parser.add_argument(
        "--only",
        default=",".join(DEFAULT_CHECKS),
        help=f"돌릴 블록을 쉼표로({', '.join(CHECKS)}). 기본은 BigDataQuery 를 뺀 여섯",
    )
    parser.add_argument("--database", type=Path, default=DUCKDB_PATH, help="시뮬레이션 DuckDB")
    parser.add_argument(
        "--equipment-database", type=Path, default=EQUIPMENT_DUCKDB_PATH, help="설비 DuckDB"
    )
    parser.add_argument("--dataset-id", default=None, help="비우면 가장 최근에 적재한 데이터셋")
    parser.add_argument(
        "--census-all-revisions",
        action="store_true",
        help="8-10 센서스를 저장된 모든 리비전으로 센다(기본은 활성·공식버전 대상 리비전)",
    )
    parser.add_argument(
        "--bdq-sample",
        type=int,
        default=DEFAULT_SAMPLE,
        help="적재일을 볼 표본 코드 수(0 이면 표본 적재일과 사본 확인을 모두 건너뛴다)",
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
    parser.add_argument(
        "--check-summary",
        type=Path,
        default=None,
        metavar="파일",
        help="DB 를 열지 않고, 손으로 옮겨 적은 전송용 요약 줄의 확인 코드·줄 안 검산·8-10 줄 수만 "
        "다시 셈한다(사외가 받은 리뷰 압축본에 돌린다 — 런북 8-6)",
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
    "home": "8-9",
    "census": "8-10",
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
    elif name == "home":
        yield check_home_months(session)
    elif name == "census":
        yield from iter_census(session, all_revisions=args.census_all_revisions)
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
            notes=session.notes,
        )


SUMMARY_HEADING: Final = "### 전송용 요약 (`inspect_real_data_checks.py` — 범례 런북 8-6)"
_INTERRUPTED: Final = "(중단 — 여기까지)"


def summary_lines(notes: Sequence[str], *, interrupted: bool = False) -> list[str]:
    """돌린 블록이 모은 줄을 한 절로 — 블록 출력 뒤에 따로 찍는다. 줄마다 끝에 확인 코드를 단다.

    머리 아래 줄만 옮겨 적는 몫이다 — 읽는 법은 런북 8-6 범례 한 곳에 둔다(요약에 안내문을 두면 옮겨
    적을 줄로 잘못 읽힌다). 멈춘 실행(`Ctrl+C`)이면 머리 바로 아래에 「(중단 — 여기까지)」 를 둔다.
    """
    lines = [SUMMARY_HEADING, ""]
    if interrupted:
        lines.append(_INTERRUPTED)
    lines.extend(f"{note} #{summary_code(_summary_body(note))}" for note in notes)
    return [*lines, ""]


# 옮겨 적은 8-10 — 머리의 `0 아님 k/n` 과 `합 S`, 아래 수 줄(`8-10 C<번호> <수>`). 칸 가름은
# `_CELL_SEP` 꼴이면 된다(손으로 옮기며 가운뎃점을 바꿔 쓴 줄).
_CENSUS_HEAD: Final = re.compile(
    rf"^8-10\s+\S+\s+[\d,]+{_CELL_SEP}0\s*아님\s*(?P<k>\d+)\s*/\s*\d+.*{_CELL_SEP}"
    r"합\s*(?P<sum>[\d,]+)"
)
_CENSUS_ALL_ZERO: Final = re.compile(rf"^8-10\s+\S+\s+[\d,]+{_CELL_SEP}모두\s*0\b")
_CENSUS_ITEM: Final = re.compile(r"^8-10\s+C\s*\d+\s+(?P<count>[\d,]+)\s*$")


def _last_number(text: str) -> float | None:
    numbers = _SUMMARY_NUMBER.findall(text.replace(",", ""))
    return float(numbers[-1]) if numbers else None


def _equations(body: str, *, coded: bool = True) -> Iterator[bool]:
    """줄 안의 `합 = 항 + 항` 식마다 맞는지.

    칸(` · ` — 손으로 옮긴 줄은 `;` · `, ` 도)마다 보고, 수가 아닌 칸(실패 등)은 건너뛴다. 손으로 쓴
    줄(`coded=False`)은 항이 둘 이상인 식만 본다 — `8장 = <stamp> …` 처럼 띄어 쓴 접은 줄을 식으로
    읽지 않게.
    """
    for cell in _CELL_SPLIT.split(body):
        if " = " not in cell:
            continue
        left, right = cell.split(" = ", 1)
        parts = right.split(" + ")
        if not coded and len(parts) < 2:
            continue
        total = _last_number(left)
        terms = [_last_number(term) for term in parts]
        if total is None or any(term is None for term in terms):
            continue
        yield math.isclose(total, sum(cast(float, term) for term in terms))


def check_transcript(lines: Iterable[str]) -> list[str]:
    """손으로 옮겨 적은 리뷰 압축본을 다시 셈한다 — 맞지 않는 것마다 한 줄. 비면 다 맞다.

    넷을 본다. 줄 끝 확인 코드(`#NN`)가 그 줄의 수로 다시 셈한 것과 같은지, 요약 키(`8-…`)로
    시작하는 줄에 확인 코드가 있는지, 줄 안 `합 = 항 + 항` 식이 서는지(손으로 쓴 줄 — 판정 · B ·
    A · 7장요청 같은 것 — 도 항이 둘 이상인 식은 본다), 8-10 머리의 `0 아님 k` · `합 S` 가 그
    아래(다음 8-10 머리 전까지) 수 줄의 개수 · 합과 같은지. 8-10 은 머리마다 따로 센다 — 요약이
    둘 이상 든 파일(다시 돌린 블록을 함께 붙인 리뷰 전문 같은 것)도 본다. 줄 앞의 목록 표지는
    떼고 보고, 칸 가름은 ` · ` 대신 `;` · `, ` 로 바꿔 쓴 것도 같은 칸으로 읽는다.
    """
    problems: list[str] = []
    groups: list[tuple[int, int, int, list[int]]] = []
    for number, raw in enumerate(lines, start=1):
        text = _summary_body(raw)
        coded = _SUMMARY_CODE.match(text)
        body = text if coded is None else coded.group("body")
        if coded is None:
            if _SUMMARY_KEY.match(text):
                problems.append(f"줄 {number} — 8장 요약 줄인데 확인 코드(`#NN`)가 없다")
        elif summary_code(body) != coded.group("code"):
            problems.append(f"줄 {number} — 확인 코드가 맞지 않는다(그 줄의 수를 다시 본다)")
        if not all(_equations(body, coded=coded is not None)):
            problems.append(f"줄 {number} — 줄 안 검산 식이 서지 않는다")
        head = _CENSUS_HEAD.match(body)
        if head is not None:
            groups.append(
                (number, int(head.group("k")), int(head.group("sum").replace(",", "")), [])
            )
        elif _CENSUS_ALL_ZERO.match(body):
            groups.append((number, 0, 0, []))
        item = _CENSUS_ITEM.match(body)
        if item is not None:
            if not groups:
                problems.append(f"줄 {number} — 8-10 수 줄인데 위에 8-10 머리 줄이 없다")
                continue
            groups[-1][3].append(int(item.group("count").replace(",", "")))
    for number, listed, total, items in groups:
        if len(items) != listed or sum(items) != total:
            problems.append(
                f"줄 {number} — 8-10 머리(0 아님 {listed} · 합 {total:,})와 아래 수 줄"
                f"({len(items)}줄 · 합 {sum(items):,})이 다르다 — 줄이 빠졌거나 겹쳤다"
            )
    return problems


def _check_summary(path: Path) -> int:
    """`--check-summary` — 받은 리뷰 압축본 파일을 다시 셈해 맞지 않는 줄 번호만 찍는다.

    값은 찍지 않는다. 맞지 않는 줄이 있거나 확인 코드가 있는 줄이 하나도 없으면 1 이다.
    """
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        print(f"파일을 읽지 못함 — {_failure(exc)}")
        return 2
    coded = sum(1 for line in lines if _SUMMARY_CODE.match(_summary_body(line)))
    problems = check_transcript(lines)
    print(f"확인 코드가 있는 줄 {coded:,} · 맞지 않는 것 {len(problems):,}")
    for problem in problems:
        print(f"- {problem}")
    return 1 if problems or not coded else 0


_HEADER: Final = (
    "<!-- inspect_real_data_checks.py — 아래 블록을 리뷰 문서 "
    "「실데이터 확인」 절에 그대로 붙인다 -->\n"
)


def main(argv: Sequence[str] | None = None, *, probe: BigDataQueryProbe | None = None) -> int:
    _use_utf8_stdout()
    args = parse_args(argv)
    if args.check_summary is not None:
        return _check_summary(Path(args.check_summary))
    # `--output` 은 먼저 비우고 머리 한 줄부터 쓴다 — 일찍 끝나는 길(블록 이름 틀림·DB 잠김)에서도
    # 지난 실행의 파일이 새것처럼 남지 않는다.
    sink = _Sink(None if args.output is None else Path(args.output))
    try:
        sink.emit(_HEADER)
        return _run(args, sink, probe=probe)
    finally:
        sink.close()


def _opens_app_database(session: Session, *, simulation: bool, equipment: bool) -> bool:
    """고른 블록이 앱이 여는 운영 DB 자리를 여는가. 사본만 열면 사용자 앱과 겹치지 않는다.

    판정은 `settings.is_operational_database_place` 다 — 같은 파일(하드링크·긴 경로 접두 포함)·운영
    `data/` 아래·git 저장소 안이면 운영으로 보고 앱 프로세스를 먼저 본다.
    """
    operational = (DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH)
    targets = []
    if simulation:
        targets.append(session.simulation_path)
    if equipment:
        targets.append(session.equipment_path)
    return any(is_operational_database_place(path, operational) for path in targets)


def _run(args: argparse.Namespace, sink: _Sink, *, probe: BigDataQueryProbe | None) -> int:
    selected = [name.strip() for name in str(args.only).split(",") if name.strip()]
    unknown = [name for name in selected if name not in CHECKS]
    if unknown or not selected:
        sink.emit(f"모르는 블록: {unknown or '(없음)'} — 고를 수 있는 것: {', '.join(CHECKS)}")
        return 2
    now = datetime.now()
    today = args.today or now.date()
    session = Session(
        simulation_path=Path(args.database),
        equipment_path=Path(args.equipment_database),
        dataset_id=args.dataset_id,
    )
    needs_simulation = any(name in selected for name in ("env", "legacy", "reqb", "home", "census"))
    needs_equipment = any(name in selected for name in ("env", "equipment", "census"))
    if _opens_app_database(session, simulation=needs_simulation, equipment=needs_equipment):
        # 앱은 rerun 동안만 DB 를 쥔다(`pinned_connections`) — 쉬는 앱은 아래 잠금 확인을 지나치고,
        # 그동안 이 연결이 사용자 앱의 rerun 을 막는다. 판정은 화면 확인 스크립트와 같은 것을 쓴다.
        from check_deploy_screens import running_app_count

        running = running_app_count()
        if running:
            sink.emit(_APP_RUNNING_MESSAGE)
            return 1
        if running is None:
            sink.emit(_SCAN_FAILED_NOTE)
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
        sink.emit(_LOCK_MESSAGE)
        return 1
    interrupted = False
    try:
        for name in CHECKS:
            if name not in selected:
                continue
            title = _BLOCK_TITLES[name]
            try:
                for part in _block_parts(name, session, args, now=now, today=today, probe=probe):
                    sink.emit("\n".join(part))
            except KeyboardInterrupt:
                # 열린 표에 붙지 않게 빈 줄을 먼저 둔다. 멈춤은 요약을 찍은 뒤 그대로 밖으로 보낸다.
                interrupted = True
                sink.emit(f"\n- `{title}` 블록이 멈췄다 — 중단(KeyboardInterrupt)\n")
                session.notes.append(_note(title, "멈춤 중단"))
                raise
            except Exception as exc:  # 한 블록이 멈춰도 다음 블록은 잰다. 문구는 찍지 않는다
                sink.emit(f"\n- `{title}` 블록이 멈췄다 — {_failure(exc)}\n")
                session.notes.append(_note(title, f"멈춤 {_failure(exc)}"))
    finally:
        session.close()
        # 멈춘 실행(`Ctrl+C`)도 잰 데까지의 요약을 남긴다 — 사외로 가는 것은 이 요약뿐이다. 시간
        # 제한으로 프로세스가 죽으면 여기도 닿지 않는다(런북 8-0 — 그때는 멈춘 블록 이름만 옮긴다).
        sink.emit("\n".join(summary_lines(session.notes, interrupted=interrupted)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
