"""Weekly standard target Capa from effective daily Capa and manual availability."""

from __future__ import annotations

import re
from datetime import date
from io import BytesIO

import pandas as pd

from capa_simulation.services.weighted_unit_capacity import (
    WEIGHTED_CAPACITY_HIERARCHY,
    effective_process_capacity_long,
)

WEEKLY_AVAILABILITY_COLUMNS = ["공정", "Weeknum", "가용대수"]
WEEK_CALENDAR_COLUMNS = ["Weeknum", "주차시작일", "주차종료일", "생산계획년월"]
_WEEK_PATTERN = re.compile(r"^(?P<year>\d{2})-W(?P<week>\d{2})$")


def build_iso_week_calendar(start_date: date, end_date: date) -> pd.DataFrame:
    """Build Monday-start ISO weeks intersecting the requested date range."""
    if start_date > end_date:
        raise ValueError("조회 시작일은 종료일보다 늦을 수 없습니다.")

    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    first_monday = start - pd.Timedelta(days=start.weekday())
    last_monday = end - pd.Timedelta(days=end.weekday())
    rows: list[dict[str, object]] = []
    for week_start in pd.date_range(first_monday, last_monday, freq="7D"):
        week_end = week_start + pd.Timedelta(days=6)
        iso_calendar = week_start.isocalendar()
        rows.append(
            {
                "Weeknum": f"{iso_calendar.year % 100:02d}-W{iso_calendar.week:02d}",
                "주차시작일": week_start.date(),
                "주차종료일": week_end.date(),
                # A cross-month week uses the month containing its Monday.
                "생산계획년월": week_start.year * 100 + week_start.month,
            }
        )
    return pd.DataFrame(rows, columns=WEEK_CALENDAR_COLUMNS)


def build_weekly_availability_template(
    processes: list[str],
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Build one editable CSV row for every process and ISO week."""
    normalized_processes = list(
        dict.fromkeys(str(process).strip() for process in processes if str(process).strip())
    )
    calendar = build_iso_week_calendar(start_date, end_date)
    if not normalized_processes or calendar.empty:
        return pd.DataFrame(columns=["공정", "Weeknum", "주차시작일", "주차종료일", "가용대수"])

    process_frame = pd.DataFrame({"공정": normalized_processes})
    template = process_frame.merge(calendar, how="cross")
    template["가용대수"] = 0.0
    return template[["공정", "Weeknum", "주차시작일", "주차종료일", "가용대수"]]


def parse_weekly_availability_csv(content: bytes) -> pd.DataFrame:
    """Parse UTF-8/CP949 manual weekly availability into a validated table."""
    if not content:
        raise ValueError("가용설비 CSV 파일이 비어 있습니다.")

    source: pd.DataFrame | None = None
    for encoding in ("utf-8-sig", "cp949"):
        try:
            source = pd.read_csv(BytesIO(content), encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    if source is None:
        raise ValueError("가용설비 CSV는 UTF-8 또는 CP949 인코딩이어야 합니다.")
    return prepare_weekly_availability(source)


def prepare_weekly_availability(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize and validate the manual process-week availability contract."""
    missing = [column for column in WEEKLY_AVAILABILITY_COLUMNS if column not in data.columns]
    if missing:
        raise ValueError(f"가용설비 CSV 필수 컬럼이 없습니다: {', '.join(missing)}")

    result = data[WEEKLY_AVAILABILITY_COLUMNS].copy()
    result = result.dropna(how="all").reset_index(drop=True)
    if result.empty:
        raise ValueError("가용설비 CSV에 입력된 행이 없습니다.")

    result["공정"] = result["공정"].astype("string").str.strip()
    result["Weeknum"] = result["Weeknum"].astype("string").str.strip().str.upper()
    if result["공정"].isna().any() or result["공정"].eq("").any():
        raise ValueError("가용설비 CSV의 공정에는 누락값을 입력할 수 없습니다.")
    if result["Weeknum"].isna().any() or result["Weeknum"].eq("").any():
        raise ValueError("가용설비 CSV의 Weeknum에는 누락값을 입력할 수 없습니다.")

    invalid_weeks = [
        weeknum for weeknum in result["Weeknum"].drop_duplicates() if not _valid_weeknum(weeknum)
    ]
    if invalid_weeks:
        raise ValueError(f"Weeknum은 YY-W## 형식의 유효한 ISO 주차여야 합니다: {invalid_weeks[:5]}")

    available = pd.to_numeric(result["가용대수"], errors="coerce")
    if available.isna().any():
        raise ValueError("가용설비 CSV의 가용대수에 숫자가 아닌 값 또는 누락값이 있습니다.")
    if available.lt(0).any():
        raise ValueError("가용설비 CSV의 가용대수는 0 이상이어야 합니다.")
    result["가용대수"] = available.astype("float64")

    duplicated = result.duplicated(["공정", "Weeknum"], keep=False)
    if duplicated.any():
        examples = result.loc[duplicated, ["공정", "Weeknum"]].drop_duplicates().head(5)
        raise ValueError(
            f"가용설비 CSV의 공정·Weeknum이 중복되었습니다: {examples.to_dict('records')}"
        )
    return result.sort_values(["공정", "Weeknum"], ignore_index=True)


def build_weekly_standard_target_capacity(
    required_equipment: pd.DataFrame,
    run_day: pd.DataFrame,
    weekly_availability: pd.DataFrame,
    start_date: date,
    end_date: date,
    detail_level: str,
) -> pd.DataFrame:
    """Calculate weekly standard daily input for each process/product classification."""
    if detail_level not in WEIGHTED_CAPACITY_HIERARCHY:
        raise ValueError(f"지원하지 않는 표준 목표 Capa 집계 수준입니다: {detail_level}")

    production_required_equipment = exclude_er_required_equipment(required_equipment)
    monthly_capacity = effective_process_capacity_long(
        production_required_equipment,
        detail_level,
    )
    level_index = WEIGHTED_CAPACITY_HIERARCHY.index(detail_level)
    hierarchy_dimensions = WEIGHTED_CAPACITY_HIERARCHY[: level_index + 1]
    display_dimensions = ["공정", "소요기준", *hierarchy_dimensions[1:]]
    result_columns = [
        "Weeknum",
        "주차시작일",
        "주차종료일",
        "생산계획년월",
        *display_dimensions,
        "원수요_부하량",
        "STEP_소요대수",
        "공정 유효 Capa",
        "RUN_DAY",
        "대당 일 Capa",
        "가용대수",
        "일 표준 가능량",
    ]
    if monthly_capacity.empty:
        return pd.DataFrame(columns=result_columns)

    prepared_run_day = _prepare_run_day(run_day)
    monthly_capacity = monthly_capacity.merge(
        prepared_run_day,
        on=["생산계획년월", "공정"],
        how="left",
        validate="many_to_one",
    )
    missing_run_day = monthly_capacity["RUN_DAY"].isna()
    if missing_run_day.any():
        examples = (
            monthly_capacity.loc[missing_run_day, ["생산계획년월", "공정"]]
            .drop_duplicates()
            .head(5)
            .to_dict("records")
        )
        raise ValueError(f"RQ_RUN_DAY 연결값이 없는 표준 목표 Capa 기준이 있습니다: {examples}")
    monthly_capacity["대당 일 Capa"] = monthly_capacity["공정 유효 Capa"].div(
        monthly_capacity["RUN_DAY"]
    )

    calendar = build_iso_week_calendar(start_date, end_date)
    # This is an intentional month-to-week expansion, not an accidental many-to-many join.
    weekly = monthly_capacity.merge(calendar, on="생산계획년월", validate="many_to_many")
    prepared_availability = prepare_weekly_availability(weekly_availability)
    weekly = weekly.merge(
        prepared_availability,
        on=["공정", "Weeknum"],
        how="left",
        validate="many_to_one",
    )
    weekly["일 표준 가능량"] = weekly["대당 일 Capa"] * weekly["가용대수"]
    return weekly[result_columns].sort_values(
        ["주차시작일", *display_dimensions],
        ignore_index=True,
    )


def weekly_standard_target_to_wide(
    data: pd.DataFrame,
    classification_columns: list[str],
    value_column: str = "일 표준 가능량",
) -> pd.DataFrame:
    """Pivot one weekly metric into Weeknum columns for Plotly display."""
    required = ["Weeknum", "주차시작일", *classification_columns, value_column]
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"표준 목표 Capa 필수 컬럼이 없습니다: {', '.join(missing)}")
    if data.empty:
        return pd.DataFrame(columns=classification_columns)

    week_order = (
        data[["Weeknum", "주차시작일"]]
        .drop_duplicates()
        .sort_values("주차시작일")["Weeknum"]
        .tolist()
    )
    duplicated = data.duplicated([*classification_columns, "Weeknum"], keep=False)
    if duplicated.any():
        examples = (
            data.loc[duplicated, [*classification_columns, "Weeknum"]]
            .drop_duplicates()
            .head(5)
            .to_dict("records")
        )
        raise ValueError(f"표준 목표 Capa의 분류·Weeknum이 중복되었습니다: {examples}")
    wide = data.pivot(
        index=classification_columns,
        columns="Weeknum",
        values=value_column,
    ).reset_index()
    wide.columns.name = None
    return wide.reindex(columns=[*classification_columns, *week_order])


def exclude_er_required_equipment(data: pd.DataFrame) -> pd.DataFrame:
    """Exclude engineering-run demand before standard Capa aggregation."""
    if "양산구분" not in data.columns:
        raise ValueError("소요대수 상세 필수 컬럼이 없습니다: 양산구분")
    production_mask = ~data["양산구분"].astype("string").str.strip().str.upper().eq("ER")
    return data.loc[production_mask].reset_index(drop=True)


def _prepare_run_day(data: pd.DataFrame) -> pd.DataFrame:
    required = ["생산계획년월", "공정", "RUN_DAY"]
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"RQ_RUN_DAY 필수 컬럼이 없습니다: {', '.join(missing)}")
    result = data[required].copy()
    month = pd.to_numeric(result["생산계획년월"], errors="coerce")
    valid_month = month.notna() & month.mod(1).eq(0)
    month_integer = month.fillna(0).astype("int64")
    valid_month &= month_integer.mod(100).between(1, 12)
    if not valid_month.all():
        raise ValueError("RQ_RUN_DAY의 생산계획년월은 YYYYMM 형식이어야 합니다.")
    result["생산계획년월"] = month_integer
    result["공정"] = result["공정"].astype("string").str.strip()
    if result["공정"].isna().any() or result["공정"].eq("").any():
        raise ValueError("RQ_RUN_DAY의 공정에는 누락값이 없어야 합니다.")
    run_day = pd.to_numeric(result["RUN_DAY"], errors="coerce")
    if run_day.isna().any() or run_day.le(0).any():
        raise ValueError("RQ_RUN_DAY의 RUN_DAY는 0보다 큰 숫자여야 합니다.")
    result["RUN_DAY"] = run_day.astype("float64")
    duplicated = result.duplicated(["생산계획년월", "공정"], keep=False)
    if duplicated.any():
        examples = (
            result.loc[duplicated, ["생산계획년월", "공정"]]
            .drop_duplicates()
            .head(5)
            .to_dict("records")
        )
        raise ValueError(f"RQ_RUN_DAY의 생산계획년월·공정이 중복되었습니다: {examples}")
    return result


def _valid_weeknum(value: object) -> bool:
    matched = _WEEK_PATTERN.fullmatch(str(value))
    if matched is None:
        return False
    year = 2000 + int(matched.group("year"))
    week = int(matched.group("week"))
    try:
        date.fromisocalendar(year, week, 1)
    except ValueError:
        return False
    return True
