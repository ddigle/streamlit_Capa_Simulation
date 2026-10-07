# Purpose: Shared content-addressed caches for simulation calculations.

"""Shared content-addressed caches for simulation calculations."""

import hashlib
import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable, Mapping, Sequence
from datetime import date
from typing import Any, NamedTuple

import pandas as pd
import streamlit as st

from capa_simulation.services.availability_gap import GapComparison, build_availability_gap
from capa_simulation.services.capacity_reference_editor import build_reference_edit_table
from capa_simulation.services.dashboard import (
    PRODUCTION_DETAIL_CUSTOMER_DIMENSIONS,
    PRODUCTION_DETAIL_DIMENSIONS,
    build_monthly_wafer_load_from_load,
    build_production_dashboard,
)
from capa_simulation.services.display_order import PreparedDisplayOrder
from capa_simulation.services.equipment_availability import (
    build_equipment_lifecycle_spans,
    build_space_equipment_status,
    build_weekly_equipment_availability,
)
from capa_simulation.services.load_calculator import (
    DemandBasis,
    build_monthly_volume,
    calculate_chip_and_wafer_loads,
    filter_edp_plan,
)
from capa_simulation.services.month_filter import MONTH_COLUMN, filter_month_range
from capa_simulation.services.monthly_equipment_availability import (
    build_monthly_equipment_availability,
    build_monthly_equipment_contributions,
    span_date_range,
)
from capa_simulation.services.product_share import build_product_volume
from capa_simulation.services.required_equipment import (
    calculate_required_equipment,
)
from capa_simulation.services.required_shortening import (
    TARGET_LEVELS,
    ShorteningPlan,
    plan_required_shortening,
    process_month_export_frame,
    unit_export_frame,
)
from capa_simulation.services.route_step_editor import route_step_tables
from capa_simulation.services.securement_rate import calculate_securement_rate
from capa_simulation.services.standard_target_capacity import (
    add_pkg_equivalent_standard_target,
    build_weekly_standard_target_capacity,
)
from capa_simulation.services.undated_equipment import undated_equipment
from capa_simulation.services.unit_capacity import (
    CapacityAssumptions,
    calculate_unit_capacity,
    capacity_assumptions,
)
from capa_simulation.services.usage_basis import usage_excluded_equipment
from capa_simulation.services.weighted_unit_capacity import (
    effective_process_capacity_to_month_table,
)

HomeSimulationCacheKey = tuple[int, str, int, int, str]

# 세션끼리 나누는 HOME Figure 의 칸 수 — **묶음마다** 따로 센다(`shared_home_figure_store`).
# 네 묶음 한 벌이 pickle 로 약 0.34MB 다(LOB 0.13·상세 B/N 0.14·주요공정 0.04·계획 세부수량
# 0.02 — 70공정·32개월 로컬 DB 사본의 샘플 관측). 묶음마다 32칸이면 다 차도 네 묶음 합이 한 벌
# 32칸, 곧 묶음을 가르기 전 상한(약 11MB)과 같다.
SHARED_HOME_FIGURE_MAX_ENTRIES = 32


class SharedBlobStore:
    """프로세스 공용 LRU. 값은 pickle 바이트로 둔다.

    객체를 그대로 나누면 한 세션이 꺼낸 Figure 를 고칠 때 다른 세션 화면이 바뀐다. 바이트로
    두면 꺼내는 쪽마다 제 사본을 받는다. 세션은 여러 스레드에서 돌므로 잠금으로 감싼다.
    """

    def __init__(self, max_entries: int) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._items: OrderedDict[Hashable, bytes] = OrderedDict()

    def get(self, key: Hashable) -> bytes | None:
        with self._lock:
            blob = self._items.get(key)
            if blob is not None:
                self._items.move_to_end(key)
            return blob

    def put(self, key: Hashable, blob: bytes) -> None:
        with self._lock:
            self._items[key] = blob
            self._items.move_to_end(key)
            while len(self._items) > self._max_entries:
                self._items.popitem(last=False)

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


@st.cache_resource(show_spinner=False)
def shared_home_figure_store(bundle: str) -> SharedBlobStore:
    """HOME Figure 묶음 하나(`bundle` — LOB·계획 세부수량·주요공정·상세 B/N)를 세션끼리 나누는
    저장소. 키가 내용 전체를 말하므로 비울 일이 없다.

    **묶음마다 저장소가 따로다.** 한 LRU 에 섞으면 토글 조합이 가장 많은 LOB 가 칸을 밀어
    조합이 적은 묶음까지 내쫓는다. 키는 (테마, 그 묶음의 키)다. 편집 없는 리비전(`pristine-`
    토큰)의 그림만 들어온다 — 새로고침한 세션이 Figure 생성을 건너뛰고 복원만 치른다. 값의
    형식과 복원은 `components/home_rendering.py` 가 정한다(`to_dict()` 목록, 검증 없이 다시
    세워 여덟 개에 약 0.05초 — 합성 표본의 샘플 관측).
    """
    del bundle  # 캐시 칸을 가르는 인자일 뿐 저장소 모양은 묶음과 무관하다.
    return SharedBlobStore(SHARED_HOME_FIGURE_MAX_ENTRIES)


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
    return (
        reference_version,
        scenario_token,
        start_month,
        end_month,
        display_order_digest(display_order),
    )


def display_order_digest(display_order: pd.DataFrame) -> str:
    """공용 표시순서 표(`RQ_DISPLAY_ORDER`) 내용의 SHA-256. 컬럼·dtype·행 값을 모두 덮는다.

    **표시순서는 `reference_version` 을 바꾸지 않고 바뀐다**(`reference_cache.
    apply_global_display_order`). 그래서 `reference_version` 을 키로 쓰면서 표시순서로 정렬한
    결과를 캐시하는 래퍼는 이 값도 키에 넣어야 한다 — 빠뜨리면 Admin 에서 순서를 바꾼 뒤에도
    옛 순서가 남는다.
    """
    return frame_digest(display_order)


def frame_digest(frame: pd.DataFrame) -> str:
    """프레임 내용의 SHA-256. 컬럼·dtype·행 값을 모두 덮는다 — 같은 글자면 같은 내용이다.

    **키 방침** — 이 모듈의 래퍼 키는 함수의 실제 입력 전부(이 지문·범위·날짜·선택값)를 싣고,
    **코드 상수(사용기준 규칙 `COUNTED_USAGE_BASIS`·분류 표 등)는 싣지 않는다.** 상수가 바뀌려면
    배포로 프로세스가 새로 뜨고, 캐시는 프로세스 메모리라 그때 함께 빈다.
    """
    digest = hashlib.sha256()
    digest.update("\x1f".join(map(str, frame.columns)).encode("utf-8"))
    digest.update("\x1f".join(map(str, frame.dtypes)).encode("utf-8"))
    digest.update(
        pd.util.hash_pandas_object(frame, index=True, categorize=True)
        .to_numpy(dtype="uint64")
        .tobytes()
    )
    return digest.hexdigest()


# (시나리오 키, 호기 마스터·비가동·기존보유·Cut-off 내용 지문, 달, 오늘).
RequiredShorteningCacheKey = tuple[ScenarioCacheKey, str, str, str, str, tuple[int, ...], str]


def required_shortening_cache_key(
    scenario_key: ScenarioCacheKey,
    *,
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    baseline: pd.DataFrame,
    cutoff: pd.DataFrame,
    months: tuple[int, ...],
    today: date,
) -> RequiredShorteningCacheKey:
    """필요단축일정 결과의 키. **소요대수는 해시하지 않고 시나리오 키가 대신한다.**

    소요대수(약 3MB)는 `(reference_version, content_token, 조회기간)` 이 정하므로 그 키를 그대로
    싣는다 — 내용을 해시하면 적중에도 수십 ms 를 쓴다. 설비 쪽 네 표는 저장 안 한 편집본일 수
    있어 리비전 번호가 아니라 내용 지문이다. 오늘이 바뀌면 바닥(`max(구간 앞, 오늘)`)이 달라지므로
    날짜도 키에 든다.
    """
    return (
        scenario_key,
        frame_digest(equipment),
        frame_digest(downtime),
        frame_digest(baseline),
        frame_digest(cutoff),
        tuple(int(month) for month in months),
        today.isoformat(),
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
    캐시가 빗나가면 `route_step_tables` 가 `RQ_REQB` 를 한 번만 전처리해 두 표에 나눠 준다.
    """
    del cache_key
    return route_step_tables(_upeh, _reqb)


# 기준 정보 편집표 칸 수. 편집표 여섯 개가 나눠 쓴다 — 한 시나리오·기간에 열린 탭 몇 개면
# 차므로 여러 세션·시나리오를 오가도 넉넉하다.
REFERENCE_EDIT_TABLE_MAX_ENTRIES = 24


@st.cache_data(show_spinner=False, max_entries=REFERENCE_EDIT_TABLE_MAX_ENTRIES)
def get_reference_edit_table(
    cache_key: ScenarioCacheKey,
    display_order_key: str,
    *,
    table_name: str,
    dimensions: tuple[str, ...],
    value_column: str | None,
    page: str,
    tab: str,
    _data: pd.DataFrame,
    _display_order: PreparedDisplayOrder | None,
) -> pd.DataFrame:
    """기준 정보의 열린 편집표(Wide 변환 → 표시순서 정렬 → 분류 컬럼 재배치).

    rerun 마다 다시 만들고 있었다(UPEH 2,660×39 표에서 약 320ms, 합성 표본의 샘플 관측).
    키는 `scenario_cache_key`(편집 기간) + 표시순서 내용(`display_order_digest`) + 표 이름·
    분류 컬럼·값 컬럼·화면 범위다. **표시순서 다이제스트를 빼면 안 된다** — 표시순서는
    `reference_version` 을 바꾸지 않고 바뀐다.

    `_data` 는 키의 `content_token` 을 발급한 바로 그 활성 시나리오에서 키와 같은 기간으로
    자른 표, `_display_order` 는 `display_order_key` 를 만든 `RQ_DISPLAY_ORDER` 를 준비한
    것이어야 한다. 다른 것을 넘기면 키와 내용이 어긋난다. 검증 예외는 캐시되지 않고,
    `st.cache_data` 는 꺼낼 때마다 사본을 준다.
    """
    del cache_key, display_order_key
    return build_reference_edit_table(
        _data,
        table_name=table_name,
        dimensions=dimensions,
        value_column=value_column,
        display_order=_display_order,
        page=page,
        tab=tab,
    )


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
) -> tuple[
    pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, CapacityAssumptions, pd.DataFrame
]:
    """Reuse HOME results while hashing only ``cache_key`` on warm reruns.

    마지막 원소는 제품×월 Wafer·PKG 수량(EDP 포함)이다. 제품별 비중 행이 쓰고, EDP 를 뺀
    화면에서도 색 칸을 정하는 목록으로 쓴다 — 이미 만든 Wafer 상세 환산을 묶기만 한다.

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
    unit_capacity, required_equipment = get_scenario_capacity_and_demand(
        scenario_key,
        _scenario_tables=_tables,
        _reference_tables=_reference_tables,
    )
    # 측정률 행이 없어 중립값으로 이어 간 건수와 달. **프레임이 아니라 이 값을 꺼내서
    # 돌려준다** — `attrs` 는 병합·슬라이스를 지나며 사라지고, HOME 은 대당 Capa 프레임
    # 자체를 쓰지 않는다. 시나리오 전체 기간 기준이다(조회기간 밖의 달도 센다).
    assumed_defaults = capacity_assumptions(unit_capacity)
    _, wafer_load = calculate_chip_and_wafer_loads(_plan, _yield_data, _chip_qty)
    monthly_wafer = build_monthly_wafer_load_from_load(wafer_load)
    product_volume = build_product_volume(_plan, wafer_load)
    securement_rate = get_securement_rate(scenario_key, _available_equipment, required_equipment)
    return (
        monthly_density,
        production_detail,
        monthly_wafer,
        securement_rate,
        assumed_defaults,
        product_volume,
    )


@st.cache_data(show_spinner=False, max_entries=8)
def get_home_lob_without_edp(
    cache_key: HomeSimulationCacheKey,
    _tables: Mapping[str, pd.DataFrame],
    _display_order: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """EDP 를 뺀 Density·계획 세부수량·Wafer 부하량·제품별 수량. **소요대수는 만들지 않는다.**

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
    return monthly_density, production_detail, monthly_wafer, build_product_volume(plan, wafer_load)


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


# 입장 화면 Summary 의 완성된 요약 값(`components/intro_summary`). 모든 사용자가
# 같은 값(최신 공식버전)을 보므로 서버에 한 벌만 둔다 — 세션마다 다시 만들면
# 새 탭·F5·테마 전환마다 HOME 보다 먼저 0.5초를 썼다(로컬 합성 DB 사본에서 잰 소요시간).
# 키는 (공식버전 id, 그 시나리오 이름, 공용 표시순서 판, 공정 표시명 판, 공용 판정 기준의
# 내용 지문)이고 요약에 들어가는 것을 모두 덮는다(공식 리비전은 고칠 수 없다). `_build` 는
# 키에 넣지 않는다. 머리 줄 토글 셋의 몫은 여기 넣지 않는다 — 아래 `shared_intro_toggle_store`
# 에 몫마다 따로 둔다(선행 B/O 를 저장해도 이 요약을 다시 만들지 않게).
# 일시적일 수 있는 실패(DB 잠금 등)는 `_build` 가 예외로 올리므로 여기 남지 않는다.
IntroSummaryCacheKey = tuple[str, str, int, int, str]
# 토글 몫(선행 B/O·선행 입고·GAP) 칸 수. 한 칸은 JSON 몇 KB 다.
INTRO_TOGGLE_MAX_ENTRIES = 24


@st.cache_data(show_spinner=False, max_entries=4)
def get_intro_summary_payload(
    cache_key: IntroSummaryCacheKey,
    _build: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    return _build()


@st.cache_resource(show_spinner=False)
def shared_intro_toggle_store() -> SharedBlobStore:
    """입장 화면 Summary 토글 몫(`components/intro_summary._toggle_parts`)을 세션끼리 나누는 저장소.

    `st.cache_data` 와 달리 **있는지 먼저 볼 수 있어야** 한다 — 비교 GAP 은 처음 만들 때 무거워
    없으면 HOME 페이지 앞에서 만들지 않고 「준비 중」으로 보낸 뒤 페이지 뒤에서 만든다. 키는
    공식버전 id 와 그 몫이 쓰는 프로필 판뿐이고, 값은 JSON 바이트라 꺼내는 쪽마다 제 사본을 받는다.
    """
    return SharedBlobStore(INTRO_TOGGLE_MAX_ENTRIES)


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


@st.cache_data(show_spinner=False, max_entries=8)
def get_undated_equipment(equipment: pd.DataFrame) -> pd.DataFrame:
    """일정 미정 설비 행(`services/undated_equipment.undated_equipment`)을 rerun 사이에 다시 쓴다.

    가용설비 현황은 위젯 하나에도 페이지 전체가 다시 돌고, 이 계산은 호기 마스터 검증
    (`prepare_equipment_master`)을 거쳐 3천 행에 90ms 남짓 든다. 결과는 호기 마스터 내용만으로
    정해지므로(기준일이 없다) 내용 해시가 곧 키다. Main 과 Static/Dynamic 이 같은(거르기 전) 표를
    넘겨 한 벌을 함께 쓰고, 범위는 받은 쪽이 좁힌다.
    """
    return undated_equipment(equipment)


@st.cache_data(show_spinner=False, max_entries=8)
def get_usage_excluded_equipment(equipment: pd.DataFrame) -> pd.DataFrame:
    """사용기준이 HBM 이 아니어서 가용대수에 세지 않는 행(`services/usage_basis`)을 다시 쓴다.

    일정 미정(`get_undated_equipment`)과 같은 까닭이다 — 호기 마스터 검증을 거치고 결과가 호기
    마스터 내용만으로 정해진다. Main·Static/Dynamic·필요단축일정이 거르기 전 표를 넘겨 한 벌을 함께
    쓰고 범위는 받은 쪽이 좁힌다.
    """
    return usage_excluded_equipment(equipment)


# (호기 마스터 내용 지문, 비가동 일정 내용 지문, 기준일).
SpaceStatusCacheKey = tuple[str, str, str]


def space_status_cache_key(
    equipment: pd.DataFrame, downtime: pd.DataFrame, *, as_of: date
) -> SpaceStatusCacheKey:
    """Space 기준일 상태의 키. 판정이 보는 입력을 모두 싣는다.

    두 표는 저장 안 한 편집본일 수 있어 리비전·편집본 세대가 아니라 내용 지문이다 — 세대
    번호는 세션마다 0 부터 세어 내용이 달라도 겹친다. 사용기준 규칙(`COUNTED_USAGE_BASIS`)처럼
    결과에 닿는 코드 상수는 넣지 않는다 — 이 모듈의 키 방침(`frame_digest` 아래 주석)이다.
    """
    return (frame_digest(equipment), frame_digest(downtime), as_of.isoformat())


@st.cache_data(show_spinner=False, max_entries=8)
def _cached_space_equipment_status(
    cache_key: SpaceStatusCacheKey,
    _equipment: pd.DataFrame,
    _downtime: pd.DataFrame,
    _as_of: date,
) -> pd.DataFrame:
    return build_space_equipment_status(_equipment, _downtime, as_of=_as_of)


def get_space_equipment_status(
    equipment: pd.DataFrame, downtime: pd.DataFrame, *, as_of: date
) -> pd.DataFrame:
    """Space 현황의 기준일 상태(`build_space_equipment_status`)를 같은 내용이면 다시 쓴다.

    배치 편집 중에는 한 회차에 저장본(조건 카드·FAB·층 요약)과 편집본(편집기·겹침 경고)을
    따로 판정하고, `적용` 은 `st.rerun()` 으로 두 회차를 돈다 — 캐시가 없을 때 적용 한 번에
    같은 판정을 5~6번(3천 행에 한 번 0.13초 남짓) 했다. 판정은 호기 마스터 검증을 거치므로
    검증에 실패한 편집본은 `ValueError` 를 그대로 낸다(예외는 캐시하지 않는다). 받은 프레임은
    부를 때마다 새 사본이라 고쳐 써도 캐시가 바뀌지 않는다.
    """
    return _cached_space_equipment_status(
        space_status_cache_key(equipment, downtime, as_of=as_of), equipment, downtime, as_of
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


# 시나리오 전체 기간 계산 결과의 칸 수. 70공정·30개월 합성 표본에서 한 칸이 pickle 로 약
# 16MB 다(샘플 관측) — 4칸이면 64MB 안쪽이다. 칸은 (리비전, 내용) 하나에 하나라 넉넉하다.
FULL_CAPACITY_MAX_ENTRIES = 4

# 시나리오 내용만 대표하는 키. 월 범위가 없다 — 조회기간은 이 결과를 잘라 쓴다.
FullScenarioCacheKey = tuple[int, str]


class CapacityOutcome(NamedTuple):
    """전체 기간 계산의 결과 또는 실패.

    **실패도 캐시한다.** 예외는 캐시되지 않아, 오류가 난 시나리오를 여는 실행마다 몇 초짜리
    계산을 처음부터 다시 돌게 된다.
    """

    unit_capacity: pd.DataFrame | None
    required_equipment: pd.DataFrame | None
    error: str | None


def _capacity_tables(
    scenario_tables: Mapping[str, pd.DataFrame],
    reference_tables: Mapping[str, pd.DataFrame],
    month_range: tuple[int, int] | None,
) -> dict[str, pd.DataFrame]:
    """계산 입력 표. `month_range` 가 없으면 전체 기간이다. 어느 쪽이든 사본을 넘긴다.

    **행이 없는 표는 자르지 않는다.** `filter_month_range` 는 빈 표를 「선택할 년월이 없다」로
    던지는데, 측정률 표는 비어도 계산이 1.0 가정으로 도는 정당한 상태다. 자르다 던지면 조회기간
    검사가 진짜 원인 대신 그 문구를 올려 모든 계산 화면이 엉뚱한 곳을 가리켰다(2026-09-29 리뷰).
    """
    tables = {
        name: (
            _copied(scenario_tables[name])
            if month_range is None or scenario_tables[name].empty
            else filter_month_range(scenario_tables[name], *month_range, name)
        )
        for name in (*CAPACITY_INPUT_TABLES, *DEMAND_INPUT_TABLES)
        if name not in MONTHLESS_INPUT_TABLES
    }
    tables.update({name: reference_tables[name] for name in REFERENCE_INPUT_TABLES})
    # 월 축이 없는 시나리오 표는 슬라이스가 복사를 만들지 않으므로 여기서 복사한다.
    tables.update({name: _copied(scenario_tables[name]) for name in SCENARIO_MONTHLESS_TABLES})
    return tables


def _copied(frame: pd.DataFrame) -> pd.DataFrame:
    # 세션이 들고 있는 표를 계산에 그대로 넘기지 않는다. 계산 쪽이 입력을 고치면 세션의
    # 편집본이 바뀌는데 토큰은 그대로라, 캐시와 내용이 갈라진다.
    return frame.copy(deep=True)


def _capacity_outcome(tables: Mapping[str, pd.DataFrame]) -> CapacityOutcome:
    try:
        unit_capacity, required_equipment = get_capacity_and_demand(tables)
    except ValueError as exc:
        # 기준정보 계약 위반만 결과로 담는다. 다른 예외는 코드 결함이라 그대로 올린다.
        return CapacityOutcome(None, None, str(exc))
    return CapacityOutcome(unit_capacity, required_equipment, None)


@st.cache_data(show_spinner=False, max_entries=FULL_CAPACITY_MAX_ENTRIES)
def get_full_capacity_outcome(
    cache_key: FullScenarioCacheKey,
    _scenario_tables: Mapping[str, pd.DataFrame],
    _reference_tables: Mapping[str, pd.DataFrame],
) -> CapacityOutcome:
    """시나리오 **전체 기간**의 대당 Capa 와 소요대수. 조회기간은 이 결과를 잘라 쓴다.

    월끼리 섞이는 계산이 없어(누적·이월·보간 없음) 자른 결과가 그 기간만 계산한 결과와
    같다 — 70공정 합성 표본 세 기간에서 행 차례까지 확인했다. 그래서 조회기간을 바꿔도 다시
    계산하지 않는다(처음 보는 기간마다 1.8~2.4초가 들었다, 샘플 관측).

    **어느 달이든 기준정보 오류가 있으면 결과 대신 오류를 담는다.** 보지 않는 달의 오류를
    그 달을 열 때까지 미루지 않기 위해서다(2026-09-28 사용자 결정). 리비전 저장·공식 발행
    검사도 같은 결과를 본다.

    `cache_key` 는 (reference_version, content_token) 이다. 두 표 묶음은 그 키를 만든 바로
    그 활성 시나리오·기준정보여야 한다 — `get_scenario_capacity_and_demand` 와 같은 계약이다.
    """
    del cache_key
    return _capacity_outcome(_capacity_tables(_scenario_tables, _reference_tables, None))


@st.cache_data(show_spinner=False, max_entries=16)
def get_period_capacity_error(
    cache_key: ScenarioCacheKey,
    _scenario_tables: Mapping[str, pd.DataFrame],
    _reference_tables: Mapping[str, pd.DataFrame],
) -> str | None:
    """전체 계산이 실패했을 때만 부른다. 그 오류가 조회기간 **안**에도 있는지 가른다."""
    _, _, start_month, end_month = cache_key
    tables = _capacity_tables(_scenario_tables, _reference_tables, (start_month, end_month))
    return _capacity_outcome(tables).error


def outside_period_error(start_month: int, end_month: int, error: str) -> str:
    """조회기간 밖의 달 때문에 멈췄다고 말한다. 보는 기간이 고장 났다고 읽히지 않게 한다.

    고칠 화면은 표마다 다르다 — 수율·PKG PLAN 은 생산 계획 화면이다. 「기준 정보 페이지에서」로
    못 박으면 수율 오류문이 가리키는 곳(생산 계획 → 수율 탭)과 어긋난다(2026-09-29 리뷰).
    """
    return (
        f"조회기간({_month_text(start_month)}~{_month_text(end_month)}) 밖의 달에 기준정보 "
        "오류가 있어 계산을 멈췄습니다. Capa 는 시나리오 전체 기간을 한 번에 계산하므로 어느 "
        "달이든 고쳐야 풀립니다 — 오류가 가리키는 화면(수율·PKG PLAN 은 생산 계획, 그 밖은 기준 "
        f"정보 페이지)에서 고친 뒤 새 리비전으로 저장하세요. 오류: {error}"
    )


def _month_text(month: int) -> str:
    return f"{month // 100}-{month % 100:02d}"


def slice_capacity_months(frame: pd.DataFrame, start_month: int, end_month: int) -> pd.DataFrame:
    """전체 기간 결과를 조회기간으로 자른다. `attrs` 도 같은 기준으로 다시 붙인다.

    월 컬럼이 있는 프레임(제외 목록)은 같이 자른다 — 화면은 보는 기간의 제외만 보여야
    한다. 나머지(측정률 가정 건수·달)는 시나리오 전체 값 그대로 둔다(사용자 결정).
    """
    sliced = _month_rows(frame, start_month, end_month)
    sliced.attrs = {
        name: (
            _month_rows(value, start_month, end_month)
            if isinstance(value, pd.DataFrame) and MONTH_COLUMN in value.columns
            else value
        )
        for name, value in frame.attrs.items()
    }
    return sliced


def _month_rows(frame: pd.DataFrame, start_month: int, end_month: int) -> pd.DataFrame:
    months = pd.to_numeric(frame[MONTH_COLUMN], errors="coerce")
    return frame.loc[months.between(start_month, end_month)].reset_index(drop=True)


@st.cache_data(show_spinner=False, max_entries=16)
def get_scenario_capacity_and_demand(
    cache_key: ScenarioCacheKey,
    _scenario_tables: Mapping[str, pd.DataFrame],
    _reference_tables: Mapping[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """활성 시나리오의 대당 Capa 와 소요대수를 조회기간으로 잘라 준다. 키만 해시한다.

    다섯 페이지가 get_capacity_and_demand 에 프레임 11개를 넘겨 st.cache_data 가 내용을
    해시했다 — 적중해도 105ms(하위 두 캐시 66+95ms). 여기서는 (reference_version,
    content_token, start, end) 만 해시해 결과 언피클만 남는다.

    계산은 **시나리오 전체 기간**으로 한 번 하고(`get_full_capacity_outcome`) 여기서 자른다.
    어느 달이든 기준정보 오류가 있으면 **조회기간과 상관없이 멈춘다.** 오류가 조회기간 안에도
    있으면 그 오류를 그대로, 밖에만 있으면 「조회기간 밖」이라고 말한다 — 보는 기간이 고장
    났다고 읽히지 않게.

    `_scenario_tables` 는 키의 content_token 을 발급한 바로 그 active_scenario["tables"]
    여야 한다. 다른 객체를 넘기면 옛 표가 새 토큰에 묶인다.
    """
    reference_version, content_token, start_month, end_month = cache_key
    outcome = get_full_capacity_outcome(
        (reference_version, content_token),
        _scenario_tables=_scenario_tables,
        _reference_tables=_reference_tables,
    )
    if outcome.error is not None:
        period_error = get_period_capacity_error(
            cache_key,
            _scenario_tables=_scenario_tables,
            _reference_tables=_reference_tables,
        )
        if period_error is not None:
            raise ValueError(period_error)
        raise ValueError(outside_period_error(start_month, end_month, outcome.error))
    assert outcome.unit_capacity is not None and outcome.required_equipment is not None
    return (
        slice_capacity_months(outcome.unit_capacity, start_month, end_month),
        slice_capacity_months(outcome.required_equipment, start_month, end_month),
    )


@st.cache_data(show_spinner=False, max_entries=8)
def get_required_shortening(
    cache_key: RequiredShorteningCacheKey,
    _equipment: pd.DataFrame,
    _downtime: pd.DataFrame,
    _baseline: pd.DataFrame,
    _cutoff: pd.DataFrame,
    _required_equipment: pd.DataFrame,
) -> ShorteningPlan:
    """다섯 목표의 필요단축일정. 목표·공정 선택은 이 결과를 고르기만 하므로 다시 계산하지 않는다.

    결과에는 CSV 가 호기 줄에 붙일 마스터 속성(`ShorteningPlan.unit_master`)도 실린다 — 호기
    마스터에서만 나오므로 키의 마스터 내용 지문이 그것까지 덮는다.

    프레임은 해시하지 않는다 — 키(`required_shortening_cache_key`)가 내용 지문과 시나리오 키를
    모두 싣는다. `_required_equipment` 는 키의 시나리오 키로 받은 바로 그 소요대수여야 한다.
    호기 마스터가 계약을 어기면 `ValueError` 가 그대로 올라간다(캐시에 남지 않는다).

    호기 구간은 Static/Dynamic 과 **같은 구간 캐시**(`get_equipment_lifecycle_spans`)에서 받는다.
    키의 마스터·비가동 지문을 그대로 쓰므로 다시 해시하지 않는다. 시나리오·기존보유·오늘만 바뀌어
    이 결과가 새로 돌 때도 구간(3천 행·32개월에 2초 남짓, 샘플 관측)은 다시 만들지 않고, 두 탭의
    구간 범위가 같으면 한 벌을 나눈다.
    """
    _, equipment_digest, downtime_digest, _, _, months, today = cache_key
    span = span_date_range(months, _cutoff) if months else None
    spans = (
        get_equipment_lifecycle_spans(
            (equipment_digest, downtime_digest, span[0].isoformat(), span[1].isoformat()),
            _equipment=_equipment,
            _downtime=_downtime,
        )
        if span is not None
        else None
    )
    return plan_required_shortening(
        equipment=_equipment,
        downtime=_downtime,
        baseline=_baseline,
        cutoff=_cutoff,
        required_equipment=_required_equipment,
        months=months,
        today=date.fromisoformat(today),
        spans=spans,
    )


@st.cache_data(show_spinner=False, max_entries=16)
def get_required_shortening_csvs(
    cache_key: RequiredShorteningCacheKey,
    level: float,
    processes: tuple[str, ...],
    months: tuple[int, ...],
    _plan: ShorteningPlan,
) -> tuple[bytes, bytes, bytes]:
    """필요단축일정 CSV 세 벌의 바이트 — 고른 목표의 호기별, 다섯 목표의 호기별, 고른 목표의
    공정·월.

    탭이 열린 rerun 마다(목표만 바꿔도) 세 표를 다시 만들고 직렬화했다(2026-10-08 점검 A10).
    계획은 이미 `get_required_shortening` 이 캐시하므로, 그 키에 화면이 고르는 것(목표·공정 차례·
    달)만 더한 키로 바이트를 둔다. `processes` 는 **화면의 차례 그대로**다 — CSV 의 공정 차례가
    그것을 따른다. `_plan` 은 같은 `cache_key` 로 받은 바로 그 계획이어야 한다(해시하지 않는다).
    지연 생성(콜러블)은 쓰지 않는다(TODO [결정] — 콜러블의 예외는 삼켜지고 AppTest 가 바이트를 못
    본다).

    바이트는 BOM 이 붙은 UTF-8 이다 — Excel 이 한글을 깨뜨리지 않게(`table_toolbar.CSV_MIME` 과 짝).
    """
    del cache_key
    frames = (
        unit_export_frame(_plan, (level,), processes),
        unit_export_frame(_plan, TARGET_LEVELS, processes),
        process_month_export_frame(_plan, (level,), processes, months),
    )
    units, all_levels, process_months = (
        frame.to_csv(index=False).encode("utf-8-sig") for frame in frames
    )
    return units, all_levels, process_months


# Static/Dynamic 의 구간 → 월별 → 비교. 필요단축일정과 같은 방식이다 — 프레임은 `_` 인자로 해시하지
# 않고, 키가 **함수의 실제 입력 전부**를 내용 지문으로 싣는다. 세 서비스 함수는 오늘 날짜·설정을
# 읽지 않는다(오늘은 페이지의 기본 조회기간과 샘플 fleet 을 거쳐 들어오고, 그 둘은 날짜·마스터
# 지문이 덮는다). 코드 상수는 키에 넣지 않는다(`frame_digest` 의 키 방침).

# (호기 마스터 내용 지문, 비가동 내용 지문, 구간 시작, 구간 끝)
EquipmentSpanCacheKey = tuple[str, str, str, str]


def equipment_span_cache_key(
    *,
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    start_date: date,
    end_date: date,
) -> EquipmentSpanCacheKey:
    """`get_equipment_lifecycle_spans` 의 키. 마스터·비가동은 저장 안 한 편집본·샘플일 수 있어 내용
    지문이다. `required_shortening_cache_key` 의 두 지문과 같은 함수라 필요단축일정과 키가 겹친다.
    """
    return (
        frame_digest(equipment),
        frame_digest(downtime),
        start_date.isoformat(),
        end_date.isoformat(),
    )


@st.cache_data(show_spinner=False, max_entries=8)
def get_equipment_lifecycle_spans(
    cache_key: EquipmentSpanCacheKey,
    _equipment: pd.DataFrame,
    _downtime: pd.DataFrame,
) -> pd.DataFrame:
    """세는 데 쓰는 호기 생애주기 구간(`build_equipment_lifecycle_spans(with_unit_share=True)`).

    Static/Dynamic 은 보기(가용대수 비교 · 분류별 내역 · 확보율 교차검증)나 같은 탭의 위젯 하나만
    바꿔도 페이지 전체가 다시 돌아, 상태 판정을 바뀌는 날마다 다시 하는 이 계산이 매번 들었다
    (2026-10-08 점검 A2 — 데모 19행 0.34초, 3천 행 복제 6개월 1.45초·32개월 2.35초). 필요단축일정도
    이 캐시를 쓴다(`get_required_shortening`).

    `_equipment`·`_downtime` 은 키의 두 지문을 만든 바로 그 프레임이어야 한다. 마스터가 계약을
    어기면 `ValueError` 가 그대로 올라간다(캐시에 남지 않는다).
    """
    _, _, start, end = cache_key
    return build_equipment_lifecycle_spans(
        _equipment,
        _downtime,
        start_date=date.fromisoformat(start),
        end_date=date.fromisoformat(end),
        with_unit_share=True,
    )


# (구간·기존보유·Cut-off 내용 지문, 달, 환산비 지문)
DynamicMonthlyCacheKey = tuple[str, str, str, tuple[int, ...], str]


def dynamic_monthly_cache_key(
    *,
    spans: pd.DataFrame,
    baseline: pd.DataFrame,
    cutoff: pd.DataFrame,
    months: Sequence[int],
    conversion_ratios: Mapping[str, float] | None,
) -> DynamicMonthlyCacheKey:
    """월별 Dynamic(`build_monthly_equipment_availability`·`_contributions`)의 키.

    **환산비는 따로 싣는다** — 구간 표에는 환산비 칸이 없어 구간 지문이 그것을 덮지 않는다. 없음과
    빈 매핑은 서비스가 같게 읽으므로(`conversion_ratios or {}`) 같은 지문이다.
    """
    ratios = sorted((str(unit), float(ratio)) for unit, ratio in (conversion_ratios or {}).items())
    return (
        frame_digest(spans),
        frame_digest(baseline),
        frame_digest(cutoff),
        tuple(int(month) for month in months),
        hashlib.sha256(repr(ratios).encode("utf-8")).hexdigest(),
    )


# (월별 키, Static 내용 지문)
AvailabilityComparisonCacheKey = tuple[DynamicMonthlyCacheKey, str]


def availability_comparison_cache_key(
    monthly_key: DynamicMonthlyCacheKey, *, static: pd.DataFrame
) -> AvailabilityComparisonCacheKey:
    """`get_availability_comparison` 의 키. Static(`RQ_EQP_AVBL`)은 공정 × 월이라 작아 내용을
    해시한다 — 기준정보 판·시나리오 토큰으로 대신하지 않는다."""
    return (monthly_key, frame_digest(static))


@st.cache_data(show_spinner=False, max_entries=16)
def get_availability_comparison(
    cache_key: AvailabilityComparisonCacheKey,
    _spans: pd.DataFrame,
    _baseline: pd.DataFrame,
    _cutoff: pd.DataFrame,
    _static: pd.DataFrame,
    _conversion_ratios: Mapping[str, float] | None,
) -> tuple[pd.DataFrame, GapComparison]:
    """Static/Dynamic 의 월별 Dynamic 분해와 Static 대비 비교(`build_availability_gap`).

    보기 전환마다 다시 돌던 둘을 묶어 둔다(점검 A2). 프레임·매핑은 키를 만든 바로 그 값이어야
    한다(`dynamic_monthly_cache_key` + `availability_comparison_cache_key`).
    """
    (_, _, _, months, _), _ = cache_key
    monthly = build_monthly_equipment_availability(
        _spans, _baseline, _cutoff, months, conversion_ratios=_conversion_ratios
    )
    return monthly, build_availability_gap(monthly, _static, months)


@st.cache_data(show_spinner=False, max_entries=8)
def get_monthly_equipment_contributions(
    cache_key: DynamicMonthlyCacheKey,
    _spans: pd.DataFrame,
    _baseline: pd.DataFrame,
    _cutoff: pd.DataFrame,
    _conversion_ratios: Mapping[str, float] | None,
) -> pd.DataFrame:
    """분류별 내역의 호기별 기여(`build_monthly_equipment_contributions`).

    `호기 목록` 과 칸 누르기가 쓰고, 분류·표시를 바꾸는 rerun 마다 다시 만들지 않는다. 키는 월별과
    같다(`dynamic_monthly_cache_key`).
    """
    _, _, _, months, _ = cache_key
    return build_monthly_equipment_contributions(
        _spans, _baseline, _cutoff, months, conversion_ratios=_conversion_ratios
    )
