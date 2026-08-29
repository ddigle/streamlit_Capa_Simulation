"""Equipment input validation, weekly availability, and space-stage status."""

from __future__ import annotations

from datetime import date

import pandas as pd

BASELINE_COLUMNS = ("공정", "분류", "기존보유대수", "비고")
EQUIPMENT_COLUMNS = (
    "호기",
    "공정",
    "분류",
    "동",
    "층",
    "X",
    "Y",
    "너비",
    "사전인프라완료일",
    "입고일",
    "Hookup완료일",
    "하드웨어셋업완료일",
    "Qual완료일",
    "TTTM완료일",
    "양산전환일",
    "비고",
)
DOWNTIME_COLUMNS = (
    "비가동ID",
    "호기",
    "비가동유형",
    "시작일",
    "종료일",
    "상세사유",
    "비고",
)
MILESTONES = (
    ("사전인프라완료일", "사전 인프라"),
    ("입고일", "입고"),
    ("Hookup완료일", "Hookup"),
    ("하드웨어셋업완료일", "H/W 셋업"),
    ("Qual완료일", "Qual"),
    ("TTTM완료일", "TTTM"),
    ("양산전환일", "양산"),
)
TRANSITION_EVENT_COLUMNS = (
    "호기",
    "공정",
    "분류",
    "동",
    "층",
    "이전단계",
    "전환단계",
    "전환일",
    "일정상태",
    "기준일대비",
)
DOWNTIME_TYPES = ("개발대여", "공사", "고장", "이설", "기타")
WEEKLY_COLUMNS = (
    "Weeknum",
    "주차시작일",
    "주차종료일",
    "공정",
    "분류",
    "기존보유대수",
    "추가설비대수",
    "총대수",
    "양산전환대수",
    "셋업중대수",
    "운영비가동대수",
    "가용대수",
    "비가동대수",
)
SAMPLE_BASELINE_COUNTS = (
    ("Pre B/D", 46.0),
    ("Wafer_Sorter", 18.0),
    ("AVI-CoW", 21.0),
    ("Laser Grooving", 16.0),
    ("Wafer Grinding", 14.0),
    ("Wafer Mount", 12.0),
    ("Wafer Saw", 19.0),
    ("Plasma Clean", 25.0),
    ("DAF Attach", 35.0),
    ("Die Attach", 42.0),
    ("TC Bonding", 51.0),
    ("Mass Reflow", 18.0),
    ("Underfill", 38.0),
    ("Mold", 27.0),
    ("Cure", 13.0),
    ("Laser Marking", 15.0),
    ("Ball Attach", 32.0),
    ("Flux Clean", 17.0),
    ("Singulation", 29.0),
    ("Package Sorter", 20.0),
    ("Burn-In", 48.0),
    ("Final Test", 44.0),
    ("AVI-PKG", 23.0),
    ("O/S Test", 18.0),
    ("Taping", 16.0),
    ("Packing", 12.0),
    ("X-Ray", 26.0),
    ("SAM", 22.0),
    ("Warpage", 19.0),
    ("Shipping Inspection", 10.0),
)


def empty_equipment_baseline() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "공정": pd.Series(dtype="string"),
            "분류": pd.Series(dtype="string"),
            "기존보유대수": pd.Series(dtype="float64"),
            "비고": pd.Series(dtype="string"),
        }
    )


def empty_equipment_master() -> pd.DataFrame:
    date_columns = {column for column, _ in MILESTONES}
    return pd.DataFrame(
        {
            column: pd.Series(
                dtype=(
                    "datetime64[ns]"
                    if column in date_columns
                    else "float64"
                    if column in {"X", "Y", "너비"}
                    else "string"
                )
            )
            for column in EQUIPMENT_COLUMNS
        }
    )


def empty_downtime_schedule() -> pd.DataFrame:
    return pd.DataFrame(
        {
            column: pd.Series(
                dtype="datetime64[ns]" if column in {"시작일", "종료일"} else "string"
            )
            for column in DOWNTIME_COLUMNS
        }
    )


def sample_equipment_baseline() -> pd.DataFrame:
    """Return a detached baseline copied from the development Core Data sample."""
    return pd.DataFrame(
        {
            "공정": pd.Series(
                [process for process, _ in SAMPLE_BASELINE_COUNTS],
                dtype="string",
            ),
            "분류": pd.Series(["전체"] * len(SAMPLE_BASELINE_COUNTS), dtype="string"),
            "기존보유대수": pd.Series(
                [count for _, count in SAMPLE_BASELINE_COUNTS],
                dtype="float64",
            ),
            "비고": pd.Series(
                ["Core Data 개발 샘플"] * len(SAMPLE_BASELINE_COUNTS),
                dtype="string",
            ),
        }
    )


def prepare_equipment_baseline(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize and validate aggregate counts for unidentified legacy equipment."""
    _require_columns(data, BASELINE_COLUMNS, "기존 보유대수")
    result = data.loc[:, BASELINE_COLUMNS].copy()
    result = _drop_blank_rows(result, ("공정", "분류", "기존보유대수"))
    if result.empty:
        return empty_equipment_baseline()

    _normalize_required_text(result, ("공정", "분류"), "기존 보유대수")
    counts = pd.to_numeric(result["기존보유대수"], errors="coerce")
    if not (counts.notna() & counts.ge(0)).all():
        raise ValueError("기존보유대수는 0 이상의 숫자여야 합니다.")
    result["기존보유대수"] = counts.astype("float64")
    result["비고"] = _optional_text(result["비고"])
    duplicated = result.duplicated(["공정", "분류"], keep=False)
    if duplicated.any():
        examples = _key_examples(result.loc[duplicated], ("공정", "분류"))
        raise ValueError(f"기존 보유대수의 공정·분류가 중복되었습니다: {examples}")
    return result.reset_index(drop=True)


def prepare_equipment_master(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize and validate equipment milestones and space coordinates."""
    _require_columns(data, EQUIPMENT_COLUMNS, "호기 마스터")
    result = data.loc[:, EQUIPMENT_COLUMNS].copy()
    result = _drop_blank_rows(result, ("호기",))
    if result.empty:
        return empty_equipment_master()

    _normalize_required_text(result, ("호기", "공정", "분류"), "호기 마스터")
    for column in ("동", "층", "비고"):
        result[column] = _optional_text(result[column])
    duplicated = result["호기"].duplicated(keep=False)
    if duplicated.any():
        examples = result.loc[duplicated, "호기"].drop_duplicates().head(5).tolist()
        raise ValueError(f"호기는 중복될 수 없습니다: {examples}")

    for column in ("X", "Y", "너비"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    coordinate_present = result.loc[:, ["X", "Y", "너비"]].notna()
    incomplete_coordinates = coordinate_present.any(axis=1) & ~coordinate_present.all(axis=1)
    if incomplete_coordinates.any():
        examples = result.loc[incomplete_coordinates, "호기"].head(5).tolist()
        raise ValueError(f"Space 좌표 X·Y·너비는 함께 입력해야 합니다: {examples}")
    invalid_coordinates = coordinate_present.all(axis=1) & (
        result["X"].lt(0)
        | result["X"].gt(100)
        | result["Y"].lt(0)
        | result["Y"].gt(60)
        | result["너비"].le(0)
        | result["X"].add(result["너비"]).gt(100)
    )
    if invalid_coordinates.any():
        examples = result.loc[invalid_coordinates, "호기"].head(5).tolist()
        raise ValueError(f"Space 좌표는 X 0~100, Y 0~60 범위 안에 있어야 합니다: {examples}")

    milestone_columns = tuple(column for column, _ in MILESTONES)
    for column in milestone_columns:
        result[column] = _normalize_date(result[column], column)
    invalid_order = _invalid_milestone_order(result, milestone_columns)
    if invalid_order.any():
        examples = result.loc[invalid_order, "호기"].head(5).tolist()
        raise ValueError(f"설비 단계 완료일의 순서가 올바르지 않습니다: {examples}")
    return result.reset_index(drop=True)


def prepare_downtime_schedule(
    data: pd.DataFrame,
    *,
    equipment: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Normalize and validate equipment downtime intervals."""
    _require_columns(data, DOWNTIME_COLUMNS, "비가동 일정")
    result = data.loc[:, DOWNTIME_COLUMNS].copy()
    result = _drop_blank_rows(result, ("비가동ID", "호기", "비가동유형", "시작일"))
    if result.empty:
        return empty_downtime_schedule()

    _normalize_required_text(result, ("비가동ID", "호기", "비가동유형"), "비가동 일정")
    for column in ("상세사유", "비고"):
        result[column] = _optional_text(result[column])
    duplicated = result["비가동ID"].duplicated(keep=False)
    if duplicated.any():
        examples = result.loc[duplicated, "비가동ID"].drop_duplicates().head(5).tolist()
        raise ValueError(f"비가동ID는 중복될 수 없습니다: {examples}")
    result["시작일"] = _normalize_date(result["시작일"], "시작일")
    result["종료일"] = _normalize_date(result["종료일"], "종료일")
    if result["시작일"].isna().any():
        raise ValueError("모든 비가동 일정에 시작일을 입력해야 합니다.")
    invalid_end = result["종료일"].notna() & result["종료일"].lt(result["시작일"])
    if invalid_end.any():
        examples = result.loc[invalid_end, "비가동ID"].head(5).tolist()
        raise ValueError(f"비가동 종료일은 시작일보다 빠를 수 없습니다: {examples}")
    if equipment is not None:
        prepared_equipment = prepare_equipment_master(equipment)
        unknown = result.loc[~result["호기"].isin(prepared_equipment["호기"]), "호기"]
        if not unknown.empty:
            examples = unknown.drop_duplicates().head(5).tolist()
            raise ValueError(f"호기 마스터에 없는 설비의 비가동 일정이 있습니다: {examples}")
    return result.reset_index(drop=True)


def build_weekly_equipment_availability(
    baseline: pd.DataFrame,
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    *,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Aggregate week-end equipment status by ISO Weeknum."""
    if start_date > end_date:
        raise ValueError("주차별 조회 시작일은 종료일보다 늦을 수 없습니다.")
    prepared_baseline = prepare_equipment_baseline(baseline)
    prepared_equipment = prepare_equipment_master(equipment)
    prepared_downtime = prepare_downtime_schedule(downtime, equipment=prepared_equipment)
    groups = pd.concat(
        [
            prepared_baseline.loc[:, ["공정", "분류"]],
            prepared_equipment.loc[:, ["공정", "분류"]],
        ],
        ignore_index=True,
    ).drop_duplicates()
    if groups.empty:
        return pd.DataFrame(columns=WEEKLY_COLUMNS)

    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    first_monday = start - pd.Timedelta(days=start.weekday())
    last_monday = end - pd.Timedelta(days=end.weekday())
    week_starts = pd.date_range(first_monday, last_monday, freq="7D")
    baseline_counts = prepared_baseline.set_index(["공정", "분류"])["기존보유대수"]
    rows: list[dict[str, object]] = []
    for week_start in week_starts:
        week_end = week_start + pd.Timedelta(days=6)
        iso_calendar = week_start.isocalendar()
        weeknum = f"{iso_calendar.year % 100:02d}-W{iso_calendar.week:02d}"
        ownership_date = prepared_equipment["입고일"].fillna(prepared_equipment["양산전환일"])
        arrived = prepared_equipment.loc[ownership_date.notna() & ownership_date.le(week_end)]
        production = arrived.loc[arrived["양산전환일"].notna() & arrived["양산전환일"].le(week_end)]
        offline_ids = set(_active_downtime(prepared_downtime, week_end)["호기"].tolist())
        for process, classification in groups.itertuples(index=False, name=None):
            key = (process, classification)
            base_count = float(baseline_counts.get(key, 0.0))
            group_arrived = arrived.loc[
                arrived["공정"].eq(process) & arrived["분류"].eq(classification)
            ]
            group_production = production.loc[
                production["공정"].eq(process) & production["분류"].eq(classification)
            ]
            arrived_count = len(group_arrived)
            production_count = len(group_production)
            offline_count = int(group_production["호기"].isin(offline_ids).sum())
            setup_count = arrived_count - production_count
            available_count = base_count + production_count - offline_count
            rows.append(
                {
                    "Weeknum": weeknum,
                    "주차시작일": week_start.date(),
                    "주차종료일": week_end.date(),
                    "공정": str(process),
                    "분류": str(classification),
                    "기존보유대수": base_count,
                    "추가설비대수": arrived_count,
                    "총대수": base_count + arrived_count,
                    "양산전환대수": production_count,
                    "셋업중대수": setup_count,
                    "운영비가동대수": offline_count,
                    "가용대수": available_count,
                    "비가동대수": setup_count + offline_count,
                }
            )
    return pd.DataFrame(rows, columns=WEEKLY_COLUMNS)


def build_inactive_equipment(
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    *,
    as_of: date,
) -> pd.DataFrame:
    """Return arrived equipment that is preparing for production or offline."""
    prepared_equipment = prepare_equipment_master(equipment)
    prepared_downtime = prepare_downtime_schedule(downtime, equipment=prepared_equipment)
    if prepared_equipment.empty:
        return pd.DataFrame(columns=("호기", "공정", "분류", "상태", "현재단계", "비가동유형"))
    timestamp = pd.Timestamp(as_of)
    ownership_date = prepared_equipment["입고일"].fillna(prepared_equipment["양산전환일"])
    arrived = (
        prepared_equipment.loc[ownership_date.notna() & ownership_date.le(timestamp)]
        .copy()
        .reset_index(drop=True)
    )
    arrived["현재단계"] = equipment_stages_as_of(arrived, as_of=as_of)
    active_downtime = _active_downtime(prepared_downtime, timestamp)
    reason_by_equipment = active_downtime.groupby("호기")["비가동유형"].agg(_joined_unique)
    arrived["비가동유형"] = arrived["호기"].map(reason_by_equipment)
    preparing = arrived["현재단계"].ne("양산")
    offline = arrived["비가동유형"].notna()
    result = arrived.loc[preparing | offline].copy()
    result.insert(
        3,
        "상태",
        result["비가동유형"].notna().map({True: "운영 비가동", False: "양산 준비 중"}),
    )
    return result.reset_index(drop=True)


def equipment_stages_as_of(equipment: pd.DataFrame, *, as_of: date) -> pd.Series:
    """Return the latest completed milestone for every equipment row."""
    prepared = prepare_equipment_master(equipment)
    stages = pd.Series("예정", index=prepared.index, dtype="string")
    timestamp = pd.Timestamp(as_of)
    for column, label in MILESTONES:
        completed = prepared[column].notna() & prepared[column].le(timestamp)
        stages.loc[completed] = label
    return stages


def build_space_equipment_status(
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    *,
    as_of: date,
) -> pd.DataFrame:
    """Build the shared unit-level source used by the Space dashboard."""
    prepared_equipment = prepare_equipment_master(equipment)
    prepared_downtime = prepare_downtime_schedule(downtime, equipment=prepared_equipment)
    result = prepared_equipment.copy()
    if result.empty:
        result["단계"] = pd.Series(dtype="string")
        result["상태"] = pd.Series(dtype="string")
        result["비가동유형"] = pd.Series(dtype="string")
        return result
    result["단계"] = equipment_stages_as_of(prepared_equipment, as_of=as_of)
    active_downtime = _active_downtime(prepared_downtime, pd.Timestamp(as_of))
    reason_by_equipment = active_downtime.groupby("호기")["비가동유형"].agg(_joined_unique)
    result["비가동유형"] = result["호기"].map(reason_by_equipment).astype("string")
    result["상태"] = result["단계"]
    result.loc[result["비가동유형"].notna(), "상태"] = "비가동"
    return result.reset_index(drop=True)


def build_milestone_transition_events(
    equipment: pd.DataFrame,
    *,
    start_date: date,
    end_date: date,
    as_of: date,
) -> pd.DataFrame:
    """Return milestone transitions scheduled inside a selected date range."""
    if start_date > end_date:
        raise ValueError("단계 전환 조회 시작일은 종료일보다 늦을 수 없습니다.")
    prepared = prepare_equipment_master(equipment)
    if prepared.empty:
        return pd.DataFrame(columns=TRANSITION_EVENT_COLUMNS)

    milestone_columns = [column for column, _ in MILESTONES]
    identity_columns = ["호기", "공정", "분류", "동", "층"]
    events = prepared.melt(
        id_vars=identity_columns,
        value_vars=milestone_columns,
        var_name="단계컬럼",
        value_name="전환일",
    ).dropna(subset=["전환일"])
    if events.empty:
        return pd.DataFrame(columns=TRANSITION_EVENT_COLUMNS)

    stage_by_column = dict(MILESTONES)
    stage_order = {column: index for index, (column, _) in enumerate(MILESTONES)}
    previous_stage = {
        column: "착수 전" if index == 0 else MILESTONES[index - 1][1]
        for index, (column, _) in enumerate(MILESTONES)
    }
    events["단계순서"] = events["단계컬럼"].map(stage_order).astype("int64")
    events["이전단계"] = events["단계컬럼"].map(previous_stage).astype("string")
    events["전환단계"] = events["단계컬럼"].map(stage_by_column).astype("string")
    events["전환일"] = pd.to_datetime(events["전환일"], errors="raise")
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    events = events.loc[events["전환일"].between(start, end, inclusive="both")].copy()
    if events.empty:
        return pd.DataFrame(columns=TRANSITION_EVENT_COLUMNS)

    as_of_timestamp = pd.Timestamp(as_of)
    events["일정상태"] = events["전환일"].le(as_of_timestamp).map({True: "완료", False: "예정"})
    day_differences = events["전환일"].sub(as_of_timestamp).dt.days
    events["기준일대비"] = day_differences.map(_format_day_difference).astype("string")
    events = events.sort_values(["전환일", "단계순서", "공정", "호기"], kind="stable")
    return events.loc[:, TRANSITION_EVENT_COLUMNS].reset_index(drop=True)


def _active_downtime(downtime: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    if downtime.empty:
        return downtime.copy()
    active = downtime["시작일"].le(as_of) & (
        downtime["종료일"].isna() | downtime["종료일"].ge(as_of)
    )
    return downtime.loc[active].copy()


def _invalid_milestone_order(data: pd.DataFrame, columns: tuple[str, ...]) -> pd.Series:
    invalid = pd.Series(False, index=data.index)
    previous = pd.Series(pd.NaT, index=data.index, dtype="datetime64[ns]")
    for column in columns:
        current = data[column]
        invalid |= current.notna() & previous.notna() & current.lt(previous)
        previous = previous.where(current.isna(), current)
    return invalid


def _joined_unique(values: pd.Series) -> str:
    return ", ".join(values.astype("string").drop_duplicates().tolist())


def _format_day_difference(days: int) -> str:
    if days == 0:
        return "D-Day"
    if days > 0:
        return f"D-{days}"
    return f"D+{-days}"


def _require_columns(data: pd.DataFrame, columns: tuple[str, ...], label: str) -> None:
    missing = [column for column in columns if column not in data.columns]
    if missing:
        raise ValueError(f"{label} 필수 컬럼이 없습니다: {', '.join(missing)}")


def _drop_blank_rows(data: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    present = pd.DataFrame(index=data.index)
    for column in columns:
        values = data[column]
        present[column] = values.notna() & values.astype("string").str.strip().ne("")
    return data.loc[present.any(axis=1)].copy()


def _normalize_required_text(data: pd.DataFrame, columns: tuple[str, ...], label: str) -> None:
    for column in columns:
        data[column] = data[column].astype("string").str.strip()
        invalid = data[column].isna() | data[column].eq("")
        if invalid.any():
            raise ValueError(f"{label}의 {column}에 누락값이 있습니다.")


def _optional_text(series: pd.Series) -> pd.Series:
    result = series.astype("string").str.strip()
    return result.mask(result.eq(""))


def _normalize_date(series: pd.Series, label: str) -> pd.Series:
    missing = series.isna() | series.astype("string").str.strip().eq("")
    converted = pd.to_datetime(series.mask(missing), errors="coerce")
    invalid = ~missing & converted.isna()
    if invalid.any():
        examples = series.loc[invalid].head(5).tolist()
        raise ValueError(f"{label}은 날짜 형식이어야 합니다: {examples}")
    return converted.dt.normalize()


def _key_examples(data: pd.DataFrame, columns: tuple[str, ...]) -> list[str]:
    return (
        data.loc[:, columns]
        .astype("string")
        .agg(" / ".join, axis=1)
        .drop_duplicates()
        .head(5)
        .tolist()
    )
