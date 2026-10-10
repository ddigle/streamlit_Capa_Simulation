# Purpose: 원천 Core Data 에 남아 있는 기존 결과와 신규 계산값을 같은 단위로 대조한다.

"""기존 앱이 계산해 원천에 실어 보낸 값과 이 앱의 계산값을 맞춰 본다.

`raw_data.core_data` 에 기존 결과 컬럼이 그대로 보존돼 있어 별도 테이블이 필요 없다.

**집계 단위를 맞추는 것이 이 모듈의 전부다.** 원천은 경로(공정·STEP·MCP)별로 행이
펼쳐져 있고 기존 결과 컬럼은 그 경로 행마다 같은 값이 반복된다. 그래서 기존 쪽은
**계획 한 줄(`RQ_PKG_PLAN` 업무 키) × `WF 구분`** 을 한 칸으로 보고 그 안의 반복을 접은
뒤, 대조 키로 합산한다. 신규 쪽도 같은 계획 줄들을 합산하므로 양쪽 단위가 같아진다.

접는 층을 한 단계 위(대조 키)에서 잡으면 **서로 다른 계획 줄까지 하나로 뭉개진다.**
처음에 그렇게 만들었다가 값이 갈리는 키를 전부 `대조 불가` 로 떨어뜨렸고, 그 결과
샘플에서 Wafer 270키 중 121키만 보고 "차이율 0.0000%, 완전 일치" 라는 거짓 결론을 냈다.
빠진 149키는 기존값이 없어서가 아니라 계획 줄이 여럿이라 갈린 것이었다.
`tests/test_legacy_comparison.py` 가 이 함정을 고정한다.

기존 결과 컬럼이 한 칸 안에서도 갈리면 그때는 접을 수 없다. 조용히 하나를 고르지 않고
`값 불일치` 로 세어 밖으로 내보낸다 — 실데이터에서는 경로마다 다른 값이 실려 오는 것이
정상일 수 있고, 그러면 이 대조 자체를 다시 설계해야 한다는 신호다.

**정식 대조(`COMPARISONS`)는 셋이다.**

| 기존 컬럼 | 신규 계산 | 단위 | 대조 키 |
|---|---|---|---|
| `WF수(매)` | `calculate_wafer_load` 의 물량 | 매 | `COMPARISON_KEYS` |
| `EQ(억Gb)` | `calculate_density_load` 의 물량 | 억Gb | `COMPARISON_KEYS` |
| `Plan_Chip(K개)` | `calculate_chip_load` 의 물량 | K개 | 계획 줄(Pack Code 합산) × WF 구분 |

`Plan_Chip(K개)` 는 사내 실데이터(리뷰 202610071831 8-2)에서 신규 Chip 부하량과 계획 줄 단위로
1,264키 중 1,248키가 ≈1 이라 같은 정의로 보고 넣었다(2026-10-08 사용자 결정). `GOOD_DIE` 는
부하량이 아니라 웨이퍼당 양품 다이 쪽 속성이라 넣지 않는다. `PCB수(K매)` 는 신규 산식이 없다.
`소요대수` 는 값이 경로 행마다 달라 대조 단위가 다르다 — 사내 확인 스크립트가 경로 키로 따로
대조하고, 기존÷신규가 ≈60 인 무리를 가르는 집계(아래 「소요대수 ≈60 배 가르기」)도 거기서 쓴다.
로컬 합성 샘플은 `소요대수` 를 채우지 않는다(`scripts/generate_sample_core_data.py`).

Wafer `WF수(매)` 는 사내 실데이터에서 계획 줄 × WF 구분 안에서도 경로 행마다 갈렸다(경로
값이다). 신규 계산에는 경로마다 갈리는 Wafer 값이 없으므로, 아래 「Wafer 경로 값 가르기」가
원천 경로 값이 어느 경로 칸을 따라 갈리는지를 개수로 가른다. 계획 줄 대조는 연속성을 위해
그대로 둔다.

사내 실데이터에서는 키별 값을 밖으로 낼 수 없다. 그래서 대조 결과를 **분포로만** 접는
`difference_distribution`(차이율)·`ratio_distribution`(기존 ÷ 신규) 를 둔다 —
`scripts/inspect_real_data_checks.py` 가 이 둘로 리뷰 문서에 옮길 집계를 만든다. 대조 키와 접는
단위는 `compare_metric` 의 `keys`·`grain` 으로 바꿀 수 있다(소요대수는 경로 키로 접는다).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from capa_simulation.io.core_data_source import CoreDataContract, load_core_data_contract
from capa_simulation.services.frame_contracts import (
    match_key,
    normalize_demand_basis,
    require_columns,
)
from capa_simulation.services.load_calculator import CHIP_KEYS, YIELD_KEYS
from capa_simulation.services.required_equipment import LOAD_KEYS, REQB_COLUMNS
from capa_simulation.services.unit_capacity import (
    MODULE_KEYS,
    PERFORMANCE_KEYS,
    RUN_DAY_KEYS,
    RUN_RATE_KEYS,
    VITAL_KEYS,
)

# 원천 행과 신규 계산 행을 잇는 키. 둘 다 이 조합을 갖고 있다.
COMPARISON_KEYS: list[str] = ["생산계획년월", "제품정보", "Stack", "WF 구분"]

COMPARISON_COLUMNS: list[str] = [
    *COMPARISON_KEYS,
    "지표",
    "기존값",
    "신규값",
    "차이",
    "차이율",
    "값 불일치",
]

# 차이율이 이 값을 넘으면 반올림 오차가 아니다. 화면·스크립트가 바꿔 넘길 수 있다.
DEFAULT_TOLERANCE = 0.005


@dataclass(frozen=True)
class LegacyMetric:
    """대조할 지표 하나. 기존 컬럼과 신규 계산 결과를 같은 단위로 맞춰 둔다.

    `plan_line` 이 참이면 대조 키가 `COMPARISON_KEYS` 가 아니라 **계획 줄(Pack Code 합산) ×
    WF 구분**(`plan_line_keys`)이다. 계획 줄마다 맞대므로 월×제품×Stack 합계보다 엄격하다.
    """

    label: str
    legacy_column: str
    new_column: str = "물량"
    plan_line: bool = False


COMPARISONS: tuple[LegacyMetric, ...] = (
    LegacyMetric(label="Wafer 부하량 (매)", legacy_column="WF수(매)"),
    LegacyMetric(label="Density (억Gb)", legacy_column="EQ(억Gb)"),
    LegacyMetric(label="Chip 부하량 (K개)", legacy_column="Plan_Chip(K개)", plan_line=True),
)


def legacy_grain(contract: CoreDataContract) -> list[str]:
    """기존 결과 값이 한 번만 기록되는 단위.

    계획 한 줄(`RQ_PKG_PLAN` 업무 키)에 `WF 구분` 을 더한 것이다. 업무 키를 계약에서
    읽으므로 키가 늘면(예: `Pack Code` 승격) 대조도 따라 움직인다.
    """
    return [*contract.derived_keys["RQ_PKG_PLAN"], "WF 구분"]


def plan_line_keys(contract: CoreDataContract) -> list[str]:
    """계획 줄(Pack Code 합산) × WF 구분. 부하량 계산 결과에는 `Pack Code` 가 없다 — 합산된다."""
    return [key for key in legacy_grain(contract) if key != "Pack Code"]


def metric_keys(metric: LegacyMetric, contract: CoreDataContract) -> list[str]:
    """그 지표의 대조 키."""
    return plan_line_keys(contract) if metric.plan_line else list(COMPARISON_KEYS)


def compare_metric(
    core: pd.DataFrame,
    calculated: pd.DataFrame,
    metric: LegacyMetric,
    contract: CoreDataContract | None = None,
    *,
    keys: Sequence[str] | None = None,
    grain: Sequence[str] | None = None,
) -> pd.DataFrame:
    """기존 컬럼과 신규 계산을 대조 키 단위 합계로 맞춰 본다.

    `core` 는 `build_q_core_data` 를 거친 **파생 프레임**이어야 한다. 업무 키의 `양산구분`
    이 그 단계에서 만들어지므로 원시 프레임을 넘기면 `require_columns` 가 막는다.

    한쪽에만 있는 키도 결과에 남긴다. 빠진 쪽은 0 이 아니라 결측으로 두어 "값이 0" 과
    "그 키가 없음" 을 구분한다.

    `keys` 는 양쪽을 잇는 대조 키(비우면 지표의 `metric_keys`), `grain` 은 기존 값이 한 번만
    기록되는 단위다(기본은 `legacy_grain`). 기존 쪽은 `grain` 안의 반복을 접은 뒤 `keys` 로
    더하므로 `keys` 는 `grain` 안에 있어야 한다. 결과의 앞 칸은 `keys` 차례 그대로다.
    """
    selected = contract or load_core_data_contract()
    key_list = list(dict.fromkeys(keys if keys is not None else metric_keys(metric, selected)))
    grain_list = list(dict.fromkeys(grain if grain is not None else legacy_grain(selected)))
    outside = [key for key in key_list if key not in grain_list]
    if outside:
        raise ValueError(f"대조 키가 접는 단위 밖에 있습니다: {outside}")
    require_columns(core, [*grain_list, metric.legacy_column], "Core Data")
    require_columns(calculated, [*key_list, metric.new_column], "신규 계산")

    legacy = _legacy_totals(core, metric.legacy_column, grain_list, key_list)
    fresh = _summed(calculated, metric.new_column, "신규값", key_list)
    merged = legacy.merge(fresh, on=key_list, how="outer", validate="one_to_one")
    # outer 조인으로 생긴 결측은 "불일치 아님" 이다. `eq(True)` 가 결측을 False 로 접는다.
    merged["값 불일치"] = merged["값 불일치"].eq(True)

    merged["지표"] = metric.label
    merged["차이"] = merged["신규값"] - merged["기존값"]
    # 기존값이 0 이면 비율이 무한대가 된다. 절대 차이만 남기고 비율은 비운다.
    denominator = merged["기존값"].abs()
    merged["차이율"] = (merged["차이"].abs() / denominator).where(denominator.gt(0))
    columns = [*key_list, *COMPARISON_COLUMNS[len(COMPARISON_KEYS) :]]
    return merged.loc[:, columns].sort_values(["지표", *key_list], ignore_index=True)


def summarize_comparison(
    comparison: pd.DataFrame,
    tolerance: float = DEFAULT_TOLERANCE,
) -> dict[str, object]:
    """지표별로 "몇 건 중 몇 건이 어긋나는가" 를 센다.

    원인이 다른 것을 같은 통에 넣지 않는다. **한쪽에만 있는 키**는 연결 실패,
    **값 불일치**는 기존 쪽을 접을 수 없었다는 뜻, **기존 0·신규 있음**은 기존이 0 을
    적어 비율을 구할 수 없는 자리, **허용 초과**만이 비율로 확인한 계산 차이다.
    뭉치면 원인을 못 찾는다 — 실제로 값 불일치를 `신규에만 있음` 으로 흘려보내
    "기존이 비워 둔 자리" 라고 잘못 읽은 적이 있고, 기존 0 은 `fillna(0.0)` 때문에
    통과로 세어 버린 적이 있다.
    """
    if comparison.empty:
        return {
            "대조 건수": 0,
            "허용 초과": 0,
            "기존 0·신규 있음": 0,
            "값 불일치": 0,
            "신규에만 있음": 0,
            "기존에만 있음": 0,
            "최대 차이율": None,
        }
    conflicting = comparison["값 불일치"].astype(bool)
    legacy_missing = comparison["기존값"].isna() & ~conflicting
    fresh_missing = comparison["신규값"].isna()
    matched = comparison.loc[~conflicting & ~comparison["기존값"].isna() & ~fresh_missing]
    ratio = matched["차이율"]
    exceeded = matched.loc[ratio.gt(tolerance)]
    # 기존값이 0 이면 비율이 없다. 예전에 `fillna(0.0)` 으로 통과시켜 59건을 놓쳤다.
    zero_based = matched.loc[ratio.isna() & matched["차이"].ne(0)]
    return {
        "대조 건수": int(len(matched)),
        "허용 초과": int(len(exceeded)),
        # 기존이 0 을 적어 둔 자리. 비율이 없으므로 절대 차이로만 판단해야 한다.
        "기존 0·신규 있음": int(len(zero_based)),
        # 기존 쪽을 접을 수 없었던 키. 차이가 아니라 집계 실패다.
        "값 불일치": int(conflicting.sum()),
        # 기존이 비워 둔 자리를 신규가 채우는 것은 안전한 방향이다.
        "신규에만 있음": int((legacy_missing & ~fresh_missing).sum()),
        # 신규가 놓친 자리다. 이쪽이 0 이 아니면 계산이 빠뜨린 것이 있다는 뜻이다.
        "기존에만 있음": int((fresh_missing & ~legacy_missing & ~conflicting).sum()),
        "최대 차이율": (None if ratio.dropna().empty else float(ratio.max())),
    }


@dataclass(frozen=True)
class DifferenceDistribution:
    """키별 차이율(|신규 − 기존| ÷ |기존|)을 분포로만 접은 것. 키·값은 담지 않는다.

    대상은 `summarize_comparison` 의 「대조 건수」와 같은 키(양쪽에 값이 있고 접을 수 있었던
    키) 가운데 기존값이 0 이 아닌 것이다. `sum_ratio` 는 그 키들의 Σ신규 ÷ Σ기존 — 합계 자체는
    업무 물량이라 비율로만 남긴다.
    """

    keys: int
    median: float | None
    p95: float | None
    maximum: float | None
    over: tuple[tuple[float, int], ...]
    sum_ratio: float | None


@dataclass(frozen=True)
class RatioDistribution:
    """키별 기존 ÷ 신규 비율의 분포. 단위·정의가 같은지 값을 내보내지 않고 가늠하는 증거다.

    두 값이 모두 양수인 키만 본다(`undefined` 는 나머지 대조 키 수). `near` 는 (기준, 키 수) —
    비율이 기준의 ±`tolerance` 안에 든 키다. `decades` 는 (k, 키 수) — 비율을 10^k 자릿수로
    반올림해 센 것이다(1000 배 단위 차이가 한눈에 보인다).
    """

    keys: int
    undefined: int
    median: float | None
    p5: float | None
    p95: float | None
    tolerance: float
    near: tuple[tuple[float, int], ...]
    decades: tuple[tuple[int, int], ...]


# 「거의 같다」 기준. 단위가 1000 배 갈렸는지 가리는 용도라 반올림 오차보다 넉넉하게 둔다.
NEAR_TOLERANCE = 0.05
NEAR_TARGETS: tuple[float, ...] = (1.0, 1_000.0, 0.001)
DIFFERENCE_THRESHOLDS: tuple[float, ...] = (0.001, 0.01)


def _matched_rows(comparison: pd.DataFrame) -> pd.DataFrame:
    """`summarize_comparison` 의 「대조 건수」 와 같은 행 — 양쪽에 값이 있고 접을 수 있었던 키."""
    conflicting = comparison["값 불일치"].astype(bool)
    present = comparison["기존값"].notna() & comparison["신규값"].notna()
    return comparison.loc[present & ~conflicting]


def _quantile(values: pd.Series, q: float) -> float | None:
    return None if values.empty else float(np.quantile(values.to_numpy(dtype="float64"), q))


def difference_distribution(
    comparison: pd.DataFrame,
    thresholds: Sequence[float] = DIFFERENCE_THRESHOLDS,
) -> DifferenceDistribution:
    """`compare_metric` 결과의 차이율 분포. 임계(기본 0.1%·1%)를 넘는 키 수를 함께 센다."""
    matched = _matched_rows(comparison)
    rates = pd.to_numeric(matched["차이율"], errors="coerce").dropna().astype("float64")
    legacy_total = float(pd.to_numeric(matched["기존값"], errors="coerce").sum())
    fresh_total = float(pd.to_numeric(matched["신규값"], errors="coerce").sum())
    return DifferenceDistribution(
        keys=int(len(rates)),
        median=_quantile(rates, 0.5),
        p95=_quantile(rates, 0.95),
        maximum=None if rates.empty else float(rates.max()),
        over=tuple((float(limit), int(rates.gt(limit).sum())) for limit in thresholds),
        sum_ratio=fresh_total / legacy_total if legacy_total else None,
    )


def ratio_distribution(
    comparison: pd.DataFrame,
    *,
    targets: Sequence[float] = NEAR_TARGETS,
    tolerance: float = NEAR_TOLERANCE,
) -> RatioDistribution:
    """`compare_metric` 결과의 기존 ÷ 신규 비율 분포."""
    matched = _matched_rows(comparison)
    legacy = pd.to_numeric(matched["기존값"], errors="coerce").astype("float64")
    fresh = pd.to_numeric(matched["신규값"], errors="coerce").astype("float64")
    return describe_ratios(legacy, fresh, targets=targets, tolerance=tolerance)


def describe_ratios(
    numerator: pd.Series,
    denominator: pd.Series,
    *,
    targets: Sequence[float] = NEAR_TARGETS,
    tolerance: float = NEAR_TOLERANCE,
) -> RatioDistribution:
    """같은 길이의 두 수열로 비율 분포를 만든다. 두 값이 모두 양수인 자리만 센다.

    키 대조 없이 행 단위로 정의 후보(예: `GOOD_DIE ÷ Net Die`)를 볼 때도 쓴다.
    """
    top = pd.to_numeric(numerator, errors="coerce").astype("float64").reset_index(drop=True)
    bottom = pd.to_numeric(denominator, errors="coerce").astype("float64").reset_index(drop=True)
    usable = top.gt(0) & bottom.gt(0)
    ratios = (top.loc[usable] / bottom.loc[usable]).astype("float64")
    near = tuple(
        (float(target), int(((ratios / target) - 1.0).abs().le(tolerance).sum()))
        for target in targets
    )
    decade_counts: dict[int, int] = {}
    for value in ratios:
        decade = int(math.floor(math.log10(value) + 0.5))
        decade_counts[decade] = decade_counts.get(decade, 0) + 1
    return RatioDistribution(
        keys=int(len(ratios)),
        undefined=int(len(top) - len(ratios)),
        median=_quantile(ratios, 0.5),
        p5=_quantile(ratios, 0.05),
        p95=_quantile(ratios, 0.95),
        tolerance=tolerance,
        near=near,
        decades=tuple(sorted(decade_counts.items())),
    )


def _summed(
    frame: pd.DataFrame, value_column: str, output_name: str, keys: list[str]
) -> pd.DataFrame:
    """신규 계산 쪽. 키 하나에 여러 행이 나올 수 있으므로 더한다."""
    prepared = _normalized(frame, keys, value_column)
    grouped = prepared.groupby(keys, as_index=False, dropna=False)[[value_column]].sum()
    grouped.columns = [*keys, output_name]
    return grouped


def _legacy_totals(
    frame: pd.DataFrame, value_column: str, grain: list[str], keys: list[str]
) -> pd.DataFrame:
    """기존 결과 쪽. 그레인 안의 경로 반복을 접은 뒤 대조 키로 합산한다.

    한 그레인 안에서 값이 갈리면 접을 수 없다. 그 대조 키는 `값 불일치` 로 표시하고
    기존값을 비워 둔다 — 조용히 하나를 고르면 대조가 거짓말이 된다.
    """
    prepared = _normalized(frame, grain, value_column)
    folded = prepared.groupby(grain, as_index=False, dropna=False).agg(
        **{
            value_column: pd.NamedAgg(column=value_column, aggfunc="max"),
            "_고유값수": pd.NamedAgg(column=value_column, aggfunc="nunique"),
        }
    )
    folded["_불일치"] = folded["_고유값수"].gt(1)
    grouped = folded.groupby(keys, as_index=False, dropna=False).agg(
        기존값=pd.NamedAgg(column=value_column, aggfunc="sum"),
        **{"값 불일치": pd.NamedAgg(column="_불일치", aggfunc="any")},
    )
    grouped.loc[grouped["값 불일치"], "기존값"] = pd.NA
    return grouped


def _normalized(frame: pd.DataFrame, keys: list[str], value_column: str) -> pd.DataFrame:
    prepared = frame.loc[:, [*keys, value_column]].copy()
    for key in keys:
        if key != "생산계획년월":
            prepared[key] = prepared[key].astype("string").str.strip()
    prepared["생산계획년월"] = pd.to_numeric(prepared["생산계획년월"], errors="coerce").astype(
        "Int64"
    )
    prepared[value_column] = pd.to_numeric(prepared[value_column], errors="coerce")
    return prepared.dropna(subset=[value_column])


# ---------------------------------------------------------------- 소요대수 ≈60 배 가르기
#
# 사내 실데이터(리뷰 202610071831·202610080745 8-2)에서 경로 키 27,568개 가운데 약 절반이 기존 =
# 신규 × 60 이었고 WF 소요기준에 몰렸다. 분↔시간 같은 단위 어긋남으로 보이지만 **어느 쪽이 틀렸는지
# 모른다.** 아래 함수들은 그 무리가 어디서 나는지를 값 없이 개수로 가른다(2026-10-08 사용자 결정).
# 세 무리 — 기존 ÷ 신규가 ≈60, ≈1(각 ±`NEAR_TOLERANCE`), 그 밖 — 로 나누고 무리마다 속성·공정·산식
# 인자를 견준다. 입력은 `compare_metric(keys=REQB_COLUMNS)` 결과(경로 키 13)다.

SUSPECT_RATIO = 60.0
SUSPECT_GROUP = "≈60"
AGREE_GROUP = "≈1"
OTHER_GROUP = "그 밖"
RATIO_GROUPS: tuple[str, ...] = (SUSPECT_GROUP, AGREE_GROUP, OTHER_GROUP)
GROUP_COLUMN = "무리"
RATIO_COLUMN = "기존÷신규"
# 단위 상수가 원인이면 비율이 60 에 딱 붙는다. ±5% 안이지만 퍼져 있으면 다른 원인이다.
TIGHT_TOLERANCE = 0.001
# 키 하나에 원천 경로 행의 값이 여럿이면 이 표지로 묶는다(값은 찍지 않는다).
MANY_VALUES = "<여럿>"
# 신규 계산 결과(`calculate_required_equipment`)에서 읽는 인자의 표 이름.
RESULT_TABLE = "신규 계산"


@dataclass(frozen=True)
class RatioGroups:
    """비율이 정의된 대조 키(두 값이 모두 양수)에 `무리`·`기존÷신규` 칸을 단 것."""

    frame: pd.DataFrame
    undefined: int
    tight: int

    def size(self, group: str) -> int:
        return int(self.frame[GROUP_COLUMN].eq(group).sum())


def ratio_groups(comparison: pd.DataFrame, *, tolerance: float = NEAR_TOLERANCE) -> RatioGroups:
    """`compare_metric` 결과를 세 무리로 나눈다. `undefined` 는 비율이 없는 대조 건수다.

    대상은 `ratio_distribution` 과 같은 키라 두 표의 수가 맞아떨어진다.
    """
    matched = _matched_rows(comparison)
    legacy = pd.to_numeric(matched["기존값"], errors="coerce").astype("float64")
    fresh = pd.to_numeric(matched["신규값"], errors="coerce").astype("float64")
    usable = legacy.gt(0) & fresh.gt(0)
    frame = matched.loc[usable].copy()
    ratio = (legacy.loc[usable] / fresh.loc[usable]).astype("float64")
    frame[RATIO_COLUMN] = ratio
    frame[GROUP_COLUMN] = OTHER_GROUP
    frame.loc[_near(ratio, 1.0, tolerance), GROUP_COLUMN] = AGREE_GROUP
    frame.loc[_near(ratio, SUSPECT_RATIO, tolerance), GROUP_COLUMN] = SUSPECT_GROUP
    return RatioGroups(
        frame=frame.reset_index(drop=True),
        undefined=int(len(matched) - int(usable.sum())),
        tight=int(_near(ratio, SUSPECT_RATIO, TIGHT_TOLERANCE).sum()),
    )


@dataclass(frozen=True)
class ProcessConsistency:
    """공정마다 그 키들이 어느 무리에 드는가. 다섯 칸의 합이 `processes` 다."""

    processes: int
    all_suspect: int
    all_agree: int
    all_other: int
    mixed: int  # ≈60 과 ≈1 이 함께 있다(그 밖이 끼어도)
    partly_other: int  # ≈60·≈1 가운데 하나와 그 밖


def process_consistency(frame: pd.DataFrame, process: str = "공정") -> ProcessConsistency:
    present = (
        pd.crosstab(_match_column(frame, process), frame[GROUP_COLUMN])
        .reindex(columns=list(RATIO_GROUPS), fill_value=0)
        .gt(0)
    )
    suspect = present[SUSPECT_GROUP]
    agree = present[AGREE_GROUP]
    other = present[OTHER_GROUP]
    return ProcessConsistency(
        processes=int(len(present)),
        all_suspect=int((suspect & ~agree & ~other).sum()),
        all_agree=int((agree & ~suspect & ~other).sum()),
        all_other=int((other & ~suspect & ~agree).sum()),
        mixed=int((suspect & agree).sum()),
        partly_other=int((other & (suspect ^ agree)).sum()),
    )


@dataclass(frozen=True)
class SplitCount:
    """≈60 과 ≈1 이 섞인 공정 가운데 그 속성이 둘을 가르는 공정 수.

    `splits` — 공정 안에서 속성 값마다 무리가 하나뿐이다. `trivial` — 그렇지만 값이 키마다 달라
    저절로 갈린 것이라 증거가 못 된다. `fails` — 한 값 안에 두 무리가 섞여 있다.
    """

    attribute: str
    splits: int
    fails: int
    trivial: int


def split_mixed_processes(
    frame: pd.DataFrame, attributes: Sequence[str], process: str = "공정"
) -> tuple[SplitCount, ...]:
    """≈60 과 ≈1 이 함께 있는 공정만 골라, 속성마다 두 무리를 가르는지 센다(그 밖 키는 뺀다)."""
    pair = frame.loc[frame[GROUP_COLUMN].isin((SUSPECT_GROUP, AGREE_GROUP))]
    owner = _match_column(pair, process)
    kinds = pair[GROUP_COLUMN].groupby(owner).nunique()
    mixed = pair.loc[owner.isin(set(kinds.index[kinds.gt(1)]))]
    results: list[SplitCount] = []
    for attribute in attributes:
        if attribute not in mixed.columns:
            continue
        cells = pd.DataFrame(
            {
                "공정": _match_column(mixed, process),
                "값": _match_column(mixed, attribute),
                "무리": mixed[GROUP_COLUMN],
            }
        )
        pure = cells.groupby(["공정", "값"])["무리"].nunique().eq(1).groupby(level="공정").all()
        values = cells.groupby("공정")["값"].nunique()
        size = cells.groupby("공정").size()
        trivial = pure & values.eq(size)
        results.append(
            SplitCount(
                attribute=attribute,
                splits=int((pure & ~trivial).sum()),
                fails=int((~pure).sum()),
                trivial=int(trivial.sum()),
            )
        )
    return tuple(results)


@dataclass(frozen=True)
class Quantiles:
    keys: int
    p5: float | None
    median: float | None
    p95: float | None


def group_spread(frame: pd.DataFrame, values: pd.Series) -> dict[str, Quantiles]:
    """무리마다 값의 p5·중앙·p95. `values` 는 `frame` 과 같은 인덱스다(빈 값은 뺀다)."""
    numeric = pd.to_numeric(values, errors="coerce").astype("float64")
    spread: dict[str, Quantiles] = {}
    for group in RATIO_GROUPS:
        part = numeric.loc[frame[GROUP_COLUMN].eq(group)].dropna()
        spread[group] = Quantiles(
            keys=int(len(part)),
            p5=_quantile(part, 0.05),
            median=_quantile(part, 0.5),
            p95=_quantile(part, 0.95),
        )
    return spread


def median_ratio(spread: dict[str, Quantiles]) -> float | None:
    """≈60 무리 중앙 ÷ ≈1 무리 중앙. 60 이나 1/60 근처면 그 인자가 단위째 다르다."""
    suspect = spread[SUSPECT_GROUP].median
    agree = spread[AGREE_GROUP].median
    if suspect is None or agree is None or agree == 0:
        return None
    return suspect / agree


@dataclass(frozen=True)
class ScalingCheck:
    """한 인자를 60 배로 고쳐 다시 계산한 결과(`scaling_check`)."""

    applicable: int  # 그 인자가 산식에 걸리는 ≈60 키
    fixed: int
    collateral: int


def scaling_check(
    frame: pd.DataFrame,
    keys: Sequence[str],
    applies: pd.Series | None = None,
    *,
    factor: float = SUSPECT_RATIO,
    tolerance: float = NEAR_TOLERANCE,
) -> ScalingCheck:
    """그 인자를 신규가 60 배가 되는 쪽으로 고쳐 다시 계산하면 ≈60 키가 몇이나 ≈1 이 되는가.

    소요대수 = 부하량 ÷ 대당 Capa 는 인자들의 곱·나눗셈이다. 그래서 **키 하나만 보면 어느 인자를
    고쳐도 똑같이 60 배가 맞는다** — 그것으로는 인자를 가를 수 없다. 가르는 것은 인자 값이 정해지는
    단위(`keys`)다. 인자 값 하나는 그 단위를 같이 쓰는 경로 키 모두에 걸리므로, 고침도 인자 값
    단위로 한다.

    - `fixed` — ≈1 키와 같이 쓰지 않는 인자 값만 고쳤을 때 ≈1 이 되는 ≈60 키.
    - `collateral` — ≈60 키가 쓰는 인자 값을 모두 고치면 함께 바뀌어 ≈1 을 벗어나는 ≈1 키.

    `fixed` 가 `applicable` 과 같고 `collateral` 이 0 이면 그 인자 하나로 60 배가 설명된다.
    `applies` 는 그 인자가 산식에 걸리는 키다(UPEH 는 Main, ST 는 MI 에만 걸린다). 걸리지 않는
    키는 고쳐도 값이 바뀌지 않는다.
    """
    if applies is None:
        reach = pd.Series(True, index=frame.index)
    else:
        reach = applies.reindex(frame.index, fill_value=False).astype(bool)
    group = frame[GROUP_COLUMN]
    suspect = group.eq(SUSPECT_GROUP) & reach
    agree = group.eq(AGREE_GROUP) & reach
    entity = _key_ids(frame, keys)
    touched = reach & entity.isin(set(entity.loc[suspect]))
    shared = entity.isin(set(entity.loc[agree]))
    legacy = pd.to_numeric(frame["기존값"], errors="coerce").astype("float64")
    fresh = pd.to_numeric(frame["신규값"], errors="coerce").astype("float64")

    def near_one(scaled: pd.Series) -> pd.Series:
        rescaled = fresh.where(~scaled, fresh * factor)
        return _near(legacy / rescaled, 1.0, tolerance)

    return ScalingCheck(
        applicable=int(suspect.sum()),
        fixed=int((suspect & near_one(touched & ~shared)).sum()),
        collateral=int((agree & ~near_one(touched)).sum()),
    )


@dataclass(frozen=True)
class FormulaInput:
    """소요대수 산식의 인자 하나 — 어느 표의 어느 칸이고, 값이 어느 단위로 정해지며, 어디에 걸리나.

    `keys` 는 인자 값이 정해지는 단위(`scaling_check` 가 공유를 판정한다), `join_keys` 는 값을
    읽어 오는 키다(비우면 `keys`). `bases`·`area` 가 비면 모든 키에 걸린다. `volume` 이면 업무
    물량이라 절대값을 찍지 않는다.
    """

    label: str
    table: str
    column: str
    keys: tuple[str, ...]
    join_keys: tuple[str, ...] = ()
    bases: tuple[str, ...] = ()
    area: str | None = None
    volume: bool = False

    @property
    def lookup_keys(self) -> tuple[str, ...]:
        return self.join_keys or self.keys


_PERFORMANCE_INPUT_KEYS = (*PERFORMANCE_KEYS, "소요기준")

# 산식(AGENTS.md 6장): 소요대수 = 부하량 ÷ 대당 Capa,
# 대당 Capa = 환산_UPEH × 24 × CAPA_RUN_RATE ÷ 편중률 × 모듈수 × RUN_DAY ÷ Lot 측정률 ÷ WF측정률,
# 환산_UPEH = UPEH(Main) 또는 3600 ÷ ST(MI), CHIP·PKG 는 ÷ 1000.
# WF 부하량 = 생산수량 × 1000 × 구분_Chip ÷ EDS ÷ BE ÷ Net Die,
# CHIP 부하량 = 생산수량 × 구분_Chip ÷ BE, PKG 부하량 = 생산수량.
# Dummy 는 (1 − EDS) 가 더 걸려 수율이 곱으로만 들지 않는다.
FORMULA_INPUTS: tuple[FormulaInput, ...] = (
    FormulaInput(
        "부하량",
        RESULT_TABLE,
        "부하량",
        keys=tuple(LOAD_KEYS),
        join_keys=tuple(REQB_COLUMNS),
        volume=True,
    ),
    FormulaInput("구분_Chip", "RQ_CHIP_QTY", "구분_Chip", tuple(CHIP_KEYS), bases=("CHIP", "WF")),
    FormulaInput("Net Die", "RQ_CHIP_QTY", "Net Die", tuple(CHIP_KEYS), bases=("WF",)),
    FormulaInput("EDS_수율", "RQ_YLD", "EDS_수율", tuple(YIELD_KEYS), bases=("WF",)),
    FormulaInput("BE_수율", "RQ_YLD", "BE_수율", tuple(YIELD_KEYS), bases=("CHIP", "WF")),
    FormulaInput("UPEH", "RQ_UPEH", "UPEH", _PERFORMANCE_INPUT_KEYS, area="Main"),
    FormulaInput("ST", "RQ_UPEH", "ST", _PERFORMANCE_INPUT_KEYS, area="MI"),
    FormulaInput("CAPA_RUN_RATE", "RQ_RUN_RATE", "CAPA_RUN_RATE", tuple(RUN_RATE_KEYS)),
    FormulaInput("편중률", "RQ_VITAL", "편중률", tuple(VITAL_KEYS)),
    FormulaInput("모듈수", "RQ_MODULE", "모듈수", tuple(MODULE_KEYS)),
    FormulaInput("RUN_DAY", "RQ_RUN_DAY", "RUN_DAY", tuple(RUN_DAY_KEYS)),
    FormulaInput("Lot 측정률", "RQ_LOT_RATIO", "Lot 측정률", tuple(PERFORMANCE_KEYS)),
    FormulaInput("WF측정률", "RQ_WF_RATIO", "WF측정률", tuple(PERFORMANCE_KEYS)),
)


def attach_formula_inputs(
    frame: pd.DataFrame,
    required: pd.DataFrame,
    tables: dict[str, pd.DataFrame],
    inputs: Sequence[FormulaInput] = FORMULA_INPUTS,
) -> pd.DataFrame:
    """키마다 산식 인자 값을 붙인다(칸 이름은 `label`). 표나 칸이 없으면 빈 칸이다.

    값은 계산이 받는 리비전 표 그대로다 — 계산이 빈 측정률·0 을 1.0 으로 메우는 것은 하지 않는다.
    """
    result = frame.copy()
    for item in inputs:
        source = required if item.table == RESULT_TABLE else tables.get(item.table)
        needed = [*item.lookup_keys, item.column]
        if source is None or any(column not in source.columns for column in needed):
            result[item.label] = np.nan
            continue
        result[item.label] = _lookup(frame, source, item.lookup_keys, item.column)
    return result


def input_applies(frame: pd.DataFrame, item: FormulaInput) -> pd.Series:
    """그 인자가 산식에 걸리는 키."""
    reach = pd.Series(True, index=frame.index)
    if item.bases:
        bases = {basis.casefold() for basis in item.bases}
        reach &= _match_column(frame, "소요기준").isin(bases)
    if item.area is not None:
        reach &= _match_column(frame, "Area_Name").eq(item.area.casefold())
    return reach


def hourly_rate(frame: pd.DataFrame) -> pd.Series:
    """계산이 쓰는 환산_UPEH — Main 은 UPEH, MI 는 3600 ÷ ST, CHIP·PKG 는 ÷ 1000.

    `attach_formula_inputs` 가 붙인 `UPEH`·`ST` 칸을 쓴다.
    """
    area = _match_column(frame, "Area_Name")
    upeh = pd.to_numeric(frame["UPEH"], errors="coerce").astype("float64")
    st = pd.to_numeric(frame["ST"], errors="coerce").astype("float64")
    rate = upeh.where(area.eq("main"))
    rate = rate.mask(area.eq("mi"), 3600.0 / st.where(st.gt(0)))
    per_kea = _match_column(frame, "소요기준").isin({"chip", "pkg"})
    return rate.mask(per_kea, rate / 1000.0)


def time_agreement(frame: pd.DataFrame) -> pd.Series:
    """UPEH × ST ÷ 3600 — 두 시간 칸이 다 있는 키에서 서로 맞는지(초 단위 ST 면 1 근처)."""
    upeh = pd.to_numeric(frame["UPEH"], errors="coerce").astype("float64")
    st = pd.to_numeric(frame["ST"], errors="coerce").astype("float64")
    return (upeh * st / 3600.0).where(upeh.gt(0) & st.gt(0))


def folded_route_totals(
    frame: pd.DataFrame, route: pd.DataFrame, column: str, grain: Sequence[str]
) -> pd.Series:
    """원천 경로 행의 값을 기존 소요대수와 같은 규칙(`grain` 안에서 접고 경로 키로 합산)으로 붙인다.

    `일 필요` 처럼 기존 시스템이 경로 행마다 실어 보낸 중간값을 키 단위로 견줄 때 쓴다.
    """
    if column not in route.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    grain_list = list(dict.fromkeys([*grain, *REQB_COLUMNS]))
    totals = _legacy_totals(route, column, grain_list, list(REQB_COLUMNS))
    return _lookup(frame, totals, REQB_COLUMNS, "기존값")


@dataclass(frozen=True)
class CategoryContrast:
    """원천 범주 컬럼 하나의 무리별 값 종류. 값 자체는 담지 않는다."""

    column: str
    distinct: dict[str, int]
    shared: int  # ≈60·≈1 둘 다에 있는 값 종류
    suspect_only: int  # ≈60 에만 있는 값 종류
    suspect_only_keys: int  # 그 값을 가진 ≈60 키
    agree_only: int  # ≈1 에만 있는 값 종류
    numeric_ratio: float | None  # 숫자로 읽히는 값의 무리 중앙 ≈60 ÷ ≈1


@dataclass(frozen=True)
class RouteLink:
    """무리를 단 경로 키와 원천 경로 행의 짝. 원천에만 있는 칸(기존 시스템의 값)을 키에 붙인다.

    `pairs` 는 (`_키`, `_원천`) — `frame` 인덱스와 `route` 인덱스다. 키 하나에 원천 행이 여럿일 수
    있다(Pack Code 가 다른 계획 줄).
    """

    frame: pd.DataFrame
    route: pd.DataFrame
    pairs: pd.DataFrame

    @classmethod
    def build(
        cls, frame: pd.DataFrame, route: pd.DataFrame, keys: Sequence[str] = tuple(REQB_COLUMNS)
    ) -> RouteLink:
        key_list = list(keys)
        left = pd.DataFrame({key: _match_column(frame, key) for key in key_list})
        left["_키"] = frame.index
        right = pd.DataFrame({key: _match_column(route, key) for key in key_list})
        right["_원천"] = route.index
        pairs = left.merge(right, on=key_list, how="inner").loc[:, ["_키", "_원천"]]
        return cls(frame=frame, route=route, pairs=pairs.reset_index(drop=True))

    def texts(self, column: str) -> pd.DataFrame:
        """(`_키`, `무리`, `값`) — 빈 값은 뺀다."""
        if column not in self.route.columns:
            return pd.DataFrame(columns=["_키", GROUP_COLUMN, "값"])
        values = self.route[column].astype("string").str.strip()
        texts = pd.DataFrame(
            {
                "_키": self.pairs["_키"].to_numpy(),
                GROUP_COLUMN: self.frame[GROUP_COLUMN].reindex(self.pairs["_키"]).to_numpy(),
                "값": values.reindex(self.pairs["_원천"]).to_numpy(),
            }
        )
        filled = texts["값"].astype("string").fillna("").ne("")
        return texts.loc[filled.astype(bool)].reset_index(drop=True)

    def numbers(self, column: str) -> pd.Series:
        """키마다 원천 값의 중앙(숫자로 읽히는 것만)."""
        texts = self.texts(column)
        numeric = pd.to_numeric(texts["값"], errors="coerce").astype("float64")
        per_key = numeric.groupby(texts["_키"]).median()
        return per_key.reindex(self.frame.index).astype("float64")

    def labels(self, column: str) -> pd.Series:
        """키마다 원천 값 — 하나뿐이면 그 값, 여럿이면 `MANY_VALUES`, 없으면 빈 칸."""
        texts = self.texts(column)
        grouped = texts.groupby("_키")["값"]
        single = grouped.first().where(grouped.nunique().eq(1), MANY_VALUES)
        return single.reindex(self.frame.index).astype("string")

    def contrast(self, column: str) -> CategoryContrast | None:
        """무리별 값 종류와 겹침. 컬럼이 없거나 값이 하나도 없으면 `None`."""
        texts = self.texts(column)
        if texts.empty:
            return None
        sets = {
            group: set(texts.loc[texts[GROUP_COLUMN].eq(group), "값"].dropna())
            for group in RATIO_GROUPS
        }
        suspect_only = sets[SUSPECT_GROUP] - sets[AGREE_GROUP]
        holders = texts.loc[
            texts[GROUP_COLUMN].eq(SUSPECT_GROUP) & texts["값"].isin(suspect_only), "_키"
        ]
        spread = group_spread(self.frame, self.numbers(column))
        return CategoryContrast(
            column=column,
            distinct={group: len(values) for group, values in sets.items()},
            shared=len(sets[SUSPECT_GROUP] & sets[AGREE_GROUP]),
            suspect_only=len(suspect_only),
            suspect_only_keys=int(holders.nunique()),
            agree_only=len(sets[AGREE_GROUP] - sets[SUSPECT_GROUP]),
            numeric_ratio=median_ratio(spread),
        )


# ---------------------------------------------------------------- Wafer `WF수(매)` 경로 값 가르기
#
# 사내 실데이터(리뷰 202610071831 8-2)에서 Wafer 대조 296키 가운데 287키가 `값 불일치` 였다 —
# 같은 계획 줄 × WF 구분 안에서도 경로(공정) 행마다 원천 `WF수(매)` 가 갈린다. 계획 줄 값이
# 아니라 경로 값이라 대조를 경로 단위로 다시 본다(2026-10-10 사용자 결정). **신규 계산에는
# 경로마다 갈리는 Wafer 값이 없다** — `required_equipment` 는 계획 줄(Pack Code 합산) × WF 구분의
# Wafer 부하량을 그 계획 줄의 모든 WF 경로에 같은 `부하량` 으로 붙이고, 측정률은 부하가 아니라
# 대당 Capa 의 분모로 들며, Step수·Side반영률은 산식에 없다. 그래서 아래 함수들은 원천 경로 값이
# 무엇으로 갈리는지를 값 없이 개수로 가른다.

# 칸 안의 값이 「한 값」인지 — (최대 − 최소) ≤ 이 비율 × 최대 절댓값. 곱·나눗셈 뒤의
# 반올림만 넘긴다.
ROUTE_SPLIT_TOLERANCE = TIGHT_TOLERANCE
# 계획 줄 × WF 구분 칸 안에서 경로 행마다 달라질 수 있는 칸. 계획 줄 키는 칸 안에서 한 값이라
# 넣지 않는다.
WAFER_ROUTE_ATTRIBUTES: tuple[str, ...] = (
    "소요기준",
    "Area_Name",
    "공정",
    "STEP_SEQ",
    "MCP_SEQ",
    "Step수",
    "Para",
)
# 원천 경로 값과 같은 단위(매)라 곱·나눗셈이 아니라 더하기·빼기로 견주는 칸.
WAFER_ROUTE_ADDEND = "TEST WF수(매)"


@dataclass(frozen=True)
class RouteFactor:
    """경로 값을 가를 후보 하나 — 원천 경로 칸(여럿이면 곱)."""

    label: str
    columns: tuple[str, ...]


WAFER_ROUTE_FACTORS: tuple[RouteFactor, ...] = (
    RouteFactor("Lot 측정률", ("Lot 측정률",)),
    RouteFactor("WF측정률", ("WF측정률",)),
    RouteFactor("Lot 측정률 × WF측정률", ("Lot 측정률", "WF측정률")),
    RouteFactor("Side반영률", ("Side반영률",)),
    RouteFactor("MCP_Chip_Ratio", ("MCP_Chip_Ratio",)),
    RouteFactor("CUM_수율", ("CUM_수율",)),
    RouteFactor("Step수", ("Step수",)),
    RouteFactor("Para", ("Para",)),
    RouteFactor("Shot수", ("Shot수",)),
    RouteFactor("일 필요", ("일 필요",)),
)


def route_factor_values(frame: pd.DataFrame, factor: RouteFactor) -> pd.Series:
    """행마다 후보 값 — 칸들의 곱. 칸이 없거나 숫자로 읽히지 않으면 빈 값이다.

    글자 칸(`Step수`·`Para`·`Shot수`)도 숫자로 읽히면 읽는다.
    """
    if any(column not in frame.columns for column in factor.columns):
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    product = pd.Series(1.0, index=frame.index, dtype="float64")
    for column in factor.columns:
        product = product * pd.to_numeric(frame[column], errors="coerce").astype("float64")
    return product


@dataclass(frozen=True)
class RouteValueSpread:
    """계획 줄 × WF 구분 칸이 경로마다 갈리는 정도.

    `split` 은 `compare_metric` 이 `값 불일치` 로 떨어뜨리는 규칙(칸 안 고유값이 둘 이상) 그대로다.
    `route_split` 은 경로 행(Area_Name 있음)·양수 값만 남겨 `tolerance` 를 넘게 갈리는 칸이다 —
    아래 가르기(`split_route_cells`·`fold_route_cells`)가 보는 칸이다. 둘의 차는 계획 줄 행·0 값이
    만든 갈림이다.
    """

    cells: int
    split: int
    route_cells: int
    route_split: int


@dataclass(frozen=True)
class RouteCells:
    """경로 행·양수 값만 남긴 원천 행과 칸 번호·값. `split` 은 갈리는 칸 번호다."""

    frame: pd.DataFrame
    cell: pd.Series
    values: pd.Series
    split: frozenset[int]

    def split_rows(self) -> pd.Series:
        return self.cell.isin(self.split)


def _varies(values: pd.Series, cell: pd.Series, tolerance: float) -> pd.Series:
    """칸마다 값이 갈리나 — (최대 − 최소) > `tolerance` × 최대 절댓값. 인덱스는 칸 번호다."""
    grouped = values.groupby(cell)
    high = grouped.max()
    low = grouped.min()
    scale = pd.concat([high.abs(), low.abs()], axis=1).max(axis=1)
    return (high - low).gt(scale * tolerance)


def route_cells(
    core: pd.DataFrame,
    value_column: str,
    grain: Sequence[str],
    *,
    tolerance: float = ROUTE_SPLIT_TOLERANCE,
) -> tuple[RouteValueSpread, RouteCells]:
    """기존 값이 한 번만 실린다고 본 칸(`grain`, 보통 `legacy_grain`)이 경로마다 갈리는지 센다."""
    values = pd.to_numeric(core[value_column], errors="coerce").astype("float64")
    present = core.loc[values.notna()]
    cell_all = _key_ids(present, grain)
    distinct = values.loc[present.index].groupby(cell_all).nunique()
    area = present["Area_Name"].astype("string").str.strip().fillna("")
    route_mask = area.ne("") & values.loc[present.index].gt(0)
    route = present.loc[route_mask]
    cell = cell_all.loc[route.index]
    route_values = values.loc[route.index]
    varies = _varies(route_values, cell, tolerance)
    split = frozenset(int(index) for index in varies.index[varies])
    spread = RouteValueSpread(
        cells=int(len(distinct)),
        split=int(distinct.gt(1).sum()),
        route_cells=int(cell.nunique()),
        route_split=len(split),
    )
    return spread, RouteCells(frame=route, cell=cell, values=route_values, split=split)


def split_route_cells(
    cells: RouteCells,
    attributes: Sequence[str] = WAFER_ROUTE_ATTRIBUTES,
    *,
    tolerance: float = ROUTE_SPLIT_TOLERANCE,
) -> tuple[SplitCount, ...]:
    """갈리는 칸마다 그 속성 값 안에서 경로 값이 한 값인지 센다(`SplitCount` 와 같은 세 칸).

    `splits` — 칸 안에서 속성 값마다 한 값이다. `trivial` — 그렇지만 속성 값이 행마다 달라 저절로
    그렇게 된 것이라 증거가 못 된다. `fails` — 한 속성 값 안에서도 갈린다.
    """
    rows = cells.split_rows()
    frame = cells.frame.loc[rows]
    cell = cells.cell.loc[rows]
    values = cells.values.loc[rows]
    results: list[SplitCount] = []
    for attribute in attributes:
        if attribute not in frame.columns:
            continue
        pair = pd.DataFrame(
            {"칸": cell.to_numpy(), "값": _match_column(frame, attribute).to_numpy()},
            index=frame.index,
        )
        sub_cell = pair.groupby(["칸", "값"], sort=False).ngroup()
        owner = pair["칸"].groupby(sub_cell).first()
        pure = (~_varies(values, sub_cell, tolerance)).groupby(owner).all()
        distinct = pair.groupby("칸")["값"].nunique().reindex(pure.index)
        size = pair.groupby("칸").size().reindex(pure.index)
        trivial = pure & distinct.eq(size)
        results.append(
            SplitCount(
                attribute=attribute,
                splits=int((pure & ~trivial).sum()),
                fails=int((~pure).sum()),
                trivial=int(trivial.sum()),
            )
        )
    return tuple(results)


@dataclass(frozen=True)
class FactorFold:
    """갈리는 칸이 후보를 나누거나 곱하면 한 값이 되는가. 값은 담지 않는다.

    `testable` — 갈리는 칸 가운데 모든 행에 후보 값(양수)이 있는 칸. `constant` — 그 가운데
    후보가 칸 안에서 한 값이라 후보로는 가를 수 없는 칸. `divided` 가 `testable − constant` 에
    가까우면 원천 경로 값 = 계획 줄 값 × 후보다(후보의 단위·배율과 무관 — 칸 안의 비만 본다).
    """

    label: str
    testable: int
    constant: int
    divided: int
    multiplied: int


def fold_route_cells(
    cells: RouteCells,
    factor: pd.Series,
    *,
    label: str,
    tolerance: float = ROUTE_SPLIT_TOLERANCE,
) -> FactorFold:
    """`factor` 는 `cells.frame` 과 같은 인덱스의 후보 값이다(`route_factor_values`)."""
    rows = cells.split_rows()
    cell = cells.cell.loc[rows]
    values = cells.values.loc[rows]
    candidate = factor.reindex(cell.index).astype("float64")
    complete = candidate.gt(0).groupby(cell).all()
    testable = cell.isin(set(complete.index[complete]))
    cell = cell.loc[testable]
    values = values.loc[testable]
    candidate = candidate.loc[testable]
    return FactorFold(
        label=label,
        testable=int(cell.nunique()),
        constant=int((~_varies(candidate, cell, tolerance)).sum()),
        divided=int((~_varies(values / candidate, cell, tolerance)).sum()),
        multiplied=int((~_varies(values * candidate, cell, tolerance)).sum()),
    )


@dataclass(frozen=True)
class AddendFold:
    """같은 단위 칸(`TEST WF수(매)`)을 빼거나 더하면 갈리는 칸이 한 값이 되는가."""

    testable: int
    subtracted: int
    added: int


def fold_route_addend(
    cells: RouteCells, column: str = WAFER_ROUTE_ADDEND, *, tolerance: float = ROUTE_SPLIT_TOLERANCE
) -> AddendFold:
    """모든 행에 그 칸 값(0 포함)이 있는 갈리는 칸만 본다. 칸이 없으면 모두 0 이다."""
    if column not in cells.frame.columns:
        return AddendFold(testable=0, subtracted=0, added=0)
    rows = cells.split_rows()
    cell = cells.cell.loc[rows]
    values = cells.values.loc[rows]
    addend = pd.to_numeric(cells.frame.loc[rows, column], errors="coerce").astype("float64")
    complete = addend.notna().groupby(cell).all()
    testable = cell.isin(set(complete.index[complete]))
    cell = cell.loc[testable]
    return AddendFold(
        testable=int(cell.nunique()),
        subtracted=int(
            (~_varies(values.loc[testable] - addend.loc[testable], cell, tolerance)).sum()
        ),
        added=int((~_varies(values.loc[testable] + addend.loc[testable], cell, tolerance)).sum()),
    )


def measured_wafer_load(required: pd.DataFrame, tables: dict[str, pd.DataFrame]) -> pd.Series:
    """`부하량 × Lot 측정률 × WF측정률` — 소요대수가 실제로 나누는 부하.

    측정률은 부하가 아니라 대당 Capa 의 분모로 들지만, 곱으로 옮기면 이 값이 된다.

    측정률이 비었거나 0 이면 계산과 같이 1.0 이다. 음수 행은 계산이 이미 뺐다.
    """
    measured = [item for item in FORMULA_INPUTS if item.label in {"Lot 측정률", "WF측정률"}]
    inputs = attach_formula_inputs(required, required, tables, measured)
    load = pd.to_numeric(required["부하량"], errors="coerce").astype("float64")
    for item in measured:
        ratio = pd.to_numeric(inputs[item.label], errors="coerce").astype("float64")
        load = load * ratio.where(ratio.gt(0), 1.0)
    return load


@dataclass(frozen=True)
class FactorAgreement:
    """경로 키마다 기존 ÷ 신규가 후보를 따라가는가. 값은 담지 않는다.

    `keys` — 비율과 후보 값(양수)이 다 있는 키. `off_one` — 그 가운데 후보가 1 이 아닌 키(1 인 키는
    따라가는지 가를 수 없다). 그 키들을 기존 ÷ 신규가 후보(`near_factor`)·1 ÷ 후보(`near_inverse`)·1
    (`near_one` — 후보와 무관)에 붙는지 센다. 셋 모두 `tolerance` 안이다.
    """

    label: str
    keys: int
    off_one: int
    near_factor: int
    near_inverse: int
    near_one: int


def factor_agreement(
    frame: pd.DataFrame,
    factor: pd.Series,
    *,
    label: str,
    tolerance: float = TIGHT_TOLERANCE,
) -> FactorAgreement:
    """`frame` 은 `ratio_groups(...).frame`(비율 칸이 있다), `factor` 는 같은 인덱스의 키별
    후보 값이다."""
    ratio = pd.to_numeric(frame[RATIO_COLUMN], errors="coerce").astype("float64")
    candidate = factor.reindex(frame.index).astype("float64")
    usable = ratio.gt(0) & candidate.gt(0)
    off = usable & ~_near(candidate, 1.0, tolerance)
    return FactorAgreement(
        label=label,
        keys=int(usable.sum()),
        off_one=int(off.sum()),
        near_factor=int((off & _near(ratio / candidate, 1.0, tolerance)).sum()),
        near_inverse=int((off & _near(ratio * candidate, 1.0, tolerance)).sum()),
        near_one=int((off & _near(ratio, 1.0, tolerance)).sum()),
    )


def route_factor_by_key(link: RouteLink, factor: RouteFactor) -> pd.Series:
    """키마다 후보 값 — 짝지은 원천 경로 행의 후보 값 중앙(`RouteLink.numbers` 와 같은 규칙)."""
    column = "_후보"
    route = link.route.assign(**{column: route_factor_values(link.route, factor)})
    return RouteLink(frame=link.frame, route=route, pairs=link.pairs).numbers(column)


def _near(values: pd.Series, target: float, tolerance: float) -> pd.Series:
    return ((values / target) - 1.0).abs().le(tolerance).fillna(False).astype(bool)


def _match_column(frame: pd.DataFrame, column: str) -> pd.Series:
    """맞대기 전용 값 — 월은 정수, 소요기준은 `normalize_demand_basis` 를 거쳐 `match_key`."""
    values = frame[column]
    if column == "생산계획년월":
        values = pd.to_numeric(values, errors="coerce").astype("Int64")
    elif column == "소요기준":
        values = normalize_demand_basis(values)
    return match_key(values)


def _key_ids(frame: pd.DataFrame, keys: Sequence[str]) -> pd.Series:
    """`keys` 조합마다 번호 하나. 인자 값 하나를 같이 쓰는 키는 같은 번호다."""
    key_list = list(keys)
    matched = pd.DataFrame({key: _match_column(frame, key) for key in key_list})
    return matched.groupby(key_list, sort=False, dropna=False).ngroup()


def _lookup(
    target: pd.DataFrame, source: pd.DataFrame, keys: Sequence[str], column: str
) -> pd.Series:
    """`source` 의 `column` 을 `keys` 로 `target` 행마다 읽는다. 키가 겹치면 첫 값이다."""
    key_list = list(keys)
    left = pd.DataFrame({key: _match_column(target, key) for key in key_list})
    right = pd.DataFrame({key: _match_column(source, key) for key in key_list})
    right["_값"] = pd.to_numeric(source[column], errors="coerce").to_numpy(dtype="float64")
    folded = right.groupby(key_list, sort=False, dropna=False)["_값"].first().reset_index()
    merged = left.merge(folded, on=key_list, how="left", validate="many_to_one")
    return pd.Series(merged["_값"].to_numpy(dtype="float64"), index=target.index)
