# Purpose: 설비 마스터·기존 보유대수·비가동 일정 입력을 정규화하고 검증한다.

"""설비 마스터·기존 보유대수·비가동 일정 입력을 정규화하고 검증한다."""

from __future__ import annotations

import pandas as pd

from capa_simulation.services.equipment_contract import (
    BASELINE_COLUMNS,
    BASELINE_KEY_COLUMNS,
    COORDINATE_COLUMNS,
    DATE_COLUMNS,
    DOWNTIME_COLUMNS,
    DOWNTIME_KEY_COLUMNS,
    EQUIPMENT_COLUMNS,
    FLAG_COLUMNS,
    QUAL_CONFIRMATION_STATUSES,
    REFERENCE_TEXT_COLUMNS,
    VALID_BUILDINGS,
    VALID_FLOORS,
    empty_downtime_schedule,
    empty_equipment_baseline,
    empty_equipment_master,
)
from capa_simulation.services.floor_layout_profile import (
    DEFAULT_CANVAS_HEIGHT,
    DEFAULT_CANVAS_WIDTH,
    FloorCanvasMap,
)
from capa_simulation.services.frame_contracts import require_columns


def prepare_equipment_baseline(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize aggregate counts for unidentified legacy equipment."""
    require_columns(data, BASELINE_COLUMNS, "기존 보유대수")
    result = data.loc[:, BASELINE_COLUMNS].copy()
    result = _drop_blank_rows(result, ("공정", "분류", "기존보유대수"))
    if result.empty:
        return empty_equipment_baseline()
    _normalize_required_text(result, BASELINE_KEY_COLUMNS, "기존 보유대수")
    counts = pd.to_numeric(result["기존보유대수"], errors="coerce")
    if not (counts.notna() & counts.ge(0)).all():
        raise ValueError("기존보유대수는 0 이상의 숫자여야 합니다.")
    result["기존보유대수"] = counts.astype("float64")
    result["비고"] = _optional_text(result["비고"])
    duplicated = result.duplicated(list(BASELINE_KEY_COLUMNS), keep=False)
    if duplicated.any():
        examples = _key_examples(result.loc[duplicated], BASELINE_KEY_COLUMNS)
        raise ValueError(f"기존 보유대수의 공정·분류가 중복되었습니다: {examples}")
    return result.reset_index(drop=True)


def prepare_equipment_master(
    data: pd.DataFrame,
    *,
    floor_canvases: FloorCanvasMap | None = None,
) -> pd.DataFrame:
    """호기 마스터 30컬럼 계약을 정규화하고 검증한다.

    `floor_canvases` 를 넘기면 층별 캔버스 폭·높이를 상한으로 좌표를 검사한다. 넘기지
    않으면 상한 검사를 건너뛴다 — 이미 저장된 리비전은 캔버스가 줄어든 뒤에도 열려야 한다.
    """
    require_columns(data, EQUIPMENT_COLUMNS, "호기 마스터")
    result = data.loc[:, EQUIPMENT_COLUMNS].copy()
    result = _drop_blank_rows(result, ("호기",))
    if result.empty:
        return empty_equipment_master()

    _normalize_required_text(result, ("호기", "공정소분류"), "호기 마스터")
    for column in REFERENCE_TEXT_COLUMNS + ("동", "층"):
        result[column] = _optional_text(result[column])
    result["확정상태"] = _optional_text(result["확정상태"])
    duplicated = result["호기"].duplicated(keep=False)
    if duplicated.any():
        examples = result.loc[duplicated, "호기"].drop_duplicates().head(5).tolist()
        raise ValueError(f"호기는 중복될 수 없습니다: {examples}")

    for column in FLAG_COLUMNS:
        result[column] = result[column].astype("string").str.strip().str.upper()
        invalid = ~result[column].isin(["Y", "N"])
        if invalid.any():
            examples = result.loc[invalid, "호기"].head(5).tolist()
            raise ValueError(f"{column}는 Y 또는 N이어야 합니다: {examples}")

    for column in COORDINATE_COLUMNS:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    _validate_locations_and_coordinates(result, floor_canvases)

    for column in DATE_COLUMNS:
        result[column] = _normalize_date(result[column], column)
    ordinary = result["장기보관여부"].eq("N") & result["기존설비여부"].eq("N")
    missing_required_dates = ordinary & (result["입고일정"].isna() | result["Qual일정"].isna())
    if missing_required_dates.any():
        examples = result.loc[missing_required_dates, "호기"].head(5).tolist()
        raise ValueError(
            f"장기보관·기존설비가 아닌 호기는 입고일정과 Qual일정이 필수입니다: {examples}"
        )
    missing_confirmation = ordinary & result["확정상태"].isna()
    if missing_confirmation.any():
        examples = result.loc[missing_confirmation, "호기"].head(5).tolist()
        raise ValueError(f"장기보관·기존설비가 아닌 호기는 Qual 확정상태가 필수입니다: {examples}")
    invalid_confirmation = result["확정상태"].notna() & ~result["확정상태"].isin(
        QUAL_CONFIRMATION_STATUSES
    )
    if invalid_confirmation.any():
        examples = result.loc[invalid_confirmation, "호기"].head(5).tolist()
        raise ValueError(f"확정상태는 계획·확정·완료·지연 중 하나여야 합니다: {examples}")
    invalid_setup_order = (
        result["입고일정"].notna()
        & result["Qual일정"].notna()
        & result["Qual일정"].lt(result["입고일정"])
    )
    invalid_pre_arrival = _invalid_optional_order(result, ("제진대일정", "물류일정", "입고일정"))
    if (invalid_setup_order | invalid_pre_arrival).any():
        examples = result.loc[invalid_setup_order | invalid_pre_arrival, "호기"].head(5).tolist()
        raise ValueError(f"제진대·물류·입고·Qual 일정 순서가 올바르지 않습니다: {examples}")
    both_exit_dates = result["반출일정"].notna() & result["이설일"].notna()
    if both_exit_dates.any():
        examples = result.loc[both_exit_dates, "호기"].head(5).tolist()
        raise ValueError(f"반출일정과 이설일은 동시에 입력할 수 없습니다: {examples}")
    for exit_column in ("반출일정", "이설일"):
        before_arrival = (
            result[exit_column].notna()
            & result["입고일정"].notna()
            & result[exit_column].lt(result["입고일정"])
        )
        if before_arrival.any():
            examples = result.loc[before_arrival, "호기"].head(5).tolist()
            raise ValueError(f"{exit_column}은 입고일정보다 빠를 수 없습니다: {examples}")
    return result.reset_index(drop=True)


def prepare_downtime_schedule(
    data: pd.DataFrame,
    *,
    equipment: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Normalize downtime intervals keyed by equipment, type, and start date."""
    require_columns(data, DOWNTIME_COLUMNS, "비가동 일정")
    result = data.loc[:, DOWNTIME_COLUMNS].copy()
    result = _drop_blank_rows(result, DOWNTIME_KEY_COLUMNS)
    if result.empty:
        return empty_downtime_schedule()
    _normalize_required_text(result, ("호기", "비가동유형"), "비가동 일정")
    for column in ("상세사유", "비고"):
        result[column] = _optional_text(result[column])
    result["시작일"] = _normalize_date(result["시작일"], "시작일")
    result["종료일"] = _normalize_date(result["종료일"], "종료일")
    if result["시작일"].isna().any():
        raise ValueError("모든 비가동 일정에 시작일을 입력해야 합니다.")
    duplicated = result.duplicated(list(DOWNTIME_KEY_COLUMNS), keep=False)
    if duplicated.any():
        examples = _key_examples(result.loc[duplicated], DOWNTIME_KEY_COLUMNS)
        raise ValueError(f"호기·비가동유형·시작일이 중복되었습니다: {examples}")
    invalid_end = result["종료일"].notna() & result["종료일"].lt(result["시작일"])
    if invalid_end.any():
        examples = _key_examples(result.loc[invalid_end], DOWNTIME_KEY_COLUMNS)
        raise ValueError(f"비가동 종료일은 시작일보다 빠를 수 없습니다: {examples}")
    if equipment is not None:
        prepared_equipment = prepare_equipment_master(equipment)
        _validate_downtime_equipment(result, prepared_equipment)
    return result.reset_index(drop=True)


def _validate_downtime_equipment(
    prepared_downtime: pd.DataFrame,
    prepared_equipment: pd.DataFrame,
) -> None:
    unknown = prepared_downtime.loc[
        ~prepared_downtime["호기"].isin(prepared_equipment["호기"]), "호기"
    ]
    if not unknown.empty:
        examples = unknown.drop_duplicates().head(5).tolist()
        raise ValueError(f"호기 마스터에 없는 설비의 비가동 일정이 있습니다: {examples}")


def prepare_downtime_for_prepared_equipment(
    downtime: pd.DataFrame,
    prepared_equipment: pd.DataFrame,
) -> pd.DataFrame:
    """Validate downtime against an equipment frame normalized by this module."""
    prepared_downtime = prepare_downtime_schedule(downtime)
    _validate_downtime_equipment(prepared_downtime, prepared_equipment)
    return prepared_downtime


def _validate_locations_and_coordinates(
    result: pd.DataFrame,
    floor_canvases: FloorCanvasMap | None,
) -> None:
    layout = result["레이아웃표시"].eq("Y")
    missing_location = layout & (
        result["동"].isna()
        | result["층"].isna()
        | result.loc[:, COORDINATE_COLUMNS].isna().any(axis=1)
    )
    if missing_location.any():
        examples = result.loc[missing_location, "호기"].head(5).tolist()
        raise ValueError(
            f"레이아웃표시 Y 호기는 동·층·좌표·크기를 모두 입력해야 합니다: {examples}"
        )
    invalid_building = result["동"].notna() & ~result["동"].isin(VALID_BUILDINGS)
    invalid_floor = result["층"].notna() & ~result["층"].isin(VALID_FLOORS)
    if (invalid_building | invalid_floor).any():
        examples = result.loc[invalid_building | invalid_floor, "호기"].head(5).tolist()
        raise ValueError(f"동은 C1~C5, 층은 1F~6F 범위여야 합니다: {examples}")
    coordinate_present = result.loc[:, COORDINATE_COLUMNS].notna()
    incomplete = coordinate_present.any(axis=1) & ~coordinate_present.all(axis=1)
    if incomplete.any():
        examples = result.loc[incomplete, "호기"].head(5).tolist()
        raise ValueError(f"Space 좌표와 Xsize·Ysize는 함께 입력해야 합니다: {examples}")
    complete = coordinate_present.all(axis=1)
    invalid = complete & (
        result["X좌표"].lt(0)
        | result["Y좌표"].lt(0)
        | result["Xsize"].le(0)
        | result["Ysize"].le(0)
    )
    if invalid.any():
        examples = result.loc[invalid, "호기"].head(5).tolist()
        raise ValueError(f"Space 좌표는 0 이상, 크기는 0 초과여야 합니다: {examples}")
    if floor_canvases is None:
        return
    limit_width, limit_height = _canvas_limits(result, floor_canvases)
    outside = complete & (
        result["X좌표"].add(result["Xsize"]).gt(limit_width)
        | result["Y좌표"].add(result["Ysize"]).gt(limit_height)
    )
    if outside.any():
        examples = result.loc[outside, "호기"].head(5).tolist()
        raise ValueError(f"Space 블럭이 층 캔버스 범위를 벗어났습니다: {examples}")


def _canvas_limits(
    result: pd.DataFrame,
    floor_canvases: FloorCanvasMap,
) -> tuple[pd.Series, pd.Series]:
    width = pd.Series(DEFAULT_CANVAS_WIDTH, index=result.index, dtype="float64")
    height = pd.Series(DEFAULT_CANVAS_HEIGHT, index=result.index, dtype="float64")
    for (building, floor), (canvas_width, canvas_height) in floor_canvases.items():
        matched = result["동"].eq(building) & result["층"].eq(floor)
        width = width.mask(matched, canvas_width)
        height = height.mask(matched, canvas_height)
    return width, height


def _invalid_optional_order(data: pd.DataFrame, columns: tuple[str, ...]) -> pd.Series:
    invalid = pd.Series(False, index=data.index)
    for left, right in zip(columns, columns[1:], strict=False):
        invalid |= data[left].notna() & data[right].notna() & data[right].lt(data[left])
    return invalid


def _drop_blank_rows(data: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    present = pd.DataFrame(index=data.index)
    for column in columns:
        values = data[column]
        present[column] = values.notna() & values.astype("string").str.strip().ne("")
    return data.loc[present.any(axis=1)].copy()


def _normalize_required_text(data: pd.DataFrame, columns: tuple[str, ...], label: str) -> None:
    for column in columns:
        data[column] = data[column].astype("string").str.strip()
        invalid = data[column].isna() | data[column].eq("")
        if invalid.any():
            raise ValueError(f"{label}의 {column}에 누락값이 있습니다.")


def _optional_text(series: pd.Series) -> pd.Series:
    result = series.astype("string").str.strip()
    return result.mask(result.eq(""))


def _normalize_date(series: pd.Series, label: str) -> pd.Series:
    missing = series.isna() | series.astype("string").str.strip().eq("")
    converted = pd.to_datetime(series.mask(missing), errors="coerce")
    invalid = ~missing & converted.isna()
    if invalid.any():
        examples = series.loc[invalid].head(5).tolist()
        raise ValueError(f"{label}은 날짜 형식이어야 합니다: {examples}")
    return converted.dt.normalize()


def _key_examples(data: pd.DataFrame, columns: tuple[str, ...]) -> list[str]:
    return (
        data.loc[:, columns]
        .astype("string")
        .agg(" / ".join, axis=1)
        .drop_duplicates()
        .head(5)
        .tolist()
    )
