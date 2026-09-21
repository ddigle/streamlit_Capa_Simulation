# Purpose: 효율·UPEH·수율 실적 화면이 공유하는 월별 Gap·우선순위 계산과 합성 데모를 만든다.

"""실적 Gap 공통 계산.

효율·UPEH·수율 세 화면은 **같은 질문을 지표만 바꿔 묻는다** — 기준 대비 실적이 얼마나
모자라고, 어느 공정부터 손대야 하고, 손대고 있는 과제는 어디까지 왔나. 세 화면이 각자
표를 만들면 같은 질문에 세 가지 답이 나온다. 여기서 한 번만 계산하고 화면은 지표
사양(`MetricSpec`)만 바꿔 끼운다.

**Gap 의 뜻이 지표마다 다르다.** 효율과 수율은 비율 그 자체라 차이를 `%p` 로 읽고,
UPEH 는 절대 수량이라 차이를 비율로 읽어야 공정 간 비교가 된다. 이 차이를 화면이 아니라
사양이 갖는다 — 화면에 흩어 두면 한 곳만 고쳐지고 나머지는 조용히 틀린 단위로 남는다.

데모는 `dynamic_capacity.DEMO_PROFILES` 에서 나온다. 상위 워터폴과 같은 공정·제품
세계라야 「그 손실을 이 화면에서 파고든다」가 성립한다. 난수를 쓰지 않는다 — 다시 열
때마다 숫자가 달라지면 화면을 두고 이야기할 수가 없다.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sin

import pandas as pd

from capa_simulation.services.dynamic_capacity import DEMO_PROFILES

MONTHLY_ACTUAL_COLUMNS = (
    "생산계획년월",
    "공정",
    "양산구분",
    "제품정보",
    "Stack",
    "WF 구분",
    "소요기준",
    "생산수량",
    "기준 효율",
    "실적 효율",
    "기준 UPEH",
    "실적 UPEH",
    "기준 수율",
    "실적 수율",
)

# 데모가 도는 구간. 12개월이라야 「연속 몇 개월 미달」이 뜻을 갖는다.
DEMO_START_MONTH = 202601
DEMO_MONTH_COUNT = 12


@dataclass(frozen=True)
class MetricSpec:
    """한 지표를 화면에 올리는 데 필요한 것 전부.

    `gap_kind` 가 `"point"` 면 `실적 − 기준` 을 `%p` 로, `"ratio"` 면 `실적 ÷ 기준 − 1` 을
    `%` 로 읽는다. 둘을 섞으면 UPEH 2,400 과 2,050 의 차이가 `-350%p` 로 적힌다.
    """

    name: str
    actual_column: str
    standard_column: str
    gap_kind: str
    value_format: str
    source: str
    description: str
    # 소수 자릿수는 지표마다 다르다. 수율은 Gap 이 0.5%p 수준이라 한 자리로 적으면
    # `-0.0%p` 로 뭉개져 화면이 「차이가 없다」고 거짓말한다.
    value_decimals: int = 1
    gap_decimals: int = 1

    @property
    def gap_unit(self) -> str:
        """라벨에 적는 단위. `Gap (%p)` 처럼 쓴다."""
        return "%p" if self.gap_kind == "point" else "%"

    @property
    def gap_suffix(self) -> str:
        """이미 `%` 로 서식한 **값 뒤**에 붙일 것. `%` 를 또 붙이면 `4.3%%p` 가 된다."""
        return "p" if self.gap_kind == "point" else ""


EFFICIENCY_METRIC = MetricSpec(
    name="효율",
    actual_column="실적 효율",
    standard_column="기준 효율",
    gap_kind="point",
    value_format="percent",
    source="생산이력 DB",
    description="설비가 계획시간 중 실제로 돌아간 비율입니다. 기준 효율은 Capa 기준정보 값입니다.",
)
UPEH_METRIC = MetricSpec(
    name="UPEH",
    actual_column="실적 UPEH",
    standard_column="기준 UPEH",
    gap_kind="ratio",
    value_format="%,.0f",
    value_decimals=0,
    source="생산이력 DB",
    description="설비 한 대가 한 시간에 처리한 수량입니다. 기준 UPEH 는 Capa 기준정보 값입니다.",
)
YIELD_METRIC = MetricSpec(
    name="수율",
    actual_column="실적 수율",
    standard_column="기준 수율",
    gap_kind="point",
    value_format="percent",
    source="수율 실적 DB",
    description="투입 대비 양품 비율입니다. 기준 수율은 Capa 기준정보(RQ_YLD) 값입니다.",
    value_decimals=2,
    gap_decimals=2,
)

ALL_METRICS = (EFFICIENCY_METRIC, UPEH_METRIC, YIELD_METRIC)


# 공정마다 다른 결말을 준다. 전부 미달이면 우선순위 표가 아무것도 고르지 못하고, 전부
# 양호하면 이 화면을 왜 만드는지가 안 보인다. `DEMO_PROFILES` 의 순서와 1:1 이다.
#
#   drift  : 12개월에 걸쳐 실적에 더해지는 양. 양수면 개선, 음수면 악화다. 기준 대비
#            처음 벌어져 있던 폭(`standard × (factor − 1)`)보다 크면 중간에 기준을 넘는다.
#   yield_ : 기준 수율에 얹는 고정 편차. 수율은 폭이 좁아 효율과 같은 크기를 쓸 수 없다.
#   volume : 월 생산수량(Kea). **PKG 환산 물량**이다 — WF 매와 CHIP Kea 를 그대로 더하면
#            WF 공정이 늘 물량 1위가 되어 우선순위가 단위 차이를 순위로 착각한다. 실제 DB
#            연결 때도 우선순위 가중치로 쓸 공통 환산 물량을 함께 받아야 한다.
_DEMO_TUNING = (
    # Wafer Sorter — 크게 회복하지만 효율은 아직 못 맞춘다. UPEH·수율은 막바지에 넘어선다
    (0.055, 0.0012, 4_200.0),
    (0.055, 0.0008, 3_100.0),
    # Pre B/D — 개선 중이지만 아직 못 맞춘다
    (0.030, -0.0020, 3_800.0),
    (0.030, -0.0015, 2_600.0),
    # TC Bonding — 물량이 크면서 계속 나빠진다. 우선순위 맨 위에 서야 할 공정이다
    (-0.020, -0.0055, 5_400.0),
    (-0.020, -0.0042, 4_700.0),
    # Mold — 기준에 붙어 오르내린다. 마지막 달만 살짝 미달해 「관찰」이 어떤 모습인지 보인다
    (0.0055, 0.0018, 6_100.0),
    (0.0055, 0.0012, 7_400.0),
    # AVI-PKG — 중반에 기준을 넘어선다
    (0.070, 0.0026, 3_300.0),
    (0.070, 0.0021, 5_200.0),
)
_DEMO_STANDARD_YIELDS = (0.994, 0.991, 0.988, 0.996, 0.985, 0.993, 0.997, 0.995, 0.989, 0.992)

_ACTION_COLUMNS = ("공정", "개선 과제", "담당", "목표월", "진행", "기대 효과")
_ACTION_TEMPLATES = (
    ("{metric} 저하 구간 설비 파라미터 재설정", "기술팀", "진행중"),
    ("{metric} 기준값 재산정 및 기준정보 반영", "제조기술팀", "검토"),
    ("{metric} 하락 원인 설비 예방보전 주기 단축", "설비팀", "진행중"),
    ("{metric} 이상 로트 선별 및 재작업 기준 정비", "품질팀", "계획"),
)


def build_monthly_actual_demo() -> pd.DataFrame:
    """월 × 공정 × 제품 합성 실적. 공정마다 **다른 이야기**를 갖도록 만든다.

    전부 고르게 미달하면 우선순위 표가 아무것도 고르지 못해 화면이 할 말을 잃는다. 악화
    추세 몇 개, 개선 추세 몇 개, 기준을 넘는 것 몇 개를 일부러 둔다.
    """
    records: list[dict[str, object]] = []
    for month_index in range(DEMO_MONTH_COUNT):
        month = _shift_month(DEMO_START_MONTH, month_index)
        for profile_index, profile in enumerate(DEMO_PROFILES):
            drift, yield_offset, volume = _DEMO_TUNING[profile_index % len(_DEMO_TUNING)]
            wave = sin((month_index + profile_index) * 0.55)
            trend = drift * month_index / max(1, DEMO_MONTH_COUNT - 1)
            actual_efficiency = _clip(
                profile.standard_efficiency * profile.efficiency_factor + trend + wave * 0.006,
                0.40,
                0.995,
            )
            actual_upeh = profile.standard_upeh * (profile.upeh_factor + trend * 0.9 + wave * 0.008)
            standard_yield = _DEMO_STANDARD_YIELDS[profile_index % len(_DEMO_STANDARD_YIELDS)]
            # 수율은 폭이 좁다. 효율과 같은 추세를 그대로 쓰면 한두 달 만에 100% 에
            # 붙어 버려 추이가 평평해진다. 고정 편차에 추세를 아주 작게만 얹는다.
            actual_yield = _clip(
                standard_yield + yield_offset + trend * 0.02 + wave * 0.0012,
                0.90,
                0.9995,
            )
            records.append(
                {
                    "생산계획년월": month,
                    "공정": profile.process,
                    "양산구분": "양산",
                    "제품정보": profile.product,
                    "Stack": profile.stack,
                    "WF 구분": profile.wafer_type,
                    "소요기준": profile.requirement_basis,
                    # 영향 물량. 우선순위가 「미달폭 × 물량」이라 값이 없으면 순위가 없다.
                    "생산수량": round(volume * (1.0 + 0.08 * sin(month_index * 0.8)), 0),
                    "기준 효율": profile.standard_efficiency,
                    "실적 효율": actual_efficiency,
                    "기준 UPEH": profile.standard_upeh,
                    "실적 UPEH": actual_upeh,
                    "기준 수율": standard_yield,
                    "실적 수율": actual_yield,
                }
            )
    return pd.DataFrame.from_records(records, columns=list(MONTHLY_ACTUAL_COLUMNS))


def build_gap_table(
    monthly: pd.DataFrame,
    metric: MetricSpec,
    dimensions: list[str],
) -> pd.DataFrame:
    """분류별 기준·실적·Gap·영향 물량. 비율은 **집계한 뒤 다시 계산**한다.

    월별 비율의 단순 평균은 물량이 다른 달을 같은 무게로 세어 실제 손실과 어긋난다.
    생산수량을 가중치로 쓴다.
    """
    required = [*dimensions, metric.actual_column, metric.standard_column, "생산수량"]
    missing = [column for column in required if column not in monthly.columns]
    if missing:
        raise ValueError(f"실적 Gap 계산에 필요한 컬럼이 없습니다: {', '.join(missing)}")
    if monthly.empty:
        return pd.DataFrame(
            columns=[
                *dimensions,
                metric.standard_column,
                metric.actual_column,
                "Gap",
                "생산수량",
                "영향 비중",
            ]
        )

    frame = monthly.copy()
    weight = pd.to_numeric(frame["생산수량"], errors="coerce").fillna(0.0)
    frame["_가중_실적"] = pd.to_numeric(frame[metric.actual_column], errors="coerce") * weight
    frame["_가중_기준"] = pd.to_numeric(frame[metric.standard_column], errors="coerce") * weight
    frame["_가중치"] = weight
    grouped = frame.groupby(dimensions, as_index=False, dropna=False, sort=False)[
        ["_가중_실적", "_가중_기준", "_가중치"]
    ].sum()
    result = grouped[dimensions].copy()
    result[metric.standard_column] = _ratio_or_na(grouped["_가중_기준"], grouped["_가중치"])
    result[metric.actual_column] = _ratio_or_na(grouped["_가중_실적"], grouped["_가중치"])
    result["Gap"] = gap_values(result[metric.actual_column], result[metric.standard_column], metric)
    result["생산수량"] = grouped["_가중치"]
    total_weight = float(grouped["_가중치"].sum())
    result["영향 비중"] = grouped["_가중치"] / total_weight if total_weight else 0.0
    return result


def gap_values(actual: pd.Series, standard: pd.Series, metric: MetricSpec) -> pd.Series:
    """지표 사양이 정한 방식으로 차이를 낸다. 두 방식을 섞지 않는 유일한 지점이다."""
    if metric.gap_kind == "point":
        return actual - standard
    return _ratio_or_na(actual, standard) - 1.0


def build_priority_table(
    monthly: pd.DataFrame,
    metric: MetricSpec,
    dimensions: list[str],
) -> pd.DataFrame:
    """개선 우선순위. 미달폭만 보면 물량이 작은 공정이 1위로 올라온다.

    점수는 `미달폭 × 영향 비중 × 연속 미달 가중`이다. 연속 미달을 섞는 이유는 한 달
    튄 것과 반년째 못 맞추는 것이 같은 일이 아니기 때문이다.
    """
    gaps = build_gap_table(monthly, metric, dimensions)
    if gaps.empty:
        gaps["연속 미달"] = pd.Series(dtype="int64")
        gaps["점수"] = pd.Series(dtype="float64")
        gaps["상태"] = pd.Series(dtype="string")
        gaps.insert(0, "우선순위", pd.Series(dtype="int64"))
        return gaps

    streaks = _shortfall_streaks(monthly, metric, dimensions)
    result = gaps.merge(streaks, on=dimensions, how="left", validate="one_to_one")
    result["연속 미달"] = result["연속 미달"].fillna(0).astype("int64")
    shortfall = (-result["Gap"]).clip(lower=0.0)
    streak_weight = 1.0 + result["연속 미달"] / max(1, DEMO_MONTH_COUNT)
    result["점수"] = shortfall * result["영향 비중"] * streak_weight * 1_000
    result["상태"] = [_status_label(int(streak)) for streak in result["연속 미달"]]
    result = result.sort_values("점수", ascending=False, kind="stable")
    result.insert(0, "우선순위", range(1, len(result) + 1))
    return result.reset_index(drop=True)


def build_monthly_trend(
    monthly: pd.DataFrame,
    metric: MetricSpec,
    *,
    processes: list[str] | None = None,
) -> pd.DataFrame:
    """월별 기준·실적·Gap 한 줄씩. 추이 차트와 표가 같은 값을 보게 한다."""
    frame = monthly
    if processes:
        frame = frame.loc[frame["공정"].astype(str).isin(processes)]
    trend = build_gap_table(frame, metric, ["생산계획년월"])
    if trend.empty:
        return trend
    return trend.sort_values("생산계획년월").reset_index(drop=True)


def build_improvement_actions(metric: MetricSpec, priority: pd.DataFrame) -> pd.DataFrame:
    """개선과제 샘플. **우선순위 표에서 나온 공정**에만 과제를 붙인다.

    아무 공정에나 과제를 뿌리면 「순위와 과제가 따로 논다」는 인상을 준다. 이 화면이
    보여 줄 것은 순위가 곧 과제 목록이 된다는 흐름이다.
    """
    if priority.empty or "상태" not in priority.columns:
        return pd.DataFrame(columns=list(_ACTION_COLUMNS))
    targets = priority.loc[priority["상태"].ne("정상")].head(4)
    records: list[dict[str, object]] = []
    for offset, (_, row) in enumerate(targets.iterrows()):
        template = _ACTION_TEMPLATES[offset % len(_ACTION_TEMPLATES)]
        recovery = abs(float(row["Gap"])) * 0.6
        records.append(
            {
                "공정": row["공정"],
                "개선 과제": template[0].format(metric=metric.name),
                "담당": template[1],
                "목표월": _shift_month(DEMO_START_MONTH, DEMO_MONTH_COUNT + offset),
                "진행": template[2],
                "기대 효과": (
                    f"{metric.name} {recovery:.{metric.gap_decimals}%}{metric.gap_suffix} 회복"
                ),
            }
        )
    return pd.DataFrame.from_records(records, columns=list(_ACTION_COLUMNS))


def _shortfall_streaks(
    monthly: pd.DataFrame,
    metric: MetricSpec,
    dimensions: list[str],
) -> pd.DataFrame:
    """분류별 **마지막 달 기준 연속 미달 개월**. 중간에 회복하면 거기서 끊는다."""
    frame = monthly.copy()
    frame["_gap"] = gap_values(
        pd.to_numeric(frame[metric.actual_column], errors="coerce"),
        pd.to_numeric(frame[metric.standard_column], errors="coerce"),
        metric,
    )
    monthly_gap = frame.groupby(
        [*dimensions, "생산계획년월"], as_index=False, dropna=False, sort=True
    ).agg(_gap=("_gap", "mean"))
    records: list[dict[str, object]] = []
    for keys, group in monthly_gap.groupby(dimensions, dropna=False, sort=False):
        ordered = group.sort_values("생산계획년월")
        streak = 0
        for value in reversed(ordered["_gap"].tolist()):
            if value >= 0:
                break
            streak += 1
        key_values = keys if isinstance(keys, tuple) else (keys,)
        record: dict[str, object] = dict(zip(dimensions, key_values, strict=True))
        record["연속 미달"] = streak
        records.append(record)
    return pd.DataFrame.from_records(records, columns=[*dimensions, "연속 미달"])


def _status_label(streak: int) -> str:
    """상태는 **지금**을 말한다. 마지막 달이 기준을 채웠으면 정상이다.

    기간 평균 Gap 으로 판정하면 반년 전의 미달이 지금의 상태로 읽힌다. 회복한 공정이
    계속 「관찰」에 남아 우선순위 표가 옛날 이야기를 하게 된다. 평균 Gap 은 `Gap` 컬럼이
    따로 답한다.
    """
    if streak == 0:
        return "정상"
    if streak >= 3:
        return "개선 필요"
    return "관찰"


def _shift_month(month: int, offset: int) -> int:
    year, value = divmod(month, 100)
    total = year * 12 + (value - 1) + offset
    return (total // 12) * 100 + (total % 12) + 1


def _ratio_or_na(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """분모가 0이면 **결측** 으로 남긴다. `dynamic_capacity._ratio_or_zero` 와 합치지 않는다."""
    result = numerator.astype("float64") / denominator.astype("float64").replace(0.0, pd.NA)
    return result.astype("float64")


def _clip(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)
