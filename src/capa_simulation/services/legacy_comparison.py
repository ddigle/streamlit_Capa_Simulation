# Purpose: 원천 Core Data 에 남아 있는 기존 결과와 신규 계산값을 같은 키로 대조한다.

"""기존 앱이 계산해 원천에 실어 보낸 값과 이 앱의 계산값을 맞춰 본다.

신규 계산을 실제 업무 판단에 쓰기 전 마지막 관문이다. 별도 테이블을 만들 필요가 없다 —
`raw_data.core_data` 에 기존 결과 컬럼이 그대로 보존돼 있다.

**지금 대조할 수 있는 것은 두 개뿐이다.**

| 기존 컬럼 | 신규 계산 | 단위 |
|---|---|---|
| `WF수(매)` | `calculate_wafer_load` 의 물량 | 매 |
| `EQ(억Gb)` | `calculate_density_load` 의 물량 | 억Gb |

`소요대수` 는 원천 46,500행이 전부 NULL 이고 `PCB수(K매)` 는 124행에 상수 하나뿐이라
역산도 대조도 불가능하다. 값이 채워진 Core Data 를 다시 받아야 한다.
`Plan_Chip(K개)`·`GOOD_DIE` 는 이 앱의 Chip 부하량과 단위·정의가 같다는 근거가 아직
없어서 넣지 않았다 — 확인되면 `COMPARISONS` 에 한 줄 추가하면 된다.

**두 쪽의 집계 방식이 다르다.** 원천은 경로(공정·STEP·MCP)별로 행이 펼쳐져 있고 기존
결과 컬럼은 그 행마다 **같은 값이 반복**된다. 실측하면 키 하나에 31행, 서로 다른 값은 1개다.
그래서 기존 쪽은 **키별 대표값 하나**를 집고, 신규 쪽은 합계를 낸다. 기존 쪽을 합산하면
경로 수만큼 뻥튀기되어 차이율이 30/31 로 나온다 — 실제로 처음에 그렇게 나왔다.

키 안에 서로 다른 기존 값이 있으면 대표값을 고를 수 없으므로 결측으로 두고 `값 불일치`
로 따로 센다. 조용히 하나를 고르면 대조 자체가 거짓말이 된다.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

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
]

# 차이율이 이 값을 넘으면 그냥 반올림 오차가 아니다. 임의 기준이 아니라 "눈으로 확인이
# 필요한 선" 을 하나 정해 둔 것이며, 화면·스크립트가 이 값을 바꿔 넘길 수 있다.
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


def compare_metric(
    core: pd.DataFrame,
    calculated: pd.DataFrame,
    metric: LegacyMetric,
) -> pd.DataFrame:
    """기존 컬럼과 신규 계산을 키 단위 합계로 맞춰 본다.

    한쪽에만 있는 키도 결과에 남긴다. 빠진 쪽은 0 이 아니라 결측으로 두어 "값이 0" 과
    "그 키가 없음" 을 구분한다.
    """
    require_columns(core, [*COMPARISON_KEYS, metric.legacy_column], "Core Data")
    require_columns(calculated, [*COMPARISON_KEYS, metric.new_column], "신규 계산")

    legacy = _representative(core, metric.legacy_column, "기존값")
    fresh = _summed(calculated, metric.new_column, "신규값")
    merged = legacy.merge(fresh, on=COMPARISON_KEYS, how="outer", validate="one_to_one")

    merged["지표"] = metric.label
    merged["차이"] = merged["신규값"] - merged["기존값"]
    # 기존값이 0 이면 비율이 무한대가 된다. 절대 차이만 남기고 비율은 비운다.
    denominator = merged["기존값"].abs()
    merged["차이율"] = (merged["차이"].abs() / denominator).where(denominator.gt(0))
    return merged.loc[:, COMPARISON_COLUMNS].sort_values(
        ["지표", *COMPARISON_KEYS], ignore_index=True
    )


def summarize_comparison(
    comparison: pd.DataFrame,
    tolerance: float = DEFAULT_TOLERANCE,
) -> dict[str, object]:
    """지표별로 "몇 건 중 몇 건이 어긋나는가" 를 센다.

    한쪽에만 있는 키는 `한쪽만 있음` 으로 따로 센다. 차이가 아니라 연결 실패이므로
    같은 통에 넣으면 원인을 못 찾는다.
    """
    if comparison.empty:
        return {
            "대조 건수": 0,
            "허용 초과": 0,
            "신규에만 있음": 0,
            "기존에만 있음": 0,
            "최대 차이율": None,
        }
    legacy_missing = comparison["기존값"].isna()
    fresh_missing = comparison["신규값"].isna()
    matched = comparison.loc[~legacy_missing & ~fresh_missing]
    exceeded = matched.loc[matched["차이율"].fillna(0.0).gt(tolerance)]
    return {
        "대조 건수": int(len(matched)),
        "허용 초과": int(len(exceeded)),
        # 기존이 비워 둔 자리를 신규가 채우는 것은 안전한 방향이다.
        "신규에만 있음": int((legacy_missing & ~fresh_missing).sum()),
        # 신규가 놓친 자리다. 이쪽이 0 이 아니면 계산이 빠뜨린 것이 있다는 뜻이다.
        "기존에만 있음": int((fresh_missing & ~legacy_missing).sum()),
        "최대 차이율": (None if matched.empty else float(matched["차이율"].fillna(0.0).max())),
    }


def _summed(frame: pd.DataFrame, value_column: str, output_name: str) -> pd.DataFrame:
    """신규 계산 쪽. 키 하나에 여러 행이 나올 수 있으므로 더한다."""
    prepared = _normalized(frame, value_column)
    grouped = prepared.groupby(COMPARISON_KEYS, as_index=False, dropna=False)[[value_column]].sum()
    grouped.columns = [*COMPARISON_KEYS, output_name]
    return grouped


def _representative(frame: pd.DataFrame, value_column: str, output_name: str) -> pd.DataFrame:
    """기존 결과 쪽. 경로 행마다 같은 값이 반복되므로 **대표값 하나**를 집는다.

    키 안에 서로 다른 값이 있으면 대표값을 고를 수 없다. 그때는 결측으로 두어 아래
    요약이 `값 불일치` 로 세게 한다. 조용히 첫 값을 고르면 대조가 거짓말이 된다.
    """
    prepared = _normalized(frame, value_column)
    grouped = prepared.groupby(COMPARISON_KEYS, as_index=False, dropna=False).agg(
        **{
            output_name: pd.NamedAgg(column=value_column, aggfunc="max"),
            "_고유값수": pd.NamedAgg(column=value_column, aggfunc="nunique"),
        }
    )
    grouped.loc[grouped["_고유값수"].gt(1), output_name] = pd.NA
    return grouped.drop(columns=["_고유값수"])


def _normalized(frame: pd.DataFrame, value_column: str) -> pd.DataFrame:
    prepared = frame.loc[:, [*COMPARISON_KEYS, value_column]].copy()
    for key in COMPARISON_KEYS:
        if key != "생산계획년월":
            prepared[key] = prepared[key].astype("string").str.strip()
    prepared["생산계획년월"] = pd.to_numeric(prepared["생산계획년월"], errors="coerce").astype(
        "Int64"
    )
    prepared[value_column] = pd.to_numeric(prepared[value_column], errors="coerce")
    return prepared.dropna(subset=[value_column])
