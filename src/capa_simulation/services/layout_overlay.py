# Purpose: 가정 설비 시나리오 배치 차이를 공식에 얹고·편집본에서 뽑고·같아진 것을 지운다.

"""가정 설비 시나리오의 Space 배치 차이(설비 `0031`).

**공식 배치**는 공통 대장의 배치 일곱 칸(`SCENARIO_LAYOUT_COLUMNS`)과 층 현행값(도면 요소·Main
설비명 위치)이다. 가정 설비 시나리오는 그 위의 **공식과 다른 것만**(2026-10-24 사용자 결정
LY1·LY2)을 일정 리비전마다 든다 — 손대지 않은 호기·요소는 공식을 따라간다.

- 호기 차이 한 행 = 호기 키 하나의 일곱 칸 **통째**(Q5)와 저장 당시 Main 설비. Main 설비 모듈
  묶음(Main 설비 행 둘 이상 — `space_layout_edit.module_group_rows`)은 **묶음 통째**다.
- 도면 요소 차이 = (층, 요소 id) 마다 `set`(그 id 의 요소 통째) 또는 `drop`(공식 요소를 지움).
- Main 설비명 위치 차이 = (층, Main 설비) 마다 위치 또는 None(공식의 그 행을 지워 처음 위치).

얹기(`apply_unit_overlay`)는 예외를 내지 않고 늘 「모듈 행 동·층 같음」 을 지키는 마스터를 낸다 —
공식에서 묶음 소속이 바뀐 모듈은 그 가정 배치에서 동·층만 묶음에 맞추고 X·Y 를 비운다(설계 5-2).
쓰기 때 정규화(`normalize_layout_overlay`)는 공식과 같아진 차이를 지운다(설계 5-6). 이 모듈은 DB·
화면을 모른다 — 읽기·쓰기 차례는 `persistence/equipment_repository.py` 가 정한다.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, fields
from typing import Any, Final, Literal, cast

import pandas as pd

from capa_simulation.services.equipment_contract import (
    EQUIPMENT_ID_COLUMN,
    PARENT_EQUIPMENT_COLUMN,
    SCENARIO_LAYOUT_COLUMNS,
)
from capa_simulation.services.floor_layout_mark import FloorLayoutMark
from capa_simulation.services.floor_layout_profile import CANVAS_DECIMALS, FloorKey
from capa_simulation.services.space_layout_edit import module_group_rows, natural_name_key

# 호기 하나의 배치 일곱 칸 — (동, 층, X좌표, Y좌표, Xsize, Ysize, 레이아웃표시). 동·층은 앞뒤 공백을
# 걷은 글자(빈 글은 None), 숫자는 `CANVAS_DECIMALS` 로 반올림(빈 값은 None), 레이아웃표시는 대문자.
Place = tuple[str | None, str | None, float | None, float | None, float | None, float | None, str]
# 호기 하나의 배치 일곱 칸 **원래 값**(표 칸 그대로 — 반올림 없음). 공통 프레임에 공식 값을 다시
# 적을 때 쓴다 — `Place` 는 견줄 꼴이라 그대로 적으면 좌표가 반올림된다.
LayoutCells = tuple[object, ...]
# 호기 차이 한 행 — (호기 키, 저장 당시 Main 설비, 일곱 칸).
UnitChange = tuple[str, str | None, Place]
# Main 설비명 위치 차이 한 행 — (Main 설비, 위치 또는 None = 공식 행을 지움).
LabelChange = tuple[str, str | None]
# 저장 역할 — 공식 설비 시나리오면 공식 배치(공통·층 현행값)를, 가정이면 그 시나리오의 배치
# 차이를 쓴다.
LayoutRole = Literal["official", "overlay"]
LAYOUT_ROLES: Final = ("official", "overlay")

# 빈 배치 차이의 지문(`layout_hash`). 0031 뒤 코드는 빈 차이에도 이 값을 적는다 — NULL 은 이관
# 리비전이거나 0031 을 모르는 코드가 쓴 리비전이다.
EMPTY_LAYOUT_DIGEST: Final = "empty"
MARK_CHANGE_KINDS: Final = ("set", "drop")
# 일정 리비전 출처(`origin`)의 허용값 — 0027 DDL 주석의 다섯에 「배치 차이 모두 지우기」·공식 발행
# 정리(`layout_clear`)를 더한다. DuckDB 는 CHECK 를 고칠 수 없어 서비스가 본다.
SCHEDULE_REVISION_ORIGINS: Final = (
    "legacy",
    "save",
    "clone",
    "propagate",
    "restore",
    "layout_clear",
)
_UNKNOWN_FLOOR: Final = "미정"


@dataclass(frozen=True)
class MarkChange:
    """층 도면 요소 차이 하나 — `kind` 가 "set" 이면 `mark` 가 그 id 의 요소 통째, "drop" 이면
    None."""

    mark_id: str
    kind: str
    mark: FloorLayoutMark | None = None


FloorMarkChanges = tuple[FloorKey, tuple[MarkChange, ...]]
FloorLabelChanges = tuple[FloorKey, tuple[LabelChange, ...]]


@dataclass(frozen=True)
class LayoutOverlay:
    """일정 리비전 하나의 배치 차이(저장소·화면 사이의 값).

    캐시에는 이것이 아니라 기본형 payload(`to_payload`)를 싣고 꺼낼 때 `from_payload` 로 지금
    클래스를 다시 만든다(AGENTS 5장 21). 만들 때는 `make_layout_overlay` 를 써 차례를 맞춘다 —
    지문이 차례에 흔들리지 않게.
    """

    units: tuple[UnitChange, ...] = ()
    marks: tuple[FloorMarkChanges, ...] = ()
    labels: tuple[FloorLabelChanges, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.units or self.marks or self.labels)

    def marks_for(self, key: FloorKey) -> tuple[MarkChange, ...]:
        """그 층의 도면 요소 차이(없으면 빈 튜플)."""
        return next((changes for floor, changes in self.marks if floor == key), ())

    def labels_for(self, key: FloorKey) -> tuple[LabelChange, ...]:
        """그 층의 Main 설비명 위치 차이(없으면 빈 튜플)."""
        return next((changes for floor, changes in self.labels if floor == key), ())

    @property
    def floors(self) -> tuple[FloorKey, ...]:
        """요소·이름표 차이가 있는 층(차례대로)."""
        return tuple(
            sorted({floor for floor, _ in self.marks} | {floor for floor, _ in self.labels})
        )

    @property
    def unit_keys(self) -> frozenset[str]:
        return frozenset(key for key, _, _ in self.units)

    @property
    def mark_count(self) -> int:
        return sum(len(changes) for _, changes in self.marks)

    @property
    def label_count(self) -> int:
        return sum(len(changes) for _, changes in self.labels)

    def digest(self) -> str:
        """정렬한 내용 해시(`layout_hash`). 빈 차이는 `EMPTY_LAYOUT_DIGEST`."""
        if not self:
            return EMPTY_LAYOUT_DIGEST
        text = json.dumps(self.to_payload(), ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def without_units(self) -> LayoutOverlay:
        """호기 차이를 뺀 것(합친 본문에 이미 든 호기 차이를 다시 싣지 않는 캐시 칸용)."""
        return LayoutOverlay(marks=self.marks, labels=self.labels)

    def to_payload(self) -> dict[str, object]:
        """기본형(튜플·dict·str·float·bool·None)만 든 값. 요소는 필드 이름 → 값 dict 이다."""
        return {
            "units": tuple((key, parent, tuple(place)) for key, parent, place in self.units),
            "marks": tuple(
                (
                    tuple(floor),
                    tuple(
                        (change.mark_id, change.kind, _mark_payload(change.mark))
                        for change in changes
                    ),
                )
                for floor, changes in self.marks
            ),
            "labels": tuple(
                (tuple(floor), tuple((parent, spot) for parent, spot in changes))
                for floor, changes in self.labels
            ),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> LayoutOverlay:
        """`to_payload` 의 값(튜플이든 JSON 목록이든)에서 **지금 클래스**로 다시 만든다."""
        units = tuple(
            (str(key), None if parent is None else str(parent), _place_from(place))
            for key, parent, place in _items(payload.get("units"))
        )
        marks = tuple(
            (
                _floor_from(floor),
                tuple(
                    MarkChange(
                        mark_id=str(mark_id),
                        kind=str(kind),
                        mark=None if mark is None else FloorLayoutMark(**dict(mark)),
                    )
                    for mark_id, kind, mark in _items(changes)
                ),
            )
            for floor, changes in _items(payload.get("marks"))
        )
        labels = tuple(
            (
                _floor_from(floor),
                tuple(
                    (str(parent), None if spot is None else str(spot))
                    for parent, spot in _items(changes)
                ),
            )
            for floor, changes in _items(payload.get("labels"))
        )
        return cls(units=units, marks=marks, labels=labels)


def _mark_payload(mark: FloorLayoutMark | None) -> dict[str, Any] | None:
    if mark is None:
        return None
    return {item.name: getattr(mark, item.name) for item in fields(FloorLayoutMark)}


def _items(value: object) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"배치 차이 payload 꼴이 아닙니다: {type(value).__name__}")
    return list(value)


def _floor_from(value: object) -> FloorKey:
    building, floor = _items(value)
    return str(building), str(floor)


def _place_from(value: object) -> Place:
    building, floor, x, y, w, h, flag = _items(value)
    return (
        None if building is None else str(building),
        None if floor is None else str(floor),
        _number(x),
        _number(y),
        _number(w),
        _number(h),
        str(flag),
    )


def make_layout_overlay(
    units: Iterable[UnitChange] = (),
    marks: Mapping[FloorKey, Sequence[MarkChange]] | None = None,
    labels: Mapping[FloorKey, Sequence[LabelChange]] | None = None,
) -> LayoutOverlay:
    """차례를 맞춘 배치 차이 — 호기는 키 차례, 층은 (동, 층) 차례, 이름표는 Main 설비 차례. 요소는
    받은 차례 그대로다(새 요소를 그리는 차례). 빈 층은 뺀다."""
    unit_rows = tuple(sorted(units, key=lambda row: row[0]))
    mark_rows = tuple(
        (floor, tuple(changes)) for floor, changes in sorted((marks or {}).items()) if changes
    )
    label_rows = tuple(
        (floor, tuple(sorted(changes, key=lambda row: row[0])))
        for floor, changes in sorted((labels or {}).items())
        if changes
    )
    return LayoutOverlay(units=unit_rows, marks=mark_rows, labels=label_rows)


# ------------------------------------------------------------------ 호기 배치


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(number, CANVAS_DECIMALS)


def _text(value: object) -> str | None:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    return text or None


def _flag(value: object) -> str:
    text = _text(value)
    return text.upper() if text is not None else ""


def place_of(row: Mapping[str, object] | pd.Series[Any]) -> Place:
    """한 행의 배치 일곱 칸을 견줄 꼴로(동·층 앞뒤 공백 걷음·빈 글은 None, 숫자 반올림·NaN 은 None,
    레이아웃표시 대문자)."""
    building, floor, x, y, w, h, flag = (row.get(column) for column in SCENARIO_LAYOUT_COLUMNS)
    return (
        _text(building),
        _text(floor),
        _number(x),
        _number(y),
        _number(w),
        _number(h),
        _flag(flag),
    )


def _places(frame: pd.DataFrame) -> list[Place]:
    """행마다 `place_of` (같은 반올림 — 행 하나와 표 전체가 갈리지 않게)."""
    columns = [frame[column].tolist() for column in SCENARIO_LAYOUT_COLUMNS]
    return [
        (
            _text(building),
            _text(floor),
            _number(x),
            _number(y),
            _number(w),
            _number(h),
            _flag(flag),
        )
        for building, floor, x, y, w, h, flag in zip(*columns, strict=True)
    ]


def _parent_of(value: object) -> str | None:
    return _text(value)


@dataclass(frozen=True)
class LayoutBase:
    """공식(공통) 배치 한 벌 — 호기 키마다 일곱 칸·Main 설비·설비명, 모듈 묶음에 든 키의 Main 설비.

    `keys` 는 표 차례다. 묶음(`groups`)은 `space_layout_edit.module_group_rows` 한 규칙이다.
    """

    keys: tuple[str, ...]
    places: Mapping[str, Place]
    parents: Mapping[str, str | None]
    names: Mapping[str, str]
    groups: Mapping[str, str]

    def members(self) -> dict[str, list[str]]:
        """모듈 묶음(Main 설비) → 그 키들(표 차례)."""
        result: dict[str, list[str]] = {}
        for key in self.keys:
            group = self.groups.get(key)
            if group is not None:
                result.setdefault(group, []).append(key)
        return result

    def with_places(self, places: Mapping[str, Place]) -> LayoutBase:
        """같은 호기·묶음에 일곱 칸만 바꾼 것."""
        return LayoutBase(
            keys=self.keys,
            places={**self.places, **places},
            parents=self.parents,
            names=self.names,
            groups=self.groups,
        )


def layout_base(frame: pd.DataFrame, keys: Sequence[str]) -> LayoutBase:
    """설비 마스터(또는 공통 프레임) 행 차례와 같은 차례의 호기 키로 `LayoutBase` 를 만든다."""
    rows = frame.reset_index(drop=True)
    if len(rows) != len(keys):
        raise ValueError("배치 행 수와 호기 키 수가 다릅니다.")
    ordered = tuple(str(key) for key in keys)
    names = rows[EQUIPMENT_ID_COLUMN].astype("string").str.strip().tolist()
    parent_values = (
        rows[PARENT_EQUIPMENT_COLUMN].tolist()
        if PARENT_EQUIPMENT_COLUMN in rows.columns
        else [None] * len(rows)
    )
    groups = module_group_rows(rows).tolist()
    return LayoutBase(
        keys=ordered,
        places=dict(zip(ordered, _places(rows), strict=True)),
        parents={key: _parent_of(value) for key, value in zip(ordered, parent_values, strict=True)},
        names={key: str(name) for key, name in zip(ordered, names, strict=True)},
        groups={
            key: group for key, group in zip(ordered, groups, strict=True) if isinstance(group, str)
        },
    )


def _spot(place: Place) -> tuple[str | None, str | None]:
    return place[0], place[1]


def _majority_spot(
    members: Sequence[str], places: Mapping[str, Place], names: Mapping[str, str]
) -> tuple[str | None, str | None]:
    """구성원 (동, 층) 가운데 가장 많은 쪽 — 같으면 설비명 자연 정렬 첫 모듈의 것."""
    counts = Counter(_spot(places[key]) for key in members)
    best = max(counts.values())
    tied = {spot for spot, count in counts.items() if count == best}
    for key in sorted(members, key=lambda item: natural_name_key(names.get(item, item))):
        spot = _spot(places[key])
        if spot in tied:
            return spot
    return _spot(places[members[0]])


def _unplaced(place: Place, spot: tuple[str | None, str | None]) -> Place:
    """동·층을 `spot` 으로, X·Y 를 비운 일곱 칸(크기·레이아웃표시는 그대로)."""
    return (spot[0], spot[1], None, None, place[4], place[5], place[6])


@dataclass(frozen=True)
class _Effective:
    places: dict[str, Place]
    orphans: int
    regrouped: tuple[str, ...]


def _effective_places(base: LayoutBase, units: Sequence[UnitChange]) -> _Effective:
    """공식 위에 호기 차이를 얹은 일곱 칸 — 공식과 다른 값을 가질 수 있는 키만 든다(설계 5-1·5-2).

    - 공통에 없는 키의 차이는 버리고 센다(`orphans`).
    - 묶음 밖 호기는 차이 일곱 칸을 통째로 얹는다.
    - 모듈 묶음 G 는 **머문 구성원**(기록한 Main 설비가 G — 또는 기록한 이름이 지금 대장에 없고 그
      이름으로 기록한 차이가 모두 G 에 있음: 공식에서 묶음 이름만 바꿈)이 있으면 그들의 (동, 층)
      (갈리면 많은 쪽)이 G 의 가정 자리다 — 나머지 구성원은 동·층을 그 자리로, X·Y 를 비운다.
      머문 구성원이 없으면 G 는 공식 자리를 따르고 소속이 다른 차이 모듈만 G 의 공식 동·층으로
      맞추고 X·Y 를 비운다. 맞춘 묶음은 `regrouped` 에 적는다.
    """
    changes: dict[str, tuple[str | None, Place]] = {}
    orphans = 0
    for key, parent, place in units:
        if key not in base.places:
            orphans += 1
            continue
        changes[key] = (parent, place)
    result: dict[str, Place] = {}
    members = base.members()
    for key, (_, place) in changes.items():
        if key not in base.groups:
            result[key] = place
    if not any(key in base.groups for key in changes):
        return _Effective(result, orphans, ())
    known_parents = {parent for parent in base.parents.values() if parent is not None}
    recorded_groups: dict[str, set[str | None]] = {}
    for key, (parent, _) in changes.items():
        if parent is not None:
            recorded_groups.setdefault(parent, set()).add(base.groups.get(key))
    regrouped: list[str] = []
    for group, keys in members.items():
        changed = [key for key in keys if key in changes]
        if not changed:
            continue

        def stayed(key: str, group: str = group) -> bool:
            recorded = changes[key][0]
            if recorded == group:
                return True
            if recorded is None or recorded in known_parents:
                return False
            return recorded_groups.get(recorded, set()) == {group}

        stay = [key for key in changed if stayed(key)]
        adjusted = False
        if stay:
            spot = _majority_spot(stay, {key: changes[key][1] for key in stay}, base.names)
            for key in keys:
                own = changes[key][1] if key in changes else base.places[key]
                if key in stay and _spot(own) == spot:
                    result[key] = own
                    continue
                result[key] = _unplaced(own, spot)
                adjusted = adjusted or result[key] != own
        else:
            spot = _majority_spot(keys, base.places, base.names)
            for key in changed:
                own = changes[key][1]
                result[key] = _unplaced(own, spot)
                adjusted = adjusted or result[key] != own
        if adjusted:
            regrouped.append(group)
    return _Effective(result, orphans, tuple(sorted(regrouped, key=natural_name_key)))


def _unit_changes(
    effective: Mapping[str, Place], base: LayoutBase, *, candidates: Collection[str]
) -> tuple[UnitChange, ...]:
    """`effective`(키 → 얹은 일곱 칸 — 없으면 공식) 가운데 공식과 다른 것만 차이로(설계 5-6 의 2·3).

    모듈 묶음은 통째다 — 한 모듈이라도 다르면 모든 모듈을 그 값으로 적고, 모두 같으면 통째로 뺀다.
    `candidates` 는 다를 수 있는 키다(그 밖은 공식 그대로라 보지 않는다). 기록하는 Main 설비는
    지금 공통(`base.parents`)의 값이다.
    """
    members = base.members()
    wanted: set[str] = set()
    seen_groups: set[str] = set()
    for key in candidates:
        if key not in base.places:
            continue
        group = base.groups.get(key)
        if group is None:
            if effective.get(key, base.places[key]) != base.places[key]:
                wanted.add(key)
            continue
        if group in seen_groups:
            continue
        seen_groups.add(group)
        keys = members[group]
        if any(effective.get(item, base.places[item]) != base.places[item] for item in keys):
            wanted.update(keys)
    return tuple(
        (key, base.parents.get(key), effective.get(key, base.places[key])) for key in sorted(wanted)
    )


def _layout_column_positions(frame: pd.DataFrame) -> list[int]:
    positions = frame.columns.get_indexer(pd.Index(list(SCENARIO_LAYOUT_COLUMNS)))
    if (positions < 0).any():
        raise ValueError("배치 일곱 칸이 없는 표에는 배치 차이를 얹지 않습니다.")
    return [int(position) for position in positions]


def _set_place(
    frame: pd.DataFrame, row: int, columns: Sequence[int], place: Sequence[object]
) -> None:
    for column, value in zip(columns, place, strict=True):
        frame.iat[row, column] = cast(Any, value)


def layout_cells(frame: pd.DataFrame, keys: Sequence[str]) -> dict[str, LayoutCells]:
    """행 차례 = `keys` 인 표의 호기 키 → 배치 일곱 칸 원래 값(반올림 없음)."""
    rows = frame.reset_index(drop=True)
    if len(rows) != len(keys):
        raise ValueError("배치 행 수와 호기 키 수가 다릅니다.")
    columns = [rows[column].tolist() for column in SCENARIO_LAYOUT_COLUMNS]
    return {
        str(key): tuple(values)
        for key, values in zip(keys, zip(*columns, strict=True), strict=True)
    }


def _cells_place(cells: LayoutCells) -> Place:
    return place_of(dict(zip(SCENARIO_LAYOUT_COLUMNS, cells, strict=True)))


@dataclass(frozen=True)
class AppliedLayout:
    """`apply_unit_overlay` 의 결과.

    - `equipment` — 39칸, 차이를 얹은 것(행 차례 그대로).
    - `official_places` — 얹은 값이 공식과 실제로 다른 호기의 얹기 전(공식) 일곱 칸, 키 차례.
    - `orphans` — 공통에 없는 키라 버린 차이 행 수.
    - `regrouped` — 공식에서 모듈 구성이 바뀌어 가정 자리를 다시 맞춘 묶음의 Main 설비.
    """

    equipment: pd.DataFrame
    official_places: tuple[tuple[str, Place], ...] = ()
    orphans: int = 0
    regrouped: tuple[str, ...] = ()


def apply_unit_overlay(
    master: pd.DataFrame,
    unit_key_pairs: Sequence[tuple[str, str]],
    units: Sequence[UnitChange],
) -> AppliedLayout:
    """합친 마스터(행 차례 = `unit_key_pairs` 차례)에 호기 차이를 얹는다. **예외를 내지 않는다**
    (불변식 I4) — 묶음 소속이 바뀐 모듈은 자리 없음으로 둬 늘 「모듈 행 동·층 같음」 을 지킨다."""
    if not units:
        return AppliedLayout(master.copy())
    keys = [key for _, key in unit_key_pairs]
    base = layout_base(master, keys)
    effective = _effective_places(base, units)
    result = master.reset_index(drop=True).copy()
    columns = _layout_column_positions(result)
    position = {key: index for index, key in enumerate(keys)}
    official: list[tuple[str, Place]] = []
    for key, place in effective.places.items():
        if place == base.places[key]:
            continue
        _set_place(result, position[key], columns, place)
        official.append((key, base.places[key]))
    return AppliedLayout(
        equipment=result,
        official_places=tuple(sorted(official)),
        orphans=effective.orphans,
        regrouped=effective.regrouped,
    )


@dataclass(frozen=True)
class LayoutSplit:
    """편집본 배치를 공통 쪽과 배치 차이로 나눈 것(`split_layout`).

    - `common_places` — 공통 대장에 쓸 일곱 칸(편집본의 모든 키).
    - `units` — 이 시나리오의 호기 차이(정규화한 것 — 공식 역할이면 늘 빈 튜플).
    - `refusal` — 저장하지 않을 까닭(없으면 None).
    """

    common_places: Mapping[str, Place]
    units: tuple[UnitChange, ...] = ()
    refusal: str | None = None


def split_layout(
    edited_base: LayoutBase,
    *,
    official: LayoutBase,
    started: Mapping[str, Place],
    role: LayoutRole,
    overlay_present: bool,
) -> LayoutSplit:
    """검증을 마친 편집본(`edited_base` — `layout_base(편집본, 키)`)의 배치를 공통 쪽과 배치 차이로
    나눈다(설계 6-1).

    `official` 은 공통 최신(공식 배치), `started` 는 편집을 시작한 합친 배치(키 → 일곱 칸 —
    공통 ⊕ 출발 리비전의 차이), `overlay_present` 는 출발 리비전에 호기 차이가 있었는가다.

    - **공식 역할**: 편집에서 바뀐 호기(편집본 ≠ 시작)만 공통에 편집본 값을, 나머지는 공식 값을
      쓴다 — 새 호기는 편집본 값. 차이는 비운다. 출발 리비전에 차이가 있으면(그 시나리오가 가정이던
      때의 리비전) 배치를 바꾼 저장은 거부한다 — 묶음 일부만 공통으로 가 공식 묶음이 갈리지 않게.
    - **가정 역할**: 공통 쪽은 `hypothetical_common_places` — 있던 호기는 공식 값 그대로, 새 호기는
      동·층·X·Y 를 비우고 크기·레이아웃표시만 편집본 값(Q1 — 있는 묶음에 드는 새 모듈과 공식 자리가
      미정인 호기는 그 묶음의 공식 동·층). 공식 동·층이 다른 호기를 한 묶음으로 묶는 고침은 거부한다
      (묶음 구성은 공통이다). 차이 = 편집본 ≠ 공통 쪽(묶음 통째).
    """
    keys = edited_base.keys
    if role == "official":
        changed = [
            key for key in keys if key in started and edited_base.places[key] != started[key]
        ]
        if overlay_present and changed:
            return LayoutSplit(
                common_places={},
                refusal=(
                    "이 리비전에는 이 설비 시나리오가 가정이던 때의 배치 차이가 있어 공식 배치를 "
                    f"고치지 않았습니다(바뀐 호기 {len(changed)}대) — 최신 리비전을 불러와 배치를 "
                    "고치세요. 날짜만 고친 저장은 됩니다."
                ),
            )
        moved = set(changed)
        common = {
            key: edited_base.places[key]
            if key not in official.places or key in moved
            else official.places[key]
            for key in keys
        }
        return LayoutSplit(common_places=common)
    common = hypothetical_common_places(edited_base, official)
    groups = edited_base.members()
    refusal = _mixed_group_refusal(groups, common, edited_base, official)
    if refusal is not None:
        return LayoutSplit(common_places=common, refusal=refusal)
    split_base = edited_base.with_places(common)
    units = _unit_changes(edited_base.places, split_base, candidates=keys)
    return LayoutSplit(common_places=common, units=units)


def _undecided(place: Place) -> bool:
    """공식 동·층이 둘 다 비었다(「동·층 미정」 — 가정 시나리오에서 자리 없이 넣은 호기 등)."""
    return _spot(place) == (None, None)


def hypothetical_common_places(edited_base: LayoutBase, official: LayoutBase) -> dict[str, Place]:
    """가정 역할 저장이 공통 대장에 쓸 일곱 칸(편집본의 모든 키 — `split_layout` 의 공통 쪽).

    - 있던 호기는 공식 값 그대로(I7 — 가정 편집이 공식 배치를 옮기지 않는다).
    - 새 호기(공식에 없는 키)는 동·층·X·Y 를 비우고 크기·레이아웃표시만 편집본 값(Q1).
    - 모듈 묶음에 드는 새 호기와 **공식 동·층이 미정인** 있던 호기는 그 묶음의 공식 동·층(자리가
      정해진 구성원의 많은 쪽)에 X·Y 를 비운다 — 공통의 묶음이 동·층으로 갈리지 않게(검토 F2a).
      미정 호기도 새 모듈처럼 맞춰야 가정에서 자리 없이 넣은 호기를 나중에 그 시나리오의 묶음에
      넣을 수 있다(공식 배치를 가르지 않는다).

    S2 화면 잠금(설비 마스터 탭 제출·붙여넣기)도 이 값으로 편집본을 맞춘다 — 그러면 저장이 배치
    차이를 만들지 않는다(화면이 차이를 보이기 전에는 만들지 않게)."""
    common: dict[str, Place] = {}
    for key in edited_base.keys:
        place = edited_base.places[key]
        if key in official.places:
            common[key] = official.places[key]
        else:
            common[key] = (None, None, None, None, place[4], place[5], place[6])
    for members in edited_base.members().values():
        known = [
            key
            for key in members
            if key in official.places and not _undecided(official.places[key])
        ]
        if not known:
            continue
        spot = _majority_spot(known, official.places, edited_base.names)
        for key in members:
            if key not in official.places or _undecided(official.places[key]):
                common[key] = _unplaced(common[key], spot)
    return common


def _named_rows(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """설비명이 있는 행만(같은 이름은 첫 행) — 검증 전 편집본에도 `layout_base` 를 세울 수 있게."""
    names = frame[EQUIPMENT_ID_COLUMN].map(_text)
    keep = names.notna() & ~names.duplicated()
    return frame.loc[keep.to_numpy(dtype=bool)].reset_index(drop=True), [
        str(name) for name in names.loc[keep]
    ]


def assumption_common_places(
    buffer: pd.DataFrame, saved: pd.DataFrame, origins: Mapping[str, str]
) -> dict[str, Place]:
    """가정 설비 시나리오 편집본에서 저장본 값이 아니라 **공통 쪽 규칙**으로 자리가 정해지는 행 —
    지금 설비명 → 가정 역할 저장이 공통 대장에 쓸 일곱 칸(`hypothetical_common_places`).

    새 호기(자리 없음 — 있는 묶음에 드는 모듈은 그 묶음의 공식 동·층)와, 공식 동·층이 미정인데
    묶음에 든 있던 호기(그 묶음의 공식 동·층)다. 그 밖의 있던 호기는 들지 않는다 — 공식(저장본)
    값 그대로라 저장본 값으로 되돌린다(`space_layout_edit.saved_layout_drift`).

    `origins` 는 지금 설비명 → 저장하면 이어받을 저장본 설비명(`inherited_unit_names`)이다. 설비
    시나리오 2단계 S2 화면 잠금(설비 마스터 탭 제출·붙여넣기 미리보기)이 편집본을 이 자리로
    맞춰, 가정 세션의 저장이 화면이 아직 보이지 않는 배치 차이를 만들지 않게 한다(S3 가 가정 배치
    편집을 연다).
    """
    rows, names = _named_rows(buffer)
    saved_rows, saved_names = _named_rows(saved)
    keys = [f"저장본:{origins[name]}" if name in origins else f"새:{name}" for name in names]
    edited_base = layout_base(rows, keys)
    official = layout_base(saved_rows, [f"저장본:{name}" for name in saved_names])
    allowed = hypothetical_common_places(edited_base, official)
    return {
        name: allowed[key]
        for name, key in zip(names, keys, strict=True)
        if key not in official.places or allowed[key] != official.places[key]
    }


def misplaced_rows(buffer: pd.DataFrame, places: Mapping[str, Place]) -> dict[str, Place]:
    """`places`(설비명 → 일곱 칸) 가운데 편집본 그 행의 자리가 다른 것만."""
    rows, names = _named_rows(buffer)
    current = dict(zip(names, _places(rows), strict=True))
    return {name: place for name, place in places.items() if current.get(name, place) != place}


def place_rows(buffer: pd.DataFrame, targets: Mapping[str, Place]) -> pd.DataFrame:
    """`targets`(설비명 → 일곱 칸) 행의 배치 칸을 그 자리로 맞춘 `buffer` 사본 — 견줄 값이 다른 칸만
    바꾼다(크기·레이아웃표시처럼 같은 칸은 편집본 값 그대로). 나머지 칸·행은 그대로다."""
    if not targets:
        return buffer
    result = buffer.copy()
    names = result[EQUIPMENT_ID_COLUMN].map(_text)
    for name, target in targets.items():
        mask = names.eq(name).fillna(False).to_numpy(dtype=bool)
        for row in mask.nonzero()[0]:
            here = place_of(result.iloc[int(row)])
            for column, now, value in zip(SCENARIO_LAYOUT_COLUMNS, here, target, strict=True):
                if now != value:
                    result.loc[result.index[int(row)], column] = value
    return result


def _spot_words(spot: tuple[str | None, str | None]) -> str:
    building, floor = spot
    if building is None and floor is None:
        return _UNKNOWN_FLOOR
    return f"{building or _UNKNOWN_FLOOR} {floor or _UNKNOWN_FLOOR}"


def _mixed_group_refusal(
    groups: Mapping[str, Sequence[str]],
    common: Mapping[str, Place],
    edited: LayoutBase,
    official: LayoutBase,
) -> str | None:
    """가정 역할의 공통 쪽에서 공식 동·층이 다른 호기가 한 묶음에 드는가 — 첫 경우의 거부 글."""
    found = _mixed_group(groups, common, edited, official)
    return found[0] if found is not None else None


def _mixed_group(
    groups: Mapping[str, Sequence[str]],
    common: Mapping[str, Place],
    edited: LayoutBase,
    official: LayoutBase,
) -> tuple[str, str] | None:
    """`_mixed_group_refusal` 의 첫 경우 — (거부 글, 묶음 자리와 공식 동·층이 다른 호기의 키)."""
    for group in sorted(groups, key=natural_name_key):
        members = list(groups[group])
        spots = {_spot(common[key]) for key in members}
        if len(spots) <= 1:
            continue
        # 묶음 자리는 그 묶음에 원래 있던(공식 Main 설비가 같은) 모듈의 많은 쪽, 없으면 많은 쪽이다.
        native = [key for key in members if official.parents.get(key) == group] or members
        spot = _majority_spot(native, common, edited.names)
        outsider = next(
            key
            for key in sorted(members, key=lambda item: natural_name_key(edited.names[item]))
            if _spot(common[key]) != spot
        )
        return (
            (
                "가정 설비 시나리오에서는 공식 층이 다른 호기를 한 묶음으로 묶지 않습니다"
                f"({edited.names[outsider]} 은 공식 {_spot_words(_spot(common[outsider]))}, "
                f"묶음 {group} 은 {_spot_words(spot)}) — 묶음 구성은 공통이라 공식 설비 "
                "시나리오에서 바꾸세요."
            ),
            outsider,
        )
    return None


def assumption_group_refusal(
    buffer: pd.DataFrame,
    saved: pd.DataFrame,
    origins: Mapping[str, str],
    official_places: Mapping[str, Place],
) -> tuple[str, str] | None:
    """가정 설비 시나리오 편집본이 공식 동·층이 다른 호기를 한 묶음으로 묶는가 — 저장소
    (`split_layout`)가 같은 글로 거부할 경우 (거부 글, 그 호기의 지금 설비명), 아니면 None.

    설비 마스터 탭 제출·붙여넣기 미리보기가 저장 전에 같은 판정을 쓴다(설계 10장·6-1·Q1(c)).
    `saved` 는 세션 저장본(가정 배치를 얹은 것), `origins` 는 지금 설비명 → 이어받을 저장본
    설비명(`inherited_unit_names`), `official_places` 는 저장본 설비명 → 공식과 다른 호기의 공식
    일곱 칸(`EquipmentSnapshot.layout_official_places`)이다 — 공식 배치는 저장본에서 그것을 되돌린
    것이다(Main 설비는 공통 칸이라 저장본 그대로가 공식이다)."""
    rows, names = _named_rows(buffer)
    saved_rows, saved_names = _named_rows(saved)
    keys = [f"저장본:{origins[name]}" if name in origins else f"새:{name}" for name in names]
    edited_base = layout_base(rows, keys)
    official = layout_base(saved_rows, [f"저장본:{name}" for name in saved_names])
    official = official.with_places(
        {
            f"저장본:{name}": place
            for name, place in official_places.items()
            if f"저장본:{name}" in official.places
        }
    )
    common = hypothetical_common_places(edited_base, official)
    found = _mixed_group(edited_base.members(), common, edited_base, official)
    if found is None:
        return None
    message, outsider = found
    return message, edited_base.names[outsider]


def common_with_places(
    common: pd.DataFrame,
    keys: Sequence[str],
    places: Mapping[str, Place],
    *,
    current: Mapping[str, Place] | None = None,
    official: Mapping[str, LayoutCells] | None = None,
) -> pd.DataFrame:
    """공통 프레임(행 차례 = `keys`)의 배치 일곱 칸을 `places` 자리로 바꾼 사본(자리가 같은 행은
    그대로). `current` 는 그 프레임의 지금 일곱 칸(이미 잰 것이 있으면 다시 재지 않는다).

    `places` 는 견줄 꼴(반올림)이라 그대로 적지 않는다 — 바꿀 자리가 `official`(키 → 공통 대장 그
    호기의 원래 일곱 칸)과 같으면 그 **원래 값**을 옮기고(가정 역할 저장이 공식 좌표 10.25 를
    10.2 로 적어 공통 리비전을 만들지 않게), 그 밖은 지금 값과 다른 칸만 바꾼다(새 호기의 자리를
    비울 때 크기·레이아웃표시는 편집본 값 그대로)."""
    result = common.reset_index(drop=True).copy()
    now = dict(current) if current is not None else dict(zip(keys, _places(result), strict=True))
    columns = _layout_column_positions(result)
    for row, key in enumerate(keys):
        place = places.get(key)
        here = now.get(key)
        if place is None or place == here:
            continue
        cells = official.get(key) if official is not None else None
        if cells is not None and _cells_place(cells) == place:
            _set_place(result, row, columns, cells)
            continue
        for index, (column, value) in enumerate(zip(columns, place, strict=True)):
            if here is None or here[index] != value:
                result.iat[row, column] = value
    return result


# ------------------------------------------------------------------ 층 도면 요소·이름표


def effective_floor_marks(
    official: Sequence[FloorLayoutMark], changes: Sequence[MarkChange]
) -> tuple[FloorLayoutMark, ...]:
    """공식 요소를 그 차례로 훑어 `drop` 이면 빼고 `set` 이면 차이 내용으로 바꾼 뒤, 공식에 없는
    id 의 `set` 을 차이 차례로 붙인다(설계 5-3). 공식이 그 사이 지운 요소를 가정이 고쳤으면 새
    요소로 남는다."""
    if not changes:
        return tuple(official)
    by_id = {change.mark_id: change for change in changes}
    result: list[FloorLayoutMark] = []
    present: set[str] = set()
    for mark in official:
        present.add(mark.mark_id)
        change = by_id.get(mark.mark_id)
        if change is None:
            result.append(mark)
        elif change.kind == "set" and change.mark is not None:
            result.append(change.mark)
    for change in changes:
        if change.mark_id not in present and change.kind == "set" and change.mark is not None:
            result.append(change.mark)
    return tuple(result)


def mark_changes(
    effective: Sequence[FloorLayoutMark], official: Sequence[FloorLayoutMark]
) -> tuple[MarkChange, ...]:
    """한 층의 합친 요소 목록에서 공식과 다른 것만 — 공식에만 있는 id 는 `drop`, 공식과 내용이
    다른 요소는 `set`, 공식에 없는 요소는 `set`. 차례만 바꾼 요소는 차이로 적지 않는다.

    차례는 **정해져 있다**: 공식에 있는 id 는 공식 차례로, 그 뒤 공식에 없는 id 를 합친 차례로.
    편집기가 낸 목록(새 요소를 더한 뒤 공식 요소를 지웠다 되살리면 그 요소가 끝으로 감)과 차이를
    다시 합친 목록(`effective_floor_marks` — 공식 차례 → 새 요소)이 같은 차이·같은 지문을 내야 남의
    일정 저장 뒤 배치 빨리 감기가 서기 때문이다(설계 6-1·15장 「결과 지문 결정적」)."""
    by_id: dict[str, FloorLayoutMark] = {}
    for mark in effective:
        by_id.setdefault(mark.mark_id, mark)
    official_ids = {mark.mark_id for mark in official}
    changes: list[MarkChange] = []
    for mark in official:
        now = by_id.get(mark.mark_id)
        if now is None:
            changes.append(MarkChange(mark.mark_id, "drop"))
        elif now != mark:
            changes.append(MarkChange(mark.mark_id, "set", now))
    added: set[str] = set()
    for mark in effective:
        if mark.mark_id not in official_ids and mark.mark_id not in added:
            added.add(mark.mark_id)
            changes.append(MarkChange(mark.mark_id, "set", mark))
    return tuple(changes)


def effective_group_labels(
    official: Mapping[str, str], changes: Sequence[LabelChange]
) -> dict[str, str]:
    """공식 Main 설비명 위치에 차이를 덮는다(None 은 그 행을 지운다 — 처음 위치)."""
    result = dict(official)
    for parent, spot in changes:
        if spot is None:
            result.pop(parent, None)
        else:
            result[parent] = spot
    return dict(sorted(result.items()))


def label_changes(
    effective: Mapping[str, str], official: Mapping[str, str]
) -> tuple[LabelChange, ...]:
    """합친 위치에서 공식과 다른 것만(공식에 있는데 합친 쪽에 없으면 None)."""
    return tuple(
        (parent, effective.get(parent))
        for parent in sorted(set(effective) | set(official))
        if effective.get(parent) != official.get(parent)
    )


# 층 하나의 공식 값 — (도면 요소, Main 설비명 위치).
OfficialFloor = tuple[Sequence[FloorLayoutMark], Mapping[str, str]]


def normalize_layout_overlay(
    overlay: LayoutOverlay,
    base: LayoutBase,
    official_floors: Mapping[FloorKey, OfficialFloor],
) -> LayoutOverlay:
    """그 쓰기의 공식(공통 `base`·층 현행값 `official_floors`) 기준으로 같아진 차이를 지운다
    (설계 5-6).

    1. 공통에 없는 호기 키 차이 → 뺌. 2. 묶음 통째 맞추기(얹은 값 기준). 3. 공식과 같은 호기 → 뺌.
    4. 공식과 같은 요소 `set`·공식에 없는 id 의 `drop` → 뺌. 5. 공식과 같은 이름표·공식에 행이
    없는 None → 뺌. `official_floors` 에 없는 층은 공식 요소·이름표가 없는 층으로 본다.
    """
    if not overlay:
        return overlay
    effective = _effective_places(base, overlay.units)
    units = _unit_changes(effective.places, base, candidates=effective.places.keys())
    marks: dict[FloorKey, tuple[MarkChange, ...]] = {}
    labels: dict[FloorKey, tuple[LabelChange, ...]] = {}
    for floor in overlay.floors:
        official_marks, official_labels = official_floors.get(floor, ((), {}))
        if overlay.marks_for(floor):
            marks[floor] = mark_changes(
                effective_floor_marks(official_marks, overlay.marks_for(floor)), official_marks
            )
        if overlay.labels_for(floor):
            labels[floor] = label_changes(
                effective_group_labels(official_labels, overlay.labels_for(floor)), official_labels
            )
    return make_layout_overlay(units, marks, labels)


def overlay_unit_count(overlay: LayoutOverlay, base: LayoutBase) -> int:
    """호기 차이를 **설비 단위**로 센다(모듈 묶음은 1대 — 지금 공통의 묶음 기준)."""
    seen: set[str] = set()
    count = 0
    for key in overlay.unit_keys:
        group = base.groups.get(key)
        if group is None:
            count += 1
        elif group not in seen:
            seen.add(group)
            count += 1
    return count


@dataclass(frozen=True)
class LayoutDifference:
    """그리는 한 벌의 가정 배치가 공식과 얼마나 다른가(머리 알림·견주기 재료 — 설계 8-2).

    - `units` — 일곱 칸이 공식과 실제로 다른 **설비 단위** 수(Main 설비 묶음은 1대). 그 시나리오에
      일정이 없는 호기(G2 — 계산·도면에서 빠짐)는 세지 않고 `unscheduled` 에 센다.
    - `display_only` — `units` 가운데 레이아웃표시만 다른 설비 수(자리·크기는 공식 그대로).
    - `stored_units`·`marks`·`labels` — 그 리비전에 **저장된** 차이 행 수(원시 — 공식과 같아진 행은
      다음 쓰기 때 지워진다). 요소·이름표의 실효 수는 층 현행값으로 정규화한 차이를 넘겨 센다.
    """

    units: int = 0
    display_only: int = 0
    unscheduled: int = 0
    stored_units: int = 0
    marks: int = 0
    labels: int = 0

    def __bool__(self) -> bool:
        return bool(self.units or self.marks or self.labels)


def layout_difference(
    effective: pd.DataFrame,
    unit_key_pairs: Sequence[tuple[str, str]],
    official_places: Iterable[tuple[str, Place]],
    unscheduled: Collection[str],
    overlay: LayoutOverlay,
) -> LayoutDifference:
    """차이를 얹은 마스터(`effective` — 행 차례 = `unit_key_pairs`)와 그 얹기 전 공식 일곱 칸
    (`official_places` — 실제로 다른 호기만, `EquipmentSnapshot.layout_official_places`)으로 실효
    셈을, `overlay`(그 리비전의 차이)로 저장된 행 수를 낸다. `unscheduled` 는 일정 없는 설비명이다.
    """
    official = dict(official_places)
    if not official:
        return LayoutDifference(
            stored_units=len(overlay.units),
            marks=overlay.mark_count,
            labels=overlay.label_count,
        )
    keys = [key for _, key in unit_key_pairs]
    base = layout_base(effective, keys)
    names = {key: name for name, key in unit_key_pairs}
    # 설비 단위 — 묶음은 ("묶음", Main 설비), 단독 호기는 ("호기", 키).
    counted: dict[tuple[str, str], bool] = {}
    skipped: set[tuple[str, str]] = set()
    for key, before in official.items():
        if key not in base.places:
            continue
        group = base.groups.get(key)
        unit = ("묶음", group) if group is not None else ("호기", key)
        if names.get(key) in unscheduled:
            skipped.add(unit)
            continue
        after = base.places[key]
        only_display = after[:6] == before[:6] and after[6] != before[6]
        counted[unit] = counted.get(unit, True) and only_display
    return LayoutDifference(
        units=len(counted),
        display_only=sum(1 for only in counted.values() if only),
        unscheduled=len(skipped - set(counted)),
        stored_units=len(overlay.units),
        marks=overlay.mark_count,
        labels=overlay.label_count,
    )


def layout_counts_words(units: int, marks: int, labels: int) -> str:
    """「호기 3대·요소 1개·이름표 2개」 — 0 인 것은 뺀다. 모두 0 이면 빈 글."""
    parts = []
    if units:
        parts.append(f"호기 {units}대")
    if marks:
        parts.append(f"요소 {marks}개")
    if labels:
        parts.append(f"이름표 {labels}개")
    return "·".join(parts)
