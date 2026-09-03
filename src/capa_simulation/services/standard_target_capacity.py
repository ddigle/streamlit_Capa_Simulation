# Purpose: Weekly standard target Capa from effective daily Capa and manual availability.

"""Weekly standard target Capa from effective daily Capa and manual availability."""

from __future__ import annotations

import re
from datetime import date, timedelta
from io import BytesIO
from typing import cast

import pandas as pd

from capa_simulation.services.clipboard_table import parse_clipboard_table
from capa_simulation.services.weighted_unit_capacity import (
    DEMAND_ID_COLUMNS,
    WEIGHTED_CAPACITY_HIERARCHY,
    effective_process_capacity_long,
)

WEEKLY_AVAILABILITY_COLUMNS = ["공정", "Weeknum", "가용대수"]
WEEK_CALENDAR_COLUMNS = ["Weeknum", "주차시작일", "주차종료일", "생산계획년월"]
STANDARD_TARGET_DUMMY_EXCLUDED_PROCESSES = ("Pre B/D",)
PKG_EQUIVALENT_COLUMN = "PKG 환산 일 표준 가능량"
PKG_PLAN_KEYS = [
    "생산계획년월",
    "양산구분",
    "제품정보",
    "Stack",
    "Capa Code",
    "Customer",
    "CS",
]
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


def parse_weekly_availability_clipboard(content: str) -> pd.DataFrame:
    """Parse header-inclusive weekly availability copied from Excel."""
    return prepare_weekly_availability(parse_clipboard_table(content, "가용설비"))


def prepare_weekly_availability(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize and validate the manual process-week availability contract."""
    missing = [column for column in WEEKLY_AVAILABILITY_COLUMNS if column not in data.columns]
    if missing:
        raise ValueError(f"가용설비 입력 표 필수 컬럼이 없습니다: {', '.join(missing)}")

    result = data[WEEKLY_AVAILABILITY_COLUMNS].copy()
    result = result.dropna(how="all").reset_index(drop=True)
    if result.empty:
        raise ValueError("가용설비 입력 표에 행이 없습니다.")

    result["공정"] = result["공정"].astype("string").str.strip()
    result["Weeknum"] = result["Weeknum"].astype("string").str.strip().str.upper()
    if result["공정"].isna().any() or result["공정"].eq("").any():
        raise ValueError("가용설비 입력 표의 공정에는 누락값을 입력할 수 없습니다.")
    if result["Weeknum"].isna().any() or result["Weeknum"].eq("").any():
        raise ValueError("가용설비 입력 표의 Weeknum에는 누락값을 입력할 수 없습니다.")

    invalid_weeks = [
        weeknum for weeknum in result["Weeknum"].drop_duplicates() if not _valid_weeknum(weeknum)
    ]
    if invalid_weeks:
        raise ValueError(f"Weeknum은 YY-W## 형식의 유효한 ISO 주차여야 합니다: {invalid_weeks[:5]}")

    available = pd.to_numeric(result["가용대수"], errors="coerce")
    if available.isna().any():
        raise ValueError("가용설비 입력 표의 가용대수에 숫자가 아닌 값 또는 누락값이 있습니다.")
    if available.lt(0).any():
        raise ValueError("가용설비 입력 표의 가용대수는 0 이상이어야 합니다.")
    result["가용대수"] = available.astype("float64")

    duplicated = result.duplicated(["공정", "Weeknum"], keep=False)
    if duplicated.any():
        examples = result.loc[duplicated, ["공정", "Weeknum"]].drop_duplicates().head(5)
        raise ValueError(
            f"가용설비 입력 표의 공정·Weeknum이 중복되었습니다: {examples.to_dict('records')}"
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

    production_required_equipment = prepare_standard_target_required_equipment(required_equipment)
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


def add_pkg_equivalent_standard_target(
    weekly_target: pd.DataFrame,
    required_equipment: pd.DataFrame,
    plan: pd.DataFrame,
    detail_level: str,
) -> pd.DataFrame:
    """Add daily PKG Kea equivalent while preserving the calculated demand mix."""
    if detail_level not in WEIGHTED_CAPACITY_HIERARCHY:
        raise ValueError(f"지원하지 않는 표준 목표 Capa 집계 수준입니다: {detail_level}")

    level_index = WEIGHTED_CAPACITY_HIERARCHY.index(detail_level)
    hierarchy_dimensions = WEIGHTED_CAPACITY_HIERARCHY[: level_index + 1]
    display_dimensions = ["공정", "소요기준", *hierarchy_dimensions[1:]]
    group_keys = ["생산계획년월", *display_dimensions]
    target_required = [*group_keys, "원수요_부하량", "일 표준 가능량"]
    missing_target = [column for column in target_required if column not in weekly_target.columns]
    if missing_target:
        raise ValueError(f"표준 목표 Capa 필수 컬럼이 없습니다: {', '.join(missing_target)}")

    result = weekly_target.copy()
    if result.empty:
        result[PKG_EQUIVALENT_COLUMN] = pd.Series(dtype="float64")
        return result

    source = prepare_standard_target_required_equipment(required_equipment)
    source_required = [*DEMAND_ID_COLUMNS, "부하량"]
    missing_source = [column for column in source_required if column not in source.columns]
    if missing_source:
        raise ValueError(f"소요대수 상세 필수 컬럼이 없습니다: {', '.join(missing_source)}")
    source = source[source_required].copy()
    _normalize_month_values(source, "소요대수 상세")
    source_text_columns = [
        column for column in DEMAND_ID_COLUMNS if column not in {"생산계획년월", "소요기준"}
    ]
    _normalize_text_values(source, source_text_columns, "소요대수 상세")
    source["소요기준"] = (
        source["소요기준"].astype("string").str.strip().str.upper().replace({"WAFER": "WF"})
    )
    _assert_complete_values(source, DEMAND_ID_COLUMNS, "소요대수 상세")
    source["부하량"] = _numeric_values(source["부하량"], "소요대수 상세.부하량")
    source = source.loc[source["부하량"].gt(0)].drop_duplicates(DEMAND_ID_COLUMNS)

    prepared_plan = _prepare_pkg_plan_for_equivalent(plan)
    link_columns = list(dict.fromkeys([*group_keys, *PKG_PLAN_KEYS]))
    demand_links = source[link_columns].drop_duplicates()
    demand_links = demand_links.merge(
        prepared_plan,
        on=PKG_PLAN_KEYS,
        how="left",
        validate="many_to_one",
        indicator="_pkg_plan_merge",
    )
    missing_plan = demand_links["_pkg_plan_merge"].ne("both")
    if missing_plan.any():
        examples = demand_links.loc[missing_plan, PKG_PLAN_KEYS].head(5).to_dict("records")
        raise ValueError(f"PKG 환산에 필요한 RQ_PKG_PLAN 연결값이 없습니다: {examples}")
    demand_links = demand_links.drop(columns="_pkg_plan_merge")

    pkg_plan_by_group = demand_links.groupby(group_keys, as_index=False, dropna=False).agg(
        PKG_계획=("생산수량", "sum")
    )
    result = result.merge(
        pkg_plan_by_group,
        on=group_keys,
        how="left",
        validate="many_to_one",
    )
    original_load = pd.to_numeric(result["원수요_부하량"], errors="coerce")
    daily_target = pd.to_numeric(result["일 표준 가능량"], errors="coerce")
    conversion_ratio = result["PKG_계획"].div(original_load.where(original_load.gt(0)))
    result[PKG_EQUIVALENT_COLUMN] = daily_target * conversion_ratio
    return result.drop(columns="PKG_계획")


def build_standard_target_logic_analysis(
    required_equipment: pd.DataFrame,
    run_day: pd.DataFrame,
    weekly_availability: pd.DataFrame,
    weeknum: str,
    process: str,
    demand_basis: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Explain one process-week target through its product and WF mix."""
    normalized_weeknum = str(weeknum).strip().upper()
    if not _valid_weeknum(normalized_weeknum):
        raise ValueError("로직 분석 Weeknum은 YY-W## 형식의 유효한 ISO 주차여야 합니다.")

    normalized_process = str(process).strip()
    if not normalized_process:
        raise ValueError("로직 분석 공정을 선택해야 합니다.")
    normalized_basis = str(demand_basis).strip().upper().replace("WAFER", "WF")
    if not normalized_basis:
        raise ValueError("로직 분석 소요기준을 선택해야 합니다.")

    matched = _WEEK_PATTERN.fullmatch(normalized_weeknum)
    if matched is None:  # pragma: no cover - guarded by _valid_weeknum
        raise ValueError("로직 분석 Weeknum 형식을 확인하세요.")
    week_start = date.fromisocalendar(
        2000 + int(matched.group("year")),
        int(matched.group("week")),
        1,
    )
    production_month = week_start.year * 100 + week_start.month

    required = ["생산계획년월", "공정", "소요기준", "양산구분"]
    missing = [column for column in required if column not in required_equipment.columns]
    if missing:
        raise ValueError(f"소요대수 상세 필수 컬럼이 없습니다: {', '.join(missing)}")

    source = required_equipment.copy()
    month = pd.to_numeric(source["생산계획년월"], errors="coerce")
    process_values = source["공정"].astype("string").str.strip()
    basis_values = (
        source["소요기준"].astype("string").str.strip().str.upper().replace({"WAFER": "WF"})
    )
    source = source.loc[
        month.eq(production_month)
        & process_values.eq(normalized_process)
        & basis_values.eq(normalized_basis)
    ].reset_index(drop=True)
    source = prepare_standard_target_required_equipment(source)
    if source.empty:
        raise ValueError("선택한 주차·공정·소요기준에 해당하는 양산 소요대수 데이터가 없습니다.")

    week_end = week_start + timedelta(days=6)
    target = build_weekly_standard_target_capacity(
        required_equipment=source,
        run_day=run_day,
        weekly_availability=weekly_availability,
        start_date=week_start,
        end_date=week_end,
        detail_level="공정",
    )
    target = target.loc[
        target["Weeknum"].eq(normalized_weeknum)
        & target["공정"].eq(normalized_process)
        & target["소요기준"].eq(normalized_basis)
    ].reset_index(drop=True)
    if len(target) != 1:
        raise ValueError("선택한 조건의 공정 종합 표준 가능량을 하나로 확정할 수 없습니다.")

    contributions = effective_process_capacity_long(source, "WF 구분")
    total_load = float(cast(float, target.at[0, "원수요_부하량"]))
    total_required = float(cast(float, target.at[0, "STEP_소요대수"]))
    contributions = contributions.rename(columns={"공정 유효 Capa": "분류 유효 Capa"})
    contributions["부하량 비중"] = contributions["원수요_부하량"].div(
        total_load if total_load > 0 else float("nan")
    )
    contributions["소요대수 비중"] = contributions["STEP_소요대수"].div(
        total_required if total_required > 0 else float("nan")
    )
    contributions["Capa 역수 기여"] = contributions["부하량 비중"].div(
        contributions["분류 유효 Capa"].where(contributions["분류 유효 Capa"].gt(0))
    )
    contribution_columns = [
        "생산계획년월",
        "공정",
        "소요기준",
        "양산구분",
        "제품정보",
        "Stack",
        "WF 구분",
        "원수요_부하량",
        "부하량 비중",
        "STEP_소요대수",
        "소요대수 비중",
        "분류 유효 Capa",
        "Capa 역수 기여",
    ]
    return target, contributions[contribution_columns].reset_index(drop=True)


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


def prepare_standard_target_required_equipment(data: pd.DataFrame) -> pd.DataFrame:
    """Apply every demand exclusion used only by standard target Capa."""
    production = exclude_er_required_equipment(data)
    exception_mask = _standard_target_exception_mask(production)
    return production.loc[~exception_mask].reset_index(drop=True)


def standard_target_exception_row_count(data: pd.DataFrame) -> int:
    """Count detailed rows omitted by process-specific standard target rules."""
    production = exclude_er_required_equipment(data)
    return int(_standard_target_exception_mask(production).sum())


def _standard_target_exception_mask(data: pd.DataFrame) -> pd.Series:
    required = ["공정", "WF 구분"]
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"소요대수 상세 필수 컬럼이 없습니다: {', '.join(missing)}")
    process = data["공정"].astype("string").str.strip().str.upper()
    wf_type = data["WF 구분"].astype("string").str.strip().str.upper()
    excluded_processes = {
        value.strip().upper() for value in STANDARD_TARGET_DUMMY_EXCLUDED_PROCESSES
    }
    return process.isin(excluded_processes) & wf_type.eq("DUMMY")


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


def _prepare_pkg_plan_for_equivalent(data: pd.DataFrame) -> pd.DataFrame:
    required = [*PKG_PLAN_KEYS, "생산수량"]
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"RQ_PKG_PLAN 필수 컬럼이 없습니다: {', '.join(missing)}")

    result = data[required].copy()
    _normalize_month_values(result, "RQ_PKG_PLAN")
    text_columns = [column for column in PKG_PLAN_KEYS if column != "생산계획년월"]
    _normalize_text_values(result, text_columns, "RQ_PKG_PLAN")
    _assert_complete_values(result, PKG_PLAN_KEYS, "RQ_PKG_PLAN")
    result["생산수량"] = _numeric_values(result["생산수량"], "RQ_PKG_PLAN.생산수량")
    if result["생산수량"].lt(0).any():
        raise ValueError("RQ_PKG_PLAN의 생산수량은 0 이상이어야 합니다.")
    duplicated = result.duplicated(PKG_PLAN_KEYS, keep=False)
    if duplicated.any():
        examples = result.loc[duplicated, PKG_PLAN_KEYS].drop_duplicates().head(5)
        raise ValueError(f"RQ_PKG_PLAN 업무 키가 중복되었습니다: {examples.to_dict('records')}")
    return result


def _normalize_month_values(data: pd.DataFrame, table_name: str) -> None:
    numeric = pd.to_numeric(data["생산계획년월"], errors="coerce")
    valid = numeric.notna() & numeric.mod(1).eq(0)
    months = numeric.fillna(0).astype("int64")
    valid &= months.mod(100).between(1, 12)
    if not valid.all():
        raise ValueError(f"{table_name}의 생산계획년월은 YYYYMM 형식이어야 합니다.")
    data["생산계획년월"] = months


def _normalize_text_values(data: pd.DataFrame, columns: list[str], table_name: str) -> None:
    for column in columns:
        data[column] = data[column].astype("string").str.strip()
    _assert_complete_values(data, columns, table_name)


def _assert_complete_values(data: pd.DataFrame, columns: list[str], table_name: str) -> None:
    if any(data[column].isna().any() or data[column].eq("").any() for column in columns):
        raise ValueError(f"{table_name}의 필수 연결 키에 누락값이 있습니다.")


def _numeric_values(series: pd.Series, label: str) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.isna().any():
        raise ValueError(f"{label}에 숫자가 아닌 값 또는 누락값이 있습니다.")
    return numeric.astype("float64")


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
