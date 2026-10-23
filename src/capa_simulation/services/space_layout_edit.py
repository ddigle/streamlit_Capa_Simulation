# Purpose: Space 배치 편집기·뷰어 입력을 만들고 적용값을 검증해 편집본에 얹는 순수 계산을 모은다.

"""Space 배치 편집기(드래그앤드롭)의 파이썬 쪽 계산.

편집 상태는 브라우저가 쥐고 `적용` 때 한 번에 보낸다. 여기서 하는 일은 셋이다.

1. **입력** — 설비 편집본(호기 상태 포함)에서 이 층 편집기에 보낼 호기를 고른다. 대상은
   Space 현황이 그리는 호기와 같다(레이아웃표시 Y 이고 도면 이탈일 — 반출/이설일정, 없으면
   정지일정 — 전). 좌표가 있으면 도면에, 없으면 미배치 트레이에 놓는다. 동·층이 빈 호기는 모든
   층 트레이에 뜬다.
2. **검증** — 브라우저가 보낸 적용값을 다시 검사한다. 하나라도 어긋나면 `ValueError` 로 적용
   전체를 거부한다. 조용히 버리면 그 편집이 사라진 채 화면은 적용된 것처럼 보인다.
3. **반영** — 검증한 변경을 편집본 설비 마스터에 얹는다. 트레이로 빼도 크기는 남기고, 다른
   층으로 보낸 호기는 그 층 캔버스 안으로 민다. Main 설비 묶음은 동·층을 함께 맞춘다(모듈 행은
   동·층이 같아야 저장된다).

**이름 바꾸기**(2026-10-08 사용자 결정 「설비명 자체를 바꾸기」)는 표시 별칭이 아니라 설비 마스터의
설비명(묶음이면 그 Main 설비)을 바꾼다. 비가동 일정의 설비명이 따라가고, 같은 세션의 저장 안 한 이름
바꿈은 `PendingRenames`(지금 이름 → 저장본 이름)로 기억해 변경 목록이 「지우고 새로 넣음」이 아니라
「이름 바꿈」으로 읽히게 한다.

좌표 계약은 Space 배치도와 같다: 원점은 왼쪽 아래, 상자는 (X, Y) → (X+Xsize, Y+Ysize).
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Final, Literal, cast

import pandas as pd

from capa_simulation.services.equipment_contract import (
    ARRIVAL_DATE_COLUMN,
    EQUIPMENT_ID_COLUMN,
    LAYOUT_REFLECTED_COLUMN,
    PARENT_EQUIPMENT_COLUMN,
    QUAL_CONFIRMATION_STATUSES,
    QUAL_DATE_COLUMN,
    QUAL_STATUS_COLUMN,
    STORAGE_FLAG_COLUMN,
)
from capa_simulation.services.equipment_units import unit_keys
from capa_simulation.services.fab_layout import floor_label
from capa_simulation.services.floor_layout_mark import FloorLayoutMark, prepare_floor_layout_marks
from capa_simulation.services.floor_layout_profile import (
    CANVAS_DECIMALS,
    MAX_CANVAS_EXTENT,
    CanvasSize,
    FloorKey,
    normalize_canvas_size,
    rounded_to_canvas,
)
from capa_simulation.services.frame_contracts import scalar_match_key
from capa_simulation.services.korean_particle import (
    with_direction_particle,
    with_object_particle,
    with_topic_particle,
)

POSITION_COLUMNS: Final = ("X좌표", "Y좌표")
SIZE_COLUMNS: Final = ("Xsize", "Ysize")
# 편집기가 바꾸는 칸. 나머지 칸이 다르면 RawData 의 다른 편집이다. 이름 바꿈(설비명·Main 설비)은
# 이 칸이 아니라 `PendingRenames` 가 가른다.
PLACE_COLUMNS: Final = ("동", "층", "X좌표", "Y좌표", "Xsize", "Ysize", "레이아웃표시")
UNIT_ID_MAX: Final = 40
NEW_UNIT_HISTORY: Final = "Space 편집기에서 추가"
_DEFAULT_SIZE: Final = (12.0, 7.0)
# 이름이 겹치는지 볼 때의 규칙 — 대소문자·앞뒤 공백만 다른 두 이름은 같은 이름이다(`match_key`).
_SAME_NAME_NOTE: Final = "대소문자·앞뒤 공백만 다른 이름도 같은 이름으로 봅니다"
RenameKind = Literal["unit", "group"]


@dataclass(frozen=True)
class UnitChange:
    """호기 하나의 적용값. `placed` 가 거짓이면 X·Y 는 비운다(크기 `w`·`h` 는 있으면 남긴다)."""

    unit_id: str
    placed: bool
    x: float | None
    y: float | None
    w: float | None
    h: float | None
    move_to: FloorKey | None


@dataclass(frozen=True)
class CreatedUnit:
    """편집기에서 새로 넣은 호기. 설비 마스터가 꼭 요구하는 값만 받는다."""

    unit_id: str
    process: str
    line: str
    use: str
    existing: bool
    arrival: date | None
    qual: date | None
    confirm: str


@dataclass(frozen=True)
class NameChange:
    """이름 바꿈 하나. `kind="unit"` 은 그 행의 설비명을, `"group"` 은 그 Main 설비를 쓰는 **모든
    행**(편집기에 없는 형제 포함)의 Main 설비를 바꾼다. 자기 설비명을 Main 설비로 적은 한 행짜리
    묶음은 설비명을 바꾸면 Main 설비도 따라간다."""

    kind: RenameKind
    old: str
    new: str


@dataclass(frozen=True)
class EditorApply:
    """검증을 마친 적용값 한 번. `canvas`·`marks` 는 바꾼 경우에만 값이 있다."""

    changes: tuple[UnitChange, ...]
    created: tuple[CreatedUnit, ...]
    canvas: CanvasSize | None
    marks: tuple[FloorLayoutMark, ...] | None
    renames: tuple[NameChange, ...] = ()

    @property
    def unit_renames(self) -> dict[str, str]:
        """설비명 이름 바꿈(옛 이름 → 새 이름)."""
        return {change.old: change.new for change in self.renames if change.kind == "unit"}

    @property
    def group_renames(self) -> dict[str, str]:
        """Main 설비 이름 바꿈(옛 이름 → 새 이름)."""
        return {change.old: change.new for change in self.renames if change.kind == "group"}


@dataclass(frozen=True)
class PendingRenames:
    """저장 안 한 이름 바꿈 — **지금 이름 → 저장본 이름**. 설비명(`units`)과 Main 설비(`groups`).

    호기는 설비명으로만 짝지어지므로, 이것 없이는 이름을 바꾼 호기가 저장본과 견줄 때 「지운 호기 +
    새 호기」로 읽힌다(변경 목록에서 빠지고 RawData 의 다른 편집 2건으로 세어진다)."""

    units: Mapping[str, str] = field(default_factory=dict)
    groups: Mapping[str, str] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.units or self.groups)


@dataclass(frozen=True)
class ReservedNames:
    """편집본 설비 마스터에 없지만 새 설비명(새 호기·이름 바꿈)으로 쓸 수 없는 이름
    (`reserved_names`).

    - `deleted`: 저장본에 있는데 RawData 에서 지우고 아직 저장하지 않은 설비명. 다른 호기가 그
      이름을 이으면 저장 뒤 같은 이름의 다른 설비가 되어 옛 이력(진척 비교 기준선 등)과 섞인다.
      Space 에서 이름을 바꿔 비운 이름은 아니다 — 그것은 다시 써도 된다.
    - `orphan_downtime`: 설비 마스터에 없는 설비명을 가리키는 비가동 일정(보통 저장이 막는다). 그
      이름을 쓰면 그 일정이 말없이 새 이름의 호기에 붙는다.
    """

    deleted: frozenset[str] = frozenset()
    orphan_downtime: frozenset[str] = frozenset()


@dataclass(frozen=True)
class EditorInputs:
    """한 층 편집기에 보낼 호기와 영역 정보."""

    items: tuple[dict[str, Any], ...]
    reserved_extent: CanvasSize
    default_size: CanvasSize
    unplaced_floorless: int


def finite_or_none(value: object) -> float | None:
    """숫자로 읽히는 유한한 값만 float 로, 그 밖(None·bool·NA·NaN·무한대·글자)은 None 으로 돌려준다.
    편집기로 보내는 값에도 쓴다 — Components v2 가 NaN 을 JSON 에 실으면 브라우저가 거부한다."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _present(value: object) -> bool:
    """값이 있는가. None·NA·NaN·NaT 를 모두 빈 칸으로 본다 — 날짜 칸의 NaT 를 값으로 보면 새 호기를
    붙인 편집본의 모든 행이 「바뀌었다」가 된다."""
    if value is None:
        return False
    if pd.api.types.is_scalar(value):
        return not bool(pd.isna(cast(Any, value)))
    return True


def _text(value: object) -> str:
    return str(value) if _present(value) else ""


def _iso_date(value: object, field: str, unit_id: str) -> date | None:
    text = _text(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"새 호기 {unit_id} 의 {field} 날짜를 읽지 못했습니다: {text}") from exc


# ------------------------------------------------------------------ 입력


def _parents(frame: pd.DataFrame) -> pd.Series:
    """행마다 Main 설비(앞뒤 공백 제거, 비면 NA). 선택 컬럼이라 없는 표도 받는다."""
    if PARENT_EQUIPMENT_COLUMN not in frame.columns:
        return pd.Series(pd.NA, index=frame.index, dtype="string")
    parents = frame[PARENT_EQUIPMENT_COLUMN].astype("string").str.strip()
    return parents.where(parents.ne(""))


def _floor_mask(frame: pd.DataFrame, key: FloorKey) -> pd.Series:
    return frame["동"].eq(key[0]).fillna(False).astype(bool) & frame["층"].eq(key[1]).fillna(
        False
    ).astype(bool)


# 편집기에 보내는 행에서 호기(설비명)마다 브라우저로 보낼 색·경계 날짜를 만드는
# 함수(`components/space_layout.unit_appearance` 를 묶어 넘긴다). 색 토큰은 화면 몫이라 이 모듈은
# 받기만 한다.
Appearance = Callable[[pd.DataFrame], Mapping[str, Mapping[str, Any]]]


def editor_inputs(
    status: pd.DataFrame,
    *,
    floor: FloorKey,
    stage_of: Mapping[str, str] | None = None,
    new_ids: set[str] | None = None,
    arrived_ids: set[str] | None = None,
    appearance: Appearance | None = None,
) -> EditorInputs:
    """설비 편집본의 호기 상태(`build_space_equipment_status` 결과)에서 이 층 편집기 입력을 만든다.

    - 도면: 레이아웃반영여부(레이아웃표시 Y · 도면 이탈일 전) 이고 이 층에 X·Y·크기가 다 있는 호기
    - 트레이: 같은 대상 중 X·Y 가 없고 이 층이거나 층 미정인 호기. Main 설비 묶음의 다른 모듈이
      이 층 도면에 서 있으면 그 형제는 트레이에 따로 내놓지 않고 묶음의 미배치 모듈(`placed`
      거짓)로 함께 보낸다(상자를 한 모듈에만 그린 옛 설비) — 편집기가 그 묶음을 처음 옮기거나
      키울 때 바둑판 제 칸에 함께 놓는다(`tile_module_group`).
    - 영역 하한: 이 층에 좌표가 있지만 편집기에 안 나오는 호기(N·반출/이설 완료 …)가 차지한 범위.
      저장 검증은 그런 행에도 캔버스 상한을 걸므로 영역을 그보다 줄이지 못하게 한다.
    - `appearance` 를 주면 보내는 호기(도면·트레이)에만 불러 그 면·글자·경계 날짜를 항목에 얹는다.
    """
    target = status[LAYOUT_REFLECTED_COLUMN].fillna(False).astype(bool)
    on_floor = _floor_mask(status, floor)
    # 층 미정: 동까지 비었으면 모든 층, 동만 정해졌으면 그 동의 층마다 트레이에 뜬다.
    floorless = status["동"].isna() | (
        status["동"].eq(floor[0]).fillna(False).astype(bool) & status["층"].isna()
    )
    has_position = status.loc[:, list(POSITION_COLUMNS)].notna().all(axis=1)
    has_size = status.loc[:, list(SIZE_COLUMNS)].notna().all(axis=1)
    placed = target & on_floor & has_position & has_size
    keys = unit_keys(status)
    placed_keys = set(keys[placed].tolist())
    parents = _parents(status)
    unplaced = target & ~has_position & (on_floor | floorless)
    tray = unplaced & ~keys.isin(placed_keys)
    companions = unplaced & keys.isin(placed_keys) & parents.notna()
    hidden = on_floor & has_position & has_size & ~placed
    reserved = (
        (
            float((status.loc[hidden, "X좌표"] + status.loc[hidden, "Xsize"]).max()),
            float((status.loc[hidden, "Y좌표"] + status.loc[hidden, "Ysize"]).max()),
        )
        if hidden.any()
        else (0.0, 0.0)
    )
    standalone = placed & parents.isna()
    sizes = status.loc[standalone, list(SIZE_COLUMNS)]
    default_size = (
        (float(sizes["Xsize"].median()), float(sizes["Ysize"].median()))
        if not sizes.empty
        else _DEFAULT_SIZE
    )
    stages = stage_of or {}
    news = new_ids or set()
    arrivals = arrived_ids or set()
    shown = placed | tray | companions
    rows = status.loc[shown].assign(
        _placed=placed[shown], _floorless=floorless[shown], _parent=parents[shown]
    )
    # 다른 층에서 옮겨 온 호기는 같은 좌표로 와 기존 호기를 덮을 수 있다 — 맨 뒤(맨 위에 그림)로.
    order = (
        rows[EQUIPMENT_ID_COLUMN].astype("string").isin(arrivals).astype(int).argsort(kind="stable")
    )
    looks = appearance(rows) if appearance is not None else {}
    items: list[dict[str, Any]] = []
    for row in rows.iloc[order].to_dict(orient="records"):
        unit_id = str(row[EQUIPMENT_ID_COLUMN]).strip()
        parent = row["_parent"]
        items.append(
            {
                **looks.get(unit_id, {}),
                "id": unit_id,
                "label": unit_id,
                "stage": stages.get(unit_id, str(row.get("상태", "") or "")),
                "x": finite_or_none(row["X좌표"]),
                "y": finite_or_none(row["Y좌표"]),
                "w": finite_or_none(row["Xsize"]),
                "h": finite_or_none(row["Ysize"]),
                "placed": bool(row["_placed"]),
                "is_new": unit_id in news,
                "arrived": unit_id in arrivals,
                "floorless": bool(row["_floorless"]),
                "group": str(parent) if _present(parent) else None,
            }
        )
    unplaced_floorless = int((target & ~has_position & floorless).sum())
    return EditorInputs(
        items=tuple(items),
        reserved_extent=reserved,
        default_size=default_size,
        unplaced_floorless=unplaced_floorless,
    )


def new_unit_options(master: pd.DataFrame) -> dict[str, Any]:
    """편집기의 호기 추가 폼 선택지. 크기 힌트는 공정소분류별 가운데 크기(모듈 행 제외)."""

    def choices(column: str) -> list[str]:
        values = master[column].dropna().astype(str).str.strip()
        return sorted(value for value in values.unique() if value)

    sized = master.loc[
        master.loc[:, list(SIZE_COLUMNS)].notna().all(axis=1) & _parents(master).isna()
    ]
    hints = {
        str(name): [
            rounded_to_canvas(float(group["Xsize"].median())),
            rounded_to_canvas(float(group["Ysize"].median())),
        ]
        for name, group in sized.groupby("공정소분류")
    }
    unit_ids = set(master[EQUIPMENT_ID_COLUMN].dropna().astype(str).str.strip())
    # Main 설비 이름도 새 호기 이름으로 쓸 수 없다(설비 한 대가 두 번 세어진다).
    parent_ids = set(_parents(master).dropna().astype(str))
    return {
        "processes": choices("공정소분류"),
        "lines": choices("공정구분"),
        "uses": choices("투자구분"),
        "sizeHints": hints,
        "existingIds": sorted(unit_ids | parent_ids),
        "parentIds": sorted(parent_ids),
        "confirmations": list(QUAL_CONFIRMATION_STATUSES),
    }


# ------------------------------------------------------------------ 모듈 묶음 바둑판

# 모듈 묶음 = 이 편집기에 실린 호기 가운데 Main 설비가 같은 것이 둘 이상인 묶음(2026-10-23 사용자
# 요청). 사람이 고치는 것은 묶음 범위(이 층 도면에 선 모듈의 바깥 상자)뿐이고, 안의 모듈은 범위를
# 바둑판으로 똑같이 나눈 칸에 자동으로 선다. 편집기 JS(`editor.js` 의 `tileModuleGroup`·
# `naturalCompare`·`moduleGrid`)가 같은 규칙이고 `tests/test_space_module_group.py` 가 node 로 둘을
# 대조한다 — 한쪽을 고치면 다른 쪽도 고친다.
_TICKS_PER_UNIT: Final = 10**CANVAS_DECIMALS
_NAME_TOKEN: Final = re.compile(r"[0-9]+|[^0-9]+")
ModuleBox = tuple[float, float, float, float]


def module_grid(count: int) -> tuple[int, int]:
    """모듈 수 → (열, 행). 거의 정사각 격자다(열 = ⌈√n⌉, 행 = ⌈n ÷ 열⌉) — 넷이면 2×2,
    둘이면 2×1."""
    cols = max(1, math.ceil(math.sqrt(count)))
    return cols, max(1, math.ceil(count / cols))


def natural_name_key(name: str) -> tuple[tuple[tuple[int, int, str], ...], str]:
    """설비명 자연 정렬 열쇠(…12A, 12B, 12C, 12D — `EQ2` 가 `EQ10` 앞). 숫자 덩이(ASCII 0-9)는
    수로, 나머지 덩이는 소문자로 견주고, 덩이가 같으면 짧은 쪽이 앞이며, 그래도 같으면 글자 그대로
    견준다."""
    tokens = tuple(
        (0, int(token), "") if "0" <= token[0] <= "9" else (1, 0, token.lower())
        for token in _NAME_TOKEN.findall(name)
    )
    return tokens, name


def _ticks(value: float) -> int:
    """좌표·치수를 저장 정밀도 눈금(정수)으로 — 반올림은 JS 와 같은 `⌊v × 10^자리 + 0.5⌋`."""
    return math.floor(value * _TICKS_PER_UNIT + 0.5)


def tile_module_group(box: ModuleBox, names: Sequence[str]) -> dict[str, ModuleBox]:
    """묶음 범위 `box`(X, Y, 폭, 높이)를 `module_grid` 열×행으로 **똑같이** 나눈 칸에 모듈을 하나씩
    둔다(이름 → 칸).

    - 차례는 설비명 자연 정렬(`natural_name_key`)로 왼→오, 위→아래 — 첫 모듈이 왼쪽 위다. 칸이
      남으면(모듈 셋 → 2×2) 마지막 칸이 빈다.
    - 칸 폭·높이는 저장 정밀도 눈금으로 범위 ÷ 열(행)의 내림이고 **마지막 열(오른쪽)·마지막
      행(맨 아래)이 나머지를 받는다** — 칸들이 범위를 틈·겹침 없이 꼭 채운다.
    - 범위가 칸마다 한 눈금(`1 / 10^자리`)보다 작으면 오른쪽·위로 넓힌다(영역 밖으로 나가는지는
      부르는 쪽이 본다).
    """
    if not names:
        return {}
    cols, rows = module_grid(len(names))
    left, bottom = _ticks(box[0]), _ticks(box[1])
    width, height = max(_ticks(box[2]), cols), max(_ticks(box[3]), rows)
    cell_w, cell_h = width // cols, height // rows
    last_w, last_h = width - cell_w * (cols - 1), height - cell_h * (rows - 1)
    scale = _TICKS_PER_UNIT
    tiles: dict[str, ModuleBox] = {}
    for index, name in enumerate(sorted(names, key=natural_name_key)):
        col, row = index % cols, index // cols
        x = left + col * cell_w
        # 행은 위(0)에서 센다. 맨 아래 행이 범위 바닥에 서고 그 위로 칸 높이씩 쌓인다.
        y = bottom if row == rows - 1 else bottom + last_h + (rows - 2 - row) * cell_h
        w = last_w if col == cols - 1 else cell_w
        h = last_h if row == rows - 1 else cell_h
        tiles[name] = (x / scale, y / scale, w / scale, h / scale)
    return tiles


def _module_groups(editor_items: Sequence[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    """편집기에 실린 호기를 Main 설비로 묶어 모듈이 둘 이상인 묶음만(Main 설비 → 호기들)."""
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for item in editor_items:
        group = item.get("group")
        if isinstance(group, str) and group:
            groups.setdefault(group, []).append(item)
    return {group: items for group, items in groups.items() if len(items) >= 2}


def _box_ticks(values: Sequence[float | None]) -> tuple[int, int, int, int] | None:
    """(X, Y, 폭, 높이) → 눈금 넷. 하나라도 없으면 None."""
    x, y, w, h = values
    if x is None or y is None or w is None or h is None:
        return None
    return _ticks(x), _ticks(y), _ticks(w), _ticks(h)


def _regrid_module_groups(
    changes: Sequence[UnitChange],
    editor_items: Sequence[Mapping[str, Any]],
    bounds: CanvasSize,
) -> list[UnitChange]:
    """이번 적용에서 이 층 도면에 놓이거나 자리·크기가 바뀐 모듈 묶음을 정본 규칙
    (`tile_module_group`)으로 다시 놓는다.

    범위는 적용 뒤 이 층 도면에 선 모듈(이번에 바뀐 것은 바뀐 값, 아닌 것은 편집기에 보낸 값)의
    바깥 상자이고, 묶음의 모든 모듈(좌표가 없던 형제 포함)이 그 범위의 제 칸에 선다. 브라우저 값이
    규칙과 다르면(반올림 한 끝 등) **규칙 값으로 바로잡는다** — 거부하지 않는다. 바뀐 모듈이 없는
    묶음(바둑판이 아닌 옛 묶음 포함)은 건드리지 않는다. 묶음째 트레이로 빼거나 다른 층으로 보낸
    묶음도 그대로다. 한 묶음의 모듈이 갈라지면(일부만 빼거나 보냄) 편집기가 막는 길이라
    `ValueError` 다."""
    by_id = {change.unit_id: change for change in changes}
    fixed: dict[str, UnitChange] = {}
    added: list[UnitChange] = []
    for group, items in _module_groups(editor_items).items():
        ids = [str(item["id"]) for item in items]
        if not any(unit_id in by_id for unit_id in ids):
            continue
        before: dict[str, tuple[int, int, int, int] | None] = {}
        boxes: list[tuple[int, int, int, int]] = []
        apart: list[str] = []
        for item, unit_id in zip(items, ids, strict=True):
            sent = (
                _box_ticks([finite_or_none(item.get(key)) for key in ("x", "y", "w", "h")])
                if bool(item.get("placed"))
                else None
            )
            before[unit_id] = sent
            change = by_id.get(unit_id)
            now = (
                sent
                if change is None
                else _box_ticks([change.x, change.y, change.w, change.h])
                if change.placed and change.move_to is None
                else None
            )
            if change is not None and now is None:
                apart.append(unit_id)
            if now is not None:
                boxes.append(now)
        if not boxes:
            continue
        if apart:
            raise ValueError(
                f"Main 설비 {group} 의 모듈은 묶음째 옮기거나 빼야 합니다 — "
                f"{', '.join(sorted(apart, key=natural_name_key))} 만 따로 왔습니다."
            )
        left = min(box[0] for box in boxes)
        bottom = min(box[1] for box in boxes)
        right = max(box[0] + box[2] for box in boxes)
        top = max(box[1] + box[3] for box in boxes)
        scale = _TICKS_PER_UNIT
        tiles = tile_module_group(
            (left / scale, bottom / scale, (right - left) / scale, (top - bottom) / scale), ids
        )
        for unit_id in ids:
            x, y, w, h = tiles[unit_id]
            if x + w > bounds[0] + 1e-9 or y + h > bounds[1] + 1e-9:
                raise ValueError(
                    f"Main 설비 {group} 의 묶음 범위가 편집 영역 {bounds[0]:g} × {bounds[1]:g} 를 "
                    "벗어났습니다."
                )
            tile = UnitChange(unit_id, True, x, y, w, h, None)
            if unit_id in by_id:
                fixed[unit_id] = tile
            elif before[unit_id] != _box_ticks([x, y, w, h]):
                added.append(tile)
    return [fixed.get(change.unit_id, change) for change in changes] + added


# ------------------------------------------------------------------ 검증


def _require_name(name: str, subject: str) -> None:
    """설비명 글자 규칙(새 호기·이름 바꿈 공용): 1~`UNIT_ID_MAX` 자, 탭·줄바꿈·특수 공백 없음."""
    if not name or len(name) > UNIT_ID_MAX:
        raise ValueError(f"{subject}은 1~{UNIT_ID_MAX}자여야 합니다: {name!r}")
    if not name.isprintable():
        raise ValueError(f"{subject}에 탭·줄바꿈·특수 공백을 쓸 수 없습니다: {name!r}")


def _same_name(name: str, names: Collection[str]) -> str | None:
    """`names` 가운데 `name` 과 같은 이름(대소문자·앞뒤 공백 무시, `scalar_match_key`)."""
    key = scalar_match_key(name)
    return next((other for other in names if scalar_match_key(other) == key), None)


def _named(name: str, other: str) -> str:
    """겹친 이름이 글자까지 같으면 그대로, 대소문자·공백만 다르면 그 이름을 덧붙인다."""
    return name if other == name else f"{name}({other})"


def _reserved_reasons(reserved: ReservedNames) -> dict[str, str]:
    """편집본에 호기가 없어도 새 설비명으로 쓸 수 없는 이름(열쇠) → 까닭."""
    reasons: dict[str, str] = {}
    for name in sorted(reserved.orphan_downtime):
        reasons[scalar_match_key(name)] = (
            f"설비 마스터에 없는 설비명 {with_object_particle(name)} 가리키는 비가동 일정이 "
            "RawData 편집본에 남아 있어 그 일정이 이 호기에 붙습니다 — 그 비가동 일정을 먼저 "
            "고치거나 지우세요"
        )
    for name in sorted(reserved.deleted):
        reasons[scalar_match_key(name)] = (
            f"저장본의 {with_object_particle(name)} RawData 에서 지우고 아직 저장하지 않았습니다 "
            "— 그 이름을 이으면 저장 뒤 옛 호기의 이력과 섞이니, 지운 것을 먼저 저장하거나 "
            "되돌리세요"
        )
    return reasons


def _parse_created(
    unit_id: str,
    raw: Mapping[str, Any],
    taken: set[str],
    options: Mapping[str, Sequence[str]],
    reserved: Mapping[str, str],
) -> CreatedUnit:
    """새 호기 하나. 이름은 설비명·Main 설비와 대소문자·앞뒤 공백 무시로도 겹칠 수 없다(이름
    바꾸기와 같은 규칙)."""
    _require_name(unit_id, "새 호기 이름")
    parent = _same_name(unit_id, options.get("parentIds", ()))
    if parent is not None:
        raise ValueError(f"이미 Main 설비로 쓰는 이름입니다: {_named(unit_id, parent)}")
    holder = _same_name(unit_id, taken)
    if holder is not None:
        raise ValueError(f"이미 있는 호기입니다: {_named(unit_id, holder)}")
    if scalar_match_key(unit_id) in reserved:
        raise ValueError(
            f"새 호기 이름 {with_topic_particle(unit_id)} 쓸 수 없습니다 — "
            f"{reserved[scalar_match_key(unit_id)]}."
        )
    process = _text(raw.get("process")).strip()
    line = _text(raw.get("line")).strip()
    use = _text(raw.get("use")).strip()
    if process not in options.get("processes", ()):
        raise ValueError(f"새 호기 {unit_id} 의 공정소분류를 고를 수 없는 값입니다: {process!r}")
    if line and line not in options.get("lines", ()):
        raise ValueError(f"새 호기 {unit_id} 의 공정구분을 고를 수 없는 값입니다: {line!r}")
    if use and use not in options.get("uses", ()):
        raise ValueError(f"새 호기 {unit_id} 의 투자구분을 고를 수 없는 값입니다: {use!r}")
    existing = raw.get("existing") is True
    arrival = _iso_date(raw.get("arrival"), ARRIVAL_DATE_COLUMN, unit_id)
    qual = _iso_date(raw.get("qual"), QUAL_DATE_COLUMN, unit_id)
    confirm = _text(raw.get("confirm")).strip()
    if not existing:
        # 설비 마스터 계약: 반입·Qual 일정은 비워도 되고(둘 다 있으면 반입 ≤ Qual), Qual상태는
        # Qual일정이 있을 때만 필수다. Qual일정 없이 고른 Qual상태도 받는다.
        if arrival is not None and qual is not None and qual < arrival:
            raise ValueError(f"새 호기 {unit_id} 의 Qual일정이 반입일정보다 빠릅니다.")
        if confirm and confirm not in QUAL_CONFIRMATION_STATUSES:
            raise ValueError(
                f"새 호기 {unit_id} 의 {QUAL_STATUS_COLUMN}를 고를 수 없는 값입니다: {confirm!r}"
            )
        if qual is not None and not confirm:
            raise ValueError(
                f"신규 설비 {with_topic_particle(unit_id)} Qual일정이 있어 {QUAL_STATUS_COLUMN}가 "
                "필요합니다."
            )
    return CreatedUnit(
        unit_id=unit_id,
        process=process,
        line=line,
        use=use,
        existing=existing,
        arrival=None if existing else arrival,
        qual=None if existing else qual,
        confirm="" if existing else confirm,
    )


def _parse_renames(
    raw_renames: object,
    *,
    editor_ids: Collection[str],
    editor_groups: Collection[str],
) -> list[NameChange]:
    """적용값의 `renames`(``[{"kind": "unit"|"group", "from", "to"}]``)를 읽는다. 바꿀 것은 이
    편집기에 보낸 호기·묶음뿐이고, 새 이름은 설비명 글자 규칙을 따른다. 그대로인 항목은 버린다."""
    if raw_renames is None:
        return []
    if not isinstance(raw_renames, list):
        raise ValueError("이름 바꿈 목록을 읽지 못했습니다.")
    changes: list[NameChange] = []
    seen: set[tuple[str, str]] = set()
    for raw in raw_renames:
        if not isinstance(raw, Mapping):
            raise ValueError("이름 바꿈 목록을 읽지 못했습니다.")
        kind = raw.get("kind")
        old = _text(raw.get("from")).strip()
        new = _text(raw.get("to")).strip()
        if kind == "unit":
            if old not in editor_ids:
                raise ValueError(f"이 편집기에 없는 호기의 이름은 바꿀 수 없습니다: {old}")
            subject, what = f"{old} 의 새 이름", "호기"
        elif kind == "group":
            if old not in editor_groups:
                raise ValueError(f"이 편집기에 없는 Main 설비의 이름은 바꿀 수 없습니다: {old}")
            subject, what = f"Main 설비 {old} 의 새 이름", "Main 설비"
        else:
            raise ValueError(f"이름 바꿈의 종류를 알 수 없습니다: {kind!r}")
        if (kind, old) in seen:
            raise ValueError(f"같은 {what}의 이름 바꿈이 두 번 왔습니다: {old}")
        seen.add((kind, old))
        if not new:
            raise ValueError(f"{subject}을 비울 수 없습니다.")
        _require_name(new, subject)
        if new != old:
            changes.append(NameChange(kind=kind, old=old, new=new))
    return changes


def _require_distinct_names(
    renames: Sequence[NameChange],
    *,
    master_ids: Collection[str],
    group_ids: Collection[str],
    created_ids: Collection[str],
    reserved: Mapping[str, str],
) -> None:
    """바꾼 뒤에도 설비명·Main 설비 이름이 겹치지 않는지 본다(설비 마스터 전체 — 다른 층·
    미배치·레이아웃 제외 포함). 겹침은 `scalar_match_key` 로 본다 — 대소문자·앞뒤 공백만 다른 두
    이름은 같은 이름이다. 저장 검증(`prepare_equipment_master`)은 글자 그대로 견주므로 그보다
    엄하다. 바꾼 뒤의 상태로 보므로 같은 적용에서 A→X·B→A 처럼 비운 이름을 다시 쓰는 것은 받는다.

    - 설비명을 바꾸면: 다른 설비명(새로 넣는 호기, 같은 적용의 다른 이름 바꿈 포함)·Main 설비
      이름과 겹칠 수 없다. 자기 대소문자만 바꾸는 것은 된다. 자기 설비명을 Main 설비로 적은 한
      행짜리 묶음은 Main 설비가 따라가므로 그 묶음과는 겹치지 않는다.
    - Main 설비 이름을 바꾸면: 어떤 설비명과도, 다른 Main 설비 이름과도 겹칠 수 없다.
    - 설비명은 편집본에 호기가 없어도 `reserved`(`_reserved_reasons` — RawData 에서 지우고 저장 안
      한 저장본 이름, 설비 마스터에 없는 설비명을 가리키는 비가동 일정)와도 겹칠 수 없다.
    """
    units = {change.old: change.new for change in renames if change.kind == "unit"}
    groups = {change.old: change.new for change in renames if change.kind == "group"}
    if not units and not groups:
        return
    # 자기 설비명을 Main 설비로 적은 한 행짜리 묶음(저장 검증이 이 경우만 이름이 같아도 받는다).
    self_named = set(master_ids) & set(group_ids)
    # 바꾼 뒤의 이름(열쇠) → (그 이름을 쓰는 것, 겹칠 때 알릴 까닭). 자기 자신은 `owner` 로 가른다.
    unit_names: dict[str, list[tuple[str, str]]] = {}
    group_names: dict[str, list[tuple[str, str]]] = {}
    for name in master_ids:
        if name not in units:
            unit_names.setdefault(scalar_match_key(name), []).append(
                (f"unit:{name}", f"이미 있는 설비명입니다({name})")
            )
    for name in created_ids:
        unit_names.setdefault(scalar_match_key(name), []).append(
            (f"created:{name}", f"이번 적용에서 새로 넣는 호기 이름입니다({name})")
        )
    for old, new in units.items():
        unit_names.setdefault(scalar_match_key(new), []).append(
            (f"unit:{old}", f"이번 적용에서 {old} 도 {with_direction_particle(new)} 바꿉니다")
        )
    for name in group_ids:
        if name not in groups and not (name in units and name in self_named):
            group_names.setdefault(scalar_match_key(name), []).append(
                (f"group:{name}", f"이미 Main 설비 이름입니다({name})")
            )
    for old, new in groups.items():
        group_names.setdefault(scalar_match_key(new), []).append(
            (
                f"group:{old}",
                f"이번 적용에서 Main 설비 {old} 도 {with_direction_particle(new)} 바꿉니다",
            )
        )

    def refuse(subject: str, new: str, reason: str) -> ValueError:
        return ValueError(
            f"{subject} {with_topic_particle(new)} 쓸 수 없습니다 — {reason}. 설비명·Main 설비 "
            f"이름은 설비 마스터 전체(다른 층·미배치 포함)에서 하나여야 하고, {_SAME_NAME_NOTE}."
        )

    for change in renames:
        key = scalar_match_key(change.new)
        owner = f"{change.kind}:{change.old}"
        subject = (
            f"{change.old} 의 새 이름"
            if change.kind == "unit"
            else f"Main 설비 {change.old} 의 새 이름"
        )
        same_kind = unit_names if change.kind == "unit" else group_names
        other_kind = group_names if change.kind == "unit" else unit_names
        for who, reason in same_kind.get(key, []):
            if who != owner:
                raise refuse(subject, change.new, reason)
        for _, reason in other_kind.get(key, []):
            raise refuse(subject, change.new, reason)
        if change.kind == "unit" and key in reserved:
            raise ValueError(
                f"{subject} {with_topic_particle(change.new)} 쓸 수 없습니다 — {reserved[key]}."
            )


def parse_editor_apply(
    payload: Mapping[str, Any],
    *,
    editor_ids: set[str],
    master_ids: set[str],
    floor: FloorKey,
    floors: Sequence[FloorKey],
    canvas: CanvasSize,
    unit_options: Mapping[str, Sequence[str]],
    editor_groups: Collection[str] = frozenset(),
    reserved: ReservedNames | None = None,
    editor_items: Sequence[Mapping[str, Any]] = (),
) -> EditorApply:
    """브라우저 적용값을 검증한다. **하나라도 어긋나면 `ValueError`** — 일부만 반영하지 않는다.

    `editor_ids` 는 이번 편집기에 보낸 호기, `master_ids` 는 편집본의 모든 호기(새 호기 중복 검사).
    `editor_groups` 는 이번 편집기에 보낸 호기의 Main 설비(이름을 바꿀 수 있는 묶음)이고, Main 설비
    전체 목록은 `unit_options["parentIds"]` 다. `reserved`(`reserved_names`)는 편집본에 호기가
    없어도 새 설비명(새 호기·이름 바꿈)으로 쓸 수 없는 이름이다. 다른 층으로 보낸 호기의 좌표는 그
    층 영역을 여기서 모르므로 범위를 보지 않는다 — `apply_layout_edits` 가 그 층 캔버스 안으로 민다.

    `editor_items`(이번 편집기에 보낸 호기 `editor_inputs(...).items`)를 주면 이 층 도면에
    놓이거나 자리·크기가 바뀐 Main 설비 모듈 묶음을 정본 규칙으로 다시 놓는다
    (`_regrid_module_groups` — 브라우저 값이 규칙과 다르면 규칙 값으로 바로잡고, 좌표가 없던 형제도
    제 칸에 놓는다).
    """
    held = _reserved_reasons(reserved or ReservedNames())
    targets = {floor_label(key): key for key in floors if key != floor}
    new_canvas: CanvasSize | None = None
    raw_canvas = payload.get("canvas")
    if isinstance(raw_canvas, Mapping):
        width, height = (
            finite_or_none(raw_canvas.get("width")),
            finite_or_none(raw_canvas.get("height")),
        )
        if width is None or height is None:
            raise ValueError("편집 영역 크기를 읽지 못했습니다.")
        new_canvas = normalize_canvas_size(width, height)
    elif raw_canvas is not None:
        raise ValueError("편집 영역 크기를 읽지 못했습니다.")
    bounds = new_canvas or canvas
    changes: list[UnitChange] = []
    created: list[CreatedUnit] = []
    seen: set[str] = set()
    for raw in payload.get("changes") or []:
        if not isinstance(raw, Mapping):
            raise ValueError("편집기 적용값의 형식이 맞지 않습니다.")
        unit_id = _text(raw.get("id")).strip()
        if unit_id in seen:
            raise ValueError(f"같은 호기가 두 번 왔습니다: {unit_id}")
        seen.add(unit_id)
        if raw.get("created") is not None:
            if not isinstance(raw.get("created"), Mapping):
                raise ValueError(f"새 호기 {unit_id} 의 값을 읽지 못했습니다.")
            # 같은 적용에서 먼저 넣은 새 호기와도 겹칠 수 없다(대소문자·앞뒤 공백 무시).
            taken = master_ids | editor_ids | {unit.unit_id for unit in created}
            created.append(_parse_created(unit_id, raw["created"], taken, unit_options, held))
        elif unit_id not in editor_ids:
            raise ValueError(f"이 편집기에 없는 호기입니다: {unit_id}")
        move_to: FloorKey | None = None
        if raw.get("moveTo") is not None:
            move_to = targets.get(_text(raw.get("moveTo")))
            if move_to is None:
                raise ValueError(f"{unit_id} 를 보낼 층을 알 수 없습니다: {raw.get('moveTo')!r}")
        w, h = finite_or_none(raw.get("w")), finite_or_none(raw.get("h"))
        if (w is None) != (h is None) or (w is not None and h is not None and (w <= 0 or h <= 0)):
            raise ValueError(f"{unit_id} 의 크기는 0 보다 큰 폭·높이 둘 다여야 합니다.")
        if w is not None and h is not None and (w > MAX_CANVAS_EXTENT or h > MAX_CANVAS_EXTENT):
            raise ValueError(f"{unit_id} 의 크기가 너무 큽니다: {w:g} × {h:g}")
        placed = raw.get("placed") is True
        x = y = None
        if placed:
            x, y = finite_or_none(raw.get("x")), finite_or_none(raw.get("y"))
            if x is None or y is None or w is None or h is None:
                raise ValueError(f"{unit_id} 를 놓은 좌표·크기를 읽지 못했습니다.")
            x, y, w, h = (
                rounded_to_canvas(x),
                rounded_to_canvas(y),
                rounded_to_canvas(w),
                rounded_to_canvas(h),
            )
            if x < 0 or y < 0:
                raise ValueError(f"{unit_id} 의 좌표는 0 이상이어야 합니다.")
            if move_to is None and (x + w > bounds[0] + 1e-9 or y + h > bounds[1] + 1e-9):
                raise ValueError(
                    f"{unit_id} 가 편집 영역 {bounds[0]:g} × {bounds[1]:g} 를 벗어났습니다."
                )
        elif w is not None and h is not None:
            w, h = rounded_to_canvas(w), rounded_to_canvas(h)
        if raw.get("created") is not None and (w is None or h is None):
            raise ValueError(f"새 호기 {unit_id} 의 크기가 없습니다.")
        changes.append(UnitChange(unit_id, placed, x, y, w, h, move_to))
    changes = _regrid_module_groups(changes, editor_items, bounds)
    raw_marks = payload.get("marks")
    marks: tuple[FloorLayoutMark, ...] | None = None
    if raw_marks is not None:
        if not isinstance(raw_marks, list):
            raise ValueError("도면 요소 목록을 읽지 못했습니다.")
        marks = prepare_floor_layout_marks(raw_marks, bounds)
    renames = _parse_renames(
        payload.get("renames"), editor_ids=editor_ids, editor_groups=editor_groups
    )
    _require_distinct_names(
        renames,
        master_ids=master_ids | editor_ids,
        group_ids=set(unit_options.get("parentIds", ())),
        created_ids={unit.unit_id for unit in created},
        reserved=held,
    )
    return EditorApply(
        changes=tuple(changes),
        created=tuple(created),
        canvas=new_canvas,
        marks=marks,
        renames=tuple(renames),
    )


# ------------------------------------------------------------------ 반영


def created_unit_row(unit: CreatedUnit, master: pd.DataFrame, size: CanvasSize) -> dict[str, Any]:
    """새 호기 행. 받은 값만 넣고 나머지는 비운다 — 다른 호기의 일정·담당자를 베끼지 않는다.
    공정대분류만 같은 공정소분류의 값을 따른다(계층이라 하나로 정해진다). 층 미정·미배치로 선다."""
    row: dict[str, Any] = {column: None for column in master.columns}
    parents = master.loc[
        master["공정소분류"].astype("string").str.strip().eq(unit.process).fillna(False),
        "공정대분류",
    ].dropna()
    row.update(
        {
            EQUIPMENT_ID_COLUMN: unit.unit_id,
            "공정소분류": unit.process,
            "공정대분류": parents.iloc[0] if not parents.empty else None,
            "공정구분": unit.line or None,
            "투자구분": unit.use or None,
            STORAGE_FLAG_COLUMN: "N",
            "기존설비여부": "Y" if unit.existing else "N",
            ARRIVAL_DATE_COLUMN: pd.Timestamp(unit.arrival) if unit.arrival else None,
            QUAL_DATE_COLUMN: pd.Timestamp(unit.qual) if unit.qual else None,
            QUAL_STATUS_COLUMN: unit.confirm or None,
            "레이아웃표시": "Y",
            "Xsize": size[0],
            "Ysize": size[1],
            "호기이력": NEW_UNIT_HISTORY,
        }
    )
    if "환산비" in row:
        row["환산비"] = 1.0
    return row


def _aligned(extra: pd.DataFrame, like: pd.DataFrame) -> pd.DataFrame:
    """새 행 프레임의 칸 형을 편집본에 맞춘다. 빈 날짜 칸이 object(None)로 붙으면 편집본의 날짜 칸
    전체가 object 로 바뀌어 다른 호기까지 「바뀌었다」로 보인다."""
    for column in like.columns:
        dtype = like[column].dtype
        if pd.api.types.is_bool_dtype(dtype):
            continue
        try:
            extra[column] = extra[column].astype(dtype)
        except (TypeError, ValueError):
            continue
    return extra


def _id_mask(frame: pd.DataFrame, unit_id: str) -> pd.Series:
    return (
        frame[EQUIPMENT_ID_COLUMN]
        .astype("string")
        .str.strip()
        .eq(unit_id)
        .fillna(False)
        .astype(bool)
    )


def _fit_moved_into_canvases(
    master: pd.DataFrame,
    moved: Sequence[UnitChange],
    canvases: Mapping[FloorKey, CanvasSize],
    default_canvas: CanvasSize,
) -> None:
    """좌표째 다른 층으로 보낸 호기를 그 층 영역 안으로 민다. Main 설비 묶음은 모양째 옮기고,
    묶음(또는 호기)이 영역보다 크면 그 층 트레이로 보낸다(크기는 남긴다)."""
    groups: dict[tuple[FloorKey, str], list[pd.Series]] = {}
    keys = unit_keys(master)
    for change in moved:
        if change.move_to is None or not change.placed:
            continue
        mask = _id_mask(master, change.unit_id)
        groups.setdefault((change.move_to, str(keys[mask].iloc[0])), []).append(mask)
    for (target, _), masks in groups.items():
        rows = pd.concat([master.loc[mask] for mask in masks])
        width, height = canvases.get(target, default_canvas)
        left, bottom = float(rows["X좌표"].min()), float(rows["Y좌표"].min())
        right = float((rows["X좌표"] + rows["Xsize"]).max())
        top = float((rows["Y좌표"] + rows["Ysize"]).max())
        combined = masks[0]
        for mask in masks[1:]:
            combined = combined | mask
        if right - left > width + 1e-9 or top - bottom > height + 1e-9:
            master.loc[combined, list(POSITION_COLUMNS)] = None
            continue
        shift_x, shift_y = min(0.0, width - right), min(0.0, height - top)
        master.loc[combined, "X좌표"] = (master.loc[combined, "X좌표"] + shift_x).round(
            CANVAS_DECIMALS
        )
        master.loc[combined, "Y좌표"] = (master.loc[combined, "Y좌표"] + shift_y).round(
            CANVAS_DECIMALS
        )


def _harmonize_groups(master: pd.DataFrame, changed_ids: Sequence[str]) -> None:
    """바뀐 모듈 행의 동·층을 같은 Main 설비의 모든 행에 맞춘다(편집기에 없던 형제 포함).

    편집기에 없던 형제(반출/이설 완료·레이아웃표시 N …)가 이 맞춤으로 **층이 바뀌면** 그 X·Y 를
    비운다. 옛 층 좌표를 지닌 채 따라가면 새 층 캔버스 밖이라 거부되거나 새 층에 유령 영역을 남긴다.
    크기는 남긴다(크기만 있는 행은 받는다)."""
    parents = _parents(master)
    ids = master[EQUIPMENT_ID_COLUMN].astype("string").str.strip()
    changed = set(changed_ids)
    done: set[str] = set()
    for unit_id in changed_ids:
        mask = _id_mask(master, unit_id)
        if not mask.any():
            continue
        parent = parents[mask].iloc[0]
        if not _present(parent) or parent in done:
            continue
        done.add(str(parent))
        siblings = parents.eq(parent).fillna(False).astype(bool)
        building, floor = master.loc[mask, "동"].iloc[0], master.loc[mask, "층"].iloc[0]
        same_floor = master["동"].eq(building).fillna(False).astype(bool) & master["층"].eq(
            floor
        ).fillna(False).astype(bool)
        leaving = siblings & ~same_floor & ~ids.isin(changed).fillna(False).astype(bool)
        master.loc[leaving, list(POSITION_COLUMNS)] = None
        master.loc[siblings, ["동", "층"]] = [building, floor]


def apply_layout_edits(
    master: pd.DataFrame,
    apply: EditorApply,
    *,
    floor: FloorKey,
    canvases: Mapping[FloorKey, CanvasSize],
    default_canvas: CanvasSize,
) -> pd.DataFrame:
    """검증한 적용값을 편집본 설비 마스터에 얹은 새 프레임을 돌려준다(원본은 그대로).

    - 놓기·옮기기·크기: 그 층, X·Y·크기, 레이아웃표시 Y
    - 트레이로 빼기: X·Y 만 비우고 크기는 남긴다. 동·층은 그대로(그 층 트레이에 남는다)
    - 다른 층으로 보내기: 동·층을 바꾸고, 놓여 있던 호기는 좌표째 그 층 영역 안으로 민다
    - 새 호기: 받은 값만 채운 행을 끝에 붙인다(층 미정·미배치, 놓았으면 그 자리)
    """
    result = master.copy()
    sizes = {change.unit_id: (change.w, change.h) for change in apply.changes}
    if apply.created:
        rows = []
        for unit in apply.created:
            width, height = sizes.get(unit.unit_id, (None, None))
            if width is None or height is None:
                raise ValueError(f"새 호기 {unit.unit_id} 의 크기가 없습니다.")
            rows.append(created_unit_row(unit, result, (width, height)))
        extra = _aligned(pd.DataFrame(rows, columns=result.columns), result)
        result = pd.concat([result, extra], ignore_index=True)
    for change in apply.changes:
        mask = _id_mask(result, change.unit_id)
        if not mask.any():
            raise ValueError(f"편집본에 없는 호기입니다: {change.unit_id}")
        target = change.move_to or floor
        if change.placed:
            result.loc[mask, ["동", "층"]] = [target[0], target[1]]
            result.loc[mask, ["X좌표", "Y좌표", "Xsize", "Ysize"]] = [
                change.x,
                change.y,
                change.w,
                change.h,
            ]
        else:
            result.loc[mask, list(POSITION_COLUMNS)] = None
            if change.w is not None and change.h is not None:
                result.loc[mask, list(SIZE_COLUMNS)] = [change.w, change.h]
            if change.move_to is not None:
                result.loc[mask, ["동", "층"]] = [target[0], target[1]]
        result.loc[mask, "레이아웃표시"] = "Y"
    _fit_moved_into_canvases(result, apply.changes, canvases, default_canvas)
    _harmonize_groups(result, [change.unit_id for change in apply.changes])
    return result


def apply_name_changes(
    master: pd.DataFrame, downtime: pd.DataFrame, renames: Sequence[NameChange]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """검증한 이름 바꿈을 설비 마스터와 비가동 일정에 얹은 새 프레임 둘을 돌려준다(원본은 그대로).

    `apply_layout_edits` **뒤에** 부른다 — 배치 변경은 옛 설비명으로 온다. 바꿈은 한꺼번에 한다(A↔B
    처럼 서로 바꾼 이름도 맞게 간다). 좌표·크기 등 나머지 칸은 그대로라 배치가 남는다.

    - 설비명: 그 행의 설비명과, 그 설비명을 가리키는 비가동 일정의 설비명. 자기 설비명을 Main 설비로
      적은 한 행짜리 묶음은 Main 설비도 따라간다.
    - Main 설비: 그 이름을 쓰는 모든 행(편집기에 없는 형제 포함). 비가동 일정은 설비명만 가리키므로
      바꿀 것이 없다.
    """
    units = {change.old: change.new for change in renames if change.kind == "unit"}
    groups = {change.old: change.new for change in renames if change.kind == "group"}
    if not units and not groups:
        return master, downtime
    result = master.copy()
    ids = result[EQUIPMENT_ID_COLUMN].astype("string").str.strip()
    parents = _parents(result)
    renamed = ids.isin(list(units)).fillna(False).astype(bool)
    new_parents = parents.copy()
    grouped = parents.isin(list(groups)).fillna(False).astype(bool)
    new_parents.loc[grouped] = parents.loc[grouped].map(groups)
    follows = renamed & parents.eq(ids).fillna(False).astype(bool)
    new_parents.loc[follows] = ids.loc[follows].map(units)
    if renamed.any():
        result.loc[renamed, EQUIPMENT_ID_COLUMN] = ids.loc[renamed].map(units)
    changed_parents = grouped | follows
    if changed_parents.any():
        result.loc[changed_parents, PARENT_EQUIPMENT_COLUMN] = new_parents.loc[changed_parents]
    return result, _renamed_downtime(downtime, units)


def _renamed_downtime(downtime: pd.DataFrame, units: Mapping[str, str]) -> pd.DataFrame:
    """비가동 일정의 설비명을 (옛 이름 → 새 이름) 지도대로 한꺼번에 바꾼 사본."""
    schedule = downtime.copy()
    if not units or schedule.empty:
        return schedule
    names = schedule[EQUIPMENT_ID_COLUMN].astype("string").str.strip()
    hit = names.isin(list(units)).fillna(False).astype(bool)
    if hit.any():
        schedule.loc[hit, EQUIPMENT_ID_COLUMN] = names.loc[hit].map(units)
    return schedule


# ------------------------------------------------------------------ 저장 안 한 이름 바꿈


def _name_set(values: pd.Series) -> set[str]:
    return set(values.dropna().astype(str).str.strip()) - {""}


def _compose(
    current: Mapping[str, str], applied: Mapping[str, str], saved: set[str]
) -> dict[str, str]:
    """지금 이름 → 저장본 이름 지도에 이번 바꿈(옛 이름 → 새 이름)을 잇는다. A→B 뒤 B→C 는 C→A,
    다시 A 로 돌리면 항목이 빠진다. 저장본에 없던 이름(새 호기)은 기억하지 않는다."""
    if not applied:
        return dict(current)
    result = {now: origin for now, origin in current.items() if now not in applied}
    for old, new in applied.items():
        origin = current.get(old, old)
        if origin in saved and origin != new:
            result[new] = origin
    return result


def compose_renames(
    pending: PendingRenames, apply: EditorApply, *, saved: pd.DataFrame
) -> PendingRenames:
    """이번 적용의 이름 바꿈을 세션의 저장 안 한 이름 바꿈에 잇는다(`saved` 는 최신 저장본)."""
    return PendingRenames(
        units=_compose(pending.units, apply.unit_renames, _name_set(saved[EQUIPMENT_ID_COLUMN])),
        groups=_compose(pending.groups, apply.group_renames, _name_set(_parents(saved))),
    )


def live_renames(
    pending: PendingRenames | None, saved: pd.DataFrame, buffer: pd.DataFrame
) -> PendingRenames:
    """지금도 맞는 항목만 남긴다 — 지금 이름이 편집본에 있고 저장본 이름이 저장본에 있으며, 저장본
    이름이 편집본에 없거나 **그 이름을 이 지도의 다른 살아 있는 항목이 이어받았을 때**(맞바꿈 A↔B,
    A→X 뒤 B→A). RawData 에서 그 사이 되돌린 이름(지금 이름이 편집본에 없음)과 옛 이름을 새로 쓴
    행(옛 이름이 편집본에 있는데 이어받은 항목이 없음)은 이름 바꿈으로 읽지 않는다."""
    if not pending:
        return PendingRenames()
    return PendingRenames(
        units=_live_entries(
            pending.units,
            saved=_name_set(saved[EQUIPMENT_ID_COLUMN]),
            buffer=_name_set(buffer[EQUIPMENT_ID_COLUMN]),
        ),
        groups=_live_entries(
            pending.groups, saved=_name_set(_parents(saved)), buffer=_name_set(_parents(buffer))
        ),
    )


def _live_entries(
    entries: Mapping[str, str], *, saved: set[str], buffer: set[str]
) -> dict[str, str]:
    """`live_renames` 의 한 지도. 옛 이름이 편집본에 남아 있으면 그 이름을 지금 이름으로 쓰는 다른
    항목도 살아 있어야 한다 — 하나가 죽으면 그것에 기대던 항목도 다시 본다(고정점까지)."""
    live = {now: origin for now, origin in entries.items() if now in buffer and origin in saved}
    while True:
        dead = [now for now, origin in live.items() if origin in buffer and origin not in live]
        if not dead:
            return live
        for now in dead:
            live.pop(now)


def reserved_names(
    saved: pd.DataFrame,
    buffer: pd.DataFrame,
    downtime: pd.DataFrame,
    renames: PendingRenames | None,
) -> ReservedNames:
    """편집본(`buffer` 설비 마스터·`downtime` 비가동 일정)에 호기가 없어도 새 설비명으로 쓸 수 없는
    이름. 저장본에서 사라진 이름 가운데 저장 안 한 이름 바꿈(`renames`)으로 비운 것은 지운 것이
    아니다."""
    buffer_ids = _name_set(buffer[EQUIPMENT_ID_COLUMN])
    renamed_away = set(live_renames(renames, saved, buffer).units.values())
    deleted = _name_set(saved[EQUIPMENT_ID_COLUMN]) - buffer_ids - renamed_away
    orphan = (
        _name_set(downtime[EQUIPMENT_ID_COLUMN]) - buffer_ids
        if EQUIPMENT_ID_COLUMN in downtime.columns
        else set()
    )
    return ReservedNames(deleted=frozenset(deleted), orphan_downtime=frozenset(orphan))


def name_changes(
    saved: pd.DataFrame, buffer: pd.DataFrame, renames: PendingRenames | None
) -> pd.DataFrame:
    """저장 안 한 이름 바꿈 목록(바꿈마다 한 줄): 구분·이전 이름·새 이름. Main 설비는 묶음마다 한
    줄이고 구분에 모듈 행 수를 단다."""
    live = live_renames(renames, saved, buffer)
    parents = _parents(buffer)
    rows = [
        {"구분": "설비명", "이전 이름": origin, "새 이름": now}
        for now, origin in sorted(live.units.items())
    ]
    rows += [
        {
            "구분": f"Main 설비(모듈 {int(parents.eq(now).fillna(False).sum())}행)",
            "이전 이름": origin,
            "새 이름": now,
        }
        for now, origin in sorted(live.groups.items())
    ]
    return pd.DataFrame(rows, columns=["구분", "이전 이름", "새 이름"])


def downtime_with_renames(
    downtime: pd.DataFrame,
    renames: PendingRenames | None,
    *,
    saved: pd.DataFrame,
    buffer: pd.DataFrame,
) -> pd.DataFrame:
    """저장본 비가동 일정에 저장 안 한 설비명 바꿈(저장본 이름 → 지금 이름)을 얹은 사본. 편집본과
    견줄 때 이름 바꿈을 따라간 설비명을 「RawData 의 비가동 일정 편집」으로 세지 않게 한다."""
    live = live_renames(renames, saved, buffer)
    return _renamed_downtime(downtime, {origin: now for now, origin in live.units.items()})


# ------------------------------------------------------------------ 경고·변경 목록


def _boxes(frame: pd.DataFrame) -> pd.DataFrame:
    """끝 좌표는 저장 정밀도로 반올림한다 — 붙여 놓은 이웃을 부동소수 오차로 겹침이라 하지 않게."""
    return frame.assign(
        _right=(frame["X좌표"] + frame["Xsize"]).round(CANVAS_DECIMALS),
        _top=(frame["Y좌표"] + frame["Ysize"]).round(CANVAS_DECIMALS),
    )


def layout_warnings(
    status: pd.DataFrame,
    marks_by_floor: Mapping[FloorKey, Sequence[FloorLayoutMark]],
    *,
    limit: int = 8,
) -> list[str]:
    """겹친 호기와 반입구·문·기둥·설비 금지 영역을 덮은 호기. **저장은 막지 않고 알리기만 한다**.

    대상은 편집기와 같다 — 레이아웃반영여부이고 좌표가 다 있는 호기(도면 이탈일이 지난 호기 제외).
    """
    placed = status.loc[
        status[LAYOUT_REFLECTED_COLUMN].fillna(False).astype(bool)
        & status.loc[:, [*POSITION_COLUMNS, *SIZE_COLUMNS]].notna().all(axis=1)
        & status["동"].notna()
        & status["층"].notna()
    ]
    pairs: list[str] = []
    blocked: list[str] = []
    for (building, floor), rows in _boxes(placed).groupby(["동", "층"], sort=True):
        records = rows.to_dict(orient="records")
        name = f"{building} {floor}"
        for index, a in enumerate(records):
            for b in records[index + 1 :]:
                if (
                    a["X좌표"] < b["_right"]
                    and b["X좌표"] < a["_right"]
                    and a["Y좌표"] < b["_top"]
                    and b["Y좌표"] < a["_top"]
                ):
                    pairs.append(f"{a[EQUIPMENT_ID_COLUMN]} ↔ {b[EQUIPMENT_ID_COLUMN]} ({name})")
        for mark in marks_by_floor.get((str(building), str(floor)), ()):
            if not mark.blocks:
                continue
            mark_right, mark_top = (
                rounded_to_canvas(mark.x + mark.w),
                rounded_to_canvas(mark.y + mark.h),
            )
            for record in records:
                if (
                    record["X좌표"] < mark_right
                    and mark.x < record["_right"]
                    and record["Y좌표"] < mark_top
                    and mark.y < record["_top"]
                ):
                    blocked.append(f"{record[EQUIPMENT_ID_COLUMN]} → {mark.name} ({name})")
    messages = []
    for title, rows_text in (
        ("겹친 호기", pairs),
        ("반입구·문·기둥·설비 금지 영역을 덮은 호기", blocked),
    ):
        if rows_text:
            more = f" 외 {len(rows_text) - limit}건" if len(rows_text) > limit else ""
            messages.append(
                f"{title} {len(rows_text)}건 — 저장은 막지 않습니다: "
                f"{', '.join(rows_text[:limit])}{more}"
            )
    return messages


def _where(row: Mapping[Any, Any]) -> str:
    floor = (
        "층 미정"
        if not (_present(row.get("동")) and _present(row.get("층")))
        else f"{row['동']} {row['층']}"
    )
    width, height = finite_or_none(row.get("Xsize")), finite_or_none(row.get("Ysize"))
    size = f"{width:g}×{height:g}" if width is not None and height is not None else "크기 없음"
    x, y = finite_or_none(row.get("X좌표")), finite_or_none(row.get("Y좌표"))
    if x is None or y is None:
        return f"{floor} · 미배치 {size}"
    return f"{floor} · {x:g}, {y:g} · {size}"


def buffer_matches_saved(
    saved: Sequence[pd.DataFrame],
    buffer: Sequence[pd.DataFrame],
    renames: PendingRenames | None = None,
) -> bool:
    """편집본 표들이 저장본과 내용·형까지 같고 저장 안 한 이름 바꿈이 없는가. 참이면
    `layout_changes`·`name_changes` 는 빈 표, `other_change_count` 는 0, `table_changed` 는 거짓,
    `unsaved_unit_ids` 는 빈 묶음이다(저장본 설비명은 검증으로 겹치지 않는다) — 셀마다 견주는
    비교를 건너뛰는 빠른 길이다.

    판정은 내용(`DataFrame.equals`)으로만 한다. 편집본 세대·리비전 번호로 판정하면 세대를 올리지
    않는 편집을 놓친다. `equals` 는 칸 형까지 보므로 값은 같고 형만 다르면 「다르다」로 보고 셀
    비교로 넘어간다(안전한 쪽). 반대로 `equals` 가 같다고 보는데 셀 비교가 다르다고 하는 경우도
    있다 — 예: `0.0`↔`-0.0`, object 칸의 Timestamp↔datetime64·`True`↔`1`. 모두 셀 비교가 거짓
    「다름」을 내는 쪽이라, 빠른 길이 빈 결과를 내도 실제 편집을 숨기지 않는다.
    """
    if renames or len(saved) != len(buffer):
        return False
    return all(left.equals(right) for left, right in zip(saved, buffer, strict=True))


def _comparable(value: object) -> str:
    if not _present(value):
        return ""
    number = finite_or_none(value)
    if number is not None and not isinstance(value, str):
        return repr(round(number, 6))
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    return str(value).strip()


def layout_changes(
    saved: pd.DataFrame, buffer: pd.DataFrame, renames: PendingRenames | None = None
) -> pd.DataFrame:
    """저장본과 편집본의 배치 칸 차이(호기마다 한 줄): 설비명·Main 설비·구분·이전·새.

    이름을 바꾼 호기는 `renames` 로 저장본의 옛 이름 행과 견준다(설비명은 지금 이름). 이름만 바꾼
    호기는 여기 없고 `name_changes` 가 말한다."""
    saved_rows = {
        str(row[EQUIPMENT_ID_COLUMN]).strip(): row for row in saved.to_dict(orient="records")
    }
    origins = live_renames(renames, saved, buffer).units
    rows = []
    for row in buffer.to_dict(orient="records"):
        unit_id = str(row[EQUIPMENT_ID_COLUMN]).strip()
        before = saved_rows.get(origins.get(unit_id, unit_id))
        parent = row.get(PARENT_EQUIPMENT_COLUMN)
        parent_text = str(parent) if _present(parent) else ""
        if before is None:
            if _text(row.get("호기이력")) != NEW_UNIT_HISTORY:
                continue
            rows.append(
                {
                    EQUIPMENT_ID_COLUMN: unit_id,
                    PARENT_EQUIPMENT_COLUMN: parent_text,
                    "변경": "새 호기",
                    "이전": "",
                    "새": _where(row),
                }
            )
            continue
        if all(_comparable(before.get(c)) == _comparable(row.get(c)) for c in PLACE_COLUMNS):
            continue
        before_floor = (_comparable(before.get("동")), _comparable(before.get("층")))
        after_floor = (_comparable(row.get("동")), _comparable(row.get("층")))
        was_placed = _present(before.get("X좌표"))
        now_placed = _present(row.get("X좌표"))
        floor_changed = before_floor != after_floor
        if floor_changed and "" not in before_floor:
            kind = "층 이동"
        elif not now_placed and was_placed:
            kind = "트레이로 빼기(크기 유지)"
        elif not now_placed:
            kind = "층 지정(미배치)" if floor_changed else "크기"
        elif not was_placed:
            kind = "새 배치"
        else:
            kind = "이동·크기"
        rows.append(
            {
                EQUIPMENT_ID_COLUMN: unit_id,
                PARENT_EQUIPMENT_COLUMN: parent_text,
                "변경": kind,
                "이전": _where(before),
                "새": _where(row),
            }
        )
    return pd.DataFrame(
        rows, columns=[EQUIPMENT_ID_COLUMN, PARENT_EQUIPMENT_COLUMN, "변경", "이전", "새"]
    )


def _parent_follows(
    before: Mapping[Any, Any],
    row: Mapping[Any, Any],
    *,
    origin: str,
    unit_id: str,
    groups: Mapping[str, str],
) -> bool:
    """이 행의 Main 설비 차이가 이름 바꿈으로 설명되는가 — 그 묶음 이름을 바꿨거나(지금 이름 →
    저장본 이름), 자기 설비명을 Main 설비로 적은 행의 설비명을 바꿔 Main 설비가 따라갔거나."""
    was = _comparable(before.get(PARENT_EQUIPMENT_COLUMN))
    now = _comparable(row.get(PARENT_EQUIPMENT_COLUMN))
    if not was or not now:
        return False
    return groups.get(now) == was or (was == origin and now == unit_id)


def other_change_count(
    saved: pd.DataFrame, buffer: pd.DataFrame, renames: PendingRenames | None = None
) -> int:
    """배치 칸이 아닌 차이가 있는 호기 수(RawData 의 저장 안 한 다른 편집). 지운 호기도 센다.
    이름 바꿈(`renames`)으로 설명되는 설비명·Main 설비 차이는 세지 않는다."""
    saved_rows = {
        str(row[EQUIPMENT_ID_COLUMN]).strip(): row for row in saved.to_dict(orient="records")
    }
    buffer_rows = {
        str(row[EQUIPMENT_ID_COLUMN]).strip(): row for row in buffer.to_dict(orient="records")
    }
    live = live_renames(renames, saved, buffer)
    others = [
        column
        for column in buffer.columns
        if column not in PLACE_COLUMNS and column != EQUIPMENT_ID_COLUMN
    ]
    count = len(saved_rows.keys() - buffer_rows.keys() - set(live.units.values()))
    for unit_id, row in buffer_rows.items():
        origin = live.units.get(unit_id, unit_id)
        before = saved_rows.get(origin)
        if before is None:
            if _text(row.get("호기이력")) != NEW_UNIT_HISTORY:
                count += 1
            continue
        differs = [c for c in others if _comparable(before.get(c)) != _comparable(row.get(c))]
        if PARENT_EQUIPMENT_COLUMN in differs and _parent_follows(
            before, row, origin=origin, unit_id=unit_id, groups=live.groups
        ):
            differs.remove(PARENT_EQUIPMENT_COLUMN)
        if differs:
            count += 1
    return count


def table_changed(saved: pd.DataFrame, buffer: pd.DataFrame) -> bool:
    """두 표의 내용이 다른가(값의 형 차이는 무시). 설비 마스터 밖의 RawData 편집(기존 보유대수·
    비가동 일정)을 알린다. 「다르다」로 잘못 보면 메모 칸이 더 뜰 뿐이라 행 순서도 견준다."""
    if list(saved.columns) != list(buffer.columns) or len(saved) != len(buffer):
        return True
    rows = [
        [tuple(_comparable(value) for value in row) for row in frame.itertuples(index=False)]
        for frame in (saved, buffer)
    ]
    return rows[0] != rows[1]


def unsaved_unit_ids(
    saved: pd.DataFrame,
    buffer: pd.DataFrame,
    floor: FloorKey,
    renames: PendingRenames | None = None,
) -> tuple[set[str], set[str]]:
    """(저장본에 없는 새 호기, 다른 층에서 이 층으로 옮겨 왔지만 아직 저장하지 않은 호기). 이름만
    바꾼 호기(`renames`)는 새 호기가 아니다 — 저장본의 옛 이름 행과 견준다."""
    saved_floor = {
        str(row[EQUIPMENT_ID_COLUMN]).strip(): (
            _comparable(row.get("동")),
            _comparable(row.get("층")),
        )
        for row in saved.to_dict(orient="records")
    }
    origins = live_renames(renames, saved, buffer).units
    here = (floor[0], floor[1])
    new_ids: set[str] = set()
    arrived: set[str] = set()
    for row in buffer.to_dict(orient="records"):
        unit_id = str(row[EQUIPMENT_ID_COLUMN]).strip()
        before = saved_floor.get(origins.get(unit_id, unit_id))
        if before is None:
            new_ids.add(unit_id)
            continue
        now = (_comparable(row.get("동")), _comparable(row.get("층")))
        if now == here and before != here and "" not in before:
            arrived.add(unit_id)
    return new_ids, arrived


def viewer_items(
    located: pd.DataFrame, *, looks: Mapping[str, Mapping[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """층 상세 뷰어(편집기와 같은 도면, 보기 전용)에 보낼 저장본 호기. 좌표·크기가 다 있는 행만
    받는다. `detail` 은 풍선·선택 줄에 붙는 공정과 운영 비가동이다. `looks` 는 설비명마다 얹을
    면·글자·경계 날짜(`fill`·`ink`·`realFrom` … — `components/space_layout.unit_appearance`)다. 층의
    세는 행 전체로 범례 대수와 함께 한 번 구한 것을 받으므로 `located` 밖의 설비명이 있어도 된다.

    층 상세는 페이더를 놓을 때마다 이 목록을 다시 만든다(1천여 행) — 행마다 Series 를 만드는
    `iterrows` 대신 칸을 목록으로 꺼내 돈다."""
    found = looks or {}

    def column(name: str, *, required: bool = False) -> list[Any]:
        if name in located.columns or required:
            return located[name].tolist()
        return [None] * len(located)

    items: list[dict[str, Any]] = []
    rows = zip(
        column(EQUIPMENT_ID_COLUMN, required=True),
        column("상태"),
        column("X좌표", required=True),
        column("Y좌표", required=True),
        column("Xsize", required=True),
        column("Ysize", required=True),
        column("공정소분류"),
        column("비가동유형"),
        _parents(located).tolist(),
        strict=True,
    )
    for name, stage, x, y, width, height, process_value, downtime_value, parent in rows:
        process = _text(process_value).strip()
        downtime = _text(downtime_value).strip()
        unit_id = str(name).strip()
        items.append(
            {
                **found.get(unit_id, {}),
                "id": unit_id,
                "label": unit_id,
                "stage": _text(stage),
                "x": finite_or_none(x),
                "y": finite_or_none(y),
                "w": finite_or_none(width),
                "h": finite_or_none(height),
                "placed": True,
                "group": str(parent) if _present(parent) else None,
                "detail": " · ".join(
                    part for part in (process, f"비가동 {downtime}" if downtime else "") if part
                ),
            }
        )
    return items
