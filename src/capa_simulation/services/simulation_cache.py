# Purpose: Shared content-addressed caches for simulation calculations.

"""Shared content-addressed caches for simulation calculations."""

import functools
import hashlib
import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable, Mapping, Sequence
from datetime import date
from typing import Any, NamedTuple

import pandas as pd
import streamlit as st

from capa_simulation.services.availability_gap import GapComparison, build_availability_gap
from capa_simulation.services.availability_sheet import AvailabilitySheet, build_availability_sheet
from capa_simulation.services.capacity_reference_editor import build_reference_edit_table
from capa_simulation.services.dashboard import (
    PRODUCTION_DETAIL_CUSTOMER_DIMENSIONS,
    PRODUCTION_DETAIL_DIMENSIONS,
    build_monthly_wafer_load_from_load,
    build_production_dashboard,
)
from capa_simulation.services.display_order import (
    PreparedDisplayOrder,
    apply_display_order,
    prepare_display_order,
    reorder_display_columns,
)
from capa_simulation.services.equipment_availability import (
    build_equipment_lifecycle_spans,
    build_equipment_status_as_of,
    build_inactive_equipment_month_view,
    build_milestone_transition_events,
    build_space_equipment_status,
    build_weekly_equipment_availability,
    inactive_equipment_rows,
)
from capa_simulation.services.load_calculator import (
    DemandBasis,
    build_monthly_volume,
    calculate_chip_and_wafer_loads,
    filter_edp_plan,
    plan_to_edit_table,
    split_editable_yield_rows,
    yield_to_edit_table,
)
from capa_simulation.services.month_filter import MONTH_COLUMN, filter_month_range
from capa_simulation.services.monthly_equipment_availability import (
    build_monthly_equipment_availability,
    build_monthly_equipment_contributions,
    span_date_range,
)
from capa_simulation.services.process_capa_detail import (
    PRODUCT_ROW_LIMIT,
    ProcessCalculationRows,
    ProcessMonthTrace,
    build_process_month_trace,
    build_process_product_demand,
    process_calculation_rows,
)
from capa_simulation.services.process_equipment_timeline import (
    ProcessEquipmentTimeline,
    build_process_equipment_timeline,
)
from capa_simulation.services.product_share import build_product_volume
from capa_simulation.services.required_equipment import (
    REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR,
    REQUIRED_LOAD_EXCLUSIONS_ATTR,
    RESULT_DIMENSIONS,
    UNROUTED_LOADS_ATTR,
    RequiredExclusionCounts,
    calculate_required_equipment,
    required_equipment_to_month_table,
    required_exclusion_counts,
)
from capa_simulation.services.required_shortening import (
    TARGET_LEVELS,
    MonthlyTarget,
    ShorteningPlan,
    plan_required_shortening,
    process_month_export_frame,
    unit_export_frame,
)
from capa_simulation.services.route_step_editor import route_step_tables
from capa_simulation.services.schedule_confirmation import schedule_confirmation_issues
from capa_simulation.services.securement_cross_check import (
    CrossCheck,
    cross_check_from_monthly,
)
from capa_simulation.services.securement_rate import calculate_securement_rate
from capa_simulation.services.shortening_baseline import ShorteningBaseline
from capa_simulation.services.shortening_progress import compare_progress, progress_export_frame
from capa_simulation.services.standard_target_capacity import (
    add_pkg_equivalent_standard_target,
    build_weekly_standard_target_capacity,
    exclude_er_required_equipment,
    split_standard_target_required_equipment,
)
from capa_simulation.services.undated_equipment import undated_equipment
from capa_simulation.services.unit_capacity import (
    CAPACITY_EXCLUSIONS_ATTR,
    UNIT_CAPACITY_DIMENSIONS,
    CapacityAssumptions,
    calculate_unit_capacity,
    capacity_assumptions,
    unit_capacity_to_month_table,
)
from capa_simulation.services.usage_basis import usage_excluded_equipment
from capa_simulation.services.weekly_availability_input import (
    build_weekly_availability_template,
)
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


# (시나리오 키, 설비 마스터·비가동·기존보유·Cut-off 내용 지문, 달, 오늘).
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


@st.cache_data(show_spinner=False, max_entries=16)
def check_scenario_capacity(
    cache_key: ScenarioCacheKey,
    _scenario_tables: Mapping[str, pd.DataFrame],
    _reference_tables: Mapping[str, pd.DataFrame],
    _required_equipment: Callable[[], pd.DataFrame] | None = None,
) -> bool:
    """이 키의 대당 Capa·소요대수 계산이 서는지만 본다. 적중이면 프레임을 풀지 않는다.

    키 전용 파생 캐시(확보율 등)가 오류를 냈을 때, 그 오류가 시나리오 계산이 멈춘 것인지 그 뒤
    단계(가용대수·확보율 검증)의 것인지 가르는 데 쓴다 — 앞의 것만 「계산 멈춤」이다. 실패는
    캐시되지 않으므로 오류가 난 시나리오는 매번 `get_scenario_capacity_and_demand` 가 다시
    던진다(그쪽의 전체 기간 결과가 실패를 담아 두어 싸다). 부르는 쪽은
    `page_bootstrap.stop_calculation_on_error` 로 감싸 사이드바의 「✓ 적용」을 거둔다.

    가용설비 현황(Static/Dynamic·필요단축일정)은 이것을 **오류 확인**으로 쓴다 — 소요대수 프레임이
    필요 없는 보기에서도 기준정보 오류를 같은 문구로 알리되 프레임은 풀지 않는다. 그 화면은
    「✓ 적용」을 쓰지 않으므로 감싸지 않고, 같은 키·같은 표 묶음의 로더
    (`scenario_required_equipment`)를 `_required_equipment` 로 준다. 빗나간 회차에는 그 로더로
    계산을 확인한다 — 같은 회차에 소요대수를 쓰는 곳(달 범위·계획·교차검증)이 그 로더를 나눠
    프레임을 다시 풀지 않는다.
    """
    if _required_equipment is not None:
        _required_equipment()
        return True
    get_scenario_capacity_and_demand(
        cache_key,
        _scenario_tables=_scenario_tables,
        _reference_tables=_reference_tables,
    )
    return True


def scenario_required_equipment(
    cache_key: ScenarioCacheKey,
    *,
    scenario_tables: Mapping[str, pd.DataFrame],
    reference_tables: Mapping[str, pd.DataFrame],
) -> Callable[[], pd.DataFrame]:
    """이 키의 소요대수를 **부를 때만** 꺼내는 로더(`get_scenario_capacity_and_demand` 의 둘째 값).

    키 전용 캐시(오류 확인·달 범위·필요단축일정·확보율 교차검증)가 빗나갈 때만 프레임이 필요하므로
    프레임 대신 이것을 넘긴다 — 적중 회차에는 소요대수(합성 표본 30개월에 pickle 약 12MB, 샘플
    관측)를 풀지 않는다. 한 로더는 프레임을 **한 번만** 푼다 — 한 회차에 여러 캐시가 함께 빗나가도
    (첫 진입, 조회기간·토큰이 바뀐 회차) 언피클은 한 번이다. 실패는 기억하지 않아 다음에 부르면 다시
    꺼낸다. 로더는 그 회차에서만 쓰고 세션·캐시에 두지 않는다 — 키가 바뀐 회차는 새 로더다.

    두 표 묶음은 키의 content_token 을 발급한 바로 그 활성 시나리오·기준정보여야 한다. 계산 함수는
    부를 때 이 모듈에서 찾는다 — 페이지 테스트가 그 속성을 바꾼다. 받은 프레임은 읽기만 한다(같은
    회차의 다른 쓰임이 같은 객체를 받는다).
    """

    @functools.cache
    def load() -> pd.DataFrame:
        _, required_equipment = get_scenario_capacity_and_demand(
            cache_key,
            _scenario_tables=scenario_tables,
            _reference_tables=reference_tables,
        )
        return required_equipment

    return load


@st.cache_data(show_spinner=False, max_entries=16)
def get_required_month_span(
    cache_key: ScenarioCacheKey,
    _required_equipment: Callable[[], pd.DataFrame],
) -> tuple[int, int] | None:
    """이 키의 소요대수가 있는 첫 달·끝 달(`생산계획년월` 의 숫자 최소·최대). 없으면 `None`.

    필요단축일정이 고를 달(조회기간 ∩ 이 범위)을 정하는 데는 이 두 수만 든다. 적중이면 소요대수를
    풀지 않고, 빗나가면 로더를 부른다. 로더는 이 키로 소요대수를 꺼내는 것
    (`scenario_required_equipment`)이어야 한다. 계산 오류는 캐시되지 않고 그대로 올라간다.
    """
    required_equipment = _required_equipment()
    if required_equipment.empty or MONTH_COLUMN not in required_equipment.columns:
        return None
    present = pd.to_numeric(required_equipment[MONTH_COLUMN], errors="coerce").dropna()
    if present.empty:
        return None
    return int(present.min()), int(present.max())


@st.cache_data(show_spinner=False, max_entries=16)
def get_scenario_securement_rate(
    cache_key: ScenarioCacheKey,
    _scenario_tables: Mapping[str, pd.DataFrame],
    _reference_tables: Mapping[str, pd.DataFrame],
    _available_equipment: pd.DataFrame,
) -> pd.DataFrame:
    """확보율을 시나리오 키만으로 꺼낸다. **적중이면 소요대수를 풀지 않는다.**

    `get_securement_rate` 도 키만 해시하지만 부르는 쪽이 소요대수를 넘겨야 해, 그것만 쓰면 적중해도
    `get_scenario_capacity_and_demand` 의 결과(대당 Capa 와 함께 pickle 약 16MB, 합성 표본의 샘플
    관측)를 매 회차 언피클한다. 빗나가면 그 둘을 이 안에서 부르고, 확보율은 HOME 과 같은
    `get_securement_rate` 칸을 쓴다. `_available_equipment` 는 키의 시나리오·월 범위로 자른
    `RQ_EQP_AVBL` 이어야 한다(`get_securement_rate` 와 같은 계약).
    """
    _, required_equipment = get_scenario_capacity_and_demand(
        cache_key,
        _scenario_tables=_scenario_tables,
        _reference_tables=_reference_tables,
    )
    return get_securement_rate(cache_key, _available_equipment, required_equipment)


class ScenarioResultSummary(NamedTuple):
    """산출 결과가 열린 탭과 무관하게 매 회차 쓰는 작은 파생값. 큰 프레임 대신 이것만 푼다."""

    capacity_exclusions: pd.DataFrame
    capacity_assumptions: CapacityAssumptions
    unit_capacity_rows: int
    required_exclusions: pd.DataFrame
    # 소요대수의 공정 고유값(원본 값·원본 차례). 표시순서 정렬은 부르는 쪽이 한다.
    processes: pd.DataFrame
    # 계획 쪽에서 소요대수에 들지 않은 것 — 부하량에서 빠진 계획과 경로 없는 계획 부하.
    load_exclusions: pd.DataFrame
    unrouted_loads: pd.DataFrame


@st.cache_data(show_spinner=False, max_entries=16)
def get_scenario_result_summary(
    cache_key: ScenarioCacheKey,
    _scenario_tables: Mapping[str, pd.DataFrame],
    _reference_tables: Mapping[str, pd.DataFrame],
) -> ScenarioResultSummary:
    """대당 Capa·소요대수 결과의 제외 목록·측정률 가정·행 수·공정 고유값.

    `attrs` 는 병합·슬라이스를 지나며 사라지므로 프레임째가 아니라 값을 꺼내 담는다. 계산 오류는
    캐시되지 않아 매 회차 다시 던진다 — 부르는 쪽은 `stop_calculation_on_error` 로 감싼다.
    """
    unit_capacity, required_equipment = get_scenario_capacity_and_demand(
        cache_key,
        _scenario_tables=_scenario_tables,
        _reference_tables=_reference_tables,
    )
    processes = required_equipment[["공정"]].drop_duplicates()
    processes.attrs = {}
    return ScenarioResultSummary(
        capacity_exclusions=unit_capacity.attrs.get(CAPACITY_EXCLUSIONS_ATTR, pd.DataFrame()),
        capacity_assumptions=capacity_assumptions(unit_capacity),
        unit_capacity_rows=len(unit_capacity),
        required_exclusions=required_equipment.attrs.get(
            REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR, pd.DataFrame()
        ),
        processes=processes,
        load_exclusions=required_equipment.attrs.get(REQUIRED_LOAD_EXCLUSIONS_ATTR, pd.DataFrame()),
        unrouted_loads=required_equipment.attrs.get(UNROUTED_LOADS_ATTR, pd.DataFrame()),
    )


@st.cache_data(show_spinner=False, max_entries=16)
def get_scenario_exclusion_counts(
    cache_key: ScenarioCacheKey,
    _scenario_tables: Mapping[str, pd.DataFrame],
    _reference_tables: Mapping[str, pd.DataFrame],
) -> RequiredExclusionCounts:
    """소요대수에 들지 않은 수요 건수(조회기간 기준). HOME 이 결론 위 한 줄에 쓴다.

    정수 넷이라 적중 회차의 값이 작다 — 결과 요약(`get_scenario_result_summary`)은 제외 목록
    프레임째 담아 HOME 의 매 회차에 풀기에는 크다. 키·`_` 인자 계약은
    `get_scenario_capacity_and_demand` 와 같다.
    """
    _, required_equipment = get_scenario_capacity_and_demand(
        cache_key,
        _scenario_tables=_scenario_tables,
        _reference_tables=_reference_tables,
    )
    return required_exclusion_counts(required_equipment)


@st.cache_data(show_spinner=False, max_entries=32)
def get_display_ordered_values(
    values: pd.DataFrame,
    display_order_key: str,
    page: str,
    tab: str,
    _display_order: PreparedDisplayOrder | None,
) -> list[str]:
    """분류 한 컬럼의 고유값 표를 표시순서로 정렬해 글자 목록으로 낸다(필터 선택지).

    표가 작아(공정 수 행) 내용째 해시한다. `apply_display_order` 는 규칙 필터·충돌 검사 고정비가
    있어 70행에도 수 ms 가 든다(합성 표본의 샘플 관측). `_display_order` 는 `display_order_key` 를
    만든 `RQ_DISPLAY_ORDER` 를 준비한 것이어야 한다 — 표시순서는 `reference_version` 을 바꾸지 않고
    바뀐다. 규칙 충돌 같은 검증 예외는 캐시되지 않고 그대로 난다.
    """
    del display_order_key
    column = str(values.columns[0])
    return apply_display_order(values, _display_order, page, tab)[column].astype(str).tolist()


@st.cache_data(show_spinner=False, max_entries=16)
def get_required_month_table(
    cache_key: ScenarioCacheKey,
    display_order_key: str,
    page: str,
    tab: str,
    _scenario_tables: Mapping[str, pd.DataFrame],
    _reference_tables: Mapping[str, pd.DataFrame],
    _display_order: PreparedDisplayOrder | None,
) -> tuple[pd.DataFrame, list[str]]:
    """소요대수 월 표(표시순서 정렬·분류 컬럼 재배치)와 그 분류 컬럼 차례.

    키는 시나리오 키 + 표시순서 지문(`display_order_digest`) + 화면 범위다. 상세 토글·컬럼
    필터는 이 뒤에서 매 회차 건다. `_display_order` 는 `display_order_key` 를 만든
    `RQ_DISPLAY_ORDER` 를 준비한 것이어야 한다.
    """
    del display_order_key
    _, required_equipment = get_scenario_capacity_and_demand(
        cache_key,
        _scenario_tables=_scenario_tables,
        _reference_tables=_reference_tables,
    )
    table = apply_display_order(
        required_equipment_to_month_table(required_equipment), _display_order, page, tab
    )
    return reorder_display_columns(table, RESULT_DIMENSIONS, _display_order, page, tab)


@st.cache_data(show_spinner=False, max_entries=8)
def get_step_unit_capacity_table(
    cache_key: ScenarioCacheKey,
    display_order_key: str,
    page: str,
    tab: str,
    _scenario_tables: Mapping[str, pd.DataFrame],
    _reference_tables: Mapping[str, pd.DataFrame],
    _display_order: PreparedDisplayOrder | None,
) -> tuple[pd.DataFrame, list[str]]:
    """STEP별 대당 Capa 월 표(전 공정 피벗 → 표시순서 정렬 → 분류 컬럼 재배치)와 그 분류 컬럼 차례.

    공정 필터는 이 뒤에서 매 회차 건다(지금도 정렬 뒤에 걸렸다) — 공정을 바꿀 때마다 전 공정 STEP
    월표를 다시 피벗·정렬하지 않는다. 키는 시나리오 키 + 표시순서 지문 + 화면 범위다. 대당 Capa 는
    빗나갈 때만 이 안에서 받는다.
    """
    del display_order_key
    unit_capacity, _ = get_scenario_capacity_and_demand(
        cache_key,
        _scenario_tables=_scenario_tables,
        _reference_tables=_reference_tables,
    )
    table = apply_display_order(
        unit_capacity_to_month_table(unit_capacity), _display_order, page, tab
    )
    return reorder_display_columns(table, list(UNIT_CAPACITY_DIMENSIONS), _display_order, page, tab)


@st.cache_data(show_spinner=False, max_entries=32)
def get_effective_process_capacity_table(
    cache_key: ScenarioCacheKey,
    _scenario_tables: Mapping[str, pd.DataFrame],
    _reference_tables: Mapping[str, pd.DataFrame],
    detail_level: str,
) -> pd.DataFrame:
    """공정 유효 Capa 월 표. 공정 필터는 이 뒤에 걸리므로 필터마다 같은 계산을 반복하고 있었다.

    소요대수는 키가 정하므로 빗나갈 때만 이 안에서 받는다 — 넘겨받으면 적중할 때도 부르는 쪽이
    소요대수를 언피클해야 한다. `_scenario_tables` 는 키의 content_token 을 발급한 활성 시나리오의
    표여야 한다(`get_scenario_capacity_and_demand` 와 같은 계약).
    """
    _, required_equipment = get_scenario_capacity_and_demand(
        cache_key,
        _scenario_tables=_scenario_tables,
        _reference_tables=_reference_tables,
    )
    return effective_process_capacity_to_month_table(required_equipment, detail_level)


# 캐시가 빗나갈 때만 부르는 프레임 로더. 키가 내용을 정하는 래퍼는 프레임 대신 이것을 받아,
# 적중한 회차에는 입력 조각을 자르지도 않는다.
FrameSource = pd.DataFrame | Callable[[], pd.DataFrame]


def _frame_from(source: FrameSource) -> pd.DataFrame:
    return source() if callable(source) else source


@st.cache_data(show_spinner=False, max_entries=16)
def get_route_step_tables(
    cache_key: ScenarioCacheKey,
    _upeh: FrameSource,
    _reqb: FrameSource,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """공정별 Capa STEP 구성 탭의 (요약, 선택 목록).

    둘 다 순수 함수라 내용 토큰으로 캐시한다. 쓰는 곳은 STEP 구성 탭 본문과 STEP 팝업뿐이라
    페이지는 **그 탭이 보이거나 팝업이 열린 회차에만** 부른다.
    키는 (reference_version, content_token, start_month, end_month) — 프레임은 해시하지 않는다.
    두 입력은 프레임 또는 로더이고 로더는 빗나갈 때만 부른다. 캐시가 빗나가면
    `route_step_tables` 가 `RQ_REQB` 를 한 번만 전처리해 두 표에 나눠 준다.
    """
    del cache_key
    return route_step_tables(_frame_from(_upeh), _frame_from(_reqb))


@st.cache_data(show_spinner=False, max_entries=8)
def _prepared_display_order(
    display_order_key: str, _display_order: pd.DataFrame
) -> PreparedDisplayOrder | None:
    del display_order_key
    return prepare_display_order(_display_order)


def get_prepared_display_order(display_order: pd.DataFrame) -> PreparedDisplayOrder | None:
    """공용 표시순서 표를 검증·파생한 것(`prepare_display_order`). 키는 **내용 지문**이다.

    계산 화면 공통 진입(`load_page_context`)이 회차마다 부른다. 지문 계산이 검증·파생보다 싸서
    내용이 같으면 검증·파생을 다시 하지 않는다. 표시순서는 `reference_version` 을 바꾸지 않고
    바뀌므로(Admin 교체·리비전 불러오기) 버전이 아니라 `display_order_digest` 로 가른다.
    `st.cache_data` 는 꺼낼 때마다 사본을 주므로 호출부가 규칙을 고쳐도 다른 회차가 오염되지
    않고, 검증 예외는 캐시되지 않아 매번 다시 난다.
    """
    return _prepared_display_order(display_order_digest(display_order), display_order)


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
    _data: FrameSource,
    _display_order: PreparedDisplayOrder | None,
) -> pd.DataFrame:
    """기준 정보의 열린 편집표(Wide 변환 → 표시순서 정렬 → 분류 컬럼 재배치).

    rerun 마다 다시 만들고 있었다(UPEH 2,660×39 표에서 약 320ms, 합성 표본의 샘플 관측).
    키는 `scenario_cache_key`(편집 기간) + 표시순서 내용(`display_order_digest`) + 표 이름·
    분류 컬럼·값 컬럼·화면 범위다. **표시순서 다이제스트를 빼면 안 된다** — 표시순서는
    `reference_version` 을 바꾸지 않고 바뀐다.

    `_data` 는 키의 `content_token` 을 발급한 바로 그 활성 시나리오에서 키와 같은 기간으로
    자른 표(또는 그 표를 자르는 로더 — 빗나갈 때만 부른다), `_display_order` 는
    `display_order_key` 를 만든 `RQ_DISPLAY_ORDER` 를 준비한 것이어야 한다. 다른 것을 넘기면
    키와 내용이 어긋난다. 검증 예외는 캐시되지 않고, `st.cache_data` 는 꺼낼 때마다 사본을 준다.
    """
    del cache_key, display_order_key
    return build_reference_edit_table(
        _frame_from(_data),
        table_name=table_name,
        dimensions=dimensions,
        value_column=value_column,
        display_order=_display_order,
        page=page,
        tab=tab,
    )


class StandardTargetSummary(NamedTuple):
    """표준 목표가 매 회차 쓰는 시나리오 수준의 작은 값. 큰 프레임 대신 이것만 푼다."""

    # 표준 목표 예외(Pre B/D 의 Dummy)로 뺀 소요대수 상세 행 수. 공정 선택과 무관하다.
    exception_rows: int
    # ER 을 뺀 `RQ_REQB` 의 공정 고유값(원본 값·원본 차례). 표시순서 정렬은 부르는 쪽이 한다.
    processes: pd.DataFrame


# 표준 목표 제외를 거친 소요대수의 칸 수. 한 칸이 pickle 로 약 9.5MB 다(69,081행 합성 표본의 샘플
# 관측). 키가 시나리오 하나라 몇 칸이면 된다.
STANDARD_TARGET_SPLIT_MAX_ENTRIES = 4


@st.cache_data(show_spinner=False, max_entries=STANDARD_TARGET_SPLIT_MAX_ENTRIES)
def get_standard_target_split(
    cache_key: ScenarioCacheKey,
    _scenario_tables: Mapping[str, pd.DataFrame],
    _reference_tables: Mapping[str, pd.DataFrame],
) -> tuple[pd.DataFrame, int]:
    """표준 목표 제외(ER·Pre B/D Dummy)를 거친 소요대수(공정 필터 전)와 예외로 뺀 행 수.

    분리 결과는 소요대수 하나만의 함수라 시나리오 키가 정한다 — 날짜·분류 수준·가용대수는 이
    프레임을 바꾸지 않으므로 키에 넣지 않는다(넣으면 같은 프레임이 조건마다 따로 쌓인다). 로직
    분석은 칸을 하나 고를 때마다 소요대수가 필요한데, 대당 Capa 와 함께 풀면 약 16MB(합성 표본의
    샘플 관측)이고 이 프레임만 풀면 그 절반 아래다. 주간 결과·요약 캐시가
    빗나갈 때도 여기서 받는다.
    """
    _, required_equipment = get_scenario_capacity_and_demand(
        cache_key,
        _scenario_tables=_scenario_tables,
        _reference_tables=_reference_tables,
    )
    return split_standard_target_required_equipment(required_equipment)


@st.cache_data(show_spinner=False, max_entries=16)
def get_standard_target_summary(
    cache_key: ScenarioCacheKey,
    _scenario_tables: Mapping[str, pd.DataFrame],
    _reference_tables: Mapping[str, pd.DataFrame],
) -> StandardTargetSummary:
    """표준 목표의 예외 행 수와 공정 필터 선택지 재료. 키는 시나리오 키 하나다.

    표시 항목·PKG 기준·팝업 열기처럼 결과와 무관한 조작은 이 캐시에 적중해, 소요대수 언피클·ER/예외
    분리·`RQ_REQB` 전체 ER 제외(합성 표본에서 회차당 약 0.13초, 샘플 관측)를 다시 하지 않는다.
    주차별 가용대수가 비어 화면이 멈추는 회차에도 예외 행 수는 그려야 하므로 가용대수와 무관한
    이 키에 둔다. 계산 오류는 캐시되지 않아 매 회차 다시 던진다 — 부르는 쪽은
    `stop_calculation_on_error` 로 감싼다.
    """
    _, exception_rows = get_standard_target_split(
        cache_key,
        _scenario_tables=_scenario_tables,
        _reference_tables=_reference_tables,
    )
    processes = exclude_er_required_equipment(_scenario_tables["RQ_REQB"])[["공정"]]
    processes = processes.drop_duplicates()
    processes.attrs = {}
    return StandardTargetSummary(exception_rows=exception_rows, processes=processes)


# 표준 목표 주간 결과의 키 — (시나리오 키, 주차별 가용대수 내용 지문, 시작일, 종료일, 분류 수준,
# 공정 선택, 제품 선택). 선택은 정렬한 튜플이고 빈 튜플은 「거르지 않음」이다.
StandardTargetWeeklyKey = tuple[
    ScenarioCacheKey, str, str, str, str, tuple[str, ...], tuple[str, ...]
]


def standard_target_weekly_cache_key(
    scenario_key: ScenarioCacheKey,
    *,
    availability: pd.DataFrame,
    start_date: date,
    end_date: date,
    detail_level: str,
    processes: Sequence[str] = (),
    products: Sequence[str] = (),
) -> StandardTargetWeeklyKey:
    """표준 목표 주간 결과의 키. **소요대수는 해시하지 않고 시나리오 키가 대신한다.**

    소요대수 상세는 사내·합성 모두 5만 행을 넘는다. Streamlit 1.63 은 5만 행 이상인 DataFrame
    인자를 1만 행 표본으로만 해시해, 표본 밖 한 행만 바뀌는 편집(UPEH·REQB 한 칸)이 캐시에 묻혀
    옛 결과가 나왔다. 소요대수는 `(reference_version, content_token, 월 범위)` 가 정하므로 그
    키를 그대로 싣는다. 가용대수는 설비 DB 의 비버전 최신값이라 내용 지문이다.

    키에는 그 호출이 소요대수에 건 **행 필터 전부**를 싣는다 — 공정 선택(빈 선택은 전체)과 제품
    선택(재공 현황만 쓴다). 제품 선택을 빼면 재공 현황이 채운 일부 제품 결과가 같은 날짜·분류
    수준의 표준 목표에 적중한다. 월은 조회일이 아니라 달력 주차의 귀속 달로 잡은 범위다.
    """
    return (
        scenario_key,
        frame_digest(availability),
        start_date.isoformat(),
        end_date.isoformat(),
        detail_level,
        _row_selection(processes),
        _row_selection(products),
    )


def _row_selection(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value) for value in values}))


def _scenario_month_slice(
    scenario_tables: Mapping[str, pd.DataFrame], name: str, scenario_key: ScenarioCacheKey
) -> pd.DataFrame:
    """키의 월 범위로 자른 시나리오 표. 키와 내용이 한 객체에서 나오게 래퍼 안에서 자른다."""
    _, _, start_month, end_month = scenario_key
    return filter_month_range(scenario_tables[name], start_month, end_month, name)


def _standard_target_demand(
    cache_key: StandardTargetWeeklyKey,
    scenario_tables: Mapping[str, pd.DataFrame],
    reference_tables: Mapping[str, pd.DataFrame],
) -> pd.DataFrame:
    """표준 목표 제외(ER·Pre B/D Dummy)를 적용하고 키의 공정·제품 선택으로 거른 소요대수."""
    scenario_key, _, _, _, _, processes, products = cache_key
    prepared, _ = get_standard_target_split(
        scenario_key,
        _scenario_tables=scenario_tables,
        _reference_tables=reference_tables,
    )
    if not processes and not products:
        return prepared
    selected = pd.Series(True, index=prepared.index)
    if processes:
        selected &= prepared["공정"].isin(processes)
    if products:
        selected &= prepared["제품정보"].isin(products)
    return prepared.loc[selected].reset_index(drop=True)


@st.cache_data(show_spinner=False, max_entries=32)
def get_weekly_standard_target_capacity(
    cache_key: StandardTargetWeeklyKey,
    _scenario_tables: Mapping[str, pd.DataFrame],
    _reference_tables: Mapping[str, pd.DataFrame],
    _weekly_availability: pd.DataFrame,
) -> pd.DataFrame:
    """주차별 표준 목표 Capa. 키(`standard_target_weekly_cache_key`)만 해시한다.

    소요대수·`RQ_RUN_DAY` 는 이 안에서 `_scenario_tables` 와 키의 월로 얻는다 — 페이지가 미리
    잘라 넘기면 키와 내용이 갈라질 자리가 생긴다. `_scenario_tables` 는 키의 content_token 을
    발급한 바로 그 활성 시나리오의 표, `_weekly_availability` 는 키의 지문을 만든 바로 그
    가용대수여야 한다. 계산 오류(ValueError)는 캐시되지 않아 매번 다시 드러난다.
    """
    scenario_key, _, start_text, end_text, detail_level, _, _ = cache_key
    return build_weekly_standard_target_capacity(
        required_equipment=_standard_target_demand(cache_key, _scenario_tables, _reference_tables),
        run_day=_scenario_month_slice(_scenario_tables, "RQ_RUN_DAY", scenario_key),
        weekly_availability=_weekly_availability,
        start_date=date.fromisoformat(start_text),
        end_date=date.fromisoformat(end_text),
        detail_level=detail_level,
    )


@st.cache_data(show_spinner=False, max_entries=16)
def get_pkg_equivalent_standard_target(
    cache_key: StandardTargetWeeklyKey,
    _scenario_tables: Mapping[str, pd.DataFrame],
    _reference_tables: Mapping[str, pd.DataFrame],
    _weekly_availability: pd.DataFrame,
) -> pd.DataFrame:
    """PKG Kea 환산 표준 목표 Capa. 키와 `_` 인자 계약은 `get_weekly_standard_target_capacity`
    와 같다. PKG 기준이 켜진 회차에만 부른다 — PKG 연결 오류는 그때만 드러난다.

    주간 결과는 같은 키의 주간 캐시에서 받는다(적중이면 언피클만). `RQ_PKG_PLAN` 은 키의 월로
    이 안에서 자른다.
    """
    scenario_key, _, _, _, detail_level, _, _ = cache_key
    weekly_target = get_weekly_standard_target_capacity(
        cache_key,
        _scenario_tables=_scenario_tables,
        _reference_tables=_reference_tables,
        _weekly_availability=_weekly_availability,
    )
    return add_pkg_equivalent_standard_target(
        weekly_target=weekly_target,
        required_equipment=_standard_target_demand(cache_key, _scenario_tables, _reference_tables),
        plan=_scenario_month_slice(_scenario_tables, "RQ_PKG_PLAN", scenario_key),
        detail_level=detail_level,
    )


class StandardTargetOutcome(NamedTuple):
    """전체 공정으로 계산한 주간 결과 또는 실패와, 계산 뒤 공정 거르기가 계산 전 거르기와 같은지.

    **실패도 담는다.** 고르지 않은 공정의 데이터 오류(소요기준 둘·원수요 부하량 불일치·RUN_DAY 누락·
    PKG 연결 누락)로 전체 계산이 실패해도, 공정을 고른 화면은 그 공정만으로 다시 계산해야 한다.
    예외를 캐시하지 않으면 그 화면이 매 회차 전체 계산을 다시 돌린다.
    """

    weekly_target: pd.DataFrame | None
    error: str | None
    # 원본 공정명이 이미 다듬어져 있다(앞뒤 공백 없음). 계산은 공정명을 strip 하므로, 아니면 계산 뒤
    # 거르기가 계산 전(원본 이름) 거르기와 다른 행을 고를 수 있다.
    exact_process_filter: bool


@st.cache_data(show_spinner=False, max_entries=16)
def get_all_process_standard_target(
    cache_key: StandardTargetWeeklyKey,
    _scenario_tables: Mapping[str, pd.DataFrame],
    _reference_tables: Mapping[str, pd.DataFrame],
    _weekly_availability: pd.DataFrame,
) -> StandardTargetOutcome:
    """공정 선택 없이(전체 공정) 계산한 주간 결과. 부르는 쪽은 `get_standard_target_weekly_result`
    와 PKG 환산(`get_all_process_pkg_standard_target`)이다 — 키의 공정·제품 선택은 비어 있다.

    공정끼리 섞이는 계산이 없어(원수요 키·분류 그룹·RUN_DAY·가용대수·PKG 계획 연결이 모두 공정을
    싣는다) 전체 결과를 공정으로 거른 것이 고른 공정만 계산한 것과 같다. 그래서 공정 조합마다 따로
    계산·캐시하지 않는다.
    """
    scenario_key, _, start_text, end_text, detail_level, _, _ = cache_key
    prepared, _ = get_standard_target_split(
        scenario_key,
        _scenario_tables=_scenario_tables,
        _reference_tables=_reference_tables,
    )
    raw_processes = prepared["공정"].astype("string")
    exact = bool(raw_processes.str.strip().eq(raw_processes).fillna(False).all())
    try:
        weekly_target = build_weekly_standard_target_capacity(
            required_equipment=prepared,
            run_day=_scenario_month_slice(_scenario_tables, "RQ_RUN_DAY", scenario_key),
            weekly_availability=_weekly_availability,
            start_date=date.fromisoformat(start_text),
            end_date=date.fromisoformat(end_text),
            detail_level=detail_level,
        )
    except ValueError as exc:
        return StandardTargetOutcome(None, str(exc), exact)
    return StandardTargetOutcome(weekly_target, None, exact)


@st.cache_data(show_spinner=False, max_entries=16)
def get_all_process_pkg_standard_target(
    cache_key: StandardTargetWeeklyKey,
    _scenario_tables: Mapping[str, pd.DataFrame],
    _reference_tables: Mapping[str, pd.DataFrame],
    _weekly_availability: pd.DataFrame,
) -> StandardTargetOutcome:
    """전체 공정 결과의 PKG Kea 환산. 키와 `_` 인자 계약은 `get_all_process_standard_target` 과
    같다.

    주간 결과는 같은 키의 `get_all_process_standard_target` 에서 받는다(적중이면 언피클만). 그쪽이
    실패했으면 그 실패를 그대로 낸다. **비PKG 결과와 캐시 함수를 나눈다** — 한 캐시 함수가 제
    자신을 부르면 Streamlit 1.63 의 계산 잠금(`threading.Lock`, 재진입 불가)이 같은 칸에서 교착할
    수 있다.
    """
    base = get_all_process_standard_target(
        cache_key,
        _scenario_tables=_scenario_tables,
        _reference_tables=_reference_tables,
        _weekly_availability=_weekly_availability,
    )
    if base.weekly_target is None:
        return base
    scenario_key, _, _, _, detail_level, _, _ = cache_key
    prepared, _ = get_standard_target_split(
        scenario_key,
        _scenario_tables=_scenario_tables,
        _reference_tables=_reference_tables,
    )
    try:
        weekly_target = add_pkg_equivalent_standard_target(
            weekly_target=base.weekly_target,
            required_equipment=prepared,
            plan=_scenario_month_slice(_scenario_tables, "RQ_PKG_PLAN", scenario_key),
            detail_level=detail_level,
        )
    except ValueError as exc:
        return StandardTargetOutcome(None, str(exc), base.exact_process_filter)
    return StandardTargetOutcome(weekly_target, None, base.exact_process_filter)


def get_standard_target_weekly_result(
    cache_key: StandardTargetWeeklyKey,
    *,
    pkg: bool,
    _scenario_tables: Mapping[str, pd.DataFrame],
    _reference_tables: Mapping[str, pd.DataFrame],
    _weekly_availability: pd.DataFrame,
) -> pd.DataFrame:
    """표준 목표 화면의 주간 결과(`pkg` 면 PKG 환산). 공정 선택은 전체 공정 결과를 거른다.

    전체 공정 결과(`get_all_process_standard_target`, PKG 는
    `get_all_process_pkg_standard_target`)를 한 번 두고 고른 공정으로 거른다 — 공정 조합마다 주간
    계산을 다시 돌리지 않는다. **거른 결과가 고른 공정만 계산한 결과와 다를 수 있는 자리는 고른
    공정만 계산하는 길(`get_weekly_standard_target_capacity`·`get_pkg_equivalent_standard_target`)로
    간다** — 셋이다.

    - 전체 계산이 실패했다: 고르지 않은 공정의 오류가 고른 공정의 결과를 막지 않는다(고른 공정에도
      오류가 있으면 그 길의 문구로 멈춘다). 공정을 고르지 않았으면 그 오류를 그대로 던진다.
    - 원본 공정명에 앞뒤 공백이 있다: 계산은 공정명을 다듬으므로 계산 뒤 거르기가 다른 행을 고를
      수 있다.
    - 거른 결과가 비었다: 고른 공정만 계산하는 길의 빈 결과(컬럼만 있는 표)를 그대로 낸다.

    제품 선택이 있는 호출(재공 현황)은 거르지 않고 고른 공정·제품만 계산하는 길로 간다. 키와 `_`
    인자 계약은 `get_weekly_standard_target_capacity` 와 같다.
    """
    scenario_key, availability_digest, start_text, end_text, detail_level, processes, products = (
        cache_key
    )
    if not products:
        all_processes: StandardTargetWeeklyKey = (
            scenario_key,
            availability_digest,
            start_text,
            end_text,
            detail_level,
            (),
            (),
        )
        all_process_result = (
            get_all_process_pkg_standard_target if pkg else get_all_process_standard_target
        )
        outcome = all_process_result(
            all_processes,
            _scenario_tables=_scenario_tables,
            _reference_tables=_reference_tables,
            _weekly_availability=_weekly_availability,
        )
        if outcome.weekly_target is None:
            if not processes:
                raise ValueError(outcome.error)
        elif not processes:
            return outcome.weekly_target
        elif outcome.exact_process_filter:
            selected = outcome.weekly_target.loc[
                outcome.weekly_target["공정"].isin(processes)
            ].reset_index(drop=True)
            if not selected.empty:
                return selected
    filtered = get_pkg_equivalent_standard_target if pkg else get_weekly_standard_target_capacity
    return filtered(
        cache_key,
        _scenario_tables=_scenario_tables,
        _reference_tables=_reference_tables,
        _weekly_availability=_weekly_availability,
    )


@st.cache_data(show_spinner=False, max_entries=16)
def get_weekly_availability_template_csv(
    processes: tuple[str, ...],
    start_date: date,
    end_date: date,
    availability_key: str,
    _saved: pd.DataFrame,
) -> bytes:
    """표준 목표 주차별 가용설비 CSV 양식의 바이트(BOM 이 붙은 UTF-8).

    양식(공정 × 주차, 저장된 가용대수를 싣는다)과 그 직렬화는 캐시가 없으면 매 회차 든다(합성 표본
    9,170행에서 약 12ms, 샘플 관측). 키는 입력 전부다 — 공정 **차례**(양식 행 차례가 그것을
    따른다)·시작·종료일·저장된 가용대수의 내용 지문(`frame_digest`). `_saved` 는 그 지문을 만든
    바로 그 프레임이어야 한다.
    지연 생성(콜러블)은 쓰지 않는다(TODO [결정] 2026-09-18 — 콜러블의 예외는 삼켜지고 AppTest 가
    바이트를 못 본다).
    """
    del availability_key
    template = build_weekly_availability_template(
        list(processes), start_date, end_date, saved=_saved
    )
    return template.to_csv(index=False).encode("utf-8-sig")


# 내려받기 CSV 바이트의 키 — (용도, 표 내용 지문, 분류 컬럼, 서식). 서식은 소수 자리·값 서식처럼
# 바이트를 정하는 나머지 인자를 글자로 적은 것이다.
CsvExportKey = tuple[str, str, tuple[str, ...], str]


def csv_export_key(
    purpose: str,
    table: pd.DataFrame,
    classification_columns: Sequence[str],
    format_text: str,
) -> CsvExportKey:
    """화면 표를 내보내는 CSV 의 키. 표는 내용 지문이라 필터·표시순서·조건이 무엇이든 같은 표면
    같다."""
    return (purpose, frame_digest(table), tuple(classification_columns), format_text)


@st.cache_data(show_spinner=False, max_entries=16)
def get_export_csv(cache_key: CsvExportKey, _build: Callable[[], bytes]) -> bytes:
    """화면 표의 내려받기 CSV 바이트. 키가 같으면 `_build` 를 부르지 않는다.

    캐시가 없으면 내려받기를 누르지 않아도 매 회차 내보내기 표 조립과 직렬화가 든다(소요대수 상세
    2,660행에서 약 70ms, 합성 표본의 샘플 관측). 콜러블 지연 생성은 쓰지 않는다(TODO [결정]
    2026-09-18) — 대신 표 내용 지문 키로 바이트를 둔다. `_build` 는 **키를 만든 바로 그 표와 키에
    적은 서식으로만** 바이트를 만드는 함수여야 한다(`functools.partial` 로 인자를 박아 넘긴다).
    빗나가면 이 회차에서 바로 부르므로 오류는 지금처럼 화면에 드러나고 캐시되지 않는다. 코드
    상수(컬럼 라벨)는 키에 넣지 않는다(키 방침).
    """
    del cache_key
    return _build()


# 생산 계획 편집표 원본의 칸 수. 한 시나리오·조회기간에 표 하나라 세션·시나리오 몇 개를 오가도
# 넉넉하다.
PLAN_EDIT_TABLE_MAX_ENTRIES = 8


@st.cache_data(show_spinner=False, max_entries=PLAN_EDIT_TABLE_MAX_ENTRIES)
def get_plan_edit_table(
    cache_key: ScenarioCacheKey,
    display_order_key: str,
    _plan: pd.DataFrame,
    _display_order: PreparedDisplayOrder | None,
) -> pd.DataFrame:
    """생산 계획 PKG PLAN 편집표의 원본(월 Wide 피벗 → 표시순서 정렬).

    편집표는 미적용 편집을 지키려고 닫힌 탭에서도 매 회차 그리므로 원본도 매 회차 필요하다. 환산
    조건 토글·탭 전환은 입력이 같아 피벗(합성 표본에서 약 20ms, 샘플 관측)을 다시 하지 않는다. 키는
    `get_reference_edit_table` 과 같은 꼴 — 편집 기간의 `scenario_cache_key` + 표시순서 지문이다.
    편집 적용·붙여넣기 적용·가상 제품 등록·되돌리기는 모두 새(또는 리비전 고정) content_token 을
    낸다.

    `_plan` 은 키의 content_token 을 발급한 바로 그 활성 시나리오에서 키와 같은 기간으로 자른
    `RQ_PKG_PLAN`, `_display_order` 는 `display_order_key` 를 만든 `RQ_DISPLAY_ORDER` 를 준비한
    것이어야 한다. 검증 예외는 캐시되지 않고, `st.cache_data` 는 꺼낼 때마다 사본을 준다.
    """
    del cache_key, display_order_key
    return plan_to_edit_table(_plan, _display_order)


class YieldEditTables(NamedTuple):
    """수율 편집표 원본과 표에 실을 수 없어 잠근 행(값 결측·0 이하·100% 초과)."""

    table: pd.DataFrame
    locked: pd.DataFrame


@st.cache_data(show_spinner=False, max_entries=PLAN_EDIT_TABLE_MAX_ENTRIES)
def get_yield_edit_tables(
    cache_key: ScenarioCacheKey,
    display_order_key: str,
    _yield_data: pd.DataFrame,
    _display_order: PreparedDisplayOrder | None,
) -> YieldEditTables:
    """생산 계획 수율 편집표의 원본과 잠근 행. 키와 `_` 인자 계약은 `get_plan_edit_table` 과 같다.

    잠근 행은 적용 때 원본 그대로 되붙이는 재료라(`restore_locked_yield_rows`) 표와 한 묶음으로
    낸다 — 같은 입력의 결정적 출력이다. 표를 세울 수 없는 오류(연결 키 결측·중복)는 캐시되지 않아
    매 회차 다시 나고, 화면은 지금처럼 수율 탭에만 알린다.
    """
    del cache_key, display_order_key
    editable, locked = split_editable_yield_rows(_yield_data)
    return YieldEditTables(
        table=yield_to_edit_table(editable, _display_order, locked=locked), locked=locked
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
    # 같은 자리라, 같은 시나리오·월 범위면 Static Capa 화면들·공정 Capa 상세와 한 번만 계산한다.
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

    가용설비 현황은 위젯 하나에도 페이지 전체가 다시 돌고, 이 계산은 설비 마스터 검증
    (`prepare_equipment_master`)을 거쳐 3천 행에 90ms 남짓 든다. 결과는 설비 마스터 내용만으로
    정해지므로(기준일이 없다) 내용 해시가 곧 키다. Main 과 Static/Dynamic 이 같은(거르기 전) 표를
    넘겨 한 벌을 함께 쓰고, 범위는 받은 쪽이 좁힌다.
    """
    return undated_equipment(equipment)


@st.cache_data(show_spinner=False, max_entries=8)
def get_usage_excluded_equipment(equipment: pd.DataFrame) -> pd.DataFrame:
    """사용기준이 HBM·EDP 가 아니어서 가용대수에 세지 않는 행(`services/usage_basis`)을 다시 쓴다.

    일정 미정(`get_undated_equipment`)과 같은 까닭이다 — 설비 마스터 검증을 거치고 결과가 호기
    마스터 내용만으로 정해진다. Main·Static/Dynamic·필요단축일정이 거르기 전 표를 넘겨 한 벌을 함께
    쓰고 범위는 받은 쪽이 좁힌다.
    """
    return usage_excluded_equipment(equipment)


# (설비 마스터 내용 지문, 오늘).
ScheduleConfirmationCacheKey = tuple[str, str]


@st.cache_data(show_spinner=False, max_entries=8)
def _cached_schedule_confirmation_issues(
    cache_key: ScheduleConfirmationCacheKey, _equipment: pd.DataFrame
) -> pd.DataFrame:
    _, today = cache_key
    return schedule_confirmation_issues(_equipment, today=date.fromisoformat(today))


def get_schedule_confirmation_issues(equipment: pd.DataFrame, *, today: date) -> pd.DataFrame:
    """일정 확인 알림 행(`services/schedule_confirmation.schedule_confirmation_issues`)을 다시 쓴다.

    가용설비 현황은 위젯 하나에도 페이지 전체가 다시 돌고 RawData 는 숨은 탭에서도
    그려진다. 고르기는 날짜 칸을 단계마다 읽어 3천 행에 40ms 남짓 들고 키 지문은 그
    10분의 1쯤이다(합성 표본을 3천 행으로 늘려 잰 샘플 관측).

    키는 설비 마스터 내용 지문 + 오늘이다. 미확인이 오늘에 따라 바뀌고, 표는 저장 안 한
    편집본일 수 있어 리비전·편집본 세대가 아니라 내용 지문이다(`space_status_cache_key` 와
    같은 까닭). 그래서 Main 호기 현황(저장본)과 RawData 경고(편집본·미리보기 후보)가 이 한
    길을 쓰고, 아직 고치지 않은 편집본은 저장본 사본이라 한 벌을 나눈다. 프레임은 해시하지
    않는다. 범위(공정·설비명)는 받은 쪽이 좁힌다.
    """
    return _cached_schedule_confirmation_issues(
        (frame_digest(equipment), today.isoformat()), equipment
    )


# (설비 마스터 내용 지문, 비가동 일정 내용 지문, 기준일).
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
    같은 판정을 5~6번(3천 행에 한 번 0.13초 남짓) 했다. 판정은 설비 마스터 검증을 거치므로
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
    return full_capacity_outcome(_scenario_tables, _reference_tables)


def full_capacity_outcome(
    scenario_tables: Mapping[str, pd.DataFrame],
    reference_tables: Mapping[str, pd.DataFrame],
) -> CapacityOutcome:
    """`get_full_capacity_outcome` 의 캐시 없는 순수 코어 — 같은 표 묶음, 같은 계산, 같은 실패 판정.

    Streamlit 실행 문맥이 없는 배경 작업(공식버전 자동 갱신)이 쓴다. 화면은 이것을 직접 부르지 않고
    캐시된 `get_full_capacity_outcome` 을 쓴다.
    """
    return _capacity_outcome(_capacity_tables(scenario_tables, reference_tables, None))


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
    _required_equipment: Callable[[], pd.DataFrame],
) -> ShorteningPlan:
    """다섯 목표의 필요단축일정. 목표·공정 선택은 이 결과를 고르기만 하므로 다시 계산하지 않는다.

    결과에는 CSV 가 호기 줄에 붙일 마스터 속성(`ShorteningPlan.unit_master`)도 실린다 — 호기
    마스터에서만 나오므로 키의 마스터 내용 지문이 그것까지 덮는다.

    프레임은 해시하지 않는다 — 키(`required_shortening_cache_key`)가 내용 지문과 시나리오 키를
    모두 싣는다. **소요대수는 빗나갈 때만 이 안에서** 로더로 꺼낸다 — 적중 회차에는 그 프레임을
    풀지 않는다. 로더는 키의 시나리오 키로 소요대수를 꺼내는 것(`scenario_required_equipment`)이어야
    한다. 설비 마스터가 계약을 어기면 `ValueError` 가 그대로 올라간다(캐시에 남지 않는다).

    호기 구간은 Static/Dynamic 과 **같은 구간 캐시**(`get_equipment_lifecycle_spans`)에서 받는다.
    키의 마스터·비가동 지문을 그대로 쓰므로 다시 해시하지 않는다. 시나리오·기존보유·오늘만 바뀌어
    이 결과가 새로 돌 때도 구간(3천 행·32개월에 2초 남짓, 샘플 관측)은 다시 만들지 않고, 두 탭의
    구간 범위가 같으면 한 벌을 나눈다.
    """
    _, equipment_digest, downtime_digest, _, _, months, today = cache_key
    required_equipment = _required_equipment()
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
        required_equipment=required_equipment,
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


@st.cache_data(show_spinner=False, max_entries=16)
def get_shortening_progress(
    cache_key: RequiredShorteningCacheKey,
    baseline_id: str,
    level: float,
    _plan: ShorteningPlan,
    _baseline: ShorteningBaseline,
) -> pd.DataFrame:
    """필요단축일정 진척 비교 — 고른 목표에서 기준선(과거)과 지금 계획(현재)을 짝지은 행.

    계획은 `get_required_shortening` 이 이미 캐시하므로, 그 키에 기준선 id·목표만 더한다. **기준선은
    고칠 수 없어** id 가 내용을 정한다(지우고 같은 id 로 다시 생기는 일이 없다 — uuid). `_plan` 은
    같은 `cache_key` 로 받은 바로 그 계획, `_baseline` 은 그 id 로 읽은 기준선이어야 한다(해시하지
    않는다). 「비교 안 함」 회차는 이 함수까지 오지 않는다.
    """
    del cache_key, baseline_id
    return compare_progress(
        _baseline.units_at(level),
        _plan.at(level).units,
        current_processes=_plan.processes,
        today=_plan.today,
    )


@st.cache_data(show_spinner=False, max_entries=16)
def get_shortening_progress_csv(
    cache_key: RequiredShorteningCacheKey,
    baseline_id: str,
    level: float,
    processes: tuple[str, ...],
    _rows: pd.DataFrame,
) -> bytes:
    """「진척 비교 CSV」 의 바이트(BOM 이 붙은 UTF-8). `processes` 는 화면의 카드 차례다.

    필요단축일정 CSV 세 벌과 같은 규칙이다 — 키 캐시이고 지연 생성(콜러블)은 쓰지 않는다. `_rows` 는
    같은 계획 키·기준선·목표로 받은 `get_shortening_progress` 의 결과여야 한다.
    """
    del cache_key, baseline_id
    frame = progress_export_frame(_rows, level=level, processes=processes)
    return frame.to_csv(index=False).encode("utf-8-sig")


# Static/Dynamic 의 구간 → 월별 → 비교. 필요단축일정과 같은 방식이다 — 프레임은 `_` 인자로 해시하지
# 않고, 키가 **함수의 실제 입력 전부**를 내용 지문으로 싣는다. 세 서비스 함수는 오늘 날짜·설정을
# 읽지 않는다(오늘은 페이지의 기본 조회기간과 샘플 fleet 을 거쳐 들어오고, 그 둘은 날짜·마스터
# 지문이 덮는다). 코드 상수는 키에 넣지 않는다(`frame_digest` 의 키 방침).

# (설비 마스터 내용 지문, 비가동 내용 지문, 구간 시작, 구간 끝)
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


# (실제 월별 키, 비가동 비운 반사실 월별 키 — 없으면 None, RQ_EQP_OWN·LENT·AVBL 내용 지문)
AvailabilitySheetCacheKey = tuple[
    DynamicMonthlyCacheKey, DynamicMonthlyCacheKey | None, str, str, str
]


def availability_sheet_cache_key(
    actual_key: DynamicMonthlyCacheKey,
    free_key: DynamicMonthlyCacheKey | None,
    *,
    static_owned: pd.DataFrame,
    static_lent: pd.DataFrame,
    static_available: pd.DataFrame,
) -> AvailabilitySheetCacheKey:
    """`get_availability_sheet` 의 키. 월별 키 둘은 구간·기존보유·Cut-off·달·환산비 지문을 담고,
    Static 세 표는 공정 × 월이라 작아 내용을 해시한다."""
    return (
        actual_key,
        free_key,
        frame_digest(static_owned),
        frame_digest(static_lent),
        frame_digest(static_available),
    )


@st.cache_data(show_spinner=False, max_entries=16)
def get_availability_sheet(
    cache_key: AvailabilitySheetCacheKey,
    _actual_monthly: pd.DataFrame,
    _free_spans: pd.DataFrame | None,
    _baseline: pd.DataFrame,
    _cutoff: pd.DataFrame,
    _conversion_ratios: Mapping[str, float] | None,
    _static_owned: pd.DataFrame,
    _static_lent: pd.DataFrame,
    _static_available: pd.DataFrame,
) -> AvailabilitySheet:
    """「Static 대비 일정」 비교 시트(`build_availability_sheet`, 9행의 월 × 공정 재료).

    `_actual_monthly` 는 키의 실제 월별 키로 받은 월별 분해(`get_availability_comparison`)이고,
    `_free_spans` 는 같은 마스터·같은 범위에서 비가동만 비운 생애주기 구간이다(키의 반사실 월별
    키를 만든 그 구간 — 페이지는 `get_equipment_lifecycle_spans` 에 빈 비가동으로 받는다). 반사실
    키가 None 이면 보유·대여를 비운 시트다(「가용대수 비교」 그림 — 반사실 구간을 만들지 않는다).
    프레임은 해시하지 않는다(`_` 인자 — 5만 행 표본 해시 함정).
    """
    actual_key, free_key, _, _, _ = cache_key
    months = actual_key[3]
    free_monthly = (
        None
        if free_key is None or _free_spans is None
        else build_monthly_equipment_availability(
            _free_spans, _baseline, _cutoff, months, conversion_ratios=_conversion_ratios
        )
    )
    return build_availability_sheet(
        _actual_monthly,
        free_monthly,
        _static_owned,
        _static_lent,
        _static_available,
        months,
    )


# Main(호기 현황·비가동 호기·Qual 일정)의 판정. 페이지에 fragment 가 없어 같은 보기를 열어 둔 채
# 다른 위젯·사이드바를 만져도 페이지 전체가 다시 돌므로 판정을 캐시한다. 키는 **거른 뒤의**
# 마스터·비가동 내용 지문과 그 판정의 날짜 인자다 — 공정·추가 조건 필터와 저장본·샘플 전환이 지문을
# 바꾼다. 거르기 전 표나 리비전 id 로 키를 잡으면 필터를 바꿔도 옛 표가 남는다. 판정 함수들은 오늘
# 날짜·설정·세션을 읽지 않는다. 공정 표시명·오늘 선은 캐시 밖에서 입힌다. 검증에 실패한 표의
# `ValueError` 는 캐시에 남지 않는다.

# (거른 마스터 내용 지문, 거른 비가동 내용 지문, 날짜 인자 isoformat)
EquipmentJudgementCacheKey = tuple[str, str, str]


@st.cache_data(show_spinner=False, max_entries=8)
def _cached_inactive_equipment_month(
    cache_key: EquipmentJudgementCacheKey,
    _equipment: pd.DataFrame,
    _downtime: pd.DataFrame,
) -> tuple[tuple[date, ...], pd.DataFrame]:
    _, _, month = cache_key
    moments, inactive = build_inactive_equipment_month_view(
        _equipment, _downtime, month=date.fromisoformat(month)
    )
    return tuple(moments), inactive


def get_inactive_equipment_month(
    equipment: pd.DataFrame, downtime: pd.DataFrame, *, month: date
) -> tuple[list[date], pd.DataFrame]:
    """Main 「비가동 호기 › 그 달 전체」 — (잰 시점, 그 달 비가동 호기).

    `build_inactive_equipment_month_view` 의 캐시다.

    시점(한 달 30여 개)마다 판정을 다시 하는 보기라 사내 규모(호기 1,566·비가동 300, 합성 사본)에서
    한 번에 2초 남짓 든다(샘플 관측). 결과는 **그 달(년·월)**과 두 표로만 정해지므로 키의 날짜는 그
    달 1일이다 — 같은 달 안에서 기준일만 옮기면 다시 계산하지 않고, 달이 바뀌면 새로 잰다.
    """
    cache_key = (
        frame_digest(equipment),
        frame_digest(downtime),
        date(month.year, month.month, 1).isoformat(),
    )
    moments, inactive = _cached_inactive_equipment_month(cache_key, equipment, downtime)
    return list(moments), inactive


@st.cache_data(show_spinner=False, max_entries=8)
def _cached_lifecycle_gantt_spans(
    cache_key: EquipmentSpanCacheKey,
    _equipment: pd.DataFrame,
    _downtime: pd.DataFrame,
) -> pd.DataFrame:
    _, _, start, end = cache_key
    return build_equipment_lifecycle_spans(
        _equipment,
        _downtime,
        start_date=date.fromisoformat(start),
        end_date=date.fromisoformat(end),
    )


def get_lifecycle_gantt_spans(
    equipment: pd.DataFrame, downtime: pd.DataFrame, *, start_date: date, end_date: date
) -> pd.DataFrame:
    """Main 「호기 현황 › 생애주기 일정」 의 구간(`build_equipment_lifecycle_spans`, 지분 없이).

    그림은 40대만 그리지만 「나머지 N행」 을 세려면 거른 호기 전체의 구간이 든다 — 사내 규모 합성
    사본에서 한 번에 1초 남짓이다(샘플 관측). 키는 `equipment_span_cache_key` 와 같은 꼴(거른 두
    표의 내용 지문 + 범위)이지만 **세는 구간(`get_equipment_lifecycle_spans`, 지분·집계분류가 바뀌는
    날에도 끊는다)과는 다른 캐시**다 — 끊는 자리가 달라 서로 대신할 수 없다.
    """
    cache_key = equipment_span_cache_key(
        equipment=equipment, downtime=downtime, start_date=start_date, end_date=end_date
    )
    return _cached_lifecycle_gantt_spans(cache_key, equipment, downtime)


# (Static/Dynamic 비교 키, 소요대수를 낸 시나리오 키)
SecurementCrossCheckCacheKey = tuple[AvailabilityComparisonCacheKey, ScenarioCacheKey]


class SecurementCrossCheckResult(NamedTuple):
    """확보율 교차검증 결과. 맞대지 않았으면 `check` 가 없다.

    까닭은 차례대로 본다 — 소요대수가 비면 `has_demand` 가 거짓이고, 소요대수는 있는데 Static 이
    비면 `has_demand` 만 참이다. 화면은 이 차례로 안내 문구를 고른다.
    """

    has_demand: bool
    check: CrossCheck | None


def securement_cross_check_result(
    static: pd.DataFrame, monthly: pd.DataFrame, required_equipment: pd.DataFrame
) -> SecurementCrossCheckResult:
    """`cross_check_from_monthly` 를 맞댈 것이 있을 때만 부른다(캐시 없음).

    소요대수나 Static 이 비면 맞대지 않는다. 맞대지 못하면(`KeyError`·`ValueError`) 그대로 올라간다.
    """
    if required_equipment.empty:
        return SecurementCrossCheckResult(has_demand=False, check=None)
    if static.empty:
        return SecurementCrossCheckResult(has_demand=True, check=None)
    return SecurementCrossCheckResult(
        has_demand=True,
        check=cross_check_from_monthly(static, monthly, required_equipment),
    )


@st.cache_data(show_spinner=False, max_entries=8)
def get_securement_cross_check(
    cache_key: SecurementCrossCheckCacheKey,
    _monthly: pd.DataFrame,
    _static: pd.DataFrame,
    _required_equipment: Callable[[], pd.DataFrame],
) -> SecurementCrossCheckResult:
    """Static/Dynamic 「확보율 교차검증」(`securement_cross_check_result`).

    그 보기를 열어 둔 rerun(공정 바꾸기·다른 위젯·사이드바)마다 다시 맞대지 않게 캐시한다. 입력 셋은
    키가 모두 정한다 — 월별 Dynamic 은 비교 키 안의 월별 키(구간·기존보유·Cut-off·달·환산비 지문),
    Static 은 비교 키 안의 Static 지문, 소요대수는 시나리오 키(reference_version·content_token·
    조회기간)다. 프레임은 해시하지 않는다: `_monthly`·`_static` 은 그 비교 키로 받은 월별·
    Static 이다.

    **소요대수는 로더로 받아 빗나갈 때만 푼다** — 적중 회차에는 그 프레임을 풀지 않는다. 로더는 키의
    시나리오 키로 소요대수를 꺼내는 것(`scenario_required_equipment`)이어야 한다. 공정 선택·표시명·
    반올림은 캐시 밖이다. 맞대지 못하면(`KeyError`·`ValueError`) 캐시에 남지 않고 그대로 올라간다.
    """
    del cache_key
    return securement_cross_check_result(_static, _monthly, _required_equipment())


@st.cache_data(show_spinner=False, max_entries=8)
def _cached_equipment_status_as_of(
    cache_key: EquipmentJudgementCacheKey,
    _equipment: pd.DataFrame,
    _downtime: pd.DataFrame,
) -> pd.DataFrame:
    _, _, as_of = cache_key
    return build_equipment_status_as_of(_equipment, _downtime, as_of=date.fromisoformat(as_of))


def get_equipment_status_as_of(
    equipment: pd.DataFrame, downtime: pd.DataFrame, *, as_of: date
) -> pd.DataFrame:
    """Main 「호기 현황(상태 분포·호기 목록)」「Qual 일정」 의 기준일 상태.

    `build_equipment_status_as_of` 의 캐시다. 키는 거른 두 표의 내용 지문 + 기준일이다 — 기준일을
    옮기면(기본값이 오늘이라 날짜가 바뀌어도) 새로 판정한다. Qual 의 고정 지분·거르기와 표시명은
    캐시 밖이다.
    """
    cache_key = (frame_digest(equipment), frame_digest(downtime), as_of.isoformat())
    return _cached_equipment_status_as_of(cache_key, equipment, downtime)


def get_inactive_equipment(
    equipment: pd.DataFrame, downtime: pd.DataFrame, *, as_of: date
) -> pd.DataFrame:
    """Main 「비가동 호기 › 기준일 시점」(`build_inactive_equipment` 와 같다).

    같은 기준일 상태 캐시(`get_equipment_status_as_of`)에서 비가동 술어(보유 & ~가용)만 건다 —
    `build_inactive_equipment` 가 바로 그 둘의 합이다.
    """
    return inactive_equipment_rows(get_equipment_status_as_of(equipment, downtime, as_of=as_of))


# (거른 마스터 내용 지문, 시작, 끝, 기준일)
TransitionEventsCacheKey = tuple[str, str, str, str]


@st.cache_data(show_spinner=False, max_entries=8)
def _cached_milestone_transition_events(
    cache_key: TransitionEventsCacheKey, _equipment: pd.DataFrame
) -> pd.DataFrame:
    _, start, end, as_of = cache_key
    return build_milestone_transition_events(
        _equipment,
        start_date=date.fromisoformat(start),
        end_date=date.fromisoformat(end),
        as_of=date.fromisoformat(as_of),
    )


def get_milestone_transition_events(
    equipment: pd.DataFrame, *, start_date: date, end_date: date, as_of: date
) -> pd.DataFrame:
    """Main 「단계 전환」 의 전환 일정(`build_milestone_transition_events`).

    비가동을 보지 않는 판정이라 키는 거른 마스터 지문 + 기간 + 기준일(완료·예정을 가른다)이다.
    전환단계·일정상태·Qual상태 거르기와 집계·표시명은 캐시 밖이다.
    """
    cache_key = (
        frame_digest(equipment),
        start_date.isoformat(),
        end_date.isoformat(),
        as_of.isoformat(),
    )
    return _cached_milestone_transition_events(cache_key, equipment)


# ------------------------------------------------------------------ 공정 Capa 상세 (공식 기준)
# 공정 하나 · 분류 하나 · 달 하나짜리 작은 결과라 칸을 넉넉히 둔다. 판정 기준에 닿는 값(과부족·
# 판정)은 여기 두지 않는다 — 기준을 바꿔도 캐시가 갈릴 일이 없게 화면이 회차마다 만든다
# (`process_capa_detail.build_process_capa_summary`).
PROCESS_DETAIL_ROWS_MAX_ENTRIES = 16
PROCESS_DETAIL_VIEW_MAX_ENTRIES = 32


@st.cache_data(show_spinner=False, max_entries=PROCESS_DETAIL_ROWS_MAX_ENTRIES)
def get_process_calculation_rows(
    cache_key: ScenarioCacheKey,
    process: str,
    _scenario_tables: Mapping[str, pd.DataFrame],
    _reference_tables: Mapping[str, pd.DataFrame],
) -> ProcessCalculationRows:
    """이 키의 대당 Capa·소요대수 결과와 두 제외 목록을 공정 하나로 거른 조각.

    아래 두 래퍼가 빗나갈 때 이것을 받는다 — 분류·거르기·달을 바꿔도 시나리오 전체 프레임
    (`get_scenario_capacity_and_demand`, pickle 수십 MB)을 다시 풀지 않고 이 작은 조각만 푼다.
    이것이 빗나갈 때만 전체 프레임을 푼다. 두 표 묶음은 키의 content_token 을 발급한 활성
    시나리오·기준정보여야 한다(`get_scenario_capacity_and_demand` 와 같은 계약). 계산 오류는
    캐시되지 않고 그대로 난다.
    """
    unit_capacity, required_equipment = get_scenario_capacity_and_demand(
        cache_key,
        _scenario_tables=_scenario_tables,
        _reference_tables=_reference_tables,
    )
    return process_calculation_rows(unit_capacity, required_equipment, process=process)


@st.cache_data(show_spinner=False, max_entries=PROCESS_DETAIL_VIEW_MAX_ENTRIES)
def get_process_product_demand(
    cache_key: ScenarioCacheKey,
    display_order_key: str,
    process: str,
    split: str,
    months: tuple[int, ...],
    _scenario_tables: Mapping[str, pd.DataFrame],
    _reference_tables: Mapping[str, pd.DataFrame],
    _display_order: PreparedDisplayOrder | None,
    products: tuple[str, ...] = (),
    production_classes: tuple[str, ...] = (),
    limit: int = PRODUCT_ROW_LIMIT,
) -> pd.DataFrame:
    """공정 하나의 제품별 소요대수 월 표(`build_process_product_demand`).

    키는 시나리오 키 + 표시순서 지문(`display_order_digest`) + 공정·분류·달·거르기·상한이다 — 행
    차례가 표시순서(산출 결과 · 소요대수)를 따르므로 지문이 키에 든다. `_display_order` 는
    `display_order_key` 를 만든 `RQ_DISPLAY_ORDER` 를 준비한 것이어야 한다. 빗나가면 공정 조각
    (`get_process_calculation_rows`)만 받는다.
    """
    del display_order_key
    rows = get_process_calculation_rows(
        cache_key,
        process,
        _scenario_tables=_scenario_tables,
        _reference_tables=_reference_tables,
    )
    return build_process_product_demand(
        rows.required_equipment,
        process=process,
        split=split,
        months=months,
        display_order=_display_order,
        products=products,
        production_classes=production_classes,
        limit=limit,
    )


@st.cache_data(show_spinner=False, max_entries=PROCESS_DETAIL_VIEW_MAX_ENTRIES)
def get_process_month_trace(
    cache_key: ScenarioCacheKey,
    process: str,
    month: int,
    _scenario_tables: Mapping[str, pd.DataFrame],
    _reference_tables: Mapping[str, pd.DataFrame],
) -> ProcessMonthTrace:
    """고른 달 한 공정의 경로 인자·공통 인자·제외 경로·근거 요약(`build_process_month_trace`).

    인자 표는 대당 Capa 계산과 같은 조합이다 — `RQ_MODULE` 은 기준정보에서, 나머지는 시나리오
    표에서 읽는다(`_capacity_tables`). 표는 빗나갈 때만 공정·달로 거른다. 키는 시나리오 키 + 공정·
    달이다 — 인자 표 내용은 키의 content_token·reference_version 이 정한다.
    """
    rows = get_process_calculation_rows(
        cache_key,
        process,
        _scenario_tables=_scenario_tables,
        _reference_tables=_reference_tables,
    )
    capacity_tables = {
        name: (
            _reference_tables[name] if name in REFERENCE_INPUT_TABLES else _scenario_tables[name]
        )
        for name in CAPACITY_INPUT_TABLES
    }
    return build_process_month_trace(rows, capacity_tables, process=process, month=month)


# 공정 Capa 상세의 설비 일정(참고). 필요단축일정 탭과 같은 계산을 공용 판정 기준(달마다 다른
# 목표)으로 한 벌 더 두고, 공정 하나의 설비 일정(신규 호기·비가동 손실·전월 대비)을 따로 둔다.
# 탭의 칸(`get_required_shortening`)은 그대로다.

# (필요단축일정 키, 목표 기본값, 기본값과 다른 달의 (월, 목표))
RequiredShorteningTargetCacheKey = tuple[
    RequiredShorteningCacheKey, float, tuple[tuple[int, float], ...]
]


def required_shortening_target_cache_key(
    shortening_key: RequiredShorteningCacheKey, target: MonthlyTarget
) -> RequiredShorteningTargetCacheKey:
    """`get_required_shortening_for_target` 의 키 — 탭의 계획 키에 목표(기본값 + 예외 달)를 더한다.

    같은 입력이면 앞 원소가 탭의 키와 같다. 목표는 계산할 달로 좁혀 만든다(`target_from_thresholds`)
    — 그 밖의 월별 예외가 키를 가르지 않게.
    """
    return (shortening_key, float(target.default), tuple(target.monthly))


@st.cache_data(show_spinner=False, max_entries=8)
def get_required_shortening_for_target(
    cache_key: RequiredShorteningTargetCacheKey,
    _equipment: pd.DataFrame,
    _downtime: pd.DataFrame,
    _baseline: pd.DataFrame,
    _cutoff: pd.DataFrame,
    _required_equipment: Callable[[], pd.DataFrame],
) -> ShorteningPlan:
    """달마다 다른 목표 하나(공용 판정 기준의 확보기준)의 필요단축일정. `plan.at(목표)` 로 꺼낸다.

    탭(`get_required_shortening`)과 같은 규칙이다 — 프레임은 해시하지 않고 키가 내용 지문·시나리오
    키·달·오늘·목표를 모두 싣는다. 소요대수는 빗나갈 때만 로더로 꺼내고, 호기 구간은 같은 구간
    캐시(`get_equipment_lifecycle_spans`)에서 받는다. 목표는 키에서 다시 세운다 — 키와 다른 목표가
    들어올 길이 없다. 공정 선택은 이 결과를 고르기만 한다(공정끼리 따로 계산한다).
    """
    shortening_key, default, monthly = cache_key
    _, equipment_digest, downtime_digest, _, _, months, today = shortening_key
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
        required_equipment=_required_equipment(),
        months=months,
        today=date.fromisoformat(today),
        levels=(MonthlyTarget(default=default, monthly=monthly),),
        spans=spans,
    )


# (설비 마스터·비가동·기존보유·Cut-off 내용 지문, 달, 공정)
ProcessEquipmentTimelineCacheKey = tuple[str, str, str, str, tuple[int, ...], str]


def process_equipment_timeline_cache_key(
    *,
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    baseline: pd.DataFrame,
    cutoff: pd.DataFrame,
    months: Sequence[int],
    process: str,
) -> ProcessEquipmentTimelineCacheKey:
    """`get_process_equipment_timeline` 의 키. 네 표는 거르기 전 그대로의 내용 지문이다.

    **오늘은 넣지 않는다** — 구간·호기별 기여는 오늘을 보지 않는다. 필요단축일정 키를 이미
    만들었으면 `process_timeline_key_from_shortening` 이 지문을 다시 계산하지 않고 같은 키를 낸다.
    """
    return (
        frame_digest(equipment),
        frame_digest(downtime),
        frame_digest(baseline),
        frame_digest(cutoff),
        tuple(sorted({int(month) for month in months})),
        str(process).strip(),
    )


def process_timeline_key_from_shortening(
    shortening_key: RequiredShorteningCacheKey, process: str
) -> ProcessEquipmentTimelineCacheKey:
    """필요단축일정 키의 네 지문·달로 설비 일정 키를 낸다(같은 입력이면 위 함수와 같은 키)."""
    _, equipment_digest, downtime_digest, baseline_digest, cutoff_digest, months, _ = shortening_key
    return (
        equipment_digest,
        downtime_digest,
        baseline_digest,
        cutoff_digest,
        tuple(sorted({int(month) for month in months})),
        str(process).strip(),
    )


@st.cache_data(show_spinner=False, max_entries=8)
def get_process_equipment_timeline(
    cache_key: ProcessEquipmentTimelineCacheKey,
    _equipment: pd.DataFrame,
    _downtime: pd.DataFrame,
    _baseline: pd.DataFrame,
    _cutoff: pd.DataFrame,
) -> ProcessEquipmentTimeline:
    """공정 하나의 설비 일정(`build_process_equipment_timeline`).

    신규 호기·호기별 손실·전월 대비·비가동 화살표를 한 번에 싣는다.

    프레임은 키를 만든 바로 그 표여야 한다(해시하지 않는다). 공정으로 거른 마스터로 구간을 두 번
    (실제·비가동 없음) 만들므로 **공용 구간 캐시(`get_equipment_lifecycle_spans`)는 쓰지 않는다** —
    공정 하나·그 공정 축만큼이라 작다. 단축 계획(오늘이 드는 것)은 따로 받아 `unit_events` 로
    겹친다. 마스터가 계약을 어기면 `ValueError` 가 그대로 올라간다(캐시에 남지 않는다).
    """
    *_, months, process = cache_key
    return build_process_equipment_timeline(
        _equipment, _downtime, _baseline, _cutoff, process=process, months=months
    )
