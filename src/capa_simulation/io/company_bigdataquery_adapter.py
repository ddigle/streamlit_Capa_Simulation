# Purpose: Company-only BigDataQuery adapter for the shared Core Data pipeline.

"""Company-only BigDataQuery adapter for the shared Core Data pipeline.

This module intentionally contains no CSV export.  Configure the SQL and source
column mapping in the marked section, then the Streamlit scenario page will pass
the returned DataFrame directly to the normalizer and DuckDB repository.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from types import ModuleType
from typing import Final, Protocol, cast

import pandas as pd

from capa_simulation.io.core_data_source import CoreDataBatch

_SIMULATION_CODE_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
# 목록 조회 모듈이 같은 표식을 봐야 해서 공개 이름이다. 비공개로 두면 다른 모듈이
# 밑줄 이름을 참조하게 된다.
UNCONFIGURED_MARKER: Final = "__TODO_CONFIGURE_BIGDATAQUERY__"
# 기간을 지정하지 않은 호출이 쓰는 창. 화면에서 기간을 고르면 그 값이 이 기본값을 대신한다.
DEFAULT_QUERY_WINDOW_DAYS: Final = 90
# 조회 요청자의 사내 계정을 넣는 환경변수. 사람마다 다른 값이라 저장소에 두지 않는다 —
# 배포 ZIP 을 받은 다른 사람이 남의 계정으로 조회하게 된다.
BDQ_USER_NAME_ENV: Final = "CAPA_BDQ_USER_NAME"

# ---------------------------------------------------------------------------
# 사내 환경 설정 영역
#
# 1) 아래 SQL을 실제 조회문으로 교체합니다.
# 2) 조건절의 {simulation_code}는 유지합니다.
# 3) DB 컬럼명이 Core Data 78컬럼명과 다르면 SOURCE_COLUMN_MAPPING에 등록합니다.
# 4) 조회 기간은 호출자가 `QueryWindow` 로 넘깁니다. {start_date}·{end_date} 자리를
#    지우면 기간을 좁힐 수 없어 팩트 테이블을 전면 조회합니다.
# ---------------------------------------------------------------------------
QUERY_TEMPLATE = """
SELECT
    catb_sim_info_id AS `시뮬레이션 ID`,
    catb_plan_id AS `PLAN ID`,
    base_yyyymm AS 기준정보년월,
    prod_knd AS 제품타입,
    u_pkg AS `U/PKG`,
    user_fam3_code AS UsreFamily3,
    fam4_code AS Family4,
    u_6 AS `U/6`,
    pkg1 AS PKG1,
    site AS SITE,
    area_class AS `Area Class`,
    mod_comp_flag AS `Module/comp`,
    lob_code AS `LOB Code`,
    pkg_part_no AS `PKG Part No`,
    capa_code AS `Capa Code`,
    prod_info AS 제품정보,
    plan_yyyymm AS 생산계획년월,
    plan_qty AS 생산수량,
    stack AS Stack,
    customer AS Customer,
    pack_code AS `Pack Code`,
    sh_flag AS `S/H`,
    cs AS CS,
    d_eq AS D_EQ,
    wf_knd AS `WF 구분`,
    knd_chip_qty AS 구분_Chip,
    knd_eq_qty AS 구분_EQ,
    chip_qty AS Chip수,
    plan_chip_kqty AS `Plan_Chip(K개)`,
    plan_chip_qty AS CHIP,
    net_die AS `Net Die`,
    `month` AS `Month`,
    plan_kqty AS `계획(K개)`,
    h8_cvt_plan_kqty AS `8H 환산 계획(K개)`,
    wf_kqty AS `WF수(매)`,
    pcb_kqty AS `PCB수(K매)`,
    eq_eok_gb AS `EQ(억Gb)`,
    omitt_yn AS 누락여부,
    plan_baseinfo_yn AS 계획기초정보여부,
    fab AS FAB,
    area_name AS Area_Name,
    proc AS 공정,
    maker AS 메이커,
    step_seq AS STEP_SEQ,
    mcp_seq AS MCP_SEQ,
    model_nm AS 모델명,
    para_val AS Para,
    step_qty AS Step수,
    capa_run_rate AS CAPA_RUN_RATE,
    req_std AS 소요기준,
    run_day AS RUN_DAY,
    day_req AS `일 필요`,
    upeh AS UPEH,
    st AS ST,
    lot_msr_rate AS `Lot 측정률`,
    wf_msr_rate AS WF측정률,
    wf_yield_eds AS EDS_수율,
    wf_yield_be AS BE_수율,
    wf_yield_cum AS CUM_수율,
    good_die AS GOOD_DIE,
    test_wf_qty AS `TEST WF수(매)`,
    shot_time AS `Shot Time`,
    shot_qty AS Shot수,
    index_time AS `Index Time`,
    modul_qty AS 모듈수,
    side_rate AS Side반영률,
    bias_rate AS 편중률,
    eqp_qty AS 설비보유,
    '' AS 설비대수변화관리,
    eqp_renteval_qty AS 설비대여평가,
    rent_eval_item AS 설비대여평가항목,
    rent_eval_desc AS `설비대여평가DESC`,
    mcp_chip_ratio AS MCP_Chip_Ratio,
    req_qty AS 소요대수,
    omitt_yn AS `시뮬레이션 누락여부`,
    hcb_eqp_qty AS 설비보유HCB,
    'ST_HBM' AS CUSTOM,
    bonding AS BONDING
FROM camp_tsp.campavp_catb_sim_rslt_report
WHERE impala_insert_time >= '{start_date}'
  AND impala_insert_time <  '{end_date}'
  AND catb_sim_info_id = '{simulation_code}'
"""

SOURCE_COLUMN_MAPPING: dict[str, str] = {
    "시뮬레이션 id": "시뮬레이션 ID",
    "plan id": "PLAN ID",
    "u/pkg": "U/PKG",
    "usrefamily3": "UsreFamily3",
    "family4": "Family4",
    "u/6": "U/6",
    "pkg1": "PKG1",
    "site": "SITE",
    "area class": "Area Class",
    "module/comp": "Module/comp",
    "lob code": "LOB Code",
    "pkg part no": "PKG Part No",
    "capa code": "Capa Code",
    "stack": "Stack",
    "customer": "Customer",
    "pack code": "Pack Code",
    "s/h": "S/H",
    "cs": "CS",
    "d_eq": "D_EQ",
    "wf 구분": "WF 구분",
    "구분_chip": "구분_Chip",
    "구분_eq": "구분_EQ",
    "chip수": "Chip수",
    "plan_chip(k개)": "Plan_Chip(K개)",
    "chip": "CHIP",
    "net die": "Net Die",
    "month": "Month",
    "계획(k개)": "계획(K개)",
    "8h 환산 계획(k개)": "8H 환산 계획(K개)",
    "wf수(매)": "WF수(매)",
    "pcb수(k매)": "PCB수(K매)",
    "eq(억gb)": "EQ(억Gb)",
    "fab": "FAB",
    "area_name": "Area_Name",
    "step_seq": "STEP_SEQ",
    "mcp_seq": "MCP_SEQ",
    "para": "Para",
    "step수": "Step수",
    "capa_run_rate": "CAPA_RUN_RATE",
    "run_day": "RUN_DAY",
    "upeh": "UPEH",
    "st": "ST",
    "lot 측정률": "Lot 측정률",
    "wf측정률": "WF측정률",
    "eds_수율": "EDS_수율",
    "be_수율": "BE_수율",
    "cum_수율": "CUM_수율",
    "good_die": "GOOD_DIE",
    "test wf수(매)": "TEST WF수(매)",
    "shot time": "Shot Time",
    "shot수": "Shot수",
    "index time": "Index Time",
    "side반영률": "Side반영률",
    "설비대여평가desc": "설비대여평가DESC",
    "mcp_chip_ratio": "MCP_Chip_Ratio",
    "설비보유hcb": "설비보유HCB",
    "custom": "CUSTOM",
    "bonding": "BONDING",
}


@dataclass(frozen=True)
class QueryWindow:
    """조회 기간. 시작일·종료일 모두 화면 라벨과 같이 '포함' 이다."""

    start_date: date
    end_date: date

    def __post_init__(self) -> None:
        if self.start_date > self.end_date:
            raise ValueError("조회 시작일은 종료일보다 늦을 수 없습니다.")

    @property
    def days(self) -> int:
        return (self.end_date - self.start_date).days + 1

    def sql_bounds(self) -> tuple[str, str]:
        """`impala_insert_time >= a AND < b` 에 넣을 두 문자열.

        상한이 배타(`<`)라 종료일 당일 적재분이 통째로 빠졌다. 화면 라벨이 '포함' 이므로
        SQL 상한만 다음 날로 민다. 포함/배타 차이를 흡수하는 자리는 여기 한 곳이고,
        목록 조회와 상세 조회가 같은 메서드를 쓰므로 두 단계의 규칙이 어긋날 수 없다.
        """
        return (
            self.start_date.strftime("%Y-%m-%d"),
            (self.end_date + timedelta(days=1)).strftime("%Y-%m-%d"),
        )

    def label(self) -> str:
        return f"{self.start_date:%Y-%m-%d} ~ {self.end_date:%Y-%m-%d}"


def default_query_window(
    *,
    today: date | None = None,
    days: int = DEFAULT_QUERY_WINDOW_DAYS,
) -> QueryWindow:
    """기간을 지정하지 않은 호출이 쓰는 기본 창(오늘 포함 최근 `days` 일)."""
    end_date = today or datetime.now().date()
    return QueryWindow(start_date=end_date - timedelta(days=days), end_date=end_date)


def resolve_detail_window(
    catalog_window: QueryWindow | None,
    *,
    today: date | None = None,
) -> QueryWindow:
    """상세 조회 창. 목록에서 고른 기간으로 **좁히지 않는다**.

    상세 SQL 은 기간과 `catb_sim_info_id` 를 AND 로 묶어 그 코드의 *행* 을 자른다. 목록
    기간이 하루면 그 코드의 하루치 행만 저장돼 원천이 잘린 시나리오가 조용히 남는다.
    그래서 기본 창과 목록 창의 합집합을 쓴다 — 선택이 없으면 기본 창과 정확히 같고,
    기본 창보다 오래된 코드를 골랐을 때만 아래로 넓어진다(넓히지 않으면 0행이다).
    """
    default = default_query_window(today=today)
    if catalog_window is None:
        return default
    return QueryWindow(
        start_date=min(default.start_date, catalog_window.start_date),
        end_date=max(default.end_date, catalog_window.end_date),
    )


class BigDataQueryModule(Protocol):
    """사내 `bigdataquery` 모듈에서 우리가 쓰는 부분.

    **여기 적힌 이름이 실제와 어긋나면 호출이 `TypeError` 로 죽는다.** 모듈은 `cast` 로
    들어오므로 이 선언을 대신 확인해 주는 장치가 없다 — `cast` 는 런타임 무검사이고 이
    Protocol 은 `isinstance` 대상이 아니며 패키지 타입 스텁도 없다.

    `user_name` 의 패키지 기본값은 빈 문자열이고, 서버(Linux) 환경에서는 그 빈값을
    `parameter user_name is necessary.` 로 거부한다. 그래서 **채울 수 있을 때만** 넘긴다 —
    `get_data_keywords` 를 보라.
    """

    def getData(
        self,
        *,
        param: str,
        convert_type: bool,
        verbose: bool,
        user_name: str = "",
    ) -> pd.DataFrame: ...


@dataclass(frozen=True)
class BigDataQueryCoreDataProvider:
    """Fetch one simulation code and return a DataFrame without local files."""

    simulation_name: str
    source_registered_at: datetime | None = None
    query_template: str = QUERY_TEMPLATE
    column_mapping: Mapping[str, str] = field(default_factory=lambda: SOURCE_COLUMN_MAPPING.copy())
    # 기본값이 있는 필드를 맨 뒤에 두어 기존 위치·키워드 생성이 그대로 돈다.
    window: QueryWindow | None = None

    def fetch(self, simulation_code: str) -> CoreDataBatch:
        code = _validated_simulation_code(simulation_code)
        window = self.window or default_query_window()
        query = build_query(self.query_template, code, window=window)
        module = cast(BigDataQueryModule, load_bigdataquery_module())
        frame = call_get_data(module, query)
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("bigdataquery.getData() 반환값은 pandas DataFrame이어야 합니다.")
        # 0행 방어는 반드시 rename 앞이다. 뒤에 두면 아래 MPGA TEST 예외가 먼저
        # `KeyError('모듈수')` 로 터지고, 아예 없으면 빈 프레임이 정규화를 통과해
        # 원인과 먼 문구로 죽는다.
        if frame.empty:
            raise ValueError(
                f"시뮬레이션 코드 {code} 의 조회 결과가 0행입니다. "
                f"조회 기간({window.label()})에 원천 데이터가 있는지 확인하세요."
            )
        renamed = frame.rename(columns=dict(self.column_mapping))
        # TODO: MPGA TEST 원천 모듈수 산정 규칙이 확정되면 제거
        module_count = pd.to_numeric(renamed["모듈수"], errors="coerce")

        mpga_test_exception = renamed["공정"].astype("string").str.strip().eq(
            "MPGA TEST"
        ) & module_count.between(0.95, 0.96, inclusive="both")

        renamed.loc[mpga_test_exception, "모듈수"] = 1

        return CoreDataBatch(
            simulation_code=code,
            simulation_name=self.simulation_name,
            source_type="BIGDATAQUERY",
            frame=renamed,
            source_registered_at=self.source_registered_at,
        )


def build_query(
    query_template: str,
    simulation_code: str,
    *,
    window: QueryWindow | None = None,
) -> str:
    """Validate the local adapter configuration and render one safe query."""
    if UNCONFIGURED_MARKER in query_template:
        raise RuntimeError(
            "BigDataQuery SQL이 아직 설정되지 않았습니다. "
            "company_bigdataquery_adapter.py의 QUERY_TEMPLATE을 실제 SQL로 교체하세요."
        )
    if "{simulation_code}" not in query_template:
        raise ValueError("BigDataQuery SQL에는 {simulation_code} 조건 자리가 필요합니다.")
    code = _validated_simulation_code(simulation_code)
    start_bound, end_bound = (window or default_query_window()).sql_bounds()
    return query_template.format(
        simulation_code=code,
        start_date=start_bound,
        end_date=end_bound,
    )


def is_bigdataquery_adapter_configured() -> bool:
    return UNCONFIGURED_MARKER not in QUERY_TEMPLATE and "{simulation_code}" in QUERY_TEMPLATE


def is_bigdataquery_package_available() -> bool:
    """사내 패키지 존재 여부. import 하지 않고 명세만 찾아본다.

    화면 안내에만 쓴다. 버튼 비활성 판정에는 쓰지 않는다 — 패키지가 없어도 버튼을 눌러
    한국어 안내를 볼 수 있어야 한다.
    """
    try:
        return importlib.util.find_spec("bigdataquery") is not None
    except (ImportError, ValueError):
        return False


def is_valid_simulation_code(value: str) -> bool:
    """목록에서 고른 코드가 저장까지 갈 수 있는지 미리 보는 술어.

    정규식은 `_validated_simulation_code` 한 곳에만 둔다. 조회를 다 돌린 뒤 저장 직전에
    실패하지 않도록 목록 단계에서 같은 판정을 먼저 보여 주려는 것이다.
    """
    try:
        _validated_simulation_code(value)
    except ValueError:
        return False
    return True


def _validated_simulation_code(value: str) -> str:
    code = value.strip()
    if not code:
        raise ValueError("시뮬레이션 코드는 비어 있을 수 없습니다.")
    if _SIMULATION_CODE_PATTERN.fullmatch(code) is None:
        raise ValueError("시뮬레이션 코드는 영문·숫자와 '.', '_', '-'만 사용할 수 있습니다.")
    return code


def resolve_user_name() -> str | None:
    """조회 요청자의 사내 계정. 없으면 `None` 이고, 그러면 인자를 아예 넘기지 않는다.

    **값이 없다고 여기서 멈추지 않는다.** Windows 에서는 패키지가 로그인 이름으로 요청자를
    스스로 식별하므로 지금도 인자 없이 잘 돈다 — 여기서 막으면 도는 경로를 새로 깨는 것이다.
    빈값을 거부하는 것은 서버(Linux) 환경뿐이고, 그때는 `call_get_data` 가 패키지의 문구를
    받아 무엇을 채워야 하는지로 바꿔 준다.

    Windows 로그인 이름으로 대신 채우지도 않는다. 사내 계정과 다르면 조용히 남의 이름이
    붙거나 권한 오류로 되돌아오는데, 둘 다 원인이 안 보인다.
    """
    return os.environ.get(BDQ_USER_NAME_ENV, "").strip() or None


def get_data_keywords(query: str) -> dict[str, object]:
    """`getData` 에 넘길 인자. 요청자 계정은 **있을 때만** 들어간다."""
    keywords: dict[str, object] = {"param": query, "convert_type": True, "verbose": True}
    user_name = resolve_user_name()
    if user_name is not None:
        keywords["user_name"] = user_name
    return keywords


def call_get_data(module: BigDataQueryModule, query: str) -> object:
    """조회 한 번. 요청자 계정을 안 넘긴 채 거부당하면 **무엇을 채워야 하는지**로 바꾼다.

    패키지가 내는 `parameter user_name is necessary.` 만으로는 어느 환경변수를 넣어야
    하는지 알 수 없다. 사내 WebIDE 에서 로그인·토큰이 모두 정상인데도 조회가 100% 막혀
    있었고, 원인을 찾는 데 두 세션이 걸렸다.
    """
    try:
        return module.getData(**get_data_keywords(query))  # type: ignore[arg-type]
    except Exception as error:  # noqa: BLE001 - 패키지 예외 종류를 모른다. 문구만 보고 되던진다
        if resolve_user_name() is None and "user_name" in str(error):
            raise RuntimeError(
                f"BigDataQuery 조회에 요청자의 사내 계정이 필요합니다. {BDQ_USER_NAME_ENV} "
                f"환경변수에 본인 AD 계정을 넣고 새 셸에서 앱을 다시 띄우세요 — WebIDE 는 "
                f'`export {BDQ_USER_NAME_ENV}="<AD 계정>"`, Windows 는 '
                f'`setx {BDQ_USER_NAME_ENV} "<AD 계정>"`.'
            ) from error
        raise


def load_bigdataquery_module() -> ModuleType:
    try:
        return importlib.import_module("bigdataquery")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "현재 환경에 bigdataquery 패키지가 없습니다. "
            "이 패키지는 사내 전용이라 pyproject.toml 의존성에 넣지 않습니다. "
            "사내 환경에서 `uv pip install bigdataquery` 로 따로 설치한 뒤 실행하세요."
        ) from exc
