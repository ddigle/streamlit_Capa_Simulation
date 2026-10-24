# Purpose: Space 동·층 사용 상태 프로필의 모델·값 검증·층 고르기 거르기·층별 호기 셈 규칙을 둔다.

"""Space 동·층 사용 상태(2026-10-24 사용자 결정 S1~S6).

저장은 설비 DB 의 `equipment_ops.floor_state_profile`·`floor_state`(설비 `0029`)이고 SQL 은
`persistence/floor_state_store.py` 가 갖는다. 이 모듈은 Streamlit·DB 를 모르는 규칙만 둔다.

- 층마다 「사용」(기본, 행 없음) 또는 「비활성」 하나다. 비활성에는 사유 둘 가운데 하나가 붙는다 —
  `UNUSED`(사용 안 함)·`NOT_LINE`(생산라인 아님).
- 모두에게 같은 공용 현행값이고 설비 시나리오·설비 리비전과 무관하다(S6).
- **저장 검사는 그대로다**(S5) — 설비 마스터의 동·층 범위(C1~C5·1F~6F)는 비활성 층도 통과한다.
  비활성은 Space 목록·도면과 층 고르기(층 바로 가기·「다른 층으로 보내기」·RawData 동·층 칸)에서만
  숨긴다.
- 읽기는 관용이다 — 저장소가 읽은 행에 모르는 동·층이 있으면 버리고, 모르는 사유는
  `inactive_label` 이 「비활성」 으로 그린다. 저장 입구(`prepare_floor_states`)만 엄격하다.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final

import pandas as pd

from capa_simulation.services.equipment_contract import (
    EQUIPMENT_ID_COLUMN,
    LAYOUT_EXITED_COLUMN,
    VALID_BUILDINGS,
    VALID_FLOORS,
)
from capa_simulation.services.equipment_units import unit_keys
from capa_simulation.services.fab_layout import FLOOR_KEYS, floor_label
from capa_simulation.services.floor_layout_profile import FloorKey

__all__ = [
    "ACTIVE_STATE",
    "DEFAULT_FLOOR_REASON",
    "FLOOR_REASONS",
    "FLOOR_REASON_CHOICES",
    "FLOOR_REASON_LABELS",
    "FloorStates",
    "building_active_count",
    "building_state",
    "floor_states_fingerprint",
    "floor_unit_counts",
    "floors_by_building",
    "inactive_floor_summary",
    "inactive_floor_warnings",
    "inactive_label",
    "master_location_options",
    "newly_inactive",
    "prepare_floor_states",
    "selectable_floor_keys",
    "with_building",
]

FLOOR_REASONS: Final = ("UNUSED", "NOT_LINE")
# 도면 블록·목록 표·풍선·배너의 짧은 글.
FLOOR_REASON_LABELS: Final[Mapping[str, str]] = {
    "UNUSED": "사용 안 함",
    "NOT_LINE": "생산라인 아님",
}
# 편집표 사유 칸에서만 쓰는 긴 글(뜻을 함께 보인다).
FLOOR_REASON_CHOICES: Final[Mapping[str, str]] = {
    "UNUSED": "사용 안 함",
    "NOT_LINE": "생산라인 아님(사무·창고 등)",
}
# 사유를 비운 채 끈 층(편집표 `사용` 만 끈 칸)은 이 사유다 — 비활성에는 늘 사유가 있다(S1).
DEFAULT_FLOOR_REASON: Final = "UNUSED"
# 동 머리 줄의 「그 동 6개 층 모두 사용」 값. 사유 코드와 겹치지 않는다.
ACTIVE_STATE: Final = "ACTIVE"
# 모르는 사유 코드(앞으로 사유를 더한 DB 를 옛 코드가 읽음)의 글.
_UNKNOWN_REASON_LABEL: Final = "비활성"
# 저장 미리보기 경고에 이름을 적는 호기 수.
_WARNING_NAME_LIMIT: Final = 5

FloorRow = tuple[str, str, str]


@dataclass(frozen=True)
class FloorStates:
    """동·층 사용 상태 한 벌. `version` 0 은 한 번도 저장하지 않은 것(모두 사용)이다.

    `rows` 는 비활성 층만의 (동, 층, 사유 코드)이고 `FLOOR_KEYS` 차례다 — 캐시에 실리도록 기본형
    튜플로 둔다(AGENTS 5장 21). 아래 읽기 도우미는 `rows` 로 정해지는 값이라 필드가 아니다(캐시는
    init 필드만 싣는다).
    """

    rows: tuple[FloorRow, ...] = ()
    version: int = 0
    source: str = ""
    updated_at: datetime | None = None

    @property
    def inactive(self) -> dict[FloorKey, str]:
        """비활성 층 → 사유 코드."""
        return {(building, floor): reason for building, floor, reason in self.rows}

    def reason_of(self, key: FloorKey) -> str | None:
        """그 층의 사유 코드. 사용이면 None."""
        return self.inactive.get(key)

    def is_active(self, key: FloorKey) -> bool:
        return key not in self.inactive

    @property
    def active_keys(self) -> tuple[FloorKey, ...]:
        """사용 층(`FLOOR_KEYS` 차례)."""
        inactive = self.inactive
        return tuple(key for key in FLOOR_KEYS if key not in inactive)


def _floor_key(value: object) -> FloorKey | None:
    """(동, 층) 짝이 FAB 의 30개 층이면 그 키, 아니면 None."""
    if not isinstance(value, tuple) or len(value) != 2:
        return None
    key = (str(value[0]), str(value[1]))
    return key if key in FLOOR_KEYS else None


def inactive_label(code: str) -> str:
    """사유 코드 → 짧은 글. 모르는 코드는 「비활성」 — 읽기에서 막지 않는다."""
    return FLOOR_REASON_LABELS.get(code, _UNKNOWN_REASON_LABEL)


def prepare_floor_states(raw: Mapping[FloorKey, object]) -> tuple[FloorRow, ...]:
    """저장 입구 검증. 비활성 층 → 사유 코드를 `FLOOR_KEYS` 차례의 행으로 돌려준다.

    키는 FAB 의 30개 층이어야 하고, 값은 `FLOOR_REASONS` 의 코드다. 빈 값·None 은 「사용」 이라 행이
    없다. 그 밖의 값은 조용히 버리지 않고 `ValueError` 다.
    """
    prepared: dict[FloorKey, str] = {}
    for raw_key, value in raw.items():
        key = _floor_key(raw_key)
        if key is None:
            raise ValueError(f"FAB 의 층이 아닙니다: {raw_key!r}")
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        if not isinstance(value, str) or value.strip() not in FLOOR_REASONS:
            raise ValueError(
                f"층 사용 사유는 {'·'.join(FLOOR_REASON_LABELS.values())} 가운데 하나여야 "
                f"합니다: {floor_label(key)} {value!r}"
            )
        prepared[key] = value.strip()
    return tuple((key[0], key[1], prepared[key]) for key in FLOOR_KEYS if key in prepared)


def floor_states_fingerprint(states: FloorStates) -> str:
    """비활성 층·사유의 지문(FAB 뷰어 epoch). version 은 넣지 않는다 — 같은 내용이면 같다."""
    payload = "|".join(f"{building}:{floor}:{reason}" for building, floor, reason in states.rows)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _building_keys(building: str) -> tuple[FloorKey, ...]:
    return tuple(key for key in FLOOR_KEYS if key[0] == building)


def building_state(draft: Mapping[FloorKey, str], building: str) -> str | None:
    """동 머리 줄의 지금 값 — 그 동 6개 층이 모두 사용이면 `ACTIVE_STATE`, 모두 같은 사유면 그
    코드, 섞였으면 None."""
    reasons = {draft.get(key) for key in _building_keys(building)}
    if len(reasons) != 1:
        return None
    (only,) = reasons
    return ACTIVE_STATE if only is None else only


def building_active_count(draft: Mapping[FloorKey, str], building: str) -> tuple[int, int]:
    """(사용 층 수, 그 동 층 수) — 섞인 동 머리 라벨 「사용 4/6」."""
    keys = _building_keys(building)
    return sum(1 for key in keys if key not in draft), len(keys)


def with_building(
    draft: Mapping[FloorKey, str], building: str, reason: str | None
) -> dict[FloorKey, str]:
    """그 동 6개 층을 한꺼번에 — None(또는 `ACTIVE_STATE`)은 모두 사용, 코드는 모두 그 사유. 다른
    동은 그대로다."""
    result = {key: value for key, value in draft.items() if key[0] != building}
    if reason is not None and reason != ACTIVE_STATE:
        result.update({key: reason for key in _building_keys(building)})
    return {key: result[key] for key in FLOOR_KEYS if key in result}


def newly_inactive(before: FloorStates, draft: Mapping[FloorKey, str]) -> tuple[FloorKey, ...]:
    """저장본에서 사용이던 층 가운데 초안에서 비활성인 것(`FLOOR_KEYS` 차례). 사유만 바꾼 층은
    들지 않는다 — 호기 있는 층 끄기 확인(S4)의 대상이다."""
    saved = before.inactive
    return tuple(key for key in FLOOR_KEYS if key in draft and key not in saved)


def floor_unit_counts(status: pd.DataFrame) -> dict[FloorKey, int]:
    """층마다 아직 그 층에 있는 **설비 대수**(끄기 확인의 n).

    동·층이 그 층이고 도면 이탈(`LAYOUT_EXITED_COLUMN`)이 아닌 행의 설비키 수다 — Main 설비로 묶은
    모듈 행은 1대, 레이아웃표시 Y·N 모두 센다. FAB 의 30개 층 밖 행은 버린다. 행이 없는 층은 키가
    없다. 목록 표 `배치대수`·`미배치대수`(기준일·필터 안·설비지분 합)와 기준이 다르다.
    """
    if status.empty or "동" not in status.columns or "층" not in status.columns:
        return {}
    frame = status
    if LAYOUT_EXITED_COLUMN in frame.columns:
        frame = frame.loc[~frame[LAYOUT_EXITED_COLUMN].fillna(False).astype(bool)]
    if frame.empty or EQUIPMENT_ID_COLUMN not in frame.columns:
        return {}
    keys = unit_keys(frame)
    buildings = frame["동"].astype("string").str.strip()
    floors = frame["층"].astype("string").str.strip()
    counts: dict[FloorKey, set[str]] = {}
    for building, floor, unit in zip(buildings, floors, keys, strict=True):
        if pd.isna(building) or pd.isna(floor) or pd.isna(unit) or not str(unit):
            continue
        key = (str(building), str(floor))
        if key in FLOOR_KEYS:
            counts.setdefault(key, set()).add(str(unit))
    return {key: len(counts[key]) for key in FLOOR_KEYS if key in counts}


def selectable_floor_keys(
    states: FloorStates, *, keep: FloorKey | None = None
) -> tuple[FloorKey, ...]:
    """고를 수 있는 층 = 사용 층 + `keep`(지금 연 층이 비활성이면 그 층). `FLOOR_KEYS` 차례.

    `층 바로 가기`·`다른 층으로 보내기` 가 같이 쓴다.
    """
    inactive = states.inactive
    return tuple(key for key in FLOOR_KEYS if key not in inactive or key == keep)


def floors_by_building(states: FloorStates) -> dict[str, tuple[str, ...]]:
    """동 → 사용 층(`VALID_FLOORS` 차례). 사용 층이 하나도 없는 동도 빈 튜플로 든다."""
    inactive = states.inactive
    return {
        building: tuple(
            floor
            for floor in VALID_FLOORS
            if (building, floor) in FLOOR_KEYS and (building, floor) not in inactive
        )
        for building in VALID_BUILDINGS
    }


def _present_values(present: pd.DataFrame, column: str, valid: Iterable[str]) -> set[str]:
    if present.empty or column not in present.columns:
        return set()
    values = set(present[column].dropna().astype("string").str.strip())
    return values & set(valid)


def master_location_options(
    states: FloorStates, present: pd.DataFrame
) -> tuple[list[str], list[str]]:
    """설비 마스터 편집표 동·층 **칸 단위** 선택지(동 목록, 층 목록).

    동 = 사용 층이 하나라도 있는 동 ∪ 표에 이미 있는 유효 동, 층 = 어느 동에서든 사용인 층 ∪ 표에
    이미 있는 유효 층. 차례는 `VALID_BUILDINGS`·`VALID_FLOORS` 다. 표에 있는 값을 남기는 까닭 —
    Streamlit 1.63 은 선택지 밖 값을 칸 오류로 그린다(비활성 층에 남은 호기 행이 빨갛게 서면 안
    된다). 동·층이 따로인 칸이라 「C1 + 3F」 처럼 짝만 꺼진 층은 여기서 거르지 못한다.
    """
    active = states.active_keys
    buildings_in_use = {key[0] for key in active} | _present_values(present, "동", VALID_BUILDINGS)
    floors_in_use = {key[1] for key in active} | _present_values(present, "층", VALID_FLOORS)
    return (
        [building for building in VALID_BUILDINGS if building in buildings_in_use],
        [floor for floor in VALID_FLOORS if floor in floors_in_use],
    )


def _floor_runs(floors: Iterable[str]) -> str:
    """「1F·2F·3F·5F」 → 「1F~3F·5F」(`VALID_FLOORS` 차례로 이어진 층을 줄인다)."""
    order = {floor: index for index, floor in enumerate(VALID_FLOORS)}
    ranked = sorted({floor for floor in floors if floor in order}, key=order.__getitem__)
    parts: list[str] = []
    start = previous = None
    for floor in ranked:
        if previous is not None and order[floor] == order[previous] + 1:
            previous = floor
            continue
        if start is not None and previous is not None:
            parts.append(start if start == previous else f"{start}~{previous}")
        start = previous = floor
    if start is not None and previous is not None:
        parts.append(start if start == previous else f"{start}~{previous}")
    return "·".join(parts)


def inactive_floor_summary(states: FloorStates) -> str:
    """비활성 층을 동·사유마다 줄여 적은 글 — 「C1 3F(사용 안 함) · C5 1F~6F(생산라인 아님)」.
    비활성 층이 없으면 빈 글."""
    parts: list[str] = []
    inactive = states.inactive
    for building in VALID_BUILDINGS:
        by_reason: dict[str, list[str]] = {}
        for key in _building_keys(building):
            reason = inactive.get(key)
            if reason is not None:
                by_reason.setdefault(inactive_label(reason), []).append(key[1])
        for label, floors in by_reason.items():
            parts.append(f"{building} {_floor_runs(floors)}({label})")
    return " · ".join(parts)


def _locations(frame: pd.DataFrame) -> dict[str, FloorKey | None]:
    """설비명 → (동, 층). 동·층이 비면 None."""
    if frame.empty or EQUIPMENT_ID_COLUMN not in frame.columns:
        return {}
    names = frame[EQUIPMENT_ID_COLUMN].astype("string").str.strip()
    buildings = (
        frame["동"].astype("string").str.strip()
        if "동" in frame.columns
        else pd.Series(pd.NA, index=frame.index, dtype="string")
    )
    floors = (
        frame["층"].astype("string").str.strip()
        if "층" in frame.columns
        else pd.Series(pd.NA, index=frame.index, dtype="string")
    )
    located: dict[str, FloorKey | None] = {}
    for name, building, floor in zip(names, buildings, floors, strict=True):
        if pd.isna(name) or not str(name):
            continue
        located[str(name)] = (
            None if pd.isna(building) or pd.isna(floor) else (str(building), str(floor))
        )
    return located


def inactive_floor_warnings(
    master: pd.DataFrame, saved: pd.DataFrame, states: FloorStates
) -> list[str]:
    """저장 미리보기 경고(막지 않는다). 편집본에서 동·층이 비활성 층이고 저장본과 다른(새 행 포함)
    호기를 한 줄로 말한다. 그대로인 호기는 세지 않는다 — 이미 그 층에 있던 호기다."""
    inactive = states.inactive
    if not inactive:
        return []
    before = _locations(saved)
    moved: dict[str, FloorKey] = {}
    for name, key in _locations(master).items():
        if key is None or key not in inactive:
            continue
        if name in before and before[name] == key:
            continue
        moved[name] = key
    if not moved:
        return []
    floors = [key for key in FLOOR_KEYS if key in set(moved.values())]
    where = " · ".join(f"{floor_label(key)} {inactive_label(inactive[key])}" for key in floors)
    names = list(moved)
    shown = ", ".join(names[:_WARNING_NAME_LIMIT])
    more = f" 외 {len(names) - _WARNING_NAME_LIMIT}대" if len(names) > _WARNING_NAME_LIMIT else ""
    return [
        f"비활성 층으로 옮긴 호기 {len(names)}대 — 저장은 되지만 Space 목록·도면에서 "
        f"숨습니다({where}): {shown}{more}"
    ]
