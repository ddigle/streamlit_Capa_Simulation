# Purpose: 설비 운영 입력의 주차별 가용대수·호기 생애주기 구간·Space 단계와 전환 이벤트를 집계한다.

"""설비 운영 입력의 주차 집계·생애주기·Space 상태.

입력 검증은 `equipment_validation.py` 의 `prepare_*` 를 불러 쓰고, 설비 DB 가 비어 있을 때의
화면 샘플은 `equipment_samples.py` 가 갖는다 — 이 모듈에는 둘 다 없다.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from typing import cast

import pandas as pd

from capa_simulation.services.equipment_contract import (
    ARRIVAL_DATE_COLUMN,
    COUNT_CATEGORY_COLUMN,
    COUNTED_COLUMN,
    EQUIPMENT_ID_COLUMN,
    RELOCATION_DATE_COLUMN,
    SCHEDULE_STAGES,
    STATUS_COUNT_COLUMNS,
    STORAGE_FLAG_COLUMN,
    TRANSITION_EVENT_COLUMNS,
    WEEKLY_COLUMNS,
    counts_for_capacity,
)
from capa_simulation.services.equipment_units import (
    UNIT_COUNT_DECIMALS,
    UNIT_KEY_COLUMN,
    UNIT_SHARE_COLUMN,
    held_unit_shares,
    unit_keys,
)
from capa_simulation.services.equipment_validation import (
    prepare_downtime_for_prepared_equipment,
    prepare_equipment_baseline,
    prepare_equipment_master,
)
from capa_simulation.services.iso_week_calendar import weeknum_label


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
            (COUNT_CATEGORY_COLUMN, "string"),
            (COUNTED_COLUMN, "bool"),
            ("레이아웃반영여부", "boolean"),
            ("비가동유형", "string"),
            (UNIT_KEY_COLUMN, "string"),
            (UNIT_SHARE_COLUMN, "float64"),
        ):
            result[column] = pd.Series(dtype=dtype)
        return result

    timestamp = as_of
    existing = result["기존설비여부"].eq("Y")
    storage = result[STORAGE_FLAG_COLUMN].eq("Y")
    arrived = (
        existing
        | storage
        | (result[ARRIVAL_DATE_COLUMN].notna() & result[ARRIVAL_DATE_COLUMN].le(timestamp))
    )
    removal_complete = result["반출일정"].notna() & result["반출일정"].le(timestamp)
    relocation_complete = result[RELOCATION_DATE_COLUMN].notna() & result[
        RELOCATION_DATE_COLUMN
    ].le(timestamp)
    exited = removal_complete | relocation_complete
    owned = arrived & ~exited
    qualified = existing | (result["Qual일정"].notna() & result["Qual일정"].le(timestamp))

    active_downtime = _active_downtime(prepared_downtime, timestamp)
    reason_by_equipment = active_downtime.groupby(EQUIPMENT_ID_COLUMN)["비가동유형"].agg(
        _joined_unique
    )
    result["비가동유형"] = result[EQUIPMENT_ID_COLUMN].map(reason_by_equipment).astype("string")
    offline = result["비가동유형"].notna() & owned
    available = owned & qualified & ~storage & ~offline

    status = pd.Series("입고 예정", index=result.index, dtype="string")
    status.loc[owned & ~qualified & ~storage] = "셋업 진행중"
    status.loc[available] = "가용"
    status.loc[storage & owned] = "보관 설비"
    status.loc[result["반출일정"].notna() & ~removal_complete] = "반출 예정"
    status.loc[result[RELOCATION_DATE_COLUMN].notna() & ~relocation_complete] = "이설 예정"
    status.loc[offline] = "운영 비가동"
    status.loc[removal_complete] = "반출 완료"
    status.loc[relocation_complete] = "이설 완료"
    result["상태"] = status
    result["보유여부"] = owned.astype("boolean")
    result["가용여부"] = available.astype("boolean")
    # 세는 자리는 이름이 아니라 가용 판정을 본다. 반출·이설일정이 적힌 호기는 실행일 전까지 이름이
    # 「반출 예정」·「이설 예정」이지만 가용이면 가용으로 센다(`equipment_contract` 의 집계분류).
    result[COUNT_CATEGORY_COLUMN] = status.mask(available.fillna(False).astype("bool"), "가용")
    result[COUNTED_COLUMN] = counts_for_capacity(result)
    result["레이아웃반영여부"] = (result["레이아웃표시"].eq("Y") & ~exited).astype("boolean")
    # 지분은 **이 시점의 보유**로 매긴다. 모듈을 떼어 반출해도 남은 모듈이 한 대를 채우고,
    # 입고 전 모듈은 형제가 보유 중인 동안 0 이다.
    keys = unit_keys(result)
    result[UNIT_KEY_COLUMN] = keys
    result[UNIT_SHARE_COLUMN] = held_unit_shares(keys, owned)
    return result.reset_index(drop=True)


# 상태가 바뀔 수 있는 날은 정해져 있다. 판정이 보는 컬럼이 그것뿐이기 때문이다 —
# `반입일정`·`Qual일정`·`반출일정`·`이설일정` 은 그날 `le` 로 넘어가고, 비가동은 `시작일` 에
# 켜져 `종료일` 다음 날 꺼진다. 다른 날에는 같은 판정이 나오므로 샘플링할 이유가 없다.
_TIMELINE_EVENT_COLUMNS = (ARRIVAL_DATE_COLUMN, "Qual일정", "반출일정", RELOCATION_DATE_COLUMN)

LIFECYCLE_SPAN_COLUMNS = (
    EQUIPMENT_ID_COLUMN,
    "공정소분류",
    "공정대분류",
    "상태",
    "시작일",
    "종료일",
)
_MOMENT_COLUMN = "_시점"


def build_equipment_lifecycle_spans(
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    *,
    start_date: date,
    end_date: date,
    with_unit_share: bool = False,
) -> pd.DataFrame:
    """호기별 생애주기 구간. 점 이벤트(일정 컬럼)를 구간으로 접는다.

    `with_unit_share` 를 켜면 세는 데 쓰는 구간이 된다. `설비지분`·`설비키`·`집계분류`·
    `가용대수반영` 컬럼을 붙이고, **지분이나 집계분류가 바뀌는 날에도** 구간을 끊는다. 모듈
    형제의 입고·반출로 지분이 바뀌면 상태는 그대로여도 대수 축 몫이 달라지고, 반출일정이 적힌
    호기는 셋업 중·Qual 후가 모두 「반출 예정」 한 이름이라 이름으로만 끊으면 가용이 된 날을
    잃는다. 월별 대수(`monthly_equipment_availability`)가 켜서 쓴다. 끄면(기본) 상태 이름이
    바뀔 때만 끊어 생애주기 Gantt 가 지금처럼 그린다.

    **판정 규칙을 다시 적지 않는다.** 상태가 바뀔 수 있는 날마다
    `_build_equipment_status_from_prepared` 를 그대로 부르고, 이어지는 같은 상태를 한 구간
    으로 묶는다. 규칙을 옮겨 적으면 이 화면만 조용히 다른 이야기를 하게 된다 — 주차별
    집계·상태 막대·Space 배치도가 모두 그 함수 하나를 본다.

    끝을 여는 구간은 `end_date` 에서 자른다. 조회 범위 밖의 일은 이 화면이 답할 것이
    아니다.
    """
    if start_date > end_date:
        raise ValueError("생애주기 조회 시작일은 종료일보다 늦을 수 없습니다.")
    columns = [
        *LIFECYCLE_SPAN_COLUMNS,
        *(
            (UNIT_SHARE_COLUMN, UNIT_KEY_COLUMN, COUNT_CATEGORY_COLUMN, COUNTED_COLUMN)
            if with_unit_share
            else ()
        ),
    ]
    prepared = prepare_equipment_master(equipment)
    if prepared.empty:
        return pd.DataFrame(columns=columns)
    prepared_downtime = prepare_downtime_for_prepared_equipment(downtime, prepared)

    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    breakpoints = _lifecycle_breakpoints(prepared, prepared_downtime, start=start, end=end)
    process_by_unit = prepared.set_index(EQUIPMENT_ID_COLUMN)[["공정소분류", "공정대분류"]]

    # 열린 구간 하나는 (상태, 집계분류, 지분, 시작일)이다. 앞 셋 중 하나라도 바뀌면 끊는다.
    open_spans: dict[str, tuple[str, str, float, pd.Timestamp]] = {}
    rows: list[dict[str, object]] = []

    def close(
        unit: str,
        status: str,
        category: str,
        share: float,
        began: pd.Timestamp,
        finished: pd.Timestamp,
    ) -> None:
        row: dict[str, object] = {
            EQUIPMENT_ID_COLUMN: unit,
            "공정소분류": process_by_unit.at[unit, "공정소분류"],
            "공정대분류": process_by_unit.at[unit, "공정대분류"],
            "상태": status,
            "시작일": began.date(),
            "종료일": finished.date(),
        }
        if with_unit_share:
            row[UNIT_SHARE_COLUMN] = share
            row[COUNT_CATEGORY_COLUMN] = category
        rows.append(row)

    for moment in breakpoints:
        status_frame = _build_equipment_status_from_prepared(
            prepared, prepared_downtime, as_of=moment
        )
        shares = (
            status_frame[UNIT_SHARE_COLUMN].round(UNIT_COUNT_DECIMALS + 3)
            if with_unit_share
            else pd.Series(1.0, index=status_frame.index)
        )
        # Gantt(끈 쪽)는 이름만 본다 — 집계분류를 이름으로 채우면 끊는 자리가 지금과 같다.
        categories = (
            status_frame[COUNT_CATEGORY_COLUMN] if with_unit_share else status_frame["상태"]
        )
        for unit, status, category, share in zip(
            status_frame[EQUIPMENT_ID_COLUMN],
            status_frame["상태"],
            categories,
            shares,
            strict=True,
        ):
            state = (str(status), str(category), float(share))
            previous = open_spans.get(str(unit))
            if previous is not None and previous[:3] == state:
                continue
            if previous is not None:
                # 앞 구간은 이 날 **전날**까지다. 같은 날 두 상태가 겹쳐 보이면 안 된다.
                close(str(unit), *previous[:3], previous[3], moment - pd.Timedelta(days=1))
            open_spans[str(unit)] = (*state, moment)
    for unit, (status, category, share, began) in open_spans.items():
        close(unit, status, category, share, began, end)
    result = pd.DataFrame(rows, columns=columns)
    if with_unit_share:
        key_by_unit = dict(zip(prepared[EQUIPMENT_ID_COLUMN], unit_keys(prepared), strict=True))
        result[UNIT_KEY_COLUMN] = result[EQUIPMENT_ID_COLUMN].map(key_by_unit)
        # 사용기준은 날짜와 상관없는 호기 속성이라 구간을 끊지 않는다. 호기마다 한 번 매긴다.
        counted_by_unit = dict(
            zip(prepared[EQUIPMENT_ID_COLUMN], counts_for_capacity(prepared), strict=True)
        )
        result[COUNTED_COLUMN] = (
            result[EQUIPMENT_ID_COLUMN].map(counted_by_unit).fillna(False).astype("bool")
        )
    # 길이가 0 인 구간은 같은 날 두 번 바뀐 것이다. 그리면 폭 없는 막대라 보이지 않는다.
    result = result.loc[result["종료일"] >= result["시작일"]]
    return result.sort_values([EQUIPMENT_ID_COLUMN, "시작일"]).reset_index(drop=True)


def _lifecycle_breakpoints(
    prepared: pd.DataFrame,
    prepared_downtime: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> list[pd.Timestamp]:
    """판정이 달라질 수 있는 날만 모은다. 조회 시작일은 항상 첫 표본이다."""
    moments: set[pd.Timestamp] = {start}
    for column in _TIMELINE_EVENT_COLUMNS:
        moments.update(pd.to_datetime(prepared[column].dropna()).tolist())
    if not prepared_downtime.empty:
        moments.update(pd.to_datetime(prepared_downtime["시작일"].dropna()).tolist())
        finished = pd.to_datetime(prepared_downtime["종료일"].dropna())
        moments.update((finished + pd.Timedelta(days=1)).tolist())
    return sorted(moment for moment in moments if start <= moment <= end)


def build_weekly_equipment_availability(
    baseline: pd.DataFrame,
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    *,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """ISO 주차·공정소분류별 총대수·가용대수·비가동대수와 분류 대수(각 주 일요일 판정).

    호기 마스터 쪽은 **사용기준이 HBM 인 행만** 센다(`equipment_contract.counts_for_capacity`).
    기존 보유대수는 사용기준이 없어 지금처럼 모두 센다.
    """
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
        # 행을 세지 않고 설비지분을 더한다. 모듈 행 넷이 한 대로, 모듈 하나의 PM 이 0.25대로
        # 잡힌다. 그래서 정수로 자르지 않는다 — 자르면 0.75 가 0 이 된다.
        # 사용기준이 HBM 이 아닌 행은 지분을 0 으로 본다(`counts_for_capacity`). 가용만 빼면
        # 「비가동 = 보유 - 가용」이 그 호기를 모두 비가동으로 세므로 보유·분류 대수에서도 뺀다.
        share = status[UNIT_SHARE_COLUMN].astype("float64") * status[COUNTED_COLUMN].astype(
            "float64"
        )
        weighted = status.assign(
            _지분=share,
            _보유=status["보유여부"].fillna(False).astype("float64") * share,
            _가용=status["가용여부"].fillna(False).astype("float64") * share,
        )
        status_summary = weighted.groupby("공정소분류", observed=True).agg(
            보유호기=("_보유", "sum"),
            가용호기=("_가용", "sum"),
        )
        # 분류 대수는 상태 이름이 아니라 집계분류로 센다 — 실행일 전의 반출·이설 예정 호기가
        # 가용이면 가용호기대수에 든다(`equipment_contract.STATUS_COUNT_COLUMNS`).
        status_counts = (
            weighted.groupby(["공정소분류", COUNT_CATEGORY_COLUMN], observed=True)["_지분"]
            .sum()
            .unstack(fill_value=0)
            if not weighted.empty
            else pd.DataFrame()
        )
        for process in processes.tolist():
            base_count = float(baseline_counts.get(process, 0.0))
            if process in status_summary.index:
                owned_count = _unit_count(status_summary.at[process, "보유호기"])
                available_units = _unit_count(status_summary.at[process, "가용호기"])
            else:
                owned_count = 0.0
                available_units = 0.0
            row: dict[str, object] = {
                "Weeknum": weeknum,
                "주차시작일": week_start.date(),
                "주차종료일": week_end.date(),
                "공정소분류": str(process),
                "기존보유대수": base_count,
                "추가설비대수": owned_count,
                "총대수": base_count + owned_count,
                "가용대수": base_count + available_units,
                # `+ 0.0` 은 음수 0 을 지운다(지분 합끼리 빼면 -0.0 이 남을 수 있다).
                "비가동대수": round(owned_count - available_units, UNIT_COUNT_DECIMALS) + 0.0,
            }
            for status_name, column in STATUS_COUNT_COLUMNS.items():
                row[column] = (
                    _unit_count(status_counts.at[process, status_name])
                    if process in status_counts.index and status_name in status_counts.columns
                    else 0.0
                )
            rows.append(row)
    return pd.DataFrame(rows, columns=WEEKLY_COLUMNS)


def _unit_count(value: object) -> float:
    """대수 축 한 칸. 지분 합의 부동소수 끝자리를 버린다(1/3 × 3 = 1)."""
    return round(float(cast(float, value)), UNIT_COUNT_DECIMALS)


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


def _month_bounds(month: date) -> tuple[date, date]:
    """그 달의 첫날과 마지막 날. 기준일 아무 날짜나 받는다."""
    first = date(month.year, month.month, 1)
    next_first = (
        date(month.year + 1, 1, 1) if month.month == 12 else date(month.year, month.month + 1, 1)
    )
    return first, next_first - timedelta(days=1)


def inactive_equipment_moments(
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    *,
    month: date,
) -> list[date]:
    """그 달 안에서 **판정이 달라질 수 있는 날**. 월초 ∪ 구간이 바뀌는 날 ∪ 일요일.

    일요일만 재면 월요일에 시작해 토요일에 끝난 비가동이 통째로 빠진다. 그래서 상태가
    바뀔 수 있는 날을 `_lifecycle_breakpoints` 에서 그대로 받아 온다 — 판정이 보는 컬럼이
    그것뿐이라 그 사이의 날에는 같은 답이 나온다. 여기서 규칙을 다시 적지 않는다.

    **생애주기 구간(`build_equipment_lifecycle_spans`)의 시작일을 쓰지 않는다.** 그 구간은
    **상태 이름으로 묶은** 것이라 이름이 그대로인 채 판정만 바뀌는 날을 잃는다 —
    반출일정이 적힌 호기는 입고 전·셋업 중·Qual 후가 모두 「반출 예정」 한 구간이라 입고일
    ·Qual일에 경계가 생기지 않는다. 그 호기의 비가동 구간이 한 주보다 짧고 일요일을 비껴
    가면 이름 화이트리스트와 똑같이 통째로 빠진다.

    호기 마스터가 비면 월초와 일요일만 남는다. 그 시점들로 재도 결과는 빈 표라 화면이
    답을 못 내는 일은 없다.
    """
    month_start, month_end = _month_bounds(month)
    moments = {month_start}
    prepared = prepare_equipment_master(equipment)
    if not prepared.empty:
        prepared_downtime = prepare_downtime_for_prepared_equipment(downtime, prepared)
        moments.update(
            breakpoint.date()
            for breakpoint in _lifecycle_breakpoints(
                prepared,
                prepared_downtime,
                start=pd.Timestamp(month_start),
                end=pd.Timestamp(month_end),
            )
        )
    sunday = month_start + timedelta(days=(6 - month_start.weekday()) % 7)
    while sunday <= month_end:
        moments.add(sunday)
        sunday += timedelta(days=7)
    return sorted(moments)


def build_inactive_equipment_in_month(
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    *,
    month: date,
    moments: Sequence[date] | None = None,
) -> pd.DataFrame:
    """그 달 안에서 **한 번이라도** 비가동이었던 호기.

    **상태 이름 화이트리스트로 고르지 않는다.** 상태는 호기당 하나뿐이고 사다리 아래쪽이
    위쪽을 덮는다 — 셋업 중인 호기에 반출일정이 적혀 있으면 상태는 「반출 예정」이 되므로
    「운영 비가동」·「셋업 진행중」을 이름으로 골라 세는 집계는 그 호기를 통째로 잃는다.
    이름 목록은 사다리가 한 칸 늘 때마다 조용히 틀려지기도 한다. 그래서 시점 표와 **같은
    술어**(`build_inactive_equipment` = 보유 & ~가용)를 `inactive_equipment_moments` 의
    시점마다 다시 물어 `설비명` 으로 union 한다.

    `month` 는 그 달의 아무 날짜라도 된다(기준일을 그대로 넘긴다). `moments` 를 주면 그
    시점 집합을 그대로 쓴다 — 화면이 캡션에 적는 시점 개수와 실제로 잰 시점이 어긋나지
    않게 하려는 것이다.

    결과는 시점 표와 같은 컬럼의 `설비명` 바로 뒤에 `비가동 시작`·`비가동 종료`를 붙인 것이다.
    이 둘은 구간의 실제 시작·끝이 아니라 **그 호기가 비가동으로 잡힌 시점의 최소·최대**다.
    """
    if moments is None:
        moments = inactive_equipment_moments(equipment, downtime, month=month)
    sampled = sorted(set(moments)) or [_month_bounds(month)[0]]
    stacked = pd.concat(
        [
            build_inactive_equipment(equipment, downtime, as_of=moment).assign(
                **{_MOMENT_COLUMN: moment}
            )
            for moment in sampled
        ],
        ignore_index=True,
    )
    caught = stacked.groupby(EQUIPMENT_ID_COLUMN)[_MOMENT_COLUMN].agg(["min", "max"])
    result = (
        stacked.drop_duplicates(EQUIPMENT_ID_COLUMN, keep="first")
        .drop(columns=[_MOMENT_COLUMN])
        .reset_index(drop=True)
    )
    # 두 컬럼은 `설비명` 바로 뒤에 붙인다.
    after_id = cast(int, result.columns.get_loc(EQUIPMENT_ID_COLUMN)) + 1
    result.insert(after_id, "비가동 시작", result[EQUIPMENT_ID_COLUMN].map(caught["min"]))
    result.insert(after_id + 1, "비가동 종료", result[EQUIPMENT_ID_COLUMN].map(caught["max"]))
    return result.sort_values(["비가동 시작", EQUIPMENT_ID_COLUMN], kind="stable").reset_index(
        drop=True
    )


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
    prepared = prepared.assign(**{UNIT_KEY_COLUMN: unit_keys(prepared)})
    identity_columns = [
        EQUIPMENT_ID_COLUMN,
        "공정대분류",
        "공정소분류",
        "동",
        "층",
        "확정상태",
        UNIT_KEY_COLUMN,
    ]
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
        ARRIVAL_DATE_COLUMN: "물류",
        "Qual일정": "입고",
        "반출일정": "가용/보관",
        RELOCATION_DATE_COLUMN: "가용/보관",
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
    events = events.sort_values(
        ["전환일", "단계순서", "공정소분류", EQUIPMENT_ID_COLUMN], kind="stable"
    )
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
