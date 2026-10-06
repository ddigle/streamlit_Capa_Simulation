# Purpose: 설비 마스터·기존 보유대수·비가동 일정 입력을 정규화하고 검증한다.

"""설비 마스터·기존 보유대수·비가동 일정 입력을 정규화하고 검증한다."""

from __future__ import annotations

from typing import Any

import pandas as pd

from capa_simulation.services.equipment_contract import (
    ARRIVAL_DATE_COLUMN,
    BASELINE_COLUMNS,
    BASELINE_KEY_COLUMNS,
    CONVERSION_RATIO_COLUMN,
    COORDINATE_COLUMNS,
    DATE_COLUMNS,
    DEFAULT_CONVERSION_RATIO,
    DOWNTIME_COLUMNS,
    DOWNTIME_KEY_COLUMNS,
    EQUIPMENT_COLUMNS,
    EQUIPMENT_ID_COLUMN,
    FLAG_COLUMNS,
    PARENT_EQUIPMENT_COLUMN,
    QUAL_CONFIRMATION_STATUSES,
    REFERENCE_TEXT_COLUMNS,
    RELOCATION_DATE_COLUMN,
    STORAGE_FLAG_COLUMN,
    UNIT_CONSISTENT_COLUMNS,
    VALID_BUILDINGS,
    VALID_FLOORS,
    empty_downtime_schedule,
    empty_equipment_baseline,
    empty_equipment_master,
    with_optional_equipment_columns,
)
from capa_simulation.services.floor_layout_profile import (
    CANVAS_DECIMALS,
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
    invalid_counts = ~(counts.notna() & counts.ge(0))
    if invalid_counts.any():
        examples = _key_examples(result.loc[invalid_counts], BASELINE_KEY_COLUMNS)
        raise ValueError(f"기존보유대수는 0 이상의 숫자여야 합니다: {examples}")
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
    """호기 마스터 36컬럼 계약을 정규화하고 검증한다. 선택 컬럼은 없으면 빈 칸이다
    (`OPTIONAL_EQUIPMENT_COLUMNS`).

    `floor_canvases` 를 넘기면 층별 캔버스 폭·높이를 상한으로 좌표를 검사한다. 넘기지
    않으면 상한 검사를 건너뛴다 — 이미 저장된 리비전은 캔버스가 줄어든 뒤에도 열려야 한다.
    """
    data = with_optional_equipment_columns(data)
    require_columns(data, EQUIPMENT_COLUMNS, "호기 마스터")
    result = data.loc[:, EQUIPMENT_COLUMNS].copy()
    result = _drop_blank_rows(result, (EQUIPMENT_ID_COLUMN,))
    if result.empty:
        return empty_equipment_master()

    _normalize_required_text(result, (EQUIPMENT_ID_COLUMN, "공정소분류"), "호기 마스터")
    for column in REFERENCE_TEXT_COLUMNS + ("동", "층"):
        result[column] = _optional_text(result[column])
    result["확정상태"] = _optional_text(result["확정상태"])
    result[PARENT_EQUIPMENT_COLUMN] = _optional_text(result[PARENT_EQUIPMENT_COLUMN])
    duplicated = result[EQUIPMENT_ID_COLUMN].duplicated(keep=False)
    if duplicated.any():
        examples = result.loc[duplicated, EQUIPMENT_ID_COLUMN].drop_duplicates().head(5).tolist()
        raise ValueError(f"설비명은 중복될 수 없습니다: {examples}")
    _validate_unit_groups(result)

    for column in FLAG_COLUMNS:
        result[column] = result[column].astype("string").str.strip().str.upper()
        invalid = ~result[column].isin(["Y", "N"])
        if invalid.any():
            examples = result.loc[invalid, EQUIPMENT_ID_COLUMN].head(5).tolist()
            raise ValueError(f"{column}는 Y 또는 N이어야 합니다: {examples}")

    for column in COORDINATE_COLUMNS:
        result[column] = _readable_number(result, column)
    _validate_locations_and_coordinates(result, floor_canvases)
    result[CONVERSION_RATIO_COLUMN] = _normalize_conversion_ratio(result)

    for column in DATE_COLUMNS:
        result[column] = _normalize_date(result[column], column)
    # 반입·Qual 일정은 비워도 된다(2026-10-06 사용자 결정) — 반입이 비면 「입고 예정」, 반입만 있고
    # Qual 이 비면 「셋업 진행중」에 머물러 날짜가 들어올 때까지 가용대수에 들지 않는다. 확정상태는
    # Qual 일정의 실행관리 값이라 Qual일정이 있는 신규 호기에만 필수다.
    ordinary = result[STORAGE_FLAG_COLUMN].eq("N") & result["기존설비여부"].eq("N")
    missing_confirmation = ordinary & result["Qual일정"].notna() & result["확정상태"].isna()
    if missing_confirmation.any():
        examples = result.loc[missing_confirmation, EQUIPMENT_ID_COLUMN].head(5).tolist()
        raise ValueError(
            f"Qual일정이 있는 호기(보관·기존설비 제외)는 Qual 확정상태가 필수입니다: {examples}"
        )
    invalid_confirmation = result["확정상태"].notna() & ~result["확정상태"].isin(
        QUAL_CONFIRMATION_STATUSES
    )
    if invalid_confirmation.any():
        examples = result.loc[invalid_confirmation, EQUIPMENT_ID_COLUMN].head(5).tolist()
        raise ValueError(f"확정상태는 계획·확정·완료·지연 중 하나여야 합니다: {examples}")
    invalid_setup_order = (
        result[ARRIVAL_DATE_COLUMN].notna()
        & result["Qual일정"].notna()
        & result["Qual일정"].lt(result[ARRIVAL_DATE_COLUMN])
    )
    invalid_pre_arrival = _invalid_optional_order(
        result, ("제진대일정", "물류일정", ARRIVAL_DATE_COLUMN)
    )
    if (invalid_setup_order | invalid_pre_arrival).any():
        examples = (
            result.loc[invalid_setup_order | invalid_pre_arrival, EQUIPMENT_ID_COLUMN]
            .head(5)
            .tolist()
        )
        raise ValueError(f"제진대·물류·반입·Qual 일정 순서가 올바르지 않습니다: {examples}")
    both_exit_dates = result["반출일정"].notna() & result[RELOCATION_DATE_COLUMN].notna()
    if both_exit_dates.any():
        examples = result.loc[both_exit_dates, EQUIPMENT_ID_COLUMN].head(5).tolist()
        raise ValueError(
            f"반출일정과 {RELOCATION_DATE_COLUMN}은 동시에 입력할 수 없습니다: {examples}"
        )
    for exit_column in ("반출일정", RELOCATION_DATE_COLUMN):
        before_arrival = (
            result[exit_column].notna()
            & result[ARRIVAL_DATE_COLUMN].notna()
            & result[exit_column].lt(result[ARRIVAL_DATE_COLUMN])
        )
        if before_arrival.any():
            examples = result.loc[before_arrival, EQUIPMENT_ID_COLUMN].head(5).tolist()
            raise ValueError(f"{exit_column}은 반입일정보다 빠를 수 없습니다: {examples}")
    return result.reset_index(drop=True)


def _validate_unit_groups(result: pd.DataFrame) -> None:
    """Main 설비로 묶은 모듈 행이 한 설비로 셀 수 있는 모양인지 본다.

    - Main 설비는 다른 행의 설비명과 같을 수 없다. 설비 행(APW01)과 모듈 행(APW01A~D)을 함께
      두면 같은 설비가 두 번 세어진다.
    - 한 설비의 모듈 행끼리 공정·공정구분·투자구분·동·층이 같아야 한다. 화면 필터가 이 값들로
      행을 거르므로, 다르면 필터가 설비를 쪼개 지분 합이 1 이 아니게 된다.
    """
    parents = result[PARENT_EQUIPMENT_COLUMN]
    named = parents.notna()
    if not named.any():
        return
    # 자기 호기를 적은 것은 무해하다(묶음 1행 = 지분 1). 다른 행의 호기를 가리킬 때만 막는다.
    units = result[EQUIPMENT_ID_COLUMN].astype("string")
    colliding = named & parents.isin(set(units)) & parents.ne(units)
    if colliding.any():
        examples = parents.loc[colliding].drop_duplicates().head(5).tolist()
        raise ValueError(
            "Main 설비는 다른 행의 설비명과 같을 수 없습니다 — 설비 행과 모듈 행을 함께 두면 "
            f"같은 설비가 두 번 세어집니다. 설비 행을 지우고 모듈 행만 남기세요: {examples}"
        )
    keys = parents.where(named, result[EQUIPMENT_ID_COLUMN])
    for column in UNIT_CONSISTENT_COLUMNS:
        values = result[column].astype("string").fillna("")
        mixed = values.groupby(keys).nunique().gt(1)
        if mixed.any():
            examples = mixed.loc[mixed].index.tolist()[:5]
            raise ValueError(f"같은 Main 설비의 모듈 행은 {column} 이 같아야 합니다: {examples}")


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
    _normalize_required_text(result, (EQUIPMENT_ID_COLUMN, "비가동유형"), "비가동 일정")
    for column in ("상세사유", "비고"):
        result[column] = _optional_text(result[column])
    result["시작일"] = _normalize_date(result["시작일"], "시작일")
    result["종료일"] = _normalize_date(result["종료일"], "종료일")
    if result["시작일"].isna().any():
        raise ValueError("모든 비가동 일정에 시작일을 입력해야 합니다.")
    duplicated = result.duplicated(list(DOWNTIME_KEY_COLUMNS), keep=False)
    if duplicated.any():
        examples = _key_examples(result.loc[duplicated], DOWNTIME_KEY_COLUMNS)
        raise ValueError(f"설비명·비가동유형·시작일이 중복되었습니다: {examples}")
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
        ~prepared_downtime[EQUIPMENT_ID_COLUMN].isin(prepared_equipment[EQUIPMENT_ID_COLUMN]),
        EQUIPMENT_ID_COLUMN,
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
    """Space 위치 계약.

    레이아웃표시는 「도면 대상인가」만 가른다 — Y 인데 좌표가 없으면 Space 편집기의 미배치
    트레이에 뜨고, 동·층까지 비면 모든 층 트레이에 뜬다. 크기만 있고 X·Y 가 없는 행도 받는다
    (트레이로 빼도 실제 설비 치수를 지킨다, 2026-10-01 사용자 결정).

    - X좌표·Y좌표는 함께, Xsize·Ysize 도 함께 넣거나 비운다.
    - X·Y 가 있으면 크기도 있어야 한다. 레이아웃표시 Y 면 동·층도 있어야 한다. N 행은 예전처럼
      동·층 없이 좌표만 있어도 받는다 — 그런 행이 든 리비전이 다시 읽힐 때 막히지 않게.
    - 부호는 있는 값마다 본다(X·Y ≥ 0, 크기 > 0). 캔버스 상한은 X·Y 가 있는 행에만 건다.

    과거 리비전을 다시 읽을 때도 이 검사를 탄다. 그래서 **풀기만 하고 다시 조이지 않는다** —
    조이면 그 사이에 저장된 리비전이 열리지 않는다.
    """
    invalid_building = result["동"].notna() & ~result["동"].isin(VALID_BUILDINGS)
    invalid_floor = result["층"].notna() & ~result["층"].isin(VALID_FLOORS)
    if (invalid_building | invalid_floor).any():
        examples = (
            result.loc[invalid_building | invalid_floor, EQUIPMENT_ID_COLUMN].head(5).tolist()
        )
        raise ValueError(f"동은 C1~C5, 층은 1F~6F 범위여야 합니다: {examples}")
    position = result.loc[:, ["X좌표", "Y좌표"]].notna()
    size = result.loc[:, ["Xsize", "Ysize"]].notna()
    has_position = position.all(axis=1)
    has_size = size.all(axis=1)
    missing_location = result["동"].isna() | result["층"].isna()
    rules = (
        (position.any(axis=1) & ~has_position, "X좌표·Y좌표는 함께 넣거나 함께 비워야 합니다"),
        (size.any(axis=1) & ~has_size, "Xsize·Ysize는 함께 넣거나 함께 비워야 합니다"),
        (has_position & ~has_size, "Space 좌표(X좌표·Y좌표)가 있으면 Xsize·Ysize 도 넣어야 합니다"),
        (
            has_position & result["레이아웃표시"].eq("Y") & missing_location,
            "레이아웃표시 Y 호기에 좌표를 넣으면 동·층도 넣어야 합니다",
        ),
        (
            has_position & (result["X좌표"].lt(0) | result["Y좌표"].lt(0)),
            "Space 좌표(X좌표·Y좌표)는 0 이상이어야 합니다",
        ),
        (
            has_size & (result["Xsize"].le(0) | result["Ysize"].le(0)),
            "Xsize·Ysize는 0 보다 커야 합니다",
        ),
    )
    for broken, message in rules:
        if broken.any():
            examples = result.loc[broken, EQUIPMENT_ID_COLUMN].head(5).tolist()
            raise ValueError(f"{message}: {examples}")
    complete = has_position & has_size
    if floor_canvases is None:
        return
    limit_width, limit_height = _canvas_limits(result, floor_canvases)
    # 끝 좌표는 저장 정밀도로 반올림해 견준다. 편집기가 캔버스 끝에 붙여 놓은 호기(88.7 + 11.3)가
    # 부동소수 합(100.00000000000001)으로 「밖」이 되지 않게 — 푸는 쪽이라 과거 리비전도 열린다.
    outside = complete & (
        result["X좌표"].add(result["Xsize"]).round(CANVAS_DECIMALS).gt(limit_width)
        | result["Y좌표"].add(result["Ysize"]).round(CANVAS_DECIMALS).gt(limit_height)
    )
    if outside.any():
        raise ValueError(_outside_canvas_message(result, outside, complete, floor_canvases))


def _outside_canvas_message(
    result: pd.DataFrame,
    outside: pd.Series,
    complete: pd.Series,
    floor_canvases: FloorCanvasMap,
) -> str:
    """캔버스를 벗어난 호기를 동·층별로 묶어 **원인과 고칠 곳**까지 적는다.

    누가 층 캔버스를 줄여 두면, 뒤에 다른 사람이 무관한 기존보유대수 한 칸만 고쳐 저장해도
    호기 마스터 전체 검증이 이 오류로 막힌다. 예전 문구는 호기 이름만 적어서 원인이 캔버스
    라는 것도, 어디서 고치는지도 알 수 없었다(2026-09-29 버그 보고). 검사 범위는 그대로
    두고(바뀐 행만 보면 검증이 약해진다) 문구만 넓힌다 — 층 이름·캔버스 크기·그 층 호기를
    담는 데 필요한 크기·해결 방법.
    """
    floors: list[str] = []
    outside_rows = result.loc[outside]
    for (raw_building, raw_floor), rows in outside_rows.groupby(
        ["동", "층"], dropna=False, sort=True
    ):
        building, floor = _text_or_none(raw_building), _text_or_none(raw_floor)
        unplaced = building is None or floor is None
        stored = None if unplaced else floor_canvases.get((str(building), str(floor)))
        width, height = (
            stored if stored is not None else (DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT)
        )
        on_floor = complete & _same_value(result["동"], building) & _same_value(result["층"], floor)
        right = result.loc[on_floor, "X좌표"].add(result.loc[on_floor, "Xsize"]).max()
        top = result.loc[on_floor, "Y좌표"].add(result.loc[on_floor, "Ysize"]).max()
        need_width = max(width, round(float(right), CANVAS_DECIMALS))
        need_height = max(height, round(float(top), CANVAS_DECIMALS))
        label = "동·층 미지정" if unplaced else f"{building} {floor}"
        source = "" if stored is not None else "(저장된 캔버스 없음 · 기본값)"
        examples = rows[EQUIPMENT_ID_COLUMN].head(5).tolist()
        floors.append(
            f"{label} 캔버스 {width:g} × {height:g}{source} — 이 층 호기를 모두 담으려면 "
            f"{need_width:g} × {need_height:g} 이상: {examples}"
        )
    return (
        "Space 블럭이 층 캔버스 범위를 벗어났습니다 — 그 동·층의 캔버스가 호기 좌표보다 "
        f"좁습니다. {'; '.join(floors[:3])}. 호기 마스터 저장은 모든 호기를 한 번에 검증하므로 "
        "그 층과 무관한 칸만 고쳐도 같은 오류로 막힙니다. Space 현황의 그 동·층 상세 레이아웃에서 "
        "「도면·캔버스 편집」으로 캔버스를 넓히거나, 가용설비 현황에서 그 호기의 X좌표·Y좌표·"
        "Xsize·Ysize 를 고치세요."
    )


def _text_or_none(value: Any) -> str | None:
    """groupby 키를 글자로 바꾼다. 결측(`dropna=False` 가 남긴 NA)은 `None` 이다."""
    return None if pd.isna(value) else str(value)


def _same_value(column: pd.Series, value: str | None) -> pd.Series:
    """`value` 가 `None` 이면 결측 행을, 아니면 같은 값인 행을 참으로 돌려준다."""
    if value is None:
        return column.isna()
    return column.eq(value).fillna(False).astype(bool)


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


def _normalize_conversion_ratio(result: pd.DataFrame) -> pd.Series:
    """환산비를 양수 실수로 맞춘다. 빈 칸은 기준 모델(1.0)로 본다.

    **빈 칸과 못 읽는 값을 가른다.** 둘 다 `to_numeric` 으로는 NaN 이 되는데, 빈 칸은
    1.0 으로 채우고 못 읽는 값은 막아야 한다. 한데 묶어 1.0 으로 채우면 `1,5`·`1.5배`
    같은 오타가 조용히 기준 모델로 내려앉아, 화면에는 아무 말도 없이 그 설비의 몫이
    3분의 1 줄어든다.

    빈 칸을 0 으로 읽지도 않는다. 모델이 하나뿐인 공정은 적을 것이 없어 대개 비어 있고,
    0 으로 읽으면 그 설비가 가용대수에서 통째로 사라진다.

    0 과 음수는 막는다. 0 은 「이 설비는 없는 셈」이라는 뜻이 되는데 그것은 비가동 일정이
    맡는 일이고, 음수는 다른 설비의 몫을 깎아 합계를 거짓으로 만든다.
    """
    raw = result[CONVERSION_RATIO_COLUMN]
    blank = raw.isna() | raw.astype("string").str.strip().isin(["", "nan", "None", "<NA>"])
    ratio = pd.to_numeric(raw, errors="coerce")
    unreadable = ~blank & ratio.isna()
    if unreadable.any():
        examples = result.loc[unreadable, EQUIPMENT_ID_COLUMN].head(5).tolist()
        raise ValueError(f"환산비를 숫자로 읽을 수 없습니다: {examples}")
    not_positive = ~blank & ratio.le(0)
    if not_positive.any():
        examples = result.loc[not_positive, EQUIPMENT_ID_COLUMN].head(5).tolist()
        raise ValueError(f"환산비는 0보다 큰 숫자여야 합니다: {examples}")
    return ratio.mask(blank, DEFAULT_CONVERSION_RATIO).astype("float64")


def _readable_number(result: pd.DataFrame, column: str) -> pd.Series:
    """좌표·크기 칸을 숫자로 읽는다. **빈 칸과 못 읽는 값을 가른다**(환산비와 같은 이유).

    좌표는 비어도 되는 칸이라(레이아웃표시 Y 의 미배치·크기만 있는 행), 못 읽는 값을 NaN 으로
    흘리면 붙여넣기의 `12,5`·`12m`·줄바꿈 없는 공백이 조용히 「미배치」로 저장된다.
    """
    raw = result[column]
    blank = raw.isna() | raw.astype("string").str.strip().isin(["", "nan", "None", "<NA>"])
    number = pd.to_numeric(raw, errors="coerce")
    unreadable = ~blank & number.isna()
    if unreadable.any():
        examples = result.loc[unreadable, EQUIPMENT_ID_COLUMN].head(5).tolist()
        raise ValueError(f"{column}를 숫자로 읽을 수 없습니다: {examples}")
    return number.mask(blank).astype("float64")


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
