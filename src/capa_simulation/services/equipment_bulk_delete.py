# Purpose: 설비 세 표에서 고른 행과 딸린 비가동 일정을 한 번에 빼고 되돌리는 계획을 세운다.

"""**고른 행을 키로 기억하고, 키로 지운다.**

직접 편집 표에서 여러 행을 지우는 기본 방법(행 체크 + Delete)은 필터가 걸리면 잠긴다 —
부분만 보이는 상태에서 「지운다」와 「안 보인다」를 가를 수 없어서다
(`components/table_view_controls.py`). 그래서 필터로 좁혀 놓고 한 번에 지우는 길은 편집표
밖에서 따로 낸다.

**행 번호로 기억하지 않는다.** 편집본은 제출할 때마다 다시 만들어지고, 필터 없이 행을
지우면 `st.data_editor` 가 번호를 다시 매긴다. 번호는 다음 실행이면 다른 행을 가리킨다.
대신 각 표의 업무 키 — 호기 / 공정+분류 / 호기+비가동유형+시작일 — 로 기억한다. 검증 전
편집본에는 같은 키가 둘일 수 있는데, 그러면 둘 다 지운다. 그것이 맞는 답이다.

**호기를 지우면 그 호기의 비가동 일정도 같이 뺀다**(2026-09-28 사용자 결정). 남겨 두면
저장이 「호기 마스터에 없는 설비의 비가동 일정이 있습니다」로 막힌다.

이 모듈은 `streamlit` 을 모른다. 편집본 세 표는 `(기존 보유대수, 호기 마스터, 비가동 일정)`
차례의 튜플이다 — 작업 공간(`components/equipment_data_workspace.py`)의 `Frames` 와 같다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

import pandas as pd

from capa_simulation.services.equipment_contract import (
    BASELINE_KEY_COLUMNS,
    DOWNTIME_KEY_COLUMNS,
)

EQUIPMENT_TARGET = "호기 마스터"
BASELINE_TARGET = "기존 보유대수"
DOWNTIME_TARGET = "비가동 일정"

# 표 이름 → (편집본 튜플 안의 자리, 업무 키). 튜플 차례는 화면 탭 차례와 다르다.
TARGET_LAYOUT: Mapping[str, tuple[int, tuple[str, ...]]] = {
    BASELINE_TARGET: (0, BASELINE_KEY_COLUMNS),
    EQUIPMENT_TARGET: (1, ("호기",)),
    DOWNTIME_TARGET: (2, DOWNTIME_KEY_COLUMNS),
}
_DATE_KEY_COLUMNS = frozenset({"시작일"})

Frames = tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]
RowKey = tuple[str, ...]


def normalize_key_value(value: object, *, is_date: bool = False) -> str:
    """키 한 칸을 비교할 수 있는 글자로. 빈 값은 빈 글자, 날짜는 `YYYY-MM-DD` 다.

    편집표를 지나면 같은 날짜가 `Timestamp`·`date`·문자열로 섞여 온다. 모양이 달라도 같은
    날이면 같은 키여야 한다.
    """
    if value is None or value is pd.NA or value is pd.NaT:
        return ""
    if isinstance(value, float) and value != value:  # NaN
        return ""
    if is_date:
        parsed = pd.to_datetime(str(value), errors="coerce")
        return parsed.date().isoformat() if isinstance(parsed, pd.Timestamp) else ""
    return str(value).strip()


def row_keys(frame: pd.DataFrame, target: str) -> list[RowKey]:
    """행마다 업무 키. 키 컬럼이 없는 표(빈 편집본)는 빈 목록이다."""
    _, columns = TARGET_LAYOUT[target]
    if frame.empty or not set(columns) <= set(frame.columns):
        return []
    return [
        tuple(
            normalize_key_value(value, is_date=column in _DATE_KEY_COLUMNS)
            for column, value in zip(columns, values, strict=True)
        )
        for values in frame.loc[:, list(columns)].itertuples(index=False, name=None)
    ]


def checked_keys(edited: pd.DataFrame, select_column: str, target: str) -> frozenset[RowKey]:
    """편집표가 돌려준 프레임에서 선택 칸이 켜진 행의 키. 손대지 않은 칸은 `None` 으로 온다."""
    if edited.empty or select_column not in edited.columns:
        return frozenset()
    # `fillna` 를 object 칸에 먼저 걸면 pandas 가 dtype 을 몰래 내린다(다음 major 에서 동작이
    # 바뀐다고 경고한다). 참인 칸만 고르면 None·NaN·NA 는 저절로 거짓이다.
    checked = edited[select_column].eq(True).fillna(False).astype(bool)
    keys = row_keys(edited.loc[checked], target)
    return frozenset(key for key in keys if any(key))


def matching_keys(
    frame: pd.DataFrame,
    filters: Mapping[str, Sequence[str]],
    target: str,
) -> frozenset[RowKey]:
    """필터 조건에 맞는 행의 키. 조건이 없으면 전체다.

    `table_view_controls` 가 보기를 좁힐 때와 같은 비교다 — 글자로 바꾸고 앞뒤 공백을 떼고
    고른 값 안에 드는지 본다. 그래야 「적용」을 누르기 전의 조건으로 골라도 적용한 뒤 보이는
    행과 같다.
    """
    matched = frame
    for column, chosen in filters.items():
        if chosen and column in matched.columns:
            matched = matched.loc[matched[column].astype(str).str.strip().isin(list(chosen))]
    return frozenset(key for key in row_keys(matched, target) if any(key))


@dataclass(frozen=True)
class DeletionPlan:
    """지울 행. `removed` 는 편집본 튜플과 같은 차례로 표마다 빠질 행을 담는다."""

    target: str
    removed: Frames

    @property
    def target_count(self) -> int:
        return len(self.removed[TARGET_LAYOUT[self.target][0]])

    @property
    def cascaded_downtime_count(self) -> int:
        """호기를 지울 때 함께 빠지는 비가동 일정 수. 다른 표를 지울 때는 0 이다."""
        return len(self.removed[2]) if self.target == EQUIPMENT_TARGET else 0

    def sample_keys(self, limit: int = 5) -> list[str]:
        """확인 문구에 적을 앞 몇 개의 키."""
        keys = row_keys(self.removed[TARGET_LAYOUT[self.target][0]], self.target)
        return [" · ".join(part for part in key if part) for key in keys[:limit]]


def plan_deletion(frames: Frames, target: str, keys: Iterable[RowKey]) -> DeletionPlan:
    """지울 행을 정한다. 호기를 지우면 그 호기의 비가동 일정까지 넣는다."""
    wanted = frozenset(keys)
    position, _ = TARGET_LAYOUT[target]
    removed = [frame.iloc[0:0] for frame in frames]
    table = frames[position]
    mask = [key in wanted for key in row_keys(table, target)] if not table.empty else []
    removed[position] = table.loc[mask] if mask else table.iloc[0:0]
    if target == EQUIPMENT_TARGET and not removed[position].empty:
        machines = {key[0] for key in row_keys(removed[position], EQUIPMENT_TARGET)}
        downtime = frames[2]
        if not downtime.empty and "호기" in downtime.columns:
            owned = downtime["호기"].map(normalize_key_value).isin(machines)
            removed[2] = downtime.loc[owned]
    return DeletionPlan(target=target, removed=(removed[0], removed[1], removed[2]))


def apply_deletion(frames: Frames, plan: DeletionPlan) -> Frames:
    """계획한 행을 뺀다. 계획은 같은 편집본으로 세운 것이어야 한다(행 자리로 뺀다)."""
    result = [
        frame.drop(index=gone.index).reset_index(drop=True)
        for frame, gone in zip(frames, plan.removed, strict=True)
    ]
    return result[0], result[1], result[2]


def _reinsert(current: pd.DataFrame, rows: pd.DataFrame) -> pd.DataFrame:
    """`rows` 를 지우기 전 자리로 끼워 넣는다. 자리를 모르면 뒤에 붙인다.

    `plan_deletion` 이 남긴 행 이름은 지우기 직전 편집본의 행 번호다(편집본은 늘 0 부터 매긴
    번호다 — `apply_deletion` 이 다시 매긴다). 작은 번호부터 그 자리에 넣으면 그 사이 편집이
    없을 때 지우기 전 순서가 그대로 돌아온다. 되돌린 행이 맨 뒤로 가면 저장할 때 순서만 다른
    리비전이 생겼다(2026-10-05 E2E).
    """
    if rows.empty:
        return current
    if not all(isinstance(label, int) for label in rows.index.tolist()):
        return pd.concat([current, rows], ignore_index=True)
    result = current.reset_index(drop=True)
    for label in sorted(rows.index.tolist()):
        position = min(int(label), len(result))
        result = pd.concat(
            [result.iloc[:position], rows.loc[[label]], result.iloc[position:]],
            ignore_index=True,
        )
    return result


def restore_rows(frames: Frames, removed: Frames) -> tuple[Frames, int]:
    """방금 뺀 행을 지우기 전 자리로 되돌린다. 그 사이에 같은 키가 다시 생겼으면 건너뛴다.

    건너뛴 행 수를 함께 돌려준다 — 몰래 빠뜨리지 않고 화면이 말하게 한다.
    """
    restored: list[pd.DataFrame] = []
    skipped = 0
    for target, (position, _) in sorted(TARGET_LAYOUT.items(), key=lambda item: item[1][0]):
        current, gone = frames[position], removed[position]
        if gone.empty:
            restored.append(current)
            continue
        present = set(row_keys(current, target))
        back = [key not in present for key in row_keys(gone, target)]
        skipped += back.count(False)
        restored.append(_reinsert(current, gone.loc[back]))
    return (restored[0], restored[1], restored[2]), skipped
