# Purpose: Space 배치 집계(설비·상태별 대수·점유율·층별 배치)와 층 상세 범례·도면 요소 색을 만든다.

from __future__ import annotations

import html
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass

import pandas as pd

from capa_simulation.design import theme, tokens
from capa_simulation.services.equipment_units import (
    UNIT_SHARE_COLUMN,
    format_unit_count,
    unit_total,
)
from capa_simulation.services.fab_layout import FLOOR_KEYS, floor_label
from capa_simulation.services.floor_layout_mark import MARK_COLOR_KEYS
from capa_simulation.services.floor_layout_profile import (
    DEFAULT_CANVAS_HEIGHT,
    DEFAULT_CANVAS_WIDTH,
    CanvasSize,
    FloorKey,
)


def _unit_shares(equipment: pd.DataFrame) -> pd.Series:
    """행마다 설비지분. 상태 판정을 거치지 않은 표(지분 컬럼이 없는 표)는 행 하나가 한 대다."""
    if UNIT_SHARE_COLUMN in equipment.columns:
        return equipment[UNIT_SHARE_COLUMN].astype("float64").fillna(1.0)
    return pd.Series(1.0, index=equipment.index, dtype="float64")


def equipment_unit_total(equipment: pd.DataFrame) -> float:
    """행이 아니라 설비 대수. 모체호기로 묶은 모듈 행 넷이 한 대다."""
    return unit_total(_unit_shares(equipment))


def stage_counts(equipment: pd.DataFrame) -> dict[str, float]:
    """상태별 설비 대수(층 배치도 범례). 행을 세지 않고 설비지분을 더하고, 0 대인 상태는 뺀다.

    모듈 하나가 비가동이면 그 설비는 가용 0.75 · 운영 비가동 0.25 로 갈린다. 상태마다
    **직접 더한다** — 합계에서 빼면 반올림 끝자리가 -0.0 으로 남아 「-0대」가 찍힌다.
    """
    if equipment.empty or "상태" not in equipment.columns:
        return {}
    shares = _unit_shares(equipment)
    counts = {
        status: unit_total(shares.where(equipment["상태"].eq(status), 0.0))
        for status in tokens.EQUIPMENT_STAGE_COLORS
    }
    return {status: count for status, count in counts.items() if count > 0}


def occupancy_ratio(placed: pd.DataFrame, canvas_width: float, canvas_height: float) -> float:
    """도면에 그린 호기 사각형 면적 합 ÷ 캔버스 면적. 캔버스 단위의 상대값이고(실제 m² 아님)
    겹친 자리는 두 번 센다. 캔버스가 없으면 0."""
    area = canvas_width * canvas_height
    if placed.empty or area <= 0:
        return 0.0
    sizes = placed.loc[:, ["Xsize", "Ysize"]].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    return float((sizes["Xsize"] * sizes["Ysize"]).sum()) / area


@dataclass(frozen=True)
class FloorPlacement:
    """한 층의 배치 집계. FAB 도면의 층 블록과 층 목록 표가 같은 값을 쓴다 — 상태가 아니라 배치를
    센다(상태는 층 상세의 색과 범례가 말한다)."""

    key: FloorKey
    placed: float
    unplaced: float
    occupancy: float


def _by_floor(frame: pd.DataFrame) -> dict[FloorKey, pd.DataFrame]:
    rows = frame.dropna(subset=["동", "층"])
    return {
        (str(building), str(floor)): group
        for (building, floor), group in rows.groupby(["동", "층"], sort=False)
    }


def floor_placements(
    counted: pd.DataFrame,
    unplaced: pd.DataFrame,
    located: pd.DataFrame,
    canvas_of: Callable[[FloorKey], CanvasSize],
) -> tuple[FloorPlacement, ...]:
    """FAB 의 30개 층(이름 순)마다 배치·미배치 대수와 점유율. 대수는 설비지분 합이다.

    `counted` 는 세는 배치 행, `unplaced` 는 레이아웃표시 Y 인데 좌표가 없는 행, `located` 는
    도면에 그리는 행(점유율의 면적)이다. 동·층이 정해지지 않은 미배치는 어느 층에도 들지 않는다 —
    호출하는 쪽이 따로 말한다."""
    counted_by = _by_floor(counted)
    unplaced_by = _by_floor(unplaced)
    located_by = _by_floor(located)
    return tuple(
        FloorPlacement(
            key=key,
            placed=equipment_unit_total(counted_by.get(key, counted.iloc[0:0])),
            unplaced=equipment_unit_total(unplaced_by.get(key, unplaced.iloc[0:0])),
            occupancy=occupancy_ratio(located_by.get(key, located.iloc[0:0]), *canvas_of(key)),
        )
        for key in FLOOR_KEYS
    )


def floor_block_stats(
    placements: Collection[FloorPlacement],
) -> dict[str, dict[str, str | None]]:
    """층 블록 글자(편집기 `data.linkStats`). 키는 블록의 연결(「C1 1F」)이다.

    블록 안에는 배치 대수와, 있으면 미배치 대수만 적는다(점유율은 풍선). 상태별 대수는 넣지
    않는다 — FAB·층 칸은 배치를 센다(2026-10-01 결정). 이 값은 epoch 에 넣지 않는다: 넣으면 기준일만
    바꿔도 편집 중 내용과 실행 취소가 지워진다."""
    return {
        floor_label(placement.key): {
            "placed": f"배치 {format_unit_count(placement.placed)}대",
            "unplaced": (
                f"미배치 {format_unit_count(placement.unplaced)}대"
                if placement.unplaced > 0
                else None
            ),
            "occupancy": (f"점유율 {placement.occupancy:.1%}" if placement.placed > 0 else None),
        }
        for placement in placements
    }


def mark_colors() -> dict[str, str]:
    """영역 색 키 → 지금 테마의 색. 검증된 범주 팔레트(제품별 비중과 같은 색)를 그대로 쓴다.
    층·FAB 도면(편집기)이 같은 색을 쓴다."""
    named = dict(zip(MARK_COLOR_KEYS[:-1], tokens.PRODUCT_SHARE_COLORS, strict=False))
    return {**named, MARK_COLOR_KEYS[-1]: tokens.PRODUCT_SHARE_OTHER}


def keep_out_color() -> str:
    """겹침·설비 금지 표시색. 다크의 부족색은 어두운 캔버스에서 1.9:1 로 묻혀 밝은 감소색을 쓴다."""
    return tokens.DELTA_AREA_DECREASE if theme.current_mode() == "dark" else tokens.STATUS_SHORTAGE


def stage_legend_markup(
    counts: Mapping[str, float] | None, *, exclude: Collection[str] = ()
) -> str:
    """층 상세 머리 줄 오른쪽의 상태 범례. `counts` 가 있으면 그 층에 있는 상태만 대수와 함께
    (「가용 5대」), 없으면 모든 상태의 색 뜻만 보인다(배치 편집 중 — 편집본은 저장본과 대수가
    다르다). 도면 안이 아니라 머리 줄에 두어 도면이 테두리 안을 다 쓴다."""
    chips = []
    for status, color in tokens.EQUIPMENT_STAGE_COLORS.items():
        if status in exclude or (counts is not None and status not in counts):
            continue
        text = status if counts is None else f"{status} {format_unit_count(counts[status])}대"
        chips.append(
            '<span style="display:inline-flex;align-items:center;gap:5px;white-space:nowrap">'
            f'<span aria-hidden="true" style="width:11px;height:11px;border-radius:2px;'
            f'background:{color};flex:none"></span>{html.escape(text)}</span>'
        )
    return (
        '<div style="display:flex;flex-wrap:wrap;justify-content:flex-end;gap:4px 14px;'
        f'font-size:0.82rem;color:{tokens.TEXT_MUTED}">{"".join(chips)}</div>'
    )


def invalid_equipment_rows(
    equipment: pd.DataFrame,
    *,
    canvas_width: float = DEFAULT_CANVAS_WIDTH,
    canvas_height: float = DEFAULT_CANVAS_HEIGHT,
) -> list[int]:
    required = {"X좌표", "Y좌표", "Xsize", "Ysize"}
    if not required.issubset(equipment.columns):
        return list(range(1, len(equipment) + 1))
    numeric = equipment.loc[:, ["X좌표", "Y좌표", "Xsize", "Ysize"]].apply(
        pd.to_numeric, errors="coerce"
    )
    invalid = (
        numeric.isna().any(axis=1)
        | numeric["X좌표"].lt(0)
        | numeric["Y좌표"].lt(0)
        | numeric["Xsize"].le(0)
        | numeric["Ysize"].le(0)
        | numeric["X좌표"].add(numeric["Xsize"]).gt(canvas_width)
        | numeric["Y좌표"].add(numeric["Ysize"]).gt(canvas_height)
    )
    return [int(index) + 1 for index in numeric.index[invalid].tolist()]
