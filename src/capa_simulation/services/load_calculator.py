# Purpose: PKG and wafer monthly volume calculations.

"""PKG and wafer monthly volume calculations."""

from collections.abc import Sequence
from typing import Literal

import pandas as pd

from capa_simulation.services.display_order import DisplayOrderInput, apply_display_order
from capa_simulation.services.display_order_scopes import (
    PAGE_PLAN,
    TAB_CONVERSION,
    TAB_PKG_PLAN,
    TAB_YIELD,
)
from capa_simulation.services.frame_checks import assert_unique_keys, strip_text_columns
from capa_simulation.services.frame_contracts import (
    match_key,
    require_columns,
    scalar_match_key,
)
from capa_simulation.services.product_type import (
    DUMMY_DIVISIONS_BY_PRODUCT_TYPE,
    EDP_PRODUCT_TYPE,
    PRODUCT_TYPE_COLUMN,
    product_type_of,
)

DemandBasis = Literal["PKG", "Chip", "Wafer", "Density"]

CLASSIFICATION_COLUMNS = ["양산구분", "제품정보", "Stack"]
LOAD_DETAIL_COLUMNS = ["Capa Code", "Customer", "CS"]
# 제품타입별 `WF 구분` 규칙은 `services/product_type.py` 가 단일 근거다.
# 계획에 딸려 다니지만 사용자가 격자에서 고칠 값이 아닌 속성들. 편집 왕복에서 떨어지므로
# `attach_plan_attributes` 로 되붙인다.
#
# `Pack Code` 는 여기 두지 않는다 — 업무 키로 올라가 `PLAN_EDITOR_DIMENSIONS` 에 있으므로,
# 남겨 두면 `attach_plan_attributes` 가 키와 속성 양쪽에서 같은 컬럼을 골라 중복 라벨
# 프레임을 만들고 바로 다음 `_normalize_text` 가 죽는다.
PLAN_ATTRIBUTE_COLUMNS = [PRODUCT_TYPE_COLUMN]
# `Pack Code` 는 같은 7키 안에서 생산수량을 가르는 업무 키다. 격자에서 합쳐 보이면
# 편집 왕복에서 Pack Code 별 수량을 되살릴 수 없으므로 행 차원으로 노출한다.
PLAN_EDITOR_DIMENSIONS = [
    "양산구분",
    "제품정보",
    "Stack",
    "Capa Code",
    "Customer",
    "CS",
    "Pack Code",
]
PLAN_REQUIRED_COLUMNS = [
    "생산계획년월",
    *CLASSIFICATION_COLUMNS,
    "생산수량",
]
YIELD_KEYS = ["생산계획년월", "제품정보", "Stack", "WF 구분"]
YIELD_REQUIRED_COLUMNS = [*YIELD_KEYS, "EDS_수율", "BE_수율"]
YIELD_EDITOR_DIMENSIONS = ["수율 구분", "제품정보", "Stack", "WF 구분"]
YIELD_VALUE_COLUMNS = ["EDS_수율", "BE_수율"]
YIELD_DISPLAY_NAMES = {"EDS_수율": "EDS", "BE_수율": "BE"}
YIELD_INTERNAL_NAMES = {display: internal for internal, display in YIELD_DISPLAY_NAMES.items()}
# 편집표에서 뺀 수율 행에 붙는 까닭 컬럼(`split_editable_yield_rows`).
YIELD_LOCK_REASON_COLUMN = "사유"
# 범위 밖 수율 오류에 적는 예시 칸 수. 사용자가 어느 행인지 찾을 수 있으면 된다.
YIELD_RANGE_EXAMPLE_LIMIT = 5
# 계산 경로의 범위 밖 수율 오류 끝에 붙이는 고치는 곳. 기준정보 오류는 보지 않는 달이어도 계산을
# 멈춘다(2026-09-28 사용자 결정) — 대신 어디를 고칠지 알린다.
YIELD_RANGE_FIX_HINT = (
    "생산 계획 → 수율 탭에서 그 달의 EDS·BE 를 둘 다 고쳐 적용하세요 — 그 칸은 수율 표에서 "
    "빈칸으로 보입니다. 그 달이 조회기간 밖이면 사이드바 조회기간을 넓혀야 수율 탭에 나옵니다."
)
CHIP_KEYS = ["제품정보", "Stack", "WF 구분"]
CHIP_REQUIRED_COLUMNS = [*CHIP_KEYS, "구분_Chip", "Net Die"]
DENSITY_KEYS = ["제품정보", "Stack", "WF 구분"]
DENSITY_REQUIRED_COLUMNS = [*DENSITY_KEYS, "구분_Chip", "구분_EQ"]

# 기준정보가 없어 계산에서 뺀 계획 행을 결과 프레임에 붙여 화면이 목록으로 보여준다.
# 예전에는 여기서 예외를 던져 계획 행 하나 때문에 페이지 전체가 멈췄다.
#
# 값은 DataFrame 이 아니라 레코드 튜플로 담는다. `attrs` 에 DataFrame 을 넣으면
# `pd.concat` 이 attrs 를 동등 비교하다가 "truth value of a DataFrame is ambiguous" 로
# 죽는다. 부하량 프레임들은 소요대수 계산에서 실제로 concat 된다.
LOAD_EXCLUSIONS_ATTR = "excluded_load_rows"
LOAD_EXCLUSION_COLUMNS = ["생산계획년월", "제품정보", "Stack", "WF 구분", "누락 기준정보"]


def plan_to_edit_table(plan: pd.DataFrame, display_order: DisplayOrderInput = None) -> pd.DataFrame:
    """Pivot the default Long PKG plan into an editable month-column table."""
    required = ["생산계획년월", *PLAN_EDITOR_DIMENSIONS, "생산수량"]
    require_columns(plan, required, "RQ_PKG_PLAN")
    prepared = _normalize_text(plan[required], PLAN_EDITOR_DIMENSIONS)
    prepared["생산계획년월"] = pd.to_numeric(prepared["생산계획년월"], errors="coerce").astype(
        "Int64"
    )
    prepared = _to_numeric(prepared, ["생산수량"], "RQ_PKG_PLAN")
    prepared["생산수량"] = prepared["생산수량"].fillna(0.0)

    identity_columns = ["생산계획년월", *PLAN_EDITOR_DIMENSIONS]
    empty_columns = [column for column in identity_columns if prepared[column].isna().any()]
    if empty_columns:
        # 어느 컬럼이 비었는지 적어야 한다. `Pack Code` 승격 이전에 저장한 리비전은 그
        # 컬럼이 NULL 이라 여기서 멈추고 생산 계획 페이지 전체가 선다. 사이드바 「편집
        # 되돌리기」로도 풀리지 않는다 — 되돌아가는 원본 리비전 자체가 그 모양이다.
        raise ValueError(
            "RQ_PKG_PLAN의 편집 테이블 식별 컬럼에 누락값이 있습니다: "
            f"{', '.join(empty_columns)}. 그 컬럼이 비어 있는 옛 리비전은 BigDataQuery 에서 "
            "다시 조회·저장해야 합니다."
        )

    duplicate_keys = [*PLAN_EDITOR_DIMENSIONS, "생산계획년월"]
    assert_unique_keys(prepared, duplicate_keys, "RQ_PKG_PLAN의 월별 계획 키가")

    result = prepared.pivot(
        index=PLAN_EDITOR_DIMENSIONS,
        columns="생산계획년월",
        values="생산수량",
    ).reset_index()
    result.columns.name = None
    raw_month_columns = [
        column for column in result.columns if column not in PLAN_EDITOR_DIMENSIONS
    ]
    result[raw_month_columns] = result[raw_month_columns].fillna(0.0)
    result = result.rename(columns={column: str(int(column)) for column in raw_month_columns})
    month_columns = sorted(
        [column for column in result.columns if column not in PLAN_EDITOR_DIMENSIONS]
    )
    result = result[[*PLAN_EDITOR_DIMENSIONS, *month_columns]]
    return apply_display_order(result, display_order, PAGE_PLAN, TAB_PKG_PLAN)


def plan_from_edit_table(plan_table: pd.DataFrame) -> pd.DataFrame:
    """Convert the edited month-column plan back to the calculation Long format."""
    require_columns(plan_table, PLAN_EDITOR_DIMENSIONS, "PKG PLAN 편집값")
    month_columns = [
        column for column in plan_table.columns if column not in PLAN_EDITOR_DIMENSIONS
    ]
    invalid_months = [
        column for column in month_columns if not str(column).isdigit() or len(str(column)) != 6
    ]
    if invalid_months:
        raise ValueError(f"PKG PLAN의 월 컬럼은 YYYYMM 형식이어야 합니다: {invalid_months}")

    long_plan = plan_table.melt(
        id_vars=PLAN_EDITOR_DIMENSIONS,
        value_vars=month_columns,
        var_name="생산계획년월",
        value_name="생산수량",
    )
    long_plan["생산계획년월"] = pd.to_numeric(long_plan["생산계획년월"], errors="raise").astype(
        "Int64"
    )
    long_plan["생산수량"] = _blank_text_to_na(long_plan["생산수량"])
    long_plan = _to_numeric(long_plan, ["생산수량"], "PKG PLAN 편집값")
    long_plan["생산수량"] = long_plan["생산수량"].fillna(0.0)
    if long_plan["생산수량"].lt(0).any():
        raise ValueError("PKG PLAN 생산수량은 0 이상이어야 합니다.")
    # 수량 0 행을 여기서 버리면 그 제품이 편집 격자에서 사라져 다시 물량을 넣을 수 없고,
    # 내려받은 CSV 와 행 수가 달라져 붙여넣기가 어긋난다. 0 은 "이 달 계획 없음" 이라는
    # 사용자의 입력이므로 그대로 보존하고, 계산 경계(_prepare_plan)에서 제외한다.
    return long_plan.sort_values(["생산계획년월", *PLAN_EDITOR_DIMENSIONS]).reset_index(drop=True)


def attach_plan_attributes(long_plan: pd.DataFrame, source_plan: pd.DataFrame) -> pd.DataFrame:
    """편집 격자가 들고 있지 않은 계획 속성을 원래 계획에서 되붙인다.

    격자는 `PLAN_EDITOR_DIMENSIONS` 와 월 컬럼만 보여 준다. `제품타입` 은 사용자가 고칠
    값이 아니라 제품에 딸린 속성이라 격자에 두지 않았는데, 되붙이지 않으면 변경사항을
    적용할 때마다 조용히 사라진다. 그러면 `replace_month_range` 가 "편집값에 원본 컬럼이
    없습니다" 로 막고, 화면에는 오류만 뜬 채 적용이 안 된다.

    `Pack Code` 는 업무 키라 격자가 직접 들고 오므로 여기서 되붙일 것이 없다.

    격자에 없던 새 행은 붙일 원본이 없어 결측으로 남는다. 그 상태로 EDP 를 판별하려 하면
    `filter_edp_plan` 이 어느 제품인지 짚어 알려 준다 — 조용히 넘어가지 않는다.
    """
    attributes = [column for column in PLAN_ATTRIBUTE_COLUMNS if column in source_plan.columns]
    if not attributes:
        return long_plan
    keys = [column for column in PLAN_EDITOR_DIMENSIONS if column in source_plan.columns]
    lookup = _normalize_text(source_plan[[*keys, *attributes]], keys).drop_duplicates(subset=keys)
    merged = _normalize_text(long_plan, keys).merge(
        lookup, on=keys, how="left", validate="many_to_one"
    )
    return merged


def yield_to_edit_table(
    yield_data: pd.DataFrame,
    display_order: DisplayOrderInput = None,
    *,
    locked: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Pivot Long yield data into editable EDS/BE rows with month columns.

    `locked` 는 `split_editable_yield_rows` 가 뺀 행이다. 그 (제품, Stack, WF 구분) 행과 달 열을
    **빈칸으로** 싣는다 — 제품의 모든 달이 잠기면 표에 그 제품 행이 없어 이 화면에서 고칠 길이
    없었다(2026-09-29 리뷰). 빈칸은 적용 때 `restore_locked_yield_rows` 가 원본으로 되붙이고,
    EDS·BE 를 둘 다 채우면 채운 값이 이긴다. 붙여넣기 양식도 이 표라 같은 행이 실린다.
    """
    require_columns(yield_data, YIELD_REQUIRED_COLUMNS, "RQ_YLD")
    prepared = _normalize_text(yield_data[YIELD_REQUIRED_COLUMNS], YIELD_KEYS[1:])
    prepared["생산계획년월"] = pd.to_numeric(prepared["생산계획년월"], errors="coerce").astype(
        "Int64"
    )
    prepared = _to_numeric(prepared, YIELD_VALUE_COLUMNS, "RQ_YLD")

    if prepared[YIELD_KEYS].isna().any(axis=None):
        raise ValueError("RQ_YLD의 연결 키에 누락값이 있습니다.")
    if prepared[YIELD_VALUE_COLUMNS].isna().any(axis=None):
        raise ValueError("RQ_YLD의 EDS_수율 또는 BE_수율에 누락값이 있습니다.")
    assert_unique_keys(prepared, YIELD_KEYS, "RQ_YLD 연결 키가")
    _validate_yield_range(prepared, "RQ_YLD")
    if locked is not None and not locked.empty:
        prepared = pd.concat([prepared, _locked_yield_placeholders(locked)], ignore_index=True)
        assert_unique_keys(prepared, YIELD_KEYS, "RQ_YLD 연결 키가")

    long_yield = prepared.melt(
        id_vars=YIELD_KEYS,
        value_vars=YIELD_VALUE_COLUMNS,
        var_name="수율 구분",
        value_name="수율",
    )
    long_yield["수율 구분"] = long_yield["수율 구분"].replace(YIELD_DISPLAY_NAMES)
    result = long_yield.pivot(
        index=YIELD_EDITOR_DIMENSIONS,
        columns="생산계획년월",
        values="수율",
    ).reset_index()
    result.columns.name = None
    raw_month_columns = [
        column for column in result.columns if column not in YIELD_EDITOR_DIMENSIONS
    ]
    result = result.rename(columns={column: str(int(column)) for column in raw_month_columns})
    month_columns = sorted(
        [column for column in result.columns if column not in YIELD_EDITOR_DIMENSIONS]
    )
    result = result[[*YIELD_EDITOR_DIMENSIONS, *month_columns]]
    return apply_display_order(
        result,
        display_order,
        PAGE_PLAN,
        TAB_YIELD,
        value_aliases={"수율 구분": YIELD_DISPLAY_NAMES},
    )


def _locked_yield_placeholders(locked: pd.DataFrame) -> pd.DataFrame:
    """뺀 수율 행의 연결 키에 EDS·BE 를 빈칸으로 둔 행. 편집표에 빈칸 칸으로 실린다."""
    require_columns(locked, YIELD_KEYS, "편집 불가 수율 행")
    placeholders = _normalize_text(locked[YIELD_KEYS], YIELD_KEYS[1:])
    placeholders["생산계획년월"] = pd.to_numeric(
        placeholders["생산계획년월"], errors="coerce"
    ).astype("Int64")
    for column in YIELD_VALUE_COLUMNS:
        placeholders[column] = pd.Series(float("nan"), index=placeholders.index, dtype="float64")
    return placeholders[YIELD_REQUIRED_COLUMNS]


def yield_from_edit_table(yield_table: pd.DataFrame) -> pd.DataFrame:
    """Convert edited month-column yields back to the RQ_YLD Long format."""
    require_columns(yield_table, YIELD_EDITOR_DIMENSIONS, "수율 편집값")
    month_columns = [
        column for column in yield_table.columns if column not in YIELD_EDITOR_DIMENSIONS
    ]
    invalid_months = [
        column for column in month_columns if not str(column).isdigit() or len(str(column)) != 6
    ]
    if invalid_months:
        raise ValueError(f"수율의 월 컬럼은 YYYYMM 형식이어야 합니다: {invalid_months}")

    prepared = _normalize_text(yield_table, YIELD_EDITOR_DIMENSIONS)
    invalid_types = sorted(set(prepared["수율 구분"].dropna()) - set(YIELD_INTERNAL_NAMES))
    if invalid_types:
        raise ValueError(f"지원하지 않는 수율 구분이 있습니다: {invalid_types}")

    long_yield = prepared.melt(
        id_vars=YIELD_EDITOR_DIMENSIONS,
        value_vars=month_columns,
        var_name="생산계획년월",
        value_name="수율",
    )
    long_yield["수율 구분"] = long_yield["수율 구분"].replace(YIELD_INTERNAL_NAMES)
    long_yield["생산계획년월"] = pd.to_numeric(long_yield["생산계획년월"], errors="raise").astype(
        "Int64"
    )
    long_yield["수율"] = _blank_text_to_na(long_yield["수율"])
    long_yield = _to_numeric(long_yield, ["수율"], "수율 편집값")
    long_yield = long_yield.dropna(subset=["수율"])

    duplicated = long_yield.duplicated(["생산계획년월", *YIELD_EDITOR_DIMENSIONS], keep=False)
    if duplicated.any():
        raise ValueError("수율 편집값의 월별 연결 키가 중복되었습니다.")

    result = long_yield.pivot(
        index=YIELD_KEYS,
        columns="수율 구분",
        values="수율",
    ).reset_index()
    result.columns.name = None
    require_columns(result, YIELD_REQUIRED_COLUMNS, "수율 편집값")
    if result[YIELD_VALUE_COLUMNS].isna().any(axis=None):
        raise ValueError("동일한 기준에는 EDS_수율과 BE_수율이 모두 필요합니다.")
    _validate_yield_range(result, "수율 편집값")
    return result[YIELD_REQUIRED_COLUMNS].sort_values(YIELD_KEYS).reset_index(drop=True)


def split_editable_yield_rows(yield_data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """수율 편집표에 실을 행과 실을 수 없는 행(값 결측·0 이하·100% 초과)으로 가른다.

    `yield_to_edit_table` 은 값 칸 하나만 비었거나 0 이어도 표 전체를 거부한다. 생산 계획
    화면은 그 오류로 PKG PLAN 편집·붙여넣기·가상 제품 등록·환산까지 멈췄다(2026-09-29 횡전개
    감사). 이 화면은 그 값을 **고치는 곳**이라 서면 안 된다.

    계산은 두 경우가 다르다(2026-09-29 리뷰). 값이 **빈** 행은 `_drop_rows_missing_values` 가
    환산의 제외 목록으로 내리고 이어 간다. **0 이하·100% 초과** 행은 `_prepare_load_base` 가
    Chip·Wafer 환산과 HOME·소요대수·확보율을 행 예시와 함께 멈춘다 — 기준정보 오류는 숨기지
    않는다(2026-09-28 사용자 결정). 어느 쪽이든 고치는 길은 이 표다.

    그런 행을 원본 값 그대로 표에 실으면 값 검사가 표 전체를 거부하고, 빈칸으로 실어 그대로
    적용하면 적용의 `dropna` 가 원천 행을 지운다. 그래서 **(월, 제품, Stack, WF 구분) 행
    단위로** 값을 표에서 빼고(`yield_to_edit_table(locked=...)` 가 그 칸을 빈칸으로 싣는다), 적용
    때 `restore_locked_yield_rows` 가 원본 그대로 되붙인다. 판정은 `_validate_yield_range` 와
    같다 — 그보다 좁으면 `1.2` 같은 값이 여전히 화면을 세운다.

    연결 키 결측·중복은 행 하나의 값 문제가 아니라 표 구조의 문제라 가르지 않고 그대로 던진다.

    Returns:
        (편집표에 실을 행, 뺀 행). 뺀 행은 원본 컬럼 그대로에 `사유` 컬럼을 더한다.
    """
    require_columns(yield_data, YIELD_REQUIRED_COLUMNS, "RQ_YLD")
    keys = _normalize_text(yield_data[YIELD_KEYS], YIELD_KEYS[1:])
    keys["생산계획년월"] = pd.to_numeric(keys["생산계획년월"], errors="coerce").astype("Int64")
    if keys.isna().any(axis=None):
        raise ValueError("RQ_YLD의 연결 키에 누락값이 있습니다.")
    assert_unique_keys(keys, YIELD_KEYS, "RQ_YLD 연결 키가")

    problems: list[list[str]] = [[] for _ in range(len(yield_data))]
    for column in YIELD_VALUE_COLUMNS:
        raw = yield_data[column]
        numeric = pd.to_numeric(raw, errors="coerce")
        label = YIELD_DISPLAY_NAMES[column]
        for flagged, text in (
            (raw.isna(), "값 없음"),
            (raw.notna() & numeric.isna(), "숫자 아님"),
            (numeric.le(0), "0 이하"),
            (numeric.gt(1), "100% 초과"),
        ):
            for position in flagged.fillna(False).astype(bool).to_numpy().nonzero()[0]:
                problems[position].append(f"{label} {text}")
    # 위치로 가른다 — 원천 인덱스가 겹쳐도(이어 붙인 프레임) 라벨 정렬에 기대지 않는다.
    reasons = [", ".join(found) for found in problems]
    locked_mask = pd.Series(reasons).ne("").to_numpy()
    locked = yield_data.loc[locked_mask].copy()
    locked[YIELD_LOCK_REASON_COLUMN] = [reason for reason in reasons if reason]
    return yield_data.loc[~locked_mask].copy(), locked


def restore_locked_yield_rows(edited: pd.DataFrame, locked: pd.DataFrame) -> pd.DataFrame:
    """편집표에서 뺀 수율 행을 적용 결과(`yield_from_edit_table`)에 원본 값 그대로 되붙인다.

    뺀 행의 달은 표에서 빈칸으로 보인다. 그 칸을 그대로 두면 원본이 남고, 사용자가 EDS·BE 를
    **둘 다** 채웠으면 채운 값이 이긴다 — 되붙이면 같은 연결 키가 두 번 들어간다. 하나만
    채웠으면 `yield_from_edit_table` 이 「둘 다 필요」로 이미 막는다.

    값 범위는 다시 검사하지 않는다. 뺀 행은 정의상 범위 밖이고, 그 값을 고치지 않고 남겨
    두는 것이 이 함수의 일이다. 계산은 결측 행을 제외 목록으로 내리지만 0 이하·100% 초과 행에서는
    멈춘다(`_prepare_load_base`) — 남긴 값은 사용자가 이 표의 빈칸을 채워 고칠 때까지 오류로 남는다.
    """
    if locked.empty:
        return edited
    kept = _normalize_text(locked[YIELD_REQUIRED_COLUMNS], YIELD_KEYS[1:])
    kept["생산계획년월"] = pd.to_numeric(kept["생산계획년월"], errors="coerce").astype("Int64")
    edited_keys = pd.MultiIndex.from_frame(edited[YIELD_KEYS])
    overridden = pd.MultiIndex.from_frame(kept[YIELD_KEYS]).isin(edited_keys)
    kept = kept.loc[~overridden]
    if kept.empty:
        return edited
    combined = pd.concat([edited[YIELD_REQUIRED_COLUMNS], kept], ignore_index=True)
    return combined.sort_values(YIELD_KEYS).reset_index(drop=True)


def _normalize_text(data: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """텍스트 키를 strip 한 **복사본**을 돌려준다.

    호출부가 넘기는 것은 `plan[required]` 같은 열 슬라이스이거나 호출부가 계속 쓰는
    프레임이다. 제자리에서 고치면 원본을 함께 바꾸거나 슬라이스 경고를 낸다.
    """
    normalized = data.copy()
    strip_text_columns(normalized, columns)
    return normalized


def _blank_text_to_na(values: pd.Series) -> pd.Series:
    """공백만 든 글자 칸을 빈칸(NA)으로 내린다 — `reference_csv._is_blank` 와 같은 판정.

    붙여넣기 검증(`assert_numeric_edit_values`)은 `' '` 를 빈칸으로 통과시키는데, 여기서
    그대로 `_to_numeric` 에 넣으면 「숫자가 아닌 값」으로 표 전체가 거부되고 어느 칸인지도
    알리지 않았다(2026-09-29 횡전개 감사). 검증과 변환이 빈칸을 같은 뜻으로 읽게 한다.
    """
    blank = values.map(lambda value: isinstance(value, str) and not value.strip())
    return values.mask(blank.astype(bool))


def _to_numeric(data: pd.DataFrame, columns: list[str], table_name: str) -> pd.DataFrame:
    converted = data.copy()
    for column in columns:
        original = converted[column]
        converted[column] = pd.to_numeric(original, errors="coerce")
        invalid = original.notna() & converted[column].isna()
        if invalid.any():
            raise ValueError(f"{table_name}.{column}에 숫자가 아닌 값이 있습니다.")
    return converted


def _validate_yield_range(data: pd.DataFrame, table_name: str, *, fix_hint: str = "") -> None:
    """수율이 0 초과 100% 이하인지 본다. 막을 때는 **어느 행인지** 건수와 예시로 알린다.

    예전 문구는 「RQ_YLD의 수율은 0 초과 100% 이하여야 합니다.」뿐이라 HOME·소요대수·확보율이
    멈춰도 어느 제품·달인지 찾을 길이 없었다(2026-09-29 리뷰). 계산 경로의 프레임은 계획 행으로
    펼쳐져 같은 수율 행이 거래선·Capa Code 수만큼 겹치므로 수율 연결 키로 줄여 센다. 부르는
    쪽은 모두 `생산계획년월` 을 `Int64` 로 맞춰 넘긴다.
    """
    cells: list[pd.DataFrame] = []
    for column in YIELD_VALUE_COLUMNS:
        values = data[column]
        invalid = values.le(0) | values.gt(1)
        if not bool(invalid.any()):
            continue
        found = data.loc[invalid, YIELD_KEYS].copy()
        found["구분"] = YIELD_DISPLAY_NAMES[column]
        found["값"] = values.loc[invalid].astype("float64")
        cells.append(found)
    if not cells:
        return
    invalid_cells = pd.concat(cells, ignore_index=True).drop_duplicates()
    invalid_rows = invalid_cells[YIELD_KEYS].drop_duplicates()
    examples = [
        f"{month} · {product} · {stack} · {division} → {kind} {value:.4g}({value * 100:.4g}%)"
        for month, product, stack, division, kind, value in invalid_cells.head(
            YIELD_RANGE_EXAMPLE_LIMIT
        ).itertuples(index=False)
    ]
    rest = len(invalid_cells) - len(examples)
    message = (
        f"{table_name}의 수율은 0 초과 100% 이하여야 합니다: {len(invalid_rows):,}행, "
        f"예시(년월 · 제품 · Stack · WF 구분) {'; '.join(examples)}"
        + (f" 외 {rest:,}칸" if rest > 0 else "")
        + "."
    )
    raise ValueError(f"{message} {fix_hint}" if fix_hint else message)


def _prepare_plan(plan: pd.DataFrame) -> pd.DataFrame:
    require_columns(plan, PLAN_REQUIRED_COLUMNS, "RQ_PKG_PLAN")
    available_detail_columns = [column for column in LOAD_DETAIL_COLUMNS if column in plan.columns]
    # 제품타입은 분류 키가 아니지만 계산 분기가 참조하므로 있으면 그대로 들고 간다.
    carried = [PRODUCT_TYPE_COLUMN] if PRODUCT_TYPE_COLUMN in plan.columns else []
    prepared_columns = [*PLAN_REQUIRED_COLUMNS, *available_detail_columns, *carried]
    prepared = _normalize_text(
        plan[prepared_columns],
        [*CLASSIFICATION_COLUMNS, *available_detail_columns, *carried],
    )
    prepared["생산계획년월"] = pd.to_numeric(prepared["생산계획년월"], errors="coerce").astype(
        "Int64"
    )
    prepared = _to_numeric(prepared, ["생산수량"], "RQ_PKG_PLAN")

    missing_keys = prepared[["생산계획년월", *CLASSIFICATION_COLUMNS]].isna().any(axis=1)
    if missing_keys.any():
        raise ValueError("RQ_PKG_PLAN에 월별 물량 분류 키가 누락된 행이 있습니다.")
    return drop_unplanned_rows(prepared)


def drop_unplanned_rows(plan: pd.DataFrame) -> pd.DataFrame:
    """계산에서 제외할 수량 0 행을 걷어낸다.

    편집 격자는 계획이 없는 달도 행으로 들고 있어야 사용자가 다시 물량을 넣을 수 있다.
    그러나 계산은 모든 계획 행에 대해 RQ_CHIP_QTY·RQ_YLD 매칭을 요구하므로, 계획이 없는
    제품까지 기준정보를 갖출 것을 강요하게 된다. 그래서 계산 입구에서만 제외한다.
    """
    quantities = pd.to_numeric(plan["생산수량"], errors="coerce").fillna(0.0)
    return plan.loc[quantities.gt(0)].copy()


def _prepare_load_base(
    plan: pd.DataFrame,
    yield_data: pd.DataFrame,
    chip_qty: pd.DataFrame,
) -> pd.DataFrame:
    """Expand each plan by WF type and attach the matching yield and chip standards."""
    prepared_plan = _prepare_plan(plan)
    require_columns(yield_data, YIELD_REQUIRED_COLUMNS, "RQ_YLD")
    require_columns(chip_qty, CHIP_REQUIRED_COLUMNS, "RQ_CHIP_QTY")

    prepared_yield = _normalize_text(yield_data[YIELD_REQUIRED_COLUMNS], YIELD_KEYS[1:])
    prepared_yield["생산계획년월"] = pd.to_numeric(
        prepared_yield["생산계획년월"], errors="coerce"
    ).astype("Int64")
    prepared_yield = _to_numeric(prepared_yield, ["EDS_수율", "BE_수율"], "RQ_YLD")

    prepared_chip = _normalize_text(chip_qty[CHIP_REQUIRED_COLUMNS], CHIP_KEYS)
    prepared_chip = _to_numeric(prepared_chip, ["구분_Chip", "Net Die"], "RQ_CHIP_QTY")

    assert_unique_keys(prepared_yield, YIELD_KEYS, "RQ_YLD 연결 키가")
    assert_unique_keys(prepared_chip, CHIP_KEYS, "RQ_CHIP_QTY 연결 키가")

    expanded = prepared_plan.merge(
        prepared_chip,
        on=["제품정보", "Stack"],
        how="left",
        validate="many_to_many",
        indicator="_chip_merge",
    )
    chip_missing = expanded["_chip_merge"] != "both"
    exclusions = [_load_exclusion_rows(expanded.loc[chip_missing], "RQ_CHIP_QTY")]
    expanded = expanded.loc[~chip_missing].drop(columns="_chip_merge")

    calculation = expanded.merge(
        prepared_yield,
        on=YIELD_KEYS,
        how="left",
        validate="many_to_one",
        indicator="_yield_merge",
    )
    yield_missing = calculation["_yield_merge"] != "both"
    exclusions.append(_load_exclusion_rows(calculation.loc[yield_missing], "RQ_YLD"))
    calculation = calculation.loc[~yield_missing].drop(columns="_yield_merge")

    calculation, value_exclusions = _drop_rows_missing_values(
        calculation,
        (("RQ_CHIP_QTY", ["구분_Chip", "Net Die"]), ("RQ_YLD", YIELD_VALUE_COLUMNS)),
    )
    exclusions.extend(value_exclusions)

    _validate_yield_range(calculation, "RQ_YLD", fix_hint=YIELD_RANGE_FIX_HINT)
    if calculation["Net Die"].le(0).any():
        raise ValueError("Net Die는 0보다 커야 합니다.")
    if calculation["구분_Chip"].lt(0).any():
        raise ValueError("구분_Chip은 0 이상이어야 합니다.")

    calculation.attrs[LOAD_EXCLUSIONS_ATTR] = _merge_load_exclusions(exclusions)
    return calculation


def _drop_rows_missing_values(
    calculation: pd.DataFrame,
    sources: Sequence[tuple[str, Sequence[str]]],
) -> tuple[pd.DataFrame, list[tuple[tuple[object, ...], ...]]]:
    """기준정보 행은 붙었는데 **칸이 비어 있는** 계획 행을 조인 실패와 같이 취급한다.

    조인은 성공했으므로 위의 `_chip_merge`·`_yield_merge` 에 걸리지 않는다. 그대로 두면
    수율·Net Die 가 NaN 인 채 곱셈을 지나 부하량이 NaN 이 되고, 뒤의 `groupby().sum()` 이
    그것을 0 으로 접는다. 소요대수가 조용히 적게 나오고 확보율은 그만큼 낙관 쪽으로 틀어지는데
    화면에는 아무 흔적도 남지 않는다.

    예외를 던지지 않는 이유는 위 `LOAD_EXCLUSIONS_ATTR` 주석과 같다 — 계획 행 하나 때문에
    페이지 전체가 멈추면 안 된다. 대신 왜 빠졌는지 목록으로 남긴다.
    """
    groups: list[tuple[tuple[object, ...], ...]] = []
    missing_any = pd.Series(False, index=calculation.index)
    for table_name, columns in sources:
        missing = calculation[list(columns)].isna().any(axis=1)
        if not missing.any():
            continue
        groups.append(_load_exclusion_rows(calculation.loc[missing], f"{table_name} 값 없음"))
        missing_any |= missing
    if not missing_any.any():
        return calculation, groups
    return calculation.loc[~missing_any].copy(), groups


def _load_exclusion_rows(
    unmatched: pd.DataFrame, table_name: str
) -> tuple[tuple[object, ...], ...]:
    """조인에 실패한 계획 행을 "무엇이 없어서 빠졌는지" 레코드로 정리한다."""
    if unmatched.empty:
        return ()
    columns = [column for column in LOAD_EXCLUSION_COLUMNS[:-1] if column in unmatched.columns]
    rows = unmatched[columns].drop_duplicates()
    return tuple(
        (*(record.get(column) for column in LOAD_EXCLUSION_COLUMNS[:-1]), table_name)
        for record in rows.to_dict("records")
    )


def _merge_load_exclusions(
    groups: list[tuple[tuple[object, ...], ...]],
) -> tuple[tuple[object, ...], ...]:
    merged: list[tuple[object, ...]] = []
    seen: set[tuple[object, ...]] = set()
    for group in groups:
        for row in group:
            # 순서는 화면에 그대로 나가므로 유지하고, 중복 판정만 집합으로 한다.
            # 리스트 `in` 은 행 수의 제곱이라 기준정보가 통째로 빠진 배포에서 목이 됐다.
            if row in seen:
                continue
            seen.add(row)
            merged.append(row)
    return tuple(merged)


def calculate_chip_load(
    plan: pd.DataFrame,
    yield_data: pd.DataFrame,
    chip_qty: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate Top/Core/Buffer/Slave/Master and Dummy chip volume in Kea."""
    return _calculate_chip_load_from_base(_prepare_load_base(plan, yield_data, chip_qty))


def calculate_chip_and_wafer_loads(
    plan: pd.DataFrame,
    yield_data: pd.DataFrame,
    chip_qty: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calculate Chip and Wafer loads from one shared validated join result."""
    calculation = _prepare_load_base(plan, yield_data, chip_qty)
    return (
        _calculate_chip_load_from_base(calculation),
        _calculate_wafer_load_from_base(calculation),
    )


def carry_load_exclusions(source: pd.DataFrame, target: pd.DataFrame) -> pd.DataFrame:
    """제외 목록을 결과 프레임에 이어붙인다. pandas 연산에서 attrs 는 쉽게 사라진다."""
    target.attrs[LOAD_EXCLUSIONS_ATTR] = source.attrs.get(LOAD_EXCLUSIONS_ATTR, ())
    return target


def load_exclusions(data: pd.DataFrame) -> pd.DataFrame:
    """기준정보가 없어 계산에서 빠진 계획 행 목록을 표로 돌려준다."""
    excluded = data.attrs.get(LOAD_EXCLUSIONS_ATTR)
    if not excluded:
        return pd.DataFrame(columns=LOAD_EXCLUSION_COLUMNS)
    return pd.DataFrame(list(excluded), columns=LOAD_EXCLUSION_COLUMNS)


def _dummy_mask(calculation: pd.DataFrame) -> pd.Series:
    """Dummy 산식을 받을 행을 (제품타입, WF 구분) 으로 고른다.

    `WF 구분` 만 보고 고르면 두 제품군이 공유하는 이름 때문에 한쪽 규칙이 다른 쪽에
    적용된다. 지금은 Dummy 가 HBM 에만 있어 결과가 같지만, 규칙을 이름 하나에 걸어 두면
    나중에 EDP 쪽 규칙을 넣을 때 HBM 이 조용히 따라 움직인다.

    `제품타입` 이 없는 프레임(제품타입 도입 이전 경로)은 예전처럼 이름만 보고 고른다.
    """
    division = match_key(calculation["WF 구분"])
    if PRODUCT_TYPE_COLUMN not in calculation.columns:
        declared = {
            scalar_match_key(name)
            for names in DUMMY_DIVISIONS_BY_PRODUCT_TYPE.values()
            for name in names
        }
        return division.isin(declared).fillna(False)

    # 제품타입도 대소문자를 가리지 않는다. `WF 구분` 만 흡수하고 제품타입은 글자 그대로
    # 맞추면, 원천 표기가 한 글자만 달라도 Dummy 규칙이 통째로 빗나간다.
    product_type = match_key(product_type_of(calculation))
    mask = pd.Series(False, index=calculation.index)
    for declared_type, dummy_divisions in DUMMY_DIVISIONS_BY_PRODUCT_TYPE.items():
        if not dummy_divisions:
            continue
        names = {scalar_match_key(name) for name in dummy_divisions}
        mask |= product_type.eq(scalar_match_key(declared_type)) & division.isin(names).fillna(
            False
        )
    return mask


def _calculate_chip_load_from_base(load_base: pd.DataFrame) -> pd.DataFrame:
    calculation = load_base.copy()
    calculation["물량"] = (
        calculation["생산수량"] * calculation["구분_Chip"] / calculation["BE_수율"]
    )
    is_dummy = _dummy_mask(calculation)
    calculation.loc[is_dummy, "물량"] = (
        calculation.loc[is_dummy, "생산수량"]
        * calculation.loc[is_dummy, "구분_Chip"]
        / calculation.loc[is_dummy, "EDS_수율"]
        / calculation.loc[is_dummy, "BE_수율"]
        * (1 - calculation.loc[is_dummy, "EDS_수율"])
    )
    return carry_load_exclusions(load_base, calculation)


def calculate_wafer_load(
    plan: pd.DataFrame,
    yield_data: pd.DataFrame,
    chip_qty: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate regular and Dummy wafer volume in sheets."""
    return _calculate_wafer_load_from_base(_prepare_load_base(plan, yield_data, chip_qty))


def _calculate_wafer_load_from_base(load_base: pd.DataFrame) -> pd.DataFrame:
    calculation = load_base.copy()
    calculation["물량"] = (
        calculation["생산수량"]
        * 1_000
        * calculation["구분_Chip"]
        / calculation["EDS_수율"]
        / calculation["BE_수율"]
        / calculation["Net Die"]
    )
    is_dummy = _dummy_mask(calculation)
    calculation.loc[is_dummy, "물량"] *= 1 - calculation.loc[is_dummy, "EDS_수율"]
    return carry_load_exclusions(load_base, calculation)


def calculate_density_load(plan: pd.DataFrame, density_data: pd.DataFrame) -> pd.DataFrame:
    """Calculate product density by capacity-bearing WF type in 100M Gb."""
    prepared_plan = _prepare_plan(plan)
    require_columns(density_data, DENSITY_REQUIRED_COLUMNS, "RQ_CHIP_EQ")

    prepared_density = _normalize_text(density_data[DENSITY_REQUIRED_COLUMNS], DENSITY_KEYS)
    prepared_density = _to_numeric(prepared_density, ["구분_Chip", "구분_EQ"], "RQ_CHIP_EQ")

    if prepared_density[DENSITY_KEYS].isna().any(axis=None):
        raise ValueError("RQ_CHIP_EQ의 연결 키에 누락값이 있습니다.")
    assert_unique_keys(prepared_density, DENSITY_KEYS, "RQ_CHIP_EQ 연결 키가")

    calculation = prepared_plan.merge(
        prepared_density,
        on=["제품정보", "Stack"],
        how="left",
        validate="many_to_many",
        indicator="_density_merge",
    )
    # Chip·Wafer 경로와 같은 처리다. 예전에는 여기서 예외를 던져 계획 행 하나 때문에
    # Density 환산은 물론 HOME 대시보드까지 통째로 멈췄다. 용량이 발생하지 않는 제품이나
    # `구분_EQ` 미등록 신규 제품이 계획에 한 줄만 들어와도 그렇게 된다.
    density_missing = calculation["_density_merge"] != "both"
    exclusions = [_load_exclusion_rows(calculation.loc[density_missing], "RQ_CHIP_EQ")]
    calculation = calculation.loc[~density_missing].drop(columns="_density_merge")

    # 빈 칸도 Chip·Wafer 경로와 같이 제외 목록으로 내린다.
    calculation, value_exclusions = _drop_rows_missing_values(
        calculation, (("RQ_CHIP_EQ", ["구분_Chip", "구분_EQ"]),)
    )
    exclusions.extend(value_exclusions)

    # **0 이하는 제외가 아니라 오류로 둔다.** 0 은 「없는 값」이 아니라 있는 값이라
    # `값 없음` 사유로 적으면 라벨이 거짓이 되고, 곱셈 항이라 빼도 합계가 그대로여서
    # 「줄어든 만큼은 제외 목록에 있다」가 헐거워진다. 다만 **조인 뒤로** 옮긴다 —
    # 계획에 없는 제품의 기준정보 한 줄 때문에 화면이 멈추던 것이 그 자리였다.
    for column in ("구분_Chip", "구분_EQ"):
        if calculation[column].le(0).any():
            raise ValueError(f"RQ_CHIP_EQ.{column}은 0보다 커야 합니다.")

    calculation["물량"] = (
        calculation["생산수량"] * calculation["구분_Chip"] * calculation["구분_EQ"] / 100_000
    )
    calculation.attrs[LOAD_EXCLUSIONS_ATTR] = _merge_load_exclusions(exclusions)
    return calculation


def _pivot_monthly(
    data: pd.DataFrame,
    detailed: bool,
    display_order: DisplayOrderInput = None,
) -> pd.DataFrame:
    classification_columns = [*CLASSIFICATION_COLUMNS]
    if detailed:
        classification_columns.append("WF 구분")
    grouped = (
        data.groupby(["생산계획년월", *classification_columns], as_index=False, dropna=False)[
            ["물량"]
        ]
        .sum()
        .sort_values([*classification_columns, "생산계획년월"])
    )
    pivoted = grouped.pivot(
        index=classification_columns,
        columns="생산계획년월",
        values="물량",
    ).fillna(0)
    pivoted.columns = [str(int(month)) for month in pivoted.columns]
    return apply_display_order(pivoted.reset_index(), display_order, PAGE_PLAN, TAB_CONVERSION)


def build_monthly_volume(
    plan: pd.DataFrame,
    yield_data: pd.DataFrame,
    chip_qty: pd.DataFrame,
    demand_basis: DemandBasis,
    detailed: bool = False,
    density_data: pd.DataFrame | None = None,
    display_order: DisplayOrderInput = None,
) -> pd.DataFrame:
    """Return a monthly matrix grouped by production class, product, and stack."""
    prepared_plan = _prepare_plan(plan)
    if demand_basis == "PKG":
        volume = prepared_plan.rename(columns={"생산수량": "물량"})
        if detailed:
            volume["WF 구분"] = "PKG"
        return _pivot_monthly(volume, detailed, display_order)
    if demand_basis == "Chip":
        chip_load = calculate_chip_load(prepared_plan, yield_data, chip_qty)
        return carry_load_exclusions(chip_load, _pivot_monthly(chip_load, detailed, display_order))
    if demand_basis == "Wafer":
        wafer_load = calculate_wafer_load(prepared_plan, yield_data, chip_qty)
        return carry_load_exclusions(
            wafer_load, _pivot_monthly(wafer_load, detailed, display_order)
        )
    if demand_basis == "Density":
        if density_data is None:
            raise ValueError("Density 계산에 RQ_CHIP_EQ 기준정보가 필요합니다.")
        density_load = calculate_density_load(prepared_plan, density_data)
        return carry_load_exclusions(
            density_load, _pivot_monthly(density_load, detailed, display_order)
        )
    raise ValueError(f"지원하지 않는 소요기준입니다: {demand_basis}")


def filter_edp_plan(plan: pd.DataFrame, include_edp: bool) -> pd.DataFrame:
    """EDP 토글이 꺼져 있는 동안 `제품타입` 이 EDP-TSV 인 계획 행을 환산에서 뺀다.

    **판별은 `제품타입` 이다** (2026-09-05 확인). 예전에는 `제품정보` 에 `DDR` 이 들어
    있는지로 판별했는데, 그것은 개발 표본에서 EDP-TSV 제품이 `A1a-DDR5` 하나뿐이라
    우연히 맞아떨어진 것이었다. 실제로 EDP-TSV 제품명에는 전부 DDR4 또는 DDR5 가
    들어 있지만, 그 반대(이름에 DDR 이 든 비-EDP 제품)는 보장되지 않는다. 제품군을 정하는
    것은 이름이 아니라 `제품타입` 컬럼이다.

    토글이 켜져 있으면 아무것도 가리지 않으므로 판별 자체가 필요 없다. 그래서 컬럼 요구도
    그때는 하지 않는다 — 판단이 필요한 순간에만 근거를 요구한다.
    """
    if include_edp:
        return plan.copy()
    require_columns(plan, [PRODUCT_TYPE_COLUMN], "RQ_PKG_PLAN")
    product_type = product_type_of(plan)
    unknown = product_type.isna() | product_type.eq("")
    if unknown.any():
        examples = sorted(
            {str(value) for value in plan.loc[unknown, "제품정보"].dropna().unique()[:5]}
        )
        raise ValueError(
            "제품타입이 비어 있어 EDP 여부를 판단할 수 없습니다"
            f"({unknown.sum()}행, 예: {', '.join(examples) or '제품정보 없음'}). "
            "기준정보를 다시 등록하거나 EDP 를 포함해 조회하세요."
        )
    # 같은 파일의 `_dummy_mask` 와 같은 규칙으로 맞춘다. 한쪽은 대소문자를 가리지 않고
    # 다른 쪽은 글자 그대로 맞추면, 같은 행이 Dummy 판정에서는 EDP 고 토글에서는 아니다.
    # 위의 빈값 가드는 `product_type` 원본을 그대로 본다 — `match_key` 는 빈 값을 빈
    # 문자열로 내리므로 `isna()` 분기가 영영 거짓이 된다.
    return plan.loc[match_key(product_type).ne(scalar_match_key(EDP_PRODUCT_TYPE))].copy()
