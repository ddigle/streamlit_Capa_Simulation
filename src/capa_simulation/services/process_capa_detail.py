# Purpose: 공정 하나의 월별 공식 요약·제품별 소요대수·고른 달의 경로 인자를 계산 결과에서 꺼낸다.

"""공정 Capa 상세 — 공정 하나를 공식 기준(Core Data · 대수)으로 펼쳐 보는 순수 계산.

계산을 새로 하지 않는다. 이미 계산된 결과(확보율·소요대수 상세·대당 Capa)와 기준정보 표를 **공정
하나로 거르고** 화면이 읽을 꼴로 묶을 뿐이다. 그래서 여기 숫자는 산출 결과·Static Capa 와 같다.

- **월별 요약**(`build_process_capa_summary`): 총보유·대여·가용·소요·확보율과 그 달 확보기준에 대한
  판정·부호 있는 과부족·부족 원인. 판정·과부족은 판정 기준에 닿으므로 캐시하지 않고 회차마다 만든다.
- **제품별 소요대수**(`build_process_product_demand`): 소요대수 상세를 분류(제품정보 등)로 합한
  월 표. 자식 행을 다 더하면 요약의 소요대수와 같다.
- **HOME 표시 확보율**(`home_display_rates`): HOME 이 원 확보율에 얹는 실행 Capa·선행 B/O 를 같은
  함수로 얹은 값. 요약 표의 회색 참고 줄이다.
- **고른 달의 경로 추적**(`build_process_month_trace`): 경로마다 부하량·UPEH/ST·환산 UPEH·측정률·
  대당 Capa·소요대수와 그 달 공정 공통 인자. 인자는 공정으로 거른 기준정보 표를 대당 Capa 계산과
  **같은 키**로 붙여 꺼낸다 — `unit_capacity` 는 고치지 않는다. 그래서 대당 Capa 식이 바뀌면
  `route_factor_product` 도 함께 고쳐야 하고, 시험(경로 인자의 곱 = 대당 Capa)이 그 어긋남을 잡는다.

공정을 고를 때는 계산과 같은 정규화(앞뒤 공백 떼기)를 지난 값으로 맞댄다.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from typing import Final, NamedTuple

import pandas as pd

from capa_simulation.services.advance_load import apply_advance_to_securement
from capa_simulation.services.display_order import DisplayOrderInput, apply_display_order
from capa_simulation.services.display_order_scopes import PAGE_CALCULATION, TAB_REQUIRED
from capa_simulation.services.execution_capacity import apply_execution_adjustment
from capa_simulation.services.frame_contracts import (
    DEMAND_BASES,
    normalize_demand_basis,
    require_columns,
)
from capa_simulation.services.required_equipment import (
    PKG_UNCOUNTED_REASON,
    REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR,
)
from capa_simulation.services.securement_rate import (
    BALANCE_COLUMN,
    CAUSE_COLUMN,
    CAUSE_OWNED_SHORT,
    CAUSE_RENTAL,
    OWNED_COLUMN,
    STATUS_COLUMN,
    WARNING_NEED_COLUMN,
    securement_balance,
)
from capa_simulation.services.securement_threshold import SecurementThresholds
from capa_simulation.services.unit_capacity import (
    CAPACITY_EXCLUSIONS_ATTR,
    MEASUREMENT_RATIO_ZERO_DEFAULT,
    PERFORMANCE_KEYS,
)
from capa_simulation.services.weighted_unit_capacity import DEMAND_ID_COLUMNS

MONTH = "생산계획년월"

# ------------------------------------------------------------------ 월별 요약
LENT_COLUMN: Final = "대여대수"
# 총보유 − 대여 − 가용이 0 이 아닌 달. 가용은 원천에서 `설비보유 − 설비대여평가` 로 파생되므로
# 어긋나면 표를 손으로 고쳤거나 파생이 바뀐 것이다 — 화면이 ⚠ 로 알린다.
MISMATCH_COLUMN: Final = "가용 불일치"
AVAILABILITY_TOLERANCE: Final = 1e-9
# 부족 원인의 셋째 값. 가용이 `총보유 − 대여` 와 어긋난 달에서, 총보유 − 대여로는 확보인데 가용이
# 모자라면 대여 탓이 아니다 — 표가 따로 고쳐진 탓이다(기준정보 화면이 셋을 따로 편집한다).
CAUSE_AVAILABILITY_MISMATCH: Final = "가용 불일치"
SUMMARY_COLUMNS: Final = [
    MONTH,
    "공정",
    OWNED_COLUMN,
    LENT_COLUMN,
    "가용대수",
    "소요대수",
    "확보율",
    "확보기준",
    "경고기준",
    STATUS_COLUMN,
    BALANCE_COLUMN,
    WARNING_NEED_COLUMN,
    CAUSE_COLUMN,
    MISMATCH_COLUMN,
]

# ------------------------------------------------------------------ 제품별 소요대수
# 분류 이름 → 합할 컬럼. 화면의 「분류」 선택지가 이 차례 그대로다.
PRODUCT_DEMAND_SPLITS: Final[dict[str, tuple[str, ...]]] = {
    "제품정보": ("제품정보",),
    "양산구분·제품": ("양산구분", "제품정보"),
    "Stack": ("Stack",),
    "WF 구분": ("WF 구분",),
    "소요기준": ("소요기준",),
}
DEFAULT_PRODUCT_SPLIT: Final = "제품정보"
PRODUCT_ROW_LIMIT: Final = 12
PRODUCT_LABEL_COLUMN: Final = "분류"
OTHER_ROW_COLUMN: Final = "그 밖"
GROUPED_COUNT_COLUMN: Final = "묶은 수"
OTHER_LABEL_SEPARATOR: Final = " · "
# 거르기 밖 소요가 든 「그 밖」 행의 꼬리말과, 위에 안 보이는 분류값이 없을 때의 이름.
OTHER_FILTERED_SUFFIX: Final = " (거르기 밖 포함)"
FILTERED_OUT_LABEL: Final = "거르기 밖"

# ------------------------------------------------------------------ 경로 추적
ROUTE_KEYS: Final = [
    "Area_Name",
    "STEP_SEQ",
    "MCP_SEQ",
    "양산구분",
    "제품정보",
    "Stack",
    "WF 구분",
    "소요기준",
]
REQB_ROW_COUNT_COLUMN: Final = "REQB 행 수"
RATIO_BASIS_SUFFIX: Final = " 근거"
# 측정률이 1.0 인 두 꼴. 행이 없어 이어 간 가정(`unit_capacity` 의 assumed)과, 행은 있으나 빈칸·0
# 이라 1.0 을 쓴 것(`MEASUREMENT_RATIO_ZERO_DEFAULT`)은 뜻이 다르다 — 앞의 것은 기준정보 누락이다.
RATIO_ASSUMED_MISSING_ROW: Final = "행 없음 → 1.0 가정"
RATIO_BLANK_OR_ZERO: Final = "빈칸·0 → 1.0"
RATIO_COLUMNS: Final = (("Lot 측정률", "RQ_LOT_RATIO"), ("WF측정률", "RQ_WF_RATIO"))
# 측정률을 잇는 키 — 대당 Capa 계산의 `PERFORMANCE_KEYS` 에서 이미 거른 달·공정을 뺀 것이다.
RATIO_ROUTE_KEYS: Final = tuple(key for key in PERFORMANCE_KEYS if key not in (MONTH, "공정"))
ROUTE_COLUMNS: Final = [
    *ROUTE_KEYS,
    REQB_ROW_COUNT_COLUMN,
    "부하량",
    "UPEH",
    "ST",
    "환산_UPEH",
    "CAPA_RUN_RATE",
    "편중률",
    "모듈수",
    "RUN_DAY",
    "Lot 측정률",
    f"Lot 측정률{RATIO_BASIS_SUFFIX}",
    "WF측정률",
    f"WF측정률{RATIO_BASIS_SUFFIX}",
    "대당 Capa",
    "소요대수",
]
EXCLUSION_REASON_COLUMN: Final = "제외사유"
# 규칙상 빠진 경로(계산 규칙이 일부러 세지 않는 행). 오류 제외와 섞어 세면 정상 공정도 늘 「제외
# 경로 n」을 띄운다 — 근거 요약은 둘을 따로 센다.
RULE_EXCLUSION_REASONS: Final = (PKG_UNCOUNTED_REASON,)
RULE_EXCLUDED_COLUMN: Final = "규칙상 제외"
MISSING_CAPACITY_REASON: Final = "대당 Capa 없음"
TOP_PRODUCT_LIMIT: Final = 5
SHARE_COLUMN: Final = "비중"
_AREA_KEYS: Final = {"main": "Main", "mi": "MI"}


def month_column(month: int) -> str:
    """제품별 소요대수 표의 월 컬럼 이름. 월 표 관례대로 `YYYYMM` 글자다."""
    return str(int(month))


# ================================================================== 월별 요약


def build_process_capa_summary(
    securement_rate: pd.DataFrame,
    owned_equipment: pd.DataFrame,
    lent_equipment: pd.DataFrame,
    *,
    process: str,
    months: Sequence[int],
    thresholds: SecurementThresholds,
) -> pd.DataFrame:
    """공정 하나의 월별 공식 요약. `months` 의 달마다 한 행이고 차례도 그대로다.

    - `securement_rate` 는 `calculate_securement_rate` 결과(시나리오 표 기준)다. 가용대수·소요대수·
      확보율이 그 값 그대로다 — 산출 결과·Static Capa 와 같은 숫자다.
    - `owned_equipment`·`lent_equipment` 는 `RQ_EQP_OWN`(`설비보유`)·`RQ_EQP_LENT`(`설비대여평가`)
      다. (달, 공정)으로 합하고, 행이 없거나 빈칸인 달은 0 대다(`equipment_count` 의 「빈칸 = 0 대」
      와 같은 규칙).
    - 확보율·가용 행이 없는 달은 가용·소요 0 이다(확보율 없음, 판정 없음). 소요가 있는데 가용 행이
      없으면 `calculate_securement_rate` 가 이미 멈췄다.
    - 판정·과부족·부족 원인은 `securement_balance` 한 길이다(그 달 확보기준 = `for_month`).
    - 다만 `가용 불일치` 인 달에서 「대여 영향」은 다시 가른다. 총보유 − 대여로 판정해도 확보면
      대여는 부족의 까닭이 아니므로 「가용 불일치」(`CAUSE_AVAILABILITY_MISMATCH`)로 둔다 — 대여
      0 인데 가용만 낮춘 달이 그렇다. 총보유 − 대여로도 확보가 아니면 「대여 영향」 그대로다.
    """
    require_columns(securement_rate, [MONTH, "공정", "가용대수", "소요대수"], "확보율")
    key = process.strip()
    ordered = _ordered_months(months)
    rate_rows = securement_rate.loc[_process_mask(securement_rate["공정"], key)]
    available = _monthly_sum(rate_rows, "가용대수")
    demand = _monthly_sum(rate_rows, "소요대수")
    owned = _monthly_equipment(owned_equipment, "설비보유", key, "RQ_EQP_OWN")
    lent = _monthly_equipment(lent_equipment, "설비대여평가", key, "RQ_EQP_LENT")

    frame = pd.DataFrame(
        {
            MONTH: pd.Series(ordered, dtype="int64"),
            "공정": pd.Series([key] * len(ordered), dtype="object"),
            OWNED_COLUMN: pd.Series([owned.get(m, 0.0) for m in ordered], dtype="float64"),
            "가용대수": pd.Series([available.get(m, 0.0) for m in ordered], dtype="float64"),
            "소요대수": pd.Series([demand.get(m, 0.0) for m in ordered], dtype="float64"),
        }
    )
    if frame.empty:
        return _empty_summary()
    result = securement_balance(frame, thresholds=thresholds)
    result[LENT_COLUMN] = pd.Series([lent.get(m, 0.0) for m in ordered], dtype="float64")
    residual = result[OWNED_COLUMN].sub(result[LENT_COLUMN]).sub(result["가용대수"])
    result[MISMATCH_COLUMN] = residual.abs().gt(AVAILABILITY_TOLERANCE)
    result[CAUSE_COLUMN] = [
        CAUSE_AVAILABILITY_MISMATCH
        if cause == CAUSE_RENTAL
        and mismatch
        and thresholds.status((owned_count - lent_count) / demand_count, int(month)) == "secure"
        else cause
        for cause, mismatch, owned_count, lent_count, demand_count, month in zip(
            result[CAUSE_COLUMN],
            result[MISMATCH_COLUMN],
            result[OWNED_COLUMN],
            result[LENT_COLUMN],
            result["소요대수"],
            result[MONTH],
            strict=True,
        )
    ]
    return result[SUMMARY_COLUMNS]


class ProcessCapaKpis(NamedTuple):
    """요약 표에서 바로 읽는 머리 지표. 기간 합은 쓰지 않는다(동일 설비의 기간 중복)."""

    lowest_rate: float | None
    lowest_rate_month: int | None
    shortage_months: int
    max_shortage: int
    owned_short_months: int
    rental_months: int
    mismatch_months: int


def process_capa_kpis(summary: pd.DataFrame) -> ProcessCapaKpis:
    """최저 확보율과 그 달, 확보기준 미달 달 수·월 최대 부족 대수, 부족 원인별 달 수.

    원인별 달 수(보유로도 부족·대여 영향·가용 불일치)를 더하면 미달 달 수다.

    미달 달은 판정이 확보가 아닌 달이다(Static Capa 와 같은 정의). 월 최대 부족은 과부족 음수 크기의
    최댓값이다 — 잡음 경계 달은 미달로 세되 크기는 0 이다.
    """
    require_columns(summary, [MONTH, "확보율", STATUS_COLUMN, BALANCE_COLUMN, CAUSE_COLUMN], "요약")
    rates = pd.to_numeric(summary["확보율"], errors="coerce")
    lowest_rate: float | None = None
    lowest_month: int | None = None
    if rates.notna().any():
        position = int(rates.reset_index(drop=True).idxmin())
        lowest_rate = float(rates.iloc[position])
        lowest_month = int(summary[MONTH].iloc[position])
    short = summary[STATUS_COLUMN].isin(["warning", "shortage"])
    balances = pd.to_numeric(summary.loc[short, BALANCE_COLUMN], errors="coerce").fillna(0)
    return ProcessCapaKpis(
        lowest_rate=lowest_rate,
        lowest_rate_month=lowest_month,
        shortage_months=int(short.sum()),
        max_shortage=int(max(0, -int(balances.min()))) if not balances.empty else 0,
        owned_short_months=int(summary[CAUSE_COLUMN].eq(CAUSE_OWNED_SHORT).sum()),
        rental_months=int(summary[CAUSE_COLUMN].eq(CAUSE_RENTAL).sum()),
        mismatch_months=int(summary[CAUSE_COLUMN].eq(CAUSE_AVAILABILITY_MISMATCH).sum()),
    )


def home_display_rates(
    securement_rate: pd.DataFrame,
    *,
    process: str,
    months: Sequence[int],
    execution_rows: pd.DataFrame | None = None,
    advance_ratio: pd.DataFrame | None = None,
) -> dict[int, float | None]:
    """HOME 이 그 공정의 달마다 보이는 확보율 — 요약 표 「확보율 (HOME 표시)」 줄.

    HOME 과 같은 함수·같은 차례다: 원 확보율에 실행 Capa 증감(%p)을 얹고
    (`apply_execution_adjustment`, `execution_rows` 가 None 이면 얹지 않는다) 선행 B/O 변동률을
    곱한다 (`apply_advance_to_securement`, `advance_ratio` 가 None 이면 곱하지 않는다). 달은
    `months` 차례이고 확보율이 없는 달(소요 0)은 None 이다. 공정은 계산과 같은 정규화로 고른다.
    """
    require_columns(securement_rate, [MONTH, "공정", "확보율"], "확보율")
    rows = securement_rate.loc[_process_mask(securement_rate["공정"], process.strip())]
    if execution_rows is not None:
        rows = apply_execution_adjustment(rows, execution_rows)
    if advance_ratio is not None:
        rows = apply_advance_to_securement(rows, advance_ratio)
    found: dict[int, float | None] = {}
    for month, rate in zip(
        pd.to_numeric(rows[MONTH], errors="coerce"),
        pd.to_numeric(rows["확보율"], errors="coerce"),
        strict=True,
    ):
        if pd.isna(month) or int(month) in found:
            continue
        found[int(month)] = None if pd.isna(rate) else float(rate)
    return {int(month): found.get(int(month)) for month in _ordered_months(months)}


def _empty_summary() -> pd.DataFrame:
    return pd.DataFrame({column: pd.Series(dtype="object") for column in SUMMARY_COLUMNS})


def _monthly_sum(rows: pd.DataFrame, value_column: str) -> dict[int, float]:
    months = pd.to_numeric(rows[MONTH], errors="coerce").tolist()
    values = pd.to_numeric(rows[value_column], errors="coerce").fillna(0.0).tolist()
    totals: dict[int, float] = {}
    for month, value in zip(months, values, strict=True):
        if pd.isna(month):
            continue
        totals[int(month)] = totals.get(int(month), 0.0) + float(value)
    return totals


def _monthly_equipment(
    frame: pd.DataFrame, value_column: str, process: str, label: str
) -> dict[int, float]:
    require_columns(frame, [MONTH, "공정", value_column], label)
    return _monthly_sum(frame.loc[_process_mask(frame["공정"], process)], value_column)


# ================================================================== 공정 하나로 거른 계산 결과


class ProcessCalculationRows(NamedTuple):
    """한 공정의 계산 결과 조각. 시나리오 전체 프레임 대신 이것만 캐시해 풀기 싸게 한다."""

    required_equipment: pd.DataFrame
    unit_capacity: pd.DataFrame
    required_exclusions: pd.DataFrame
    capacity_exclusions: pd.DataFrame


def process_calculation_rows(
    unit_capacity: pd.DataFrame,
    required_equipment: pd.DataFrame,
    *,
    process: str,
) -> ProcessCalculationRows:
    """대당 Capa·소요대수 결과와 두 제외 목록(`attrs`)을 공정 하나로 거른다.

    `attrs` 는 거르기를 지나며 사라지므로 제외 목록은 따로 담는다. 받은 프레임은 고치지 않는다.
    """
    key = process.strip()
    return ProcessCalculationRows(
        required_equipment=_process_rows(required_equipment, key),
        unit_capacity=_process_rows(unit_capacity, key),
        required_exclusions=_process_rows(
            required_equipment.attrs.get(REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR), key
        ),
        capacity_exclusions=_process_rows(unit_capacity.attrs.get(CAPACITY_EXCLUSIONS_ATTR), key),
    )


def _process_rows(frame: object, process: str) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or "공정" not in frame.columns:
        return pd.DataFrame()
    rows = frame.loc[_process_mask(frame["공정"], process)].reset_index(drop=True)
    rows.attrs = {}
    return rows


# ================================================================== 제품별 소요대수


def build_process_product_demand(
    required_equipment: pd.DataFrame,
    *,
    process: str,
    split: str,
    months: Sequence[int],
    display_order: DisplayOrderInput = None,
    products: Collection[str] = (),
    production_classes: Collection[str] = (),
    limit: int = PRODUCT_ROW_LIMIT,
) -> pd.DataFrame:
    """공정 하나의 소요대수를 분류(`PRODUCT_DEMAND_SPLITS`)로 합한 월 표.

    컬럼은 분류 컬럼들 · `분류`(보이는 글자) · `그 밖`(묶음 행인가) · `묶은 수` · 월 컬럼
    (`month_column`, 값 없는 달은 0)이다. **행을 다 더하면 그 공정 소요대수(요약의 부모 행)와 같다**
    — 아무것도 버리지 않고 남는 것은 「그 밖」 한 행에 합친다.

    - 행 차례는 산출 결과 · 소요대수 표시순서(`apply_display_order`)다. 규칙이 없으면 분류값
      오름차순이다.
    - 기간 안 소요가 0 인 분류는 행을 두지 않는다(더해도 0 이라 합은 그대로다).
    - `products`·`production_classes` 로 거르면(비면 거르지 않음) 거른 밖의 소요는 「그 밖」에
      합친다. 거르기와 분류 컬럼이 다르면(제품으로 거르고 Stack 으로 나누면) 거르기 밖 소요가 위에
      보이는 분류값과 같은 값을 실을 수 있다 — 그래서 그때 「그 밖」 이름은 꼬리말
      「(거르기 밖 포함)」을 달고, 위에 안 보이는 분류값이 하나도 없으면 「거르기 밖」이다.
    - 분류가 `limit` 개를 넘으면 기간 소요가 큰 `limit` 개를 남기고(같으면 표시순서 앞쪽) 나머지는
      「그 밖」에 합친다. 남긴 행은 표시순서 그대로다.
    - 「그 밖」 행의 분류 컬럼은 빈 글자, `분류` 는 「그 밖 k개」, `묶은 수` 는 그 행에 묶인 분류값
      가운데 **위에 보이지 않는 것**의 수 k 다(위 행과 겹치는 값은 세지 않는다).
    """
    if split not in PRODUCT_DEMAND_SPLITS:
        raise ValueError(f"지원하지 않는 제품별 소요대수 분류입니다: {split}")
    if limit < 1:
        raise ValueError("제품별 소요대수 행 상한은 1 이상이어야 합니다.")
    dimensions = list(PRODUCT_DEMAND_SPLITS[split])
    ordered = _ordered_months(months)
    month_columns = [month_column(month) for month in ordered]
    filter_columns = ["양산구분", "제품정보"]
    text_columns = list(dict.fromkeys([*dimensions, *filter_columns]))
    needed = list(dict.fromkeys([MONTH, "공정", *text_columns, "소요대수"]))
    require_columns(required_equipment, needed, "소요대수 상세")

    rows = required_equipment.loc[_process_mask(required_equipment["공정"], process), needed].copy()
    rows[MONTH] = pd.to_numeric(rows[MONTH], errors="coerce")
    rows = rows.loc[rows[MONTH].isin(ordered)].copy()
    rows[MONTH] = rows[MONTH].astype("int64")
    for column in text_columns:
        rows[column] = rows[column].astype("string").str.strip().fillna("")
    if "소요기준" in dimensions:
        rows["소요기준"] = normalize_demand_basis(rows["소요기준"]).fillna("")
    rows["소요대수"] = pd.to_numeric(rows["소요대수"], errors="coerce").fillna(0.0)

    selected = _selected(rows["제품정보"], products) & _selected(
        rows["양산구분"], production_classes
    )
    kept = _nonzero(_wide(rows.loc[selected], dimensions, ordered), month_columns)
    filtered_out = _nonzero(_wide(rows.loc[~selected], dimensions, ordered), month_columns)
    kept = apply_display_order(kept, display_order, PAGE_CALCULATION, TAB_REQUIRED).reset_index(
        drop=True
    )

    overflow = kept.iloc[0:0]
    if len(kept) > limit:
        totals = kept[month_columns].sum(axis=1).tolist()
        ranked = sorted(range(len(kept)), key=lambda position: (-totals[position], position))
        shown_positions = sorted(ranked[:limit])
        overflow_positions = sorted(ranked[limit:])
        overflow = kept.iloc[overflow_positions]
        kept = kept.iloc[shown_positions]

    shown = kept.reset_index(drop=True)
    shown[PRODUCT_LABEL_COLUMN] = _labels(shown, dimensions)
    shown[OTHER_ROW_COLUMN] = False
    shown[GROUPED_COUNT_COLUMN] = 1

    merged = [frame for frame in (overflow, filtered_out) if not frame.empty]
    if merged:
        bucket = pd.concat(merged, ignore_index=True)
        visible = set(shown[dimensions].itertuples(index=False, name=None))
        bucket_values = set(bucket[dimensions].itertuples(index=False, name=None))
        count = len(bucket_values - visible)
        other: dict[str, object] = {column: "" for column in dimensions}
        other.update(
            {
                PRODUCT_LABEL_COLUMN: _other_label(count, filtered=not filtered_out.empty),
                OTHER_ROW_COLUMN: True,
                GROUPED_COUNT_COLUMN: count,
            }
        )
        other.update({column: float(bucket[column].sum()) for column in month_columns})
        other_row = pd.DataFrame([other])
        shown = other_row if shown.empty else pd.concat([shown, other_row], ignore_index=True)

    columns = [*dimensions, PRODUCT_LABEL_COLUMN, OTHER_ROW_COLUMN, GROUPED_COUNT_COLUMN]
    result = shown.reindex(columns=[*columns, *month_columns])
    result[OTHER_ROW_COLUMN] = result[OTHER_ROW_COLUMN].astype("bool")
    result[GROUPED_COUNT_COLUMN] = result[GROUPED_COUNT_COLUMN].astype("int64")
    for column in month_columns:
        result[column] = result[column].astype("float64")
    return result


def _other_label(count: int, *, filtered: bool) -> str:
    """「그 밖」 행 이름. 거르기 밖 소요가 들었으면 꼬리말을 달고, 안 보이는 분류값이 없으면
    「거르기 밖」이다."""
    if not filtered:
        return f"그 밖 {count}개"
    if count == 0:
        return FILTERED_OUT_LABEL
    return f"그 밖 {count}개{OTHER_FILTERED_SUFFIX}"


def _selected(values: pd.Series, allowed: Collection[str]) -> pd.Series:
    if not allowed:
        return pd.Series(True, index=values.index, dtype="bool")
    wanted = {str(value).strip() for value in allowed}
    return values.isin(wanted).astype("bool")


def _wide(rows: pd.DataFrame, dimensions: list[str], months: list[int]) -> pd.DataFrame:
    month_columns = [month_column(month) for month in months]
    if rows.empty:
        empty: dict[str, pd.Series] = {column: pd.Series(dtype="string") for column in dimensions}
        empty.update({column: pd.Series(dtype="float64") for column in month_columns})
        return pd.DataFrame(empty)
    grouped = rows.groupby([*dimensions, MONTH], dropna=False)["소요대수"].sum()
    wide = grouped.unstack(MONTH, fill_value=0).reindex(columns=months, fill_value=0.0)
    wide.columns = pd.Index(month_columns)
    return wide.reset_index()


def _nonzero(frame: pd.DataFrame, month_columns: list[str]) -> pd.DataFrame:
    if frame.empty:
        return frame
    return frame.loc[frame[month_columns].sum(axis=1).gt(0)].reset_index(drop=True)


def _labels(frame: pd.DataFrame, dimensions: list[str]) -> list[str]:
    return [
        OTHER_LABEL_SEPARATOR.join(str(value) for value in values)
        for values in frame[dimensions].itertuples(index=False, name=None)
    ]


# ================================================================== 고른 달의 경로 추적


class CommonFactors(NamedTuple):
    """그 달 그 공정의 공통 인자. 효율·여유율은 양산구분마다, 일수·모듈수는 공정 하나에 하나다."""

    by_class: pd.DataFrame
    run_day: float | None
    module_count: float | None


class MonthEvidence(NamedTuple):
    """근거 패널이 숫자로 적는 짧은 요약.

    `excluded_route_count` 는 오류로 빠진 경로(대당 Capa 없음 등)만, `rule_excluded_route_count` 는
    계산 규칙이 일부러 세지 않은 경로(`RULE_EXCLUSION_REASONS` — PKG 의 Buffer 아닌 행)만 센다.
    """

    route_count: int
    excluded_route_count: int
    rule_excluded_route_count: int
    unique_demand_load: float
    required: float
    effective_capacity: float | None
    product_count: int
    top_products: pd.DataFrame
    assumed_ratio_routes: int
    blank_ratio_routes: int


class ProcessMonthTrace(NamedTuple):
    """고른 달 한 공정의 계산 사슬."""

    process: str
    month: int
    routes: pd.DataFrame
    common_factors: CommonFactors
    excluded: pd.DataFrame
    evidence: MonthEvidence


def build_process_month_trace(
    rows: ProcessCalculationRows,
    capacity_tables: Mapping[str, pd.DataFrame],
    *,
    process: str,
    month: int,
) -> ProcessMonthTrace:
    """고른 달의 경로마다 인자와 소요대수, 공정 공통 인자, 제외 경로, 근거 요약.

    - 경로는 대당 Capa 의 키(`ROUTE_KEYS` — Area·STEP·MCP·양산구분·제품정보·Stack·WF 구분·소요기준)
      다. Capa Code·Customer·CS 가 다른 `RQ_REQB` 행은 한 경로로 합친다 — 부하량·소요대수는 더하고
      대당 Capa 는 같다.
    - 인자는 `capacity_tables`(`CAPACITY_INPUT_TABLES` — 대당 Capa 계산에 넣은 표, `RQ_MODULE` 은
      기준정보 쪽)를 공정·달로 거른 뒤 대당 Capa 계산과 같은 키로 붙인다. 환산 UPEH 는 대당 Capa
      결과에서 받는다.
    - 측정률이 1.0 인 경로는 `… 근거` 칸에 「행 없음 → 1.0 가정」 또는 「빈칸·0 → 1.0」을 적는다.
    - 원수요 부하량은 STEP 이 여럿이어도 한 번만 센다(원수요 키 `DEMAND_ID_COLUMNS` 로 중복을 뺀
      합 — `effective_process_capacity_long` 과 같은 값이되 그 검증을 다시 하지 않는다. 본 계산이
      강제하지 않는 규칙 위반 데이터에서 근거 패널만 멈추지 않게 한다).
    - 제외 경로(`excluded`)에는 오류 제외와 규칙상 제외를 함께 싣고 `규칙상 제외` 칸으로 가른다.
    """
    key = process.strip()
    target = int(month)
    required_rows = _month_rows(_process_rows(rows.required_equipment, key), target)
    routes = _routes(required_rows)
    unit_rows = _month_rows(_process_rows(rows.unit_capacity, key), target)
    routes = _attach_converted_upeh(routes, unit_rows)
    routes = _attach_raw_upeh(routes, _table_rows(capacity_tables, "RQ_UPEH", key, target))
    common = _common_factors(capacity_tables, key, target)
    routes = routes.merge(common.by_class, on="양산구분", how="left")
    routes["모듈수"] = common.module_count if common.module_count is not None else float("nan")
    routes["RUN_DAY"] = common.run_day if common.run_day is not None else float("nan")
    for column, table_name in RATIO_COLUMNS:
        routes = _attach_ratio(
            routes, _table_rows(capacity_tables, table_name, key, target), column
        )
    routes = routes.reindex(columns=ROUTE_COLUMNS)

    excluded = _excluded_routes(
        _month_rows(_process_rows(rows.required_exclusions, key), target),
        _month_rows(_process_rows(rows.capacity_exclusions, key), target),
    )
    evidence = _evidence(required_rows, routes, excluded)
    return ProcessMonthTrace(
        process=key,
        month=target,
        routes=routes,
        common_factors=common,
        excluded=excluded,
        evidence=evidence,
    )


def route_factor_product(routes: pd.DataFrame) -> pd.Series:
    """경로 인자로 대당 Capa 를 다시 곱한다(검산). 식과 곱하는 차례는 `calculate_unit_capacity`
    와 같다.

    `대당 Capa = 환산_UPEH × 24 × CAPA_RUN_RATE ÷ 편중률 × 모듈수 × RUN_DAY ÷ Lot 측정률 ÷ WF측정률`
    """
    return (
        routes["환산_UPEH"]
        * 24.0
        * routes["CAPA_RUN_RATE"]
        / routes["편중률"]
        * routes["모듈수"]
        * routes["RUN_DAY"]
        / routes["Lot 측정률"]
        / routes["WF측정률"]
    )


def _routes(required_rows: pd.DataFrame) -> pd.DataFrame:
    if required_rows.empty:
        return pd.DataFrame(
            {
                **{column: pd.Series(dtype="string") for column in ROUTE_KEYS},
                REQB_ROW_COUNT_COLUMN: pd.Series(dtype="int64"),
                "부하량": pd.Series(dtype="float64"),
                "대당 Capa": pd.Series(dtype="float64"),
                "소요대수": pd.Series(dtype="float64"),
            }
        )
    prepared = _key_frame(required_rows, ROUTE_KEYS)
    for column in ("부하량", "대당 Capa", "소요대수"):
        prepared[column] = _float(prepared[column])
    grouped = prepared.groupby(ROUTE_KEYS, dropna=False, sort=True).agg(
        **{
            REQB_ROW_COUNT_COLUMN: ("소요대수", "size"),
            "부하량": ("부하량", "sum"),
            "대당 Capa": ("대당 Capa", "first"),
            "소요대수": ("소요대수", "sum"),
        }
    )
    return grouped.reset_index()


def _attach_converted_upeh(routes: pd.DataFrame, unit_rows: pd.DataFrame) -> pd.DataFrame:
    if unit_rows.empty or "환산_UPEH" not in unit_rows.columns:
        return routes.assign(환산_UPEH=float("nan"))
    converted = _key_frame(unit_rows, ROUTE_KEYS)[[*ROUTE_KEYS, "환산_UPEH"]]
    converted = converted.drop_duplicates(ROUTE_KEYS)
    return routes.merge(converted, on=ROUTE_KEYS, how="left")


def _attach_raw_upeh(routes: pd.DataFrame, upeh: pd.DataFrame) -> pd.DataFrame:
    if upeh.empty:
        return routes.assign(UPEH=float("nan"), ST=float("nan"))
    raw = _key_frame(upeh, ROUTE_KEYS)
    raw = raw.loc[raw["소요기준"].isin(DEMAND_BASES)]
    raw = raw[[*ROUTE_KEYS, "UPEH", "ST"]].drop_duplicates(ROUTE_KEYS)
    raw["UPEH"] = _float(raw["UPEH"])
    raw["ST"] = _float(raw["ST"])
    return routes.merge(raw, on=ROUTE_KEYS, how="left")


def _common_factors(tables: Mapping[str, pd.DataFrame], process: str, month: int) -> CommonFactors:
    run_rate = _class_values(_table_rows(tables, "RQ_RUN_RATE", process, month), "CAPA_RUN_RATE")
    vital = _class_values(_table_rows(tables, "RQ_VITAL", process, month), "편중률")
    by_class = run_rate.merge(vital, on="양산구분", how="outer").sort_values(
        "양산구분", kind="stable", ignore_index=True
    )
    module = tables.get("RQ_MODULE")
    module_rows = (
        module.loc[_process_mask(module["공정"], process)]
        if isinstance(module, pd.DataFrame) and "공정" in module.columns
        else pd.DataFrame()
    )
    return CommonFactors(
        by_class=by_class,
        run_day=_first_value(_table_rows(tables, "RQ_RUN_DAY", process, month), "RUN_DAY"),
        module_count=_first_value(module_rows, "모듈수"),
    )


def _class_values(rows: pd.DataFrame, value_column: str) -> pd.DataFrame:
    if rows.empty or value_column not in rows.columns:
        return pd.DataFrame(
            {"양산구분": pd.Series(dtype="string"), value_column: pd.Series(dtype="float64")}
        )
    values = _key_frame(rows, ["양산구분"])[["양산구분", value_column]].drop_duplicates("양산구분")
    values[value_column] = _float(values[value_column])
    return values.reset_index(drop=True)


def _first_value(rows: pd.DataFrame, column: str) -> float | None:
    if rows.empty or column not in rows.columns:
        return None
    values = pd.to_numeric(rows[column], errors="coerce").dropna()
    return None if values.empty else float(values.iloc[0])


def _attach_ratio(routes: pd.DataFrame, ratio_rows: pd.DataFrame, column: str) -> pd.DataFrame:
    """측정률을 경로 키(`PERFORMANCE_KEYS`)로 붙이고 1.0 의 꼴을 적는다. 값 규칙은 대당 Capa
    와 같다.

    행이 없으면 1.0(가정), 빈칸·0 이면 1.0, 그 밖은 그 값이다. 음수 경로는 대당 Capa 에서 빠졌으므로
    여기 오지 않는다. 표는 이미 공정·달로 걸렀으므로 그 둘은 키에서 뺀다.
    """
    basis_column = f"{column}{RATIO_BASIS_SUFFIX}"
    if ratio_rows.empty or column not in ratio_rows.columns:
        assumed = routes.copy()
        assumed[column] = MEASUREMENT_RATIO_ZERO_DEFAULT
        assumed[basis_column] = RATIO_ASSUMED_MISSING_ROW
        return assumed
    keys = list(RATIO_ROUTE_KEYS)
    prepared = _key_frame(ratio_rows, keys)[[*keys, column]].drop_duplicates(keys)
    raw = prepared[column]
    blank = raw.isna() | raw.astype("string").str.strip().eq("").fillna(False).astype("bool")
    numeric = _float(raw.mask(blank))
    prepared["_blank_or_zero"] = blank | numeric.eq(0).fillna(False).astype("bool")
    prepared[column] = numeric.mask(prepared["_blank_or_zero"], MEASUREMENT_RATIO_ZERO_DEFAULT)
    prepared["_matched"] = True
    merged = routes.merge(prepared, on=keys, how="left")
    matched = merged["_matched"].eq(True)
    blank_or_zero = merged["_blank_or_zero"].eq(True)
    merged[column] = merged[column].where(matched, MEASUREMENT_RATIO_ZERO_DEFAULT).astype("float64")
    merged[basis_column] = [
        _ratio_basis(is_matched, is_blank)
        for is_matched, is_blank in zip(matched, blank_or_zero, strict=True)
    ]
    return merged.drop(columns=["_blank_or_zero", "_matched"])


def _ratio_basis(matched: bool, blank_or_zero: bool) -> str:
    if not matched:
        return RATIO_ASSUMED_MISSING_ROW
    return RATIO_BLANK_OR_ZERO if blank_or_zero else ""


def _excluded_routes(
    required_exclusions: pd.DataFrame, capacity_exclusions: pd.DataFrame
) -> pd.DataFrame:
    """그 달 계산에서 빠진 `RQ_REQB` 행.

    대당 Capa 가 없던 까닭이 대당 Capa 제외 목록에 있으면 사유에 함께 적는다.
    """
    if required_exclusions.empty:
        return pd.DataFrame(
            {
                **{column: pd.Series(dtype="string") for column in ROUTE_KEYS},
                "부하량": pd.Series(dtype="float64"),
                EXCLUSION_REASON_COLUMN: pd.Series(dtype="object"),
                RULE_EXCLUDED_COLUMN: pd.Series(dtype="bool"),
            }
        )
    detail_columns = [
        column
        for column in ("Capa Code", "Customer", "CS", "부하량", EXCLUSION_REASON_COLUMN)
        if column in required_exclusions.columns
    ]
    excluded = _key_frame(required_exclusions, ROUTE_KEYS)[[*ROUTE_KEYS, *detail_columns]]
    if (
        not capacity_exclusions.empty
        and EXCLUSION_REASON_COLUMN in capacity_exclusions.columns
        and EXCLUSION_REASON_COLUMN in excluded.columns
        and all(column in capacity_exclusions.columns for column in ROUTE_KEYS)
    ):
        reasons = _key_frame(capacity_exclusions, ROUTE_KEYS)[
            [*ROUTE_KEYS, EXCLUSION_REASON_COLUMN]
        ]
        reasons = reasons.drop_duplicates(ROUTE_KEYS).rename(
            columns={EXCLUSION_REASON_COLUMN: "_capacity_reason"}
        )
        excluded = excluded.merge(reasons, on=ROUTE_KEYS, how="left")
        detailed = (
            excluded[EXCLUSION_REASON_COLUMN].eq(MISSING_CAPACITY_REASON)
            & excluded["_capacity_reason"].notna()
        )
        excluded.loc[detailed, EXCLUSION_REASON_COLUMN] = [
            f"{MISSING_CAPACITY_REASON} ({reason})"
            for reason in excluded.loc[detailed, "_capacity_reason"]
        ]
        excluded = excluded.drop(columns="_capacity_reason")
    exclusion_reasons = (
        excluded[EXCLUSION_REASON_COLUMN]
        if EXCLUSION_REASON_COLUMN in excluded.columns
        else pd.Series("", index=excluded.index, dtype="object")
    )
    excluded[RULE_EXCLUDED_COLUMN] = exclusion_reasons.isin(RULE_EXCLUSION_REASONS).astype("bool")
    return excluded.sort_values(ROUTE_KEYS, kind="stable", ignore_index=True)


def _evidence(
    required_rows: pd.DataFrame, routes: pd.DataFrame, excluded: pd.DataFrame
) -> MonthEvidence:
    required_total = (
        float(pd.to_numeric(required_rows["소요대수"], errors="coerce").sum())
        if not required_rows.empty
        else 0.0
    )
    unique_load = _unique_demand_load(required_rows)
    top_products = _top_products(required_rows, required_total)
    basis_columns = [f"{column}{RATIO_BASIS_SUFFIX}" for column, _ in RATIO_COLUMNS]
    bases = routes[basis_columns] if not routes.empty else pd.DataFrame(columns=basis_columns)
    rule_excluded = excluded[RULE_EXCLUDED_COLUMN].eq(True)
    return MonthEvidence(
        route_count=len(routes),
        excluded_route_count=len(excluded.loc[~rule_excluded, ROUTE_KEYS].drop_duplicates()),
        rule_excluded_route_count=len(excluded.loc[rule_excluded, ROUTE_KEYS].drop_duplicates()),
        unique_demand_load=unique_load,
        required=required_total,
        effective_capacity=unique_load / required_total if required_total > 0 else None,
        product_count=(int(required_rows["제품정보"].nunique()) if not required_rows.empty else 0),
        top_products=top_products,
        assumed_ratio_routes=int(bases.isin([RATIO_ASSUMED_MISSING_ROW]).any(axis=1).sum()),
        blank_ratio_routes=int(bases.isin([RATIO_BLANK_OR_ZERO]).any(axis=1).sum()),
    )


def _unique_demand_load(required_rows: pd.DataFrame) -> float:
    """그 달 공정의 원수요 부하량 — STEP 마다 같은 부하량이 실리므로 원수요 키로 중복을 뺀 합이다.

    키는 `effective_process_capacity_long` 과 같은 정규화(글자 앞뒤 공백, 소요기준 대문자·
    `WAFER → WF`)를 지난다. 그 함수와 달리 공정당 소요기준 하나·키 완전성·부하량 일치를 검사하지
    않는다 — 본 계산(대당 Capa·소요대수·확보율)이 강제하지 않는 규칙이라, 그 데이터에서 요약 표는
    서는데 근거 패널만 예외로 멈추면 안 된다. 같은 원수요 키의 부하량이 다르면 첫 행을 쓴다.
    """
    if required_rows.empty:
        return 0.0
    keys = [column for column in DEMAND_ID_COLUMNS if column != MONTH]
    prepared = _key_frame(required_rows, keys)
    loads = pd.to_numeric(prepared.drop_duplicates(keys)["부하량"], errors="coerce").fillna(0.0)
    return float(loads.sum())


def _top_products(required_rows: pd.DataFrame, required_total: float) -> pd.DataFrame:
    if required_rows.empty:
        return pd.DataFrame(
            {
                "제품정보": pd.Series(dtype="string"),
                "소요대수": pd.Series(dtype="float64"),
                SHARE_COLUMN: pd.Series(dtype="float64"),
            }
        )
    prepared = _key_frame(required_rows, ["제품정보"])
    prepared["소요대수"] = pd.to_numeric(prepared["소요대수"], errors="coerce").fillna(0.0)
    grouped = prepared.groupby("제품정보", sort=True)["소요대수"].sum().reset_index()
    grouped = grouped.sort_values("소요대수", ascending=False, kind="stable").head(
        TOP_PRODUCT_LIMIT
    )
    grouped[SHARE_COLUMN] = (
        grouped["소요대수"] / required_total if required_total > 0 else float("nan")
    )
    return grouped.reset_index(drop=True)


# ================================================================== 공용 도우미


def _process_mask(values: pd.Series, process: str) -> pd.Series:
    """계산과 같은 정규화(앞뒤 공백 떼기)를 지난 값으로 공정 하나를 고른다."""
    return values.astype("string").str.strip().eq(process.strip()).fillna(False).astype("bool")


def _float(values: pd.Series) -> pd.Series:
    """숫자 칸을 `float64` 로 맞춘다. 숫자로 못 읽는 칸은 NaN 이다(계산이 이미 막은 값이다)."""
    return pd.to_numeric(values, errors="coerce").astype("float64")


def _ordered_months(months: Sequence[int]) -> list[int]:
    return list(dict.fromkeys(int(month) for month in months))


def _month_rows(frame: pd.DataFrame, month: int) -> pd.DataFrame:
    if frame.empty or MONTH not in frame.columns:
        return frame
    months = pd.to_numeric(frame[MONTH], errors="coerce")
    return frame.loc[months.eq(month)].reset_index(drop=True)


def _table_rows(
    tables: Mapping[str, pd.DataFrame], name: str, process: str, month: int
) -> pd.DataFrame:
    """기준정보 표 하나를 공정·달로 거른 사본. 표가 없으면 빈 프레임이다."""
    table = tables.get(name)
    if not isinstance(table, pd.DataFrame) or "공정" not in table.columns:
        return pd.DataFrame()
    rows = table.loc[_process_mask(table["공정"], process)]
    return _month_rows(rows, month).copy()


def _key_frame(frame: pd.DataFrame, keys: Sequence[str]) -> pd.DataFrame:
    """맞댈 키를 계산과 같은 꼴로 맞춘 사본 — 글자는 앞뒤 공백을 떼고, `Area_Name` 은 `Main`·`MI`,
    소요기준은 대문자·`WAFER → WF` 다. 계산이 이미 막은 값(빈 키 등)은 그대로 둔다."""
    prepared = frame.copy()
    for key in keys:
        prepared[key] = prepared[key].astype("string").str.strip()
    if "Area_Name" in keys:
        folded = prepared["Area_Name"].str.casefold()
        prepared["Area_Name"] = (
            folded.map(_AREA_KEYS).fillna(prepared["Area_Name"]).astype("string")
        )
    if "소요기준" in keys:
        prepared["소요기준"] = normalize_demand_basis(prepared["소요기준"])
    return prepared
