# Purpose: Shared content-addressed caches for simulation calculations.

"""Shared content-addressed caches for simulation calculations."""

import hashlib
from collections.abc import Mapping
from datetime import date

import pandas as pd
import streamlit as st

from capa_simulation.services.dashboard import (
    PRODUCTION_DETAIL_CUSTOMER_DIMENSIONS,
    PRODUCTION_DETAIL_DIMENSIONS,
    build_monthly_wafer_load_from_load,
    build_production_dashboard,
)
from capa_simulation.services.equipment_availability import (
    build_weekly_equipment_availability,
)
from capa_simulation.services.load_calculator import (
    DemandBasis,
    build_monthly_volume,
    calculate_chip_and_wafer_loads,
    filter_edp_plan,
)
from capa_simulation.services.month_filter import filter_month_range
from capa_simulation.services.required_equipment import (
    calculate_required_equipment,
)
from capa_simulation.services.route_step_editor import route_step_catalog, route_step_summary
from capa_simulation.services.securement_rate import calculate_securement_rate
from capa_simulation.services.standard_target_capacity import (
    add_pkg_equivalent_standard_target,
    build_weekly_standard_target_capacity,
)
from capa_simulation.services.unit_capacity import calculate_unit_capacity
from capa_simulation.services.weighted_unit_capacity import (
    effective_process_capacity_to_month_table,
)

HomeSimulationCacheKey = tuple[int, str, int, int, str]

# 활성 시나리오 내용과 월 범위를 대표하는 키. 아래 키 전용 캐시들이 공유한다.
ScenarioCacheKey = tuple[int, str, int, int]


def scenario_cache_key(
    reference_version: int,
    active_scenario: Mapping[str, object],
    start_month: int,
    end_month: int,
) -> ScenarioCacheKey:
    """(reference_version, content_token, start, end).

    `revision` 이 아니라 `content_token` 이다. 세션 편집 번호는 다른 내용에서도 겹치고
    `st.cache_data` 는 프로세스 전역이라 다른 브라우저 세션과도 겹친다.
    """
    return (reference_version, str(active_scenario["content_token"]), start_month, end_month)


def build_home_simulation_cache_key(
    *,
    reference_version: int,
    scenario_token: str,
    start_month: int,
    end_month: int,
    display_order: pd.DataFrame,
) -> HomeSimulationCacheKey:
    """Build a small key covering every mutable HOME calculation input boundary.

    `get_home_simulation` 은 프레임 인자를 `_` 로 시작하게 두어 내용 해시를 건너뛴다.
    따라서 이 키가 입력 동일성을 혼자 책임진다. 예전에는 시나리오 편집 카운터
    (`revision`)를 넣었는데, 그 번호는 서로 다른 내용에서도 겹친다. 세션 편집은
    0,1,2... 로 올라가고 저장 리비전을 불러오면 그 번호가 그대로 들어오기 때문이다.
    `st.cache_data` 는 프로세스 전역이라 다른 브라우저 세션과도 겹쳤다.
    시나리오 내용이 바뀔 때마다 새로 발급되는 `content_token` 을 쓴다.
    """
    digest = hashlib.sha256()
    digest.update("\x1f".join(map(str, display_order.columns)).encode("utf-8"))
    digest.update("\x1f".join(map(str, display_order.dtypes)).encode("utf-8"))
    digest.update(
        pd.util.hash_pandas_object(display_order, index=True, categorize=True)
        .to_numpy(dtype="uint64")
        .tobytes()
    )
    return (
        reference_version,
        scenario_token,
        start_month,
        end_month,
        digest.hexdigest(),
    )


@st.cache_data(show_spinner=False, max_entries=16)
def get_securement_rate(
    cache_key: ScenarioCacheKey,
    _available_equipment: pd.DataFrame,
    _required_equipment: pd.DataFrame,
) -> pd.DataFrame:
    """확보율. 두 프레임은 키(시나리오 내용·월 범위)가 정하므로 해시하지 않는다.

    required_equipment(3MB)를 해시하느라 적중에도 35ms 를 쓰고 있었다. 가용대수는 같은
    시나리오·월 범위의 RQ_EQP_AVBL 슬라이스, 소요대수는 같은 키의 계산 결과여야 한다.
    """
    del cache_key
    return calculate_securement_rate(_available_equipment, _required_equipment)


@st.cache_data(show_spinner=False, max_entries=32)
def get_effective_process_capacity_table(
    cache_key: ScenarioCacheKey,
    _required_equipment: pd.DataFrame,
    detail_level: str,
) -> pd.DataFrame:
    """공정 유효 Capa 월 표. 공정 필터는 이 뒤에 걸리므로 필터마다 같은 계산을 반복하고 있었다.

    소요대수는 같은 키로 계산한 결과라 키가 내용을 이미 결정한다. 넘겨받아 해시하면 적중할
    때도 19MB 프레임을 다시 훑는다 — `get_securement_rate` 와 같은 계약이다.
    """
    del cache_key
    return effective_process_capacity_to_month_table(_required_equipment, detail_level)


@st.cache_data(show_spinner=False, max_entries=16)
def get_route_step_tables(
    cache_key: ScenarioCacheKey,
    _upeh: pd.DataFrame,
    _reqb: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """공정별 Capa STEP 구성 탭의 (요약, 선택 목록).

    둘 다 순수 함수인데 rerun 마다 다시 만들고 있었다(721~963ms, 탭이 닫혀 있어도). 목록은
    작업·경로 선택 위젯의 options 라 숨은 탭에서도 있어야 하므로 건너뛰지 않고 캐시한다.
    키는 (reference_version, content_token, start_month, end_month) — 프레임은 해시하지 않는다.
    """
    del cache_key
    return route_step_summary(_reqb), route_step_catalog(_upeh, _reqb)


@st.cache_data(show_spinner=False, max_entries=16)
def get_pkg_equivalent_standard_target(
    required_equipment: pd.DataFrame,
    run_day: pd.DataFrame,
    weekly_availability: pd.DataFrame,
    start_date: date,
    end_date: date,
    detail_level: str,
    plan: pd.DataFrame,
    *,
    _weekly_target: pd.DataFrame,
) -> pd.DataFrame:
    """PKG Kea 환산 표준 목표 Capa.

    키는 1차 입력이다. 파생 프레임(weekly_target)을 키로 쓰면 5만 행을 넘길 때 Streamlit 이
    1만 행 표본만 해시해 가용대수 편집이 캐시에 묻힐 수 있다.

    `_weekly_target` 은 **키에 들어간 여섯 인자로 만든** 주간 표준 목표여야 한다. 다른
    인자로 만든 프레임을 넘기면 키와 내용이 어긋나 틀린 값이 캐시에 남는다. 여기서 다시
    부르면 호출자가 방금 만든 것을 한 번 더 해시하고 역직렬화한다.
    """
    return add_pkg_equivalent_standard_target(
        weekly_target=_weekly_target,
        required_equipment=required_equipment,
        plan=plan,
        detail_level=detail_level,
    )


@st.cache_data(show_spinner=False, max_entries=32)
def get_weekly_standard_target_capacity(
    required_equipment: pd.DataFrame,
    run_day: pd.DataFrame,
    weekly_availability: pd.DataFrame,
    start_date: date,
    end_date: date,
    detail_level: str,
) -> pd.DataFrame:
    """Cache the weekly standard target Capa for one active scenario and CSV input."""
    return build_weekly_standard_target_capacity(
        required_equipment=required_equipment,
        run_day=run_day,
        weekly_availability=weekly_availability,
        start_date=start_date,
        end_date=end_date,
        detail_level=detail_level,
    )


@st.cache_data(show_spinner=False, max_entries=32)
def get_monthly_volume(
    plan: pd.DataFrame,
    yield_data: pd.DataFrame,
    chip_qty: pd.DataFrame,
    demand_basis: DemandBasis,
    detailed: bool,
    density_data: pd.DataFrame,
    display_order: pd.DataFrame,
) -> pd.DataFrame:
    # Load-calculation cache schema v2: normalize WF type before Dummy detection.
    return build_monthly_volume(
        plan=plan,
        yield_data=yield_data,
        chip_qty=chip_qty,
        demand_basis=demand_basis,
        detailed=detailed,
        density_data=density_data,
        display_order=display_order,
    )


@st.cache_data(show_spinner=False, max_entries=32)
def get_production_dashboard(
    plan: pd.DataFrame,
    density_data: pd.DataFrame,
    display_order: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    return build_production_dashboard(plan, density_data, display_order)


@st.cache_data(show_spinner=False, max_entries=16)
def get_home_simulation(
    cache_key: HomeSimulationCacheKey,
    _tables: Mapping[str, pd.DataFrame],
    _display_order: pd.DataFrame,
    _reference_tables: Mapping[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Reuse HOME results while hashing only ``cache_key`` on warm reruns.

    월 슬라이스는 이 안에서 한다. 호출자가 미리 잘라서 넘기면 캐시가 적중해도 표 열 개를
    자르고 복사한 뒤 버린다(warm rerun 27~36ms 중 93~98%). 키와 프레임을 한 객체에서
    꺼내므로 apply_month_updates 직후 옛 슬라이스가 새 토큰에 묶이는 함정도 닫힌다.
    """
    _, _, start_month, end_month, _ = cache_key

    def sliced(name: str) -> pd.DataFrame:
        return filter_month_range(_tables[name], start_month, end_month, name)

    _plan = sliced("RQ_PKG_PLAN")
    _yield_data = sliced("RQ_YLD")
    _available_equipment = sliced("RQ_EQP_AVBL")
    # 월 축이 없는 두 표는 그대로.
    _density_data = _tables["RQ_CHIP_EQ"]
    _chip_qty = _tables["RQ_CHIP_QTY"]
    # Load-calculation cache schema v2: normalize WF type before Dummy detection.
    monthly_density, production_detail = get_production_dashboard(
        _plan,
        _density_data,
        _display_order,
    )
    # 대당 Capa 와 소요대수는 HOME 전용이 아니다. 이 키의 앞 네 칸이 `ScenarioCacheKey` 와
    # 같은 자리라, 같은 시나리오·월 범위면 Static Capa 다섯 페이지와 한 번만 계산한다.
    # 표시순서가 바뀌어도(이 키의 다섯째 칸) 소요대수는 그대로 살아남는다.
    scenario_key: ScenarioCacheKey = cache_key[:4]
    _, required_equipment = get_scenario_capacity_and_demand(
        scenario_key,
        _scenario_tables=_tables,
        _reference_tables=_reference_tables,
    )
    _, wafer_load = calculate_chip_and_wafer_loads(_plan, _yield_data, _chip_qty)
    monthly_wafer = build_monthly_wafer_load_from_load(wafer_load)
    securement_rate = get_securement_rate(scenario_key, _available_equipment, required_equipment)
    return monthly_density, production_detail, monthly_wafer, securement_rate


@st.cache_data(show_spinner=False, max_entries=8)
def get_home_lob_without_edp(
    cache_key: HomeSimulationCacheKey,
    _tables: Mapping[str, pd.DataFrame],
    _display_order: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """EDP 를 뺀 Density·계획 세부수량·Wafer 부하량. **소요대수는 여기서 만들지 않는다.**

    EDP 제외는 LOB 로 표현되는 값, 곧 `확보율 × 부하량` 꼴로 나오는 값에만 건다. 설비가
    받는 부하는 EDP 를 포함한 전체 계획이므로 확보율과 B/N 공정 순위는 바뀌면 안 된다.
    그래서 설비 수요 계산을 다시 돌리지 않고 부하량 쪽만 다시 만든다.

    토글을 켠 동안에만 불린다. 끈 상태에서는 이 계산 자체가 돌지 않는다.
    """
    _, _, start_month, end_month, _ = cache_key
    plan = filter_edp_plan(
        filter_month_range(_tables["RQ_PKG_PLAN"], start_month, end_month, "RQ_PKG_PLAN"),
        False,
    )
    yield_data = filter_month_range(_tables["RQ_YLD"], start_month, end_month, "RQ_YLD")
    monthly_density, production_detail = build_production_dashboard(
        plan,
        _tables["RQ_CHIP_EQ"],
        _display_order,
    )
    _, wafer_load = calculate_chip_and_wafer_loads(plan, yield_data, _tables["RQ_CHIP_QTY"])
    monthly_wafer = build_monthly_wafer_load_from_load(wafer_load)
    return monthly_density, production_detail, monthly_wafer


@st.cache_data(show_spinner=False, max_entries=8)
def get_home_plan_detail(
    cache_key: HomeSimulationCacheKey,
    _tables: Mapping[str, pd.DataFrame],
    _display_order: pd.DataFrame,
    *,
    include_edp: bool,
    include_customer: bool,
) -> pd.DataFrame:
    """기본(EDP 포함·제품/Stack)이 아닌 조합의 계획 세부수량.

    기본 조합은 `get_home_simulation` 이 이미 만들어 돌려주므로 여기 오지 않는다. 토글을
    건드린 사람만 이 계산을 치른다.
    """
    _, _, start_month, end_month, _ = cache_key
    plan = filter_edp_plan(
        filter_month_range(_tables["RQ_PKG_PLAN"], start_month, end_month, "RQ_PKG_PLAN"),
        include_edp,
    )
    _, detail = build_production_dashboard(
        plan,
        _tables["RQ_CHIP_EQ"],
        _display_order,
        detail_dimensions=(
            PRODUCTION_DETAIL_CUSTOMER_DIMENSIONS
            if include_customer
            else PRODUCTION_DETAIL_DIMENSIONS
        ),
    )
    return detail


@st.cache_data(show_spinner=False, max_entries=8)
def get_home_comparison_plan(
    cache_key: HomeSimulationCacheKey,
    _tables: Mapping[str, pd.DataFrame],
    _comparison_plan: pd.DataFrame,
    _display_order: pd.DataFrame,
    *,
    comparison_revision_id: str,
    include_edp: bool,
    detail_dimensions: tuple[str, ...],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """비교 시나리오의 **계획만** 가져와 현재 기준정보로 환산한 Density·Wafer·세부수량.

    수율·Chip 기준정보가 그 사이 바뀌었어도 그것은 계획 변동이 아니다. 계획 차이만 보려는
    것이므로 `RQ_PKG_PLAN` 만 비교 시나리오에서 가져오고 환산에 쓰는 표는 현재 것을 쓴다.

    `comparison_revision_id` 는 키에만 쓴다. 프레임 인자는 `_` 로 시작해 해시를 건너뛰므로
    어느 리비전의 계획인지를 이 값이 혼자 책임진다.
    """
    del comparison_revision_id
    _, _, start_month, end_month, _ = cache_key
    plan = filter_edp_plan(
        filter_month_range(_comparison_plan, start_month, end_month, "RQ_PKG_PLAN"),
        include_edp,
    )
    monthly_density, production_detail = build_production_dashboard(
        plan,
        _tables["RQ_CHIP_EQ"],
        _display_order,
        detail_dimensions=list(detail_dimensions),
    )
    _, wafer_load = calculate_chip_and_wafer_loads(
        plan,
        filter_month_range(_tables["RQ_YLD"], start_month, end_month, "RQ_YLD"),
        _tables["RQ_CHIP_QTY"],
    )
    monthly_wafer = build_monthly_wafer_load_from_load(wafer_load)
    return monthly_density, monthly_wafer, production_detail


@st.cache_data(show_spinner=False, max_entries=16)
def get_weekly_equipment_availability(
    baseline: pd.DataFrame,
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    *,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Reuse the weekly availability aggregation across reruns of the equipment page.

    가용설비 현황 페이지에는 fragment 가 없어 위젯 하나를 건드릴 때마다 페이지 전체가
    다시 실행된다. 이 집계는 조회기간 주차 수에 비례해 13주 300ms · 52주 1.5s 가 든다.
    세 프레임은 이미 리비전과 4개 필터가 반영된 결과라서 내용 해시가 곧 올바른 키다.
    """
    return build_weekly_equipment_availability(
        baseline,
        equipment,
        downtime,
        start_date=start_date,
        end_date=end_date,
    )


CAPACITY_INPUT_TABLES = (
    "RQ_UPEH",
    "RQ_RUN_RATE",
    "RQ_VITAL",
    "RQ_MODULE",
    "RQ_RUN_DAY",
    "RQ_LOT_RATIO",
    "RQ_WF_RATIO",
)

DEMAND_INPUT_TABLES = ("RQ_REQB", "RQ_PKG_PLAN", "RQ_YLD", "RQ_CHIP_QTY")

# 월 축이 없는 입력은 두 갈래다.
# - REFERENCE_INPUT_TABLES: 시나리오가 소유하지 않아 활성 리비전에서 그대로 읽는다.
# - SCENARIO_MONTHLESS_TABLES: 시나리오가 소유하지만 월 축이 없어 월 슬라이스를 하지
#   않는다. 가상 제품 복제 등록이 여기에 행을 추가한다.
REFERENCE_INPUT_TABLES = ("RQ_MODULE",)
SCENARIO_MONTHLESS_TABLES = ("RQ_CHIP_QTY",)
MONTHLESS_INPUT_TABLES = (*REFERENCE_INPUT_TABLES, *SCENARIO_MONTHLESS_TABLES)


def get_capacity_and_demand(
    tables: Mapping[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """대당 Capa 와 그에 따른 소요대수를 한 번에 만든다.

    다섯 페이지가 같은 두 호출을 이어 붙이면서 RQ 이름 11개를 각자 손으로 적고 있었다.
    프레임을 어디서 가져오는지는 페이지마다 다르므로(활성 시나리오 · 월 필터 결과 ·
    사용자 편집본) 매핑만 받고 출처는 호출자에게 남긴다.

    캐시는 get_scenario_capacity_and_demand 가 키로 건다. 여기는 계산 순서만 정한다.
    """
    unit_capacity = calculate_unit_capacity(
        upeh=tables["RQ_UPEH"],
        run_rate=tables["RQ_RUN_RATE"],
        vital=tables["RQ_VITAL"],
        module=tables["RQ_MODULE"],
        run_day=tables["RQ_RUN_DAY"],
        lot_ratio=tables["RQ_LOT_RATIO"],
        wf_ratio=tables["RQ_WF_RATIO"],
    )
    required_equipment = calculate_required_equipment(
        reqb=tables["RQ_REQB"],
        plan=tables["RQ_PKG_PLAN"],
        yield_data=tables["RQ_YLD"],
        chip_qty=tables["RQ_CHIP_QTY"],
        unit_capacity=unit_capacity,
    )
    return unit_capacity, required_equipment


@st.cache_data(show_spinner=False, max_entries=16)
def get_scenario_capacity_and_demand(
    cache_key: ScenarioCacheKey,
    _scenario_tables: Mapping[str, pd.DataFrame],
    _reference_tables: Mapping[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """활성 시나리오의 대당 Capa 와 소요대수. 키만 해시하고 월 슬라이스는 안에서 한다.

    다섯 페이지가 get_capacity_and_demand 에 프레임 11개를 넘겨 st.cache_data 가 내용을
    해시했다 — 적중해도 105ms(하위 두 캐시 66+95ms). 여기서는 (reference_version,
    content_token, start, end) 만 해시해 결과 언피클 ~50ms 만 남는다. 슬라이스도 안에서
    하므로 적중 시 페이지가 미리 자르던 표 9~12개(~50ms)도 사라진다.

    `_scenario_tables` 는 키의 content_token 을 발급한 바로 그 active_scenario["tables"]
    여야 한다. 다른 객체를 넘기면 옛 표가 새 토큰에 묶인다.
    """
    _, _, start_month, end_month = cache_key
    tables = {
        name: filter_month_range(_scenario_tables[name], start_month, end_month, name)
        for name in (*CAPACITY_INPUT_TABLES, *DEMAND_INPUT_TABLES)
        if name not in MONTHLESS_INPUT_TABLES
    }
    tables.update({name: _reference_tables[name] for name in REFERENCE_INPUT_TABLES})
    # 월 축이 없는 시나리오 표는 슬라이스가 복사를 만들지 않으므로 여기서 복사한다.
    tables.update(
        {name: _scenario_tables[name].copy(deep=True) for name in SCENARIO_MONTHLESS_TABLES}
    )
    return get_capacity_and_demand(tables)
