# Purpose: Space 배치 편집기·뷰어 입력을 만들고 적용값을 검증해 편집본에 얹는 순수 계산을 모은다.

"""Space 배치 편집기(드래그앤드롭)의 파이썬 쪽 계산.

편집 상태는 브라우저가 쥐고 `적용` 때 한 번에 보낸다. 여기서 하는 일은 셋이다.

1. **입력** — 설비 편집본(호기 상태 포함)에서 이 층 편집기에 보낼 호기를 고른다. 대상은
   Space 현황이 그리는 호기와 같다(레이아웃표시 Y 이고 반출·이설 실행 전). 좌표가 있으면 도면에,
   없으면 미배치 트레이에 놓는다. 동·층이 빈 호기는 모든 층 트레이에 뜬다.
2. **검증** — 브라우저가 보낸 적용값을 다시 검사한다. 하나라도 어긋나면 `ValueError` 로 적용
   전체를 거부한다. 조용히 버리면 그 편집이 사라진 채 화면은 적용된 것처럼 보인다.
3. **반영** — 검증한 변경을 편집본 호기 마스터에 얹는다. 트레이로 빼도 크기는 남기고, 다른
   층으로 보낸 호기는 그 층 캔버스 안으로 민다. Main 설비 묶음은 동·층을 함께 맞춘다(모듈 행은
   동·층이 같아야 저장된다).

좌표 계약은 Space 배치도와 같다: 원점은 왼쪽 아래, 상자는 (X, Y) → (X+Xsize, Y+Ysize).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Final, cast

import pandas as pd

from capa_simulation.services.equipment_contract import (
    ARRIVAL_DATE_COLUMN,
    EQUIPMENT_ID_COLUMN,
    PARENT_EQUIPMENT_COLUMN,
    QUAL_CONFIRMATION_STATUSES,
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
from capa_simulation.services.korean_particle import with_topic_particle

POSITION_COLUMNS: Final = ("X좌표", "Y좌표")
SIZE_COLUMNS: Final = ("Xsize", "Ysize")
# 편집기가 바꾸는 칸. 나머지 칸이 다르면 RawData 의 다른 편집이다.
PLACE_COLUMNS: Final = ("동", "층", "X좌표", "Y좌표", "Xsize", "Ysize", "레이아웃표시")
UNIT_ID_MAX: Final = 40
NEW_UNIT_HISTORY: Final = "Space 편집기에서 추가"
_DEFAULT_SIZE: Final = (12.0, 7.0)


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
    """편집기에서 새로 넣은 호기. 호기 마스터가 꼭 요구하는 값만 받는다."""

    unit_id: str
    process: str
    line: str
    use: str
    existing: bool
    arrival: date | None
    qual: date | None
    confirm: str


@dataclass(frozen=True)
class EditorApply:
    """검증을 마친 적용값 한 번. `canvas`·`marks` 는 바꾼 경우에만 값이 있다."""

    changes: tuple[UnitChange, ...]
    created: tuple[CreatedUnit, ...]
    canvas: CanvasSize | None
    marks: tuple[FloorLayoutMark, ...] | None


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


def editor_inputs(
    status: pd.DataFrame,
    *,
    floor: FloorKey,
    stage_of: Mapping[str, str] | None = None,
    new_ids: set[str] | None = None,
    arrived_ids: set[str] | None = None,
) -> EditorInputs:
    """설비 편집본의 호기 상태(`build_space_equipment_status` 결과)에서 이 층 편집기 입력을 만든다.

    - 도면: 레이아웃반영여부(레이아웃표시 Y · 반출·이설 전) 이고 이 층에 X·Y·크기가 다 있는 호기
    - 트레이: 같은 대상 중 X·Y 가 없고 이 층이거나 층 미정인 호기. Main 설비 묶음의 다른 모듈이
      이 층 도면에 서 있으면 그 형제는 트레이에 따로 내놓지 않는다(상자를 한 모듈에만 그린 설비).
    - 영역 하한: 이 층에 좌표가 있지만 편집기에 안 나오는 호기(N·반출 완료 …)가 차지한 범위.
      저장 검증은 그런 행에도 캔버스 상한을 걸므로 영역을 그보다 줄이지 못하게 한다.
    """
    target = status["레이아웃반영여부"].fillna(False).astype(bool)
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
    tray = target & ~has_position & (on_floor | floorless) & ~keys.isin(placed_keys)
    hidden = on_floor & has_position & has_size & ~placed
    reserved = (
        (
            float((status.loc[hidden, "X좌표"] + status.loc[hidden, "Xsize"]).max()),
            float((status.loc[hidden, "Y좌표"] + status.loc[hidden, "Ysize"]).max()),
        )
        if hidden.any()
        else (0.0, 0.0)
    )
    parents = _parents(status)
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
    shown = placed | tray
    rows = status.loc[shown].assign(
        _placed=placed[shown], _floorless=floorless[shown], _parent=parents[shown]
    )
    # 다른 층에서 옮겨 온 호기는 같은 좌표로 와 기존 호기를 덮을 수 있다 — 맨 뒤(맨 위에 그림)로.
    order = (
        rows[EQUIPMENT_ID_COLUMN].astype("string").isin(arrivals).astype(int).argsort(kind="stable")
    )
    items: list[dict[str, Any]] = []
    for row in rows.iloc[order].to_dict(orient="records"):
        unit_id = str(row[EQUIPMENT_ID_COLUMN]).strip()
        parent = row["_parent"]
        items.append(
            {
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


# ------------------------------------------------------------------ 검증


def _parse_created(
    unit_id: str,
    raw: Mapping[str, Any],
    taken: set[str],
    options: Mapping[str, Sequence[str]],
) -> CreatedUnit:
    if not unit_id or len(unit_id) > UNIT_ID_MAX:
        raise ValueError(f"새 호기 이름은 1~{UNIT_ID_MAX}자여야 합니다: {unit_id!r}")
    if not unit_id.isprintable():
        raise ValueError(f"새 호기 이름에 탭·줄바꿈·특수 공백을 쓸 수 없습니다: {unit_id!r}")
    if unit_id in options.get("parentIds", ()):
        raise ValueError(f"이미 Main 설비로 쓰는 이름입니다: {unit_id}")
    if unit_id in taken:
        raise ValueError(f"이미 있는 호기입니다: {unit_id}")
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
    qual = _iso_date(raw.get("qual"), "Qual일정", unit_id)
    confirm = _text(raw.get("confirm")).strip()
    if not existing:
        # 호기 마스터 계약: 기존설비가 아니면 반입·Qual 일정(반입 ≤ Qual)과 확정상태가 필수다.
        if arrival is None or qual is None:
            raise ValueError(
                f"신규 설비 {with_topic_particle(unit_id)} 반입일정과 Qual일정이 필요합니다."
            )
        if qual < arrival:
            raise ValueError(f"새 호기 {unit_id} 의 Qual일정이 반입일정보다 빠릅니다.")
        if confirm not in QUAL_CONFIRMATION_STATUSES:
            raise ValueError(f"새 호기 {unit_id} 의 확정상태를 골라 주세요.")
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


def parse_editor_apply(
    payload: Mapping[str, Any],
    *,
    editor_ids: set[str],
    master_ids: set[str],
    floor: FloorKey,
    floors: Sequence[FloorKey],
    canvas: CanvasSize,
    unit_options: Mapping[str, Sequence[str]],
) -> EditorApply:
    """브라우저 적용값을 검증한다. **하나라도 어긋나면 `ValueError`** — 일부만 반영하지 않는다.

    `editor_ids` 는 이번 편집기에 보낸 호기, `master_ids` 는 편집본의 모든 호기(새 호기 중복 검사).
    다른 층으로 보낸 호기의 좌표는 그 층 영역을 여기서 모르므로 범위를 보지 않는다 —
    `apply_layout_edits` 가 그 층 캔버스 안으로 민다.
    """
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
            created.append(
                _parse_created(unit_id, raw["created"], master_ids | editor_ids, unit_options)
            )
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
    raw_marks = payload.get("marks")
    marks: tuple[FloorLayoutMark, ...] | None = None
    if raw_marks is not None:
        if not isinstance(raw_marks, list):
            raise ValueError("도면 요소 목록을 읽지 못했습니다.")
        marks = prepare_floor_layout_marks(raw_marks, bounds)
    return EditorApply(
        changes=tuple(changes), created=tuple(created), canvas=new_canvas, marks=marks
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
            "Qual일정": pd.Timestamp(unit.qual) if unit.qual else None,
            "확정상태": unit.confirm or None,
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

    편집기에 없던 형제(반출 완료·레이아웃표시 N …)가 이 맞춤으로 **층이 바뀌면** 그 X·Y 를 비운다.
    옛 층 좌표를 지닌 채 따라가면 새 층 캔버스 밖이라 거부되거나 새 층에 유령 영역을 남긴다.
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
    """검증한 적용값을 편집본 호기 마스터에 얹은 새 프레임을 돌려준다(원본은 그대로).

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

    대상은 편집기와 같다 — 레이아웃반영여부이고 좌표가 다 있는 호기(반출·이설 완료 제외).
    """
    placed = status.loc[
        status["레이아웃반영여부"].fillna(False).astype(bool)
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


def _comparable(value: object) -> str:
    if not _present(value):
        return ""
    number = finite_or_none(value)
    if number is not None and not isinstance(value, str):
        return repr(round(number, 6))
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    return str(value).strip()


def layout_changes(saved: pd.DataFrame, buffer: pd.DataFrame) -> pd.DataFrame:
    """저장본과 편집본의 배치 칸 차이(호기마다 한 줄): 설비명·Main 설비·구분·이전·새."""
    saved_rows = {
        str(row[EQUIPMENT_ID_COLUMN]).strip(): row for row in saved.to_dict(orient="records")
    }
    rows = []
    for row in buffer.to_dict(orient="records"):
        unit_id = str(row[EQUIPMENT_ID_COLUMN]).strip()
        before = saved_rows.get(unit_id)
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


def other_change_count(saved: pd.DataFrame, buffer: pd.DataFrame) -> int:
    """배치 칸이 아닌 차이가 있는 호기 수(RawData 의 저장 안 한 다른 편집). 지운 호기도 센다."""
    saved_rows = {
        str(row[EQUIPMENT_ID_COLUMN]).strip(): row for row in saved.to_dict(orient="records")
    }
    buffer_rows = {
        str(row[EQUIPMENT_ID_COLUMN]).strip(): row for row in buffer.to_dict(orient="records")
    }
    others = [column for column in buffer.columns if column not in PLACE_COLUMNS]
    count = len(saved_rows.keys() - buffer_rows.keys())
    for unit_id, row in buffer_rows.items():
        before = saved_rows.get(unit_id)
        if before is None:
            if _text(row.get("호기이력")) != NEW_UNIT_HISTORY:
                count += 1
            continue
        if any(_comparable(before.get(c)) != _comparable(row.get(c)) for c in others):
            count += 1
    return count


def table_changed(saved: pd.DataFrame, buffer: pd.DataFrame) -> bool:
    """두 표의 내용이 다른가(값의 형 차이는 무시). 호기 마스터 밖의 RawData 편집(기존 보유대수·
    비가동 일정)을 알린다. 「다르다」로 잘못 보면 메모 칸이 더 뜰 뿐이라 행 순서도 견준다."""
    if list(saved.columns) != list(buffer.columns) or len(saved) != len(buffer):
        return True
    rows = [
        [tuple(_comparable(value) for value in row) for row in frame.itertuples(index=False)]
        for frame in (saved, buffer)
    ]
    return rows[0] != rows[1]


def unsaved_unit_ids(
    saved: pd.DataFrame, buffer: pd.DataFrame, floor: FloorKey
) -> tuple[set[str], set[str]]:
    """(저장본에 없는 새 호기, 다른 층에서 이 층으로 옮겨 왔지만 아직 저장하지 않은 호기)."""
    saved_floor = {
        str(row[EQUIPMENT_ID_COLUMN]).strip(): (
            _comparable(row.get("동")),
            _comparable(row.get("층")),
        )
        for row in saved.to_dict(orient="records")
    }
    here = (floor[0], floor[1])
    new_ids: set[str] = set()
    arrived: set[str] = set()
    for row in buffer.to_dict(orient="records"):
        unit_id = str(row[EQUIPMENT_ID_COLUMN]).strip()
        before = saved_floor.get(unit_id)
        if before is None:
            new_ids.add(unit_id)
            continue
        now = (_comparable(row.get("동")), _comparable(row.get("층")))
        if now == here and before != here and "" not in before:
            arrived.add(unit_id)
    return new_ids, arrived


def viewer_items(located: pd.DataFrame) -> list[dict[str, Any]]:
    """층 상세 뷰어(편집기와 같은 도면, 보기 전용)에 보낼 저장본 호기. 좌표·크기가 다 있는 행만
    받는다. `detail` 은 풍선·선택 줄에 붙는 공정과 운영 비가동이다."""
    items: list[dict[str, Any]] = []
    parents = _parents(located)
    for (_, row), parent in zip(located.iterrows(), parents, strict=True):
        process = _text(row.get("공정소분류")).strip()
        downtime = _text(row.get("비가동유형")).strip()
        items.append(
            {
                "id": str(row[EQUIPMENT_ID_COLUMN]).strip(),
                "label": str(row[EQUIPMENT_ID_COLUMN]).strip(),
                "stage": _text(row.get("상태")),
                "x": finite_or_none(row["X좌표"]),
                "y": finite_or_none(row["Y좌표"]),
                "w": finite_or_none(row["Xsize"]),
                "h": finite_or_none(row["Ysize"]),
                "placed": True,
                "group": str(parent) if _present(parent) else None,
                "detail": " · ".join(
                    part for part in (process, f"비가동 {downtime}" if downtime else "") if part
                ),
            }
        )
    return items
