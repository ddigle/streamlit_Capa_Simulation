# Purpose: 설비 마스터·기존 보유대수·비가동 일정 입력을 정규화하고 검증한다.

"""설비 마스터·기존 보유대수·비가동 일정 입력을 정규화하고 검증한다."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from datetime import date
from typing import Any

import pandas as pd

from capa_simulation.services.equipment_contract import (
    AREA_CODE_COLUMN,
    AREA_CODES,
    ARRIVAL_ACTUAL_COLUMN,
    ARRIVAL_DATE_COLUMN,
    ARRIVAL_STATUS_COLUMN,
    ARRIVAL_STATUSES,
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
    EXIT_SCHEDULE_COLUMNS,
    FLAG_COLUMNS,
    PARENT_EQUIPMENT_COLUMN,
    QUAL_ACTUAL_COLUMN,
    QUAL_CONFIRMATION_STATUSES,
    QUAL_DATE_COLUMN,
    QUAL_STATUS_COLUMN,
    REFERENCE_TEXT_COLUMNS,
    RELOCATION_DATE_COLUMN,
    STOP_DATE_COLUMN,
    STORAGE_FLAG_COLUMN,
    UNIT_CONSISTENT_COLUMNS,
    VALID_BUILDINGS,
    VALID_FLOORS,
    empty_downtime_schedule,
    empty_equipment_baseline,
    empty_equipment_master,
    normalize_area_code,
    unknown_area_codes,
    with_optional_equipment_columns,
)
from capa_simulation.services.floor_layout_profile import (
    CANVAS_DECIMALS,
    DEFAULT_CANVAS_HEIGHT,
    DEFAULT_CANVAS_WIDTH,
    CanvasSize,
    FloorCanvasMap,
    FloorKey,
)
from capa_simulation.services.frame_contracts import require_columns
from capa_simulation.services.schedule_confirmation import actual_record_warnings


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
    today: date | None = None,
) -> pd.DataFrame:
    """설비 마스터 38컬럼 계약을 정규화하고 검증한다. 선택 컬럼은 없으면 빈 칸이다
    (`OPTIONAL_EQUIPMENT_COLUMNS`).

    `floor_canvases` 를 넘기면 층별 캔버스 폭·높이를 상한으로 좌표를 검사한다. 넘기지
    않으면 상한 검사를 건너뛴다 — 이미 저장된 리비전은 캔버스가 줄어든 뒤에도 열려야 한다.

    `today` 를 넘기면 **저장할 때만 도는** 실적 검사를 한다(`_validate_actual_dates` — 실적이
    오늘보다 늦음·반입실적이 Qual실적보다 늦음). 결과가 날짜에 따라 달라지는 검사라 리비전을 다시
    읽을 때는 넘기지 않는다 — 저장 때 통과한 리비전이 시간이 지나 열리지 않으면 안 된다.
    """
    data = with_optional_equipment_columns(data)
    require_columns(data, EQUIPMENT_COLUMNS, "설비 마스터")
    result = data.loc[:, EQUIPMENT_COLUMNS].copy()
    result = _drop_blank_rows(result, (EQUIPMENT_ID_COLUMN,))
    if result.empty:
        return empty_equipment_master()

    _normalize_required_text(result, (EQUIPMENT_ID_COLUMN, "공정소분류"), "설비 마스터")
    for column in REFERENCE_TEXT_COLUMNS + ("동", "층"):
        result[column] = _optional_text(result[column])
    result[AREA_CODE_COLUMN] = normalize_area_code(result[AREA_CODE_COLUMN])
    result[QUAL_STATUS_COLUMN] = _optional_text(result[QUAL_STATUS_COLUMN])
    result[ARRIVAL_STATUS_COLUMN] = _optional_text(result[ARRIVAL_STATUS_COLUMN])
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
    # Qual 이 비면 「셋업 진행중」에 머물러 날짜가 들어올 때까지 가용대수에 들지 않는다. Qual상태는
    # Qual 일정의 진행 상태 값이라 Qual일정이 있는 신규 호기에만 필수다.
    ordinary = result[STORAGE_FLAG_COLUMN].eq("N") & result["기존설비여부"].eq("N")
    missing_confirmation = (
        ordinary & result[QUAL_DATE_COLUMN].notna() & result[QUAL_STATUS_COLUMN].isna()
    )
    if missing_confirmation.any():
        examples = result.loc[missing_confirmation, EQUIPMENT_ID_COLUMN].head(5).tolist()
        raise ValueError(
            f"Qual일정이 있는 호기(보관·기존설비 제외)는 {QUAL_STATUS_COLUMN}가 필수입니다: "
            f"{examples}"
        )
    # 반입상태는 새 선택 컬럼이라 옛 리비전에 값이 없다 — 리비전을 다시 읽을 때 돌아도 막히지
    # 않는다.
    for status_column, allowed in (
        (QUAL_STATUS_COLUMN, QUAL_CONFIRMATION_STATUSES),
        (ARRIVAL_STATUS_COLUMN, ARRIVAL_STATUSES),
    ):
        invalid_status = result[status_column].notna() & ~result[status_column].isin(allowed)
        if invalid_status.any():
            examples = result.loc[invalid_status, EQUIPMENT_ID_COLUMN].head(5).tolist()
            raise ValueError(
                f"{status_column}는 {'·'.join(allowed)} 중 하나여야 합니다: {examples}"
            )
    invalid_setup_order = (
        result[ARRIVAL_DATE_COLUMN].notna()
        & result[QUAL_DATE_COLUMN].notna()
        & result[QUAL_DATE_COLUMN].lt(result[ARRIVAL_DATE_COLUMN])
    )
    invalid_pre_arrival = _invalid_optional_order(
        result, ("제진대일정", "물류일정", ARRIVAL_DATE_COLUMN)
    )
    # 신규 호기는 빈 일정을 건너뛰고 **있는 날짜끼리** 차례를 본다 — 반입이 비어도 물류 ≤ Qual
    # 이다. 보관·기존설비는 예전처럼 이웃한 둘만 본다(그런 저장본이 다시 열려야 한다). 신규 호기는
    # 이 규칙이 생기기 전에 반입·Qual 이 필수였으므로 이미 저장된 리비전이 새로 막히지 않는다.
    invalid_chain = ordinary & _invalid_present_order(
        result, ("제진대일정", "물류일정", ARRIVAL_DATE_COLUMN, QUAL_DATE_COLUMN)
    )
    invalid_order = invalid_setup_order | invalid_pre_arrival | invalid_chain
    if invalid_order.any():
        examples = result.loc[invalid_order, EQUIPMENT_ID_COLUMN].head(5).tolist()
        raise ValueError(f"제진대·물류·반입·Qual 일정 순서가 올바르지 않습니다: {examples}")
    # 들어온 적 없는 신규 호기를 내보낼 수는 없다. 받아 두면 반입 없이 「반출/이설 완료」가 되어
    # 어느 대수에도 들지 않고 일정 미정 알림에서도 빠진다.
    exit_without_arrival = (
        ordinary
        & result[ARRIVAL_DATE_COLUMN].isna()
        & result.loc[:, list(EXIT_SCHEDULE_COLUMNS)].notna().any(axis=1)
    )
    if exit_without_arrival.any():
        examples = result.loc[exit_without_arrival, EQUIPMENT_ID_COLUMN].head(5).tolist()
        raise ValueError(
            f"반입일정이 없는 신규 설비에는 {STOP_DATE_COLUMN}·{RELOCATION_DATE_COLUMN}을 넣을 수 "
            f"없습니다: {examples}"
        )
    # 두 날짜를 함께 적을 수 있다(2026-10-16 사용자 결정) — 정지한 뒤 자리를 비운다. 거꾸로면 집계
    # 이탈일(둘 중 이른 날)과 도면 이탈일(반출/이설일정)의 뜻이 어긋난다.
    stop_after_exit = (
        result[STOP_DATE_COLUMN].notna()
        & result[RELOCATION_DATE_COLUMN].notna()
        & result[STOP_DATE_COLUMN].gt(result[RELOCATION_DATE_COLUMN])
    )
    if stop_after_exit.any():
        examples = result.loc[stop_after_exit, EQUIPMENT_ID_COLUMN].head(5).tolist()
        raise ValueError(
            f"{STOP_DATE_COLUMN}은 {RELOCATION_DATE_COLUMN}보다 늦을 수 없습니다: {examples}"
        )
    for exit_column in EXIT_SCHEDULE_COLUMNS:
        before_arrival = (
            result[exit_column].notna()
            & result[ARRIVAL_DATE_COLUMN].notna()
            & result[exit_column].lt(result[ARRIVAL_DATE_COLUMN])
        )
        if before_arrival.any():
            examples = result.loc[before_arrival, EQUIPMENT_ID_COLUMN].head(5).tolist()
            raise ValueError(f"{exit_column}은 반입일정보다 빠를 수 없습니다: {examples}")
    if today is not None:
        _validate_actual_dates(result, today)
    return result.reset_index(drop=True)


def _validate_actual_dates(result: pd.DataFrame, today: date) -> None:
    """저장할 때만 도는 실적 검사. 실적은 이미 일어난 날이라 오늘보다 늦을 수 없고, Qual 은
    반입한 뒤에 끝난다."""
    limit = pd.Timestamp(today)
    for column in (ARRIVAL_ACTUAL_COLUMN, QUAL_ACTUAL_COLUMN):
        future = result[column].notna() & result[column].gt(limit)
        if future.any():
            examples = result.loc[future, EQUIPMENT_ID_COLUMN].head(5).tolist()
            raise ValueError(
                f"{column}은 오늘({limit:%Y-%m-%d})보다 늦을 수 없습니다 — 실적은 이미 끝난 날을 "
                f"적습니다: {examples}"
            )
    reversed_actuals = (
        result[ARRIVAL_ACTUAL_COLUMN].notna()
        & result[QUAL_ACTUAL_COLUMN].notna()
        & result[ARRIVAL_ACTUAL_COLUMN].gt(result[QUAL_ACTUAL_COLUMN])
    )
    if reversed_actuals.any():
        examples = result.loc[reversed_actuals, EQUIPMENT_ID_COLUMN].head(5).tolist()
        raise ValueError(
            f"{ARRIVAL_ACTUAL_COLUMN}은 {QUAL_ACTUAL_COLUMN}보다 늦을 수 없습니다: {examples}"
        )


def area_code_warnings(equipment: pd.DataFrame) -> list[str]:
    """Area Code 가 Main·MI·부대 밖인 호기를 알리는 경고(저장은 막지 않는다). 검증 전 편집본도
    받는다 — 컬럼이 없거나 표가 비면 빈 목록이다."""
    if equipment.empty or AREA_CODE_COLUMN not in equipment.columns:
        return []
    unknown = unknown_area_codes(equipment[AREA_CODE_COLUMN]).to_numpy()
    if not unknown.any():
        return []
    rows = equipment.loc[unknown]
    names = (
        rows[EQUIPMENT_ID_COLUMN].astype("string").fillna("").str.strip().tolist()
        if EQUIPMENT_ID_COLUMN in rows.columns
        else []
    )
    values = sorted({str(value).strip() for value in rows[AREA_CODE_COLUMN].tolist()})
    return [
        f"{AREA_CODE_COLUMN} 가 {'·'.join(AREA_CODES)} 밖인 호기 {len(rows):,}건 — 저장은 되지만 "
        f"값을 확인하세요({', '.join(values[:5])}): {names[:5]}"
    ]


def equipment_save_warnings(equipment: pd.DataFrame) -> list[str]:
    """설비 마스터를 저장하기 전에 알릴 것(막지 않는다). 검증 전 편집본도 받는다.

    - Area Code 가 Main·MI·부대 밖(`area_code_warnings`)
    - 실적 누락·상태 갱신 필요(`schedule_confirmation.actual_record_warnings`) — 오늘과 무관한
      두 경고다. 오늘에 따라 달라지는 「미확인」은 여기에 넣지 않는다.
    """
    return [*area_code_warnings(equipment), *actual_record_warnings(equipment)]


_COLLISION_EXAMPLES = 5
_COLLISION_HEAD = (
    "Main 설비는 다른 행의 설비명과 같을 수 없습니다 — 설비 행과 그 설비를 Main 설비로 적은 모듈 "
    "행을 함께 두면 같은 설비가 두 번 세어집니다"
)


class UnitGroupCollisionError(ValueError):
    """Main 설비가 다른 행의 설비명과 같다. `collisions` 는 {설비 행 이름: 그 이름을 Main 설비로
    적은 모듈 행 이름들}이다.

    문구만으로는 어느 쪽이 붙여넣은 행인지 모른다 — 검증은 병합된 표 하나만 보기 때문이다.
    붙여넣기 미리보기는 이 예외를 잡아 양쪽의 출처를 붙인 문구(`unit_group_collision_message`)로
    다시 알린다. 문자열을 다시 읽지 않도록 이름을 그대로 싣는다.
    """

    def __init__(self, collisions: Mapping[str, Sequence[str]]) -> None:
        self.collisions = {parent: tuple(modules) for parent, modules in collisions.items()}
        super().__init__(unit_group_collision_message(self.collisions))

    def __reduce__(self) -> tuple[type[UnitGroupCollisionError], tuple[dict[str, tuple[str, ...]]]]:
        return (type(self), (self.collisions,))


def unit_group_collision_message(
    collisions: Mapping[str, Sequence[str]],
    *,
    pasted: Collection[str] | None = None,
    existing: Collection[str] = (),
) -> str:
    """충돌한 **양쪽 설비명**(설비 행과 그 이름을 Main 설비로 적은 모듈 행)을 적은 오류 문구.

    `pasted` 가 없으면 직접 편집·저장 경로다 — 두 행이 모두 지금 표에 있으니 한쪽을 지우라고
    한다. `pasted`(붙여넣은 표의 설비명)를 주면 붙여넣기 미리보기다. `existing` 은 붙여넣기 **전**
    편집본의 설비명이다. 이름마다 출처를 붙인다 — 붙여넣기에만 있으면 (붙여넣기), 편집본에만
    있으면 (편집본), 둘 다에 있으면 (붙여넣기·편집본). 둘 다에 있는 이름은 한 곳에서만 빼면 다시
    막히므로 그렇게 적는다. 고칠 길은 출처를 따른다(2026-10-08 점검 A3·리뷰, 사내 AWB05 와 같은
    꼴: 모듈 행이 저장된 설비의 설비 행을 다시 붙여넣었다).

    - 붙여넣은 이름이 충돌에 하나도 없다 — 편집본 안에서 이미 부딪힌 것이다. 붙여넣기와 상관없으니
      직접 편집에서 한쪽을 지우라고만 한다.
    - 충돌한 이름이 모두 붙여넣기에만 있다 — 붙여넣을 표 안에서 부딪혔다. 그 표를 고친다.
    - 그 밖 — **붙여넣기는 설비명 기준으로 행을 더하거나 바꿀 뿐 이미 있는(편집본의) 행을 지우지
      않는다.** 편집본 쪽 행을 없애는 길은 직접 편집뿐이다.
    """
    shown = list(collisions.items())[:_COLLISION_EXAMPLES]
    pasted_names = set(pasted) if pasted is not None else None
    existing_names = set(existing)

    def origin_of(value: str) -> str:
        assert pasted_names is not None
        if value in pasted_names:
            return "붙여넣기·편집본" if value in existing_names else "붙여넣기"
        return "편집본"

    def names(values: Sequence[str]) -> str:
        if pasted_names is None:
            return ", ".join(values)
        groups: list[tuple[str, list[str]]] = []
        for value in values:
            origin = origin_of(value)
            if groups and groups[-1][0] == origin:
                groups[-1][1].append(value)
            else:
                groups.append((origin, [value]))
        return ", ".join(f"{', '.join(group)}({origin})" for origin, group in groups)

    pairs = " / ".join(
        f"설비 행 {names([parent])} · 모듈 행 {names(modules)}" for parent, modules in shown
    )
    more = f" 외 {len(collisions) - len(shown)}건" if len(collisions) > len(shown) else ""
    if pasted_names is None:
        remedy = (
            "한쪽만 남기세요 — 모듈로 나눠 세려면 설비 행을, 한 대로 세려면 모듈 행을 지우거나 "
            "그 행의 Main 설비를 비웁니다."
        )
    else:
        every = {*collisions, *(module for modules in collisions.values() for module in modules)}
        if not every & pasted_names:
            remedy = (
                "붙여넣기 전 편집본에 이미 있던 충돌입니다 — 직접 편집에서 한쪽을 지운 뒤 다시 "
                "미리보세요."
            )
        elif every <= pasted_names - existing_names:
            remedy = "붙여넣을 표에서 한쪽을 빼고 다시 미리보세요."
        else:
            remedy = (
                "붙여넣기는 이미 있는(편집본의) 행을 지우지 않습니다 — 편집본 쪽 행을 없애려면 "
                "직접 편집에서 지운 뒤 다시 미리보세요. 붙여넣은 쪽이 잘못이면 그 행을 빼고 다시 "
                "붙여넣으세요."
            )
            if every & pasted_names & existing_names:
                remedy += " (붙여넣기·편집본) 이름은 두 곳 모두에서 빼야 합니다."
    return f"{_COLLISION_HEAD}: {pairs}{more}. {remedy}"


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
        collisions: dict[str, tuple[str, ...]] = {}
        for parent, module in zip(parents.loc[colliding], units.loc[colliding], strict=True):
            collisions[str(parent)] = (*collisions.get(str(parent), ()), str(module))
        raise UnitGroupCollisionError(collisions)
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
        raise ValueError(f"설비 마스터에 없는 설비의 비가동 일정이 있습니다: {examples}")


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
    outside = complete & _beyond_canvas(result, limit_width, limit_height)
    if outside.any():
        raise ValueError(_outside_canvas_message(result, outside, complete, floor_canvases))


def floor_equipment_outside_canvas(
    equipment: pd.DataFrame, floor: FloorKey, canvas: CanvasSize
) -> list[str]:
    """그 동·층 호기 가운데 블럭(좌표 + 크기)이 `canvas` 를 벗어나는 설비명(표 차례).

    저장 검증(`_validate_locations_and_coordinates`)과 **같은 행, 같은 판정**이다 — 레이아웃표시·
    상태·화면 필터와 무관하게 그 층에서 좌표·크기가 다 있는 행을 모두 본다. 층 캔버스를 바꾸는
    화면(Space `도면·캔버스 편집` 팝업)이 저장된 마스터를 넘겨, 그 캔버스로 바꾸면 다음 설비 저장이
    「캔버스 밖」으로 막히는지 미리 잰다. 화면에 그린 행만 넘기면 안 보이는 호기를 놓친다.
    """
    if equipment.empty or not {"동", "층", *COORDINATE_COLUMNS} <= set(equipment.columns):
        return []
    numeric = equipment.loc[:, list(COORDINATE_COLUMNS)].apply(pd.to_numeric, errors="coerce")
    on_floor = (
        equipment["동"].astype("string").eq(floor[0]).fillna(False)
        & equipment["층"].astype("string").eq(floor[1]).fillna(False)
        & numeric.notna().all(axis=1)
    )
    outside = on_floor & _beyond_canvas(numeric, float(canvas[0]), float(canvas[1]))
    return [str(name) for name in equipment.loc[outside, EQUIPMENT_ID_COLUMN]]


def _beyond_canvas(
    frame: pd.DataFrame, width: pd.Series | float, height: pd.Series | float
) -> pd.Series:
    """블럭 끝이 캔버스 폭·높이를 넘는 행. 끝 좌표는 저장 정밀도로 반올림해 견준다 — 편집기가
    캔버스 끝에 붙여 놓은 호기(88.7 + 11.3)가 부동소수 합(100.00000000000001)으로 「밖」이 되지
    않게(푸는 쪽이라 과거 리비전도 열린다)."""
    right = frame["X좌표"].add(frame["Xsize"]).round(CANVAS_DECIMALS)
    top = frame["Y좌표"].add(frame["Ysize"]).round(CANVAS_DECIMALS)
    return right.gt(width) | top.gt(height)


def _outside_canvas_message(
    result: pd.DataFrame,
    outside: pd.Series,
    complete: pd.Series,
    floor_canvases: FloorCanvasMap,
) -> str:
    """캔버스를 벗어난 호기를 동·층별로 묶어 **원인과 고칠 곳**까지 적는다.

    누가 층 캔버스를 줄여 두면, 뒤에 다른 사람이 무관한 기존보유대수 한 칸만 고쳐 저장해도
    설비 마스터 전체 검증이 이 오류로 막힌다. 예전 문구는 호기 이름만 적어서 원인이 캔버스
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
        f"좁습니다. {'; '.join(floors[:3])}. 설비 마스터 저장은 모든 호기를 한 번에 검증하므로 "
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


def _invalid_present_order(data: pd.DataFrame, columns: tuple[str, ...]) -> pd.Series:
    """빈 칸을 건너뛰고 있는 날짜를 바로 앞의 **있는** 날짜와 견준다(앞이 더 늦으면 참)."""
    invalid = pd.Series(False, index=data.index)
    previous = data[columns[0]]
    for column in columns[1:]:
        current = data[column]
        invalid |= current.notna() & previous.notna() & current.lt(previous)
        previous = current.where(current.notna(), previous)
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
