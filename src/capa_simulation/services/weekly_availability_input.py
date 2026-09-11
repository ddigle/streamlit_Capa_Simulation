# Purpose: 표준 목표 Capa의 수동 주차별 가용대수 입력 표 계약을 검증한다.

"""표준 목표 Capa의 수동 주차별 가용대수 입력 표 계약을 검증한다."""

from __future__ import annotations

from collections.abc import Iterable
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


def parse_weekly_availability_clipboard(
    content: str,
    *,
    known_processes: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Parse header-inclusive weekly availability copied from Excel."""
    return prepare_weekly_availability(
        parse_clipboard_table(content, "가용설비"),
        known_processes=known_processes,
    )


def prepare_weekly_availability(
    data: pd.DataFrame,
    *,
    known_processes: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Normalize and validate the manual process-week availability contract.

    `known_processes` 를 주면 그 목록 밖의 공정명을 오류로 막는다. 화면은 공정명을 화면용
    라벨로 갈아 그리므로 사용자가 그 라벨을 그대로 양식에 적을 수 있는데, 검증이 없으면
    실재하지 않는 공정 행이 조용히 저장되어 어떤 계산에도 붙지 않는다. 보유 공정 목록은
    화면이 소유하므로 넘기는 것은 페이지의 몫이고, 이 모듈은 받은 **원본** 목록만 본다.

    목록 없이(`None`) 부르는 경로는 셋이며 이유가 각각 있다.

    - `EquipmentRepository.save_standard_target_availability` — 저장 직전 페이지가 이미
      `parse_weekly_availability_clipboard` 에 목록을 넘겨 막았다. 저장소는 보유 공정
      목록을 알지 못하므로 두 번째 관문을 세우지 않는다.
    - `EquipmentRepository.load_standard_target_availability` — 이미 저장된 값을 되읽는
      경로다. 시나리오가 바뀌어 공정 목록이 달라졌을 때 읽기를 막으면 화면이 영영 열리지
      않고 `입력 초기화` 조차 누를 수 없게 된다.
    - `services/standard_target_capacity.py` — 저장된 값을 계산에 넘길 뿐이고, 붙지 않는
      공정 행은 조인에서 그대로 떨어진다.
    """
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

    if known_processes is not None:
        allowed = {str(process).strip() for process in known_processes}
        allowed.discard("")
        unknown = sorted({str(process) for process in result["공정"] if process not in allowed})
        if unknown:
            raise ValueError(
                "가용설비 입력 표에 보유하지 않은 공정이 있습니다. CSV 양식의 원본 "
                f"공정명을 그대로 쓰세요: {unknown[:5]}"
            )

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
