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

**대조 대상은 지금 두 개뿐이다.**

| 기존 컬럼 | 신규 계산 | 단위 |
|---|---|---|
| `WF수(매)` | `calculate_wafer_load` 의 물량 | 매 |
| `EQ(억Gb)` | `calculate_density_load` 의 물량 | 억Gb |

`소요대수`·`PCB수(K매)`·`Plan_Chip(K개)`·`GOOD_DIE` 를 넣지 않은 것은 **업무 사실이 아니라
지금 손에 있는 합성 샘플의 사정** 때문이다. 로컬 샘플은 `scripts/generate_sample_core_data.py`
가 만든 것이라 `소요대수` 를 아예 채우지 않는다. 실데이터에는 값이 있을 수 있으므로
`scripts/compare_legacy_results.py` 가 매 실행마다 후보 컬럼의 채움 상태를 찍어, 쓸 수 있게
되면 사람이 아니라 실행 결과가 알려 주게 해 두었다.

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
from capa_simulation.services.frame_contracts import require_columns

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
    """대조할 지표 하나. 기존 컬럼과 신규 계산 결과를 같은 단위로 맞춰 둔다."""

    label: str
    legacy_column: str
    new_column: str = "물량"


COMPARISONS: tuple[LegacyMetric, ...] = (
    LegacyMetric(label="Wafer 부하량 (매)", legacy_column="WF수(매)"),
    LegacyMetric(label="Density (억Gb)", legacy_column="EQ(억Gb)"),
)


def legacy_grain(contract: CoreDataContract) -> list[str]:
    """기존 결과 값이 한 번만 기록되는 단위.

    계획 한 줄(`RQ_PKG_PLAN` 업무 키)에 `WF 구분` 을 더한 것이다. 업무 키를 계약에서
    읽으므로 키가 늘면(예: `Pack Code` 승격) 대조도 따라 움직인다.
    """
    return [*contract.derived_keys["RQ_PKG_PLAN"], "WF 구분"]


def compare_metric(
    core: pd.DataFrame,
    calculated: pd.DataFrame,
    metric: LegacyMetric,
    contract: CoreDataContract | None = None,
    *,
    keys: Sequence[str] = tuple(COMPARISON_KEYS),
    grain: Sequence[str] | None = None,
) -> pd.DataFrame:
    """기존 컬럼과 신규 계산을 대조 키 단위 합계로 맞춰 본다.

    `core` 는 `build_q_core_data` 를 거친 **파생 프레임**이어야 한다. 업무 키의 `양산구분`
    이 그 단계에서 만들어지므로 원시 프레임을 넘기면 `require_columns` 가 막는다.

    한쪽에만 있는 키도 결과에 남긴다. 빠진 쪽은 0 이 아니라 결측으로 두어 "값이 0" 과
    "그 키가 없음" 을 구분한다.

    `keys` 는 양쪽을 잇는 대조 키, `grain` 은 기존 값이 한 번만 기록되는 단위다(기본은
    `legacy_grain`). 기존 쪽은 `grain` 안의 반복을 접은 뒤 `keys` 로 더하므로 `keys` 는
    `grain` 안에 있어야 한다. 결과의 앞 칸은 `keys` 차례 그대로다.
    """
    selected = contract or load_core_data_contract()
    key_list = list(dict.fromkeys(keys))
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
