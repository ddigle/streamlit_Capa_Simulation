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

import pandas as pd

from capa_simulation.services.clipboard_table import parse_clipboard_table
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


def empty_past_table(columns: tuple[str, ...]) -> pd.DataFrame:
    """아직 아무것도 넣지 않은 정상 상태의 빈 프레임."""
    return pd.DataFrame(
        {
            column: pd.Series(dtype="object" if column in _TEXT_COLUMNS else "float64")
            for column in columns
        }
    )


def prepare_past_table(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    """저장·계산 공용 정규화. 컬럼 계약과 키 중복을 검사한다.

    빈 문자열로 들어온 분류값은 빈 칸 그대로 둔다. `Stack` 이나 `Customer` 가 없는 과거
    자료가 있을 수 있고, 그것을 막으면 넣을 방법이 사라진다. 중복만 막는다 — 같은 키가
    두 번 들어오면 어느 값이 맞는지 알 수 없다.
    """
    table_name = _TABLE_NAMES[columns]
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{table_name}은(는) pandas DataFrame이어야 합니다.")
    missing = [column for column in columns if column not in frame.columns]
    extra = [column for column in frame.columns if column not in columns]
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append(f"누락: {', '.join(missing)}")
        if extra:
            details.append(f"추가: {', '.join(str(column) for column in extra)}")
        raise ValueError(f"{table_name} 컬럼 계약이 일치하지 않습니다 ({'; '.join(details)}).")
    if frame.empty:
        return empty_past_table(columns)
    prepared = frame.loc[:, list(columns)].copy()
    for column in columns:
        if column in _TEXT_COLUMNS:
            prepared[column] = prepared[column].astype("string").fillna("").str.strip()
        else:
            prepared[column] = pd.to_numeric(prepared[column], errors="coerce")
    prepared = prepared.dropna(subset=["생산계획년월"])
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
        prepared[column] = prepared[column].fillna(0.0).astype("float64")
    keys = _KEY_COLUMNS[columns]
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
    """Excel 에서 복사한 머리글 포함 표를 읽는다."""
    parsed = parse_clipboard_table(content, _TABLE_NAMES[columns])
    return prepare_past_table(parsed, columns)


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
