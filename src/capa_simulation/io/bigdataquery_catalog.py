# Purpose: 사내 BigDataQuery 에서 기간 내 시뮬레이션 코드 목록을 조회한다.

"""기간으로 시뮬레이션 코드 목록을 조회하는 전용 경계.

상세 조회(`company_bigdataquery_adapter.QUERY_TEMPLATE`)와 한 파일에 섞지 않는다. 상세
SQL 은 78컬럼 계약과 순서까지 대조되는 검사를 받고 있고, `build_query` 는
`{simulation_code}` 자리를 필수로 요구해 이 목록 SQL 로는 통과할 수 없다.

여기서 하는 것은 조회뿐이다. 결과를 `CoreDataBatch`·`normalize_core_data` 경로에 넣지
않고 파일로도 쓰지 않는다 — 5컬럼 목록이 78컬럼 경로에 닿으면 계약 오류가 아니라
`KeyError` 로 죽는다.
"""

from __future__ import annotations

from typing import Final, cast

import pandas as pd

from capa_simulation.io.company_bigdataquery_adapter import (
    UNCONFIGURED_MARKER,
    BigDataQueryModule,
    QueryWindow,
    load_bigdataquery_module,
)

# 사내 결과 계약이다. 별칭 5개를 코드에서 고쳐 쓰지 않는다 — 화면 라벨은 서비스 계층이
# 따로 만든다.
CATALOG_COLUMNS: Final[tuple[str, ...]] = (
    "simulation_name",
    "simulation_code",
    "plan_name",
    "plan_code",
    "regist_data",
)

# 팩트 테이블 전면 스캔을 막는 상한. 날짜 입력에 강제하지 않고 제출 시 검증해서
# 사용자가 왜 막혔는지 문구로 알 수 있게 한다.
MAX_CATALOG_WINDOW_DAYS: Final = 366

_DATE_PLACEHOLDERS: Final[tuple[str, ...]] = ("{start_date}", "{end_date}")

# ---------------------------------------------------------------------------
# 사내 환경 설정 영역
#
# 1) 아래 SQL을 실제 목록 조회문으로 교체합니다.
# 2) 조건절의 {start_date}·{end_date}는 유지합니다.
# 3) 별칭 5개(CATALOG_COLUMNS)는 화면과 자동 입력이 그대로 참조하므로 바꾸지 않습니다.
# ---------------------------------------------------------------------------
CATALOG_QUERY_TEMPLATE = """
SELECT DISTINCT
    simul_nm AS simulation_name,
    catb_sim_info_id AS simulation_code,
    plan_nm AS plan_name,
    catb_plan_id AS plan_code,
    reg_date AS regist_data
FROM camp_tsp.campavp_catb_sim_rslt_report
WHERE impala_insert_time >= '{start_date}'
    AND impala_insert_time <  '{end_date}'
"""


def is_bigdataquery_catalog_configured(query_template: str = CATALOG_QUERY_TEMPLATE) -> bool:
    """목록 SQL 이 채워졌는지. 상세 SQL 판정과 분리해 어느 쪽이 비었는지 구분한다."""
    return UNCONFIGURED_MARKER not in query_template and all(
        placeholder in query_template for placeholder in _DATE_PLACEHOLDERS
    )


def build_catalog_query(
    window: QueryWindow,
    *,
    query_template: str = CATALOG_QUERY_TEMPLATE,
) -> str:
    """검증을 모두 마친 목록 조회문 하나를 만든다.

    검사는 전부 사내 패키지 import 이전이다. 사외 PC 에서도 설정 오류를 먼저 알 수 있다.
    """
    if UNCONFIGURED_MARKER in query_template:
        raise RuntimeError(
            "BigDataQuery 목록 조회 SQL이 아직 설정되지 않았습니다. "
            "bigdataquery_catalog.py의 CATALOG_QUERY_TEMPLATE을 실제 SQL로 교체하세요."
        )
    for placeholder in _DATE_PLACEHOLDERS:
        if placeholder not in query_template:
            raise ValueError(f"목록 조회 SQL에는 {placeholder} 조건 자리가 필요합니다.")
    if window.days > MAX_CATALOG_WINDOW_DAYS:
        raise ValueError(
            f"목록 조회 기간은 최대 {MAX_CATALOG_WINDOW_DAYS}일입니다. 기간을 줄여 다시 조회하세요."
        )
    start_bound, end_bound = window.sql_bounds()
    return query_template.format(start_date=start_bound, end_date=end_bound)


def fetch_simulation_catalog(
    window: QueryWindow,
    *,
    query_template: str = CATALOG_QUERY_TEMPLATE,
) -> pd.DataFrame:
    """기간 내 시뮬레이션 코드 목록을 계약 5컬럼으로 돌려준다."""
    query = build_catalog_query(window, query_template=query_template)
    module = cast(BigDataQueryModule, load_bigdataquery_module())
    frame = module.getData(param=query, convert_type=True, verbose=True)
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("bigdataquery.getData() 반환값은 pandas DataFrame이어야 합니다.")
    missing = [column for column in CATALOG_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError("목록 조회 결과에 계약 별칭이 없습니다: " + ", ".join(missing))
    # 화면 선택은 위치 인덱스로 돌아온다. 컬럼 순서와 인덱스를 여기서 고정해 두지 않으면
    # 라벨과 위치가 어긋나 조용히 다른 코드가 선택된다.
    return frame.loc[:, list(CATALOG_COLUMNS)].reset_index(drop=True)
