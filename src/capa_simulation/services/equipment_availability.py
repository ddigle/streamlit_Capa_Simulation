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
    EXIT_FOLLOWS_COLUMN,
    EXIT_SCHEDULE_COLUMNS,
    EXIT_STARTS_COLUMN,
    LAYOUT_EXITED_COLUMN,
    LAYOUT_REFLECTED_COLUMN,
    QUAL_DATE_COLUMN,
    QUAL_STATUS_COLUMN,
    RELOCATION_DATE_COLUMN,
    SCHEDULE_STAGES,
    STATUS_COUNT_COLUMNS,
    STATUS_EXIT_PLANNED,
    STATUS_EXITED,
    STATUS_STOP_PLANNED,
    STATUS_STOPPED,
    STOP_DATE_COLUMN,
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
    as_of: pd.Timestamp | pd.Series,
) -> pd.DataFrame:
    """Build one as-of snapshot from already validated equipment inputs.

    `as_of` 가 Series 면 행마다 그 행의 시점으로 판정한다(index 는 `prepared` 와 같아야 한다).
    생애주기 구간이 (호기, 바뀔 수 있는 날)을 쌓은 표 한 장을 한 번에 판정할 때 쓴다. 판정 줄은
    한 벌이다 — 시점이 섞이므로 비가동만 행마다 거르고(`_active_downtime_by_row`), 지분은
    (설비키, 시점) 묶음마다 매긴다.
    """
    result = prepared.copy()
    if result.empty:
        for column, dtype in (
            ("상태", "string"),
            ("보유여부", "boolean"),
            ("가용여부", "boolean"),
            (COUNT_CATEGORY_COLUMN, "string"),
            (COUNTED_COLUMN, "bool"),
            (LAYOUT_EXITED_COLUMN, "boolean"),
            (LAYOUT_REFLECTED_COLUMN, "boolean"),
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
    stop_date = result[STOP_DATE_COLUMN]
    relocation_date = result[RELOCATION_DATE_COLUMN]
    stop_complete = stop_date.notna() & stop_date.le(timestamp)
    relocation_complete = relocation_date.notna() & relocation_date.le(timestamp)
    # 집계 이탈일 = min(정지일정, 반출/이설일정). 그날부터 보유·가용·지분에서 빠진다.
    exited = stop_complete | relocation_complete
    # 도면 이탈일 = 반출/이설일정, 없으면 정지일정. 정지한 뒤 자리를 비우기 전까지는 도면에 남는다.
    # 두 날짜 가운데 하나만 적힌 행은 두 이탈일이 같은 날이다.
    left_layout = relocation_complete | (relocation_date.isna() & stop_complete)
    owned = arrived & ~exited
    qualified = existing | (
        result[QUAL_DATE_COLUMN].notna() & result[QUAL_DATE_COLUMN].le(timestamp)
    )

    if isinstance(timestamp, pd.Series):
        result["비가동유형"] = _active_downtime_by_row(result, prepared_downtime, timestamp)
    else:
        active_downtime = _active_downtime(prepared_downtime, timestamp)
        reason_by_equipment = active_downtime.groupby(EQUIPMENT_ID_COLUMN)["비가동유형"].agg(
            _joined_unique
        )
        result["비가동유형"] = result[EQUIPMENT_ID_COLUMN].map(reason_by_equipment).astype("string")
    offline = result["비가동유형"].notna() & owned
    available = owned & qualified & ~storage & ~offline

    # 뒤에 쓴 줄이 앞을 덮는다: 입고 예정 < 셋업 진행중 < 가용 < 보관 설비 < 반출/이설 예정 <
    # 정지 예정 < 운영 비가동 < 정지 < 반출/이설 완료.
    status = pd.Series("입고 예정", index=result.index, dtype="string")
    status.loc[owned & ~qualified & ~storage] = "셋업 진행중"
    status.loc[available] = "가용"
    status.loc[storage & owned] = "보관 설비"
    status.loc[relocation_date.notna() & ~relocation_complete] = STATUS_EXIT_PLANNED
    status.loc[stop_date.notna() & ~stop_complete] = STATUS_STOP_PLANNED
    status.loc[offline] = "운영 비가동"
    status.loc[stop_complete] = STATUS_STOPPED
    status.loc[relocation_complete] = STATUS_EXITED
    result["상태"] = status
    result["보유여부"] = owned.astype("boolean")
    result["가용여부"] = available.astype("boolean")
    # 세는 자리는 이름이 아니라 가용 판정을 본다. 정지·반출/이설일정이 적힌 호기는 실행일 전까지
    # 이름이 「정지 예정」·「반출/이설 예정」이지만 가용이면 가용으로 센다(`equipment_contract` 의
    # 집계분류).
    result[COUNT_CATEGORY_COLUMN] = status.mask(available.fillna(False).astype("bool"), "가용")
    result[COUNTED_COLUMN] = counts_for_capacity(result)
    result[LAYOUT_EXITED_COLUMN] = left_layout.astype("boolean")
    result[LAYOUT_REFLECTED_COLUMN] = (result["레이아웃표시"].eq("Y") & ~left_layout).astype(
        "boolean"
    )
    # 지분은 **이 시점의 보유**로 매긴다. 모듈을 떼어 반출해도 남은 모듈이 한 대를 채우고,
    # 입고 전 모듈은 형제가 보유 중인 동안 0 이다.
    keys = unit_keys(result)
    result[UNIT_KEY_COLUMN] = keys
    # 행마다 시점이 다르면 같은 시점의 형제끼리만 나눈다 — 한 시점에 한 설비키의 행은 모두 쌓인다.
    share_groups = (
        result.groupby([keys, timestamp], sort=False).ngroup()
        if isinstance(timestamp, pd.Series)
        else keys
    )
    result[UNIT_SHARE_COLUMN] = held_unit_shares(share_groups, owned)
    return result.reset_index(drop=True)


# 상태가 바뀔 수 있는 날은 정해져 있다. 판정이 보는 컬럼이 그것뿐이기 때문이다 —
# `반입일정`·`Qual일정`·`정지일정`·`반출/이설일정` 은 그날 `le` 로 넘어가고, 비가동은 `시작일` 에
# 켜져 `종료일` 다음 날 꺼진다. 다른 날에는 같은 판정이 나오므로 샘플링할 이유가 없다. 실적은
# 판정이 보지 않는다(집계는 일정 기준) — 넣지 않는다.
_TIMELINE_EVENT_COLUMNS = (
    ARRIVAL_DATE_COLUMN,
    QUAL_DATE_COLUMN,
    STOP_DATE_COLUMN,
    RELOCATION_DATE_COLUMN,
)
# 그 가운데 설비가 나가는 날(판정의 `exited` 와 「정지」→「반출/이설 완료」). 세는 구간이 이 날에
# 닿는 경계를 따로 적는다.
_EXIT_DATE_COLUMNS = EXIT_SCHEDULE_COLUMNS

# 단계 전환 표가 반출/이설 전환의 이전 단계를 가를 때 잠깐 쓰는 칸.
_STOPPED_ON = "_정지일"

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
    형제의 입고·정지로 지분이 바뀌면 상태는 그대로여도 대수 축 몫이 달라지고, 정지일정이 적힌
    호기는 셋업 중·Qual 후가 모두 「정지 예정」 한 이름이라 이름으로만 끊으면 가용이 된 날을
    잃는다. 월별 대수(`monthly_equipment_availability`)가 켜서 쓴다. 끄면(기본) 상태 이름이
    바뀔 때만 끊어 생애주기 Gantt 가 지금처럼 그린다.

    켜면 `반출이설시작`·`반출이설직전` 도 붙인다 — 구간 시작일, 또는 종료일 다음 날이 그 설비키의
    정지일정·반출/이설일정인가. **구간의 날짜는 그대로 상태가 바뀐 날이다**(Gantt 와 같다). 월별
    기여는 바뀐 다음 날부터지만 정지·반출/이설로 가용을 잃는 것은 그날부터라(2026-10-08 사용자
    결정) 월별이 이 표시를 보고 그 경계만 밀지 않는다. 설비키 단위로 보는 것은 모듈 하나가 나가는
    날 형제의 지분도 같이 바뀌기 때문이다 — 나간 모듈만 당일로 두고 형제의 지분 경계를 다음 날로
    밀면 그날 하루 설비가 한 대보다 적게 세어진다.

    **판정 규칙을 다시 적지 않는다.** 판정할 (호기, 시점) 행을 쌓아
    `_build_equipment_status_from_prepared` 를 한 번 그대로 부르고, 이어지는 같은 상태를 한
    구간으로 묶는다(`_stacked_lifecycle_moments`). 규칙을 옮겨 적으면 이 화면만 조용히 다른
    이야기를 하게 된다 — 주차별 집계·상태 막대·Space 배치도가 모두 그 함수 하나를 본다.

    끝을 여는 구간은 `end_date` 에서 자른다. 조회 범위 밖의 일은 이 화면이 답할 것이
    아니다.
    """
    if start_date > end_date:
        raise ValueError("생애주기 조회 시작일은 종료일보다 늦을 수 없습니다.")
    columns = [
        *LIFECYCLE_SPAN_COLUMNS,
        *(
            (
                UNIT_SHARE_COLUMN,
                UNIT_KEY_COLUMN,
                COUNT_CATEGORY_COLUMN,
                COUNTED_COLUMN,
                EXIT_STARTS_COLUMN,
                EXIT_FOLLOWS_COLUMN,
            )
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

    stacked, moments = _stacked_lifecycle_moments(prepared, prepared_downtime, start=start, end=end)
    status_frame = _build_equipment_status_from_prepared(stacked, prepared_downtime, as_of=moments)
    shares = (
        status_frame[UNIT_SHARE_COLUMN].round(UNIT_COUNT_DECIMALS + 3)
        if with_unit_share
        else pd.Series(1.0, index=status_frame.index)
    )
    # Gantt(끈 쪽)는 이름만 본다 — 집계분류를 이름으로 채우면 끊는 자리가 지금과 같다.
    categories = status_frame[COUNT_CATEGORY_COLUMN] if with_unit_share else status_frame["상태"]
    # 쌓은 행은 시점 차례, 같은 시점 안에서는 마스터 차례다.
    for unit, moment, status, category, share in zip(
        status_frame[EQUIPMENT_ID_COLUMN],
        moments,
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
        keys = unit_keys(prepared)
        key_by_unit = dict(zip(prepared[EQUIPMENT_ID_COLUMN], keys, strict=True))
        result[UNIT_KEY_COLUMN] = result[EQUIPMENT_ID_COLUMN].map(key_by_unit)
        # 사용기준은 날짜와 상관없는 호기 속성이라 구간을 끊지 않는다. 호기마다 한 번 매긴다.
        counted_by_unit = dict(
            zip(prepared[EQUIPMENT_ID_COLUMN], counts_for_capacity(prepared), strict=True)
        )
        result[COUNTED_COLUMN] = (
            result[EQUIPMENT_ID_COLUMN].map(counted_by_unit).fillna(False).astype("bool")
        )
        exit_days = _exit_days_by_key(prepared, keys)
        unit_exits = [exit_days.get(str(key), frozenset()) for key in result[UNIT_KEY_COLUMN]]
        result[EXIT_STARTS_COLUMN] = pd.Series(
            [began in days for began, days in zip(result["시작일"], unit_exits, strict=True)],
            index=result.index,
            dtype="bool",
        )
        result[EXIT_FOLLOWS_COLUMN] = pd.Series(
            [
                finished + timedelta(days=1) in days
                for finished, days in zip(result["종료일"], unit_exits, strict=True)
            ],
            index=result.index,
            dtype="bool",
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
    moments.update(_lifecycle_change_days(prepared, prepared_downtime)[_MOMENT_COLUMN].tolist())
    return sorted(moment for moment in moments if start <= moment <= end)


def _lifecycle_change_days(prepared: pd.DataFrame, prepared_downtime: pd.DataFrame) -> pd.DataFrame:
    """설비키마다 판정이 달라질 수 있는 날(`설비키`·`_시점`, 같은 쌍은 한 번).

    일정 컬럼 넷의 날짜와 비가동 시작일·종료일 다음 날이다(`_TIMELINE_EVENT_COLUMNS` 의 주석).
    호기가 아니라 설비키로 모으는 것은 모듈 하나의 입고·정지·반출이 형제의 지분도 바꾸기
    때문이다 — 비가동은 설비명을 그 설비키로 옮긴다(비가동 설비명은 마스터에 있다고 검증됐다).
    """
    keys = unit_keys(prepared)
    parts = [
        pd.DataFrame({UNIT_KEY_COLUMN: keys, _MOMENT_COLUMN: prepared[column]})
        for column in _TIMELINE_EVENT_COLUMNS
    ]
    if not prepared_downtime.empty:
        key_by_unit = pd.Series(keys.to_numpy(), index=prepared[EQUIPMENT_ID_COLUMN].to_numpy())
        downtime_keys = prepared_downtime[EQUIPMENT_ID_COLUMN].map(key_by_unit)
        parts.append(
            pd.DataFrame(
                {UNIT_KEY_COLUMN: downtime_keys, _MOMENT_COLUMN: prepared_downtime["시작일"]}
            )
        )
        parts.append(
            pd.DataFrame(
                {
                    UNIT_KEY_COLUMN: downtime_keys,
                    _MOMENT_COLUMN: prepared_downtime["종료일"] + pd.Timedelta(days=1),
                }
            )
        )
    days = pd.concat(parts, ignore_index=True).dropna(subset=[_MOMENT_COLUMN])
    return pd.DataFrame(
        {
            UNIT_KEY_COLUMN: days[UNIT_KEY_COLUMN].astype("string"),
            _MOMENT_COLUMN: pd.to_datetime(days[_MOMENT_COLUMN]),
        }
    ).drop_duplicates(ignore_index=True)


def _stacked_lifecycle_moments(
    prepared: pd.DataFrame,
    prepared_downtime: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.Series]:
    """생애주기 구간이 판정할 (호기, 시점) 행과 행마다의 시점.

    조회 시작일에는 모든 호기를, 그 뒤 바뀔 수 있는 날(`_lifecycle_breakpoints` 와 같은 날)마다
    **그날 일정·비가동 경계가 걸린 설비키 묶음의 호기만** 쌓는다. 판정이 보는 것은 자기 행의
    날짜·자기 비가동·같은 설비키 형제의 보유뿐이라, 그날 아무것도 걸리지 않은 묶음은 앞 판정과
    같은 답이 나와 구간을 끊지 않는다 — 날마다 모든 호기를 다시 판정하면 비용이 (바뀌는 날 수 ×
    호기 수)로 커진다. 한 날에 걸린 설비키는 형제 행을 모두 쌓아 그날의 지분 묶음이 온전하다.

    행은 시점 차례, 같은 시점 안에서는 마스터 차례다. 시점 Series 의 index 는 쌓은 표와 같다.
    """
    days = _lifecycle_change_days(prepared, prepared_downtime)
    later = days.loc[days[_MOMENT_COLUMN].gt(start) & days[_MOMENT_COLUMN].le(end)]
    positions = pd.DataFrame(
        {UNIT_KEY_COLUMN: unit_keys(prepared).array, "_위치": range(len(prepared))}
    )
    later_rows = later.merge(positions, on=UNIT_KEY_COLUMN).sort_values(
        [_MOMENT_COLUMN, "_위치"], kind="stable"
    )
    stacked = prepared.iloc[[*range(len(prepared)), *later_rows["_위치"].tolist()]].reset_index(
        drop=True
    )
    moments = pd.Series(start, index=range(len(prepared)), dtype="datetime64[ns]")
    if not later_rows.empty:
        moments = pd.concat([moments, later_rows[_MOMENT_COLUMN]], ignore_index=True)
    return stacked, moments


def _exit_days_by_key(prepared: pd.DataFrame, keys: pd.Series) -> dict[str, frozenset[date]]:
    """설비키마다 정지·반출/이설일정. 모듈 하나가 나가는 날 형제의 지분도 바뀌어 묶음 단위로
    모은다."""
    days: dict[str, set[date]] = {}
    for column in _EXIT_DATE_COLUMNS:
        present = prepared[column].notna().to_numpy()
        for key, moment in zip(
            keys.loc[present], pd.to_datetime(prepared.loc[present, column]), strict=True
        ):
            days.setdefault(str(key), set()).add(moment.date())
    return {key: frozenset(found) for key, found in days.items()}


def build_weekly_equipment_availability(
    baseline: pd.DataFrame,
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    *,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """ISO 주차·공정소분류별 총대수·가용대수·비가동대수와 분류 대수(각 주 일요일 판정).

    설비 마스터 쪽은 **사용기준이 HBM·EDP 인 행만** 센다(`equipment_contract.counts_for_capacity`).
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
        # 사용기준이 HBM·EDP 가 아닌 행은 지분을 0 으로 본다(`counts_for_capacity`). 가용만 빼면
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
        # 분류 대수는 상태 이름이 아니라 집계분류로 센다 — 실행일 전의 정지·반출/이설 예정 호기가
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
    return inactive_equipment_rows(build_equipment_status_as_of(equipment, downtime, as_of=as_of))


def inactive_equipment_rows(status: pd.DataFrame) -> pd.DataFrame:
    """시점 표에서 비가동 호기(보유 & ~가용)만. 시점 보기와 「그 달 전체」가 같은 술어를 쓴다."""
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
    정지일정이 적힌 호기는 입고 전·셋업 중·Qual 후가 모두 「정지 예정」 한 구간이라 입고일
    ·Qual일에 경계가 생기지 않는다. 그 호기의 비가동 구간이 한 주보다 짧고 일요일을 비껴
    가면 이름 화이트리스트와 똑같이 통째로 빠진다.

    설비 마스터가 비면 월초와 일요일만 남는다. 그 시점들로 재도 결과는 빈 표라 화면이
    답을 못 내는 일은 없다.
    """
    prepared = prepare_equipment_master(equipment)
    prepared_downtime = (
        None if prepared.empty else prepare_downtime_for_prepared_equipment(downtime, prepared)
    )
    return _inactive_moments_from_prepared(prepared, prepared_downtime, month=month)


def _inactive_moments_from_prepared(
    prepared: pd.DataFrame,
    prepared_downtime: pd.DataFrame | None,
    *,
    month: date,
) -> list[date]:
    """`inactive_equipment_moments` 의 본문. 검증을 마친 두 표를 받는다(마스터가 비면 비가동은
    보지 않는다 — `None` 이어도 된다)."""
    month_start, month_end = _month_bounds(month)
    moments = {month_start}
    if not prepared.empty and prepared_downtime is not None:
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
    위쪽을 덮는다 — 셋업 중인 호기에 정지일정이 적혀 있으면 상태는 「정지 예정」이 되므로
    「운영 비가동」·「셋업 진행중」을 이름으로 골라 세는 집계는 그 호기를 통째로 잃는다.
    이름 목록은 사다리가 한 칸 늘 때마다 조용히 틀려지기도 한다. 그래서 시점 표와 **같은
    술어**(`build_inactive_equipment` = 보유 & ~가용)를 `inactive_equipment_moments` 의
    시점마다 다시 물어 `설비명` 으로 union 한다.

    `month` 는 그 달의 아무 날짜라도 된다(기준일을 그대로 넘긴다). `moments` 를 주면 그
    시점 집합을 그대로 쓴다 — 화면이 캡션에 적는 시점 개수와 실제로 잰 시점이 어긋나지
    않게 하려는 것이다.

    결과는 시점 표와 같은 컬럼의 `설비명` 바로 뒤에 `비가동 시작`·`비가동 종료`를 붙인 것이다.
    이 둘은 구간의 실제 시작·끝이 아니라 **그 호기가 비가동으로 잡힌 시점의 최소·최대**다.

    마스터·비가동 검증(`prepare_*`)은 **한 번만** 하고 시점마다 판정만 다시 한다 — 시점마다
    `build_inactive_equipment` 를 부르면 같은 검증을 시점 수(한 달 30여 개)만큼 되풀이한다.
    판정 함수는 받은 표를 고치지 않으므로(`prepared.copy()` 로 시작) 결과가 같다.
    """
    prepared = prepare_equipment_master(equipment)
    prepared_downtime = prepare_downtime_for_prepared_equipment(downtime, prepared)
    if moments is None:
        moments = _inactive_moments_from_prepared(prepared, prepared_downtime, month=month)
    return _inactive_in_month_from_prepared(
        prepared, prepared_downtime, month=month, moments=moments
    )


def build_inactive_equipment_month_view(
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    *,
    month: date,
) -> tuple[list[date], pd.DataFrame]:
    """Main 「비가동 호기 › 그 달 전체」 한 벌 — (잰 시점, 그 달 비가동 호기).

    `inactive_equipment_moments` 와 `build_inactive_equipment_in_month(moments=)` 를 차례로 부른
    것과 같다. 검증을 한 번만 하고 두 결과가 같은 시점 집합을 쓴다(캡션의 시점 개수와 실제로 잰
    시점이 어긋나지 않게). 결과는 그 달(년·월)과 두 표로만 정해진다 — 같은 달의 다른 날을 넘겨도
    같다.
    """
    prepared = prepare_equipment_master(equipment)
    prepared_downtime = prepare_downtime_for_prepared_equipment(downtime, prepared)
    moments = _inactive_moments_from_prepared(prepared, prepared_downtime, month=month)
    inactive = _inactive_in_month_from_prepared(
        prepared, prepared_downtime, month=month, moments=moments
    )
    return moments, inactive


def _inactive_in_month_from_prepared(
    prepared: pd.DataFrame,
    prepared_downtime: pd.DataFrame,
    *,
    month: date,
    moments: Sequence[date],
) -> pd.DataFrame:
    """`build_inactive_equipment_in_month` 의 본문. 검증을 마친 두 표를 받는다."""
    sampled = sorted(set(moments)) or [_month_bounds(month)[0]]
    stacked = pd.concat(
        [
            inactive_equipment_rows(
                _build_equipment_status_from_prepared(
                    prepared, prepared_downtime, as_of=pd.Timestamp(moment)
                )
            ).assign(**{_MOMENT_COLUMN: moment})
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
    prepared = prepare_equipment_master(equipment)
    return build_space_equipment_status_from_prepared(
        prepared, prepare_downtime_for_prepared_equipment(downtime, prepared), as_of=as_of
    )


def build_space_equipment_status_from_prepared(
    prepared: pd.DataFrame,
    prepared_downtime: pd.DataFrame,
    *,
    as_of: date,
) -> pd.DataFrame:
    """`build_space_equipment_status` 의 검증 뒤 몫 — 검증을 마친 설비 마스터·비가동 일정으로 기준일
    상태를 만든다. Space 기준일 페이더처럼 기준일만 바뀌는 회차는 검증을 다시 하지 않는다
    (`simulation_cache.get_space_equipment_status` 가 검증 결과를 내용 지문으로 다시 쓴다)."""
    result = _build_equipment_status_from_prepared(
        prepared, prepared_downtime, as_of=pd.Timestamp(as_of)
    )
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
    # 정지일정은 다른 이름으로 한 번 더 싣는다 — 반출/이설 전환의 이전 단계가 「정지」인지 가른다.
    # 녹이는(`melt`) 날짜 컬럼과 이름이 같으면 안 된다. 정지일정 = 반출/이설일정인 행은 그날 바로
    # 「반출/이설 완료」라(전날은 「정지 예정」) 정지 단계를 거치지 않는다 — 정지 전환을 빼고
    # 「가용/보관 → 반출/이설」 한 건으로 둔다. 두면 한 대가 그날 두 번 세어진다.
    stop_dates = prepared[STOP_DATE_COLUMN]
    same_day = stop_dates.notna() & stop_dates.eq(prepared[RELOCATION_DATE_COLUMN])
    prepared = prepared.assign(
        **{_STOPPED_ON: stop_dates, STOP_DATE_COLUMN: stop_dates.mask(same_day)}
    )
    identity_columns = [
        EQUIPMENT_ID_COLUMN,
        "공정대분류",
        "공정소분류",
        "동",
        "층",
        QUAL_STATUS_COLUMN,
        _STOPPED_ON,
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
        QUAL_DATE_COLUMN: "입고",
        STOP_DATE_COLUMN: "가용/보관",
        RELOCATION_DATE_COLUMN: "가용/보관",
    }
    order = {column: index for index, column in enumerate(date_columns)}
    events["단계순서"] = events["단계컬럼"].map(order).astype("int64")
    events["이전단계"] = events["단계컬럼"].map(previous_stage).astype("string")
    events["전환단계"] = events["단계컬럼"].map(stage_by_column).astype("string")
    events["전환일"] = pd.to_datetime(events["전환일"], errors="raise")
    # 정지한 뒤(전날까지) 자리를 비우는 호기는 반출/이설 전환의 이전 단계가 「정지」다.
    stopped_first = events["단계컬럼"].eq(RELOCATION_DATE_COLUMN) & pd.to_datetime(
        events[_STOPPED_ON]
    ).lt(events["전환일"]).fillna(False).astype("bool")
    events.loc[stopped_first, "이전단계"] = stage_by_column[STOP_DATE_COLUMN]
    # Qual상태는 Qual 단계에만 뜻이 있다. 다른 단계는 결측으로 두는데, 결측을 그대로
    # 넘기면 표에 "None" 이라는 글자가 찍혀 값이 있는 것처럼 보인다. 빈 칸으로 만든다.
    events[QUAL_STATUS_COLUMN] = (
        events[QUAL_STATUS_COLUMN]
        .astype("string")
        .where(events["단계컬럼"].eq(QUAL_DATE_COLUMN))
        .fillna("")
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


def _active_downtime_by_row(
    equipment: pd.DataFrame, downtime: pd.DataFrame, moments: pd.Series
) -> pd.Series:
    """행마다 그 행의 시점에 걸린 비가동유형(없으면 NA).

    `_active_downtime` 과 같은 창(시작일 ≤ 시점, 종료일이 없거나 ≥ 시점)이고, 유형은 비가동 표
    차례로 잇는다 — 시점 하나로 판정할 때 설비명마다 묶어 잇는 차례와 같다.
    """
    if downtime.empty:
        return pd.Series(pd.NA, index=equipment.index, dtype="string")
    rows = pd.DataFrame(
        {
            "_행": range(len(equipment)),
            EQUIPMENT_ID_COLUMN: equipment[EQUIPMENT_ID_COLUMN].astype("string").to_numpy(),
            _MOMENT_COLUMN: moments.to_numpy(),
        }
    )
    windows = pd.DataFrame(
        {
            EQUIPMENT_ID_COLUMN: downtime[EQUIPMENT_ID_COLUMN].astype("string").to_numpy(),
            "비가동유형": downtime["비가동유형"].to_numpy(),
            "시작일": downtime["시작일"].to_numpy(),
            "종료일": downtime["종료일"].to_numpy(),
            "_차례": range(len(downtime)),
        }
    )
    joined = rows.merge(windows, on=EQUIPMENT_ID_COLUMN)
    moment = joined[_MOMENT_COLUMN]
    active = joined["시작일"].le(moment) & (joined["종료일"].isna() | joined["종료일"].ge(moment))
    reasons = (
        joined.loc[active]
        .sort_values(["_행", "_차례"], kind="stable")
        .groupby("_행")["비가동유형"]
        .agg(_joined_unique)
    )
    return pd.Series(
        reasons.reindex(range(len(equipment))).to_numpy(), index=equipment.index
    ).astype("string")


def _joined_unique(values: pd.Series) -> str:
    return ", ".join(values.astype("string").drop_duplicates().tolist())


def _format_day_difference(days: int) -> str:
    if days == 0:
        return "D-Day"
    if days > 0:
        return f"D-{days}"
    return f"D+{-days}"
