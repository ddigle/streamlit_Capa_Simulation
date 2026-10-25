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

import numpy as np
import pandas as pd

from capa_simulation.services.equipment_contract import (
    ARRIVAL_DATE_COLUMN,
    EQUIPMENT_ID_COLUMN,
    LAYOUT_REFLECTED_COLUMN,
    PARENT_EQUIPMENT_COLUMN,
    QUAL_CONFIRMATION_STATUSES,
    QUAL_DATE_COLUMN,
    QUAL_STATUS_COLUMN,
    SCENARIO_LAYOUT_COLUMNS,
    STORAGE_FLAG_COLUMN,
)
from capa_simulation.services.equipment_units import unit_keys
from capa_simulation.services.fab_layout import floor_label
from capa_simulation.services.floor_layout_mark import (
    GROUP_LABEL_POSITIONS,
    FloorLayoutMark,
    GroupLabels,
    prepare_floor_layout_marks,
)
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
# 편집기가 바꾸는 칸(계약의 배치 일곱 칸 — 가정 설비 시나리오의 배치 차이도 이 일곱 칸이다). 나머지
# 칸이 다르면 설비 마스터의 다른 편집이다. 이름 바꿈(설비명·Main 설비)은 이 칸이 아니라
# `PendingRenames` 가 가른다.
PLACE_COLUMNS: Final = SCENARIO_LAYOUT_COLUMNS
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
    # 묶음과 함께 옮겨진 숨은 모듈(`EditorInputs.ghosts`)의 새 X·Y·크기. 같은 층이고 레이아웃표시는
    # 그대로 둔다(`apply_layout_edits`).
    hidden_moves: tuple[UnitChange, ...] = ()
    # 이 층에 남는 모듈 묶음의 Main 설비명 위치 — (편집기에 실린 **옛** Main 설비 이름, 위치).
    # 적용값에 `groupLabels` 가 없으면 None(위치는 그대로, 이름 바꿈만 따라간다 —
    # `next_group_labels`).
    group_labels: tuple[tuple[str, str], ...] | None = None

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
    새 호기」로 읽힌다(변경 목록에서 빠지고 설비 마스터의 다른 편집 2건으로 세어진다)."""

    units: Mapping[str, str] = field(default_factory=dict)
    groups: Mapping[str, str] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.units or self.groups)


@dataclass(frozen=True)
class ReservedNames:
    """편집본 설비 마스터에 없지만 새 설비명(새 호기·이름 바꿈)으로 쓸 수 없는 이름
    (`reserved_names`).

    - `deleted`: 저장본에 있는데 설비 마스터에서 지우고 아직 저장하지 않은 설비명. 다른 호기가 그
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
    # 숨은 모듈 — 편집기에 실린 모듈 묶음의 형제 가운데 이 층에 상자(X·Y·크기)가 있지만 도면 대상이
    # 아닌 행(레이아웃표시 N·도면 이탈 …). 그리지 않지만 묶음 바둑판의 제 칸을 차지하고 묶음과 함께
    # 옮겨진다(``{"id", "group", "x", "y", "w", "h"}``).
    ghosts: tuple[dict[str, Any], ...] = ()


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
    - 숨은 모듈(`ghosts`): 그런 호기 가운데 보내는 호기와 Main 설비가 같은 것. 묶음 바둑판의 칸
      수·자리에 들어가(빈 칸으로 남는다) 보이는 모듈이 제 칸을 지키고, 묶음을 옮기면 함께 옮겨진다.
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
    sent_groups = {item["group"] for item in items if item["group"]}
    ghostly = hidden & parents.isin(sent_groups).fillna(False).astype(bool)
    ghosts = tuple(
        {
            "id": str(row[EQUIPMENT_ID_COLUMN]).strip(),
            "group": str(row["_parent"]),
            "x": finite_or_none(row["X좌표"]),
            "y": finite_or_none(row["Y좌표"]),
            "w": finite_or_none(row["Xsize"]),
            "h": finite_or_none(row["Ysize"]),
        }
        for row in status.loc[ghostly].assign(_parent=parents[ghostly]).to_dict(orient="records")
    )
    return EditorInputs(
        items=tuple(items),
        reserved_extent=reserved,
        default_size=default_size,
        unplaced_floorless=unplaced_floorless,
        ghosts=ghosts,
    )


def new_unit_options(master: pd.DataFrame) -> dict[str, Any]:
    """편집기의 호기 추가 폼 선택지. 크기 힌트는 공정소분류별 가운데 크기(모듈 행 제외). 서랍에서
    크기 없는 호기를 놓을 때 빌릴 앞 3자리 크기(`prefix_sizes`)와 그 종류를 가를 모듈 묶음의 Main
    설비(`module_parents`)도 함께 보낸다."""

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
        "prefixSizes": prefix_sizes(master),
        "moduleParents": sorted(module_parents(master)),
    }


def module_group_rows(master: pd.DataFrame) -> pd.Series:
    """행마다 그 행이 든 Main 설비 모듈 묶음(Main 설비가 같은 행이 표 전체에서 둘 이상)의 Main 설비,
    묶음 밖이면 NA. 모듈 묶음 판정의 한 곳이다 — 저장 전 바둑판 검사(`module_layout_violations`)와
    가정 설비 시나리오 배치 차이의 묶음 통째 규칙(`services/layout_overlay.py`)이 같이 쓴다."""
    parents = _parents(master)
    return parents.where(parents.map(parents.value_counts()).fillna(0).ge(2).astype(bool))


def _module_rows(master: pd.DataFrame) -> pd.Series:
    """행마다 Main 설비 모듈 묶음의 모듈인가 — Main 설비가 같은 행이 표 전체에서 둘 이상."""
    return module_group_rows(master).notna()


def module_parents(master: pd.DataFrame) -> set[str]:
    """Main 설비 모듈 묶음(행 둘 이상)의 Main 설비. 서랍 크기 불러오기의 종류(모듈/호기)를 편집기가
    `prefix_sizes` 와 같은 기준으로 가르도록 함께 보낸다 — 형제가 편집기에 실리지 않은 모듈도
    모듈이다."""
    parents = _parents(master)
    return {str(name) for name in parents.loc[_module_rows(master)].dropna().unique()}


# 서랍에서 크기 없는 호기를 놓을 때 크기를 빌릴 설비를 고르는 열쇠 — 설비명 앞 몇 글자
# (2026-10-23 사용자 결정). 편집기 JS(`editor.js` 의 `// <edit-tools>` 구획 `namePrefix`)가 같은
# 규칙이다.
NAME_PREFIX_LENGTH: Final = 3


def name_prefix(name: object) -> str:
    """설비명 앞 3자리 — 앞뒤 공백을 걷은 첫 세 글자(대소문자 그대로, 글자는 코드 포인트).
    세 글자보다 짧거나 비면 ``""``(빌리지 않는다)."""
    if not _present(name):
        return ""
    text = str(name).strip()
    return text[:NAME_PREFIX_LENGTH] if len(text) >= NAME_PREFIX_LENGTH else ""


def prefix_sizes(master: pd.DataFrame) -> dict[str, dict[str, dict[str, Any]]]:
    """설비명 앞 3자리 → 그 앞 3자리이고 크기(Xsize·Ysize 가 0 보다 큼)가 있는 설비 가운데
    설비명 자연 정렬(`natural_name_key`)이 가장 뒤인 설비의 ``{"name", "w", "h"}``.

    배치 편집기 서랍에서 크기 없는 호기를 놓을 때, 이번 편집에서 놓은 같은 앞 3자리 설비가
    없으면 이 크기를 빌린다(없으면 이 층 가운데 크기 — 2026-10-23 사용자 결정). ``master`` 는
    편집본(저장본 + 저장 안 한 편집)이다. Main 설비 모듈 묶음(Main 설비가 같은 행이 둘 이상)의
    모듈(``"module"``)과 그 밖의 설비(``"unit"``)는 따로 고른다 — 모듈 크기는 묶음 범위의 한
    칸이라 서로 빌리지 않는다."""
    out: dict[str, dict[str, dict[str, Any]]] = {"unit": {}, "module": {}}
    if master.empty:
        return out
    names = master[EQUIPMENT_ID_COLUMN].astype("string").str.strip()
    widths = pd.to_numeric(master["Xsize"], errors="coerce")
    heights = pd.to_numeric(master["Ysize"], errors="coerce")
    modules = _module_rows(master)
    best: dict[tuple[str, str], tuple[Any, str, float, float]] = {}
    for name, raw_w, raw_h, module in zip(names, widths, heights, modules, strict=True):
        prefix = name_prefix(name)
        width, height = finite_or_none(raw_w), finite_or_none(raw_h)
        if not prefix or width is None or height is None or width <= 0 or height <= 0:
            continue
        kind = "module" if bool(module) else "unit"
        key = natural_name_key(str(name))
        current = best.get((kind, prefix))
        if current is None or key > current[0]:
            best[(kind, prefix)] = (key, str(name), width, height)
    for (kind, prefix), (_, name, width, height) in sorted(best.items()):
        out[kind][prefix] = {
            "name": name,
            "w": rounded_to_canvas(width),
            "h": rounded_to_canvas(height),
        }
    return out


# ------------------------------------------------------------------ 모듈 묶음 바둑판

# 모듈 묶음 = 이 편집기에 실린 호기와 숨은 모듈(`EditorInputs.ghosts`) 가운데 Main 설비가 같은 것이
# 둘 이상인 묶음(2026-10-23 사용자 요청). 사람이 고치는 것은 묶음 범위(이 층 도면에 선 모듈의 바깥
# 상자)뿐이고, 안의 모듈은 범위를 바둑판으로 똑같이 나눈 칸에 자동으로 선다. 칸 자리는 지금
# 자리를 지킨다(`assign_module_cells`) — 새로 놓을 때만 설비명 자연 정렬이다
# (`tile_module_group`). 편집기 JS(`editor.js` 의 `// <module-tiling>` 구획)가 같은 규칙이고
# `tests/test_space_module_group.py` 가 node 로 둘을 대조한다 — 한쪽을 고치면 다른 쪽도 고친다.
_TICKS_PER_UNIT: Final = 10**CANVAS_DECIMALS
_NAME_TOKEN: Final = re.compile(r"[0-9]+|[^0-9]+")
ModuleBox = tuple[float, float, float, float]
_Ticks = tuple[int, int, int, int]
# 이만큼까지의 모듈은 가로 한 줄로 선다(2026-10-23 사용자 답 「2모듈이거나 3모듈이면 가로로 일렬
# 배치」). 그보다 많으면 거의 정사각 격자다.
ONE_ROW_MODULES: Final = 3


def module_grid(count: int) -> tuple[int, int]:
    """모듈 수 → (열, 행). 셋까지는 가로 한 줄(열 = n, 행 = 1 — 둘이면 2×1, 셋이면 3×1)이고,
    넷부터는 거의 정사각 격자다(열 = ⌈√n⌉, 행 = ⌈n ÷ 열⌉ — 넷이면 2×2, 다섯이면 3×2)."""
    if count <= ONE_ROW_MODULES:
        return max(1, count), 1
    cols = math.ceil(math.sqrt(count))
    return cols, math.ceil(count / cols)


def default_group_label(count: int) -> str:
    """Main 설비명 위치를 고른 적이 없는(층 위치 행이 없는) 모듈 묶음의 위치. 한 줄 묶음
    (`module_grid` 의 행이 1 — 모듈 2·3)은 범위 바깥 위다 — 가운데는 가운데 모듈 이름표와 겹친다
    (2026-10-24 결정 (e)). 두 줄 이상(모듈 넷부터)은 범위 정가운데(모듈 꼭짓점이 만나는 자리)다.
    편집기 JS(`editor.js` 의 `// <module-tiling>` 구획 `groupLabelDefault`)가 같은 규칙이다."""
    return GROUP_LABEL_POSITIONS[1] if module_grid(count)[1] == 1 else GROUP_LABEL_POSITIONS[0]


def natural_name_key(name: str) -> tuple[tuple[tuple[int, int, str], ...], str]:
    """설비명 자연 정렬 열쇠(…12A, 12B, 12C, 12D — `EQ2` 가 `EQ10` 앞). 숫자 덩이(ASCII 0-9)는
    수로, 나머지 덩이는 소문자로 견주고, 덩이가 같으면 짧은 쪽이 앞이며, 그래도 같으면 글자 그대로
    견준다. 글자는 코드 포인트로 견준다(JS 도 `Array.from` 으로 같게 본다)."""
    tokens = tuple(
        (0, int(token), "") if "0" <= token[0] <= "9" else (1, 0, token.lower())
        for token in _NAME_TOKEN.findall(name)
    )
    return tokens, name


def _ticks(value: float) -> int:
    """좌표·치수를 저장 정밀도 눈금(정수)으로 — 반올림은 JS 와 같은 `⌊v × 10^자리 + 0.5⌋`."""
    return math.floor(value * _TICKS_PER_UNIT + 0.5)


def _cell_ticks(box: _Ticks, count: int) -> list[_Ticks]:
    """눈금 범위를 `module_grid(count)` 열×행으로 **똑같이** 나눈 칸(칸 번호 차례 — 왼→오, 위→아래).

    칸 폭·높이는 범위 ÷ 열(행)의 내림이고 마지막 열(오른쪽)·마지막 행(맨 아래)이 나머지를 받는다 —
    칸들이 범위를 틈·겹침 없이 꼭 채운다. 범위가 칸마다 한 눈금보다 작으면 오른쪽·위로 넓힌다."""
    cols, rows = module_grid(count)
    left, bottom = box[0], box[1]
    width, height = max(box[2], cols), max(box[3], rows)
    cell_w, cell_h = width // cols, height // rows
    last_w, last_h = width - cell_w * (cols - 1), height - cell_h * (rows - 1)
    cells: list[_Ticks] = []
    for row in range(rows):
        # 행은 위(0)에서 센다. 맨 아래 행이 범위 바닥에 서고 그 위로 칸 높이씩 쌓인다.
        y = bottom if row == rows - 1 else bottom + last_h + (rows - 2 - row) * cell_h
        h = last_h if row == rows - 1 else cell_h
        for col in range(cols):
            w = last_w if col == cols - 1 else cell_w
            cells.append((left + col * cell_w, y, w, h))
    return cells


def _value_box(ticks: _Ticks) -> ModuleBox:
    scale = _TICKS_PER_UNIT
    return (ticks[0] / scale, ticks[1] / scale, ticks[2] / scale, ticks[3] / scale)


def _tick_box(box: ModuleBox) -> _Ticks:
    return _ticks(box[0]), _ticks(box[1]), _ticks(box[2]), _ticks(box[3])


def _outer_ticks(boxes: Collection[_Ticks]) -> _Ticks:
    left = min(box[0] for box in boxes)
    bottom = min(box[1] for box in boxes)
    right = max(box[0] + box[2] for box in boxes)
    top = max(box[1] + box[3] for box in boxes)
    return left, bottom, right - left, top - bottom


def module_cells(box: ModuleBox, count: int) -> list[ModuleBox]:
    """묶음 범위 `box`(X, Y, 폭, 높이)를 `count` 칸 바둑판으로 똑같이 나눈 칸(칸 번호 차례 —
    왼→오, 위→아래). 칸 수는 열×행이라 `count` 보다 많을 수 있다(남는 칸은 빈다)."""
    return [_value_box(cell) for cell in _cell_ticks(_tick_box(box), count)]


def tile_module_group(box: ModuleBox, names: Sequence[str]) -> dict[str, ModuleBox]:
    """묶음을 **새로** 놓을 때(서랍에서 놓기)의 자리 — 범위 `box` 를 `module_grid` 열×행으로
    똑같이 나눈 칸에 설비명 자연 정렬(`natural_name_key`) 차례로 모듈을 하나씩 둔다(이름 → 칸).
    첫 모듈이 왼쪽 위다. 칸이 남으면(모듈 다섯 → 3×2) 마지막 칸이 빈다."""
    if not names:
        return {}
    cells = module_cells(box, len(names))
    return {name: cells[index] for index, name in enumerate(sorted(names, key=natural_name_key))}


def _assign_cell_ticks(boxes: Mapping[str, _Ticks | None]) -> dict[str, int]:
    """`assign_module_cells` 의 눈금 본(이름 → 칸 번호)."""
    order = sorted(boxes, key=natural_name_key)
    boxed = [name for name in order if boxes[name] is not None]
    used: set[int] = set()
    slots: dict[str, int] = {}
    if boxed:
        cells = _cell_ticks(_outer_ticks([cast(_Ticks, boxes[name]) for name in boxed]), len(order))
        pairs = []
        for index, name in enumerate(boxed):
            x, y, w, h = cast(_Ticks, boxes[name])
            for number, (cx, cy, cw, ch) in enumerate(cells):
                dx, dy = (2 * x + w) - (2 * cx + cw), (2 * y + h) - (2 * cy + ch)
                pairs.append((dx * dx + dy * dy, index, number))
        for _, index, number in sorted(pairs):
            if boxed[index] in slots or number in used:
                continue
            slots[boxed[index]] = number
            used.add(number)
    cols, rows = module_grid(len(order))
    free = (number for number in range(cols * rows) if number not in used)
    for name in order:
        if name not in slots:
            slots[name] = next(free)
    return slots


def assign_module_cells(mods: Mapping[str, ModuleBox | None]) -> dict[str, int]:
    """묶음 모듈의 칸 배정(이름 → 칸 번호, `module_cells` 차례) — **지금 자리를 지킨다**.

    상자가 있는 모듈의 바깥 상자를 모듈 수만큼의 바둑판으로 나눠, 상자 중심과 칸 중심의 거리
    (눈금 제곱)가 가까운 짝부터 묶는다 — 같으면 설비명 자연 정렬 앞 모듈, 앞 칸이 먼저다. 이미
    바둑판이면 모듈마다 제 칸이다(차례가 이름순이 아니어도). 상자가 없는 모듈(좌표 없는 형제)은
    남은 칸을 자연 정렬 차례로 받는다."""
    return _assign_cell_ticks(
        {name: None if box is None else _tick_box(box) for name, box in mods.items()}
    )


def _deviation_ticks(boxes: Mapping[str, _Ticks]) -> tuple[int, dict[str, _Ticks]]:
    """바깥 상자를 모듈 수 바둑판으로 나눈 칸(지금 자리 배정)과의 가장 큰 눈금 차, 그리고 그 칸."""
    cells = _cell_ticks(_outer_ticks(list(boxes.values())), len(boxes))
    slots = _assign_cell_ticks(dict(boxes))
    laid = {name: cells[slots[name]] for name in boxes}
    worst = max(
        abs(a - b) for name, box in boxes.items() for a, b in zip(box, laid[name], strict=True)
    )
    return worst, laid


def module_tile_deviation(mods: Mapping[str, ModuleBox | None]) -> int | None:
    """묶음이 바둑판에서 얼마나 벗어났나(눈금) — 모두 상자가 있을 때, 바깥 상자를 모듈 수
    바둑판으로 나눈 칸(지금 자리 배정 `assign_module_cells`)과의 가장 큰 차. 0 이면 바둑판
    그대로다. 상자 없는 모듈이 있으면 None."""
    if not mods or any(box is None for box in mods.values()):
        return None
    return _deviation_ticks({name: _tick_box(cast(ModuleBox, box)) for name, box in mods.items()})[
        0
    ]


def _module_groups(
    editor_items: Sequence[Mapping[str, Any]], ghosts: Sequence[Mapping[str, Any]]
) -> dict[str, tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]]:
    """편집기에 실린 호기와 숨은 모듈을 Main 설비로 묶어, 둘을 합쳐 모듈이 둘 이상이고 실린 호기가
    하나라도 있는 묶음만(Main 설비 → (실린 호기들, 숨은 모듈들))."""
    groups: dict[str, tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]] = {}
    for item in editor_items:
        group = item.get("group")
        if isinstance(group, str) and group:
            groups.setdefault(group, ([], []))[0].append(item)
    for ghost in ghosts:
        group = ghost.get("group")
        if isinstance(group, str) and group in groups:
            groups[group][1].append(ghost)
    return {
        group: members
        for group, members in groups.items()
        if len(members[0]) + len(members[1]) >= 2
    }


def _box_ticks(values: Sequence[float | None]) -> _Ticks | None:
    """(X, Y, 폭, 높이) → 눈금 넷. 하나라도 없으면 None."""
    x, y, w, h = values
    if x is None or y is None or w is None or h is None:
        return None
    return _ticks(x), _ticks(y), _ticks(w), _ticks(h)


def _sent_box(item: Mapping[str, Any]) -> _Ticks | None:
    return _box_ticks([finite_or_none(item.get(key)) for key in ("x", "y", "w", "h")])


# 브라우저 값이 바둑판 칸과 이만큼(눈금)까지 다르면 바로잡고, 더 다르면 거부한다 — 반올림 한 끝
# 차이로 적용이 막히지 않게 하되, 모듈 하나만 옮기거나 키운 값을 묶음 범위를 넓혀 받아들이지
# 않는다.
_TILE_TOLERANCE: Final = 1


def _regrid_module_groups(
    changes: Sequence[UnitChange],
    editor_items: Sequence[Mapping[str, Any]],
    bounds: CanvasSize,
    ghosts: Sequence[Mapping[str, Any]] = (),
    ghost_moves: Mapping[str, ModuleBox] | None = None,
) -> tuple[list[UnitChange], list[UnitChange]]:
    """이번 적용에서 이 층 도면에 놓이거나 자리·크기가 바뀐 모듈 묶음이 묶음 범위의 바둑판
    그대로인지 보고 정본 칸 값으로 맞춘다(바뀐 호기 목록, 숨은 모듈의 새 자리).

    적용 뒤 묶음의 모든 모듈(바뀐 것은 바뀐 값, 아닌 것은 편집기에 보낸 값, 숨은 모듈은 함께 옮겨
    온 값)의 바깥 상자를 범위로 삼아 칸을 나누고, 모듈마다 지금 자리에 가까운 칸
    (`assign_module_cells`)과 견준다. 차이가 모듈마다 `_TILE_TOLERANCE` 눈금 안이면(반올림 한 끝 등)
    **칸 값으로 바로잡고**, 더 크면 모듈 하나만 옮기거나 키운 값이라 `ValueError` 다. 바뀐 모듈이
    없는 묶음(바둑판이 아닌 옛 묶음 포함)은 건드리지 않는다. 묶음째 트레이로 빼거나 다른 층으로
    보낸 묶음도 그대로다(숨은 모듈은 남는다). 한 묶음의 모듈이 갈라지면(일부만 빼거나 보내거나 좌표
    없는 형제가 안 놓임) 편집기가 막는 길이라 `ValueError` 다."""
    moved_ghosts = dict(ghost_moves or {})
    by_id = {change.unit_id: change for change in changes}
    fixed: dict[str, UnitChange] = {}
    added: list[UnitChange] = []
    hidden: list[UnitChange] = []
    for group, (items, hidden_rows) in _module_groups(editor_items, ghosts).items():
        ids = [str(item["id"]) for item in items]
        ghost_ids = [str(ghost["id"]) for ghost in hidden_rows]
        if not any(unit_id in by_id for unit_id in ids) and not any(
            ghost_id in moved_ghosts for ghost_id in ghost_ids
        ):
            continue
        before: dict[str, _Ticks | None] = {}
        finals: dict[str, _Ticks | None] = {}
        apart: list[str] = []
        for item, unit_id in zip(items, ids, strict=True):
            before[unit_id] = _sent_box(item) if bool(item.get("placed")) else None
            change = by_id.get(unit_id)
            if change is None:
                finals[unit_id] = before[unit_id]
            elif change.placed and change.move_to is None:
                finals[unit_id] = _box_ticks([change.x, change.y, change.w, change.h])
            else:
                finals[unit_id] = None
                apart.append(unit_id)
        if all(finals[unit_id] is None for unit_id in ids):
            # 묶음째 트레이로 빼거나 다른 층으로 보냈다 — 숨은 모듈은 보낸 자리 그대로다
            # (편집기 `restoreGhosts` 가 처음 자리로 되돌려 보낸다). 다른 층이면
            # `_harmonize_groups` 가 층을 맞춘다.
            if any(ghost_id in moved_ghosts for ghost_id in ghost_ids):
                raise ValueError(
                    f"Main 설비 {group} 의 숨은 모듈만 옮겨 왔습니다 — 묶음째 옮겨야 합니다."
                )
            continue
        if apart:
            raise ValueError(
                f"Main 설비 {group} 의 모듈은 묶음째 옮기거나 빼야 합니다 — "
                f"{', '.join(sorted(apart, key=natural_name_key))} 만 따로 왔습니다."
            )
        left_out = [unit_id for unit_id in ids if finals[unit_id] is None]
        if left_out:
            raise ValueError(
                f"Main 설비 {group} 의 모듈은 묶음째 옮기거나 빼야 합니다 — "
                f"{', '.join(sorted(left_out, key=natural_name_key))} 가 묶음 범위에 놓이지 "
                "않았습니다."
            )
        for ghost, ghost_id in zip(hidden_rows, ghost_ids, strict=True):
            before[ghost_id] = _sent_box(ghost)
            moved = moved_ghosts.get(ghost_id)
            finals[ghost_id] = before[ghost_id] if moved is None else _tick_box(moved)
        boxes = {name: cast(_Ticks, box) for name, box in finals.items()}
        worst, laid = _deviation_ticks(boxes)
        if worst > _TILE_TOLERANCE:
            raise ValueError(
                f"Main 설비 {group} 의 모듈이 묶음 범위를 바둑판으로 나눈 칸에 서 있지 않습니다 — "
                "모듈 하나만 옮기거나 크기를 바꿀 수 없으니 묶음째 옮기거나 범위를 고치세요."
            )
        for name, cell in laid.items():
            x, y, w, h = _value_box(cell)
            if x + w > bounds[0] + 1e-9 or y + h > bounds[1] + 1e-9:
                raise ValueError(
                    f"Main 설비 {group} 의 묶음 범위가 편집 영역 {bounds[0]:g} × {bounds[1]:g} 를 "
                    "벗어났습니다."
                )
            tile = UnitChange(name, True, x, y, w, h, None)
            if name in by_id:
                fixed[name] = tile
            elif before[name] != cell:
                (hidden if name in ghost_ids else added).append(tile)
    return [fixed.get(change.unit_id, change) for change in changes] + added, hidden


def _parse_ghost_moves(
    raw_ghosts: object, ghosts: Sequence[Mapping[str, Any]], bounds: CanvasSize
) -> dict[str, ModuleBox]:
    """적용값의 `ghosts`(묶음과 함께 옮겨진 숨은 모듈 ``[{"id", "x", "y", "w", "h"}]``)를 읽는다.
    이번 편집기에 보낸 숨은 모듈만 받고, 값은 이 층 영역 안이어야 한다."""
    if raw_ghosts is None:
        return {}
    if not isinstance(raw_ghosts, list):
        raise ValueError("숨은 모듈 목록을 읽지 못했습니다.")
    known = {str(ghost["id"]) for ghost in ghosts}
    moves: dict[str, ModuleBox] = {}
    for raw in raw_ghosts:
        if not isinstance(raw, Mapping):
            raise ValueError("숨은 모듈 목록을 읽지 못했습니다.")
        unit_id = _text(raw.get("id")).strip()
        if unit_id not in known:
            raise ValueError(f"이 편집기에 없는 숨은 모듈입니다: {unit_id}")
        if unit_id in moves:
            raise ValueError(f"같은 숨은 모듈이 두 번 왔습니다: {unit_id}")
        values = [finite_or_none(raw.get(key)) for key in ("x", "y", "w", "h")]
        if any(value is None for value in values):
            raise ValueError(f"숨은 모듈 {unit_id} 의 좌표·크기를 읽지 못했습니다.")
        x, y, w, h = (rounded_to_canvas(cast(float, value)) for value in values)
        if x < 0 or y < 0 or w <= 0 or h <= 0:
            raise ValueError(f"숨은 모듈 {unit_id} 의 좌표·크기가 맞지 않습니다.")
        if x + w > bounds[0] + 1e-9 or y + h > bounds[1] + 1e-9:
            raise ValueError(
                f"숨은 모듈 {unit_id} 가 편집 영역 {bounds[0]:g} × {bounds[1]:g} 를 벗어났습니다."
            )
        moves[unit_id] = (x, y, w, h)
    return moves


# ------------------------------------------------------------------ 마스터 저장의 묶음 좌표·크기

# 모듈 묶음의 좌표·크기는 Space 배치 편집기에서 묶음 범위로만 고친다(2026-10-23 사용자 답 「막자」).
# 설비 마스터를 저장하는 길(설비 마스터 직접 편집·붙여넣기·CSV 업로드·일괄 삭제·Space 배치 저장 —
# 모두 `components/equipment_data_workspace.save_equipment_buffer`)은 저장 직전에
# `module_layout_violations` 로 저장본과 견줘, 모듈 좌표·크기가 바뀌었는데 바둑판이 아닌 묶음이
# 있으면 저장을 거부한다. 배치 편집기가 적용한 묶음은 적용 뒤 모양(`module_layouts`)을 세션에 두고
# 그 모양 그대로면 통과시킨다 — 편집기 결과는 `parse_editor_apply` 가 이미 같은 규칙으로 봤고, 숨은
# 모듈이 있는 묶음을 빼거나 다른 층으로 보낸 결과처럼 바둑판 칸이 비는 모양도 있다.
_COORDINATE_COLUMNS: Final = (*POSITION_COLUMNS, *SIZE_COLUMNS)
# 한 행의 좌표·크기 눈금(X좌표·Y좌표·Xsize·Ysize, 빈 칸·못 읽는 값은 None).
_RowTicks = tuple[int | None, int | None, int | None, int | None]
# 한 묶음의 모양 — 행마다 (설비명, 좌표·크기 눈금), 설비명 차례.
ModuleLayout = tuple[tuple[str, _RowTicks], ...]


def _row_ticks(frame: pd.DataFrame) -> dict[str, _RowTicks]:
    """설비명(앞뒤 공백 제거) → 좌표·크기 눈금. 반올림은 바둑판 눈금(`_ticks`)과 같다. 설비명이
    비거나 겹치는 행(저장 검증이 막는다)은 처음 것만 본다."""
    if frame.empty or EQUIPMENT_ID_COLUMN not in frame.columns:
        return {}
    numbers = (
        frame.reindex(columns=list(_COORDINATE_COLUMNS))
        .apply(pd.to_numeric, errors="coerce")
        .to_numpy(dtype="float64", na_value=np.nan)
    )
    finite = np.isfinite(numbers)
    scaled = np.floor(np.where(finite, numbers, 0.0) * _TICKS_PER_UNIT + 0.5)
    names = frame[EQUIPMENT_ID_COLUMN].astype("string").str.strip()
    out: dict[str, _RowTicks] = {}
    for name, values, oks in zip(names, scaled.tolist(), finite.tolist(), strict=True):
        if pd.isna(name) or not name or str(name) in out:
            continue
        x, y, w, h = (int(value) if ok else None for value, ok in zip(values, oks, strict=True))
        out[str(name)] = (x, y, w, h)
    return out


def _equipment_names(frame: pd.DataFrame) -> pd.Series:
    """행마다 설비명(앞뒤 공백 제거)."""
    return frame[EQUIPMENT_ID_COLUMN].astype("string").str.strip()


def _module_rows_by_group(master: pd.DataFrame) -> dict[str, list[tuple[str, _RowTicks]]]:
    """Main 설비 모듈 묶음(Main 설비 행 둘 이상) → 그 행들의 (설비명, 좌표·크기 눈금). 눈금은
    묶음 행만 읽는다 — 저장 전 검사가 회차마다 돌아 마스터 전체를 훑지 않는다."""
    if master.empty or EQUIPMENT_ID_COLUMN not in master.columns:
        return {}
    parents = module_group_rows(master)
    member = parents.notna().to_numpy(dtype=bool)
    if not member.any():
        return {}
    rows = master[member]
    ticks = _row_ticks(rows)
    groups: dict[str, list[tuple[str, _RowTicks]]] = {}
    for name, parent in zip(_equipment_names(rows), parents[member], strict=True):
        if pd.isna(name) or str(name) not in ticks:
            continue
        groups.setdefault(str(parent), []).append((str(name), ticks[str(name)]))
    return {group: items for group, items in groups.items() if len(items) >= 2}


def _layout_of(rows: Sequence[tuple[str, _RowTicks]]) -> ModuleLayout:
    return tuple(sorted(rows, key=lambda row: row[0]))


def module_layouts(master: pd.DataFrame, groups: Collection[str]) -> dict[str, ModuleLayout]:
    """`groups` 가운데 `master` 에서 모듈 묶음(Main 설비 행 둘 이상)인 것의 모양. 배치 편집기 적용
    뒤 그 적용이 옮기거나 빼거나 보낸 묶음의 모양을 세션에 두면, 저장 검사
    (`module_layout_violations`)가 그 모양 그대로인 묶음을 편집기 결과로 보고 통과시킨다."""
    rows = _module_rows_by_group(master)
    return {group: _layout_of(rows[group]) for group in groups if group in rows}


def _placed_ticks(row: _RowTicks) -> bool:
    return row[0] is not None and row[1] is not None


def _vanished_rows(
    saved: pd.DataFrame, saved_names: pd.Series, candidate: pd.DataFrame, renames: Mapping[str, str]
) -> dict[_RowTicks, int]:
    """저장본에 있었는데 후보에 없는 행의 좌표·크기 눈금 → 행 수. 설비 마스터에서 이름만 바꾼 행이
    바뀐 행으로 읽히지 않게 같은 값과 한 번씩 짝짓는다 — 저장본에 없는 묶음 행이 있을 때만
    구한다."""
    present = {renames.get(str(name), str(name)) for name in _equipment_names(candidate).dropna()}
    gone = saved[(~saved_names.isin(present) & saved_names.notna()).to_numpy(dtype=bool)]
    counts: dict[_RowTicks, int] = {}
    for row in _row_ticks(gone).values():
        if any(value is not None for value in row):
            counts[row] = counts.get(row, 0) + 1
    return counts


def module_layout_violations(
    saved: pd.DataFrame,
    candidate: pd.DataFrame,
    *,
    renames: Mapping[str, str] | None = None,
    approved: Mapping[str, ModuleLayout] | None = None,
) -> list[str]:
    """설비 마스터 저장 후보 `candidate` 에서 모듈 좌표·크기가 저장본 `saved` 와 달라졌는데 묶음
    범위의 바둑판이 아닌 Main 설비 묶음(설비명 자연 정렬). 비면 저장해도 된다.

    - **바뀐 묶음**: 묶음 행 하나라도 X좌표·Y좌표·Xsize·Ysize 가 저장본의 같은 설비명(`renames` —
      지금 이름 → 저장본 이름, Space 에서 바꾼 저장 안 한 이름)과 다르다. 저장본에 없는 설비명은
      좌표·크기가 하나라도 있으면 바뀐 것이다 — 다만 저장본에서 사라진 행과 값이 같으면 설비
      마스터에서 이름만 바꾼 행으로 보고 바뀌지 않은 것이다. 행을 묶음에 넣거나 빼는 편집(Main 설비
      칸)만으로는 바뀌지 않는다(그 행의 좌표·크기가 그대로면).
    - 바뀌지 않은 묶음(바둑판이 아닌 옛 묶음 포함)은 보지 않는다. `approved`(배치 편집기가 적용한
      묶음 → 적용 뒤 모양, `module_layouts`)와 모양이 같은 묶음도 보지 않는다.
    - 바뀐 묶음은 좌표가 있는 행이 하나도 없거나(묶음째 미배치), 좌표가 있던 행이 좌표를 잃지
      않았고 좌표가 있는 행이 모두 크기를 갖고 그 바깥 상자를 행 수 바둑판으로 나눈 칸
      (`assign_module_cells` 배정)과 모두 한 눈금(`_TILE_TOLERANCE`) 안이어야 한다 — 배치 편집기
      적용의 서버 판정과 같다. 좌표 없는 형제는 칸 수에 넣지 않는다(편집기가 묶음을 처음 옮길 때
      놓는다)."""
    accepted = approved or {}
    groups = {
        group: rows
        for group, rows in _module_rows_by_group(candidate).items()
        if accepted.get(group) != _layout_of(rows)
    }
    if not groups:
        return []
    mapping = renames or {}
    # 저장본은 묶음 행의 옛 이름만 읽는다.
    saved_names = (
        _equipment_names(saved)
        if EQUIPMENT_ID_COLUMN in saved.columns
        else pd.Series(dtype="string", index=saved.index)
    )
    wanted = {mapping.get(name, name) for rows in groups.values() for name, _ in rows}
    before = _row_ticks(saved[saved_names.isin(wanted).to_numpy(dtype=bool)])
    vanished: dict[_RowTicks, int] | None = None
    violations: list[str] = []
    for group, rows in groups.items():
        changed = lost = False
        for name, row in rows:
            old = before.get(mapping.get(name, name))
            if old is None:
                if all(value is None for value in row):
                    continue
                if vanished is None:
                    vanished = _vanished_rows(saved, saved_names, candidate, mapping)
                if vanished.get(row, 0) > 0:
                    vanished[row] -= 1
                    continue
                changed = True
            elif old != row:
                changed = True
                lost = lost or (_placed_ticks(old) and not _placed_ticks(row))
        if not changed:
            continue
        placed = {name: row for name, row in rows if _placed_ticks(row)}
        if not placed:
            continue
        if lost or any(None in row for row in placed.values()):
            violations.append(group)
            continue
        boxes = {name: cast(_Ticks, row) for name, row in placed.items()}
        if _deviation_ticks(boxes)[0] > _TILE_TOLERANCE:
            violations.append(group)
    return sorted(violations, key=natural_name_key)


def module_layout_message(groups: Sequence[str]) -> str:
    """`module_layout_violations` 가 찾은 묶음으로 저장을 거부하는 문구 — 어느 묶음인지 말한다."""
    shown = ", ".join(groups[:3]) + (f" 외 {len(groups) - 3}개" if len(groups) > 3 else "")
    return (
        f"Main 설비 {shown} 의 모듈 좌표·크기는 Space 배치 편집기에서 묶음 범위로 고칩니다 — "
        "설비 마스터 표·붙여넣기·CSV 로 바꾼 X좌표·Y좌표·Xsize·Ysize 가 묶음 범위를 바둑판으로 "
        "나눈 칸이 아니어서 저장할 수 없습니다. 그 값을 저장본대로 되돌리거나, Space 현황 층 "
        "상세의 `배치 편집` 에서 그 묶음을 옮기거나 키워 다시 놓은 뒤 저장하세요."
    )


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
            "설비 마스터 편집본에 남아 있어 그 일정이 이 호기에 붙습니다 — 그 비가동 일정을 먼저 "
            "고치거나 지우세요"
        )
    for name in sorted(reserved.deleted):
        reasons[scalar_match_key(name)] = (
            f"저장본의 {with_object_particle(name)} 설비 마스터에서 지우고 아직 저장하지 "
            "않았습니다 — 그 이름을 이으면 저장 뒤 옛 호기의 이력과 섞이니, 지운 것을 먼저 "
            "저장하거나 되돌리세요"
        )
    return reasons


def _require_new_unit_name(
    unit_id: str,
    taken: Collection[str],
    parent_ids: Collection[str],
    reserved: Mapping[str, str],
) -> None:
    """새 호기 이름 규칙(Space 편집기 새 호기·설비 마스터 「새 호기」 칸 공용): 글자 규칙
    (`_require_name`), 설비명·Main 설비 이름과 대소문자·앞뒤 공백 무시 겹침, 쓸 수 없는 이름
    (`_reserved_reasons`)."""
    _require_name(unit_id, "새 호기 이름")
    parent = _same_name(unit_id, parent_ids)
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


def check_new_unit_name(
    name: str, *, master: pd.DataFrame, reserved: ReservedNames | None = None
) -> str | None:
    """새 호기 이름 하나를 보고 걸리면 그 까닭, 받으면 None — 설비 마스터 「새 호기」 칸(개편 단계
    C)이 Space 편집기 새 호기와 **같은 규칙**(`_require_new_unit_name`, 13장 D12 — 대소문자만 다른
    이름도 막음)으로 본다. `master` 는 편집본 설비 마스터(그 설비명·Main 설비 이름과 겹치지 않아야
    한다), `reserved` 는 `reserved_names`. 문구는 Space 거부 문구 그대로다."""
    unit_id = name.strip()
    try:
        _require_new_unit_name(
            unit_id,
            _name_set(master[EQUIPMENT_ID_COLUMN]) if EQUIPMENT_ID_COLUMN in master.columns else (),
            set(_parents(master).dropna().astype(str)),
            _reserved_reasons(reserved or ReservedNames()),
        )
    except ValueError as exc:
        return str(exc)
    return None


def _parse_created(
    unit_id: str,
    raw: Mapping[str, Any],
    taken: set[str],
    options: Mapping[str, Sequence[str]],
    reserved: Mapping[str, str],
) -> CreatedUnit:
    """새 호기 하나. 이름은 설비명·Main 설비와 대소문자·앞뒤 공백 무시로도 겹칠 수 없다(이름
    바꾸기와 같은 규칙)."""
    _require_new_unit_name(unit_id, taken, options.get("parentIds", ()), reserved)
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
    only: tuple[RenameKind, str] | None = None,
) -> None:
    """바꾼 뒤에도 설비명·Main 설비 이름이 겹치지 않는지 본다(설비 마스터 전체 — 다른 층·
    미배치·레이아웃 제외 포함). 겹침은 `scalar_match_key` 로 본다 — 대소문자·앞뒤 공백만 다른 두
    이름은 같은 이름이다. 저장 검증(`prepare_equipment_master`)은 글자 그대로 견주므로 그보다
    엄하다. 바꾼 뒤의 상태로 보므로 같은 적용에서 A→X·B→A 처럼 비운 이름을 다시 쓰는 것은 받는다.

    - 설비명을 바꾸면: 다른 설비명(새로 넣는 호기, 같은 적용의 다른 이름 바꿈 포함)·Main 설비
      이름과 겹칠 수 없다. 자기 대소문자만 바꾸는 것은 된다. 자기 설비명을 Main 설비로 적은 한
      행짜리 묶음은 Main 설비가 따라가므로 그 묶음과는 겹치지 않는다.
    - Main 설비 이름을 바꾸면: 어떤 설비명과도, 다른 Main 설비 이름과도 겹칠 수 없다.
    - 설비명은 편집본에 호기가 없어도 `reserved`(`_reserved_reasons` — 설비 마스터에서 지우고 저장
      안 한 저장본 이름, 설비 마스터에 없는 설비명을 가리키는 비가동 일정)와도 겹칠 수 없다.

    `only`(종류, 옛 이름)를 주면 그 바꿈 하나만 거부 대상으로 본다 — 나머지는 비우는 이름·차지하는
    이름으로만 셈에 든다(`check_unit_rename`).
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
        if only is not None and (change.kind, change.old) != only:
            continue
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


def check_unit_rename(
    old: str,
    new: str,
    *,
    master: pd.DataFrame,
    reserved: ReservedNames | None = None,
    renaming: Mapping[str, str] | None = None,
    group_renaming: Mapping[str, str] | None = None,
    created: Collection[str] = (),
) -> str | None:
    """설비명 하나의 이름 바꿈(옛 → 새)을 보고 걸리면 그 까닭, 받으면 None. 이름 바꾸기 자리(Space
    편집기 `parse_editor_apply`·설비 마스터 호기 상세)가 **모두 이 함수를 부른다**(G4·R2 — 이름
    바꾸기는 같은 호기) — 규칙을 더하면 모든 자리가 따라간다.

    - `master` 는 편집본 설비 마스터다. 바꾸기 **전**(옛 이름이 있다)이든 제출 **뒤**(이 바꿈과
      `renaming` 이 이미 들어 옛 이름이 없고 새 이름이 있다 — 비가동·Main 설비가 따라갔든
      아니든)든 받는다(`_names_before` 가 가른다). 제출 뒤 마스터에 새 이름이 두 행이면 다른
      호기와 겹친 것이다.
    - `renaming` 은 같은 제출의 다른 설비명 이름 바꿈(옛 → 새)이다. 그 옛 이름은 비워져 다시 쓸 수
      있고(맞바꿈 A↔B·사슬 A→B→C) 새 이름은 차지된다(두 호기를 같은 새 이름으로 바꾸면 거부).
    - `group_renaming` 은 같은 제출의 Main 설비 이름 바꿈, `created` 는 같은 제출에서 새로 넣는 호기
      이름이다(Space 편집기 — 비운 Main 설비 이름은 쓸 수 있고 새 이름·새 호기 이름은 차지된다).
    - `reserved`(`reserved_names`)는 편집본에 호기가 없어도 쓸 수 없는 이름(저장 안 한 지운 이름·
      설비 마스터에 없는 설비명의 비가동 일정)이다.

    글자는 1~`UNIT_ID_MAX` 자·인쇄 가능, 비울 수 없다. 다른 호기 설비명·Main 설비 이름과
    대소문자·앞뒤 공백 무시로 겹치면 거부하고, 자기 이름의 대소문자만 바꾸는 것과 자기 설비명을 Main
    설비로 적은 한 행 묶음(Main 설비가 따라간다)은 받는다. 같은 이름(앞뒤 공백만 다름 포함)이면 바꿀
    것이 없어 None. 거부 문구는 Space 적용 거부 그대로다.
    """
    old_name, new_name = old.strip(), new.strip()
    if new_name == old_name:
        return None
    subject = f"{old_name} 의 새 이름"
    if not new_name:
        return f"{subject}을 비울 수 없습니다."
    change = NameChange(kind="unit", old=old_name, new=new_name)
    others = [
        NameChange(kind="unit", old=other.strip(), new=target.strip())
        for other, target in (renaming or {}).items()
        if other.strip() != old_name and other.strip() != target.strip()
    ]
    groups = [
        NameChange(kind="group", old=other.strip(), new=target.strip())
        for other, target in (group_renaming or {}).items()
        if other.strip() != target.strip()
    ]
    unit_ids, group_ids = _names_before(master, [change, *others])
    try:
        _require_name(new_name, subject)
        _require_distinct_names(
            [change, *others, *groups],
            master_ids=unit_ids,
            group_ids=group_ids,
            created_ids=created,
            reserved=_reserved_reasons(reserved or ReservedNames()),
            only=("unit", old_name),
        )
    except ValueError as exc:
        return str(exc)
    return None


def _names_before(master: pd.DataFrame, changes: Sequence[NameChange]) -> tuple[set[str], set[str]]:
    """`check_unit_rename` 이 볼 바꾸기 **전** (설비명 모음, Main 설비 이름 모음).

    옛 이름이 모두 있거나 새 이름이 하나라도 없으면 `master` 를 바꾸기 전으로 읽는다(맞바꿈 A↔B
    는 앞뒤 모음이 같다). 아니면 제출 뒤 마스터다 — 바꿈마다 새 이름 행 **하나**를 옛 이름으로
    돌린다(같은 새 이름이 둘 이상이면 남은 행이 「이미 있는 설비명」 으로 걸린다). 그 행이 자기
    설비명을 Main 설비로 적은 한 행 묶음이었으면(`rename_followers` 가 따라 옮긴 꼴) Main 설비도
    돌린다 — 다른 묶음의 Main 설비 이름과 겹친 새 이름은 그대로 두어 겹침으로 걸리게."""
    ids = master[EQUIPMENT_ID_COLUMN].astype("string").str.strip()
    parents = _parents(master)
    present = _name_set(ids)
    named = [change for change in changes if change.new]
    if all(change.old in present for change in named) or not all(
        change.new in present for change in named
    ):
        return present, _name_set(parents)
    restored_ids: list[object] = list(ids)
    restored_parents: list[object] = list(parents)
    group_rows = parents.value_counts()
    done: set[int] = set()
    for change in named:
        position = next(
            (
                index
                for index, name in enumerate(ids)
                if index not in done and isinstance(name, str) and name == change.new
            ),
            None,
        )
        if position is None:
            continue
        done.add(position)
        restored_ids[position] = change.old
        parent = restored_parents[position]
        if isinstance(parent, str) and parent == change.new and int(group_rows.get(parent, 0)) == 1:
            restored_parents[position] = change.old
    return _text_set(restored_ids), _text_set(restored_parents)


def _text_set(values: Sequence[object]) -> set[str]:
    """글자 값만(빈 글자 빼고) 모은 이름 모음."""
    return {value for value in values if isinstance(value, str) and value}


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
    editor_ghosts: Sequence[Mapping[str, Any]] = (),
) -> EditorApply:
    """브라우저 적용값을 검증한다. **하나라도 어긋나면 `ValueError`** — 일부만 반영하지 않는다.

    `editor_ids` 는 이번 편집기에 보낸 호기, `master_ids` 는 편집본의 모든 호기(새 호기 중복 검사).
    `editor_groups` 는 이번 편집기에 보낸 호기의 Main 설비(이름을 바꿀 수 있는 묶음)이고, Main 설비
    전체 목록은 `unit_options["parentIds"]` 다. `reserved`(`reserved_names`)는 편집본에 호기가
    없어도 새 설비명(새 호기·이름 바꿈)으로 쓸 수 없는 이름이다. 다른 층으로 보낸 호기의 좌표는 그
    층 영역을 여기서 모르므로 범위를 보지 않는다 — `apply_layout_edits` 가 그 층 캔버스 안으로 민다.

    `editor_items`(이번 편집기에 보낸 호기 `editor_inputs(...).items`)와 `editor_ghosts`(숨은 모듈
    `editor_inputs(...).ghosts`)를 주면 이 층 도면에 놓이거나 자리·크기가 바뀐 Main 설비 모듈 묶음이
    묶음 범위의 바둑판 그대로인지 본다(`_regrid_module_groups` — 한 눈금 안의 어긋남은 칸 값으로
    바로잡고, 더 어긋나거나 갈라진 묶음은 거부한다). 묶음과 함께 옮겨진 숨은 모듈은 적용값의
    ``ghosts`` 로 오고 `EditorApply.hidden_moves` 가 된다. 모듈 묶음의 Main 설비명 위치는 적용값의
    ``groupLabels`` 로 오고(실린 모듈 묶음만) `EditorApply.group_labels` 가 된다 — 층 위치 목록으로
    합치는 것은 `next_group_labels` 다.
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
    changes, hidden_moves = _regrid_module_groups(
        changes,
        editor_items,
        bounds,
        editor_ghosts,
        _parse_ghost_moves(payload.get("ghosts"), editor_ghosts, bounds),
    )
    raw_marks = payload.get("marks")
    marks: tuple[FloorLayoutMark, ...] | None = None
    if raw_marks is not None:
        if not isinstance(raw_marks, list):
            raise ValueError("도면 요소 목록을 읽지 못했습니다.")
        marks = prepare_floor_layout_marks(raw_marks, bounds)
    renames = _parse_renames(
        payload.get("renames"), editor_ids=editor_ids, editor_groups=editor_groups
    )
    group_labels = _parse_group_labels(
        payload.get("groupLabels"), set(_module_groups(editor_items, editor_ghosts))
    )
    _require_distinct_renames(
        renames,
        master_ids=master_ids | editor_ids,
        group_ids=set(unit_options.get("parentIds", ())),
        created_ids={unit.unit_id for unit in created},
        reserved=reserved,
    )
    return EditorApply(
        changes=tuple(changes),
        created=tuple(created),
        canvas=new_canvas,
        marks=marks,
        renames=tuple(renames),
        hidden_moves=tuple(hidden_moves),
        group_labels=group_labels,
    )


def _require_distinct_renames(
    renames: Sequence[NameChange],
    *,
    master_ids: Collection[str],
    group_ids: Collection[str],
    created_ids: Collection[str],
    reserved: ReservedNames | None,
) -> None:
    """Space 적용의 이름 바꿈 겹침 검사 — 적용값 차례대로, 설비명은 공용 `check_unit_rename`
    (설비 마스터 호기 상세와 같은 함수), Main 설비는 같은 판정(`_require_distinct_names`)으로 보고
    처음 걸린 바꿈의 까닭으로 `ValueError`. 이름 모음만 아는 자리라 두 칸짜리 판정용 표를 만들어
    넘긴다."""
    units = {change.old: change.new for change in renames if change.kind == "unit"}
    groups = {change.old: change.new for change in renames if change.kind == "group"}
    names = _names_master(master_ids, group_ids)
    for change in renames:
        if change.kind == "unit":
            refusal = check_unit_rename(
                change.old,
                change.new,
                master=names,
                reserved=reserved,
                renaming={old: new for old, new in units.items() if old != change.old},
                group_renaming=groups,
                created=created_ids,
            )
            if refusal is not None:
                raise ValueError(refusal)
            continue
        _require_distinct_names(
            renames,
            master_ids=master_ids,
            group_ids=group_ids,
            created_ids=created_ids,
            reserved=_reserved_reasons(reserved or ReservedNames()),
            only=(change.kind, change.old),
        )


def _names_master(unit_ids: Collection[str], group_ids: Collection[str]) -> pd.DataFrame:
    """설비명 모음·Main 설비 이름 모음만 든 판정용 설비 마스터(`check_unit_rename` 이 읽는 두
    칸)."""
    units, groups = sorted(unit_ids), sorted(group_ids)
    return pd.DataFrame(
        {
            EQUIPMENT_ID_COLUMN: pd.array([*units, *([pd.NA] * len(groups))], dtype="string"),
            PARENT_EQUIPMENT_COLUMN: pd.array([*([pd.NA] * len(units)), *groups], dtype="string"),
        }
    )


def _parse_group_labels(
    raw_labels: object, module_groups: Collection[str]
) -> tuple[tuple[str, str], ...] | None:
    """적용값의 `groupLabels`(``[{"group": 옛 Main 설비, "position": "center"|"top"|"bottom"}]``)를
    읽는다. 이 편집기에 실린 모듈 묶음(모듈 둘 이상 — 숨은 모듈 포함)만 받고, 한 묶음에 한 번이다.
    없으면 None."""
    if raw_labels is None:
        return None
    if not isinstance(raw_labels, list):
        raise ValueError("Main 설비명 위치 목록을 읽지 못했습니다.")
    labels: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw in raw_labels:
        if not isinstance(raw, Mapping):
            raise ValueError("Main 설비명 위치 목록을 읽지 못했습니다.")
        group = _text(raw.get("group")).strip()
        if group not in module_groups:
            raise ValueError(f"이 편집기에 없는 모듈 묶음의 Main 설비명 위치입니다: {group}")
        if group in seen:
            raise ValueError(f"같은 Main 설비의 이름 위치가 두 번 왔습니다: {group}")
        seen.add(group)
        position = _text(raw.get("position")).strip()
        if position not in GROUP_LABEL_POSITIONS:
            raise ValueError(
                f"Main 설비 {group} 의 이름 위치를 알 수 없습니다: {position!r} — 가운데·위·아래 "
                "중 하나입니다."
            )
        labels.append((group, position))
    return tuple(labels)


def module_group_sizes(
    editor_items: Sequence[Mapping[str, Any]], ghosts: Sequence[Mapping[str, Any]] = ()
) -> dict[str, int]:
    """이 편집기에 실린 모듈 묶음(편집기 호기와 숨은 모듈을 합쳐 모듈 둘 이상)의 Main 설비 → 모듈
    수. 편집기 JS(`groupCounts`)와 같은 셈이다 — 바둑판 칸 수이자 Main 설비명 처음 위치
    (`default_group_label`)의 근거다."""
    return {
        group: len(items) + len(hidden)
        for group, (items, hidden) in _module_groups(editor_items, ghosts).items()
    }


def next_group_labels(
    current: GroupLabels, applied: EditorApply, module_groups: Mapping[str, int]
) -> dict[str, str]:
    """적용 뒤 이 층의 Main 설비명 위치(행이 없는 묶음은 처음 위치 `default_group_label` 로 선다).

    `current` 는 편집기에 보낸 위치(대기분, 없으면 저장값), `module_groups` 는 이 편집기에 실린
    모듈 묶음과 모듈 수(`module_group_sizes`)다. 편집기가 위치를 보냈으면(`applied.group_labels`)
    그 묶음들의 위치는 보낸 값으로 갈아 끼운다 — 보내지 않은 실린 묶음(다른 층으로 보냄)은 이
    층에서 빠지고, 실리지 않은 묶음(지금 기준일에 편집기에 없는 묶음)의 위치는 그대로 남는다. Main
    설비 이름 바꿈(`applied.group_renames`)은 새 이름으로 따라간다.

    보낸 위치가 그 묶음의 처음 위치이면 행을 두지 않는다 — 다만 이미 같은 위치의 행이 있으면(손대지
    않은 묶음) 그대로 둬, 아무것도 고르지 않은 적용이 층 위치 목록을 바꾸지 않는다. 한 줄 묶음(모듈
    2·3)은 처음 위치가 위라 가운데를 고르면 가운데 행이 남는다."""
    renamed = applied.group_renames
    if applied.group_labels is None:
        return dict(sorted((renamed.get(name, name), spot) for name, spot in current.items()))
    # 실리지 않은 묶음의 위치도 이름 바꿈을 따라간다(모듈 하나만 실려 묶음이 아닌 채 Main
    # 설비 이름을 바꾼 때).
    kept = {
        renamed.get(name, name): spot for name, spot in current.items() if name not in module_groups
    }
    for group, position in applied.group_labels:
        name = renamed.get(group, group)
        kept.pop(name, None)
        if current.get(group) == position or position != default_group_label(
            module_groups.get(group, 0)
        ):
            kept[name] = position
    return dict(sorted(kept.items()))


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
    - 숨은 모듈(`hidden_moves`): 묶음과 함께 옮겨진 X·Y·크기만 바꾼다(층·레이아웃표시 그대로)
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
    for move in apply.hidden_moves:
        # 묶음과 함께 옮겨진 숨은 모듈 — 같은 층의 자리·크기만 바꾸고 레이아웃표시는 그대로 둔다.
        mask = _id_mask(result, move.unit_id)
        if not mask.any():
            raise ValueError(f"편집본에 없는 호기입니다: {move.unit_id}")
        result.loc[mask, ["X좌표", "Y좌표", "Xsize", "Ysize"]] = [move.x, move.y, move.w, move.h]
    _fit_moved_into_canvases(result, apply.changes, canvases, default_canvas)
    _harmonize_groups(result, [change.unit_id for change in apply.changes])
    return result


def apply_name_changes(
    master: pd.DataFrame, downtime: pd.DataFrame, renames: Sequence[NameChange]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """검증한 이름 바꿈을 설비 마스터와 비가동 일정에 얹은 새 프레임 둘을 돌려준다(원본은 그대로).

    `apply_layout_edits` **뒤에** 부른다 — 배치 변경은 옛 설비명으로 온다. 바꿈은 한꺼번에 한다(A↔B
    처럼 서로 바꾼 이름도 맞게 간다). 좌표·크기 등 나머지 칸은 그대로라 배치가 남는다.

    - 설비명: 그 행의 설비명. 따라가는 칸(비가동 일정의 설비명, 자기 설비명을 Main 설비로 적은 한
      행짜리 묶음의 Main 설비)은 `rename_followers` 가 옮긴다 — 설비 마스터 호기 상세의 이름
      바꾸기와 같은 함수다.
    - Main 설비: 그 이름을 쓰는 모든 행(편집기에 없는 형제 포함). 비가동 일정은 설비명만 가리키므로
      바꿀 것이 없다.
    """
    units = {change.old: change.new for change in renames if change.kind == "unit"}
    groups = {change.old: change.new for change in renames if change.kind == "group"}
    if not units and not groups:
        return master, downtime
    result = master.copy()
    ids = result[EQUIPMENT_ID_COLUMN].astype("string").str.strip()
    renamed = ids.isin(list(units)).fillna(False).astype(bool)
    if renamed.any():
        result.loc[renamed, EQUIPMENT_ID_COLUMN] = ids.loc[renamed].map(units)
    # 자기 이름을 Main 설비로 적은 행이 먼저 따라간다 — 묶음 이름 바꿈은 그 뒤 남은 행에만 닿는다
    # (새 설비명은 다른 Main 설비 이름과 겹칠 수 없어 따라간 행이 묶음 바꿈에 다시 걸리지 않는다).
    result, schedule = rename_followers(result, downtime, units)
    if groups:
        parents = _parents(result)
        grouped = parents.isin(list(groups)).fillna(False).astype(bool)
        if grouped.any():
            result.loc[grouped, PARENT_EQUIPMENT_COLUMN] = parents.loc[grouped].map(groups)
    return result, schedule


def rename_followers(
    master: pd.DataFrame,
    downtime: pd.DataFrame,
    renames: Mapping[str, str],
    *,
    touched_parent_rows: Collection[Any] = (),
    touched_downtime_rows: Collection[Any] = (),
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """설비명 이름 바꿈(옛 → 새)을 따라가는 칸을 옮긴 새 프레임 둘(원본은 그대로). `master` 의
    설비명은 **이미 새 이름**이다(Space 는 `apply_name_changes` 가, 설비 마스터 호기 상세는 칸
    고침이 넣는다).

    - 비가동 일정의 설비명: 옛 → 새로 한꺼번에(맞바꿈 A↔B 도 맞게 간다).
    - 자기 설비명을 Main 설비로 적은 한 행짜리 묶음: 그 행의 Main 설비가 옛 이름이면 새 이름으로
      (저장 검증이 이름이 같아도 받는 유일한 묶음이다).

    `touched_parent_rows`·`touched_downtime_rows` 는 같은 제출에서 사용자가 그 칸(Main 설비·비가동
    설비명)을 직접 고친 행의 **index 라벨**이다 — 손댄 값을 이름 바꿈이 덮지 않는다. Space 는 빈
    값을 넘긴다. 이름 바꿈은 호기 키를 그대로 두므로 저장하면 모든 설비 시나리오의 일정·비가동이
    따라간다(`equipment_scenario.assign_unit_keys`).
    """
    units = {old: new for old, new in renames.items() if old != new}
    if not units:
        return master, downtime
    result = master.copy()
    ids = result[EQUIPMENT_ID_COLUMN].astype("string").str.strip()
    origins = ids.map({new: old for old, new in units.items()})
    follows = (
        origins.notna().fillna(False).astype(bool)
        & _parents(result).eq(origins).fillna(False).astype(bool)
        & ~pd.Series(result.index.isin(list(touched_parent_rows)), index=result.index)
    )
    if follows.any():
        result.loc[follows, PARENT_EQUIPMENT_COLUMN] = ids.loc[follows]
    return result, _renamed_downtime(downtime, units, keep=touched_downtime_rows)


def _renamed_downtime(
    downtime: pd.DataFrame, units: Mapping[str, str], *, keep: Collection[Any] = ()
) -> pd.DataFrame:
    """비가동 일정의 설비명을 (옛 이름 → 새 이름) 지도대로 한꺼번에 바꾼 사본. `keep`(index 라벨)
    행은 그대로 둔다."""
    schedule = downtime.copy()
    if not units or schedule.empty:
        return schedule
    names = schedule[EQUIPMENT_ID_COLUMN].astype("string").str.strip()
    hit = names.isin(list(units)).fillna(False).astype(bool) & ~pd.Series(
        schedule.index.isin(list(keep)), index=schedule.index
    )
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


def compose_unit_renames(
    pending: PendingRenames, renames: Mapping[str, str], *, saved_names: Collection[str]
) -> PendingRenames:
    """설비명 이름 바꿈(옛 → 새)을 세션의 저장 안 한 이름 지도에 잇는다 — Main 설비 쪽은 그대로.

    A→B 뒤 B→C 는 C→A 로, 다시 A 로 돌리면 항목이 빠진다. 저장본 이름(`saved_names`)에 없던 이름(이
    세션에 새로 넣은 호기)은 기억하지 않는다 — 짝지을 저장본 호기가 없다. Space 편집기
    (`compose_renames`)와 설비 마스터 호기 상세가 같은 함수로 잇는다."""
    return PendingRenames(
        units=_compose(pending.units, renames, set(saved_names)), groups=dict(pending.groups)
    )


def compose_renames(
    pending: PendingRenames, apply: EditorApply, *, saved: pd.DataFrame
) -> PendingRenames:
    """이번 적용의 이름 바꿈을 세션의 저장 안 한 이름 바꿈에 잇는다(`saved` 는 최신 저장본).
    설비명은 `compose_unit_renames`, Main 설비는 같은 규칙으로 따로 잇는다."""
    units = compose_unit_renames(
        pending, apply.unit_renames, saved_names=_name_set(saved[EQUIPMENT_ID_COLUMN])
    )
    return PendingRenames(
        units=units.units,
        groups=_compose(pending.groups, apply.group_renames, _name_set(_parents(saved))),
    )


def live_renames(
    pending: PendingRenames | None, saved: pd.DataFrame, buffer: pd.DataFrame
) -> PendingRenames:
    """지금도 맞는 항목만 남긴다 — 지금 이름이 편집본에 있고 저장본 이름이 저장본에 있으며, 저장본
    이름이 편집본에 없거나 **그 이름을 이 지도의 다른 살아 있는 항목이 이어받았을 때**(맞바꿈 A↔B,
    A→X 뒤 B→A). 설비 마스터에서 그 사이 되돌린 이름(지금 이름이 편집본에 없음)과 옛 이름을 새로 쓴
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
    견줄 때 이름 바꿈을 따라간 설비명을 「설비 마스터의 비가동 일정 편집」으로 세지 않게 한다."""
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


def _rows_by_name(frame: pd.DataFrame) -> dict[str, Mapping[Any, Any]]:
    """설비명(앞뒤 공백 걷음) → 그 행(같은 이름이 여럿이면 첫 행)."""
    rows: dict[str, Mapping[Any, Any]] = {}
    for row in frame.to_dict(orient="records"):
        rows.setdefault(_text(row.get(EQUIPMENT_ID_COLUMN)).strip(), row)
    return rows


def saved_layout_drift(
    saved: pd.DataFrame, buffer: pd.DataFrame, origins: Mapping[str, str]
) -> list[str]:
    """`buffer` 에서 저장본 호기를 잇는 행 가운데 배치 일곱 칸(`PLACE_COLUMNS`)이 저장본 그 호기와
    다른 행의 설비명(`buffer` 차례). `origins` 는 지금 설비명 → 저장하면 이어받을 저장본 설비명
    (`equipment_scenario.inherited_unit_names` — 저장의 호기 키 규칙 그대로)이고, 그 밖의 행(새
    호기)은 보지 않는다.

    가정 설비 시나리오의 배치 칸 임시 잠금(설비 시나리오 2단계 S1 — 이 판에서 배치 칸은 공통이라
    고치면 공식 배치가 바뀐다)이 설비 마스터 탭 제출·붙여넣기 미리보기에서 쓴다. 제출 전 편집본이
    아니라 **저장본**과 견준다 — 앞 제출에서 지우거나 설비명을 바꿔 둔 호기를 같은 이름으로 다시
    넣어도 저장하면 그 호기 키를 이어 공통 배치를 고치기 때문이다."""
    saved_rows = _rows_by_name(saved)
    drift: list[str] = []
    for row in buffer.to_dict(orient="records"):
        name = _text(row.get(EQUIPMENT_ID_COLUMN)).strip()
        origin = origins.get(name)
        previous = saved_rows.get(origin) if origin is not None else None
        if previous is None or name in drift:
            continue
        if any(_comparable(previous.get(c)) != _comparable(row.get(c)) for c in PLACE_COLUMNS):
            drift.append(name)
    return drift


def restore_saved_layout(
    buffer: pd.DataFrame, saved: pd.DataFrame, origins: Mapping[str, str]
) -> pd.DataFrame:
    """`origins`(지금 설비명 → 저장본 설비명) 행의 배치 일곱 칸을 저장본 그 호기 값으로 되돌린
    `buffer` 사본(나머지 칸·행은 그대로)."""
    if not origins:
        return buffer
    result = buffer.copy()
    saved_rows = _rows_by_name(saved)
    columns = [column for column in PLACE_COLUMNS if column in result.columns]
    ids = result[EQUIPMENT_ID_COLUMN].astype("string").str.strip()
    for name, origin in origins.items():
        previous = saved_rows.get(origin)
        if previous is None:
            continue
        mask = ids.eq(name).fillna(False).astype(bool)
        for column in columns:
            result.loc[mask, column] = previous.get(column)
    return result


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
    """배치 칸이 아닌 차이가 있는 호기 수(설비 마스터의 저장 안 한 다른 편집). 지운 호기도 센다.
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
    """두 표의 내용이 다른가(값의 형 차이는 무시). 설비 마스터 표 밖의 설비 마스터 탭 편집(기존
    보유대수·비가동 일정)을 알린다. 「다르다」로 잘못 보면 메모 칸이 더 뜰 뿐이라 행 순서도
    견준다."""
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
