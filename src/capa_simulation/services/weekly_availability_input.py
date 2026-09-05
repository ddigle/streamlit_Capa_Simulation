# Purpose: 표준 목표 Capa의 수동 주차별 가용대수 입력 표 계약을 검증한다.

"""표준 목표 Capa의 수동 주차별 가용대수 입력 표 계약을 검증한다."""

from __future__ import annotations

from datetime import date

import pandas as pd

from capa_simulation.services.clipboard_table import parse_clipboard_table
from capa_simulation.services.iso_week_calendar import build_iso_week_calendar, valid_weeknum

WEEKLY_AVAILABILITY_COLUMNS = ["공정", "Weeknum", "가용대수"]


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
        weeknum for weeknum in result["Weeknum"].drop_duplicates() if not valid_weeknum(weeknum)
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
