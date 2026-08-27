"""Equipment schedule validation and weekly availability aggregation."""

from __future__ import annotations

from datetime import date

import pandas as pd

BASELINE_COLUMNS = ("공정", "분류", "기존보유대수", "비고")
SCHEDULE_COLUMNS = (
    "호기",
    "공정",
    "분류",
    "입고일",
    "셋업시작일",
    "셋업완료일",
    "비고",
)
WEEKLY_COLUMNS = (
    "Weeknum",
    "주차시작일",
    "주차종료일",
    "공정",
    "분류",
    "기존보유대수",
    "추가설비대수",
    "총대수",
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


def empty_equipment_schedule() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "호기": pd.Series(dtype="string"),
            "공정": pd.Series(dtype="string"),
            "분류": pd.Series(dtype="string"),
            "입고일": pd.Series(dtype="datetime64[ns]"),
            "셋업시작일": pd.Series(dtype="datetime64[ns]"),
            "셋업완료일": pd.Series(dtype="datetime64[ns]"),
            "비고": pd.Series(dtype="string"),
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
    """Normalize and validate the aggregate count that predates unit schedules."""
    _require_columns(data, BASELINE_COLUMNS, "기존 보유대수")
    result = data.loc[:, BASELINE_COLUMNS].copy()
    result = _drop_blank_rows(result, ("공정", "분류", "기존보유대수"))
    if result.empty:
        return empty_equipment_baseline()

    _normalize_required_text(result, ("공정", "분류"), "기존 보유대수")
    counts = pd.to_numeric(result["기존보유대수"], errors="coerce")
    valid_counts = counts.notna() & counts.ge(0)
    if not valid_counts.all():
        raise ValueError("기존보유대수는 0 이상의 숫자여야 합니다.")
    result["기존보유대수"] = counts.astype("float64")
    result["비고"] = _optional_text(result["비고"])
    duplicated = result.duplicated(["공정", "분류"], keep=False)
    if duplicated.any():
        examples = _key_examples(result.loc[duplicated], ("공정", "분류"))
        raise ValueError(f"기존 보유대수의 공정·분류가 중복되었습니다: {examples}")
    return result.reset_index(drop=True)


def prepare_equipment_schedule(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize and validate equipment-level arrival and setup dates."""
    _require_columns(data, SCHEDULE_COLUMNS, "설비호기 일정")
    result = data.loc[:, SCHEDULE_COLUMNS].copy()
    result = _drop_blank_rows(result, ("호기", "공정", "분류", "입고일"))
    if result.empty:
        return empty_equipment_schedule()

    _normalize_required_text(result, ("호기", "공정", "분류"), "설비호기 일정")
    result["비고"] = _optional_text(result["비고"])
    duplicated = result["호기"].duplicated(keep=False)
    if duplicated.any():
        examples = result.loc[duplicated, "호기"].drop_duplicates().head(5).tolist()
        raise ValueError(f"호기는 중복될 수 없습니다: {examples}")

    for column in ("입고일", "셋업시작일", "셋업완료일"):
        result[column] = _normalize_date(result[column], column)
    if result["입고일"].isna().any():
        raise ValueError("모든 설비호기에 입고일을 입력해야 합니다.")

    start_before_arrival = result["셋업시작일"].notna() & result["셋업시작일"].lt(result["입고일"])
    complete_before_arrival = result["셋업완료일"].notna() & result["셋업완료일"].lt(
        result["입고일"]
    )
    complete_before_start = (
        result["셋업시작일"].notna()
        & result["셋업완료일"].notna()
        & result["셋업완료일"].lt(result["셋업시작일"])
    )
    invalid = start_before_arrival | complete_before_arrival | complete_before_start
    if invalid.any():
        examples = result.loc[invalid, "호기"].head(5).tolist()
        raise ValueError(f"입고일·셋업시작일·셋업완료일의 순서가 올바르지 않습니다: {examples}")
    return result.reset_index(drop=True)


def build_weekly_equipment_availability(
    baseline: pd.DataFrame,
    schedule: pd.DataFrame,
    *,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Aggregate counts by ISO Weeknum, using Monday through Sunday."""
    if start_date > end_date:
        raise ValueError("주차별 조회 시작일은 종료일보다 늦을 수 없습니다.")
    prepared_baseline = prepare_equipment_baseline(baseline)
    prepared_schedule = prepare_equipment_schedule(schedule)
    groups = pd.concat(
        [
            prepared_baseline.loc[:, ["공정", "분류"]],
            prepared_schedule.loc[:, ["공정", "분류"]],
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
        arrived = prepared_schedule.loc[prepared_schedule["입고일"].le(week_end)]
        available = arrived.loc[arrived["셋업완료일"].notna() & arrived["셋업완료일"].le(week_end)]
        arrived_counts = arrived.groupby(["공정", "분류"]).size()
        available_counts = available.groupby(["공정", "분류"]).size()
        for process, classification in groups.itertuples(index=False, name=None):
            key = (process, classification)
            base_count = float(baseline_counts.get(key, 0.0))
            additional_count = int(arrived_counts.get(key, 0))
            available_additions = int(available_counts.get(key, 0))
            total_count = base_count + additional_count
            available_count = base_count + available_additions
            rows.append(
                {
                    "Weeknum": weeknum,
                    "주차시작일": week_start.date(),
                    "주차종료일": week_end.date(),
                    "공정": str(process),
                    "분류": str(classification),
                    "기존보유대수": base_count,
                    "추가설비대수": additional_count,
                    "총대수": total_count,
                    "가용대수": available_count,
                    "비가동대수": total_count - available_count,
                }
            )
    return pd.DataFrame(rows, columns=WEEKLY_COLUMNS)


def build_inactive_equipment(schedule: pd.DataFrame, *, as_of: date) -> pd.DataFrame:
    """Return arrived equipment that has not completed setup at the given date."""
    prepared = prepare_equipment_schedule(schedule)
    if prepared.empty:
        result = prepared.copy()
        result.insert(3, "상태", pd.Series(dtype="string"))
        return result
    timestamp = pd.Timestamp(as_of)
    arrived = prepared["입고일"].le(timestamp)
    inactive = prepared["셋업완료일"].isna() | prepared["셋업완료일"].gt(timestamp)
    result = prepared.loc[arrived & inactive].copy()
    setup_started = result["셋업시작일"].notna() & result["셋업시작일"].le(timestamp)
    result.insert(3, "상태", setup_started.map({True: "셋업 진행 중", False: "셋업 대기"}))
    return result.reset_index(drop=True)


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
