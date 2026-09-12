# Purpose: Equipment input validation, weekly availability, and space status.

"""Equipment input validation, weekly availability, and space status."""

from __future__ import annotations

from datetime import date
from typing import cast

import pandas as pd

from capa_simulation.services.equipment_contract import (
    SCHEDULE_STAGES,
    STATUS_COUNT_COLUMNS,
    TRANSITION_EVENT_COLUMNS,
    WEEKLY_COLUMNS,
)
from capa_simulation.services.equipment_validation import (
    prepare_downtime_for_prepared_equipment,
    prepare_equipment_baseline,
    prepare_equipment_master,
)
from capa_simulation.services.iso_week_calendar import weeknum_label

# Backward-compatible public name used by the Space page.


def build_equipment_status_as_of(
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    *,
    as_of: date,
) -> pd.DataFrame:
    """Return exclusive lifecycle status plus independent owned/available flags."""
    prepared = prepare_equipment_master(equipment)
    prepared_downtime = prepare_downtime_for_prepared_equipment(downtime, prepared)
    return _build_equipment_status_from_prepared(
        prepared,
        prepared_downtime,
        as_of=pd.Timestamp(as_of),
    )


def _build_equipment_status_from_prepared(
    prepared: pd.DataFrame,
    prepared_downtime: pd.DataFrame,
    *,
    as_of: pd.Timestamp,
) -> pd.DataFrame:
    """Build one as-of snapshot from already validated equipment inputs."""
    result = prepared.copy()
    if result.empty:
        for column, dtype in (
            ("상태", "string"),
            ("보유여부", "boolean"),
            ("가용여부", "boolean"),
            ("레이아웃반영여부", "boolean"),
            ("비가동유형", "string"),
        ):
            result[column] = pd.Series(dtype=dtype)
        return result

    timestamp = as_of
    existing = result["기존설비여부"].eq("Y")
    storage = result["장기보관여부"].eq("Y")
    arrived = existing | storage | (result["입고일정"].notna() & result["입고일정"].le(timestamp))
    removal_complete = result["반출일정"].notna() & result["반출일정"].le(timestamp)
    relocation_complete = result["이설일"].notna() & result["이설일"].le(timestamp)
    exited = removal_complete | relocation_complete
    owned = arrived & ~exited
    qualified = existing | (result["Qual일정"].notna() & result["Qual일정"].le(timestamp))

    active_downtime = _active_downtime(prepared_downtime, timestamp)
    reason_by_equipment = active_downtime.groupby("호기")["비가동유형"].agg(_joined_unique)
    result["비가동유형"] = result["호기"].map(reason_by_equipment).astype("string")
    offline = result["비가동유형"].notna() & owned
    available = owned & qualified & ~storage & ~offline

    status = pd.Series("입고 예정", index=result.index, dtype="string")
    status.loc[owned & ~qualified & ~storage] = "셋업 진행중"
    status.loc[available] = "가용"
    status.loc[storage & owned] = "보관 설비"
    status.loc[result["반출일정"].notna() & ~removal_complete] = "반출 예정"
    status.loc[result["이설일"].notna() & ~relocation_complete] = "이설 예정"
    status.loc[offline] = "운영 비가동"
    status.loc[removal_complete] = "반출 완료"
    status.loc[relocation_complete] = "이설 완료"
    result["상태"] = status
    result["보유여부"] = owned.astype("boolean")
    result["가용여부"] = available.astype("boolean")
    result["레이아웃반영여부"] = (result["레이아웃표시"].eq("Y") & ~exited).astype("boolean")
    return result.reset_index(drop=True)


def build_weekly_equipment_availability(
    baseline: pd.DataFrame,
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    *,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Aggregate owned, available, and lifecycle counts by ISO week and small process."""
    if start_date > end_date:
        raise ValueError("주차별 조회 시작일은 종료일보다 늦을 수 없습니다.")
    prepared_baseline = prepare_equipment_baseline(baseline)
    prepared_equipment = prepare_equipment_master(equipment)
    prepared_downtime = prepare_downtime_for_prepared_equipment(downtime, prepared_equipment)
    processes = (
        pd.concat([prepared_baseline["공정"], prepared_equipment["공정소분류"]], ignore_index=True)
        .dropna()
        .drop_duplicates()
    )
    if processes.empty:
        return pd.DataFrame(columns=WEEKLY_COLUMNS)

    baseline_counts = prepared_baseline.groupby("공정", observed=True)["기존보유대수"].sum()
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    first_monday = start - pd.Timedelta(days=start.weekday())
    last_monday = end - pd.Timedelta(days=end.weekday())
    rows: list[dict[str, object]] = []
    for week_start in pd.date_range(first_monday, last_monday, freq="7D"):
        week_end = week_start + pd.Timedelta(days=6)
        weeknum = weeknum_label(week_start)
        status = _build_equipment_status_from_prepared(
            prepared_equipment,
            prepared_downtime,
            as_of=week_end,
        )
        status_summary = status.groupby("공정소분류", observed=True).agg(
            보유호기=("보유여부", "sum"),
            가용호기=("가용여부", "sum"),
        )
        status_counts = pd.crosstab(status["공정소분류"], status["상태"])
        for process in processes.tolist():
            base_count = float(baseline_counts.get(process, 0.0))
            if process in status_summary.index:
                owned_count = int(cast(float, status_summary.at[process, "보유호기"]))
                available_units = int(cast(float, status_summary.at[process, "가용호기"]))
            else:
                owned_count = 0
                available_units = 0
            row: dict[str, object] = {
                "Weeknum": weeknum,
                "주차시작일": week_start.date(),
                "주차종료일": week_end.date(),
                "공정소분류": str(process),
                "기존보유대수": base_count,
                "추가설비대수": owned_count,
                "총대수": base_count + owned_count,
                "가용대수": base_count + available_units,
                "비가동대수": owned_count - available_units,
            }
            for status_name, column in STATUS_COUNT_COLUMNS.items():
                row[column] = (
                    int(cast(float, status_counts.at[process, status_name]))
                    if process in status_counts.index and status_name in status_counts.columns
                    else 0
                )
            rows.append(row)
    return pd.DataFrame(rows, columns=WEEKLY_COLUMNS)


def build_inactive_equipment(
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    *,
    as_of: date,
) -> pd.DataFrame:
    """Return owned unit-level equipment that is not currently available."""
    status = build_equipment_status_as_of(equipment, downtime, as_of=as_of)
    if status.empty:
        return status
    return status.loc[status["보유여부"] & ~status["가용여부"]].reset_index(drop=True)


def build_space_equipment_status(
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    *,
    as_of: date,
) -> pd.DataFrame:
    """Build the unit-level source used by the Space dashboard."""
    result = build_equipment_status_as_of(equipment, downtime, as_of=as_of)
    result["단계"] = result["상태"]
    return result.reset_index(drop=True)


def build_milestone_transition_events(
    equipment: pd.DataFrame,
    *,
    start_date: date,
    end_date: date,
    as_of: date,
) -> pd.DataFrame:
    """Return equipment schedule events inside the selected date range."""
    if start_date > end_date:
        raise ValueError("단계 전환 조회 시작일은 종료일보다 늦을 수 없습니다.")
    prepared = prepare_equipment_master(equipment)
    if prepared.empty:
        return pd.DataFrame(columns=TRANSITION_EVENT_COLUMNS)
    identity_columns = ["호기", "공정대분류", "공정소분류", "동", "층", "확정상태"]
    date_columns = [column for column, _ in SCHEDULE_STAGES]
    events = prepared.melt(
        id_vars=identity_columns,
        value_vars=date_columns,
        var_name="단계컬럼",
        value_name="전환일",
    ).dropna(subset=["전환일"])
    if events.empty:
        return pd.DataFrame(columns=TRANSITION_EVENT_COLUMNS)
    stage_by_column = dict(SCHEDULE_STAGES)
    previous_stage = {
        "제진대일정": "착수 전",
        "물류일정": "제진대",
        "입고일정": "물류",
        "Qual일정": "입고",
        "반출일정": "가용/보관",
        "이설일": "가용/보관",
    }
    order = {column: index for index, column in enumerate(date_columns)}
    events["단계순서"] = events["단계컬럼"].map(order).astype("int64")
    events["이전단계"] = events["단계컬럼"].map(previous_stage).astype("string")
    events["전환단계"] = events["단계컬럼"].map(stage_by_column).astype("string")
    events["전환일"] = pd.to_datetime(events["전환일"], errors="raise")
    # 확정상태는 Qual 단계에만 뜻이 있다. 다른 단계는 결측으로 두는데, 결측을 그대로
    # 넘기면 표에 "None" 이라는 글자가 찍혀 값이 있는 것처럼 보인다. 빈 칸으로 만든다.
    events["확정상태"] = (
        events["확정상태"].astype("string").where(events["단계컬럼"].eq("Qual일정")).fillna("")
    )
    events = events.loc[
        events["전환일"].between(pd.Timestamp(start_date), pd.Timestamp(end_date), inclusive="both")
    ].copy()
    if events.empty:
        return pd.DataFrame(columns=TRANSITION_EVENT_COLUMNS)
    as_of_timestamp = pd.Timestamp(as_of)
    events["일정상태"] = events["전환일"].le(as_of_timestamp).map({True: "완료", False: "예정"})
    events["기준일대비"] = (
        events["전환일"].sub(as_of_timestamp).dt.days.map(_format_day_difference).astype("string")
    )
    events = events.sort_values(["전환일", "단계순서", "공정소분류", "호기"], kind="stable")
    return events.loc[:, TRANSITION_EVENT_COLUMNS].reset_index(drop=True)


def _active_downtime(downtime: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    if downtime.empty:
        return downtime.copy()
    active = downtime["시작일"].le(as_of) & (
        downtime["종료일"].isna() | downtime["종료일"].ge(as_of)
    )
    return downtime.loc[active].copy()


def _joined_unique(values: pd.Series) -> str:
    return ", ".join(values.astype("string").drop_duplicates().tolist())


def _format_day_difference(days: int) -> str:
    if days == 0:
        return "D-Day"
    if days > 0:
        return f"D-{days}"
    return f"D+{-days}"
