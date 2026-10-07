# Purpose: 입장 화면 Summary 가 그리는 공식버전 6개월 요약(생산계획·B/N·월별 시트)을 계산한다.

"""공식버전 요약 — 입장 화면 `Summary` 가 그리는 값.

HOME 은 고른 시나리오·조회기간·토글로 **상세**를 보여 준다. 입장 화면의 `Summary` 는 그와 따로
**사용자가 지정해 둔 최신 공식버전** 하나의 여섯 달만 요약한다(2026-10-02 사용자 결정).

- **기간**: 공식버전 시나리오의 시작월부터 여섯 달. 시작월은 그 리비전에 저장된 조회기간 시작
  (`ScenarioPreset.start_month`)과 생산계획의 첫 달 중 **늦은 쪽**이다 — 앞쪽은 데이터가 없는
  달이고, 뒤쪽은 공식버전을 지정한 사람이 보라고 저장해 둔 시작이다. 계획이 여섯 달보다 짧으면
  있는 달까지만 그린다. 연간 Total 은 넣지 않는다.
- **생산계획**: HOME `Density (억Gb)` 행과 같은 값(`부하량`)이다.
- **B/N 확보율**: 리비전 프리셋의 `B/N 집계 공정`(필터)만 놓고 달마다 확보율이 가장 낮은 공정 —
  HOME 의 B/N 과 같은 순위 함수다. 부족 대수는 그 공정의 `소요대수 − 가용대수` 를 올림한 값이다.
- **월별 시트**: 그 달의 Density · Wafer 계획 · 제품별 비중(Wafer 기준). 색 칸 배정은 HOME 과 같은
  함수로 이 여섯 달에서 정한다.

HOME 토글의 **기본값**과 같은 화면이다 — EDP 제외, 선행·실행 Capa 반영 없음. 과거 구간은 이 기간에
들어오지 않는다(시작월이 생산계획의 첫 달 이후다).

Summary 머리 줄의 토글 셋(선행 B/O·선행 입고·GAP)이 켜졌을 때의 값도 여기서 함께 낸다.
토글은 브라우저 안에서만 바뀌므로 세 갈래를 미리 다 계산해 보낸다. **HOME 의 같은 토글과 같은
함수**를 쓴다.

- **선행 B/O**(`build_advance_summary`): `build_advance_load_ratio` 로 변동률을 내
  `apply_advance_to_*` 로 Density·Wafer·확보율에 건다. 변동률은 화면이 쓰는 계획(EDP 제외)
  기준이다. B/N 공정은 바뀌지 않는다(한 달 안의 모든 공정에 같은 수를 곱한다). 소요·가용대수는
  HOME 처럼 그대로다.
- **GAP**(`build_comparison_summary`): 비교 시나리오 계획과의 차이 = 선행 **전** 값 − 비교 값.
  HOME 이 선행을 켜도 GAP 을 원 데이터끼리 재는 것과 같다(`home_lob_figures`).
- 증감 글자는 HOME 과 같은 형식·숨김 규칙(`services/plan_gap.py`)이다.

이 모듈은 프레임만 받는 순수 계산이다. 공식버전을 찾고 캐시된 HOME 계산을 부르는 일은
`components/intro_summary.py` 가 한다.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from capa_simulation.services.advance_load import (
    apply_advance_to_density,
    apply_advance_to_securement,
    apply_advance_to_wafer,
    build_advance_load_ratio,
    prepare_advance_load,
)
from capa_simulation.services.dashboard import (
    build_monthly_bottleneck_ranking,
    build_monthly_bottlenecks_from_ranking,
)
from capa_simulation.services.display_order import DisplayOrderInput
from capa_simulation.services.frame_contracts import require_columns
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.plan_gap import (
    DENSITY_GAP_FORMAT,
    GAP_EPSILON,
    WAFER_GAP_FORMAT,
    WAFER_GAP_SCALE,
    format_gap,
)
from capa_simulation.services.product_share import (
    OTHER_PRODUCT_LABEL,
    PRODUCT_SHARE_BASIS_WAFER,
    assign_product_slots,
    build_product_share_cells,
)

SUMMARY_MONTH_COUNT = 6


def shift_month(month: int, offset: int) -> int:
    """`YYYYMM` 에서 `offset` 달 뒤(음수면 앞)의 `YYYYMM`."""
    index = (month // 100) * 12 + (month % 100 - 1) + offset
    return (index // 12) * 100 + index % 12 + 1


def summary_months(
    preset_start: int,
    source_start: int,
    source_end: int,
    count: int = SUMMARY_MONTH_COUNT,
) -> list[int]:
    """요약이 그리는 달. 시작월부터 `count` 달이되 생산계획의 마지막 달을 넘지 않는다."""
    start = max(preset_start, source_start)
    return [month for month in (shift_month(start, k) for k in range(count)) if month <= source_end]


@dataclass(frozen=True)
class BottleneckMonth:
    """한 달의 B/N. 대수가 없으면 `required`·`available`·`short_units` 가 None 이다."""

    process: str
    rate: float
    required: float | None
    available: float | None
    short_units: int | None


@dataclass(frozen=True)
class OfficialSummary:
    """요약 한 벌. 모든 튜플은 `months` 와 같은 차례·같은 길이다(값이 없는 달은 None)."""

    months: tuple[int, ...]
    density: tuple[float | None, ...]
    wafer: tuple[float | None, ...]
    bottlenecks: tuple[BottleneckMonth | None, ...]
    # 범례 차례. `product_slots[i]` 는 그 제품의 색 칸 번호이고 `기타` 는 None 이다.
    products: tuple[str, ...]
    product_slots: tuple[int | None, ...]
    # 달마다 (제품 차례, 비중) — 도넛 조각 차례 그대로.
    mix: tuple[tuple[tuple[int, float], ...], ...]

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(month_label(month) for month in self.months)


def _finite(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _monthly_values(frame: pd.DataFrame, column: str, months: Sequence[int]) -> list[float | None]:
    require_columns(frame, ["생산계획년월", column], column)
    values = pd.to_numeric(frame[column], errors="coerce")
    by_month = values.groupby(pd.to_numeric(frame["생산계획년월"], errors="coerce")).sum(
        min_count=1
    )
    return [_finite(by_month.get(month)) for month in months]


def short_units(required: float | None, available: float | None) -> int | None:
    """모자라는 대수. 소수 소요대수는 올림한다 — 0.2대 모자라도 한 대를 더 들여야 한다."""
    if required is None or available is None:
        return None
    # 소요대수 계산의 부동소수 꼬리(예: 33.000000001)가 한 대를 더 만들지 않게 한다.
    return max(0, math.ceil(required - available - 1e-9))


def _bottlenecks(
    securement_rate: pd.DataFrame,
    included_processes: Sequence[str],
    months: Sequence[int],
) -> list[BottleneckMonth | None]:
    ranking = build_monthly_bottleneck_ranking(securement_rate, list(included_processes))
    top = build_monthly_bottlenecks_from_ranking(ranking)
    rows = {int(row["생산계획년월"]): row for _, row in top.iterrows()}
    result: list[BottleneckMonth | None] = []
    for month in months:
        row = rows.get(month)
        rate = None if row is None else _finite(row["확보율"])
        if row is None or rate is None:
            result.append(None)
            continue
        required = _finite(row.get("소요대수"))
        available = _finite(row.get("가용대수"))
        result.append(
            BottleneckMonth(
                process=str(row["공정"]),
                rate=rate,
                required=required,
                available=available,
                short_units=short_units(required, available),
            )
        )
    return result


def build_official_summary(
    *,
    months: Sequence[int],
    monthly_density: pd.DataFrame,
    monthly_wafer: pd.DataFrame,
    securement_rate: pd.DataFrame,
    product_volume: pd.DataFrame,
    slot_volume: pd.DataFrame,
    display_order: DisplayOrderInput,
    included_processes: Sequence[str],
) -> OfficialSummary:
    """캐시된 HOME 계산 결과로 요약 한 벌을 만든다.

    `product_volume` 은 그리는 수량(EDP 제외), `slot_volume` 은 색 칸을 정하는 수량(EDP 포함)이다 —
    HOME 과 같은 짝이라 EDP 가 빠져도 남은 제품의 색이 바뀌지 않는다.
    """
    month_list = list(months)
    labels = [month_label(month) for month in month_list]
    slots = assign_product_slots(slot_volume, display_order)
    cells = build_product_share_cells(
        product_volume, PRODUCT_SHARE_BASIS_WAFER, slots, month_labels=labels
    )
    products = list(slots.order)
    product_slots: list[int | None] = [slots.slot[name] for name in products]
    has_other = any(
        piece.product == OTHER_PRODUCT_LABEL for cell in cells.values() for piece in cell.slices
    )
    if has_other:
        products.append(OTHER_PRODUCT_LABEL)
        product_slots.append(None)
    index = {name: position for position, name in enumerate(products)}
    mix = tuple(
        tuple(
            (index[piece.product], float(piece.share))
            for piece in (cells[label].slices if label in cells else ())
            if piece.product in index
        )
        for label in labels
    )
    return OfficialSummary(
        months=tuple(month_list),
        density=tuple(_monthly_values(monthly_density, "부하량", month_list)),
        wafer=tuple(_monthly_values(monthly_wafer, "Wafer 부하량", month_list)),
        bottlenecks=tuple(_bottlenecks(securement_rate, included_processes, month_list)),
        products=tuple(products),
        product_slots=tuple(product_slots),
        mix=mix,
    )


@dataclass(frozen=True)
class AdvanceSummary:
    """선행 B/O 를 켠 요약. 튜플은 모두 요약의 `months` 와 같은 차례·같은 길이다.

    `density_delta`·`wafer_delta`·`rate_delta` 는 HOME 이 값 위·막대 안에 적는 증감 글자 그대로다
    (적을 것이 없는 달은 빈 글자). `applied` 는 선행 B/O 가 실제로 걸린 달, `unapplied` 는 입력은
    있지만 반영하면 계획이 0 이하가 되어 걸지 못한 달이다(HOME 화면 경고와 같은 규칙).
    """

    density: tuple[float | None, ...]
    wafer: tuple[float | None, ...]
    bottlenecks: tuple[BottleneckMonth | None, ...]
    density_delta: tuple[str, ...]
    wafer_delta: tuple[str, ...]
    rate_delta: tuple[str, ...]
    applied: tuple[int, ...]
    unapplied: tuple[int, ...]


def _rate_delta(rate: float | None, base: float | None) -> str:
    """HOME B/N 막대 안 증감(`home_lob_figures._bottleneck_rate_labels`)과 같은 글자."""
    if rate is None or base is None:
        return ""
    difference = rate - base
    if math.isnan(difference) or abs(difference) < GAP_EPSILON:
        return ""
    return f"{difference * 100:+.0f}%"


def build_advance_summary(
    *,
    months: Sequence[int],
    monthly_density: pd.DataFrame,
    monthly_wafer: pd.DataFrame,
    securement_rate: pd.DataFrame,
    included_processes: Sequence[str],
    advance_rows: pd.DataFrame,
    base: OfficialSummary,
) -> AdvanceSummary:
    """HOME 「선행 B/O」 토글과 같은 계산으로 요약의 Density·Wafer·B/N 을 다시 낸다.

    `monthly_density`·`monthly_wafer` 는 요약이 그리는 계획(EDP 제외)이고 `base` 는 그것으로 만든
    요약이다. 증감 글자는 `base` 와의 차이다.
    """
    month_list = list(months)
    ratio = build_advance_load_ratio(monthly_density, advance_rows)
    density = apply_advance_to_density(monthly_density, ratio)
    wafer = apply_advance_to_wafer(monthly_wafer, ratio)
    securement = apply_advance_to_securement(securement_rate, ratio)
    density_values = _monthly_values(density, "부하량", month_list)
    wafer_values = _monthly_values(wafer, "Wafer 부하량", month_list)
    bottlenecks = _bottlenecks(securement, included_processes, month_list)
    entered = prepare_advance_load(advance_rows)
    inputs = {
        int(month)
        for month, amount in zip(entered["생산계획년월"], entered["선행 물량"], strict=True)
        if float(amount) != 0.0
    }
    applied_months = {
        int(month)
        for month, amount in zip(ratio["생산계획년월"], ratio["선행 물량"], strict=True)
        if float(amount) != 0.0
    }
    return AdvanceSummary(
        density=tuple(density_values),
        wafer=tuple(wafer_values),
        bottlenecks=tuple(bottlenecks),
        density_delta=tuple(
            format_gap(_difference(new, old), DENSITY_GAP_FORMAT)
            for new, old in zip(density_values, base.density, strict=True)
        ),
        wafer_delta=tuple(
            format_gap(_difference(new, old), WAFER_GAP_FORMAT, scale=WAFER_GAP_SCALE)
            for new, old in zip(wafer_values, base.wafer, strict=True)
        ),
        rate_delta=tuple(
            _rate_delta(
                None if new is None else new.rate,
                None if old is None else old.rate,
            )
            for new, old in zip(bottlenecks, base.bottlenecks, strict=True)
        ),
        applied=tuple(month for month in month_list if month in applied_months),
        unapplied=tuple(
            month for month in month_list if month in inputs and month not in applied_months
        ),
    )


@dataclass(frozen=True)
class ComparisonSummary:
    """GAP — 비교 시나리오 계획과의 차이. 튜플은 요약의 `months` 와 같은 차례·같은 길이다.

    `density`·`wafer` 는 비교 시나리오 쪽 값(없는 달은 None), `*_gap` 은 HOME 이 값 아래에 적는
    GAP 글자 그대로다(요약 값 − 비교 값, 적을 것이 없는 달은 빈 글자).
    """

    density: tuple[float | None, ...]
    wafer: tuple[float | None, ...]
    density_gap: tuple[str, ...]
    wafer_gap: tuple[str, ...]

    @property
    def covered(self) -> bool:
        """비교 시나리오가 이 기간의 달을 하나라도 가졌는가."""
        return any(value is not None for value in self.density) or any(
            value is not None for value in self.wafer
        )


def _difference(new: float | None, old: float | None) -> float | None:
    return None if new is None or old is None else new - old


def build_comparison_summary(
    *,
    months: Sequence[int],
    base: OfficialSummary,
    comparison_density: pd.DataFrame,
    comparison_wafer: pd.DataFrame,
) -> ComparisonSummary:
    """요약(선행 전)과 비교 시나리오의 같은 달 계획 차이.

    `comparison_density`·`comparison_wafer` 는 비교 시나리오의 계획을 공식버전의 기준정보로 환산한
    월별 표다(`simulation_cache.get_home_comparison_plan` — HOME GAP 과 같은 함수).
    """
    month_list = list(months)
    density = _monthly_values(comparison_density, "부하량", month_list)
    wafer = _monthly_values(comparison_wafer, "Wafer 부하량", month_list)
    return ComparisonSummary(
        density=tuple(density),
        wafer=tuple(wafer),
        density_gap=tuple(
            format_gap(_difference(own, other), DENSITY_GAP_FORMAT)
            for own, other in zip(base.density, density, strict=True)
        ),
        wafer_gap=tuple(
            format_gap(_difference(own, other), WAFER_GAP_FORMAT, scale=WAFER_GAP_SCALE)
            for own, other in zip(base.wafer, wafer, strict=True)
        ),
    )
