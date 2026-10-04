# Purpose: 적재 시점 이전 과거 구간 입력값의 정규화·검증과 CSV·붙여넣기 직렬화를 담당한다.

"""과거 구간 공용 프로필.

DB 에 적재되는 원천은 적재 시점 이후의 달만 담는다. 그래서 지난 해를 함께 보려면 그 구간을
따로 넣어야 한다. 과거는 이미 끝난 값이라 불변이므로 시나리오 리비전이 아니라 공용
프로필에 둔다.

**산출하지 않는다.** 여기 들어오는 값은 화면을 채우는 데 필요한 최소한이고, 나머지는 그
값들에서 곧장 나온다 — `Wafer Capa = Wafer Total × 확보율`, `B/N Capa = Density × 확보율`,
B/N 순위는 확보율 오름차순이다. 그래서 공정명을 따로 받지 않는다. 공정별 확보율 표가
공정명을 이미 갖고 있다.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype

from capa_simulation.services.clipboard_table import parse_clipboard_table
from capa_simulation.services.display_order import DisplayOrderInput, apply_display_order
from capa_simulation.services.display_order_scopes import (
    PAGE_PLAN,
    TAB_PKG_PLAN,
)
from capa_simulation.services.frame_contracts import require_exact_columns
from capa_simulation.services.month_columns import month_label

PAST_MONTH_COLUMNS = ("생산계획년월", "Density", "Wafer Total")
PAST_DETAIL_COLUMNS = ("생산계획년월", "제품정보", "Stack", "Customer", "생산수량")
PAST_SECUREMENT_COLUMNS = ("생산계획년월", "공정", "확보율")

_TEXT_COLUMNS = {"제품정보", "Stack", "Customer", "공정"}
_KEY_COLUMNS = {
    PAST_MONTH_COLUMNS: ["생산계획년월"],
    PAST_DETAIL_COLUMNS: ["생산계획년월", "제품정보", "Stack", "Customer"],
    PAST_SECUREMENT_COLUMNS: ["생산계획년월", "공정"],
}
_TABLE_NAMES = {
    PAST_MONTH_COLUMNS: "과거 월별 실적",
    PAST_DETAIL_COLUMNS: "과거 계획 세부수량",
    PAST_SECUREMENT_COLUMNS: "과거 공정별 확보율",
}
# 값 칸의 빈칸을 무엇으로 읽는가 — 컬럼마다 따로 정한다(2026-09-29 빈칸 횡전개).
#  - `생산수량`(계획 세부수량): 빈칸 = 0. 거래선 행을 합쳐 접을 때 빈칸과 0 의 합계가 같다.
#  - `Density`·`Wafer Total`·`확보율`: 빈칸을 **막는다.** 0 으로 읽으면 그 달의 B/N Capa·
#    Wafer Capa 가 0 이 되고, 확보율은 그 공정이 그 달 B/N 1위가 된다 — 오류 없이 비관 쪽으로
#    틀린다. DB 도 세 컬럼 모두 NOT NULL 이다(0019).
# 숫자로 못 읽는 글자(`105%`·`180,000`)는 어느 컬럼이든 막는다. 새 값 컬럼을 더하면 여기에
# 규칙을 적어야 읽힌다(없으면 KeyError).
_BLANK_AS_ZERO: dict[str, bool] = {
    "Density": False,
    "Wafer Total": False,
    "생산수량": True,
    "확보율": False,
}
# 못 읽는 칸 예시는 이만큼만 적는다. 사용자가 어느 행인지 찾을 수 있으면 된다.
_EXAMPLE_LIMIT = 3


def empty_past_table(columns: tuple[str, ...]) -> pd.DataFrame:
    """아직 아무것도 넣지 않은 정상 상태의 빈 프레임."""
    return pd.DataFrame(
        {
            column: pd.Series(dtype="object" if column in _TEXT_COLUMNS else "float64")
            for column in columns
        }
    )


def _read_numbers(raw: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    """칸을 숫자로 읽어 (숫자, 빈칸, 못 읽은 칸) 을 돌려준다.

    `pd.to_numeric(errors="coerce")` 만 쓰면 못 읽는 글자가 빈칸과 똑같은 결측이 되어 「비워
    둔 칸」과 「`105%`·`180,000` 처럼 적은 칸」을 가를 수 없다. 그래서 원문이 비었는지를
    먼저 본다. 앞뒤 공백(줄바꿈 없는 공백 포함)은 지우고 읽는다.

    DB 에서 읽은 표처럼 이미 숫자인 컬럼은 결측만 빈칸으로 본다. 불러오기가 예외를 내면
    HOME 이 열리지 않는데, 0019 가 값 컬럼을 모두 NOT NULL 로 두어 저장된 표는 여기서 막히지
    않는다.
    """
    if is_numeric_dtype(raw):
        numbers = raw.astype("float64")
        return numbers, numbers.isna(), pd.Series(False, index=raw.index)
    text = raw.astype("string").str.strip().fillna("")
    blank = text.eq("").astype(bool)
    numbers = pd.to_numeric(text.astype(object).where(~blank), errors="coerce").astype("float64")
    # `inf`·`1e400` 도 글자로는 숫자지만 값으로는 못 쓴다.
    unreadable = ~blank & ~pd.Series(np.isfinite(numbers.to_numpy()), index=raw.index)
    return numbers, blank, unreadable


def _row_examples(
    frame: pd.DataFrame,
    mask: pd.Series,
    labels: list[str],
    detail: pd.Series | None = None,
) -> str:
    """막힌 행 몇 개를 「키 · 키 → 무엇」 꼴로 적는다. 사용자가 Excel 에서 그 행을 찾는 글이다."""
    lines: list[str] = []
    for position in mask[mask].index[:_EXAMPLE_LIMIT]:
        line = " · ".join(str(frame.at[position, column]) for column in labels)
        lines.append(line if detail is None else f"{line} → {detail.at[position]}")
    rest = int(mask.sum()) - len(lines)
    return "; ".join(lines) + (f" 외 {rest}행" if rest > 0 else "")


def _quoted(raw: pd.Series) -> pd.Series:
    """사용자가 적은 원문 그대로를 따옴표로 감싼다."""
    return raw.astype("string").fillna("").map(lambda value: f"'{value}'")


def _read_months(
    prepared: pd.DataFrame, keys: list[str], table_name: str
) -> tuple[pd.Series, pd.Series]:
    """생산계획년월을 (숫자, 빈 행) 으로 읽는다. 비어 있지 않은데 못 읽으면 막는다.

    `25.11`·`202511.5` 는 숫자로는 읽히지만 정수로 자르면 다른 달이 되므로 함께 막는다.
    """
    raw = prepared["생산계획년월"]
    months, blank, unreadable = _read_numbers(raw)
    unreadable = unreadable | (~blank & months.mod(1).ne(0))
    if unreadable.any():
        labelled = prepared.assign(**{"생산계획년월": _quoted(raw)})
        raise ValueError(
            f"{table_name}의 생산계획년월을 YYYYMM 숫자로 읽을 수 없습니다: "
            f"{_row_examples(labelled, unreadable, keys)}. "
            "`202511` 처럼 여섯 자리 숫자로 적으세요 — `2025-11`·`2025/11`·날짜 서식은 받지 "
            "않습니다. 못 읽는 행을 빼고 읽으면 저장할 때 그 행이 지워집니다."
        )
    return months, blank


def _drop_blank_month_rows(
    prepared: pd.DataFrame, blank_months: pd.Series, table_name: str
) -> pd.DataFrame:
    """년월이 빈 행을 가른다 — **모든 칸이 빈 행만** 떨구고, 다른 칸이 찬 행은 막는다.

    Excel 에서 년월 셀을 병합한 표(첫 행에만 `202511`, 이어진 행은 빈칸)를 붙여넣으면 이어진
    행은 값·분류가 다 있는데 년월만 빈다. 그 행을 떨구면 「N행을 읽었습니다」 뒤 저장이 그 행을
    표에서 지운다 — 확보율이면 B/N 1위가 말없이 바뀐다(2026-09-29 리뷰). 어느 달인지 알 수
    없으니 추측해 채우지도 않는다.
    """
    others = [column for column in prepared.columns if column != "생산계획년월"]
    filled = pd.Series(False, index=prepared.index)
    for column in others:
        if column in _TEXT_COLUMNS:
            filled |= prepared[column].ne("")
        else:
            filled |= ~_read_numbers(prepared[column])[1]
    orphan = blank_months & filled
    if orphan.any():
        labelled = prepared.assign(**{"생산계획년월": ""}).astype("string")
        labelled = labelled.apply(lambda column: column.str.strip()).fillna("")
        labelled = labelled.mask(labelled.eq(""), "빈칸")
        raise ValueError(
            f"{table_name}에 생산계획년월이 빈 행이 {int(orphan.sum()):,}개 있습니다: "
            f"{_row_examples(labelled, orphan, list(prepared.columns))}. Excel 에서 년월 셀을 "
            "병합했다면 병합을 풀고 모든 행에 년월을 채워 다시 붙여넣으세요 — 년월 없는 행을 빼고 "
            "읽으면 저장할 때 그 행이 지워집니다."
        )
    return prepared.loc[~blank_months].copy()


def _value_rule(column: str, *, unreadable_text: bool, blank_refused: bool) -> str:
    """값 칸 오류 문구 끝의 안내 — 막힌 까닭에 맞는 것만 적는다."""
    rules: list[str] = []
    if unreadable_text:
        rules.append(
            "천 단위 쉼표 없이 숫자만 적으세요(`180,000` → `180000`) — 쉼표는 지역 설정마다 천 "
            "단위인지 소수점인지 달라 받지 않습니다."
        )
        if column == "확보율":
            rules.append("확보율은 소수로 적습니다(`105%` → `1.05`).")
    if blank_refused:
        consequence = {
            "Density": "그 달 B/N Capa 가 0 이 됩니다",
            "Wafer Total": "그 달 Wafer Capa 가 0 이 됩니다",
            "확보율": "그 공정이 그 달 B/N 1위가 되고 B/N Capa 가 0 이 됩니다",
        }[column]
        rules.append(
            f"빈칸은 0 으로 읽지 않습니다 — 0 이면 {consequence}. 값이 없는 달은 그 행을 빼고 "
            "붙여넣으세요."
        )
    return " ".join(rules)


def _read_values(
    prepared: pd.DataFrame, column: str, keys: list[str], table_name: str
) -> pd.Series:
    """값 칸 하나를 `_BLANK_AS_ZERO` 규칙대로 읽는다. 막히는 칸은 행 예시와 함께 알린다."""
    raw = prepared[column]
    values, blank, unreadable = _read_numbers(raw)
    blank_refused = blank & (not _BLANK_AS_ZERO[column])
    refused = unreadable | blank_refused
    if refused.any():
        detail = _quoted(raw).where(~blank, "빈칸")
        rule = _value_rule(
            column,
            unreadable_text=bool(unreadable.any()),
            blank_refused=bool(blank_refused.any()),
        )
        raise ValueError(
            f"{table_name}의 {column} 칸을 숫자로 읽을 수 없습니다: "
            f"{_row_examples(prepared, refused, keys, detail)}. {rule}"
        )
    return values.fillna(0.0).astype("float64")


def prepare_past_table(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    """저장·계산 공용 정규화. 컬럼 계약과 키 중복을 검사한다.

    빈 문자열로 들어온 분류값은 빈 칸 그대로 둔다. `Stack` 이나 `Customer` 가 없는 과거
    자료가 있을 수 있고, 그것을 막으면 넣을 방법이 사라진다. 중복만 막는다 — 같은 키가
    두 번 들어오면 어느 값이 맞는지 알 수 없다.

    **못 읽는 칸을 말없이 버리거나 0 으로 만들지 않는다**(2026-09-29 빈칸 횡전개). 저장은
    그 표를 지우고 다시 넣으므로, 붙여넣기에서 떨어진 행은 저장하는 순간 사라진다.
    - **모든 칸이 빈** 행만 떨군다. 년월만 빈 행(Excel 병합 셀)과 비어 있지 않은데 `YYYYMM`
      숫자로 못 읽는 행(`2025-11`·`2025/11`·`2025-11-01`·`25.11`)은 예시와 함께 막는다.
    - 값 칸의 빈칸은 `_BLANK_AS_ZERO` 가 컬럼마다 정한 대로 읽고, 숫자로 못 읽는 글자는 막는다.
    """
    table_name = _TABLE_NAMES[columns]
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{table_name}은(는) pandas DataFrame이어야 합니다.")
    require_exact_columns(frame.columns, columns, f"{table_name} 컬럼")
    if frame.empty:
        return empty_past_table(columns)
    prepared = frame.loc[:, list(columns)].copy()
    for column in columns:
        if column in _TEXT_COLUMNS:
            prepared[column] = prepared[column].astype("string").fillna("").str.strip()
    keys = _KEY_COLUMNS[columns]
    months, blank_months = _read_months(prepared, keys, table_name)
    prepared = _drop_blank_month_rows(prepared, blank_months, table_name)
    prepared["생산계획년월"] = months.loc[prepared.index]
    if prepared.empty:
        return empty_past_table(columns)
    prepared["생산계획년월"] = prepared["생산계획년월"].astype("int64")
    invalid = ~prepared["생산계획년월"].mod(100).between(1, 12)
    if invalid.any():
        examples = sorted({int(value) for value in prepared.loc[invalid, "생산계획년월"]})[:5]
        raise ValueError(
            f"{table_name}의 생산계획년월이 YYYYMM 형식이 아닙니다: {', '.join(map(str, examples))}"
        )
    value_columns = [
        column for column in columns if column != "생산계획년월" and column not in _TEXT_COLUMNS
    ]
    for column in value_columns:
        prepared[column] = _read_values(prepared, column, keys, table_name)
    duplicated = prepared.duplicated(subset=keys)
    if duplicated.any():
        first = prepared.loc[duplicated, keys].astype("string").agg(" · ".join, axis=1)
        raise ValueError(
            f"{table_name}에 같은 키가 두 번 들어 있습니다: {', '.join(first.head(5))}"
        )
    if "제품정보" in columns:
        blank = prepared["제품정보"].eq("")
        if blank.any():
            raise ValueError(f"{table_name}의 제품정보는 비어 있을 수 없습니다.")
    if "공정" in columns:
        blank = prepared["공정"].eq("")
        if blank.any():
            raise ValueError(f"{table_name}의 공정은 비어 있을 수 없습니다.")
    return prepared.sort_values(keys).reset_index(drop=True)


def past_table_to_csv(frame: pd.DataFrame, columns: tuple[str, ...]) -> bytes:
    """수정 없이 그대로 다시 붙여넣을 수 있는 UTF-8 CSV."""
    return prepare_past_table(frame, columns).to_csv(index=False).encode("utf-8-sig")


def past_table_from_clipboard(content: str, columns: tuple[str, ...]) -> pd.DataFrame:
    """Excel 에서 복사한 머리글 포함 표를 읽는다.

    **읽은 행이 없으면 막는다**(2026-09-29 리뷰). 저장은 표를 통째로 바꾸므로 0행을 대기로
    쌓으면 저장 한 번에 그 표가 비워진다 — 머리글만 복사했거나 행이 모두 빈 붙여넣기다. 표를
    비우는 기능은 따로 두지 않았다.
    """
    table_name = _TABLE_NAMES[columns]
    parsed = parse_clipboard_table(content, table_name)
    prepared = prepare_past_table(parsed, columns)
    if prepared.empty:
        raise ValueError(
            f"{table_name} 붙여넣기에서 읽은 행이 없습니다. 머리글 아래 데이터 행까지 함께 "
            "복사하세요 — 0행을 저장하면 저장된 표가 통째로 지워지므로 받지 않습니다."
        )
    return prepared


def past_sample_rows(columns: tuple[str, ...]) -> pd.DataFrame:
    """양식에 넣을 예시 한두 행. 빈 양식만 주면 무엇을 어떤 단위로 적을지 알 수 없다."""
    if columns == PAST_MONTH_COLUMNS:
        return pd.DataFrame(
            {
                "생산계획년월": [202601, 202602],
                "Density": [12.34, 13.05],
                "Wafer Total": [180_000.0, 190_000.0],
            }
        )
    if columns == PAST_DETAIL_COLUMNS:
        return pd.DataFrame(
            {
                "생산계획년월": [202601, 202601],
                "제품정보": ["DEMO-A", "DEMO-A"],
                "Stack": ["12H", "12H"],
                "Customer": ["DEMO-CUST-1", "DEMO-CUST-2"],
                "생산수량": [1_200.0, 800.0],
            }
        )
    return pd.DataFrame(
        {
            "생산계획년월": [202601, 202601],
            "공정": ["DEMO_PROCESS_A", "DEMO_PROCESS_B"],
            "확보율": [1.05, 1.32],
        }
    )


def merge_past_months(
    calculated: pd.DataFrame,
    past: pd.DataFrame,
    *,
    value_columns: dict[str, str],
    start_month: int,
    end_month: int,
) -> pd.DataFrame:
    """계산 결과에 없는 달만 과거 입력으로 채운다.

    같은 달이 양쪽에 있으면 **계산이 이긴다.** 적재 범위가 뒤로 넘어가면 그 달은 자연히
    실데이터로 갈리고 과거 입력은 손대지 않은 채 남는다 — 적재가 밀릴 때마다 입력을
    지워야 실데이터가 보이는 구조는 오래 못 간다.

    `value_columns` 는 과거 표의 컬럼을 계산 표의 컬럼으로 옮기는 이름표다.
    """
    if "생산계획년월" not in calculated.columns:
        raise ValueError("계산 결과에 `생산계획년월` 컬럼이 없습니다.")
    prepared = prepare_past_table(past, PAST_MONTH_COLUMNS)
    in_range = prepared.loc[prepared["생산계획년월"].between(start_month, end_month)]
    calculated_months = {
        int(value) for value in pd.to_numeric(calculated["생산계획년월"], errors="coerce").dropna()
    }
    fresh = in_range.loc[~in_range["생산계획년월"].isin(calculated_months)]
    if fresh.empty:
        return calculated.copy()
    added = pd.DataFrame({"생산계획년월": fresh["생산계획년월"].to_numpy()})
    for past_column, target_column in value_columns.items():
        added[target_column] = fresh[past_column].to_numpy()
    added["년월"] = [month_label(int(value)) for value in added["생산계획년월"]]
    merged = pd.concat([calculated, added], ignore_index=True)
    return merged.sort_values("생산계획년월", kind="stable").reset_index(drop=True)


def merge_past_frame(
    calculated: pd.DataFrame,
    past: pd.DataFrame,
    *,
    start_month: int,
    end_month: int,
) -> pd.DataFrame:
    """월 컬럼을 그대로 가진 표(확보율 등)를 같은 규칙으로 합친다."""
    if past.empty:
        return calculated.copy()
    in_range = past.loc[past["생산계획년월"].between(start_month, end_month)]
    calculated_months = {
        int(value) for value in pd.to_numeric(calculated["생산계획년월"], errors="coerce").dropna()
    }
    fresh = in_range.loc[~in_range["생산계획년월"].isin(calculated_months)]
    if fresh.empty:
        return calculated.copy()
    return pd.concat([calculated, fresh], ignore_index=True)


def past_plan_detail_to_wide(
    past_detail: pd.DataFrame,
    dimensions: list[str],
    *,
    start_month: int,
    end_month: int,
    exclude_months: set[int],
) -> pd.DataFrame:
    """과거 계획 세부수량을 화면 표와 같은 Wide 모양으로 편다.

    분류에 `Customer` 가 없으면 거래선을 합쳐 접는다. 화면이 제품·Stack 으로만 볼 때
    거래선별 행이 그대로 남으면 같은 제품이 여러 줄로 갈린다.
    """
    prepared = prepare_past_table(past_detail, PAST_DETAIL_COLUMNS)
    in_range = prepared.loc[
        prepared["생산계획년월"].between(start_month, end_month)
        & ~prepared["생산계획년월"].isin(exclude_months)
    ]
    if in_range.empty:
        return pd.DataFrame(columns=[*dimensions])
    grouped = in_range.groupby([*dimensions, "생산계획년월"], as_index=False, dropna=False)[
        "생산수량"
    ].sum()
    grouped["년월"] = [month_label(int(value)) for value in grouped["생산계획년월"]]
    wide: pd.DataFrame = grouped.pivot(
        index=dimensions, columns="년월", values="생산수량"
    ).reset_index()
    wide.columns.name = None
    return wide


def merge_past_plan_detail(
    production_detail: pd.DataFrame,
    past_detail: pd.DataFrame,
    dimensions: list[str],
    display_order: DisplayOrderInput = None,
) -> pd.DataFrame:
    """계획 세부수량에 과거 구간 열을 붙이고 화면 표시순서를 다시 세운다.

    **`groupby` 의 기본 정렬을 쓰지 않는다.** 기본값(`sort=True`)은 그룹 키로 다시 정렬하는데,
    들어온 표는 이미 `apply_display_order` 로 사용자가 정한 차례를 갖고 있다. 그대로 두면
    과거를 넣는 순간 제품 차례가 가나다순으로 뒤집힌다.

    `sort=False` 만으로는 과거에만 있는 분류가 맨 뒤에 붙는다. 표시순서를 한 번 더 세워
    그 행도 제자리에 놓는다.
    """
    if past_detail.empty:
        return production_detail
    merged = (
        pd.concat([production_detail, past_detail], ignore_index=True)
        .groupby(dimensions, as_index=False, dropna=False, sort=False)
        .sum(numeric_only=True)
        .reset_index(drop=True)
    )
    return apply_display_order(merged, display_order, PAGE_PLAN, TAB_PKG_PLAN)
