# Purpose: 표준 목표 Capa의 수동 주차별 가용대수 입력 표 계약을 검증한다.

"""표준 목표 Capa의 수동 주차별 가용대수 입력 표 계약을 검증한다."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

import pandas as pd

from capa_simulation.services.clipboard_table import parse_clipboard_table
from capa_simulation.services.frame_checks import assert_unique_keys
from capa_simulation.services.frame_contracts import require_columns
from capa_simulation.services.iso_week_calendar import build_iso_week_calendar, valid_weeknum

WEEKLY_AVAILABILITY_COLUMNS = ["공정", "Weeknum", "가용대수"]
_TEMPLATE_COLUMNS = ["공정", "Weeknum", "주차시작일", "주차종료일", "가용대수"]


def build_weekly_availability_template(
    processes: list[str],
    start_date: date,
    end_date: date,
    *,
    saved: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """공정 × ISO 주차마다 한 행인 편집용 양식을 만든다. 가용대수는 **저장된 값**을 싣는다.

    저장값이 없는 칸은 0 이 아니라 **빈칸**이다(2026-09-29 버그 보고). 예전에는 모든 칸을
    0.0 으로 채워 내려 줘서, 양식을 받아 일부 공정만 고쳐 통째로 붙여넣으면 이미 넣어 둔
    다른 공정·주차가 0 대로 덮였다. 하류에서 「없음」은 표준 미설정(경고·빈칸)이고 0 은
    「0 대」(경고 없음)라 뜻이 다르다. 붙여넣기는 빈칸 행을 떨어뜨리므로(아래
    `parse_weekly_availability_clipboard`), 저장값을 채우고 나머지를 비워 두면 양식을 그대로
    되붙여도 아무것도 바뀌지 않는다.
    """
    normalized_processes = list(
        dict.fromkeys(str(process).strip() for process in processes if str(process).strip())
    )
    calendar = build_iso_week_calendar(start_date, end_date)
    if not normalized_processes or calendar.empty:
        return pd.DataFrame(columns=_TEMPLATE_COLUMNS)

    process_frame = pd.DataFrame({"공정": normalized_processes})
    template = process_frame.merge(calendar, how="cross")
    template["가용대수"] = _saved_counts(template, saved)
    return template[_TEMPLATE_COLUMNS]


def _saved_counts(template: pd.DataFrame, saved: pd.DataFrame | None) -> pd.Series:
    """양식 행 순서대로 저장된 가용대수를 돌려준다. 저장값이 없으면 NaN(= CSV 빈칸)."""
    empty = pd.Series(float("nan"), index=template.index, dtype="float64")
    if saved is None or saved.empty:
        return empty
    require_columns(saved, WEEKLY_AVAILABILITY_COLUMNS, "저장된 가용설비")
    # 저장본은 되읽기 경로가 이미 정규화했다(공정 strip·Weeknum 대문자·키 유일). 키 dtype 만
    # 양식과 같은 평범한 문자열로 맞춰 붙인다.
    lookup = {
        (str(process), str(weeknum)): float(count)
        for process, weeknum, count in saved[WEEKLY_AVAILABILITY_COLUMNS].itertuples(
            index=False, name=None
        )
    }
    keys = zip(template["공정"].astype(str), template["Weeknum"].astype(str), strict=True)
    return pd.Series(
        [lookup.get(key, float("nan")) for key in keys],
        index=template.index,
        dtype="float64",
    )


def parse_weekly_availability_clipboard(
    content: str,
    *,
    known_processes: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Excel 에서 복사한 헤더 포함 주차별 가용대수 표를 읽는다.

    **가용대수 빈칸 행은 「그대로 둠」이다**(2026-09-29 버그 보고). 저장이 (공정, Weeknum)
    upsert 라, 떨어뜨린 키는 저장된 값 또는 미설정이 그대로 남는다. 양식이 저장값을 채워
    내려오므로 사용자는 고칠 칸만 고치고 통째로 되붙이면 된다. 못 읽는 글자(`abc`)는
    빈칸과 달리 막는다 — 적었다고 믿는 값이 조용히 버려지면 안 된다.
    """
    return prepare_weekly_availability(
        parse_clipboard_table(content, "가용설비"),
        known_processes=known_processes,
        drop_blank_counts=True,
    )


def prepare_weekly_availability(
    data: pd.DataFrame,
    *,
    known_processes: Iterable[str] | None = None,
    drop_blank_counts: bool = False,
) -> pd.DataFrame:
    """Normalize and validate the manual process-week availability contract.

    `drop_blank_counts` 는 붙여넣기 경로(`parse_weekly_availability_clipboard`)만 켠다.
    가용대수가 빈 행을 떨어뜨리고, 남는 행이 없으면 「적용할 값이 없습니다」로 멈춘다.
    끄면(기본) 빈칸은 예전처럼 오류다 — 되읽기·계산 경로의 표는 DB 가 `NOT NULL` 로 지킨
    값이라 빈칸이 들어올 일이 없고, 들어온다면 조용히 떨어뜨릴 것이 아니라 드러내야 한다.

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
    require_columns(data, WEEKLY_AVAILABILITY_COLUMNS, "가용설비 입력 표")

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

    raw = result["가용대수"]
    blank = raw.isna() | raw.astype("string").str.strip().eq("")
    available = pd.to_numeric(raw, errors="coerce")
    garbled = available.isna() & ~blank
    if garbled.any():
        examples = (
            result.loc[garbled, ["공정", "Weeknum"]].head(5).astype(str).agg(" ".join, axis=1)
        )
        raise ValueError(f"가용설비 입력 표의 가용대수가 숫자가 아닙니다: {examples.tolist()}")
    if drop_blank_counts:
        result = result.loc[~blank].reset_index(drop=True)
        available = available.loc[~blank].reset_index(drop=True)
        if result.empty:
            raise ValueError(
                "적용할 값이 없습니다. 가용대수를 한 칸 이상 적어 붙여넣으세요 — 빈칸은 "
                "저장된 값을 그대로 둡니다."
            )
    elif blank.any():
        raise ValueError("가용설비 입력 표의 가용대수에 누락값이 있습니다.")
    if available.lt(0).any():
        raise ValueError("가용설비 입력 표의 가용대수는 0 이상이어야 합니다.")
    result["가용대수"] = available.astype("float64")

    assert_unique_keys(result, ["공정", "Weeknum"], "가용설비 입력 표의 공정·Weeknum이")
    return result.sort_values(["공정", "Weeknum"], ignore_index=True)
