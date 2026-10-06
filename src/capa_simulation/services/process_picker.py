# Purpose: 조회기간의 최종 확보율을 공정별로 요약해 선택 화면의 부족·충족·판정 없음 구역을 정한다.

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from typing import Literal

import pandas as pd

from capa_simulation.services.frame_contracts import normalize_month_column, require_columns
from capa_simulation.services.securement_threshold import SecurementThresholds

PICKER_COLUMNS = ("생산계획년월", "공정", "확보율")


@dataclass(frozen=True)
class ProcessPickerItem:
    """원본 공정 키와 조회기간의 유효 확보율 근거를 담는다."""

    process: str
    minimum_rate: float | None
    minimum_month: int | None
    valid_month_count: int
    group: Literal["shortfall", "sufficient", "unavailable"]


def build_process_picker_summary(
    securement: pd.DataFrame,
    ordered_options: Sequence[str],
    *,
    start_month: int,
    end_month: int,
    thresholds: SecurementThresholds,
) -> tuple[ProcessPickerItem, ...]:
    """최종 확보율의 유효 최소값만 읽고 입력 옵션의 원본 키와 순서를 유지한다.

    포함 공정 선택으로 거르지 않아 현재 OFF인 공정도 같은 근거로 판단한다. NaN·무한대는
    유효한 월에서 제외하며, 숫자가 남지 않은 공정을 0% 또는 부족으로 바꾸지 않는다.

    충족은 **유효한 모든 달이 그 달의 판정으로 확보일 때**다(`thresholds.status`). 기준이 달마다
    같으면 「최저 확보율 ≥ 기준」과 같은 말이지만, 월별 예외가 있으면 최저가 아닌 달이 더 높은
    기준에 걸릴 수 있다. 표시하는 최저 확보율·그 달은 판정과 따로 그대로 둔다.
    """
    require_columns(securement, PICKER_COLUMNS, "공정 선택 확보율")
    if not isfinite(thresholds.default_secure) or thresholds.default_secure < 0:
        raise ValueError("공정 선택 확보 기준은 0 이상의 유한한 값이어야 합니다.")
    bounds = pd.DataFrame({"생산계획년월": [start_month, end_month]})
    normalize_month_column(bounds, "공정 선택 조회기간")
    start_month, end_month = (int(value) for value in bounds["생산계획년월"])
    if start_month > end_month:
        raise ValueError("공정 선택 시작 월은 종료 월보다 클 수 없습니다.")

    prepared = securement.loc[:, list(PICKER_COLUMNS)].copy()
    normalize_month_column(prepared, "공정 선택 확보율")
    prepared["공정"] = prepared["공정"].astype("string").str.strip()
    prepared["확보율"] = pd.to_numeric(prepared["확보율"], errors="coerce")
    valid = (
        prepared["생산계획년월"].between(start_month, end_month)
        & prepared["공정"].notna()
        & prepared["확보율"].notna()
        & ~prepared["확보율"].isin([float("inf"), float("-inf")])
    )
    prepared = prepared.loc[valid]
    summaries: dict[str, ProcessPickerItem] = {}
    for process, rows in prepared.groupby("공정", sort=False):
        minimum_rate = float(rows["확보율"].min())
        minimum_month = int(rows.loc[rows["확보율"].eq(minimum_rate), "생산계획년월"].min())
        # 부등호를 여기 다시 적지 않고 HOME 과 같은 판정(`capacity_status`)을 지난다. 경계를
        # 따로 적으면 한쪽만 바뀌어, HOME 결론이 「기준 미달」이라 세는 공정이 아래 구역에 숨는다.
        sufficient = all(
            thresholds.status(float(rate), int(month)) == "secure"
            for rate, month in zip(rows["확보율"], rows["생산계획년월"], strict=True)
        )
        summaries[str(process)] = ProcessPickerItem(
            process=str(process),
            minimum_rate=minimum_rate,
            minimum_month=minimum_month,
            valid_month_count=int(rows["생산계획년월"].nunique()),
            group="sufficient" if sufficient else "shortfall",
        )
    return tuple(
        summaries.get(process, ProcessPickerItem(process, None, None, 0, "unavailable"))
        for process in ordered_options
    )
