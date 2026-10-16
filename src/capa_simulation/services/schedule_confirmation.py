# Purpose: 반입·Qual 단계의 일정·실적·상태를 맞대어 미확인·실적 누락·상태 갱신 필요 호기를 고른다.

"""일정 확인 알림(2026-10-16 사용자 결정).

설비 마스터의 반입·Qual 단계는 일정·실적·상태 세 칸이 짝이다(`equipment_contract.ACTUAL_STAGES`).
세 칸이 서로 맞지 않는 호기를 단계마다 고른다. **저장은 막지 않는다** — 알리기만 한다.

- **미확인** — 상태가 계획·확정이고, 실적이 비었고, **일정 < 오늘**. 일정 당일은 아직 진행 중일 수
  있어 다음 날부터다. 오늘(`today`)을 인자로 받는다 — 앞으로 할 계획까지 늘 미확인으로 뜨지 않게
  일정이 지난 것만 본다.
- **실적 누락** — 상태가 「완료」인데 실적이 비었다.
- **상태 갱신 필요** — 실적이 있는데 상태가 아직 계획·확정이다.

**검증(`prepare_*`) 안에 두지 않는다.** 미확인은 날짜가 지나면 결과가 바뀌므로, 검증에 넣으면 저장
때 통과한 리비전이 시간이 지나 열리지 않는다. 그래서 이 모듈은 검증을 부르지 않고 **검증 전
편집본도 그대로 받는다** — 필요한 칸만 읽고, 못 읽는 날짜는 빈 칸으로, 없는 컬럼은 모두 빈 칸으로
본다(옛 편집본에는 실적·반입상태 칸이 없다). 설비명이 빈 행은 검증이 버리는 행이라 보지 않는다.

**대수는 행이 아니라 설비를 센다.** 결과 행에 `설비키`(`equipment_units.unit_keys` — Main
설비로 묶은 모듈 행은 그 Main 설비)를 싣고, 「N대」는 걸린 설비키의 수다. 모듈 넷 가운데
하나만 걸려도, 넷 다 걸려도 그 설비 한 대다 — 확인할 대상의 수라 지분(몫)으로 나누지
않는다. 「N건」(저장 전 경고)은 (호기, 단계) 행 수이고, Space 「!」(`flagged_equipment`)는
상자마다 묻으므로 설비명이다.

지연(상태 「지연」)은 여기서 고르지 않는다 — 실적이 들어올 때까지 이어지는 구간이라 시점마다
달라지고, Space 도면의 빨강 채우기가 맡는다.
"""

from __future__ import annotations

from collections.abc import Collection
from datetime import date
from typing import Final

import pandas as pd

from capa_simulation.services.equipment_contract import (
    ACTUAL_STAGES,
    DONE_STAGE_STATUS,
    EQUIPMENT_ID_COLUMN,
    OPEN_STAGE_STATUSES,
    ActualStage,
)
from capa_simulation.services.equipment_units import UNIT_KEY_COLUMN, unit_keys

PROCESS_COLUMN: Final = "공정소분류"
CONFIRMATION_KIND_COLUMN: Final = "확인구분"
STAGE_COLUMN: Final = "단계"
SCHEDULE_COLUMN: Final = "일정"
ACTUAL_COLUMN: Final = "실적"
STATUS_COLUMN: Final = "상태"

UNCONFIRMED: Final = "미확인"
MISSING_ACTUAL: Final = "실적 누락"
STATUS_UPDATE_NEEDED: Final = "상태 갱신 필요"
# 차례가 곧 결과 행의 차례다.
CONFIRMATION_KINDS: Final = (UNCONFIRMED, MISSING_ACTUAL, STATUS_UPDATE_NEEDED)

CONFIRMATION_COLUMNS: Final = (
    EQUIPMENT_ID_COLUMN,
    PROCESS_COLUMN,
    UNIT_KEY_COLUMN,
    CONFIRMATION_KIND_COLUMN,
    STAGE_COLUMN,
    SCHEDULE_COLUMN,
    ACTUAL_COLUMN,
    STATUS_COLUMN,
)

_EXAMPLES: Final = 5


def schedule_confirmation_issues(equipment: pd.DataFrame, *, today: date) -> pd.DataFrame:
    """설비 마스터(검증 전 편집본도 받는다)에서 세 알림에 걸리는 (호기, 단계)를 고른다.

    돌려주는 칸은 `CONFIRMATION_COLUMNS`(설비명·공정소분류·설비키·확인구분·단계·일정·실적·
    상태)다. 한 행이 한 (호기, 단계, 확인구분)이다 — 반입과 Qual 이 둘 다 미확인인 호기는 두
    행이다. 차례는 확인구분(`CONFIRMATION_KINDS`) → 단계(반입 → Qual) → 일정(빈 칸은 뒤) →
    설비명이다.
    """
    return _issues(equipment, kinds=CONFIRMATION_KINDS, today=pd.Timestamp(today))


def unconfirmed_issues(equipment: pd.DataFrame, *, today: date) -> pd.DataFrame:
    """미확인만. 칸과 차례는 `schedule_confirmation_issues` 와 같다. 다른 두 확인구분을 구하지 않아
    회차마다 부르는 Space 「!」(`space_unit_state.unit_boundaries`)가 쓴다."""
    return _issues(equipment, kinds=(UNCONFIRMED,), today=pd.Timestamp(today))


def actual_record_issues(equipment: pd.DataFrame) -> pd.DataFrame:
    """오늘과 무관한 두 알림(실적 누락·상태 갱신 필요)만. 칸과 차례는
    `schedule_confirmation_issues` 와 같다. 저장 미리보기 경고(`actual_record_warnings`)가 쓴다."""
    return _issues(equipment, kinds=(MISSING_ACTUAL, STATUS_UPDATE_NEEDED), today=None)


def confirmation_counts(
    issues: pd.DataFrame,
    *,
    processes: Collection[str] | None = None,
    unit_ids: Collection[str] | None = None,
) -> dict[str, int]:
    """확인구분별 **설비 수**(설비키 기준, 셋 다 늘 있다). 반입·Qual 이 함께 걸린 설비도,
    모듈 여럿이 걸린 설비도 한 대다.

    `processes` 를 주면 그 공정소분류만, `unit_ids` 를 주면 그 설비명(행)만 센다.
    """
    rows = _scoped(issues, processes, unit_ids)
    return {
        kind: int(rows.loc[rows[CONFIRMATION_KIND_COLUMN].eq(kind), UNIT_KEY_COLUMN].nunique())
        for kind in CONFIRMATION_KINDS
    }


def flagged_equipment(issues: pd.DataFrame, kind: str = UNCONFIRMED) -> frozenset[str]:
    """그 확인구분에 걸린 설비명. Space 도면의 「!」 표식처럼 호기마다 한 번 물을 때 쓴다."""
    if kind not in CONFIRMATION_KINDS:
        raise ValueError(f"확인구분은 {'·'.join(CONFIRMATION_KINDS)} 중 하나여야 합니다: {kind}")
    chosen = issues.loc[issues[CONFIRMATION_KIND_COLUMN].eq(kind), EQUIPMENT_ID_COLUMN]
    return frozenset(str(name) for name in chosen)


def schedule_confirmation_notice(
    issues: pd.DataFrame,
    *,
    processes: Collection[str] | None = None,
    unit_ids: Collection[str] | None = None,
) -> str | None:
    """「미확인 N대 (반입 a · Qual b) — …」 한 줄. 미확인이 없으면 `None`(그리지 않는다).

    앞의 대수와 괄호 안은 설비 수(설비키 기준)이고 0 인 단계는 적지 않는다. 반입·Qual 이 함께 걸린
    설비는 양쪽에 한 번씩 들어 괄호 안의 합이 앞의 대수보다 클 수 있다.
    """
    rows = _scoped(issues, processes, unit_ids)
    unconfirmed = rows.loc[rows[CONFIRMATION_KIND_COLUMN].eq(UNCONFIRMED)]
    total = int(unconfirmed[UNIT_KEY_COLUMN].nunique())
    if total == 0:
        return None
    per_stage = [
        (stage.label, int(group[UNIT_KEY_COLUMN].nunique()))
        for stage in ACTUAL_STAGES
        for group in (unconfirmed.loc[unconfirmed[STAGE_COLUMN].eq(stage.label)],)
    ]
    parts = " · ".join(f"{label} {count:,}" for label, count in per_stage if count > 0)
    return (
        f"{UNCONFIRMED} {total:,}대 ({parts}) — 일정이 지났는데 실적이 비고 상태가 "
        f"{'·'.join(OPEN_STAGE_STATUSES)}입니다. 실적을 적거나 상태를 고치세요."
    )


def schedule_confirmation_summary(issues: pd.DataFrame) -> str | None:
    """세 알림을 한 줄로 — 「미확인 N대 · 실적 누락 N대 · 상태 갱신 필요 N대 — …」. 셋 다 없으면
    `None`(그리지 않는다).

    대수는 `confirmation_counts`(설비키 기준)이고 0 인 구분은 적지 않는다. 한 설비가 두 구분에
    걸리면 양쪽에 한 번씩 든다. 고칠 (호기, 단계) 행은 받은 쪽이 목록으로 보인다(RawData 펼침
    목록).
    """
    counts = confirmation_counts(issues)
    parts = [f"{kind} {count:,}대" for kind, count in counts.items() if count > 0]
    if not parts:
        return None
    return (
        f"{' · '.join(parts)} — 반입·Qual 의 일정·실적·상태가 서로 맞지 않습니다"
        "(저장은 됩니다). 고칠 호기는 아래 목록에 있습니다."
    )


def actual_record_warnings(equipment: pd.DataFrame) -> list[str]:
    """저장 미리보기에 띄울 경고 — 실적 누락·상태 갱신 필요 한 줄씩(없는 쪽은 빠진다). 저장은
    막지 않는다. 검증 전 편집본도 받는다."""
    issues = actual_record_issues(equipment)
    explanations = {
        MISSING_ACTUAL: f"상태가 「{DONE_STAGE_STATUS}」인데 실적이 비었습니다",
        STATUS_UPDATE_NEEDED: f"실적이 있는데 상태가 {'·'.join(OPEN_STAGE_STATUSES)}입니다",
    }
    messages: list[str] = []
    for kind, explanation in explanations.items():
        rows = issues.loc[issues[CONFIRMATION_KIND_COLUMN].eq(kind)]
        if rows.empty:
            continue
        examples = [
            f"{name}({stage})"
            for name, stage in zip(
                rows[EQUIPMENT_ID_COLUMN].head(_EXAMPLES),
                rows[STAGE_COLUMN].head(_EXAMPLES),
                strict=True,
            )
        ]
        more = f" 외 {len(rows) - _EXAMPLES:,}건" if len(rows) > _EXAMPLES else ""
        messages.append(
            f"{kind} {len(rows):,}건 — {explanation}(저장은 됩니다): {', '.join(examples)}{more}"
        )
    return messages


def _issues(
    equipment: pd.DataFrame,
    *,
    kinds: tuple[str, ...],
    today: pd.Timestamp | None,
) -> pd.DataFrame:
    if equipment.empty or EQUIPMENT_ID_COLUMN not in equipment.columns:
        return _empty()
    names = equipment[EQUIPMENT_ID_COLUMN].astype("string").str.strip()
    named = (names.notna() & names.ne("")).fillna(False).to_numpy()
    if not named.any():
        return _empty()
    frame = equipment.loc[named]
    names = names.loc[named]
    keys = unit_keys(frame)
    processes = (
        frame[PROCESS_COLUMN].astype("string").str.strip()
        if PROCESS_COLUMN in frame.columns
        else pd.Series(pd.NA, index=frame.index, dtype="string")
    )
    pieces: list[pd.DataFrame] = []
    for kind_order, kind in enumerate(CONFIRMATION_KINDS):
        if kind not in kinds:
            continue
        for stage_order, stage in enumerate(ACTUAL_STAGES):
            schedule, actual, status = _stage_values(frame, stage)
            chosen = _kind_mask(kind, schedule, actual, status, today)
            if not chosen.any():
                continue
            pieces.append(
                pd.DataFrame(
                    {
                        EQUIPMENT_ID_COLUMN: names.loc[chosen],
                        PROCESS_COLUMN: processes.loc[chosen],
                        UNIT_KEY_COLUMN: keys.loc[chosen],
                        CONFIRMATION_KIND_COLUMN: kind,
                        STAGE_COLUMN: stage.label,
                        SCHEDULE_COLUMN: schedule.loc[chosen],
                        ACTUAL_COLUMN: actual.loc[chosen],
                        STATUS_COLUMN: status.loc[chosen],
                        "_kind": kind_order,
                        "_stage": stage_order,
                    }
                )
            )
    if not pieces:
        return _empty()
    result = pd.concat(pieces, ignore_index=True)
    result = result.sort_values(
        ["_kind", "_stage", SCHEDULE_COLUMN, EQUIPMENT_ID_COLUMN],
        kind="stable",
        na_position="last",
    )
    return _typed(result.loc[:, list(CONFIRMATION_COLUMNS)].reset_index(drop=True))


def _kind_mask(
    kind: str,
    schedule: pd.Series,
    actual: pd.Series,
    status: pd.Series,
    today: pd.Timestamp | None,
) -> pd.Series:
    """한 단계에서 그 확인구분에 걸리는 행(bool)."""
    open_status = status.isin(OPEN_STAGE_STATUSES).fillna(False).astype("bool")
    no_actual = actual.isna()
    if kind == UNCONFIRMED:
        if today is None:
            raise ValueError("미확인은 오늘 날짜가 있어야 고를 수 있습니다.")
        overdue = schedule.notna() & schedule.lt(today)
        return (open_status & no_actual & overdue).fillna(False).astype("bool")
    if kind == MISSING_ACTUAL:
        done = status.eq(DONE_STAGE_STATUS).fillna(False).astype("bool")
        return (done & no_actual).astype("bool")
    return (open_status & actual.notna()).astype("bool")


def _stage_values(
    frame: pd.DataFrame, stage: ActualStage
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """(일정, 실적, 상태). 없는 컬럼은 빈 칸, 못 읽는 날짜도 빈 칸이다."""
    return (
        _dates(frame, stage.schedule),
        _dates(frame, stage.actual),
        _text(frame, stage.status),
    )


def _dates(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns]")
    raw = frame[column]
    blank = raw.isna() | raw.astype("string").str.strip().eq("")
    parsed = pd.to_datetime(raw.mask(blank), errors="coerce")
    return pd.Series(parsed, index=frame.index).astype("datetime64[ns]").dt.normalize()


def _text(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(pd.NA, index=frame.index, dtype="string")
    text = frame[column].astype("string").str.strip()
    return text.mask(text.eq(""))


def _scoped(
    issues: pd.DataFrame,
    processes: Collection[str] | None,
    unit_ids: Collection[str] | None,
) -> pd.DataFrame:
    kept = pd.Series(True, index=issues.index)
    if processes is not None:
        kept &= issues[PROCESS_COLUMN].isin(set(processes)).fillna(False).astype(bool)
    if unit_ids is not None:
        kept &= issues[EQUIPMENT_ID_COLUMN].isin(set(unit_ids)).fillna(False).astype(bool)
    return issues.loc[kept]


def _typed(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.astype(
        {
            EQUIPMENT_ID_COLUMN: "string",
            PROCESS_COLUMN: "string",
            UNIT_KEY_COLUMN: "string",
            CONFIRMATION_KIND_COLUMN: "string",
            STAGE_COLUMN: "string",
            SCHEDULE_COLUMN: "datetime64[ns]",
            ACTUAL_COLUMN: "datetime64[ns]",
            STATUS_COLUMN: "string",
        }
    )


def _empty() -> pd.DataFrame:
    return _typed(pd.DataFrame({column: [] for column in CONFIRMATION_COLUMNS}))
