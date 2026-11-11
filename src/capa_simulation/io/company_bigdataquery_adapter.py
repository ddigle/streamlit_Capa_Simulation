# Purpose: Company-only BigDataQuery adapter for the shared Core Data pipeline.

"""Company-only BigDataQuery adapter for the shared Core Data pipeline.

This module intentionally contains no CSV export.  Configure the SQL and source
column mapping in the marked section, then the Streamlit scenario page will pass
the returned DataFrame directly to the normalizer and DuckDB repository.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import re
import threading
import time
from collections.abc import Mapping
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from types import ModuleType
from typing import Final, Protocol, cast

import pandas as pd

from capa_simulation.io.container_start_report import (
    BDQ_USER_NAME_ENV as BDQ_USER_NAME_ENV,
)
from capa_simulation.io.container_start_report import (
    STEP_INSTALL,
    STEP_TOKEN,
    STEP_USER_NAME,
    start_check_hint,
)
from capa_simulation.io.core_data_source import CoreDataBatch
from capa_simulation.services.korean_particle import with_subject_particle

_SIMULATION_CODE_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
# 목록 조회 모듈이 같은 표식을 봐야 해서 공개 이름이다. 비공개로 두면 다른 모듈이
# 밑줄 이름을 참조하게 된다.
UNCONFIGURED_MARKER: Final = "__TODO_CONFIGURE_BIGDATAQUERY__"
# 기간을 지정하지 않은 호출이 쓰는 창. 화면에서 기간을 고르면 그 값이 이 기본값을 대신한다.
DEFAULT_QUERY_WINDOW_DAYS: Final = 90
# 상세 조회 기본 창 — 원천 등록일 앞뒤 며칠(2026-09-29 사용자 결정). 적재 시각
# (`impala_insert_time`)은 보통 등록일 뒤지만 적재 배치·시간대 차이로 앞설 수 있어 앞쪽을 더 둔다.
# 창이 길수록 사내 조회가 오래 걸려 기본은 좁게 두고, 등록 뒤에도 계속 수정·재적재되는
# 시뮬레이션은 등록 화면에서 기간을 넓혀 조회한다.
DETAIL_WINDOW_DAYS_BEFORE: Final = 7
DETAIL_WINDOW_DAYS_AFTER: Final = 3
# 조회 요청자의 사내 계정을 넣는 환경변수 `BDQ_USER_NAME_ENV` 는 C-DEP CD 시작 스크립트도 읽어
# `io/container_start_report.py` 가 이름을 갖고 여기서 다시 내보낸다.

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


def registration_detail_window(
    first_registered_on: date,
    last_registered_on: date | None = None,
    *,
    today: date | None = None,
) -> QueryWindow:
    """상세 조회 기본 창 — 원천 등록일 `DETAIL_WINDOW_DAYS_BEFORE` 일 전 ~
    `DETAIL_WINDOW_DAYS_AFTER` 일 뒤(2026-09-29 사용자 결정 A+B).

    상세 SQL 은 기간과 `catb_sim_info_id` 를 AND 로 묶어 그 코드의 *행* 을 자르므로 창 밖에
    적재된 행은 오류 없이 빠진다. 그래도 창을 넓게 잡으면 사내 조회가 오래 걸려 기본은 등록일
    앞뒤로 좁게 두고, 등록 뒤에도 계속 수정·재적재된 시뮬레이션은 사용자가 화면에서 넓힌다.
    목록에 같은 코드의 등록일이 여러 날 보였으면(`last_registered_on`) 그 사이도 덮는다 — 이미
    보인 적재분을 기본값이 자르지 않게 한다. 끝은 오늘을 넘지 않는다(날짜 입력의 상한).
    """
    last = max(first_registered_on, last_registered_on or first_registered_on)
    end_cap = today or datetime.now().date()
    start_date = min(first_registered_on - timedelta(days=DETAIL_WINDOW_DAYS_BEFORE), end_cap)
    end_date = max(start_date, min(last + timedelta(days=DETAIL_WINDOW_DAYS_AFTER), end_cap))
    return QueryWindow(start_date=start_date, end_date=end_date)


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
                f"조회 기간({window.label()})에 원천 데이터가 있는지 확인하세요 — 원천 등록일과 "
                "기간이 어긋났으면 상세 조회 기간을 넓혀 다시 조회하세요."
            )
        renamed = frame.rename(columns=dict(self.column_mapping))
        # 이 두 컬럼은 공통 78컬럼 검증보다 먼저 아래 원천 보정이 사용한다.
        # 매핑 누락·충돌을 여기서 밝혀야 KeyError나 DataFrame 타입 오류로 원인이 가려지지 않는다.
        missing = [column for column in ("공정", "모듈수") if column not in renamed.columns]
        if missing:
            raise ValueError(
                f"BigDataQuery 원천 보정에 필요한 컬럼이 없습니다: {', '.join(missing)}"
            )
        duplicated = renamed.columns[renamed.columns.duplicated()].unique().tolist()
        if duplicated:
            names = ", ".join(map(str, duplicated))
            raise ValueError(f"BigDataQuery 컬럼 매핑 결과에 중복 컬럼이 있습니다: {names}")
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


@dataclass(frozen=True)
class _Flight:
    """지금 도는 조회 하나 — 결과 자리와 시작 시각(`time.monotonic`)."""

    answer: Future[object]
    started: float


# 지금 도는 조회문마다 그 조회. 결과를 남겨 두는 캐시가 아니라 겹침만 막는다(`call_get_data`).
_IN_FLIGHT: Final[dict[str, _Flight]] = {}
_IN_FLIGHT_LOCK: Final = threading.Lock()
# 같은 조회문에 합류하는 상한 — 잰 가장 긴 실패(907초, 서버 쪽 15분 제한과 맞다)를 넘겨 이만큼
# 돌아오지 않은 조회는 끝나기를 기대하지 않는다. 앱은 조회를 취소할 길이 없어 이 뒤로는 겹침을
# 감수하고 새로 묻는다.
IN_FLIGHT_JOIN_SECONDS: Final = 1200.0


def call_get_data(module: BigDataQueryModule, query: str) -> object:
    """조회 한 번. 같은 조회문이 이미 도는 중이면 새로 묻지 않고 그 결과(또는 실패)를 같이 기다린다.

    화면은 조회 중에도 단추가 눌리고, 누를 때마다 Streamlit 이 앞 회차를 멈추지 못한 채(`getData`
    안에 있다) 새 회차를 곧바로 세운다 — 그대로 두면 서버에 같은 조회가 누른 만큼 겹쳐 쌓인다. 긴
    조회일수록 다시 누르기 쉽고 서버에는 그때가 가장 나쁘다. 기다리는 쪽은 사본을 받는다.

    합류는 조회 시작부터 `IN_FLIGHT_JOIN_SECONDS` 까지다 — `getData` 가 돌아오지 않아도 프로세스의
    그 조회문 부름이 다 함께 멈추지 않게, 그 뒤의 첫 부름이 자리를 넘겨받아 새로 묻고 나머지는
    거기에 합류한다. 겹침은 조회문마다 그 시간에 하나로 그친다.
    """
    while True:
        with _IN_FLIGHT_LOCK:
            running = _IN_FLIGHT.get(query)
            now = time.monotonic()
            if running is None or now - running.started >= IN_FLIGHT_JOIN_SECONDS:
                mine = _Flight(Future(), now)
                _IN_FLIGHT[query] = mine
                break
            remaining = IN_FLIGHT_JOIN_SECONDS - (now - running.started)
        try:
            joined = running.answer.result(timeout=remaining)
        except FutureTimeoutError:
            continue
        return joined.copy() if isinstance(joined, pd.DataFrame) else joined
    if running is not None:
        _log_failure("같은 조회문이 돌아오지 않아 새로 묻는다")
    try:
        result = _get_data_once(module, query)
    except BaseException as error:
        mine.answer.set_exception(error)
        raise
    finally:
        with _IN_FLIGHT_LOCK:
            if _IN_FLIGHT.get(query) is mine:
                del _IN_FLIGHT[query]
    mine.answer.set_result(result)
    return result


def _get_data_once(module: BigDataQueryModule, query: str) -> object:
    """`getData` 한 번. 요청자 계정을 안 넘긴 채 거부당하면 **무엇을 채워야 하는지**로 바꾼다.

    패키지가 내는 `parameter user_name is necessary.` 만으로는 어느 환경변수를 넣어야
    하는지 알 수 없다. 사내 WebIDE 에서 로그인·토큰이 모두 정상인데도 조회가 100% 막혀
    있었고, 원인을 찾는 데 두 세션이 걸렸다.
    """
    started = time.monotonic()
    try:
        answer = module.getData(**get_data_keywords(query))  # type: ignore[arg-type]
    except Exception as error:  # 패키지 예외 종류를 모른다. 문구만 보고 바꿔 던진다
        if resolve_user_name() is None and "user_name" in str(error):
            _log_failure(
                f"요청자 계정({BDQ_USER_NAME_ENV}) 없음", type_names=failure_type_names(error)
            )
            raise RuntimeError(
                f"BigDataQuery 조회에 요청자의 AD 계정이 필요합니다. {BDQ_USER_NAME_ENV} "
                f"환경변수에 본인 AD 계정을 넣고 새 셸에서 앱을 다시 띄우세요 — WebIDE 는 "
                f'`export {BDQ_USER_NAME_ENV}="<AD 계정>"`, Windows 는 '
                f'`setx {BDQ_USER_NAME_ENV} "<AD 계정>"`.' + _start_check_line(STEP_USER_NAME)
            ) from error
        hint = _start_check_line(STEP_TOKEN) if is_login_token_failure(error) else ""
        failure = BigDataQueryCallError(error, hint=hint, seconds=time.monotonic() - started)
        _log_failure("조회 실패", kind=failure.kind, type_names=failure.type_names)
        if failure.kind == QUERY_FAILURE_TOKEN:
            _note_token_failure(True)
        raise failure from error
    _note_token_failure(False)
    return answer


# 이 프로세스의 마지막 조회가 토큰 갈래로 실패했나 — 관리자 상태 알림(`AD-10`)이 회차마다 읽는다.
# 토큰 실패에 세우고 조회 성공에 내린다(다른 실패는 그대로 둔다 — 토큰이 살아났는지 모른다). 예약
# 스레드도 조회하므로 Streamlit 은 부르지 않고 값만 둔다.
_TOKEN_FAILURE_LOCK: Final = threading.Lock()
_token_failed = False


def _note_token_failure(failed: bool) -> None:
    global _token_failed
    with _TOKEN_FAILURE_LOCK:
        _token_failed = failed


def last_query_failed_on_token() -> bool:
    """이 프로세스의 마지막 판정이 토큰 실패인가(성공한 조회가 그 뒤에 없었나)."""
    with _TOKEN_FAILURE_LOCK:
        return _token_failed


def forget_token_failure() -> None:
    """시험 전용 — 프로세스에 남은 토큰 실패 표지를 지운다."""
    _note_token_failure(False)


def _start_check_line(step: str) -> str:
    """C-DEP CD 컨테이너 시작 스크립트가 남긴 그 단계의 결과 한 단락(앞에 빈 줄). 결과 파일이 없는
    개발·사내 PC 에서는 빈 문자열이라 안내가 지금과 같다."""
    hint = start_check_hint(step)
    return f"\n\n{hint}" if hint else ""


def is_login_token_failure(error: BaseException) -> bool:
    """로그인 토큰이 없거나(`TokenNotFoundException` 꼴) 무효 · 만료인 패키지 예외인가. 종류 이름과
    문구로 가른 추정이다(`_token_clue`) — 갈래 「토큰」(`classify_query_failure`)과 서버 시작 점검
    토큰 줄 안내가 같은 판정을 쓴다."""
    return _token_clue(_failure_chain(error)) is not None


# 조회 실패의 갈래. 패키지 예외 종류를 모르므로 예외 사슬의 종류 이름과 문구의 낱말로 가른 추정이다.
# 「토큰」 은 다시 해도 같다 — 토큰을 새로 넣어야 풀린다(관리자 일).
QUERY_FAILURE_TOKEN: Final = "토큰"
QUERY_FAILURE_TIMEOUT: Final = "시간 초과"
QUERY_FAILURE_CONNECTION: Final = "연결"
QUERY_FAILURE_SQL: Final = "SQL"
QUERY_FAILURE_OTHER: Final = "그 밖"
# 조회문 자체를 탓하는 낱말 — 기다린 시간과 상관없이 조회문 거절이다. 같은 SQL 갈래의 나머지
# (`not found` · `does not exist` 등)는 긴 조회 중 다시 적재한 표에서도 난다
# (`LONG_FAILURE_SECONDS`).
_QUERY_TEXT_WORDS: Final[tuple[str, ...]] = ("syntax", "parse", "analysis", "semantic")
# 로그인 토큰을 탓하는 분명한 낱말만 — 사내 실패 문구를 아직 모르니 넓히지 않는다. 앞 둘은 패키지가
# 토큰이 없을 때 내는 문구(`TokenNotFoundException` — 「no bigdataquery token issued … at
# '/config/.credential/'」)에서 온다. 구문 오류의 「unexpected token」 은 여기 없고, 문법 낱말
# (`_QUERY_TEXT_WORDS`)이 함께 있으면 토큰으로 보지 않는다.
_TOKEN_FAILURE_WORDS: Final[tuple[str, ...]] = (
    "bigdataquery token",
    ".credential",
    "invalid token",
    "invalid_token",
    "token is invalid",
    "token expired",
    "token has expired",
    "token is expired",
    "expired token",
)
# 차례대로 본다 — 「connect timeout」 은 시간 초과, 「host not found」 는 연결이다.
_FAILURE_WORDS: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    (
        QUERY_FAILURE_TIMEOUT,
        (
            "timeout",
            "timed out",
            "time out",
            "deadline",
            "time limit",
            "time_limit",
            "timelimit",
            "시간 초과",
            "시간 제한",
        ),
    ),
    (
        QUERY_FAILURE_CONNECTION,
        (
            "connect",
            "refused",
            "reset by peer",
            "unreachable",
            "network",
            "socket",
            "transport",
            "broken pipe",
            "host",
            "name resolution",
            "getaddrinfo",
            "ssl",
            "handshake",
            "연결",
        ),
    ),
    (
        QUERY_FAILURE_SQL,
        (
            *_QUERY_TEXT_WORDS,
            "programmingerror",
            "could not resolve",
            "not found",
            "does not exist",
            "unknown column",
            "invalid column",
        ),
    ),
    # 까닭을 말하지 않는 낱말 — 갈래는 그 밖이고 점검 줄에 단서로만 적는다. `sql` 은 맨 뒤다.
    # 드라이버 문구는 함수 이름(`SQLFetch` 등)으로도 이 낱말을 실을 수 있어 조회문 거절의 근거가
    # 되지 못한다.
    (
        QUERY_FAILURE_OTHER,
        ("memory", "exceeded", "cancel", "expired", "killed", "aborted", "rejected", "sql"),
    ),
)
# 조회문 거절은 초 단위로 돌아온다 — 이만큼 기다린 뒤의 실패는 문법 낱말(`_QUERY_TEXT_WORDS`)이
# 없으면 DB 가 끝내지 못한 것으로 읽고 시간 초과의 길(다시 묻지 않음 · 기간을 줄임)로 보낸다.
# `not found` · `does not exist` 도 여기 든다. 잰 가장 긴 성공(366일 목록 157초)의 두 배쯤이다.
LONG_FAILURE_SECONDS: Final = 300.0
LONG_FAILURE_CLUE: Final = "오래 걸림"
_FAILURE_ADVICE: Final[Mapping[str, str]] = {
    QUERY_FAILURE_TOKEN: "로그인 토큰이 없거나 만료 · 무효입니다 — 다시 해도 같으니 관리자에게 "
    "알려 주세요(토큰을 새로 넣어야 풀립니다).",
    QUERY_FAILURE_TIMEOUT: "DB 응답이 늦었습니다 — 잠시 뒤 같은 조회를 다시 하거나 "
    "기간을 줄여 다시 하세요.",
    QUERY_FAILURE_CONNECTION: "DB 에 닿지 못했습니다 — 네트워크 연결을 확인하고 잠시 뒤 같은 "
    "조회를 다시 하세요.",
    QUERY_FAILURE_SQL: "DB 가 조회문을 받지 않았습니다 — 다시 해도 같으니 아래 원문을 "
    "관리자에게 알려 주세요.",
    QUERY_FAILURE_OTHER: "잠시 뒤 같은 조회를 다시 하세요. 같은 실패가 이어지면 아래 원문을 "
    "관리자에게 알려 주세요.",
}
# 화면에 옮기는 원문 길이. 패키지 문구에 조회문 전체가 실려 오기도 한다.
_ORIGINAL_TEXT_LIMIT: Final = 300


def _original_text(error: BaseException) -> str:
    """화면에 옮길 원문 한 줄 — 종류 이름과 `_ORIGINAL_TEXT_LIMIT` 로 자른 문구."""
    text = str(error).strip()
    if len(text) > _ORIGINAL_TEXT_LIMIT:
        text = text[:_ORIGINAL_TEXT_LIMIT] + " …"
    return f"{type(error).__name__}: {text or '(문구 없음)'}"


def _failure_chain(error: BaseException) -> list[BaseException]:
    """`error` 와 그 원인들(`__cause__`·`__context__`). 돌아오는 사슬은 끊는다."""
    chain: list[BaseException] = []
    current: BaseException | None = error
    while current is not None and current not in chain and len(chain) < 5:
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain


def failure_type_names(error: BaseException) -> tuple[str, ...]:
    """예외 사슬의 종류 이름. 문구는 식별값을 실을 수 있어 사외로 가는 기록에는 이것만 적는다."""
    return tuple(type(link).__name__ for link in _failure_chain(error))


def _token_clue(chain: list[BaseException]) -> str | None:
    """토큰 실패면 근거 낱말(`_TOKEN_FAILURE_WORDS` 의 것 — 종류 이름으로 가렸으면 빈 글), 아니면
    None. 문법 낱말이 함께 있으면 구문 오류로 보고 None 이다."""
    names = " ".join(type(link).__name__ for link in chain).casefold()
    text = " ".join(str(link) for link in chain).casefold()
    if any(word in names or word in text for word in _QUERY_TEXT_WORDS):
        return None
    if "token" in names:
        return ""
    return next((word for word in _TOKEN_FAILURE_WORDS if word in text), None)


def _sorted_failure(error: BaseException) -> tuple[str, str]:
    """(갈래, 근거 낱말). 종류(`TimeoutError`·`ConnectionError`)로 가렸거나 맞은 낱말이 없으면
    낱말은 빈 글이다. 낱말은 `_TOKEN_FAILURE_WORDS` · `_FAILURE_WORDS` 의 것뿐이라 문구를 싣지
    않는다. 토큰을 맨 앞에 본다 — 사슬에 `ConnectionError` 가 있거나 문구에 연결 낱말이 있어도 토큰
    실패는 「연결」 안내(네트워크 · 다시)가 틀린 길이다."""
    chain = _failure_chain(error)
    token = _token_clue(chain)
    if token is not None:
        return QUERY_FAILURE_TOKEN, token
    if any(isinstance(link, TimeoutError) for link in chain):
        return QUERY_FAILURE_TIMEOUT, ""
    if any(isinstance(link, ConnectionError) for link in chain):
        return QUERY_FAILURE_CONNECTION, ""
    haystack = " ".join(f"{type(link).__name__} {link}" for link in chain).casefold()
    for kind, words in _FAILURE_WORDS:
        for word in words:
            if word in haystack:
                return kind, word
    return QUERY_FAILURE_OTHER, ""


def classify_query_failure(error: BaseException) -> str:
    """조회 실패의 갈래(`QUERY_FAILURE_*`). 문구는 가르는 데만 쓴다."""
    return _sorted_failure(error)[0]


def query_failure_clue(error: BaseException) -> str:
    """갈래를 정한 낱말(`_FAILURE_WORDS` 의 것 — 문구 원문이 아니다). 종류로 가렸거나 맞은 낱말이
    없으면 빈 글이다. 점검 스크립트가 갈래 옆에 적어 같은 「SQL」 이 문법 낱말(`syntax` 등)로
    섰는지 `not found` 같은 넓은 낱말로 섰는지, 「그 밖」 이 무엇을 달고 왔는지 가른다."""
    return _sorted_failure(error)[1]


# 화면이 잡아 보여 주는 실패도 앱 로그에 한 줄 남긴다 — 셸·화면을 볼 수 없는 자리(C-DEP CD)에서
# 로그가 유일한 단서일 수 있다. 원문(계정 이름 등이 든다)은 화면에만 두고, 로그에는 첫 문장과
# 갈래만 적는다.
_LOGGER = logging.getLogger(__name__)


def _log_failure(message: str, *, kind: str = "", type_names: tuple[str, ...] = ()) -> None:
    detail = f" 갈래={kind}" if kind else ""
    if type_names:
        detail += f" 종류={','.join(type_names)}"
    _LOGGER.warning("BigDataQuery 실패: %s%s", message.split(". ")[0].splitlines()[0], detail)


def _is_long_wait_failure(kind: str, clue: str, seconds: float | None) -> bool:
    """오래 기다린 끝의 실패를 시간 초과로 올릴지. 토큰 · 시간 초과 · 연결은 그 갈래가 맞고, SQL 은
    문법 낱말일 때만 그대로 둔다."""
    if seconds is None or seconds < LONG_FAILURE_SECONDS:
        return False
    return kind == QUERY_FAILURE_OTHER or (
        kind == QUERY_FAILURE_SQL and clue not in _QUERY_TEXT_WORDS
    )


class BigDataQueryCallError(RuntimeError):
    """`getData` 가 낸 패키지 예외. 화면들이 잡는 `RuntimeError` 로 올려 갈래와 다시 할 길을
    알린다 — 패키지의 `Error` 같은 종류는 화면이 잡는 예외 튜플(`BOOTSTRAP_ERRORS`) 밖이라 그대로
    두면 화면이 traceback 으로 멈춘다(사내 리뷰 202610200720, 목록 조회 첫 판 실패). 원래 예외는
    `__cause__` 에 있다. `seconds` 는 실패까지 걸린 초다 — `LONG_FAILURE_SECONDS` 를 넘겨 그 밖이나
    넓은 SQL 낱말로 갈린 실패는 시간 초과로 올린다(`_is_long_wait_failure`)."""

    def __init__(
        self, error: BaseException, *, hint: str = "", seconds: float | None = None
    ) -> None:
        self.kind, self.clue = _sorted_failure(error)
        if _is_long_wait_failure(self.kind, self.clue, seconds):
            self.kind = QUERY_FAILURE_TIMEOUT
            self.clue = f"{LONG_FAILURE_CLUE} {self.clue}".strip()
        self.type_names = failure_type_names(error)
        super().__init__(
            f"BigDataQuery 조회가 실패했습니다({self.kind}). {_FAILURE_ADVICE[self.kind]}\n\n"
            f"원문 — {_original_text(error)}{hint}"
        )


def load_bigdataquery_module() -> ModuleType:
    """사내 패키지를 불러온다. 실패는 모두 화면들이 잡는 `RuntimeError` 로 올린다.

    패키지가 깔렸어도 불러오다 깨질 수 있다(DLL·numpy 판·패키지가 쓰는 모듈 없음). 그 예외
    (`ImportError`·`AttributeError` 등)는 `BOOTSTRAP_ERRORS` 밖이라 그대로 두면 목록 조회·저장이
    traceback 으로 멈춘다. 「패키지가 없다」는 안내는 패키지 자체가 없을 때만 낸다 — 점검
    스크립트가 그 문구로 가른다. 그 첫 문장은 바꾸지 않고, C-DEP CD 컨테이너(셸이 없어 설치 안내를
    따를 수 없다)에서는 시작 스크립트의 설치 단계 결과를 뒤에 덧붙인다. `KeyboardInterrupt` 같은
    `BaseException` 은 잡지 않는다.
    """
    try:
        return importlib.import_module("bigdataquery")
    except ModuleNotFoundError as exc:
        _log_failure(f"패키지를 불러오지 못함(없는 모듈 {exc.name})")
        if exc.name in (None, "bigdataquery"):
            raise RuntimeError(
                "현재 환경에 bigdataquery 패키지가 없습니다. "
                "이 패키지는 공개 인덱스(PyPI)에 없어 pyproject.toml 의존성에 넣지 않습니다. "
                "README 「초기 설정」 4단계대로 따로 설치한 뒤 실행하세요."
                + _start_check_line(STEP_INSTALL)
            ) from exc
        raise RuntimeError(
            "bigdataquery 패키지를 불러오지 못했습니다 — 패키지가 쓰는 모듈 "
            f"{with_subject_particle(f'`{exc.name}`')} "
            "없습니다. 패키지를 다시 설치한 뒤 실행하세요(README 「초기 설정」 "
            "4단계)."
        ) from exc
    except Exception as exc:  # 패키지 초기화가 낼 예외 종류를 모른다
        _log_failure("패키지 초기화 실패", type_names=failure_type_names(exc))
        raise RuntimeError(
            "bigdataquery 패키지를 불러오지 못했습니다. 패키지를 다시 설치한 뒤 "
            "실행하세요(README 「초기 설정」 4단계). 같은 실패가 이어지면 아래 원문을 관리자에게 "
            f"알려 주세요.\n\n원문 — {_original_text(exc)}"
        ) from exc
