# Purpose: 필요단축일정 기준선(그때 계획 결과를 얼린 공용 기록)의 모델·이름 규칙·얼리는 표를 둔다.

"""필요단축일정 기준선(진척 비교의 「과거」).

기준선은 **그때 화면이 보던 계획(`ShorteningPlan`)을 그대로 얼린 것**이다 — 다섯 목표의 호기 결과와
그때 맞댄 공정·Cut-off, 머리 정보(이름·저장 시각·그날 오늘·조회 달·계산의 출처). 저장은 설비 DB 의
`equipment_ops.shortening_baseline*`(0021)이고 SQL 은 `persistence/shortening_baseline_store.py` 가
갖는다. 이 모듈은 Streamlit·DB 를 모른다.

- **고칠 수 없다.** 새로 저장하거나 통째로 지운다. 모든 사용자가 같은 목록을 본다.
- **이름**은 앞뒤 공백을 걷은 글이고 비면 거절한다. 겹치는 이름은 저장 쪽이 거절한다(목록에서
  이름으로 고르기 때문이다). 기본 이름은 `YYYY-MM-DD 기준선` 이다.
- **얼리는 표**(`BASELINE_UNIT_COLUMNS`)는 목표마다 `LevelPlan.units` 의 칸에 호기 마스터의 설비명·
  환산비(`ShorteningPlan.unit_master`)를 붙인 것이다. 기여 시작은 목표 Qual 다음 날이라 싣지 않는다.
  가상 호기 「추가N」은 마스터에 없어 설비명·환산비가 빈칸이다.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from capa_simulation.services.equipment_contract import (
    CONVERSION_RATIO_COLUMN,
    EQUIPMENT_ID_COLUMN,
)
from capa_simulation.services.required_shortening import (
    KIND_SHORTENED,
    LEVEL_COLUMN,
    ShorteningPlan,
    level_percent,
)

__all__ = [
    "BASELINE_NAME_MAX_LENGTH",
    "BASELINE_SAVED_BY_MAX_LENGTH",
    "BASELINE_UNIT_COLUMNS",
    "BaselineProvenance",
    "ShorteningBaseline",
    "ShorteningBaselineDraft",
    "ShorteningBaselineSummary",
    "baseline_label",
    "baseline_units_frame",
    "default_baseline_name",
    "freeze_plan",
    "normalize_baseline_name",
    "normalize_baseline_units",
    "normalize_saved_by",
]

BASELINE_NAME_MAX_LENGTH = 60
BASELINE_SAVED_BY_MAX_LENGTH = 40

BASELINE_UNIT_COLUMNS = (
    LEVEL_COLUMN,
    "공정",
    "호기",
    "구분",
    EQUIPMENT_ID_COLUMN,
    "모듈 수",
    CONVERSION_RATIO_COLUMN,
    "기존 Qual",
    "목표 Qual",
    "단축일수",
    "늘어난 환산대수",
    "대상 월",
    "해소 기여 월",
)
"""얼리는 호기 표의 칸. 날짜는 `date`(빈칸 None), 달은 `YYYYMM` 정수다."""

# 하루씩 더한 환산 몫의 부동소수 끝자리를 턴다(`required_shortening._DECIMALS` 와 같은 자리).
_DECIMALS = 9
_DATE_COLUMNS = ("기존 Qual", "목표 Qual")
_INTEGER_COLUMNS = (LEVEL_COLUMN, "모듈 수", "단축일수", "대상 월")
_FLOAT_COLUMNS = (CONVERSION_RATIO_COLUMN, "늘어난 환산대수")
_TEXT_COLUMNS = ("공정", "호기", "구분", EQUIPMENT_ID_COLUMN, "해소 기여 월")


@dataclass(frozen=True)
class BaselineProvenance:
    """기준선 머리에 남기는 계산의 출처. 모르면 None 이다(시나리오 이름표가 없는 세션 등)."""

    saved_by: str | None = None
    equipment_revision_id: str | None = None
    equipment_revision_no: int | None = None
    reference_version: int | None = None
    scenario_id: str | None = None
    scenario_name: str | None = None
    scenario_revision_id: str | None = None
    scenario_revision_no: int | None = None
    scenario_content_token: str | None = None


@dataclass(frozen=True)
class ShorteningBaselineSummary:
    """목록 한 줄 — 기준선 머리."""

    baseline_id: str
    name: str
    saved_at: datetime
    plan_today: date
    start_month: int
    end_month: int
    saved_by: str | None = None
    equipment_revision_id: str | None = None
    equipment_revision_no: int | None = None
    reference_version: int | None = None
    scenario_id: str | None = None
    scenario_name: str | None = None
    scenario_revision_id: str | None = None
    scenario_revision_no: int | None = None
    scenario_content_token: str | None = None


@dataclass(frozen=True)
class ShorteningBaselineDraft:
    """저장하기 전의 기준선. `freeze_plan` 이 만든다 — 이름은 이미 다듬은 값이다."""

    name: str
    plan_today: date
    start_month: int
    end_month: int
    processes: tuple[str, ...]
    cutoff_days: Mapping[str, int]
    units: pd.DataFrame
    provenance: BaselineProvenance = field(default_factory=BaselineProvenance)


@dataclass(frozen=True)
class ShorteningBaseline:
    """저장된 기준선 한 벌 — 머리, 그때 맞댄 공정(차례대로)·Cut-off, 다섯 목표의 호기 표."""

    summary: ShorteningBaselineSummary
    processes: tuple[str, ...]
    cutoff_days: Mapping[str, int]
    units: pd.DataFrame

    def units_at(self, level: float) -> pd.DataFrame:
        """고른 목표의 호기 표(목표 칸 없이). 그 목표에 단축할 호기가 없었으면 빈 표다."""
        chosen = self.units.loc[self.units[LEVEL_COLUMN].eq(level_percent(level))]
        return chosen.drop(columns=LEVEL_COLUMN).reset_index(drop=True)


def default_baseline_name(day: date) -> str:
    """`기준선 저장` 의 기본 이름."""
    return f"{day:%Y-%m-%d} 기준선"


def normalize_baseline_name(value: object) -> str:
    """앞뒤 공백을 걷은 이름. 비었거나 너무 길면 `ValueError` 다."""
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError("기준선 이름을 적어 주세요.")
    if len(text) > BASELINE_NAME_MAX_LENGTH:
        raise ValueError(f"기준선 이름은 {BASELINE_NAME_MAX_LENGTH}자 이하여야 합니다.")
    return text


def normalize_saved_by(value: object) -> str | None:
    """저장한 사람(선택). 비면 None, 길면 잘라 낸다 — 로그인이 없어 적는 사람이 판단한다."""
    text = "" if value is None else str(value).strip()
    return text[:BASELINE_SAVED_BY_MAX_LENGTH] or None


def baseline_label(summary: ShorteningBaselineSummary) -> str:
    """선택 상자 라벨 「이름 · 저장일」. 기준선은 고칠 수 없어 라벨도 바뀌지 않는다."""
    return f"{summary.name} · {summary.saved_at:%Y-%m-%d}"


def freeze_plan(
    plan: ShorteningPlan,
    *,
    name: object,
    provenance: BaselineProvenance | None = None,
) -> ShorteningBaselineDraft:
    """계획 한 벌을 저장할 기준선으로 얼린다. 이름이 비었거나 조회 달이 없으면 `ValueError`."""
    if not plan.months:
        raise ValueError("조회 달이 없어 기준선을 저장할 수 없습니다.")
    return ShorteningBaselineDraft(
        name=normalize_baseline_name(name),
        plan_today=plan.today,
        start_month=int(plan.months[0]),
        end_month=int(plan.months[-1]),
        processes=tuple(str(process) for process in plan.processes),
        cutoff_days={
            str(process): int(days)
            for process, days in plan.cutoff_days.items()
            if process in plan.processes
        },
        units=baseline_units_frame(plan),
        provenance=provenance or BaselineProvenance(),
    )


def baseline_units_frame(plan: ShorteningPlan) -> pd.DataFrame:
    """다섯 목표의 호기 결과를 한 표로(`BASELINE_UNIT_COLUMNS`). 목표 차례, 그 안은 계산 차례다."""
    master = plan.unit_master.drop_duplicates("호기").set_index("호기")
    blocks: list[pd.DataFrame] = []
    for level_plan in plan.levels:
        units = level_plan.units
        if units.empty:
            continue
        block = units.copy()
        block.insert(0, LEVEL_COLUMN, level_percent(level_plan.level))
        shortened = block["구분"].eq(KIND_SHORTENED)
        for column in (EQUIPMENT_ID_COLUMN, CONVERSION_RATIO_COLUMN):
            mapped = block["호기"].map(master[column]) if not master.empty else None
            block[column] = mapped.where(shortened) if mapped is not None else None
        blocks.append(block.loc[:, list(BASELINE_UNIT_COLUMNS)])
    if not blocks:
        return _empty_units()
    return normalize_baseline_units(pd.concat(blocks, ignore_index=True))


def normalize_baseline_units(frame: pd.DataFrame) -> pd.DataFrame:
    """칸·형을 맞춘다. 얼릴 때와 DB 에서 읽을 때(날짜가 `datetime64` 로 온다) 같은 함수를 쓴다."""
    if frame.empty:
        return _empty_units()
    result = frame.loc[:, list(BASELINE_UNIT_COLUMNS)].copy()
    for column in _DATE_COLUMNS:
        result[column] = pd.Series(
            [_as_date(value) for value in result[column]], index=result.index, dtype="object"
        )
    for column in _INTEGER_COLUMNS:
        result[column] = pd.to_numeric(result[column]).astype("Int64")
    result[LEVEL_COLUMN] = result[LEVEL_COLUMN].astype("int64")
    for column in _FLOAT_COLUMNS:
        result[column] = pd.to_numeric(result[column]).astype("float64").round(_DECIMALS)
    for column in _TEXT_COLUMNS:
        result[column] = pd.Series(
            [None if _blank(value) else str(value) for value in result[column]],
            index=result.index,
            dtype="object",
        )
    result["해소 기여 월"] = result["해소 기여 월"].fillna("")
    return result.reset_index(drop=True)


def _empty_units() -> pd.DataFrame:
    frame = pd.DataFrame({column: pd.Series(dtype="object") for column in BASELINE_UNIT_COLUMNS})
    frame[LEVEL_COLUMN] = frame[LEVEL_COLUMN].astype("int64")
    for column in _INTEGER_COLUMNS[1:]:
        frame[column] = frame[column].astype("Int64")
    for column in _FLOAT_COLUMNS:
        frame[column] = frame[column].astype("float64")
    return frame


def _blank(value: object) -> bool:
    return (
        value is None
        or value is pd.NA
        or value is pd.NaT
        or (isinstance(value, float) and math.isnan(value))
    )


def _as_date(value: object) -> date | None:
    """표 칸의 날짜. `Timestamp`·`datetime64` 는 날짜로 낮추고, 빈칸은 None 이다."""
    if _blank(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    stamp = pd.Timestamp(str(value))
    return None if pd.isna(stamp) else stamp.date()
