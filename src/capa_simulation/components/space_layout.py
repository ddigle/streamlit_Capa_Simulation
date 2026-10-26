# Purpose: Space 배치 집계·호기 상자 색·필요 단축 얹기·층 상세 범례·호기 표를 만든다.

from __future__ import annotations

import html
import re
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Final, cast

import pandas as pd

from capa_simulation.design import theme, tokens
from capa_simulation.services.equipment_contract import (
    EQUIPMENT_ID_COLUMN,
    LINE_TYPE_GROUPS,
    PARENT_EQUIPMENT_COLUMN,
)
from capa_simulation.services.equipment_units import (
    UNIT_COUNT_DECIMALS,
    UNIT_KEY_COLUMN,
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
from capa_simulation.services.space_color_basis import (
    COLOR_BASIS_CAPA,
    COLOR_BASIS_LINE_TYPE,
    COLOR_BASIS_SHORTENING,
    CapaGroup,
    color_groups,
)
from capa_simulation.services.space_layout_edit import natural_name_key
from capa_simulation.services.space_shortening_layer import BUCKET_LABELS, BUCKETS
from capa_simulation.services.space_unit_state import (
    DELAYED_STATE,
    EXIT_PLANNED_STATE,
    FLAG_STATE,
    OFFLINE_STATE,
    REAL_STATE,
    STOPPED_STATE,
    STORAGE_STATE,
    VISIBLE_STATE,
    boundary_payload,
    unit_states_at,
)


def row_unit_shares(equipment: pd.DataFrame) -> pd.Series:
    """행마다 설비지분. 상태 판정을 거치지 않은 표(지분 컬럼이 없는 표)는 행 하나가 한
    대다. 범례·배치 대수와 층 상세 뷰어의 「겹쳐 숨긴 반입 예정 n대」가 같은 축으로 센다."""
    if UNIT_SHARE_COLUMN in equipment.columns:
        return equipment[UNIT_SHARE_COLUMN].astype("float64").fillna(1.0)
    return pd.Series(1.0, index=equipment.index, dtype="float64")


def equipment_unit_total(equipment: pd.DataFrame) -> float:
    """행이 아니라 설비 대수. Main 설비로 묶은 모듈 행 넷이 한 대다."""
    return unit_total(row_unit_shares(equipment))


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


def _floor_sums(frame: pd.DataFrame, values: pd.Series) -> dict[FloorKey, float]:
    """`values`(`frame` 과 같은 행 차례)의 (동, 층)별 합. 동·층이 빈 행은 어느 층에도 들지 않는다.

    층마다 그 층 행만 원래 차례로 모은 배열을 numpy 로 더한다 — `Series.sum` 과 같은 쌍별 합이라
    층 프레임을 잘라 `equipment_unit_total`·`occupancy_ratio` 로 더하던 값과 비트까지 같다."""
    known = (frame["동"].notna() & frame["층"].notna()).to_numpy(dtype=bool)
    if not known.any():
        return {}
    array = values.to_numpy(dtype="float64")[known]
    sums: dict[FloorKey, float] = {}
    for key, positions in frame.loc[known].groupby(["동", "층"], sort=False).indices.items():
        building, floor = cast(tuple[object, object], key)
        sums[(str(building), str(floor))] = float(array[positions].sum())
    return sums


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
    # 층마다 프레임을 잘라 pandas 연산을 돌리면 빈 층까지 30번의 고정비가 회차마다 든다 — 표마다
    # (동, 층) 묶음을 한 번만 낸다. 빈 `located` 는 Xsize·Ysize 칸이 없어도 된다.
    placed_by = _floor_sums(counted, row_unit_shares(counted))
    unplaced_by = _floor_sums(unplaced, row_unit_shares(unplaced))
    area_by: dict[FloorKey, float] = {}
    if not located.empty:
        sizes = located.loc[:, ["Xsize", "Ysize"]].apply(pd.to_numeric, errors="coerce").fillna(0.0)
        area_by = _floor_sums(located, sizes["Xsize"] * sizes["Ysize"])
    placements = []
    for key in FLOOR_KEYS:
        canvas_width, canvas_height = canvas_of(key)
        area = canvas_width * canvas_height
        placements.append(
            FloorPlacement(
                key=key,
                placed=round(placed_by.get(key, 0.0), UNIT_COUNT_DECIMALS),
                unplaced=round(unplaced_by.get(key, 0.0), UNIT_COUNT_DECIMALS),
                occupancy=area_by[key] / area if key in area_by and area > 0 else 0.0,
            )
        )
    return tuple(placements)


def floor_block_stats(
    placements: Collection[FloorPlacement],
    *,
    inactive: Mapping[FloorKey, str] | None = None,
    layout_differences: Mapping[FloorKey, int] | None = None,
    short_lines: Mapping[FloorKey, str] | None = None,
) -> dict[str, dict[str, str | None]]:
    """층 블록 글자(편집기 `data.linkStats`). 키는 블록의 연결(「C1 1F」)이다.

    블록 안에는 배치 대수와, 있으면 미배치 대수만 적는다(점유율은 풍선). 상태별 대수는 넣지
    않는다 — FAB·층 칸은 배치를 센다(2026-10-01 결정). 이 값은 epoch 에 넣지 않는다: 넣으면 기준일만
    바꿔도 편집 중 내용과 실행 취소가 지워진다.

    `inactive` 는 비활성 층 → 사유의 화면 글(`floor_state.inactive_label` — 사람이 직접 적은 글
    20자까지, 옛 코드는 「사용 안 함」·「생산라인 아님」)이다. 그 층 칸에만 `"inactive"` 를 싣는다
    — 편집기가 회색 빗금 + 사유 글자(블록 안은 8글자에서 줄임 — `editor.js` `clipOff`)로 그리고
    보기에서는 열지 않는다. 대수 칸은 그대로 싣는다(풍선).

    `layout_differences` 는 「공식과 견주기」 를 켠 회차의 층 → 공식과 자리가 다른 설비 수다
    (`layout_overlay.unit_differences_by_floor`). 0 보다 큰 층 칸에 `"layout"`(「가정 배치 n대
    다름」)을 싣는다 — 블록 풍선 한 줄이다(설계 8-3).

    `short_lines` 는 색 기준 「필요 단축」 을 켠 동안의 층 → 셋째 줄 글(「단축 3대 · 최대
    −18일」)이다. 그 층 칸에만 `"short"` 를 싣는다 — 끈 동안 칸이 없다(뷰어 payload 그대로). 비활성
    층에는 싣지 않는다 (층 대수를 보이지 않는다 — 층 사용 0029 규칙)."""
    stats: dict[str, dict[str, str | None]] = {}
    for placement in placements:
        cell: dict[str, str | None] = {
            "placed": f"배치 {format_unit_count(placement.placed)}대",
            "unplaced": (
                f"미배치 {format_unit_count(placement.unplaced)}대"
                if placement.unplaced > 0
                else None
            ),
            "occupancy": (f"점유율 {placement.occupancy:.1%}" if placement.placed > 0 else None),
        }
        if inactive and placement.key in inactive:
            cell["inactive"] = inactive[placement.key]
        elif short_lines and placement.key in short_lines:
            cell["short"] = short_lines[placement.key]
        differs = (layout_differences or {}).get(placement.key, 0)
        if differs > 0:
            cell["layout"] = f"가정 배치 {differs:,}대 다름"
        stats[floor_label(placement.key)] = cell
    return stats


def mark_colors() -> dict[str, str]:
    """영역 색 키 → 지금 테마의 색. 검증된 범주 팔레트(제품별 비중과 같은 색)를 그대로 쓴다.
    층·FAB 도면(편집기)이 같은 색을 쓴다."""
    named = dict(zip(MARK_COLOR_KEYS[:-1], tokens.PRODUCT_SHARE_COLORS, strict=False))
    return {**named, MARK_COLOR_KEYS[-1]: tokens.PRODUCT_SHARE_OTHER}


def block_tints() -> dict[str, str]:
    """FAB 층 블록 면색 — 영역 색 키 → 지금 테마의 **불투명** 면.

    영역 색을 `SPACE_BLOCK_TINT_ALPHA` 만큼 캔버스(`SPACE_CANVAS`) 위에 미리 섞는다. 반투명으로
    칠하면 블록 뒤의 도면·격자가 비친다(2026-10-07 사용자 결정 — 색을 고른 블록은 불투명). 바탕을
    블록 기본 면(`SPACE_BLOCK_FILL`)이 아니라 캔버스로 두는 것은, 반투명이던 때 그 색이 캔버스
    위에 얹혀 보였기 때문이다 — 빈 캔버스 위에서는 색이 전과 같다. 편집기가
    `var(--sle-block-tint-<키>)` 로 쓴다(`space_layout_editor._palette`).
    """
    return {
        key: tokens.opaque_mix(color, tokens.SPACE_CANVAS, tokens.SPACE_BLOCK_TINT_ALPHA)
        for key, color in mark_colors().items()
    }


def keep_out_color() -> str:
    """겹침·설비 금지 표시색. 다크의 부족색은 어두운 캔버스에서 1.9:1 로 묻혀 밝은 감소색을 쓴다."""
    return tokens.DELTA_AREA_DECREASE if theme.current_mode() == "dark" else tokens.STATUS_SHORTAGE


# ------------------------------------------------------------------ 호기 상자 색·범례
# 색 기준 그룹 밖의 범례 칸. 그룹 이름(공정구분 여섯·숫자로 읽히는 투자Capa 글자)과 겹치지 않는다.
LEGEND_DEFAULT: Final = "그 밖"
LEGEND_STORAGE: Final = "보관"
LEGEND_DELAY: Final = "지연"
LEGEND_PRE_ARRIVAL: Final = "반입 전"
LEGEND_EXIT_PLANNED: Final = "반출/이설 예정"
LEGEND_STOPPED: Final = "정지 중"
LEGEND_OFFLINE: Final = "운영 비가동"
LEGEND_UNCONFIRMED: Final = "미확인"


@dataclass(frozen=True)
class ColorGroupStyle:
    """색 기준 그룹 하나의 면·글자 색(지금 테마)."""

    label: str
    fill: str
    ink: str


@dataclass(frozen=True)
class ColorChoice:
    """사이드바 「색 기준」과 그룹 체크(2026-10-16 사용자 결정 — 질문 7 권장안).

    `basis` 는 `space_color_basis.COLOR_BASES` 가운데 하나, `capa` 는 설비 마스터 전체에서 만든
    투자Capa 그룹(공정구분 기준이어도 들고 다닌다 — 기준을 바꿔도 같은 그룹이다), `enabled` 는
    체크한 그룹 이름이다.
    """

    basis: str
    capa: tuple[CapaGroup, ...]
    enabled: frozenset[str]

    def styles(self) -> tuple[ColorGroupStyle, ...]:
        """그 기준의 모든 그룹(체크박스 차례)과 색. 필요 단축은 그룹이 없다(색은 단축 구간)."""
        if self.basis == COLOR_BASIS_SHORTENING:
            return ()
        if self.basis == COLOR_BASIS_CAPA:
            return tuple(
                ColorGroupStyle(
                    group.label,
                    tokens.SPACE_CAPA_RAMP[group.level],
                    tokens.SPACE_CAPA_RAMP_INKS[group.level],
                )
                for group in self.capa
            )
        return tuple(
            ColorGroupStyle(
                group, tokens.SPACE_LINE_TYPE_FILLS[group], tokens.SPACE_LINE_TYPE_INKS[group]
            )
            for group in LINE_TYPE_GROUPS
        )

    def checked(self) -> tuple[ColorGroupStyle, ...]:
        """체크한 그룹만(차례 그대로)."""
        return tuple(style for style in self.styles() if style.label in self.enabled)


def default_color_choice(capa: Sequence[CapaGroup] = ()) -> ColorChoice:
    """고를 위젯이 없을 때(호기가 없는 화면)의 기본 — 공정구분, 여섯 그룹 모두 켬."""
    return ColorChoice(COLOR_BASIS_LINE_TYPE, tuple(capa), frozenset(LINE_TYPE_GROUPS))


def _aligned(boundaries: pd.DataFrame, rows: pd.DataFrame) -> pd.DataFrame:
    """`rows` 행 차례의 경계 날짜. `boundaries` 는 `unit_boundaries(rows …)` 처럼 `rows` 의 인덱스를
    모두 품어야 한다(빠진 행이 있으면 KeyError — 다른 표의 경계를 잘못 넘긴 것이다)."""
    return boundaries if boundaries.index.equals(rows.index) else boundaries.loc[rows.index]


def unit_appearance(
    status: pd.DataFrame, boundaries: pd.DataFrame, *, choice: ColorChoice
) -> dict[str, dict[str, Any]]:
    """호기(설비명)마다 브라우저로 보낼 기본 면·글자(`fill`·`ink`)와 경계 날짜(`boundary_payload`).

    `boundaries` 는 `status` 의 경계 날짜(`space_unit_state.unit_boundaries(status, …)`)다 — 층 상세
    회차는 범례 대수(`space_legend_counts`)와 한 번 구한 것을 나눠 쓴다. 면·글자는 색 기준과
    체크만 반영한다 — 체크한 그룹이면 그 그룹 색, 아니면 기본 회색. 지연(빨강)과 보관(검정)은
    기준일을 보는 브라우저가 이 위에 덮는다(`storage`·`delays`). 체크·색 기준을 바꾸면 이 두 칸만
    바뀌어 도면은 같은 epoch 로 색만 다시 칠한다(보던 배율을 지킨다).
    """
    if status.empty or EQUIPMENT_ID_COLUMN not in status.columns:
        return {}
    chosen = {style.label: style for style in choice.checked()}
    groups = color_groups(status, choice.basis, choice.capa)
    payload = boundary_payload(_aligned(boundaries, status))
    names = status[EQUIPMENT_ID_COLUMN].astype("string").str.strip()
    looks: dict[str, dict[str, Any]] = {}
    for name, group, fields in zip(names, groups, payload, strict=True):
        if pd.isna(name):
            continue
        style = None if pd.isna(group) else chosen.get(str(group))
        looks[str(name)] = {
            **fields,
            "fill": style.fill if style is not None else tokens.SPACE_UNIT_DEFAULT_FILL,
            "ink": style.ink if style is not None else tokens.SPACE_UNIT_DEFAULT_INK,
        }
    return looks


def apply_layer_looks(
    looks: Mapping[str, Mapping[str, Any]], layer_looks: Mapping[str, Mapping[str, Any]]
) -> dict[str, dict[str, Any]]:
    """`unit_appearance` 결과에 「필요 단축」 표시(`layer` 구간·`dim`)를 얹는다.

    표시된 호기는 면·글자(`fill`·`ink`)를 비운다 — 브라우저가 `var(--sle-short-<구간>-fill|ink)` 로
    칠해 테마를 따른다. 흐릴 호기에는 `dim` 만 단다. 값이 없는 칸은 싣지 않는다(끈 동안 payload
    그대로).
    """
    out: dict[str, dict[str, Any]] = {}
    for name, look in looks.items():
        merged = dict(look)
        extra = layer_looks.get(name)
        if extra:
            bucket = extra.get("layer")
            if isinstance(bucket, str) and bucket in BUCKETS:
                merged["layer"] = bucket
                merged["fill"] = ""
                merged["ink"] = ""
            if extra.get("dim"):
                merged["dim"] = True
        out[name] = merged
    return out


def fill_kinds(states: pd.DataFrame, groups: pd.Series, enabled: Collection[str]) -> pd.Series:
    """행마다 채우기의 뜻(범례 칸). 지연 → 보관 → 체크한 그룹 → 그 밖, 위가 이긴다."""
    checked = groups.isin(set(enabled)).fillna(False).astype(bool)
    kinds = pd.Series(LEGEND_DEFAULT, index=states.index, dtype="string")
    kinds = kinds.mask(checked, groups.astype("string"))
    kinds = kinds.mask(states[STORAGE_STATE], LEGEND_STORAGE)
    return kinds.mask(states[DELAYED_STATE], LEGEND_DELAY)


def space_legend_counts(
    rows: pd.DataFrame,
    boundaries: pd.DataFrame,
    *,
    choice: ColorChoice,
    as_of: date,
) -> dict[str, float]:
    """층 상세 범례의 기준일 대수. 대수가 있는 칸만 돌려준다.

    `boundaries` 는 `rows` 의 경계 날짜(`space_unit_state.unit_boundaries(rows, …)` — 미확인은 그
    `today` 로 고정)다. `rows` 는 세는 배치 행(`placed_unit_rows` — 모듈 묶음은 상자가 한 행이어도
    모든 행)이고 대수는 설비지분 합이다(상태 범례 때와 같은 셈, 「배치 N대」와 같은 축). 채우기
    칸(그룹·그 밖·보관·지연)은 합이 배치 대수다. 테·덧표시 칸은 따로 센다 — 반입 전(실물 없음),
    반출/이설 예정(실물이 있어 노랑 테인 것), 정지 중, 운영 비가동. **미확인은 설비 수**다(설비키,
    지분으로 나누지 않음 — 확인할 대상의 수라 `schedule_confirmation.confirmation_counts` 와 같은
    셈이고 오늘 기준이라 기준일을 따르지 않는다). 도면에 없는(도면 이탈일이 지난) 행은 세지 않는다.
    칸마다 직접 더한다 — 합계에서 빼면 반올림 끝자리가 -0.0 으로 남아 「-0대」가 찍힌다.
    """
    if rows.empty:
        return {}
    states = unit_states_at(_aligned(boundaries, rows), as_of=as_of)
    shares = row_unit_shares(rows)
    shown = states[VISIBLE_STATE]
    kinds = fill_kinds(states, color_groups(rows, choice.basis, choice.capa), choice.enabled)
    counts: dict[str, float] = {
        str(kind): unit_total(shares.where(shown & kinds.eq(kind).fillna(False).astype(bool), 0.0))
        for kind in kinds.loc[shown].dropna().unique()
    }
    real = states[REAL_STATE]
    marks = {
        LEGEND_PRE_ARRIVAL: ~real,
        LEGEND_EXIT_PLANNED: real & states[EXIT_PLANNED_STATE],
        LEGEND_STOPPED: states[STOPPED_STATE],
        LEGEND_OFFLINE: states[OFFLINE_STATE],
    }
    for label, mask in marks.items():
        counts[label] = unit_total(shares.where(shown & mask, 0.0))
    keys = rows[UNIT_KEY_COLUMN] if UNIT_KEY_COLUMN in rows.columns else rows[EQUIPMENT_ID_COLUMN]
    counts[LEGEND_UNCONFIRMED] = float(keys.loc[shown & states[FLAG_STATE]].nunique())
    return {label: count for label, count in counts.items() if count > 0}


_SWATCH = "display:inline-block;flex:none;box-sizing:border-box;"


def _fill_swatch(fill: str) -> str:
    return (
        f"{_SWATCH}width:11px;height:11px;border-radius:2px;background:{fill};"
        f"border:1px solid {tokens.SPACE_BORDER}"
    )


def _mark_swatches() -> dict[str, tuple[str, str]]:
    """테·덧표시 칸의 견본(꼴, 안 글자). 도면의 테·빗금·표식과 같은 색이다."""
    box = f"{_SWATCH}width:14px;height:10px;border-radius:2px;"
    return {
        # 반입 예정 점선은 도면 테(3.5px)처럼 굵게 — 견본 칸도 3px 이라 2px 칸보다 조금 크다.
        LEGEND_PRE_ARRIVAL: (
            f"{_SWATCH}width:16px;height:11px;border-radius:2px;"
            f"border:3px dashed {tokens.SPACE_RING_PRE_ARRIVAL}",
            "",
        ),
        LEGEND_EXIT_PLANNED: (
            f"{box}border:2px solid {tokens.SPACE_RING_EXIT};"
            f"box-shadow:0 0 0 1px {tokens.SPACE_RING_EXIT_OUTLINE}",
            "",
        ),
        LEGEND_STOPPED: (
            f"{box}border:1px solid {tokens.SPACE_BORDER};background:repeating-linear-gradient("
            f"45deg,{tokens.SPACE_HATCH} 0 1.5px,{tokens.SPACE_UNIT_DEFAULT_FILL} 1.5px 4px)",
            "",
        ),
        LEGEND_OFFLINE: (
            f"{_SWATCH}width:12px;height:12px;border-radius:50%;"
            f"border:1.5px solid {tokens.SPACE_TEXT};background:linear-gradient(90deg,"
            f"{tokens.SURFACE} 28%,{tokens.SPACE_TEXT} 28% 43%,{tokens.SURFACE} 43% 57%,"
            f"{tokens.SPACE_TEXT} 57% 72%,{tokens.SURFACE} 72%)",
            "",
        ),
        LEGEND_UNCONFIRMED: (
            f"{_SWATCH}width:13px;height:13px;border-radius:50%;background:{tokens.SPACE_FLAG_FILL};"
            f"color:{tokens.SPACE_FLAG_INK};font-size:10px;font-weight:700;line-height:13px;"
            "text-align:center",
            "!",
        ),
    }


def space_legend_markup(
    counts: Mapping[str, float] | None,
    *,
    choice: ColorChoice,
    as_of: date | None = None,
    fills: bool = True,
) -> str:
    """층 상세 머리 줄 오른쪽의 범례. 도면 안이 아니라 머리 줄에 두어 도면이 테두리 안을 다 쓴다.

    `counts` 가 있으면(보기) 대수가 있는 칸만 「PKG 5대」로 — 체크한 그룹 색·그 밖·보관·지연,
    그리고 반입 전(주황 점선)·반출/이설 예정(노랑 두 겹)·정지 중(빗금)·운영 비가동·미확인(「!」) —
    끝에 기준일을 단다. `None`(배치 편집 중)이면 채우기 뜻만(체크한 그룹·그 밖·보관·지연) 보인다 —
    편집 화면은 테·덧표시를 그리지 않고, 편집본은 저장본과 대수가 다르다.

    `fills` 가 거짓이면 채우기 칸(그룹·그 밖·보관·지연)을 싣지 않는다 — 색 기준 「필요 단축」 을
    켰는데 계획을 못 읽은 회차는 상자가 모두 기본 회색이고 도면이 지연·보관 면을 칠하지 않는다
    (결정 D12·R5). 그 회차에 「지연 1대」 견본을 세우면 도면에서 찾을 수 없는 빨강이 된다.
    """
    fill_entries = [(style.label, _fill_swatch(style.fill), "") for style in choice.checked()]
    fill_entries += [
        (LEGEND_DEFAULT, _fill_swatch(tokens.SPACE_UNIT_DEFAULT_FILL), ""),
        (LEGEND_STORAGE, _fill_swatch(tokens.SPACE_UNIT_STORAGE_FILL), ""),
        (LEGEND_DELAY, _fill_swatch(tokens.SPACE_UNIT_DELAY_FILL), ""),
    ]
    entries = fill_entries if fills else []
    if counts is not None:
        marks = [(label, swatch, inner) for label, (swatch, inner) in _mark_swatches().items()]
        entries = [entry for entry in entries + marks if counts.get(entry[0], 0) > 0]
    chips = []
    for label, swatch, inner in entries:
        text = label if counts is None else f"{label} {format_unit_count(counts[label])}대"
        chips.append(
            '<span style="display:inline-flex;align-items:center;gap:5px;white-space:nowrap">'
            f'<span aria-hidden="true" style="{swatch}">{html.escape(inner)}</span>'
            f"{html.escape(text)}</span>"
        )
    if counts is not None and as_of is not None:
        chips.append(f'<span style="white-space:nowrap">기준 {as_of.isoformat()}</span>')
    return (
        '<div style="display:flex;flex-wrap:wrap;justify-content:flex-end;align-items:center;'
        f'gap:4px 14px;font-size:0.82rem;color:{tokens.TEXT_MUTED}">{"".join(chips)}</div>'
    )


def _legend_chip(swatch: str, inner: str, text: str) -> str:
    return (
        '<span style="display:inline-flex;align-items:center;gap:5px;white-space:nowrap">'
        f'<span aria-hidden="true" style="{swatch}">{html.escape(inner)}</span>'
        f"{html.escape(text)}</span>"
    )


def shortening_legend_markup(
    counts: Mapping[str, int],
    mark_counts: Mapping[str, float],
    *,
    as_of: date,
    dim: bool = True,
) -> str:
    """색 기준 「필요 단축」 을 켠 층 상세 머리 줄 범례 — 구간 넷의 대수(설비 대수 — 모듈 묶음 한
    대, `counts` 는 「이 층에서 단축할 호기」 목록과 같은 축)·임박 테·「흐림 = 단축 없음」, 그리고
    지금의 테·덧표시 칸(반입 전·반출/이설 예정·정지 중·운영 비가동·미확인 — `space_legend_counts` 의
    그 칸)과 기준일. 「흐림」 칸은 `dim`(단축 없는 호기 흐리게)을 켰을 때만 선다. 채우기 칸(그룹·그
    밖·보관·지연)은 싣지 않는다 — 켠 동안 도면은 지연·보관 면을 칠하지 않는다 (결정 D12 — 풍선
    글로만)."""
    chips = [
        _legend_chip(
            _fill_swatch(tokens.SPACE_SHORT_FILLS[bucket]),
            "",
            f"{BUCKET_LABELS[bucket]} {counts[bucket]}대",
        )
        for bucket in BUCKETS
        if counts.get(bucket, 0) > 0
    ]
    chips.append(
        _legend_chip(
            f"{_SWATCH}width:14px;height:10px;border-radius:5px;"
            f"border:2px solid {tokens.SPACE_SHORT_IMMINENT};"
            f"background:{tokens.SPACE_SHORT_FILLS['s']}",
            "",
            "임박 테",
        )
    )
    if dim:
        chips.append(
            _legend_chip(
                _fill_swatch(tokens.SPACE_UNIT_DEFAULT_FILL)
                + f";opacity:{tokens.SPACE_SHORT_DIM_OPACITY}",
                "",
                "흐림 = 단축 없음",
            )
        )
    for label, (swatch, inner) in _mark_swatches().items():
        if mark_counts.get(label, 0) > 0:
            chips.append(
                _legend_chip(swatch, inner, f"{label} {format_unit_count(mark_counts[label])}대")
            )
    chips.append(f'<span style="white-space:nowrap">기준 {as_of.isoformat()}</span>')
    return (
        '<div style="display:flex;flex-wrap:wrap;justify-content:flex-end;align-items:center;'
        f'gap:4px 14px;font-size:0.82rem;color:{tokens.TEXT_MUTED}">{"".join(chips)}</div>'
    )


def widget_key_class(key: str) -> str:
    """Streamlit 이 key 있는 요소에 다는 클래스(`st-key-<key>`, 영문·숫자·_·- 밖의 글자는 `-`)."""
    return "st-key-" + re.sub(r"[^a-zA-Z0-9_-]", "-", key.strip())


def color_check_style(swatches: Sequence[tuple[str, str]]) -> str:
    """사이드바 그룹 체크박스 글자 앞에 그 그룹 색 견본을 단다(`(위젯 key, 면색)`).

    라벨이 아니라 CSS 로 단다 — 체크박스 라벨은 마크다운이라 색 칸을 넣을 수 없다. **비공식 경로다**
    (`stMarkdownContainer`) — 판올림에서 바뀌면 견본이 안 보일 뿐 체크는 그대로다.
    """
    if not swatches:
        return "<style></style>"
    selectors = [
        f'.{widget_key_class(key)} [data-testid="stMarkdownContainer"] p::before'
        for key, _ in swatches
    ]
    rules = [
        f"{selector} {{ background: {fill}; }}"
        for selector, (_, fill) in zip(selectors, swatches, strict=True)
    ]
    return (
        "<style>\n"
        + ",\n".join(selectors)
        + ' {\n  content: "";\n  display: inline-block;\n  width: 0.8em;\n  height: 0.8em;\n'
        "  margin-right: 0.4em;\n  border-radius: 2px;\n"
        f"  border: 1px solid {tokens.SPACE_BORDER};\n"
        "  box-sizing: border-box;\n  vertical-align: -0.08em;\n}\n"
        + "\n".join(rules)
        + "\n</style>"
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


# 층 상세 아래 호기 표의 칸 — 요청한 차례 그대로(2026-10-23 사용자 요청 3). 칸 이름은 설비
# 마스터 그대로다: 요청의 「Qual 실적」 은 `Qual실적`, 「반입/Qual일정」 은 `반입/Qual 이력`,
# 「단계」 는 기준일(페이더)의 상태 글자 `단계`(`build_space_equipment_status` 가 `상태` 를 옮겨
# 적은 칸 — 도면 상자의 단계 이름과 같다)다. 층 CSV 는 이 표가 아니라 모든 칸이다(현장 배치
# 검토용).
FLOOR_TABLE_COLUMNS: Final = (
    "Area Code",
    "공정소분류",
    EQUIPMENT_ID_COLUMN,
    "공정구분",
    "투자Capa",
    "투자구분",
    "사용기준",
    "동",
    "층",
    "제진대일정",
    "물류일정",
    "반입일정",
    "반입실적",
    "반입상태",
    "Qual일정",
    "Qual실적",
    "Qual상태",
    "정지일정",
    "반출/이설일정",
    "반입/Qual 이력",
    "단계",
)


def floor_table(rows: pd.DataFrame) -> pd.DataFrame:
    """층 상세 아래 호기 표 — `FLOOR_TABLE_COLUMNS` 의 칸만 그 차례로(없는 칸은 건너뛴다)."""
    return rows.loc[:, [column for column in FLOOR_TABLE_COLUMNS if column in rows.columns]]


def picked_unit_rows(rows: pd.DataFrame, unit_id: str) -> pd.DataFrame:
    """층 상세 도면에서 누른 호기의 줄(2026-10-23 사용자 결정 — 누른 설비 줄만).

    Main 설비 모듈이면 그 Main 설비의 줄 전부이고 누른 모듈이 첫 줄, 나머지는 설비명 자연 정렬이다
    (`rows` 는 그 층의 행 — 좌표 없는 형제·레이아웃표시 N 모듈도 그 설비의 설비 마스터 행이라
    든다). 설비명은 앞뒤 공백을 걷고 견준다. 누른 호기가 없으면 빈 표다."""
    names = rows[EQUIPMENT_ID_COLUMN].astype("string").str.strip()
    hit = names.eq(unit_id).fillna(False).astype(bool)
    if not hit.any():
        return rows.iloc[0:0]
    if PARENT_EQUIPMENT_COLUMN in rows.columns:
        parents = rows[PARENT_EQUIPMENT_COLUMN].astype("string").str.strip()
        parent = parents[hit].iloc[0]
        if not pd.isna(parent) and parent:
            hit |= parents.eq(parent).fillna(False).astype(bool)
    order = sorted(
        rows.index[hit],
        key=lambda index: (names[index] != unit_id, natural_name_key(str(names[index]))),
    )
    return rows.loc[order]
