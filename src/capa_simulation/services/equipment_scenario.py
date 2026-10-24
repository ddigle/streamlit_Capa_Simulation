# Purpose: 설비 마스터를 공통·시나리오 일정으로 나눠 합치고 호기 키·일정 없음·되돌림 차이를 본다.

"""설비 마스터를 공통 호기 대장과 설비 시나리오 일정으로 나누고 합친다.

설비 마스터 39칸 가운데 일정 일곱 칸(`SCENARIO_SCHEDULE_COLUMNS`)은 설비 시나리오마다, 나머지 32칸은
모든 시나리오가 함께 쓰는 공통 호기 대장이다. 두 쪽은 설비명이 아니라 **호기 키**로 이어진다 — Space
편집기에서 설비명을 바꿔도 다른 시나리오의 일정·비가동이 그 호기를 따라가게.

- 옛 리비전의 호기는 `legacy_unit_key(설비명)` 이 키다(SQL `'n' || md5(equipment_id)` 와 같은 값).
- 새 호기는 `new_unit_key()`(uuid) 를 받는다. 저장 때 키를 정하는 규칙은 `assign_unit_keys`.
- 화면 프레임(39칸)에는 키 칸이 없다 — 붙여넣기·CSV·편집표가 그대로다. 키는 따로 (설비명, 키) 쌍으로
  든다.
- 「이 리비전으로 되돌리기」·「여기서 새 시나리오」(E7)의 확인 재료는 `schedule_restore_preview`
  다 — 같은 공통 대장과 합친 두 한 벌을 호기마다 견준다.

이 모듈은 DB·화면을 모른다. 읽기·저장 순서는 `persistence/equipment_repository.py` 가 정한다.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

import pandas as pd
from pandas.api.types import is_datetime64_any_dtype

from capa_simulation.services.equipment_contract import (
    COMMON_MASTER_COLUMNS,
    DOWNTIME_COLUMNS,
    EQUIPMENT_COLUMNS,
    EQUIPMENT_ID_COLUMN,
    SCENARIO_MEMO_COLUMN,
    SCENARIO_SCHEDULE_COLUMNS,
    SCENARIO_SCHEDULE_DATE_COLUMNS,
)

# 호기 키 칸. 계약 칸이 아니라 나누기·합치기 사이에서만 쓰는 이름이다(화면·CSV 에 나가지 않는다).
UNIT_KEY_COLUMN = "unit_key"

# 공통 쪽 프레임 — 공통 32칸 + 키.
COMMON_FRAME_COLUMNS = (*COMMON_MASTER_COLUMNS, UNIT_KEY_COLUMN)
# 일정 쪽 프레임 — 키 + 일정 일곱 칸.
SCHEDULE_FRAME_COLUMNS = (UNIT_KEY_COLUMN, *SCENARIO_SCHEDULE_COLUMNS)
# 비가동 일정의 설비명 밖 다섯 칸. 시나리오 쪽 비가동은 설비명 대신 키를 든다.
DOWNTIME_VALUE_COLUMNS = tuple(
    column for column in DOWNTIME_COLUMNS if column != EQUIPMENT_ID_COLUMN
)
SCHEDULE_DOWNTIME_COLUMNS = (UNIT_KEY_COLUMN, *DOWNTIME_VALUE_COLUMNS)

_DOWNTIME_DATE_COLUMNS = ("시작일", "종료일")


def legacy_unit_key(name: str) -> str:
    """옛 리비전 호기의 키. SQL `'n' || md5(equipment_id)` 와 같은 값이어야 한다(UTF-8 바이트)."""
    return "n" + hashlib.md5(name.encode("utf-8"), usedforsecurity=False).hexdigest()


def new_unit_key() -> str:
    """새 호기의 키(uuid 32자). 옛 키(`n` + 32자)와 길이가 달라 겹치지 않는다."""
    return uuid4().hex


def assign_unit_keys(
    names: Sequence[str],
    base_unit_keys: Mapping[str, str],
    renames: Mapping[str, str],
    *,
    new_key: Callable[[], str] = new_unit_key,
) -> dict[str, str]:
    """편집본 설비명마다 호기 키를 정한다(저장 때).

    1. 이름 지도(`renames` — 지금 이름 → 저장본 이름)로 이어받는 키가 먼저 차지한다.
    2. 남은 호기는 그 이름이 저장본에 있고 그 키가 아직 쓰이지 않았을 때만 그 키를 잇는다(1·2 는
       `inherited_unit_names`).
    3. 그 밖은 새 키다. 「A→B 이름 바꿈 + 새 A」 에서 B 가 A 의 키를 잇고 새 A 는 새 키를 받는다.
       설비 마스터 탭에서 설비명을 고친 호기도 지도가 없으므로 새 키다(지운 호기 + 새 호기).
    4. 결과 키가 겹치면(두 호기가 한 저장본 이름을 이었다) `ValueError` — 한 호기의 일정이 두 호기로
       갈라지지 않게.
    """
    ordered = [str(name) for name in names]
    repeated = sorted({name for name in ordered if ordered.count(name) > 1})
    if repeated:
        raise ValueError(f"설비명이 겹쳐 호기 키를 정할 수 없습니다: {repeated[:5]}")
    keys = {
        name: base_unit_keys[origin]
        for name, origin in inherited_unit_names(ordered, base_unit_keys, renames).items()
    }
    for name in ordered:
        if name not in keys:
            keys[name] = new_key()
    owners: dict[str, list[str]] = {}
    for name in ordered:
        owners.setdefault(keys[name], []).append(name)
    shared = [names_ for names_ in owners.values() if len(names_) > 1]
    if shared:
        detail = ", ".join(" · ".join(group) for group in shared[:5])
        raise ValueError(
            f"한 호기를 둘 이상의 설비명이 이었습니다({detail}) — 이름 바꾸기를 되돌리고 한 호기만 "
            "그 이름을 잇게 하세요."
        )
    return {name: keys[name] for name in ordered}


def inherited_unit_names(
    names: Sequence[str], saved_names: Collection[str], renames: Mapping[str, str]
) -> dict[str, str]:
    """편집본 설비명 → 저장하면 그 호기 키를 이어받을 저장본 설비명(`assign_unit_keys` 의 1·2 규칙
    그대로). 새 키를 받을 이름(새 호기)은 빠진다.

    1. 이름 지도(`renames` — 지금 이름 → 저장본 이름)가 먼저 잇는다.
    2. 남은 이름은 저장본에 같은 이름이 있고 그 호기를 아직 아무도 잇지 않았을 때 잇는다.

    키 정하기(저장)와 가정 설비 시나리오의 배치 칸 임시 잠금(어느 행이 「있던 호기」인가)이 같은
    규칙을 쓴다 — 둘이 갈리면 잠금이 새 호기로 본 행이 저장에서 있던 호기의 공통 칸을 고친다. 같은
    설비명이 여럿이면 첫 것만 잇는다(저장은 겹침으로 거부된다)."""
    saved = set(saved_names)
    inherited: dict[str, str] = {}
    for name in names:
        origin = renames.get(name)
        if origin is not None and origin in saved:
            inherited.setdefault(name, origin)
    used = set(inherited.values())
    for name in names:
        if name not in inherited and name in saved and name not in used:
            inherited[name] = name
            used.add(name)
    return inherited


def split_equipment(
    equipment: pd.DataFrame, unit_keys: Mapping[str, str]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """39칸 설비 마스터를 (공통 32칸 + 키, 키 + 일정 일곱 칸) 로 나눈다. 행 차례는 그대로다.

    모든 행이 일정 쪽에도 한 행씩 나온다 — 어느 행을 실제로 쓸지는 `select_schedule_rows` 가 가른다.
    키가 없는 설비명이 있으면 `KeyError` 다(호출부가 `assign_unit_keys` 를 먼저 부른다).
    """
    frame = equipment.reset_index(drop=True)
    keys = _keys_for(frame[EQUIPMENT_ID_COLUMN], unit_keys)
    common = frame.loc[:, list(COMMON_MASTER_COLUMNS)].copy()
    common[UNIT_KEY_COLUMN] = keys
    schedule = frame.loc[:, list(SCENARIO_SCHEDULE_COLUMNS)].copy()
    schedule.insert(0, UNIT_KEY_COLUMN, keys)
    return common, schedule


def split_downtime(downtime: pd.DataFrame, unit_keys: Mapping[str, str]) -> pd.DataFrame:
    """비가동 일정의 설비명을 호기 키로 바꾼다(키 + 다섯 칸). 행 차례는 그대로다."""
    frame = downtime.reset_index(drop=True)
    result = frame.loc[:, list(DOWNTIME_VALUE_COLUMNS)].copy()
    result.insert(0, UNIT_KEY_COLUMN, _keys_for(frame[EQUIPMENT_ID_COLUMN], unit_keys))
    return result


def _keys_for(names: pd.Series, unit_keys: Mapping[str, str]) -> pd.Series:
    missing = sorted({str(name) for name in names if str(name) not in unit_keys})
    if missing:
        raise KeyError(f"호기 키가 없는 설비명이 있습니다: {missing[:5]}")
    return pd.Series([unit_keys[str(name)] for name in names], index=names.index, dtype="string")


def normalize_schedule_frame(schedule: pd.DataFrame) -> pd.DataFrame:
    """일정 쪽 프레임을 계약 형으로 맞춘다(키 + 일곱 칸).

    DB 에서 읽은 날짜 칸이 모두 NULL 이거나 행이 없으면 날짜형이 아닌 객체 칸일 수 있다 — 그대로
    합치면 합친 마스터의 그 칸이 날짜형이 아니게 된다. 날짜형인 칸은 단위(ns·us)를 건드리지 않는다.
    """
    result = schedule.reindex(columns=list(SCHEDULE_FRAME_COLUMNS)).copy()
    result[UNIT_KEY_COLUMN] = result[UNIT_KEY_COLUMN].astype("string")
    for column in SCENARIO_SCHEDULE_DATE_COLUMNS:
        if not is_datetime64_any_dtype(result[column]):
            result[column] = pd.to_datetime(result[column])
    if not isinstance(result[SCENARIO_MEMO_COLUMN].dtype, pd.StringDtype):
        result[SCENARIO_MEMO_COLUMN] = result[SCENARIO_MEMO_COLUMN].astype("string")
    return result.reset_index(drop=True)


def normalize_schedule_downtime(downtime: pd.DataFrame) -> pd.DataFrame:
    """시나리오 쪽 비가동을 계약 형으로 맞춘다(키 + 다섯 칸, 날짜 둘)."""
    result = downtime.reindex(columns=list(SCHEDULE_DOWNTIME_COLUMNS)).copy()
    for column in SCHEDULE_DOWNTIME_COLUMNS:
        if column in _DOWNTIME_DATE_COLUMNS:
            if not is_datetime64_any_dtype(result[column]):
                result[column] = pd.to_datetime(result[column])
        elif not isinstance(result[column].dtype, pd.StringDtype):
            result[column] = result[column].astype("string")
    return result.reset_index(drop=True)


@dataclass(frozen=True)
class MergedEquipment:
    """공통과 일정을 합친 결과(검증 전).

    - `equipment` — 39칸, 공통 행 차례. 일정 행이 없는 호기도 들고 그 일곱 칸은 비어 있다.
    - `downtime` — 비가동 여섯 칸. 설비명은 키로 **지금 공통 이름**을 붙인다.
    - `unit_key_pairs` — (설비명, 키), 공통 행 차례.
    - `unscheduled_units` — 이 시나리오에 일정 행이 없는 설비명(F4 「일정 없음」).
    - `orphan_rows` — 공통에 없는 키를 가리켜 버린 일정·비가동 행 수.
    """

    equipment: pd.DataFrame
    downtime: pd.DataFrame
    unit_key_pairs: tuple[tuple[str, str], ...]
    unscheduled_units: frozenset[str]
    orphan_rows: int


def merge_equipment(
    common: pd.DataFrame, schedule: pd.DataFrame, downtime: pd.DataFrame
) -> MergedEquipment:
    """공통(32칸 + 키)에 일정(키 + 일곱 칸)·비가동(키 + 다섯 칸)을 키로 붙인다.

    공통 행 차례대로 왼쪽 결합한다(키는 양쪽에서 유일해야 한다 — `validate="one_to_one"`). 일정 행이
    없는 호기는 일정 칸이 비고 `unscheduled_units` 에 든다. 공통에 없는 키의 일정·비가동 행은 버리고
    `orphan_rows` 에 센다. 값 검증은 하지 않는다 — 호출부가 `prepare_equipment_master` 로 한다.
    """
    left = common.reset_index(drop=True)
    keys = left[UNIT_KEY_COLUMN].astype("string")
    if keys.isna().any() or keys.duplicated().any():
        raise ValueError("공통 호기 대장의 호기 키가 비었거나 겹칩니다.")
    known = set(keys.tolist())
    names = left[EQUIPMENT_ID_COLUMN].astype("string")

    right = normalize_schedule_frame(schedule)
    attached = right[UNIT_KEY_COLUMN].isin(known).to_numpy()
    orphan_schedule = int((~attached).sum())
    right = right.loc[attached]

    joined = (
        left.drop(columns=[UNIT_KEY_COLUMN])
        .assign(**{UNIT_KEY_COLUMN: keys})
        .merge(right, on=UNIT_KEY_COLUMN, how="left", validate="one_to_one", indicator=True)
    )
    unscheduled = frozenset(
        str(name) for name in joined.loc[joined["_merge"].eq("left_only"), EQUIPMENT_ID_COLUMN]
    )
    equipment = joined.reindex(columns=list(EQUIPMENT_COLUMNS))
    equipment = _with_schedule_types(equipment).reset_index(drop=True)

    events = normalize_schedule_downtime(downtime)
    owned = events[UNIT_KEY_COLUMN].isin(known).to_numpy()
    orphan_downtime = int((~owned).sum())
    events = events.loc[owned]
    name_by_key = dict(zip(keys.tolist(), names.tolist(), strict=True))
    merged_downtime = events.loc[:, list(DOWNTIME_VALUE_COLUMNS)].copy()
    merged_downtime.insert(
        0,
        EQUIPMENT_ID_COLUMN,
        pd.Series(
            [name_by_key[str(key)] for key in events[UNIT_KEY_COLUMN]],
            index=events.index,
            dtype="string",
        ),
    )
    return MergedEquipment(
        equipment=equipment,
        downtime=merged_downtime.reindex(columns=list(DOWNTIME_COLUMNS)).reset_index(drop=True),
        unit_key_pairs=tuple(
            (str(name), str(key)) for name, key in zip(names.tolist(), keys.tolist(), strict=True)
        ),
        unscheduled_units=unscheduled,
        orphan_rows=orphan_schedule + orphan_downtime,
    )


def _with_schedule_types(equipment: pd.DataFrame) -> pd.DataFrame:
    """합친 마스터의 일정 칸을 계약 형으로 맞춘다(일정 행이 하나도 안 붙으면 객체 칸이 된다)."""
    result = equipment.copy()
    for column in SCENARIO_SCHEDULE_DATE_COLUMNS:
        if not is_datetime64_any_dtype(result[column]):
            result[column] = pd.to_datetime(result[column])
    if not isinstance(result[SCENARIO_MEMO_COLUMN].dtype, pd.StringDtype):
        result[SCENARIO_MEMO_COLUMN] = result[SCENARIO_MEMO_COLUMN].astype("string")
    return result


def calculation_frames(
    baseline: pd.DataFrame,
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    unscheduled_units: Collection[str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """계산에 넘기는 세 표 — 이 시나리오에 일정이 없는 호기와 그 비가동을 뺀다.

    F4 「반입일정이 비면 그 시나리오에는 없는 호기와 같다」 를 그대로 읽는다. 기존설비여부
    Y·보관유무 Y 호기는 반입일정 없이도 보유로 세므로(`services/equipment_availability.py`) 일정
    칸이 빈 것만으로는 빠지지 않는다 — 그래서 일정 행이 없다는 사실(`unscheduled_units`)로 뺀다.
    기존 보유대수는 공통이라 그대로다. 편집·설비 마스터 탭·CSV 는 이 표가 아니라 39칸 전체를 쓴다.
    """
    if not unscheduled_units:
        return baseline, equipment, downtime
    excluded = list(unscheduled_units)
    keep = ~equipment[EQUIPMENT_ID_COLUMN].isin(excluded).to_numpy()
    keep_downtime = ~downtime[EQUIPMENT_ID_COLUMN].isin(excluded).to_numpy()
    return (
        baseline,
        equipment.loc[keep].reset_index(drop=True),
        downtime.loc[keep_downtime].reset_index(drop=True),
    )


def select_schedule_rows(
    schedule: pd.DataFrame,
    *,
    previously_scheduled: Collection[str],
    downtime_keys: Collection[str],
    new_keys: Collection[str],
) -> pd.DataFrame:
    """일정 쪽 프레임에서 이번 리비전에 실제로 쓸 행을 고른다.

    「저장본에 일정 행이 있던 호기 ∪ 일정 일곱 칸에 값이 하나라도 있는 호기 ∪ 비가동이 있는 호기 ∪
    새 호기」. 값 없는 일정 없음 호기는 행을 만들지 않는다 — 다음 읽기에서도 일정 없음이다.
    """
    frame = schedule.reset_index(drop=True)
    keys = frame[UNIT_KEY_COLUMN].astype("string")
    has_value = frame.loc[:, list(SCENARIO_SCHEDULE_COLUMNS)].notna().any(axis=1)
    wanted = (
        has_value
        | keys.isin(list(previously_scheduled))
        | keys.isin(list(downtime_keys))
        | keys.isin(list(new_keys))
    )
    return frame.loc[wanted.fillna(False).to_numpy()].reset_index(drop=True)


def new_unit_keys(unit_keys: Iterable[str], base_common_keys: Collection[str]) -> frozenset[str]:
    """새 호기 = 키가 저장본 공통에 없던 호기."""
    known = set(base_common_keys)
    return frozenset(key for key in unit_keys if key not in known)


def new_downtime_rows(
    base_downtime: pd.DataFrame,
    downtime: pd.DataFrame,
    *,
    exclude_keys: Collection[str] = (),
    unit_keys: Collection[str] | None = None,
) -> pd.DataFrame:
    """편집본 비가동(키 + 다섯 칸) 가운데 다른 시나리오에 함께 넣을 **새 비가동**만 고른다.

    한 비가동은 (호기 키, 유형, 시작일) 로 가린다. 저장본에 없던 행이라도 고침이면 새 비가동이
    아니다 — 결정 「고치기·지우기는 지금 시나리오만」. 고친 행이 다른 시나리오에 옛 행과 겹친 공사로
    남지 않게(겹침은 검증이 막지 않아 가용대수가 두 번 줄어든다) 이번에 사라진 행과 닮은 새 행은
    모두 고침으로 본다:

    - 같은 호기 키에서 이번에 사라진 행이 있으면 그 호기의 새 행은 모두 고침이다(시작일·유형 가운데
      하나든 둘 다든).
    - 같은 (유형, 시작일) 의 행이 다른 호기에서 사라졌으면 고침이다(비가동 행의 설비명만 옮김).

    한 저장에서 옛 비가동을 지우고 같은 호기에 새 비가동을 넣으면 새 것도 이 시나리오에만 남는다 —
    퍼뜨리지 않는 쪽으로 틀린다(결과 알림의 「함께 넣은 목록」 에 없으니 보인다).

    `exclude_keys`(보통 새 호기)의 비가동은 고르지 않는다 — 새 호기 비가동은 새 호기 넣기를 따른다.
    `unit_keys`(편집본 공통의 호기 키)를 주면 지운 호기와 함께 빠진 비가동은 둘째 규칙에서 뺀다 —
    옮긴 것이 아니라 호기째 지운 것이다.
    """
    base_ids = downtime_identities(base_downtime)
    frame = downtime.reset_index(drop=True)
    ids = downtime_identities(frame)
    removed = set(base_ids) - set(ids)
    kept = None if unit_keys is None else {str(key) for key in unit_keys}
    removed_keys = {key for key, _, _ in removed}
    removed_events = {(kind, start) for key, kind, start in removed if kept is None or key in kept}
    excluded = {str(key) for key in exclude_keys}
    known = set(base_ids)
    wanted = [
        identity not in known
        and identity[0] not in excluded
        and identity[0] not in removed_keys
        and (identity[1], identity[2]) not in removed_events
        for identity in ids
    ]
    return frame.loc[wanted].reset_index(drop=True)


def downtime_identities(frame: pd.DataFrame) -> list[tuple[str, str, str]]:
    """비가동 행(키 + 다섯 칸)마다 (호기 키, 유형, 시작일 `YYYY-MM-DD`). 날짜 단위(ns·us)와
    무관하게 견준다."""
    return [
        (str(key), str(kind), pd.Timestamp(start).strftime("%Y-%m-%d"))
        for key, kind, start in zip(
            frame[UNIT_KEY_COLUMN], frame["비가동유형"], frame["시작일"], strict=True
        )
    ]


class MergedView(Protocol):
    """합친 한 벌 — 39칸 마스터·비가동·(설비명, 호기 키)·일정 없음. `MergedEquipment` 와
    `persistence` 의 `EquipmentSnapshot` 이 이 꼴이다(이 모듈은 저장소 모델을 모른다)."""

    @property
    def equipment(self) -> pd.DataFrame: ...

    @property
    def downtime(self) -> pd.DataFrame: ...

    @property
    def unit_key_pairs(self) -> tuple[tuple[str, str], ...]: ...

    @property
    def unscheduled_units(self) -> frozenset[str]: ...


@dataclass(frozen=True)
class ScheduleRestorePreview:
    """일정 리비전 하나를 **지금 공통 대장**과 합쳐 그 시나리오 최신 자리에 놓으면 무엇이 바뀌는가.

    E7 「이 리비전으로 되돌리기」 확인 글과 「여기서 새 시나리오」 안내가 쓴다. 수는 모두 지금 공통
    대장의 호기 기준이다(그 뒤로 지운 호기의 옛 일정은 합칠 때 버려져 어디에도 세지 않는다).

    - `changed_units` — 일정(날짜 여섯·시나리오 메모·일정 행 있음/없음)이나 비가동이 하나라도
      달라지는 호기 수. 0 이면 되돌릴 것이 없다(`identical`).
    - `downtime_rows_before`·`downtime_rows_after` — 비가동 행 수(지금 최신 → 되돌린 뒤).
    - `unscheduled_after` — 되돌린 뒤 일정 없음 호기 수(그 리비전에 일정 행이 없는 호기).
    - `newly_unscheduled` — 지금은 일정이 있다가 되돌리면 일정 없음이 되는 호기 수.
    - `added_since` — 그 리비전을 저장한 뒤 공통 대장에 든 호기 수. 그 리비전은 그 호기를 몰라
      일정 행이 없으므로 늘 일정 없음이 된다(F4 — 그 시나리오 계산·Space 에서 빠진다).
    """

    changed_units: int = 0
    downtime_rows_before: int = 0
    downtime_rows_after: int = 0
    unscheduled_after: int = 0
    newly_unscheduled: int = 0
    added_since: int = 0

    @property
    def identical(self) -> bool:
        """일정·비가동이 모든 호기에서 같다 — 되돌려도 새 리비전을 만들지 않는다."""
        return self.changed_units == 0


def schedule_restore_preview(
    current: MergedView,
    restored: MergedView,
    *,
    source_unit_keys: Collection[str],
) -> ScheduleRestorePreview:
    """지금 최신(`current`)과 되돌릴 리비전(`restored`)을 호기마다 견준다.

    두 한 벌은 **같은 공통 대장**과 합친 것이어야 한다(호기 키 쌍이 같다 — 다르면 `ValueError`).
    일정은 날짜 여섯·시나리오 메모와 일정 행 있음/없음을, 비가동은 그 호기의 (유형·시작일·종료일·
    상세사유·비고) 묶음을 차례와 무관하게 견준다 — 비가동 행 차례는 내용이 아니다.
    `source_unit_keys` 는 그 리비전을 저장할 때 함께 본 공통 대장의 호기 키다(`added_since`).
    """
    if tuple(current.unit_key_pairs) != tuple(restored.unit_key_pairs):
        raise ValueError("두 한 벌의 공통 대장이 달라 일정을 견줄 수 없습니다.")
    before = _schedule_signatures(current)
    after = _schedule_signatures(restored)
    before_events = _downtime_signatures(current.downtime)
    after_events = _downtime_signatures(restored.downtime)
    known = {str(key) for key in source_unit_keys}
    changed = 0
    newly_unscheduled = 0
    added_since = 0
    for name, key in current.unit_key_pairs:
        if before[name] != after[name] or before_events.get(name, ()) != after_events.get(name, ()):
            changed += 1
        if before[name] is not None and after[name] is None:
            newly_unscheduled += 1
        if key not in known:
            added_since += 1
    return ScheduleRestorePreview(
        changed_units=changed,
        downtime_rows_before=len(current.downtime),
        downtime_rows_after=len(restored.downtime),
        unscheduled_after=sum(1 for value in after.values() if value is None),
        newly_unscheduled=newly_unscheduled,
        added_since=added_since,
    )


def _comparable(value: Any) -> str:
    """견주기용 글자 — 빈 값은 빈 글자, 날짜는 `YYYY-MM-DD`(단위 ns·us 와 무관)."""
    if value is None or (not isinstance(value, str) and bool(pd.isna(value))):
        return ""
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _schedule_signatures(view: MergedView) -> dict[str, tuple[str, ...] | None]:
    """설비명 → 일곱 칸 글자(일정 없음 호기는 None)."""
    frame = view.equipment
    names = [str(name) for name in frame[EQUIPMENT_ID_COLUMN]]
    rows = frame.loc[:, list(SCENARIO_SCHEDULE_COLUMNS)].itertuples(index=False, name=None)
    unscheduled = view.unscheduled_units
    return {
        name: None if name in unscheduled else tuple(_comparable(value) for value in row)
        for name, row in zip(names, rows, strict=True)
    }


def _downtime_signatures(downtime: pd.DataFrame) -> dict[str, tuple[tuple[str, ...], ...]]:
    """설비명 → 그 호기 비가동 다섯 칸 글자 묶음(정렬 — 차례와 무관)."""
    grouped: dict[str, list[tuple[str, ...]]] = {}
    names = [str(name) for name in downtime[EQUIPMENT_ID_COLUMN]]
    rows = downtime.loc[:, list(DOWNTIME_VALUE_COLUMNS)].itertuples(index=False, name=None)
    for name, row in zip(names, rows, strict=True):
        grouped.setdefault(name, []).append(tuple(_comparable(value) for value in row))
    return {name: tuple(sorted(events)) for name, events in grouped.items()}
